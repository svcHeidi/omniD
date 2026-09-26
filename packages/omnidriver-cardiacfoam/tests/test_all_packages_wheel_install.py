"""The four published distributions work together outside this checkout.

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
_PACKAGES = (
    "omnidriver",
    "omnidriver-openfoam",
    "omnidriver-cardiacfoam",
    "omnidriver-cardiaccore",
    # Added 2026-09-25 (solver-conformance B-I3): the fifth distribution. It
    # registers no entry point until its plugin exists (Task 11), so here it
    # proves only that its wheel installs beside the other four and ships its
    # generated catalog -- the location check below covers it too.
    # Corrected 2026-09-25 (final review S-M5): its entry point has been
    # active since e4bc873 (Task 11), so this also installs a registered
    # `opencarp` plugin beside the other four.
    "omnidriver-opencarp",
)


def _run(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


@pytest.mark.slow
def test_all_package_wheels_discover_and_invoke_cardiacfoam(tmp_path: Path) -> None:
    """Prove the declared four-distribution route without checkout imports."""
    source_root = tmp_path / "sources"
    dist_root = tmp_path / "dist"
    source_root.mkdir()
    dist_root.mkdir()
    for package in _PACKAGES:
        shutil.copytree(_REPOSITORY_ROOT / "packages" / package, source_root / package)

    environment_root = tmp_path / "venv"
    # symlinks=True is load-bearing. 2026-09-23: venv.create defaults to
    # symlinks=False, which *copies* the interpreter, and a copied uv-managed
    # CPython cannot resolve @rpath/libpython3.11.dylib -- dyld aborts and
    # ensurepip dies with SIGABRT before any repository code is imported. Both
    # wheel tests are @pytest.mark.slow, so that abort was invisible to every
    # `-m "not slow"` run. See Core's test_wheel_install_imports.py, where the
    # same default had kept the test from ever executing on such a machine.
    venv.create(environment_root, with_pip=True, symlinks=True)
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
        from omnidriver.openfoam.environment import openfoam_environment_context
        from omnidriver.core.plugin_interface import load_plugin_context
        from omnidriver.core.runtime.sweep_runner import _stage_entry_case

        repository = Path({str(_REPOSITORY_ROOT)!r}).resolve()
        for distribution_name in {list(_PACKAGES)!r}:
            location = Path(metadata.distribution(distribution_name).locate_file("")).resolve()
            assert not location.is_relative_to(repository), location

        assert "cardiacfoam" in discover_plugins()
        # `DriverContext.identity` is a `StackIdentity` (one `ProviderIdentity`
        # per composed provider under `.providers`, ordered least-specific
        # first) -- it has no singular `.id` of its own. Corrected 2026-09-22
        # (final whole-branch review, Finding 3): this raised `AttributeError`
        # until now, unnoticed because this whole file is `@pytest.mark.slow`.
        assert load_plugin_context("cardiacfoam").identity.to_json()["providers"][-1]["id"] == "org.cardiacfoam"
        assert openfoam_environment_context().capabilities.case_runtime_conventions.conventions().output_collection_relpath == "postProcessing"
        assert openfoam_environment_context().capabilities.case_runtime_conventions.conventions().instance_directory_pattern
        assert openfoam_environment_context().capabilities.case_runtime_conventions.conventions().case_discovery_ignored_directory_names == ("postProcessing", "logs")
        assert "blockMesh" in openfoam_environment_context().capabilities.command_authorization.environment_commands()
        assert load_plugin_context("cardiacfoam").capabilities.case_runtime_conventions.conventions().output_collection_relpath == "postProcessing"
        assert load_plugin_context("cardiacfoam").capabilities.case_runtime_conventions.conventions().instance_directory_pattern
        assert load_plugin_context("cardiacfoam").capabilities.case_runtime_conventions.conventions().case_discovery_ignored_directory_names == ("postProcessing", "logs")
        assert "blockMesh" in load_plugin_context("cardiacfoam").capabilities.command_authorization.environment_commands()
        assert files("omnidriver.cardiacfoam").joinpath(
            "fixtures/template/constant/electroProperties"
        ).is_file()

        assert files("omnidriver.opencarp").joinpath("opencarp_parameters.json").is_file()

        assert "cardiaccore" in discover_plugins()
        # Same migration as the cardiacFoam assertion above.
        assert load_plugin_context("cardiaccore").identity.to_json()["providers"][-1]["id"] == "org.omnidriver.cardiaccore"
        assert load_plugin_context("cardiaccore").capabilities.case_runtime_conventions.conventions().output_collection_relpath == "postProcessing"
        assert "blockMesh" in load_plugin_context("cardiaccore").capabilities.command_authorization.environment_commands()

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
    # `plugin_identity` is `StackIdentity.to_json()` (Task 7's migration,
    # corrected 2026-09-22 here): no top-level `id`, only `providers`, one
    # `ProviderIdentity` per composed provider, ordered least-specific first.
    # cardiacFoam is the most specific (composed on top of the openfoam
    # environment provider), so it is the last entry -- same `[-1]` idiom as
    # `test_plugin_architecture.py`'s `identity.to_json()["providers"][-1]`.
    assert (
        payload["capability_manifest"]["plugin_identity"]["providers"][-1]["id"]
        == "org.cardiacfoam"
    )

    cardiaccore_describe = _run(
        [
            str(python),
            "-m",
            "omnidriver",
            "describe",
            "--plugin",
            "cardiaccore",
            "--entry",
            "cardiaccore-human-purkinje-slab",
            "--cases-root",
            str(cases_root),
        ],
        cwd=probe_root,
        env=clean_environment,
    )
    cardiaccore_payload = json.loads(cardiaccore_describe)
    assert cardiaccore_payload["resolved_name"] == "cardiaccore-human-purkinje-slab"
    # Same migration as the cardiacFoam assertion above -- see
    # `test_generic_contract.py`'s `identity.to_json()["providers"][-1]["id"]`
    # for the established idiom this follows.
    assert (
        cardiaccore_payload["capability_manifest"]["plugin_identity"]["providers"][-1]["id"]
        == "org.omnidriver.cardiaccore"
    )
