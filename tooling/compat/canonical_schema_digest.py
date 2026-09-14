# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Callandor GmbH and contributors
"""Print the canonical digest of each JSON schema (or any JSON file).

Usage::

    python tooling/compat/canonical_schema_digest.py [PATH ...]
    python tooling/compat/canonical_schema_digest.py --json [PATH ...]
    python tooling/compat/canonical_schema_digest.py --kind vector PATH ...

Without arguments every ``wakir_protocol/schemas/*.json`` file is
digested. Output is ``<sha256hex>  <path>`` per line (``sha256sum``
style) or a JSON object ``{path: digest}`` with ``--json``.

``--kind`` selects the rule (:mod:`tooling.compat.canon`): ``schema``
(default) strips annotations, ``vector`` digests the document
unstripped. Passing a test vector without ``--kind vector`` yields a
digest that is not the one the compat gate compares.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable, Sequence

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tooling.compat.canon import KIND_SCHEMA, KINDS, digest_file, rule_text  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GLOB = REPO_ROOT / "wakir_protocol" / "schemas"


def _default_paths() -> list[Path]:
    return sorted(DEFAULT_GLOB.glob("*.json"))


def digests(paths: Iterable[Path], kind: str = KIND_SCHEMA) -> dict[str, str]:
    out: dict[str, str] = {}
    for path in paths:
        try:
            rel = str(path.resolve().relative_to(REPO_ROOT))
        except ValueError:
            rel = str(path)
        out[rel] = digest_file(path, kind)
    return out


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--json", action="store_true", help="emit a JSON object")
    parser.add_argument("--kind", choices=KINDS, default=KIND_SCHEMA,
                        help="canonicalisation rule to apply (default: schema)")
    parser.add_argument("--rule", action="store_true", help="print both rules and exit")
    args = parser.parse_args(argv)

    if args.rule:
        for kind in KINDS:
            print(rule_text(kind))
        return 0

    paths = args.paths or _default_paths()
    result = digests(paths, args.kind)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        for rel, digest in result.items():
            print(f"{digest}  {rel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
