"""
High-level extraction interface for Splunk journal files
"""

import gzip
import io
import logging
import sys
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import boto3
import zstandard as zstd

from .decoder import JournalDecoder
from .output_formatters import get_formatter
from .writers import FileWriter, S3Writer, StdoutWriter

logger = logging.getLogger(__name__)


class Extractor:
    """
    High-level extractor for Splunk journal files with streaming support.
    """

    def __init__(self):
        self._s3_client = None

    @property
    def s3_client(self):
        """Lazy initialization of S3 client"""
        if self._s3_client is None:
            self._s3_client = boto3.client("s3")
        return self._s3_client

    def extract(
        self,
        input_path: Optional[str] = None,
        output_path: Optional[str] = None,
        output_format: str = "ndjson",
    ) -> int:
        """
        Extract journal to output with automatic compression detection

        Args:
            input_path: Local file path, s3://bucket/key, or None for stdin
            output_path: Local file path, s3://bucket/key, or None for stdout
            output_format: 'ndjson', 'csv', 'parquet' (default: ndjson)
            input_compression: 'auto' (detect from filename), 'zst', 'gz', 'none'
            output_compression: 'auto' (detect from filename), 'gz', 'none'

        Returns:
            Number of events extracted
        """
        input_desc = input_path or "stdin"
        output_desc = output_path or "stdout"
        logger.info(f"Extracting {input_desc} -> {output_desc} (format: {output_format})")

        input_stream = self._open_input(input_path)

        # Create decoder with streaming reader
        decoder = JournalDecoder(reader=input_stream)

        formatter = get_formatter(output_format)

        # Process events line by line
        event_count = 0
        with self._open_output(output_path) as output_writer:
            with formatter(output_stream=output_writer) as writer:
                while decoder.scan():
                    event = decoder.get_event()
                    event_data = event.to_normalized_dict()
                    writer.write(event_data)
                    event_count += 1

                    # Log progress
                    if event_count % 10000 == 0:
                        logger.debug(f"Processed {event_count} events")

                if decoder.err():
                    raise decoder.err()

        logger.info(f"Successfully extracted {event_count} events")
        return event_count

    def _open_stdin_input(self) -> io.BufferedReader:
        """
        Open stdin with optional decompression

        Args:
            compression: 'zst', 'gz', or 'none' (default: 'none')

        Returns:
            BufferedReader ready for decoding
        """
        logger.debug("Opening stdin for input")

        # Get stdin as binary stream
        stdin_stream = sys.stdin.buffer

        return io.BufferedReader(stdin_stream)

    def _apply_decompression(self, filename: str, stream) -> io.BufferedReader:
        """
        Apply decompression to stream based on filename extension

        Args:
            filename: Filename or path (used to detect compression type)
            stream: Raw byte stream (file object or S3 Body)

        Returns:
            BufferedReader with decompressed stream
        """
        filename_lower = filename.lower()

        if filename_lower.endswith(".zst"):
            # Zstandard streaming decompression
            dctx = zstd.ZstdDecompressor()
            decompressed = dctx.stream_reader(stream)
            return decompressed

        elif filename_lower.endswith(".gz"):
            # Gzip streaming decompression
            decompressed = gzip.GzipFile(fileobj=stream)
            return decompressed

        else:
            # Uncompressed
            return stream

    def _open_input(self, path: str) -> io.BufferedReader:
        """
        Open input stream with automatic compression detection

        Supports:
        - Local files: /path/to/journal.zst
        - S3 URIs: s3://bucket/key/journal.zst
        - Compression: .zst, .gz, uncompressed

        Returns:
            BufferedReader ready for decoding (decompressed if needed)
        """
        if path is None:
            return self._open_stdin_input()
        if path.startswith("s3://"):
            return self._open_s3_input(path)
        else:
            return self._open_local_input(path)

    def _open_local_input(self, path: str) -> io.BufferedReader:
        """Open local file with automatic decompression"""
        file_path = Path(path)

        if not file_path.exists():
            raise FileNotFoundError(f"Input file not found: {path}")

        # Open raw file
        raw_file = open(file_path, "rb")

        # Apply decompression based on extension
        return self._apply_decompression(path, raw_file)

    def _open_s3_input(self, s3_uri: str) -> io.BufferedReader:
        """
        Open S3 object with automatic decompression (streaming, no download)

        Args:
            s3_uri: S3 URI like s3://bucket/path/to/journal.zst

        Returns:
            BufferedReader with decompressed stream
        """
        # Parse S3 URI
        parsed = urlparse(s3_uri)
        bucket = parsed.netloc
        key = parsed.path.lstrip("/")

        logger.debug(f"Opening S3 stream: bucket={bucket}, key={key}")

        # Get streaming body from S3
        response = self.s3_client.get_object(Bucket=bucket, Key=key)
        s3_stream = response["Body"]

        # Apply decompression based on key extension
        return self._apply_decompression(key, s3_stream)

    def _open_output(self, path: str):
        """
        Create output writer for local file or S3

        Args:
            path: Local file path or s3://bucket/key
            output_format: 'ndjson', 'csv', 'parquet'

        Returns:
            Writer object with write() and close() methods
        """
        if not path:
            # Stdout output
            output = StdoutWriter()
        elif path.startswith("s3://"):
            # S3 output - write to buffer then upload
            output = S3Writer(path, self.s3_client)
        else:
            # Local file output
            output_path = Path(path)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Map ndjson to json for get_output_writer (it calls it 'json')
            output = FileWriter(str(output_path))

        return output
