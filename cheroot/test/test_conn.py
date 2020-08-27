"""Tests for TCP connection handling, including proper and timely close."""

from __future__ import absolute_import, division, print_function
__metaclass__ = type

import socket
import time

import six
import pytest
from jaraco.text import trim, unwrap
from six.moves import range, http_client, urllib

from cheroot.test import helper, webtest
from cheroot._compat import IS_PYPY
import cheroot.server


timeout = 1
pov = 'pPeErRsSiIsStTeEnNcCeE oOfF vViIsSiIoOnN'


class Controller(helper.Controller):
    """Controller for serving WSGI apps."""

    def hello(req, resp):
        """Render Hello world."""
        return 'Hello, world!'

    def pov(req, resp):
        """Render ``pov`` value."""
        return pov

    def stream(req, resp):
        """Render streaming response."""
        if 'set_cl' in req.environ['QUERY_STRING']:
            resp.headers['Content-Length'] = str(10)

        def content():
            for x in range(10):
                yield str(x)

        return content()

    def upload(req, resp):
        """Process file upload and render thank."""
        if not req.environ['REQUEST_METHOD'] == 'POST':
            raise AssertionError(
                "'POST' != request.method %r" %
                req.environ['REQUEST_METHOD'],
            )
        return "thanks for '%s'" % req.environ['wsgi.input'].read()

    def custom_204(req, resp):
        """Render response with status 204."""
        resp.status = '204'
        return 'Code = 204'

    def custom_304(req, resp):
        """Render response with status 304."""
        resp.status = '304'
        return 'Code = 304'

    def err_before_read(req, resp):
        """Render response with status 500."""
        resp.status = '500 Internal Server Error'
        return 'ok'

    def one_megabyte_of_a(req, resp):
        """Render 1MB response."""
        return 'a' * 1024 * 1024

    def wrong_cl_buffered(req, resp):
        """Render buffered response with invalid length value."""
        resp.headers['Content-Length'] = '5'
        return 'I have too many bytes'

    def wrong_cl_unbuffered(req, resp):
        """Render unbuffered response with invalid length value."""
        resp.headers['Content-Length'] = '5'
        return ['I too', ' have too many bytes']

    def _munge(string):
        """Encode PATH_INFO correctly depending on Python version.

        WSGI 1.0 is a mess around unicode. Create endpoints
        that match the PATH_INFO that it produces.
        """
        if six.PY2:
            return string
        return string.encode('utf-8').decode('latin-1')

    handlers = {
        '/hello': hello,
        '/pov': pov,
        '/page1': pov,
        '/page2': pov,
        '/page3': pov,
        '/stream': stream,
        '/upload': upload,
        '/custom/204': custom_204,
        '/custom/304': custom_304,
        '/err_before_read': err_before_read,
        '/one_megabyte_of_a': one_megabyte_of_a,
        '/wrong_cl_buffered': wrong_cl_buffered,
        '/wrong_cl_unbuffered': wrong_cl_unbuffered,
    }


@pytest.fixture
def testing_server(wsgi_server_client):
    """Attach a WSGI app to the given server and preconfigure it."""
    app = Controller()

    def _timeout(req, resp):
        return str(wsgi_server.timeout)
    app.handlers['/timeout'] = _timeout
    wsgi_server = wsgi_server_client.server_instance
    wsgi_server.wsgi_app = app
    wsgi_server.max_request_body_size = 1001
    wsgi_server.timeout = timeout
    wsgi_server.server_client = wsgi_server_client
    wsgi_server.keep_alive_conn_limit = 2

    return wsgi_server


@pytest.fixture
def test_client(testing_server):
    """Get and return a test client out of the given server."""
    return testing_server.server_client


def header_exists(header_name, headers):
    """Check that a header is present."""
    return header_name.lower() in (k.lower() for (k, _) in headers)


def header_has_value(header_name, header_value, headers):
    """Check that a header with a given value is present."""
    return header_name.lower() in (
        k.lower() for (k, v) in headers
        if v == header_value
    )


