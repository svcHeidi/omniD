from __future__ import annotations

import typing
import unittest

from omnidriver.dict_entries import DictEntry, Phase

VALID_PHASES = {"anatomy", "physics", "stimulus", "solver"}


class TestDictEntryStructuredConstraints(unittest.TestCase):
    """DictEntry exposes four structured-constraint fields so that
    constraints can be expressed in a form the validator can evaluate.

    The fields are additive (P8 additive-only policy): every existing
    DictEntry must construct unchanged with empty defaults.
    """

    def _build_entry(self, **overrides) -> "DictEntry":
        defaults = {
            "driver_path": "test.path",
            "description": "fixture",
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

    def test_applicable_when_accepts_value_predicate(self) -> None:
        entry = self._build_entry(
            applicable_when={"myocardiumSolver": "monodomainSolver"},
        )
        self.assertEqual(
            entry.applicable_when, {"myocardiumSolver": "monodomainSolver"},
        )

    def test_applicable_when_accepts_value_list_predicate(self) -> None:
        """Some constraints target multiple legal values
        (e.g. 'manufactured ionic models X, Y, Z')."""
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

    def test_entry_remains_frozen(self) -> None:
        """The additive fields must not loosen the existing
        immutability guarantee on DictEntry."""
        import dataclasses
        entry = self._build_entry()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            entry.applicable_when = {"x": "y"}  # type: ignore[misc]


def test_dict_entry_has_phases_field_accepting_a_frozenset():
    entry = DictEntry(
        driver_path="foo",
        description="x",
        source_refs=("bar",),
        phases=frozenset({"physics"}),
    )
    assert entry.phases == frozenset({"physics"})


def test_dict_entry_phases_supports_multi_phase_ownership():
    entry = DictEntry(
        driver_path="nRegions",
        description="number of regions",
        source_refs=("bar",),
        phases=frozenset({"anatomy", "solver"}),
    )
    assert entry.phases == frozenset({"anatomy", "solver"})


def test_dict_entry_phases_default_is_empty_frozenset():
    entry = DictEntry(driver_path="foo", description="x", source_refs=("bar",))
    assert entry.phases == frozenset()


def test_phase_literal_values():
    args = typing.get_args(Phase)
    assert set(args) == VALID_PHASES
