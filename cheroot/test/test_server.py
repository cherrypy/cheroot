"""Tests for the HTTP server."""

from __future__ import annotations

import contextlib
import gc
import os
import pathlib
import queue
import socket
import subprocess
import sys
import tempfile
import threading
import time
import types
import typing as _t
import urllib.parse  # noqa: WPS301
import uuid
from http import HTTPStatus

import pytest

import requests
import requests_unixsocket

from .._compat import IS_LINUX, IS_MACOS, IS_WINDOWS, SYS_PLATFORM, bton, ntob
from ..server import IS_UID_GID_RESOLVABLE, Gateway, HTTPServer
from ..testing import (
    ANY_INTERFACE_IPV4,
    ANY_INTERFACE_IPV6,
    EPHEMERAL_PORT,
    SUCCESSFUL_SUBPROCESS_EXIT,
)
from ..workers.threadpool import ThreadPool, WorkerThread


IS_SLOW_ENV = IS_MACOS or IS_WINDOWS
PY38_OR_LOWER = sys.version_info[:2] <= (3, 8)


unix_only_sock_test = pytest.mark.skipif(
    not hasattr(socket, 'AF_UNIX'),
    reason='UNIX domain sockets are only available under UNIX-based OS',
)


non_macos_sock_test = pytest.mark.skipif(
    IS_MACOS,
    reason='Peercreds lookup does not work under macOS/BSD currently.',
)


def _wait_until(
    *,
    compute_condition: _t.Callable[[], bool],
    timeout: float = 10,
) -> bool:
    """Wait until the condition is true or the timeout expires."""
    deadline = time.monotonic() + timeout
    while not compute_condition() and time.monotonic() < deadline:
        time.sleep(0.05)
    return compute_condition()


@pytest.fixture(params=('abstract', 'file'))
def unix_sock_file(request):
    """Check that bound UNIX socket address is stored in server."""
    if PY38_OR_LOWER:
        # FIXME: This can be dropped together with Python 3.8.
        # FIXME: It's coming from `trustme < 1.2.0` as newer versions
        # FIXME: fixed the compatibility but dropped Python 3.8 support.
        pytest.skip('`requests-unixsocket` is defunct under Python 3.8')
    name = 'unix_{request.param}_sock'.format(**locals())
    return request.getfixturevalue(name)


@pytest.fixture
def unix_abstract_sock():
    """Return an abstract UNIX socket address."""
    if not IS_LINUX:
        pytest.skip(
            f'{SYS_PLATFORM} does not support an abstract socket namespace',
        )
    return b''.join(
        (
            b'\x00cheroot-test-socket',
            ntob(str(uuid.uuid4())),
        ),
    ).decode()


@pytest.fixture
def unix_file_sock():
    """Yield a UNIX file socket."""
    tmp_sock_fh, tmp_sock_fname = tempfile.mkstemp()

    yield tmp_sock_fname

    os.close(tmp_sock_fh)
    os.unlink(tmp_sock_fname)


def _make_server(
    server_class: type[HTTPServer] = HTTPServer,
    *,
    minthreads: int = 10,
) -> HTTPServer:
    """Make a server on an ephemeral port, without starting it."""
    return server_class(
        bind_addr=(ANY_INTERFACE_IPV4, EPHEMERAL_PORT),
        gateway=Gateway,
        minthreads=minthreads,
    )


def test_prepare_makes_server_ready():
    """Check that prepare() makes the server ready, and stop() clears it."""
    httpserver = HTTPServer(
        bind_addr=(ANY_INTERFACE_IPV4, EPHEMERAL_PORT),
        gateway=Gateway,
    )

    assert not httpserver.ready
    assert not httpserver.requests._threads

    httpserver.prepare()

    assert httpserver.ready
    assert httpserver.requests._threads
    for thr in httpserver.requests._threads:
        assert thr.ready

    httpserver.stop()

    assert not httpserver.requests._threads
    assert not httpserver.ready


def test_stop_interrupts_serve():
    """Check that stop() interrupts running of serve()."""
    httpserver = HTTPServer(
        bind_addr=(ANY_INTERFACE_IPV4, EPHEMERAL_PORT),
        gateway=Gateway,
    )

    httpserver.prepare()
    serve_thread = threading.Thread(target=httpserver.serve)
    serve_thread.start()

    serve_thread.join(0.5)
    assert serve_thread.is_alive()

    httpserver.stop()

    serve_thread.join(0.5)
    assert not serve_thread.is_alive()


