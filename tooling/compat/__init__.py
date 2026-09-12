# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Callandor GmbH and contributors
"""Cross-repo compatibility tooling for the wakir schema set.

``wakir-protocol`` is the canonical home of the JSON schemas, the shared
test vectors and the ``wakir-inclusion-proof/v1`` document format.
``wakir-runtime`` and ``wakir-verify`` mirror parts of that set. The
modules in this package make drift between the three repositories
visible and blocking:

- :mod:`canon` — the canonicalisation rule and digest (the single
  definition all three repositories implement).
- :mod:`allowlist` — the bounded-waiver format (``compat-allowlist.json``).
- :mod:`check_mirror` — compares this repository against a local clone of
  runtime or verify using the mirror map.
- :mod:`run_vectors_with` — drives another repository's Merkle
  implementation over the shared proof-path vectors.
- :mod:`canonical_schema_digest` — prints the canonical digest per schema.

Dependencies: Python standard library plus ``rfc8785``. Nothing else.
"""
