"""Tests for managing HTTP issues (malformed requests, etc)."""

import errno
import mimetypes
import socket
import sys

import cheroot
from cheroot._compat import HTTPConnection, HTTPSConnection, ntob, py3k
from cheroot import wsgi

from cheroot.test import helper


class HTTPTests(helper.CherootWebCase):

    def setup_server(cls):
        class Root(helper.Controller):

            def hello(self, req, resp):
                return "Hello world!"
            
            def no_body(self, req, resp):
                return "Hello world!"

        cls.httpserver.wsgi_app = Root()
        cls.httpserver.max_request_body_size = 30000000
    setup_server = classmethod(setup_server)
    
    def test_normal_request(self):
        self.getPage("/hello")
        self.assertStatus(200)
        self.assertBody(ntob('Hello world!'))
    
    def test_no_content_length(self):
        # "The presence of a message-body in a request is signaled by the
        # inclusion of a Content-Length or Transfer-Encoding header field in
        # the request's message-headers."
        # 
        # Send a message with neither header and no body.
        if self.scheme == "https":
            c = HTTPSConnection('%s:%s' % (self.interface(), self.PORT))
        else:
            c = HTTPConnection('%s:%s' % (self.interface(), self.PORT))
        c.request("POST", "/no_body")
        response = c.getresponse()
        self.body = response.fp.read()
        self.status = str(response.status)
        self.assertStatus(200)
        self.assertBody(ntob('Hello world!'))
        
        # Now send a message that has no Content-Length, but does send a body.
        # Verify that CP times out the socket and responds
        # with 411 Length Required.
        if self.scheme == "https":
            c = HTTPSConnection('%s:%s' % (self.interface(), self.PORT))
        else:
            c = HTTPConnection('%s:%s' % (self.interface(), self.PORT))
        c.request("POST", "/")
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
        c._output(ntob('GET /'))
        c._send_output()
        if hasattr(c, 'strict'):
            response = c.response_class(c.sock, strict=c.strict, method='GET')
        else:
            # Python 3.2 removed the 'strict' feature, saying:
            # "http.client now always assumes HTTP/1.x compliant servers."
            response = c.response_class(c.sock, method='GET')
        response.begin()
        self.assertEqual(response.status, 400)
        self.assertEqual(response.fp.read(22), ntob("Malformed Request-Line"))
        c.close()

    def test_malformed_header(self):
        if self.scheme == 'https':
            c = HTTPSConnection('%s:%s' % (self.interface(), self.PORT))
        else:
            c = HTTPConnection('%s:%s' % (self.interface(), self.PORT))
        c.putrequest('GET', '/')
        c.putheader('Content-Type', 'text/plain')
        # See http://www.cherrypy.org/ticket/941 
        c._output(ntob('Re, 1.2.3.4#015#012'))
        c.endheaders()
        
        response = c.getresponse()
        self.status = str(response.status)
        self.assertStatus(400)
        self.body = response.fp.read(20)
        self.assertBody("Illegal header line.")
    
    def test_http_over_https(self):
        if self.scheme != 'https':
            return self.skip("skipped (not running HTTPS)... ")
        
        # Try connecting without SSL.
        conn = HTTPConnection('%s:%s' % (self.interface(), self.PORT))
        conn.putrequest("GET", "/", skip_host=True)
        conn.putheader("Host", self.HOST)
        conn.endheaders()
        response = conn.response_class(conn.sock, method="GET")
        try:
            response.begin()
            self.assertEqual(response.status, 400)
            self.body = response.read()
            self.assertBody("The client sent a plain HTTP request, but this "
                            "server only speaks HTTPS on this port.")
        except socket.error:
            e = sys.exc_info()[1]
            # "Connection reset by peer" is also acceptable.
            if e.errno != errno.ECONNRESET:
                raise

    def test_garbage_in(self):
        # Connect without SSL regardless of server.scheme
        c = HTTPConnection('%s:%s' % (self.interface(), self.PORT))
        c._output(ntob('gjkgjklsgjklsgjkljklsg'))
        c._send_output()
        response = c.response_class(c.sock, method="GET")
        try:
            response.begin()
            self.assertEqual(response.status, 400)
            self.assertEqual(response.fp.read(22), ntob("Malformed Request-Line"))
            c.close()
        except socket.error:
            e = sys.exc_info()[1]
            # "Connection reset by peer" is also acceptable.
            if e.errno != errno.ECONNRESET:
                raise

