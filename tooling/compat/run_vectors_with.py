# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Callandor GmbH and contributors
"""Drive another repository's Merkle implementation over the shared vectors.

Usage::

    python tooling/compat/run_vectors_with.py --impl runtime  /path/to/wakir-runtime
    python tooling/compat/run_vectors_with.py --impl verify   /path/to/wakir-verify
    python tooling/compat/run_vectors_with.py --impl reference

``--impl runtime`` imports ``wat.merkle.aggregator``; ``--impl verify``
imports ``wakir_verify.merkle_proof`` and ``wakir_verify.manifest``;
``--impl reference`` uses a self-contained hashlib + RFC 8785
implementation (the same one ``tests/test_proof_path_vectors.py`` uses).
The counterpart's root directory is put on ``sys.path``; no
installation is needed.

For every vector under ``tests/fixtures/proof-path-vectors/`` the
implementation must reproduce: every leaf hash, every tree level, the
root, every recorded sibling path (hash and side), a ``True`` verdict
for every honest proof, a ``False`` verdict for the tampered leaf, and
— when a manifest loader is available — the manifest's root and leaf
list. Exit ``0`` iff every check passes; mismatches are listed.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
VECTOR_DIR = REPO_ROOT / "tests" / "fixtures" / "proof-path-vectors"
LEAF_KEYS = ("event_id", "time", "payload_hash", "capability_token_hash")
IMPLS = {
    "runtime": ("wat.merkle.aggregator", None),
    "verify": ("wakir_verify.merkle_proof", "wakir_verify.manifest"),
    "reference": (None, None),
}


def _reference_impl() -> SimpleNamespace:
    import rfc8785

    def _sha(b: bytes) -> bytes:
        return hashlib.sha256(b).digest()

    def compute_leaf_hash(event_id: str, time: str, payload_hash: str, capability_token_hash: str) -> bytes:
        return _sha(rfc8785.dumps({
            "event_id": event_id, "time": time,
            "payload_hash": payload_hash, "capability_token_hash": capability_token_hash,
        }))

    def build_merkle_tree(leaves: Sequence[bytes]):
        if not leaves:
            raise ValueError("no leaves")
        levels = [list(leaves)]
        current = list(leaves)
        while len(current) > 1:
            if len(current) % 2 == 1:
                current = current + [current[-1]]
            levels[-1] = current
            current = [_sha(current[i] + current[i + 1]) for i in range(0, len(current), 2)]
            levels.append(current)
        return current[0], levels

    def merkle_proof(leaves: Sequence[bytes], leaf_index: int):
        _, levels = build_merkle_tree(leaves)
        out, idx = [], leaf_index
        for level in levels[:-1]:
            sib = idx ^ 1 if (idx ^ 1) < len(level) else idx
            out.append((level[sib], "L" if sib < idx else "R"))
            idx //= 2
        return out

    def verify_merkle_proof(leaf_hash: bytes, proof, root: bytes) -> bool:
        cur = leaf_hash
        for sibling, side in proof:
            if side == "L":
                cur = _sha(sibling + cur)
            elif side == "R":
                cur = _sha(cur + sibling)
            else:
                return False
        return cur == root

    return SimpleNamespace(
        compute_leaf_hash=compute_leaf_hash,
        build_merkle_tree=build_merkle_tree,
        merkle_proof=merkle_proof,
        verify_merkle_proof=verify_merkle_proof,
    )


def load_impl(kind: str, root: Optional[Path]) -> tuple[Any, Any]:
    """Return ``(merkle_module, manifest_module_or_None)`` for *kind*."""
    if kind not in IMPLS:
        raise ValueError(f"unknown impl {kind!r}; choose from {sorted(IMPLS)}")
    merkle_name, manifest_name = IMPLS[kind]
    if merkle_name is None:
        return _reference_impl(), None
    if root is None:
        raise ValueError(f"--impl {kind} needs the counterpart root directory")
    sys.path.insert(0, str(root.resolve()))
    merkle = importlib.import_module(merkle_name)
    manifest = importlib.import_module(manifest_name) if manifest_name else None
    return merkle, manifest


def run(vector_dir: Path, merkle: Any, manifest_mod: Any = None) -> tuple[list[str], int]:
    """Return ``(failures, checks)`` for every vector in *vector_dir*."""
    failures: list[str] = []
    checks = 0

    def check(cond: bool, msg: str) -> None:
        nonlocal checks
        checks += 1
        if not cond:
            failures.append(msg)

    files = sorted(vector_dir.glob("vector-*.json"))
    check(bool(files), f"no vectors under {vector_dir}")
    for path in files:
        vec = json.loads(path.read_text(encoding="utf-8"))
        name = path.name
        leaves = [merkle.compute_leaf_hash(**{k: leaf[k] for k in LEAF_KEYS}) for leaf in vec["leaves"]]
        check([h.hex() for h in leaves] == vec["leaf_hashes"], f"{name}: leaf hashes differ")
        root, levels = merkle.build_merkle_tree(leaves)
        check([[h.hex() for h in lvl] for lvl in levels] == vec["levels"], f"{name}: tree levels differ")
        check(root.hex() == vec["merkle_root"], f"{name}: root differs")
        root_bytes = bytes.fromhex(vec["merkle_root"])
        for proof in vec["proofs"]:
            idx = proof["leaf_index"]
            got = [(h.hex(), side) for h, side in merkle.merkle_proof(leaves, idx)]
            want = [(s["hash"], s["side"]) for s in proof["siblings"]]
            check(got == want, f"{name}: sibling path for leaf {idx} differs: {got} != {want}")
            check(
                merkle.verify_merkle_proof(bytes.fromhex(proof["leaf_hash"]),
                                           [(bytes.fromhex(s["hash"]), s["side"]) for s in proof["siblings"]],
                                           root_bytes) is True,
                f"{name}: honest proof for leaf {idx} did not verify",
            )
        if "tampered" in vec:
            t = vec["tampered"]
            tampered_leaf = merkle.compute_leaf_hash(**{k: t["leaf"][k] for k in LEAF_KEYS})
            check(tampered_leaf.hex() == t["leaf_hash"], f"{name}: tampered leaf hash differs")
            verdict = merkle.verify_merkle_proof(
                tampered_leaf,
                [(bytes.fromhex(s["hash"]), s["side"]) for s in t["proof"]["siblings"]],
                root_bytes,
            )
            check(verdict is False, f"{name}: tampered leaf verified as True")
        if manifest_mod is not None and "manifest" in vec:
            loaded = manifest_mod.load_manifest_from_dict(vec["manifest"])
            check(loaded.merkle_root.hex() == vec["merkle_root"], f"{name}: manifest loader root differs")
            check([leaf.leaf_hash.hex() for leaf in loaded.leaves] == vec["leaf_hashes"],
                  f"{name}: manifest loader leaves differ")
            if hasattr(manifest_mod, "compute_manifest_consistency"):
                check(manifest_mod.compute_manifest_consistency(loaded) is True,
                      f"{name}: manifest consistency check failed")
    return failures, checks


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("root", nargs="?", type=Path, help="counterpart repository root")
    parser.add_argument("--impl", required=True, choices=sorted(IMPLS))
    parser.add_argument("--vectors", type=Path, default=VECTOR_DIR)
    args = parser.parse_args(argv)
    try:
        merkle, manifest_mod = load_impl(args.impl, args.root)
    except (ValueError, ImportError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    failures, checks = run(args.vectors, merkle, manifest_mod)
    for line in failures:
        print(f"FAIL {line}")
    print(f"proof-path vectors via {args.impl}: {checks - len(failures)}/{checks} checks passed")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
