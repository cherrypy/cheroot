"""Tests for ``cheroot.ssl.pyopenssl``."""
# Assuming OpenSSL is imported as 'SSL' in your test module

import errno
import io
import socket
import ssl
import threading
import time
from contextlib import suppress

import pytest

from OpenSSL import SSL

from cheroot import errors
from cheroot.makefile import StreamReader, StreamWriter
from cheroot.ssl.pyopenssl import pyOpenSSLAdapter
from cheroot.ssl.tls_socket import TLSSocket, ssl_conn_type

# --- The Main Integration Test ---
from cheroot.wsgi import Server as WSGIServer


_CONNECTION_TIMEOUT_SECONDS = 5.0
_SOCKET_BUFFER_SIZE = 4096


@pytest.mark.usefixtures('mocker')
def test_full_pyopenssl_environ_population(
    tls_certificate_pem_path,
    tls_certificate_private_key_pem_path,
    mocker,
):
    """
    Test pyOpenSSL adapter populates WSGI environ with HTTP and SSL variables.

    Performs an end-to-end test by:
    - Starting a WSGI server with pyOpenSSL TLS adapter
    - Making an SSL client connection
    - Sending an HTTP request over TLS
    - Verifying environ contains correct HTTP vars (METHOD, PATH, QUERY, etc.)
    - Verifying environ contains SSL vars (PROTOCOL, CIPHER, VERSION, DN, etc.)

    This ensures the pyOpenSSL integration correctly exposes SSL connection
    details to WSGI applications through the environ dictionary.
    """
    captured = {'environ': {}}

    def capture_wsgi_app(environ, start_response):
        captured['environ'].update(environ)
        start_response('200 OK', [('Content-Type', 'text/plain')])
        return [b'Hello, secure world!']

    bind_host = '127.0.0.1'
    port = 0

    adapter = pyOpenSSLAdapter(
        tls_certificate_pem_path,
        tls_certificate_private_key_pem_path,
        ciphers='ALL',
    )

    # Use WSGIServer instead of HTTPServer
    server = WSGIServer(
        bind_addr=(bind_host, port),
        wsgi_app=capture_wsgi_app,
    )
    server.ssl_adapter = adapter

    # Prepare the server (binds the socket)
    server.prepare()
    actual_port = server.bind_addr[1]

    # Start the server in a thread
    server_thread = threading.Thread(target=server.serve, daemon=True)
    server_thread.start()

    time.sleep(1)  # Give it time to start

    try:
        # Connect using SSL
        context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

        # === CLIENT SIDE ===
        # 1. Creating socket connection
        sock = socket.create_connection(
            (bind_host, actual_port),
            timeout=_CONNECTION_TIMEOUT_SECONDS,
        )

        # 2. Wrapping with SSL and completing handshake
        client_sock = context.wrap_socket(sock, server_hostname=bind_host)

        # 3. Create request
        request = (
            b'GET /test/path?q=1 HTTP/1.1\r\n'
            b'Host: localhost\r\n'
            b'Connection: close\r\n\r\n'
        )

        # 4. Send request
        client_sock.sendall(request)

        # 5. Read response
        client_sock.settimeout(0.5)
        response = b''
        try:
            while True:
                chunk = client_sock.recv(_SOCKET_BUFFER_SIZE)
                if not chunk:
                    break
                response += chunk
        except socket.timeout:
            # Possible timeout when the server closes
            # the connection after sending the response.
            pass

        client_sock.close()

    finally:
        # Give server time to process
        time.sleep(0.5)

        server.stop()
        server_thread.join(timeout=2)

    captured_environ = captured['environ']

    # Assertions - HTTP Request variables should be populated
    assert captured_environ.get('REQUEST_METHOD') == 'GET', (
        f"Expected REQUEST_METHOD='GET', got '{captured_environ.get('REQUEST_METHOD')}'"
    )

    assert captured_environ.get('PATH_INFO') == '/test/path', (
        f"Expected PATH_INFO='/test/path', got '{captured_environ.get('PATH_INFO')}'"
    )

    assert captured_environ.get('QUERY_STRING') == 'q=1', (
        f"Expected empty QUERY_STRING, got '{captured_environ.get('QUERY_STRING')}'"
    )

    assert captured_environ.get('SERVER_PROTOCOL') == 'HTTP/1.1', (
        f"Expected SERVER_PROTOCOL='HTTP/1.1', got '{captured_environ.get('SERVER_PROTOCOL')}'"
    )

    # SSL variables should be populated
    assert 'SSL_PROTOCOL' in captured_environ, 'SSL_PROTOCOL not in environ'
    assert 'TLSv1' in captured_environ['SSL_PROTOCOL']

    assert 'SSL_CIPHER' in captured_environ, 'SSL_CIPHER not in environ'

    assert 'SSL_VERSION_LIBRARY' in captured_environ
    assert 'OpenSSL' in captured_environ['SSL_VERSION_LIBRARY']

    assert 'SSL_VERSION_INTERFACE' in captured_environ
    assert 'pyOpenSSL' in captured_environ['SSL_VERSION_INTERFACE']

    assert 'SSL_SERVER_M_SERIAL' in captured_environ

    assert 'SSL_SERVER_S_DN_CN' in captured_environ, (
        'SSL_SERVER_S_DN_CN not in environ'
    )
    assert captured_environ['SSL_SERVER_S_DN_CN'] == 'localhost', (
        f"Expected CN='localhost', got '{captured_environ['SSL_SERVER_S_DN_CN']}'"
    )


