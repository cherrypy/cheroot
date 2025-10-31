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
    """Check ``SSLConnection`` methods morph ``SysCallError`` to appropriate exceptions."""
    SysCallError = type('SysCallError', (Exception,), {})

    mocker.patch('OpenSSL.SSL.Connection')
    mocker.patch('cheroot.ssl.pyopenssl.SSL.SysCallError', SysCallError)
    mock_ssl_context._context = 0xDEADBEEF

    conn = SSLConnection(mock_ssl_context, mocker.MagicMock(name='socket'))

    simulated_error = SysCallError(simulated_errno, 'Simulated error')
    getattr(conn._ssl_conn, tested_method_name).side_effect = simulated_error

    with pytest.raises(
        expected_exception,
        match=f'.*Error in calling {tested_method_name}.*',
    ) as exc:
        getattr(conn, tested_method_name)()

    assert isinstance(exc.value.__cause__, SysCallError)
    assert exc.value.__cause__.args[0] == simulated_errno
