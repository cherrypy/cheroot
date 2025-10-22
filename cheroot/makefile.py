"""Socket file object."""

# prefer slower Python-based io module
import _pyio as io
import socket

from . import errors as _errors


# Write only 16K at a time to sockets
SOCK_WRITE_BLOCKSIZE = 16384


class BufferedWriter(io.BufferedWriter):
    """Faux file object attached to a socket object."""

    def write(self, b):
        """Write bytes to buffer."""
        self._checkClosed()
        if isinstance(b, str):
            raise TypeError("can't write str to binary stream")

        with self._write_lock:
            self._write_buf.extend(b)
            self._flush_unlocked()
            return len(b)

    def _flush_unlocked(self):
        self._checkClosed('flush of closed file')
        while self._write_buf:
            try:
                # ssl sockets only except 'bytes', not bytearrays
                # so perhaps we should conditionally wrap this for perf?
                n = self.raw.write(bytes(self._write_buf))
            except io.BlockingIOError as e:
                n = e.characters_written

            if n == 0:
                # If nothing was written we need to break
                # to avoid infinte loops
                break

            del self._write_buf[:n]

    def close(self):
        """
        Close the stream and its underlying file object.

        This method is designed to be idempotent (it can be called multiple
        times without side effects). It gracefully handles a race condition
        where the underlying socket may have already been closed by the remote
        client or another thread.

        A :exc:`ConnectionError` or :exc:`OSError` with
        :data:`~errno.EBADF` or :data:`~errno.ENOTCONN` is caught
        and ignored, as these indicate a normal, expected connection teardown.
        Other exceptions are re-raised.
        """
        # pylint incorrectly flags inherited self.closed property as constant
        if self.closed:  # pylint: disable=using-constant-test
            return

        try:
            super().close()
        except _errors.acceptable_sock_shutdown_exceptions:
            return
        except ConnectionError:
            return
        except OSError as err:
            # Handle EBADF and other acceptable socket shutdown errors
            if err.errno in _errors.acceptable_sock_shutdown_error_codes:
                return
            raise


class StreamReader(io.BufferedReader):
    """Socket stream reader."""

    def __init__(self, sock, mode='r', bufsize=io.DEFAULT_BUFFER_SIZE):
        """Initialize socket stream reader."""
        super().__init__(socket.SocketIO(sock, mode), bufsize)
        self.bytes_read = 0

    def read(self, *args, **kwargs):
        """Capture bytes read."""
        val = super().read(*args, **kwargs)
        self.bytes_read += len(val)
        return val

    def has_data(self):
        """Return true if there is buffered data to read."""
        return len(self._read_buf) > self._read_pos


class StreamWriter(BufferedWriter):
    """Socket stream writer."""

    def __init__(self, sock, mode='w', bufsize=io.DEFAULT_BUFFER_SIZE):
        """Initialize socket stream writer."""
        super().__init__(socket.SocketIO(sock, mode), bufsize)
        self.bytes_written = 0

    def write(self, val, *args, **kwargs):
        """Capture bytes written."""
        res = super().write(val, *args, **kwargs)
        self.bytes_written += len(val)
        return res


def MakeFile(sock, mode='r', bufsize=io.DEFAULT_BUFFER_SIZE):
    """File object attached to a socket object."""
    cls = StreamReader if 'r' in mode else StreamWriter
    return cls(sock, mode, bufsize)
