# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Callandor GmbH and contributors
"""Version level of the compatibility canon (tooling/compat/versions.json).

Invariant: every declared wire-format version maps to exactly one schema
``$id`` and to at least one shared vector that actually uses it; reserved
versions have no vector; the manifest schema's enum is exactly declared
plus reserved.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
VERSIONS = json.loads((REPO_ROOT / "tooling" / "compat" / "versions.json").read_text(encoding="utf-8"))
MIRROR_MAP = json.loads((REPO_ROOT / "tooling" / "compat" / "mirror-map.json").read_text(encoding="utf-8"))
GROUPS = ("manifest", "inclusion_proof", "proof_path_vector")


def _load(rel: str) -> dict:
    return json.loads((REPO_ROOT / rel).read_text(encoding="utf-8"))


def _version_used(group: str, vector: dict, version: str) -> bool:
    if group == "manifest":
        return vector["manifest"]["version"] == version and all(
            p["manifest_version"] == version for p in vector["proofs"]
        )
    if group == "inclusion_proof":
        return all(p["schema"] == version for p in vector["proofs"]) and (
            "tampered" not in vector or vector["tampered"]["proof"]["schema"] == version
        )
    return vector["schema"] == version


def test_versions_file_shape() -> None:
    assert VERSIONS["schema"] == "wakir-compat-versions/v1"
    for group in GROUPS:
        assert VERSIONS[group]["declared"], group


@pytest.mark.parametrize("group", GROUPS)
def test_every_declared_version_has_schema_id_and_vectors(group: str) -> None:
    for entry in VERSIONS[group]["declared"]:
        assert entry["vectors"], f"{group}: {entry['version']} has no vector"
        if entry["schema"] is not None:
            schema = _load(entry["schema"])
            assert schema["$id"] == entry["schema_id"], entry["version"]
        for rel in entry["vectors"]:
            vector = _load(rel)
            assert _version_used(group, vector, entry["version"]), f"{rel} does not use {entry['version']}"


def test_manifest_enum_is_exactly_declared_plus_reserved() -> None:
    schema = _load("wakir_protocol/schemas/wakir-wat-manifest-v1.json")
    enum = set(schema["properties"]["version"]["enum"])
    declared = {e["version"] for e in VERSIONS["manifest"]["declared"]}
    reserved = {e["version"] for e in VERSIONS["manifest"]["reserved"]}
    assert enum == declared | reserved
    assert not declared & reserved


def test_reserved_versions_have_no_vector() -> None:
    reserved = {e["version"] for e in VERSIONS["manifest"]["reserved"]}
    for rel in sorted((REPO_ROOT / "tests" / "fixtures" / "proof-path-vectors").glob("vector-*.json")):
        vector = json.loads(rel.read_text(encoding="utf-8"))
        assert vector["manifest"]["version"] not in reserved
        assert all(p["manifest_version"] not in reserved for p in vector["proofs"])


def test_out_of_scope_versions_are_not_on_the_proof_path() -> None:
    schema = _load("wakir_protocol/schemas/wat-manifest-v2.json")
    out = set()
    for entry in VERSIONS["manifest"]["out_of_scope"]:
        out |= set(entry["versions"])
    assert set(schema["properties"]["version"]["enum"]) == out
    declared = {e["version"] for e in VERSIONS["manifest"]["declared"]}
    assert not out & declared


def test_producer_constant_is_wired_into_mirror_map() -> None:
    consts = MIRROR_MAP["repos"]["runtime"]["version_constants"]
    assert len(consts) == 1
    const = consts[0]
    producer = VERSIONS["manifest"]["declared"][0]["producer_constant"]
    assert const["path"] == producer["path"]
    assert const["declared_in"] == "manifest"
    regex = re.compile(const["regex"], re.MULTILINE)
    assert regex.search('X = 1\nMANIFEST_VERSION = "wakir-wat-manifest/v1"\n').group(1) == "wakir-wat-manifest/v1"
    assert regex.search('EXPECTED_MANIFEST_VERSION = "0.5.1"\n') is None


def test_field_map_pins_the_known_divergence() -> None:
    fm = VERSIONS["manifest"]["field_map"]
    assert {"version", "hour_slot"} <= set(fm["runtime_emits"])
    assert {"envelope", "hour", "merkle_root"} <= set(fm["verify_reads"])
    assert "raw['version']" in fm["constraint"]
