"""Test suite for ``cheroot.errors``."""

import errno
import io
import math

import pytest

from cheroot import errors, makefile

from .._compat import (  # noqa: WPS130
    IS_LINUX,
    IS_MACOS,
    IS_SOLARIS,
    IS_WINDOWS,
)


@pytest.mark.parametrize(
    ('err_names', 'err_nums'),
    (
        (('', 'some-nonsense-name'), []),
        (
            (
                'EPROTOTYPE',
                'EAGAIN',
                'EWOULDBLOCK',
                'WSAEWOULDBLOCK',
                'EPIPE',
            ),
            (91, 11, 32)
            if IS_LINUX
            else (32, 35, 41)
            if IS_MACOS
            else (98, 11, 32)
            if IS_SOLARIS
            else (32, 10041, 11, 10035)
            if IS_WINDOWS
            else (),
        ),
    ),
)
def test_plat_specific_errors(err_names, err_nums):
    """Test that ``plat_specific_errors`` gets correct error numbers list."""
    actual_err_nums = errors.plat_specific_errors(*err_names)
    assert len(actual_err_nums) == len(err_nums)
    assert sorted(actual_err_nums) == sorted(err_nums)


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
    # Mock the _is_acceptable_socket_shutdown_error function if needed
    # for simplicity, we rely on the real errors module here.
    return writer


# Use the set directly from the source code
ACCEPTABLE_SHUTDOWN_ERRORS = tuple(
    (code, errno.errorcode.get(code, f'Unknown:{code}'))
    for code in errors.acceptable_sock_shutdown_error_codes
)


@pytest.mark.parametrize(('err_num', 'err_name'), ACCEPTABLE_SHUTDOWN_ERRORS)
def test_flush_unlocked_handles_shutdown_errors(
    mock_buffer_writer,
    mocker,
    err_num,
    err_name,
):
    """
    Test that the method catches and ignores specific socket shutdown errors.

    The errors are defined in acceptable_sock_shutdown_error_codes.
    """
    # 1. Setup the mock write method
    mock_write_method = mocker.Mock()

    # 2. Configure the mock to raise a generic OSError with the specific errno
    err = OSError(err_num, f'Mocked Socket Error: {err_name}')
    mock_write_method.side_effect = err

    # 3. Patch the actual 'write' method on the raw socket instance
    mocker.patch.object(mock_buffer_writer.raw, 'write', new=mock_write_method)
    initial_len = len(mock_buffer_writer._write_buf)

    # 4. Assert that the function does not raise any exception
    try:
        mock_buffer_writer._flush_unlocked()
    except Exception as exc:
        pytest.fail(
            f'Unexpected exception raised for {err_name}: {type(exc).__name__}',
        )

    # 5. Check the buffer was not flushed
    # The logic is 'return' on acceptable error, so the write was attempted,
    # but the deletion logic was skipped, and the buffer contents remain.
    assert len(mock_buffer_writer._write_buf) == initial_len

    # 6. Check the write attempt was made exactly once
    assert mock_write_method.call_count == 1


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