def test_HTTP11_persistent_connections(test_client):
    """Test persistent HTTP/1.1 connections."""
    # Initialize a persistent HTTP connection
    http_connection = test_client.get_connection()
    http_connection.auto_open = False
    http_connection.connect()

    # Make the first request and assert there's no "Connection: close".
    status_line, actual_headers, actual_resp_body = test_client.get(
        '/pov', http_conn=http_connection,
    )
    actual_status = int(status_line[:3])
    assert actual_status == 200
    assert status_line[4:] == 'OK'
    assert actual_resp_body == pov.encode()
    assert not header_exists('Connection', actual_headers)

    # Make another request on the same connection.
    status_line, actual_headers, actual_resp_body = test_client.get(
        '/page1', http_conn=http_connection,
    )
    actual_status = int(status_line[:3])
    assert actual_status == 200
    assert status_line[4:] == 'OK'
    assert actual_resp_body == pov.encode()
    assert not header_exists('Connection', actual_headers)

    # Test client-side close.
    status_line, actual_headers, actual_resp_body = test_client.get(
        '/page2', http_conn=http_connection,
        headers=[('Connection', 'close')],
    )
    actual_status = int(status_line[:3])
    assert actual_status == 200
    assert status_line[4:] == 'OK'
    assert actual_resp_body == pov.encode()
    assert header_has_value('Connection', 'close', actual_headers)

    # Make another request on the same connection, which should error.
    with pytest.raises(http_client.NotConnected):
        test_client.get('/pov', http_conn=http_connection)


@pytest.mark.parametrize(
    'set_cl',
    (
        False,  # Without Content-Length
        True,  # With Content-Length
    ),
)
def test_streaming_11(test_client, set_cl):
    """Test serving of streaming responses with HTTP/1.1 protocol."""
    # Initialize a persistent HTTP connection
    http_connection = test_client.get_connection()
    http_connection.auto_open = False
    http_connection.connect()

    # Make the first request and assert there's no "Connection: close".
    status_line, actual_headers, actual_resp_body = test_client.get(
        '/pov', http_conn=http_connection,
    )
    actual_status = int(status_line[:3])
    assert actual_status == 200
    assert status_line[4:] == 'OK'
    assert actual_resp_body == pov.encode()
    assert not header_exists('Connection', actual_headers)

    # Make another, streamed request on the same connection.
    if set_cl:
        # When a Content-Length is provided, the content should stream
        # without closing the connection.
        status_line, actual_headers, actual_resp_body = test_client.get(
            '/stream?set_cl=Yes', http_conn=http_connection,
        )
        assert header_exists('Content-Length', actual_headers)
        assert not header_has_value('Connection', 'close', actual_headers)
        assert not header_exists('Transfer-Encoding', actual_headers)

        assert actual_status == 200
        assert status_line[4:] == 'OK'
        assert actual_resp_body == b'0123456789'
    else:
        # When no Content-Length response header is provided,
        # streamed output will either close the connection, or use
        # chunked encoding, to determine transfer-length.
        status_line, actual_headers, actual_resp_body = test_client.get(
            '/stream', http_conn=http_connection,
        )
        assert not header_exists('Content-Length', actual_headers)
        assert actual_status == 200
        assert status_line[4:] == 'OK'
        assert actual_resp_body == b'0123456789'

        chunked_response = False
        for k, v in actual_headers:
            if k.lower() == 'transfer-encoding':
                if str(v) == 'chunked':
                    chunked_response = True

        if chunked_response:
            assert not header_has_value('Connection', 'close', actual_headers)
        else:
            assert header_has_value('Connection', 'close', actual_headers)

            # Make another request on the same connection, which should
            # error.
            with pytest.raises(http_client.NotConnected):
                test_client.get('/pov', http_conn=http_connection)

        # Try HEAD.
        # See https://www.bitbucket.org/cherrypy/cherrypy/issue/864.
        # TODO: figure out how can this be possible on an closed connection
        # (chunked_response case)
        status_line, actual_headers, actual_resp_body = test_client.head(
            '/stream', http_conn=http_connection,
        )
        assert actual_status == 200
        assert status_line[4:] == 'OK'
        assert actual_resp_body == b''
        assert not header_exists('Transfer-Encoding', actual_headers)


