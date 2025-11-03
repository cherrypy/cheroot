=========
Changelog
=========

..
    You should *NOT* be adding new change log entries to this file, this
    file is managed by towncrier. You *may* edit previous change logs to
    fix problems like typo corrections or such.
    To add a new change log entry, please see
    https://pip.pypa.io/en/latest/development/contributing/#news-entries
    we named the news folder "docs/changelog-fragments.d/".

    WARNING: Don't drop the next directive!

.. towncrier release notes start

v11.1.1
=======

*(2025-11-03)*


Packaging updates and notes for downstreams
-------------------------------------------

- The packaging configuration has been fixed to ensure
  that only :file:`cheroot` package will be installed
  into :file:`site-packages/` -- by :user:`webknjaz`.

  This fixes a regression introduced in version 11.1.0.

  *Related issues and pull requests on GitHub:*
  :issue:`790`.

  *Related commits on GitHub:*
  :commit:`d286d1a10718e871366743f3f496c760113cee15`.


----


v11.1.0
=======

*(2025-11-03)*


Features
--------

- Added optional private key password argument to SSL adapters to support password-protected private keys
  -- by :user:`jatalahd`.

  *Related issues and pull requests on GitHub:*
  :issue:`752`.


Contributor-facing changes
--------------------------

- Added missing ``__all__`` and ``IS_WINDOWS`` definitions to ``.pyi`` stub files for mypy.

  -- by :user:`julianz-`

  *Related issues and pull requests on GitHub:*
  :issue:`774`.

- Made ``test_http_over_https_error`` compatible with Solaris -- by :user:`mtelka`.

  *Related issues and pull requests on GitHub:*
  :issue:`776`.

- Increased timeout values ``test_client.server_instance.timeout`` and ``http_request_timeout``
  to make related tests more stable.

  *Related issues and pull requests on GitHub:*
  :issue:`777`.


----


v11.0.0
=======

*(2025-09-21)*


Features
--------

- When load is too high, Cheroot now responds with a 503 Service Unavailable HTTP error.
  Previously it silently closed the connection.

  -- by :user:`itamarst`

  *Related issues and pull requests on GitHub:*
  :issue:`745`.


Removals and backward incompatible breaking changes
---------------------------------------------------

- Cheroot dropped support for Python 3.6 and 3.7.
  It now requires Python 3.8 or later.

  -- by :user:`jaraco`

  *Related issues and pull requests on GitHub:*
  :issue:`565`, :issue:`633`.

  *Related commits on GitHub:*
  :commit:`437863ee`.


Packaging updates and notes for downstreams
-------------------------------------------

- Declared Python 3.12 and Python 3.13 as supported officially
  -- by :user:`webknjaz`.

  *Related issues and pull requests on GitHub:*
  :issue:`696`.

  *Related commits on GitHub:*
  :commit:`5db4f634`.

- The minimum version of the ``setuptools-scm`` build dependency
  has been set to 7. The Git archives are now produced by it
  natively, instead of relying on a third party plugin which is
  no longer being used.

  -- by :user:`serhii73`

  *Related issues and pull requests on GitHub:*
  :issue:`628`.

- The packaging metadata has been migrated to the
  :file:`pyproject.toml`-based :pep:`621` declaration
  -- by :user:`jaraco` and :user:`webknjaz`.

  As a part of this update, the minimum version of the
  ``setuptools`` build backend was bumped to 61.2.
  Moreover, any compatibility shims that existed in
  :file:`setup.cfg` and :file:`setup.py` have been
  removed for good.

  *Related issues and pull requests on GitHub:*
  :issue:`690`.


Contributor-facing changes
--------------------------

- The test infrastructure has been updated to stop using
  the ``pytest-forked`` plugin
  -- by :user:`jaraco` and :user:`webknjaz`.

  This plugin was causing problems with upgrading to modern
  versions of Pytest and it is not going to be fixed anytime
  soon.

  It was used in a test that interacts with the system
  resource limits under \*NIX environments in hopes to isolate
  the side effects caused by the preparatory code.

  It is possible that this will have an effect on the test
  sessions and we may have to look for alternative solutions
  for test process isolation.

  *Related issues and pull requests on GitHub:*
  :issue:`502`, :issue:`511`, :issue:`680`, :issue:`681`, :issue:`703`.

