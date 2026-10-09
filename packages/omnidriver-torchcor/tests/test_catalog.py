from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from omnidriver.torchcor import catalog
from omnidriver.torchcor.catalog import Catalog, CatalogError, describe, source_digest

FIXTURES = Path(__file__).parent / "fixtures"
DESCRIBED = json.loads((FIXTURES / "describe.json").read_text())


def _repository(tmp_path: Path) -> Path:
    """A solver repository whose runner prints the committed --describe output."""
    root = tmp_path / "torchcor-cases"
    (root / "scripts").mkdir(parents=True)
    (root / "torchcor" / "torchcor").mkdir(parents=True)
    (root / "cases").mkdir()
    (root / "omnidriver.toml").write_text('plugin = "torchcor"\ntutorials = "cases"\nsource = "torchcor"\nscripts = "scripts"\n')
    (root / "torchcor" / "torchcor" / "__init__.py").write_text("")
    (root / "scripts" / "run_case.py").write_text(
        f"import sys\nsys.stdout.write(open({str(FIXTURES / 'describe.json')!r}).read())\n"
    )
    return root


def test_the_catalogue_is_built_from_the_runners_describe():
    built = Catalog.from_describe(DESCRIBED)
    assert built.keys["conductivity_S_per_m.et"]["kind"] == "scalar"
    assert built.keys["device"]["menu"] == ["cpu"]
    assert built.devices == ("cpu",)
    assert "TenTusscherPanfilov" in built.ionic_models
    assert built.ionic_models["TenTusscherPanfilov"]["options"]["cell_type"]["menu"] == ["ENDO", "EPI", "MCELL"]
    assert "V_init" in built.ionic_models["TenTusscherPanfilov"]["init"]


def test_the_digest_follows_the_bytes_of_the_runner_and_the_source_not_their_mtimes(tmp_path):
    root = _repository(tmp_path)
    runner, source = root / "scripts" / "run_case.py", root / "torchcor"
    first = source_digest(runner, source)
    (source / "torchcor" / "__init__.py").touch()
    assert source_digest(runner, source) == first
    (source / "torchcor" / "__init__.py").write_text("# changed\n")
    assert source_digest(runner, source) != first


def test_a_cached_describe_is_reused(tmp_path, monkeypatch):
    root = _repository(tmp_path)
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
    root = _repository(tmp_path)
    (root / "scripts" / "run_case.py").write_text("import sys\nsys.exit('no torchcor here')\n")
    with pytest.raises(CatalogError, match="--describe") as raised:
        describe(root / "scripts" / "run_case.py", root / "torchcor", dict(os.environ), None)
    assert "no torchcor here" in str(raised.value)


def test_without_a_supplied_repository_there_is_no_catalogue(monkeypatch):
    monkeypatch.delenv(catalog.REPOSITORY_VARIABLE, raising=False)
    assert catalog.supplied_catalog() is None


def test_a_supplied_repository_gives_its_catalogue(tmp_path, monkeypatch):
    root = _repository(tmp_path)
    monkeypatch.setenv(catalog.REPOSITORY_VARIABLE, str(root))
    monkeypatch.setenv("OMNIDRIVER_SCRATCH_DIR", str(tmp_path / "scratch"))
    assert catalog.supplied_catalog().keys["dx_mm"]["unit"] == "mm"


def test_the_key_catalogue_lists_every_key_and_the_cases_own_model_fields(tmp_path, monkeypatch):
    from omnidriver.torchcor.plugin import TorchCorPlugin

    root = _repository(tmp_path)
    case = root / "cases" / "nversion"
    case.mkdir()
    (case / "case.json").write_text((FIXTURES / "case.json").read_text())
    monkeypatch.setenv(catalog.REPOSITORY_VARIABLE, str(root))
    entries = {e["key"]: e for e in TorchCorPlugin().get_record_key_catalog(case)}
    assert {e["document"] for e in entries.values()} == {"case.json"}
    assert entries["chi_per_mm"]["value_kind"] == "scalar"
    assert entries["ionic_options.cell_type"]["menu"] == ["ENDO", "EPI", "MCELL"]
    assert entries["ionic_init.V_init"]["value_kind"] == "scalar"
    assert entries["dx_mm"]["source_refs"] == [f"{root / 'scripts' / 'run_case.py'} --describe"]


def test_without_a_runner_the_document_is_listed_open(monkeypatch, tmp_path):
    from omnidriver.torchcor.plugin import TorchCorPlugin

    monkeypatch.delenv(catalog.REPOSITORY_VARIABLE, raising=False)
    (tmp_path / "case.json").write_text((FIXTURES / "case.json").read_text())
    (entry,) = TorchCorPlugin().get_record_key_catalog(tmp_path)
    assert entry["document"] == "case.json" and entry["key"] == "<any>" and entry["validated"] is False
