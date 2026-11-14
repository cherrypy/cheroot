# Where to Look First

When picking up a task, get oriented before proposing anything.
Read, in this order:

1. The packaging metadata -- what the project is, what it depends
   on, what it exposes.
2. The source of the module the task is about.
3. The shared test fixtures, then the tests for that module --
   they are the behavioral contract.
4. `tox.ini` and `.pre-commit-config.yaml` -- how things get run
   locally and in CI.
5. The main CI/CD workflow.

Here:

1. `pyproject.toml` (build backend and metadata).
2. `cheroot/<module>.py` and its `.pyi` stub -- the type
   annotations live in the stubs, checked against the code by
   MyPy's `stubtest` (exceptions in `stubtest_allowlist.txt`).
3. `cheroot/test/conftest.py` and `cheroot/test/_pytest_plugin.py`,
   plus the helpers in `cheroot/test/helper.py` and
   `cheroot/test/webtest.py`, then `cheroot/test/test_<module>.py`.
4. As above, plus `toxfile.py` -- an in-tree tox plugin that
   installs from the lock files.
5. `.github/workflows/ci-cd.yml`, which delegates to
   `tox-dev/workflow`'s `reusable-tox.yml`.

Other places worth knowing:

- `dependencies/` -- direct dependencies per tox env, and the
  pinned lock files generated from them.
- `docs/` -- Sphinx docs (RST); change notes go under
  `docs/changelog-fragments.d/`, and `CHANGES.rst` is generated
  from them.
