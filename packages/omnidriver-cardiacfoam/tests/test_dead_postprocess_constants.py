import importlib

import pytest

_MODULES = [
    # restitution_curves's defaults module was deleted 2026-09-25: the
    # tutorial migrated onto a tutorial record (docs/superpowers/specs/
    # 2026-09-24-tutorials-are-pointers-design.md), which has no defaults
    # module to carry these dead constants at all.
    "omnidriver.cardiacfoam.tutorials.defaults.manufactured_eikonal_ecg",
    "omnidriver.cardiacfoam.tutorials.defaults.manufactured_bath_bidomain",
    "omnidriver.cardiacfoam.tutorials.defaults.manufactured_monodomain_pseudo_ecg",
    "omnidriver.cardiacfoam.tutorials.defaults.cable_1d_cv_convergence",
    "omnidriver.cardiacfoam.tutorials.defaults.cable_1d_restitution",
    "omnidriver.cardiacfoam.tutorials.defaults.manufactured_purkinje_graph",
    "omnidriver.cardiacfoam.tutorials.defaults.manufactured_monodomain_total_lagrangian_em",
    "omnidriver.cardiacfoam.tutorials.defaults.single_cell",
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
