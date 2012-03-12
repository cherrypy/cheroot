from cheroot._compat import ntob
from cheroot.test import helper
from cheroot import wsgi


class WSGITests(helper.CherootWebCase):

    def setup_server(cls):
        def test_start_response_twice_no_exc_info(environ, start_response):
            status = '200 OK'
            response_headers = [('Content-type', 'text/plain')]
            start_response(status, response_headers)
            start_response(status, response_headers)
            return [ntob('Hello'), ntob(''), ntob(' '), ntob(''), ntob('world')]

        cls.httpserver.wsgi_app = wsgi.WSGIPathInfoDispatcher({
            '/start_response_twice_no_exc_info': test_start_response_twice_no_exc_info,
            })
    setup_server = classmethod(setup_server)

    def test_start_response_twice_no_exc_info(self):
        self.getPage("/start_response_twice_no_exc_info")
        self.assertStatus(500)
        self.assertInLog(
            "WSGI start_response called a second time with no exc_info.")

