"""Tests for TLS support."""

import contextlib
import errno
import functools
import http.client
import io
import json
import os
import socket
import ssl
import subprocess
import sys
import threading
import time
import traceback

import pytest

import OpenSSL.SSL
import requests
import trustme
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.serialization import (
    BestAvailableEncryption,
    Encoding,
    PrivateFormat,
    load_pem_private_key,
)

from cheroot.connections import ConnectionManager
from cheroot.server import HTTPConnection
from cheroot.ssl import (
    Adapter,
    _ensure_peer_speaks_https,
    builtin as builtin_adapter,
)

from .._compat import (
    IS_ABOVE_OPENSSL10,
    IS_ABOVE_OPENSSL31,
    IS_CI,
    IS_LINUX,
    IS_MACOS,
    IS_PYPY,
    IS_WINDOWS,
    bton,
    ntob,
    ntou,
)
from ..server import HTTPServer, get_ssl_adapter_class
from ..testing import (
    ANY_INTERFACE_IPV4,
    ANY_INTERFACE_IPV6,
    EPHEMERAL_PORT,
    # get_server_client,
    _get_conn_data,
    _probe_ipv6_sock,
)
from ..wsgi import Gateway_10


IS_GITHUB_ACTIONS_WORKFLOW = bool(os.getenv('GITHUB_WORKFLOW'))
IS_WIN2016 = (
    IS_WINDOWS
    # pylint: disable=unsupported-membership-test
    and b'Microsoft Windows Server 2016 Datacenter'
    in subprocess.check_output(
        ('systeminfo',),
    )
)
IS_LIBRESSL_BACKEND = ssl.OPENSSL_VERSION.startswith('LibreSSL')
IS_PYOPENSSL_SSL_VERSION_1_0 = OpenSSL.SSL.SSLeay_version(
    OpenSSL.SSL.SSLEAY_VERSION,
).startswith(b'OpenSSL 1.0.')
PY310_PLUS = sys.version_info[:2] >= (3, 10)
PY38_OR_LOWER = sys.version_info[:2] <= (3, 8)

if PY38_OR_LOWER:
    # FIXME: This can be dropped together with Python 3.8.
    # FIXME: It's coming from `trustme < 1.2.0` as newer versions
    # FIXME: fixed the compatibility but dropped Python 3.8 support.
    pytestmark = [
        pytest.mark.filterwarnings(
            r'ignore:Passing pyOpenSSL PKey objects is deprecated\. '
            r'You should use a cryptography private key instead\.:'
            'DeprecationWarning:OpenSSL.SSL',
        ),
        pytest.mark.filterwarnings(
            r'ignore:Passing pyOpenSSL X509 objects is deprecated\. '
            r'You should use a cryptography\.x509\.Certificate instead\.:'
            'DeprecationWarning:OpenSSL.SSL',
        ),
    ]


_stdlib_to_openssl_verify = {
    ssl.CERT_NONE: OpenSSL.SSL.VERIFY_NONE,
    ssl.CERT_OPTIONAL: OpenSSL.SSL.VERIFY_PEER,
    ssl.CERT_REQUIRED: OpenSSL.SSL.VERIFY_PEER
    + OpenSSL.SSL.VERIFY_FAIL_IF_NO_PEER_CERT,
}


missing_ipv6 = pytest.mark.skipif(
    not _probe_ipv6_sock('::1'),
    reason=''
    'IPv6 is disabled '
    '(for example, under Travis CI '
    'which runs under GCE supporting only IPv4)',
)


class HelloWorldGateway(Gateway_10):
    """Gateway responding with Hello World to root URI."""

    def respond(self):
        """Respond with dummy content via HTTP."""
        req = self.req
        req_uri = bton(req.uri)
        if req_uri == '/':
            req.status = b'200 OK'
            req.ensure_headers_sent()
            req.write(b'Hello world!')
            return None
        if req_uri == '/env':
            req.status = b'200 OK'
            req.ensure_headers_sent()
            env = self.get_environ()
            # drop files so that it can be json dumped
            env.pop('wsgi.errors')
            env.pop('wsgi.input')
            print(env)
            req.write(json.dumps(env).encode('utf-8'))
            return None
        return super(HelloWorldGateway, self).respond()


def make_tls_http_server(bind_addr, ssl_adapter, request):
    """Create and start an HTTP server bound to ``bind_addr``."""
    httpserver = HTTPServer(
        bind_addr=bind_addr,
        gateway=HelloWorldGateway,
    )
    # httpserver.gateway = HelloWorldGateway
    httpserver.ssl_adapter = ssl_adapter

    threading.Thread(target=httpserver.safe_start).start()

    while not httpserver.ready:
        time.sleep(0.1)

    request.addfinalizer(httpserver.stop)

    return httpserver


def get_key_password():
    """Return a predefined password string.

    It is to be used for decrypting private keys.
    """
    return 'криївка'


@pytest.fixture(scope='session')
def private_key_password():
    """Provide hardcoded password for private key."""
    return get_key_password()


