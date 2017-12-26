"""Tests for managing HTTP issues (malformed requests, etc)."""
# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :

from contextlib import closing
import errno
import socket

import pytest
import six
from six.moves import urllib, http_client

from cheroot.test import helper, webtest


HTTP_BAD_REQUEST = 400
HTTP_LENGTH_REQUIRED = 411
HTTP_NOT_FOUND = 404
HTTP_OK = 200
HTTP_VERSION_NOT_SUPPORTED = 505


class HelloController(helper.Controller):
    def hello(req, resp):
        return 'Hello world!'

    def body_required(req, resp):
        if req.environ.get('Content-Length', None) is None:
            resp.status = '411 Length Required'
            return
        return 'Hello world!'

    def query_string(req, resp):
        return req.environ.get('QUERY_STRING', '')

    def asterisk(req, resp):
        method = req.environ.get('REQUEST_METHOD', 'NO METHOD FOUND')
        tmpl = 'Got asterisk URI path with {method} method'
        return tmpl.format(**locals())

    def _munge(string):
        """
        WSGI 1.0 is a mess around unicode. Create endpoints
        that match the PATH_INFO that it produces.
        """
        if six.PY3:
            return string.encode('utf-8').decode('latin-1')
        return string

    handlers = {
        '/hello': hello,
        '/no_body': hello,
        '/body_required': body_required,
        '/query_string': query_string,
        _munge('/привіт'): hello,
        _munge('/Юххууу'): hello,
        '/\xa0Ðblah key 0 900 4 data': hello,
        '/*': asterisk,
    }


def _get_http_response(connection, method='GET'):
    c = connection
    kwargs = {'strict': c.strict} if hasattr(c, 'strict') else {}
    # Python 3.2 removed the 'strict' feature, saying:
    # "http.client now always assumes HTTP/1.x compliant servers."
    return c.response_class(c.sock, method=method, **kwargs)


@pytest.fixture(scope='module')
def testing_server(wsgi_server):
    wsgi_server.wsgi_app = HelloController()
    wsgi_server.max_request_body_size = 30000000
    return wsgi_server


@pytest.fixture
def server_client(testing_server):
    host, port = testing_server.bind_addr

    interface = webtest.interface(host)

    def probe_ipv6_sock(interface):
        # Alternate way is to check IPs on interfaces using glibc, like:
        # github.com/Gautier/minifail/blob/master/minifail/getifaddrs.py
        try:
            with closing(socket.socket(family=socket.AF_INET6)) as sock:
                sock.bind((interface, 0))
        except OSError as sock_err:
            if sock_err.errno != errno.EADDRNOTAVAIL:
                raise
        else:
            return True

        return False

    if ':' in interface and not probe_ipv6_sock(interface):
        interface = '127.0.0.1'
        if ':' in host:
            host = interface

    class _TestClient(object):
        def __init__(self, host, port):
            self._host = host
            self._port = port

        def get_connection(self):
            name = '{interface}:{port}'.format(
                interface=interface,
                port=self._port,
            )
            return http_client.HTTPConnection(name)

        def request(self, uri, method='GET'):
            return webtest.openURL(
                uri, method=method,
                host=self._host, port=self._port,
            )

        def get(self, uri):
            return self.request(uri, method='GET')

        def post(self, uri):
            return self.request(uri, method='POST')

        def put(self, uri):
            return self.request(uri, method='PUT')

        def patch(self, uri):
            return self.request(uri, method='PATCH')

        def delete(self, uri):
            return self.request(uri, method='DELETE')

        def connect(self, uri):
            return self.request(uri, method='CONNECT')

        def options(self, uri):
            return self.request(uri, method='OPTIONS')

    test_client = _TestClient(host, port)
    return test_client


def test_http_connect_request(server_client):
    status_line = server_client.connect('/anything')[0]
    actual_status = int(status_line[:3])
    assert actual_status == 405


