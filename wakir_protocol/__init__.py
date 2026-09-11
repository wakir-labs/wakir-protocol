# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Callandor GmbH and contributors
"""Wakir Protocol — Wirelang specs, capability tokens, identity substrate.

Public protocol layer of the Wakir platform. Bundles the Apache-2.0
licensed protocol substrate (Wirelang spec, capability-token wrapper,
identity-substrate, JSON-schemas) separated from the BUSL-1.1 runtime in
the ``wakir-labs/wakir-runtime`` repo.

Sub-packages:

- :mod:`wakir_protocol.canonical` — JCS canonical-form rules
  (caveat-set canonicalisation, etc).
- :mod:`wakir_protocol.identity_substrate` — AIP/DID-document signing,
  BIP32 key-derivation, recovery drills, Shamir split, KID resolver.
- :mod:`wakir_protocol.persona` — persona canonical-form, persona-hash,
  persona-migration and persona-validator (Apache parts only).
- :mod:`wakir_protocol.schemas` — JSON schemas + schema-registry adapters.
- :mod:`wakir_protocol.adapters` — SPIFFE workload-API + NATS adapter
  stubs.
- :mod:`wakir_protocol.cli` — Apache-licensed CLI helpers (bridge-forward
  publisher, doppelbetrieb aggregate/score).
- :mod:`wakir_protocol.wirelang` — frame-builder + NATS subject-mapping
  reference implementation.
- :mod:`wakir_protocol.examples` — example JSON vectors.

Spec documents live in the repo-level ``docs/`` tree under CC-BY-4.0.

ADR-Anker: ADR-0023a, ADR-0034 §3.3, ADR-0062 Cut-2.
"""

__version__ = "0.1.0"
