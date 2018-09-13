import pytest
import requests
import ssl
from cheroot.ssl.builtin import BuiltinSSLAdapter

class TestMore(object):

    def test_more_wsgi_server_one(self, crazy_wsgi_session):
        resp = crazy_wsgi_session.get('http://crazy_app/')
        print ("inside test_more_wsgi_server_one, response is {}".format(resp))
        assert 1 == 1
        assert 1 == 0

    def test_more_wsgi_server_two(self, crazy_wsgi_https_session):
        resp = crazy_wsgi_https_session.get('https://crazy_app2/')
        print ("inside test_more_wsgi_server_two, response is {}".format(resp))
        assert 1 == 1
        assert 1 == 0

    def test_more_wsgi_server_three(self, make_session_for_cheroot):
        ssl_adapter = BuiltinSSLAdapter(
            certificate='test/ssl/server.cert',
            private_key='test/ssl/server.key',
            certificate_chain='test/ssl/ca.cert'
        )
        ssl_adapter.context.verify_mode = ssl.CERT_NONE
        my_session = make_session_for_cheroot(prefix="https://try_this", ssl_adapter=ssl_adapter)
        resp = my_session.get("https://try_this")
        print("inside test_more_wsgi_server_three, response code is {}".format(resp))
        print("inside test_more_wsgi_server_three, response text is:{}".format(resp.text))
        assert 1 == 1
        assert 1 == 0
