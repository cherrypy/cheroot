"""Tests for ``cheroot.ssl.builtin``."""

import socket
import ssl
import threading
import time
from contextlib import closing

import pytest

from cheroot import errors
from cheroot.makefile import StreamReader, StreamWriter
from cheroot.ssl.builtin import BuiltinSSLAdapter
from cheroot.ssl.tls_socket import TLSSocket


_CONNECTION_TIMEOUT_SECONDS = 5.0
_SOCKET_BUFFER_SIZE = 4096


@pytest.mark.usefixtures('mocker')
def test_full_builtin_environ_population(
    tls_certificate_pem_path,
    tls_certificate_private_key_pem_path,
    mocker,
):
    """Test that builtin adapter populates all SSL environ variables correctly."""
    captured = {'environ': {}}

    def capture_wsgi_app(environ, start_response):
        captured['environ'].update(environ)
        start_response('200 OK', [('Content-Type', 'text/plain')])
        return [b'Hello, secure world!']

    bind_host = '127.0.0.1'
    port = 0

    adapter = BuiltinSSLAdapter(
        tls_certificate_pem_path,
        tls_certificate_private_key_pem_path,
    )

    from cheroot.wsgi import Server as WSGIServer

    server = WSGIServer(
        bind_addr=(bind_host, port),
        wsgi_app=capture_wsgi_app,
    )
    server.ssl_adapter = adapter

    server.prepare()
    actual_port = server.bind_addr[1]

    server_thread = threading.Thread(target=server.serve, daemon=True)
    server_thread.start()

    time.sleep(1)

    try:
        context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

        sock = socket.create_connection(
            (bind_host, actual_port),
            timeout=_CONNECTION_TIMEOUT_SECONDS,
        )
        client_sock = context.wrap_socket(sock, server_hostname=bind_host)

        request = (
            b'GET /test/path?q=1 HTTP/1.1\r\n'
            b'Host: localhost\r\n'
            b'Connection: close\r\n\r\n'
        )
        client_sock.sendall(request)

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
        time.sleep(0.5)
        server.stop()
        server_thread.join(timeout=2)

    captured_environ = captured['environ']

    # HTTP Request variables
    assert captured_environ.get('REQUEST_METHOD') == 'GET'
    assert captured_environ.get('PATH_INFO') == '/test/path'
    assert captured_environ.get('QUERY_STRING') == 'q=1'
    assert captured_environ.get('SERVER_PROTOCOL') == 'HTTP/1.1'

    # SSL variables
    assert 'SSL_PROTOCOL' in captured_environ
    assert 'TLS' in captured_environ['SSL_PROTOCOL']

    assert 'SSL_CIPHER' in captured_environ

    assert 'SSL_VERSION_LIBRARY' in captured_environ
    assert 'OpenSSL' in captured_environ['SSL_VERSION_LIBRARY']

    assert 'SSL_VERSION_INTERFACE' in captured_environ
    assert 'Python' in captured_environ['SSL_VERSION_INTERFACE']

    assert 'SSL_SERVER_M_SERIAL' in captured_environ

    assert 'SSL_SERVER_S_DN_CN' in captured_environ
    assert captured_environ['SSL_SERVER_S_DN_CN'] == 'localhost'


@pytest.mark.usefixtures('mocker')
def test_wrap_with_builtin_ssl_wrap_fails(
    tls_certificate_pem_path,
    tls_certificate_private_key_pem_path,
    mocker,
):
    """Test that SSL wrap_socket error raises FatalSSLAlert."""
    adapter = BuiltinSSLAdapter(
        tls_certificate_pem_path,
        tls_certificate_private_key_pem_path,
    )
    adapter.context = adapter._create_context()

    server_sock, client_sock = socket.socketpair()

    try:

        def failing_wrap_socket(sock, *args, **kwargs):
            raise ssl.SSLError('SSL wrap failed')

        mocker.patch.object(
            adapter.context,
            'wrap_socket',
            side_effect=failing_wrap_socket,
        )

        with pytest.raises(
            errors.FatalSSLAlert,
            match='Error creating SSL socket',
        ):
            adapter._wrap_with_builtin(server_sock)

    finally:
        server_sock.close()
        client_sock.close()


