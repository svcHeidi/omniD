"""Opt-in selected-source and selected-runtime preflight gates.

With no fixture variables these tests skip.  Once any source or native input
is supplied, incomplete or invalid selections fail before any case can be
staged.  They intentionally do not execute a solver or create output.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from selected_cardiacfoam_fixture import (
    FixtureInputError,
    selected_runtime_from_environment,
    selected_source_from_environment,
)


_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_selected_source_preflight() -> None:
    selected = selected_source_from_environment()
    if selected is None:
        pytest.skip("selected-source fixture was not requested")
    assert selected.root.is_dir()
    assert selected.src_status == ""
    assert selected.permitted_drift_digest.startswith("sha256:")


def test_selected_runtime_preflight() -> None:
    source = selected_source_from_environment()
    try:
        selected = selected_runtime_from_environment(
            source, repository_root=_REPOSITORY_ROOT
        )
    except FixtureInputError:
        # An explicitly supplied native input must fail rather than turn into
        # a skip; preserving the exception keeps that distinction visible.
        raise
    if selected is None:
        pytest.skip("selected-runtime fixture was not requested")
    assert selected.output_root.is_dir()
    assert selected.build_manifest.is_file()
    assert selected.build_manifest_digest.startswith("sha256:")
    assert dict(selected.openfoam_identity)["WM_PROJECT_DIR"]
