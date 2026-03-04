#!/usr/bin/env python3
"""
Version bumping script for splunk-ddss-extractor

Usage:
    python scripts/bump_version.py patch   # 0.2.1 -> 0.2.2
    python scripts/bump_version.py minor   # 0.2.1 -> 0.3.0
    python scripts/bump_version.py major   # 0.2.1 -> 1.0.0
    python scripts/bump_version.py --current  # Show current version
"""

import argparse
import re
import sys
from pathlib import Path


class VersionBumper:
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.setup_py_path = project_root / "setup.py"
        self.init_py_path = project_root / "src" / "splunk_ddss_extractor" / "__init__.py"

    def get_current_version(self) -> str:
        """Get current version from setup.py"""
        content = self.setup_py_path.read_text(encoding="utf-8")
        match = re.search(r'version="([^"]+)"', content)
        if not match:
            raise ValueError("Could not find version in setup.py")
        return match.group(1)

    def parse_version(self, version: str) -> tuple[int, int, int]:
        """Parse semantic version string into major, minor, patch"""
        match = re.match(r"^(\d+)\.(\d+)\.(\d+)$", version)
        if not match:
            raise ValueError(f"Invalid version format: {version}")
        return int(match.group(1)), int(match.group(2)), int(match.group(3))

    def bump_version(self, current_version: str, bump_type: str) -> str:
        """Bump version based on type (major, minor, patch)"""
        major, minor, patch = self.parse_version(current_version)

        if bump_type == "major":
            return f"{major + 1}.0.0"
        elif bump_type == "minor":
            return f"{major}.{minor + 1}.0"
        elif bump_type == "patch":
            return f"{major}.{minor}.{patch + 1}"
        else:
            raise ValueError(f"Invalid bump type: {bump_type}")

    def update_setup_py(self, new_version: str) -> None:
        """Update version in setup.py"""
        content = self.setup_py_path.read_text(encoding="utf-8")
        updated_content = re.sub(
            r'version="[^"]+"',
            f'version="{new_version}"',
            content
        )
        self.setup_py_path.write_text(updated_content, encoding="utf-8")
        print(f"Updated {self.setup_py_path}")

    def update_init_py(self, new_version: str) -> None:
        """Update version in __init__.py"""
        content = self.init_py_path.read_text(encoding="utf-8")
        updated_content = re.sub(
            r'__version__ = "[^"]+"',
            f'__version__ = "{new_version}"',
            content
        )
        self.init_py_path.write_text(updated_content, encoding="utf-8")
        print(f"Updated {self.init_py_path}")

    def verify_versions_match(self) -> bool:
        """Verify that versions in both files match"""
        setup_version = self.get_current_version()

        init_content = self.init_py_path.read_text(encoding="utf-8")
        init_match = re.search(r'__version__ = "([^"]+)"', init_content)
        if not init_match:
            return False

        init_version = init_match.group(1)
        return setup_version == init_version

    def show_current_version(self) -> None:
        """Show current version and verify consistency"""
        try:
            current_version = self.get_current_version()
            print(f"Current version: {current_version}")

            if self.verify_versions_match():
                print("✓ Versions are consistent between setup.py and __init__.py")
            else:
                print("✗ Version mismatch between setup.py and __init__.py")
                sys.exit(1)

        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)

    def bump(self, bump_type: str) -> None:
        """Bump version in both files"""
        try:
            # Verify current state
            if not self.verify_versions_match():
                print("Error: Version mismatch between files. Please fix manually first.")
                sys.exit(1)

            current_version = self.get_current_version()
            new_version = self.bump_version(current_version, bump_type)

            print(f"Bumping version: {current_version} -> {new_version}")

            # Update both files
            self.update_setup_py(new_version)
            self.update_init_py(new_version)

            print(f"✓ Version successfully bumped to {new_version}")

        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Bump version in setup.py and __init__.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s patch     # 0.2.1 -> 0.2.2
  %(prog)s minor     # 0.2.1 -> 0.3.0
  %(prog)s major     # 0.2.1 -> 1.0.0
  %(prog)s --current # Show current version
        """
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "bump_type",
        nargs="?",
        choices=["major", "minor", "patch"],
        help="Type of version bump"
    )
    group.add_argument(
        "--current",
        action="store_true",
        help="Show current version"
    )

    args = parser.parse_args()

    # Find project root (look for setup.py)
    project_root = Path(__file__).parent.parent
    if not (project_root / "setup.py").exists():
        print("Error: Could not find setup.py in project root")
        sys.exit(1)

    bumper = VersionBumper(project_root)

    if args.current:
        bumper.show_current_version()
    else:
        bumper.bump(args.bump_type)


if __name__ == "__main__":
    main()