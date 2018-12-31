"""Tests for TLS/SSL support."""
# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :

from __future__ import absolute_import, division, print_function
__metaclass__ = type

import functools
import ssl
import sys
import threading
import time

import OpenSSL.SSL
import pytest
import requests
import six
import trustme

from .._compat import bton, ntob, ntou
from .._compat import IS_ABOVE_OPENSSL10, IS_PYPY
from .._compat import IS_LINUX, IS_MACOS, IS_WINDOWS
from ..server import Gateway, HTTPServer, get_ssl_adapter_class
from ..testing import (
    ANY_INTERFACE_IPV4,
    ANY_INTERFACE_IPV6,
    EPHEMERAL_PORT,
    # get_server_client,
    _get_conn_data,
)


IS_LIBRESSL_BACKEND = ssl.OPENSSL_VERSION.startswith('LibreSSL')
PY27 = sys.version_info[:2] == (2, 7)


_stdlib_to_openssl_verify = {
    ssl.CERT_NONE: OpenSSL.SSL.VERIFY_NONE,
    ssl.CERT_OPTIONAL: OpenSSL.SSL.VERIFY_PEER,
    ssl.CERT_REQUIRED:
        OpenSSL.SSL.VERIFY_PEER + OpenSSL.SSL.VERIFY_FAIL_IF_NO_PEER_CERT,
}


fails_under_py3 = pytest.mark.xfail(
    six.PY3,
    reason='Fails under Python 3',
)


fails_under_py3_in_pypy = pytest.mark.xfail(
    six.PY3 and IS_PYPY,
    reason='Fails under PyPy3',
)


class HelloWorldGateway(Gateway):
    """Gateway responding with Hello World to root URI."""

    def respond(self):
        """Respond with dummy content via HTTP."""
        req = self.req
        req_uri = bton(req.uri)
        if req_uri == '/':
            req.status = b'200 OK'
            req.ensure_headers_sent()
            req.write(b'Hello world!')
            return
        return super(HelloWorldGateway, self).respond()


def make_tls_http_server(bind_addr, ssl_adapter):
    """Create and start an HTTP server bound to bind_addr."""
    httpserver = HTTPServer(
        bind_addr=bind_addr,
        gateway=HelloWorldGateway,
    )
    # httpserver.gateway = HelloWorldGateway
    httpserver.ssl_adapter = ssl_adapter

    threading.Thread(target=httpserver.safe_start).start()

    while not httpserver.ready:
        time.sleep(0.1)

    return httpserver


@pytest.fixture
def tls_http_server():
    """Provision a server creator as a fixture."""
    def start_srv():
        bind_addr, ssl_adapter = yield
        httpserver = make_tls_http_server(bind_addr, ssl_adapter)
        yield httpserver
        yield httpserver

    srv_creator = iter(start_srv())
    next(srv_creator)
    yield srv_creator
    try:
        while True:
            httpserver = next(srv_creator)
            if httpserver is not None:
                httpserver.stop()
    except StopIteration:
        pass


@pytest.fixture
def ca():
    """Provide a certificate authority via fixture."""
    ca = trustme.CA()
    yield ca
    del ca


@pytest.mark.parametrize(
    'adapter_type',
    (
        'builtin',
        'pyopenssl',
    ),
)
def test_ssl_adapters(tls_http_server, ca, adapter_type):
    """Test ability to connect to server via HTTPS using adapters."""
    interface, host, port = _get_conn_data(ANY_INTERFACE_IPV4)
    cert = ca.issue_server_cert(ntou(interface), )
    with \
            ca.cert_pem.tempfile() as ca_temp_path, \
            cert.private_key_and_cert_chain_pem.tempfile() as cert_pem:
        tls_adapter_cls = get_ssl_adapter_class(name=adapter_type)
        tls_adapter = tls_adapter_cls(
            cert_pem, cert_pem,
        )
        if adapter_type == 'pyopenssl':
            tls_adapter.context = tls_adapter.get_context()

        cert.configure_cert(tls_adapter.context)

        tlshttpserver = tls_http_server.send(
            (
                (interface, port),
                tls_adapter,
            )
        )

        # testclient = get_server_client(tlshttpserver)
        # testclient.get('/')

        interface, host, port = _get_conn_data(
            tlshttpserver.bind_addr
        )

        resp = requests.get(
            'https://' + interface + ':' + str(port) + '/',
            verify=ca_temp_path
        )

    assert resp.status_code == 200
    assert resp.text == 'Hello world!'


