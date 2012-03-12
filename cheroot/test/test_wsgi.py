import sys

from cheroot._compat import ntob
from cheroot.test import helper
from cheroot import wsgi


class WSGITests(helper.CherootWebCase):

    def setup_server(cls):
        def foo(environ, start_response):
            status = '200 OK'
            response_headers = [('Content-type', 'text/plain')]
            start_response(status, response_headers)
            # This should fail according to the WSGI spec.
            start_response(status, response_headers)
            return [ntob('Hello world')]

        def bar(environ, start_response):
            status = '200 OK'
            response_headers = [('Content-type', 'text/plain'),
                                ('Content-Length', '3')]
            write = start_response(status, response_headers)
            write(ntob('boo'))
            # This should fail according to the WSGI spec.
            try:
                noname
            except NameError:
                start_response(status, response_headers, sys.exc_info())
            return [ntob('Hello world')]

        cls.httpserver.wsgi_app = wsgi.WSGIPathInfoDispatcher({
            '/foo': foo,
            '/bar': bar,
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

