# Solver adapter lead: skeptical pre-Phase-2 audit

Date: 2026-09-22. Scope: cardiacFoam/cardiacCore adapter contracts, normalized addressing and validation, workflow inputs, and Phase 2 prerequisites. Role: Maintainer; builder evidence contract read for interpretation boundaries. No production code changed; no native solver execution performed. Findings concern the inspected working tree, not a promise that any scientific workflow is validated.

## Decision

The layers are broadly appropriate: Core owns orchestration and generic records; OpenFOAM owns language/runtime mechanics; each solver adapter owns readers, meanings, conditions, workflow choices and result interpretation. Both adapters already reuse `DictEntry`, `DictionaryCatalog`, `TutorialSpec`, utility manifests and the OpenFOAM provider stack. They are not yet behaviorally normalized. Approve the *direction* of one transactional write channel, but revise Phase 2 before executing it: transactions cannot repair ambiguous parameter identity, inaccurate workflow consumption or missing semantic validation.

Normalize the lifecycle and result contracts, not the solvers' scientific vocabulary or available workflows. A preprocessing adapter legitimately has no solver command, ionic model or samplable electrophysiology field. Missing support should be explicit, rather than an empty callable that resembles a successful check.

## Observed findings, ranked

### P1 A1 — Namespaced parameter identity is lost before provenance/validation

Committed code: `cardiaccore.workflows.run_config.build_config` flattens all values through Core `specs.validation.slot_key`. `make_human_purkinje_slab_spec` supplies no `active_input_paths`, so `read_input_values` reads the entire catalog. It records absent ordinary leaves as `None`; subsequent scar entries overwrite conductivity entries sharing the same suffix. Collision inventory from the live catalog:

- `fiberField`: `$CARDIAC_CONDUCTIVITY.fiberField`, `$CARDIAC_SCAR.fiberField`.
- `sheetField`: the same two documents.
- `severityField`: `$CARDIAC_SCAR.severityField`, `$PURKINJE_SCAR.severityField`.

**Reproduced:** minimal conductivity dictionary declares `fiberField originalFiber; sheetField originalSheet;`; slab request overrides conductivity fiber to `customFiber`. `build_config(spec)` returns `preprocessing.fiberField=None`, `sheetField=None`, and no diagnostics. Updating a dictionary value in its original key position does not move it after the later scar key in insertion order.

This is an existing committed defect in `build_config`, even though that file also contains unrelated uncommitted validator work. The new `_relevant_catalog_paths` WIP helper addresses a separate validation path; it does not alter `build_config`.

**Gate:** preserve a canonical identity containing provider/document/scope/key through request, write plan, effective readback, RunDocument, validation, sweep, and resume digest. At minimum bind each workflow to the documents it actually consumes and reject remaining flattened collisions. Never silently choose a winner. Test two documents with the same leaf and different values, including an absent optional document and requested override.

### P1 A2 — Dynamic paths accept a ventricle the native contract does not read

Committed code: `cardiaccore.workflows.overrides._template_for` substitutes any one concrete segment with `<ventKey>`, without validating against `catalogs.inputs.VENT_KEYS == ('lv', 'rv')`. `_check_value` accepts any nonempty string as a `vector3`; scalar validation admits nonfinite Python floats.

**Reproduced:** all three succeed in `validate_input_overrides(..., allowed_paths=PURKINJE_TREE_INPUT_PATHS)`:

```python
{'$PURKINJE_TREE.nonsense.N_it': 3}
{'$PURKINJE_TREE.lv.seed': 'not a vector'}
{'$CARDIAC_CONDUCTIVITY.df': float('nan')}
```

The first can create a dictionary block the declared native reader never consumes, defeating the module's stated protection against silent no-op overrides. This is a mechanical failure, independent of domain acceptance. NaN matters for Python callers and any permissive JSON parser; strict standard JSON does not represent it.

**Gate:** generic placeholder grammar plus adapter-provided allowed bindings, strict vector parsing/serialization in the OpenFOAM owner, finite numeric requirements where the native parameter contract requires them, and unknown bindings rejected before mutation. Phase 2 Task 4 must not simply move the five existing checks unchanged; Task 5 must enforce bindings as well as substitute text.

### P1 A3 — Mutation and workflow consumption are inconsistent