def test_normal_request(server_client):
    status_line, _, actual_resp_body = server_client.get('/hello')
    actual_status = int(status_line[:3])
    assert actual_status == HTTP_OK
    assert actual_resp_body == b'Hello world!'


def test_query_string_request(server_client):
    status_line, _, actual_resp_body = server_client.get(
        '/query_string?test=True'
    )
    actual_status = int(status_line[:3])
    assert actual_status == HTTP_OK
    assert actual_resp_body == b'test=True'


@pytest.mark.parametrize(
    'uri',
    (
        '/hello',  # plain
        '/query_string?test=True',  # query
        '/{0}?{1}={2}'.format(  # quoted unicode
            *map(urllib.parse.quote, ('Юххууу', 'ї', 'йо'))
        ),
    )
)
def test_parse_acceptable_uri(server_client, uri):
    status_line = server_client.get(uri)[0]
    actual_status = int(status_line[:3])
    assert actual_status == HTTP_OK


@pytest.mark.xfail(six.PY2, reason='Fails on Python 2')
def test_parse_uri_unsafe_uri(server_client):
    """Test that malicious URI does not allow HTTP injection.

    This effectively checks that sending GET request with URL

    /%A0%D0blah%20key%200%20900%204%20data

    is not converted into

    GET /
    blah key 0 900 4 data
    HTTP/1.1

    which would be a security issue otherwise.
    """
    c = server_client.get_connection()
    resource = '/\xa0Ðblah key 0 900 4 data'.encode('latin-1')
    quoted = urllib.parse.quote(resource)
    assert quoted == '/%A0%D0blah%20key%200%20900%204%20data'
    request = 'GET {quoted} HTTP/1.1'.format(**locals())
    c._output(request.encode('utf-8'))
    c._send_output()
    response = _get_http_response(c, method='GET')
    response.begin()
    assert response.status == HTTP_OK
    assert response.fp.read(12) == b'Hello world!'
    c.close()


def test_parse_uri_invalid_uri(server_client):
    c = server_client.get_connection()
    c._output(u'GET /йопта! HTTP/1.1'.encode('utf-8'))
    c._send_output()
    response = _get_http_response(c, method='GET')
    response.begin()
    assert response.status == HTTP_BAD_REQUEST
    assert response.fp.read(21) == b'Malformed Request-URI'
    c.close()


@pytest.mark.parametrize(
    'uri',
    (
        'hello',  # ascii
        'привіт',  # non-ascii
    )
)
def test_parse_no_leading_slash_invalid(server_client, uri):
    """
    URIs with no leading slash produce a 400
    """
    status_line, _, actual_resp_body = server_client.get(
        urllib.parse.quote(uri)
    )
    actual_status = int(status_line[:3])
    assert actual_status == HTTP_BAD_REQUEST
    assert b'starting with a slash' in actual_resp_body


def test_parse_uri_absolute_uri(server_client):
    status_line, _, actual_resp_body = server_client.get('http://google.com/')
    actual_status = int(status_line[:3])
    assert actual_status == HTTP_BAD_REQUEST
    expected_body = b'Absolute URI not allowed if server is not a proxy.'
    assert actual_resp_body == expected_body


def test_parse_uri_asterisk_uri(server_client):
    status_line, _, actual_resp_body = server_client.options('*')
    actual_status = int(status_line[:3])
    assert actual_status == HTTP_OK
    expected_body = b'Got asterisk URI path with OPTIONS method'
    assert actual_resp_body == expected_body


def test_parse_uri_fragment_uri(server_client):
    status_line, _, actual_resp_body = server_client.get(
        '/hello?test=something#fake',
    )
    actual_status = int(status_line[:3])
    assert actual_status == HTTP_BAD_REQUEST
    expected_body = b'Illegal #fragment in Request-URI.'
    assert actual_resp_body == expected_body


