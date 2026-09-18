# cardiacCore interface retirement review

Inspected the dirty OmniD and `/Users/simaocastro/cardiacCoreStandalone`
working trees on 2026-09-16. This is a retirement checklist, not a new callable
contract. Current contracts remain in the installed cardiacCore adapter.

## Intended ownership

- OmniD owns orchestration and its shared agent handbook.
- `omnidriver-cardiaccore` owns agent-facing cardiacCore catalogs, workflows,
  Python operations and package guidance.
- Native cardiacCore owns C++ executables, builds, dictionaries, native cases
  and native verification. These are not duplicate orchestrator code.
- Native documentation should point agents to the package, not offer a second
  Python pipeline or separately maintained usage catalog.

## What still prevents blanket deletion

| Standalone content | Package evidence | Required action |
| --- | --- | --- |
| `agent/pipeline_runner.py`, `preflight.py`, `describe.py`, `dict_builder.py`, JSON catalogs/schemas | OmniD orchestration and adapter catalogs exist, but standalone preflight tests include graph/scar combinations beyond the adapter's current scope | Remove the old interface and its exclusive tests only after retaining required domain facts or explicitly recording unsupported capabilities; no second runner is needed |
| `agent/deduce_purkinje_seeds.py` | Package seed proposal consumes native LV/RV surface masks and AHA labels; old script reconstructs recovered-septal candidates with UVC thresholds | Resolve the method choice; these implementations are not equivalent |
| `agent/check_purkinje_coverage.py` | Package has array coverage and a new optional native-file report | Compare representative output and remapping before removal |
| `agent/normalize_electrode_positions.py` | Package has frame calculations; standalone additionally reads VTK, computes reference offsets and writes JSON | Decide whether those file bridges are required and migrate/test them before removing the only implementation |
| `agent/check_seed_distances.py` | No corresponding declared package operation found | Decide whether to retain a nearest-node distance observation; do not carry over its unexplained 10-unit success threshold as scientific acceptance |
| Tutorial instructions and pipeline plans | Some still instruct users to run the standalone seed script | Update live callers and usage instructions in the same retirement batch; retain historical provenance as history |

The standalone tree already contains uncommitted deletion of the old plugin
scaffold and packaging. Preserve those changes and all native code/case edits.

## Package consistency issues

The current package adds `read_native_seed_surface_fields`,
`coverage_report_from_native_files` and `write_seed_dictionary`, but some
operation failure/status fields still say native sampling is pending. The
support-boundary record repeats that stale claim. The Purkinje module header
still says it does not write cases despite the explicit writer.

Fix descriptions against verified entrypoints before presenting the package as
the sole supported interface. An implemented reader is not proof of native
file compatibility or scientific equivalence.

## Safe retirement order

1. Seed decision resolved by the user: retain the package's native-surface
   plus AHA method; retire the standalone UVC-threshold method. Other
   file-bridge requirements remain to be reviewed.
2. Reconcile package contracts with implemented functions and verify the
   retained behavior using focused tests and representative supplied artifacts.
3. In the native repository, remove obsolete orchestration/catalog interfaces
   and their exclusive tests, updating active documentation and callers.
4. Remove superseded scientific helpers only after the corresponding checks
   pass. Git history retains old code; no executable legacy copy or fallback
   should remain in the active tree.

With workspace permission, removed `agent/deduce_purkinje_seeds.py` and
`agent/tests/test_deduce_purkinje_seeds.py` from the native repository. Updated
active seed references and marked historical instructions. Existing case
inputs and C++ code were not changed. This selects the approved method; it
does not claim equivalence to the retired method.

Package status/failure descriptions now expose the optional seed reader and
direct array-coverage callers to the native coverage operation. The Purkinje
module documents the explicit writer's side effect. The remaining standalone
runner/catalog interface and other helpers have not yet been deleted.

Verification after seed retirement: 41 cardiacCore tests passed from source
and 41 passed against a freshly built wheel outside the checkout, with the
optional PyVista/VTK dependency installed. The reader-to-seed test consumes
surface exports without UVC-derived masks. These are synthetic file/array
checks, not native solver or scientific acceptance runs. Both repositories'
diff whitespace checks passed. Changes remain uncommitted.

## Detailed remaining delta after seed retirement

