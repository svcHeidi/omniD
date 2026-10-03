"""The published distributions work together outside this checkout: an artifact
gate that builds and installs every wheel into a fresh venv and exercises plugin
discovery and ``describe``. No case, OpenFOAM or solver binary participates.
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


_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_PACKAGES = (
    "omnidriver",
    "omnidriver-openfoam",
    "omnidriver-cardiacfoam",
    "omnidriver-cardiaccore",
    "omnidriver-opencarp",
)


def _run(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


@pytest.mark.slow
def test_all_package_wheels_discover_and_invoke_cardiacfoam(tmp_path: Path) -> None:
    source_root = tmp_path / "sources"
    dist_root = tmp_path / "dist"
    source_root.mkdir()
    dist_root.mkdir()
    for package in _PACKAGES:
        shutil.copytree(_REPOSITORY_ROOT / "packages" / package, source_root / package)

    environment_root = tmp_path / "venv"
    # symlinks=True: a copied uv-managed CPython cannot resolve
    # @rpath/libpython3.11.dylib, so ensurepip dies with SIGABRT.
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
    # A record's describe needs its native case directory to exist; nothing in it is read.
    (cases_root / "NiedererEtAl2011verification").mkdir()
    (cases_root / "cases" / "bivCase").mkdir(parents=True)
    clean_environment = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    probe = textwrap.dedent(
        f"""
        import importlib.metadata as metadata
        from pathlib import Path
        from importlib.resources import files

        from omnidriver.core.plugin_discovery import discover_plugins
        from omnidriver.core.plugin_interface import load_plugin_context
        from omnidriver.core.runtime.sweep_runner import _stage_entry_case

        repository = Path({str(_REPOSITORY_ROOT)!r}).resolve()
        for distribution_name in {list(_PACKAGES)!r}:
            location = Path(metadata.distribution(distribution_name).locate_file("")).resolve()
            assert not location.is_relative_to(repository), location

        assert "cardiacfoam" in discover_plugins()
        # `DriverContext.identity` is a `StackIdentity`, one `ProviderIdentity`
        # per provider, least specific first; it has no singular `.id`.
        assert load_plugin_context("cardiacfoam").identity.to_json()["providers"][-1]["id"] == "org.cardiacfoam"
        assert load_plugin_context("openfoam-environment").stack.call("get_case_runtime_conventions").generated_directory_names
        assert load_plugin_context("openfoam-environment").stack.call("get_case_runtime_conventions").instance_directory_pattern
        assert "blockMesh" in load_plugin_context("openfoam-environment").stack.call("get_environment_commands")
        assert load_plugin_context("cardiacfoam").stack.call("get_case_runtime_conventions").generated_directory_names
        assert load_plugin_context("cardiacfoam").stack.call("get_case_runtime_conventions").instance_directory_pattern
        assert "blockMesh" in load_plugin_context("cardiacfoam").stack.call("get_environment_commands")
        assert files("omnidriver.cardiacfoam").joinpath(
            "fixtures/template/constant/electroProperties"
        ).is_file()

        assert files("omnidriver.opencarp").joinpath("opencarp_parameters.json").is_file()

        assert "cardiaccore" in discover_plugins()
        # Same migration as the cardiacFoam assertion above.
        assert load_plugin_context("cardiaccore").identity.to_json()["providers"][-1]["id"] == "org.omnidriver.cardiaccore"
        assert load_plugin_context("cardiaccore").stack.call("get_case_runtime_conventions").generated_directory_names
        assert "blockMesh" in load_plugin_context("cardiaccore").stack.call("get_environment_commands")

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
            "niederer2011",
            "--cases-root",
            str(cases_root),
        ],
        cwd=probe_root,
        env=clean_environment,
    )
    payload = json.loads(describe)
    assert payload["entry"]["entry_name"] == "niederer2011"
    # Providers are ordered least-specific first; cardiacFoam is the last.
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
            "humanSlab",
            "--cases-root",
            str(cases_root),
        ],
        cwd=probe_root,
        env=clean_environment,
    )
    cardiaccore_payload = json.loads(cardiaccore_describe)
    assert cardiaccore_payload["entry"]["entry_name"] == "humanSlab"
    assert (
        cardiaccore_payload["capability_manifest"]["plugin_identity"]["providers"][-1]["id"]
        == "org.omnidriver.cardiaccore"
    )
