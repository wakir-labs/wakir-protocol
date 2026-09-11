# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Callandor GmbH and contributors
"""Smoke test for the shared proof-path Merkle vectors.

Loads ``tests/fixtures/proof-path-vectors/vector-{1,2,3}.json`` and
re-derives every recorded value from first principles (``hashlib`` +
RFC 8785 JCS) without importing either the runtime or the verifier
Merkle module. The same files are consumed by ``wat.merkle.aggregator``
(wakir-runtime) and ``wakir_verify.merkle_proof`` (wakir-verify); if any
of the three implementations changes its hash rules, this test or one
of its siblings goes red.

Invariants covered:

- leaf hash = sha256(JCS(four-field tuple))
- inner hash = sha256(left || right)
- odd levels duplicate the last node (Bitcoin convention)
- single-leaf tree: root == leaf, empty sibling path
- every recorded proof reconstructs the recorded root
- the tampered leaf in vector-3 does NOT reconstruct the root
- every proof document validates against the wakir-inclusion-proof/v1
  schema stub
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import jsonschema
import pytest
import rfc8785

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "proof-path-vectors"
SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent
    / "wakir_protocol"
    / "schemas"
    / "wakir-inclusion-proof-v1.json"
)
VECTOR_FILES = ["vector-1.json", "vector-2.json", "vector-3.json"]
LEAF_KEYS = ("event_id", "time", "payload_hash", "capability_token_hash")


# ---------------------------------------------------------------------------
# Reference implementation (deliberately minimal and self-contained)
# ---------------------------------------------------------------------------


def _sha256(b: bytes) -> bytes:
    return hashlib.sha256(b).digest()


def _leaf_hash(leaf: dict) -> bytes:
    assert tuple(sorted(leaf)) == tuple(sorted(LEAF_KEYS)), leaf.keys()
    return _sha256(rfc8785.dumps({k: leaf[k] for k in LEAF_KEYS}))


def _levels(leaves: list[bytes]) -> list[list[bytes]]:
    assert leaves, "zero leaves is not a valid tree"
    levels = [list(leaves)]
    current = list(leaves)
    while len(current) > 1:
        if len(current) % 2 == 1:
            current = current + [current[-1]]
        levels[-1] = current
        current = [_sha256(current[i] + current[i + 1]) for i in range(0, len(current), 2)]
        levels.append(current)
    return levels


def _verify(leaf_hash: bytes, siblings: list[dict], root: bytes) -> bool:
    cur = leaf_hash
    for s in siblings:
        sib = bytes.fromhex(s["hash"])
        if s["side"] == "L":
            cur = _sha256(sib + cur)
        elif s["side"] == "R":
            cur = _sha256(cur + sib)
        else:
            return False
    return cur == root


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def schema_validator() -> jsonschema.Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(schema)


def _load(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_all_three_vectors_present() -> None:
    for name in VECTOR_FILES:
        assert (FIXTURE_DIR / name).is_file(), name


@pytest.mark.parametrize("name", VECTOR_FILES)
def test_recorded_values_rederive_from_first_principles(name: str) -> None:
    vec = _load(name)
    assert vec["schema"] == "wakir-proof-path-vector/v1"
    leaf_hashes = [_leaf_hash(leaf) for leaf in vec["leaves"]]
    assert [h.hex() for h in leaf_hashes] == vec["leaf_hashes"]
    levels = _levels(leaf_hashes)
    assert [[h.hex() for h in lvl] for lvl in levels] == vec["levels"]
    assert levels[-1][0].hex() == vec["merkle_root"]


@pytest.mark.parametrize("name", VECTOR_FILES)
def test_every_recorded_proof_reconstructs_root(name: str, schema_validator) -> None:
    vec = _load(name)
    root = bytes.fromhex(vec["merkle_root"])
    expected = {e["leaf_index"]: e["verified"] for e in vec["expected"]}
    assert len(vec["proofs"]) == len(vec["leaves"]) == len(expected)
    for proof in vec["proofs"]:
        schema_validator.validate(proof)
        idx = proof["leaf_index"]
        assert proof["schema"] == "wakir-inclusion-proof/v1"
        assert proof["leaf_count"] == len(vec["leaves"])
        assert proof["merkle_root"] == vec["merkle_root"]
        assert proof["leaf_hash"] == vec["leaf_hashes"][idx]
        assert _verify(bytes.fromhex(proof["leaf_hash"]), proof["siblings"], root) is expected[idx]


def test_vector_1_single_leaf_root_equals_leaf_and_empty_path() -> None:
    vec = _load("vector-1.json")
    assert len(vec["leaves"]) == 1
    assert vec["merkle_root"] == vec["leaf_hashes"][0]
    assert vec["proofs"][0]["siblings"] == []
    assert vec["levels"] == [[vec["merkle_root"]]]


def test_vector_2_odd_level_duplicates_last_leaf() -> None:
    vec = _load("vector-2.json")
    assert len(vec["leaves"]) == 3
    # Level 0 is recorded post-duplication: four entries, last two equal.
    lvl0 = vec["levels"][0]
    assert len(lvl0) == 4 and lvl0[2] == lvl0[3] == vec["leaf_hashes"][2]
    # The proof for leaf 2 therefore carries its own hash as the level-0
    # sibling, sitting on the right.
    proof = vec["proofs"][2]
    assert proof["siblings"][0] == {"hash": vec["leaf_hashes"][2], "side": "R"}
    assert len(proof["siblings"]) == 2


def test_vector_3_tampered_leaf_does_not_verify() -> None:
    vec = _load("vector-3.json")
    t = vec["tampered"]
    assert t["expected_verified"] is False
    idx = t["leaf_index"]
    honest = vec["leaves"][idx]
    assert t["leaf"] != honest, "tampered leaf must differ from the honest leaf"
    assert _leaf_hash(t["leaf"]).hex() == t["leaf_hash"]
    assert t["leaf_hash"] != vec["leaf_hashes"][idx]
    root = bytes.fromhex(vec["merkle_root"])
    # Same proof, tampered leaf: must fail.
    assert _verify(bytes.fromhex(t["leaf_hash"]), t["proof"]["siblings"], root) is False
    # Same proof, honest leaf: must pass (sanity: the proof itself is intact).
    assert _verify(bytes.fromhex(vec["leaf_hashes"][idx]), t["proof"]["siblings"], root) is True


def test_hash_rules_are_documented_in_every_vector() -> None:
    for name in VECTOR_FILES:
        rules = _load(name)["hash_rules"]
        assert rules["hash"] == "sha256"
        for key in ("leaf", "inner", "odd_level", "sibling_side"):
            assert rules[key], key
