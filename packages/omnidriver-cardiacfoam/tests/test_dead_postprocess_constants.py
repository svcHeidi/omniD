import importlib

import pytest

_MODULES = [
    # restitution_curves's defaults module was deleted 2026-09-25: the
    # tutorial migrated onto a tutorial record (docs/superpowers/specs/
    # 2026-09-24-tutorials-are-pointers-design.md), which has no defaults
    # module to carry these dead constants at all.
    # manufactured_monodomain_pseudo_ecg's defaults module was deleted
    # 2026-09-27: the tutorial migrated onto a tutorial record
    # (records/manufactured_monodomain_pseudo_ecg.py, tutorials-are-pointers
    # plan §5c, step 5.4b-P), for the same reason as restitution_curves
    # above.
    # cable_1d_cv_convergence's and cable_1d_restitution's defaults modules
    # were deleted 2026-09-27: both tutorials migrated onto tutorial records
    # (records/cable_1d_cv_convergence.py, records/cable_1d_restitution.py,
    # tutorials-are-pointers plan §5e, steps 5.3/5.2), for the same reason
    # as restitution_curves above.
    "omnidriver.cardiacfoam.tutorials.defaults.manufactured_purkinje_graph",
    "omnidriver.cardiacfoam.tutorials.defaults.manufactured_monodomain_total_lagrangian_em",
]
_DEAD_NAMES = (
    "POSTPROCESS_SCRIPT_RELPATH",
    "POSTPROCESS_FUNCTION_NAME",
    "CV_EXTRACT_SCRIPT_RELPATH",
    "TABLE_SUMMARY_RELPATH",
)


@pytest.mark.parametrize("module_name", _MODULES)
def test_defaults_module_does_not_export_dead_postprocess_constants(module_name):
    module = importlib.import_module(module_name)
    for name in _DEAD_NAMES:
        assert not hasattr(module, name), f"{module_name} still defines {name}"
        assert name not in getattr(module, "__all__", ()), (
            f"{module_name}.__all__ still lists {name}"
        )
