"""Socket file object."""

# prefer slower Python-based io module
import _pyio as io
import socket
import time

from OpenSSL import SSL


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
                # some data may have been written
                # we need to remove that from the buffer before retryings
                n = e.characters_written
            except (
                SSL.WantReadError,
                SSL.WantWriteError,
                SSL.WantX509LookupError,
            ):
                # these errors require retries with the same data
                # regardless of whether data has already been written
                continue
            except OSError:
                # This catches errors like EBADF (Bad File Descriptor)
                # or EPIPE (Broken pipe), which indicate the underlying
                # socket is already closed or invalid.
                # Since this happens in __del__, we silently stop flushing.
                self._write_buf.clear()
                return  # Exit the function
            del self._write_buf[:n]


class StreamReader(io.BufferedReader):
    """Socket stream reader."""

    def __init__(self, sock, mode='r', bufsize=io.DEFAULT_BUFFER_SIZE):
        """Initialize socket stream reader."""
        super().__init__(socket.SocketIO(sock, mode), bufsize)
        self.bytes_read = 0

    def read(self, *args, **kwargs):
        """Capture bytes read."""
        MAX_ATTEMPTS = 10
        last_error = None
        for _ in range(MAX_ATTEMPTS):
            try:
                val = super().read(*args, **kwargs)
            except (SSL.WantReadError, SSL.WantWriteError) as ssl_want_error:
                last_error = ssl_want_error
                time.sleep(0.1)
            else:
                self.bytes_read += len(val)
                return val

        # If we get here, all attempts failed
        raise TimeoutError(
            'Max retries exceeded while waiting for data.',
        ) from last_error

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