@pytest.fixture
def tls_http_server(request):
    """Provision a server creator as a fixture."""
    return functools.partial(make_tls_http_server, request=request)


@pytest.fixture
def ca():
    """Provide a certificate authority via fixture."""
    return trustme.CA()


@pytest.fixture
def tls_ca_certificate_pem_path(ca):
    """Provide a certificate authority certificate file via fixture."""
    with ca.cert_pem.tempfile() as ca_cert_pem:
        yield ca_cert_pem


@pytest.fixture
def tls_certificate(ca):
    """Provide a leaf certificate via fixture."""
    interface, _host, _port = _get_conn_data(ANY_INTERFACE_IPV4)
    return ca.issue_cert(ntou(interface))


@pytest.fixture
def tls_certificate_chain_pem_path(tls_certificate):
    """Provide a certificate chain PEM file path via fixture."""
    with tls_certificate.private_key_and_cert_chain_pem.tempfile() as cert_pem:
        yield cert_pem


@pytest.fixture
def tls_certificate_private_key_pem_path(tls_certificate):
    """Provide a certificate private key PEM file path via fixture."""
    with tls_certificate.private_key_pem.tempfile() as cert_key_pem:
        yield cert_key_pem


@pytest.fixture
def tls_certificate_passwd_private_key_pem_path(
    tls_certificate,
    private_key_password,
    tmp_path,
):
    """Return a certificate private key PEM file path."""
    key_as_bytes = tls_certificate.private_key_pem.bytes()
    private_key_object = load_pem_private_key(
        key_as_bytes,
        password=None,
        backend=default_backend(),
    )

    encrypted_key_as_bytes = private_key_object.private_bytes(
        encoding=Encoding.PEM,
        format=PrivateFormat.PKCS8,
        encryption_algorithm=BestAvailableEncryption(
            password=private_key_password.encode('utf-8'),
        ),
    )

    key_file = tmp_path / 'encrypted-private-key.pem'
    key_file.write_bytes(encrypted_key_as_bytes)

    return key_file


def _thread_except_hook(exceptions, args):
    """Append uncaught exception ``args`` in threads to ``exceptions``."""
    if issubclass(args.exc_type, SystemExit):
        return
    # cannot store the exception, it references the thread's stack
    exceptions.append(
        (
            args.exc_type,
            str(args.exc_value),
            ''.join(
                traceback.format_exception(
                    args.exc_type,
                    args.exc_value,
                    args.exc_traceback,
                ),
            ),
        ),
    )


@pytest.fixture
def thread_exceptions():
    """Provide a list of uncaught exceptions from threads via a fixture.

    Only catches exceptions on Python 3.8+.
    The list contains: ``(type, str(value), str(traceback))``
    """
    exceptions = []
    # Python 3.8+
    orig_hook = getattr(threading, 'excepthook', None)
    if orig_hook is not None:
        threading.excepthook = functools.partial(
            _thread_except_hook,
            exceptions,
        )
    try:
        yield exceptions
    finally:
        if orig_hook is not None:
            threading.excepthook = orig_hook


@pytest.mark.parametrize(
    'adapter_type',
    (
        'builtin',
        'pyopenssl',
    ),
)
def test_ssl_adapters(  # pylint: disable=too-many-positional-arguments
    http_request_timeout,
    tls_http_server,
    adapter_type,
    tls_certificate,
    tls_certificate_chain_pem_path,
    tls_certificate_private_key_pem_path,
    tls_ca_certificate_pem_path,
):
    """Test ability to connect to server via HTTPS using adapters."""
    interface, _host, port = _get_conn_data(ANY_INTERFACE_IPV4)
    tls_adapter_cls = get_ssl_adapter_class(name=adapter_type)
    tls_adapter = tls_adapter_cls(
        tls_certificate_chain_pem_path,
        tls_certificate_private_key_pem_path,
    )
    if adapter_type == 'pyopenssl':
        tls_adapter.context = tls_adapter.get_context()

    tls_certificate.configure_cert(tls_adapter.context)

    tlshttpserver = tls_http_server((interface, port), tls_adapter)

    # testclient = get_server_client(tlshttpserver)
    # testclient.get('/')

    interface, _host, port = _get_conn_data(
        tlshttpserver.bind_addr,
    )

    resp = requests.get(
        f'https://{interface!s}:{port!s}/',
        timeout=http_request_timeout,
        verify=tls_ca_certificate_pem_path,
    )

    assert resp.status_code == 200
    assert resp.text == 'Hello world!'