Inspected executable helpers, the standalone catalogs and preflight, and the
adapter's plugin, input targets, utility manifests and three workflow factories.

### Coverage remapping correction

`coverage_report_from_native_files` previously concatenated LV and RV
endocardial labels and called `normalize_rv_septal_segments(endocardial_aha)`
without zone values, which left all values unchanged. The adapter now maps only
the RVEndoFaces samples as RV-tree labels, preserving LV labels. The native-file
regression test exercises both surface branches using an LV apical-septal label:
the LV surface remains `14`, while the RV recovery surface becomes `29`.
This is a synthetic VTK/array check; representative native-case validation is
still required before claiming scientific acceptance or retiring the coverage
helper's remaining independent behavior.

### Missing functions versus missing integration

| Area | Present in package | Still missing |
| --- | --- | --- |
| Seed proposal | Surface reader, surface-plus-AHA proposal, explicit dictionary writer | Automatic workflow steps linking surface preparation/export, proposal, writing and subsequent tree generation; representative-case evidence for that complete chain |
| Coverage | Array report, optional native reader, terminal CellZone remapping | Correct RV surface remapping above; full paired-surface verification; workflow attachment. The old formatted CLI and starved-sector exit policy need not be reproduced as scientific acceptance |
| Electrodes | Frame computation, encode/decode, applying fixed reference offsets | VTK field reader, reference-offset derivation from a supplied reference, file-oriented application and JSON output. Old reference conversion assumes metres-to-millimetres; unit handling must be explicit |
| Seed distance | No declared operation found | Optional nearest-mesh-node distance observation. Old code is not distance to a continuous surface and its 10-unit success threshold is not a portable acceptance rule |
| Dictionary construction | 12 reviewed override targets and explicit seed writer | General intent-to-dictionary construction, editable tree/growth settings, shared convention construction, paired bidomain coefficients, manual groove inputs and broader morphometry inputs. Some are already described as conditional, not executable |

### Native utility catalog delta

The standalone tool catalog has 11 entries; the adapter declares five:
`setCardiacConductivity`, `setCardiacAnatomy`, `setPurkinjeSlab`,
`setPurkinjeMorphometry`, and `generatePurkinjeTree`.

The six other entries are:

- `1DgraphToFoam`: graph hand-off contract/workflow absent from the package.
- `foamTo1Dgraph`: graph export contract/workflow absent.
- `setCardiacScar`: scar dictionary, selection requirements and output gating absent.
- `setPurkinjeScar`: scar-to-graph prerequisites and policy inputs absent.
- `newVtkUnstructuredToFoam`: asset-import contract/workflow absent.
- `cleanCardiacVtk`: catalog entry for an unavailable/deferred tool, not an
  implementation to migrate or advertise as available.

These are adapter omissions, not missing C++ implementations (except the
explicitly unavailable cleanup tool). The old dictionary catalog contains
eight dictionary groups and 109 entry records; these counts do not imply 109
verified or desirable adapter inputs and must not drive a blind catalog copy.

### Preflight facts not fully carried across

The old preflight includes field class/object checks, conditional dictionary
requirements, slab/tree exclusion, refusal of RV weighted selection and the
unresolved LV weighted-endocardial combination, plus the graph/scar chain and
`writeDebugFields` requirement for `ScarRegionID`. The current adapter's
`validate_configuration` and `validate_run_semantics` return empty tuples.
Its selected workflow shapes and override allowlists limit requests, but do
not establish equivalent validation of existing supplied case dictionaries.
Generic file/dependency checks may already be provided by Core/OpenFOAM; port
only missing domain declarations after checking that path. Historical mode
restrictions must be reconciled with current native source and domain decisions.

### Retirement boundary

The old runner's scheduling, logging and execution mechanics should not be
ported; OmniD already owns those responsibilities. Neither the old schemas
nor old describe/dictionary CLIs need compatibility implementations. Before
deleting their catalogs/tests, retain needed domain contracts in the package
or explicitly classify the corresponding feature as unsupported. Native C++
tests and case/scientific verification remain native-owned.

Recommended order: decide and complete electrode file bridges; add graph
hand-off if the next experiment needs it; reconcile the selected workflow's
preflight checks; then retire only the superseded legacy helpers. Scar/import
workflows can remain explicitly unsupported without keeping a second active
orchestrator.
