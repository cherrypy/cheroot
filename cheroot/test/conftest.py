"""Pytest configuration module.

Contains fixtures, which are tightly bound to the Cheroot framework
itself, useless for end-users' app testing.
"""

import threading
import time

import pytest

import trustme
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.serialization import (
    BestAvailableEncryption,
    Encoding,
    PrivateFormat,
    load_pem_private_key,
)

from .._compat import IS_MACOS, IS_WINDOWS, ntou
from ..server import Gateway, HTTPServer
from ..testing import (  # noqa: F401  # pylint: disable=unused-import
    ANY_INTERFACE_IPV4,
    _get_conn_data,
    get_server_client,
    native_server,
    thread_and_native_server,
    thread_and_wsgi_server,
    wsgi_server,
)


@pytest.fixture
def http_request_timeout():
    """Return a common HTTP request timeout for tests with queries."""
    computed_timeout = 0.5

    if IS_MACOS:
        computed_timeout *= 2

    if IS_WINDOWS:
        computed_timeout *= 10

    return computed_timeout


@pytest.fixture
# pylint: disable=redefined-outer-name
def wsgi_server_thread(thread_and_wsgi_server):  # noqa: F811
    """Set up and tear down a Cheroot WSGI server instance.

    This exposes the server thread.
    """
    server_thread, _srv = thread_and_wsgi_server
    return server_thread


@pytest.fixture
# pylint: disable=redefined-outer-name
def native_server_thread(thread_and_native_server):  # noqa: F811
    """Set up and tear down a Cheroot HTTP server instance.

    This exposes the server thread.
    """
    server_thread, _srv = thread_and_native_server
    return server_thread


@pytest.fixture
# pylint: disable=redefined-outer-name
def wsgi_server_client(wsgi_server):  # noqa: F811
    """Create a test client out of given WSGI server."""
    return get_server_client(wsgi_server)


@pytest.fixture
# pylint: disable=redefined-outer-name
def native_server_client(native_server):  # noqa: F811
    """Create a test client out of given HTTP server."""
    return get_server_client(native_server)


@pytest.fixture
def http_server():
    """Provision a server creator as a fixture."""

    def start_srv():
        bind_addr = yield
        if bind_addr is None:
            return
        httpserver = make_http_server(bind_addr)
        yield httpserver
        yield httpserver

    srv_creator = iter(start_srv())
    next(srv_creator)  # pylint: disable=stop-iteration-return
    yield srv_creator
    try:
        while True:
            httpserver = next(srv_creator)
            if httpserver is not None:
                httpserver.stop()
    except StopIteration:
        pass


def make_http_server(bind_addr):
    """Create and start an HTTP server bound to ``bind_addr``."""
    httpserver = HTTPServer(
        bind_addr=bind_addr,
        gateway=Gateway,
    )

    threading.Thread(target=httpserver.safe_start).start()

    while not httpserver.ready:
        time.sleep(0.1)

    return httpserver


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
    """
    Generate a TLS server certificate for testing.

    Creates a certificate valid for 'test-server.local', 'localhost',
    and '127.0.0.1' with ``CN=localhost``.
    """
    interface, _host, _port = _get_conn_data(ANY_INTERFACE_IPV4)
    identities = [
        'test-server.local',
        'localhost',  # This will be used for CN and SAN
        ntou(interface),  # This is '127.0.0.1' for SAN
    ]
    return ca.issue_server_cert(*identities, common_name='localhost')


@pytest.fixture
def tls_certificate_pem_path(tls_certificate):
    """
    Return path to temp file containing the server certificate in PEM format.

    The file is automatically cleaned up after the test completes.
    """
    # The 'cert_pem' property holds the leaf certificate data.
    leaf_cert_blob = tls_certificate.cert_chain_pems[0]

    # Write to a file that persists for the test duration
    with leaf_cert_blob.tempfile() as cert_pem_path:
        yield cert_pem_path


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