@pytest.mark.parametrize(  # noqa: C901  # FIXME
    'adapter_type',
    (
        'builtin',
        'pyopenssl',
    ),
)
@pytest.mark.parametrize(
    ('is_trusted_cert', 'tls_client_identity'),
    (
        (True, 'localhost'),
        (True, '127.0.0.1'),
        (True, '*.localhost'),
        (True, 'not_localhost'),
        (False, 'localhost'),
    ),
)
@pytest.mark.parametrize(
    'tls_verify_mode',
    (
        ssl.CERT_NONE,  # server shouldn't validate client cert
        ssl.CERT_OPTIONAL,  # same as CERT_REQUIRED in client mode, don't use
        ssl.CERT_REQUIRED,  # server should validate if client cert CA is OK
    ),
)
@pytest.mark.xfail(
    IS_PYPY and IS_CI,
    reason='Fails under PyPy in CI for unknown reason',
    strict=False,
)
# pylint: disable-next=too-many-positional-arguments
def test_tls_client_auth(  # noqa: C901, WPS213  # FIXME
    # FIXME: remove twisted logic, separate tests
    http_request_timeout,
    mocker,
    tls_http_server,
    adapter_type,
    ca,
    tls_certificate,
    tls_certificate_chain_pem_path,
    tls_certificate_private_key_pem_path,
    tls_ca_certificate_pem_path,
    is_trusted_cert,
    tls_client_identity,
    tls_verify_mode,
):
    """Verify that client TLS certificate auth works correctly."""
    test_cert_rejection = (
        tls_verify_mode != ssl.CERT_NONE and not is_trusted_cert
    )
    interface, _host, port = _get_conn_data(ANY_INTERFACE_IPV4)

    client_cert_root_ca = ca if is_trusted_cert else trustme.CA()
    with mocker.mock_module.patch(
        'idna.core.ulabel',
        return_value=ntob(tls_client_identity),
    ):
        client_cert = client_cert_root_ca.issue_cert(
            ntou(tls_client_identity),
        )
        del client_cert_root_ca

    with client_cert.private_key_and_cert_chain_pem.tempfile() as cl_pem:
        tls_adapter_cls = get_ssl_adapter_class(name=adapter_type)
        tls_adapter = tls_adapter_cls(
            tls_certificate_chain_pem_path,
            tls_certificate_private_key_pem_path,
        )
        if adapter_type == 'pyopenssl':
            tls_adapter.context = tls_adapter.get_context()
            tls_adapter.context.set_verify(
                _stdlib_to_openssl_verify[tls_verify_mode],
                lambda conn, cert, errno, depth, preverify_ok: preverify_ok,
            )
        else:
            tls_adapter.context.verify_mode = tls_verify_mode

        ca.configure_trust(tls_adapter.context)
        tls_certificate.configure_cert(tls_adapter.context)

        tlshttpserver = tls_http_server((interface, port), tls_adapter)

        interface, _host, port = _get_conn_data(tlshttpserver.bind_addr)

        make_https_request = functools.partial(
            requests.get,
            f'https://{interface!s}:{port!s}/',
            # Don't wait for the first byte forever:
            timeout=http_request_timeout,
            # Server TLS certificate verification:
            verify=tls_ca_certificate_pem_path,
            # Client TLS certificate verification:
            cert=cl_pem,
        )

        if not test_cert_rejection:
            resp = make_https_request()
            is_req_successful = resp.status_code == 200
            if (
                not is_req_successful
                and IS_PYOPENSSL_SSL_VERSION_1_0
                and adapter_type == 'builtin'
                and tls_verify_mode == ssl.CERT_REQUIRED
                and tls_client_identity == 'localhost'
                and is_trusted_cert
            ):
                pytest.xfail(
                    'OpenSSL 1.0 has problems with verifying client certs',
                )
            assert is_req_successful
            assert resp.text == 'Hello world!'
            resp.close()
            return

        # xfail some flaky tests
        # https://github.com/cherrypy/cheroot/issues/237
        issue_237 = (
            IS_MACOS
            and adapter_type == 'builtin'
            and tls_verify_mode != ssl.CERT_NONE
        )
        if issue_237:
            pytest.xfail('Test sometimes fails')

        expected_ssl_errors = (requests.exceptions.SSLError,)
        if IS_WINDOWS or IS_GITHUB_ACTIONS_WORKFLOW:
            expected_ssl_errors += (requests.exceptions.ConnectionError,)
        with pytest.raises(expected_ssl_errors) as ssl_err:
            make_https_request().close()

        try:
            err_text = ssl_err.value.args[0].reason.args[0].args[0]
        except AttributeError:
            if IS_WINDOWS or IS_GITHUB_ACTIONS_WORKFLOW:
                err_text = str(ssl_err.value)
            else:
                raise

        if isinstance(err_text, int):
            err_text = str(ssl_err.value)

        expected_substrings = (
            'sslv3 alert bad certificate'
            if IS_LIBRESSL_BACKEND
            else 'tlsv1 alert unknown ca',
        )
        if IS_MACOS and IS_PYPY and adapter_type == 'pyopenssl':
            expected_substrings = ('tlsv1 alert unknown ca',)
        if (
            tls_verify_mode
            in {
                ssl.CERT_REQUIRED,
                ssl.CERT_OPTIONAL,
            }
            and not is_trusted_cert
            and tls_client_identity == 'localhost'
        ):
            expected_substrings += (
                (
                    "bad handshake: SysCallError(10054, 'WSAECONNRESET')",
                    "('Connection aborted.', "
                    'OSError("(10054, \'WSAECONNRESET\')"))',
                    "('Connection aborted.', "
                    'OSError("(10054, \'WSAECONNRESET\')",))',
                    "('Connection aborted.', "
                    'error("(10054, \'WSAECONNRESET\')",))',
                    "('Connection aborted.', "
                    'ConnectionResetError(10054, '
                    "'An existing connection was forcibly closed "
                    "by the remote host', None, 10054, None))",
                    "('Connection aborted.', "
                    'error(10054, '
                    "'An existing connection was forcibly closed "
                    "by the remote host'))",
                )
                if IS_WINDOWS
                else (
                    "('Connection aborted.', "
                    'OSError("(104, \'ECONNRESET\')"))',
                    "('Connection aborted.', "
                    'OSError("(104, \'ECONNRESET\')",))',
                    "('Connection aborted.', error(\"(104, 'ECONNRESET')\",))",
                    "('Connection aborted.', "
                    "ConnectionResetError(104, 'Connection reset by peer'))",
                    "('Connection aborted.', "
                    "error(104, 'Connection reset by peer'))",
                )
                if (IS_GITHUB_ACTIONS_WORKFLOW and IS_LINUX)
                else (
                    "('Connection aborted.', "
                    "BrokenPipeError(32, 'Broken pipe'))",
                )
            )

        if PY310_PLUS:
            # FIXME: Figure out what's happening and correct the problem
            expected_substrings += (
                'SSLError(SSLEOFError(8, '
                "'EOF occurred in violation of protocol (_ssl.c:",
            )
        if IS_GITHUB_ACTIONS_WORKFLOW and IS_WINDOWS and PY310_PLUS:
            expected_substrings += (
                "('Connection aborted.', "
                'RemoteDisconnected('
                "'Remote end closed connection without response'))",
            )

        assert any(e in err_text for e in expected_substrings)