@pytest.mark.parametrize(
    'exc_cls',
    (
        IOError,
        KeyboardInterrupt,
        OSError,
        RuntimeError,
    ),
)
def test_server_interrupt(exc_cls):
    """Check that assigning interrupt stops the server."""
    interrupt_msg = f'should catch {uuid.uuid4()!s}'
    raise_marker_sentinel = object()

    httpserver = HTTPServer(
        bind_addr=(ANY_INTERFACE_IPV4, EPHEMERAL_PORT),
        gateway=Gateway,
    )

    result_q = queue.Queue()

    def serve_thread():
        # ensure we catch the exception on the serve() thread
        try:
            httpserver.serve()
        except exc_cls as e:
            if str(e) == interrupt_msg:
                result_q.put(raise_marker_sentinel)

    httpserver.prepare()
    serve_thread = threading.Thread(target=serve_thread)
    serve_thread.start()

    serve_thread.join(0.5)
    assert serve_thread.is_alive()

    # this exception is raised on the serve() thread,
    # not in the calling context.
    httpserver.interrupt = exc_cls(interrupt_msg)

    serve_thread.join(0.5)
    assert not serve_thread.is_alive()
    assert result_q.get_nowait() is raise_marker_sentinel


def test_serving_is_false_and_stop_returns_after_ctrlc():
    """Check that stop() interrupts running of serve()."""
    httpserver = HTTPServer(
        bind_addr=(ANY_INTERFACE_IPV4, EPHEMERAL_PORT),
        gateway=Gateway,
    )

    httpserver.prepare()

    # Simulate a Ctrl-C on the first call to `run`.
    def raise_keyboard_interrupt(*args, **kwargs):
        raise KeyboardInterrupt

    httpserver._connections._selector.select = raise_keyboard_interrupt

    serve_thread = threading.Thread(target=httpserver.serve)
    serve_thread.start()

    # The thread should exit right away due to the interrupt.
    serve_thread.join(
        httpserver.expiration_interval * (4 if IS_SLOW_ENV else 2),
    )
    assert not serve_thread.is_alive()

    assert not httpserver._connections._serving
    httpserver.stop()


@pytest.mark.parametrize(
    'ip_addr',
    (
        ANY_INTERFACE_IPV4,
        ANY_INTERFACE_IPV6,
    ),
)
def test_bind_addr_inet(http_server, ip_addr):
    """Check that bound IP address is stored in server."""
    httpserver = http_server.send((ip_addr, EPHEMERAL_PORT))

    assert httpserver.bind_addr[0] == ip_addr
    assert httpserver.bind_addr[1] != EPHEMERAL_PORT


@unix_only_sock_test
def test_bind_addr_unix(http_server, unix_sock_file):
    """Check that bound UNIX socket address is stored in server."""
    httpserver = http_server.send(unix_sock_file)

    assert httpserver.bind_addr == unix_sock_file


@unix_only_sock_test
def test_bind_addr_unix_abstract(http_server, unix_abstract_sock):
    """Check that bound UNIX abstract socket address is stored in server."""
    httpserver = http_server.send(unix_abstract_sock)

    assert httpserver.bind_addr == unix_abstract_sock


PEERCRED_IDS_URI = '/peer_creds/ids'
PEERCRED_TEXTS_URI = '/peer_creds/texts'


class _TestGateway(Gateway):
    def respond(self):
        req = self.req
        conn = req.conn
        req_uri = bton(req.uri)
        if req_uri == PEERCRED_IDS_URI:
            peer_creds = conn.peer_pid, conn.peer_uid, conn.peer_gid
            self.send_payload('|'.join(map(str, peer_creds)))
            return None
        if req_uri == PEERCRED_TEXTS_URI:
            self.send_payload('!'.join((conn.peer_user, conn.peer_group)))
            return None
        return super(_TestGateway, self).respond()

    def send_payload(self, payload):
        req = self.req
        req.status = b'200 OK'
        req.ensure_headers_sent()
        req.write(ntob(payload))


@pytest.fixture
def peercreds_enabled_server(http_server, unix_sock_file):
    """Construct a test server with ``peercreds_enabled``."""
    httpserver = http_server.send(unix_sock_file)
    httpserver.gateway = _TestGateway
    httpserver.peercreds_enabled = True
    return httpserver


