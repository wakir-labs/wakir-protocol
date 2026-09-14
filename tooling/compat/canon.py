# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Callandor GmbH and contributors
"""Canonicalisation rules for cross-repo schema and vector comparison.

Two artefact kinds, two rules
-----------------------------

The compatibility gate compares two different kinds of JSON document and
they do **not** share a rule:

``KIND_SCHEMA`` — JSON Schema documents (``wakir_protocol/schemas/*.json``)::

    sha256( JCS( strip_noncanonical(document) ) )

``KIND_VECTOR`` — test vectors and every other instance document
(``tests/fixtures/**/vector-*.json``)::

    sha256( JCS(document) )

``JCS`` is RFC 8785 JSON Canonicalization Scheme serialisation
(``rfc8785.dumps``) in both cases: indentation, key order, whitespace and
unicode escaping never affect a digest — that is what JCS is for.
Nothing beyond that is normalised for vectors. A vector is data; every
byte of it is part of the contract, including any member that happens to
be called ``description``.

What ``strip_noncanonical`` removes — and where it must not
-----------------------------------------------------------

Inside a **schema**, ``strip_noncanonical`` removes, at every nesting
depth of the *schema structure*,

1. every object member whose key starts with ``x-spdx-`` **and whose
   value is a JSON string** (licence-header metadata; Apache-2.0 in
   protocol, BUSL-1.1 in runtime — the divergence is intentional), and
2. every object member named ``description`` **whose value is a JSON
   string** (human-readable annotations; wording may differ between
   mirrors without changing the contract).

Both rules apply to *annotations* only. They are suspended in two
contexts, because in those contexts a member named ``description`` (or
``x-spdx-…``) is not an annotation of the surrounding schema:

* **Instance data.** The values of ``const``, ``default``, ``enum`` and
  ``examples`` are instances, not subschemas. They are kept verbatim,
  at any depth. Without this exception ``{"const": {"description":
  "approved"}}`` and ``{"const": {"description": "denied"}}`` — two
  schemas that accept *different instances* — collapse to the same
  digest, and the gate reports green for a semantic change. That is a
  false negative of the gate itself, so the exception is a correctness
  requirement, not a nicety. (Found by the external re-review of
  2026-09-14, finding R4; no schema in the tree hit it at that point,
  which is why the digests did not move when the rule was corrected.)

* **Name-keyed maps.** In ``properties``, ``patternProperties``,
  ``$defs``, ``definitions``, ``dependentSchemas``, ``dependentRequired``
  and ``$vocabulary`` the member *names* are arbitrary identifiers, not
  schema keywords. A property named ``description`` is a property, and a
  property named ``const`` is a property — neither is an annotation and
  neither opens an instance-data context. Five persona schemas define a
  property called ``description``; drift inside such a definition must
  stay visible. The member *values* are subschemas and are stripped as
  such.

Nothing else is stripped. In particular ``$id``, ``title``, ``enum``,
``required``, ``additionalProperties`` and every other ``x-*`` extension
key are part of the canonical form of a schema.

Every repository that participates in the compatibility gate implements
these rules identically; the reference is this module.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Union

import rfc8785

#: Artefact kinds, matching the ``kind`` field of ``mirror-map.json``.
KIND_SCHEMA = "schema"
KIND_VECTOR = "vector"
KINDS: tuple[str, ...] = (KIND_SCHEMA, KIND_VECTOR)

#: Prefix of keys that are stripped when their value is a string.
STRIP_KEY_PREFIXES: tuple[str, ...] = ("x-spdx-",)

#: Exact keys that are stripped when their value is a string.
STRIP_STRING_KEYS: tuple[str, ...] = ("description",)

#: Schema keywords whose value is *instance data*, not a subschema.
#: Their subtree is canonical in full — no stripping at any depth below.
INSTANCE_DATA_KEYWORDS: tuple[str, ...] = ("const", "default", "enum", "examples")

#: Schema keywords whose object members are named by the *author*, not by
#: the JSON Schema vocabulary. The names are never annotations and never
#: open an instance-data context; the values are subschemas (or, for
#: ``dependentRequired``/``$vocabulary``, plain data that contains no
#: annotations).
NAME_KEYED_KEYWORDS: tuple[str, ...] = (
    "properties",
    "patternProperties",
    "$defs",
    "definitions",
    "dependentSchemas",
    "dependentRequired",
    "$vocabulary",
)

#: One-line statement of the schema rule, printed by the CLIs.
RULE_TEXT = (
    "schema: sha256(JCS(strip(doc))) — RFC 8785; strip at every depth of the "
    "schema structure the string-valued members named 'description' and the "
    "string-valued members whose key starts with 'x-spdx-'; never inside "
    f"instance data ({', '.join(INSTANCE_DATA_KEYWORDS)}) and never on the "
    f"member names of ({', '.join(NAME_KEYED_KEYWORDS)}); nothing else."
)

#: One-line statement of the vector rule, printed by the CLIs.
VECTOR_RULE_TEXT = (
    "vector: sha256(JCS(doc)) — RFC 8785; no stripping at all. Vectors are "
    "instance data; every member is part of the contract."
)


def rule_text(kind: str = KIND_SCHEMA) -> str:
    """The one-line rule statement for *kind*."""
    _check_kind(kind)
    return RULE_TEXT if kind == KIND_SCHEMA else VECTOR_RULE_TEXT


def _check_kind(kind: str) -> None:
    if kind not in KINDS:
        raise ValueError(f"unknown artefact kind {kind!r}; known: {list(KINDS)}")


def _is_annotation(key: str, value: Any) -> bool:
    """True if *key*/*value* is a strippable annotation member of a schema."""
    if not isinstance(value, str):
        return False
    if key in STRIP_STRING_KEYS:
        return True
    return any(key.startswith(prefix) for prefix in STRIP_KEY_PREFIXES)


# Kept as a private alias: the old name of the predicate.
_is_stripped = _is_annotation


def strip_noncanonical(obj: Any) -> Any:
    """Return a deep copy of the *schema* *obj* without its annotations.

    Instance-data subtrees (``const``, ``default``, ``enum``, ``examples``)
    and the member names of name-keyed maps (``properties``, ``$defs``, …)
    are left alone; see the module docstring for why.
    """
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for key, value in obj.items():
            if key in INSTANCE_DATA_KEYWORDS:
                # Instance data: canonical in full, at every depth below.
                out[key] = copy.deepcopy(value)
                continue
            if _is_annotation(key, value):
                continue
            if key in NAME_KEYED_KEYWORDS and isinstance(value, dict):
                # Author-chosen names: keep every member, strip its value
                # as a schema.
                out[key] = {name: strip_noncanonical(sub) for name, sub in value.items()}
                continue
            out[key] = strip_noncanonical(value)
        return out
    if isinstance(obj, list):
        return [strip_noncanonical(item) for item in obj]
    return obj


def canonical_bytes(obj: Any) -> bytes:
    """RFC 8785 serialisation of the stripped *schema* document."""
    return rfc8785.dumps(strip_noncanonical(obj))


def canonical_digest(obj: Any) -> str:
    """Lower-case hex SHA-256 of :func:`canonical_bytes` (schema rule)."""
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()


def verbatim_bytes(obj: Any) -> bytes:
    """RFC 8785 serialisation of *obj* with no stripping (vector rule)."""
    return rfc8785.dumps(obj)


def verbatim_digest(obj: Any) -> str:
    """Lower-case hex SHA-256 of :func:`verbatim_bytes` (vector rule)."""
    return hashlib.sha256(verbatim_bytes(obj)).hexdigest()


def digest(obj: Any, kind: str = KIND_SCHEMA) -> str:
    """Canonical digest of *obj* under the rule for *kind*."""
    _check_kind(kind)
    return canonical_digest(obj) if kind == KIND_SCHEMA else verbatim_digest(obj)


def load_json(path: Union[str, Path]) -> Any:
    """Load a JSON document from *path* (UTF-8)."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def digest_file(path: Union[str, Path], kind: str = KIND_SCHEMA) -> str:
    """Canonical digest of the JSON document stored at *path*."""
    return digest(load_json(path), kind)
