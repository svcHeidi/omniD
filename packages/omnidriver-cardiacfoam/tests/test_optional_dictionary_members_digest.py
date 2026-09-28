"""Empty dictionary stubs on the OpenFOAM layer change no cardiac stack's identity."""
from __future__ import annotations

from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin
from omnidriver.core.contracts.dictionary_catalog import DictionaryCatalog
from omnidriver.core.plugin_interface import driver_context
from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin


class _EnvironmentWithStubs(OpenFOAMEnvironmentPlugin):
    """The OpenFOAM layer carrying empty dictionary stubs."""

    def get_dict_entries(self):
        return ()

    def get_dictionary_catalog(self):
        return DictionaryCatalog({})

    def get_dict_groups(self):
        return {}

    def get_tutorial_displays(self):
        return ()


def test_the_cardiac_stack_identity_is_unchanged_by_deleting_the_stubs():
    with_stubs = driver_context(_EnvironmentWithStubs(), CardiacFoamPlugin(), source="test").identity
    without = driver_context(OpenFOAMEnvironmentPlugin(), CardiacFoamPlugin(), source="test").identity
    assert without.to_json() == with_stubs.to_json()