@unix_only_sock_test
@non_macos_sock_test
@pytest.mark.flaky(reruns=3, reruns_delay=2)
def test_peercreds_unix_sock(http_request_timeout, peercreds_enabled_server):
    """Check that ``PEERCRED`` lookup works when enabled."""
    httpserver = peercreds_enabled_server
    bind_addr = httpserver.bind_addr

    if isinstance(bind_addr, bytes):
        bind_addr = bind_addr.decode()

    # pylint: disable=possibly-unused-variable
    quoted = urllib.parse.quote(bind_addr, safe='')
    unix_base_uri = 'http+unix://{quoted}'.format(**locals())

    expected_peercreds = os.getpid(), os.getuid(), os.getgid()
    expected_peercreds = '|'.join(map(str, expected_peercreds))

    with requests_unixsocket.monkeypatch():
        peercreds_resp = requests.get(
            unix_base_uri + PEERCRED_IDS_URI,
            timeout=http_request_timeout,
        )
        peercreds_resp.raise_for_status()
        assert peercreds_resp.text == expected_peercreds

        peercreds_text_resp = requests.get(
            unix_base_uri + PEERCRED_TEXTS_URI,
            timeout=http_request_timeout,
        )
        assert peercreds_text_resp.status_code == 500


@pytest.mark.skipif(
    not IS_UID_GID_RESOLVABLE,
    reason='Modules `grp` and `pwd` are not available '
    'under the current platform',
)
@unix_only_sock_test
@non_macos_sock_test
def test_peercreds_unix_sock_with_lookup(
    http_request_timeout,
    peercreds_enabled_server,
):
    """Check that ``PEERCRED`` resolution works when enabled."""
    httpserver = peercreds_enabled_server
    httpserver.peercreds_resolve_enabled = True

    bind_addr = httpserver.bind_addr

    if isinstance(bind_addr, bytes):
        bind_addr = bind_addr.decode()

    # pylint: disable=possibly-unused-variable
    quoted = urllib.parse.quote(bind_addr, safe='')
    unix_base_uri = 'http+unix://{quoted}'.format(**locals())

    import grp
    import pwd

    expected_textcreds = (
        pwd.getpwuid(os.getuid()).pw_name,
        grp.getgrgid(os.getgid()).gr_name,
    )
    expected_textcreds = '!'.join(map(str, expected_textcreds))
    with requests_unixsocket.monkeypatch():
        peercreds_text_resp = requests.get(
            unix_base_uri + PEERCRED_TEXTS_URI,
            timeout=http_request_timeout,
        )
        peercreds_text_resp.raise_for_status()
        assert peercreds_text_resp.text == expected_textcreds


@pytest.mark.skipif(
    IS_WINDOWS,
    reason='This regression test is for a Linux bug, '
    'and the resource module is not available on Windows',
)
@pytest.mark.parametrize(
    'resource_limit',
    (
        1024,
        2048,
    ),
    indirect=('resource_limit',),
)
@pytest.mark.usefixtures('many_open_sockets')
def test_high_number_of_file_descriptors(native_server_client, resource_limit):
    """Test the server does not crash with a high file-descriptor value.

    This test shouldn't cause a server crash when trying to access
    file-descriptor higher than 1024.

    The earlier implementation used to rely on ``select()`` syscall that
    doesn't support file descriptors with numbers higher than 1024.
    """
    # We want to force the server to use a file-descriptor with
    # a number above resource_limit

    # Patch the method that processes
    _old_process_conn = native_server_client.server_instance.process_conn

    def native_process_conn(conn):
        native_process_conn.filenos.add(conn.socket.fileno())
        return _old_process_conn(conn)

    native_process_conn.filenos = set()
    native_server_client.server_instance.process_conn = native_process_conn

    # Trigger a crash if select() is used in the implementation
    native_server_client.connect('/')

    # Ensure that at least one connection got accepted, otherwise the
    # follow-up check wouldn't make sense
    assert len(native_process_conn.filenos) > 0

    # Check at least one of the sockets created are above the target number
    assert any(fn >= resource_limit for fn in native_process_conn.filenos)


@pytest.mark.skipif(
    not hasattr(socket, 'SO_REUSEPORT'),
    reason='socket.SO_REUSEPORT is not supported on this platform',
)
@pytest.mark.parametrize(
    'ip_addr',
    (
        ANY_INTERFACE_IPV4,
        ANY_INTERFACE_IPV6,
    ),
)
def test_reuse_port(http_server, ip_addr, mocker):
    """Check that port initialized externally can be reused."""
    family = socket.getaddrinfo(ip_addr, EPHEMERAL_PORT)[0][0]
    s = socket.socket(family)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    s.bind((ip_addr, EPHEMERAL_PORT))
    server = HTTPServer(
        bind_addr=s.getsockname()[:2],
        gateway=Gateway,
        reuse_port=True,
    )
    spy = mocker.spy(server, 'prepare')
    server.prepare()
    server.stop()
    s.close()
    assert spy.spy_exception is None