- The test infrastructure has been updated to start using
  the upstream reusable workflow :file:`reusable-tox.yml`
  from :gh:`tox-dev/workflow` -- by :user:`webknjaz`.

  This chance allows us to de-duplicate the commonly used
  CI shape.

  *Related issues and pull requests on GitHub:*
  :issue:`743`.


----


v10.0.1
=======

*(2024-04-22)*


Bug fixes
---------

- Fixed a flaw where internally unhandled exceptions
  could crash the worker threads and eventually starve
  the server of its processing resources. It is no
  longer and issue and the unhandled errors are now
  logged and suppressed except for a few expected
  exceptions that are used for normal interruption
  requests.

  -- by :user:`cameronbrunner` and :user:`webknjaz`

  *Related issues and pull requests on GitHub:*
  :issue:`310`, :issue:`346`, :issue:`354`, :issue:`358`, :issue:`365`, :issue:`375`, :issue:`599`, :issue:`641`, :issue:`649`.

- Fixed compatibility with Python 3.8 in the built-in
  TLS adapter that relies on :py:mod:`python:ssl`.

  Modern Python versions communicate specialized exceptions
  :py:exc:`ssl.SSLEOFError` and :py:exc:`ssl.SSLZeroReturnError`
  where the older versions errored out in a very generic way.

  -- by :user:`toppk` and :user:`webknjaz`

  *Related issues and pull requests on GitHub:*
  :issue:`517`, :issue:`518`.


Packaging updates and notes for downstreams
-------------------------------------------

- Started signing the package distribution artifacts in CI/CD
  with Sigstore and uploading them to GitHub Releases
  -- by :user:`webknjaz`.

  *Related commits on GitHub:*
  :commit:`27a3c944`, :commit:`c45f184e`.

- The change log management is now implemented through
  the :std:doc:`Towncrier <towncrier:index>` tool
  -- by :user:`webknjaz`.

  The contributors are now expected to :std:ref:`include
  change log fragment files in their pull requests
  <adding change notes with your prs>`.

  These news snippets can link one or more issues or pull
  requests, and be of one or more of the following categories:

  * ``bugfix``: A bug fix for something we deemed an improper undesired
    behavior that got corrected in the release to match pre-agreed
    expectations.
  * ``feature``: A new behavior, public APIs. That sort of stuff.
  * ``deprecation``: A declaration of future API removals and breaking
    changes in behavior.
  * ``breaking``: When something public gets removed in a breaking way.
    Could be deprecated in an earlier release.
  * ``doc``: Notable updates to the documentation structure or build
    process.
  * ``packaging``: Notes for downstreams about unobvious side effects
    and tooling. Changes in the test invocation considerations and
    runtime assumptions.
  * ``contrib``: Stuff that affects the contributor experience. e.g.
    Running tests, building the docs, setting up the development
    environment.
  * ``misc``: Changes that are hard to assign to any of the above
    categories.

  *Related issues and pull requests on GitHub:*
  :issue:`654`.


Contributor-facing changes
--------------------------

- Started type-checking the project with MyPy against a
  range of versions instead of just one — Python 3.8–3.12
  -- by :user:`webknjaz`.

  *Related commits on GitHub:*
  :commit:`4fa1e663`, :commit:`676edc4e`, :commit:`be9dbc41`.

- The project how has a :file:`.git-blame-ignore-revs` letting
  GitHub know which auto-formatting revisions to ignore. It is
  also possible to integrate it locally, if one wants to do so.

  -- by :user:`webknjaz`

  *Related commits on GitHub:*
  :commit:`5980a3fb`, :commit:`f8a1cc4d`.

- The project adopted the ``autopep8`` tool to assist with
  automatic code formatting. It is chosen over ``black``
  because it is less intrusive which is important to the
  maintainer as it promotes inclusivity.
  ``autopep8`` is integrated into the ``pre-commit`` check
  runner and is configured to only correct :pep:`8`
  violations, avoiding changes to compliant snippets.

  -- by :user:`webknjaz`

  *Related commits on GitHub:*
  :commit:`65ba7e69`.

- The continuous integration and pull request merges have been
  set up to only merge pull requests through merge queues
  -- by :user:`webknjaz`.

  *Related commits on GitHub:*
  :commit:`a7149e0c`.

