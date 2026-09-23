"""Production override application emits native effective-value evidence."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from omnidriver.core.contracts.dictionary import DictEntry
from omnidriver.openfoam.apply_overrides import apply_overrides, override_target_paths
from omnidriver.openfoam.effective_dictionary import EffectiveDictionaryResult


class _Catalog:
    def entries_for(self, document: str) -> tuple[DictEntry, ...]:
        if document == "controlDict":
            return (DictEntry(driver_path="deltaT", description="time step", value_kind="scalar"),)
        return ()


def test_apply_resolves_effective_value_with_execution_environment(
    monkeypatch, tmp_path: Path,
) -> None:
    system = tmp_path / "system"
    system.mkdir()
    control_dict = system / "controlDict"
    control_dict.write_text("deltaT 0.001;\n")
    context = SimpleNamespace(
        capabilities=SimpleNamespace(
            dictionaries=SimpleNamespace(catalog=lambda: _Catalog()),
            override_scopes=SimpleNamespace(scopes=lambda: ()),
            dict_regeneration=SimpleNamespace(scopes=lambda: ()),
        ),
    )
    seen: dict = {}

    def resolve(path, entry, **kwargs):
        seen.update(path=path, entry=entry, kwargs=kwargs)
        return EffectiveDictionaryResult(
            status="resolved",
            value="0.0005",
            parser="foamDictionary",
            runtime="/runtime/openfoam",
            inspected_files=(str(control_dict),),
        )

    monkeypatch.setattr(
        "omnidriver.openfoam.effective_dictionary.resolve_effective_foam_entry",
        resolve,
    )
    environment = {"PATH": "/runtime/bin", "WM_PROJECT_DIR": "/runtime/openfoam"}
    evidence = apply_overrides(
        [{"driver_path": "deltaT", "value": "0.0005"}],
        case_root=tmp_path,
        driver_context=context,
        execution_env=environment,
    )

    assert "0.0005" in control_dict.read_text()
    assert seen == {
        "path": control_dict,
        "entry": "deltaT",
        "kwargs": {"bashrc": None, "env": environment},
    }
    assert evidence[0]["status"] == "resolved"
    assert evidence[0]["value"] == "0.0005"
    assert evidence[0]["matches_requested"] is True
    assert evidence[0]["driver_path"] == "deltaT"


def test_apply_reports_when_native_effective_value_differs_from_request(
    monkeypatch, tmp_path: Path,
) -> None:
    system = tmp_path / "system"
    system.mkdir()
    (system / "controlDict").write_text("deltaT 0.001;\n")
    context = SimpleNamespace(
        capabilities=SimpleNamespace(
            dictionaries=SimpleNamespace(catalog=lambda: _Catalog()),
            override_scopes=SimpleNamespace(scopes=lambda: ()),
            dict_regeneration=SimpleNamespace(scopes=lambda: ()),
        ),
    )
    monkeypatch.setattr(
        "omnidriver.openfoam.effective_dictionary.resolve_effective_foam_entry",
        lambda *args, **kwargs: EffectiveDictionaryResult(
            status="resolved", value="0.001", parser="foamDictionary",
            runtime="/runtime/openfoam",
        ),
    )

    evidence = apply_overrides(
        [{"driver_path": "deltaT", "value": "0.0005"}],
        case_root=tmp_path,
        driver_context=context,
        execution_env={"PATH": "/runtime/bin"},
    )

    assert evidence[0]["matches_requested"] is False


def test_override_target_paths_declares_all_files_before_mutation(
    tmp_path: Path,
) -> None:
    system = tmp_path / "system"
    system.mkdir()
    context = SimpleNamespace(
        capabilities=SimpleNamespace(
            dictionaries=SimpleNamespace(catalog=lambda: _Catalog()),
            override_scopes=SimpleNamespace(scopes=lambda: ()),
            dict_regeneration=SimpleNamespace(scopes=lambda: ()),
        ),
    )

    targets = override_target_paths(
        [
            {"driver_path": "deltaT", "value": "0.0005"},
            {"driver_path": "system/fvSchemes:ddtSchemes/default", "value": "Euler"},
        ],
        case_root=tmp_path,
        driver_context=context,
    )

    assert targets == (
        system / "controlDict",
        system / "fvSchemes",
    )
