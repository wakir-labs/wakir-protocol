<!--
SPDX-License-Identifier: CC-BY-4.0
Copyright (c) 2026 Callandor GmbH and contributors

License: This document is licensed under the Creative Commons Attribution
4.0 International License. To view a copy, see
<https://creativecommons.org/licenses/by/4.0/>.
-->

---
spec: wakir-cross-repo-compat
version: 1.0.0
status: active
date: 2026-09-11
audience: implementers of wakir-runtime and wakir-verify, integrators
license: CC-BY-4.0
---

# Cross-Repo Compatibility Canon (wakir-protocol ↔ wakir-runtime ↔ wakir-verify)

`wakir-protocol` is the canonical home of the JSON schema set, the
shared test vectors and the `wakir-inclusion-proof/v1` format.
`wakir-runtime` (producer) and `wakir-verify` (independent verifier)
mirror parts of that set. This document defines what "compatible"
means, how it is measured, and how the three repositories evolve the
set without silently drifting apart (ADR-0072 Phase 4, sub-item 4c).

## 1. Levels of the canon

| Level | Artefact | Canonical location | Compared how |
|---|---|---|---|
| Schema | 17 JSON Schema 2020-12 documents | `wakir_protocol/schemas/*.json` (runtime mirrors under `wirelang/schemas/`) | canonical digest, §2 |
| Manifest | `wakir-wat-manifest/v1` instance per vector | `tests/fixtures/proof-path-vectors/vector-*.json` → `manifest` | validates against `wakir-wat-manifest-v1.json`; loads with `wakir_verify.manifest`; root re-derives |
| Test vectors | Merkle leaf → levels → root → inclusion proofs (+ tampered case) | `tests/fixtures/proof-path-vectors/` (plus the older jcs-leaf, aip-document, bip32, did-document, slip0010, wakir-ftd packs) | canonical digest of the files **and** execution through each counterpart's implementation (§4.2) |
| Proof format | `wakir-inclusion-proof/v1` | `wakir_protocol/schemas/wakir-inclusion-proof-v1.json`, `$id …/wakir-inclusion-proof-v1/0.1.0` | every `proofs[]` document validates; runtime emits it (`scripts/demo-proof.sh` step 4); verify validates it |
| Version | `MANIFEST_VERSION` ↔ schema `$id` ↔ vectors | `tooling/compat/versions.json` | one vector per declared version; producer constant read from the runtime clone; enum = declared + reserved |

## 2. Canonicalisation rule (the one rule all three repositories implement)

```text
canonical_digest(doc) = sha256( JCS( strip(doc) ) )
```

- `JCS` is RFC 8785 JSON Canonicalization Scheme (`rfc8785.dumps`).
- `strip` removes, **at every nesting depth**,
  1. every object member whose key starts with `x-spdx-` **and whose value is a JSON string**, and
  2. every object member named `description` **whose value is a JSON string**.
- Nothing else is removed. `$id`, `title`, `examples`, `enum`, `required`,
  `additionalProperties` and every other `x-*` key (e.g. `x-canonical-home`)
  are part of the canonical form.

Why string-valued only: five persona schemas define a *property* named
`description` (`properties.description` is an object). A rule that
dropped every `description` member would hide drift in exactly those
property definitions. Licence headers (`x-spdx-*`) differ by design
(Apache-2.0 in protocol, BUSL-1.1 in runtime); annotation wording may
differ; the contract may not.

Reference implementation: `tooling/compat/canon.py`
(`strip_noncanonical`, `canonical_bytes`, `canonical_digest`). CLI:
`python tooling/compat/canonical_schema_digest.py [--json] [PATH …]`.
Pinning tests: `tests/test_compat_canon.py`.

Today (2026-09-11) all 17 schemas and all 21 mirrored vector files are
canonical-identical between protocol and runtime@main except
`wakir-inclusion-proof-v1.json`, which runtime re-mirrors in its Phase-4
W4 change (allowlisted until 2026-09-30, §5).

## 3. Mirror map

`tooling/compat/mirror-map.json` lists, per counterpart, which
protocol-side files are mirrored where:

| Counterpart | Protocol pattern | Mirror directory | Required |
|---|---|---|---|
| runtime | `wakir_protocol/schemas/*.json` | `wirelang/schemas/` | yes |
| runtime | `tests/fixtures/proof-path-vectors/*.json` | `tests/fixtures/proof-path-vectors/` | not yet (flip after runtime W4) |
| runtime | `tests/fixtures/{jcs-leaf,aip-document,bip32,did-document,slip0010-ed25519,wakir-ftd}-vectors/*.json` | same path | yes |
| verify | `tests/fixtures/proof-path-vectors/*.json` | `tests/fixtures/proof-path-vectors/` | not yet (flip after verify W4) |

