import socket
import sys

if sys.version_info < (3,1):
    import io
else:
    import _pyio as io
DEFAULT_BUFFER_SIZE = io.DEFAULT_BUFFER_SIZE


class BufferedWriter(io.BufferedWriter):
    """Faux file object attached to a socket object."""

    def write(self, b):
        self._checkClosed()
        if isinstance(b, str):
            raise TypeError("can't write str to binary stream")
        
        with self._write_lock:
            self._write_buf.extend(b)
            self._flush_unlocked()
            return len(b)
    
    def _flush_unlocked(self):
        self._checkClosed("flush of closed file")
        while self._write_buf:
            try:
                # ssl sockets only except 'bytes', not bytearrays
                # so perhaps we should conditionally wrap this for perf?
                n = self.raw.write(bytes(self._write_buf))
            except io.BlockingIOError as e:
                n = e.characters_written
            del self._write_buf[:n]


def makefile(sock, mode='r', bufsize=DEFAULT_BUFFER_SIZE):
    if 'r' in mode:
        return io.BufferedReader(socket.SocketIO(sock, mode), bufsize)
    else:
        return BufferedWriter(socket.SocketIO(sock, mode), bufsize)

