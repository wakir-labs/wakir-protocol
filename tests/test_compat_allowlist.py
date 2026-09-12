# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Callandor GmbH and contributors
"""Allowlist policy invariants: every waiver is complete, tracked and bounded."""

from __future__ import annotations

import copy
import datetime as dt
from pathlib import Path

import pytest

from tooling.compat.allowlist import (
    ALLOWLIST_SCHEMA,
    AllowlistError,
    find,
    load_allowlist,
    parse_allowlist,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SHIPPED = REPO_ROOT / "tooling" / "compat" / "compat-allowlist.json"
TODAY = dt.date(2026, 9, 11)

VALID_ENTRY = {
    "repo": "runtime",
    "path": "wakir_protocol/schemas/example.json",
    "reason": "mirror lags one PR",
    "until": "2026-09-30",
    "tracking": "https://github.com/wakir-labs/wakir-runtime/pull/999",
}


def _doc(*entries: dict) -> dict:
    return {"schema": ALLOWLIST_SCHEMA, "entries": list(entries)}


def test_valid_entry_parses_and_is_found() -> None:
    entries = parse_allowlist(_doc(VALID_ENTRY), today=TODAY)
    assert len(entries) == 1
    assert find(entries, "runtime", VALID_ENTRY["path"]) is not None
    assert find(entries, "verify", VALID_ENTRY["path"]) is None


def test_empty_allowlist_is_valid() -> None:
    assert parse_allowlist(_doc(), today=TODAY) == []


@pytest.mark.parametrize("missing", sorted(VALID_ENTRY))
def test_every_field_is_mandatory(missing: str) -> None:
    entry = {k: v for k, v in VALID_ENTRY.items() if k != missing}
    with pytest.raises(AllowlistError, match=f"missing required field.*{missing}"):
        parse_allowlist(_doc(entry), today=TODAY)


def test_entry_without_until_is_invalid_not_permanent() -> None:
    entry = {k: v for k, v in VALID_ENTRY.items() if k != "until"}
    with pytest.raises(AllowlistError):
        parse_allowlist(_doc(entry), today=TODAY)


def test_expired_entry_fails() -> None:
    entry = dict(VALID_ENTRY, until="2026-09-10")
    with pytest.raises(AllowlistError, match="expired on 2026-09-10"):
        parse_allowlist(_doc(entry), today=TODAY)


def test_until_today_is_still_valid() -> None:
    entry = dict(VALID_ENTRY, until=TODAY.isoformat())
    assert parse_allowlist(_doc(entry), today=TODAY)


@pytest.mark.parametrize("bad", ["2026-9-30", "30.09.2026", "2026-13-01", "soon", ""])
def test_until_must_be_iso_date(bad: str) -> None:
    with pytest.raises(AllowlistError):
        parse_allowlist(_doc(dict(VALID_ENTRY, until=bad)), today=TODAY)


@pytest.mark.parametrize(
    "bad",
    [
        "https://github.com/wakir-labs/wakir-runtime",
        "https://github.com/other-org/repo/pull/1",
        "http://github.com/wakir-labs/wakir-runtime/pull/1",
        "ADR-0072",
        "",
    ],
)
def test_tracking_must_be_wakir_labs_pr_or_issue(bad: str) -> None:
    with pytest.raises(AllowlistError):
        parse_allowlist(_doc(dict(VALID_ENTRY, tracking=bad)), today=TODAY)


def test_tracking_accepts_issues_too() -> None:
    entry = dict(VALID_ENTRY, tracking="https://github.com/wakir-labs/wakir-verify/issues/12")
    assert parse_allowlist(_doc(entry), today=TODAY)


def test_unknown_field_is_rejected() -> None:
    with pytest.raises(AllowlistError, match="unknown field"):
        parse_allowlist(_doc(dict(VALID_ENTRY, follow_up="permanent")), today=TODAY)


def test_repo_must_be_known_counterpart() -> None:
    with pytest.raises(AllowlistError, match="repo"):
        parse_allowlist(_doc(dict(VALID_ENTRY, repo="protocol")), today=TODAY)


def test_duplicate_repo_path_is_rejected() -> None:
    with pytest.raises(AllowlistError, match="duplicate"):
        parse_allowlist(_doc(VALID_ENTRY, copy.deepcopy(VALID_ENTRY)), today=TODAY)


def test_wrong_schema_or_shape_is_rejected() -> None:
    with pytest.raises(AllowlistError):
        parse_allowlist({"schema": "other", "entries": []}, today=TODAY)
    with pytest.raises(AllowlistError):
        parse_allowlist({"schema": ALLOWLIST_SCHEMA, "entries": {}}, today=TODAY)
    with pytest.raises(AllowlistError, match="unknown top-level"):
        parse_allowlist({"schema": ALLOWLIST_SCHEMA, "entries": [], "allow": []}, today=TODAY)


def test_shipped_allowlist_is_valid_today() -> None:
    """The shipped file must load with the real UTC date.

    When an entry expires this test goes red on purpose: the waiver has
    to be removed (mirror synced) or consciously extended with a new
    tracking reference.
    """
    entries = load_allowlist(SHIPPED)
    today = dt.datetime.now(dt.timezone.utc).date()
    for entry in entries:
        assert dt.date.fromisoformat(entry["until"]) >= today
        assert (REPO_ROOT / entry["path"]).is_file(), entry["path"]


def test_missing_file_raises() -> None:
    with pytest.raises(AllowlistError, match="not found"):
        load_allowlist(REPO_ROOT / "tooling" / "compat" / "does-not-exist.json")