# --- Parameterized Test Cases ---
test_cases = [
    (
        'Success after WantReadError',
        'recv',  # Changed from 'safe_recv'
        'recv',
        [SSL.WantReadError, b'OK'],
        None,
        b'OK',
        2,
    ),
    (
        'Success after WantWriteError',
        'send',  # Changed from 'safe_send'
        'send',
        [SSL.WantWriteError, b'OK'],
        None,
        b'OK',
        2,
    ),
    (
        'Timeout',
        'recv',  # Changed from 'safe_recv'
        'recv',
        [SSL.WantReadError] * 4,
        socket.timeout,
        None,
        2,
    ),
    (
        'SysCallError: Unexpected EOF',
        'recv',  # Changed from 'safe_recv'
        'recv',
        [SSL.SysCallError(-1, 'Unexpected EOF')],
        None,
        b'',
        1,
    ),
    (
        'SysCallError: Ignorable Socket Error (e.g., Broken Pipe)',
        'recv',  # Changed from 'safe_recv'
        'recv',
        [SSL.SysCallError(errno.EPIPE, 'Broken pipe')],
        None,
        b'',
        1,
    ),
    (
        'SysCallError: Non-Ignorable Error (Connection Reset)',
        'recv',  # Changed from 'safe_recv'
        'recv',
        [SSL.SysCallError(errno.ENOTCONN, 'Socket is not connected')],
        socket.error,
        None,
        1,
    ),
    (
        'SysCallError: Non-Ignorable Error (Writer)',
        'send',  # Changed from 'safe_send'
        'send',
        [SSL.SysCallError(999, 'Fatal system error')],
        socket.error,
        None,
        1,
    ),
    (
        'SSL.Error: NoSSLError (HTTP Request)',
        'recv',  # Changed from 'safe_recv'
        'recv',
        [SSL.Error([(-1, 'SSL routines', 'http request')])],
        errors.NoSSLError,
        None,
        1,
    ),
    (
        'SSL.Error: Fatal SSL Alert',
        'recv',  # Changed from 'safe_recv'
        'recv',
        [SSL.Error([(-1, 'SSL routines', 'generic alert')])],
        errors.FatalSSLAlert,
        None,
        1,
    ),
]


