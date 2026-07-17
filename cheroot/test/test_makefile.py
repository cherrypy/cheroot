"""Tests for :py:mod:`cheroot.makefile`."""

import _pyio
import errno
import io

import pytest

from cheroot import makefile


class MockSocket:
    """A mock socket for emulating buffered I/O."""

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


class MockRawIO:
    """A mock ``io.RawIOBase`` object for use as the raw layer of a ``BufferedWriter``."""

    def __init__(self):
        """Initialize :py:class:`MockRawIO`."""
        self._is_closed = False

    def write(self, message):
        """Emulate ``io.RawIOBase write``."""
        return len(message)

    def writable(self):
        """Indicate that the raw stream supports writing."""
        return True

    def close(self):
        """Emulate close."""
        self._is_closed = True

    @property
    def closed(self):
        """Emulate the required ``closed`` property."""
        return self._is_closed


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
    """Test that double ``close()`` does not error out."""
    raw_buffer = io.BytesIO()
    buffered_writer = makefile.BufferedWriter(raw_buffer)

    buffered_writer.close()
    assert buffered_writer.closed

    buffered_writer.close()
    assert buffered_writer.closed


def test_close_when_raw_already_closed():
    """Test that ``close()`` is safe when the raw buffer was closed externally.

    Simulates a race where the OS or another thread closed the raw socket
    before ``BufferedWriter.close()`` is called.
    """
    raw_buffer = io.BytesIO()
    buffered_writer = makefile.BufferedWriter(raw_buffer)

    raw_buffer.close()
    assert buffered_writer.closed  # property reflects raw state

    buffered_writer.close()


@pytest.mark.parametrize(
    ('exc', 'reraises'),
    (
        (BrokenPipeError(errno.EPIPE, 'Broken pipe'), False),
        (OSError(errno.EBADF, 'Bad file descriptor'), False),
        (OSError(errno.EIO, 'I/O error'), True),
    ),
    ids=['broken_pipe', 'ebadf', 'unexpected_oserror'],
)
def test_close_error_handling(exc, reraises, mocker):
    """Test that expected socket errors are swallowed and others re-raised."""
    writer = makefile.BufferedWriter(MockRawIO())
    mocker.patch.object(_pyio.BufferedWriter, 'close', side_effect=exc)
    if reraises:
        with pytest.raises(OSError, match='I/O error'):
            writer.close()
    else:
        writer.close()


def _make_blocking_io_error():
    """Create a :exc:`BlockingIOError` with ``characters_written`` set."""
    err = io.BlockingIOError(errno.EAGAIN, 'Resource temporarily unavailable')
    err.characters_written = 5
    return err


@pytest.mark.parametrize(
    ('write_kwargs', 'expected_buf_len'),
    (
        ({'return_value': 0}, len(b'data to flush')),
        ({'return_value': None}, len(b'data to flush')),
        ({'side_effect': _make_blocking_io_error()}, 0),
    ),
    ids=['zero_return', 'none_return', 'blocking_io_error'],
)
def test_flush_unlocked_write_outcomes(write_kwargs, expected_buf_len, mocker):
    """Test that ``_flush_unlocked`` handles various ``write()`` outcomes."""
    data = b'data to flush'
    writer = makefile.BufferedWriter(MockRawIO())
    writer._write_buf = bytearray(data)
    mocker.patch.object(writer.raw, 'write', **write_kwargs)

    writer._flush_unlocked()

    assert len(writer._write_buf) == expected_buf_len
