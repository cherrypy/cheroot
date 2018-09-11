import pytest
import requests

class TestMore(object):

    def test_more_wsgi_server_one(self, crazy_wsgi_session):
        resp = crazy_wsgi_session.get('http://crazy_app/')
        print ("inside test_more_wsgi_server_one, response is {}".format(resp))
        assert 1 == 1
        assert 1 == 0