def test_no_content_length(server_client):
    # "The presence of a message-body in a request is signaled by the
    # inclusion of a Content-Length or Transfer-Encoding header field in
    # the request's message-headers."
    #
    # Send a message with neither header and no body.
    c = server_client.get_connection()
    c.request('POST', '/no_body')
    response = c.getresponse()
    actual_resp_body = response.fp.read()
    actual_status = response.status
    assert actual_status == HTTP_OK
    assert actual_resp_body == b'Hello world!'


def test_content_length_required(server_client):
    # Now send a message that has no Content-Length, but does send a body.
    # Verify that CP times out the socket and responds
    # with 411 Length Required.

    c = server_client.get_connection()
    c.request('POST', '/body_required')
    response = c.getresponse()
    response.fp.read()

    actual_status = response.status
    assert actual_status == HTTP_LENGTH_REQUIRED


@pytest.mark.parametrize(
    'request_line,status_code,expected_body',
    (
        (b'GET /',  # missing proto
         HTTP_BAD_REQUEST, b'Malformed Request-Line'),
        (b'GET / HTTPS/1.1',  # invalid proto
         HTTP_BAD_REQUEST, b'Malformed Request-Line: bad protocol'),
        (b'GET / HTTP/2.15',  # invalid ver
         HTTP_VERSION_NOT_SUPPORTED, b'Cannot fulfill request'),
    )
)
def test_malformed_request_line(
    server_client, request_line,
    status_code, expected_body
):
    """Test missing or invalid HTTP version in Request-Line."""
    c = server_client.get_connection()
    c._output(request_line)
    c._send_output()
    response = _get_http_response(c, method='GET')
    response.begin()
    assert response.status == status_code
    assert response.fp.read(len(expected_body)) == expected_body
    c.close()


def test_malformed_http_method(server_client):
    c = server_client.get_connection()
    c.putrequest('GeT', '/malformed_method_case')
    c.putheader('Content-Type', 'text/plain')
    c.endheaders()

    response = c.getresponse()
    actual_status = response.status
    assert actual_status == HTTP_BAD_REQUEST
    actual_resp_body = response.fp.read(21)
    assert actual_resp_body == b'Malformed method name'


def test_malformed_header(server_client):
    c = server_client.get_connection()
    c.putrequest('GET', '/')
    c.putheader('Content-Type', 'text/plain')
    # See http://www.bitbucket.org/cherrypy/cherrypy/issue/941
    c._output(b'Re, 1.2.3.4#015#012')
    c.endheaders()

    response = c.getresponse()
    actual_status = response.status
    assert actual_status == HTTP_BAD_REQUEST
    actual_resp_body = response.fp.read(20)
    assert actual_resp_body == b'Illegal header line.'


def test_request_line_split_issue_1220(server_client):
    Request_URI = (
        '/hello?'
        'intervenant-entreprise-evenement_classaction='
        'evenement-mailremerciements'
        '&_path=intervenant-entreprise-evenement'
        '&intervenant-entreprise-evenement_action-id=19404'
        '&intervenant-entreprise-evenement_id=19404'
        '&intervenant-entreprise_id=28092'
    )
    assert len('GET %s HTTP/1.1\r\n' % Request_URI) == 256

    actual_resp_body = server_client.get(Request_URI)[2]
    assert actual_resp_body == b'Hello world!'


def test_garbage_in(server_client):
    # Connect without SSL regardless of server.scheme

    c = server_client.get_connection()
    c._output(b'gjkgjklsgjklsgjkljklsg')
    c._send_output()
    response = c.response_class(c.sock, method='GET')
    try:
        response.begin()
        actual_status = response.status
        assert actual_status == HTTP_BAD_REQUEST
        actual_resp_body = response.fp.read(22)
        assert actual_resp_body == b'Malformed Request-Line'
        c.close()
    except socket.error as ex:
        # "Connection reset by peer" is also acceptable.
        if ex.errno != errno.ECONNRESET:
            raise
