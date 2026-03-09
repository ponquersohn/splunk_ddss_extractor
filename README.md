# Splunk DDSS Extractor

Convert Splunk self-hosted storage archives from compressed journal format to raw format.

## Overview

Splunk DDSS Extractor is a Python library (with a Rust native extension for performance) that processes Splunk journal archives, extracts events, and converts them to common formats for analysis and long-term storage.

**Key highlights:**
- **Rust-accelerated decoding** via PyO3 native extension (~2.7x faster than pure Python)
- Automatic compression detection (.zst, .gz, uncompressed)
- Multiple output formats: JSON Lines, CSV, Parquet
- Streaming S3 support (read/write directly, no temp files)
- CLI tool and Python API

Based on the concept from [fionera/splunker](https://github.com/fionera/splunker), extended with streaming S3 support, multiple output formats, Rust performance, and production-ready features.

## Installation

```bash
pip install splunk-ddss-extractor
```

With optional extras:

```bash
pip install splunk-ddss-extractor[s3]       # S3 streaming support (boto3)
pip install splunk-ddss-extractor[parquet]   # Parquet output (pyarrow)
pip install splunk-ddss-extractor[cli]       # CLI dependencies (click)
```

Pre-built wheels with the native Rust extension are available for Linux x86_64 and aarch64 (Python 3.10-3.13). The library falls back to a pure-Python decoder if the native extension is unavailable.

## Quick Start

### CLI

```bash
# Extract to JSON Lines
splunk-extract -i journal.zst -o output.json -f ndjson

# Extract to CSV
splunk-extract -i journal.zst -o output.csv -f csv

# Extract to Parquet
splunk-extract -i journal.zst -o output.parquet -f parquet

# S3 to local (streaming)
splunk-extract -i s3://bucket/path/journal.zst -o output.json

# S3 to S3 (streaming, no temp files)
splunk-extract -i s3://bucket/input/journal.zst -o s3://bucket/output/data.json

# Stdin/stdout
cat journal.zst | splunk-extract > output.json

# Enable debug tracing
splunk-extract -i journal.zst -o output.json --trace
```

### Python API

```python
from splunk_ddss_extractor.extractor import Extractor

extractor = Extractor()

# All compression formats are auto-detected
extractor.extract("journal.zst", "output.json", "ndjson")    # Zstandard
extractor.extract("journal.gz", "output.csv", "csv")          # Gzip
extractor.extract("journal", "output.parquet", "parquet")      # Uncompressed

# Streaming S3 (no temp files)
extractor.extract("s3://bucket/journal.zst", "s3://bucket/output.json", "ndjson")
```

### Low-level Decoder (Advanced)

The native decoder provides direct access to the binary journal format:

```python
from splunk_ddss_extractor import NativeJournalDecoder
import zstandard as zstd

with open("journal.zst", "rb") as f:
    dctx = zstd.ZstdDecompressor()
    with dctx.stream_reader(f) as reader:
        decoder = NativeJournalDecoder(reader=reader)
        while decoder.scan():
            event = decoder.get_event()
            print(f"Host: {decoder.host()}")
            print(f"Source: {decoder.source()}")
            print(f"Sourcetype: {decoder.source_type()}")
            print(f"Timestamp: {event.index_time}")
            print(f"Message: {event.message_string()}")
```

A pure-Python `JournalDecoder` is also available with the same interface, useful when the native extension cannot be built.

## Architecture

```
splunk_ddss_extractor/
├── src/splunk_ddss_extractor/    # Python package
│   ├── __init__.py
│   ├── decoder.py                # Pure-Python journal decoder
│   ├── native_decoder.py         # Rust-backed decoder (NativeJournalDecoder)
│   ├── extractor.py              # High-level extraction API
│   ├── main.py                   # CLI entry point
│   └── utils.py                  # Output writers, logging
├── rust/                         # Native extension (PyO3 + maturin)
│   ├── Cargo.toml
│   └── src/
│       ├── lib.rs                # PyO3 module
│       ├── decoder.rs            # Rust journal decoder
│       └── varint.rs             # Variable-length integer parsing
├── tests/
├── docker/
└── scripts/
```

**Components:**

1. **Native Decoder** (`rust/` + `native_decoder.py`) - Rust extension for high-throughput decoding via `scan_batch`, wrapped in Python for ergonomic use
2. **Python Decoder** (`decoder.py`) - Pure-Python fallback with identical interface
3. **Extractor** (`extractor.py`) - High-level API with auto-compression, S3 streaming, multi-format output
4. **CLI** (`main.py`) - Command-line interface via `splunk-extract`

## Output Formats

| Format | Extension | Use Case |
|--------|-----------|----------|
| JSON Lines | `.json` / `.jsonl` | Streaming, log aggregation |
| CSV | `.csv` | Spreadsheets, simple analytics |
| Parquet | `.parquet` | Columnar analytics, data lakes |

Example JSON Lines output:
```json
{"timestamp": 1761643257, "host": "server01", "source": "s3://logs/app.log", "sourcetype": "aws:cloudtrail", "message": "{\"eventVersion\":\"1.08\",...}"}
```

## Integration Examples

**AWS Lambda (streaming S3-to-S3):**

```python
from splunk_ddss_extractor.extractor import Extractor

def lambda_handler(event, context):
    extractor = Extractor()
    count = extractor.extract(
        input_path="s3://input-bucket/journal.zst",
        output_path="s3://output-bucket/output.json",
        output_format="ndjson",
    )
    return {"statusCode": 200, "events_extracted": count}
```

**Docker:**

```bash
make docker
docker run -v /path/to/data:/data splunk-ddss-extractor:latest \
    splunk-extract -i /data/journal.zst -o /data/output.json
```

## Development

### Setup

```bash
# Full setup (venv + deps + Rust extension)
make dev-setup

# Or step by step:
make venv
source venv/bin/activate
make install
make rust-build-release
```

### Commands

```bash
make test              # Run Python tests
make test-coverage     # Tests with coverage report
make rust-test         # Run Rust unit tests
make rust-build        # Build Rust extension (debug)
make rust-build-release # Build Rust extension (release)
make docker            # Build Docker image
make check             # Run all checks
make env               # Show all available commands
```

### Versioning and Releases

Version is tracked in three files kept in sync by the bump script:
- `pyproject.toml` (Python package version)
- `rust/Cargo.toml` (Rust crate version)
- `src/splunk_ddss_extractor/__init__.py` (runtime `__version__`)

```bash
make version           # Show current version
make bump-patch        # 0.3.0 -> 0.3.1
make bump-minor        # 0.3.0 -> 0.4.0
make bump-major        # 0.3.0 -> 1.0.0
make release           # Bump patch, commit, tag, and push
make release-minor     # Bump minor, commit, tag, and push
make release-major     # Bump major, commit, tag, and push
```

The `publish.yml` GitHub Actions workflow builds native wheels for Linux x86_64 and aarch64 (Python 3.10-3.13) and publishes to PyPI when a GitHub release is created.

## Performance

| Decoder | Throughput |
|---------|-----------|
| Pure Python (`JournalDecoder`) | ~29K events/s |
| Rust native (`NativeJournalDecoder`) | ~80K events/s |

The `Extractor` class uses the native decoder by default when available.

## Credits

Based on the concept from [fionera/splunker](https://github.com/fionera/splunker) (Go). This Python/Rust implementation adds streaming S3 support, multiple output formats, native performance, and a production-ready API.

## License

MIT