@pytest.mark.parametrize(  # noqa: C901  # FIXME
    'adapter_type',
    (
        pytest.param(
            'builtin',
            marks=pytest.mark.xfail(
                IS_MACOS and PY310_PLUS,
                reason='Unclosed TLS resource warnings happen on macOS '
                'under Python 3.10 (#508)',
                strict=False,
            ),
        ),
        'pyopenssl',
    ),
)
@pytest.mark.parametrize(
    ('tls_verify_mode', 'use_client_cert'),
    (
        (ssl.CERT_NONE, False),
        (ssl.CERT_NONE, True),
        (ssl.CERT_OPTIONAL, False),
        (ssl.CERT_OPTIONAL, True),
        (ssl.CERT_REQUIRED, True),
    ),
)
# pylint: disable-next=too-many-positional-arguments
def test_ssl_env(  # noqa: C901  # FIXME
    thread_exceptions,
    recwarn,
    mocker,
    http_request_timeout,
    tls_http_server,
    adapter_type,
    ca,
    tls_verify_mode,
    tls_certificate,
    tls_certificate_chain_pem_path,
    tls_certificate_private_key_pem_path,
    tls_ca_certificate_pem_path,
    use_client_cert,
):
    """Test the SSL environment generated by the SSL adapters."""
    interface, _host, port = _get_conn_data(ANY_INTERFACE_IPV4)

    with mocker.mock_module.patch(
        'idna.core.ulabel',
        return_value=ntob('127.0.0.1'),
    ):
        client_cert = ca.issue_cert(ntou('127.0.0.1'))

    with client_cert.private_key_and_cert_chain_pem.tempfile() as cl_pem:
        tls_adapter_cls = get_ssl_adapter_class(name=adapter_type)
        tls_adapter = tls_adapter_cls(
            tls_certificate_chain_pem_path,
            tls_certificate_private_key_pem_path,
        )
        if adapter_type == 'pyopenssl':
            tls_adapter.context = tls_adapter.get_context()
            tls_adapter.context.set_verify(
                _stdlib_to_openssl_verify[tls_verify_mode],
                lambda conn, cert, errno, depth, preverify_ok: preverify_ok,
            )
        else:
            tls_adapter.context.verify_mode = tls_verify_mode

        ca.configure_trust(tls_adapter.context)
        tls_certificate.configure_cert(tls_adapter.context)

        tlswsgiserver = tls_http_server((interface, port), tls_adapter)

        interface, _host, port = _get_conn_data(tlswsgiserver.bind_addr)

        resp = requests.get(
            'https://' + interface + ':' + str(port) + '/env',
            timeout=http_request_timeout,
            verify=tls_ca_certificate_pem_path,
            cert=cl_pem if use_client_cert else None,
        )

        env = json.loads(resp.content.decode('utf-8'))

        # hard coded env
        assert env['wsgi.url_scheme'] == 'https'
        assert env['HTTPS'] == 'on'

        # ensure these are present
        for key in 'SSL_VERSION_INTERFACE', 'SSL_VERSION_LIBRARY':
            assert key in env

        # pyOpenSSL generates the env before the handshake completes
        if adapter_type == 'pyopenssl':
            return

        for key in 'SSL_PROTOCOL', 'SSL_CIPHER':
            assert key in env

        # client certificate env
        if tls_verify_mode == ssl.CERT_NONE or not use_client_cert:
            assert env['SSL_CLIENT_VERIFY'] == 'NONE'
        else:
            assert env['SSL_CLIENT_VERIFY'] == 'SUCCESS'

            with open(cl_pem) as f:
                assert env['SSL_CLIENT_CERT'] in f.read()

            for key in (
                'SSL_CLIENT_M_VERSION',
                'SSL_CLIENT_M_SERIAL',
                'SSL_CLIENT_I_DN',
                'SSL_CLIENT_S_DN',
            ):
                assert key in env

    # builtin ssl environment generation may use a loopback socket
    # ensure no ResourceWarning was raised during the test
    if IS_PYPY:
        # NOTE: PyPy doesn't have ResourceWarning
        # Ref: https://doc.pypy.org/en/latest/cpython_differences.html
        return
    for warn in recwarn:
        if not issubclass(warn.category, ResourceWarning):
            continue

        # the tests can sporadically generate resource warnings
        # due to timing issues
        # all of these sporadic warnings appear to be about socket.socket
        # and have been observed to come from requests connection pool
        msg = str(warn.message)
        if 'socket.socket' in msg:
            pytest.xfail(
                '\n'.join(
                    (
                        'Sometimes this test fails due to '
                        'a socket.socket ResourceWarning:',
                        msg,
                    ),
                ),
            )
        pytest.fail(msg)

    # to perform the ssl handshake over that loopback socket,
    # the builtin ssl environment generation uses a thread
    for _, _, trace in thread_exceptions:
        print(trace, file=sys.stderr)
    assert not thread_exceptions, ': '.join(
        (
            thread_exceptions[0][0].__name__,
            thread_exceptions[0][1],
        ),
    )


