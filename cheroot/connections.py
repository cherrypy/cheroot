from __future__ import absolute_import, division, print_function
__metaclass__ = type

import io
import select
import six
import socket
import time

from . import errors
from .makefile import MakeFile

from collections import OrderedDict


try:
    import fcntl
except ImportError:
    try:
        from ctypes import windll, WinError
        import ctypes.wintypes
        _SetHandleInformation = windll.kernel32.SetHandleInformation
        _SetHandleInformation.argtypes = [
            ctypes.wintypes.HANDLE,
            ctypes.wintypes.DWORD,
            ctypes.wintypes.DWORD,
        ]
        _SetHandleInformation.restype = ctypes.wintypes.BOOL
    except ImportError:
        def prevent_socket_inheritance(sock):
            """Stub inheritance prevention.

            Dummy function, since neither fcntl nor ctypes are available.
            """
            pass
    else:
        def prevent_socket_inheritance(sock):
            """Mark the given socket fd as non-inheritable (Windows)."""
            if not _SetHandleInformation(sock.fileno(), 1, 0):
                raise WinError()
else:
    def prevent_socket_inheritance(sock):
        """Mark the given socket fd as non-inheritable (POSIX)."""
        fd = sock.fileno()
        old_flags = fcntl.fcntl(fd, fcntl.F_GETFD)
        fcntl.fcntl(fd, fcntl.F_SETFD, old_flags | fcntl.FD_CLOEXEC)


class ConnectionManager:

    def __init__(self, server):
        self.server = server
        self.connections = OrderedDict()

    def put(self, conn):
        self.connections[conn] = time.time(), conn.rfile.has_data()

    def expire(self):
        if not self.connections:
            return

        # Check for too many open connections.
        conns = list(self.connections.items())
        if self.server.keep_alive_conn_limit is not None:
            [self.close(conn[0]) for conn in conns[:-self.server.keep_alive_conn_limit]]
            conns = conns[-self.server.keep_alive_conn_limit:]

        # Check for old connections.
        now = time.time()
        for (conn, (ctime, _)) in conns:
            # Oldest connection out of the currently available ones.
            if (ctime + self.server.timeout) < now:
                self.close(conn)
            else:
                break

    def get_conn(self, server_socket):

        # Grab file descriptors from sockets, but stop if we find a
        # connection which is already marked as ready.
        socket_dict = {}
        for conn, (tstamp, has_data) in self.connections.items():
            if has_data:
                break
            socket_dict[conn.socket.fileno()] = conn
        else:
            # No ready connection.
            conn = None

        # Will require a select call.
        if not conn:
            ss_fileno = server_socket.fileno()
            socket_dict[ss_fileno] = server_socket
            rlist, _, _ = select.select(list(socket_dict), [], [], 0.1)

            # No available socket.
            if not rlist:
                return None

            try:
                # See if we have a new connection coming in.
                rlist.remove(ss_fileno)
            except ValueError:
                # No new connection, but reuse existing socket.
                conn = socket_dict[rlist.pop()]
            else:
                conn = server_socket

            # All remaining connections in rlist should be added
            # to the ready queue.
            if rlist:
                socket_dict.update({
                    fno: (socket_dict[fno], True)
                    for fno in rlist
                })

            # New connection.
            if conn is server_socket:
                return self._from_server_socket(server_socket)

        del self.connections[conn]
        return conn

    def close(self, conn):
        del self.connections[conn]
        conn.close()

    def _from_server_socket(self, server_socket):
        try:
            s, addr = server_socket.accept()
            if self.server.stats['Enabled']:
                self.server.stats['Accepts'] += 1
            prevent_socket_inheritance(s)
            if hasattr(s, 'settimeout'):
                s.settimeout(self.server.timeout)

            mf = MakeFile
            ssl_env = {}
            # if ssl cert and key are set, we try to be a secure HTTP server
            if self.server.ssl_adapter is not None:
                try:
                    s, ssl_env = self.server.ssl_adapter.wrap(s)
                except errors.NoSSLError:
                    msg = (
                        'The client sent a plain HTTP request, but '
                        'this server only speaks HTTPS on this port.'
                    )
                    buf = [
                        '%s 400 Bad Request\r\n' % self.server.protocol,
                        'Content-Length: %s\r\n' % len(msg),
                        'Content-Type: text/plain\r\n\r\n',
                        msg,
                    ]

                    sock_to_make = s if not six.PY2 else s._sock
                    wfile = mf(sock_to_make, 'wb', io.DEFAULT_BUFFER_SIZE)
                    try:
                        wfile.write(''.join(buf).encode('ISO-8859-1'))
                    except socket.error as ex:
                        if ex.args[0] not in errors.socket_errors_to_ignore:
                            raise
                    return
                if not s:
                    return
                mf = self.server.ssl_adapter.makefile
                # Re-apply our timeout since we may have a new socket object
                if hasattr(s, 'settimeout'):
                    s.settimeout(self.server.timeout)

            conn = self.server.ConnectionClass(self.server, s, mf)

            if not isinstance(self.server.bind_addr, six.string_types):
                # optional values
                # Until we do DNS lookups, omit REMOTE_HOST
                if addr is None:  # sometimes this can happen
                    # figure out if AF_INET or AF_INET6.
                    if len(s.getsockname()) == 2:
                        # AF_INET
                        addr = ('0.0.0.0', 0)
                    else:
                        # AF_INET6
                        addr = ('::', 0)
                conn.remote_addr = addr[0]
                conn.remote_port = addr[1]

            conn.ssl_env = ssl_env
            return conn

        except socket.timeout:
            # The only reason for the timeout in start() is so we can
            # notice keyboard interrupts on Win32, which don't interrupt
            # accept() by default
            return
        except socket.error as ex:
            if self.server.stats['Enabled']:
                self.server.stats['Socket Errors'] += 1
            if ex.args[0] in errors.socket_error_eintr:
                # I *think* this is right. EINTR should occur when a signal
                # is received during the accept() call; all docs say retry
                # the call, and I *think* I'm reading it right that Python
                # will then go ahead and poll for and handle the signal
                # elsewhere. See
                # https://github.com/cherrypy/cherrypy/issues/707.
                return
            if ex.args[0] in errors.socket_errors_nonblocking:
                # Just try again. See
                # https://github.com/cherrypy/cherrypy/issues/479.
                return
            if ex.args[0] in errors.socket_errors_to_ignore:
                # Our socket was closed.
                # See https://github.com/cherrypy/cherrypy/issues/686.
                return
            raise
