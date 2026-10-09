from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
from torchcor_testing import FIXTURES, context_of, repository_with_runner

from omnidriver.torchcor import catalog
from omnidriver.torchcor.catalog import Catalog, CatalogError, describe, runner_digest

DESCRIBED = json.loads((FIXTURES / "describe.json").read_text())


def test_the_catalogue_is_built_from_the_runners_describe():
    built = Catalog.from_describe(DESCRIBED)
    assert built.keys["conductivity_S_per_m.et"]["kind"] == "scalar"
    assert built.keys["device"]["menu"] == ["cpu"]
    assert "TenTusscherPanfilov" in built.ionic_models
    assert built.ionic_models["TenTusscherPanfilov"]["options"]["cell_type"]["menu"] == ["ENDO", "EPI", "MCELL"]
    assert "V_init" in built.ionic_models["TenTusscherPanfilov"]["init"]


def _interpreter(directory: Path) -> dict[str, str]:
    """An environment whose PATH starts with a python3 of its own at ``directory``."""
    directory.mkdir(parents=True)
    python = directory / "python3"
    python.write_text(f'#!/bin/sh\nexec {sys.executable} "$@"\n')
    python.chmod(0o755)
    return {"PATH": f"{directory}:/usr/bin:/bin"}


def test_the_digest_follows_the_bytes_of_the_runner_and_the_source_not_their_mtimes(tmp_path):
    root = repository_with_runner(tmp_path)
    runner, source, env = root / "scripts" / "run_case.py", root / "torchcor", _interpreter(tmp_path / "bin")
    first = runner_digest(runner, source, env)
    (source / "torchcor" / "__init__.py").touch()
    assert runner_digest(runner, source, env) == first
    (source / "torchcor" / "__init__.py").write_text("# changed\n")
    assert runner_digest(runner, source, env) != first


def test_the_digest_follows_the_interpreter_its_torch_and_the_host(tmp_path, monkeypatch):
    root = repository_with_runner(tmp_path)
    runner, source = root / "scripts" / "run_case.py", root / "torchcor"
    site = tmp_path / "site" / "torch"
    site.mkdir(parents=True)
    (site / "__init__.py").write_text("")
    (site / "version.py").write_text("__version__ = '2.14.1'\n")
    env = {**_interpreter(tmp_path / "a"), "PYTHONPATH": str(site.parent)}
    first = runner_digest(runner, source, env)
    assert runner_digest(runner, source, {**_interpreter(tmp_path / "b"), "PYTHONPATH": str(site.parent)}) != first
    (site / "version.py").write_text("__version__ = '2.15.0'\n")
    assert runner_digest(runner, source, env) != first
    (site / "version.py").write_text("__version__ = '2.14.1'\n")
    assert runner_digest(runner, source, env) == first
    monkeypatch.setattr(catalog.platform, "node", lambda: "another-host")
    assert runner_digest(runner, source, env) != first


def test_a_cached_describe_is_reused(tmp_path, monkeypatch):
    root = repository_with_runner(tmp_path)
    scratch = tmp_path / "scratch"
    runner, source = root / "scripts" / "run_case.py", root / "torchcor"
    first = describe(runner, source, dict(os.environ), scratch)
    assert first == DESCRIBED
    assert len(list((scratch / "torchcor-describe").glob("*.json"))) == 1
    catalog._MEMO.clear()

    def refuse(*args, **kwargs):
        raise AssertionError("describe ran again")

    monkeypatch.setattr(catalog.subprocess, "run", refuse)
    assert describe(runner, source, dict(os.environ), scratch) == DESCRIBED


def test_a_failing_describe_is_refused_naming_the_command_and_its_stderr(tmp_path):
    root = repository_with_runner(tmp_path)
    (root / "scripts" / "run_case.py").write_text("import sys\nsys.exit('no torchcor here')\n")
    with pytest.raises(CatalogError, match="--describe") as raised:
        describe(root / "scripts" / "run_case.py", root / "torchcor", dict(os.environ), None)
    assert "no torchcor here" in str(raised.value)


def test_without_a_repository_there_is_no_catalogue():
    assert catalog.repository_catalog(context_of()) is None


def test_the_contexts_repository_gives_its_catalogue(tmp_path, monkeypatch):
    root = repository_with_runner(tmp_path)
    monkeypatch.setenv("OMNIDRIVER_SCRATCH_DIR", str(tmp_path / "scratch"))
    assert catalog.repository_catalog(context_of(root)).keys["dx_mm"]["unit"] == "mm"


def test_the_key_catalogue_lists_every_key_and_the_cases_own_model_fields(tmp_path):
    from omnidriver.torchcor.plugin import TorchCorPlugin

    root = repository_with_runner(tmp_path)
    case = root / "cases" / "nversion"
    case.mkdir()
    (case / "case.json").write_text((FIXTURES / "case.json").read_text())
    entries = {e["key"]: e for e in TorchCorPlugin().get_record_key_catalog(case, driver_context=context_of(root))}
    assert {e["document"] for e in entries.values()} == {"case.json"}
    assert entries["chi_per_mm"]["value_kind"] == "scalar"
    assert entries["ionic_options.cell_type"]["menu"] == ["ENDO", "EPI", "MCELL"]
    assert entries["ionic_init.V_init"]["value_kind"] == "scalar" and entries["ionic_init.V_init"]["default"] == -86.2
    assert entries["dx_mm"]["source_refs"] == [f"{root / 'scripts' / 'run_case.py'} --describe"]


def test_without_a_runner_the_document_is_listed_open(tmp_path):
    from omnidriver.torchcor.plugin import TorchCorPlugin

    (tmp_path / "case.json").write_text((FIXTURES / "case.json").read_text())
    (entry,) = TorchCorPlugin().get_record_key_catalog(tmp_path, driver_context=context_of())
    assert entry["document"] == "case.json" and entry["key"] == "<any>" and entry["validated"] is False


def test_a_case_is_checked_once_per_runner_and_bytes(tmp_path, monkeypatch):
    root = repository_with_runner(tmp_path)
    case = tmp_path / "case.json"
    case.write_text((FIXTURES / "case.json").read_text())
    runner, source = root / "scripts" / "run_case.py", root / "torchcor"
    first = catalog.check(runner, source, dict(os.environ), case)
    assert [item["key"] for item in first] == ["theta", "ionic_options.cell_type", "ionic_init.V_int"]

    def refuse(*args, **kwargs):
        raise AssertionError("--check ran again")

    monkeypatch.setattr(catalog.subprocess, "run", refuse)
    assert catalog.check(runner, source, dict(os.environ), case) == first
    case.write_text(case.read_text() + " ")
    with pytest.raises(AssertionError, match="ran again"):
        catalog.check(runner, source, dict(os.environ), case)
