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
    """Mock raw.write() returning None once, then writing normally."""

    def __init__(self):
        """Initialize _RawWriteBlockOnce."""
        self.call_count = 0
        self.written = bytearray()

    def __call__(self, chunk):
        """Return None on first call to simulate a blocked write."""
        self.call_count += 1
        if self.call_count == 1:
            return None
        self.written.extend(chunk)
        return len(chunk)

    def fileno(self):
        """Return a fake fd for select()."""
        return -1


class _RawWriteBlockAlways:
    """Mock raw.write() that always returns None."""

    def __init__(self):
        """Initialize _RawWriteBlockAlways."""
        self.call_count = 0

    def __call__(self, chunk):
        """Return None to simulate a permanently blocked socket."""
        self.call_count += 1

    def fileno(self):
        """Return a fake fd for select()."""
        return -1


def test_flush_recovers_from_temporary_block(monkeypatch):
    """_flush_unlocked() retries after select when raw.write() returns None.

    A temporarily blocked socket should recover once select() reports
    the socket is writable again, delivering all buffered data.
    """
    data = b'x' * (makefile.SOCK_WRITE_BLOCKSIZE * 2)

    sock = MockSocket()
    wfile = makefile.MakeFile(sock, 'w')
    wfile._write_buf.extend(data)

    mock = _RawWriteBlockOnce()
    wfile.raw.write = mock

    # select() reports writable immediately
    monkeypatch.setattr(
        'cheroot.makefile.select.select',
        lambda _rlist, wlist, _xlist, _timeout: ([], wlist, []),
    )
    wfile._flush_unlocked()

    assert bytes(mock.written) == data, (
        'all buffered data should be written after select retry'
    )


def test_flush_raises_on_sustained_block(monkeypatch):
    """_flush_unlocked() raises BlockingIOError after select timeout.

    If the socket stays blocked past SOCK_WRITE_TIMEOUT, the write
    buffer must be preserved and BlockingIOError raised.
    """
    import io

    import pytest

    data = b'x' * makefile.SOCK_WRITE_BLOCKSIZE

    sock = MockSocket()
    wfile = makefile.MakeFile(sock, 'w')
    wfile._write_buf.extend(data)

    mock = _RawWriteBlockAlways()
    wfile.raw.write = mock

    # select() reports not writable (timeout)
    monkeypatch.setattr(
        'cheroot.makefile.select.select',
        lambda _rlist, _wlist, _xlist, _timeout: ([], [], []),
    )

    with pytest.raises(io.BlockingIOError):
        wfile._flush_unlocked()

    assert len(wfile._write_buf) == len(data), (
        'write buffer must be preserved when socket stays blocked'
    )
