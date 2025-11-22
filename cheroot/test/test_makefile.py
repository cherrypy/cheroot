"""Tests for :py:mod:`cheroot.makefile`."""

import errno
import io
import math

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

    # Should not raise any exceptions
    buffered_writer.close()
    assert buffered_writer.closed

    buffered_writer.close()  # Second call should be safe
    assert buffered_writer.closed


def test_close_handles_already_closed_buffer():
    """Test that ``close()`` handles already closed underlying buffer."""
    raw_buffer = io.BytesIO()
    buffered_writer = makefile.BufferedWriter(raw_buffer)

    # Close the underlying buffer first
    raw_buffer.close()

    # This should not raise an exception
    assert raw_buffer.closed
    assert buffered_writer.closed


def test_flush_unlocked_handles_blocking_io_error(mock_buffer_writer, mocker):
    """
    Test that a BlockingIOError is handled correctly.

    We extracting characters_written,
    and execution continues without raising the error.
    """
    # 1. Create a mock object to replace the real 'write' method
    mock_write_method = mocker.Mock()

    # 2. Set the side effect on the mock object
    err = io.BlockingIOError(errno.EAGAIN, 'Resource temporarily unavailable')
    err.characters_written = 5
    mock_write_method.side_effect = err

    # 3. Use mocker.patch.object to replace the 'write' method
    # with mock_write_method
    mocker.patch.object(mock_buffer_writer.raw, 'write', new=mock_write_method)

    # Check the initial state of the buffer
    initial_len = len(mock_buffer_writer._write_buf)

    # 4. Execute the code
    try:
        mock_buffer_writer._flush_unlocked()
    except Exception as exc:
        pytest.fail(f'Unexpected exception raised: {type(exc).__name__}')

    # 5. Verify the side-effect (buffer should be empty)
    assert len(mock_buffer_writer._write_buf) == 0

    # 6 Check mock calls (Logic/Mechanism)
    # The number of calls should be
    # initial_len / bytes_written_per_call
    expected_calls = math.ceil(initial_len / 5)
    assert mock_write_method.call_count == expected_calls


class MockRawSocket:
    """
    A mock raw socket for emulating low level unbuffered I/O.

    We use this mock with ``io.BufferedWriter``, which accesses it via
    the ``.raw`` attribute.
    """

    def __init__(self, *args, **kwargs):
        """Initialize :py:class:`MockRawSocket`."""
        # 1. Call the parent's init to set up self.messages
        super().__init__(*args, **kwargs)

        # 2. Rquired by the io.BufferedWriter base class
        self._is_closed = False

    def write(self, message):
        """Emulate ``io.RawIOBase write``."""
        # Use the underlying send method implemented in MockSocket
        return self.send(message)

    def writable(self):
        """Indicate that the raw stream supports writing."""
        return True

    def send(self, message):
        """Emulate a send."""
        return len(message)

    def close(self):
        """Emulate close."""
        self._is_closed = True

    @property
    def closed(self):
        """Emulate the required ``closed`` property."""
        return self._is_closed


@pytest.fixture
def mock_buffer_writer():
    """Fixture to create a BufferedWriter instance with a mock raw socket."""
    # Create a BufferedWriter instance with a buffer that has content
    # to ensure _flush_unlocked attempts to write.
    writer = makefile.BufferedWriter(MockRawSocket())
    writer._write_buf = bytearray(b'data to flush')
    return writer