Committed code: `make_human_purkinje_slab_spec` uses `_apply_case` without `_reject_unstaged` or `active_input_paths`. `CardiacCorePlugin.get_override_schema` advertises all catalog entries for this workflow, including scar and tree dictionaries, although its DAG runs only conductivity, anatomy, slab and morphometry. The catalog's module documentation claims declared-only dictionaries cannot become workflow x values until listed in `active_input_paths`; the slab path violates that claim.

**Reproduced:** slab schema contains `$CARDIAC_SCAR.selection`; `validate_input_overrides({'$CARDIAC_SCAR.selection': 'scar.vtu'})` succeeds. The mutation layer may then fail on a missing file or write a file no selected stage consumes.

Also, the conductivity DAG consumes literal `0/fiber` and `0/sheet`, even when those catalog inputs are overridden to `customFiber`/other names. Utility manifests hardcode default coordinate inputs, whereas workflow factories accept a `CoordinatesConvention` and can use different paths. An explicit convention is not automatically loaded from the selected case by those factories.

**Observed versus inference:** hardcoded paths and accepted overrides are observed; whether each path produces an erroneous missing-input refusal or an incomplete resume digest depends on the orchestration route. Reproduce that route before editing Core.

**Gate:** resolve the selected workflow's inputs from the final effective dictionary configuration, including field-name overrides and coordinate convention, then use that single resolved set for staging, preflight, DAG edges and provenance. Test default and renamed field inputs with unchanged native behavior. Do not confuse a key known to a utility with one consumed by this selected workflow.

### P1 A4 — Plan-time cardiacCore validator remains unwired (pre-existing WIP is not a new regression)

`CardiacCorePlugin.validate_configuration` is committed as `del spec; return ()`, and `plugin.yaml` explicitly withholds `configuration_validator`. The dirty `workflows/run_config.py` has a new `validate_configuration(spec, plugin)` implementation, and the untracked `tests/test_validate_configuration.py` calls the still-empty plugin method.

**Executed:** `.venv/bin/python -m pytest packages/omnidriver-cardiaccore/tests/test_input_overrides.py packages/omnidriver-cardiaccore/tests/test_validate_configuration.py -q` → 15 passed, 1 failed. Failure is the WIP test `test_a_half_set_bidomain_pair_outside_active_input_paths_is_now_reported`: an intracellular-only pair yields no plan-time diagnostic. Do not describe this as a regression introduced by the audit, or as a failure of the committed test suite.

**Gate:** finish/review this WIP with its owner, wire the real hook and verify composed context construction. Validate the *effective* configuration after requested overrides, not only source files; preserve the generic-case bypass deliberately. Verify the public planning and run routes, not only the helper. The pair's native failure condition is documented in the catalog; this audit did not independently execute the native reader.

### P2 A5 — Descriptions and support evidence disagree

`CardiacCorePlugin.get_override_schema` says the tree dictionary is fixed while `PURKINJE_TREE_INPUT_PATHS` includes the tree catalog and tests explicitly permit its mutation. The schema is essentially a path list and the RunDocument config schema accepts arbitrary contents of `preprocessing`. `DictEntry` has source references, unit and typical-value fields but no structured evidence state/build scope; those claims survive largely in prose and named catalogs. cardiacFoam has source scanner drift tests in `tests/test_strict_planning.py`; no `scan_dict_reads`/`strict_dict_key_report` test was found under cardiacCore tests in this audit.

**Gate:** a discoverable contract must distinguish known native key, mechanically writable in workflow, native availability, and scientific applicability. Broad mechanical experimentation need not require a new domain approval for every value. It must not be reported as validated scientific support. Retain unknown units as unknown; label examples, native defaults and recommended ranges separately. Bind source evidence to a source/build identity when available; source absence remains a supported onboarding condition, not invented certainty.

### P2 A6 — Python operation maturity and cross-solver closure remain incomplete

`catalogs.operations.OPERATIONS` offers seven useful operations with explicit preconditions, side effects and scientific limitations; their `workflow_integration` remains `pending`. `SUPPORT_BOUNDARY['pending']` explicitly includes automatic seed/coverage/coordinate-ring integration and graph hand-off. This is a legitimate capability gap, not an argument to move algorithms into Core. `refine1Dgraph` belongs to cardiacCore's utility catalog; graph conversion/import declarations are owned by cardiacFoam and were removed from cardiacCore to avoid provider-map collisions.

**Gate:** one explicitly selected producer→artifact→consumer path must prove format, mesh/coordinate identity, units, field names, staging and native execution, followed by named observation/acceptance checks. Native execution success and scientific acceptance must remain different report fields. Do not promise a ready-to-use combined solver framework from independently passing adapter suites.

