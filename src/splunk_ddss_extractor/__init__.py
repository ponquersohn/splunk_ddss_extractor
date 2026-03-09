"""
Splunk DDSS Extractor - Extract events from Splunk journal archives to raw format
"""

__version__ = "0.4.0"
__author__ = "Lech Lachowicz"

from .decoder import Event, JournalDecoder
from .native_decoder import NativeJournalDecoder, NativeAsyncJournalDecoder

__all__ = [
    "JournalDecoder",
    "NativeJournalDecoder",
    "NativeAsyncJournalDecoder",
    "Event",
]
