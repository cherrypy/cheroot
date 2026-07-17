"""Tests for :py:mod:`cheroot.ssl.pyopenssl` :py:class:`cheroot.ssl.pyopenssl.SSLConnection` wrapper."""

import errno

import pytest

from OpenSSL import SSL

from cheroot.ssl.pyopenssl import SSLConnection


@pytest.fixture
def mock_ssl_context(mocker):
    """Fixture providing a mock instance of :py:class:`OpenSSL.SSL.Context`."""
    mock_context = mocker.Mock(spec=SSL.Context)

    # Add a mock _context attribute to simulate SSL.Context behavior
    mock_context._context = mocker.Mock()
    return mock_context


@pytest.mark.filterwarnings('ignore:Non-callable called')
@pytest.mark.parametrize(
    (
        'tested_method_name',
        'simulated_errno',
        'expected_exception',
    ),
    (
        pytest.param('close', errno.EBADF, ConnectionError, id='close-EBADF'),
        pytest.param(
            'close',
            errno.ECONNABORTED,
            ConnectionAbortedError,
            id='close-ECONNABORTED',
        ),
        pytest.param(
            'send',
            errno.EPIPE,
            BrokenPipeError,
            id='send-EPIPE',
        ),  # Expanded coverage
        pytest.param(
            'shutdown',
            errno.EPIPE,
            BrokenPipeError,
            id='shutdown-EPIPE',
        ),
        pytest.param(
            'shutdown',
            errno.ECONNRESET,
            ConnectionResetError,
            id='shutdown-ECONNRESET',
        ),
        pytest.param(
            'close',
            errno.ENOTCONN,
            ConnectionError,
            id='close-ENOTCONN',
        ),
        pytest.param('close', errno.EPIPE, BrokenPipeError, id='close-EPIPE'),
        pytest.param(
            'close',
            errno.ESHUTDOWN,
            BrokenPipeError,
            id='close-ESHUTDOWN',
        ),
    ),
)
def test_close_morphs_syscall_error_correctly(
    mocker,
    mock_ssl_context,
    tested_method_name,
    simulated_errno,
    expected_exception,
):
    """Check ``SSLConnection.close()`` morphs ``SysCallError`` to ``ConnectionError``."""
    # Prevents the real OpenSSL.SSL.Connection.__init__ from running
    mocker.patch('OpenSSL.SSL.Connection')

    # Create SSLConnection object. The patched SSL.Connection() call returns
    # a mock that is stored internally as conn._ssl_conn.
    conn = SSLConnection(mock_ssl_context)

    # Define specific OpenSSL error based on the parameter
    simulated_error = SSL.SysCallError(
        simulated_errno,
        'Simulated connection error',
    )

    # Dynamically retrieve the method on the underlying mock
    underlying_method = getattr(conn._ssl_conn, tested_method_name)

    # Patch the method to raise the simulated error
    underlying_method.side_effect = simulated_error

    expected_match = (
        f'.*Error in calling {tested_method_name} on PyOpenSSL connection.*'
    )

    # Assert the expected exception is raised based on the parameter
    with pytest.raises(expected_exception, match=expected_match) as excinfo:
        getattr(conn, tested_method_name)()

    # Assert the original SysCallError is included in the new exception's cause
    assert excinfo.value.__cause__ is simulated_error
