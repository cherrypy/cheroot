import io

# this variable is only needed in Windows environments
# and is an int in those cases
# but mypy stubtest fails when adding a guard such as
# if sys.platform == 'win32' or setting is as int
WSAENOTSOCK: None

SOCK_WRITE_BLOCKSIZE: int

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