@pytest.mark.parametrize(
    'ip_addr',
    (
        ANY_INTERFACE_IPV4,
        ANY_INTERFACE_IPV6,
    ),
)
def test_https_over_http_error(http_server, ip_addr):
    """Ensure that connecting over HTTPS to HTTP port is handled."""
    httpserver = http_server.send((ip_addr, EPHEMERAL_PORT))
    interface, _host, port = _get_conn_data(httpserver.bind_addr)
    with pytest.raises(ssl.SSLError) as ssl_err:
        http.client.HTTPSConnection(
            f'{interface}:{port}',
        ).request('GET', '/')
    expected_substring = (
        'record layer failure'
        if IS_ABOVE_OPENSSL31
        else 'wrong version number'
        if IS_ABOVE_OPENSSL10
        else 'unknown protocol'
    )
    assert expected_substring in ssl_err.value.args[-1]


def test_http_over_https_no_data(mocker):
    """Test ``_ensure_peer_speaks_https()`` handles empty peek correctly."""
    mock_socket = mocker.Mock(spec=socket.socket)
    mock_socket.recv.return_value = b''  # Empty peek
    mock_socket.gettimeout.return_value = None

    # Should not raise - empty peek means we can't detect plain HTTP
    _ensure_peer_speaks_https(mock_socket)

    mock_socket.recv.assert_called_once_with(16, socket.MSG_PEEK)


@pytest.mark.parametrize(
    'exception',
    (
        socket.timeout('Timed out'),
        ConnectionResetError(errno.ECONNRESET, 'Connection reset by peer'),
    ),
    ids=('timeout', 'connection_reset'),
)
def test_http_over_https_check_socket_errors(
    exception,
    mocker,
):
    """Test ``_ensure_peer_speaks_https()`` handles socket errors gracefully."""
    mock_socket = mocker.Mock(spec=socket.socket)
    mock_socket.gettimeout.return_value = None
    mock_socket.recv.side_effect = exception
    mocked_sock_recv_spy = mocker.spy(mock_socket, 'recv')

    # socket errors should be suppressed
    _ensure_peer_speaks_https(mock_socket)
    assert mocked_sock_recv_spy.spy_exception is exception
    mocked_sock_recv_spy.assert_called_once()


