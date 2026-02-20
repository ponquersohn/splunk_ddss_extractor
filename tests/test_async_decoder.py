"""
Tests for async journal stream and decoder.

Uses asyncio.run() inside regular test functions to avoid
requiring pytest-asyncio as a dependency.
"""

import asyncio
import struct

import pytest

from splunk_ddss_extractor.async_stream import AsyncJournalStream
from splunk_ddss_extractor.async_decoder import AsyncJournalDecoder


class AsyncBytesReader:
    """Wraps bytes into an object with async read(n) -> bytes."""

    def __init__(self, data: bytes):
        self._data = memoryview(data)
        self._pos = 0

    async def read(self, n: int) -> bytes:
        chunk = bytes(self._data[self._pos : self._pos + n])
        self._pos += len(chunk)
        return chunk


def _encode_uvarint(value: int) -> bytes:
    """Encode an unsigned varint."""
    parts = []
    while value > 0x7F:
        parts.append((value & 0x7F) | 0x80)
        value >>= 7
    parts.append(value & 0x7F)
    return bytes(parts)


def _build_minimal_journal(message: bytes = b"hello world") -> bytes:
    """Build a minimal valid journal binary with one event.

    Structure:
      HEADER (opcode 0x0A)
      NEW_HOST (opcode 0x03) -> "test-host"
      NEW_SOURCE (opcode 0x04) -> "test-source"
      NEW_SOURCE_TYPE (opcode 0x05) -> "test-stype"
      NEW_STATE (opcode 0x1E) -> set active host=1, source=1, sourcetype=1
      OLDSTYLE_EVENT (opcode 0x01) -> one event with the given message
    """
    parts = []

    # 1. HEADER (opcode 0x0A) + version(1) + align_bits(1) + base_index_time(i32 LE)
    parts.append(b"\x0a")  # opcode
    parts.append(b"\x01")  # version
    parts.append(b"\x00")  # align_bits
    parts.append(struct.pack("<i", 1000))  # base_index_time = 1000

    # 2. NEW_HOST
    host = b"test-host"
    parts.append(b"\x03")  # opcode
    parts.append(_encode_uvarint(len(host)))
    parts.append(host)

    # 3. NEW_SOURCE
    source = b"test-source"
    parts.append(b"\x04")  # opcode
    parts.append(_encode_uvarint(len(source)))
    parts.append(source)

    # 4. NEW_SOURCE_TYPE
    stype = b"test-stype"
    parts.append(b"\x05")  # opcode
    parts.append(_encode_uvarint(len(stype)))
    parts.append(stype)

    # 5. NEW_STATE (opcode 0x1E = bits host|source|sourcetype, no base_time)
    parts.append(b"\x1e")  # opcode
    parts.append(_encode_uvarint(1))  # active_host = 1
    parts.append(_encode_uvarint(1))  # active_source = 1
    parts.append(_encode_uvarint(1))  # active_source_type = 1

    # 6. OLDSTYLE_EVENT (opcode 0x01)
    #    opcode & 0x01 == 1  -> no hash
    #    opcode & 0x04 == 0  -> no extended storage
    #
    # After the opcode byte, the event fields are:
    #   message_length (uvarint)  -- wire value M
    #   stream_id (uint64 LE)     -- 8 bytes
    #   stream_offset (uvarint)
    #   stream_sub_offset (uvarint)
    #   index_time_diff (uvarint)
    #   time_sub_seconds (uvarint, shifted)
    #   metadata_count (uvarint)
    #   <message bytes>
    #
    # The decoder computes:
    #   message_length = M + reader.pos + bytes_consumed_for_M
    # Then after skip(total_consumed):
    #   actual_msg_len = message_length - reader.pos
    #                  = M - (total_consumed - bytes_consumed_for_M)
    #
    # So M = len(message) + (fields_after_M_bytes)

    event_fields_after_msg_len = (
        struct.pack("<Q", 0)  # stream_id = 0  (8 bytes)
        + _encode_uvarint(0)  # stream_offset
        + _encode_uvarint(0)  # stream_sub_offset
        + _encode_uvarint(100)  # index_time_diff = 100
        + _encode_uvarint(0)  # time_sub_seconds
        + _encode_uvarint(0)  # metadata_count = 0
    )

    wire_msg_len = len(event_fields_after_msg_len) + len(message)

    parts.append(b"\x01")  # opcode OLDSTYLE_EVENT
    parts.append(_encode_uvarint(wire_msg_len))
    parts.append(event_fields_after_msg_len)
    parts.append(message)

    return b"".join(parts)


# ---------------------------------------------------------------------------
# AsyncJournalStream tests
# ---------------------------------------------------------------------------


