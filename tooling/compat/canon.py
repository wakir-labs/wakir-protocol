# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Callandor GmbH and contributors
"""Canonicalisation rule for cross-repo schema and vector comparison.

The rule
--------

The canonical digest of a JSON document is::

    sha256( JCS( strip(document) ) )

where ``JCS`` is RFC 8785 JSON Canonicalization Scheme serialisation
(``rfc8785.dumps``) and ``strip`` removes, at every nesting depth,

1. every object member whose key starts with ``x-spdx-`` **and whose
   value is a JSON string** (licence-header metadata; Apache-2.0 in
   protocol, BUSL-1.1 in runtime — the divergence is intentional), and
2. every object member named ``description`` **whose value is a JSON
   string** (human-readable annotations; wording may differ between
   mirrors without changing the contract).

Members named ``description`` whose value is *not* a string are kept.
This matters: five persona schemas define a *property* called
``description`` (``properties.description`` is an object), and drift in
such a property definition must stay visible.

Nothing else is stripped. In particular ``$id``, ``title``, ``examples``,
``enum``, ``required``, ``additionalProperties`` and every other
``x-*`` extension key are part of the canonical form.

Formatting (indentation, key order, whitespace, unicode escaping) never
affects the digest — that is what JCS is for.

Every repository that participates in the compatibility gate implements
this rule identically; the reference is this module.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Union

import rfc8785

#: Prefix of keys that are stripped when their value is a string.
STRIP_KEY_PREFIXES: tuple[str, ...] = ("x-spdx-",)

#: Exact keys that are stripped when their value is a string.
STRIP_STRING_KEYS: tuple[str, ...] = ("description",)

#: One-line statement of the rule, printed by the CLIs.
RULE_TEXT = (
    "sha256(JCS(strip(doc))) — RFC 8785; strip at every depth the "
    "string-valued members named 'description' and the string-valued "
    "members whose key starts with 'x-spdx-'; nothing else."
)


def _is_stripped(key: str, value: Any) -> bool:
    if not isinstance(value, str):
        return False
    if key in STRIP_STRING_KEYS:
        return True
    return any(key.startswith(prefix) for prefix in STRIP_KEY_PREFIXES)


def strip_noncanonical(obj: Any) -> Any:
    """Return a deep copy of *obj* with the non-canonical members removed."""
    if isinstance(obj, dict):
        return {
            key: strip_noncanonical(value)
            for key, value in obj.items()
            if not _is_stripped(key, value)
        }
    if isinstance(obj, list):
        return [strip_noncanonical(item) for item in obj]
    return obj


def canonical_bytes(obj: Any) -> bytes:
    """RFC 8785 serialisation of the stripped document."""
    return rfc8785.dumps(strip_noncanonical(obj))


def canonical_digest(obj: Any) -> str:
    """Lower-case hex SHA-256 of :func:`canonical_bytes`."""
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()


def load_json(path: Union[str, Path]) -> Any:
    """Load a JSON document from *path* (UTF-8)."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def digest_file(path: Union[str, Path]) -> str:
    """Canonical digest of the JSON document stored at *path*."""
    return canonical_digest(load_json(path))
