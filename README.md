# wakir-protocol

**The Wakir Protocol — Wirelang specs, capability tokens, identity substrate.**

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](LICENSE)
[![Docs: CC-BY-4.0](https://img.shields.io/badge/Docs-CC--BY--4.0-lightgrey.svg)](LICENSES/CC-BY-4.0.txt)

`wakir-protocol` is the language layer of the Wakir stack: the typed
inter-agent message formats, JSON schemas, capability-token envelope,
and identity-substrate conventions that let independent runtimes,
verifiers, and auditors interoperate. The runtime that uses these
artefacts lives in
[`wakir-labs/wakir-runtime`](https://github.com/wakir-labs/wakir-runtime),
and the third-party verifier lives in
[`wakir-labs/wakir-verify`](https://github.com/wakir-labs/wakir-verify).

The repository is intentionally narrow: this is the surface external
adopters depend on. Operational concerns — orchestration, federation,
persona engines — stay in the runtime.

## 1. What is stable

The pieces below are stable and safe to depend on at the current
package version. Breaking changes will go through an explicit
major-version bump.

- **Wirelang Layer 0–2** — transport, wire, and semantic layers
  of the inter-agent message format, defined in
  [`docs/wirelang-spec-v0-2.md`](docs/wirelang-spec-v0-2.md).
- **JSON schemas** — `wakir_protocol/schemas/`, covering AIP
  document, WAT manifest v2, Wirelang layers 0/1/2/3,
  recovery-drill, and federation-trust document. Each schema is
  version-pinned and accompanied by test vectors under
  `tests/fixtures/`. The shared proof-path Merkle vectors
  (`tests/fixtures/proof-path-vectors/`) are consumed by all three
  repositories; `wakir-inclusion-proof-v1.json` is the canonical
  schema for the proof document they carry. The cross-repo `compat`
  gate that keeps runtime and verify aligned with this schema set is
  described in [`docs/cross-repo-compat.md`](docs/cross-repo-compat.md).
- **Capability-token envelope** — the Layer-3 wrapper around
  AIP + Biscuit, specified in
  [`docs/layer-3-capability-token-spec.md`](docs/layer-3-capability-token-spec.md).
- **Identity substrate** — the `did:wakir` DID method, BIP32-HD
  derivation conventions, and recovery-drill projection, specified
  in [`docs/identity-substrate-spec.md`](docs/identity-substrate-spec.md).
- **Canonicalisation contract** — JCS + SHA-256 + lower-case hex,
  shared with WAT for leaf hashing; reference implementation under
  `wakir_protocol.canonical`.

## 2. What is experimental

The pieces below are published in the repository but explicitly not
covered by the stability contract. They may change shape under the
same major version.

- **Datalog caveat vocabulary, set 2.** The first set is stable;
  the second set is draft. The split is documented in the layer-3
  spec.
- **Federation-trust document v2.** Schema published, semantics
  may evolve as cross-organisation federation experience
  accumulates.
- **Multi-capability leaf projection.** Today the WAT leaf
  projection commits to a single capability per frame. A future
  multi-capability variant will land additively, without breaking
  the single-cap path.

If you depend on an experimental artefact, please open an issue so
we know to coordinate before any breaking change.

## 3. How do I validate a frame

Two paths, depending on whether you are validating from Python or
from another language:

```python
from wakir_protocol.wirelang import frame_builder
from wakir_protocol.schemas import load_schema

frame = frame_builder.build_l1(
    event_id="evt-...",
    payload={"...": "..."},
    capability_token=cap,
)

# Schema validation
schema = load_schema("wirelang-layer-1")
schema.validate(frame)

# Canonical hash
from wakir_protocol.canonical import leaf_hash
leaf = leaf_hash(frame)
```

If you are validating from another language, the JSON schemas under
`wakir_protocol/schemas/` are vanilla JSON Schema draft 2020-12 and
the canonical hash is JCS (RFC 8785) + SHA-256, lower-case hex. The
authoritative test vectors live under
[`tests/fixtures/jcs-leaf-vectors/`](tests/fixtures/jcs-leaf-vectors/);
any implementation that reproduces those `expected_leaf_hash` values
is wire-compatible.

The full validation contract — including how Layer-1 frames project
onto WAT leaves for audit-trail purposes — is documented in
[`docs/wirelang-spec-v0-2.md`](docs/wirelang-spec-v0-2.md) §4.

## 4. How do I use the schemas

The schemas are shipped both as files (`wakir_protocol/schemas/`)
and as a loader (`wakir_protocol.schemas.load_schema`). The loader
returns a validator pre-bound to the schema's `$id`, so cross-schema
`$ref` resolves locally without a network fetch.

```python
from wakir_protocol.schemas import load_schema

aip = load_schema("aip-document")
aip.validate(my_aip_doc)

manifest = load_schema("wat-manifest-v2")
manifest.validate(my_manifest)
```

Each schema is versioned in its `$id`; minor revisions keep the
same major number and stay backwards-compatible. The currently
shipped schemas are:

- `aip-document` — AIP identity document
- `wakir-wat-manifest-v1` — WAT hourly manifest, `wakir-wat-manifest/v1`
  (emitted by the runtime aggregator, read by `wakir-verify`)
- `wakir-inclusion-proof-v1` — self-contained Merkle inclusion proof,
  `wakir-inclusion-proof/v1` (emitted by the runtime proof path,
  validated by `wakir-verify`)
- `wat-manifest-v2` — WAT hourly manifest v2 (multi-capability envelope;
  not on the proof path)
- `wirelang-layer-0` / `-1` / `-2` / `-3` — Wirelang layer schemas
- `recovery-drill` — recovery-drill projection
- `federation-trust-document` — cross-organisation trust posture

## 5. How does this relate to wakir-runtime and wakir-verify

The Wakir stack is split across three repositories, by intent:

- **`wakir-protocol`** (this repository) — the language. Apache-2.0
  code plus CC-BY-4.0 spec prose. Stable surface for adopters.
- **[`wakir-runtime`](https://github.com/wakir-labs/wakir-runtime)**
  — the operator. The reference implementation that turns the
  protocol into a running accountable multi-agent organization.
  Mixed-license, BUSL-1.1-dominant for operational modules.
- **[`wakir-verify`](https://github.com/wakir-labs/wakir-verify)**
  — the third-party check. A single-binary verifier that
  reconstructs an inclusion proof from a public WAT archive and
  validates the Bitcoin attestation. Apache-2.0, zero PyPI
  surface on the hot path.

The one-line gloss:

> `wakir-protocol` defines the language, `wakir-runtime` operates
> the organization, `wakir-verify` checks the proof.

If you are building your own runtime against the Wakir wire formats,
or if you are an auditor consuming someone else's WAT archive, you
depend on `wakir-protocol` and (optionally) `wakir-verify`. You do
not need `wakir-runtime` to interoperate.

## Installation

```bash
pip install wakir-protocol
```

Or from source:

```bash
git clone https://github.com/wakir-labs/wakir-protocol
cd wakir-protocol
pip install -e .
```

## Licensing

- **Code (`wakir_protocol/`, `tests/`):** Apache-2.0 — see
  [LICENSE](LICENSE).
- **Specification documents (`docs/`):** CC-BY-4.0 with file-level
  SPDX headers — see [LICENSES/CC-BY-4.0.txt](LICENSES/CC-BY-4.0.txt).

SPDX headers are managed via REUSE tooling
([REUSE.toml](REUSE.toml)). The split is deliberate: code is
adopted under a permissive open-source license; spec prose is
adopted under a license that requires attribution, so that
implementations remain traceable to the spec they implement.

## Contributing

Bug reports, spec questions, and interoperability findings are
welcome via
[GitHub Issues](https://github.com/wakir-labs/wakir-protocol/issues).

Wakir Labs is a project of Callandor GmbH. Documentation files in
this repository are released under Creative Commons Attribution 4.0
International (CC-BY-4.0) where indicated.
