import threading
import typing as _t

__all__ = ('ThreadPool', 'WorkerThread')

class TrueyZero:
    def __add__(self, other): ...
    def __radd__(self, other): ...

trueyzero: TrueyZero

class _ShrinkRequest:
    taken: bool
    cancelled: bool

class WorkerThread(threading.Thread):
    conn: _t.Any
    server: _t.Any
    ready: bool
    _retiring: bool
    requests_seen: int
    bytes_read: int
    bytes_written: int
    start_time: _t.Any
    work_time: int
    stats: _t.Any
    def __init__(self, server): ...
    def run(self) -> None: ...
    def _get_request(self) -> _t.Any: ...

class ThreadPool:
    server: _t.Any
    min: _t.Any
    max: _t.Any
    get: _t.Any
    _lock: threading.Lock
    _shutdowns_due: int
    def __init__(
        self,
        server,
        min: int = ...,
        max: int = ...,
        accepted_queue_size: int = ...,
        accepted_queue_timeout: int = ...,
    ) -> None: ...
    def start(self) -> None: ...
    @property
    def idle(self): ...
    def put(self, obj) -> None: ...
    def grow(self, amount) -> None: ...
    def shrink(self, amount) -> None: ...
    def _serving(self) -> list[WorkerThread]: ...
    def _cancel(self, requests: list[_ShrinkRequest]) -> None: ...
    def _retires(
        self,
        worker: WorkerThread,
        request: _ShrinkRequest,
    ) -> bool: ...
    def stop(self, timeout: int = ...) -> None: ...
    @property
    def qsize(self) -> int: ...
