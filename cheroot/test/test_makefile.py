"""Tests for :py:mod:`cheroot.makefile`."""

from cheroot import makefile


class MockSocket:
    """A mock socket."""

    def __init__(self):
        """Initialize :py:class:`MockSocket`."""
        self.messages = []

    def recv_into(self, buf):
        """Simulate ``recv_into`` for Python 3."""
        if not self.messages:
            return 0
        msg = self.messages.pop(0)
        for index, byte in enumerate(msg):
            buf[index] = byte
        return len(msg)

    def recv(self, size):
        """Simulate ``recv`` for Python 2."""
        try:
            return self.messages.pop(0)
        except IndexError:
            return ''

    def send(self, val):
        """Simulate a send."""
        return len(val)

    def _decref_socketios(self):
        """Emulate socket I/O reference decrement."""
        # Ref: https://github.com/cherrypy/cheroot/issues/734


def test_bytes_read():
    """Reader should capture bytes read."""
    sock = MockSocket()
    sock.messages.append(b'foo')
    rfile = makefile.MakeFile(sock, 'r')
    rfile.read()
    assert rfile.bytes_read == 3


def test_bytes_written():
    """Writer should capture bytes written."""
    sock = MockSocket()
    sock.messages.append(b'foo')
    wfile = makefile.MakeFile(sock, 'w')
    wfile.write(b'bar')
    assert wfile.bytes_written == 3


class _RawWriteBlockOnce:
    """Mock raw.write() that returns None on the first call, then writes normally."""

    def __init__(self):
        """Initialize _RawWriteBlockOnce."""
        self.call_count = 0
        self.written = bytearray()

    def __call__(self, chunk):
        """Return None on first call to simulate a blocked socket write."""
        self.call_count += 1
        if self.call_count == 1:
            return (
                None  # simulates socket returning None on first blocked write
            )
        self.written.extend(chunk)
        return len(chunk)


def test_flush_when_raw_write_returns_none():
    """_flush_unlocked() must not treat None from raw.write() as a byte count.

    io.RawIOBase.write() returns None when a non-blocking socket cannot accept
    data. del self._write_buf[:None] is equivalent to del self._write_buf[:]
    which silently clears the entire buffer, truncating the response without
    raising an exception.
    """
    data = b'x' * (makefile.SOCK_WRITE_BLOCKSIZE * 2)  # stress the write loop

    sock = MockSocket()
    wfile = makefile.MakeFile(sock, 'w')
    wfile._write_buf.extend(data)

    mock = _RawWriteBlockOnce()
    wfile.raw.write = mock
    wfile._flush_unlocked()

    assert bytes(mock.written) == data, (
        f'Expected {len(data)} bytes but only {len(mock.written)} reached raw.write(): '
        'buffer was silently discarded when raw.write() returned None'
    )
