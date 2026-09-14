# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Callandor GmbH and contributors
"""What the required ``pytest (py3.13)`` lane actually executes.

A green tick proves the assertions that *ran*. It does not prove that
every test module was found. Two ways a module can leave the lane
without turning it red:

1. a **collection error** — pytest exits ``2`` for that, so this one is
   already loud; :func:`test_collect_only_reports_no_errors` pins that
   behaviour so it cannot be softened later (e.g. by
   ``--continue-on-collection-errors`` in ``addopts``);
2. an **import-time skip** — ``pytest.importorskip`` at module level
   turns a missing import into one skipped module. The lane stays green
   and the module's tests simply are not there. 19 modules with 309 of
   the 1132 collected node ids are guarded that way, all on ``rfc8785``
   or ``jsonschema`` — both *declared, non-optional* dependencies of
   this package. That is the silent path, and it is what
   :func:`test_declared_dependencies_are_importable` and
   :func:`test_import_time_skip_guards_are_on_optional_imports_only`
   close.

Scope: this repository only. The lane is ``.github/workflows/ci.yml``
job ``test`` (display name ``pytest (py3.13)``), a required status check
on ``main``; it runs ``pytest tests/`` with no path filter, so "collected
by the lane" and "collected by ``pytest tests/``" are the same question.

Running this file in an environment without the declared dependencies
(a dependency-free sandbox) fails on purpose: such an environment is not
the required lane and must not be mistaken for it.
"""

from __future__ import annotations

import ast
import functools
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = REPO_ROOT / "tests"
PYPROJECT = REPO_ROOT / "pyproject.toml"

#: Declared dependency (distribution name) -> module name to import.
#: Every entry of ``[project].dependencies`` must appear here, so adding
#: a dependency is a visible decision rather than a silent one.
IMPORT_NAMES = {
    "jsonschema": "jsonschema",
    "rfc8785": "rfc8785",
    "cryptography": "cryptography",
    "shamir-mnemonic": "shamir_mnemonic",
    "PyYAML": "yaml",
}

#: Import-time skip guards that are allowed, with the reason. Anything
#: named here is genuinely optional in *this* repository's lane; a guard
#: on a declared dependency is not (it hides tests instead of failing).
ALLOWED_IMPORT_TIME_GUARDS = {
    # module name -> why it may be absent
    "wat.merkle.aggregator": "lives in wakir-runtime; only importable in the compat lane",
}

#: Modules that legitimately contribute no node id. Empty on purpose:
#: a module that collects nothing is a test that silently left the lane.
MODULES_WITHOUT_NODE_IDS: dict[str, str] = {}


@functools.lru_cache(maxsize=1)
def _collect() -> tuple[int, str, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "--collect-only", "-q",
         "-p", "no:cacheprovider", "-o", "addopts="],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=600,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _node_ids_per_module() -> dict[str, int]:
    _, stdout, _ = _collect()
    counts: dict[str, int] = {}
    for line in stdout.splitlines():
        if "::" in line:
            module = line.split("::", 1)[0].strip()
            counts[module] = counts.get(module, 0) + 1
    return counts


def _test_modules() -> list[Path]:
    return sorted(TESTS_DIR.rglob("test_*.py"))


def _declared_dependencies() -> list[str]:
    """``[project].dependencies`` without a TOML parser (3.10 has none)."""
    text = PYPROJECT.read_text(encoding="utf-8")
    block = re.search(r"^dependencies = \[(.*?)^\]", text, re.MULTILINE | re.DOTALL)
    assert block, "pyproject.toml has no [project].dependencies list"
    names = []
    for raw in re.findall(r'"([^"]+)"', block.group(1)):
        names.append(re.split(r"[<>=!~\[ ]", raw, maxsplit=1)[0])
    assert names, "no dependency parsed from pyproject.toml"
    return names


def _import_time_guards(path: Path) -> list[str]:
    """Modules guarded by ``pytest.importorskip`` at *module* level."""
    guarded: list[str] = []
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if not isinstance(node, (ast.Expr, ast.Assign, ast.AnnAssign)):
            continue  # inside a function: the test skips, the module still collects
        for sub in ast.walk(node):
            if (
                isinstance(sub, ast.Call)
                and isinstance(sub.func, ast.Attribute)
                and sub.func.attr == "importorskip"
                and sub.args
                and isinstance(sub.args[0], ast.Constant)
            ):
                guarded.append(sub.args[0].value)
    return guarded


