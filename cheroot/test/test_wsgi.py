"""Test wsgi."""

import sys
import threading

import pytest
import portend
import requests
from requests_toolbelt.sessions import BaseUrlSession as Session
from jaraco.context import ExceptionTrap

try:
    from concurrent.futures.thread import ThreadPoolExecutor
except ImportError:
    pytestmark = pytest.mark.xfail(
        sys.version_info[0] == 2,
        reason='no concurrent.futures @ py2',
    )
    if sys.version_info[0] != 2:
        raise
else:
    pytestmark = pytest.mark.xfail(
        sys.version_info[0] == 2,
        reason='no concurrent.futures @ py2',
    )

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
    server = wsgi.Server(addr, app, timeout=0, accepted_queue_timeout=0)
    thread = threading.Thread(target=server.start)
    thread.setDaemon(True)
    thread.start()
    url = 'http://localhost:{port}/'.format(**locals())
    yield locals()
    # would prefer to stop server, but has errors
    # server.stop()


def test_connection_keepalive(simple_wsgi_server):
    """Test the connection keepalive works (duh)."""
    session = Session(base_url=simple_wsgi_server['url'])
    pooled = requests.adapters.HTTPAdapter(
        pool_connections=1, pool_maxsize=1000,
    )
    session.mount('http://', pooled)

    def do_request():
        with ExceptionTrap(requests.exceptions.ConnectionError) as trap:
            resp = session.get('info')
            resp.raise_for_status()
        return bool(trap)

    with ThreadPoolExecutor(max_workers=50) as pool:
        tasks = [
            pool.submit(do_request)
            for n in range(1000)
        ]
        failures = sum(task.result() for task in tasks)

    assert not failures
