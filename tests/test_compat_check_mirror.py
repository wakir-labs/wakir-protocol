# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Callandor GmbH and contributors
"""check_mirror invariants against synthetic counterpart clones.

The real counterparts are only available in CI (compat.yml clones them);
here a temporary directory plays runtime/verify so every status and the
enforce/allowlist logic is exercised deterministically.
"""

from __future__ import annotations

import datetime as dt
import json
import shutil
from pathlib import Path

import pytest

from tooling.compat import check_mirror
from tooling.compat.check_mirror import ConfigError, check_repo, load_mirror_map

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_DIR = REPO_ROOT / "wakir_protocol" / "schemas"
SHIPPED_MAP = REPO_ROOT / "tooling" / "compat" / "mirror-map.json"
FUTURE = (dt.datetime.now(dt.timezone.utc).date() + dt.timedelta(days=10)).isoformat()
PAST = (dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=1)).isoformat()


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data) + "\n", encoding="utf-8")


def _mirror_map(*, vectors_required: bool = False) -> dict:
    return {
        "schema": "wakir-compat-mirror-map/v1",
        "repos": {
            "runtime": {
                "mirrors": [
                    {"kind": "schema", "protocol": "wakir_protocol/schemas/*.json",
                     "other": "mirror/schemas/", "required": True},
                    {"kind": "vector", "protocol": "tests/fixtures/proof-path-vectors/*.json",
                     "other": "mirror/vectors/", "required": vectors_required},
                ],
                "version_constants": [
                    {"path": "src/version.py", "regex": r'^MANIFEST_VERSION = "([^"]+)"', "declared_in": "manifest"},
                ],
            }
        },
    }


def _allowlist(*entries: dict) -> dict:
    return {"schema": "wakir-compat-allowlist/v1", "entries": list(entries)}


@pytest.fixture
def counterpart(tmp_path: Path) -> Path:
    """A counterpart whose schemas are reformatted, re-worded copies."""
    other = tmp_path / "other"
    for path in SCHEMA_DIR.glob("*.json"):
        schema = json.loads(path.read_text(encoding="utf-8"))
        schema.pop("x-spdx-license-identifier", None)
        schema["x-spdx-file-copyright-text"] = "BUSL side"
        if isinstance(schema.get("description"), str):
            schema["description"] = "reworded"
        (other / "mirror" / "schemas").mkdir(parents=True, exist_ok=True)
        (other / "mirror" / "schemas" / path.name).write_text(
            json.dumps(schema, separators=(",", ":"), sort_keys=True), encoding="utf-8"
        )
    (other / "src").mkdir()
    (other / "src" / "version.py").write_text('MANIFEST_VERSION = "wakir-wat-manifest/v1"\n')
    return other


@pytest.fixture
def config(tmp_path: Path):
    def make(*, allow: tuple = (), vectors_required: bool = False):
        map_path = tmp_path / "map.json"
        allow_path = tmp_path / "allow.json"
        _write_json(map_path, _mirror_map(vectors_required=vectors_required))
        _write_json(allow_path, _allowlist(*allow))
        return map_path, allow_path
    return make


def _run(counterpart: Path, map_path: Path, allow_path: Path):
    return check_repo(
        repo="runtime",
        other_root=counterpart,
        protocol_root=REPO_ROOT,
        mirror_map=load_mirror_map(map_path),
        allowlist_path=allow_path,
    )


def test_reformatted_reworded_mirror_is_compatible(counterpart, config) -> None:
    report = _run(counterpart, *config())
    counts = report.counts()
    assert report.ok, check_mirror.render(report)
    assert counts["ok"] == len(list(SCHEMA_DIR.glob("*.json"))) + 1  # + version constant
    assert counts["absent"] == 3 and "drift" not in counts and "missing" not in counts


def test_enum_drift_fails(counterpart, config) -> None:
    target = counterpart / "mirror" / "schemas" / "wakir-wat-manifest-v1.json"
    schema = json.loads(target.read_text())
    schema["properties"]["version"]["enum"].append("wakir-wat-manifest/v3")
    target.write_text(json.dumps(schema))
    report = _run(counterpart, *config())
    assert not report.ok
    drift = [f for f in report.findings if f.status == "drift"]
    assert [f.protocol_path for f in drift] == ["wakir_protocol/schemas/wakir-wat-manifest-v1.json"]


def test_allowlisted_drift_passes_and_stays_visible(counterpart, config) -> None:
    target = counterpart / "mirror" / "schemas" / "layer-1-wire.json"
    schema = json.loads(target.read_text())
    schema["title"] = "changed"
    target.write_text(json.dumps(schema))
    entry = {"repo": "runtime", "path": "wakir_protocol/schemas/layer-1-wire.json", "reason": "test",
             "until": FUTURE, "tracking": "https://github.com/wakir-labs/wakir-runtime/pull/1"}
    report = _run(counterpart, *config(allow=(entry,)))
    assert report.ok
    allowed = [f for f in report.findings if f.status == "allowlisted"]
    assert len(allowed) == 1 and "drift:" in allowed[0].detail and FUTURE in allowed[0].detail


