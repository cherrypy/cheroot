"""Test wsgi."""

import threading

import pytest
import portend

from cheroot import wsgi


@pytest.fixture
def simple_wsgi_server():
    """Fucking simple wsgi server fixture (duh)."""
    port = portend.find_available_local_port()

    def app(environ, start_response):
        status = '200 OK'
        response_headers = [('Content-type', 'text/plain')]
        start_response(status, response_headers)
        return [b'Hello world!']

    host = '::'
    addr = host, port
    server = wsgi.Server(addr, app)
    server.prepare()
    thread = threading.Thread(target=server.serve)
    thread.setDaemon(True)
    thread.start()
    yield locals()
    server.stop()


def test_connection_keepalive(simple_wsgi_server):
    """Test the connection keepalive works (duh)."""
    pass
