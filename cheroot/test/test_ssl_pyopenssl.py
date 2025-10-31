# Assuming your existing test file has fixtures for the SSL objects
import pytest
import errno
from OpenSSL import SSL
from cheroot.ssl.pyopenssl import SSLConnection

@pytest.fixture
def mock_ssl_context(mocker):
    """Fixture providing a mock instance of SSL.Context."""
    return mocker.Mock(spec=SSL.Context)

@pytest.fixture
def mock_ssl_conn_class(mocker):
    """Fixture patching the SSL.Connection class constructor."""
    return mocker.patch('OpenSSL.SSL.Connection')

# (SysCallError errno, Expected Exception Type)
ERROR_MAPPINGS = [
    (errno.EBADF, ConnectionError),
    (errno.ECONNABORTED, ConnectionAbortedError),
    (errno.ECONNREFUSED, ConnectionRefusedError),
    (errno.ECONNRESET, ConnectionResetError),
    (errno.ENOTCONN, ConnectionError),
    (errno.EPIPE, BrokenPipeError),
    (errno.ESHUTDOWN, BrokenPipeError),
]

@pytest.mark.parametrize(
    'simulated_errno, expected_exception', ERROR_MAPPINGS
)
def test_close_morphs_syscall_error_correctly(
    mocker, mock_ssl_context, mock_ssl_conn_class, 
    simulated_errno, expected_exception
):
    # The SSLConnection object will now have a safe mock for self._ssl_conn
    conn = SSLConnection(mock_ssl_context) 
    
    # Define the specific OpenSSL error based on the parameter
    simulated_error = SSL.SysCallError(simulated_errno, 'Simulated connection error')

    # 4. Patch the 'close' method on the underlying MOCK object.
    # We retrieve the mock object that was placed in conn._ssl_conn during init.
    # The return value of the mocked SSL.Connection class is what conn._ssl_conn holds.
    underlying_mock = conn._ssl_conn 
    
    mocker.patch.object(
        underlying_mock, 'close',
        side_effect=simulated_error
    )

    # Assert the expected exception is raised based on the parameter
    with pytest.raises(expected_exception) as excinfo:
        conn.close()

    # 6. Assert the original SysCallError is included in the new exception's cause
    assert excinfo.value.__cause__ is simulated_error