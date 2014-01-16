"""A high-speed, production ready, thread pooled, generic HTTP server.

Simplest example on how to use this module directly::

    import cheroot

    def my_crazy_app(environ, start_response):
        status = '200 OK'
        response_headers = [('Content-type','text/plain')]
        start_response(status, response_headers)
        return ['Hello world!']

    server = wsgi.WSGIServer(
                ('0.0.0.0', 8070),
                server_name='www.cheroot.example',
                wsgi_app=my_crazy_app)
    server.start()

The Cheroot HTTP server can serve as many WSGI applications
as you want in one instance by using a WSGIPathInfoDispatcher::

    d = wsgi.WSGIPathInfoDispatcher({'/': my_crazy_app, '/blog': my_blog_app})
    server = wsgi.WSGIServer(('0.0.0.0', 80), wsgi_app=d)

Want SSL support? Just set server.ssl_adapter to an SSLAdapter instance.
"""

__version__ = "4.0.0beta"