def test_expired_allowlist_entry_fails_even_without_drift(counterpart, config) -> None:
    entry = {"repo": "runtime", "path": "wakir_protocol/schemas/layer-1-wire.json", "reason": "test",
             "until": PAST, "tracking": "https://github.com/wakir-labs/wakir-runtime/pull/1"}
    report = _run(counterpart, *config(allow=(entry,)))
    assert not report.ok
    assert report.allowlist_error and "expired" in report.allowlist_error


def test_missing_file_in_present_mirror_fails(counterpart, config) -> None:
    (counterpart / "mirror" / "schemas" / "aip-document.json").unlink()
    report = _run(counterpart, *config())
    assert not report.ok
    assert [f.protocol_path for f in report.findings if f.status == "missing"] == [
        "wakir_protocol/schemas/aip-document.json"
    ]


def test_missing_can_be_allowlisted(counterpart, config) -> None:
    (counterpart / "mirror" / "schemas" / "aip-document.json").unlink()
    entry = {"repo": "runtime", "path": "wakir_protocol/schemas/aip-document.json", "reason": "test",
             "until": FUTURE, "tracking": "https://github.com/wakir-labs/wakir-runtime/issues/2"}
    report = _run(counterpart, *config(allow=(entry,)))
    assert report.ok
    assert report.counts()["allowlisted"] == 1


def test_absent_required_directory_is_missing(counterpart, config) -> None:
    report = _run(counterpart, *config(vectors_required=True))
    assert not report.ok
    assert report.counts()["missing"] == 3


def test_absent_optional_directory_is_informational(counterpart, config) -> None:
    report = _run(counterpart, *config(vectors_required=False))
    assert report.ok and report.counts()["absent"] == 3


def test_present_optional_directory_is_compared(counterpart, config) -> None:
    vec_dir = counterpart / "mirror" / "vectors"
    shutil.copytree(REPO_ROOT / "tests" / "fixtures" / "proof-path-vectors", vec_dir)
    (vec_dir / "README.md").unlink(missing_ok=True)
    target = vec_dir / "vector-2.json"
    vec = json.loads(target.read_text())
    vec["merkle_root"] = "00" * 32
    target.write_text(json.dumps(vec))
    report = _run(counterpart, *config())
    assert not report.ok
    statuses = {f.protocol_path: f.status for f in report.findings if f.kind == "vector"}
    assert statuses["tests/fixtures/proof-path-vectors/vector-2.json"] == "drift"
    assert statuses["tests/fixtures/proof-path-vectors/vector-1.json"] == "ok"


def test_version_constant_mismatch_fails(counterpart, config) -> None:
    (counterpart / "src" / "version.py").write_text('MANIFEST_VERSION = "wakir-wat-manifest/v9"\n')
    report = _run(counterpart, *config())
    assert not report.ok
    assert report.counts()["version-mismatch"] == 1


def test_version_constant_unreadable_fails(counterpart, config) -> None:
    (counterpart / "src" / "version.py").write_text("# nothing here\n")
    report = _run(counterpart, *config())
    assert not report.ok and report.counts()["version-unreadable"] == 1
    (counterpart / "src" / "version.py").unlink()
    report = _run(counterpart, *config())
    assert not report.ok and report.counts()["version-unreadable"] == 1


def test_main_exit_codes(counterpart, config, tmp_path: Path) -> None:
    map_path, allow_path = config()
    base = ["--repo", "runtime", "--protocol-root", str(REPO_ROOT), "--mirror-map", str(map_path),
            "--allowlist", str(allow_path)]
    out = tmp_path / "report.json"
    assert check_mirror.main([str(counterpart), *base, "--json", str(out)]) == 0
    data = json.loads(out.read_text())
    assert data["ok"] is True and data["repo"] == "runtime" and data["findings"]

    target = counterpart / "mirror" / "schemas" / "layer-0-transport.json"
    schema = json.loads(target.read_text())
    schema["required"] = []
    target.write_text(json.dumps(schema))
    assert check_mirror.main([str(counterpart), *base]) == 1
    assert check_mirror.main([str(counterpart), *base, "--audit"]) == 0
    assert check_mirror.main([str(tmp_path / "nope"), *base]) == 2
    assert check_mirror.main([str(counterpart), "--repo", "unknown", "--mirror-map", str(map_path),
                              "--allowlist", str(allow_path)]) == 2


def test_shipped_mirror_map_is_well_formed_and_matches_files() -> None:
    mirror_map = load_mirror_map(SHIPPED_MAP)
    assert set(mirror_map["repos"]) == {"runtime", "verify"}
    for name, spec in mirror_map["repos"].items():
        for mirror in spec["mirrors"]:
            files = check_mirror._protocol_files(REPO_ROOT, mirror["protocol"])
            assert files, f"{name}: {mirror['protocol']} matches nothing"
        for const in spec["version_constants"]:
            assert const["declared_in"] in ("manifest", "inclusion_proof")
    schema_mirror = [m for m in mirror_map["repos"]["runtime"]["mirrors"] if m["kind"] == "schema"]
    assert schema_mirror and schema_mirror[0]["required"] is True


def test_malformed_mirror_map_is_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    _write_json(bad, {"schema": "wakir-compat-mirror-map/v1", "repos": {"x": {"mirrors": [{"kind": "schema"}]}}})
    with pytest.raises(ConfigError):
        load_mirror_map(bad)
    _write_json(bad, {"schema": "nope", "repos": {}})
    with pytest.raises(ConfigError):
        load_mirror_map(bad)
