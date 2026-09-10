"""The three published distributions work together outside this checkout.

This is deliberately an artifact gate, not a cardiacFoam scientific run.  It
builds each distribution from a temporary copy, installs the resulting wheels
into a fresh virtual environment, and exercises installed plugin discovery
and the public ``describe`` edge.  No source case, OpenFOAM installation, or
solver binary participates.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import textwrap
import venv
from pathlib import Path

import pytest


# This test is directly below ``tests/`` (unlike Core's wheel test, which is
# below ``tests/core/``), so the repository root is parent 3 rather than 4.
_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_PACKAGES = ("omnidriver", "omnidriver-openfoam", "omnidriver-cardiacfoam")


def _run(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


@pytest.mark.slow
def test_all_package_wheels_discover_and_invoke_cardiacfoam(tmp_path: Path) -> None:
    """Prove the declared three-distribution route without checkout imports."""
    source_root = tmp_path / "sources"
    dist_root = tmp_path / "dist"
    source_root.mkdir()
    dist_root.mkdir()
    for package in _PACKAGES:
        shutil.copytree(_REPOSITORY_ROOT / "packages" / package, source_root / package)

    environment_root = tmp_path / "venv"
    venv.create(environment_root, with_pip=True)
    python = environment_root / "bin" / "python"
    _run([str(python), "-m", "pip", "install", "-q", "build"], cwd=tmp_path)

    wheels: list[Path] = []
    for package in _PACKAGES:
        _run(
            [
                str(python),
                "-m",
                "build",
                "--wheel",
                str(source_root / package),
                "--outdir",
                str(dist_root),
            ],
            cwd=tmp_path,
        )
        wheels.append(next(dist_root.glob(f"{package.replace('-', '_')}-*.whl")))

    _run(
        [str(python), "-m", "pip", "install", "-q", *(str(wheel) for wheel in wheels)],
        cwd=tmp_path,
    )

    probe_root = tmp_path / "probe"
    cases_root = probe_root / "cases"
    cases_root.mkdir(parents=True)
    clean_environment = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    probe = textwrap.dedent(
        f"""
        import importlib.metadata as metadata
        from pathlib import Path
        from importlib.resources import files

        from omnidriver.core.plugin_discovery import discover_plugins
        from omnidriver.core.plugin_interface import generic_openfoam_context, load_plugin_context
        from omnidriver.core.runtime.sweep_runner import _stage_entry_case

        repository = Path({str(_REPOSITORY_ROOT)!r}).resolve()
        for distribution_name in {list(_PACKAGES)!r}:
            location = Path(metadata.distribution(distribution_name).locate_file("")).resolve()
            assert not location.is_relative_to(repository), location

        assert "cardiacfoam" in discover_plugins()
        assert load_plugin_context("cardiacfoam").identity.id == "org.cardiacfoam"
        assert generic_openfoam_context().capabilities.case_runtime_conventions.conventions().output_collection_relpath == "postProcessing"
        assert generic_openfoam_context().capabilities.case_runtime_conventions.conventions().time_directory_name_pattern
        assert generic_openfoam_context().capabilities.case_runtime_conventions.conventions().case_discovery_ignored_directory_names == ("postProcessing", "logs")
        assert "blockMesh" in generic_openfoam_context().capabilities.command_authorization.environment_commands()
        assert load_plugin_context("cardiacfoam").capabilities.case_runtime_conventions.conventions().output_collection_relpath == "postProcessing"
        assert load_plugin_context("cardiacfoam").capabilities.case_runtime_conventions.conventions().time_directory_name_pattern
        assert load_plugin_context("cardiacfoam").capabilities.case_runtime_conventions.conventions().case_discovery_ignored_directory_names == ("postProcessing", "logs")
        assert "blockMesh" in load_plugin_context("cardiacfoam").capabilities.command_authorization.environment_commands()
        assert files("omnidriver.cardiacfoam").joinpath(
            "fixtures/template/constant/electroProperties"
        ).is_file()

        # Core has no path-name default. In a neutral staging call, these are
        # authored inputs, even though the OpenFOAM adapter declares one of
        # the same names as a generated output root.
        source = Path("neutral-source")
        (source / "data").mkdir(parents=True)
        (source / "data" / "protocol.json").write_text("authored")
        (source / "postProcessing").mkdir()
        (source / "postProcessing" / "notes.txt").write_text("authored")
        staged = Path("neutral-staged")
        _stage_entry_case(source, staged)
        assert (staged / "data" / "protocol.json").read_text() == "authored"
        assert (staged / "postProcessing" / "notes.txt").read_text() == "authored"
        """
    )
    _run([str(python), "-c", probe], cwd=probe_root, env=clean_environment)

    describe = _run(
        [
            str(python),
            "-m",
            "omnidriver",
            "describe",
            "--plugin",
            "cardiacfoam",
            "--entry",
            "niederer2012",
            "--cases-root",
            str(cases_root),
        ],
        cwd=probe_root,
        env=clean_environment,
    )
    payload = json.loads(describe)
    assert payload["resolved_name"] == "niederer2012"
    assert payload["capability_manifest"]["plugin_identity"]["id"] == "org.cardiacfoam"
