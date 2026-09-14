# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Callandor GmbH and contributors
"""Exception-registry invariants: every waiver and deselect is complete, tracked and bounded."""

from __future__ import annotations

import copy
import datetime as dt
from pathlib import Path

import pytest

from tooling.compat.allowlist import (
    ALLOWLIST_SCHEMA,
    AllowlistError,
    deselect_args,
    find,
    load_allowlist,
    load_deselects,
    parse_allowlist,
    parse_deselects,
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


VALID_DESELECT = {
    "repo": "runtime",
    "node_id": "wirelang/tests/test_example.py::test_case",
    "reason": "cannot hold under the schema overlay",
    "until": "2026-10-31",
    "tracking": "https://github.com/wakir-labs/wakir-protocol/issues/8",
}

WORKFLOW = REPO_ROOT / ".github" / "workflows" / "compat.yml"


def _doc(*entries: dict) -> dict:
    return {"schema": ALLOWLIST_SCHEMA, "entries": list(entries)}


def _ddoc(*deselects: dict) -> dict:
    return {"schema": ALLOWLIST_SCHEMA, "entries": [], "deselects": list(deselects)}


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


# ---------------------------------------------------------------------------
# deselects — counterpart test exclusions, same expiry rule as the waivers
# ---------------------------------------------------------------------------


def test_valid_deselect_parses() -> None:
    entries = parse_deselects(_ddoc(VALID_DESELECT), today=TODAY)
    assert len(entries) == 1
    assert entries[0]["node_id"] == VALID_DESELECT["node_id"]


def test_deselects_block_is_optional() -> None:
    assert parse_deselects(_doc(), today=TODAY) == []


@pytest.mark.parametrize("missing", sorted(VALID_DESELECT))
def test_every_deselect_field_is_mandatory(missing: str) -> None:
    entry = {k: v for k, v in VALID_DESELECT.items() if k != missing}
    with pytest.raises(AllowlistError, match=f"missing required field.*{missing}"):
        parse_deselects(_ddoc(entry), today=TODAY)


def test_expired_deselect_fails() -> None:
    """The reason a deselect lives here and not in the workflow."""
    entry = dict(VALID_DESELECT, until="2026-09-10")
    with pytest.raises(AllowlistError, match="expired on 2026-09-10"):
        parse_deselects(_ddoc(entry), today=TODAY)


def test_expired_deselect_also_fails_the_mirror_check_path() -> None:
    """An expired deselect must fail the gate wherever the registry is read.

    ``check_mirror.py`` only asks for the waivers. If the deselect block
    were validated solely by the flag emitter, an expired deselect would
    survive every step that does not build flags.
    """
    entry = dict(VALID_DESELECT, until="2026-09-10")
    with pytest.raises(AllowlistError, match="expired on 2026-09-10"):
        parse_allowlist(_ddoc(entry), today=TODAY)


def test_deselect_node_id_must_name_a_test_not_a_module() -> None:
    entry = dict(VALID_DESELECT, node_id="wirelang/tests/test_example.py")
    with pytest.raises(AllowlistError, match="must be a pytest node id"):
        parse_deselects(_ddoc(entry), today=TODAY)


def test_unknown_deselect_field_is_rejected() -> None:
    with pytest.raises(AllowlistError, match="unknown field"):
        parse_deselects(_ddoc(dict(VALID_DESELECT, forever=True)), today=TODAY)


def test_duplicate_deselect_is_rejected() -> None:
    with pytest.raises(AllowlistError, match="duplicate"):
        parse_deselects(_ddoc(VALID_DESELECT, copy.deepcopy(VALID_DESELECT)), today=TODAY)


def test_deselect_tracking_must_be_wakir_labs_url() -> None:
    with pytest.raises(AllowlistError):
        parse_deselects(_ddoc(dict(VALID_DESELECT, tracking="see the wiki")), today=TODAY)


def test_shipped_deselects_are_valid_today() -> None:
    """Goes red on purpose when a shipped deselect expires."""
    entries = load_deselects(SHIPPED)
    today = dt.datetime.now(dt.timezone.utc).date()
    for entry in entries:
        assert dt.date.fromisoformat(entry["until"]) >= today, entry["node_id"]
        assert entry["repo"] in {"runtime", "verify"}


def test_deselect_args_emits_flag_pairs_for_the_requested_repo_only() -> None:
    runtime_flags = deselect_args("runtime", SHIPPED)
    verify_flags = deselect_args("verify", SHIPPED)
    assert len(runtime_flags) % 2 == 0
    assert set(runtime_flags[::2]) <= {"--deselect"}
    shipped_runtime = [e for e in load_deselects(SHIPPED) if e["repo"] == "runtime"]
    assert runtime_flags[1::2] == [e["node_id"] for e in shipped_runtime]
    shipped_verify = [e for e in load_deselects(SHIPPED) if e["repo"] == "verify"]
    assert verify_flags[1::2] == [e["node_id"] for e in shipped_verify]


def test_workflow_takes_its_deselects_from_the_registry() -> None:
    """The workflow must not spell out a node id of its own.

    A ``--deselect`` in the shell line carries no expiry and no author,
    and nothing revisits it — which is how COXSR-03/04 sat unexplained
    since May. This pins the single source.
    """
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "--deselect-args" in text, (
        "compat.yml no longer reads the deselect registry; the exceptions "
        "would stop being date-checked"
    )
    hardcoded = [
        line for line in text.splitlines()
        # prose about the rule is fine; an actual flag is not
        if "--deselect " in line
        and "--deselect-args" not in line
        and not line.lstrip().startswith("#")
    ]
    assert not hardcoded, (
        "compat.yml spells out --deselect flags instead of reading them from "
        f"tooling/compat/compat-allowlist.json: {hardcoded}"
    )
