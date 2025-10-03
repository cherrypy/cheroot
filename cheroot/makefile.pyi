import io
import sys
from typing import Optional

WSAENOTSOCK: Optional[int]

SOCK_WRITE_BLOCKSIZE: int

if sys.platform == 'win32':
    WIN_SOCKET_NOT_OPEN: Optional[int]

class BufferedWriter(io.BufferedWriter):
    def write(self, b): ...

class StreamReader(io.BufferedReader):
    bytes_read: int
    def __init__(self, sock, mode: str = ..., bufsize=...) -> None: ...
    def read(self, *args, **kwargs): ...
    def has_data(self): ...

class StreamWriter(BufferedWriter):
    bytes_written: int
    def __init__(self, sock, mode: str = ..., bufsize=...) -> None: ...
    def write(self, val, *args, **kwargs): ...

def MakeFile(sock, mode: str = ..., bufsize=...): ...
