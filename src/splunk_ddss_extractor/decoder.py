"""
Splunk Journal Parser - Python implementation

Parses Splunk journal files with automatic compression detection:
- .zst files (zstandard compression)
- .gz files (gzip compression)
- No extension or other (uncompressed)
"""

import io
import os
import struct
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import zstandard as zstd
except ImportError:
    print("Warning: zstandard module not installed. Install with: pip install zstandard")
    zstd = None


class Opcode(IntEnum):
    """Journal opcodes"""
    NOP = 0
    OLDSTYLE_EVENT = 1
    OLDSTYLE_EVENT_WITH_HASH = 2
    NEW_HOST = 3
    NEW_SOURCE = 4
    NEW_SOURCE_TYPE = 5
    NEW_STRING = 6
    DELETE = 8
    SPLUNK_PRIVATE = 9
    HEADER = 10
    HASH_SLICE = 11


@dataclass
class Header:
    """Journal header structure"""
    version: int
    align_bits: int
    base_index_time: int


@dataclass
class RawdataMetaKeyItemType:
    """Metadata key item type"""
    representation: int
    extra_ints_needed: int

    def is_float_type(self) -> bool:
        return (self.representation & 0x2) != 0


# Metadata type definitions
RMKI_TYPES = {
    0: RawdataMetaKeyItemType(0, 1),    # String
    2: RawdataMetaKeyItemType(2, 1),    # Float32
    3: RawdataMetaKeyItemType(3, 2),    # Float32Sigfigs
    4: RawdataMetaKeyItemType(4, 2),    # OffsetLen
    6: RawdataMetaKeyItemType(6, 2),    # Float32Precision
    7: RawdataMetaKeyItemType(7, 3),    # Float32SigfigsPrecision
    8: RawdataMetaKeyItemType(8, 1),    # Unsigned
    9: RawdataMetaKeyItemType(9, 1),    # Signed
    10: RawdataMetaKeyItemType(10, 1),  # Float64
    11: RawdataMetaKeyItemType(11, 2),  # Float64Sigfigs
    12: RawdataMetaKeyItemType(12, 3),  # OffsetLenWencoding
    14: RawdataMetaKeyItemType(14, 2),  # Float64Precision
    15: RawdataMetaKeyItemType(15, 0),  # Float64SigfigsPrecision
}


@dataclass
class Event:
    """Splunk journal event"""
    message_length: int = 0
    has_extended_storage: bool = False
    extended_storage_len: int = 0
    has_hash: bool = False
    hash: bytes = field(default_factory=lambda: b'\x00' * 20)
    stream_id: int = 0
    stream_offset: int = 0
    stream_sub_offset: int = 0
    index_time: int = 0
    sub_seconds: int = 0
    metadata_count: int = 0
    message: bytes = b''
    include_punctuation: bool = False

    def reset(self):
        """Reset event to initial state"""
        self.message_length = 0
        self.has_extended_storage = False
        self.extended_storage_len = 0
        self.has_hash = False
        self.hash = b'\x00' * 20
        self.stream_id = 0
        self.stream_offset = 0
        self.stream_sub_offset = 0
        self.index_time = 0
        self.sub_seconds = 0
        self.metadata_count = 0
        self.message = b''
        self.include_punctuation = False

    def message_string(self) -> str:
        """Return message as string"""
        try:
            return self.message.decode('utf-8', errors='replace')
        except:
            return str(self.message)

    def __str__(self) -> str:
        return (
            f"messageLength: {self.message_length} - "
            f"extendedStorageLen: {self.extended_storage_len} - "
            f"hash: {self.hash.hex()} - "
            f"streamID: {self.stream_id} - "
            f"streamOffset: {self.stream_offset} - "
            f"streamSubOffset: {self.stream_sub_offset} - "
            f"indexTime: {self.index_time} - "
            f"subSeconds: {self.sub_seconds} - "
            f"metadataCount: {self.metadata_count} - "
            f"message: {self.message_string()} - "
            f"includePunctuation: {self.include_punctuation}"
        )


