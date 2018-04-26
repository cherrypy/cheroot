"""Command line tool for starting a Cheroot WSGI instance.

Basic usage::

    # Start a server on 127.0.0.1:8000 with the default settings
    # for the WSGI app myapp/wsgi.py:application()
    cheroot myapp.wsgi

    # Start a server on 0.0.0.0:9000 with 8 threads
    # for the WSGI app myapp/wsgi.py:main_app()
    cheroot myapp.wsgi:main_app --bind 0.0.0.0:9000 --threads 8

    # Start a server on the UNIX socket /var/spool/myapp.sock
    cheroot myapp.wsgi --bind /var/spool/myapp.sock

    # Start a server on the abstract UNIX socket CherootServer
    cheroot myapp.wsgi --bind @CherootServer
"""

import argparse
from importlib import import_module
import os
import sys

import six

from .wsgi import Server


def get_wsgi_app(wsgi_app_path):
    """Read WSGI app path string and import application module."""
    components = wsgi_app_path.split(':')
    if len(components) > 2:
        raise ValueError(
            'Application object name is invalid: it should not contain '
            'colon (:) character.'
        )
    elif len(components) == 2:
        mod_path, app_path = components[0], components[1]
    else:
        mod_path, app_path = wsgi_app_path, 'application'

    try:
        wsgi_app = getattr(import_module(mod_path), app_path)
        if not callable(wsgi_app):
            raise TypeError
    except ImportError as imp_err:
        six.raise_from(NameError('Failed to find a module: {}'.format(
            mod_path)), imp_err)
    except AttributeError as attr_err:
        six.raise_from(NameError(
            'Failed to find application object: {}'.format(app_path)), attr_err
        )
    except TypeError as type_err:
        six.raise_from(TypeError(
            'Application must be a callable object'), type_err
        )

    return wsgi_app


def parse_wsgi_bind_addr(bind_addr_string):
    """Convert bind address string to a tuple."""
    # try and match for an IP/hostname and port
    match = six.moves.urllib.parse.urlparse('//{}'.format(bind_addr_string))
    try:
        addr = match.hostname
        port = match.port
        if addr is not None or port is not None:
            return addr, port
    except ValueError:
        pass

    # else, assume a UNIX socket path
    # if the string begins with an @ symbol, use an abstract socket
    if bind_addr_string.startswith('@'):
        return '\0{}'.format(bind_addr_string[1:]), None
    return bind_addr_string, None


def main():
    """Create a new Cheroot instance with arguments from the command line."""
    parser = argparse.ArgumentParser(
        description='Start an instance of the Cheroot WSGI server.')
    parser.add_argument(
        '_wsgi_app', metavar='APP_MODULE',
        type=str,
        help='WSGI application callable to use')
    parser.add_argument(
        '--bind', metavar='ADDRESS',
        dest='_bind_addr', type=str,
        default='127.0.0.1:8000',
        help='Network interface to listen on (default: 127.0.0.1:8000)')
    parser.add_argument(
        '--chdir', metavar='PATH',
        dest='_chdir', default='.',
        help='Set the working directory')
    parser.add_argument(
        '--server-name',
        dest='server_name', type=str,
        help='Web server name to be advertised via Server HTTP header')
    parser.add_argument(
        '--threads', metavar='INT',
        dest='numthreads', type=int,
        help='Number of threads for WSGI thread pool')
    parser.add_argument(
        '--max-threads', metavar='INT',
        dest='max', type=int,
        help='Maximum number of worker threads')
    parser.add_argument(
        '--timeout', metavar='INT',
        dest='timeout', type=int,
        help='Timeout in seconds for accepted connections')
    parser.add_argument(
        '--shutdown-timeout', metavar='INT',
        dest='shutdown_timeout', type=int,
        help='Time in seconds to wait for worker threads to cleanly exit')
    parser.add_argument(
        '--request-queue-size', metavar='INT',
        dest='request_queue_size', type=int,
        help='Maximum number of queued connections')
    parser.add_argument(
        '--accepted-queue-size', metavar='INT',
        dest='accepted_queue_size', type=int,
        help='Maximum number of active requests in queue')
    parser.add_argument(
        '--accepted-queue-timeout', metavar='INT',
        dest='accepted_queue_timeout', type=int,
        help='Timeout in seconds for putting requests into queue')
    raw_args = parser.parse_args()

    # change directory if required
    chdir = os.path.abspath(raw_args._chdir)
    os.chdir(chdir)

    # add working directory to the path so module importing will resolve
    if chdir not in sys.path:
        sys.path.insert(0, chdir)

    # validate arguments
    wsgi_app = get_wsgi_app(raw_args._wsgi_app)
    addr, port = parse_wsgi_bind_addr(raw_args._bind_addr)
    if port is None:
        bind_addr = addr
    else:
        bind_addr = addr, port

    # create a Server object based on the arguments provided
    server_args = {
        'wsgi_app': wsgi_app,
        'bind_addr': bind_addr,
    }
    for arg, value in vars(raw_args).items():
        if not arg.startswith('_') and value is not None:
            server_args[arg] = value
    server = Server(**server_args)

    server.safe_start()


if __name__ == '__main__':
    main()