@pytest.mark.parametrize(
    'set_cl',
    (
        False,  # Without Content-Length
        True,  # With Content-Length
    ),
)
def test_streaming_10(test_client, set_cl):
    """Test serving of streaming responses with HTTP/1.0 protocol."""
    original_server_protocol = test_client.server_instance.protocol
    test_client.server_instance.protocol = 'HTTP/1.0'

    # Initialize a persistent HTTP connection
    http_connection = test_client.get_connection()
    http_connection.auto_open = False
    http_connection.connect()

    # Make the first request and assert Keep-Alive.
    status_line, actual_headers, actual_resp_body = test_client.get(
        '/pov', http_conn=http_connection,
        headers=[('Connection', 'Keep-Alive')],
        protocol='HTTP/1.0',
    )
    actual_status = int(status_line[:3])
    assert actual_status == 200
    assert status_line[4:] == 'OK'
    assert actual_resp_body == pov.encode()
    assert header_has_value('Connection', 'Keep-Alive', actual_headers)

    # Make another, streamed request on the same connection.
    if set_cl:
        # When a Content-Length is provided, the content should
        # stream without closing the connection.
        status_line, actual_headers, actual_resp_body = test_client.get(
            '/stream?set_cl=Yes', http_conn=http_connection,
            headers=[('Connection', 'Keep-Alive')],
            protocol='HTTP/1.0',
        )
        actual_status = int(status_line[:3])
        assert actual_status == 200
        assert status_line[4:] == 'OK'
        assert actual_resp_body == b'0123456789'

        assert header_exists('Content-Length', actual_headers)
        assert header_has_value('Connection', 'Keep-Alive', actual_headers)
        assert not header_exists('Transfer-Encoding', actual_headers)
    else:
        # When a Content-Length is not provided,
        # the server should close the connection.
        status_line, actual_headers, actual_resp_body = test_client.get(
            '/stream', http_conn=http_connection,
            headers=[('Connection', 'Keep-Alive')],
            protocol='HTTP/1.0',
        )
        actual_status = int(status_line[:3])
        assert actual_status == 200
        assert status_line[4:] == 'OK'
        assert actual_resp_body == b'0123456789'

        assert not header_exists('Content-Length', actual_headers)
        assert not header_has_value('Connection', 'Keep-Alive', actual_headers)
        assert not header_exists('Transfer-Encoding', actual_headers)

        # Make another request on the same connection, which should error.
        with pytest.raises(http_client.NotConnected):
            test_client.get(
                '/pov', http_conn=http_connection,
                protocol='HTTP/1.0',
            )

    test_client.server_instance.protocol = original_server_protocol


@pytest.mark.parametrize(
    'http_server_protocol',
    (
        'HTTP/1.0',
        pytest.param(
            'HTTP/1.1',
            marks=pytest.mark.xfail(
                IS_PYPY and not six.PY2,
                reason='Fails under PyPy for unknown reason',
            ),
        ),
    ),
)
def test_keepalive(test_client, http_server_protocol):
    """Test Keep-Alive enabled connections."""
    original_server_protocol = test_client.server_instance.protocol
    test_client.server_instance.protocol = http_server_protocol

    http_client_protocol = 'HTTP/1.0'

    # Initialize a persistent HTTP connection
    http_connection = test_client.get_connection()
    http_connection.auto_open = False
    http_connection.connect()

    # Test a normal HTTP/1.0 request.
    status_line, actual_headers, actual_resp_body = test_client.get(
        '/page2',
        protocol=http_client_protocol,
    )
    actual_status = int(status_line[:3])
    assert actual_status == 200
    assert status_line[4:] == 'OK'
    assert actual_resp_body == pov.encode()
    assert not header_exists('Connection', actual_headers)

    # Test a keep-alive HTTP/1.0 request.

    status_line, actual_headers, actual_resp_body = test_client.get(
        '/page3', headers=[('Connection', 'Keep-Alive')],
        http_conn=http_connection, protocol=http_client_protocol,
    )
    actual_status = int(status_line[:3])
    assert actual_status == 200
    assert status_line[4:] == 'OK'
    assert actual_resp_body == pov.encode()
    assert header_has_value('Connection', 'Keep-Alive', actual_headers)
    assert header_has_value(
        'Keep-Alive',
        'timeout={test_client.server_instance.timeout}'.format(**locals()),
        actual_headers,
    )

    # Remove the keep-alive header again.
    status_line, actual_headers, actual_resp_body = test_client.get(
        '/page3', http_conn=http_connection,
        protocol=http_client_protocol,
    )
    actual_status = int(status_line[:3])
    assert actual_status == 200
    assert status_line[4:] == 'OK'
    assert actual_resp_body == pov.encode()
    assert not header_exists('Connection', actual_headers)
    assert not header_exists('Keep-Alive', actual_headers)

    test_client.server_instance.protocol = original_server_protocol


