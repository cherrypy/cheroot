"""Tests for `_TLSSocket`."""

import errno
import socket

import pytest

from OpenSSL import SSL

from cheroot import errors
from cheroot.ssl.pyopenssl import _TLSSocket


@pytest.fixture
def acceptable_codes():
    """Mock acceptable error codes."""
    return {errno.ECONNRESET, errno.EPIPE, errno.ENOTCONN}


@pytest.fixture
def mock_tls_socket(mocker, acceptable_codes):
    """Create a ``_TLSSocket`` with mocked dependencies."""
    # Mock the acceptable_sock_shutdown_error_codes
    mocker.patch.object(
        errors,
        'acceptable_sock_shutdown_error_codes',
        acceptable_codes,
    )

    socket = _TLSSocket.__new__(_TLSSocket)
    socket._ssl_conn = mocker.create_autospec(SSL.Connection, instance=True)
    socket._sock = mocker.Mock()
    return socket


# ===== SUCCESSFUL SHUTDOWN TESTS =====


def test_close_while_in_init():
    """Test that 'close while in init' errors are handled gracefully."""
    # Create a connection that will error on shutdown
    context = SSL.Context(SSL.TLSv1_2_METHOD)

    # Create an unconnected SSL connection
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    ssl_conn = SSL.Connection(context, sock)

    ssl_adapter = _TLSSocket(sock, ssl_conn)

    # close() should NOT raise an exception for 'uninitialized'
    # or 'shutdown while in init'
    ssl_adapter.close()


def test_close_clean_shutdown(mock_tls_socket):
    """Test successful close with no errors."""
    mock_tls_socket._ssl_conn.shutdown.return_value = None
    mock_tls_socket._sock.close.return_value = None

    # Should not raise any exceptions
    mock_tls_socket.close()

    mock_tls_socket._ssl_conn.shutdown.assert_called_once()
    mock_tls_socket._sock.close.assert_called_once()


def test_close_with_zero_return_error(mock_tls_socket):
    """Test close handles ``SSL.ZeroReturnError`` (clean shutdown)."""
    mock_tls_socket._ssl_conn.shutdown.side_effect = SSL.ZeroReturnError()
    mock_tls_socket._sock.close.return_value = None

    # Should not raise - ZeroReturnError is acceptable
    mock_tls_socket.close()

    mock_tls_socket._sock.close.assert_called_once()


# ===== ACCEPTABLE SSL SHUTDOWN ERRORS =====


@pytest.mark.parametrize(
    'error_reason',
    (
        'shutdown while in init',
        'uninitialized',
    ),
)
def test_close_with_acceptable_ssl_errors(mock_tls_socket, error_reason):
    """Test close handles acceptable SSL shutdown errors."""
    error = SSL.Error()
    error.args = [[('SSL routines', '', error_reason)]]
    mock_tls_socket._ssl_conn.shutdown.side_effect = error
    mock_tls_socket._sock.close.return_value = None

    # Should not raise - acceptable error
    mock_tls_socket.close()

    mock_tls_socket._sock.close.assert_called_once()


def test_close_with_reason_code_attribute(mock_tls_socket):
    """Test SSL error with _reason_code attribute."""
    error = SSL.Error()
    error._reason_code = 'shutdown while in init'
    mock_tls_socket._ssl_conn.shutdown.side_effect = error
    mock_tls_socket._sock.close.return_value = None

    # Should not raise
    mock_tls_socket.close()

    mock_tls_socket._sock.close.assert_called_once()


# ===== SYSCALL ERROR TESTS =====


@pytest.mark.parametrize(
    'errno_code',
    (
        errno.ECONNRESET,
        errno.EPIPE,
        errno.ENOTCONN,
    ),
)
def test_close_with_acceptable_syscall_errors(mock_tls_socket, errno_code):
    """Test close handles ``SysCallError`` with acceptable errno."""
    error = SSL.SysCallError(errno_code, f'Error {errno_code}')
    mock_tls_socket._ssl_conn.shutdown.side_effect = error
    mock_tls_socket._sock.close.return_value = None

    # Should not raise - errno is acceptable
    mock_tls_socket.close()

    mock_tls_socket._sock.close.assert_called_once()


