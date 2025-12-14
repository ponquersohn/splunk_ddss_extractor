#!/usr/bin/env python3
"""
CLI interface for Splunk DDSS Extractor

Extract Splunk journal files to raw format (JSON Lines, CSV, or Parquet).
Supports local files, S3 URIs, and stdin/stdout streaming.
"""

import argparse
import logging
import sys
from typing import Optional

from .extractor import Extractor

logger = logging.getLogger(__name__)


def setup_logging(log_level: str) -> None:
    """Configure logging with specified level"""
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


def parse_args() -> argparse.Namespace:
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        prog="splunk-extract",
        description="Extract Splunk journal files to raw format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Local file to local file
  %(prog)s -i journal.zst -o output.json

  # S3 to S3 (streaming, no downloads)
  %(prog)s -i s3://bucket/path/journal.zst -o s3://bucket/output/data.json

  # S3 to local (streaming)
  %(prog)s -i s3://bucket/path/journal.zst -o output.json

  # Local to S3
  %(prog)s -i journal.zst -o s3://bucket/output/data.json

  # Stdin to stdout
  cat journal.zst | %(prog)s > output.json

  # S3 to stdout (streaming)
  %(prog)s -i s3://bucket/path/journal.zst > output.json

  # Stdin to S3
  cat journal.zst | %(prog)s -o s3://bucket/output/data.json

  # Specify output format
  %(prog)s -i journal.zst -o output.csv -f csv
  %(prog)s -i journal.zst -o output.parquet -f parquet

Supported formats:
  - ndjson (newline-delimited JSON, default)
  - csv
  - parquet

Compression:
  - Input: Automatic detection (.zst, .gz, or uncompressed)
  - Output: Automatic based on extension (.gz for gzip)
        """,
    )

    parser.add_argument(
        "-i",
        "--input-file",
        "--input",
        dest="input_file",
        help="Input journal file (local path or s3://bucket/key). If not provided, reads from stdin.",
    )

    parser.add_argument(
        "-o",
        "--output-file",
        "--output",
        dest="output_file",
        help="Output file (local path or s3://bucket/key). If not provided, writes to stdout.",
    )

    parser.add_argument(
        "-f",
        "--format",
        "--output-format",
        dest="output_format",
        default="ndjson",
        choices=["ndjson", "csv", "parquet"],
        help="Output format (default: ndjson)",
    )

    parser.add_argument(
        "-l",
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level (default: INFO)",
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose output (equivalent to --log-level DEBUG)",
    )

    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress informational output (equivalent to --log-level WARNING)",
    )

    return parser.parse_args()


def determine_log_level(args: argparse.Namespace) -> str:
    """Determine log level from arguments"""
    if args.verbose:
        return "DEBUG"
    elif args.quiet:
        return "WARNING"
    else:
        return args.log_level


def main() -> int:
    """Main entry point for CLI"""
    try:
        args = parse_args()
        log_level = determine_log_level(args)
        setup_logging(log_level)

        logger.debug(f"Arguments: {args}")

        # Create extractor and run extraction
        extractor = Extractor()

        event_count = extractor.extract(
            input_path=args.input_file,
            output_path=args.output_file,
            output_format=args.output_format,
        )

        logger.info(f"Successfully extracted {event_count} events")
        return 0

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        return 130

    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        return 2

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