- Documented the upgraded :std:doc:`release process
  <contributing/release_guide>` -- by :user:`webknjaz`.

  *Related commits on GitHub:*
  :commit:`df0d1a08`.

- The change log management is now implemented through
  the :std:doc:`Towncrier <towncrier:index>` tool
  -- by :user:`webknjaz`.

  The contributors are now expected to :std:ref:`include
  change log fragment files in their pull requests
  <adding change notes with your prs>`.

  These news snippets can link one or more issues or pull
  requests, and be of one or more of the following categories:

  * ``bugfix``: A bug fix for something we deemed an improper undesired
    behavior that got corrected in the release to match pre-agreed
    expectations.
  * ``feature``: A new behavior, public APIs. That sort of stuff.
  * ``deprecation``: A declaration of future API removals and breaking
    changes in behavior.
  * ``breaking``: When something public gets removed in a breaking way.
    Could be deprecated in an earlier release.
  * ``doc``: Notable updates to the documentation structure or build
    process.
  * ``packaging``: Notes for downstreams about unobvious side effects
    and tooling. Changes in the test invocation considerations and
    runtime assumptions.
  * ``contrib``: Stuff that affects the contributor experience. e.g.
    Running tests, building the docs, setting up the development
    environment.
  * ``misc``: Changes that are hard to assign to any of the above
    categories.

  *Related issues and pull requests on GitHub:*
  :issue:`654`.


----


v10.0.0
=======

*(2023-05-20)*

- :issue:`504` via :pr:`505`: Cheroot now accepts a
  ``reuse_port`` parameter on the ``HTTPServer`` object.
  Subclasses overriding ``prepare_socket`` will no longer
  work and will need to adapt to the new interface.

v9.0.0
======

*(2022-11-19)*

- :issue:`252` via :pr:`339`: Cheroot now requires Python
  3.6 or later. Python 3.5 and Python 2.7 are still supported
  by the :gh:`maint/8.x branch
  <cherrypy/cheroot/tree/maint/8.x>` and stabilizing
  bugfixes will be accepted to that branch.

v8.6.0
======

*(2022-01-03)*

Significant improvements:

- :issue:`384` via :pr:`385`, :pr:`406`: Exposed type stubs with
  annotations for public API -- by :user:`kasium`.

- :pr:`401` (related to the :pr:`352` effort): Started reusing the
  the ``expriration_interval`` setting as timeout in the low-level
  :py:func:`~select.select` invocation, effectively reducing the system
  load when idle, that is noticeable on low-end hardware systems. On
  Windows OS, due to different :py:func:`~select.select` behavior, the
  effect is less significant and comes with a theoretically decreased
  performance on quickly repeating requests, which has however found
  to be not significant in real world scenarios.
  -- by :user:`MichaIng`.

Internal changes:

- Implemented a manual-trigger-based release workflow.
- Integrated publishing GitHub Releases into the workflow.
- Migrated the docs theme to `Furo <https://pradyunsg.me/furo>`__
  (created by :user:`pradyunsg`).
- Attempted to improve the stability of testing.
- Configured the CI to test the same distribution as will be shipped.
- Improved the linting setup and contributor checklists.
- Stopped running tests under Ubuntu 16.04.
- Tweaked the distribution packages metadata to satisfy strict checks.
- Implemented distribution build reproducibility using a pip constraints
  lock-file.
- Added per-environment lock-files into the tox test environments.

v8.5.2
======

*(2021-01-18)*

- :issue:`358` via :pr:`359`: Fixed a regression from
  :pr:`199` that made the worker threads exit on invalid
  connection attempts and could make the whole server
  unresponsive once there was no workers left.
  -- by :user:`cameronbrunner`.

v8.5.1
======

*(2020-12-12)*

- :cp-issue:`1873` via :pr:`340`: Resurrected an
  unintentionally removed feature of interrupting a server
  main thread by externally assigning an exception to the
  :py:meth:`HTTPServer.interrupt <cheroot.server.\
  HTTPServer.interrupt>` property -- by :user:`liamstask`.

- :pr:`350`: Fixed the incarnation of an earlier regression
  of not resetting the serving state
  on :py:data:`~signal.SIGINT` originally fixed by :pr:`322`
  and :pr:`331` but reintroduced by the changes in :pr:`311`
  -- by :user:`liamstask`.

