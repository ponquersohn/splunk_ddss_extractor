"""
High-level extraction interface for Splunk journal files
"""

import logging
from pathlib import Path
from typing import Dict, Any, Optional

from .decoder import JournalDecoder
from .utils import get_output_writer


logger = logging.getLogger(__name__)


def extract_journal(journal_path: str) -> list[Dict[str, Any]]:
    """
    Extract all events from a journal file

    Args:
        journal_path: Path to journal file or directory

    Returns:
        List of event dictionaries

    Raises:
        Exception: If extraction fails
    """
    logger.info(f"Extracting events from {journal_path}")

    decoder = JournalDecoder(journal_path)
    events = []

    try:
        while decoder.scan():
            event = decoder.get_event()

            event_data = {
                "timestamp": event.index_time,
                "host": decoder.host(),
                "source": decoder.source(),
                "sourcetype": decoder.source_type(),
                "message": event.message_string(),
                "stream_id": event.stream_id,
                "stream_offset": event.stream_offset,
            }

            events.append(event_data)

        if decoder.err():
            raise decoder.err()

    except Exception as e:
        logger.error(f"Error during extraction: {e}")
        raise

    logger.info(f"Extracted {len(events)} events")
    return events


def extract_to_file(
    journal_path: str,
    output_file: str,
    output_format: str = "json",
    compress: bool = True
) -> int:
    """
    Extract events from journal file and write to output file

    Args:
        journal_path: Path to journal file or directory
        output_file: Output file path
        output_format: Output format (json, csv, parquet)
        compress: Whether to gzip compress the output (default: True)
                  For JSON/CSV: creates .gz file
                  For Parquet: uses snappy compression internally

    Returns:
        Number of events extracted

    Raises:
        Exception: If extraction or writing fails
    """
    compress_note = " (compressed)" if compress else " (uncompressed)"
    logger.info(f"Extracting {journal_path} to {output_file} ({output_format}{compress_note})")

    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    decoder = JournalDecoder(journal_path)
    event_count = 0

    try:
        with get_output_writer(output_format, output_path, compress=compress) as writer:
            while decoder.scan():
                event = decoder.get_event()

                event_data = {
                    "timestamp": event.index_time,
                    "host": decoder.host(),
                    "source": decoder.source(),
                    "sourcetype": decoder.source_type(),
                    "message": event.message_string(),
                }

                writer.write(event_data)
                event_count += 1

                # Log progress
                if event_count % 10000 == 0:
                    logger.debug(f"Processed {event_count} events")

            if decoder.err():
                raise decoder.err()

    except Exception as e:
        logger.error(f"Error during extraction: {e}")
        raise

    logger.info(f"Successfully extracted {event_count} events to {output_file}")
    return event_count


def extract_batch(
    journal_paths: list[str],
    output_dir: str,
    output_format: str = "json"
) -> Dict[str, int]:
    """
    Extract multiple journal files to output directory

    Args:
        journal_paths: List of journal file paths
        output_dir: Output directory
        output_format: Output format (json, csv, parquet)

    Returns:
        Dictionary mapping input path to event count

    Raises:
        Exception: If extraction fails
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    results = {}

    for journal_path in journal_paths:
        try:
            # Generate output filename
            input_name = Path(journal_path).stem
            output_file = output_path / f"{input_name}.{output_format}"

            # Extract
            event_count = extract_to_file(
                journal_path,
                str(output_file),
                output_format
            )

            results[journal_path] = event_count

        except Exception as e:
            logger.error(f"Failed to extract {journal_path}: {e}")
            results[journal_path] = -1

    return results