@pytest.mark.parametrize(
    ('error_class', 'error_msg', 'expected_exception', 'match_text'),
    (
        (
            ssl.SSLWantReadError,
            'The operation did not complete',
            None,  # Should retry, not raise
            None,
        ),
        (
            ssl.SSLWantWriteError,
            'The operation did not complete',
            None,  # Should retry, not raise
            None,
        ),
        (
            OSError,
            'Connection reset by peer',
            errors.FatalSSLAlert,
            'TCP error during handshake',
        ),
        (
            ssl.SSLError,
            'wrong version number',
            errors.NoSSLError,
            'Client sent plain HTTP request',
        ),
        (
            ssl.SSLError,
            'certificate verify failed',
            errors.FatalSSLAlert,
            'Fatal SSL error during handshake',
        ),
        (
            ssl.SSLEOFError,
            'EOF occurred',
            errors.NoSSLError,
            'Peer closed connection during handshake',
        ),
    ),
    ids=[
        'SSLWantReadError_retry',
        'SSLWantWriteError_retry',
        'OSError_connection_reset',
        'SSLError_wrong_version',
        'SSLError_cert_failed',
        'SSLEOFError',
    ],
)
def test_builtin_handshake_error_handling(  # pylint: disable=too-many-positional-arguments
    tls_certificate_pem_path,
    tls_certificate_private_key_pem_path,
    mocker,
    error_class,
    error_msg,
    expected_exception,
    match_text,
):
    """Test various error conditions during builtin SSL handshake."""
    adapter = BuiltinSSLAdapter(
        tls_certificate_pem_path,
        tls_certificate_private_key_pem_path,
    )
    adapter.context = adapter._create_context()

    server_sock, client_sock = socket.socketpair()

    try:
        handshake_attempts = {'count': 0}

        def failing_do_handshake():
            handshake_attempts['count'] += 1
            if handshake_attempts['count'] == 1:
                raise error_class(error_msg)
            # Second attempt succeeds (for retry cases)

        # Mock wrap_socket to return a mock SSL socket
        mock_ssl_socket = mocker.MagicMock(spec=ssl.SSLSocket)
        mock_ssl_socket.do_handshake = failing_do_handshake
        mock_ssl_socket.context = adapter.context

        mocker.patch.object(
            adapter.context,
            'wrap_socket',
            return_value=mock_ssl_socket,
        )

        # Mock select for WantRead/WantWrite cases
        if error_class in {ssl.SSLWantReadError, ssl.SSLWantWriteError}:
            mocker.patch(
                'select.select',
                return_value=(
                    [server_sock.fileno()],
                    [server_sock.fileno()],
                    [],
                ),
            )

        if expected_exception:
            with pytest.raises(expected_exception, match=match_text):
                adapter._wrap_with_builtin(server_sock)
        else:
            # Should retry and succeed
            tls_sock = adapter._wrap_with_builtin(server_sock)
            assert isinstance(tls_sock, TLSSocket)
            assert handshake_attempts['count'] >= 2, (
                f'Expected retry but only {handshake_attempts["count"]} attempts'
            )

    finally:
        server_sock.close()
        client_sock.close()


def test_builtin_handshake_timeout(
    tls_certificate_pem_path,
    tls_certificate_private_key_pem_path,
    mocker,
):
    """Test that handshake times out on repeated WantRead errors."""
    adapter = BuiltinSSLAdapter(
        tls_certificate_pem_path,
        tls_certificate_private_key_pem_path,
    )
    adapter.context = adapter._create_context()

    server_sock, client_sock = socket.socketpair()

    with closing(server_sock), closing(client_sock):
        # Mock wrap_socket
        mock_ssl_socket = mocker.MagicMock(spec=ssl.SSLSocket)
        mock_ssl_socket.do_handshake.side_effect = ssl.SSLWantReadError()

        mocker.patch.object(
            adapter.context,
            'wrap_socket',
            return_value=mock_ssl_socket,
        )

        # Mock select to return empty (timeout)
        mocker.patch('select.select', return_value=([], [], []))

        with pytest.raises(TimeoutError, match='Handshake failed'):
            adapter._wrap_with_builtin(server_sock)


def test_builtin_create_ssl_socket_error(
    tls_certificate_pem_path,
    tls_certificate_private_key_pem_path,
    mocker,
):
    """Test that wrap_socket errors are caught and converted to FatalSSLAlert."""
    adapter = BuiltinSSLAdapter(
        tls_certificate_pem_path,
        tls_certificate_private_key_pem_path,
    )
    # Create the context first so it has valid certs
    adapter.context = adapter._create_context()

    server_sock, client_sock = socket.socketpair()

    with closing(server_sock), closing(client_sock):
        # Now patch wrap_socket AFTER context is created
        mocker.patch.object(
            adapter.context,
            'wrap_socket',
            side_effect=ssl.SSLError('Failed to create SSL socket'),
        )

    with pytest.raises(
        errors.FatalSSLAlert,
        match='Error creating SSL socket',
    ):
        adapter._wrap_with_builtin(server_sock)


