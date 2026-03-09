#!/usr/bin/env python3
"""
Version bumping script for splunk-ddss-extractor.

Keeps pyproject.toml, Cargo.toml, and __init__.py in sync.

Usage:
    python scripts/bump_version.py patch      # 0.3.0 -> 0.3.1
    python scripts/bump_version.py minor      # 0.3.0 -> 0.4.0
    python scripts/bump_version.py major      # 0.3.0 -> 1.0.0
    python scripts/bump_version.py --set 1.0.0  # Set explicit version
    python scripts/bump_version.py --current  # Show current version
"""

import argparse
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

VERSION_FILES = {
    "pyproject.toml": {
        "path": PROJECT_ROOT / "pyproject.toml",
        "pattern": r'^(version\s*=\s*")([^"]+)(")',
        "flags": re.MULTILINE,
    },
    "Cargo.toml": {
        "path": PROJECT_ROOT / "rust" / "Cargo.toml",
        "pattern": r'^(version\s*=\s*")([^"]+)(")',
        "flags": re.MULTILINE,
    },
    "__init__.py": {
        "path": PROJECT_ROOT / "src" / "splunk_ddss_extractor" / "__init__.py",
        "pattern": r'^(__version__\s*=\s*")([^"]+)(")',
        "flags": re.MULTILINE,
    },
}


def read_version(name: str, spec: dict) -> str | None:
    """Read version from a file using its regex pattern."""
    try:
        content = spec["path"].read_text(encoding="utf-8")
        match = re.search(spec["pattern"], content, spec["flags"])
        return match.group(2) if match else None
    except FileNotFoundError:
        return None


def write_version(spec: dict, new_version: str) -> None:
    """Write version to a file using its regex pattern."""
    content = spec["path"].read_text(encoding="utf-8")
    updated = re.sub(
        spec["pattern"],
        rf"\g<1>{new_version}\3",
        content,
        flags=spec["flags"],
    )
    spec["path"].write_text(updated, encoding="utf-8")


def parse_version(version: str) -> tuple[int, int, int]:
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)$", version)
    if not match:
        raise ValueError(f"Invalid version format: {version}")
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def bump_version(current: str, bump_type: str) -> str:
    major, minor, patch = parse_version(current)
    if bump_type == "major":
        return f"{major + 1}.0.0"
    elif bump_type == "minor":
        return f"{major}.{minor + 1}.0"
    elif bump_type == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ValueError(f"Invalid bump type: {bump_type}")


def get_versions() -> dict[str, str | None]:
    return {name: read_version(name, spec) for name, spec in VERSION_FILES.items()}


def show_current():
    versions = get_versions()
    unique = set(v for v in versions.values() if v is not None)

    for name, ver in versions.items():
        status = "" if ver else " (not found)"
        print(f"  {name}: {ver or 'N/A'}{status}")

    if len(unique) == 1:
        print(f"\nCurrent version: {unique.pop()}")
        print("All files in sync.")
    elif len(unique) == 0:
        print("\nNo version found in any file.")
        sys.exit(1)
    else:
        print("\nVersion MISMATCH detected!")
        sys.exit(1)


def set_all_versions(new_version: str):
    # Validate format
    parse_version(new_version)

    for name, spec in VERSION_FILES.items():
        if spec["path"].exists():
            old = read_version(name, spec)
            write_version(spec, new_version)
            print(f"  {name}: {old} -> {new_version}")
        else:
            print(f"  {name}: skipped (file not found)")


def main():
    parser = argparse.ArgumentParser(
        description="Bump version across pyproject.toml, Cargo.toml, and __init__.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s patch        # 0.3.0 -> 0.3.1
  %(prog)s minor        # 0.3.0 -> 0.4.0
  %(prog)s major        # 0.3.0 -> 1.0.0
  %(prog)s --set 1.0.0  # Set explicit version
  %(prog)s --current    # Show current version
        """,
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "bump_type",
        nargs="?",
        choices=["major", "minor", "patch"],
        help="Type of version bump",
    )
    group.add_argument("--current", action="store_true", help="Show current version")
    group.add_argument("--set", metavar="VERSION", help="Set an explicit version")

    args = parser.parse_args()

    if args.current:
        show_current()
        return

    if args.set:
        new_version = args.set
        print(f"Setting version to {new_version}:")
        set_all_versions(new_version)
        print(f"\nVersion set to {new_version}")
        return

    # Bump: read current from pyproject.toml as source of truth
    current = read_version("pyproject.toml", VERSION_FILES["pyproject.toml"])
    if not current:
        print("Error: Could not read version from pyproject.toml")
        sys.exit(1)

    new_version = bump_version(current, args.bump_type)
    print(f"Bumping version: {current} -> {new_version}")
    set_all_versions(new_version)
    print(f"\nVersion bumped to {new_version}")


if __name__ == "__main__":
    main()
