"""Pytest configuration module.

Contains fixtures, which are tightly bound to the Cheroot framework
itself, useless for end-users' app testing.
"""

from __future__ import absolute_import, division, print_function
__metaclass__ = type

import pytest
import pyriform
from webtest import TestApp
import requests

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
    app = TestApp("http://localhost:{}".format(wsgi_server.bind_addr[1]))
    return pyriform.WSGIAdapter(app)

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
