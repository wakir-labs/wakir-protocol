# wakir-protocol

**Wakir Protocol — Wirelang specs, capability tokens, identity substrate.**

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](LICENSE)
[![Docs: CC-BY-4.0](https://img.shields.io/badge/Docs-CC--BY--4.0-lightgrey.svg)](LICENSES/CC-BY-4.0.txt)

> **Skeleton README — final marketing copy delivered by Júlia in
> Cut-2-Tag-2 (Comms-Hand).** This skeleton exists so the empty
> public repo has a navigable landing page from day one.

## Was ist `wakir-protocol`?

`wakir-protocol` ist die Protocol-Layer-Substrate der Wakir-Plattform.
Sie enthält:

- **Wirelang-Spec Layer 0–2** — Transport, Wire, Semantic (siehe
  [`docs/wirelang-spec-v0-2.md`](docs/wirelang-spec-v0-2.md)).
- **Capability-Token-Wrapper** — AIP+Biscuit-Adopter-Pattern
  ([`docs/layer-3-capability-token-spec.md`](docs/layer-3-capability-token-spec.md)).
- **Identity-Substrate** — DID-Methode, BIP32-HD-Konvention, Recovery-
  Drills ([`docs/identity-substrate-spec.md`](docs/identity-substrate-spec.md)).
- **JSON-Schemas** — AIP-Document, WAT-Manifest-v2, Wirelang-Layer-0/1/2/3,
  Recovery-Drill, Federation-Trust-Document.
- **Reference-Parser** (Python) — `wakir_protocol.wirelang.frame_builder`,
  `wakir_protocol.canonical.caveat_set`.

## Licensing

- **Code (`wakir_protocol/`, `tests/`):** Apache-2.0 — siehe [LICENSE](LICENSE).
- **Spec-Docs (`docs/`):** CC-BY-4.0 file-level SPDX — siehe
  [LICENSES/CC-BY-4.0.txt](LICENSES/CC-BY-4.0.txt).

SPDX-Headers werden via REUSE-Tooling ([REUSE.toml](REUSE.toml)) verwaltet.

## Verwandte Repos

- [`wakir-labs/wakir-verify`](https://github.com/wakir-labs/wakir-verify)
  — Brand-Proof External Verifier (Apache-2.0).
- [`wakir-labs/wakir-runtime`](https://github.com/wakir-labs/wakir-runtime)
  — Persona-Engine, Federation-Substrate, Operational Runtime
  (BUSL-1.1 mit Apache-2.0-Foundation-Anteilen).

## Installation

```bash
pip install wakir-protocol
```

oder von Source:

```bash
git clone https://github.com/wakir-labs/wakir-protocol
cd wakir-protocol
pip install -e .
```

## Quick-Start

```python
from wakir_protocol.identity_substrate import aip_document
from wakir_protocol.schemas import wakir_persona_v1
from wakir_protocol.canonical import caveat_set
```

Vollständige Examples in
[`wakir_protocol/examples/`](wakir_protocol/examples/) und
Test-Vektoren in [`tests/fixtures/`](tests/fixtures/).

## Spec-Versions

- Wirelang Layer 0–2: `v0.2.0` (`docs/wirelang-spec-v0-2.md`)
- Capability-Token Layer 3: AIP-document + Biscuit-v3 wrapping
- Identity-Substrate: DID-Methode `did:wakir`, BIP32-HD m/44'/...
- WAT-Manifest: v2 (`wakir_protocol/schemas/wat-manifest-v2.json`)

## Status

- **Version:** `0.1.0` (initial public release per ADR-0062 Cut-2).
- **Stability:** Beta. Layer 0–2 spec stable. Layer 3 capability-token-
  envelope stable. Datalog-Caveat-Vocabulary Phase-1 stable, Phase-2 draft.

## Contributing

Bug-Reports und Spec-Fragen via
[GitHub-Issues](https://github.com/wakir-labs/wakir-protocol/issues).

## Verweise

- ADR-0023a — Wirelang Tech-Spec.
- ADR-0034 §3.3 — Repo- und Lizenz-Strategie.
- ADR-0062 Cut-2 — Repo-Split-Strategie Phase-2.

---

*Skeleton-README. Júlia liefert finale Marketing-Copy + Adopter-Onboarding-
Section in Cut-2-Tag-2.*
