import importlib

import pytest

_MODULES = [
    "omnidriver.cardiac.tutorials.defaults.restitution_curves",
    "omnidriver.cardiac.tutorials.defaults.manufactured_eikonal_ecg",
    "omnidriver.cardiac.tutorials.defaults.manufactured_bath_bidomain",
    "omnidriver.cardiac.tutorials.defaults.manufactured_monodomain_pseudo_ecg",
    "omnidriver.cardiac.tutorials.defaults.cable_1d_cv_convergence",
    "omnidriver.cardiac.tutorials.defaults.cable_1d_restitution",
    "omnidriver.cardiac.tutorials.defaults.manufactured_purkinje_graph",
    "omnidriver.cardiac.tutorials.defaults.manufactured_monodomain_total_lagrangian_em",
    "omnidriver.cardiac.tutorials.defaults.single_cell",
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
