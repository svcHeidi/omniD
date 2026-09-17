"""Any value the native utilities actually read is movable.

The catalog is guidance, not permission: it enumerates what the C++ reads,
so a path outside it names a key no utility consumes. Resolution comes from
the declaring document, so no per-path routing table has to be maintained.
"""

import pytest

from omnidriver.cardiaccore.catalogs.inputs import CATALOG
from omnidriver.cardiaccore.workflows.overrides import (
    resolve_override_target,
    validate_input_overrides,
)


def test_every_declared_entry_resolves_to_a_native_location():
    """No declared key is unreachable; that was the freeze this removes."""
    for entry in CATALOG.entries:
        path = entry.driver_path.replace("<ventKey>", "lv")
        target = resolve_override_target(path)
        assert target.file_relpath.startswith("system/")
        assert target.key


@pytest.mark.parametrize("vent", ["lv", "rv"])
def test_the_ventricle_segment_resolves_from_the_path(vent):
    target = resolve_override_target(f"$PURKINJE_TREE.{vent}.N_it")
    assert target.file_relpath == "system/generatePurkinjeTreeDict"
    assert target.scope == (vent,)
    assert target.key == "N_it"


def test_a_nested_block_resolves_to_the_full_scope():
    target = resolve_override_target("$PURKINJE_TREE.lv.extension.depthMin")
    assert target.scope == ("lv", "extension")
    assert target.key == "depthMin"


def test_a_top_level_key_resolves_with_no_scope():
    target = resolve_override_target("$CARDIAC_CONDUCTIVITY.df")
    assert target.file_relpath == "system/setCardiacConductivityDict"
    assert target.scope == ()
    assert target.key == "df"


def test_the_tree_parameters_are_movable():
    """These were declared-only; the agent may now set them."""
    validated = validate_input_overrides({
        "$PURKINJE_TREE.lv.N_it": 36,
        "$PURKINJE_TREE.lv.seed": [0.011, 0.019, -0.002],
        "$PURKINJE_TREE.lv.extension.depthMin": 0.15,
        "$PURKINJE_TREE.growthModel": "surfaceFollow",
        "$PURKINJE_MORPHOMETRY.subendocardialWeight": 0.4,
    })
    assert validated["$PURKINJE_TREE.lv.N_it"] == 36
    assert validated["$PURKINJE_TREE.lv.seed"] == [0.011, 0.019, -0.002]


def test_a_vector_may_also_be_given_the_way_a_dictionary_spells_it():
    validated = validate_input_overrides({"$PURKINJE_TREE.hisBundleSeed": "(0.014 0.022 -0.007)"})
    assert validated["$PURKINJE_TREE.hisBundleSeed"] == "(0.014 0.022 -0.007)"


def test_a_key_no_utility_reads_is_still_refused():
    """grooveMode is absent from the catalog because native never reads it.

    Groove detection is unconditional in setCardiacAnatomy, so writing this
    key would be silently ignored rather than rejected by the solver. That is
    the one thing the catalog can tell an agent that the solver cannot.
    """
    with pytest.raises(ValueError, match="not declared"):
        validate_input_overrides({"$CARDIAC_ANATOMY.grooveMode": "manual"})


def test_an_unknown_dictionary_is_refused_as_unresolvable():
    with pytest.raises(ValueError, match="no declaring document"):
        validate_input_overrides({"$NOT_A_DICTIONARY.someKey": 1})


def test_declared_types_and_enums_still_guide():
    with pytest.raises(ValueError, match="enum"):
        validate_input_overrides({"$PURKINJE_TREE.lv.terminalModel": "diffusive"})
    with pytest.raises(TypeError):
        validate_input_overrides({"$PURKINJE_TREE.lv.N_it": 3.5})
    with pytest.raises(TypeError):
        validate_input_overrides({"$PURKINJE_TREE.lv.seed": [0.0, 1.0]})