def test_keepalive_conn_management(test_client):
    """Test management of Keep-Alive connections."""
    test_client.server_instance.timeout = 2

    def connection():
        # Initialize a persistent HTTP connection
        http_connection = test_client.get_connection()
        http_connection.auto_open = False
        http_connection.connect()
        return http_connection

    def request(conn, keepalive=True):
        status_line, actual_headers, actual_resp_body = test_client.get(
            '/page3', headers=[('Connection', 'Keep-Alive')],
            http_conn=conn, protocol='HTTP/1.0',
        )
        actual_status = int(status_line[:3])
        assert actual_status == 200
        assert status_line[4:] == 'OK'
        assert actual_resp_body == pov.encode()
        if keepalive:
            assert header_has_value('Connection', 'Keep-Alive', actual_headers)
            assert header_has_value(
                'Keep-Alive',
                'timeout={test_client.server_instance.timeout}'.
                format(**locals()),
                actual_headers,
            )
        else:
            assert not header_exists('Connection', actual_headers)
            assert not header_exists('Keep-Alive', actual_headers)

    disconnect_errors = (
        http_client.BadStatusLine,
        http_client.CannotSendRequest,
        http_client.NotConnected,
    )

    # Make a new connection.
    c1 = connection()
    request(c1)

    # Make a second one.
    c2 = connection()
    request(c2)

    # Reusing the first connection should still work.
    request(c1)

    # Creating a new connection should still work, but we should
    # have run out of available connections to keep alive, so the
    # server should tell us to close.
    c3 = connection()
    request(c3, keepalive=False)

    # Show that the third connection was closed.
    with pytest.raises(disconnect_errors):
        request(c3)

    # Wait for some of our timeout.
    time.sleep(1.2)

    # Refresh the second connection.
    request(c2)

    # Wait for the remainder of our timeout, plus one tick.
    time.sleep(1.2)

    # First connection should now be expired.
    with pytest.raises(disconnect_errors):
        request(c1)

    # But the second one should still be valid.
    request(c2)

    # Restore original timeout.
    test_client.server_instance.timeout = timeout


@pytest.mark.parametrize(
    'timeout_before_headers',
    (
        True,
        False,
    ),
)
def test_HTTP11_Timeout(test_client, timeout_before_headers):
    """Check timeout without sending any data.

    The server will close the connection with a 408.
    """
    conn = test_client.get_connection()
    conn.auto_open = False
    conn.connect()

    if not timeout_before_headers:
        # Connect but send half the headers only.
        conn.send(b'GET /hello HTTP/1.1')
        conn.send(('Host: %s' % conn.host).encode('ascii'))
    # else: Connect but send nothing.

    # Wait for our socket timeout
    time.sleep(timeout * 2)

    # The request should have returned 408 already.
    response = conn.response_class(conn.sock, method='GET')
    response.begin()
    assert response.status == 408
    conn.close()