@pytest.mark.parametrize(
    (
        'test_case_name',
        'call_method',
        'mock_target',
        'side_effects',
        'expected_exception',
        'expected_result',
        'expected_call_count',
    ),
    test_cases,
    ids=[case[0] for case in test_cases],  # Extract names at module level
)
def test_safe_call_coverage(  # pylint: disable=too-many-positional-arguments
    test_case_name,
    call_method,
    mock_target,
    side_effects,
    expected_exception,
    expected_result,
    expected_call_count,
    mocker,
):
    """Test all critical success, retry, and error-mapping paths in _safe_call."""
    # Create mocks
    mock_ssl_conn = mocker.MagicMock()
    mock_ssl_conn.__class__ = ssl_conn_type
    getattr(mock_ssl_conn, mock_target).side_effect = side_effects

    mock_raw_socket = mocker.MagicMock()
    mock_raw_socket.gettimeout.return_value = 1.0
    mock_context = mocker.MagicMock()

    # Configure time mocks for the timeout case
    mock_sleep = mocker.patch('time.sleep')

    if expected_exception is socket.timeout:
        start_time = 1000.0
        mocker.patch('time.time').side_effect = [
            start_time,  # Start time
            start_time + 0.05,  # First check (0.05 < 0.1)
            start_time + 0.15,  # Second check (0.15 > 0.1) -> Timeout
        ]
    else:
        mocker.patch('time.time').return_value = 1000.0

    # Create TLSSocket
    tls_socket = TLSSocket(mock_ssl_conn, mock_raw_socket, mock_context)

    # Call the method
    call_func = getattr(tls_socket, call_method)
    if expected_exception:
        # Test Case expects an exception
        with pytest.raises(expected_exception):
            # Pass dummy args for recv/send
            call_func(1024) if call_method == 'recv' else call_func(
                b'test data',
            )

    else:
        # Test Case expects a successful return
        actual_result = (
            call_func(1024)
            if call_method == 'recv'
            else call_func(b'test data')
        )
        assert actual_result == expected_result

    # Final check on call count
    assert (
        getattr(mock_ssl_conn, mock_target).call_count == expected_call_count
    )

    # Ensure sleep was called if errors occurred that require retries
    if expected_exception is not None and expected_exception not in {
        socket.error,
        errors.NoSSLError,
        errors.FatalSSLAlert,
    }:
        assert mock_sleep.called


def test_tlssocket_is_readable(mocker):
    """Test that TLSSocket properly declares itself as readable."""
    mock_ssl_conn = mocker.MagicMock(spec=SSL.Connection)
    mock_raw_socket = mocker.MagicMock()
    mock_context = mocker.MagicMock()
    mock_raw_socket.gettimeout.return_value = 1.0

    tls_socket = TLSSocket(mock_ssl_conn, mock_raw_socket, mock_context)

    assert isinstance(tls_socket, io.RawIOBase)

    # The real test - if these are False, our methods aren't being called
    if tls_socket.readable() is False:
        pytest.fail(
            'TLSSocket.readable() is not working - check if changes were applied to the actual file',
        )

    assert tls_socket.readable() is True
    assert hasattr(tls_socket, 'readinto')


@pytest.mark.parametrize(
    (
        'io_method',
        'error_class',
        'call_target',
        'test_input',
        'expected_output',
    ),
    (
        ('readinto', SSL.WantReadError, 'recv', 100, b'Hello World'),
        ('write', SSL.WantWriteError, 'send', b'Test data', 9),
    ),
    ids=['readinto_WantReadError', 'write_WantWriteError'],
)
def test_tlssocket_io_handles_want_errors(  # pylint: disable=too-many-positional-arguments
    mocker,
    io_method,
    error_class,
    call_target,
    test_input,
    expected_output,
):
    """Test that TLSSocket I/O methods handle WantRead/WantWrite errors with retry."""
    # Setup mocks
    mock_ssl_conn = mocker.MagicMock(spec=ssl_conn_type)
    mock_ssl_conn.__class__ = ssl_conn_type
    mock_raw_socket = mocker.MagicMock()
    mock_context = mocker.MagicMock()
    mock_raw_socket.gettimeout.return_value = 1.0

    # Track call count
    call_count = {'count': 0}

    # Configure mock to raise error first, then succeed
    def io_operation(*args, **kwargs):
        call_count['count'] += 1

        if call_count['count'] == 1:
            raise error_class()
        if call_target == 'recv':
            return expected_output
        # send
        return len(args[0]) if args else expected_output

    # Attach mock to the appropriate method
    setattr(mock_ssl_conn, call_target, io_operation)

    # Create TLSSocket
    tls_socket = TLSSocket(mock_ssl_conn, mock_raw_socket, mock_context)

    # Execute the I/O operation
    if io_method == 'readinto':
        buffer = bytearray(test_input)
        bytes_read = tls_socket.readinto(buffer)
        assert bytes(buffer[:bytes_read]) == expected_output
        assert bytes_read == len(expected_output)
    else:  # write
        bytes_written = tls_socket.write(test_input)
        assert bytes_written == expected_output

    # Verify retry happened
    assert call_count['count'] == 2, (
        f'Should have retried after {error_class.__name__}'
    )