def test_close_with_unacceptable_syscall_error(mock_tls_socket):
    """Test close raises on ``SysCallError`` with unacceptable errno."""
    error = SSL.SysCallError(errno.EBADF, 'Bad file descriptor')
    mock_tls_socket._ssl_conn.shutdown.side_effect = error
    mock_tls_socket._sock.close.return_value = None

    with pytest.raises(errors.FatalSSLAlert) as exc_info:
        mock_tls_socket.close()

    assert 'SysCallError' in str(exc_info.value)
    assert 'Bad file descriptor' in str(exc_info.value)


def test_close_with_syscall_error_no_args(mock_tls_socket):
    """Test ``SysCallError`` with no args."""
    error = SSL.SysCallError(-1, 'Error with errno -1')
    error.args = [-1]
    mock_tls_socket._ssl_conn.shutdown.side_effect = error
    mock_tls_socket._sock.close.return_value = None

    # No errno to check, should raise
    with pytest.raises(errors.FatalSSLAlert):
        mock_tls_socket.close()


# ===== UNACCEPTABLE SSL ERRORS =====


def test_close_with_unacceptable_ssl_error(mock_tls_socket):
    """Test close raises on unacceptable SSL error."""
    error = SSL.Error()
    error.args = [[('SSL routines', '', 'some other error')]]
    mock_tls_socket._ssl_conn.shutdown.side_effect = error
    mock_tls_socket._sock.close.return_value = None

    with pytest.raises(errors.FatalSSLAlert) as exc_info:
        mock_tls_socket.close()

    assert 'Error during TLS socket close' in str(exc_info.value)


def test_close_with_ssl_error_empty_args(mock_tls_socket):
    """Test ``SSL.Error`` with empty args."""
    error = SSL.Error()
    error.args = []
    mock_tls_socket._ssl_conn.shutdown.side_effect = error
    mock_tls_socket._sock.close.return_value = None

    # No error reason, should raise
    with pytest.raises(errors.FatalSSLAlert):
        mock_tls_socket.close()


def test_close_with_ssl_error_malformed_args(mock_tls_socket):
    """Test ``SSL.Error`` with malformed args (not tuple or wrong length)."""
    error = SSL.Error()
    error.args = [['not', 'a', 'tuple']]
    mock_tls_socket._ssl_conn.shutdown.side_effect = error
    mock_tls_socket._sock.close.return_value = None

    # Malformed args, should raise
    with pytest.raises(errors.FatalSSLAlert):
        mock_tls_socket.close()


def test_close_with_ssl_error_short_tuple(mock_tls_socket):
    """Test ``SSL.Error`` with tuple that's too short."""
    error = SSL.Error()
    error.args = [[('SSL routines', 'only two')]]
    mock_tls_socket._ssl_conn.shutdown.side_effect = error
    mock_tls_socket._sock.close.return_value = None

    # Tuple too short, should raise
    with pytest.raises(errors.FatalSSLAlert):
        mock_tls_socket.close()


# ===== SOCKET CLOSE ERRORS =====


@pytest.mark.parametrize(
    'errno_code',
    (
        errno.ECONNRESET,
        errno.EPIPE,
    ),
)
def test_close_with_acceptable_socket_errors(mock_tls_socket, errno_code):
    """Test close handles socket ``OSError`` with acceptable errno."""
    mock_tls_socket._ssl_conn.shutdown.return_value = None
    socket_error = OSError(errno_code, f'Socket error {errno_code}')
    mock_tls_socket._sock.close.side_effect = socket_error

    # Should not raise
    mock_tls_socket.close()


def test_close_with_unacceptable_socket_error(mock_tls_socket):
    """Test close raises on socket ``OSError`` with unacceptable errno."""
    mock_tls_socket._ssl_conn.shutdown.return_value = None
    socket_error = OSError(errno.EBADF, 'Bad file descriptor')
    mock_tls_socket._sock.close.side_effect = socket_error

    with pytest.raises(errors.FatalSSLAlert) as exc_info:
        mock_tls_socket.close()

    assert 'OSError' in str(exc_info.value)


def test_close_with_ssl_shutdown_oserror_unacceptable(mock_tls_socket):
    """Test close handles unacceptable ``OSError`` during SSL shutdown."""
    error = OSError(errno.EBADF, 'Bad file descriptor')
    mock_tls_socket._ssl_conn.shutdown.side_effect = error
    mock_tls_socket._sock.close.return_value = None

    with pytest.raises(errors.FatalSSLAlert) as exc_info:
        mock_tls_socket.close()

    assert 'OSError' in str(exc_info.value)