def test_builtin_adapter_get_server_cert_environ_no_cert(
    tls_certificate_private_key_pem_path,
):
    """Test that _get_server_cert_environ returns empty dict when no certificate."""
    adapter = BuiltinSSLAdapter(
        None,  # No certificate
        tls_certificate_private_key_pem_path,
    )

    environ = adapter._get_server_cert_environ()
    assert len(environ) == 0


def test_builtin_adapter_get_server_cert_environ_invalid_file(
    tls_certificate_private_key_pem_path,
):
    """Test that _get_server_cert_environ handles invalid cert file gracefully."""
    with pytest.raises(
        FileNotFoundError,
        match='SSL certificate file not found',
    ):
        BuiltinSSLAdapter(
            '/nonexistent/cert.pem',
            tls_certificate_private_key_pem_path,
        )


def test_builtin_adapter_client_cert_no_verification(
    tls_certificate_pem_path,
    tls_certificate_private_key_pem_path,
    mocker,
):
    """Test that client cert environ is not populated when verification is disabled."""
    adapter = BuiltinSSLAdapter(
        tls_certificate_pem_path,
        tls_certificate_private_key_pem_path,
    )

    # Mock TLSSocket with no client cert verification
    mock_conn = mocker.MagicMock()

    # IMPORTANT: Mock _sock, not _ssl_socket!
    mock_conn._sock.getpeercert = mocker.MagicMock(
        side_effect=lambda binary_form=False: None,
    )
    mock_conn.context.verify_mode = ssl.CERT_NONE

    ssl_environ = {'HTTPS': 'on'}
    environ = adapter._get_client_cert_environ(mock_conn, ssl_environ)

    assert environ['SSL_CLIENT_VERIFY'] == 'NONE'
    assert 'SSL_CLIENT_CERT' not in environ


def test_streamreader_with_tls_and_regular_sockets(mocker):
    """Test StreamReader works with both TLSSocket and regular sockets."""
    # Test with TLSSocket
    mock_ssl_socket = mocker.MagicMock(spec=ssl.SSLSocket)
    mock_tls_socket = TLSSocket(
        ssl_socket=mock_ssl_socket,
        raw_socket=mocker.MagicMock(),
        context=mocker.MagicMock(),
    )

    buffered_reader = StreamReader(mock_tls_socket)
    assert isinstance(buffered_reader, StreamReader)
    assert buffered_reader.bytes_read == 0
    assert hasattr(buffered_reader, 'read')

    # Test with regular socket
    regular_sock = mocker.MagicMock()
    mock_socket_io = mocker.patch('socket.SocketIO')
    mock_socket_io.return_value = mocker.MagicMock()

    buffered_reader = StreamReader(regular_sock)

    # Verify SocketIO was called to wrap regular socket
    mock_socket_io.assert_called_once_with(regular_sock, 'rb')
    assert isinstance(buffered_reader, StreamReader)
    assert buffered_reader.bytes_read == 0


def test_streamwriter_with_tls_and_regular_sockets(mocker):
    """Test StreamWriter works with both TLSSocket and regular sockets."""
    # Test with TLSSocket
    mock_ssl_socket = mocker.MagicMock(spec=ssl.SSLSocket)
    mock_tls_socket = TLSSocket(
        ssl_socket=mock_ssl_socket,
        raw_socket=mocker.MagicMock(),
        context=mocker.MagicMock(),
    )

    buffered_writer = StreamWriter(mock_tls_socket)
    assert isinstance(buffered_writer, StreamWriter)
    assert buffered_writer.bytes_written == 0
    assert hasattr(buffered_writer, 'write')

    # Test with regular socket
    regular_sock = mocker.MagicMock()
    mock_socket_io = mocker.patch('socket.SocketIO')
    mock_socket_io.return_value = mocker.MagicMock()

    buffered_writer = StreamWriter(regular_sock)

    # Verify SocketIO was called to wrap regular socket
    mock_socket_io.assert_called_once_with(regular_sock, 'wb')
    assert isinstance(buffered_writer, StreamWriter)
    assert buffered_writer.bytes_written == 0
