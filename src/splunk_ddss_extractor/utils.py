"""
Utility functions for Splunk Archiver
"""

import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, Optional


def setup_logging(level: str = "INFO") -> logging.Logger:
    """
    Setup logging configuration

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)

    Returns:
        Root logger
    """
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format=log_format,
        stream=sys.stdout
    )
    return logging.getLogger()


def parse_s3_event(event: Dict[str, Any]) -> Dict[str, str]:
    """
    Parse S3 event notification

    Args:
        event: S3 event dictionary

    Returns:
        Dictionary with bucket and key
    """
    try:
        record = event["Records"][0]
        s3_info = record["s3"]
        bucket = s3_info["bucket"]["name"]
        key = s3_info["object"]["key"]

        return {
            "bucket": bucket,
            "key": key,
            "size": s3_info["object"].get("size", 0),
            "event_name": record["eventName"]
        }
    except (KeyError, IndexError) as e:
        raise ValueError(f"Invalid S3 event format: {e}")


def format_json_line(event_data: Dict[str, Any]) -> str:
    """
    Format event as JSON line

    Args:
        event_data: Event dictionary

    Returns:
        JSON string
    """
    return json.dumps(event_data, ensure_ascii=False)


def format_csv_line(event_data: Dict[str, Any], include_header: bool = False) -> str:
    """
    Format event as CSV line

    Args:
        event_data: Event dictionary
        include_header: Whether to include header row

    Returns:
        CSV string
    """
    import csv
    import io

    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=["timestamp", "host", "source", "sourcetype", "message"]
    )

    if include_header:
        writer.writeheader()

    writer.writerow(event_data)
    return output.getvalue().strip()


def get_output_writer(output_format: str, output_file: Path, compress: bool = True):
    """
    Get appropriate output writer for format

    Args:
        output_format: Output format (json=NDJSON, csv, parquet)
        output_file: Output file path
        compress: Whether to gzip compress the output (default: True)
                  Note: json format outputs NDJSON (one JSON object per line)

    Returns:
        Writer object with write() method
    """
    if output_format == "json":
        return JSONLinesWriter(output_file, compress=compress)
    elif output_format == "csv":
        return CSVWriter(output_file, compress=compress)
    elif output_format == "parquet":
        return ParquetWriter(output_file, compress=compress)
    else:
        raise ValueError(f"Unsupported output format: {output_format}")


class JSONLinesWriter:
    """
    Write events as NDJSON (Newline Delimited JSON / JSON Lines) format

    Each event is written as a complete JSON object on a single line.
    This format is ideal for streaming processing and can be consumed line-by-line.

    Supports optional gzip compression.
    """

    def __init__(self, output_file: Path, compress: bool = True):
        import gzip

        self.compress = compress
        self.output_file = output_file

        if compress:
            # Add .gz extension if not present
            if not str(output_file).endswith('.gz'):
                self.output_file = Path(str(output_file) + '.gz')
            self.file = gzip.open(self.output_file, "wt", encoding="utf-8")
        else:
            self.file = open(output_file, "w", encoding="utf-8")

        self.count = 0

    def write(self, event_data: Dict[str, Any]):
        """Write event as JSON line"""
        self.file.write(format_json_line(event_data) + "\n")
        self.count += 1

    def close(self):
        """Close file"""
        self.file.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class CSVWriter:
    """Write events as CSV with optional gzip compression"""

    def __init__(self, output_file: Path, compress: bool = True):
        import csv
        import gzip
        import io

        self.compress = compress
        self.output_file = output_file

        if compress:
            # Add .gz extension if not present
            if not str(output_file).endswith('.gz'):
                self.output_file = Path(str(output_file) + '.gz')
            self.file = gzip.open(self.output_file, "wt", encoding="utf-8", newline="")
        else:
            self.file = open(output_file, "w", encoding="utf-8", newline="")

        self.writer = csv.DictWriter(
            self.file,
            fieldnames=["timestamp", "host", "source", "sourcetype", "message"]
        )
        self.writer.writeheader()
        self.count = 0

    def write(self, event_data: Dict[str, Any]):
        """Write event as CSV row"""
        self.writer.writerow(event_data)
        self.count += 1

    def close(self):
        """Close file"""
        self.file.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class ParquetWriter:
    """Write events as Parquet (requires pyarrow)

    Note: Parquet has built-in compression, so the compress parameter
    controls the compression method rather than gzip wrapper.
    """

    def __init__(self, output_file: Path, compress: bool = True):
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
            self.pa = pa
            self.pq = pq
        except ImportError:
            raise ImportError(
                "pyarrow required for Parquet output. "
                "Install with: pip install pyarrow"
            )

        self.output_file = output_file
        self.compress = compress
        self.events = []
        self.count = 0

    def write(self, event_data: Dict[str, Any]):
        """Buffer event for writing"""
        self.events.append(event_data)
        self.count += 1

    def close(self):
        """Write all buffered events to Parquet file"""
        if not self.events:
            return

        # Convert to PyArrow table
        table = self.pa.Table.from_pylist(self.events)

        # Write to Parquet with compression
        # Parquet format handles compression internally
        compression = "snappy" if self.compress else "none"

        self.pq.write_table(
            table,
            str(self.output_file),
            compression=compression
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
