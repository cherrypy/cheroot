import typing as _t

def suppress(
    *exceptions: _t.Type[BaseException],
) -> _t.ContextManager[None]: ...

IS_ABOVE_OPENSSL10: bool | None
IS_ABOVE_OPENSSL31: bool | None
IS_CI: bool
IS_GITHUB_ACTIONS_WORKFLOW: bool
IS_PYPY: bool
SYS_PLATFORM: str
IS_WINDOWS: bool
IS_LINUX: bool
IS_MACOS: bool
IS_SOLARIS: bool
PLATFORM_ARCH: str
IS_PPC: bool

def ntob(n: str, encoding: str = ...) -> bytes: ...
def ntou(n: str, encoding: str = ...) -> str: ...
def bton(b: bytes, encoding: str = ...) -> str: ...
def assert_native(n: str) -> None: ...
def extract_bytes(mv: memoryview | bytes) -> bytes: ...
