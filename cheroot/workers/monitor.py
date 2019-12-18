"""Monitor for threadpool."""

import threading
import time

from .dynpool import DynamicPoolResizer


class BackgroundTask(threading.Thread):
    """A subclass of threading.Thread whose run() method repeats.

    Use this class for most repeating tasks. It uses time.sleep() to wait
    for each interval, which isn't very responsive; that is, even if you call
    self.cancel(), you'll have to wait until the sleep() call finishes before
    the thread stops. To compensate, it defaults to being daemonic, which means
    it won't delay stopping the whole process.
    """

    def __init__(
        self,
        interval,
        function,
        args=None,
        kwargs=None,
        logger=None,
    ):
        """Initialize a BackgroundTask."""
        super(BackgroundTask, self).__init__()
        self.interval = interval
        self.function = function
        self.args = args if args else []
        self.kwargs = kwargs if kwargs else {}
        self.running = False
        self.log = logger or (lambda msg: None)
        # default to daemonic
        self.daemon = True

    def cancel(self):
        """Cancel the task."""
        self.running = False

    def run(self):
        """Run - Invoke function every interval seconds."""
        self.running = True
        while self.running:
            time.sleep(self.interval)
            if not self.running:
                return
            try:
                self.function(*self.args, **self.kwargs)
            except Exception as e:
                self.log(
                    'Error in background task thread function {}:{}.'.format(
                        self.function,
                        e,
                    ), )
                # Quit on first error to avoid massive logs.
                raise


class Monitor(object):
    """Monitor a BackgroundTask."""

    callback = None
    """The function to call at intervals."""

    frequency = 60
    """The time in seconds between callback runs."""

    thread = None
    """A :class:`BackgroundTask` thread.
    """
    def __init__(self, callback, frequency=60, name=None, logger=None):
        """Initialize Monitor."""
        self.callback = callback
        self.frequency = frequency
        self.thread = None
        self.name = name or self.__class__.__name__
        self.log = logger or (lambda msg: None)

    def start(self):
        """Start our callback in its own background thread."""
        if self.frequency > 0:
            threadname = self.name
            if self.thread is None:
                self.thread = BackgroundTask(
                    self.frequency,
                    self.callback,
                    logger=self.log,
                )
                self.thread.setName(threadname)
                self.thread.start()
                self.log('Started monitor thread {}.'.format(threadname))
            else:
                self.log(
                    'Monitor thread {} already started.'.format(threadname), )

    start.priority = 70

    def stop(self):
        """Stop our callback's background task thread."""
        if self.thread is None:
            self.log('No thread running for {}.'.format(self.name))
        else:
            if self.thread is not threading.currentThread():
                name = self.thread.getName()
                self.thread.cancel()
                if not self.thread.daemon:
                    self.log('Joining {}'.format(name))
                    self.thread.join()
                self.log('Stopped thread {}.'.format(name))
            self.thread = None

    def graceful(self):
        """Stop the callback's background task thread and restart it."""
        self.stop()
        self.start()


class ThreadPoolMonitor(Monitor):
    """ThreadPoolMonitor for dynamic resizing."""

    def __init__(self, frequency, name=None, logger=None):
        """Initialize ThreadPoolMonitor."""
        self._run = lambda: None
        self._resizer = None
        super(ThreadPoolMonitor, self).__init__(
            self.run,
            frequency=frequency,
            name=name,
            logger=logger,
        )

    def run(self):
        """Run the monitor."""
        self._run()

    def configure(self, thread_pool, minspare, maxspare, shrinkfreq, logfreq):
        """Configure the pool resizer."""
        self._resizer = DynamicPoolResizer(
            thread_pool,
            minspare,
            maxspare,
            shrinkfreq=shrinkfreq,
            logfreq=logfreq,
            logger=self.log,
        )
        self._run = self._resizer.run

    def stop(self):
        """Stop the monitor."""
        self._run = lambda: None
        super(ThreadPoolMonitor, self).stop()

    stop.priority = 10
