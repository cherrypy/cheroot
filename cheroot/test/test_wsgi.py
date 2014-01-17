import sys

from cheroot.test import helper
from cheroot import wsgi


class WSGITests(helper.CherootWebCase):

    def setup_server(cls):

        def hello(environ, start_response):
            status = '200 OK'
            response_headers = [('Content-type', 'text/plain'),
                                ('Content-Length', '11')]
            start_response(status, response_headers)
            return [b'Hello world']

        def foo(environ, start_response):
            status = '200 OK'
            response_headers = [('Content-type', 'text/plain')]
            start_response(status, response_headers)
            # This should fail according to the WSGI spec.
            start_response(status, response_headers)
            return [b'Hello world']

        def bar(environ, start_response):
            status = '200 OK'
            response_headers = [('Content-type', 'text/plain'),
                                ('Content-Length', '3')]
            write = start_response(status, response_headers)
            write(b'boo')
            # This should fail according to the WSGI spec.
            try:
                noname
            except NameError:
                start_response(status, response_headers, sys.exc_info())
            return [b'Hello world']

        def baz(environ, start_response):
            status = 200
            response_headers = [('Content-type', 'text/plain')]
            # This should fail because status is not a str
            start_response(status, response_headers)
            return [b'Hello world']

        def qoph(environ, start_response):
            status = '200 OK'
            response_headers = [('Content-type', 5)]
            # This should fail because the response header value is not a str
            start_response(status, response_headers)
            return [b'Hello world']

        cls.httpserver.wsgi_app = wsgi.WSGIPathInfoDispatcher({
            '/foo': foo,
            '/bar': bar,
            '/baz': baz,
            '/qoph': qoph,
            '/hello': hello,
        })
    setup_server = classmethod(setup_server)

    def test_start_response_twice_no_exc_info(self):
        self.getPage("/foo")
        self.assertStatus(500)
        self.assertInLog(
            "WSGI start_response called a second time with no exc_info.")

    def test_start_response_with_exc_info_after_headers(self):
        self.getPage("/bar")
        # Note that the failure in this case occurs after the response
        # has been written out, so we don't get a 500...
        self.assertStatus(200)
        # But we still get a logged error :)
        self.assertInLog(
            "WSGI start_response called a second time with no exc_info.")

    def test_nonstring_status(self):
        self.getPage("/baz")
        self.assertStatus(500)
        self.assertInLog(
            "WSGI response status is not of type str.")

    def test_nonstring_header_value(self):
        self.getPage("/qoph")
        self.assertStatus(500)
        self.assertInLog(
            "WSGI response header value %s is not of type str." % repr(5))

    def test_notfound(self):
        self.getPage("/tev")
        self.assertStatus(404)

    def test_gateway_u0(self):
        old_gw = self.httpserver.gateway
        self.httpserver.gateway = wsgi.WSGIGateway_u0
        try:
            self.getPage("/hello")
            self.assertStatus(200)
        finally:
            self.httpserver.gateway = old_gw
