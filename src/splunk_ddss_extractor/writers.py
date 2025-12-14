import gzip
import io
import logging
import sys
from typing import Any, Dict, Optional, Tuple

import boto3
import zstandard as zstd

logger = logging.getLogger(__name__)


class OutputWriter:

    def _get_compression(self, filename: str, stream) -> io.BufferedWriter:
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
            dctx = zstd.ZstdCompressor()
            self.compressor = dctx.stream_writer(stream)
            return io.BufferedWriter(self.compressor)

        elif filename_lower.endswith(".gz"):
            # Gzip streaming decompression
            self.compressor = gzip.GzipFile(fileobj=stream)
            return io.BufferedWriter(self.compressor)

        else:
            # Uncompressed
            return io.BufferedWriter(stream)

    def __init__(self):
        self.compressor: Optional[Any] = None

    def write(self, data: str):
        raise NotImplementedError()

    def close(self):
        if self.compressor:
            self.compressor.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()


class StdoutWriter(OutputWriter):
    """
    Writer that outputs to stdout

    Note: Compression to stdout is supported but uncommon.
    """

    def __init__(self):
        super().__init__()
        self.file = sys.stdout

    def write(self, data: str):
        """Write event to stdout"""
        self.file.write(data)

    def close(self):
        """Close file if needed"""


class FileWriter(OutputWriter):
    """
    Writer that outputs to local file

    Supports optional gzip or zstd compression based on file extension.
    """

    def __init__(self, file_path: str):
        super().__init__()
        self.file_path = file_path
        self.file = open(file_path, "wb")
        self.file = self._get_compression(file_path, self.file)

    def write(self, data: str):
        """Write event to file"""
        self.file.write(data.encode("utf-8"))

    def close(self):
        """Close file"""
        self.file.close()


class S3Writer(OutputWriter):
    """
    Writer that buffers output and uploads to S3 on close

    Note: Currently buffers in memory. For very large files,
    consider using multipart upload with streaming.
    """

    def _parse_s3_uri(self, s3_uri: str) -> Tuple[str, str]:
        """
        Parse S3 URI into bucket and key

        Args:
            s3_uri: S3 URI (e.g., s3://bucket/key)

        Returns:
            Tuple of (bucket, key)
        """
        if not s3_uri.startswith("s3://"):
            raise ValueError(f"Invalid S3 URI: {s3_uri}")

        path_parts = s3_uri[5:].split("/", 1)
        bucket = path_parts[0]
        key = path_parts[1] if len(path_parts) > 1 else ""

        return bucket, key

    def __init__(self, s3_uri: str, s3_client=None):
        self.s3_uri = s3_uri
        self.s3_client = s3_client or boto3.client("s3")

        self.bucket, self.key = self._parse_s3_uri(s3_uri)

        # Create in-memory buffer
        self.buffer = io.BytesIO()
        self.temp_file = self._get_compression(s3_uri, self.buffer)

    def write(self, event_data: Dict[str, Any]):
        """Write event to buffer"""
        self.temp_file.write(event_data)

    def close(self):
        """Flush buffer and upload to S3"""
        self.temp_file.close()

        # need to do it better here i guess. the issue is that usually super close should be called last
        # here we need to call it first to flush the buffer and finish compression
        super().close()

        # Get buffer contents
        data = self.buffer.getvalue()

        logger.info(
            f"Uploading to S3: s3://{self.bucket}/{self.key} ({len(data)} bytes)"
        )

        # Upload to S3
        self.s3_client.put_object(Bucket=self.bucket, Key=self.key, Body=data)

        logger.info(f"Successfully uploaded to s3://{self.bucket}/{self.key}")
