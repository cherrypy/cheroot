from cheroot.compat import ntob
from cheroot.test import helper
from cheroot import wsgi


class WSGIGraftTests(helper.CherootWebCase):

    def setup_server(cls):
        import os
        curdir = os.path.join(os.getcwd(), os.path.dirname(__file__))

        def test_app(environ, start_response):
            status = '200 OK'
            response_headers = [('Content-type', 'text/plain')]
            start_response(status, response_headers)
            output = ['Hello, world!\n',
                      'This is a wsgi app running within Cheroot!\n\n']
            keys = list(environ.keys())
            keys.sort()
            for k in keys:
                output.append('%s: %s\n' % (k, environ[k]))
            return [ntob(x, 'utf-8') for x in output]

        def test_empty_string_app(environ, start_response):
            status = '200 OK'
            response_headers = [('Content-type', 'text/plain')]
            start_response(status, response_headers)
            return [b'Hello', b'', b' ', b'', b'world']

        class WSGIResponse(object):

            def __init__(self, appresults):
                self.appresults = appresults
                self.iter = iter(appresults)

            def __iter__(self):
                return self

            def next(self):
                return self.iter.next()

            def __next__(self):
                return next(self.iter)

            def close(self):
                if hasattr(self.appresults, "close"):
                    self.appresults.close()

        class ReversingMiddleware(object):

            def __init__(self, app):
                self.app = app

            def __call__(self, environ, start_response):
                results = self.app(environ, start_response)

                class Reverser(WSGIResponse):

                    def next(this):
                        line = list(this.iter.next())
                        line.reverse()
                        return "".join(line)

                    def __next__(this):
                        line = list(next(this.iter))
                        line.reverse()
                        return bytes(line)
                return Reverser(results)

        class Root(helper.Controller):

            def normal(self, req, resp):
                return "I'm a regular Cheroot page handler!"

        cls.httpserver.wsgi_app = wsgi.WSGIPathInfoDispatcher({
            '/': Root(),
            '/hosted/app1': test_app,
            '/hosted/app3': test_empty_string_app,
            '/hosted/app2': ReversingMiddleware(Root()),
        })

    setup_server = classmethod(setup_server)

    wsgi_output = '''Hello, world!
This is a wsgi app running within Cheroot!'''

    def test_01_standard_app(self):
        self.getPage("/normal")
        self.assertBody("I'm a regular Cheroot page handler!")

    def test_04_pure_wsgi(self):
        self.getPage("/hosted/app1")
        self.assertHeader("Content-Type", "text/plain")
        self.assertInBody(self.wsgi_output)

    def test_05_wrapped_cp_app(self):
        self.getPage("/hosted/app2/normal")
        body = list("I'm a regular Cheroot page handler!")
        body.reverse()
        body = "".join(body)
        self.assertInBody(body)

    def test_06_empty_string_app(self):
        self.getPage("/hosted/app3")
        self.assertHeader("Content-Type", "text/plain")
        self.assertInBody('Hello world')