v8.5.0
======

*(2020-12-05)*

- :issue:`305` via :pr:`311`: In
  :py:class:`~cheroot.connections.ConnectionManager`,
  process connections as they become active rather than
  waiting for a ``tick`` event, addressing performance
  degradation introduced in v8.1.0 -- by :user:`liamstask`.

- :issue:`341` via :pr:`342`: Suppress legitimate OS errors
  expected on shutdown -- by :user:`webknjaz`.

v8.4.8
======

*(2020-11-24)*

- :issue:`317` via :pr:`337`: Fixed a regression in
  8.4.5 where the connections dictionary would change
  size during iteration, leading to a :py:exc:`RuntimeError`
  raised in the logs -- by :user:`liamstask`.

v8.4.7
======

*(2020-11-15)*

- :pr:`334`: Started filtering out TLS/SSL errors when
  the version requested by the client is unsupported
  -- by :user:`sanderjo` and :user:`Safihre`.

v8.4.6
======

*(2020-11-15)*

- :issue:`328` via :pr:`322` and :pr:`331`: Fixed a
  regression introduced in the earlier refactoring in v8.4.4
  via :pr:`309` that caused the :py:meth:`~cheroot.server.\
  HTTPServer.serve` method to skip setting
  ``serving=False`` on :py:data:`~signal.SIGINT` and
  :py:data:`~signal.SIGTERM` -- by :user:`marc1n` and
  :user:`cristicbz`.

v8.4.5
======

*(2020-08-24)*

- :issue:`312` via :pr:`313`: Fixed a regression introduced
  in the earlier refactoring in v8.4.4 via :pr:`309` that
  caused the connection manager to modify the selector map
  while looping over it -- by :user:`liamstask`.

- :issue:`312` via :pr:`316`: Added a regression test for
  the error handling in :py:meth:`~cheroot.connections.\
  ConnectionManager.get_conn` to ensure more stability
  -- by :user:`cyraxjoe`.

v8.4.4
======

*(2020-08-12)*

- :issue:`304` via :pr:`309`: Refactored :py:class:`~\
  cheroot.connections.ConnectionManager` to use :py:meth:`~\
  selectors.BaseSelector.get_map` and reorganized the
  readable connection tracking -- by :user:`liamstask`.

- :issue:`304` via :pr:`309`: Fixed the server shutdown
  sequence to avoid race condition resulting in accepting
  new connections while it is being terminated
  -- by :user:`liamstask`.

v8.4.3
======

*(2020-08-12)*

- :pr:`282`: Fixed a race condition happening when an HTTP
  client attempts to reuse a persistent HTTP connection after
  it's been discarded on the server in :py:class:`~cheroot.\
  server.HTTPRequest` but no TCP FIN packet has been received
  yet over the wire -- by :user:`meaksh`.

  This change populates the ``Keep-Alive`` header exposing
  the timeout value for persistent HTTP/1.1 connections which
  helps mitigate such race conditions by letting the client
  know not to reuse the connection after that time interval.

v8.4.2
======

*(2020-07-28)*

- Fixed a significant performance regression introduced in
  v8.1.0 (:issue:`305` via :pr:`308`) - by :user:`mar10`.

  The issue turned out to add 0.1s delay on new incoming
  connection processing. We've lowered that delay to mitigate
  the problem short-term, better fix is yet to come.

v8.4.1
======

*(2020-07-26)*

- Prevent :py:exc:`ConnectionAbortedError` traceback from being
  printed out to the terminal output during the app start-up on
  Windows when built-in TLS adapter is used (:issue:`302` via
  :pr:`306`) - by :user:`mxii-ca`.

v8.4.0
======

*(2020-07-23)*

- Converted management from low-level :py:func:`~select.select` to
  high-level :py:mod:`selectors` (:issue:`249` via :pr:`301`)
  - by :user:`tommilligan`.

  This change also introduces a conditional dependency on
  ``selectors2`` as a fall-back for legacy Python interpreters.

v8.3.1
======

*(2020-07-13)*

- Fixed TLS socket related unclosed resource warnings
  (:pr:`291` and :pr:`298`).
- Made terminating keep-alive connections more graceful
  (:issue:`263` via :pr:`277`).

v8.3.0
======

*(2020-02-09)*

