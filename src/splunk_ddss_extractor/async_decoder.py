"""
Async Splunk Journal Parser

Mirrors JournalDecoder but accepts an async reader, enabling use in
async contexts (aioboto3 streams, aiofiles, etc.).

Reuses Event, Opcode, Header, RMKI_TYPES, and all decode_*_from_bytes
helpers from the sync decoder module — no duplication of data structures.
"""

import logging
import struct
from typing import Dict, List, Optional

from .async_stream import AsyncJournalStream
from .decoder import (
    Event,
    Opcode,
    RMKI_TYPES,
    decode_shifted_varint_from_bytes,
    decode_uvarint_from_bytes,
)

logger = logging.getLogger(__name__)


class MetadataError(Exception):
    """Non-fatal metadata extraction error"""
    pass


class AsyncJournalDecoder:
    """Async Splunk journal decoder"""

    HASH_SIZE = 20

    def __init__(self, reader, trace: bool = False):
        self.reader = AsyncJournalStream(reader)
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

    def _trace(self, message: str):
        """Instance-specific trace logging"""
        if self.trace:
            logger.debug(f"[TRACE:{id(self)}] {message}")

    def _warn_metadata_error(self, context: str, error: Exception):
        """Track metadata extraction errors for summary reporting"""
        # Count the error type
        error_key = f"{context}: {type(error).__name__}"
        self.metadata_error_counts[error_key] = self.metadata_error_counts.get(error_key, 0) + 1
        self.total_metadata_errors += 1

        # Only log individual errors when tracing is enabled
        if self.trace:
            logger.debug(f"Metadata error #{self.total_metadata_errors} in {context}: {error}")

    def get_error_summary(self):
        """Get summary of metadata errors encountered"""
        if not self.metadata_error_counts:
            return None

        summary = {
            "total_errors": self.total_metadata_errors,
            "events_with_errors": self.events_with_errors,
            "error_types": dict(self.metadata_error_counts)
        }
        return summary

    def log_error_summary(self):
        """Log final error summary"""
        summary = self.get_error_summary()
        if summary:
            logger.warning(f"Metadata extraction summary: {summary['total_errors']} errors "
                         f"across {summary['events_with_errors']} events. "
                         f"Error types: {summary['error_types']}")
        else:
            logger.debug("No metadata errors encountered")

    def host(self) -> str:
        """Get current host"""
        if Opcode.NEW_HOST in self.fields and self.active_host > 0:
            return self.fields[Opcode.NEW_HOST][self.active_host - 1]
        return ""

    def source(self) -> str:
        """Get current source"""
        if Opcode.NEW_SOURCE in self.fields and self.active_source > 0:
            return self.fields[Opcode.NEW_SOURCE][self.active_source - 1]
        return ""

    def source_type(self) -> str:
        """Get current source type"""
        if Opcode.NEW_SOURCE_TYPE in self.fields and self.active_source_type > 0:
            return self.fields[Opcode.NEW_SOURCE_TYPE][self.active_source_type - 1]
        return ""

    async def scan(self) -> bool:
        """Scan for next event, returns True if event found"""
        while True:
            try:
                self.opcode = await self.reader.read_byte()
                self._trace(f"Read opcode: 0x{self.opcode:02x}")
            except EOFError:
                self.error = None
                return False
            except Exception as e:
                self.error = e
                return False

            if self._is_event_opcode(self.opcode):
                self.event.reset()

            try:
                await self._decode_next()
            except MetadataError as e:
                # Metadata errors are non-fatal - log and continue
                self._warn_metadata_error("scan", e)
            except Exception as e:
                # Raw decoding errors are fatal
                self.error = e
                return False

            if self._is_event_opcode(self.opcode):
                return True

    def err(self) -> Optional[Exception]:
        """Get last error"""
        return self.error

    def get_event(self) -> Event:
        """Get current event"""
        return self.event

    def _is_event_opcode(self, opcode: int) -> bool:
        """Check if opcode is an event opcode"""
        return (
            opcode == Opcode.OLDSTYLE_EVENT
            or opcode == Opcode.OLDSTYLE_EVENT_WITH_HASH
            or (opcode >= 32 and opcode <= 43)
        )

    async def _decode_next(self):
        """Decode next opcode"""
        if self.opcode == Opcode.HEADER:
            await self._decode_header()
        elif self.opcode == Opcode.SPLUNK_PRIVATE:
            await self._decode_splunk_private()
        elif self.opcode == Opcode.NEW_HOST:
            await self._decode_host()
        elif self.opcode == Opcode.NEW_SOURCE:
            await self._decode_source()
        elif self.opcode == Opcode.NEW_SOURCE_TYPE:
            await self._decode_source_type()
        elif self.opcode == Opcode.NEW_STRING:
            await self._decode_string()
        elif self.opcode == Opcode.NOP:
            pass  # No operation
        elif 17 <= self.opcode <= 31:
            await self._decode_new_state()
        elif self._is_event_opcode(self.opcode):
            await self._decode_event()
        else:
            raise ValueError(f"Unknown opcode: 0x{self.opcode:02x}")

    async def _decode_header(self):
        """Decode journal header"""
        data = await self.reader.read(6)  # 1 + 1 + 4 bytes
        version = data[0]
        align_bits = data[1]  # noqa unused currently
        self.base_index_time = struct.unpack("<i", data[2:6])[0]  # noqa unused currently

        logger.debug(f"Journal Version: {version}")

    async def _decode_splunk_private(self):
        """Decode splunk private data (skip it)"""
        length = await self.reader.read_uvarint()
        await self.reader.skip(length)

    async def _read_string_field(self) -> str:
        """Read string field"""
        length = await self.reader.read_uvarint()
        data = await self.reader.read(length)
        return data.decode("utf-8", errors="replace")

    async def _decode_host(self):
        """Decode new host"""
        s = await self._read_string_field()
        if Opcode.NEW_HOST not in self.fields:
            self.fields[Opcode.NEW_HOST] = []
        self.fields[Opcode.NEW_HOST].append(s)

    async def _decode_source(self):
        """Decode new source"""
        s = await self._read_string_field()
        if Opcode.NEW_SOURCE not in self.fields:
            self.fields[Opcode.NEW_SOURCE] = []
        self.fields[Opcode.NEW_SOURCE].append(s)

    async def _decode_source_type(self):
        """Decode new source type"""
        s = await self._read_string_field()
        if Opcode.NEW_SOURCE_TYPE not in self.fields:
            self.fields[Opcode.NEW_SOURCE_TYPE] = []
        self.fields[Opcode.NEW_SOURCE_TYPE].append(s)

    async def _decode_string(self):
        """Decode new string"""
        s = await self._read_string_field()
        if Opcode.NEW_STRING not in self.fields:
            self.fields[Opcode.NEW_STRING] = []
        self.fields[Opcode.NEW_STRING].append(s)

    async def _decode_new_state(self):
        """Decode new state (opcodes 17-31)"""
        # Active host
        if self.opcode & 0x8 != 0:
            self.active_host = await self.reader.read_uvarint()

        # Active source
        if self.opcode & 0x4 != 0:
            self.active_source = await self.reader.read_uvarint()

        # Active source type
        if self.opcode & 0x2 != 0:
            self.active_source_type = await self.reader.read_uvarint()

        # Base time
        if self.opcode & 0x1 != 0:
            data = await self.reader.read(4)
            self.base_event_time = struct.unpack("<i", data)[0]

    async def _decode_event(self):
        """Decode event"""
        logger.debug("Decoding event...")
        # Peek ahead to read event metadata
        EVENT_INFO_SIZE = 8 * 10 + 8 + self.HASH_SIZE  # Estimate
        peek = await self.reader.peek(EVENT_INFO_SIZE)

        offset = 0

        # Message length
        self.event.message_length, n = decode_uvarint_from_bytes(peek, offset)
        offset += n
        self.event.message_length += self.reader.pos + offset

        # Extended storage
        if self.opcode & 0x4 != 0:
            self.event.has_extended_storage = True
            self.event.extended_storage_len, n = decode_uvarint_from_bytes(peek, offset)
            offset += n

        # Hash
        if self.opcode & 0x01 == 0:
            self.event.has_hash = True
            self.event.hash = peek[offset : offset + self.HASH_SIZE]
            offset += self.HASH_SIZE

        # Stream ID (uint64, little endian)
        self.event.stream_id = struct.unpack("<Q", peek[offset : offset + 8])[0]
        offset += 8

        # Stream offset
        self.event.stream_offset, n = decode_uvarint_from_bytes(peek, offset)
        offset += n

        # Stream sub offset
        self.event.stream_sub_offset, n = decode_uvarint_from_bytes(peek, offset)
        offset += n

        # _time
        self.event.index_time_diff, n = decode_uvarint_from_bytes(peek, offset)
        offset += n

        self.event.index_time = self.base_index_time + self.event.index_time_diff

        # Sub seconds
        self.event.time_sub_seconds, n = decode_shifted_varint_from_bytes(peek, offset)
        offset += n

        self.event.event_time = self.base_event_time * 1000 + self.event.time_sub_seconds

        # Metadata count
        self.event.metadata_count, n = decode_uvarint_from_bytes(peek, offset)
        offset += n

        # Discard what we peeked
        await self.reader.skip(offset)

        # Read metadata
        if self.event.metadata_count > 0:
            metadata_peek = await self.reader.peek(4 * 10 * self.event.metadata_count)
            n = self.decode_metadata(metadata_peek)
            await self.reader.skip(n)

        # Extended storage
        if self.event.has_extended_storage:
            e_storage = await self.reader.read(self.event.extended_storage_len)  # noqa
            # Extended storage handling (not fully implemented)

        # Calculate actual message length
        self.event.message_length = self.event.message_length - self.reader.pos

        # Read message
        self.event.message = await self.reader.read(self.event.message_length)

        # Include punctuation flag
        self.event.include_punctuation = (self.opcode & 0x22) == 34

        self.event.source = self.source()
        self.event.sourcetype = self.source_type()
        self.event.host = self.host()

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
                        self._trace(f"Metadata {field_index}: {value_index}, {field}: {value}")

                        # Check if this was an error field
                        if field == "__field_error__":
                            extraction_errors.append(value)
                            continue

                        if field not in self.event.metadata_fields:
                            self.event.metadata_fields[field] = value
                        else:
                            if isinstance(self.event.metadata_fields[field], list):
                                self.event.metadata_fields[field].append(value)
                            else:
                                self.event.metadata_fields[field] = [
                                    self.event.metadata_fields[field],
                                    value,
                                ]
                    except Exception as e:
                        error_msg = f"field={field_index}, value={value_index}: {str(e)}"
                        extraction_errors.append(error_msg)
                        self._warn_metadata_error(f"decode_metadata field processing", e)

            except Exception as e:
                error_msg = f"metadata entry {i}: {str(e)}"
                extraction_errors.append(error_msg)
                self._warn_metadata_error(f"decode_metadata entry {i}", e)
                # Try to continue with next metadata entry
                metadata_offset += 1  # Minimal increment to try next position

        # Add extraction errors to metadata if any occurred
        if extraction_errors:
            self.event.metadata_fields["__extraction_errors__"] = extraction_errors
            self.events_with_errors += 1

        return metadata_offset

    def decode_field(self, key, value):
        """Decode fields from tuple"""
        key -= 1
        value -= 1

        fields = self.fields[Opcode.NEW_STRING]
        try:
            ret = (fields[key], fields[value])
        except Exception as e:
            self._warn_metadata_error(f"decode_field(key={key+1}, value={value+1})", e)
            # Return error indicator that can be detected in event metadata
            ret = ("__field_error__", f"key={key+1}, value={value+1}: {str(e)}")
        return ret

    def _read_metadata(self, peek: bytes, offset: int) -> List[int]:
        """Read metadata entry, returns bytes consumed"""
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

            # Get type from combined value
            rmki_key = int(meta_key & 0xF)
            rest = meta_key >> 4
            type_val = RMKI_TYPES.get(rmki_key)
            if type_val:
                num_to_read = type_val.extra_ints_needed
            else:
                num_to_read = 0
        ret = []
        # Read extra integers
        for i in range(num_to_read):
            long_val, n = decode_uvarint_from_bytes(peek, offset + peek_offset)
            ret.append((rest, long_val))
            if n == -1:
                raise ValueError("Cannot read varint for metadata value")
            peek_offset += n

        return peek_offset, ret
