"""Tests for managing HTTP issues (malformed requests, etc)."""
# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :

import errno
import socket

from cheroot._compat import (
    HTTPConnection, HTTPSConnection,
    quote as url_quote, ntob
)
from cheroot.test import helper


class HTTPTests(helper.CherootWebCase):

    def setup_server(cls):
        class Root(helper.Controller):

            def hello(self, req, resp):
                return 'Hello world!'

            def no_body(self, req, resp):
                return 'Hello world!'

            def body_required(self, req, resp):
                if req.environ.get('Content-Length', None) is None:
                    resp.status = '411 Length Required'
                    return
                return 'Hello world!'

            def query_string(self, req, resp):
                return req.environ.get('QUERY_STRING', '')

        setattr(Root, 'привіт', Root.hello)
        setattr(Root, 'Юххууу', Root.hello)

        cls.httpserver.wsgi_app = Root()
        cls.httpserver.max_request_body_size = 30000000
    setup_server = classmethod(setup_server)

    def test_normal_request(self):
        self.getPage('/hello')
        self.assertStatus(200)
        self.assertBody(b'Hello world!')

    def test_query_string_request(self):
        self.getPage('/query_string?test=True')
        self.assertStatus(200)
        self.assertBody(b'test=True')

    def test_parse_uri(self):
        for uri in ['/hello', '/query_string?test=True', 'hello',
                    url_quote('привіт'),
                    '/{0}?{1}={2}'.format(
                        *map(url_quote, ('Юххууу', 'ї', 'йо'))
                    )]:
            self.getPage(uri)
            self.assertStatus(200)

    def test_parse_uri_invalid_uri(self):
        if self.scheme == 'https':
            c = HTTPSConnection('%s:%s' % (self.interface(), self.PORT))
        else:
            c = HTTPConnection('%s:%s' % (self.interface(), self.PORT))
        c._output(ntob('GET /йопта! HTTP/1.1', 'utf-8'))
        c._send_output()
        if hasattr(c, 'strict'):
            response = c.response_class(c.sock, strict=c.strict, method='GET')
        else:
            # Python 3.2 removed the 'strict' feature, saying:
            # "http.client now always assumes HTTP/1.x compliant servers."
            response = c.response_class(c.sock, method='GET')
        response.begin()
        assert response.status == 400
        assert response.fp.read(21) == b'Malformed Request-URI'
        c.close()

    def test_parse_uri_absolute_uri(self):
        self.getPage('http://google.com/')
        self.assertStatus(400)
        self.assertBody(b'Absolute URI not allowed if server is not a proxy.')

    def test_parse_uri_asterisk_uri(self):
        self.getPage('*', method='OPTIONS')
        self.assertStatus(404)

    def test_parse_uri_fragment_uri(self):
        self.getPage('/hello?test=something#fake')
        self.assertStatus(400)
        self.assertBody(b'Illegal #fragment in Request-URI.')

    def test_no_content_length(self):
        # "The presence of a message-body in a request is signaled by the
        # inclusion of a Content-Length or Transfer-Encoding header field in
        # the request's message-headers."
        #
        # Send a message with neither header and no body.
        if self.scheme == 'https':
            c = HTTPSConnection('%s:%s' % (self.interface(), self.PORT))
        else:
            c = HTTPConnection('%s:%s' % (self.interface(), self.PORT))
        c.request('POST', '/no_body')
        response = c.getresponse()
        self.body = response.fp.read()
        self.status = str(response.status)
        self.assertStatus(200)
        self.assertBody(b'Hello world!')

    def test_content_length_required(self):
        # Now send a message that has no Content-Length, but does send a body.
        # Verify that CP times out the socket and responds
        # with 411 Length Required.

        if self.scheme == 'https':
            c = HTTPSConnection('%s:%s' % (self.interface(), self.PORT))
        else:
            c = HTTPConnection('%s:%s' % (self.interface(), self.PORT))
        c.request('POST', '/body_required')
        response = c.getresponse()
        self.body = response.fp.read()

        self.status = str(response.status)
        self.assertStatus(411)

    def test_malformed_request_line(self):
        # Test missing version in Request-Line

        if self.scheme == 'https':
            c = HTTPSConnection('%s:%s' % (self.interface(), self.PORT))
        else:
            c = HTTPConnection('%s:%s' % (self.interface(), self.PORT))
        c._output(b'GET /')
        c._send_output()
        if hasattr(c, 'strict'):
            response = c.response_class(c.sock, strict=c.strict, method='GET')
        else:
            # Python 3.2 removed the 'strict' feature, saying:
            # "http.client now always assumes HTTP/1.x compliant servers."
            response = c.response_class(c.sock, method='GET')
        response.begin()
        self.assertEqual(response.status, 400)
        self.assertEqual(response.fp.read(22), b'Malformed Request-Line')
        c.close()

    def test_malformed_http_method(self):

        if self.scheme == 'https':
            c = HTTPSConnection('%s:%s' % (self.interface(), self.PORT))
        else:
            c = HTTPConnection('%s:%s' % (self.interface(), self.PORT))
        c.putrequest('GeT', '/malformed_method_case')
        c.putheader('Content-Type', 'text/plain')
        c.endheaders()

        response = c.getresponse()
        self.status = str(response.status)
        self.assertStatus(400)
        self.body = response.fp.read(21)
        self.assertBody('Malformed method name')

    def test_malformed_header(self):

        if self.scheme == 'https':
            c = HTTPSConnection('%s:%s' % (self.interface(), self.PORT))
        else:
            c = HTTPConnection('%s:%s' % (self.interface(), self.PORT))
        c.putrequest('GET', '/')
        c.putheader('Content-Type', 'text/plain')
        # See http://www.bitbucket.org/cherrypy/cherrypy/issue/941
        c._output(b'Re, 1.2.3.4#015#012')
        c.endheaders()

        response = c.getresponse()
        self.status = str(response.status)
        self.assertStatus(400)
        self.body = response.fp.read(20)
        self.assertBody('Illegal header line.')

    def test_request_line_split_issue_1220(self):

        Request_URI = (
            '/hello?intervenant-entreprise-evenement_classaction=evenement-mailremerciements'
            '&_path=intervenant-entreprise-evenement&intervenant-entreprise-evenement_action-id=19404'
            '&intervenant-entreprise-evenement_id=19404&intervenant-entreprise_id=28092'
        )
        self.assertEqual(len('GET %s HTTP/1.1\r\n' % Request_URI), 256)
        self.getPage(Request_URI)
        self.assertBody('Hello world!')

    def test_garbage_in(self):
        # Connect without SSL regardless of server.scheme

        c = HTTPConnection('%s:%s' % (self.interface(), self.PORT))
        c._output(b'gjkgjklsgjklsgjkljklsg')
        c._send_output()
        response = c.response_class(c.sock, method='GET')
        try:
            response.begin()
            self.assertEqual(response.status, 400)
            self.assertEqual(response.fp.read(22), b'Malformed Request-Line')
            c.close()
        except socket.error as ex:
            # "Connection reset by peer" is also acceptable.
            if ex.errno != errno.ECONNRESET:
                raise
