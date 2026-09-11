# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Callandor GmbH and contributors
"""Compare this repository's schema set with a local clone of runtime or verify.

Usage::

    python tooling/compat/check_mirror.py --repo runtime /path/to/wakir-runtime
    python tooling/compat/check_mirror.py --repo verify  /path/to/wakir-verify

Exit codes: ``0`` compatible (all findings ``ok``, ``absent`` or
``allowlisted``), ``1`` incompatible or invalid/expired allowlist,
``2`` usage or configuration error.

What is compared
----------------

``tooling/compat/mirror-map.json`` lists, per counterpart repository,
glob patterns of protocol-side JSON files and the directory in the
counterpart that mirrors them. Every file is compared by its canonical
digest (:mod:`tooling.compat.canon`). Findings per file:

``ok``           digests equal
``drift``        both present, digests differ                       -> fail
``missing``      present in protocol, absent in counterpart          -> fail
``absent``       the whole mirror directory does not exist yet and the
                 mirror is ``required: false``                       -> info
``allowlisted``  ``drift``/``missing`` covered by a valid allowlist entry

Additionally ``version_constants`` in the mirror map are read from the
counterpart's source with a regex and compared with the versions
declared in ``tooling/compat/versions.json``.

Enforcement is on by default (ADR-0072 Phase 4, trade-off 4). ``--audit``
reports without failing; it exists for local exploration only and is not
used by CI.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Sequence

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tooling.compat import allowlist as _allowlist  # noqa: E402
from tooling.compat.canon import RULE_TEXT, digest_file  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MIRROR_MAP = REPO_ROOT / "tooling" / "compat" / "mirror-map.json"
DEFAULT_ALLOWLIST = REPO_ROOT / "tooling" / "compat" / "compat-allowlist.json"
DEFAULT_VERSIONS = REPO_ROOT / "tooling" / "compat" / "versions.json"
MIRROR_MAP_SCHEMA = "wakir-compat-mirror-map/v1"
FAILING = ("drift", "missing", "version-mismatch", "version-unreadable")


class ConfigError(ValueError):
    """mirror-map.json or versions.json is malformed."""


@dataclass
class Finding:
    status: str
    kind: str
    protocol_path: str
    other_path: str
    detail: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "status": self.status,
            "kind": self.kind,
            "protocol_path": self.protocol_path,
            "other_path": self.other_path,
            "detail": self.detail,
        }


@dataclass
class Report:
    repo: str
    findings: list[Finding] = field(default_factory=list)
    allowlist_error: Optional[str] = None

    @property
    def ok(self) -> bool:
        if self.allowlist_error:
            return False
        return not any(f.status in FAILING for f in self.findings)

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for f in self.findings:
            out[f.status] = out.get(f.status, 0) + 1
        return dict(sorted(out.items()))


def load_mirror_map(path: Path = DEFAULT_MIRROR_MAP) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != MIRROR_MAP_SCHEMA:
        raise ConfigError(f"mirror map schema must be {MIRROR_MAP_SCHEMA!r}")
    repos = data.get("repos")
    if not isinstance(repos, dict) or not repos:
        raise ConfigError("mirror map needs a non-empty 'repos' object")
    for name, spec in repos.items():
        for mirror in spec.get("mirrors", []):
            for key in ("kind", "protocol", "other", "required"):
                if key not in mirror:
                    raise ConfigError(f"repos.{name}: mirror entry lacks {key!r}: {mirror}")
            if not isinstance(mirror["required"], bool):
                raise ConfigError(f"repos.{name}: 'required' must be a boolean")
    return data


def declared_versions(versions_path: Path, group: str) -> list[str]:
    data = json.loads(versions_path.read_text(encoding="utf-8"))
    block = data.get(group)
    if not isinstance(block, dict) or "declared" not in block:
        raise ConfigError(f"versions.json: group {group!r} has no 'declared' list")
    return [entry["version"] for entry in block["declared"]]


def _protocol_files(protocol_root: Path, pattern: str) -> list[Path]:
    directory = protocol_root / Path(pattern).parent
    if not directory.is_dir():
        return []
    return sorted(
        p for p in directory.iterdir()
        if p.is_file() and fnmatch.fnmatch(p.name, Path(pattern).name)
    )


def check_repo(
    *,
    repo: str,
    other_root: Path,
    protocol_root: Path = REPO_ROOT,
    mirror_map: Optional[dict[str, Any]] = None,
    allowlist_path: Path = DEFAULT_ALLOWLIST,
    versions_path: Path = DEFAULT_VERSIONS,
) -> Report:
    mirror_map = mirror_map or load_mirror_map()
    if repo not in mirror_map["repos"]:
        raise ConfigError(f"unknown repo {repo!r}; known: {sorted(mirror_map['repos'])}")
    spec = mirror_map["repos"][repo]
    report = Report(repo=repo)

    try:
        entries = _allowlist.load_allowlist(allowlist_path)
    except _allowlist.AllowlistError as exc:
        report.allowlist_error = str(exc)
        entries = []

    for mirror in spec.get("mirrors", []):
        files = _protocol_files(protocol_root, mirror["protocol"])
        other_dir = other_root / mirror["other"]
        if not files:
            report.findings.append(Finding("config", mirror["kind"], mirror["protocol"], mirror["other"],
                                           "pattern matches no protocol file"))
            continue
        if not other_dir.is_dir():
            status = "missing" if mirror["required"] else "absent"
            for path in files:
                rel = str(path.relative_to(protocol_root))
                other_rel = str(Path(mirror["other"]) / path.name)
                f = Finding(status, mirror["kind"], rel, other_rel, "mirror directory does not exist")
                _apply_allowlist(f, entries, repo)
                report.findings.append(f)
            continue
        for path in files:
            rel = str(path.relative_to(protocol_root))
            other = other_dir / path.name
            other_rel = str(Path(mirror["other"]) / path.name)
            if not other.is_file():
                f = Finding("missing", mirror["kind"], rel, other_rel, "file absent in counterpart")
            else:
                mine, theirs = digest_file(path), digest_file(other)
                if mine == theirs:
                    f = Finding("ok", mirror["kind"], rel, other_rel, mine[:16])
                else:
                    f = Finding("drift", mirror["kind"], rel, other_rel, f"protocol {mine[:16]} != counterpart {theirs[:16]}")
            _apply_allowlist(f, entries, repo)
            report.findings.append(f)

    for const in spec.get("version_constants", []):
        source = other_root / const["path"]
        declared = declared_versions(versions_path, const["declared_in"])
        if not source.is_file():
            report.findings.append(Finding("version-unreadable", "version", "tooling/compat/versions.json",
                                           const["path"], "source file absent in counterpart"))
            continue
        match = re.search(const["regex"], source.read_text(encoding="utf-8"), re.MULTILINE)
        if not match:
            report.findings.append(Finding("version-unreadable", "version", "tooling/compat/versions.json",
                                           const["path"], f"regex {const['regex']!r} did not match"))
            continue
        value = match.group(1)
        if value in declared:
            report.findings.append(Finding("ok", "version", "tooling/compat/versions.json", const["path"], value))
        else:
            report.findings.append(Finding("version-mismatch", "version", "tooling/compat/versions.json",
                                           const["path"], f"{value!r} not in declared {declared}"))
    return report


def _apply_allowlist(finding: Finding, entries: list[dict[str, str]], repo: str) -> None:
    if finding.status not in ("drift", "missing"):
        return
    entry = _allowlist.find(entries, repo, finding.protocol_path)
    if entry is not None:
        finding.detail = f"{finding.status}: {finding.detail}; allowlisted until {entry['until']} ({entry['tracking']})"
        finding.status = "allowlisted"


def render(report: Report) -> str:
    lines = [f"compat check: protocol vs {report.repo}", f"rule: {RULE_TEXT}", ""]
    width = max((len(f.protocol_path) for f in report.findings), default=10)
    for f in report.findings:
        lines.append(f"{f.status:17} {f.kind:8} {f.protocol_path:{width}}  {f.detail}")
    lines.append("")
    lines.append("summary: " + ", ".join(f"{k}={v}" for k, v in report.counts().items()))
    if report.allowlist_error:
        lines.append(f"ALLOWLIST INVALID: {report.allowlist_error}")
    lines.append("result: " + ("COMPATIBLE" if report.ok else "INCOMPATIBLE"))
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("other_root", type=Path, help="local clone of the counterpart repository")
    parser.add_argument("--repo", required=True, help="counterpart name as listed in mirror-map.json")
    parser.add_argument("--protocol-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--mirror-map", type=Path, default=DEFAULT_MIRROR_MAP)
    parser.add_argument("--allowlist", type=Path, default=DEFAULT_ALLOWLIST)
    parser.add_argument("--versions", type=Path, default=DEFAULT_VERSIONS)
    parser.add_argument("--json", type=Path, help="also write the report as JSON to this path")
    parser.add_argument("--audit", action="store_true", help="report only, never fail (local use)")
    args = parser.parse_args(argv)

    if not args.other_root.is_dir():
        print(f"error: {args.other_root} is not a directory", file=sys.stderr)
        return 2
    try:
        mirror_map = load_mirror_map(args.mirror_map)
        report = check_repo(
            repo=args.repo,
            other_root=args.other_root,
            protocol_root=args.protocol_root,
            mirror_map=mirror_map,
            allowlist_path=args.allowlist,
            versions_path=args.versions,
        )
    except (ConfigError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(render(report))
    if args.json:
        args.json.write_text(json.dumps({
            "repo": report.repo,
            "ok": report.ok,
            "allowlist_error": report.allowlist_error,
            "findings": [f.as_dict() for f in report.findings],
        }, indent=2) + "\n", encoding="utf-8")
    if report.ok or args.audit:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
