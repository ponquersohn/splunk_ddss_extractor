# Version Bumping Script

This directory contains scripts for managing the project version.

## bump_version.py

A comprehensive script to bump version numbers in both `setup.py` and `src/splunk_ddss_extractor/__init__.py`.

### Usage

#### Via Script (Recommended)

```bash
# Show current version
python3 scripts/bump_version.py --current

# Bump patch version (0.2.1 -> 0.2.2)
python3 scripts/bump_version.py patch

# Bump minor version (0.2.1 -> 0.3.0)
python3 scripts/bump_version.py minor

# Bump major version (0.2.1 -> 1.0.0)
python3 scripts/bump_version.py major
```

#### Via Makefile (Easy Access)

```bash
# Show current version and environment info
make version

# Bump versions
make bump-patch   # 0.2.1 -> 0.2.2
make bump-minor   # 0.2.1 -> 0.3.0
make bump-major   # 0.2.1 -> 1.0.0
```

### Features

- **Consistency Check**: Verifies versions match between both files before making changes
- **Atomic Updates**: Updates both files or fails completely (no partial updates)
- **Validation**: Ensures semantic versioning format (major.minor.patch)
- **Error Handling**: Clear error messages and proper exit codes
- **Dry Run Support**: `--current` flag shows version without making changes

### Files Updated

1. **setup.py**: `version="x.y.z"` on line ~8
2. **src/splunk_ddss_extractor/__init__.py**: `__version__ = "x.y.z"` on line ~5

### Example Output

```bash
$ python3 scripts/bump_version.py --current
Current version: 0.2.1
✓ Versions are consistent between setup.py and __init__.py

$ python3 scripts/bump_version.py patch
Bumping version: 0.2.1 -> 0.2.2
Updated /home/ponq/dev/splunk_archiver/setup.py
Updated /home/ponq/dev/splunk_archiver/src/splunk_ddss_extractor/__init__.py
✓ Version successfully bumped to 0.2.2
```

### Error Scenarios

The script handles several error scenarios:

- **Version Mismatch**: If versions differ between files, script stops and asks for manual fix
- **Invalid Version Format**: If current version doesn't follow semantic versioning
- **File Not Found**: If setup.py or __init__.py files are missing
- **Permission Errors**: If files cannot be written to

### Integration

This script is designed to work with:
- **Git workflows**: Run before committing version changes
- **CI/CD pipelines**: Automated version bumping in release workflows
- **Development workflow**: Easy version management during development