def test_HTTP11_Timeout_after_request(test_client):
    """Check timeout after at least one request has succeeded.

    The server should close the connection without 408.
    """
    fail_msg = "Writing to timed out socket didn't fail as it should have: %s"

    # Make an initial request
    conn = test_client.get_connection()
    conn.putrequest('GET', '/timeout?t=%s' % timeout, skip_host=True)
    conn.putheader('Host', conn.host)
    conn.endheaders()
    response = conn.response_class(conn.sock, method='GET')
    response.begin()
    assert response.status == 200
    actual_body = response.read()
    expected_body = str(timeout).encode()
    assert actual_body == expected_body

    # Make a second request on the same socket
    conn._output(b'GET /hello HTTP/1.1')
    conn._output(('Host: %s' % conn.host).encode('ascii'))
    conn._send_output()
    response = conn.response_class(conn.sock, method='GET')
    response.begin()
    assert response.status == 200
    actual_body = response.read()
    expected_body = b'Hello, world!'
    assert actual_body == expected_body

    # Wait for our socket timeout
    time.sleep(timeout * 2)

    # Make another request on the same socket, which should error
    conn._output(b'GET /hello HTTP/1.1')
    conn._output(('Host: %s' % conn.host).encode('ascii'))
    conn._send_output()
    response = conn.response_class(conn.sock, method='GET')
    try:
        response.begin()
    except (socket.error, http_client.BadStatusLine):
        pass
    except Exception as ex:
        pytest.fail(fail_msg % ex)
    else:
        if response.status != 408:
            pytest.fail(fail_msg % response.read())

    conn.close()

    # Make another request on a new socket, which should work
    conn = test_client.get_connection()
    conn.putrequest('GET', '/pov', skip_host=True)
    conn.putheader('Host', conn.host)
    conn.endheaders()
    response = conn.response_class(conn.sock, method='GET')
    response.begin()
    assert response.status == 200
    actual_body = response.read()
    expected_body = pov.encode()
    assert actual_body == expected_body

    # Make another request on the same socket,
    # but timeout on the headers
    conn.send(b'GET /hello HTTP/1.1')
    # Wait for our socket timeout
    time.sleep(timeout * 2)
    response = conn.response_class(conn.sock, method='GET')
    try:
        response.begin()
    except (socket.error, http_client.BadStatusLine):
        pass
    except Exception as ex:
        pytest.fail(fail_msg % ex)
    else:
        if response.status != 408:
            pytest.fail(fail_msg % response.read())

    conn.close()

    # Retry the request on a new connection, which should work
    conn = test_client.get_connection()
    conn.putrequest('GET', '/pov', skip_host=True)
    conn.putheader('Host', conn.host)
    conn.endheaders()
    response = conn.response_class(conn.sock, method='GET')
    response.begin()
    assert response.status == 200
    actual_body = response.read()
    expected_body = pov.encode()
    assert actual_body == expected_body
    conn.close()


def test_HTTP11_pipelining(test_client):
    """Test HTTP/1.1 pipelining.

    :py:mod:`http.client` doesn't support this directly.
    """
    conn = test_client.get_connection()

    # Put request 1
    conn.putrequest('GET', '/hello', skip_host=True)
    conn.putheader('Host', conn.host)
    conn.endheaders()

    for trial in range(5):
        # Put next request
        conn._output(
            ('GET /hello?%s HTTP/1.1' % trial).encode('iso-8859-1'),
        )
        conn._output(('Host: %s' % conn.host).encode('ascii'))
        conn._send_output()

        # Retrieve previous response
        response = conn.response_class(conn.sock, method='GET')
        # there is a bug in python3 regarding the buffering of
        # ``conn.sock``. Until that bug get's fixed we will
        # monkey patch the ``response`` instance.
        # https://bugs.python.org/issue23377
        if not six.PY2:
            response.fp = conn.sock.makefile('rb', 0)
        response.begin()
        body = response.read(13)
        assert response.status == 200
        assert body == b'Hello, world!'

    # Retrieve final response
    response = conn.response_class(conn.sock, method='GET')
    response.begin()
    body = response.read()
    assert response.status == 200
    assert body == b'Hello, world!'

    conn.close()


def test_100_Continue(test_client):
    """Test 100-continue header processing."""
    conn = test_client.get_connection()

    # Try a page without an Expect request header first.
    # Note that http.client's response.begin automatically ignores
    # 100 Continue responses, so we must manually check for it.
    conn.putrequest('POST', '/upload', skip_host=True)
    conn.putheader('Host', conn.host)
    conn.putheader('Content-Type', 'text/plain')
    conn.putheader('Content-Length', '4')
    conn.endheaders()
    conn.send(b"d'oh")
    response = conn.response_class(conn.sock, method='POST')
    version, status, reason = response._read_status()
    assert status != 100
    conn.close()

    # Now try a page with an Expect header...
    conn.connect()
    conn.putrequest('POST', '/upload', skip_host=True)
    conn.putheader('Host', conn.host)
    conn.putheader('Content-Type', 'text/plain')
    conn.putheader('Content-Length', '17')
    conn.putheader('Expect', '100-continue')
    conn.endheaders()
    response = conn.response_class(conn.sock, method='POST')

    # ...assert and then skip the 100 response
    version, status, reason = response._read_status()
    assert status == 100
    while True:
        line = response.fp.readline().strip()
        if line:
            pytest.fail(
                '100 Continue should not output any headers. Got %r' %
                line,
            )
        else:
            break

    # ...send the body
    body = b'I am a small file'
    conn.send(body)

    # ...get the final response
    response.begin()
    status_line, actual_headers, actual_resp_body = webtest.shb(response)
    actual_status = int(status_line[:3])
    assert actual_status == 200
    expected_resp_body = ("thanks for '%s'" % body).encode()
    assert actual_resp_body == expected_resp_body
    conn.close()