Semantics: `required: true` → a mirror directory that does not exist is
`missing` (fails). `required: false` → a non-existent directory is
`absent` (informational); once the directory exists every file is
compared and any missing or drifting file fails. Version constants:
`wat/cmd/aggregator_cli.py` `MANIFEST_VERSION` must be one of the
declared manifest versions.

Excluded on purpose (documented in the map): `tests/fixtures/schema-registry/`
(OTS anchor fixture whose byte-level digest pin is stale on both sides —
Cross-Review Zone 3 item, not on the proof path), protocol-only fixture
packs (`tv-w-1`, `tv-w-2`, `persona_definitions`), and Python sources.

## 4. The `compat` gate in wakir-protocol

Workflow `.github/workflows/compat.yml`, job display name (the
Branch-Protection required context):

```text
compat (runtime + verify consume this schema set)
```

Triggers: `pull_request` and `push` to `main`, **no path filter**.
Actions pinned by commit SHA. Enforce is on; there is no audit mode in CI.

### 4.1 Steps

1. Clone `wakir-runtime@main` and `wakir-verify@main` (depth 1).
2. `check_mirror.py --repo runtime` and `--repo verify` — canonical
   digests, allowlist, version constants (§3, §5).
3. `run_vectors_with.py --impl runtime` and `--impl verify` — the
   counterpart's own `compute_leaf_hash`, `build_merkle_tree`,
   `merkle_proof`, `verify_merkle_proof` (and verify's
   `load_manifest_from_dict` + `compute_manifest_consistency`) must
   reproduce every recorded value in the PR's vectors and reject the
   tampered leaf.
4. Overlay the PR's schemas and vector packs into the clones and run the
   counterparts' schema/vector-consuming tests against them:
   runtime — `tests/wat/test_merkle.py`, `test_hash_consistency.py`,
   `test_manifest_v1_schema_smoke.py`, `test_manifest_v2_schema_smoke.py`,
   `test_manifest_signing_schema.py`, `tests/scripts/test_demo_proof.py`,
   `wirelang/tests/test_layer_{0,1,2,3}*.py`, `test_aip_document_golden.py`,
   `test_datalog_caveat_schema.py`, `test_ftd_verifier.py`,
   `test_persona_v2_schema.py`,
   `test_federation_caveat_override_event_export_schema.py`,
   `persona_engine/test_format_conformance.py`;
   verify — `tests/test_merkle_proof.py`, `tests/test_manifest.py`.
   Any counterpart test file mentioning `proof-path-vectors` is added
   automatically, so the counterparts' own vector tests join the gate as
   soon as they land. Two runtime tests are deselected by node id:
   `test_coxsr_03_anchor_manifest_well_formed` and
   `test_coxsr_04_schema_digest_fixture_round_trips` pin the **byte**
   digest of runtime's own copy of `caveat-override-event-export.json`
   and cannot hold for any mirror that is allowed to differ in
   `x-spdx-*`/`description` (Zone 3 follow-up: re-pin on the canonical
   digest or on the protocol bytes).

### 4.2 What runtime and verify implement on their side

Both counterparts run their own gate against `protocol@main` with the
same rule and the same allowlist format:

- **Canonical digest**: §2, byte-for-byte the same algorithm. A
  convenient cross-check: `python tooling/compat/canonical_schema_digest.py`
  in a protocol checkout must print the same digest the counterpart
  computes for its mirrored file.
- **Vectors**: load `tests/fixtures/proof-path-vectors/vector-{1,2,3}.json`
  (mirrored byte-identically or read from the protocol clone). Layout is
  documented in `tests/fixtures/proof-path-vectors/README.md`; each
  vector carries `leaves[]`, `leaf_hashes[]`, `levels[][]`, `merkle_root`,
  `manifest`, `proofs[]`, `expected[]` and (vector-3) `tampered`.
- **Proof documents**: validate against the mirrored
  `wakir-inclusion-proof-v1.json` with `additionalProperties: false`;
  `manifest_version` = manifest `version`, `hour` = manifest `hour_slot`.
- **Allowlist**: §5 format, protocol-side paths, `until` mandatory and
  checked against the UTC date, `tracking` a wakir-labs PR/issue URL.

## 5. Allowlist policy (bounded waivers only)

