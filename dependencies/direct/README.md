# What is this place?

This folder only contains direct dependency definitions mapped to
their corresponding `tox` environments. This is the place to declare
any new ones. Only set lower version boundaries in those files,
corresponding to when the features we rely on were introduced,
API-wise.

Never add transitive (indirect) dependencies here. If a broken version
of any dependency type (direct or transitive) needs to be excluded
from the dependency resolution, use `*-constraints.in` files to list
things that are not allowed. Be precise, exclude specific versions
on specific platform using environment markers where possible.
