# SPDX-License-Identifier: Apache-2.0
"""Wirelang-side adapter modules.

This package contains wirelang-owned indirection layers over third-party
or substrate-specific APIs. Persona-container code imports adapter
surfaces; the adapters delegate to upstream libraries internally.

The adapter pattern is wirelang's stable surface boundary: upstream
library breaking changes touch only the adapter implementation; the
adapter-surface contract is the wirelang-side stable interface.

Current adapters:

- :mod:`wakir_protocol.adapters.spiffe_workload_api` (this module skeleton +
This module mock impl) — SPIFFE Workload API surface stub,
  indirection over the upstream ``spiffe`` PyPI package. Surface +
  hermetic in-process :class:`MockSpiffeWorkloadApiAdapter` for tests;
  real upstream-``spiffe``-backed functional implementation deferred to
This module / Phase-2c.
"""