def test_collect_only_reports_no_errors() -> None:
    """A module that cannot be imported must fail the lane, not vanish.

    pytest exits ``2`` and appends ``, N errors`` to the summary line
    when a module fails to import. Both are asserted, so neither
    ``--continue-on-collection-errors`` nor a swallowed exit code can
    turn a missing module back into a green tick.
    """
    returncode, stdout, stderr = _collect()
    summary = [ln for ln in stdout.splitlines() if re.match(r"^\d+ tests? collected", ln)]
    assert summary, f"no collection summary line\n{stdout[-4000:]}"
    assert "error" not in summary[-1], summary[-1]
    reported_errors = [ln for ln in stdout.splitlines() if ln.startswith("ERROR ")]
    assert not reported_errors, reported_errors
    assert returncode == 0, f"exit {returncode}\n{stdout[-4000:]}\n{stderr[-2000:]}"


def test_every_test_module_contributes_at_least_one_node_id() -> None:
    """No module may leave the lane silently."""
    counts = _node_ids_per_module()
    empty = []
    for path in _test_modules():
        rel = str(path.relative_to(REPO_ROOT))
        if counts.get(rel, 0) == 0 and rel not in MODULES_WITHOUT_NODE_IDS:
            empty.append(rel)
    assert not empty, (
        "these modules collected nothing — an import-time skip or an empty "
        f"module, either way their assertions did not run: {empty}"
    )


def test_collected_node_id_total_is_the_sum_of_the_modules() -> None:
    """Guards against a parse that silently loses node ids."""
    counts = _node_ids_per_module()
    _, stdout, _ = _collect()
    reported = re.search(r"^(\d+) tests? collected", stdout, re.MULTILINE)
    assert reported, stdout[-2000:]
    assert sum(counts.values()) == int(reported.group(1))
    assert len(counts) == len(_test_modules())


@pytest.mark.parametrize("dependency", _declared_dependencies())
def test_declared_dependencies_are_importable(dependency: str) -> None:
    """Turn 309 silently skipped node ids into one loud failure.

    ``rfc8785``, ``jsonschema`` and ``cryptography`` are declared, not
    optional. If the lane's environment lacks one, 19 test modules skip
    at import time and the tick stays green. Here it does not.
    """
    assert dependency in IMPORT_NAMES, (
        f"new dependency {dependency!r}: add its import name to IMPORT_NAMES "
        "so the lane keeps checking that it is really installed"
    )
    # Deliberately __import__, never pytest.importorskip: a missing
    # declared dependency has to fail, not skip.
    __import__(IMPORT_NAMES[dependency])


def test_import_time_skip_guards_are_on_optional_imports_only() -> None:
    """A guard on a declared dependency hides tests instead of failing."""
    declared = set(_declared_dependencies()) | set(IMPORT_NAMES.values())
    offenders: dict[str, list[str]] = {}
    for path in _test_modules():
        guards = _import_time_guards(path)
        bad = [g for g in guards if g not in ALLOWED_IMPORT_TIME_GUARDS]
        if bad:
            offenders[str(path.relative_to(REPO_ROOT))] = bad
    # Today every import-time guard is on rfc8785/jsonschema, i.e. on
    # declared dependencies. They stay (removing them is a separate,
    # owner-side change), but they are only harmless because
    # test_declared_dependencies_are_importable fails first if the
    # dependency is missing. What must not happen unnoticed is a guard on
    # something *undeclared*: that would be a test disappearing with no
    # check behind it at all.
    undeclared = {
        module: [g for g in guards if g.split(".")[0] not in declared]
        for module, guards in offenders.items()
    }
    undeclared = {m: g for m, g in undeclared.items() if g}
    assert not undeclared, (
        "import-time pytest.importorskip on an undeclared module: these "
        "tests vanish from a green lane. Declare the dependency or list "
        f"the module in ALLOWED_IMPORT_TIME_GUARDS with a reason: {undeclared}"
    )
