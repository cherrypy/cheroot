"""Tests for :py:mod:`cheroot.makefile`."""

import errno

import pytest

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


class DeadSocket(MockSocket):
    """A mock socket whose file descriptor is already invalid.

    Simulates a connection that was torn down (e.g. an aborted TLS
    session) so that any attempt to send raises ``OSError``.
    """

    def __init__(self, exc=None):
        """Initialize :py:class:`DeadSocket` with the error to raise."""
        super().__init__()
        self._exc = exc or OSError(errno.EBADF, 'Bad file descriptor')

    def send(self, val):
        """Fail as if the underlying descriptor is gone."""
        raise self._exc


@pytest.mark.parametrize(
    'exc',
    (
        OSError(errno.EBADF, 'Bad file descriptor'),
        ValueError('I/O operation on closed file.'),
    ),
    ids=('oserror-ebadf', 'valueerror-closed'),
)
def test_flush_on_dead_socket_is_swallowed(exc):
    """Flushing to a dead socket must not raise.

    A buffered write flushed after the socket's descriptor became
    invalid should not propagate the error, otherwise it taints the
    worker thread teardown path and can wedge the server over time.

    Ref: https://github.com/cherrypy/cheroot/issues/710
    """
    sock = DeadSocket(exc)
    wfile = makefile.MakeFile(sock, 'w')
    # Fill the buffer without triggering an immediate flush.
    wfile._write_buf.extend(b'payload')
    # An explicit flush must not raise even though the socket is dead.
    wfile.flush()
    # The unsendable buffered bytes are dropped rather than retried forever.
    assert not wfile._write_buf


def test_close_on_dead_socket_is_swallowed():
    """Closing a writer with a dead socket must not raise.

    ``close`` performs an implicit flush; on a dead descriptor this is
    the exact path exercised by the finalizer ``IOBase.__del__``.
    """
    sock = DeadSocket()
    wfile = makefile.MakeFile(sock, 'w')
    wfile._write_buf.extend(b'payload')
    # Must not raise, mirroring finalizer-driven teardown.
    wfile.close()
