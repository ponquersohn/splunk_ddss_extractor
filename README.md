# Splunk DDSS Extractor

Convert Splunk self-hosted storage archives from compressed journal format to raw format.

## Overview

Splunk DDSS Extractor is a Python library that processes Splunk journal archives, extracts events, and converts them to raw format for easier analysis and long-term storage. Use it in your own applications, data pipelines, or as a CLI tool.

**Note:** This project is based on the concept from [fionera/splunker](https://github.com/fionera/splunker), reimplemented in Python with additional features for production use.

## Features

- Automatic compression detection (.zst, .gz, uncompressed)
- Extract events with full metadata (host, source, sourcetype, timestamps)
- Multiple output formats (JSON Lines, CSV, Parquet)
- Streaming processing for memory efficiency
- Simple Python API and CLI interface
- Docker support for containerized deployments
- Integrates with AWS Lambda, ECS, or any Python environment

## Quick Start

### Using the Makefile (Recommended)

```bash
# Show all available commands
make env

# Complete development setup (venv + dependencies)
make dev-setup

# Run tests
make test

# Build Docker image
make docker
```

### Manual Setup

#### Installation

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install -e .

# Optional: Install Parquet support
pip install pyarrow
```

#### Basic Usage

**Extract a journal file:**

```python
from splunk_ddss_extractor.extractor import Extractor

extractor = Extractor()

# Extract to JSON Lines
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

# Extract from S3 to local file (streaming, no download)
extractor.extract(
    input_path='s3://bucket/path/journal.zst',
    output_path='output.json',
    output_format='ndjson'
)

# Extract from local to S3
extractor.extract(
    input_path='/path/to/journal.zst',
    output_path='s3://bucket/output/data.json',
    output_format='ndjson'
)
```

**Low-level streaming (advanced):**

```python
from splunk_ddss_extractor.decoder import JournalDecoder
import zstandard as zstd

# For low-level access, decoder needs an uncompressed stream
# If reading a compressed file, decompress it first:
with open('/path/to/journal.zst', 'rb') as compressed_file:
    dctx = zstd.ZstdDecompressor()
    with dctx.stream_reader(compressed_file) as reader:
        decoder = JournalDecoder(reader=reader)
        while decoder.scan():
            event = decoder.get_event()
            print(f"Host: {decoder.host()}")
            print(f"Source: {decoder.source()}")
            print(f"Sourcetype: {decoder.source_type()}")
            print(f"Timestamp: {event.index_time}")
            print(f"Message: {event.message_string()}")

# For uncompressed journal files:
with open('/path/to/journal', 'rb') as f:
    decoder = JournalDecoder(reader=f)
    while decoder.scan():
        event = decoder.get_event()
        # Process event...
```

#### Docker Usage

```bash
# Build image
make docker

# Run with local file
docker run -v /path/to/data:/data ghcr.io/ponquersohn/splunk_ddss_extractor:latest

# Use in your own Dockerfile
FROM ghcr.io/ponquersohn/splunk_ddss_extractor:latest
COPY your_script.py /app/
CMD ["python", "/app/your_script.py"]
```

## Architecture

This is a **Python library** with the following components:

1. **Journal Decoder** - Low-level decoder for Splunk's binary journal format
2. **Extractor Interface** - High-level API for common extraction tasks
3. **Output Writers** - Support for JSON, CSV, and Parquet formats
4. **Compression Detection** - Automatic detection and handling of .zst, .gz formats

**Integration Options:**
- Direct Python import in your applications
- AWS Lambda functions for serverless processing
- ECS/Fargate tasks for batch processing
- Docker containers for isolated environments
- Local scripts for one-off extractions

See [CLAUDE.md](CLAUDE.md) for detailed architecture documentation.

## Development

### Quick Commands

```bash
# Run tests
make test

# Run tests with coverage
make test-coverage

# Build Docker image
make docker

# Test Docker locally
make docker-run

# Run all checks (tests)
make check

# Clean temporary files
make clean
```

### Manual Commands

```bash
# Run tests
pytest tests/

# Code formatting
black src/ tests/

# Local Docker testing
cd docker
docker-compose up
```

## Configuration

When integrating with AWS or other environments, you may use these environment variables:

- `OUTPUT_FORMAT`: Output format - json, csv, or parquet (default: json)
- `LOG_LEVEL`: Logging level (default: INFO)
- `AWS_REGION`: AWS region for S3 operations (default: us-east-1)
- `S3_BUCKET`: S3 bucket name (for S3 integrations)

## Output Formats

### JSON Lines (default)

```json
{"timestamp": 1234567890, "host": "server01", "source": "/var/log/app.log", "sourcetype": "app", "message": "Event data"}
```

### CSV

```csv
timestamp,host,source,sourcetype,message
1234567890,server01,/var/log/app.log,app,"Event data"
```

### Parquet

Columnar format optimized for analytics (requires pyarrow).

## Credits

This project is inspired by and based on the concept from [fionera/splunker](https://github.com/fionera/splunker), a Go implementation for extracting Splunk journal files. This Python implementation extends the original concept with:

- Streaming S3 support (no temporary files)
- Multiple output formats (JSON Lines, CSV, Parquet)
- Python library API for easy integration
- Docker and AWS deployment options

## License

Proprietary

## Contributing

See [CLAUDE.md](CLAUDE.md) for development guidelines.
