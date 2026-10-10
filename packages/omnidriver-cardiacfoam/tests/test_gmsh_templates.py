"""A strict plan refuses a gmsh step whose ``-setnumber`` names a value its template does not declare.

The two templates under ``fixtures/gmsh_templates`` are the monodomainPseudoECG tet box template verbatim:
``native_main_box.geo.template`` from native main (277dfeb19, ``lc = __LC__;``) and
``omnid_branch_box.geo.template`` from the native ``omnid/insulated-wall`` branch (``DefineConstant``).
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin
from omnidriver.cardiacfoam.gmsh_templates import declared_numbers, undeclared_setnumber_diagnostics
from omnidriver.core.plugin_interface import driver_context
from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin

FIXTURES = Path(__file__).parent / "fixtures" / "gmsh_templates"
TEMPLATE = "setup/box.geo.template"


def _dag(*args: str) -> dict:
    return {"steps": [{"id": "gmsh", "command": "gmsh", "args": ["-3", TEMPLATE, "-o", "box.msh", *args], "cwd": "."}]}


def _case(tmp_path: Path, fixture: str) -> Path:
    case = tmp_path / "case"
    (case / "setup").mkdir(parents=True)
    shutil.copy(FIXTURES / fixture, case / TEMPLATE)
    return case


def test_the_branch_template_declares_lc_and_native_main_does_not():
    assert declared_numbers((FIXTURES / "omnid_branch_box.geo.template").read_text()) == {"lc"}
    assert declared_numbers((FIXTURES / "native_main_box.geo.template").read_text()) == frozenset()


def test_a_name_option_replaces_the_variable_as_the_key_and_comments_declare_nothing():
    text = (
        '// DefineConstant[ ghost = { 1, Name "ghost" } ];\n'
        'DefineConstant[ lc = { 0.1, Name "Parameters/lc" }, n = 3 ];\n'
    )
    assert declared_numbers(text) == {"Parameters/lc", "n"}


def test_a_setnumber_the_native_main_template_does_not_declare_is_refused_by_name(tmp_path):
    found = undeclared_setnumber_diagnostics(_case(tmp_path, "native_main_box.geo.template"), _dag("-setnumber", "lc", "0.05"))
    assert [(item.level, item.code) for item in found] == [("error", "gmsh_setnumber_not_declared")]
    assert found[0].detail["name"] == "lc" and found[0].detail["declared"] == []
    assert "-setnumber lc" in found[0].message


def test_a_setnumber_the_branch_template_declares_passes(tmp_path):
    case = _case(tmp_path, "omnid_branch_box.geo.template")
    assert undeclared_setnumber_diagnostics(case, _dag("-setnumber", "lc", "0.05")) == ()
    assert [item.detail["name"] for item in undeclared_setnumber_diagnostics(case, _dag("-setnumber", "h", "1"))] == ["h"]


def test_a_gmsh_step_without_setnumber_or_a_missing_template_is_not_judged(tmp_path):
    case = _case(tmp_path, "native_main_box.geo.template")
    assert undeclared_setnumber_diagnostics(case, _dag()) == ()
    assert undeclared_setnumber_diagnostics(tmp_path / "empty", _dag("-setnumber", "lc", "1")) == ()
    assert undeclared_setnumber_diagnostics(case, None) == ()


@pytest.mark.parametrize(("fixture", "refused"), [
    ("native_main_box.geo.template", True), ("omnid_branch_box.geo.template", False),
])
def test_the_plugin_contributes_the_refusal_to_a_strict_plan(tmp_path, fixture, refused):
    case = _case(tmp_path, fixture)
    context = driver_context(OpenFOAMEnvironmentPlugin(), CardiacFoamPlugin(), source="test:gmsh_templates")
    plan = context.stack.call(
        "get_plan_diagnostics", case, workflow_dag=_dag("-setnumber", "lc", "0.05"),
        env={}, scratch_root=tmp_path / "scratch", driver_context=context,
    )
    assert any(item.code == "gmsh_setnumber_not_declared" for item in plan) is refused
