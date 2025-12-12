"""
Splunk DDSS Extractor - Extract events from Splunk journal archives to raw format
"""

__version__ = "0.1.0"
__author__ = "Lech Lachowicz"

from .decoder import JournalDecoder, Event
from .extractor import extract_journal, extract_to_file

__all__ = [
    "JournalDecoder",
    "Event",
    "extract_journal",
    "extract_to_file",
]
