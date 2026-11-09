# What is this place?

This folder only contains "lock files" exclusively. Nothing else.
It **MUST NEVER** be edited manually. Ever. Said files are valid Pip
constraints that are generated using `pip-tools`. They are tightly
integrated into the development environment, being mapped to the tox
environments and testing infrastructure.

To update the "lock files", trigger the `pip-tools` GitHub Actions
workflow.

The term "lock files" is used in the context of how the Pip
constraints are made, integrated and used. Without that, they are
mere constraints.

One day, we'll replace them with proper [PEP 751] lock files. That
[Brett Cannon proposed][initial lock files proposal] some time ago.
It is still being discussed [here][PEP 751 discussion].

[initial lock files proposal]:
https://discuss.python.org/t/lock-files-again-but-this-time-w-sdists
[PEP 751]: https://peps.python.org/pep-0751/
[PEP 751 discussion]:
https://discuss.python.org/t/pep-751-lock-files-again
