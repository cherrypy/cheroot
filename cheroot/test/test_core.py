"""Basic tests for the Cheroot server: request handling."""

from cheroot._compat import ntob
from cheroot.test import helper


class CoreRequestHandlingTest(helper.CherootWebCase):

    def setup_server(cls):
        class Root(helper.Controller):

            def hello(self):
                return "hello"

            def normal(self, req, resp):
                return "normal"
            
            def blank(self, req, resp):
                resp.status = ""
                return ""
            
            # According to RFC 2616, new status codes are OK as long as they
            # are between 100 and 599.
            
            # Here is an illegal code...
            def illegal(self, req, resp):
                resp.status = '781'
                return "oops"
            
            # ...and here is an unknown but legal code.
            def unknown(self, req, resp):
                resp.status = "431 My custom error"
                return "funky"
            
            # Non-numeric code
            def bad(self, req, resp):
                resp.status = "error"
                return "bad news"

            def header_list(self, req, resp):
                # helper.Controller.__call__ will transform this into
                # multiple headers with the same name, which is what
                # we're trying to test
                resp.headers['WWW-Authenticate'] = [
                    'Negotiate','Basic realm="foo"']
                return ""
            
            def commas(self, req, resp):
                resp.headers['WWW-Authenticate'] = 'Negotiate,Basic realm="foo"'
                return ""

            def start_response_error(self, req, resp):
                resp.headers[2] = 3
                return "salud!"

        cls.httpserver.wsgi_app = Root()
    setup_server = classmethod(setup_server)

    def test_status_normal(self):
        self.getPage("/normal")
        self.assertBody('normal')
        self.assertStatus(200)

    def test_status_blank(self):
        self.getPage("/blank")
        self.assertStatus(200)

    def test_status_illegal(self):
        self.getPage("/illegal")
        self.assertStatus(500)
        self.assertInBody(
            "Illegal response status from server (781 is out of range).")

    def test_status_unknown(self):
        self.getPage("/unknown")
        self.assertBody('funky')
        self.assertStatus(431)

    def test_status_syntax_error(self):
        self.getPage("/bad")
        self.assertStatus(500)
        self.assertStatus(500)
        self.assertInBody(
            "Illegal response status from server (%s is non-numeric)." %
            (repr(ntob('error'))))

    def test_multiple_headers(self):
        self.getPage('/header_list')
        self.assertEqual([(k, v) for k, v in self.headers if k == 'WWW-Authenticate'],
                         [('WWW-Authenticate', 'Negotiate'),
                          ('WWW-Authenticate', 'Basic realm="foo"'),
                          ])
        self.getPage('/commas')
        self.assertHeader('WWW-Authenticate', 'Negotiate,Basic realm="foo"')

    def test_start_response_error(self):
        self.getPage("/start_response_error")
        self.assertStatus(500)
        self.assertInBody("TypeError: WSGI response header key 2 is not of type str.")

