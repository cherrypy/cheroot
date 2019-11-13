from cheroot.cli import (
    Application,
    parse_wsgi_bind_addr
)

def test_parse_wsgi_bind_location_for_tcpip():
    assert parse_wsgi_bind_addr('192.168.1.1:80') == ('192.168.1.1', 80)
    assert parse_wsgi_bind_addr('[::1]:8000') == ('::1', 8000)

def test_parse_wsgi_bind_location_for_unix_socket():
    assert parse_wsgi_bind_addr('/tmp/cheroot.sock') == '/tmp/cheroot.sock'

def test_parse_wsgi_bind_addr_for_abstract_unix_socket():
    assert parse_wsgi_bind_addr('@cheroot') == '\0cheroot'

def test_Aplication_resolve():
    import sys
    class WSGIAppMock:
        def application(self):
            pass

        def main(self):
            pass
    try:
        wsgi_app_mock = WSGIAppMock()
        sys.modules['mypkg.wsgi'] = wsgi_app_mock
        app = Application.resolve('mypkg.wsgi')
        assert app.wsgi_app == wsgi_app_mock.application
        app = Application.resolve('mypkg.wsgi:main')
        assert app.wsgi_app == wsgi_app_mock.main
    finally:
        del sys.modules['mypkg.wsgi']