@pytest.mark.parametrize(
    'adapter_type',
    (
        'builtin',
        'pyopenssl',
    ),
)
@pytest.mark.parametrize(
    'ip_addr',
    (
        ANY_INTERFACE_IPV4,
        pytest.param(ANY_INTERFACE_IPV6, marks=missing_ipv6),
    ),
)
# pylint: disable-next=too-many-positional-arguments
def test_http_over_https_error(
    http_request_timeout,
    tls_http_server,
    adapter_type,
    ca,
    ip_addr,
    tls_certificate,
    tls_certificate_chain_pem_path,
    tls_certificate_private_key_pem_path,
):
    """Ensure that connecting over HTTP to HTTPS port is handled."""
    tls_adapter_cls = get_ssl_adapter_class(name=adapter_type)
    tls_adapter = tls_adapter_cls(
        tls_certificate_chain_pem_path,
        tls_certificate_private_key_pem_path,
    )

    tls_certificate.configure_cert(tls_adapter.context)

    interface, _host, port = _get_conn_data(ip_addr)
    tlshttpserver = tls_http_server((interface, port), tls_adapter)

    interface, _host, port = _get_conn_data(
        tlshttpserver.bind_addr,
    )

    fqdn = interface
    if ip_addr is ANY_INTERFACE_IPV6:
        fqdn = '[{fqdn}]'.format(**locals())

    resp = requests.get(
        f'http://{fqdn!s}:{port!s}/',
        timeout=http_request_timeout,
    )
    assert resp.status_code == 400
    assert resp.text == (
        'The client sent a plain HTTP request, '
        'but this server only speaks HTTPS on this port.'
    )


@pytest.mark.parametrize(
    ('error', 'raising_expectation'),
    (
        (
            BrokenPipeError(errno.EPIPE, 'Broken pipe'),
            contextlib.nullcontext(),
        ),
        (
            OSError(9999, 'An error to reckon with'),
            pytest.raises(OSError, match=r'An error to reckon with'),
        ),
    ),
    ids=('error-suppressed', 'error-propagates'),
)
def test_send_bad_request_socket_errors(
    mocker,
    error,
    raising_expectation,
):
    """Test socket error handling when sending 400 Bad Request."""
    # Mock the selector in ConnectionManager initialization
    mocker.patch('cheroot.connections._ThreadsafeSelector', autospec=True)

    mock_server = mocker.Mock(spec=HTTPServer)
    mock_server.protocol = 'HTTP/1.1'
    mock_server.socket = mocker.Mock(spec=socket.socket)
    conn_manager = ConnectionManager(mock_server)

    mock_raw_socket = mocker.Mock(spec=socket.socket)
    mock_raw_socket.sendall.side_effect = error

    with raising_expectation as exc_info:
        conn_manager._send_bad_request_plain_http_error(
            mock_raw_socket,
        )

    # If we expect an error, check it's the correct one
    should_propagate = not isinstance(
        raising_expectation,
        contextlib.nullcontext,
    )
    if should_propagate:
        assert exc_info.value is error

    mock_raw_socket.sendall.assert_called_once()
    mock_raw_socket.close.assert_called_once()


@pytest.mark.parametrize('adapter_type', ('builtin', 'pyopenssl'))
# pylint: disable-next=too-many-positional-arguments
def test_http_over_https_ssl_handshake(
    mocker,
    tls_http_server,
    adapter_type,
    tls_certificate,
    tls_certificate_chain_pem_path,
    tls_certificate_private_key_pem_path,
):
    """
    Test NoSSLError raised when SSL handshake catches HTTP.

    Normally the early probe ``_ensure_peer_speaks_https()``
    will detect a client attempting to speak HTTP on a TLS
    port but if this times out or fails for some reason, SSL
    should raise an error at the time of the handshake. Here
    we test the error is caught and triggers the emission of
    a ``400 Bad Request``.
    """
    interface, _host, port = _get_conn_data(ANY_INTERFACE_IPV4)

    tls_adapter_cls = get_ssl_adapter_class(name=adapter_type)
    tls_adapter = tls_adapter_cls(
        tls_certificate_chain_pem_path,
        tls_certificate_private_key_pem_path,
    )

    tls_certificate.configure_cert(tls_adapter.context)

    # Mock the early probe to not detect the HTTP request
    mocker.patch('cheroot.ssl._ensure_peer_speaks_https', autospec=True)

    tlshttpserver = tls_http_server((interface, port), tls_adapter)

    interface, _host, port = _get_conn_data(tlshttpserver.bind_addr)

    # Send plain HTTP
    with socket.create_connection((interface, port)) as sock:
        BUFFER_SIZE = 256
        sock.sendall(b'GET / HTTP/1.1\r\nHost: localhost\r\n\r\n')

        if adapter_type == 'pyopenssl':
            # pyopenssl can send the 400 response
            response = sock.recv(BUFFER_SIZE)
            assert b'400 Bad Request' in response
        else:
            # builtin adapter: connection closed before 400 can be sent
            with pytest.raises(
                ConnectionError,
            ):
                sock.recv(1)