- :cp-issue:`910` via :pr:`243`: Provide TLS-related
  details via WSGI environment interface.
- :pr:`248`: Fix parsing of the ``--bind`` CLI option
  for abstract UNIX sockets.


v8.2.1
======

*(2019-10-17)*

- :cp-issue:`1818`: Restore support for ``None``
  default argument to ``WebCase.getPage()``.


v8.2.0
======

*(2019-10-14)*

- Deprecated use of negative timeouts as alias for
  infinite timeouts in ``ThreadPool.stop``.
- :cp-issue:`1662` via :pr:`74`: For OPTION requests,
  bypass URI as path if it does not appear absolute.


v8.1.0
======

*(2019-10-09)*

- Workers are now request-based, addressing the
  long-standing issue with keep-alive connections
  (:issue:`91` via :pr:`199`).


v8.0.0
======

*(2019-10-09)*

- :issue:`231` via :pr:`232`: Remove custom ``setup.cfg``
  parser handling, allowing the project (including ``sdist``)
  to build/run on setuptools 41.4. Now building cheroot
  requires setuptools 30.3 or later (for declarative
  config support) and preferably 34.4 or later (as
  indicated in ``pyproject.toml``).


v7.0.0
======

*(2019-09-26)*

- :pr:`224`: Refactored "open URL" behavior in
  :py:mod:`~cheroot.test.webtest` to rely on `retry_call
  <https://jaracofunctools.readthedocs.io/en/latest/?badge=latest#jaraco.functools.retry_call>`_.
  Callers can no longer pass ``raise_subcls`` or ``ssl_context``
  positionally, but must pass them as keyword arguments.


v6.6.0
======

*(2019-09-25)*

- Revisit :pr:`85` under :pr:`221`. Now
  ``backports.functools_lru_cache`` is only
  required on Python 3.2 and earlier.
- :cp-issue:`1206` via :pr:`204`: Fix race condition in
  threadpool shrink code.


v6.5.8
======

*(2019-09-05)*

- :issue:`222` via :commit:`621f4ee`: Fix
  :py:const:`socket.SO_PEERCRED` constant fallback value
  under PowerPC.


v6.5.7
======

*(2019-09-03)*

- :issue:`198` via :commit:`9f7affe`: Fix race condition when
  toggling stats counting in the middle of request processing.

- Improve post Python 3.9 compatibility checks.

- Fix support of `abstract namespace sockets
  <https://utcc.utoronto.ca/~cks
  /space/blog/linux/SocketAbstractNamespace>`_.

v6.5.6
======

*(2019-08-19)*

- :issue:`218` via :pr:`219`: Fix HTTP parser to return 400 on
  invalid major-only HTTP version in Request-Line.


v6.5.5
======

*(2019-04-25)*

- :issue:`99` via :pr:`186`: Sockets now collect statistics (bytes
  read and written) on Python 3 same as Python 2.

- :cp-issue:`1618` via :pr:`180`: Ignore OpenSSL's 1.1+ Error 0
  under any Python while wrapping a socket.


v6.5.4
======

*(2019-01-01)*

- :issue:`113`: Fix :py:mod:`cheroot.ssl.pyopenssl`
  under Python 3.

- :issue:`154` via :pr:`159`: Remove custom license field from
  dist metadata.

- :issue:`95`: Fully integrate :py:mod:`trustme` into all TLS tests.
  Also remove all hardcoded TLS certificates.

- :issue:`42`: Remove traces of :py:mod:`unittest` and
  :py:mod:`ddt` usage.

- Fix invalid input processing in
  :py:func:`cheroot._compat.extract_bytes`.

- Fix returning error explanation over plain HTTP for PyOpenSSL.

- Add a fallback for :py:func:`os.lchmod` where it's missing.

- Avoid traceback for invalid client cert with builtin
  :py:mod:`ssl` adapter.

- Avoid deprecation warning with :py:class:`OpenSSL.SSL.Connection`.

- Fix socket wrapper in PyOpenSSL adapter.

- Improve tests coverage:

  * Client TLS certificate tests

  * :py:func:`cheroot._compat.extract_bytes`

  * ``PEERCREDS`` lookup


v6.5.3
======

*(2018-12-20)*

- :pr:`149`: Make ``SCRIPT_NAME`` optional per PEP 333.


v6.5.2
======