@pytest.fixture
def _garbage_bin():
    """Disable garbage collection when this fixture is in use."""
    gc.disable()
    yield
    gc.enable()


@pytest.fixture
def resource_limit(request):
    """Set the resource limit two times bigger then requested."""
    resource = pytest.importorskip(
        'resource',
        reason='The "resource" module is Unix-specific',
    )

    # Get current resource limits to restore them later
    soft_limit, hard_limit = resource.getrlimit(resource.RLIMIT_NOFILE)

    # We have to increase the nofile limit above 1024
    # Otherwise we see a 'Too many files open' error, instead of
    # an error due to the file descriptor number being too high
    resource.setrlimit(
        resource.RLIMIT_NOFILE,
        (request.param * 2, hard_limit),
    )

    try:  # noqa: WPS501
        yield request.param
    finally:
        # Reset the resource limit back to the original soft limit
        resource.setrlimit(resource.RLIMIT_NOFILE, (soft_limit, hard_limit))


@pytest.fixture
def many_open_sockets(request, resource_limit):
    """Allocate a lot of file descriptors by opening dummy sockets."""
    # NOTE: `@pytest.mark.usefixtures` doesn't work on fixtures which
    # NOTE: forces us to invoke this one dynamically to avoid having an
    # NOTE: unused argument.
    request.getfixturevalue('_garbage_bin')

    # Hoard a lot of file descriptors by opening and storing a lot of sockets
    test_sockets = []
    # Open a lot of file descriptors, so the next one the server
    # opens is a high number
    try:
        for _ in range(resource_limit):
            sock = socket.socket()
            test_sockets.append(sock)
            # If we reach a high enough number, we don't need to open more
            if sock.fileno() >= resource_limit:
                break
        # Check we opened enough descriptors to reach a high number
        the_highest_fileno = test_sockets[-1].fileno()
        assert the_highest_fileno >= resource_limit
        yield the_highest_fileno
    finally:
        # Close our open resources
        for test_socket in test_sockets:
            test_socket.close()


@pytest.mark.parametrize(
    ('minthreads', 'maxthreads', 'inited_maxthreads'),
    (
        (
            # NOTE: The docstring only mentions -1 to mean "no max", but other
            # NOTE: negative numbers should also work.
            1,
            -2,
            float('inf'),
        ),
        (1, -1, float('inf')),
        (1, 1, 1),
        (1, 2, 2),
        (1, float('inf'), float('inf')),
        (2, -2, float('inf')),
        (2, -1, float('inf')),
        (2, 2, 2),
        (2, float('inf'), float('inf')),
    ),
)
def test_threadpool_threadrange_set(minthreads, maxthreads, inited_maxthreads):
    """Test setting the number of threads in a ThreadPool.

    The ThreadPool should properly set the min+max number of the threads to use
    in the pool if those limits are valid.
    """
    tp = ThreadPool(
        server=None,
        min=minthreads,
        max=maxthreads,
    )
    assert tp.min == minthreads
    assert tp.max == inited_maxthreads


@pytest.mark.parametrize(
    ('minthreads', 'maxthreads', 'error'),
    (
        (-1, -1, 'min=-1 must be > 0'),
        (-1, 0, 'min=-1 must be > 0'),
        (-1, 1, 'min=-1 must be > 0'),
        (-1, 2, 'min=-1 must be > 0'),
        (0, -1, 'min=0 must be > 0'),
        (0, 0, 'min=0 must be > 0'),
        (0, 1, 'min=0 must be > 0'),
        (0, 2, 'min=0 must be > 0'),
        (
            1,
            0,
            'Expected an integer or the infinity value for the `max` argument but got 0.',
        ),
        (
            1,
            0.5,
            'Expected an integer or the infinity value for the `max` argument but got 0.5.',
        ),
        (
            2,
            0,
            'Expected an integer or the infinity value for the `max` argument but got 0.',
        ),
        (
            2,
            '1',
            "Expected an integer or the infinity value for the `max` argument but got '1'.",
        ),
        (2, 1, 'max=1 must be > min=2'),
    ),
)
def test_threadpool_invalid_threadrange(minthreads, maxthreads, error):
    """Test that a ThreadPool rejects invalid min/max values.

    The ThreadPool should raise an error with the proper message when
    initialized with an invalid min+max number of threads.
    """
    with pytest.raises((ValueError, TypeError), match=error):
        ThreadPool(
            server=None,
            min=minthreads,
            max=maxthreads,
        )


