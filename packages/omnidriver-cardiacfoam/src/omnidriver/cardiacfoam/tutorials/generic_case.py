"""Compatibility wrapper for the core generic case factory.

The generic case-folder execution path is now owned by
``omnidriver.core.runtime.generic_case`` so the main driver remains
solver-agnostic. This module stays in place only to preserve legacy imports.
"""

from omnidriver.core.runtime.generic_case import make_spec as _core_make_spec
from omnidriver.cardiacfoam.generic_case_mutation import apply_case_mutation


#: The dictionary files cardiacFoam's generic case factory has always
#: addressed. Insertion order matters: core treats the first entry as the
#: *primary* file whose presence marks a folder as belonging to this solver
#: rather than being generic, and ``electroProperties`` has always been that
#: marker. This pair used to live in core, as
#: ``compatibility.legacy_generic_case_dict_file_relpaths`` -- core defaulting
#: to two cardiac filenames for every caller. Same values, now declared by the
#: plugin that means them.
CARDIAC_DICT_FILE_RELPATHS = {
    "electro": "constant/electroProperties",
    "physics": "constant/physicsProperties",
}


def make_spec(**kwargs):
    kwargs.setdefault("_apply_case_mutation", apply_case_mutation)
    kwargs.setdefault("dict_file_relpaths", dict(CARDIAC_DICT_FILE_RELPATHS))
    return _core_make_spec(**kwargs)


def make_generic_case_spec(**kwargs):
    return make_spec(**kwargs)

__all__ = ["make_spec", "make_generic_case_spec"]
