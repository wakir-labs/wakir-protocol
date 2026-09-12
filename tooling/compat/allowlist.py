# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Callandor GmbH and contributors
"""Bounded-waiver allowlist for the cross-repo compatibility gate.

File: ``tooling/compat/compat-allowlist.json``::

    {
      "schema": "wakir-compat-allowlist/v1",
      "entries": [
        {
          "repo": "runtime",
          "path": "wakir_protocol/schemas/example.json",
          "reason": "why the mirror is allowed to lag",
          "until": "2026-09-30",
          "tracking": "https://github.com/wakir-labs/wakir-runtime/pull/123"
        }
      ]
    }

Policy
------

- Every entry needs **all** of ``repo``, ``path``, ``reason``, ``until``,
  ``tracking``. No other keys. An entry without ``until`` is invalid and
  fails the gate — there is no permanent waiver.
- ``until`` is an ISO calendar date (``YYYY-MM-DD``). It is compared
  against the UTC date at check time; an expired entry **fails** the
  gate (it does not silently stop applying).
- ``tracking`` is the URL of the pull request or issue that removes the
  need for the entry: ``https://github.com/wakir-labs/<repo>/(pull|issues)/<n>``.
- ``repo`` is ``runtime`` or ``verify`` — the counterpart the waiver
  applies to. ``path`` is the **protocol-side** path.
- Duplicate ``(repo, path)`` pairs are invalid.

An allowlisted finding is reported as ``allowlisted`` (never hidden).
"""

from __future__ import annotations

import datetime as _dt
import json
import re
from pathlib import Path
from typing import Any, Iterable, Optional, Union

ALLOWLIST_SCHEMA = "wakir-compat-allowlist/v1"
REQUIRED_KEYS = frozenset({"repo", "path", "reason", "until", "tracking"})
REPOS = ("runtime", "verify")
TRACKING_RE = re.compile(
    r"^https://github\.com/wakir-labs/[A-Za-z0-9._-]+/(pull|issues)/[0-9]+$"
)
DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")


class AllowlistError(ValueError):
    """The allowlist file is malformed, incomplete or contains expired entries."""


def _today_utc() -> _dt.date:
    return _dt.datetime.now(_dt.timezone.utc).date()


def validate_entry(entry: Any, index: int, today: _dt.date) -> dict[str, str]:
    where = f"entries[{index}]"
    if not isinstance(entry, dict):
        raise AllowlistError(f"{where}: must be an object")
    keys = set(entry)
    missing = REQUIRED_KEYS - keys
    if missing:
        raise AllowlistError(f"{where}: missing required field(s) {sorted(missing)}")
    unknown = keys - REQUIRED_KEYS
    if unknown:
        raise AllowlistError(f"{where}: unknown field(s) {sorted(unknown)}")
    for key in REQUIRED_KEYS:
        if not isinstance(entry[key], str) or not entry[key].strip():
            raise AllowlistError(f"{where}.{key}: must be a non-empty string")
    if entry["repo"] not in REPOS:
        raise AllowlistError(f"{where}.repo: must be one of {list(REPOS)}")
    if not DATE_RE.match(entry["until"]):
        raise AllowlistError(f"{where}.until: must be YYYY-MM-DD")
    try:
        until = _dt.date.fromisoformat(entry["until"])
    except ValueError as exc:
        raise AllowlistError(f"{where}.until: {exc}") from exc
    if until < today:
        raise AllowlistError(
            f"{where}: expired on {entry['until']} (today {today.isoformat()}) — "
            f"path {entry['path']!r} for {entry['repo']}; see {entry['tracking']}"
        )
    if not TRACKING_RE.match(entry["tracking"]):
        raise AllowlistError(
            f"{where}.tracking: must be a wakir-labs pull-request or issue URL"
        )
    return {key: entry[key] for key in sorted(REQUIRED_KEYS)}


def parse_allowlist(data: Any, today: Optional[_dt.date] = None) -> list[dict[str, str]]:
    """Validate an already-parsed allowlist document and return its entries."""
    today = today or _today_utc()
    if not isinstance(data, dict):
        raise AllowlistError("allowlist must be a JSON object")
    if data.get("schema") != ALLOWLIST_SCHEMA:
        raise AllowlistError(f"allowlist.schema must be {ALLOWLIST_SCHEMA!r}")
    entries = data.get("entries")
    if not isinstance(entries, list):
        raise AllowlistError("allowlist.entries must be a list")
    extra = set(data) - {"schema", "entries"}
    if extra:
        raise AllowlistError(f"allowlist: unknown top-level field(s) {sorted(extra)}")
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, str]] = []
    for index, raw in enumerate(entries):
        entry = validate_entry(raw, index, today)
        key = (entry["repo"], entry["path"])
        if key in seen:
            raise AllowlistError(f"entries[{index}]: duplicate (repo, path) {key}")
        seen.add(key)
        out.append(entry)
    return out


def load_allowlist(path: Union[str, Path], today: Optional[_dt.date] = None) -> list[dict[str, str]]:
    """Load and validate the allowlist at *path*."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AllowlistError(f"allowlist not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise AllowlistError(f"allowlist is not valid JSON: {exc}") from exc
    return parse_allowlist(data, today)


def find(entries: Iterable[dict[str, str]], repo: str, path: str) -> Optional[dict[str, str]]:
    """Return the entry covering ``(repo, path)`` or ``None``."""
    for entry in entries:
        if entry["repo"] == repo and entry["path"] == path:
            return entry
    return None
