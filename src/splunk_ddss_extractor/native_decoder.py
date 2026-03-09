"""
Native (Rust) journal decoders — sync and async wrappers around scan_batch.
"""

from ._native import ScanState, scan_batch

_READ_CHUNK = 262_144  # 256 KB


class NativeJournalDecoder:
    """Sync decoder using Rust batch processing."""

    def __init__(self, reader, trace=False):
        self._reader = reader
        self._state = ScanState()
        self._events = []
        self._idx = 0
        self._done = False
        self.trace = trace

        # Compat: error tracking attributes
        self.error = None
        self.metadata_error_counts = {}
        self.total_metadata_errors = 0
        self.events_with_errors = 0

    def scan(self) -> bool:
        """Scan for next event. Returns True if event ready."""
        # Drain buffered events first
        if self._idx < len(self._events):
            self._current = self._events[self._idx]
            self._idx += 1
            return True

        # Read next chunks until we get events or EOF
        while not self._done:
            chunk = self._reader.read(_READ_CHUNK)
            if not chunk:
                # Flush any leftover in state
                result = scan_batch(self._state, b"")
                self._events = result["events"]
                self._idx = 0
                self._done = True
                if result.get("error"):
                    self.error = ValueError(result["error"])
                self._sync_error_counts()
                if self._events:
                    self._current = self._events[0]
                    self._idx = 1
                    return True
                return False

            result = scan_batch(self._state, chunk)
            self._events = result["events"]
            self._idx = 0

            if result.get("error"):
                self.error = ValueError(result["error"])
                self._sync_error_counts()
                # Still return any events decoded before the error
                if self._events:
                    self._current = self._events[0]
                    self._idx = 1
                    return True
                return False

            if self._events:
                self._current = self._events[0]
                self._idx = 1
                return True

        return False

    def get_event(self):
        """Get current event as dict matching to_normalized_dict() format."""
        return self._current

    def err(self):
        return self.error

    def _sync_error_counts(self):
        """Sync error counts from Rust state."""
        self.total_metadata_errors = self._state.total_metadata_errors
        self.events_with_errors = self._state.events_with_errors

    def get_error_summary(self):
        self._sync_error_counts()
        if self.total_metadata_errors == 0:
            return None
        return {
            "total_errors": self.total_metadata_errors,
            "events_with_errors": self.events_with_errors,
        }

    def log_error_summary(self):
        import logging
        logger = logging.getLogger(__name__)
        summary = self.get_error_summary()
        if summary:
            logger.warning(
                f"Metadata extraction summary: {summary['total_errors']} errors "
                f"across {summary['events_with_errors']} events."
            )
        else:
            logger.debug("No metadata errors encountered")


class NativeAsyncJournalDecoder:
    """Async decoder using Rust batch processing."""

    def __init__(self, reader, trace=False):
        self._reader = reader
        self._state = ScanState()
        self._events = []
        self._idx = 0
        self._done = False
        self.trace = trace

        self.error = None
        self.metadata_error_counts = {}
        self.total_metadata_errors = 0
        self.events_with_errors = 0

    async def scan(self) -> bool:
        """Scan for next event. Returns True if event ready."""
        if self._idx < len(self._events):
            self._current = self._events[self._idx]
            self._idx += 1
            return True

        while not self._done:
            chunk = await self._reader.read(_READ_CHUNK)
            if not chunk:
                result = scan_batch(self._state, b"")
                self._events = result["events"]
                self._idx = 0
                self._done = True
                if result.get("error"):
                    self.error = ValueError(result["error"])
                self._sync_error_counts()
                if self._events:
                    self._current = self._events[0]
                    self._idx = 1
                    return True
                return False

            result = scan_batch(self._state, chunk)
            self._events = result["events"]
            self._idx = 0

            if result.get("error"):
                self.error = ValueError(result["error"])
                self._sync_error_counts()
                if self._events:
                    self._current = self._events[0]
                    self._idx = 1
                    return True
                return False

            if self._events:
                self._current = self._events[0]
                self._idx = 1
                return True

        return False

    def get_event(self):
        return self._current

    def err(self):
        return self.error

    def _sync_error_counts(self):
        self.total_metadata_errors = self._state.total_metadata_errors
        self.events_with_errors = self._state.events_with_errors

    def get_error_summary(self):
        self._sync_error_counts()
        if self.total_metadata_errors == 0:
            return None
        return {
            "total_errors": self.total_metadata_errors,
            "events_with_errors": self.events_with_errors,
        }

    def log_error_summary(self):
        import logging
        logger = logging.getLogger(__name__)
        summary = self.get_error_summary()
        if summary:
            logger.warning(
                f"Metadata extraction summary: {summary['total_errors']} errors "
                f"across {summary['events_with_errors']} events."
            )
        else:
            logger.debug("No metadata errors encountered")
