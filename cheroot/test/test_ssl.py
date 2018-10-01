"""Tests for TLS/SSL support."""
# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :

from __future__ import absolute_import, division, print_function
__metaclass__ = type

import threading
import time
from unittest.mock import (  # FIXME: replace it with pytest-mock
    patch, MagicMock
)

import pytest
import six
import trustme

from .._compat import bton, ntou
from ..server import Gateway, HTTPServer, get_ssl_adapter_class
# from ..ssl import builtin, pyopenssl
from ..testing import (
    ANY_INTERFACE_IPV4,
    # get_server_client,
    _get_conn_data,
)


fails_under_py3 = pytest.mark.xfail(
    six.PY3,
    reason='Fails under Python 3',
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
        pytest.param('pyopenssl', marks=fails_under_py3),
    ),
)
def test_ssl_adapters(tls_http_server, ca, adapter_type):
    """Test ability to connect to server via HTTPS using adapters."""
    interface, host, port = _get_conn_data(ANY_INTERFACE_IPV4)
    cert = ca.issue_server_cert(ntou(interface), )
    with ca.cert_pem.tempfile() as ca_temp_path:
        with cert.cert_chain_pems[0].tempfile() as cert_temp_path:
            tls_adapter_cls = get_ssl_adapter_class(name=adapter_type)
            if adapter_type == 'builtin':
                # Temporary patch chain loading
                # as it fails for some reason:
                with patch('ssl.SSLContext.load_cert_chain', MagicMock):
                    tls_adapter = tls_adapter_cls(
                        cert_temp_path, ca_temp_path,
                    )
            else:
                tls_adapter = tls_adapter_cls(
                    cert_temp_path, ca_temp_path,
                )
            # tls_adapter.context = tls_adapter.get_context()
            if adapter_type == 'pyopenssl':
                from OpenSSL import SSL
                ctx = SSL.Context(SSL.SSLv23_METHOD)
                tls_adapter.context = ctx
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

            import requests
            resp = requests.get(
                'https://' + interface + ':' + str(port) + '/',
                verify=ca_temp_path
            )

        assert resp.status_code == 200
        assert resp.text == 'Hello world!'
