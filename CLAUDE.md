# Splunk DDSS Extractor

## Project Overview

This project provides a Python library to convert Splunk self-hosted storage archives from compressed journal format to raw format. The library extracts events from Splunk's journal files (with automatic compression detection) and outputs them in multiple formats (JSON Lines, CSV, Parquet).

**Attribution:** This project is based on the concept from [fionera/splunker](https://github.com/fionera/splunker), a Go implementation for extracting Splunk journal files. This Python implementation extends the original with streaming S3 support, multiple output formats, and production-ready features.

**Key Features:**
- Automatic compression detection (.zst, .gz, uncompressed)
- Multiple output formats (JSON Lines, CSV, Parquet)
- Streaming processing for large files
- Metadata extraction (host, source, sourcetype, timestamp)
- Simple Python API and CLI interface

## Architecture

This is a **Python library** designed to be imported and used in your own applications or scripts. It can be:
- Installed via pip as a dependency
- Used as a CLI tool
- Integrated into data pipelines (Lambda, ECS, local scripts, etc.)
- Run in Docker containers for isolated environments

### Core Components

1. **Journal Decoder** (`src/splunk_ddss_extractor/decoder.py`)
   - Decodes Splunk's binary journal format
   - Automatic compression detection and handling
   - Streaming interface for memory-efficient processing

2. **Extractor Interface** (`src/splunk_ddss_extractor/extractor.py`)
   - High-level API for extraction tasks
   - Multiple output format support
   - Simple function calls for common use cases

3. **Utility Functions** (`src/splunk_ddss_extractor/utils.py`)
   - Output writers (JSON, CSV, Parquet)
   - Logging helpers
   - Optional S3 integration utilities

## Directory Structure

```
splunk_ddss_extractor/
├── CLAUDE.md                        # This file - project documentation
├── README.md                        # User-facing documentation
├── .gitignore                       # Git ignore patterns
├── requirements.txt                 # Python dependencies
├── setup.py                         # Python package setup
├── Makefile                         # Build and test automation
│
├── src/splunk_ddss_extractor/       # Python library
│   ├── __init__.py                  # Package initialization
│   ├── decoder.py                   # Journal decoder (core logic)
│   ├── extractor.py                 # High-level extraction interface
│   └── utils.py                     # Utility functions (output writers, logging)
│
├── docker/                          # Container definitions
│   ├── Dockerfile                   # For containerized environments
│   ├── docker-compose.yml           # Local development setup
│   └── .dockerignore
│
├── scripts/                         # Utility scripts
│   └── run_extractor.py             # Example extraction script
│
└── tests/                           # Test suite
    ├── test_decoder.py
    └── test_compression.py
```

## Key Features

### Automatic Compression Detection

The Extractor class automatically detects and handles compression based on file extension:

```python
from splunk_ddss_extractor.extractor import Extractor

extractor = Extractor()

# All these work automatically
extractor.extract("journal.zst", "output.json", "ndjson")  # Zstandard
extractor.extract("journal.gz", "output.json", "ndjson")   # Gzip
extractor.extract("journal", "output.json", "ndjson")      # Uncompressed
extractor.extract("s3://bucket/journal.zst", "output.json", "ndjson")  # S3 with auto-detect
```

**Supported Formats:**
- `.zst` - Zstandard compression (requires `zstandard` package)
- `.gz` - Gzip compression (built-in Python)
- No extension or other - Uncompressed plain text

**Note:** The low-level `JournalDecoder` class requires an uncompressed stream and does not perform automatic decompression. Use `Extractor` for automatic compression handling.

### Output Formats

Raw archive formats supported:
- **JSON Lines** (default): One event per line, easy to stream
- **CSV**: Compatible with spreadsheets and analytics tools
- **Parquet**: Columnar format optimized for analytics (requires pyarrow)

### Simple API

```python
from splunk_ddss_extractor.extractor import Extractor

extractor = Extractor()

# Extract to JSON Lines (ndjson)
extractor.extract(
    input_path='/path/to/journal.zst',
    output_path='output.json',
    output_format='ndjson'
)

# Extract to CSV
extractor.extract(
    input_path='/path/to/journal.zst',
    output_path='output.csv',
    output_format='csv'
)

# Extract to Parquet
extractor.extract(
    input_path='/path/to/journal.zst',
    output_path='output.parquet',
    output_format='parquet'
)

# Extract from S3 (streaming, no download)
extractor.extract(
    input_path='s3://bucket/path/journal.zst',
    output_path='output.json',
    output_format='ndjson'
)

# Extract to S3 (streaming upload)
extractor.extract(
    input_path='/path/to/journal.zst',
    output_path='s3://bucket/output/data.json',
    output_format='ndjson'
)
```

## Testing Results

### Production Archive Testing
Successfully tested with real production archives from S3:
- File: `s3://my-company-splunk-archives/archives/db_*/rawdata/journal.zst`
- Format: Zstandard-compressed Splunk journal
- Result: Successfully extracted events with full metadata
- Output: Verified JSON and CSV formats work correctly

### Compression Format Testing
All compression formats tested and verified:
- ✓ `.zst` (Zstandard) - 3,370 bytes → 1 event
- ✓ `.gz` (Gzip) - 3,134 bytes → 1 event
- ✓ Uncompressed - 15,281 bytes → 1 event
- ✓ Directory mode with auto-detection

Compression savings: ~78% for zst, ~79% for gz

Example extracted event:
```json
{
  "timestamp": 1761643257,
  "host": "host::http-inputs-mycompany.splunkcloud.com",
  "source": "source::s3://my-company-splunk-logs/application/...",
  "sourcetype": "sourcetype::aws:cloudtrail",
  "message": "{\"eventVersion\":\"1.08\",\"eventName\":\"DescribeInstances\",...}"
}
```

## Current Status

### Completed ✓
- Original extraction logic from fionera/splunker concept
- **Automatic compression detection** (.zst, .gz, uncompressed)
- Fixed file handling for all compression formats
- Python library with `Extractor` class interface
- **Multi-format output** (ndjson/JSON Lines, CSV, Parquet)
- **Streaming S3 support** (read and write directly to/from S3, no temp files)
- **CLI tool** (`python -m splunk_ddss_extractor.main`)
- **Stdin/stdout streaming** support
- Tested with real production archives and all compression formats
- Makefile for development workflow
- Docker support for containerized environments

### TODO
1. ~~Refactor into proper Python module~~ ✓ Complete
2. ~~Add CLI entry point~~ ✓ Complete
3. ~~Add streaming S3 support~~ ✓ Complete
4. Add error handling and retry logic improvements
5. Write comprehensive tests (expand test coverage)
6. Create detailed API documentation (docstrings, Sphinx docs)
7. Implement batch processing for large files (parallel processing)
8. Add progress bars for large files
9. Publish to PyPI
10. Add incremental processing with checkpoints

## Development Workflow

### Using Makefile Commands

```bash
# Complete development setup
make dev-setup           # Creates venv and installs dependencies

# Development tasks
make install             # Install dependencies
make test                # Run tests
make test-coverage       # Run tests with coverage
make check               # Run all checks (tests)

# Docker
make docker              # Build Docker image
make docker-run          # Run container locally

# Cleanup
make clean               # Clean temporary files
make clean-all           # Clean everything including venv

# Info
make env                 # Show environment and available commands
make version             # Show version information
```

### Local Development

```bash
# Create virtual environment
make venv
source venv/bin/activate

# Install dependencies
make install

# Run tests
make test

# Test extraction using the library
python -c "
from splunk_ddss_extractor.extractor import Extractor
extractor = Extractor()
extractor.extract('/path/to/journal.zst', 'output.json', 'ndjson')
"
```

### Docker Development

```bash
# Build and run in Docker
make docker
make docker-run

# Or manually
docker build -t splunk-ddss-extractor:latest -f docker/Dockerfile .
docker run --rm -it splunk-ddss-extractor:latest
```

### Installing as a Library

```bash
# Install in development mode
pip install -e .

# Or install from source
pip install .

# With optional dependencies
pip install -e ".[parquet]"  # Adds pyarrow for Parquet support
pip install -e ".[s3]"        # Adds boto3 for S3 integration
pip install -e ".[dev]"       # Adds development dependencies
```

## Usage Examples

### Basic Usage

```python
from splunk_ddss_extractor.extractor import Extractor

# Simple extraction
extractor = Extractor()
extractor.extract('journal.zst', 'output.json', 'ndjson')
```

### Advanced Usage (Low-level API)

```python
from splunk_ddss_extractor.decoder import JournalDecoder
import zstandard as zstd

# For compressed files, decompress first, then pass to decoder
with open('journal.zst', 'rb') as compressed_file:
    dctx = zstd.ZstdDecompressor()
    with dctx.stream_reader(compressed_file) as reader:
        decoder = JournalDecoder(reader=reader)
        while decoder.scan():
            event = decoder.get_event()
            print(f"Timestamp: {event.index_time}")
            print(f"Host: {decoder.host()}")
            print(f"Source: {decoder.source()}")
            print(f"Sourcetype: {decoder.source_type()}")
            print(f"Message: {event.message_string()}")
```

### CLI Usage

The CLI tool is available via `python -m splunk_ddss_extractor.main`:

```bash
# Extract to JSON
python -m splunk_ddss_extractor.main -i journal.zst -o output.json -f ndjson

# Extract to CSV
python -m splunk_ddss_extractor.main -i journal.zst -o output.csv -f csv

# Extract from S3 (streaming, no download)
python -m splunk_ddss_extractor.main -i s3://bucket/path/journal.zst -o output.json

# Extract to S3 (streaming upload)
python -m splunk_ddss_extractor.main -i journal.zst -o s3://bucket/output/data.json

# Stdin to stdout
cat journal.zst | python -m splunk_ddss_extractor.main > output.json

# S3 to stdout (streaming)
python -m splunk_ddss_extractor.main -i s3://bucket/path/journal.zst > output.json
```

### Integration Examples

**AWS Lambda (Streaming - No Downloads):**
```python
from splunk_ddss_extractor.extractor import Extractor

def lambda_handler(event, context):
    extractor = Extractor()

    # Extract directly from S3 to S3 (streaming, no temp files!)
    event_count = extractor.extract(
        input_path='s3://input-bucket/path/journal.zst',
        output_path='s3://output-bucket/path/output.json',
        output_format='ndjson'
    )

    return {'statusCode': 200, 'events_extracted': event_count}
```

**AWS Lambda (Legacy - with Download):**
```python
import boto3
from splunk_ddss_extractor.extractor import Extractor

def lambda_handler(event, context):
    s3 = boto3.client('s3')
    extractor = Extractor()

    # Download from S3
    s3.download_file('bucket', 'journal.zst', '/tmp/journal.zst')

    # Extract
    extractor.extract('/tmp/journal.zst', '/tmp/output.json', 'ndjson')

    # Upload result
    s3.upload_file('/tmp/output.json', 'bucket', 'output.json')
```

**ECS/Fargate Task:**
```python
from splunk_ddss_extractor.extractor import Extractor
import os

extractor = Extractor()

# Read from environment
input_file = os.environ['INPUT_FILE']  # Can be local or s3://
output_file = os.environ['OUTPUT_FILE']  # Can be local or s3://
format = os.environ.get('FORMAT', 'ndjson')

event_count = extractor.extract(input_file, output_file, format)
print(f"Extracted {event_count} events")
```

## Known Issues

From `extract_journal.py`:
- Extended storage handling not fully implemented (line 473)
- Some metadata types might not be fully parsed

**Fixed Issues:**
- ✓ Direct .zst file handling now works correctly
- ✓ Decompression logic properly handles all input types

## Dependencies

### Core Dependencies
- `zstandard`: Zstandard decompression (required)
- Standard library: `struct`, `io`, `dataclasses`

### Optional Dependencies
- `boto3`: AWS SDK (for S3 integration)
- `click`: CLI interface
- `pyarrow`: Parquet support

### Development Dependencies
- `pytest`: Testing framework
- `pytest-cov`: Coverage reporting

## Library API

### Main Classes

**`Extractor`** (`from splunk_ddss_extractor.extractor import Extractor`)

High-level interface for extraction tasks.

Methods:
- `extract(input_path, output_path, output_format='ndjson')` - Extract journal to output format
  - `input_path`: Local file path, `s3://bucket/key`, or `None` for stdin
  - `output_path`: Local file path, `s3://bucket/key`, or `None` for stdout
  - `output_format`: `'ndjson'`, `'csv'`, or `'parquet'`
  - Returns: Number of events extracted
  - Supports streaming S3 operations (no temp files)
  - Automatic compression detection (.zst, .gz, uncompressed)

**`JournalDecoder`** (`from splunk_ddss_extractor.decoder import JournalDecoder`)

Low-level decoder for journal files. Requires uncompressed stream input.

Constructor:
- `JournalDecoder(reader)` - Pass a file-like reader object (must be uncompressed)

Methods:
- `scan()` - Scan for next event, returns `True` if found
- `get_event()` - Get current event object
- `host()` - Get host metadata for current event
- `source()` - Get source metadata for current event
- `source_type()` - Get sourcetype metadata for current event
- `err()` - Get last error if any

**`Event`** (class from decoder)

Event object returned by `get_event()`:
- `index_time` - Unix timestamp
- `message_string()` - Get event message as string
- Additional fields for internal use

## Testing

```bash
# Run all tests
make test

# Run with coverage
make test-coverage

# Run specific test
pytest tests/test_decoder.py -v

# Run with verbose output
pytest tests/ -vv
```

## Future Enhancements

- [x] ~~Complete refactoring of decoder into proper module~~
- [x] ~~Add CLI entry point with argument parsing~~
- [x] ~~Streaming S3 support (read/write directly)~~
- [ ] Publish to PyPI as installable package
- [ ] Add progress bars for large files
- [ ] Batch processing for large files
- [ ] Parallel processing support for multiple files
- [ ] Incremental processing with checkpoints
- [ ] Enhanced error handling and retries
- [ ] Archive compaction/deduplication
- [ ] More integration examples for common platforms (Airflow, Step Functions, etc.)
- [ ] Performance profiling and optimization
- [ ] Comprehensive docstrings and Sphinx documentation

## Troubleshooting

### Installation Issues

**"ModuleNotFoundError: No module named 'zstandard'"**
```bash
pip install zstandard
```

**"ModuleNotFoundError: No module named 'pyarrow'"**
```bash
pip install pyarrow  # For Parquet support
```

### Extraction Issues

**"EOFError" during extraction**
- Ensure zstandard is installed: `pip install zstandard`
- Check if file is actually a .zst compressed file
- Verify file is not corrupted

**"Permission denied" errors**
- Check file permissions
- Ensure output directory exists and is writable

**High memory usage**
- Use streaming mode instead of loading all events
- Process files in smaller batches
- Consider increasing available memory

### Performance Issues

**Slow extraction**
- Check if compression detection is working (should auto-detect)
- Use faster output formats (JSON Lines faster than CSV)
- Consider parallel processing for multiple files
- Use Parquet for large datasets (better compression)

## Contributing

This is a library project. To contribute:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Run `make check` to verify tests pass
6. Submit a pull request

## License

[Add license information here]