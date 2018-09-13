"""Pytest configuration module.

Contains fixtures, which are tightly bound to the Cheroot framework
itself, useless for end-users' app testing.
"""

from __future__ import absolute_import, division, print_function
__metaclass__ = type

import ssl
import pytest
import pyriform
from webtest import TestApp
import requests

from cheroot.ssl.builtin import BuiltinSSLAdapter

from ..testing import (  # noqa: F401
    native_server, wsgi_server,
)
from ..testing import get_server_client


@pytest.fixture  # noqa: F811
def wsgi_server_client(wsgi_server):
    """Create a test client out of given WSGI server."""
    return get_server_client(wsgi_server)


@pytest.fixture  # noqa: F811
def native_server_client(native_server):
    """Create a test client out of given HTTP server."""
    return get_server_client(native_server)


@pytest.fixture
def wsgi_adapter(wsgi_server):
    # instruct TestApp to configure the WSGIProxy to use requests instead of httplib
    app = TestApp("http://localhost:{}#requests".format(wsgi_server.bind_addr[1]))
    return pyriform.WSGIAdapter(app)

@pytest.fixture
def wsgi_adapter_session(wsgi_adapter):
    session = requests.Session()
    session.mount('http://', adapter)
    return session


@pytest.fixture
def make_session_for_cheroot(wsgi_server):
    '''
    Get a factory function to create a pyriform adapter that links a
    requests session to a wsgi_server fixture.  This is done by
    having a WebTest TestApp use WSGIProxy2 to use an http library
    to proxy directly to the given URL (for the web server -- in this
    case the wsgi_server is the web server).  The httplib client doesn't
    seem to handle a wsgi_server with an ssl_adapter other than None or a
    webserver that is accessible via https.

    :param wsgi_server:
    :return: yields a function to create a pyriform session that directly
             is proxied to the wsgi_server.  Depending on the args to the
             yielded function, https can be enabled for the wsgi_server,
             the wsgi_server can be mounted at a location other than 'http://',
             and the http client used by the proxy object can be changed.
    '''

    saved_ssl_adapter = wsgi_server.ssl_adapter

    def _make_session(prefix="http://", ssl_adapter=None, test_app_client="requests"):
        scheme = "http"
        assert prefix.startswith("http")
        if prefix.startswith("https"):
            assert ssl_adapter is not None
            scheme = "https"

        wsgi_server.ssl_adapter = ssl_adapter

        app = TestApp("{}://localhost:{}#{}".format(scheme, wsgi_server.bind_addr[1], test_app_client))
        return pyriform.make_session(app, prefix)

    yield _make_session

    wsgi_server.ssl_adapter = saved_ssl_adapter


@pytest.fixture
def crazy_wsgi_session(wsgi_server):
    my_test_app = TestApp("http://127.0.0.1:{}".format(wsgi_server.bind_addr[1]))
    adapter = pyriform.WSGIAdapter(my_test_app)

    # helpful to debug .....
#    my_test_app.get("http://127.0.0.1:{}/".format(wsgi_server.bind_addr[1]))

    session = requests.Session()
    session.mount('http://crazy_app/', adapter)
    resp = session.get('http://crazy_app/')
    print(resp.text)
    return session

@pytest.fixture
def crazy_wsgi_https_session(wsgi_server):
    ssl_adapter = BuiltinSSLAdapter(
        certificate='test/ssl/server.cert',
        private_key='test/ssl/server.key',
        certificate_chain='test/ssl/ca.cert'
    )
    ssl_adapter.context.verify_mode = ssl.CERT_NONE
    wsgi_server.ssl_adapter = ssl_adapter
    # instruct TestApp to configure the WSGIProxy to use requests instead of httplib
    my_test_app = TestApp("https://localhost:{}#requests".format(wsgi_server.bind_addr[1]))
    adapter = pyriform.WSGIAdapter(my_test_app)
    print ("adapter:", dir(adapter))

    # helpful to debug .....
    my_test_app.get("https://127.0.0.1:{}/".format(wsgi_server.bind_addr[1]))

    session = requests.Session()
    session.mount('https://crazy_app2/', adapter)
    resp = session.get('https://crazy_app2/')
    print(resp.text)
    return session
