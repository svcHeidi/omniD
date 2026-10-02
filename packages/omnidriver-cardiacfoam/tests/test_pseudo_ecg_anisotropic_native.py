"""The native pseudo-ECG case's ``anisotropic`` validates clean against its real, checked-in electroProperties.

``ecgDomains.<name>.verificationModel.anisotropic`` is ``yes`` exactly when the tissue verifier is
``manufacturedAnisotropicMonodomainVerifier``; only the real case (``OMNIDRIVER_NATIVE_TUTORIALS``) can settle it."""
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
    """Build the ``{slot_key: value}`` context from a real read."""
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
    """This module's premise; if the native case stops using this verifier, revisit rather than pass."""
    context = _context_from_electro_properties(_real_electro_properties_path())
    assert context.get("verificationModel.type") == "manufacturedAnisotropicMonodomainVerifier"


def test_native_pseudo_ecg_anisotropic_validates_clean():
    from omnidriver.cardiacfoam.validation import _evaluate_ecg_anisotropic_consistency

    context = _context_from_electro_properties(_real_electro_properties_path())
    errors = _evaluate_ecg_anisotropic_consistency(context)
    assert errors == [], [e.message for e in errors]


def test_native_pseudo_ecg_validates_clean_across_fields():
    from omnidriver.cardiacfoam.validation import cross_field_diagnostics

    context = _context_from_electro_properties(_real_electro_properties_path())
    diagnostics = cross_field_diagnostics(context)
    anisotropic_diagnostics = [
        d for d in diagnostics if d.field == "ecgDomains.ECG.verificationModel.anisotropic"
    ]
    assert anisotropic_diagnostics == [], [d.message for d in anisotropic_diagnostics]