@pytest.mark.parametrize(
    'max_request_body_size',
    (
        0,
        1001,
    ),
)
def test_readall_or_close(test_client, max_request_body_size):
    """Test a max_request_body_size of 0 (the default) and 1001."""
    old_max = test_client.server_instance.max_request_body_size

    test_client.server_instance.max_request_body_size = max_request_body_size

    conn = test_client.get_connection()

    # Get a POST page with an error
    conn.putrequest('POST', '/err_before_read', skip_host=True)
    conn.putheader('Host', conn.host)
    conn.putheader('Content-Type', 'text/plain')
    conn.putheader('Content-Length', '1000')
    conn.putheader('Expect', '100-continue')
    conn.endheaders()
    response = conn.response_class(conn.sock, method='POST')

    # ...assert and then skip the 100 response
    version, status, reason = response._read_status()
    assert status == 100
    skip = True
    while skip:
        skip = response.fp.readline().strip()

    # ...send the body
    conn.send(b'x' * 1000)

    # ...get the final response
    response.begin()
    status_line, actual_headers, actual_resp_body = webtest.shb(response)
    actual_status = int(status_line[:3])
    assert actual_status == 500

    # Now try a working page with an Expect header...
    conn._output(b'POST /upload HTTP/1.1')
    conn._output(('Host: %s' % conn.host).encode('ascii'))
    conn._output(b'Content-Type: text/plain')
    conn._output(b'Content-Length: 17')
    conn._output(b'Expect: 100-continue')
    conn._send_output()
    response = conn.response_class(conn.sock, method='POST')

    # ...assert and then skip the 100 response
    version, status, reason = response._read_status()
    assert status == 100
    skip = True
    while skip:
        skip = response.fp.readline().strip()

    # ...send the body
    body = b'I am a small file'
    conn.send(body)

    # ...get the final response
    response.begin()
    status_line, actual_headers, actual_resp_body = webtest.shb(response)
    actual_status = int(status_line[:3])
    assert actual_status == 200
    expected_resp_body = ("thanks for '%s'" % body).encode()
    assert actual_resp_body == expected_resp_body
    conn.close()

    test_client.server_instance.max_request_body_size = old_max


def test_No_Message_Body(test_client):
    """Test HTTP queries with an empty response body."""
    # Initialize a persistent HTTP connection
    http_connection = test_client.get_connection()
    http_connection.auto_open = False
    http_connection.connect()

    # Make the first request and assert there's no "Connection: close".
    status_line, actual_headers, actual_resp_body = test_client.get(
        '/pov', http_conn=http_connection,
    )
    actual_status = int(status_line[:3])
    assert actual_status == 200
    assert status_line[4:] == 'OK'
    assert actual_resp_body == pov.encode()
    assert not header_exists('Connection', actual_headers)

    # Make a 204 request on the same connection.
    status_line, actual_headers, actual_resp_body = test_client.get(
        '/custom/204', http_conn=http_connection,
    )
    actual_status = int(status_line[:3])
    assert actual_status == 204
    assert not header_exists('Content-Length', actual_headers)
    assert actual_resp_body == b''
    assert not header_exists('Connection', actual_headers)

    # Make a 304 request on the same connection.
    status_line, actual_headers, actual_resp_body = test_client.get(
        '/custom/304', http_conn=http_connection,
    )
    actual_status = int(status_line[:3])
    assert actual_status == 304
    assert not header_exists('Content-Length', actual_headers)
    assert actual_resp_body == b''
    assert not header_exists('Connection', actual_headers)


