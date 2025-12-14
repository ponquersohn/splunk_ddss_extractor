"""
Entry point for running splunk_ddss_extractor as a module

Usage:
    python -m splunk_ddss_extractor [options]
"""

import sys

from .main import main

if __name__ == "__main__":
    sys.exit(main())