@pytest.mark.parametrize('adapter_type', ('builtin', 'pyopenssl'))
@pytest.mark.parametrize(
    'encrypted_key',
    (True, False),
    ids=('encrypted-key', 'unencrypted-key'),
)
@pytest.mark.parametrize(
    'transform_password_arg',
    (
        lambda pass_factory: pass_factory().encode('utf-8'),
        lambda pass_factory: pass_factory(),
        lambda pass_factory: pass_factory,
    ),
    ids=(
        'with-bytes-password',
        'with-str-password',
        'with-callable-password-provider',
    ),
)
# pylint: disable-next=too-many-positional-arguments
def test_ssl_adapters_with_private_key_password(
    http_request_timeout,
    private_key_password,
    tls_http_server,
    tls_ca_certificate_pem_path,
    tls_certificate_chain_pem_path,
    tls_certificate_passwd_private_key_pem_path,
    tls_certificate_private_key_pem_path,
    adapter_type,
    encrypted_key,
    transform_password_arg,
):
    """Check server decrypts private TLS keys with password as bytes or str."""
    key_file = (
        tls_certificate_passwd_private_key_pem_path
        if encrypted_key
        else tls_certificate_private_key_pem_path
    )
    private_key_password = transform_password_arg(get_key_password)

    tls_adapter_cls = get_ssl_adapter_class(name=adapter_type)
    tls_adapter = tls_adapter_cls(
        certificate=tls_certificate_chain_pem_path,
        private_key=key_file,
        private_key_password=private_key_password,
    )

    interface, _host, port = _get_conn_data(
        tls_http_server(
            (ANY_INTERFACE_IPV4, EPHEMERAL_PORT),
            tls_adapter,
        ).bind_addr,
    )

    resp = requests.get(
        f'https://{interface!s}:{port!s}/',
        timeout=http_request_timeout,
        verify=tls_ca_certificate_pem_path,
    )

    assert resp.status_code == 200
    assert resp.text == 'Hello world!'


@pytest.mark.parametrize(
    'adapter_type',
    ('builtin',),
)
def test_builtin_adapter_with_false_key_password(
    tls_certificate_chain_pem_path,
    tls_certificate_passwd_private_key_pem_path,
    adapter_type,
):
    """Check that builtin ssl-adapter initialization fails when wrong private key password given."""
    tls_adapter_cls = get_ssl_adapter_class(name=adapter_type)
    with pytest.raises(ssl.SSLError, match=r'^\[SSL\] PEM.+'):
        tls_adapter_cls(
            certificate=tls_certificate_chain_pem_path,
            private_key=tls_certificate_passwd_private_key_pem_path,
            private_key_password='x' * 256,
        )


@pytest.mark.parametrize(
    ('adapter_type', 'false_password', 'expected_warn'),
    (
        (
            'pyopenssl',
            '837550fd-bcb9-4320-87e6-09de6456b09',
            contextlib.nullcontext(),
        ),
        ('pyopenssl', 555555, contextlib.nullcontext()),
        (
            'pyopenssl',
            '@' * 2048,
            pytest.warns(
                UserWarning,
                match=r'^User-provided password is 2048 bytes.+',
            ),
        ),
    ),
    ids=('incorrect-password', 'integer-password', 'too-long-password'),
)
def test_openssl_adapter_with_false_key_password(
    tls_certificate_chain_pem_path,
    tls_certificate_passwd_private_key_pem_path,
    adapter_type,
    false_password,
    expected_warn,
):
    """Check that server init fails when wrong private key password given."""
    tls_adapter_cls = get_ssl_adapter_class(name=adapter_type)
    with expected_warn, pytest.raises(
        OpenSSL.SSL.Error,
        # Decode error has happened very rarely with Python 3.9 in MacOS.
        # Might be caused by a random issue in file handling leading
        # to interpretation of garbage characters in certificates.
        match=r'.+\'(bad decrypt|decode error)\'.+',
    ):
        tls_adapter_cls(
            certificate=tls_certificate_chain_pem_path,
            private_key=tls_certificate_passwd_private_key_pem_path,
            private_key_password=false_password,
        )


@pytest.mark.parametrize(
    'adapter_type',
    ('pyopenssl', 'builtin'),
)
def test_ssl_adapter_with_none_key_password(
    tls_certificate_chain_pem_path,
    tls_certificate_passwd_private_key_pem_path,
    private_key_password,
    adapter_type,
    mocker,
):
    """Check that TLS-adapters prompt for password when set as ``None``."""
    tls_adapter_cls = get_ssl_adapter_class(name=adapter_type)
    mocker.patch(
        'cheroot.ssl._ask_for_password_interactively',
        return_value=private_key_password,
    )
    tls_adapter = tls_adapter_cls(
        certificate=tls_certificate_chain_pem_path,
        private_key=tls_certificate_passwd_private_key_pem_path,
    )

    assert tls_adapter.context is not None


class PasswordCallbackHelper:
    """Collects helper methods for mocking password callback."""

    def __init__(self, adapter: Adapter):
        """Initialize helper variables."""
        self.counter = 0
        self.callback = adapter._password_callback

    def get_password(self):
        """Provide correct password on first call, wrong on other calls."""
        self.counter += 1
        return get_key_password() * self.counter

    def verify_twice_callback(self, max_length, _verify_twice, userdata):
        """Establish a mock callback for testing two-factor password prompt."""
        return self.callback(self, max_length, True, userdata)


