# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Callandor GmbH and contributors
"""Bounded exceptions for the cross-repo compatibility gate.

One file holds **every** exception this gate grants, in two kinds:
``entries`` waive a mirror finding, ``deselects`` remove a counterpart
test from the overlay run. Both carry a mandatory expiry that is
compared against the calendar, so an exception cannot outlive its
reason in silence (ADR-0075 §3).

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
      ],
      "deselects": [
        {
          "repo": "runtime",
          "node_id": "wirelang/tests/test_example.py::test_case",
          "reason": "why the overlay run may not execute this node id",
          "until": "2026-10-31",
          "tracking": "https://github.com/wakir-labs/wakir-protocol/issues/8"
        }
      ]
    }

Policy — ``entries`` (mirror waivers)
-------------------------------------

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

Policy — ``deselects`` (counterpart test exclusions)
---------------------------------------------------

Step 4 of the gate overlays this tree's schemas and vectors into the
counterpart clones and runs the counterparts' own tests against them. A
counterpart test that cannot hold under an overlay has to be named here
rather than in the workflow, for one reason: a ``--deselect`` flag
written into a shell line carries no date and no author, and nothing
ever revisits it. ``deselects`` obeys the same expiry rule as
``entries``.

- Every deselect needs **all** of ``repo``, ``node_id``, ``reason``,
  ``until``, ``tracking``. No other keys.
- ``node_id`` is a pytest node id **relative to the counterpart clone**
  and must contain ``::`` — a bare file path would silently drop a whole
  module, which is the failure mode this registry exists to prevent.
- Duplicate ``(repo, node_id)`` pairs are invalid.
- ``.github/workflows/compat.yml`` reads the flags from this file via
  ``python -m tooling.compat.allowlist --deselect-args <repo>``; it must
  not spell any ``--deselect`` out itself. ``tests/test_compat_allowlist.py``
  pins that.
"""

from __future__ import annotations

import datetime as _dt
import json
import re
from pathlib import Path
from typing import Any, Iterable, Optional, Union

ALLOWLIST_SCHEMA = "wakir-compat-allowlist/v1"
REQUIRED_KEYS = frozenset({"repo", "path", "reason", "until", "tracking"})
DESELECT_KEYS = frozenset({"repo", "node_id", "reason", "until", "tracking"})
REPOS = ("runtime", "verify")
TRACKING_RE = re.compile(
    r"^https://github\.com/wakir-labs/[A-Za-z0-9._-]+/(pull|issues)/[0-9]+$"
)
DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")


class AllowlistError(ValueError):
    """The allowlist file is malformed, incomplete or contains expired entries."""


def _today_utc() -> _dt.date:
    return _dt.datetime.now(_dt.timezone.utc).date()


def _validate_common(
    entry: Any, where: str, today: _dt.date, keys: frozenset, subject_key: str
) -> dict[str, str]:
    """Shape, repo, expiry and tracking — shared by entries and deselects."""
    if not isinstance(entry, dict):
        raise AllowlistError(f"{where}: must be an object")
    present = set(entry)
    missing = keys - present
    if missing:
        raise AllowlistError(f"{where}: missing required field(s) {sorted(missing)}")
    unknown = present - keys
    if unknown:
        raise AllowlistError(f"{where}: unknown field(s) {sorted(unknown)}")
    for key in keys:
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
            f"{subject_key} {entry[subject_key]!r} for {entry['repo']}; "
            f"see {entry['tracking']}"
        )
    if not TRACKING_RE.match(entry["tracking"]):
        raise AllowlistError(
            f"{where}.tracking: must be a wakir-labs pull-request or issue URL"
        )
    return {key: entry[key] for key in sorted(keys)}


def validate_entry(entry: Any, index: int, today: _dt.date) -> dict[str, str]:
    return _validate_common(
        entry, f"entries[{index}]", today, REQUIRED_KEYS, "path"
    )