class TestAsyncJournalStream:
    def test_read(self):
        async def _run():
            reader = AsyncBytesReader(b"abcdefgh")
            stream = AsyncJournalStream(reader)
            data = await stream.read(4)
            assert data == b"abcd"
            assert stream.tell() == 4
            data = await stream.read(4)
            assert data == b"efgh"
            assert stream.tell() == 8

        asyncio.run(_run())

    def test_read_byte(self):
        async def _run():
            reader = AsyncBytesReader(b"\x42\x43")
            stream = AsyncJournalStream(reader)
            assert await stream.read_byte() == 0x42
            assert await stream.read_byte() == 0x43

        asyncio.run(_run())

    def test_peek_does_not_advance(self):
        async def _run():
            reader = AsyncBytesReader(b"hello")
            stream = AsyncJournalStream(reader)
            peeked = await stream.peek(3)
            assert peeked == b"hel"
            assert stream.tell() == 0
            data = await stream.read(5)
            assert data == b"hello"

        asyncio.run(_run())

    def test_skip(self):
        async def _run():
            reader = AsyncBytesReader(b"abcdef")
            stream = AsyncJournalStream(reader)
            await stream.skip(3)
            assert stream.tell() == 3
            data = await stream.read(3)
            assert data == b"def"

        asyncio.run(_run())

    def test_read_uvarint(self):
        async def _run():
            # varint 300 = 0xAC 0x02
            reader = AsyncBytesReader(b"\xac\x02")
            stream = AsyncJournalStream(reader)
            value = await stream.read_uvarint()
            assert value == 300

        asyncio.run(_run())

    def test_read_varint(self):
        async def _run():
            # zigzag encode -1 → 1 → 0x01
            reader = AsyncBytesReader(b"\x01")
            stream = AsyncJournalStream(reader)
            value = await stream.read_varint()
            assert value == -1

        asyncio.run(_run())

    def test_eof_raises(self):
        async def _run():
            reader = AsyncBytesReader(b"ab")
            stream = AsyncJournalStream(reader)
            with pytest.raises(EOFError):
                await stream.read(10)

        asyncio.run(_run())

    def test_discard(self):
        async def _run():
            reader = AsyncBytesReader(b"abcdef")
            stream = AsyncJournalStream(reader)
            await stream.peek(6)  # fill buffer
            stream.discard(3)
            # pos should not change
            assert stream.tell() == 0

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# AsyncJournalDecoder tests
# ---------------------------------------------------------------------------


class TestAsyncJournalDecoder:
    def test_import(self):
        """Async decoder and stream can be imported from the package."""
        from splunk_ddss_extractor import AsyncJournalDecoder, AsyncJournalStream

        assert AsyncJournalDecoder is not None
        assert AsyncJournalStream is not None

    def test_scan_single_event(self):
        """Decoder extracts a single event from a minimal journal."""
        async def _run():
            journal = _build_minimal_journal(b"hello world")
            reader = AsyncBytesReader(journal)
            decoder = AsyncJournalDecoder(reader=reader)

            found = await decoder.scan()
            assert found is True

            event = decoder.get_event()
            assert event.message_string() == "hello world"
            assert event.host == "test-host"
            assert event.source == "test-source"
            assert event.sourcetype == "test-stype"
            assert event.index_time == 1100  # base 1000 + diff 100

            # No more events
            found = await decoder.scan()
            assert found is False
            assert decoder.err() is None

        asyncio.run(_run())

    def test_scan_utf8_message(self):
        """Decoder handles UTF-8 messages."""
        async def _run():
            msg = "événement données".encode("utf-8")
            journal = _build_minimal_journal(msg)
            reader = AsyncBytesReader(journal)
            decoder = AsyncJournalDecoder(reader=reader)

            assert await decoder.scan() is True
            assert decoder.get_event().message_string() == "événement données"

        asyncio.run(_run())

    def test_scan_empty_stream(self):
        """Decoder returns False on empty input."""
        async def _run():
            reader = AsyncBytesReader(b"")
            decoder = AsyncJournalDecoder(reader=reader)
            assert await decoder.scan() is False
            assert decoder.err() is None

        asyncio.run(_run())

    def test_get_event_returns_event_object(self):
        """get_event returns an Event with to_normalized_dict."""
        async def _run():
            journal = _build_minimal_journal(b"test")
            reader = AsyncBytesReader(journal)
            decoder = AsyncJournalDecoder(reader=reader)

            await decoder.scan()
            d = decoder.get_event().to_normalized_dict()
            assert "event" in d
            assert "host" in d
            assert "source" in d
            assert "sourcetype" in d
            assert "index_time" in d
            assert d["event"] == "test"

        asyncio.run(_run())

    def test_host_source_before_scan(self):
        """host/source/source_type return empty before any scan."""
        reader = AsyncBytesReader(b"")
        decoder = AsyncJournalDecoder(reader=reader)
        assert decoder.host() == ""
        assert decoder.source() == ""
        assert decoder.source_type() == ""
