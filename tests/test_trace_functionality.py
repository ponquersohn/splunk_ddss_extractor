"""
Tests for trace functionality and enhanced error handling in decoders
"""

import io
import logging
from unittest.mock import MagicMock, patch

import pytest

from splunk_ddss_extractor.decoder import JournalDecoder, MetadataError
from splunk_ddss_extractor.extractor import Extractor


class TestTraceFunctionality:
    """Test trace parameter functionality"""

    def test_sync_decoder_trace_parameter(self):
        """Test that sync decoder accepts trace parameter"""
        # Default (trace=False)
        decoder = JournalDecoder(reader=None)
        assert decoder.trace is False

        # Explicit trace=False
        decoder = JournalDecoder(reader=None, trace=False)
        assert decoder.trace is False

        # Explicit trace=True
        decoder = JournalDecoder(reader=None, trace=True)
        assert decoder.trace is True

    def test_extractor_trace_parameter(self):
        """Test that Extractor accepts trace parameter"""
        # Default (trace=False)
        extractor = Extractor()
        assert extractor.trace is False

        # Explicit trace=False
        extractor = Extractor(trace=False)
        assert extractor.trace is False

        # Explicit trace=True
        extractor = Extractor(trace=True)
        assert extractor.trace is True

    @patch('splunk_ddss_extractor.decoder.logger')
    def test_sync_decoder_trace_logging(self, mock_logger):
        """Test that sync decoder logs trace messages when trace=True"""
        decoder = JournalDecoder(reader=None, trace=True)

        # Test _trace method
        decoder._trace("Test message")
        mock_logger.debug.assert_called_with(f"[TRACE:{id(decoder)}] Test message")

        # Reset mock
        mock_logger.reset_mock()

        # Test with trace=False
        decoder = JournalDecoder(reader=None, trace=False)
        decoder._trace("Test message")
        mock_logger.debug.assert_not_called()

    @patch('splunk_ddss_extractor.decoder.logger')
    def test_sync_metadata_error_logging(self, mock_logger):
        """Test that sync decoder logs metadata errors correctly"""
        decoder = JournalDecoder(reader=None, trace=True)

        test_error = ValueError("Test error")
        decoder._warn_metadata_error("test_context", test_error)

        # With trace=True, should log as debug
        mock_logger.debug.assert_called_with(
            "Metadata error #1 in test_context: Test error"
        )

        # Reset mock and test trace=False - should not log individual errors
        mock_logger.reset_mock()
        decoder = JournalDecoder(reader=None, trace=False)
        decoder._warn_metadata_error("test_context", test_error)

        # Should not log individual errors when trace=False
        mock_logger.debug.assert_not_called()
        mock_logger.warning.assert_not_called()


class TestEnhancedErrorHandling:
    """Test enhanced error handling functionality"""

    def test_sync_decode_field_error_handling(self):
        """Test that sync decode_field properly handles errors"""
        decoder = JournalDecoder(reader=None, trace=False)

        # Mock the fields dict to cause an IndexError
        decoder.fields = {6: ["field1", "field2"]}  # NEW_STRING opcode is 6

        # This should return an error indicator instead of raising
        field, value = decoder.decode_field(10, 10)  # Out of bounds indices

        assert field == "__field_error__"
        assert "key=10, value=10" in value

    def test_metadata_error_exception_exists(self):
        """Test that MetadataError exception is defined"""
        from splunk_ddss_extractor.decoder import MetadataError as SyncMetadataError
        assert issubclass(SyncMetadataError, Exception)

    @patch('splunk_ddss_extractor.extractor.NativeJournalDecoder')
    def test_extractor_passes_trace_to_decoder(self, mock_decoder_class):
        """Test that Extractor passes trace parameter to NativeJournalDecoder"""
        mock_decoder = MagicMock()
        mock_decoder_class.return_value = mock_decoder
        mock_decoder.scan.return_value = False
        mock_decoder.err.return_value = None

        # Test with trace=True
        extractor = Extractor(trace=True)

        # Mock the input stream opening
        with patch.object(extractor, '_open_input') as mock_open_input, \
             patch.object(extractor, '_open_output') as mock_open_output:

            mock_open_input.return_value = MagicMock()
            mock_open_output.return_value = MagicMock()
            mock_open_output.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_open_output.return_value.__exit__ = MagicMock(return_value=None)

            with patch('splunk_ddss_extractor.extractor.get_formatter') as mock_formatter:
                mock_formatter.return_value = MagicMock()
                mock_formatter.return_value.return_value.__enter__ = MagicMock(return_value=MagicMock())
                mock_formatter.return_value.return_value.__exit__ = MagicMock(return_value=None)

                try:
                    extractor.extract(input_path="dummy", output_path="dummy")
                except:
                    pass  # We expect this to fail due to mocking, but we want to check the decoder call

            # Verify decoder was called with trace=True
            mock_decoder_class.assert_called_once()
            call_args = mock_decoder_class.call_args
            assert call_args[1]['trace'] is True

    def test_backwards_compatibility(self):
        """Test that existing code still works (backwards compatibility)"""
        decoder = JournalDecoder(reader=None)
        assert decoder.trace is False

        extractor = Extractor()
        assert extractor.trace is False


class TestErrorAggregation:
    """Test error aggregation and summary reporting"""

    def test_sync_error_counting(self):
        """Test that sync decoder counts errors without excessive logging"""
        decoder = JournalDecoder(reader=None, trace=False)

        # Simulate multiple errors
        decoder._warn_metadata_error("test_context1", IndexError("test error"))
        decoder._warn_metadata_error("test_context1", IndexError("test error"))  # Same type
        decoder._warn_metadata_error("test_context2", ValueError("different error"))

        assert decoder.total_metadata_errors == 3
        assert len(decoder.metadata_error_counts) == 2  # Two unique error types

        summary = decoder.get_error_summary()
        assert summary is not None
        assert summary["total_errors"] == 3
        assert summary["events_with_errors"] == 0
        assert "test_context1: IndexError" in summary["error_types"]
        assert "test_context2: ValueError" in summary["error_types"]
        assert summary["error_types"]["test_context1: IndexError"] == 2

    @patch('splunk_ddss_extractor.decoder.logger')
    def test_sync_error_summary_logging(self, mock_logger):
        """Test that sync decoder logs error summary correctly"""
        decoder = JournalDecoder(reader=None, trace=False)

        # No errors - should not log warning
        decoder.log_error_summary()
        mock_logger.warning.assert_not_called()
        mock_logger.debug.assert_called_with("No metadata errors encountered")

        # Reset mock
        mock_logger.reset_mock()

        # Add some errors
        decoder._warn_metadata_error("test", ValueError("test"))
        decoder.log_error_summary()

        # Should log warning with summary
        mock_logger.warning.assert_called_once()
        call_args = mock_logger.warning.call_args[0][0]
        assert "Metadata extraction summary" in call_args
        assert "1 errors across 0 events" in call_args

    def test_no_errors_summary(self):
        """Test summary when no errors occurred"""
        decoder = JournalDecoder(reader=None, trace=False)

        summary = decoder.get_error_summary()
        assert summary is None


if __name__ == "__main__":
    pytest.main([__file__])