class CountedReader:
    """Buffered reader that tracks position"""

    def __init__(self, reader: io.BufferedReader):
        self.reader = reader
        self.pos = 0
        self.buffer = b''
        self.buffer_pos = 0

    def read_byte(self) -> int:
        """Read a single byte"""
        b = self.reader.read(1)
        if not b:
            raise EOFError("End of file")
        self.pos += 1
        return b[0]

    def read(self, n: int) -> bytes:
        """Read n bytes"""
        data = self.reader.read(n)
        if len(data) < n:
            raise EOFError(f"Expected {n} bytes, got {len(data)}")
        self.pos += len(data)
        return data

    def peek(self, n: int) -> bytes:
        """Peek at next n bytes without consuming"""
        current_pos = self.reader.tell()
        data = self.reader.read(n)
        self.reader.seek(current_pos)
        return data

    def discard(self, n: int) -> int:
        """Discard n bytes"""
        data = self.reader.read(n)
        discarded = len(data)
        self.pos += discarded
        return discarded


def read_uvarint(reader: CountedReader) -> int:
    """Read unsigned varint"""
    result = 0
    shift = 0
    while True:
        b = reader.read_byte()
        result |= (b & 0x7f) << shift
        if (b & 0x80) == 0:
            break
        shift += 7
    return result


def read_varint(reader: CountedReader) -> int:
    """Read signed varint (zigzag encoded)"""
    u = read_uvarint(reader)
    # Zigzag decode
    return (u >> 1) ^ -(u & 1)


def decode_uvarint_from_bytes(data: bytes, offset: int = 0) -> Tuple[int, int]:
    """Decode uvarint from byte array, returns (value, bytes_read)"""
    result = 0
    shift = 0
    n = 0
    for i in range(offset, len(data)):
        b = data[i]
        n += 1
        result |= (b & 0x7f) << shift
        if (b & 0x80) == 0:
            return result, n
        shift += 7
    return 0, -1


def decode_varint_from_bytes(data: bytes, offset: int = 0) -> Tuple[int, int]:
    """Decode signed varint from byte array, returns (value, bytes_read)"""
    u, n = decode_uvarint_from_bytes(data, offset)
    if n == -1:
        return 0, -1
    # Zigzag decode
    value = (u >> 1) ^ -(u & 1)
    return value, n


