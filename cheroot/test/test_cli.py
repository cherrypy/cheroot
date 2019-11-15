"""Tests to verify the command line interface."""
# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :
import sys

import six
import pytest

from cheroot.cli import (
    Application,
    parse_wsgi_bind_addr,
)


@pytest.mark.parametrize(
    'raw_bind_addr, expected_bind_addr', (
        ('192.168.1.1:80', ('192.168.1.1', 80)),
        ('[::1]:8000', ('::1', 8000)),
    ),
)
def test_parse_wsgi_bind_addr_for_tcpip(raw_bind_addr, expected_bind_addr):
    """Check the parsing of the --bind option for TCP/IP addresses."""
    assert parse_wsgi_bind_addr(raw_bind_addr) == expected_bind_addr


def test_parse_wsgi_bind_addr_for_unix_socket():
    """Check the parsing of the --bind option for UNIX Sockets."""
    assert parse_wsgi_bind_addr('/tmp/cheroot.sock') == '/tmp/cheroot.sock'


def test_parse_wsgi_bind_addr_for_abstract_unix_socket():
    """Check the parsing of the --bind option for Abstract UNIX Sockets."""
    assert parse_wsgi_bind_addr('@cheroot') == '\0cheroot'


class WSGIAppMock:
    """Mock of a wsgi module."""

    def application(self):
        """Empty application method.

        Default method to be called when no specific callable
        is defined in the wsgi application identifier.

        It has an empty body because we are expecting to verify that
        the same method is return no the actual execution of it.
        """

    def main(self):
        """Empty custom method (callable) inside the mocked WSGI app.

        It has an empty body because we are expecting to verify that
        the same method is return no the actual execution of it.
        """


@pytest.mark.parametrize(
    'wsgi_app_spec, pkg_name, app_method, mocked_app', (
        ('mypkg.wsgi', 'mypkg.wsgi', 'application', WSGIAppMock()),
        ('mypkg.wsgi:application', 'mypkg.wsgi', 'application', WSGIAppMock()),
        ('mypkg.wsgi:main', 'mypkg.wsgi', 'main', WSGIAppMock()),
    ),
)
def test_Aplication_resolve(
    monkeypatch,
    wsgi_app_spec, pkg_name, app_method, mocked_app,
):
    """Check the wsgi application name conversion."""
    if six.PY2:
        # python2 requires the previous namespaces to be part of sys.modules
        #   (e.g. for 'a.b.c' we need to insert 'a', 'a.b' and 'a.b.c')
        # otherwise it fails, we're setting the same instance on each level,
        # we don't really care about those, just the last one.
        full_path = None
        for p in pkg_name.split('.'):
            full_path = p if full_path is None else '.'.join((full_path, p))
            monkeypatch.setitem(sys.modules, full_path, mocked_app)
    else:
        monkeypatch.setitem(sys.modules, pkg_name, mocked_app)
    expected_app = getattr(mocked_app, app_method)
    assert Application.resolve(wsgi_app_spec).wsgi_app == expected_app