def test_threadpool_multistart_validation(monkeypatch):
    """Test for ThreadPool multi-start behavior.

    Tests that when calling start() on a ThreadPool multiple times raises a
    :exc:`RuntimeError`
    """
    # replace _spawn_worker with a function that returns a placeholder to avoid
    # actually starting any threads
    monkeypatch.setattr(
        ThreadPool,
        '_spawn_worker',
        lambda _: types.SimpleNamespace(ready=True),
    )

    tp = ThreadPool(server=None)
    tp.start()
    with pytest.raises(
        RuntimeError,
        match='Threadpools can only be started once.',
    ):
        tp.start()


def _prepared_pool(
    request: pytest.FixtureRequest,
    *,
    minthreads: int,
) -> ThreadPool:
    """Prepare a server with a set number of threads, and return its pool."""
    httpserver = _make_server(minthreads=minthreads)
    httpserver.prepare()
    request.addfinalizer(httpserver.stop)
    return httpserver.requests


def _count_live_threads(pool: ThreadPool) -> int:
    """Count the pool's threads that have not exited yet."""
    return sum(thread.is_alive() for thread in pool._threads)


def _wait_for_thread_count(pool: ThreadPool, count: int) -> bool:
    """Wait for the pool to have the expected number of live workers."""
    return _wait_until(
        compute_condition=lambda: _count_live_threads(pool) == count,
    )


def _wait_for_empty_queue(pool: ThreadPool) -> bool:
    """Wait for the workers to take every request in the queue."""
    return _wait_until(compute_condition=lambda: pool.qsize == 0)


@pytest.fixture
def single_thread_pool(request: pytest.FixtureRequest) -> ThreadPool:
    """Return the pool of a prepared server with a minimum of one thread."""
    return _prepared_pool(request, minthreads=1)


def test_threadpool_shrink_calls_are_additive(
    single_thread_pool: ThreadPool,
) -> None:
    """Test two close-together shrink() calls retire the total requested."""
    pool = single_thread_pool
    pool.grow(20)
    pool.shrink(10)
    pool.shrink(10)
    assert pool.idle == 1
    assert _wait_for_thread_count(pool, pool.min)


def test_threadpool_shrink_keeps_minimum(
    request: pytest.FixtureRequest,
) -> None:
    """Test that shrink() keeps the minimum number of threads."""
    pool = _prepared_pool(request, minthreads=10)
    pool.grow(40)
    pool.shrink(40)
    pool.shrink(80)
    assert pool.idle == 10
    assert _wait_for_thread_count(pool, 10)
    assert pool.qsize == 0


def _read_idle_while_retiring(pool: ThreadPool) -> list[int]:
    """Return the idle counts that differ from 1 while threads retire."""
    wrong = []
    pool.grow(20)
    pool.shrink(20)
    deadline = time.monotonic() + 10
    while len(pool._serving()) > 1 and time.monotonic() < deadline:
        idle = pool.idle
        if idle != 1:
            wrong.append(idle)
    return wrong


def test_threadpool_idle_is_exact_while_threads_retire(
    single_thread_pool: ThreadPool,
) -> None:
    """A thread taking its shutdown never shows as idle and due at once."""
    pool = single_thread_pool
    with contextlib.ExitStack() as cleanup:
        cleanup.callback(sys.setswitchinterval, sys.getswitchinterval())
        # Switch threads often, as a PyPy run may
        sys.setswitchinterval(1e-6)
        wrong = [_read_idle_while_retiring(pool) for _ in range(10)]
    assert not any(wrong)


@pytest.mark.parametrize('queued_before_error', (0, 1))
def test_threadpool_interrupted_shrink_releases_unused_reservations(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
    queued_before_error: int,
) -> None:
    """An interrupted shrink keeps only successfully queued retirements."""
    queued: list[object] = []
    # Workers wait until the counts are checked
    with _paused_workers(monkeypatch):
        pool = _prepared_pool(request, minthreads=1)
        pool.grow(2)
        original_put = pool._queue.put

        def _interrupted_put(obj: object) -> None:
            if len(queued) == queued_before_error:
                # Such as a KeyboardInterrupt while waiting for room
                raise RuntimeError('interrupted')
            original_put(obj)
            queued.append(obj)

        with monkeypatch.context() as patch:
            patch.setattr(pool._queue, 'put', _interrupted_put)
            with pytest.raises(RuntimeError, match='interrupted'):
                pool.shrink(2)
        assert pool._shutdowns_due == queued_before_error
        assert pool.idle == 3 - queued_before_error

    pool.shrink(3)
    assert _wait_for_thread_count(pool, pool.min)
    assert pool.qsize == 0


