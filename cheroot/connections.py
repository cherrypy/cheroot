"""Utilities to manage open connections."""

from __future__ import absolute_import, division, print_function
__metaclass__ = type

import collections
import io
import os
import socket
import time
import threading

from . import errors
from ._compat import selectors
from ._compat import suppress
from .makefile import MakeFile

import six

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


class _SelectorManager:
    """Private wrapper of a selectors.DefaultSelector instance.

    Manage an external set of the keys that can be copied to be
    safely iterated, in addition it implements some convenient
    wrappers given the use that we have in the
    ``ConnectionManager`` class  of the ``DefaultSelector`` instance.

    The locking mechanism in this class is not strictly required
    (if we make sure we don't register/unregister any fd concurrently
    from a copy of the internal keys), but currently is the most
    stable approach.
    """

    def __init__(self):
        self._selector = selectors.DefaultSelector()
        self._selector_keys = set([])
        # The use of the lock shouldn't be necessary...
        # but in practice it is.
        #
        # TODO: make sure we have a good understanding on how the
        # Selectors instances are meant to be managed in a
        # threaded context.
        #
        # Without the lock the tests start to fail of retring to
        # delete the same key. This could be the case if two
        # threads having differents copies of the keys tries to
        # unregister the same key.
        self._register_lock = threading.Lock()

    def __len__(self):
        return len(self._selector_keys)

    def __iter__(self):
        """Return an interator over a copy of the active SelectorKeys.

        Specifically we use a copy to be able to freely use
        `register` and `unregister` while iterating over the keys.

        The underlying Selectors instance doesn't provide a public
        mapping that can be copied without iterating all over
        the values because it implements the Mapping interface from two
        underlying dicts.
        """
        return iter(self._selector_keys.copy())

    @property
    def connections(self):
        return iter(sk.data for sk in self)

    def register(self, fileobj, events, data=None):
        with self._register_lock:
            key = self._selector.register(fileobj, events, data)
            self._selector_keys.add(key)

    def unregister(self, fileobj):
        with self._register_lock:
            key = self._selector.unregister(fileobj)
            self._selector_keys.remove(key)

    def select(self, timeout=None):
        """Return a list of the connections with events in the form:
        (connection, socket_file_descriptor)
        """
        return [
            (key.data, key.fd)
            for key, _ in self._selector.select(timeout=timeout)
        ]

    def close(self):
        self._selector.close()


class ConnectionManager:
    """Class which manages HTTPConnection objects.

    This is for connections which are being kept-alive for follow-up requests.
    """

    def __init__(self, server):
        """Initialize ConnectionManager object.

        Args:
            server (cheroot.server.HTTPServer): web server object
                that uses this ConnectionManager instance.
        """
        self.server = server
        self._readable_conns = collections.deque()
        self._selector_mgr = _SelectorManager()
        self._selector_mgr.register(
            server.socket.fileno(),
            selectors.EVENT_READ,
            data=server
        )

    def put(self, conn):
        """Put idle connection into the ConnectionManager to be managed.

        Args:
            conn (cheroot.server.HTTPConnection): HTTP connection
                to be managed.
        """
        conn.last_used = time.time()
        # if this conn doesn't have any more data waiting to be read,
        # register it with the selector.
        if conn.rfile.has_data():
            self._readable_conns.append(conn)
        else:
            self._selector_mgr.register(
                conn.socket.fileno(), selectors.EVENT_READ, data=conn,
            )

    def expire(self):
        """Expire least recently used connections.

        This happens if there are either too many open connections, or if the
        connections have been timed out.

        This should be called periodically.
        """
        # find any connections still registered with the selector
        # that have not been active recently enough.
        threshold = time.time() - self.server.timeout
        for (_, sock_fd, _, conn) in self._selector_mgr:
            if conn is not self.server and conn.last_used < threshold:
                self._selector_mgr.unregister(sock_fd)
                conn.close()

    def get_conn(self):  # noqa: C901  # FIXME
        """Return a HTTPConnection object which is ready to be handled.

        A connection returned by this method should be ready for a worker
        to handle it. If there are no connections ready, None will be
        returned.

        Any connection returned by this method will need to be `put`
        back if it should be examined again for another request.

        Returns:
            cheroot.server.HTTPConnection instance, or None.

        """
        # return a readable connection if any exist
        with suppress(IndexError):
            return self._readable_conns.popleft()

        # Will require a select call.
        try:
            # The timeout value impacts performance and should be carefully
            # chosen. Ref:
            # github.com/cherrypy/cheroot/issues/305#issuecomment-663985165
            conn_ready_list = self._selector_mgr.select(timeout=0.01)
        except OSError:
            # Mark any connection which no longer appears valid
            for (_, sock_fd, _, conn) in self._selector_mgr:
                # If the server socket is invalid, we'll just ignore it and
                # wait to be shutdown.
                if conn is self.server:
                    continue

                try:
                    os.fstat(sock_fd)
                except OSError:
                    # Unregister and close all the invalid connections.
                    self._selector_mgr.unregister(sock_fd)
                    conn.close()

            # Wait for the next tick to occur.
            return None

        for (conn, sock_fd) in conn_ready_list:
            if conn is self.server:
                # New connection
                return self._from_server_socket(self.server.socket)

            # unregister connection from the selector until the server
            # has read from it and returned it via put()
            self._selector_mgr.unregister(sock_fd)
            self._readable_conns.append(conn)

        try:
            return self._readable_conns.popleft()
        except IndexError:
            return None

    def _from_server_socket(self, server_socket):  # noqa: C901  # FIXME
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

            if not isinstance(
                    self.server.bind_addr,
                    (six.text_type, six.binary_type),
            ):
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

    def close(self):
        """Close all monitored connections."""
        for conn in self._readable_conns:
            conn.close()
        self._readable_conns.clear()
        for conn in self._selector_mgr.connections:
            # Server closes its own socket.
            if conn is not self.server:
                conn.socket.close()

        self._selector_mgr.close()

    @property
    def _num_connections(self):  # noqa: D401
        """The current number of connections.

        Includes any in the readable list or registered with the selector,
        minus one for the server socket, which is always registered
        with the selector.
        """
        return len(self._readable_conns) + len(self._selector_mgr) - 1

    @property
    def can_add_keepalive_connection(self):
        """Flag whether it is allowed to add a new keep-alive connection."""
        ka_limit = self.server.keep_alive_conn_limit
        return ka_limit is None or self._num_connections < ka_limit