def validate_deselect(entry: Any, index: int, today: _dt.date) -> dict[str, str]:
    out = _validate_common(
        entry, f"deselects[{index}]", today, DESELECT_KEYS, "node_id"
    )
    # A deselect without "::" is a whole module, not a test case. That is
    # the silent-coverage-loss shape this registry exists to prevent, so
    # it is rejected rather than merely discouraged.
    if "::" not in out["node_id"]:
        raise AllowlistError(
            f"deselects[{index}].node_id: must be a pytest node id containing '::' "
            f"(got {out['node_id']!r}); deselecting a whole module is not allowed"
        )
    return out


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
    extra = set(data) - {"schema", "entries", "deselects"}
    if extra:
        raise AllowlistError(f"allowlist: unknown top-level field(s) {sorted(extra)}")
    # Validated here even though the caller only wants the entries: a
    # malformed or expired deselect must fail the gate on the very same
    # run, not only where the flags are emitted.
    parse_deselects(data, today)
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


def parse_deselects(data: Any, today: Optional[_dt.date] = None) -> list[dict[str, str]]:
    """Validate the ``deselects`` block of an already-parsed document."""
    today = today or _today_utc()
    if not isinstance(data, dict):
        raise AllowlistError("allowlist must be a JSON object")
    raw_list = data.get("deselects", [])
    if not isinstance(raw_list, list):
        raise AllowlistError("allowlist.deselects must be a list")
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, str]] = []
    for index, raw in enumerate(raw_list):
        entry = validate_deselect(raw, index, today)
        key = (entry["repo"], entry["node_id"])
        if key in seen:
            raise AllowlistError(f"deselects[{index}]: duplicate (repo, node_id) {key}")
        seen.add(key)
        out.append(entry)
    return out


def load_deselects(
    path: Union[str, Path], repo: Optional[str] = None, today: Optional[_dt.date] = None
) -> list[dict[str, str]]:
    """Load and validate the deselects at *path*, optionally filtered by repo."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AllowlistError(f"allowlist not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise AllowlistError(f"allowlist is not valid JSON: {exc}") from exc
    if data.get("schema") != ALLOWLIST_SCHEMA:
        raise AllowlistError(f"allowlist.schema must be {ALLOWLIST_SCHEMA!r}")
    out = parse_deselects(data, today)
    if repo is not None:
        if repo not in REPOS:
            raise AllowlistError(f"unknown repo {repo!r}; known: {list(REPOS)}")
        out = [e for e in out if e["repo"] == repo]
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


#: Default location of the exception registry, resolved from this file so
#: the CLI works from any working directory.
DEFAULT_ALLOWLIST_PATH = Path(__file__).resolve().parent / "compat-allowlist.json"


def deselect_args(repo: str, path: Union[str, Path, None] = None) -> list[str]:
    """``--deselect <node id>`` flags for *repo*, straight from the registry.

    Used by ``.github/workflows/compat.yml`` so the workflow never spells
    out a node id of its own. Expired or malformed deselects raise here,
    which fails the gate step that builds the flags.
    """
    entries = load_deselects(path or DEFAULT_ALLOWLIST_PATH, repo=repo)
    flags: list[str] = []
    for entry in entries:
        flags += ["--deselect", entry["node_id"]]
    return flags


def _main(argv: Optional[list[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m tooling.compat.allowlist",
        description="Validate the compat exception registry and emit deselect flags.",
    )
    parser.add_argument(
        "--deselect-args",
        metavar="REPO",
        choices=REPOS,
        help="print the --deselect flags for REPO on one line (shell-quoted)",
    )
    parser.add_argument(
        "--file", default=str(DEFAULT_ALLOWLIST_PATH), help="registry path"
    )
    args = parser.parse_args(argv)

    import shlex
    import sys

    try:
        if args.deselect_args:
            print(shlex.join(deselect_args(args.deselect_args, args.file)))
        else:
            entries = load_allowlist(args.file)
            deselects = load_deselects(args.file)
            print(
                f"compat exception registry {args.file}: "
                f"{len(entries)} mirror waiver(s), {len(deselects)} deselect(s) — all valid today"
            )
            for entry in entries:
                print(f"  waiver   {entry['repo']:8} {entry['path']} (until {entry['until']})")
            for entry in deselects:
                print(f"  deselect {entry['repo']:8} {entry['node_id']} (until {entry['until']})")
    except AllowlistError as exc:
        print(f"compat exception registry: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(_main())
