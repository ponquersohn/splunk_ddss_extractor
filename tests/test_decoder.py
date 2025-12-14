"""
Unit tests for Splunk journal decoder
"""

from pathlib import Path

import pytest


class TestJournalDecoder:
    """Test JournalDecoder functionality"""

    def test_import(self):
        """Test that decoder module can be imported"""
        from splunk_ddss_extractor.decoder import Event, JournalDecoder

        assert JournalDecoder is not None
        assert Event is not None

    def test_event_creation(self):
        """Test Event creation"""
        from splunk_ddss_extractor.decoder import Event

        event = Event()
        assert event.message_length == 0
        assert event.has_hash is False
        assert event.message == b""

    def test_event_message_string(self):
        """Test Event message string conversion"""
        from splunk_ddss_extractor.decoder import Event

        event = Event()
        event.message = b"Test message"
        assert event.message_string() == "Test message"

    # TODO: Add more tests
    # - Test journal file parsing
    # - Test varint encoding/decoding
    # - Test opcode handling
    # - Test with real journal files


class TestVarintEncoding:
    """Test varint encoding/decoding"""

    def test_decode_uvarint(self):
        """Test unsigned varint decoding"""
        from splunk_ddss_extractor.decoder import decode_uvarint_from_bytes

        # Test simple values
        value, n = decode_uvarint_from_bytes(b"\x00")
        assert value == 0
        assert n == 1

        value, n = decode_uvarint_from_bytes(b"\x01")
        assert value == 1
        assert n == 1

        value, n = decode_uvarint_from_bytes(b"\x7f")
        assert value == 127
        assert n == 1

    def test_decode_varint(self):
        """Test signed varint decoding"""
        from splunk_ddss_extractor.decoder import decode_varint_from_bytes

        # Test simple values
        value, n = decode_varint_from_bytes(b"\x00")
        assert value == 0
        assert n == 1

        value, n = decode_varint_from_bytes(b"\x01")
        assert value == -1
        assert n == 1

        value, n = decode_varint_from_bytes(b"\x02")
        assert value == 1
        assert n == 1


# TODO: Add integration tests
# TODO: Add performance tests
# TODO: Add test fixtures with sample journal files