def test_close_with_ssl_shutdown_oserror_acceptable(mock_tls_socket):
    """Test close handles acceptable ``OSError`` during SSL shutdown."""
    error = OSError(errno.ECONNRESET, 'Connection reset')
    mock_tls_socket._ssl_conn.shutdown.side_effect = error
    mock_tls_socket._sock.close.return_value = None

    # Should not raise - acceptable error
    mock_tls_socket.close()

    mock_tls_socket._sock.close.assert_called_once()


# ===== MULTIPLE ERRORS =====


def test_close_with_multiple_errors(mock_tls_socket):
    """Test close with errors in both SSL shutdown and socket close."""
    ssl_error = SSL.Error()
    ssl_error.args = [[('SSL routines', '', 'bad error')]]
    mock_tls_socket._ssl_conn.shutdown.side_effect = ssl_error

    socket_error = OSError(errno.EBADF, 'Bad file descriptor')
    mock_tls_socket._sock.close.side_effect = socket_error

    with pytest.raises(errors.FatalSSLAlert) as exc_info:
        mock_tls_socket.close()

    error_msg = str(exc_info.value)
    assert 'Multiple errors during close' in error_msg
    assert 'Error' in error_msg  # SSL.Error
    assert 'OSError' in error_msg


def test_close_ssl_error_then_acceptable_socket_error(mock_tls_socket):
    """Test SSL error followed by acceptable socket error."""
    ssl_error = SSL.Error()
    ssl_error.args = [[('SSL routines', '', 'bad error')]]
    mock_tls_socket._ssl_conn.shutdown.side_effect = ssl_error

    socket_error = OSError(errno.ECONNRESET, 'Connection reset')
    mock_tls_socket._sock.close.side_effect = socket_error

    # Only SSL error should be raised (socket error is acceptable)
    with pytest.raises(errors.FatalSSLAlert) as exc_info:
        mock_tls_socket.close()

    error_msg = str(exc_info.value)
    assert 'Multiple errors' not in error_msg
    assert 'Error during TLS socket close' in error_msg


# ===== EDGE CASES =====


def test_close_with_multiple_error_tuples(mock_tls_socket):
    """Test ``SSL.Error`` with multiple error tuples (uses first one)."""
    error = SSL.Error()
    error.args = [
        [
            ('invalid', 'tuple'),
            ('SSL routines', '', 'shutdown while in init'),
            ('SSL routines', '', 'another error'),
        ],
    ]
    mock_tls_socket._ssl_conn.shutdown.side_effect = error
    mock_tls_socket._sock.close.return_value = None

    # Should use first valid error reason
    mock_tls_socket.close()

    mock_tls_socket._sock.close.assert_called_once()


def test_close_ssl_error_none_errno(mock_tls_socket):
    """Test ``SysCallError`` with None as errno."""
    error = SSL.SysCallError(None, 'No errno')
    mock_tls_socket._ssl_conn.shutdown.side_effect = error
    mock_tls_socket._sock.close.return_value = None

    # None not in acceptable codes, should raise
    with pytest.raises(errors.FatalSSLAlert):
        mock_tls_socket.close()


def test_close_ensures_socket_close_even_on_ssl_error(mock_tls_socket):
    """Test that socket close is attempted even if SSL shutdown fails."""
    ssl_error = SSL.Error()
    ssl_error.args = [[('SSL routines', '', 'bad error')]]
    mock_tls_socket._ssl_conn.shutdown.side_effect = ssl_error
    mock_tls_socket._sock.close.return_value = None

    with pytest.raises(errors.FatalSSLAlert):
        mock_tls_socket.close()

    # Verify socket close was still attempted
    mock_tls_socket._sock.close.assert_called_once()


def test_close_with_both_acceptable_errors(mock_tls_socket):
    """Test close with acceptable errors in both SSL and socket."""
    ssl_error = SSL.SysCallError(errno.ECONNRESET, 'Connection reset')
    mock_tls_socket._ssl_conn.shutdown.side_effect = ssl_error

    socket_error = OSError(errno.EPIPE, 'Broken pipe')
    mock_tls_socket._sock.close.side_effect = socket_error

    # Should not raise - both errors are acceptable
    mock_tls_socket.close()
