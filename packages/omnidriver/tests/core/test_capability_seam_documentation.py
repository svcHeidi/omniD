"""The capability seam contract must stay documented, accurate, and rendered."""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

import pytest

from omnidriver.core import (
    capability_seams,
    compatibility,
    plugin_capabilities,
    plugin_interface,
)

from conftest import NO_REPO_ROOT, repo_root, skip_without_repo

# plugin_capabilities.__file__ = .../src/omnidriver/core/plugin_capabilities.py
DRIVER_ROOT = Path(plugin_capabilities.__file__).resolve().parent.parent.parent
pytestmark = skip_without_repo

REPO_ROOT = repo_root or NO_REPO_ROOT
GENERATOR = REPO_ROOT / "scripts" / "export-capability-seams.py"

# :consumed-by: paths were written for the old single-package layout, where
# every module lived under one src/ tree. Now core/openfoam/cardiac are
# separate packages with separate src/ roots, plus a repo-root scripts/
# directory -- resolve each relpath against whichever root actually has it.
_PACKAGE_ROOTS = (
    DRIVER_ROOT,
    REPO_ROOT / "packages" / "omnidriver-openfoam" / "src",
    REPO_ROOT / "packages" / "omnidriver-cardiacfoam" / "src",
    REPO_ROOT,
)


def _resolve_consumed_by(relpath: str) -> Path | None:
    for root in _PACKAGE_ROOTS:
        candidate = root / relpath
        if candidate.is_file():
            return candidate
    return None

REQUIRED_FIELDS = ("adapts", "consumed-by", "fallback", "status")
# The closed tier vocabulary lives on capability_seams.TIERS; restating it
# here would be exactly the kind of duplicated fact this test exists to catch.
VALID_STATUSES = capability_seams.TIERS

CAPABILITY_FIELDS = tuple(plugin_capabilities.PluginCapabilities.__annotations__)


def _protocol_for(field: str):
    annotation = plugin_capabilities.PluginCapabilities.__annotations__[field]
    name = annotation if isinstance(annotation, str) else annotation.__name__
    protocol = getattr(plugin_capabilities, name, None)
    assert protocol is not None, f"{field}: no Protocol named {name!r}"
    return name, protocol


def _fields(field: str) -> dict[str, str]:
    _, protocol = _protocol_for(field)
    return capability_seams.parse_fields(protocol.__doc__)


def _plugin_members() -> set[str]:
    """Every member a plugin may legitimately expose, across both protocols."""
    members: set[str] = set()
    for protocol in (
        plugin_interface.SolverPlugin,
        plugin_interface.SolverPluginOptionalHooks,
    ):
        members |= {name for name in dir(protocol) if not name.startswith("_")}
    return members


def _compatibility_functions() -> set[str]:
    return {name for name in dir(compatibility) if name.startswith("absent_")}


@pytest.mark.parametrize("field", CAPABILITY_FIELDS)
def test_capability_documents_all_four_fields(field: str) -> None:
    name, protocol = _protocol_for(field)
    doc = protocol.__doc__
    assert doc and doc.strip(), f"{name} has no docstring"

    parsed = _fields(field)
    missing = [key for key in REQUIRED_FIELDS if not parsed.get(key, "").strip()]
    assert not missing, f"{name} is missing or has empty fields: {missing}"

    # Prose, not just a field block: the fields describe the wiring, the prose
    # has to say why the seam exists.
    prose = doc.split(":adapts:")[0].strip()
    assert len(prose) > 80, f"{name} has a field block but no substantive prose"


@pytest.mark.parametrize("field", CAPABILITY_FIELDS)
def test_adapts_names_real_plugin_members(field: str) -> None:
    name, _ = _protocol_for(field)
    declared = _fields(field)["adapts"]
    if declared.strip() == "none":
        return
    members = _plugin_members()
    for member in (item.strip() for item in declared.split(",")):
        assert member in members, (
            f"{name} :adapts: names {member!r}, which is not a member of "
            "SolverPlugin or SolverPluginOptionalHooks"
        )


@pytest.mark.parametrize("field", CAPABILITY_FIELDS)
def test_fallback_names_real_compatibility_functions(field: str) -> None:
    name, _ = _protocol_for(field)
    declared = _fields(field)["fallback"]
    if declared.strip() == "none":
        return
    known = _compatibility_functions()
    for fn in (item.strip() for item in declared.split(",")):
        assert fn in known, (
            f"{name} :fallback: names {fn!r}, which is not a function in "
            "core/compatibility.py"
        )


