"""Q11 (plan §5g, owner 2026-09-26): the native pseudo-ECG case's
``anisotropic`` must validate clean against the real, checked-in
``constant/electroProperties``.

The owner's rule -- "get the physics right":
``ecgDomains.<name>.verificationModel.anisotropic`` is ``yes`` exactly when
the tissue verifier (``$ELECTRO_MODEL_COEFFS.verificationModel.type``) is
``manufacturedAnisotropicMonodomainVerifier``. The native
``manufacturedSolutions/monodomainPseudoECG`` case used the anisotropic
tissue verifier with ``anisotropic no`` (native ``7ae47527c``); the native
fix (this migration's Part A) sets it to ``yes``. This test reads the real
file from the native tree -- supplied only through
``OMNIDRIVER_NATIVE_TUTORIALS``, never discovered -- and proves
``_evaluate_ecg_anisotropic_consistency``/``CardiacFoamPlugin
.validate_run_semantics`` report no mismatch against it. A fixture cannot
settle this; only the real, checked-in case can.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.native

_PSEUDO_ECG_RELPATH = "manufacturedSolutions/monodomainPseudoECG"


def _native_tutorials_root() -> Path:
    value = os.environ.get("OMNIDRIVER_NATIVE_TUTORIALS")
    if not value:
        pytest.fail(
            "OMNIDRIVER_NATIVE_TUTORIALS is not set. A test marked "
            "@pytest.mark.native needs the native cardiacFOAM tutorials tree "
            "supplied explicitly via that environment variable -- it is never "
            "discovered. Run e.g.:\n"
            "  OMNIDRIVER_NATIVE_TUTORIALS=/path/to/tutorials "
            "pytest -m native"
        )
    root = Path(value)
    if not root.is_dir():
        pytest.fail(f"OMNIDRIVER_NATIVE_TUTORIALS={value!r} is not a directory")
    return root


def _real_electro_properties_path() -> Path:
    root = _native_tutorials_root()
    path = root / _PSEUDO_ECG_RELPATH / "constant" / "electroProperties"
    assert path.is_file(), f"fixture case missing: {path}"
    return path


def _context_from_electro_properties(path: Path) -> dict:
    """Build a real ``{slot_key: value}`` context from the real, checked-in
    file, the same way ``run_document_config.build_config`` builds one for
    a plan/validate pass: parse (round-trip catalog), resolve
    selectors+overrides, then fill in each applicable entry's default where
    the file did not override it."""
    from omnidriver.cardiacfoam.dict_builder import (
        parse_electro_properties, resolve_context, select_applicable_entries,
    )
    from omnidriver.core.specs.validation import slot_key
    from omnidriver.openfoam.dict_builder import populate_values

    parsed = parse_electro_properties(path)
    context = resolve_context(parsed["selectors"], overrides=parsed.get("overrides") or None)
    applicable = select_applicable_entries(context)
    populated = populate_values(applicable, context)
    result = dict(context)
    for entry in applicable:
        key = slot_key(entry.driver_path)
        if entry.dynamic_path and key not in context:
            continue
        if key in populated:
            result[key] = populated[key]
    return result


def test_native_pseudo_ecg_tissue_verifier_is_anisotropic():
    """Confirms the fact this test's premise depends on, from the real file:
    the case's tissue verifier is manufacturedAnisotropicMonodomainVerifier.
    If the native case ever stops using it, this test's scope no longer
    applies and should be revisited, not silently passed."""
    context = _context_from_electro_properties(_real_electro_properties_path())
    assert context.get("verificationModel.type") == "manufacturedAnisotropicMonodomainVerifier"


def test_native_pseudo_ecg_anisotropic_validates_clean():
    from omnidriver.cardiacfoam.validation import _evaluate_ecg_anisotropic_consistency

    context = _context_from_electro_properties(_real_electro_properties_path())
    errors = _evaluate_ecg_anisotropic_consistency(context)
    assert errors == [], [e.message for e in errors]


def test_native_pseudo_ecg_validates_clean_through_the_plugin():
    from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin

    context = _context_from_electro_properties(_real_electro_properties_path())
    diagnostics = CardiacFoamPlugin().validate_run_semantics(context)
    anisotropic_diagnostics = [
        d for d in diagnostics if d.field == "ecgDomains.ECG.verificationModel.anisotropic"
    ]
    assert anisotropic_diagnostics == [], [d.message for d in anisotropic_diagnostics]
