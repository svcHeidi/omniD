"""Phase 3 Task 9, "the `describe` seam" -- the unmet second payoff.

`core.introspection._write_surface` (Phase 2 Task 13) matched supplied keys
against catalog qualified ids, but no real invocation in this codebase ever
supplies catalog-shaped keys: the CLI hands it raw tutorial-factory kwargs
(`ionic_model`, `electro_property_overrides`). Task 9 closed that gap by
reusing a factory tutorial's own `plan_case`, run for real against a
disposable staged clone of its case (never the real `case_root`), and
reading the qualified ids/values/sources/operations off the committed
`CaseWriteRecord` -- see `core.introspection._resolve_proposed_changes`.

Three things used to be proven here, against real cardiacfoam adapter code
(this package is where `plan_case` and the real catalog live -- the
core-level fake-plugin tests in
`packages/omnidriver/tests/core/test_describe_write_surface.py` cannot
exercise any of this). All three have since been deleted, each alongside the
factory it exercised, once that factory migrated onto a tutorial record
whose `describe` path this module's `_write_surface` helper does not drive
at all (a record's own preview goes through `record_execution`, not raw
factory kwargs):

1. Proof 1 (a factory tutorial's real `plan_case`, driven by raw factory
   kwargs exactly as the CLI would supply them, produces non-empty,
   correctly-valued `proposed_changes` against a provably-untouched on-disk
   fixture case) exercised `single_cell`'s own `plan_case` -- deleted
   2026-09-27 alongside that factory (tutorials-are-pointers plan, step
   5.1).
2. Proof 2 (a whole-dict removal target -- `manufactured_monodomain_
   pseudo_ecg`'s conditional `ecgDomains` removal, which is not a
   `ParameterAssignment` at all (Task 6/7's own finding: "not a
   `ParameterAssignment`, a whole sub-dictionary has no single `key_path`")
   and so surfaces in `expected_effects` rather than in the structured
   `proposed_changes` list) exercised `manufactured_monodomain_pseudo_ecg`'s
   own `plan_case` -- deleted 2026-09-27 alongside that factory (step
   5.4b-P): the native case's `ecgDomains` is never conditionally removed by
   the migrated record (owner Q11), so no production code builds this kind
   of target any more.
3. Proof 3 (a `ParameterAssignment(operation="remove")` from
   `resolve_electro_property_removal` appearing in `proposed_changes` with
   `value: None`) was deleted 2026-09-26 with that function
   (tutorials-are-pointers 5.4a): its one caller, `manufactured_bath_
   bidomain`, migrated onto a tutorial record whose studies replace the
   bath patch maps whole (owner Q4).

No factory tutorial remains that this module's `_write_surface`/raw-kwargs
path can drive, so nothing takes these proofs' place here.
"""
