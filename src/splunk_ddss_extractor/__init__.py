"""
Splunk DDSS Extractor - Extract events from Splunk journal archives to raw format
"""

__version__ = "0.1.0"
__author__ = "Lech Lachowicz"

from .decoder import Event, JournalDecoder

__all__ = [
    "JournalDecoder",
    "Event",
]