*(2018-09-03)*

- :issue:`6` via :pr:`109`: Fix import of
  :py:mod:`cheroot.ssl.pyopenssl` by refactoring and separating
  :py:mod:`cheroot.makefile`'s stream wrappers.

- :issue:`95` via :pr:`109`: Add initial tests for SSL layer with use
  of :py:mod:`trustme`


v6.5.1
======

*(2018-09-02)*

- :issue:`93` via :pr:`110`: Improve UNIX socket FS access mode
  in :py:meth:`cheroot.server.HTTPServer.prepare` on a file socket
  when starting to listen to it.


v6.5.0
======

*(2018-08-29)*

- :cp-issue:`1001` via :pr:`52` and :pr:`108`: Add support for
  validating client certificates.


v6.4.0
======

*(2018-08-01)*

- :issue:`68` via :pr:`98`: Factor out parts of
  :py:meth:`cheroot.server.HTTPServer.start` into
  :py:meth:`prepare() <cheroot.server.HTTPServer.prepare>` and
  :py:meth:`serve() <cheroot.server.HTTPServer.serve>`


v6.3.3
======

*(2018-07-10)*

- Fix bug with returning empty result in
  :py:meth:`cheroot.ssl.builtin.BuiltinSSLAdapter.wrap`


v6.3.2
======

*(2018-06-16)*

- :issue:`100` via :pr:`101`: Respond with HTTP 400 to malicious
  ``Content-Length`` in request headers.


v6.3.1
======

*(2018-05-21)*

- :cp-issue:`1618`: Ignore OpenSSL's 1.1+ Error 0 under Python 2 while
  wrapping a socket.


v6.3.0
======

*(2018-05-17)*

- :pr:`87`: Add ``cheroot`` command and runpy launcher to
  launch a WSGI app from the command-line.


v6.2.4
======

*(2018-04-19)*

- Fix missing ``resolve_peer_creds`` argument in
  :py:class:`cheroot.wsgi.Server` being bypassed into
  :py:class:`cheroot.server.HTTPServer`.

- :pr:`85`: Revert conditional dependencies. System packagers should
  honor the dependencies as declared by cheroot, which are defined
  intentionally.


v6.2.3
======

*(2018-04-14)*

- :pr:`85`: Skip installing dependencies from backports namespace under
  Python 3.


v6.2.2
======

*(2018-04-14)*

- :issue:`84` (:cp-issue:`1704`): Fix regression, causing
  :py:exc:`ModuleNotFoundError` under ``cygwin``.


v6.2.1
======

*(2018-04-10)*

- :pr:`83`: Fix regression, caused by inverted check for Windows OS.

- Add more URLs to distribution metadata


v6.2.0
======

*(2018-04-10)*

- :pr:`37`: Implement PEERCRED lookup over UNIX-socket HTTP connection.

  * Discover connected process' PID/UID/GID

  * Respect server switches: ``peercreds_enabled`` and
    ``peercreds_resolve_enabled``

  * ``get_peer_creds`` and ``resolve_peer_creds``  methods on connection

  * ``peer_pid``, ``peer_uid``, ``peer_gid``, ``peer_user`` and ``peer_group``
    properties on connection

  * ``X_REMOTE_PID``, ``X_REMOTE_UID``, ``X_REMOTE_GID``, ``X_REMOTE_USER``
    (``REMOTE_USER``) and ``X_REMOTE_GROUP`` WSGI environment variables when
    enabled and supported

  * Per-connection caching to reduce lookup cost


v6.1.2
======

*(2018-04-08)*

- :issue:`81`: Fix regression introduced by :pr:`80`.

  * Restore :py:attr:`storing bound socket
    <cheroot.server.HTTPServer.bind_addr>` in Windows broken by use of
    :py:obj:`socket.AF_UNIX`


v6.1.1
======

*(2018-04-07)*

- :pr:`80`: Fix regression introduced by :commit:`68a5769`.

  * Get back support for :py:obj:`socket.AF_UNIX` in stored bound address in
    :py:attr:`cheroot.server.HTTPServer.bind_addr`


v6.1.0
======

*(2018-04-05)*

- :pr:`67`: Refactor test suite to completely rely on pytest.

  * Integrate ``pytest-testmon`` and ``pytest-watch``

  * Stabilize testing

