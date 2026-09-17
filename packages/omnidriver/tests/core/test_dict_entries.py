from __future__ import annotations

import unittest

from omnidriver.dict_entries import DictEntry


class TestDictEntryStructuredConstraints(unittest.TestCase):
    """DictEntry exposes five structured-constraint fields so that
    constraints can be expressed in a form the validator can evaluate.

    Existing entries construct unchanged because each field has an empty
    default.
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

    def test_co_required_with_defaults_empty(self) -> None:
        entry = self._build_entry()
        self.assertEqual(entry.co_required_with, ())

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

    def test_co_required_with_accepts_path_tuple(self) -> None:
        entry = self._build_entry(
            co_required_with=("stimulusDurationList",),
        )
        self.assertEqual(entry.co_required_with, ("stimulusDurationList",))


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


def test_core_exports_no_phase_vocabulary():
    """``omnidriver.dict_entries`` exports no solver phase vocabulary."""
    import omnidriver.dict_entries as dict_entries

    assert not hasattr(dict_entries, "Phase")


class TestCoRequiredWithEvaluation(unittest.TestCase):
    """``co_required_with`` is the inverse of ``mutually_exclusive_with``:
    a declared group must be set as a whole or not at all.

    This guards behaviour, not a fixture: the validator has to stay silent
    when nothing in the group is set, stay silent when every member is set,
    and report once per missing sibling in between.
    """

    def _group(self) -> list["DictEntry"]:
        names = ("alpha", "beta", "gamma")
        return [
            DictEntry(
                driver_path=name,
                description="fixture",
                source_refs=("ref.C",),
                co_required_with=tuple(o for o in names if o != name),
            )
            for name in names
        ]

    def _errors(self, context: dict) -> list[str]:
        from omnidriver.core.specs.validation import _evaluate_structured
        return [e.message for e in _evaluate_structured(self._group(), context, ())]

    def test_no_error_when_the_whole_group_is_absent(self) -> None:
        self.assertEqual(self._errors({}), [])

    def test_no_error_when_the_whole_group_is_set(self) -> None:
        self.assertEqual(
            self._errors({"alpha": 1.0, "beta": 2.0, "gamma": 3.0}), [],
        )

    def test_one_error_per_missing_sibling_on_a_partial_group(self) -> None:
        errors = self._errors({"alpha": 1.0})
        self.assertEqual(len(errors), 2)
        self.assertIn("alpha requires beta to be set as well.", errors)
        self.assertIn("alpha requires gamma to be set as well.", errors)

    def test_each_set_member_reports_its_own_missing_sibling(self) -> None:
        errors = self._errors({"alpha": 1.0, "beta": 2.0})
        self.assertEqual(
            sorted(errors),
            [
                "alpha requires gamma to be set as well.",
                "beta requires gamma to be set as well.",
            ],
        )
