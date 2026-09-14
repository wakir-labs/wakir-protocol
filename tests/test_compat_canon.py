# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Callandor GmbH and contributors
"""Invariants of the cross-repo canonicalisation rule (tooling/compat/canon.py).

The rule is what runtime and verify re-implement; these tests pin its
behaviour so that a change here is a deliberate, visible act.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import jsonschema
import pytest

from tooling.compat import canonical_schema_digest as digest_cli
from tooling.compat.canon import (
    KIND_SCHEMA,
    KIND_VECTOR,
    canonical_bytes,
    canonical_digest,
    digest_file,
    strip_noncanonical,
    verbatim_bytes,
    verbatim_digest,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_DIR = REPO_ROOT / "wakir_protocol" / "schemas"
SCHEMAS = sorted(SCHEMA_DIR.glob("*.json"))
VECTOR_PACKS = sorted(
    d for d in (REPO_ROOT / "tests" / "fixtures").iterdir()
    if d.is_dir() and d.name.endswith("-vectors")
)

BASE = {
    "$id": "https://wakir.dev/wirelang/schema/example/0.1.0",
    "title": "Example",
    "x-spdx-license-identifier": "Apache-2.0",
    "x-spdx-file-copyright-text": "2026 Callandor GmbH and contributors",
    "description": "top-level annotation",
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": ["a", "b"], "description": "nested annotation"},
        "description": {"type": "string", "minLength": 1},
    },
    "required": ["kind"],
}


def test_digest_is_independent_of_formatting_and_key_order() -> None:
    reordered = json.loads(json.dumps(BASE, sort_keys=True, indent=4))
    compact = json.loads(json.dumps(BASE, separators=(",", ":")))
    assert canonical_digest(BASE) == canonical_digest(reordered) == canonical_digest(compact)


def test_string_descriptions_and_spdx_keys_are_stripped_at_every_depth() -> None:
    variant = copy.deepcopy(BASE)
    variant["description"] = "different wording"
    variant["properties"]["kind"]["description"] = "also different"
    del variant["x-spdx-license-identifier"]
    variant["x-spdx-file-copyright-text"] = "someone else"
    variant["properties"]["kind"]["x-spdx-anything"] = "extra"
    assert canonical_digest(variant) == canonical_digest(BASE)
    stripped = strip_noncanonical(variant)
    assert "description" not in stripped
    assert "description" not in stripped["properties"]["kind"]
    assert not any(k.startswith("x-spdx-") for k in stripped)


def test_property_named_description_is_kept() -> None:
    """Five persona schemas define a property called ``description``.

    Its definition is an object, not a string, and must remain part of
    the canonical form — otherwise drift inside it would be invisible.
    """
    variant = copy.deepcopy(BASE)
    variant["properties"]["description"]["type"] = "integer"
    assert canonical_digest(variant) != canonical_digest(BASE)
    assert "description" in strip_noncanonical(BASE)["properties"]


def test_enum_change_changes_digest() -> None:
    variant = copy.deepcopy(BASE)
    variant["properties"]["kind"]["enum"].append("c")
    assert canonical_digest(variant) != canonical_digest(BASE)


def test_other_extension_keys_are_canonical() -> None:
    variant = copy.deepcopy(BASE)
    variant["x-canonical-home"] = "wakir-protocol"
    assert canonical_digest(variant) != canonical_digest(BASE)


def test_non_string_spdx_value_is_kept() -> None:
    variant = copy.deepcopy(BASE)
    variant["x-spdx-license-identifier"] = ["Apache-2.0"]
    assert canonical_digest(variant) != canonical_digest(BASE)


def test_canonical_bytes_is_rfc8785() -> None:
    assert canonical_bytes({"b": 1, "a": [1.0, "é"]}) == b'{"a":[1,"\xc3\xa9"],"b":1}'


@pytest.mark.parametrize("path", SCHEMAS, ids=[p.name for p in SCHEMAS])
def test_every_schema_is_valid_2020_12_and_digestible(path: Path) -> None:
    schema = json.loads(path.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["$id"].startswith("https://wakir.dev/")
    assert re.fullmatch(r"[0-9a-f]{64}", canonical_digest(schema))


def test_persona_schemas_keep_their_description_property() -> None:
    hits = 0
    for path in SCHEMAS:
        schema = json.loads(path.read_text(encoding="utf-8"))
        props = schema.get("properties", {})
        if isinstance(props.get("description"), dict):
            hits += 1
            assert "description" in strip_noncanonical(schema)["properties"], path.name
    assert hits >= 1, "expected at least one schema with a property named description"


def test_digest_cli_default_output_covers_every_schema(capsys) -> None:
    assert digest_cli.main([]) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == len(SCHEMAS)
    for line in lines:
        assert re.fullmatch(r"[0-9a-f]{64}  wakir_protocol/schemas/[^ ]+\.json", line), line


def test_digest_cli_json_matches_library(capsys) -> None:
    assert digest_cli.main(["--json", str(SCHEMAS[0])]) == 0
    data = json.loads(capsys.readouterr().out)
    rel = str(SCHEMAS[0].relative_to(REPO_ROOT))
    assert data == {rel: canonical_digest(json.loads(SCHEMAS[0].read_text(encoding="utf-8")))}


# ---------------------------------------------------------------------------
# R4 (external re-review 2026-09-14): instance data must not be stripped.
#
# The rule used to remove every string-valued ``description`` (and every
# string-valued ``x-spdx-*``) at every depth. Applied inside ``const``,
# ``enum``, ``default`` or ``examples`` that erases *instance data*: two
# schemas that accept different instances collapsed to one digest and the
# compat gate reported green for a semantic change. These are the negative
# controls for that class; each pair differs only in instance data and must
# therefore produce *different* digests.
# ---------------------------------------------------------------------------

INSTANCE_DATA_PAIRS = [
    pytest.param(
        {"const": {"description": "approved"}},
        {"const": {"description": "denied"}},
        id="const-object-with-description",
    ),
    pytest.param(
        {"enum": [{"description": "low"}, {"description": "critical"}]},
        {"enum": [{"description": "low"}, {"description": "fatal"}]},
        id="enum-objects-with-description",
    ),
    pytest.param(
        {"default": {"description": "on"}},
        {"default": {"description": "off"}},
        id="default-object-with-description",
    ),
    pytest.param(
        {"examples": [{"description": "first"}]},
        {"examples": [{"description": "second"}]},
        id="examples-object-with-description",
    ),
    pytest.param(
        {"const": {"x-spdx-license-identifier": "Apache-2.0"}},
        {"const": {"x-spdx-license-identifier": "BUSL-1.1"}},
        id="const-object-with-spdx-key",
    ),
    pytest.param(
        # Deeply nested: the instance-data context must survive the descent.
        {"$defs": {"decision": {"properties": {"outcome": {"oneOf": [
            {"const": {"meta": {"labels": [{"description": "approved"}]}}}]}}}}},
        {"$defs": {"decision": {"properties": {"outcome": {"oneOf": [
            {"const": {"meta": {"labels": [{"description": "denied"}]}}}]}}}}},
        id="nested-const-deep-in-the-tree",
    ),
]


@pytest.mark.parametrize("left,right", INSTANCE_DATA_PAIRS)
def test_instance_data_difference_changes_the_digest(left: dict, right: dict) -> None:
    assert strip_noncanonical(left) == left, "instance data must survive stripping verbatim"
    assert strip_noncanonical(right) == right
    assert canonical_digest(left) != canonical_digest(right)


def test_const_with_description_accepts_different_instances() -> None:
    """The negative control is a real semantic difference, not a hash game."""
    left = {"const": {"description": "approved"}}
    right = {"const": {"description": "denied"}}
    instance = {"description": "approved"}
    assert jsonschema.Draft202012Validator(left).is_valid(instance)
    assert not jsonschema.Draft202012Validator(right).is_valid(instance)
    assert canonical_digest(left) != canonical_digest(right)


def test_annotation_difference_still_collapses_to_one_digest() -> None:
    """Positive control: annotation wording stays outside the contract.

    This is the *purpose* of the canonicalisation and must not regress
    while the instance-data hole is closed.
    """
    left = copy.deepcopy(BASE)
    right = copy.deepcopy(BASE)
    right["description"] = "a different top-level wording"
    right["properties"]["kind"]["description"] = "a different nested wording"
    right["x-spdx-license-identifier"] = "BUSL-1.1"
    assert canonical_digest(left) == canonical_digest(right)


def test_annotation_inside_an_enum_of_schemas_is_still_stripped() -> None:
    """``anyOf``/``oneOf``/``prefixItems`` hold *schemas*, not instances."""
    left = {"anyOf": [{"type": "string", "description": "a name"}]}
    right = {"anyOf": [{"type": "string", "description": "an identifier"}]}
    assert canonical_digest(left) == canonical_digest(right)
    assert "description" not in strip_noncanonical(left)["anyOf"][0]


@pytest.mark.parametrize("keyword", ["properties", "patternProperties", "$defs", "dependentSchemas"])
def test_name_keyed_members_are_never_treated_as_annotations(keyword: str) -> None:
    """A property named ``description`` is a property, not an annotation.

    Its *value* is a subschema and is stripped as one; the member itself
    must survive, otherwise drift in the definition becomes invisible.
    """
    doc = {keyword: {"description": {"type": "string", "description": "annotation"}}}
    stripped = strip_noncanonical(doc)
    assert "description" in stripped[keyword]
    assert stripped[keyword]["description"] == {"type": "string"}
    variant = copy.deepcopy(doc)
    variant[keyword]["description"]["type"] = "integer"
    assert canonical_digest(variant) != canonical_digest(doc)


def test_property_named_like_an_instance_keyword_is_not_an_instance_context() -> None:
    """``properties.const`` is a property named ``const``, not a ``const``."""
    doc = {"properties": {"const": {"type": "string", "description": "annotation"}}}
    assert strip_noncanonical(doc) == {"properties": {"const": {"type": "string"}}}


# ---------------------------------------------------------------------------
# Vectors are instance data: digested unstripped (KIND_VECTOR).
# ---------------------------------------------------------------------------


def test_vector_digest_does_not_strip_anything() -> None:
    left = {"description": "the honest leaf", "leaf_hash": "00"}
    right = {"description": "the tampered leaf", "leaf_hash": "00"}
    assert verbatim_digest(left) != verbatim_digest(right)
    assert canonical_digest(left) == canonical_digest(right)  # the schema rule would collapse them


def test_vector_digest_is_still_jcs_normalised() -> None:
    doc = {"b": 1, "a": [1.0, "é"]}
    assert verbatim_bytes(doc) == b'{"a":[1,"\xc3\xa9"],"b":1}'
    reordered = json.loads(json.dumps(doc, sort_keys=True, indent=4))
    assert verbatim_digest(doc) == verbatim_digest(reordered)


@pytest.mark.parametrize("pack", VECTOR_PACKS, ids=[p.name for p in VECTOR_PACKS])
def test_every_shipped_vector_is_digestible_under_the_vector_rule(pack: Path) -> None:
    files = sorted(pack.glob("*.json"))
    assert files, f"{pack.name} holds no vector"
    for path in files:
        assert re.fullmatch(r"[0-9a-f]{64}", digest_file(path, KIND_VECTOR))


def test_shipped_vectors_carry_members_the_schema_rule_would_have_erased() -> None:
    """Why the split matters here and not only in theory.

    The proof-path and jcs-leaf packs carry string-valued ``description``
    / ``x-spdx-*`` members. Under the old single rule those bytes were
    outside the compared contract; under ``KIND_VECTOR`` they are inside
    it.
    """
    affected = [
        path
        for pack in VECTOR_PACKS
        for path in sorted(pack.glob("*.json"))
        if digest_file(path, KIND_VECTOR) != digest_file(path, KIND_SCHEMA)
    ]
    assert affected, "expected at least one vector whose two digests differ"


def test_digest_file_rejects_an_unknown_kind() -> None:
    with pytest.raises(ValueError):
        digest_file(SCHEMAS[0], "manifest")


def test_digest_cli_kind_vector_matches_library(capsys) -> None:
    vector = REPO_ROOT / "tests" / "fixtures" / "proof-path-vectors" / "vector-1.json"
    assert digest_cli.main(["--kind", "vector", "--json", str(vector)]) == 0
    data = json.loads(capsys.readouterr().out)
    rel = str(vector.relative_to(REPO_ROOT))
    assert data == {rel: verbatim_digest(json.loads(vector.read_text(encoding="utf-8")))}


def test_digest_cli_rule_prints_both_rules(capsys) -> None:
    assert digest_cli.main(["--rule"]) == 0
    out = capsys.readouterr().out.strip().splitlines()
    assert len(out) == 2
    assert out[0].startswith("schema:") and out[1].startswith("vector:")