def test_tlssocket_readinto_handles_syscallerror_eof(mocker):
    """Test that TLSSocket.readinto() handles SysCallError with Unexpected EOF."""
    mock_ssl_conn = mocker.MagicMock(spec=ssl_conn_type)
    mock_ssl_conn.__class__ = ssl_conn_type
    mock_raw_socket = mocker.MagicMock()
    mock_context = mocker.MagicMock()

    # SysCallError with Unexpected EOF should return empty
    mock_ssl_conn.recv = mocker.MagicMock(
        side_effect=SSL.SysCallError(-1, 'Unexpected EOF'),
    )
    mock_raw_socket.gettimeout.return_value = 1.0

    tls_socket = TLSSocket(mock_ssl_conn, mock_raw_socket, mock_context)

    buffer = bytearray(100)
    bytes_read = tls_socket.readinto(buffer)

    assert bytes_read == 0, 'Unexpected EOF should return 0 bytes (EOF)'


def test_tlssocket_with_buffered_reader(mocker):
    """Test that TLSSocket works correctly with :class:`io.BufferedReader`."""
    mock_ssl_conn = mocker.MagicMock(spec=ssl_conn_type)
    mock_ssl_conn.__class__ = ssl_conn_type
    mock_raw_socket = mocker.MagicMock()
    mock_context = mocker.MagicMock()

    call_count = {'count': 0}

    def recv_with_retry(size):
        call_count['count'] += 1
        if call_count['count'] == 1:
            raise SSL.WantReadError
        if call_count['count'] == 2:
            return b'Data from BufferedReader'
        # Return empty to signal EOF for subsequent calls
        return b''

    mock_ssl_conn.recv = recv_with_retry
    mock_raw_socket.gettimeout.return_value = 1.0

    tls_socket = TLSSocket(mock_ssl_conn, mock_raw_socket, mock_context)

    # Create BufferedReader with TLSSocket as the raw I/O
    reader = io.BufferedReader(tls_socket, buffer_size=8192)

    # Read through BufferedReader
    read_data = reader.read(100)

    assert read_data == b'Data from BufferedReader'
    assert call_count['count'] >= 2, 'Should have retried after WantReadError'


def test_tlssocket_timeout_on_repeated_errors(mocker):
    """Test that repeated SSL errors eventually timeout."""
    mock_ssl_conn = mocker.MagicMock(spec=ssl_conn_type)
    mock_ssl_conn.__class__ = ssl_conn_type
    mock_raw_socket = mocker.MagicMock()
    mock_context = mocker.MagicMock()

    # Always raise WantReadError
    mock_ssl_conn.recv = mocker.MagicMock(side_effect=SSL.WantReadError())
    mock_raw_socket.gettimeout.return_value = 1.0

    tls_socket = TLSSocket(mock_ssl_conn, mock_raw_socket, mock_context)
    tls_socket.ssl_retry_max = 0.05  # Short timeout for testing

    buffer = bytearray(100)

    with pytest.raises(socket.timeout):
        tls_socket.readinto(buffer)


def test_tlssocket_sock_shutdown(mocker):
    """Test that sock_shutdown calls the raw socket's shutdown method."""
    mock_ssl_conn = mocker.MagicMock()
    mock_ssl_conn.__class__ = ssl_conn_type
    mock_raw_socket = mocker.MagicMock()
    mock_context = mocker.MagicMock()

    tls_socket = TLSSocket(mock_ssl_conn, mock_raw_socket, mock_context)

    # Call sock_shutdown
    tls_socket.sock_shutdown(socket.SHUT_RDWR)

    # Verify it called the raw socket's shutdown, not the SSL connection's
    mock_raw_socket.shutdown.assert_called_once_with(socket.SHUT_RDWR)
    mock_ssl_conn.shutdown.assert_not_called()


@pytest.mark.usefixtures('mocker')
def test_wrap_with_pyopenssl_ssl_connection_creation_fails(
    tls_certificate_pem_path,
    tls_certificate_private_key_pem_path,
    mocker,
):
    """Test that SSL.Connection creation error raises FatalSSLAlert."""
    adapter = pyOpenSSLAdapter(
        tls_certificate_pem_path,
        tls_certificate_private_key_pem_path,
    )
    adapter.context = adapter.get_context()

    # Use a real socket
    server_sock, client_sock = socket.socketpair()

    try:
        # Patch where it's imported IN THE MODULE
        call_count = {'count': 0}

        def failing_connection(context, sock):
            call_count['count'] += 1
            raise SSL.Error([(-1, 'SSL routines', 'initialization failed')])

        # Patch ssl_conn_type, not SSL.Connection
        mocker.patch(
            'cheroot.ssl.pyopenssl.ssl_conn_type',
            side_effect=failing_connection,
        )

        with pytest.raises(
            errors.FatalSSLAlert,
            match='Error creating pyOpenSSL connection',
        ):
            adapter._wrap_with_pyopenssl(server_sock)

    finally:
        server_sock.close()
        client_sock.close()


