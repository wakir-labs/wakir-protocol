# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Callandor GmbH and contributors
"""run_vectors_with invariants: a conforming implementation passes, a
subtly wrong one is caught, and the import plumbing for counterparts works."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from tooling.compat import run_vectors_with as rv

REPO_ROOT = Path(__file__).resolve().parent.parent
VECTORS = REPO_ROOT / "tests" / "fixtures" / "proof-path-vectors"


def test_reference_implementation_passes_every_check() -> None:
    merkle, manifest_mod = rv.load_impl("reference", None)
    failures, checks = rv.run(VECTORS, merkle, manifest_mod)
    assert failures == []
    assert checks >= 20


def test_swapped_sibling_sides_are_detected() -> None:
    ref, _ = rv.load_impl("reference", None)

    def bad_proof(leaves, idx):
        return [(h, "L" if side == "R" else "R") for h, side in ref.merkle_proof(leaves, idx)]

    broken = SimpleNamespace(**{**vars(ref), "merkle_proof": bad_proof})
    failures, _ = rv.run(VECTORS, broken)
    assert any("sibling path" in f for f in failures)


def test_wrong_duplicate_rule_is_detected() -> None:
    """Padding with zero-hashes instead of duplicating the last node."""
    ref, _ = rv.load_impl("reference", None)
    import hashlib

    def bad_tree(leaves):
        levels = [list(leaves)]
        cur = list(leaves)
        while len(cur) > 1:
            if len(cur) % 2:
                cur = cur + [b"\x00" * 32]
            levels[-1] = cur
            cur = [hashlib.sha256(cur[i] + cur[i + 1]).digest() for i in range(0, len(cur), 2)]
            levels.append(cur)
        return cur[0], levels

    broken = SimpleNamespace(**{**vars(ref), "build_merkle_tree": bad_tree})
    failures, _ = rv.run(VECTORS, broken)
    assert any("tree levels differ" in f or "root differs" in f for f in failures)
    # vector-1 (single leaf) is unaffected by the padding rule
    assert not any(f.startswith("vector-1.json") for f in failures)


def test_accepting_tampered_leaf_is_detected() -> None:
    ref, _ = rv.load_impl("reference", None)
    always_true = SimpleNamespace(**{**vars(ref), "verify_merkle_proof": lambda *a, **k: True})
    failures, _ = rv.run(VECTORS, always_true)
    assert any("tampered leaf verified as True" in f for f in failures)


def test_manifest_loader_hook_is_exercised() -> None:
    ref, _ = rv.load_impl("reference", None)

    class Loaded:
        def __init__(self, root):
            self.merkle_root = bytes.fromhex(root)
            self.leaves = []

    fake_manifest = SimpleNamespace(load_manifest_from_dict=lambda m: Loaded(m["merkle_root"]))
    failures, checks_with = rv.run(VECTORS, ref, fake_manifest)
    _, checks_without = rv.run(VECTORS, ref)
    assert checks_with > checks_without
    assert any("manifest loader leaves differ" in f for f in failures)


def test_counterpart_import_plumbing(tmp_path: Path, monkeypatch) -> None:
    pkg = tmp_path / "wat" / "merkle"
    pkg.mkdir(parents=True)
    (tmp_path / "wat" / "__init__.py").write_text("")
    (pkg / "__init__.py").write_text("")
    (pkg / "aggregator.py").write_text(
        "import sys\nsys.path.insert(0, %r)\n"
        "from tooling.compat.run_vectors_with import _reference_impl\n"
        "_r = _reference_impl()\n"
        "compute_leaf_hash = _r.compute_leaf_hash\nbuild_merkle_tree = _r.build_merkle_tree\n"
        "merkle_proof = _r.merkle_proof\nverify_merkle_proof = _r.verify_merkle_proof\n" % str(REPO_ROOT)
    )
    for name in list(sys.modules):
        if name == "wat" or name.startswith("wat."):
            monkeypatch.delitem(sys.modules, name)
    monkeypatch.syspath_prepend(str(tmp_path))
    merkle, manifest_mod = rv.load_impl("runtime", tmp_path)
    assert manifest_mod is None
    failures, _ = rv.run(VECTORS, merkle)
    assert failures == []
    for name in list(sys.modules):
        if name == "wat" or name.startswith("wat."):
            monkeypatch.delitem(sys.modules, name)


def test_main_reference_exit_zero(capsys) -> None:
    assert rv.main(["--impl", "reference"]) == 0
    assert "checks passed" in capsys.readouterr().out


def test_main_requires_root_for_counterparts(tmp_path: Path) -> None:
    assert rv.main(["--impl", "verify"]) == 2
    with pytest.raises(SystemExit):
        rv.main(["--impl", "unknown"])