File `tooling/compat/compat-allowlist.json`:

```json
{
  "schema": "wakir-compat-allowlist/v1",
  "entries": [
    {
      "repo": "runtime",
      "path": "wakir_protocol/schemas/wakir-inclusion-proof-v1.json",
      "reason": "why the mirror is allowed to lag",
      "until": "2026-09-30",
      "tracking": "https://github.com/wakir-labs/wakir-protocol/pull/6"
    }
  ]
}
```

| Field | Rule |
|---|---|
| `repo` | `runtime` or `verify` — the counterpart the waiver applies to |
| `path` | protocol-side path of the mirrored file (must exist) |
| `reason` | one sentence; free text |
| `until` | `YYYY-MM-DD`; **mandatory**; compared with the UTC date at check time; an expired entry **fails the gate** (it does not silently stop applying) |
| `tracking` | `https://github.com/wakir-labs/<repo>/(pull\|issues)/<n>` — the change that removes the need for the entry |

No other keys. No permanent entries. Duplicate `(repo, path)` pairs are
invalid. An allowlisted finding is reported as `allowlisted` with its
expiry and tracking reference; it is never hidden. Validation:
`tooling/compat/allowlist.py`; tests: `tests/test_compat_allowlist.py`
(the shipped file is loaded with the real date on every CI run, so an
expiry turns the protocol CI red until the waiver is removed or
consciously extended).

## 6. Version level

`tooling/compat/versions.json` declares, per format, the versions that
exist today and the vectors that exercise them:

| Format | Declared | Reserved | Out of scope |
|---|---|---|---|
| manifest | `wakir-wat-manifest/v1` (`$id …/wakir-wat-manifest-v1/0.2.0`; producer `wat/cmd/aggregator_cli.py:MANIFEST_VERSION`; vectors 1–3) | `wakir-wat-manifest/v2` (enum reservation, no producer, no vector) | `wat-manifest/1.0`, `wat-manifest/2.0` (`wat-manifest-v2.json`, multi-cap envelope, not read by wakir-verify) |
| inclusion proof | `wakir-inclusion-proof/v1` (`$id …/0.1.0`; vectors 1–3) | — | — |
| vector container | `wakir-proof-path-vector/v1` | — | — |

Known constraint, pinned rather than fixed: the runtime aggregator emits
`version` and `hour_slot`; `wakir_verify.manifest` reads the optional
`envelope` and `hour` keys and therefore yields `envelope == ""` and
`hour is None` for real v1 manifests. Consumers read the version from
`raw["version"]` and the hour from `raw["hour_slot"]`. Changing either
side is a version bump, not a patch.

Second known constraint: the Merkle leaf rule permits an empty
`capability_token_hash`, while `wakir-wat-manifest-v1.json` requires a
64-hex digest per event row; the runtime aggregator checks presence
only. The shared vectors use 64-hex values so that the same leaves are
valid as tree input and as manifest rows; the empty-string leaf case is
covered by `jcs-leaf-vectors/vector-3-no-capability-token.json`.
Resolving the schema/producer mismatch is a Zone 3 decision.

## 7. Evolving the schema set

1. Change the canonical file in `wakir-protocol` (bump the `$id` version
   per the registry's semver rules; add a vector for every new declared
   version; register the slot in `docs/schema-registry-spec.md` §3.1).
2. The protocol PR's `compat` job goes red against the counterparts'
   `main`. Add an allowlist entry with `until` and the tracking URL of the
   counterpart PR that re-mirrors the file. Merge protocol first.
3. Re-mirror in runtime/verify; their gates go green against
   `protocol@main`.
4. Remove the allowlist entry in protocol before `until`.

Byte-tolerance is never the answer; the allowlist is the only escape
hatch, and it expires.

## 8. Local use

```text
git clone --depth 1 https://github.com/wakir-labs/wakir-runtime /tmp/runtime
git clone --depth 1 https://github.com/wakir-labs/wakir-verify  /tmp/verify
python tooling/compat/canonical_schema_digest.py
python tooling/compat/check_mirror.py --repo runtime /tmp/runtime
python tooling/compat/check_mirror.py --repo verify  /tmp/verify
python tooling/compat/run_vectors_with.py --impl runtime /tmp/runtime
python tooling/compat/run_vectors_with.py --impl verify  /tmp/verify
```

Exit codes of `check_mirror.py`: `0` compatible, `1` incompatible or
invalid/expired allowlist, `2` usage/configuration error. `--audit`
reports without failing and exists for local exploration only.