@pytest.mark.parametrize("field", CAPABILITY_FIELDS)
def test_consumed_by_names_modules_that_touch_the_capability(field: str) -> None:
    name, _ = _protocol_for(field)
    declared = _fields(field)["consumed-by"]
    if declared.startswith("none"):
        return
    # Subset semantics: every listed module must really touch this capability,
    # but the list need not be exhaustive -- adding a consumer must not break
    # the build.
    for relpath in (item.strip() for item in declared.split(",")):
        path = _resolve_consumed_by(relpath)
        assert path is not None, f"{name} :consumed-by: names missing file {relpath}"
        assert f"capabilities.{field}" in path.read_text(), (
            f"{name} :consumed-by: names {relpath}, which does not reference "
            f"capabilities.{field}"
        )


@pytest.mark.parametrize("field", CAPABILITY_FIELDS)
def test_status_is_a_known_value(field: str) -> None:
    name, _ = _protocol_for(field)
    status = _fields(field)["status"].strip()
    for tier in capability_seams.status_tiers(status):
        assert tier in VALID_STATUSES, f"{name} :status: entry {tier!r} (of {status!r}) is unknown"


def test_no_fallback_reaches_cardiac_code_at_all() -> None:
    """No capability fallback may reach cardiac code, gated or otherwise."""
    source = Path(compatibility.__file__).read_text()
    tree = ast.parse(source)
    offenders = []
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        # Look at import statements, not at the function's text: matching raw
        # source cannot tell an import from a docstring that merely names the
        # package, and a guard that forces documentation to avoid a word is
        # measuring the wrong thing.
        for child in ast.walk(node):
            if isinstance(child, ast.ImportFrom) and (child.module or "").startswith(
                "omnidriver.cardiacfoam"
            ):
                offenders.append(node.name)
                break
            if isinstance(child, ast.Import) and any(
                alias.name.startswith("omnidriver.cardiacfoam") for alias in child.names
            ):
                offenders.append(node.name)
                break

    assert offenders == [], (
        f"fallbacks reaching cardiac code: {sorted(set(offenders))}. Core "
        "imports no cardiac module any more; a fallback that needs one is a "
        "hook the plugin should implement."
    )


def test_architecture_seam_table_is_up_to_date() -> None:
    result = subprocess.run(
        [sys.executable, str(GENERATOR), "--check"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_every_probed_hook_is_declared_somewhere() -> None:
    """A hook an adapter probes must be findable in the public contract."""
    source = Path(plugin_capabilities.__file__).read_text()
    probed = set(re.findall(r'getattr\(\s*self\.plugin,\s*"([a-z_]+)"', source))
    undeclared = sorted(probed - _plugin_members())
    assert not undeclared, (
        "adapters probe hooks that no plugin protocol declares: "
        f"{undeclared}. Add them to SolverPluginOptionalHooks."
    )


def test_every_seam_declares_a_known_tier():
    """:status: is the single declaration of a member's enforcement tier."""
    from omnidriver.core import capability_seams

    seams = capability_seams.collect_seams()
    unknown = [
        (seam.field, seam.status)
        for seam in seams
        if any(
            tier not in capability_seams.TIERS
            for tier in capability_seams.status_tiers(seam.status)
        )
    ]
    assert unknown == [], (
        "capability seams declare a :status: outside the tier vocabulary "
        f"{sorted(capability_seams.TIERS)}: {unknown}"
    )


def test_get_rendered_formats_is_optional_refusing_not_neutral():
    """`get_rendered_formats` declares `:fallback: none`, so its tier must be optional-refusing, not optional-neutral."""
    from omnidriver.core import capability_seams

    tiers = capability_seams.members_by_tier()
    assert "get_rendered_formats" in tiers["optional-refusing"]
    assert "get_rendered_formats" not in tiers["optional-neutral"]


def test_validate_tiers_rejects_an_unknown_status():
    from omnidriver.core import capability_seams

    class _Seam:
        field = "made_up"
        status = "sort-of-optional"

    problems = capability_seams.validate_tiers([_Seam()])
    assert len(problems) == 1
    assert "made_up" in problems[0]
    assert "sort-of-optional" in problems[0]


def test_config_value_is_a_real_capability():
    """`plugin_interface` documents ConfigValueCapability; it must exist."""
    from omnidriver.core import plugin_capabilities

    assert hasattr(plugin_capabilities, "ConfigValueCapability")
    assert "config_value" in plugin_capabilities.PluginCapabilities.__annotations__


def test_dict_key_scanning_is_overridable():
    """A fallback no adapter can replace is not a seam."""
    from omnidriver.core import plugin_capabilities

    assert hasattr(plugin_capabilities, "DictKeyScannerCapability")
    assert "dict_key_scanner" in plugin_capabilities.PluginCapabilities.__annotations__
