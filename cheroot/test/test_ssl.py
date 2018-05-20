"""Tests for the HTTP server."""
# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :

from __future__ import absolute_import, division, print_function
__metaclass__ = type

import threading
import time
from unittest import mock

import pytest
import trustme

from six.moves import http_client

from ..server import Gateway, get_ssl_adapter_class, HTTPServer
from ..testing import (
    ANY_INTERFACE_IPV4,
    ANY_INTERFACE_IPV6,
    EPHEMERAL_PORT,
    get_server_client,
)


def make_https_server(bind_addr):
    """Create and start an HTTP server bound to bind_addr."""
    httpserver = HTTPServer(
        bind_addr=bind_addr,
        gateway=Gateway,
    )

    httpserver.ssl_adapter = make_ssl_adapter()
    threading.Thread(target=httpserver.safe_start).start()

    while not httpserver.ready:
        time.sleep(0.1)

    return httpserver


def make_ssl_adapter():
    ca = trustme.CA()

    server_cert = ca.issue_server_cert(u"test-host.example.org")

    ssl_module = 'builtin'
    ssl_adapter_cls = get_ssl_adapter_class(ssl_module)
    ssl_adapter_kwargs = {'certificate': '/dev/null', 'private_key': '/dev/null'}

    with mock.patch('ssl.SSLContext.load_cert_chain'):
        ssl_adapter = ssl_adapter_cls(**ssl_adapter_kwargs)
    server_cert.configure_cert(ssl_adapter.context)
    return ssl_adapter


@pytest.fixture
def https_server():
    """Provision a server creator as a fixture."""
    def start_srv():
        bind_addr = yield
        httpserver = make_https_server(bind_addr)
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


@pytest.mark.parametrize(
    'ip_addr',
    (
        ANY_INTERFACE_IPV4,
        ANY_INTERFACE_IPV6,
    )
)
def test_bind_addr_inet(https_server, ip_addr):
    """Check that bound IP address is stored in server."""
    httpserver = https_server.send((ip_addr, EPHEMERAL_PORT))

    assert httpserver.bind_addr[0] == ip_addr
    assert httpserver.bind_addr[1] != EPHEMERAL_PORT
    testclient = get_server_client(httpserver)
    name = '{interface}:{port}'.format(
        interface=httpserver.bind_addr[0],
        port=httpserver.bind_addr[1],
    )
    assert testclient.get('/', http_conn=http_client.HTTPSConnection(name)) == ''

