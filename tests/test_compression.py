"""
Test automatic compression detection
"""

import gzip
import tempfile
from pathlib import Path

import pytest


class TestCompressionDetection:
    """Test compression detection and handling"""

    def test_compression_type_detection(self):
        """Test get_compression_type helper"""
        from splunk_ddss_extractor.decoder import get_compression_type

        assert get_compression_type("file.zst") == "zst"
        assert get_compression_type("file.ZST") == "zst"
        assert get_compression_type("file.gz") == "gz"
        assert get_compression_type("file.GZ") == "gz"
        assert get_compression_type("file") == "none"
        assert get_compression_type("file.txt") == "none"
        assert get_compression_type("file.log") == "none"

    def test_zst_file_opening(self):
        """Test opening .zst files"""
        # This would require a real .zst journal file
        # For now, just test the import works
        from splunk_ddss_extractor.decoder import JournalDecoder

        assert JournalDecoder is not None

    def test_module_exports(self):
        """Test that all expected classes are exported"""
        from splunk_ddss_extractor.decoder import (Event, JournalDecoder,
                                                   Opcode,
                                                   get_compression_type)

        assert JournalDecoder is not None
        assert Event is not None
        assert Opcode is not None
        assert callable(get_compression_type)

    # TODO: Add tests with actual journal files
    # TODO: Test .gz decompression
    # TODO: Test uncompressed files
    # TODO: Test directory mode with various compression


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