class JournalDecoder:
    """Splunk journal decoder"""

    HASH_SIZE = 20

    def __init__(self, name: str):
        self.name = name
        self.reader: Optional[CountedReader] = None
        self.opcode = 0
        self.event = Event()
        self.error: Optional[Exception] = None

        # State
        self.fields: Dict[int, List[str]] = {}
        self.base_time = 0
        self.active_host = 0
        self.active_source = 0
        self.active_source_type = 0

        # Open the journal
        reader = self._open_journal(name)
        self.reader = CountedReader(reader)

    def _open_journal(self, name: str) -> io.BufferedReader:
        """
        Open and decompress journal file with automatic compression detection

        Supports:
        - .zst files (zstandard compression)
        - .gz files (gzip compression)
        - No extension or other (uncompressed text)
        - Directory path (looks for rawdata/journal.zst)
        """
        import gzip

        path = Path(name)

        # If it's a file, detect compression by extension
        if path.is_file():
            suffix = path.suffix.lower()

            if suffix == '.zst':
                # Zstandard compression
                if zstd is None:
                    raise ImportError("zstandard module required for .zst files. Install with: pip install zstandard")

                with open(path, 'rb') as f:
                    dctx = zstd.ZstdDecompressor()
                    decompressed = dctx.stream_reader(f)
                    data = decompressed.read()
                    return io.BufferedReader(io.BytesIO(data))

            elif suffix == '.gz':
                # Gzip compression
                with gzip.open(path, 'rb') as f:
                    data = f.read()
                    return io.BufferedReader(io.BytesIO(data))

            else:
                # Uncompressed or unknown extension - treat as plain text
                with open(path, 'rb') as f:
                    data = f.read()
                    return io.BufferedReader(io.BytesIO(data))

        # If it's a directory, look for journal file with automatic detection
        if path.is_dir():
            rawdata_path = path / "rawdata"

            # Try to find journal file with various extensions
            journal_candidates = [
                rawdata_path / "journal.zst",
                rawdata_path / "journal.gz",
                rawdata_path / "journal",
            ]

            for journal_path in journal_candidates:
                if journal_path.exists():
                    # Recursively call with the file path for compression detection
                    return self._open_journal(str(journal_path))

            raise FileNotFoundError(
                f"No journal file found in {rawdata_path}. "
                f"Looked for: journal.zst, journal.gz, journal"
            )

        # Path doesn't exist
        raise FileNotFoundError(f"Path not found: {path}")

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

    def scan(self) -> bool:
        """Scan for next event, returns True if event found"""
        while True:
            try:
                self.opcode = self.reader.read_byte()
            except EOFError:
                self.error = None
                return False
            except Exception as e:
                self.error = e
                return False

            if self._is_event_opcode(self.opcode):
                self.event.reset()

            try:
                self._decode_next()
            except Exception as e:
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
        return (opcode == Opcode.OLDSTYLE_EVENT or
                opcode == Opcode.OLDSTYLE_EVENT_WITH_HASH or
                (opcode >= 32 and opcode <= 43))

    def _decode_next(self):
        """Decode next opcode"""
        if self.opcode == Opcode.HEADER:
            self._decode_header()
        elif self.opcode == Opcode.SPLUNK_PRIVATE:
            self._decode_splunk_private()
        elif self.opcode == Opcode.NEW_HOST:
            self._decode_host()
        elif self.opcode == Opcode.NEW_SOURCE:
            self._decode_source()
        elif self.opcode == Opcode.NEW_SOURCE_TYPE:
            self._decode_source_type()
        elif self.opcode == Opcode.NEW_STRING:
            self._decode_string()
        elif self.opcode == Opcode.NOP:
            pass  # No operation
        elif 17 <= self.opcode <= 31:
            self._decode_new_state()
        elif self._is_event_opcode(self.opcode):
            self._decode_event()
        else:
            raise ValueError(f"Unknown opcode: 0x{self.opcode:02x}")

    def _decode_header(self):
        """Decode journal header"""
        data = self.reader.read(6)  # 1 + 1 + 4 bytes
        version = data[0]
        align_bits = data[1]
        base_index_time = struct.unpack('<i', data[2:6])[0]

        print(f"Journal {self.name} - Version: {version}")
        # align_mask = (1 << align_bits) - 1

    def _decode_splunk_private(self):
        """Decode splunk private data (skip it)"""
        length = read_uvarint(self.reader)
        self.reader.discard(length)

    def _read_string_field(self) -> str:
        """Read string field"""
        length = read_uvarint(self.reader)
        data = self.reader.read(length)
        return data.decode('utf-8', errors='replace')

    def _decode_host(self):
        """Decode new host"""
        s = self._read_string_field()
        if Opcode.NEW_HOST not in self.fields:
            self.fields[Opcode.NEW_HOST] = []
        self.fields[Opcode.NEW_HOST].append(s)

    def _decode_source(self):
        """Decode new source"""
        s = self._read_string_field()
        if Opcode.NEW_SOURCE not in self.fields:
            self.fields[Opcode.NEW_SOURCE] = []
        self.fields[Opcode.NEW_SOURCE].append(s)

    def _decode_source_type(self):
        """Decode new source type"""
        s = self._read_string_field()
        if Opcode.NEW_SOURCE_TYPE not in self.fields:
            self.fields[Opcode.NEW_SOURCE_TYPE] = []
        self.fields[Opcode.NEW_SOURCE_TYPE].append(s)

    def _decode_string(self):
        """Decode new string"""
        s = self._read_string_field()
        if Opcode.NEW_STRING not in self.fields:
            self.fields[Opcode.NEW_STRING] = []
        self.fields[Opcode.NEW_STRING].append(s)

    def _decode_new_state(self):
        """Decode new state (opcodes 17-31)"""
        # Active host
        if self.opcode & 0x8 != 0:
            self.active_host = read_uvarint(self.reader)

        # Active source
        if self.opcode & 0x4 != 0:
            self.active_source = read_uvarint(self.reader)

        # Active source type
        if self.opcode & 0x2 != 0:
            self.active_source_type = read_uvarint(self.reader)

        # Base time
        if self.opcode & 0x1 != 0:
            data = self.reader.read(4)
            self.base_time = struct.unpack('<i', data)[0]

    def _decode_event(self):
        """Decode event"""
        # Peek ahead to read event metadata
        EVENT_INFO_SIZE = 8 * 10 + 8 + self.HASH_SIZE  # Estimate
        peek = self.reader.peek(EVENT_INFO_SIZE)

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
            self.event.hash = peek[offset:offset + self.HASH_SIZE]
            offset += self.HASH_SIZE

        # Stream ID (uint64, little endian)
        self.event.stream_id = struct.unpack('<Q', peek[offset:offset + 8])[0]
        offset += 8

        # Stream offset
        self.event.stream_offset, n = decode_uvarint_from_bytes(peek, offset)
        offset += n

        # Stream sub offset
        self.event.stream_sub_offset, n = decode_uvarint_from_bytes(peek, offset)
        offset += n

        # Index time
        self.event.index_time, n = decode_varint_from_bytes(peek, offset)
        offset += n
        self.event.index_time += self.base_time

        # Sub seconds
        self.event.sub_seconds, n = decode_uvarint_from_bytes(peek, offset)
        offset += n

        # Metadata count
        self.event.metadata_count, n = decode_uvarint_from_bytes(peek, offset)
        offset += n

        # Discard what we peeked
        self.reader.discard(offset)

        # Read metadata
        if self.event.metadata_count > 0:
            metadata_peek = self.reader.peek(4 * 10 * self.event.metadata_count)
            metadata_offset = 0

            for i in range(self.event.metadata_count):
                n = self._read_metadata(metadata_peek, metadata_offset)
                metadata_offset += n

            self.reader.discard(metadata_offset)

        # Extended storage
        if self.event.has_extended_storage:
            e_storage = self.reader.read(self.event.extended_storage_len)
            # Extended storage handling (not fully implemented)

        # Calculate actual message length
        self.event.message_length = self.event.message_length - self.reader.pos

        # Read message
        self.event.message = self.reader.read(self.event.message_length)

        # Include punctuation flag
        self.event.include_punctuation = (self.opcode & 0x22) == 34

    def _read_metadata(self, peek: bytes, offset: int) -> int:
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
            type_val = RMKI_TYPES.get(int(meta_key & 0xF))
            if type_val:
                num_to_read = type_val.extra_ints_needed
            else:
                num_to_read = 0

        # Read extra integers
        for i in range(num_to_read):
            long_val, n = decode_varint_from_bytes(peek, offset + peek_offset)
            if n == -1:
                raise ValueError("Cannot read varint for metadata value")
            peek_offset += n

        return peek_offset