@pytest.mark.parametrize(
    ('error_class', 'error_args', 'expected_exception', 'match_text'),
    (
        (
            SSL.WantReadError,
            None,
            None,  # Should retry, not raise
            None,
        ),
        (
            OSError,
            (errno.ECONNRESET, 'Connection reset by peer'),
            errors.FatalSSLAlert,
            'TCP error during handshake',
        ),
        (
            SSL.Error,
            [(-1, 'SSL routines', 'http request')],
            errors.NoSSLError,
            'Client sent plain HTTP request',
        ),
        (
            SSL.Error,
            [(-1, 'SSL routines', 'certificate verify failed')],
            errors.FatalSSLAlert,
            'Fatal SSL error during handshake',
        ),
        (
            SSL.ZeroReturnError,  # NEW
            None,
            errors.NoSSLError,
            'Peer closed connection during handshake',
        ),
    ),
    ids=[
        'WantReadError_retry',
        'OSError_ECONNRESET',
        'SSL_http_request',
        'SSL_cert_failed',
        'ZeroReturnError',
    ],
)
def test_handshake_error_handling(  # pylint: disable=too-many-positional-arguments
    tls_certificate_pem_path,
    tls_certificate_private_key_pem_path,
    mocker,
    error_class,
    error_args,
    expected_exception,
    match_text,
):
    """Test various error conditions during SSL handshake."""
    adapter = pyOpenSSLAdapter(
        tls_certificate_pem_path,
        tls_certificate_private_key_pem_path,
    )
    adapter.context = adapter.get_context()

    server_sock, client_sock = socket.socketpair()

    try:
        original_connection = SSL.Connection
        handshake_attempts = {'count': 0}

        def patched_connection(context, sock):
            conn = original_connection(context, sock)

            def failing_handshake():
                handshake_attempts['count'] += 1
                if handshake_attempts['count'] == 1:
                    if error_args:
                        raise (
                            error_class(*error_args)
                            if isinstance(error_args, tuple)
                            else error_class(error_args)
                        )
                    raise error_class()
                # Second attempt for retry cases
                raise SSL.Error([(-1, 'SSL routines', 'test completed')])

            conn.do_handshake = failing_handshake
            return conn

        mocker.patch(
            'cheroot.ssl.pyopenssl.ssl_conn_type',
            side_effect=patched_connection,
        )
        mocker.patch(
            'select.select',
            return_value=([server_sock.fileno()], [], []),
        )

        if expected_exception:
            with pytest.raises(expected_exception, match=match_text):
                adapter._wrap_with_pyopenssl(server_sock)
        else:
            with suppress(Exception):
                adapter._wrap_with_pyopenssl(server_sock)
            assert handshake_attempts['count'] >= 2

    finally:
        server_sock.close()
        client_sock.close()


def test_streamreader_with_tls_socket(mocker):
    """Test StreamReader works correctly with TLSSocket."""
    # Setup a TLSSocket instance
    mock_ssl_socket = mocker.MagicMock()
    mock_raw_socket = mocker.MagicMock()
    mock_context = mocker.MagicMock()

    mock_tls_socket = TLSSocket(
        ssl_socket=mock_ssl_socket,
        raw_socket=mock_raw_socket,
        context=mock_context,
    )

    # Create StreamReader with TLSSocket
    buffered_reader = StreamReader(mock_tls_socket, bufsize=4096)

    # Assert it's a StreamReader instance
    assert isinstance(buffered_reader, StreamReader)
    assert buffered_reader.bytes_read == 0

    # Verify TLSSocket was used directly (not wrapped with SocketIO)
    # The _wrapped attribute would be the TLSSocket itself
    assert buffered_reader.raw is mock_tls_socket


def test_streamwriter_with_regular_socket(mocker):
    """Test StreamWriter works correctly with regular socket."""
    regular_sock = mocker.MagicMock()

    # Mock SocketIO to verify it's called for regular sockets
    mock_socket_io = mocker.patch('socket.SocketIO')
    mock_socket_io.return_value = mocker.MagicMock()

    writer = StreamWriter(regular_sock, bufsize=1024)

    # Verify SocketIO was called to wrap the regular socket
    mock_socket_io.assert_called_once_with(regular_sock, 'wb')

    # Verify it's a StreamWriter instance
    assert isinstance(writer, StreamWriter)
    assert writer.bytes_written == 0