- :cp-issue:`1664` via :pr:`66`: Implement input termination flag support as
  suggested by `@mitsuhiko <https://github.com/mitsuhiko>`_ in his
  `wsgi.input_terminated Proposal
  <https://gist.github.com/mitsuhiko/5721547>`_.

- :issue:`73`: Fix SSL error bypassing.

- :issue:`77` via :pr:`78`: Fix WSGI documentation example to support Python 3.

- :pr:`76`: Send correct conditional HTTP error in helper function.

- :cp-issue:`1404` via :pr:`75`: Fix headers being unsent before request
  closed. Now we double check that they've been sent.

- Minor docs improvements.

- Minor refactoring.


v6.0.0
======

*(2017-12-04)*

- Drop support for Python 2.6, 3.1, 3.2, and 3.3.

- Also drop built-in SSL support for Python 2.7 earlier
  than 2.7.9.


v5.11.0
=======

*(2017-12-04)*

- :cp-issue:`1621`: To support :py:mod:`~cheroot.test.webtest`
  applications that feed absolute URIs to
  :py:meth:`~cheroot.test.webtest.WebCase.getPage`
  but expect the scheme/host/port to be ignored (as cheroot 5.8
  and earlier did), provide a ``strip_netloc`` helper and recipe
  for calling it in a subclass.


v5.10.0
=======

*(2017-11-23)*

- Minor refactorings of ``cheroot/server.py`` to reduce redundancy
  of behavior.

- Delinting with fewer exceptions.

- Restored license to BSD.


v5.9.2
======

*(2017-11-23)*

- :issue:`61`: Re-release without spurious files in the distribution.


v5.9.1
======

*(2017-11-17)*

- :issue:`58`: Reverted encoding behavior in wsgi module to correct
  regression in CherryPy tests.


v5.9.0
======

*(2017-11-16)*

- :cp-issue:`1088` and :pr:`53`: Avoid using SO_REUSEADDR on Windows
  where it has different semantics.

- ``cheroot.tests.webtest`` adopts the one method that was unique
  in CherryPy, now superseding the implementation there.

- Substantial cleanup around compatibility functions
  (:py:mod:`~cheroot._compat` module).

- License unintentionally changed to MIT. BSD still declared and intended.


v5.8.3
======

*(2017-08-11)*

- Improve HTTP request line validation:

  * Improve HTTP version parsing

- Fix HTTP CONNECT method processing:

  * Respond with ``405 Method Not Allowed`` if ``proxy_mode is False``

  * Validate that request-target is in authority-form

- Improve tests in ``test.test_core``

- :pr:`44`: Fix EPROTOTYPE @ Mac OS


v5.8.2
======

*(2017-08-07)*

- Fix :pr:`39` regression. Add HTTP request line check:
  absolute URI path must start with a
  forward slash ("/").


v5.8.1
======

*(2017-08-05)*

- CI improvements:

  * Add basic working Circle CI v2 config

- Fix URI encoding bug introduced in :pr:`39`

  * Improve :py:class:`cheroot.test.helper.Controller` to properly match
    Unicode


v5.8.0
======

*(2017-08-01)*

- CI improvements:

  * Switch to native PyPy support in Travis CI

  * Take into account :pep:`257` compliant modules

  * Build wheel in AppVeyor and store it as an artifact

- Improve urllib support in :py:mod:`cheroot._compat`

- :issue:`38` via :pr:`39`: Improve URI parsing:

  * Make it compliant with :rfc:`7230`, :rfc:`7231` and :rfc:`2616`

  * Fix setting of ``environ['QUERY_STRING']`` in WSGI

  * Introduce ``proxy_mode`` and ``strict_mode`` argument in ``server.HTTPRequest``

  * Fix decoding of Unicode URIs in WSGI 1.0 gateway


v5.7.0
======

*(2017-06-24)*

- CI improvements:

  * Don't run tests during deploy stage

  * Use VM based build job environments only for ``pyenv`` environments

  * Opt-in for beta trusty image @ Travis CI

  * Be verbose when running tests (show test names)

  * Show ``xfail``/skip details during test run

- :issue:`34`: Fix ``_handle_no_ssl`` error handler calls