@pytest.mark.xfail(
    reason=unwrap(
        trim("""
        Headers from earlier request leak into the request
        line for a subsequent request, resulting in 400
        instead of 413. See cherrypy/cheroot#69 for details.
        """),
    ),
)
def test_Chunked_Encoding(test_client):
    """Test HTTP uploads with chunked transfer-encoding."""
    # Initialize a persistent HTTP connection
    conn = test_client.get_connection()

    # Try a normal chunked request (with extensions)
    body = (
        b'8;key=value\r\nxx\r\nxxxx\r\n5\r\nyyyyy\r\n0\r\n'
        b'Content-Type: application/json\r\n'
        b'\r\n'
    )
    conn.putrequest('POST', '/upload', skip_host=True)
    conn.putheader('Host', conn.host)
    conn.putheader('Transfer-Encoding', 'chunked')
    conn.putheader('Trailer', 'Content-Type')
    # Note that this is somewhat malformed:
    # we shouldn't be sending Content-Length.
    # RFC 2616 says the server should ignore it.
    conn.putheader('Content-Length', '3')
    conn.endheaders()
    conn.send(body)
    response = conn.getresponse()
    status_line, actual_headers, actual_resp_body = webtest.shb(response)
    actual_status = int(status_line[:3])
    assert actual_status == 200
    assert status_line[4:] == 'OK'
    expected_resp_body = ("thanks for '%s'" % b'xx\r\nxxxxyyyyy').encode()
    assert actual_resp_body == expected_resp_body

    # Try a chunked request that exceeds server.max_request_body_size.
    # Note that the delimiters and trailer are included.
    body = b'\r\n'.join((b'3e3', b'x' * 995, b'0', b'', b''))
    conn.putrequest('POST', '/upload', skip_host=True)
    conn.putheader('Host', conn.host)
    conn.putheader('Transfer-Encoding', 'chunked')
    conn.putheader('Content-Type', 'text/plain')
    # Chunked requests don't need a content-length
    # conn.putheader("Content-Length", len(body))
    conn.endheaders()
    conn.send(body)
    response = conn.getresponse()
    status_line, actual_headers, actual_resp_body = webtest.shb(response)
    actual_status = int(status_line[:3])
    assert actual_status == 413
    conn.close()


def test_Content_Length_in(test_client):
    """Try a non-chunked request where Content-Length exceeds limit.

    (server.max_request_body_size).
    Assert error before body send.
    """
    # Initialize a persistent HTTP connection
    conn = test_client.get_connection()

    conn.putrequest('POST', '/upload', skip_host=True)
    conn.putheader('Host', conn.host)
    conn.putheader('Content-Type', 'text/plain')
    conn.putheader('Content-Length', '9999')
    conn.endheaders()
    response = conn.getresponse()
    status_line, actual_headers, actual_resp_body = webtest.shb(response)
    actual_status = int(status_line[:3])
    assert actual_status == 413
    expected_resp_body = (
        b'The entity sent with the request exceeds '
        b'the maximum allowed bytes.'
    )
    assert actual_resp_body == expected_resp_body
    conn.close()


def test_Content_Length_not_int(test_client):
    """Test that malicious Content-Length header returns 400."""
    status_line, actual_headers, actual_resp_body = test_client.post(
        '/upload',
        headers=[
            ('Content-Type', 'text/plain'),
            ('Content-Length', 'not-an-integer'),
        ],
    )
    actual_status = int(status_line[:3])

    assert actual_status == 400
    assert actual_resp_body == b'Malformed Content-Length Header.'


@pytest.mark.parametrize(
    ('uri', 'expected_resp_status', 'expected_resp_body'),
    (
        (
            '/wrong_cl_buffered', 500,
            (
                b'The requested resource returned more bytes than the '
                b'declared Content-Length.'
            ),
        ),
        ('/wrong_cl_unbuffered', 200, b'I too'),
    ),
)
def test_Content_Length_out(
    test_client,
    uri, expected_resp_status, expected_resp_body,
):
    """Test response with Content-Length less than the response body.

    (non-chunked response)
    """
    conn = test_client.get_connection()
    conn.putrequest('GET', uri, skip_host=True)
    conn.putheader('Host', conn.host)
    conn.endheaders()

    response = conn.getresponse()
    status_line, actual_headers, actual_resp_body = webtest.shb(response)
    actual_status = int(status_line[:3])

    assert actual_status == expected_resp_status
    assert actual_resp_body == expected_resp_body

    conn.close()

    # the server logs the exception that we had verified from the
    # client perspective. Tell the error_log verification that
    # it can ignore that message.
    test_client.server_instance.error_log.ignored_msgs.extend((
        # Python 3.7+:
        "ValueError('Response body exceeds the declared Content-Length.')",
        # Python 2.7-3.6 (macOS?):
        "ValueError('Response body exceeds the declared Content-Length.',)",
    ))


