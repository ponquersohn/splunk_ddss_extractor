# Splunk DDSS Extractor

Convert Splunk self-hosted storage archives from compressed journal format to raw format.

## Overview

Splunk DDSS Extractor is a Python library that processes Splunk journal archives, extracts events, and converts them to raw format for easier analysis and long-term storage. Use it in your own applications, data pipelines, or as a CLI tool.

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
from splunk_ddss_extractor.extractor import extract_to_file

# Extract to JSON Lines
extract_to_file('/path/to/journal.zst', 'output.json', 'json')

# Extract to CSV
extract_to_file('/path/to/journal.zst', 'output.csv', 'csv')

# Extract to Parquet
extract_to_file('/path/to/journal.zst', 'output.parquet', 'parquet')
```

**Stream events:**

```python
from splunk_ddss_extractor.decoder import JournalDecoder

decoder = JournalDecoder('/path/to/journal.zst')
for event in decoder.events():
    print(f"{event.timestamp}: {event.message}")
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

## License

Proprietary

## Contributing

See [CLAUDE.md](CLAUDE.md) for development guidelines.
