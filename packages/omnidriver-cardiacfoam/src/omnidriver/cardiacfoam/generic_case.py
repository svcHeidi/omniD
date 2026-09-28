"""cardiacFoam's own answer to the core generic case factory: supplies the two
cardiac marker dict files (``electroProperties``/``physicsProperties``) and
the plugin's mutation callback core needs to recognize such a folder.
"""

from omnidriver.core.runtime.generic_case import make_spec as _core_make_spec
from omnidriver.cardiacfoam.generic_case_mutation import apply_case_mutation


#: The dictionary files cardiacFoam's generic case factory addresses.
#: Insertion order matters: core treats the first entry as the *primary* file
#: marking a folder as belonging to this solver, and ``electroProperties`` is
#: that marker.
CARDIAC_DICT_FILE_RELPATHS = {
    "electro": "constant/electroProperties",
    "physics": "constant/physicsProperties",
}


def make_spec(**kwargs):
    """cardiacFOAM's entry point for core's generic case factory: supplies this
    plugin's driver context, mutation callback and marker dict files by
    default. A caller may still pass its own ``driver_context``.
    """
    if kwargs.get("driver_context") is None:
        from omnidriver.cardiacfoam.own_context import own_driver_context

        kwargs["driver_context"] = own_driver_context()
    kwargs.setdefault("_apply_case_mutation", apply_case_mutation)
    kwargs.setdefault("dict_file_relpaths", dict(CARDIAC_DICT_FILE_RELPATHS))
    return _core_make_spec(**kwargs)


def make_generic_case_spec(**kwargs):
    return make_spec(**kwargs)

__all__ = ["make_spec", "make_generic_case_spec"]
