from __future__ import annotations

import unittest

from omnidriver.core.contracts.dictionary import DictEntry


class TestDictEntryStructuredConstraints(unittest.TestCase):
    """DictEntry exposes five structured-constraint fields so that constraints can be expressed in a form the validator can evaluate."""

    def _build_entry(self, **overrides) -> "DictEntry":
        defaults = {
            "driver_path": "test.path",
            "description": "fixture",
            "value_kind": "word",
            "source_refs": ("ref.C",),
        }
        defaults.update(overrides)
        return DictEntry(**defaults)

    def test_applicable_when_defaults_empty(self) -> None:
        entry = self._build_entry()
        self.assertEqual(entry.applicable_when, {})

    def test_forbidden_when_defaults_empty(self) -> None:
        entry = self._build_entry()
        self.assertEqual(entry.forbidden_when, {})

    def test_required_when_defaults_empty(self) -> None:
        entry = self._build_entry()
        self.assertEqual(entry.required_when, {})

    def test_mutually_exclusive_with_defaults_empty(self) -> None:
        entry = self._build_entry()
        self.assertEqual(entry.mutually_exclusive_with, ())

    def test_co_required_with_defaults_empty(self) -> None:
        entry = self._build_entry()
        self.assertEqual(entry.co_required_with, ())

    def test_required_one_of_defaults_empty_and_accepts_path_tuple(self) -> None:
        self.assertEqual(self._build_entry().required_one_of, ())
        entry = self._build_entry(required_one_of=("stimulusLocationMaxList",))
        self.assertEqual(entry.required_one_of, ("stimulusLocationMaxList",))

    def test_numeric_bounds_default_to_none_and_need_a_numeric_kind(self) -> None:
        entry = self._build_entry()
        self.assertEqual((entry.minimum, entry.exclusive_minimum), (None, None))
        self.assertEqual(self._build_entry(value_kind="scalar", exclusive_minimum=0).exclusive_minimum, 0)
        with self.assertRaises(ValueError):
            self._build_entry(value_kind="word", minimum=0)

    def test_applicable_when_accepts_value_predicate(self) -> None:
        entry = self._build_entry(
            applicable_when={"myocardiumSolver": "monodomainSolver"},
        )
        self.assertEqual(
            entry.applicable_when, {"myocardiumSolver": "monodomainSolver"},
        )

    def test_applicable_when_accepts_value_list_predicate(self) -> None:
        """Some constraints target multiple legal values (e.g. 'manufactured ionic models X, Y, Z')."""
        entry = self._build_entry(
            applicable_when={
                "ionicModel": (
                    "monodomainFDAManufactured",
                    "bidomainFDAManufactured",
                    "bathBidomainFDAManufactured",
                ),
            },
        )
        self.assertEqual(len(entry.applicable_when["ionicModel"]), 3)

    def test_forbidden_when_accepts_value_predicate(self) -> None:
        entry = self._build_entry(
            forbidden_when={"myocardiumSolver": "eikonalSolver"},
        )
        self.assertEqual(entry.forbidden_when["myocardiumSolver"], "eikonalSolver")

    def test_required_when_accepts_value_predicate(self) -> None:
        entry = self._build_entry(
            required_when={"myocardiumSolver": "singleCellSolver"},
        )
        self.assertEqual(
            entry.required_when["myocardiumSolver"], "singleCellSolver",
        )

    def test_mutually_exclusive_with_accepts_path_tuple(self) -> None:
        entry = self._build_entry(
            mutually_exclusive_with=("stimulusDurationList",),
        )
        self.assertEqual(entry.mutually_exclusive_with, ("stimulusDurationList",))

    def test_co_required_with_accepts_path_tuple(self) -> None:
        entry = self._build_entry(
            co_required_with=("stimulusDurationList",),
        )
        self.assertEqual(entry.co_required_with, ("stimulusDurationList",))


    def test_entry_remains_frozen(self) -> None:
        """The additive fields must not loosen the existing immutability guarantee on DictEntry."""
        import dataclasses
        entry = self._build_entry()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            entry.applicable_when = {"x": "y"}  # type: ignore[misc]


def test_a_bound_judges_plain_numbers_only():
    from types import SimpleNamespace

    from omnidriver.core.contracts.dictionary import bound_violations, numeric_bounds

    bounds = numeric_bounds(DictEntry(driver_path="chi", description="x", value_kind="scalar", exclusive_minimum=0))
    assert bound_violations(bounds, -1.0) == {"exclusive_minimum": 0}
    assert bound_violations(bounds, SimpleNamespace(value=-1.0, dimensions=(0, -1, 0, 0, 0, 0, 0))) == {}


def test_an_entry_states_minimum_exclusive_minimum_and_maximum_and_their_reasons_are_formatted_from_the_violations():
    from omnidriver.core.contracts.dictionary import bound_reasons, bound_violations, numeric_bounds

    entry = DictEntry(driver_path="p", description="x", value_kind="scalar", minimum=0, maximum=1)
    assert numeric_bounds(entry) == {"minimum": 0, "maximum": 1}
    assert bound_violations(numeric_bounds(entry), 2) == {"maximum": 1}
    assert bound_reasons({"maximum": 1, "minimum": 0}) == ("must be at most 1", "must be at least 0")


def test_dict_entry_has_phases_field_accepting_a_frozenset():
    entry = DictEntry(
        driver_path="foo",
        description="x",
        value_kind="word",
        source_refs=("bar",),
        phases=frozenset({"physics"}),
    )
    assert entry.phases == frozenset({"physics"})


def test_dict_entry_phases_supports_multi_phase_ownership():
    entry = DictEntry(
        driver_path="nRegions",
        description="number of regions",
        value_kind="integer",
        source_refs=("bar",),
        phases=frozenset({"anatomy", "solver"}),
    )
    assert entry.phases == frozenset({"anatomy", "solver"})


def test_dict_entry_phases_default_is_empty_frozenset():
    entry = DictEntry(
        driver_path="foo", description="x", value_kind="word", source_refs=("bar",),
    )
    assert entry.phases == frozenset()


def test_core_exports_no_phase_vocabulary():
    """Core's dictionary contract exports no ``Phase`` literal spelling cardiacFoam's four editing phases."""
    import omnidriver.core.contracts.dictionary as dictionary

    assert not hasattr(dictionary, "Phase")


def test_entries_and_catalog_agree(driver_context_for_installed_plugins):
    """The flat entries and the catalogue must not give two answers."""
    for context in driver_context_for_installed_plugins:
        flat = {entry.driver_path for entry in context.stack.call("get_dict_entries")}
        catalogued = {entry.driver_path for entry in context.stack.call("get_dictionary_catalog").entries}
        # StackIdentity has no singular id -- name every provider in the
        # composed stack instead.
        provider_ids = [p.id for p in context.identity.providers]
        assert flat == catalogued, (
            f"{provider_ids}: entries() and catalog() disagree; "
            f"missing from entries()={sorted(catalogued - flat)} "
            f"missing from catalog()={sorted(flat - catalogued)}"
        )
