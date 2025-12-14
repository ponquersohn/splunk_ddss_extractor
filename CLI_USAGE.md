# Splunk DDSS Extractor CLI Usage

## Installation

```bash
# Install in development mode
pip install -e .

# Or install with optional dependencies
pip install -e ".[parquet]"  # Adds Parquet support
pip install -e ".[dev]"       # Adds development tools
```

## Usage

After installation, you can use the CLI in three ways:

### 1. Console Script (Recommended)
```bash
splunk-extract -i journal.zst -o output.json
```

### 2. Python Module
```bash
python -m splunk_ddss_extractor -i journal.zst -o output.json
```

### 3. Direct Script
```bash
python src/splunk_ddss_extractor/main.py -i journal.zst -o output.json
```

## Command Line Options

```
usage: splunk-extract [-h] [-i INPUT_FILE] [-o OUTPUT_FILE]
                      [-f {ndjson,csv,parquet}]
                      [-l {DEBUG,INFO,WARNING,ERROR,CRITICAL}] [-v] [-q]

Options:
  -h, --help                  Show help message
  -i, --input-file PATH       Input file (local path or s3://bucket/key)
  -o, --output-file PATH      Output file (local path or s3://bucket/key)
  -f, --format FORMAT         Output format: ndjson, csv, parquet (default: ndjson)
  -l, --log-level LEVEL       Logging level (default: INFO)
  -v, --verbose               Enable verbose output (DEBUG level)
  -q, --quiet                 Suppress info output (WARNING level)
```

## Examples

### Local Files
```bash
# Basic extraction
splunk-extract -i journal.zst -o output.json

# With output format specification
splunk-extract -i journal.zst -o output.csv -f csv
splunk-extract -i journal.zst -o output.parquet -f parquet

# Verbose output
splunk-extract -i journal.zst -o output.json -v

# Quiet mode (errors/warnings only)
splunk-extract -i journal.zst -o output.json -q
```

### S3 URIs (Streaming, No Downloads)
```bash
# S3 to local
splunk-extract -i s3://bucket/path/journal.zst -o output.json

# Local to S3
splunk-extract -i journal.zst -o s3://bucket/output/data.json

# S3 to S3 (fully streaming)
splunk-extract -i s3://bucket/path/journal.zst -o s3://bucket/output/data.json

# S3 to stdout
splunk-extract -i s3://bucket/path/journal.zst > output.json
```

### Stdin/Stdout
```bash
# Stdin to stdout
cat journal.zst | splunk-extract > output.json

# Stdin to file
cat journal.zst | splunk-extract -o output.json

# Stdin to S3
cat journal.zst | splunk-extract -o s3://bucket/output/data.json

# S3 to stdout (streaming)
splunk-extract -i s3://bucket/path/journal.zst > output.json
```

### Compression Support

**Input** (automatic detection):
- `.zst` - Zstandard compression
- `.gz` - Gzip compression
- No extension - Uncompressed

**Output** (automatic based on extension):
- `.gz` - Gzip compressed output
- No `.gz` - Uncompressed output

```bash
# Compressed input, uncompressed output
splunk-extract -i journal.zst -o output.json

# Compressed input, compressed output
splunk-extract -i journal.zst -o output.json.gz

# Uncompressed input
splunk-extract -i journal -o output.json
```

## Output Formats

### NDJSON (Newline-Delimited JSON)
Default format. One JSON object per line:
```json
{"timestamp": 1735997957, "host": "host::server1", "source": "source::app", "sourcetype": "sourcetype::logs", "message": "..."}
{"timestamp": 1735997958, "host": "host::server1", "source": "source::app", "sourcetype": "sourcetype::logs", "message": "..."}
```

### CSV
Comma-separated values with headers:
```csv
timestamp,host,source,sourcetype,message
1735997957,host::server1,source::app,sourcetype::logs,"..."
1735997958,host::server1,source::app,sourcetype::logs,"..."
```

### Parquet
Columnar format optimized for analytics (requires pyarrow):
```bash
pip install -e ".[parquet]"
splunk-extract -i journal.zst -o output.parquet -f parquet
```

## Python API

You can also use the Extractor class directly in your Python code:

```python
from splunk_ddss_extractor.extractor import Extractor

extractor = Extractor()
event_count = extractor.extract(
    input_path="journal.zst",
    output_path="output.json",
    output_format="ndjson"
)
print(f"Extracted {event_count} events")
```

## Testing

```bash
# Test with local file
splunk-extract -i test_data/journal.zst -o /tmp/test_output.json -v

# Test stdin/stdout
cat test_data/journal.zst | splunk-extract > /tmp/output.json

# Verify output
head -1 /tmp/test_output.json | jq .
```

## Troubleshooting

### ModuleNotFoundError
```bash
# Ensure package is installed
pip install -e .
```

### S3 Access Issues
```bash
# Configure AWS credentials
aws configure

# Or use environment variables
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
export AWS_DEFAULT_REGION=us-east-1
```

### Compression Errors
```bash
# Install zstandard if not present
pip install zstandard

# Install pyarrow for Parquet support
pip install pyarrow
```