def _join_thread(thread: threading.Thread) -> None:
    """Join a started test thread and fail if it does not finish."""
    if thread.ident is None:
        return
    thread.join(10)
    assert not thread.is_alive()


def _release_events(*events: threading.Event) -> None:
    """Unblock test workers during cleanup, including assertion failures."""
    for event in events:
        event.set()


def _run_overlapping_shrinks(
    first: threading.Thread,
    second: threading.Thread,
    first_enqueue: threading.Event,
    second_progress: threading.Event,
    release_enqueue: threading.Event,
) -> None:
    """Hold the first enqueue until the second call has made its decision."""
    with contextlib.ExitStack() as cleanup:
        cleanup.callback(_join_thread, first)
        cleanup.callback(_join_thread, second)
        cleanup.callback(_release_events, release_enqueue)
        first.start()
        assert first_enqueue.wait(10)
        second.start()
        # The second call either tries to enqueue another request or returns.
        assert second_progress.wait(10)


def test_threadpool_unrelated_exit_keeps_pending_shutdown(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unrelated worker exit must not consume a queued retirement."""
    release_exit = threading.Event()
    release_workers = threading.Event()
    original_process = WorkerThread._process_connections_until_interrupted
    failed_worker = None

    def _controlled_process(worker: WorkerThread) -> None:
        assert release_exit.wait(10)
        if worker is failed_worker:
            return
        assert release_workers.wait(10)
        original_process(worker)

    with contextlib.ExitStack() as cleanup, monkeypatch.context() as patch:
        cleanup.callback(_release_events, release_exit, release_workers)
        patch.setattr(
            WorkerThread,
            '_process_connections_until_interrupted',
            _controlled_process,
        )
        pool = _prepared_pool(request, minthreads=2)
        pool.grow(2)
        failed_worker = pool._threads[0]
        pool.shrink(1)
        release_exit.set()
        _join_thread(failed_worker)

        # Three workers remain, with one retirement already queued.
        pool.shrink(1)
        assert pool.qsize == 1

    assert _wait_for_thread_count(pool, 2)


def _shrink_and_notify(
    pool: ThreadPool,
    finished: threading.Event,
    errors: list[BaseException],
) -> None:
    """Capture a shrink failure and signal that the caller has finished."""
    try:
        pool.shrink(2)
    except BaseException as error:
        errors.append(error)
    finally:
        finished.set()


@pytest.mark.parametrize('queue_size', (0, 1))
def test_threadpool_concurrent_shrink_keeps_minimum(
    single_thread_pool: ThreadPool,
    monkeypatch: pytest.MonkeyPatch,
    queue_size: int,
) -> None:
    """Concurrent calls must not spend the same retirement budget twice."""
    pool = single_thread_pool
    pool.grow(2)
    first_enqueue = threading.Event()
    second_progress = threading.Event()
    release_enqueue = threading.Event()
    errors: list[BaseException] = []
    queued: list[object] = []
    original_put = pool._queue.put

    def _held_put(obj: object) -> None:
        entered = (
            first_enqueue
            if threading.current_thread() is first
            else second_progress
        )
        entered.set()
        assert release_enqueue.wait(10)
        original_put(obj)
        queued.append(obj)

    first = threading.Thread(
        target=_shrink_and_notify,
        args=(pool, first_enqueue, errors),
    )
    second = threading.Thread(
        target=_shrink_and_notify,
        args=(pool, second_progress, errors),
    )
    with monkeypatch.context() as patch:
        patch.setattr(pool._queue, 'maxsize', queue_size)
        patch.setattr(pool._queue, 'put', _held_put)
        _run_overlapping_shrinks(
            first,
            second,
            first_enqueue,
            second_progress,
            release_enqueue,
        )

    assert not errors
    assert len(queued) == 2

    assert _wait_for_thread_count(pool, pool.min)
    assert pool.qsize == 0


@contextlib.contextmanager
def _paused_workers(
    monkeypatch: pytest.MonkeyPatch,
) -> _t.Iterator[threading.Event]:
    """Hold workers before they consume requests, and always release them."""
    release = threading.Event()
    original_process = WorkerThread._process_connections_until_interrupted

    def _paused_process(worker: WorkerThread) -> None:
        assert release.wait(10)
        original_process(worker)

    with contextlib.ExitStack() as cleanup, monkeypatch.context() as patch:
        cleanup.callback(release.set)
        patch.setattr(
            WorkerThread,
            '_process_connections_until_interrupted',
            _paused_process,
        )
        yield release


@pytest.mark.parametrize('worker_claimed', (False, True))
def test_threadpool_interrupt_after_enqueue_keeps_minimum(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
    *,
    worker_claimed: bool,
) -> None:
    """Retrying after an interrupted successful enqueue must keep the minimum."""
    with _paused_workers(monkeypatch) as release:
        pool = _prepared_pool(request, minthreads=1)
        pool.grow(1)
        original_put = pool._queue.put

        def _put_then_interrupt(obj: object) -> None:
            original_put(obj)
            if worker_claimed:
                release.set()
                assert _wait_for_thread_count(pool, 1)
            raise KeyboardInterrupt

        with monkeypatch.context() as patch:
            patch.setattr(pool._queue, 'put', _put_then_interrupt)
            with pytest.raises(KeyboardInterrupt):
                pool.shrink(1)
        pool.shrink(1)

    assert _wait_for_thread_count(pool, 1)
    assert pool.qsize == 0


def test_threadpool_reap_before_enqueue_returns_keeps_idle_count(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reaping before the enqueue returns must not leave a phantom shutdown."""
    pool = _prepared_pool(request, minthreads=1)
    pool.grow(2)
    original_put = pool._queue.put

    def _put_then_reap(obj: object) -> None:
        original_put(obj)
        assert _wait_for_thread_count(pool, 2)
        reaper = threading.Thread(target=pool.shrink, args=(0,))
        reaper.start()
        _join_thread(reaper)

    with monkeypatch.context() as patch:
        patch.setattr(pool._queue, 'put', _put_then_reap)
        pool.shrink(1)
    assert pool.idle == 2

    pool.shrink(1)
    assert _wait_for_thread_count(pool, 1)


def test_threadpool_unneeded_shrink_request_keeps_threads(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A shrink request that its call cancelled must not end a thread."""
    # Workers wait until the interrupted call has cancelled its request
    with _paused_workers(monkeypatch):
        pool = _prepared_pool(request, minthreads=1)
        pool.grow(2)
        original_put = pool._queue.put

        def _put_then_interrupt(obj: object) -> None:
            original_put(obj)
            raise KeyboardInterrupt

        with monkeypatch.context() as patch:
            patch.setattr(pool._queue, 'put', _put_then_interrupt)
            with pytest.raises(KeyboardInterrupt):
                pool.shrink(2)
        # It gave its shutdowns back, but its first request is queued
        assert not pool._shutdowns_due
        assert pool.qsize == 1
    assert _wait_for_empty_queue(pool)
    assert _count_live_threads(pool) == 3
    assert pool.idle == 3


def _interrupt_a_shrink_while_another_is_due(
    pool: ThreadPool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Interrupt a call once another has reserved a shutdown."""
    original_put = pool._queue.put
    second_queuing = threading.Event()
    first_done = threading.Event()
    second = threading.Thread(target=pool.shrink, args=(1,))

    def _controlled_put(obj: object) -> None:
        if threading.current_thread() is second:
            second_queuing.set()
            assert first_done.wait(10)
        original_put(obj)
        if threading.current_thread() is second:
            return
        # A worker takes the request and exits
        assert _wait_for_thread_count(pool, 2)
        second.start()
        assert second_queuing.wait(10)
        # Interrupted after its request got into the queue
        raise KeyboardInterrupt

    with contextlib.ExitStack() as cleanup, monkeypatch.context() as patch:
        cleanup.callback(_join_thread, second)
        cleanup.callback(first_done.set)
        patch.setattr(pool._queue, 'put', _controlled_put)
        with pytest.raises(KeyboardInterrupt):
            pool.shrink(amount=1)


def test_threadpool_interrupted_shrink_keeps_other_calls_shutdowns(
    single_thread_pool: ThreadPool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An interrupted call gives back only shutdowns of its own requests."""
    pool = single_thread_pool
    pool.grow(2)
    _interrupt_a_shrink_while_another_is_due(pool, monkeypatch)
    # One thread retired for each call
    assert _wait_for_thread_count(pool, 1)
    assert not pool._shutdowns_due


def test_threadpool_shrink_keeps_minimum_after_an_unrelated_exit(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A shutdown due when another thread exits must keep the minimum."""
    release_exit = threading.Event()
    release_workers = threading.Event()
    original_process = WorkerThread._process_connections_until_interrupted
    failed_worker = None

    def _controlled_process(worker: WorkerThread) -> None:
        assert release_exit.wait(10)
        if worker is failed_worker:
            return
        assert release_workers.wait(10)
        original_process(worker)

    with contextlib.ExitStack() as cleanup, monkeypatch.context() as patch:
        cleanup.callback(_release_events, release_exit, release_workers)
        patch.setattr(
            WorkerThread,
            '_process_connections_until_interrupted',
            _controlled_process,
        )
        pool = _prepared_pool(request, minthreads=2)
        pool.grow(1)
        failed_worker = pool._threads[0]
        # Retire every idle thread above the minimum: one
        pool.shrink(pool.idle)
        release_exit.set()
        _join_thread(failed_worker)
        release_workers.set()
        assert _wait_for_empty_queue(pool)
        # The request found the minimum left, and dropped its shutdown
        assert _wait_until(compute_condition=lambda: not pool._shutdowns_due)
        assert _count_live_threads(pool) == 2
        assert pool.idle == 2


@contextlib.contextmanager
def _hold_retiring_workers(
    monkeypatch: pytest.MonkeyPatch,
) -> _t.Iterator[queue.Queue[WorkerThread]]:
    """Hold workers after their processing loop has consumed a retirement."""
    release = threading.Event()
    at_exit: queue.Queue[WorkerThread] = queue.Queue()
    original_process = WorkerThread._process_connections_until_interrupted

    def _held_exit(worker: WorkerThread) -> None:
        original_process(worker)
        at_exit.put(worker)
        assert release.wait(10)

    with contextlib.ExitStack() as cleanup, monkeypatch.context() as patch:
        cleanup.callback(release.set)
        patch.setattr(
            WorkerThread,
            '_process_connections_until_interrupted',
            _held_exit,
        )
        yield at_exit


def test_threadpool_shrink_skips_threads_shutting_down(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A thread that is shutting down is neither idle nor asked again."""
    with _hold_retiring_workers(monkeypatch) as at_exit:
        pool = _prepared_pool(request, minthreads=1)
        pool.grow(2)
        pool.shrink(1)
        assert _wait_until(compute_condition=lambda: at_exit.qsize() == 1)
        # The retiring thread is still alive, but it no longer serves
        assert _count_live_threads(pool) == 3
        assert pool.idle == 2
        pool.shrink(5)
        assert _wait_until(compute_condition=lambda: at_exit.qsize() == 2)
        assert _wait_for_empty_queue(pool)
        assert not pool._shutdowns_due
        assert pool.idle == 1
    assert _wait_for_thread_count(pool, 1)


def test_overload_results_in_suitable_http_error(request):
    """A server that can't keep up with requests returns a 503 HTTP error."""
    localhost = '127.0.0.1'
    httpserver = HTTPServer(
        bind_addr=(localhost, EPHEMERAL_PORT),
        gateway=Gateway,
    )
    # Can only handle on request in parallel:
    httpserver.requests = ThreadPool(
        min=1,
        max=1,
        accepted_queue_size=1,
        accepted_queue_timeout=0,
        server=httpserver,
    )

    httpserver.prepare()
    serve_thread = threading.Thread(target=httpserver.serve)
    serve_thread.start()
    request.addfinalizer(httpserver.stop)
    # Stop the thread pool to ensure the queue fills up:
    httpserver.requests.stop()

    _host, port = httpserver.bind_addr

    # Use up the very limited thread pool queue we've set up, so future
    # requests fail:
    httpserver.requests._queue.put(None)

    response = requests.get(f'http://{localhost}:{port}', timeout=20)
    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE


def test_overload_thread_does_not_leak():
    """On shutdown the overload thread exits.

    This is a test for issue #769.
    """
    path = pathlib.Path(__file__).parent / 'threadleakcheck.py'
    process = subprocess.run([sys.executable, path], check=False)
    # We use special exit code to indicate success, rather than normal zero, so
    # the test doesn't acidentally pass:
    assert process.returncode == SUCCESSFUL_SUBPROCESS_EXIT
