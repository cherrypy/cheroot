"""Tests for :py:mod:`cheroot.makefile`."""

from cheroot import makefile


class MockSocket:
    """A mock socket."""

    def __init__(self, keep_buffer_exported=False):
        """Initialize :py:class:`MockSocket`."""
        self.messages = []
        self.keep_buffer_exported = keep_buffer_exported
        self.leaked_view = None

    def recv_into(self, buf):
        """Simulate ``recv_into`` for Python 3."""
        if not self.messages:
            return 0
        msg = self.messages.pop(0)
        for index, byte in enumerate(msg):
            buf[index] = byte
        if self.keep_buffer_exported:
            # Simulate ssl.SSLSocket.recv_into() leaking a memoryview over
            # ``buf`` past the call, as happens on PyPy (see GH-#XXX).
            self.leaked_view = memoryview(buf)
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


def test_socket_io_read_does_not_resize_buffer():
    """``_SocketIO.read()`` must not shrink its buffer in place.

    Regression test for a PyPy-only ``BufferError: Existing exports of
    data: object cannot be re-sized``, triggered when the default
    ``_pyio.RawIOBase.read()`` implementation (``del b[n:]``) resizes a
    buffer still referenced by an unreleased ``memoryview``, e.g. one
    created internally by ``ssl.SSLSocket.recv_into()``. On PyPy that
    memoryview stays alive until the next GC run instead of being
    released immediately, unlike CPython's deterministic refcounting.
    """
    sock = MockSocket(keep_buffer_exported=True)
    sock.messages.append(b'foo')
    raw = makefile._SocketIO(sock, 'r')
    assert raw.read(3) == b'foo'
    assert sock.leaked_view is not None
