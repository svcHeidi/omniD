"""TorchCor runs the repository's own package (an editable install), read when the plan is made."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from omnidriver.torchcor import provenance
from omnidriver.torchcor.provenance import torchcor_solver_builds


def _repository(tmp_path):
    source = tmp_path / "cases" / "torchcor"
    (source / "torchcor").mkdir(parents=True)
    (source / "torchcor" / "__init__.py").write_text("")
    (source / "torchcor" / "solver.py").write_text("x = 1\n")
    python = tmp_path / "venv" / "bin" / "python3"
    python.parent.mkdir(parents=True)
    python.write_text("#!/bin/sh\n")
    python.chmod(0o755)
    repository = SimpleNamespace(root=tmp_path / "cases", plugin="torchcor", source=source)
    return repository, {"PATH": str(python.parent)}


def test_the_editable_package_inside_the_repository_is_live_and_matches(tmp_path, monkeypatch):
    repository, env = _repository(tmp_path)
    monkeypatch.setattr(provenance, "_package_file", lambda python, env: repository.source / "torchcor" / "__init__.py")
    (entry,) = torchcor_solver_builds(env, repository=repository)
    (build,) = entry.builds
    assert (entry.solver, build.name, build.known) == ("torchcor", "torchcor", "live")
    assert build.source == entry.repository and build.digest == entry.repository.digest


def test_a_package_installed_from_elsewhere_is_unknown(tmp_path, monkeypatch):
    repository, env = _repository(tmp_path)
    monkeypatch.setattr(provenance, "_package_file", lambda python, env: tmp_path / "site" / "torchcor" / "__init__.py")
    (entry,) = torchcor_solver_builds(env, repository=repository)
    assert (entry.builds[0].known, entry.builds[0].source) == ("unknown", None)


def test_no_repository_is_no_entry():
    assert torchcor_solver_builds({"PATH": ""}, repository=None) == ()
