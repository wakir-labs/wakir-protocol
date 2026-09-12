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
from tooling.compat.canon import canonical_bytes, canonical_digest, strip_noncanonical

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_DIR = REPO_ROOT / "wakir_protocol" / "schemas"
SCHEMAS = sorted(SCHEMA_DIR.glob("*.json"))

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
