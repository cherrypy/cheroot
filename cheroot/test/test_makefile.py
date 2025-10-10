"""Tests for :py:mod:`cheroot.makefile`."""

import io

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


def test_close_is_idempotent():
    """Test that close() can be called multiple times safely."""
    raw_buffer = io.BytesIO()
    buffered_writer = makefile.BufferedWriter(raw_buffer)

    # Should not raise any exceptions
    buffered_writer.close()
    buffered_writer.close()  # Second call should be safe

    assert buffered_writer.closed


def test_close_handles_already_closed_buffer():
    """Test that close() handles already closed underlying buffer."""
    raw_buffer = io.BytesIO()
    buffered_writer = makefile.BufferedWriter(raw_buffer)

    # Close the underlying buffer first
    raw_buffer.close()

    # This should not raise an exception
    buffered_writer.close()
