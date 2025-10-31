"""Tests for Cheroot's pyopenssl SSLConnection wrapper."""

import errno

import pytest

from OpenSSL import SSL

from cheroot.ssl.pyopenssl import SSLConnection


@pytest.fixture
def mock_ssl_context(mocker):
    """Fixture providing a mock instance of SSL.Context."""
    mock_context = mocker.Mock(spec=SSL.Context)
    mock_context._context = mocker.Mock()
    return mock_context


# (Method Name, SysCallError errno, Expected Exception Type)
ERROR_MAPPINGS = (
    ('close', errno.EBADF, ConnectionError),
    ('close', errno.ECONNABORTED, ConnectionAbortedError),
    ('shutdown', errno.EPIPE, BrokenPipeError),  # Test 'shutdown' here
    (
        'shutdown',
        errno.ECONNRESET,
        ConnectionResetError,
    ),  # Test 'shutdown' here
    ('close', errno.ENOTCONN, ConnectionError),
    ('close', errno.EPIPE, BrokenPipeError),
    ('close', errno.ESHUTDOWN, BrokenPipeError),
)


@pytest.mark.parametrize(
    (
        'tested_method_name',
        'simulated_errno',
        'expected_exception',
    ),
    ERROR_MAPPINGS,
)
def test_close_morphs_syscall_error_correctly(
    mocker,
    mock_ssl_context,
    tested_method_name,
    simulated_errno,
    expected_exception,
):
    """Check SSLConnection.close() morphs SysCallError to ConnectionError."""
    # Prevents the real OpenSSL.SSL.Connection.__init__ from running
    mocker.patch('OpenSSL.SSL.Connection')

    # Create SSLConnection object with a mock for _ssl_conn
    conn = SSLConnection(mock_ssl_context)

    # Define the specific OpenSSL error based on the parameter
    simulated_error = SSL.SysCallError(
        simulated_errno,
        'Simulated connection error',
    )

    # Dynamically retrieve the method on the underlying mock
    underlying_method = getattr(conn._ssl_conn, tested_method_name)

    # Patch the method to raise the simulated error
    underlying_method.side_effect = simulated_error

    # Assert the expected exception is raised based on the parameter
    with pytest.raises(expected_exception) as excinfo:
        getattr(conn, tested_method_name)()

    # Assert the original SysCallError is included in the new exception's cause
    assert excinfo.value.__cause__ is simulated_error
