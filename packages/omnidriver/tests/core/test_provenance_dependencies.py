"""Resolution and fingerprinting of declared runtime dependencies."""

from __future__ import annotations

import os
from pathlib import Path

from omnidriver.core.plugin_capabilities import RuntimeDependency
from omnidriver.core.runtime.provenance import snapshot_from_components
from omnidriver.core.runtime.provenance_dependencies import (
    component_for_runtime_dependency,
)


def test_a_required_dependency_with_no_path_is_unavailable() -> None:
    dependency = RuntimeDependency(name="cardiacFoam", path=None, required=True)
    component = component_for_runtime_dependency(dependency)
    assert component.method == "unavailable"
    assert component.strength == "unavailable"
    assert component.path == "cardiacFoam"


def test_an_optional_dependency_with_no_path_is_still_reported_unavailable(
    tmp_path: Path,
) -> None:
    """I3b: a missing library in lightweight mode is a normal state, not an
    error -- but it must still be visible, never silently dropped, so it
    still shows up as unavailable rather than being omitted."""
    dependency = RuntimeDependency(name="electroMechanicalModels", path=None, required=False)
    component = component_for_runtime_dependency(dependency)
    assert component.method == "unavailable"
    assert component.strength == "unavailable"


def test_a_present_dependency_is_fingerprinted_by_content(tmp_path: Path) -> None:
    lib = tmp_path / "libbin" / "libelectroModels.dylib"
    lib.parent.mkdir()
    lib.write_bytes(b"binary contents")
    dependency = RuntimeDependency(name="electroModels", path=lib, required=True)
    component = component_for_runtime_dependency(dependency)
    assert component.method == "sha256"
    assert component.strength == "content"
    assert component.digest is not None
    # Identity is the declared dependency name, not the resolved filename or
    # directory -- a library found via a different search directory must
    # still compare as the same dependency.
    assert component.path == "electroModels"


def test_replacing_the_fake_solver_binarys_contents_changes_the_fingerprint(
    tmp_path: Path,
) -> None:
    """The acceptance criterion: rewriting a fake cardiacFoam binary's
    *contents* (not touching it) changes the declared dependency fingerprint
    for an Allrun-driven case. This is what makes a rebuilt solver visible
    to a resume that would otherwise only fingerprint the Allrun script."""
    binary = tmp_path / "bin" / "cardiacFoam"
    binary.parent.mkdir()
    binary.write_bytes(b"#!/bin/sh\necho build-one\n")

    before = component_for_runtime_dependency(
        RuntimeDependency(name="cardiacFoam", path=binary, required=True)
    )

    binary.write_bytes(b"#!/bin/sh\necho build-two -- rebuilt solver\n")

    after = component_for_runtime_dependency(
        RuntimeDependency(name="cardiacFoam", path=binary, required=True)
    )

    assert before.digest != after.digest


def test_a_timestamp_only_touch_leaves_the_fingerprint_unchanged(tmp_path: Path) -> None:
    """A checkout or rsync must not read as a rebuilt solver."""
    binary = tmp_path / "cardiacFoam"
    binary.write_bytes(b"#!/bin/sh\necho same\n")
    dependency = RuntimeDependency(name="cardiacFoam", path=binary, required=True)

    before = component_for_runtime_dependency(dependency)
    os.utime(binary, (1_800_000_000, 1_800_000_000))
    after = component_for_runtime_dependency(dependency)

    assert before.digest == after.digest


def test_a_missing_required_dependency_makes_a_snapshot_built_from_it_partial() -> None:
    """A missing required dependency makes the snapshot partial."""
    missing = component_for_runtime_dependency(
        RuntimeDependency(name="libelectroModels", path=None, required=True)
    )
    snapshot = snapshot_from_components(
        (missing,), workflow_digest="sha256:wf", plugin_identity={"id": "org.cardiacfoam"},
    )
    assert snapshot.is_complete is False


def test_a_fully_resolved_dependency_set_is_a_complete_snapshot(tmp_path: Path) -> None:
    binary = tmp_path / "cardiacFoam"
    binary.write_bytes(b"#!/bin/sh\n")
    present = component_for_runtime_dependency(
        RuntimeDependency(name="cardiacFoam", path=binary, required=True)
    )
    snapshot = snapshot_from_components(
        (present,), workflow_digest="sha256:wf", plugin_identity={"id": "org.cardiacfoam"},
    )
    assert snapshot.is_complete is True
