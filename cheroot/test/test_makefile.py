"""Tests for :py:mod:`cheroot.makefile`."""

import errno

from cheroot import makefile


class MockSocket:
    """A mock socket."""

    def __init__(self):
        """Initialize :py:class:`MockSocket`."""
        self.messages = []
        self.would_block = False

    def recv_into(self, buf):
        """Simulate ``recv_into`` for Python 3."""
        if self.would_block:
            raise BlockingIOError(errno.EWOULDBLOCK, 'would block')
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


def test_read_on_nonblocking_socket_with_no_data():
    """Reader should return ``None``, not crash, if nothing is available yet.

    A non-blocking socket's ``read()`` can return ``None`` per the
    documented ``io.RawIOBase`` contract when no data is available; this
    used to blow up on ``len(None)``. Ref: cherrypy/cheroot#278
    """
    sock = MockSocket()
    sock.would_block = True
    rfile = makefile.MakeFile(sock, 'r')
    assert rfile.read(256) is None
    assert rfile.bytes_read == 0


def test_bytes_written():
    """Writer should capture bytes written."""
    sock = MockSocket()
    sock.messages.append(b'foo')
    wfile = makefile.MakeFile(sock, 'w')
    wfile.write(b'bar')
    assert wfile.bytes_written == 3
