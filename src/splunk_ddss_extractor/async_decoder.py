"""
Async Splunk Journal Parser — high-performance version.

Mirrors JournalDecoder but accepts an async reader, enabling use in
async contexts (aioboto3 streams, aiofiles, etc.).

Buffer management is inlined directly into the decoder to eliminate
per-byte await overhead.  The only await points are _ensure() calls
(~one per 256 KB chunk) and the underlying reader.read().

Reuses Event, Opcode, Header, RMKI_TYPES, and all decode_*_from_bytes
helpers from the sync decoder module — no duplication of data structures.
"""

import logging
import struct
from typing import Dict, List, Optional

from .decoder import (
    Event,
    Opcode,
    RMKI_TYPES,
    decode_shifted_varint_from_bytes,
    decode_uvarint_from_bytes,
)

logger = logging.getLogger(__name__)

# Pre-computed frozenset for fast event-opcode membership test.
_EVENT_OPCODES = frozenset({Opcode.OLDSTYLE_EVENT, Opcode.OLDSTYLE_EVENT_WITH_HASH}
                           | set(range(32, 44)))

# Dispatch table keys (avoid repeated attribute lookups)
_OP_HEADER = int(Opcode.HEADER)
_OP_SPLUNK_PRIVATE = int(Opcode.SPLUNK_PRIVATE)
_OP_NEW_HOST = int(Opcode.NEW_HOST)
_OP_NEW_SOURCE = int(Opcode.NEW_SOURCE)
_OP_NEW_SOURCE_TYPE = int(Opcode.NEW_SOURCE_TYPE)
_OP_NEW_STRING = int(Opcode.NEW_STRING)

_READ_CHUNK = 262_144  # 256 KB read-ahead


class MetadataError(Exception):
    """Non-fatal metadata extraction error"""
    pass


