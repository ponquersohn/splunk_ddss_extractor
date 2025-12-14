from typing import Any

import zstandard as zstd


class Compressor:
    def __init__(self, stream: Any):
        self.stream = stream

    def write(self, data: bytes):
        raise NotImplementedError()


class ZstdCompressor(Compressor):
    def __init__(self, stream: Any):
        super().__init__(stream=stream)
        self.compressor = zstd.ZstdCompressor()

    def write(self, data: bytes):
        return self.compressor.compress(data)

    def close(self):
        return self.compressor.flush()