def get_compression_type(file_path: str) -> str:
    """
    Detect compression type from file extension

    Args:
        file_path: Path to file

    Returns:
        'zst', 'gz', or 'none'
    """
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix == '.zst':
        return 'zst'
    elif suffix == '.gz':
        return 'gz'
    else:
        return 'none'


def main():
    """
    Example usage

    Supports multiple input formats:
    - Direct file: journal.zst, journal.gz, or uncompressed journal
    - Directory: looks for rawdata/journal.{zst,gz,} automatically
    """
    import sys

    if len(sys.argv) < 2:
        print("Usage: python extract_journal.py <path_to_journal_file_or_directory>")
        print("")
        print("Supports:")
        print("  - Zstandard compressed: journal.zst")
        print("  - Gzip compressed: journal.gz")
        print("  - Uncompressed: journal (no extension)")
        print("  - Directory: /path/to/splunk/index/db/ (auto-detects compression)")
        print("")
        print("Examples:")
        print("  python extract_journal.py /tmp/journal.zst")
        print("  python extract_journal.py /tmp/journal.gz")
        print("  python extract_journal.py /tmp/journal")
        print("  python extract_journal.py /path/to/splunk/index/db/")
        sys.exit(1)

    journal_path = sys.argv[1]

    try:
        decoder = JournalDecoder(journal_path)

        event_count = 0
        while decoder.scan():
            event = decoder.get_event()
            event_count += 1
            if event_count <= 10:
                print(f"\n--- Event {event_count} ---")
                print(f"Host: {decoder.host()}")
                print(f"Source: {decoder.source()}")
                print(f"SourceType: {decoder.source_type()}")
                print(f"IndexTime: {event.index_time}")
                print(f"Message: {event.message_string()}")

            # Limit output for demo
            if event_count == 10:
                print(f"\n... (showing first 10 events)")
                

        if decoder.err():
            print(f"\nError: {decoder.err()}")
            raise decoder.err()

        print(f"\nTotal events processed: {event_count}")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