@pytest.mark.parametrize('adapter_type', ('pyopenssl',))
def test_openssl_adapter_verify_twice_callback(
    tls_certificate_chain_pem_path,
    tls_certificate_passwd_private_key_pem_path,
    adapter_type,
    mocker,
):
    """Check that two-time password verification fails with correct error."""
    tls_adapter_cls = get_ssl_adapter_class(name=adapter_type)
    helper = PasswordCallbackHelper(tls_adapter_cls)

    mocker.patch(
        'cheroot.ssl.pyopenssl.pyOpenSSLAdapter._password_callback',
        side_effect=helper.verify_twice_callback,
    )

    with pytest.raises(
        ValueError,
        match='Verification failed: entered passwords do not match',
    ):
        tls_adapter_cls(
            certificate=tls_certificate_chain_pem_path,
            private_key=tls_certificate_passwd_private_key_pem_path,
            private_key_password=helper.get_password,
        )


@pytest.fixture
def dummy_adapter(monkeypatch):
    """Provide a dummy SSL adapter instance."""
    # hide abstract methods so we can instantiate Adapter
    monkeypatch.setattr(Adapter, '__abstractmethods__', set())
    # pylint: disable=abstract-class-instantiated
    return Adapter(
        certificate='cert.pem',
        private_key='key.pem',
    )


def test_bind_deprecated_call(dummy_adapter):
    """Test deprecated ``bind()`` method issues warning and returns socket."""
    sock = socket.socket()

    with pytest.deprecated_call():
        result = dummy_adapter.bind(sock)

    assert result is sock

    sock.close()


def test_prepare_socket_emits_deprecation_warning(
    dummy_adapter,
):
    """
    Test ``prepare_socket()`` deprecated argument triggers a warning.

    ``ssl_adapter`` has been deprecated in ``HTTPServer.prepare_socket()``.
    """
    # Required parameters for prepare_socket (standard IPv4 TCP config)
    bind_addr = ('127.0.0.1', 8080)
    family = socket.AF_INET
    sock_type = socket.SOCK_STREAM
    proto = socket.IPPROTO_TCP
    nodelay = True

    expected_message = r'ssl_adapter.*deprecated'  # regex pattern

    with pytest.deprecated_call(match=expected_message):
        sock = HTTPServer.prepare_socket(
            bind_addr=bind_addr,
            family=family,
            type=sock_type,
            proto=proto,
            nodelay=nodelay,
            ssl_adapter=dummy_adapter,
        )

    # Check that the returned object is indeed a socket
    assert isinstance(sock, socket.socket)
    # Check we have a socket configured with file descriptor
    assert sock.fileno() > 0

    sock.close()


def test_httpconnection_makefile_deprecation(mocker):
    """
    Test ``makefile`` argument on ``HTTPConnection`` triggers a warning.

    ``makefile`` is now deprecated.
    """
    dummy_server = mocker.create_autospec(HTTPServer, instance=True)
    dummy_sock = mocker.create_autospec(socket.socket, instance=True)

    # Value for the deprecated 'makefile' parameter
    dummy_makefile_value = object()

    expected_message = r'makefile.*deprecated'

    # Act & Assert
    with pytest.deprecated_call(match=expected_message):
        # Instantiate HTTPConnection, passing the deprecated 'makefile'
        conn = HTTPConnection(
            server=dummy_server,
            sock=dummy_sock,
            makefile=dummy_makefile_value,  # This triggers the warning
        )

    # Verify assignment
    assert conn.server is dummy_server
    assert conn.socket is dummy_sock


@pytest.mark.parametrize(
    'adapter_type',
    (
        'builtin',
        'pyopenssl',
    ),
)
def test_adapter_makefile_deprecation(
    mocker,
    adapter_type,
    tls_certificate_chain_pem_path,
    tls_certificate_private_key_pem_path,
):
    """Test the adapter's makefile() method emits a deprecation warning."""
    # Mock the adapter
    tls_adapter_cls = get_ssl_adapter_class(name=adapter_type)
    tls_adapter = tls_adapter_cls(
        tls_certificate_chain_pem_path,
        tls_certificate_private_key_pem_path,
    )

    # Create a mock socket with a makefile method
    dummy_sock = mocker.Mock()
    mock_file_stream = mocker.Mock(spec=io.FileIO)
    dummy_sock.makefile.return_value = mock_file_stream

    expected_message = r'makefile.*deprecated'

    # Act & Assert
    with pytest.deprecated_call(match=expected_message):
        result = tls_adapter.makefile(dummy_sock, mode='r', bufsize=8192)

    # Assert 1: The correct delegation happened
    dummy_sock.makefile.assert_called_once_with('r', 8192)

    # Assert 2: The result is the mock file stream
    assert result is mock_file_stream


def test_default_buffer_size_deprecated():
    """Test accessing ``DEFAULT_BUFFER_SIZE`` raises warning."""
    with pytest.warns(
        DeprecationWarning,
        match='`DEFAULT_BUFFER_SIZE` is deprecated',
    ):
        val = builtin_adapter.DEFAULT_BUFFER_SIZE

    # Check that the returned value is correct
    assert val == io.DEFAULT_BUFFER_SIZE, 'DEFAULT_BUFFER_SIZE value mismatch'