class AsyncJournalDecoder:
    """Async Splunk journal decoder with inlined buffer management."""

    HASH_SIZE = 20

    def __init__(self, reader, trace: bool = False):
        self._reader = reader           # raw async reader
        self._buf = bytearray()
        self._off = 0                   # read offset into _buf
        self.pos = 0                    # absolute stream position

        self.trace = trace
        self.opcode = 0
        self.event = Event()
        self.error: Optional[Exception] = None

        # State
        self.fields: Dict[int, List[str]] = {}
        self.base_event_time = 0
        self.base_index_time = 0

        self.active_host = 0
        self.active_source = 0
        self.active_source_type = 0

        # Error tracking for summary reporting
        self.metadata_error_counts = {}
        self.total_metadata_errors = 0
        self.events_with_errors = 0

        # Build dispatch table
        self._dispatch = {
            _OP_HEADER: self._decode_header,
            _OP_SPLUNK_PRIVATE: self._decode_splunk_private,
            _OP_NEW_HOST: self._decode_host,
            _OP_NEW_SOURCE: self._decode_source,
            _OP_NEW_SOURCE_TYPE: self._decode_source_type,
            _OP_NEW_STRING: self._decode_string,
        }

    # ------------------------------------------------------------------
    # Inlined buffer management
    # ------------------------------------------------------------------

    async def _ensure(self, n: int):
        """Ensure at least *n* bytes are available from _off onwards."""
        avail = len(self._buf) - self._off
        if avail >= n:
            return
        # Compact: discard already-consumed prefix
        if self._off > 0:
            del self._buf[:self._off]
            self._off = 0
        # Fill until we have enough
        need = n - len(self._buf)
        while need > 0:
            chunk = await self._reader.read(max(_READ_CHUNK, need))
            if not chunk:
                raise EOFError("End of stream")
            self._buf.extend(chunk)
            need = n - len(self._buf)

    def _read_byte(self) -> int:
        """Sync single-byte read (caller must _ensure(1) first)."""
        b = self._buf[self._off]
        self._off += 1
        self.pos += 1
        return b

    def _read_uvarint(self):
        """Sync uvarint decode from buffer. Returns (value, bytes_consumed).
        Caller must _ensure() enough bytes beforehand (10 is always safe
        for a 64-bit varint)."""
        buf = self._buf
        off = self._off
        result = 0
        shift = 0
        while True:
            b = buf[off]
            off += 1
            result |= (b & 0x7F) << shift
            if (b & 0x80) == 0:
                consumed = off - self._off
                self._off = off
                self.pos += consumed
                return result, consumed
            shift += 7

    def _advance(self, n: int):
        """Advance read offset by *n* bytes."""
        self._off += n
        self.pos += n

    def _slice(self, n: int) -> bytes:
        """Read *n* bytes from buffer and advance (caller must _ensure first)."""
        end = self._off + n
        data = bytes(self._buf[self._off:end])
        self._off = end
        self.pos += n
        return data

    def _peek_memoryview(self, n: int) -> memoryview:
        """Return a memoryview of the next *n* bytes without consuming them."""
        return memoryview(self._buf)[self._off:self._off + n]

    # ------------------------------------------------------------------
    # Metadata-error helpers (unchanged from original)
    # ------------------------------------------------------------------

    def _warn_metadata_error(self, context: str, error: Exception):
        error_key = f"{context}: {type(error).__name__}"
        self.metadata_error_counts[error_key] = self.metadata_error_counts.get(error_key, 0) + 1
        self.total_metadata_errors += 1
        if self.trace:
            logger.debug(f"Metadata error #{self.total_metadata_errors} in {context}: {error}")

    def get_error_summary(self):
        if not self.metadata_error_counts:
            return None
        return {
            "total_errors": self.total_metadata_errors,
            "events_with_errors": self.events_with_errors,
            "error_types": dict(self.metadata_error_counts),
        }

    def log_error_summary(self):
        summary = self.get_error_summary()
        if summary:
            logger.warning(f"Metadata extraction summary: {summary['total_errors']} errors "
                           f"across {summary['events_with_errors']} events. "
                           f"Error types: {summary['error_types']}")
        else:
            logger.debug("No metadata errors encountered")

    # ------------------------------------------------------------------
    # Field accessors
    # ------------------------------------------------------------------

    def host(self) -> str:
        if Opcode.NEW_HOST in self.fields and self.active_host > 0:
            return self.fields[Opcode.NEW_HOST][self.active_host - 1]
        return ""

    def source(self) -> str:
        if Opcode.NEW_SOURCE in self.fields and self.active_source > 0:
            return self.fields[Opcode.NEW_SOURCE][self.active_source - 1]
        return ""

    def source_type(self) -> str:
        if Opcode.NEW_SOURCE_TYPE in self.fields and self.active_source_type > 0:
            return self.fields[Opcode.NEW_SOURCE_TYPE][self.active_source_type - 1]
        return ""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def scan(self) -> bool:
        """Scan for next event.  Returns True when an event is ready."""
        # Cache frequently used values as locals for tight inner loop
        buf = self._buf
        event_opcodes = _EVENT_OPCODES
        dispatch = self._dispatch

        while True:
            # --- Inline _ensure(1) + _read_byte() ---
            if self._off >= len(buf):
                try:
                    await self._ensure(1)
                    buf = self._buf  # may have been reallocated
                except EOFError:
                    self.error = None
                    return False
                except Exception as e:
                    self.error = e
                    return False

            opcode = buf[self._off]
            self._off += 1
            self.pos += 1
            self.opcode = opcode

            # Fast NOP skip — no function call overhead
            if opcode == 0:
                continue

            is_event = opcode in event_opcodes

            if is_event:
                self.event.reset()

            try:
                # Inline dispatch lookup to avoid _decode_next call overhead
                handler = dispatch.get(opcode)
                if handler is not None:
                    await handler()
                elif 17 <= opcode <= 31:
                    await self._decode_new_state()
                elif is_event:
                    await self._decode_event()
                else:
                    raise ValueError(f"Unknown opcode: 0x{opcode:02x}")
            except MetadataError as e:
                self._warn_metadata_error("scan", e)
            except Exception as e:
                self.error = e
                return False

            if is_event:
                return True

    def err(self) -> Optional[Exception]:
        return self.error

    def get_event(self) -> Event:
        return self.event

    # ------------------------------------------------------------------
    # Opcode dispatch (inlined into scan() for performance)
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Decoders
    # ------------------------------------------------------------------

    async def _decode_header(self):
        await self._ensure(6)
        data = self._slice(6)
        version = data[0]
        # data[1] = align_bits (unused)
        self.base_index_time = struct.unpack("<i", data[2:6])[0]
        logger.debug(f"Journal Version: {version}")

    async def _decode_splunk_private(self):
        await self._ensure(10)  # varint ≤ 10 bytes
        length, _ = self._read_uvarint()
        await self._ensure(length)
        self._advance(length)

    async def _read_string_field(self) -> str:
        await self._ensure(10)
        length, _ = self._read_uvarint()
        await self._ensure(length)
        data = self._slice(length)
        return data.decode("utf-8", errors="replace")

    async def _decode_host(self):
        s = await self._read_string_field()
        self.fields.setdefault(Opcode.NEW_HOST, []).append(s)

    async def _decode_source(self):
        s = await self._read_string_field()
        self.fields.setdefault(Opcode.NEW_SOURCE, []).append(s)

    async def _decode_source_type(self):
        s = await self._read_string_field()
        self.fields.setdefault(Opcode.NEW_SOURCE_TYPE, []).append(s)

    async def _decode_string(self):
        s = await self._read_string_field()
        self.fields.setdefault(Opcode.NEW_STRING, []).append(s)

    async def _decode_new_state(self):
        # Worst case: 3 varints (10 bytes each) + 4-byte int = 34 bytes
        await self._ensure(34)
        op = self.opcode
        if op & 0x8:
            self.active_host, _ = self._read_uvarint()
        if op & 0x4:
            self.active_source, _ = self._read_uvarint()
        if op & 0x2:
            self.active_source_type, _ = self._read_uvarint()
        if op & 0x1:
            data = self._slice(4)
            self.base_event_time = struct.unpack("<i", data)[0]

    async def _decode_event(self):
        if self.trace:
            logger.debug(f"[TRACE:{id(self)}] Decoding event...")

        # Peek a generous amount for the event header fields.
        # 8 varints (max 10 bytes each) + 8 bytes stream_id + 20 hash = 108
        EVENT_INFO_SIZE = 8 * 10 + 8 + self.HASH_SIZE
        await self._ensure(EVENT_INFO_SIZE)

        # Work from the underlying buffer directly via decode_uvarint_from_bytes
        # so we get full-speed varint parsing on the contiguous buffer.
        buf = self._buf
        off = self._off

        # Message length
        msg_len_wire, n = decode_uvarint_from_bytes(buf, off)
        off += n
        # message_length = wire value + absolute position after consuming wire bytes
        msg_len_wire += self.pos + (off - self._off)

        # Extended storage
        has_extended_storage = False
        extended_storage_len = 0
        if self.opcode & 0x4:
            has_extended_storage = True
            extended_storage_len, n = decode_uvarint_from_bytes(buf, off)
            off += n

        # Hash
        has_hash = False
        ev_hash = b""
        if self.opcode & 0x01 == 0:
            has_hash = True
            ev_hash = bytes(buf[off:off + self.HASH_SIZE])
            off += self.HASH_SIZE

        # Stream ID (uint64 LE)
        stream_id = struct.unpack("<Q", buf[off:off + 8])[0]
        off += 8

        # Stream offset
        stream_offset, n = decode_uvarint_from_bytes(buf, off)
        off += n

        # Stream sub offset
        stream_sub_offset, n = decode_uvarint_from_bytes(buf, off)
        off += n

        # _time
        index_time_diff, n = decode_uvarint_from_bytes(buf, off)
        off += n

        # Sub seconds
        time_sub_seconds, n = decode_shifted_varint_from_bytes(buf, off)
        off += n

        # Metadata count
        metadata_count, n = decode_uvarint_from_bytes(buf, off)
        off += n

        # Advance buffer by total consumed
        consumed = off - self._off
        self._off = off
        self.pos += consumed

        # Fill in event fields
        ev = self.event
        ev.message_length = msg_len_wire
        ev.has_extended_storage = has_extended_storage
        ev.extended_storage_len = extended_storage_len
        ev.has_hash = has_hash
        if has_hash:
            ev.hash = ev_hash
        ev.stream_id = stream_id
        ev.stream_offset = stream_offset
        ev.stream_sub_offset = stream_sub_offset
        ev.index_time_diff = index_time_diff
        ev.index_time = self.base_index_time + index_time_diff
        ev.time_sub_seconds = time_sub_seconds
        ev.event_time = self.base_event_time * 1000 + time_sub_seconds
        ev.metadata_count = metadata_count

        # Read metadata
        if metadata_count > 0:
            meta_size = 4 * 10 * metadata_count
            await self._ensure(meta_size)
            peek = bytes(self._buf[self._off:self._off + meta_size])
            n = self.decode_metadata(peek)
            self._advance(n)

        # Extended storage
        if has_extended_storage:
            await self._ensure(extended_storage_len)
            self._advance(extended_storage_len)

        # Read message
        actual_msg_len = ev.message_length - self.pos
        await self._ensure(actual_msg_len)
        ev.message = self._slice(actual_msg_len)

        # Include punctuation flag
        ev.include_punctuation = (self.opcode & 0x22) == 34

        ev.source = self.source()
        ev.sourcetype = self.source_type()
        ev.host = self.host()

    # ------------------------------------------------------------------
    # Metadata decoding (sync, operates on bytes buffer — same logic)
    # ------------------------------------------------------------------

    def decode_metadata(self, buffer):
        metadata_offset = 0
        self.event.metadata_fields = {}
        extraction_errors = []

        for i in range(self.event.metadata_count):
            try:
                n, meta_index = self._read_metadata(buffer, metadata_offset)
                metadata_offset += n

                for field_index, value_index in meta_index:
                    try:
                        field, value = self.decode_field(field_index, value_index)
                        if self.trace:
                            logger.debug(f"[TRACE:{id(self)}] Metadata {field_index}: {value_index}, {field}: {value}")

                        if field == "__field_error__":
                            extraction_errors.append(value)
                            continue

                        if field not in self.event.metadata_fields:
                            self.event.metadata_fields[field] = value
                        else:
                            existing = self.event.metadata_fields[field]
                            if isinstance(existing, list):
                                existing.append(value)
                            else:
                                self.event.metadata_fields[field] = [existing, value]
                    except Exception as e:
                        error_msg = f"field={field_index}, value={value_index}: {str(e)}"
                        extraction_errors.append(error_msg)
                        self._warn_metadata_error("decode_metadata field processing", e)

            except Exception as e:
                error_msg = f"metadata entry {i}: {str(e)}"
                extraction_errors.append(error_msg)
                self._warn_metadata_error(f"decode_metadata entry {i}", e)
                metadata_offset += 1

        if extraction_errors:
            self.event.metadata_fields["__extraction_errors__"] = extraction_errors
            self.events_with_errors += 1

        return metadata_offset

    def decode_field(self, key, value):
        key -= 1
        value -= 1
        fields = self.fields[Opcode.NEW_STRING]
        try:
            return (fields[key], fields[value])
        except Exception as e:
            self._warn_metadata_error(f"decode_field(key={key+1}, value={value+1})", e)
            return ("__field_error__", f"key={key+1}, value={value+1}: {str(e)}")

    def _read_metadata(self, peek: bytes, offset: int) -> List[int]:
        meta_key, n = decode_uvarint_from_bytes(peek, offset)
        if n == -1:
            raise ValueError("Cannot read varint for metadata key")
        peek_offset = n

        num_to_read = -1

        if self.opcode <= 2:
            meta_key <<= 3
            num_to_read = 1
        else:
            if self.opcode < 36:
                meta_key <<= 2

            rmki_key = int(meta_key & 0xF)
            rest = meta_key >> 4
            type_val = RMKI_TYPES.get(rmki_key)
            if type_val:
                num_to_read = type_val.extra_ints_needed
            else:
                num_to_read = 0
        ret = []
        for i in range(num_to_read):
            long_val, n = decode_uvarint_from_bytes(peek, offset + peek_offset)
            ret.append((rest, long_val))
            if n == -1:
                raise ValueError("Cannot read varint for metadata value")
            peek_offset += n

        return peek_offset, ret
