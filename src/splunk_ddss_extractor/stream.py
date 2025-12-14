from typing import Tuple
import logging

logger = logging.getLogger(__name__)


class JournalStream:
    def __init__(self, reader, chunk_size=64 * 1024):
        self.reader = reader
        self.chunk_size = chunk_size
        self.buffer = bytearray()
        self._eof = False
        self.pos = 0  # absolute stream position

    # -------------------------
    # Internal
    # -------------------------

    def _fill(self, n: int):
        """Ensure at least n bytes in buffer."""
        while len(self.buffer) < n and not self._eof:
            chunk = self.reader.read(max(self.chunk_size, n - len(self.buffer)))
            if not chunk:
                self._eof = True
                break
            self.buffer.extend(chunk)

        if len(self.buffer) < n:
            raise EOFError("End of stream")

    # -------------------------
    # Public API
    # -------------------------

    def tell(self) -> int:
        """Return absolute position in the stream."""
        return self.pos

    def read(self, n: int) -> bytes:
        if n <= 0:
            return b""

        self._fill(n)
        data = bytes(self.buffer[:n])
        del self.buffer[:n]
        self.pos += n
        return data

    def read_byte(self) -> int:
        self._fill(1)
        b = self.buffer[0]
        del self.buffer[0]
        self.pos += 1
        return b

    def peek(self, n: int) -> bytes:
        if n <= 0:
            return b""

        try:
            self._fill(n)
        except EOFError:
            logger.warning("Reached end of stream while peeking")
        return bytes(self.buffer[:n])

    def skip(self, n: int) -> int:
        """Read-and-drop n bytes (old discard semantics)."""
        self._fill(n)
        del self.buffer[:n]
        self.pos += n
        return n

    def discard(self, n: int = None):
        """
        Discard first n bytes of the buffer to free memory.
        Does not affect stream position (pos).
        """
        if n is None or n > len(self.buffer):
            n = len(self.buffer)
        if n > 0:
            del self.buffer[:n]

    def read_uvarint(self) -> int:
        """Read unsigned varint"""
        result = 0
        shift = 0
        while True:
            b = self.read_byte()
            result |= (b & 0x7F) << shift
            if (b & 0x80) == 0:
                break
            shift += 7
        return result

    def read_varint(self) -> int:
        """Read signed varint (zigzag encoded)"""
        u = self.read_uvarint(self)
        # Zigzag decode
        return (u >> 1) ^ -(u & 1)