## Phase 2 corrections required

1. Define a normalized request/effective configuration contract before replacing writer hooks. Solve A1–A3 at their owning boundaries; preserve parameter identities and workflow consumption.
2. Define a write-plan operation with explicit format/codec owner and nested address. The current example `kind,target,key,value,provider_id,before` has no explicit nested scope. Both `lv.seed` and deeper `lv.extension.depthMin` must survive. Core controls transactions; OpenFOAM controls dictionary bytes.
3. Preserve lifecycle differences. cardiacFoam `sweep.materialize_case` invokes `build_and_launch` and synthesizes `Allrun` (and possibly mesh setup). cardiacCore's tutorial path patches a staged case that needs supplied assets and a declared DAG. These can share a writer without being equivalent case constructors. Do not claim generic cardiacCore synthesis works merely because the old refusing sweep capability was replaced.
4. Establish a complete side-effect inventory. `apply_input_overrides` sequentially writes dictionaries; Python seed/electrode/cell-set writers and cardiacFoam synthesis also write. Every native output need not be forced into a dictionary patch abstraction. Separate preparation, planned mutation, execution and result collection.
5. Add cross-route equivalence tests: normal run, tutorial/entry sweep, generic sweep where supported, strict apply/remediation and resume should share the intended change semantics and effective record. Their assets and permissible request shapes may legitimately differ.
6. Treat schema generation and operation typing as dependent improvements after the identities, validation boundaries and lifecycle are fixed. A frozen outer dataclass does not itself make nested dictionaries immutable or establish scientific support.

## Proposed expert work packages and gates

| Work package | Owner expertise | Exit evidence |
|---|---|---|
| AD-1 Address and workflow consistency | Adapter contract expert + OpenFOAM parser expert | Collision regression; invalid dynamic binding rejected; declared/consumed/mutable surface agrees; renamed fields staged and hashed correctly |
| AD-2 Effective semantic checks | cardiacCore domain adapter expert + public API test expert | Existing WIP reviewed; paired dictionary regression passes through public plan; overrides included; generic case remains valid |
| AD-3 Transaction migration pilot | Core transactions expert + both adapter maintainers | One existing case per adapter; nested patches and missing-key insertion; before/after effective values; fault injection leaves originals and metadata intact |
| AD-4 Evidence and discovery contract | Catalog/source evidence expert | Describe schema agrees with executable validators; defaults/examples/recommendations separated; build/evidence scope visible; no claims promoted by static scanning alone |
| AD-5 Combined workflow release slice | Native cardiacCore/cardiacFoam expert + reproducibility expert | Fresh assets declared; producer-consumer artifact checks; installed-package execution; native receipts; unresolved scientific decisions recorded |

This is a proposed team decomposition, not a claim that independent experts already approved these findings. The next wave should independently attempt to falsify A1–A3 before implementation.

## Minimal reproducibility script

Run with the repository's installed editable interpreter; the temporary case is disposable:

```python
from pathlib import Path
from tempfile import TemporaryDirectory
from omnidriver.cardiaccore.workflows.preprocessing import make_human_purkinje_slab_spec, PURKINJE_TREE_INPUT_PATHS
from omnidriver.cardiaccore.workflows.run_config import build_config
from omnidriver.cardiaccore.workflows.overrides import validate_input_overrides

for request in ({'$PURKINJE_TREE.nonsense.N_it': 3},
                {'$PURKINJE_TREE.lv.seed': 'not a vector'},
                {'$CARDIAC_CONDUCTIVITY.df': float('nan')}):
    print(validate_input_overrides(request, allowed_paths=PURKINJE_TREE_INPUT_PATHS))

with TemporaryDirectory() as directory:
    spec = make_human_purkinje_slab_spec(
        cases_root=Path(directory),
        input_overrides={'$CARDIAC_CONDUCTIVITY.fiberField': 'customFiber'})
    system = Path(spec.case_root) / 'system'
    system.mkdir(parents=True)
    (system / 'setCardiacConductivityDict').write_text(
        'df 0.1; ds 0.05; dn 0.02; fiberField originalFiber; sheetField originalSheet;\n')
    config, diagnostics = build_config(spec)
    print(config['preprocessing']['fiberField'], diagnostics)  # None, ()
    print(spec.metadata['workflow_dag']['steps'][0]['consumes'])  # still 0/fiber and 0/sheet
```
