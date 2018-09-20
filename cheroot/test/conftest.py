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
def make_session_for_cheroot(wsgi_server):
    '''
    Get a factory function to create a pyriform adapter that links a
    requests session to a wsgi_server fixture.  This is done by
    having a WebTest TestApp use WSGIProxy2 to use an http library
    to proxy directly to the given URL (for the web server -- in this
    case the wsgi_server is the web server).

    :param wsgi_server:
    :return: yields a function to create a pyriform session that is proxied to the wsgi_server.
             Depending on the args to the yielded function, https can be enabled for the wsgi_server,
             the wsgi_server can be mounted at a location other than 'http://',
             and the http client used by the proxy object can be changed.
    '''

    saved_ssl_adapter = wsgi_server.ssl_adapter

    def _make_session(prefix="http://", ssl_adapter=None, test_app_client="requests", client_cert=None, client_key=None):
        '''

        :param prefix: URL prefix (or protocol or scheme);
        :param ssl_adapter: replace, for the life of the current test, the wsgi_server's ssl_adapter
        :param test_app_client: the client module used by the wsgiproxy.HostProxy for TestApp to proxy to a real URL.
              The supported clients are ['requests', 'httplib', 'urllib3']
        :param client_cert: the path to the client SSL certificate or None (for mutual authentication)
        :param client_key: the path to the client private key or None
        :return: pyriform session linked to a TestApp object that proxies requests (for the given prefix)
            to the wsgi_server using the URL prefix, localhost, and the bound port of the wsgi_server
        '''
        scheme = "http"
        assert prefix.startswith("http")
        if prefix.startswith("https"):
            assert ssl_adapter is not None
            scheme = "https"

        wsgi_server.ssl_adapter = ssl_adapter

        app = TestApp("{}://localhost:{}#{}".format(scheme, wsgi_server.bind_addr[1], test_app_client))

        my_session = requests.Session()
        my_session.verify = ssl_adapter.certificate_chain
        if client_cert is not None and client_key is not None:
            my_session.cert = (client_cert, client_key)

        # A couple of issues:
        # The constructor for WebTest.TestApp doesn't have a way to pass args to the wsgiproxy.HostProxy constructor
        # The pyriform requests adaptor eats the request verify and cert args as it isn't trivial to pass
        # such args to an instant of WebTest.TestApp
        if scheme == "https" and test_app_client == "requests":
            from wsgiproxy import HostProxy
            url = "{}://localhost:{}".format(scheme, wsgi_server.bind_addr[1])
            app.app = HostProxy(url, client="requests", verify=my_session.verify, cert=my_session.cert)
        elif scheme == "https" and test_app_client == "httplib":
            # Note, in order for this to work, wsgiproxy's httplib wrapper needs some work to split the
            # client args into HTTPSConnection args and HTTPSConnection request args.
            from wsgiproxy import HostProxy
            client_ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=ssl_adapter.certificate_chain)
            if client_cert is not None and client_key is not None:
                client_ctx.load_cert_chain(certfile=client_cert, keyfile=client_key)
            client_ctx.check_hostname = True
            url = "{}://localhost:{}".format(scheme, wsgi_server.bind_addr[1])
            app.app = HostProxy(url, client="httplib", context=client_ctx)

        my_session.mount(prefix, pyriform.WSGIAdapter(app))
        return my_session

    yield _make_session

    wsgi_server.ssl_adapter = saved_ssl_adapter
