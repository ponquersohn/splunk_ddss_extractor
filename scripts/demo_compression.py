#!/usr/bin/env python3
"""
Demo: Automatic Compression Detection

This script demonstrates the decoder's ability to automatically detect
and handle different compression formats.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from splunk_ddss_extractor.decoder import JournalDecoder, get_compression_type
from splunk_ddss_extractor.extractor import extract_to_file


def demo_compression_detection():
    """Demonstrate compression type detection"""
    print("=" * 60)
    print("Compression Detection Demo")
    print("=" * 60)
    print()

    test_files = [
        "journal.zst",
        "journal.gz",
        "journal",
        "rawdata/journal.zst",
        "archive.log",
    ]

    print("File Extension -> Detected Compression Type")
    print("-" * 60)
    for filename in test_files:
        compression = get_compression_type(filename)
        print(f"  {filename:30} -> {compression}")
    print()


def demo_extraction(test_files):
    """Demonstrate extraction from different formats"""
    print("=" * 60)
    print("Extraction Demo")
    print("=" * 60)
    print()

    for test_file in test_files:
        if not Path(test_file).exists():
            print(f"⊗ {test_file}: File not found")
            continue

        try:
            decoder = JournalDecoder(test_file)
            event_count = 0

            while decoder.scan():
                event_count += 1

            compression = get_compression_type(test_file)
            file_size = Path(test_file).stat().st_size
            print(f"✓ {test_file}")
            print(f"  Compression: {compression}")
            print(f"  Size: {file_size:,} bytes")
            print(f"  Events: {event_count}")
            print()

        except Exception as e:
            print(f"✗ {test_file}: {e}")
            print()


def main():
    """Main demo"""
    # Demo 1: Compression detection
    demo_compression_detection()

    # Demo 2: Extraction (if test files exist)
    test_files = [
        "/tmp/splunk_test/journal.zst",
        "/tmp/splunk_test/journal.gz",
        "/tmp/splunk_test/journal",
    ]

    available_files = [f for f in test_files if Path(f).exists()]

    if available_files:
        demo_extraction(available_files)
    else:
        print("No test files available for extraction demo")
        print("Create test files with:")
        print("  python extract_journal.py <source_file>")
        print()

    # Summary
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    print()
    print("The decoder automatically detects compression based on file")
    print("extension and handles decompression transparently:")
    print()
    print("  • .zst files  -> Zstandard decompression")
    print("  • .gz files   -> Gzip decompression")
    print("  • Other files -> Uncompressed (plain text)")
    print()
    print("This works seamlessly with:")
    print("  • Direct file paths")
    print("  • Directory paths (auto-finds rawdata/journal.*)")
    print("  • Module interface (extract_to_file)")
    print()


if __name__ == "__main__":
    main()