- :issue:`21`: Fix ``test_conn`` tests:

  * Improve setup_server def in HTTP connection tests

  * Fix HTTP streaming tests

  * Fix HTTP/1.1 pipelining test under Python 3

  * Fix ``test_readall_or_close`` test

  * Fix ``test_No_Message_Body``

  * Clarify ``test_598`` fail reason

- :issue:`36`: Add GitHub templates for PR, issue && contributing

- :issue:`27`: Default HTTP Server header to Cheroot version str

- Cleanup :py:mod:`~cheroot._compat` functions from server module


v5.6.0
======

*(2017-06-20)*

- Fix all :pep:`257` related errors in all non-test modules.

  ``cheroot/test/*`` folder is only one left allowed to fail with this linter.

- :cp-issue:`1602` and :pr:`30`: Optimize chunked body reader loop by returning
  empty data is the size is 0.

- :cp-issue:`1486`: Reset buffer if the body size is unknown

- :cp-issue:`1131`: Add missing size hint to SizeCheckWrapper


v5.5.2
======

*(2017-06-18)*

- :pr:`32`: Ignore ``"unknown error"`` and ``"https proxy request"``
  SSL errors.

  Ref: :gh:`sabnzbd/sabnzbd#820 <sabnzbd/sabnzbd/issues/820>`

  Ref: :gh:`sabnzbd/sabnzbd#860 <sabnzbd/sabnzbd/issues/860>`


v5.5.1
======

*(2017-06-18)*

- Make AppVeyor list separate tests in corresponding tab.

- :pr:`29`: Configure Travis CI build stages.

  Prioritize tests by stages.

  Move deploy stage to be run very last after all other stages finish.

- :pr:`31`: Ignore "Protocol wrong type for socket" (EPROTOTYPE) @ OSX for non-blocking sockets.

  This was originally fixed for regular sockets in :cp-issue:`1392`.

  Ref: https://forums.sabnzbd.org/viewtopic.php?f=2&t=22728&p=112251


v5.5.0
======

*(2017-05-02)*

- :issue:`17` via :pr:`25`: Instead of a read_headers function, cheroot now
  supplies a :py:class:`HeaderReader <cheroot.server.HeaderReader>` class to
  perform the same function.

  Any :py:class:`HTTPRequest <cheroot.server.HTTPRequest>` object may override
  the header_reader attribute to customize the handling of incoming headers.

  The server module also presents a provisional implementation of
  a :py:class:`DropUnderscoreHeaderReader
  <cheroot.server.DropUnderscoreHeaderReader>` that will exclude any headers
  containing an underscore. It remains an exercise for the
  implementer to demonstrate how this functionality might be
  employed in a server such as CherryPy.

- :pr:`26`: Configured TravisCI to run tests under OS X.


v5.4.0
======

*(2017-03-19)*

- :pr:`22`: Add "ciphers" parameter to SSLAdapter.


v5.3.0
======

*(2017-03-12)*

- :pr:`8`: Updated style to better conform to :pep:`8`.

  Refreshed project with `jaraco skeleton
  <https://github.com/jaraco/skeleton>`_.

  Docs now built and `deployed at RTD
  <https://cheroot.cherrypy.dev/en/latest/history.html>`_.


v5.2.0
======

*(2017-03-02)*

- :issue:`5`: Set ``Server.version`` to Cheroot version instead of CherryPy
  version.

- :pr:`4`: Prevent tracebacks and drop bad HTTPS connections in the
  ``BuiltinSSLAdapter``, similar to ``pyOpenSSLAdapter``.

- :issue:`3`: Test suite now runs and many tests pass. Some are still failing.


v5.1.0
======

*(2017-01-22)*

- Removed the WSGI prefix from classes in :py:mod:`cheroot.wsgi`. Kept aliases
  for compatibility.

- :issue:`1`: Corrected docstrings in :py:mod:`cheroot.server` and
  :py:mod:`cheroot.wsgi`.

- :pr:`2`: Fixed :py:exc:`ImportError` when pkg_resources cannot find the
  cheroot distribution.


v5.0.1
======

*(2017-01-14)*

- Fix error in ``parse_request_uri`` created in :commit:`68a5769`.


v5.0.0
======

*(2017-01-14)*

- Initial release based on :gh:`cherrypy.cherrypy.wsgiserver 8.8.0
  <cherrypy/cherrypy/tree/v8.8.0/cherrypy/wsgiserver>`.
