import io
from typing import BinaryIO


class LimitedReader:
    """
    LimitedReader wraps a part of a reader into a reader.
    """

    _reader: BinaryIO
    _offset: int
    _size: int
    _remaining: int

    def __init__(self, reader: BinaryIO, offset: int, size: int):
        self._reader = reader
        self._offset = offset
        self._size = size
        self._remaining = size

    def read(self, n=-1):
        if n == -1 or n > self._remaining:
            n = self._remaining
        if n == 0:
            return b""
        chunk = self._reader.read(n)
        self._remaining -= len(chunk)
        return chunk

    def seek(self, offset, whence=io.SEEK_SET):
        end_offset = self._offset + self._size
        if whence == io.SEEK_SET:
            offset = self._offset + offset
        elif whence == io.SEEK_CUR:
            offset = self._reader.tell() + offset
        elif whence == io.SEEK_END:
            offset = end_offset + offset
        else:
            raise ValueError("invalid whence value")
        if not (self._offset <= offset < end_offset):
            raise ValueError("seek position is out of bounds")
        self._remaining = end_offset - offset
        return self._reader.seek(offset, whence)
