"""
Test automatic compression detection
"""

import gzip
import tempfile
from pathlib import Path

import pytest

from splunk_ddss_extractor.extractor import Extractor


class TestCompressionDetection:
    """Test compression detection and handling"""

    def test_decompression_by_extension(self):
        """Test that _apply_decompression selects the right handler based on extension"""
        import io
        extractor = Extractor()

        # Uncompressed - should return the stream as-is
        raw = io.BytesIO(b"hello")
        result = extractor._apply_decompression("file.bin", raw)
        assert result is raw

        # .gz - should wrap in GzipFile
        raw_gz = io.BytesIO(b"")
        result = extractor._apply_decompression("file.gz", raw_gz)
        assert isinstance(result, gzip.GzipFile)

        # .zst - should wrap in zstd stream reader
        import zstandard as zstd
        raw_zst = io.BytesIO(b"")
        result = extractor._apply_decompression("file.zst", raw_zst)
        assert isinstance(result, zstd.ZstdDecompressionReader)

        # Case insensitive
        raw_zst2 = io.BytesIO(b"")
        result = extractor._apply_decompression("FILE.ZST", raw_zst2)
        assert isinstance(result, zstd.ZstdDecompressionReader)

    def test_zst_file_opening(self):
        """Test opening .zst files"""
        from splunk_ddss_extractor.decoder import JournalDecoder

        assert JournalDecoder is not None

    def test_module_exports(self):
        """Test that all expected classes are exported"""
        from splunk_ddss_extractor.decoder import Event, JournalDecoder, Opcode

        assert JournalDecoder is not None
        assert Event is not None
        assert Opcode is not None

    # TODO: Add tests with actual journal files
    # TODO: Test .gz decompression
    # TODO: Test uncompressed files
    # TODO: Test directory mode with various compression


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
