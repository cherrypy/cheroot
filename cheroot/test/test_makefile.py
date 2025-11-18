"""Tests for :py:mod:`cheroot.makefile`."""

import io

from cheroot.makefile import StreamReader, StreamWriter


class MockSocket(io.RawIOBase):
    """A mock socket for testing stream I/O."""

    def __init__(self):
        """Initialize MockSocket."""
        super().__init__()
        self.messages = []

    def readable(self):
        """Return True - supports reading."""
        return True

    def writable(self):
        """Return True - supports writing."""
        return True

    def readinto(self, buf):
        """Read data into buffer."""
        if not self.messages:
            return 0  # EOF

        msg = self.messages.pop(0)
        num_bytes = min(len(msg), len(buf))
        buf[:num_bytes] = msg[:num_bytes]  # noqa: WPS362
        return num_bytes

    def write(self, data):
        """Write data (returns length written)."""
        return len(data)


def test_bytes_read():
    """Reader should capture bytes read."""
    sock = MockSocket()
    sock.messages.append(b'foo')
    rfile = StreamReader(sock)
    rfile.read()
    assert rfile.bytes_read == 3


def test_bytes_written():
    """Writer should capture bytes written."""
    sock = MockSocket()
    wfile = StreamWriter(sock)
    wfile.write(b'bar')
    assert wfile.bytes_written == 3