@pytest.mark.parametrize(
    'adapter_type',
    (
        'builtin',
        'pyopenssl',
    ),
)
@pytest.mark.parametrize(
    'is_trusted_cert,tls_client_identity',
    (
        (True, 'localhost'), (True, '127.0.0.1'),
        (True, '*.localhost'), (True, 'not_localhost'),
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
def test_tls_client_auth(
        # FIXME: remove twisted logic, separate tests
        mocker,
        tls_http_server, ca,
        adapter_type,
        is_trusted_cert, tls_client_identity,
        tls_verify_mode,
):
    """Verify that client TLS certificate auth works correctly."""
    test_cert_rejection = (
        tls_verify_mode != ssl.CERT_NONE
        and not is_trusted_cert
    )
    interface, host, port = _get_conn_data(ANY_INTERFACE_IPV4)
    cert = ca.issue_server_cert(ntou(interface), )

    client_cert_root_ca = ca if is_trusted_cert else trustme.CA()
    with mocker.mock_module.patch(
        'idna.core.ulabel',
        return_value=ntob(tls_client_identity),
    ):
        client_cert = client_cert_root_ca.issue_server_cert(
            # FIXME: change to issue_cert once new trustme is out
            ntou(tls_client_identity),
        )
        del client_cert_root_ca

    with \
            ca.cert_pem.tempfile() as ca_temp_path, \
            cert.private_key_and_cert_chain_pem.tempfile() as cert_pem, \
            client_cert.private_key_and_cert_chain_pem.tempfile() as cl_pem:
        tls_adapter_cls = get_ssl_adapter_class(name=adapter_type)
        tls_adapter = tls_adapter_cls(
            cert_pem, cert_pem,
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
        cert.configure_cert(tls_adapter.context)

        tlshttpserver = tls_http_server.send(
            (
                (interface, port),
                tls_adapter,
            )
        )

        interface, host, port = _get_conn_data(tlshttpserver.bind_addr)

        make_https_request = functools.partial(
            requests.get,
            'https://' + interface + ':' + str(port) + '/',

            # Server TLS certificate verification:
            verify=ca_temp_path,

            # Client TLS certificate verification:
            cert=cl_pem,
        )

        if not test_cert_rejection:
            resp = make_https_request()
            assert resp.status_code == 200
            assert resp.text == 'Hello world!'
            return

        with pytest.raises(requests.exceptions.SSLError) as ssl_err:
            make_https_request()

        err_text = ssl_err.value.args[0].reason.args[0].args[0]

        expected_substring = (
            'sslv3 alert bad certificate' if IS_LIBRESSL_BACKEND
            else 'tlsv1 alert unknown ca'
        )
        if IS_PYPY and six.PY3 and IS_MACOS and adapter_type == 'pyopenssl':
            expected_substring = 'tlsv1 alert unknown ca'
        assert expected_substring in err_text


@pytest.mark.parametrize(
    'ip_addr',
    (
        ANY_INTERFACE_IPV4,
        ANY_INTERFACE_IPV6,
    )
)
def test_https_over_http_error(http_server, ip_addr):
    """Ensure that connecting over HTTPS to HTTP port is handled."""
    httpserver = http_server.send((ip_addr, EPHEMERAL_PORT))
    interface, host, port = _get_conn_data(httpserver.bind_addr)
    with pytest.raises(ssl.SSLError) as ssl_err:
        six.moves.http_client.HTTPSConnection(
            '{interface}:{port}'.format(
                interface=interface,
                port=port,
            )
        ).request('GET', '/')
    expected_substring = (
        'wrong version number' if IS_ABOVE_OPENSSL10
        else 'unknown protocol'
    )
    assert expected_substring in ssl_err.value.args[-1]


@pytest.mark.parametrize(
    'adapter_type',
    (
        'builtin',
        pytest.param('pyopenssl', marks=fails_under_py3_in_pypy),
    ),
)
@pytest.mark.parametrize(
    'ip_addr',
    (
        ANY_INTERFACE_IPV4,
        ANY_INTERFACE_IPV6,
    )
)
def test_http_over_https_error(ca, adapter_type, tls_http_server, ip_addr):
    """Ensure that connecting over HTTP to HTTPS port is handled."""
    interface, host, port = _get_conn_data(ip_addr)
    cert = ca.issue_server_cert(ntou(interface), )

    with cert.private_key_and_cert_chain_pem.tempfile() as cert_pem:
        tls_adapter_cls = get_ssl_adapter_class(name=adapter_type)
        tls_adapter = tls_adapter_cls(
            cert_pem, cert_pem,
        )
        if adapter_type == 'pyopenssl':
            tls_adapter.context = tls_adapter.get_context()

        cert.configure_cert(tls_adapter.context)

        tlshttpserver = tls_http_server.send(
            (
                (interface, port),
                tls_adapter,
            )
        )

        interface, host, port = _get_conn_data(
            tlshttpserver.bind_addr
        )

        fqdn = interface
        if ip_addr is ANY_INTERFACE_IPV6:
            fqdn = '[{}]'.format(fqdn)

        expect_fallback_response_over_plain_http = (
            (adapter_type == 'pyopenssl'
             and (IS_ABOVE_OPENSSL10 or six.PY3))
            or PY27
        )
        if expect_fallback_response_over_plain_http:
            resp = requests.get(
                'http://' + fqdn + ':' + str(port) + '/',
            )
            assert resp.status_code == 400
            assert resp.text == (
                'The client sent a plain HTTP request, '
                'but this server only speaks HTTPS on this port.'
            )
            return

        with pytest.raises(requests.exceptions.ConnectionError) as ssl_err:
            requests.get(  # FIXME: make stdlib ssl behave like PyOpenSSL
                'http://' + fqdn + ':' + str(port) + '/',
            )

    if IS_LINUX:
        expected_error_code, expected_error_text = (
            104, 'Connection reset by peer',
        )
    if IS_MACOS:
        expected_error_code, expected_error_text = (
            54, 'Connection reset by peer',
        )
    if IS_WINDOWS:
        expected_error_code, expected_error_text = (
            10054,
            'An existing connection was forcibly closed by the remote host',
        )

    underlying_error = ssl_err.value.args[0].args[-1]
    err_text = str(underlying_error)
    assert underlying_error.errno == expected_error_code
    assert expected_error_text in err_text