def test_598(test_client):
    """Test serving large file with a read timeout in place.

    Ref: https://github.com/cherrypy/cherrypy/issues/598
    """
    # Initialize a persistent HTTP connection
    conn = test_client.get_connection()
    remote_data_conn = urllib.request.urlopen(
        '%s://%s:%s/one_megabyte_of_a'
        % ('http', conn.host, conn.port),
    )
    buf = remote_data_conn.read(512)
    time.sleep(timeout * 0.6)
    remaining = (1024 * 1024) - 512
    while remaining:
        data = remote_data_conn.read(remaining)
        if not data:
            break
        buf += data
        remaining -= len(data)

    assert len(buf) == 1024 * 1024
    assert buf == b'a' * 1024 * 1024
    assert remaining == 0
    remote_data_conn.close()


@pytest.mark.parametrize(
    'invalid_terminator',
    (
        b'\n\n',
        b'\r\n\n',
    ),
)
def test_No_CRLF(test_client, invalid_terminator):
    """Test HTTP queries with no valid CRLF terminators."""
    # Initialize a persistent HTTP connection
    conn = test_client.get_connection()

    # (b'%s' % b'') is not supported in Python 3.4, so just use bytes.join()
    conn.send(b''.join((b'GET /hello HTTP/1.1', invalid_terminator)))
    response = conn.response_class(conn.sock, method='GET')
    response.begin()
    actual_resp_body = response.read()
    expected_resp_body = b'HTTP requires CRLF terminators'
    assert actual_resp_body == expected_resp_body
    conn.close()


class FaultySelectorManager:
    """Mock class to insert errors in th execution."""

    def __init__(self, orig_select_mgr):
        """Prepare the wrapper to intervene the execution.

        Initialize the flags to trigger the errors inside the
        _SelectorManager to put to test the error handling segments
        of ConnectionManager.

        This class is heavily dependent on the implementation of
        _SelectorManager and ConnectionManager, be ready to refactor
        and adjust if the integration between those two changes.
        """
        # reference to the good instance
        self.orig_select_mgr = orig_select_mgr
        # flag to trigger a fault on the iteration of connections
        self.sabotage_conn = False
        # flag that marks when the explicit closing has been done
        self.conn_closed = False
        # flag to trigger the fault in the select call
        self.request_served = False
        # flog to notify that the error has been rised for the select call
        self.os_error_triggered = False

    def __getattr__(self, attr):
        """Pass any other attribute lookup to the original _SelectorManager."""
        return getattr(self.orig_select_mgr, attr)

    def __len__(self):
        """Define a transparent __len__ method."""
        return len(self.orig_select_mgr)

    def __iter__(self):
        """Intercept the calls to the iterator."""
        result = tuple(self.orig_select_mgr)
        sabotage_targets = (
            conn for _, _, _, conn in result
            if isinstance(conn, cheroot.server.HTTPConnection)
        ) if self.sabotage_conn and not self.conn_closed else ()

        for conn in sabotage_targets:
            assert not self.conn_closed, 'The connection is already closed.'
            # close the connection to cause OSError
            conn.close()
            self.conn_closed = True

        return iter(result)

    def select(self, timeout):
        """Intercept the select call."""
        if self.request_served:
            self.os_error_triggered = True
            raise OSError('Error while selecting the client socket.')
        return self.orig_select_mgr.select(timeout)


def test_invalid_selected_connection(test_client, monkeypatch):
    """Test the error handling segment of HTTP connection selection.

    See :py:meth:`cheroot.connections.ConnectionManager.get_conn`.
    """
    faux_select_mgr = FaultySelectorManager(
        test_client.server_instance._connections._selector_mgr,
    )
    monkeypatch.setattr(
        test_client.server_instance._connections,
        '_selector_mgr',
        faux_select_mgr,
    )

    # request a page with connection keep-alive to make sure
    # we'll have a connection to be modified.
    resp_status, resp_headers, resp_body = test_client.request(
        '/page1', headers=[('Connection', 'Keep-Alive')],
    )

    assert resp_status == '200 OK'
    # trigger the internal errors
    faux_select_mgr.sabotage_conn = faux_select_mgr.request_served = True
    # give time to make sure the error gets handled
    time.sleep(0.2)
    assert faux_select_mgr.os_error_triggered
    assert faux_select_mgr.conn_closed
    # any error in the error handling should be catched by the
    # teardown verification for the error_log
