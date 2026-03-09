import csv
import io
from typing import Any, Dict

import orjson


class OutputFormatter:
    """Base writer class"""

    def __init__(self, output_stream):
        self.output_stream = output_stream

    def write(self, event_data: Dict[str, Any]):
        """Write event data (to be implemented by subclasses)"""
        raise NotImplementedError()

    def close(self):
        """Close writer (to be implemented by subclasses)"""
        raise NotImplementedError()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()


_NEWLINE = b"\n"


class JSONLinesFormatter(OutputFormatter):
    """
    Write events as NDJSON (Newline Delimited JSON / JSON Lines) format

    Each event is written as a complete JSON object on a single line.
    This format is ideal for streaming processing and can be consumed line-by-line.

    Supports optional gzip compression.
    """

    def __init__(self, output_stream):
        super().__init__(output_stream=output_stream)
        self.count = 0

    def write(self, event_data: Dict[str, Any]):
        """Write event as JSON line (bytes via orjson)"""
        self.output_stream.write_bytes(orjson.dumps(event_data) + _NEWLINE)
        self.count += 1

    def close(self):
        """Close file"""


class CSVFormatter(OutputFormatter):
    """Write events as CSV with optional gzip compression"""

    def __init__(self, output_stream: io.TextIOWrapper):
        super().__init__(output_stream=output_stream)
        self.writer = csv.DictWriter(
            self.output_stream,
            fieldnames=["timestamp", "host", "source", "sourcetype", "message"],
        )
        self.writer.writeheader()
        self.count = 0

    def write(self, event_data: Dict[str, Any]):
        """Write event as CSV row"""
        self.writer.writerow(event_data)
        self.count += 1

    def close(self):
        """Close file"""
        return


class ParquetFormatter(OutputFormatter):
    """Write events as Parquet (requires pyarrow)

    This needs redesign so its now disabled.
    """


def get_formatter(format_type: str) -> Any:
    """
    Get appropriate output formatter class for format

    Args:
        format_type: Output format (json=NDJSON, csv, parquet)

    Returns:
        Formatter class
    """
    if format_type == "ndjson":
        return JSONLinesFormatter
    elif format_type == "csv":
        return CSVFormatter
    elif format_type == "parquet":
        return ParquetFormatter
    else:
        raise ValueError(f"Unsupported output format: {format_type}")
