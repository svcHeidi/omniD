# Solver descriptions: one interpreter, per-solver data, a shared EP science layer

**Status: design, 2026-09-27. No code changed.** Written against `main` at
`876cf4a`. Sizes are `wc -l` on that tree; "code" and "prose" come from an AST
classifier that counts docstrings plus `#` lines as prose. The inputs were the
drift audit (`.superpowers/sdd/drift-audit.md`), the three plans named in §6,
`docs/solver-learning/{method,cardiacfoam,opencarp}.md`, and the native trees:
`~/noFrontendCardiacFoam_minor_errors` at `omnid/tutorials-are-pointers`, read
with `git show`, and `/usr/local/lib/opencarp/share/tutorials`, read-only.
Nothing was run.

## 0. The decision in one page

The owner asked whether TOML, YAML or JSON can define what a solver needs:
- how to run it, in parallel, later on GPU, and on HPC;
- its catalogs and its logic;
- how to construct a case and how to run one.

The answer is yes for the **mechanisms**, partly for the **logic**, and no for
**codecs and readers**. This design draws that line from the code, not from a
preference.

| what | today | under this design |
|---|---|---|
| **mechanisms**: commands, launch forms (serial, parallel, launcher checks), environment probes, case layout, generated paths, redaction, record steps, axes that only substitute a value | re-implemented per solver in Python: the `OpenCARPPlugin` (207 lines), the `OpenFOAMEnvironmentPlugin` hub (379), two `get_parallel_steps` (105 + 166), two preflights, and 1,601 lines of record modules | **one core interpreter** (`DescribedPlugin`) builds the *existing* plugin members from a per-solver `solver.toml` and per-record `*.toml`. The provider stack, the capability seams, `TutorialRecord`, `WorkflowStep`, `DefaultArgument`, `AxisContract`, `ProducedPath` and C1–C12 are kept unchanged underneath |
| **codecs and readers**: the OpenFOAM dictionary, `.par`, probes, LAT, time directories | Python | Python, **one per format**, named by the description. They are shared by every solver using that format |
| **science rules**: which quantities interact, and what they require | cardiacFOAM Python, on cardiacFOAM keys (`validation.py` V1–V8, `dict_entries_catalog.py` `required_when`) | the rules whose variables are electrophysiology quantities move once into **`omnidriver-electrophysiology`**, a small package that is mostly data. Each solver ships a `quantities.toml` that maps its keys onto those quantities, with unit, conversion and evidence. openCARP gains the rules by writing its map, not by re-coding them. Rules on cardiacFOAM-only features (verifiers, heterogeneity, the Purkinje couplers) stay in cardiacFOAM |
| **solver-specific logic**: openCARP F1/F2/F10/F14, cardiacFOAM's backend inference, dictionary synthesis, derived-value functions | Python | Python, named from the data (`resolve = "module:function"`) |
| **catalogs** | JSON (openCARP, generated from the binary) and Python literals (cardiacFOAM) | unchanged in this design. Converting cardiacFOAM's catalogs to generated JSON is the future OpenFOAM-catalog step, kept separate |
| **legacy factory path** | 3,633 lines in `tutorials/` plus core wiring | deleted as each EP tutorial migrates. TL-EM's broken factory module is retired (§5) |

**Reused, not replaced:**
- the plugin manifest: `get_profile`/`PluginProfile`, whose keys become the description's `[solver]`/`[case]` tables;
- `physics_layout.json`, which gains one field;
- `utility.manifest.toml`, the precedent for TOML and its `produces` shape;
- `DefaultArgument`, which gains its first openCARP use;
- `TutorialRecord`, built from TOML instead of hand-written;
- `core.quantities` and its `UNITS` table;
- `SchedulerAllocation`, and `_parallel_workflow_dag` with its checks;
- `record_surface`'s key grammar;
- the conformance suite.

**New:** one interpreter module and a JSON Schema in core, a `unit`/`quantity`
on `AxisContract`, one optional `quantity_map` capability, and the
electrophysiology package.

**Replaced:** per-solver Python adapter code whose content is constant data,
Python record modules, and the two `get_parallel_steps` implementations.

**A rule against building too much.** A mechanism moves from Python into core
data only when at least two of {toy, openCARP, OpenFOAM layer} need it, or when
it states a fact about a binary (such as openCARP's "prints `GIT tag` once per
MPI world", I5). Everything with one implementer stays that implementer's
Python and is named from the data. So OpenFOAM's bashrc sourcing, its
stale-build check and its `FOAM_APPBIN` probe stay in `omnidriver-openfoam`.

---

## 1. Content inventory

Classes:
- (a) a mechanism core interprets from data;
- (b) a per-format codec or reader;
- (c) a science rule;
- (d) solver-specific logic that stays Python;
- (e) per-solver content data;
- (f) legacy, deleted when its last caller migrates;
- (g) core plumbing, unchanged.

"Who" names the solvers that need the item:
- **OC**: openCARP;
- **OF**: the OpenFOAM layer;
- **CF**: cardiacFOAM;
- **CC**: cardiacCore;
- **toy**: core's test solver.

### 1.1 Core (`packages/omnidriver/src/omnidriver`, 29,177 lines, 94 modules)

| mechanism / content | where | size | who | class |
|---|---|---|---|---|
| plugin contract, `DriverContext`, loaders | `core/plugin_interface.py` | 1153 | all | a/g. The required set is derived from the seams (`_required_plugin_members`). 3 of its 6 required methods are factory-shaped: `get_tutorial_catalog`, `validate_configuration(spec)`, `predict_data_artifacts(case_root, spec)` |
| capability seams and adapters (32 seams) | `core/plugin_capabilities.py` | 2372 | all | a |
| provider composition (9 shapes) | `core/provider_stack.py` | 818 | all | a |
| discovery (entry point `omnidriver.plugins`, `requires:` closure) | `core/plugin_discovery.py` | 491 | all | a |
| YAML manifest loader (`load_plugin_profile`; no schema file, checked by hand) | `core/plugin_profile.py` | 279 | all | b |
| TOML utility-manifest loader (`tomllib`) | `core/utility_catalog.py` | 470 | CF, CC | b |
| records: `TutorialRecord`, `WorkflowStep`, `DefaultArgument`, `AxisContract` (**no unit**), `AxisPatch`, `AxisResult`, `ProducedPath`, `variant_constraints`, patch resolution | `core/tutorial_records.py` | 1231 (618 code) | all | a |
| record staging, commit, DAG, parallel pass (`_parallel_workflow_dag`, `_check_parallel_form`), `SchedulerAllocation`, `SCHEDULER_ALLOCATION_VARIABLES = ("SLURM_NTASKS",)`, positional `record_artifact_id` | `core/runtime/record_execution.py` | 968 | all | a |
| core-written runtime records | `core/runtime_records.py` | 76 | all | a |
| quantities, readers, units (`s ms us m cm mm um`), comparison, point references | `core/quantities/` | 981 | OC, CF, toy | a/b |
| key grammar for C10 (`[Int]`, `<name>`) | `core/runtime/record_surface.py` | 72 | all | a |
| DAG normalisation, `CORE_NEUTRAL_COMMANDS` (`mpirun`, `mpiexec`, `orterun`), step `cwd` (already supported) | `core/runtime/workflow.py` | 623 | all | a |
| workflow runner, log redaction, DYLD preamble for case scripts | `core/runtime/workflow_{runner,orchestrator,state}.py` | 927 | all | a |
| case write channel (`commit_case_write`), transactions | `core/case_write.py`, `core/case_transaction.py` | 1653 | all | a |
| strict planning, sweep runner (record plus legacy branches), registry | `core/strict_planning.py`, `core/runtime/sweep_runner.py`, `core/runtime/registry.py` | 856 + 1363 + 702 | all | a, with f parts |
| scratch root (`resolve_scratch_root`) | `core/specs/paths.py` | 235 | all | a |
| conformance C1–C12, `ConformanceTarget` (`environment` is `{}` in all six targets, audit §1.1) | `conformance/` | 711 | all | g |
| legacy fallbacks | `core/compatibility.py` | 530 | factory | a/f |
| factory wiring: `spec_factories` (16 refs), `make_spec` (24), `generic_case.py`, `sweep_routing.py`, `sweep_materialize.py`, `tutorial_contracts.py`, `tutorials_display.py`, `introspection` factory branches | several | about 700 | factory, case-folder | f (case-folder `make_generic_case_spec` stays) |
| retired-member guards `_RETIRED_PLUGIN_MEMBERS` | `plugin_interface.py` | about 35 | none | f |
| CLI, provenance, reports, remediation, post-processing plotting | many | about 9,000 | all | g |
| **toy solver** (tests only): `MinimalTestPlugin` 217, `E2ERecordPlugin` 210, `conformance_toy.py` 459 (22 deliberately broken subclasses), `parallel_toy.py` 47, `quantity_toy.py` 249 | `packages/omnidriver/tests/plugins/` | 1182 | toy | about 60 lines of content; the rest are stubs (§2.4) |

### 1.2 OpenFOAM layer (`omnidriver-openfoam`, 7,457 lines)

| mechanism / content | where | size | who | class |
|---|---|---|---|---|
| provider hub: forwards each hook to a module | `environment.py` | 379 (203 code) | OF | a (hook table), d (`get_input_roots`, `hex_cell_counts` key) |
| manifest: provides, `system/controlDict` required always (**the case marker**), `constant`, `Allrun` | `openfoam-environment.yaml` | 67 (41 comment) | OF | e |
| case-file roles whitelist | `profile.py` | 36 | OF | e |
| parallel form: `decomposePar -force` → `mpirun -np N … -parallel` → `reconstructPar`, N from `system/decomposeParDict:numberOfSubdomains`, a request of N refused, allocation must agree | `parallel_execution.py` `parallel_steps_for_record`, `_parallel_form` | 166 | OF | a |
| factory parallel form `solve_steps` | same | about 50 | pseudo-ECG | f |
| runtime conventions: `postProcessing`, `processor*`, instance regex, preserved `0`, case scripts; **duplicates core's runtime records** (O15) | `case_runtime_conventions.py` | 44 | OF | e |
| command set (`blockMesh`, `checkMesh`, `decomposePar`, `gmsh`, `gmshToFoam`, `postProcess`, `reconstructPar`, `setExprFields`, `topoSet`, `vtkUnstructuredToFoam`) plus installed apps under `FOAM_APPBIN`/`FOAM_USER_APPBIN` | `command_authorization.py` | 51 | OF | e + d |
| bashrc discovery list and sourcing (`bash -c source; export -p`) | `openfoam_environment.py` | 236 | OF | a-list/d-sourcing (one implementer, so it stays) |
| preflight: `WM_PROJECT_DIR` error/warning, partial env, `missing_executable`, `missing_mpi`, `stale_build` | `environment_preflight.py` | 274 | OF | a (variables, commands) + d (`stale_build`) |
| dict codec: line writer, foamlib tier, literals, `foamDictionary` evaluation, renderer, `--apply` routing | `mutators.py` 845, `foam_backend.py` 328, `literals.py` 341, `effective_dictionary.py` 495, `case_rendering.py` 506, `apply_overrides.py` 881 | 3,396 | OF (every OpenFOAM solver) | b |
| catalog synthesis primitives | `dict_builder.py` | 375 | CF, CC | a/b |
| blockMeshDict grammar (`hex (`, `vertices`, `scale`), planners | `case_planning.py` | 623 | OF | b; `plan_dict_block` f (pseudo-ECG), `plan_delta_t`/`plan_end_time` f |
| blockMesh resolution axis builder | `axes/block_mesh_resolution.py` | 397 (96 code) | CF | d (derived values over b) |
| default blockMeshDict template, `cell_counts_from_dx` | `mesh_provisioning.py` | 153 | CF | e + d |
| `render_tet_geo` (`__LC__`) | `tet_mesh_provisioning.py` | 83 | pseudo-ECG | f |
| polyMesh bbox reader, scale classes | `mesh_geometry.py` | 247 | OF | b + d |
| probes parser (`parse_probe_series`, cell-centre siblings) | `probes.py` | 133 | OF | b |
| function-object field check. **Leak:** `system/electro/controlDict` and the default region `"electro"` are cardiac vocabulary in the OpenFOAM layer | `function_object_fields.py` | 93 | OF/CF | b (the leak is fixed in S4, §6) |
| time selection (`Time::setControls` mirror), input roots | `time_selection.py` | 160 (50 code) | OF | b/d |
| C++ dict-key scanner, case key diagnostics | `dict_keys_scanner.py` 422, `case_dict_keys.py` 173 | 595 | OF | b + e |

### 1.3 cardiacFOAM (`omnidriver-cardiacfoam`, 16,530 lines)

| mechanism / content | where | size | who | class |
|---|---|---|---|---|
| plugin glue plus `validate_configuration` (solver set, ionicModel in catalog, V8) | `cardiacfoam_plugin.py` | 598 (329 code) | CF | a (glue) + c |
| manifest: provides (16, with 68 comment lines on why others are withheld), `runtime.backend` lightweight/full library lists, case profile, `cxx_mapping` | `plugin.yaml` | 160 | CF | e (already declarative) |
| region layout table and interpreter | `physics_layout.json` 9, `physics_layout.py` 158 | 167 | CF | e + a |
| **records** (5) plus shared axes and outputs | `records/*.py` | 1,524 (588 code, 831 prose) | CF | e as Python, plus d (derived values) |
| activation-probe reader (`value_unit "s"`, sentinel −1, `cell-containing`) on `openfoam.probes` | `activation_probes.py` | 83 | CF (in fact any OpenFOAM `probes` output) | b, misplaced (audit §2.8) |
| science rules V1–V8 | `validation.py` | 925 (610 code) | CF | c. V5 (tissue ∈ model's tissues) is EP-general; V1, V2, V4, V6, V7, V8 are cardiacFOAM features |
| electroProperties catalog: 160 `DictEntry`s with `required_when`/`applicable_when`/`forbidden_when`. EP-general examples: mono/bi require `chi` and `cm`; bi requires σi, σe and `phiERefPoint`; eikonal requires `c0` and a stimulus box | `dict_entries_catalog.py` | 1641 | CF | e with c inside |
| ionic model catalog: 27 models, tissues, heterogeneity, `single_cell_stimulus_amplitude`; `compatible_solvers` declared but **checked nowhere** | `ionic_model_catalog.py` | 542 | CF | e + c |
| active-tension catalog, solver-coupling rules (10) | `active_tension_catalog.py` 223, `solver_coupling.py` 111 | 334 | CF | e + c |
| key validator for records (catalog shape, `<solver>Coeffs`, `system/*` accepted unvalidated) | `record_key_validation.py` | 345 (134 code) | CF | a + b |
| dictionary synthesis, parse, regenerate, `build_and_launch` | `dict_builder.py` | 1543 (801 code) | CF (generic case, synthesize) | b + d + c |
| override resolution, patch mutation, factory transaction helpers | `overrides.py` | 1042 (517 code) | CF | a + b + f |
| backend inference, build manifest | `runtime_profile.py` | 423 (344 code) | CF | d |
| telemetry globs, library catalog, gmsh runtime dependency | `runtime_evidence.py` | 318 | CF | d + e |
| artifact prediction, case introspection, planning policy | `artifacts_predictor.py` 282, `case_introspection.py` 118, `planning_policy.py` 43 | 443 | CF | c + d |
| C++ tooling (names parser, RTST scanner, ionic catalog verification) | 179 + 187 + 382 | 748 | CF | b/d (tooling) |
| templates, detection, small glue (`system_templates`, `detection`, `own_context`, `named_catalogs`, `reports`, `config_schema`, `override_schema`, `run_document_config`, `sweep`, `case_*`, `common_dict_entries`, `dict_entries`, `monorepo`, `mesh_*`) | many | about 2,100 | CF | b/d/e |
| guidance, utility manifests (12 TOML, 622 lines), fixtures | `guidance.md`, `utilities/`, `fixtures/` | 1,512 | CF | e |
| **factory path**: 7 tutorials plus defaults plus scaffolding | `tutorials/` | 3,633 | singleCell, cable ×2, pseudo-ECG, TL-EM, Purkinje, 1D3D | f |
| factory-only helpers | `spatial_pacing.py` 53; in `overrides.py`: `merge_assignments`, `commit_case_overrides`, `resolve_entry_overrides`, `resolve_electro_property_{ensure,set}`; dead: `remove_/ensure_electro_property_dict`, `normalize_entry_overrides` | about 250 | factory | f |

Defects found by the inventory that this design must not carry over:
- Duplicated rules:
  - `HETEROGENEITY_MODELS` restates `IonicModelEntry.supports_heterogeneity`;
  - the solver set in `validate_configuration` restates the `myocardiumSolver` enum;
  - `config_schema.py`'s tissue enum restates the catalog's.
- Dead names:
  - the catalog's `sex` is gated on `"TWorldBatched"`, but the model is `TWorldcompactBatched`;
  - `display.py` presets name `TenTusscher`/`FentonKarma`, which are not in the catalog.
- `constant/electroProperties` is hard-coded at 25 sites in 15 files. Only `planning_policy.py` goes through `physics_layout.region_document` (final review M3).
- `pyproject.toml` package-data lists `fixtures/template/constant/*` but not `fixtures/single_cell_polymesh/*`, which `mesh_provisioning.meshless_polymesh_fixture()` reads. This was not checked in a wheel. It matters for the singleCell migration (S9).

### 1.4 openCARP (`omnidriver-opencarp`, 1,075 lines Python, 2,851 data)

| mechanism / content | where | size (code) | class |
|---|---|---|---|
| plugin glue: profile, stubs, the config reader with F1/F10 refusals, the renderer (`patch_par` + `check_indices` + `RenderedFile`), record key catalogue | `plugin.py` | 207 (141) | a (glue) + b (reader, renderer) |
| manifest | `opencarp.yaml` | 14 | e |
| commands, redaction (G3), `-buildinfo` probe (A4–A6), version warning | `environment.py` | 81 (48) | a (a fact about the binary) |
| parallel form `mpirun -np N openCARP …`, N from request or allocation; **launcher check** (I2, I5) | `parallel.py` | 105 (71) | a |
| `.par` codec (F1, F8–F13) | `par_format.py` | 171 (114) | b |
| LAT reader (F3, F6, F16, F17) | `lat_reader.py` | 100 (67) | b |
| catalog loader and generator (+Help, B1–B6) | `catalog.py` 59, `catalog_generation.py` 127 | 186 (135) | e + b |
| key validator: `+F` documents, F14 command-line ownership, generic catalog check (kind, menu, literal bounds), F2 `check_indices` | `validation.py` | 147 (99) | d + a (the catalog check) |
| record `niedererNVersion` and its `dx` axis | `records/` | 77 (41) | e |
| parameter catalog (generated, v18.1) | `opencarp_parameters.json` | 2,837 | e |
| guidance | `guidance.md` | 70 | e |

**Lost content (audit §4.1):**
- item 1: `run.py`'s `-tend 50 -dt 20 -mass_lumping 0` (`run.py` lines 201–214 and 250–256, read today);
- item 2: carputils solver options;
- item 3: the diagonal profile.

### 1.5 cardiacCore (`omnidriver-cardiaccore`, 4,626 lines)

It is not a solver: it is preprocessing workflows on the OpenFOAM layer. It is
in scope only where its content has the same shape as a description.
- `catalogs/inputs.py` (1038) is 87 `DictEntry` literals. Its embedded c-rules include the six bidomain conductivity entries being mutually `co_required_with`.
- `catalogs/utilities.py` (263) holds 9 `UtilityManifest`s.
- `catalogs/operations.py` (248), `purkinje.py` (69) and `support_boundary.py` (82) are data written as Python.
- `workflows/preprocessing.py` (499) holds 4 literal `workflow_dag`s.
- `operations/*` (numpy/pyvista geometry) is d.

**This design does not migrate cardiacCore** (EP first). §6 names the one
place it would follow: its utility manifests and DAG literals fit the record
TOML unchanged.

---

## 2. The solver description

### 2.1 Format: TOML for what people write, JSON for what programs write

**Decision: descriptions and records are TOML.** Studies, requests, references
and generated catalogs stay JSON.

1. **It is already the format for exactly this content.** cardiacFOAM's 12
   `utility.manifest.toml` files already declare a command's flags, inputs and
   `[[produces]]` with path and format. Core already parses them with the
   stdlib `tomllib` (`core/utility_catalog.py`). The 3.11 floor has `tomllib`,
   so there is no new dependency.
2. **YAML reinterprets exactly the values this repository must not touch.**
   PyYAML's `safe_load` is YAML 1.1: bare `yes`/`no`/`on`/`off` become booleans.
   OpenFOAM switches are spelled `yes`/`no`/`on`/`off`. openCARP reads every
   Flag spelling except `0`/`false` as on (F1), so `no` must stay the string
   `no` until the codec refuses it. TOML has no implicit typing: a bare word
   is a parse error, so every command argument and value is quoted and survives
   verbatim.
3. **Comments carry evidence.** A step's `produces` cites the run that settled
   it (`# BB1`). JSON cannot hold that.
4. **JSON stays where programs write and digests pin.** Studies are written by
   agents. Requests are pre-registered with `SHA256SUMS`. The openCARP catalog
   is generated from `+Help`. Changing their format would re-register the
   campaign for nothing.
5. **The four YAML manifests fold into the descriptions** (`opencarp.yaml`,
   `openfoam-environment.yaml`, cardiacFOAM's `plugin.yaml`): they become the
   description's `[solver]` and `[case]` tables. cardiacCore's two YAML files
   stay until cardiacCore is touched, so PyYAML stays a core dependency for now.

### 2.2 How a description loads

- **Where it lives.** Each package ships `solver.toml` beside its Python, plus
  `records/<name>.toml`. They are package data, and the wheel gate
  (`check-wheel-artifact.py`) gains an assertion that they are present.
- **How it is found.** Unchanged: the `omnidriver.plugins` entry point. Its
  target is one line in the package:
  `PLUGIN = described_plugin(__package__)`. `load_plugin_context` also accepts
  a path to a `solver.toml`. That path is supplied, never searched for, and it
  is how the toy loads with zero Python.
- **What it builds.** `core/solver_description.py` validates the TOML against
  `schemas/solver-description.schema.json` (`jsonschema`, already a
  dependency). It then builds a `DescribedPlugin`: an object that answers the
  **existing** `SolverPlugin` members from the tables (map in §2.3). The
  provider stack composes it exactly as it composes a hand-written plugin
  today, so `requires:`, the nine composition shapes and the stack digest are
  untouched.
- **`provides` is derived, not declared.** A capability is provided exactly
  when every member it adapts is answered, either by a table or by a hook
  method. That deletes the hand-maintained `provides:` lists and their 68 + 41
  comment lines about "realness". Those comments existed because a list and
  the code could disagree; a derived list cannot. The realness question (is a
  member a hollow stub?) remains only for hook methods, which guard B counts.
- **Python is named, never implied.** `[python]` names the modules a solver
  keeps, each with its role: `codec`, `reader`, `rule`, `derived`, or `hooks`.
  `hooks` is the residual escape: an object whose methods answer members the
  data does not cover. If data and a hook both answer a member, loading is
  refused by name (one source of truth). The shrinking-baseline gate (§6, guard B)
  counts Python outside those roles.

### 2.3 The schema, table by table

The **maps to** column is the existing member the table answers. That column
is the reuse guarantee.

| table | keys | maps to (existing member) |
|---|---|---|
| `[solver]` | `id`, `name`, `version`, `api_version`, `requires = [...]`, `guidance = "guidance.md"`, `records = "records/*.toml"`, `cxx_mapping` | identity members, `get_profile().requires`, `get_agent_guidance`, `get_tutorial_records`, the C++ drift scanner's roots |
| `[commands]` | `solve = [...]` (the solve step's commands), `auxiliary = [...]`, `environment = [...]` | `get_solve_step_commands`, `get_solver_commands`, `get_auxiliary_commands`, `get_environment_commands` |
| `[tool.<command>]` | `produces = [...]`: what that command always writes, stated once for every record | new; replaces `records/case_outputs.py`'s constants, the same shape as `utility.manifest.toml`'s `[[produces]]` |
| `[environment]` | `source`: `"ambient"` or `{ python = "module:function", flag = "--environment-source", env = "OPENFOAM_BASHRC" }`. `[[environment.variable]]`: `name`, `platform`, `level`, `purpose`, all **supplied**, never searched for. `[[environment.probe]]`: `run`, `when_command`, `expect` (a marker in stdout+stderr), `count`, `code`, `message`, and an optional `version = { pattern, equals, level, code }` | `get_environment_diagnostics`, `get_loaded_environment`, `get_configured_environment` |
| `[logs]` | `redact = [regex, ...]` | `get_log_redaction_patterns` |
| `[launch.parallel]` | `ranks.case = "<document>:<key>"` (optional), `launchers = [...]`, `pre = [step templates]`, `wrap = [argv template]`, `post = [step templates]`, `[[launch.parallel.check]]` (a probe run under the launcher) | `get_parallel_steps`, `get_environment_diagnostics` (for the check) |
| `[launch.gpu]` | **reserved; the schema refuses any key.** §2.3.2 says why | none |
| `[case]` | `marker = [...]`, `roles = [...]`, `[[case.document]]` (`glob`, `codec`, `role`, `required`), `[case.generated]` (directories, files, prefixes, suffixes, `replicas`, `instances`, `preserved_instances`, `case_scripts`), `input_roots = "module:function"`, `regions = "module:function"`, `legacy_marker`, `runnable_without_workflow` (case-folder entries) | `get_profile().case_files`, `has_case_marker`, `get_case_runtime_conventions`, `get_input_roots` |
| `[codec.<format>]` | `python = "module:Class"` | `get_config_value_reader`, `get_case_value_comparator`, `get_rendered_formats`, `resolve_case_mutation`, `render_case_files` |
| `[catalog]` | `file = "…json"` with `keys = "template"`, or `python = "module:object"`, or `unvalidated = true`; `rule = "module:function"` for solver-specific refusals | `get_record_key_validator`, `get_record_key_catalog` |
| `[output.<format>]` | `reader = "module:Class"`, and for readers of a solver-neutral format, `unit_from = "field"` plus a `[output.<format>.field]` table | `get_artifact_value_reader` |
| `[quantities]` | `map = "quantities.toml"`, `vocabulary = "omnidriver.electrophysiology"` | new optional seam `quantity_map` (§3) |

#### 2.3.1 Launch forms: one rank rule and three templates

**The rank rule, in core, identical for every solver.** A parallel run's N
comes from the **present** sources among:
- the case: `ranks.case`, read through the config-value reader as the run will see it (`_case_value_reader`, reused);
- the request: `parallel: N` or `--parallel N`;
- the ambient scheduler allocation (`SCHEDULER_ALLOCATION_VARIABLES`, reused).

All present sources must agree. Disagreement is refused, naming both. No
source at all is refused too. `parallel: true` means "use whatever the other
sources say".

This is the audit's R2: one spelling, one meaning. The current rules are a
special case:
- openCARP has no `ranks.case`, so request or allocation;
- OpenFOAM reads `numberOfSubdomains`, and now also *accepts* `N` and checks it against the case instead of refusing it.

So `campaign.sh`'s per-solver `--parallel` branch goes.

**Templates.** Placeholders:

| placeholder | expands to |
|---|---|
| `{step}` | the solve step's id |
| `{command}` | the solve step's command |
| `{args}` | the solve step's arguments |
| `{ranks}` | N |
| `{launcher}` | the chosen launcher's argv |

Nothing else is expanded. There are no expressions.

Launchers are neutral data in core: `mpirun = ["mpirun", "-np", "{ranks}"]`
and `srun = ["srun", "-n", "{ranks}"]`. `mpirun`, `mpiexec` and `orterun` are
already `CORE_NEUTRAL_COMMANDS`. A description lists the launchers it has
**verified** (`launchers = ["mpirun"]`). The user picks one with `--launcher`
(supplied), and the default is the first listed. `_check_parallel_form` still
runs on the result: exactly one step keeps the solve id and its `produces`.

**Launcher check** (openCARP I2/I5, and the same class of fault any MPI
solver has). `[[launch.parallel.check]]` runs:
- `run = ["{launcher}", "openCARP", "+Default"]`, with `{ranks}` = 2, in a scratch directory;
- it counts `expect` in stdout+stderr and compares that count with `count`.

On a mismatch it emits `code` and `message`. Output lines are echoed only
after the `[logs] redact` patterns are applied (evidence G3). Today's
`launcher_diagnostics` is this probe, written in Python. The shape is generic;
only openCARP declares it until an OpenFOAM run shows the same fault.

#### 2.3.2 GPU and HPC

**GPU is reserved, not built.** `future/ENVIRONMENT_CONTRACT.md` §12 records
that a device vocabulary was "deliberately not built", because nothing in
either solver launches on a device. The schema therefore refuses
`[launch.gpu]` by name, citing §12. When a real device launch exists, it would
take the parallel form's shape:
- an ambient read declared in core (`CUDA_VISIBLE_DEVICES`, like `SLURM_NTASKS`);
- a `wrap` template;
- a `check`.

This design adds no key for it.

**HPC is a mapping, not a mode.** omniD runs *inside* an allocation:
1. The allocation is read (`SLURM_NTASKS`, reused).
2. The rank rule checks it.
3. The launcher is chosen by `--launcher`.

`srun` ships as core data, but **no solver lists it until a real cluster run
shows that solver starts one MPI world under it**. That is the rule
"fixtures cannot settle external claims". The site environment (`module
load`, or a bashrc) is the existing supplied environment source. Writing job
scripts (`sbatch`) is not built; the campaign's cluster run submits its own.

#### 2.3.3 Case construction

- **Marker.** `[case] marker` lists files that must exist for a directory to be
  this solver's case. The OpenFOAM layer declares `["system/controlDict"]` (the
  owner's rule). cardiacFOAM inherits it through `requires`. Its own
  `has_case_marker` (`constant/electroProperties*`) serves case-folder entries.
  It moves into `[case]` as `legacy_marker`, and records never consult it.
  openCARP declares none: its native case is `run.py` plus `.par` files, and
  a record's `+F` consumes are checked by C8.
- **Codec.** Each `[[case.document]]` maps a glob to a codec:
  - `system/**` and `constant/**` → `openfoam_dictionary`;
  - `*.par` → `opencarp_par`;
  - `*.json` → core's neutral `json_document`, for the toy.

  Core then does the per-document dispatch, the digests and the
  `RenderedFile` construction. Today openCARP's `plugin.py` does this itself
  in about 40 lines, which move to core.
- **Where a parameter lives.** Unchanged: `document:key.path`, with
  `record_surface`'s key grammar. §3 adds quantity names that resolve to one
  of these.
- **Authored versus generated.** Unchanged in meaning (A5, C11):
  - generated = every step's `produces`, `[tool.<command>] produces`, core's runtime records, and `[case.generated]`;
  - authored = everything else in the native case.

  `[case.generated]` is `case_runtime_conventions.py` moved verbatim into
  data. At the same step (O15), the OpenFOAM copy of core's names is deleted.
- **Starting state (loose pre-processing).** A record declares its **default**
  route. Other routes are declared only where the native case has them (the
  gmsh tet templates). The description declares tools, not routes.
  `variant_constraints` stays, as route data (`admits`); §7 D8 explains why
  the audit's replacement for it does not work.

#### 2.3.4 Outputs

`[output.<format>] reader = "module:Class"` replaces `get_artifact_value_reader`'s
`if format == …` body. C12 is unchanged: every declared format must have a
reader whose declaration is valid.

The OpenFOAM `probes` reader moves into the OpenFOAM layer (audit §2.8/R4). Its
value unit comes from the **field**, which the solver declares:
`[output.openfoam_probes.field] activationTime = { unit = "s", sentinels = [-1.0] }`
in cardiacFOAM's description. So any OpenFOAM solver's probes are readable,
and cardiacFOAM keeps only the fact that `activationTime` is in seconds with
−1 meaning "never".

### 2.4 The four descriptions, written out

#### The toy (core tests): zero Python

```toml
# packages/omnidriver/tests/plugins/toy/solver.toml
[solver]
id = "org.omnidriver.toy"
name = "toy"
version = "0.1.0"
api_version = "2"
records = "records/*.toml"

[commands]
solve = ["touch"]

[environment]
source = "ambient"

[case]
marker = ["constant/mesh.json"]
[[case.document]]
glob = "constant/*.json"
codec = "json_document"          # core's neutral codec: read, agree, patch in place
role = "plugin.configuration"
required = "always"

[catalog]
keys = { "constant/mesh.json" = { cells = "integer" } }   # the toy's whole catalog

```

```toml
# packages/omnidriver/tests/plugins/toy/records/toyTutorial.toml
name = "toyTutorial"
native_case = "toyTutorial"

[[axis]]
name = "numberCells"
kind = "integer"
[[axis.patch]]
document = "constant/mesh.json"
key = "cells"
value = "{value}"

[[step]]
id = "solve"
command = ["touch", "solved.marker"]
consumes = ["constant/mesh.json"]
produces = ["solved.marker"]
```

This covers what `E2ERecordPlugin` (210 lines) and the part of
`MinimalTestPlugin` it uses provide today. The 22 broken subclasses in
`conformance_toy.py` stay Python test code: they now subclass the described
toy, overriding one member each to prove a check bites. `parallel_toy.py`
becomes a `[launch.parallel]` table of 5 lines once S3 lands the launch
templates. `quantity_toy.py` stays
Python: it tests the reader seam itself.

#### openCARP

```toml
# packages/omnidriver-opencarp/src/omnidriver/opencarp/solver.toml
[solver]
id = "org.omnidriver.opencarp"
name = "openCARP"
version = "0.1.0"
api_version = "2"
guidance = "guidance.md"            # no requires: its own environment and solver (C1)
records = "records/*.toml"

[commands]
solve = ["openCARP"]
auxiliary = ["mesher", "igbextract", "igbhead"]

[environment]
source = "ambient"                  # binaries plus one library path, supplied (A6)
[[environment.variable]]
name = "DYLD_LIBRARY_PATH"
platform = "darwin"
purpose = "the directory holding libsundials_cvode (A4-A6)"
[[environment.probe]]
when_command = "openCARP"
run = ["openCARP", "-buildinfo"]
expect = "GIT tag"
code = "opencarp_binary_unloadable"
message = "'openCARP' is on PATH but cannot start; on macOS set DYLD_LIBRARY_PATH to the directory holding libsundials_cvode (A4-A6)"
version = { pattern = 'GIT tag:\s*(\S+)', equals = "catalog:opencarp.tag", level = "warning", code = "opencarp_version_mismatch" }

[logs]
redact = ['(?<=://)[^/\s@]+(?=@)']  # the CI token in the build header (G3)

[launch.parallel]                   # PETSc partitions; outputs keep the serial layout (I6, I7)
launchers = ["mpirun"]              # the MPI openCARP was built against, first on PATH (I1)
wrap = ["{launcher}", "{command}", "{args}"]
[[launch.parallel.check]]           # another MPI starts N one-process runs (I2); one world prints the header once (I5)
run = ["{launcher}", "openCARP", "+Default"]
ranks = 2
expect = "GIT tag"
count = 1
code = "opencarp_mpi_launcher_mismatch"
message = "not the launcher of the MPI openCARP was built against: a parallel run would solve the whole problem once per process into one output directory (I2). Put that MPI's launcher first on PATH"

[[case.document]]
glob = "*.par"
codec = "opencarp_par"
role = "plugin.configuration"
required = "conditional"

[codec.opencarp_par]
python = "omnidriver.opencarp.par_format:ParCodec"   # F1, F8-F13, F2 check on render

[catalog]
file = "opencarp_parameters.json"   # generated from +Help (B1-B6); v18.1
keys = "template"                   # stim[Int].pulse.strength
rule = "omnidriver.opencarp.validation:refuse"      # +F documents only; F14 command-line ownership

[output.opencarp_lat_per_node]
reader = "omnidriver.opencarp.lat_reader:LatPerNodeReader"

[quantities]
map = "quantities.toml"
vocabulary = "omnidriver.electrophysiology"

[python]
codec = ["omnidriver.opencarp.par_format"]
reader = ["omnidriver.opencarp.lat_reader"]
rule = ["omnidriver.opencarp.validation", "omnidriver.opencarp.catalog", "omnidriver.opencarp.catalog_generation"]

```

```toml
# records/niedererNVersion.toml: native 02_EP_tissue/03E_study_resolution
# (nversion.par, singlecell.sv, run.py). Facts: docs/solver-learning/opencarp.md.
name = "niedererNVersion"
native_case = "02_EP_tissue/03E_study_resolution"

[[axis]]
name = "dx"
kind = "scalar"
unit = "um"                         # mesher -resolution is in um (F3)
quantity = "mesh.spacing"
arguments.mesh = ["-resolution[0]", "{value}", "-resolution[1]", "{value}", "-resolution[2]", "{value}"]

# run.py's own defaults (run.py:201-214, 250-256); D2. Each axis replaces its argument.
[[axis]]
name = "tend"
kind = "scalar"
unit = "ms"
quantity = "time.end"
replaces = "solve:-tend"
[[axis]]
name = "dt"
kind = "scalar"
unit = "us"
quantity = "time.step"
replaces = "solve:-dt"
[[axis]]
name = "massLumping"
kind = "enum"
choices = ["0", "1"]
replaces = "solve:-mass_lumping"

[[step]]
id = "mesh"                         # mesh.Block(size=(20,7,3), centre=(10,3.5,1.5)) in cm (F3)
command = ["mesher", "-size[0]", "2.0", "-size[1]", "0.7", "-size[2]", "0.3",
           "-center[0]", "1.0", "-center[1]", "0.35", "-center[2]", "0.15", "-mesh", "slab"]
produces = ["slab.pts", "slab.elem", "slab.lon", "slab.vec", "slab.vpts"]   # F15

[[step]]
id = "solve"                        # im_sv_init case-relative (F5); no region options (F4)
command = ["openCARP", "+F", "nversion.par", "-meshname", "slab", "-simID", "out",
           "-imp_region[0].im_sv_init", "singlecell.sv"]
defaults = { "-tend" = ["50"], "-dt" = ["20"], "-mass_lumping" = ["0"] }
consumes = ["nversion.par", "singlecell.sv"]
produces = ["out", "out/vm.igb",
            { path = "out/init_acts_vm_act-thresh.dat", format = "opencarp_lat_per_node" }]  # F6, F15
```

The `defaults` table **is** `DefaultArgument`: its first openCARP use, which
restores lost-content item 1.

Two consequences:
- The F14 validator must read `defaults` as well as `command`. This is P3
  concern 2, fixed in the same step. It then refuses `nversion.par:tend`
  (the command line owns it), and the campaign's study moves to the `tend`
  axis before the cluster run.
- `validation.read_documents` already derives ownership from the record's own
  arguments. It now reads the TOML record, so ownership has one source.

#### The OpenFOAM layer

```toml
# packages/omnidriver-openfoam/src/omnidriver/openfoam/solver.toml
[solver]
id = "org.omnidriver.openfoam.environment"
name = "OpenFOAM"
version = "0.1.0"
api_version = "2"

[commands]
environment = ["blockMesh", "checkMesh", "decomposePar", "gmsh", "gmshToFoam",
               "postProcess", "reconstructPar", "setExprFields", "topoSet", "vtkUnstructuredToFoam"]

[tool.blockMesh]                    # one zone-free hex block: R1, B3, E1, N1
produces = ["constant/polyMesh", "constant/polyMesh/boundary", "constant/polyMesh/faces",
            "constant/polyMesh/neighbour", "constant/polyMesh/owner", "constant/polyMesh/points"]
[tool.gmshToFoam]                   # plus constant/polyMesh/sets/<Physical Volume>, which the record names (B3, BB2)
produces = ["constant/polyMesh", "constant/polyMesh/boundary", "constant/polyMesh/faces",
            "constant/polyMesh/neighbour", "constant/polyMesh/owner", "constant/polyMesh/points",
            "constant/polyMesh/cellZones", "constant/polyMesh/faceZones", "constant/polyMesh/pointZones"]

[environment.source]                # bashrc sourcing has one implementer, so it stays Python
python = "omnidriver.openfoam.openfoam_environment:load_openfoam_environment"
flag = "--environment-source"
env = "OPENFOAM_BASHRC"
[[environment.variable]]
name = "WM_PROJECT_DIR"
level = "error_if_commands"         # missing_openfoam_env; a warning when the plan runs nothing
[[environment.variable]]
name = "WM_PROJECT_VERSION"
level = "warning"                   # partial_openfoam_env
[[environment.variable]]
name = "FOAM_USER_LIBBIN"
level = "warning"

[launch.parallel]                   # N is the case's own decomposition, never restated (§12)
ranks.case = "system/decomposeParDict:numberOfSubdomains"
launchers = ["mpirun"]
pre = [{ id = "{step}.decompose", command = ["decomposePar", "-force"], consumes = ["system/decomposeParDict"] }]
wrap = ["{launcher}", "{command}", "{args}", "-parallel"]
post = [{ id = "{step}.reconstruct", command = ["reconstructPar"] }]
# -force: sweeps reuse a case root, so an earlier case's processor*/ remains (decomposePar.C: a full rmDir)

[case]
marker = ["system/controlDict"]     # the owner's rule
roles = ["openfoam.control_dict", "openfoam.discretisation", "openfoam.solver_settings", "openfoam.decomposition",
         "openfoam.mesh_generation", "openfoam.case_directory", "openfoam.entrypoint", "openfoam.cleanup"]   # was profile.py
input_roots = "omnidriver.openfoam.time_selection:input_roots"   # mirrors Time::setControls
[[case.document]]
glob = "system/controlDict"
codec = "openfoam_dictionary"
role = "openfoam.control_dict"
required = "always"
[[case.document]]
glob = "constant"
role = "openfoam.case_directory"
required = "always"
[[case.document]]
glob = "Allrun"
role = "openfoam.entrypoint"
required = "conditional"
[[case.document]]
glob = "system/*"
codec = "openfoam_dictionary"
[[case.document]]
glob = "constant/**"
codec = "openfoam_dictionary"
[case.generated]                    # was case_runtime_conventions.py; core's own names are not repeated (O15)
directories = ["postProcessing", "logs", "cachedCasePostProcessing", "polyMesh", "archivedPostProcessing", "results"]
directory_prefixes = ["driverPostProcessingArchive"]
file_prefixes = ["log."]
suffixes = [".foam", ".msh", ".geo"]
preserved_suffixes = [".geo.template"]
case_scripts = ["Allrun", "Allclean", "Allrun.pre", "Allrun.post"]
replicas = ["processor*"]
instances = '^-?\d+(\.\d+)?(e[+\-]?\d+)?$'
preserved_instances = ["0"]

[codec.openfoam_dictionary]
python = "omnidriver.openfoam.codec:OpenFOAMDictionaryCodec"     # mutators + foam_backend + literals + case_rendering

[catalog]
unvalidated = true                  # OpenFOAM keys are written as asked and flagged unvalidated (owner rule)

[output.openfoam_probes]
reader = "omnidriver.openfoam.probes:ProbesReader"
unit_from = "field"                 # a solver declares each probed field's unit

[python]
codec = ["omnidriver.openfoam.codec", "omnidriver.openfoam.mutators", "omnidriver.openfoam.foam_backend",
         "omnidriver.openfoam.literals", "omnidriver.openfoam.effective_dictionary", "omnidriver.openfoam.case_rendering",
         "omnidriver.openfoam.apply_overrides", "omnidriver.openfoam.case_planning"]
reader = ["omnidriver.openfoam.probes", "omnidriver.openfoam.time_selection", "omnidriver.openfoam.mesh_geometry",
          "omnidriver.openfoam.dict_keys_scanner", "omnidriver.openfoam.case_dict_keys", "omnidriver.openfoam.function_object_fields"]
derived = ["omnidriver.openfoam.axes.block_mesh_resolution", "omnidriver.openfoam.mesh_provisioning"]
hooks = ["omnidriver.openfoam.hooks"]   # FOAM_APPBIN installed-app check, stale_build, openfoam_environment, dict_builder
```

`gmsh` is in the OpenFOAM command set today (`command_authorization.py`) even
though the owner put gmsh outside OpenFOAM's layer (5g Q2). It stays there in
this design, because moving it changes command authorization for four
records. D14 asks whether to move it into cardiacFOAM's `auxiliary`.

#### cardiacFOAM on top

```toml
# packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/solver.toml
[solver]
id = "org.cardiacfoam"
name = "cardiacFoam"
version = "0.1.0"
api_version = "2"
requires = ["org.omnidriver.openfoam.environment"]
guidance = "guidance.md"
records = "records/*.toml"

[commands]
solve = ["cardiacFoam"]
auxiliary = ["gradientReconstructionOrder"]
utilities = "utilities/*/utility.manifest.toml"     # the 12 manifests, unchanged

[environment]                       # the backend contract, moved verbatim from plugin.yaml `runtime:`
bashrc_env = "OPENFOAM_BASHRC"
[environment.backend]
required = true
selection_env = "DRIVERFOAM_CARDIACFOAM_BACKEND"
python = "omnidriver.cardiacfoam.runtime_profile:configure_runtime_environment"
[environment.backend.common]
libraries = ["libelectroModels", "libionicModels", "libgenericWriter", "libactiveTensionModels"]
[environment.backend.lightweight]
define = "USE_LIGHTWEIGHT_PHYSICSMODEL=1"
libraries = ["libphysicsModel"]
forbidden = ["libsolids4FoamModels", "libelectroMechanicalModels"]
[environment.backend.full]
define = "USE_LIGHTWEIGHT_PHYSICSMODEL=0"
source = "solids4foam"
libraries = ["libsolids4FoamModels", "libelectroMechanicalModels"]
forbidden = ["libphysicsModel"]

[case]
regions = "omnidriver.cardiacfoam.physics_layout:regions"      # physics_layout.json: roles to regions
legacy_marker = "constant/electroProperties*"                   # case folders only; goes at step C
[[case.document]]
glob = "constant/electroProperties"
role = "plugin.configuration"
required = "always"
[[case.document]]
glob = "constant/physicsProperties"
role = "plugin.configuration"
required = "always"
# ... the rest of plugin.yaml's case_profile, unchanged ...

[catalog]
python = "omnidriver.cardiacfoam.record_key_validation:record_key_validator"   # dictionary semantics; the catalog is Python today

[output.openfoam_probes.field]
activationTime = { unit = "s", sentinels = [-1.0], sampling = "cell-containing" }   # Q1-Q4

[quantities]
map = "quantities.toml"
vocabulary = "omnidriver.electrophysiology"

[python]
rule = ["omnidriver.cardiacfoam.validation", "omnidriver.cardiacfoam.record_key_validation",
        "omnidriver.cardiacfoam.solver_coupling", "omnidriver.cardiacfoam.physics_layout"]
derived = ["omnidriver.cardiacfoam.records.derived"]
hooks = ["omnidriver.cardiacfoam.cardiacfoam_plugin"]   # dictionaries, synthesis, the factory path until step C

```

`cxx_mapping` stays under `[solver]` exactly as it is in the YAML.

### 2.5 Records as data

A record TOML is `TutorialRecord` spelled in data:

| TOML | `TutorialRecord` field |
|---|---|
| `name` | `name` |
| `native_case` | `native_case_relpath` |
| `[[step]]` | `workflow_steps` (`step_id`, `command`, `consumes`, `produces`, and `defaults` as `default_arguments`) |
| `[routes]` | `workflow_variants`, `variant_selector`, `default_variant`; per-route `admits` becomes `variant_constraints` |
| `[[axis]]` | `axes` |

**An axis is one of three kinds, and never an expression language:**
1. **substitution.** `arguments.<step> = [...]` and/or `[[axis.patch]]`
   (`document`, `key`, `value`, `kind`), with `{value}` the only placeholder.
   `choices = [...]` gives an enum. This covers:
   - openCARP's `dx`;
   - cardiacFOAM's `dimension` (a `-dict` argument plus the `bidomainSolverCoeffs.dimension` patch);
   - every "replace a default argument" axis (`replaces = "<step>:<key>"`).
2. **derived.** `resolve = "module:function"` with `with = {…}` keyword
   arguments. The function has today's `AxisFunction` signature. This is where
   a tutorial's derived-value functions live, as the owner's pointer rule
   allows:
   - blockMesh counts from `dx` over the document's own extent;
   - `lc = 1/N`;
   - the ionic model's stimulus amplitude;
   - the S1–S2 end time.
3. Every axis may carry `unit` and `quantity` (§3). With a `unit`, a study may
   write `"0.5 mm"`, and core converts it to the axis unit through `UNITS`
   before `resolve` runs. Without one, the axis takes plain values as today.

`produces` on a step adds to its command's `[tool.<command>] produces`.
`{ path, format }` is `ProducedPath`.

**The bath record under this design, whole.** Today it is 169 lines: 80 code
and 83 prose.

```toml
# records/manufacturedBathBidomain.toml. Native manufacturedSolutions/bathBidomain;
# its Allrun and regression/regressionTest.sh. Outputs observed: cardiacfoam.md BB1-BB2.
name = "manufacturedBathBidomain"
native_case = "manufacturedSolutions/bathBidomain"

[routes]
select = "mesh"
default = "hex"
hex = ["mesh", "topoSet", "setConductivity", "solve"]
tet = ["gmsh", "gmshToFoam", "checkMesh", "setConductivity", "solve", "interfaceMetrics"]
[routes.admits.tet]
dimension = ["3D"]                  # the tet template is a 3D box

[[axis]]
name = "dimension"
kind = "enum"
choices = ["1D", "2D", "3D"]
arguments.mesh = ["-dict", "system/blockMeshDict.{value}"]
[[axis.patch]]
document = "constant/electroProperties"
key = "bidomainSolverCoeffs.dimension"
value = '"{value}"'
kind = "word"

[[axis]]
name = "numberCells"
kind = "integer"
resolve = "omnidriver.openfoam.axes:block_mesh_resolution"
with = { documents = ["system/blockMeshDict.1D", "system/blockMeshDict.2D", "system/blockMeshDict.3D"], expected_blocks = 3, rule = "keep_ones" }

[[axis]]
name = "tetNumberCells"
kind = "integer"
resolve = "omnidriver.cardiacfoam.records.derived:gmsh_lc_from_cells"   # -setnumber lc 1/N (G5)
with = { step = "gmsh" }

[[step]]
id = "mesh"
command = ["blockMesh"]
defaults = { "-dict" = ["system/blockMeshDict.1D"] }     # regression/regressionTest.sh
consumes = ["system/blockMeshDict.1D", "system/blockMeshDict.2D", "system/blockMeshDict.3D", "system/controlDict"]

[[step]]
id = "topoSet"                      # BB1
command = ["topoSet"]
consumes = ["system/topoSetDict"]
produces = ["constant/polyMesh/cellZones", "constant/polyMesh/sets/bath", "constant/polyMesh/sets/bathCells",
            "constant/polyMesh/sets/myocardium", "constant/polyMesh/sets/myocardiumCells"]

[[step]]
id = "gmsh"
command = ["gmsh", "-3", "setup/studies/tetConvergence/three_domain_box.geo.template", "-o", "three_domain_box.msh", "-format", "msh2"]
consumes = ["setup/studies/tetConvergence/three_domain_box.geo.template"]
produces = ["three_domain_box.msh"]

[[step]]
id = "gmshToFoam"                   # BB2: the template's two Physical Volumes
command = ["gmshToFoam", "three_domain_box.msh"]
consumes = ["three_domain_box.msh"]
produces = ["constant/polyMesh/sets/myocardium", "constant/polyMesh/sets/bath"]

[[step]]
id = "checkMesh"
command = ["checkMesh"]

[[step]]
id = "setConductivity"              # BB1/BB2: 0/ is created to hold the field (C11)
command = ["setTorsoOrganConductivityField"]
consumes = ["system/setTorsoOrganConductivityFieldDict"]
produces = ["0", "0/bodyAndOrgansConductivity"]

[[step]]
id = "solve"
command = ["cardiacFoam"]
consumes = ["system/controlDict", "system/fvSchemes", "system/fvSolution",
            "constant/physicsProperties", "constant/electroProperties"]
produces = ["constant/electroProperties.withDefaultValues", "postProcessing/*_cells.dat"]

[[step]]
id = "interfaceMetrics"
command = ["bathBidomainInterfaceMetrics", "-latestTime"]
produces = ["postProcessing/bathBidomainInterfaceMetrics.csv"]
```

**The bath record is 82 lines of TOML, with no Python and no prose beyond one
evidence tag per fact.** Where its 83 prose lines go:

| prose | destination |
|---|---|
| the migration history ("Replaces …", "Reworked 2026-09-26 …") | already in `git log` and the 5.4a report; deleted |
| the facts behind `produces` | already `cardiacfoam.md` BB1/BB2; a tag points there |
| the FDA-variant rule (whole-dictionary replacement) | already BB4/BB5; its one-line consequence goes to `guidance.md` |
| `phiERefPoint` on a cell face | solver-learning BB3 (already logged), one line in `guidance.md` ("choose a point in a cell interior at every resolution the study uses"; owner Q5, promised and never added), and a native issue to the owner. Nothing about it is code, and the record does not mention it |

### 2.6 What stays Python, and where

| package | stays Python | why |
|---|---|---|
| core | `solver_description.py` (the interpreter: about 250 code lines in S1 and about 230 more in S3) and `record_description.py` (TOML → `TutorialRecord`, about 120); core's `json_document` codec (about 60) for the toy; every existing mechanism in §1.1 | the interpreter itself |
| OpenFOAM | the dictionary codec (six modules, 3,396 lines); `time_selection`; `probes` (+ `ProbesReader`, about 40); `mesh_geometry`; the C++ scanners; `block_mesh_resolution` with named rules (`keep_ones`, `explicit`, `from_dx`); `openfoam_environment` (sourcing); the `stale_build` and `FOAM_APPBIN` checks | codec, reader, derived values, and logic with one implementer |
| cardiacFOAM | the catalogs (`dict_entries_catalog`, `ionic_model_catalog`, `active_tension_catalog`: Python data until the future catalog step); `validation.py` V1–V4 and V6–V8; `record_key_validation`; `physics_layout.py`; `runtime_profile`; `dict_builder`/`overrides` (synthesis and generic-case paths); `detection`; `records/derived.py` | cardiacFOAM rules and logic; data that is not converted in this design |
| openCARP | `par_format` (+ `ParCodec`, about 30 lines of today's `plugin.py`); `lat_reader`; `validation` (F14 ownership, F2 `check_indices`); `catalog`, `catalog_generation` | codec, reader, and binary-specific rules |
| electrophysiology | `relations.py`, `rules.py` (§3; about 120 code lines) | science functions |

---
## 3. The science layer

### 3.1 The problem it solves, measured

Today one benchmark request cannot be written once for both solvers:
- `campaign.sh` carries per-solver translation tables:
  - `dx_value`: `cardiacfoam:0.5 → 0.0005` (m), `opencarp:0.5 → 500.0` (µm);
  - `dt_where`: `system/controlDict:deltaT=1e-05` against `nversion.par:dt=10.0`.
- It also carries a per-solver `--parallel` branch.
- The check that both solvers solve the *same problem* was done by hand, as
  `cardiacfoam.md` section S. That check found the benchmark's worst fact:
  cardiacFOAM's `TNNPcompactBatched` is TNNP **2004** (`cardiacfoam.md` S1), and the paper
  specifies **2006**. No data anywhere would have refused a "TNNP 2006"
  request to cardiacFOAM.

Core may not name any of this (`check-import-boundaries.py`, empty waivers;
`test_core_declares_no_phase_vocabulary`). So the vocabulary needs a home that
both solver plugins can see and core cannot.

### 3.2 Where it lives: `omnidriver-electrophysiology`

The alternatives, compared:

| option | for | against |
|---|---|---|
| **A new package `omnidriver-electrophysiology`** (import `omnidriver.electrophysiology`), a dependency of the openCARP and cardiacFOAM plugins | one home for quantity ids, units, ionic-model identities and relations; both plugins validate against it; it is installable from a wheel; the import gate can give it a row | one more package |
| the vocabulary in `benchmarks/` beside the references | no package | plugins cannot validate their maps against it at load time; rules would have no code home; a wheel install cannot see it |
| inside cardiacFOAM, with openCARP importing it | no package | openCARP may not import cardiacFOAM (import gate), and the vocabulary is not cardiacFOAM's |
| generic physics in core (units only) | S/m is not cardiac | quantity *names* such as `membrane.capacitance` are EP vocabulary, so core would carry cardiac words |

**Recommendation: the package.** It starts as data plus about 120 code lines.
- **Import-gate row:** it may know EP quantities, units and model identities. It must not import `omnidriver.openfoam`, `omnidriver.cardiacfoam` or `omnidriver.opencarp`, and it names no solver key or file format.
- **What core gains is only a mechanism.** An optional `quantity_map` seam
  resolves quantity-named study keys and reads mapped values. Core never
  learns a quantity name. It loads the vocabulary from the package that a
  map's `vocabulary =` names, and includes that vocabulary's digest in the
  stack identity. The toy gets a toy vocabulary in its test directory, so the
  mechanism is tested with no cardiac word.

### 3.3 What the package holds

`science.toml`, **data**:

```toml
# Units the EP quantities need. Core keeps time and length; it accepts extensions
# with integer factors in the dimension's smallest listed unit (the rule of core/quantities/units.py).
[units]
"S/m"    = ["conductivity", 10000]          # base: uS/cm
"mS/cm"  = ["conductivity", 1000]
"uS/cm"  = ["conductivity", 1]
"F/m2"   = ["capacitance_per_area", 100]    # base: uF/cm2
"uF/cm2" = ["capacitance_per_area", 1]
"1/m"    = ["inverse_length", 1]
"1/cm"   = ["inverse_length", 100]
"1/mm"   = ["inverse_length", 1000]
"1/um"   = ["inverse_length", 1000000]
"A/m3"   = ["current_per_volume", 1]        # 1 uA/cm3 = 1 A/m3
"uA/cm3" = ["current_per_volume", 1]
"A/m2"   = ["current_per_area", 100]        # base: uA/cm2
"uA/cm2" = ["current_per_area", 1]
"V"      = ["voltage", 1000]
"mV"     = ["voltage", 1]

# Inputs: what a study may vary by name.
[quantity."mesh.spacing"]
dimension = "length"
[quantity."time.step"]
dimension = "time"
[quantity."time.end"]
dimension = "time"
# Fixed problem parameters: what the problem-identity report compares (section S).
[quantity."membrane.capacitance"]
dimension = "capacitance_per_area"
[quantity."surface_to_volume"]
dimension = "inverse_length"
[quantity."conductivity.intracellular"]
dimension = "conductivity"
shape = "fibre_frame"                       # (along, transverse, normal)
[quantity."conductivity.extracellular"]
dimension = "conductivity"
shape = "fibre_frame"
[quantity."conductivity.monodomain"]
dimension = "conductivity"
shape = "fibre_frame"
[quantity."stimulus.strength"]
dimension = "current_per_volume"
[quantity."stimulus.strength_per_area"]
dimension = "current_per_area"
[quantity."stimulus.duration"]
dimension = "time"
[quantity."initial.vm"]
dimension = "voltage"
[quantity."activation.threshold"]
dimension = "voltage"
[quantity."model.kind"]
kind = "identity"
choices = ["monodomain", "bidomain", "eikonal", "single_cell"]
[quantity."ionic_model"]
kind = "identity"
table = "ionic_model"
[quantity."cell_type"]
kind = "identity"
choices = ["epi", "endo", "mid"]
# Outputs: what a comparison names.
[quantity."activation_time"]
dimension = "time"
output = true

# Model identities. A solver's map points its model names here, with evidence.
# Identity is "which published model", nothing more: what each solver's implementation
# supports stays in that solver's catalog, so no fact has two homes.
[ionic_model.tentusscher_panfilov_2006]
citation = "ten Tusscher & Panfilov, Am J Physiol Heart Circ Physiol 291:H1088 (2006)"
[ionic_model.tentusscher_panfilov_2004]
citation = "ten Tusscher, Noble, Noble & Panfilov, Am J Physiol Heart Circ Physiol 286:H1573 (2004)"

# Relations: a quantity another solver states directly, derived from ones this solver states.
[[relation]]
defines = "conductivity.monodomain"
from = ["conductivity.intracellular", "conductivity.extracellular"]
function = "omnidriver.electrophysiology.relations:harmonic_mean"    # per direction
[[relation]]
defines = "stimulus.strength"
from = ["stimulus.strength_per_area", "surface_to_volume"]
function = "omnidriver.electrophysiology.relations:product"

# Rules: what a combination of quantities requires, checked at plan time as diagnostics.
# The rule is shared; the data it reads (which cell types a model supports) stays each solver's.
[[rule]]
id = "cell_type_in_model"
reads = ["ionic_model", "cell_type"]
supported_by = "map"                        # each solver's map says where its supported list lives
check = "omnidriver.electrophysiology.rules:cell_type_in_model"
```

`relations.py` and `rules.py` hold one small function each (about 80 code
lines in total). What they hold, and where it comes from:

| EP content | kind | taken from |
|---|---|---|
| `cell_type_in_model` | rule | the logic of V5 `_evaluate_tissue_compatibility`. It is **moved**, and V5 is deleted from `validation.py` in the same step. Its data stays per solver: cardiacFOAM's map names `ionic_model_catalog`'s `compatible_tissues`, where a manufactured-only model answers "no list", which skips the rule as V5 does today |
| `harmonic_mean` | relation | openCARP's `bidm_eqv_mono` (J2) |
| `product` | relation | openCARP's transmembrane stimulus, applied in µA/cm² and scaled by χ (J2) |
| `s1_s2_times(s1, n_s1, s2, n_s2)` | derived value in time quantities | `records/s1_s2_protocol_axis.py`'s `writeAfterTime`/`endTime` arithmetic. cardiacFOAM's axis keeps only its key paths |

**Considered and not moved, because each would give a fact two homes:**
- "mono/bidomain need χ and Cm" and "bidomain needs σi, σe and a potential
  reference". These are cardiacFOAM catalog relations (`required_when`), and
  cardiaccore's `co_required_with` on the same six entries. An EP copy would
  fire beside the catalog on every cardiacFOAM case. openCARP's catalog has
  defaults for all of them, so the rules would never bite there either. They
  move only if a third solver needs them, and then the catalog relation is
  deleted in the same step.

**Not moved; these stay cardiacFOAM:**
- V1/V2 and the Purkinje coupler table: cardiacFOAM's model names and couplers;
- V4 heterogeneity ranges;
- V6 personalized templates;
- V7 the anisotropic/verifier relation (owner Q11);
- V8 PVJ resistance.

These are features of one solver's C++, not shared science.

### 3.4 How a solver maps onto it: `quantities.toml`

Each entry says where the quantity lives in *this* solver, in what unit, and
on what evidence. It takes one of five forms:

| form | meaning |
|---|---|
| `axis = "<name>"` | the record's axis; the axis's own `unit` applies |
| `key = "<document>:<key>"` (or `keys = [...]` for a `fibre_frame`) | a case key, with `unit` |
| `fixed = { value, unit }` | a constant compiled into the binary |
| `relation = "<id>"` | derived from other mapped quantities |
| `identity = { <solver word> = "<vocabulary id>" }` | for identities |

Every form carries `evidence`. The **frame** (which solver axis is the
problem's along/transverse/normal, and where the origin is) is **not** in the
map. It is a fact about a case and a reference, so it stays in the
benchmark's pairing file (audit B3). There the agent states it once, as the
owner's rule requires: "the pairing is the agent's step".

**The worked example: `cardiacfoam.md` section S as data.**

```toml
# packages/omnidriver-opencarp/src/omnidriver/opencarp/quantities.toml
[input."mesh.spacing"]
axis = "dx"                                                   # um (F3)
[input."time.step"]
axis = "dt"                                                   # us
[input."time.end"]
axis = "tend"                                                 # ms
[read."model.kind"]
key = "nversion.par:bidomain"
identity = { "0" = "monodomain", "1" = "bidomain" }
[read."membrane.capacitance"]
fixed = { value = 1.0, unit = "uF/cm2" }
evidence = "opencarp.md J2 (electrics.cc)"
[read."surface_to_volume"]
key = "nversion.par:imp_region[0].cellSurfVolRatio"
unit = "1/um"
evidence = "cardiacfoam.md S"
[read."conductivity.intracellular"]
keys = ["nversion.par:gregion[0].g_il", "nversion.par:gregion[0].g_it", "nversion.par:gregion[0].g_in"]
unit = "S/m"
[read."conductivity.extracellular"]
keys = ["nversion.par:gregion[0].g_el", "nversion.par:gregion[0].g_et", "nversion.par:gregion[0].g_en"]
unit = "S/m"
[read."conductivity.monodomain"]
relation = "conductivity.monodomain"
when = { key = "nversion.par:bidm_eqv_mono", equals = "1" }   # catalog default 1 (J2)
[read."stimulus.strength_per_area"]
key = "nversion.par:stim[0].pulse.strength"
unit = "uA/cm2"
[read."stimulus.strength"]
relation = "stimulus.strength"
[read."stimulus.duration"]
key = "nversion.par:stim[0].ptcl.duration"
unit = "ms"
[read."activation.threshold"]
key = "nversion.par:lats[0].threshold"
unit = "mV"
[read."ionic_model"]
key = "nversion.par:imp_region[0].im"
identity = { tenTusscherPanfilov = "tentusscher_panfilov_2006" }
evidence = "cardiacfoam.md S (limpet tenTusscherPanfilov.model)"
[read."cell_type"]
key = "nversion.par:imp_region[0].im_param"
identity = { "flags=EPI" = "epi" }
supported = { tenTusscherPanfilov = ["flags=EPI"] }    # only what section S verified; ENDO/MCELL wait on a read of the limpet model
[read."initial.vm"]
unmapped = "singlecell.sv is a state file with no reader yet; S reads -85.23 mV by hand"
[output."activation_time"]
format = "opencarp_lat_per_node"
```

```toml
# packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/quantities.toml
[input."mesh.spacing"]
axis = "dx"                                                   # m
[input."time.step"]
key = "system/controlDict:deltaT"
unit = "s"
[input."time.end"]
key = "system/controlDict:endTime"
unit = "s"
[read."model.kind"]
key = "constant/electroProperties:myocardiumSolver"
identity = { monodomainSolver = "monodomain", bidomainSolver = "bidomain", eikonalSolver = "eikonal", singleCellSolver = "single_cell" }
[read."membrane.capacitance"]
key = "constant/electroProperties:<solver>Coeffs.cm"
unit = "F/m2"
[read."surface_to_volume"]
key = "constant/electroProperties:<solver>Coeffs.chi"
unit = "1/m"
[read."conductivity.monodomain"]
key = "constant/electroProperties:monodomainSolverCoeffs.conductivity"
unit = "S/m"
shape = "symm_tensor_diagonal"
[read."stimulus.strength"]
key = "constant/electroProperties:<solver>Coeffs.externalStimulus.stimulusIntensity"
unit = "A/m3"
[read."stimulus.duration"]
key = "constant/electroProperties:<solver>Coeffs.externalStimulus.stimulusDuration"
unit = "s"
[read."activation.threshold"]
key = "constant/electroProperties:<solver>Coeffs.activationThreshold"
unit = "V"
[read."ionic_model"]
key = "constant/electroProperties:<solver>Coeffs.ionicModel"
identity = { TNNPcompactBatched = "tentusscher_panfilov_2004", TNNP = "tentusscher_panfilov_2004" }
evidence = "cardiacfoam.md S1 (TNNP_2004Batch.H, TNNP_2004.H: 17 states, 2004 constants)"
[read."cell_type"]
key = "constant/electroProperties:<solver>Coeffs.tissue"
identity = { epicardialCells = "epi", endocardialCells = "endo", mCells = "mid" }
supported = "omnidriver.cardiacfoam.ionic_model_catalog:compatible_tissues"   # per model; None for manufactured-only
[read."initial.vm"]
default = { value = -84.0, unit = "mV" }
unless_file = "0/Vm"
evidence = "cardiacfoam.md S2: the myocardiumDomain constructor's default"
[output."activation_time"]
format = "openfoam_probes"
field = "activationTime"
```

`<solver>Coeffs` resolves through the value of `myocardiumSolver`. That is
the convention `record_key_validation` already applies. The map reuses it and
restates no scope.

The cardiacFOAM spellings are the catalogs' own:
- `epicardialCells`/`endocardialCells`/`mCells` in `ionic_model_catalog.py`;
- `$ELECTRO_MODEL_COEFFS.activationThreshold` in `dict_entries_catalog.py`.

S7 adds `test_quantity_map_keys_are_catalogued`, so each map entry is checked
against its solver's catalog. For OpenFOAM `system/*` keys, which have no
catalog, it checks against the native case instead.

**What that data does, with no per-solver code:**
1. **Solver-neutral inputs.** A study key that is a quantity name (it contains
   a `.` and no `:`; axis names are refused a `.` at load) resolves through
   the stack's map to an axis or a key, and its value (`"0.01 ms"`) is
   converted:
   - `time.step = "0.01 ms"` becomes `dt = 10` µs for openCARP and `system/controlDict:deltaT = 1e-05` s for cardiacFOAM.

   `campaign.sh`'s `dx_value`/`dt_where` tables are deleted.
2. **Problem identity** (section S, automated).
   `omnidriver describe --quantities` stages a record case, reads every
   `read.` entry, converts it to the vocabulary's unit and applies relations.
   Given two solvers, it reports:
   - each quantity with its value, unit, evidence, and match/mismatch within a stated tolerance;
   - every `unmapped` quantity, with its reason.

   On the Niederer pair it would report, from the S table:
   - σ monodomain, χ, Cm, stimulus strength and threshold: match (σ to 1e-10, stimulus to 0.01 %);
   - `ionic_model`: `tentusscher_panfilov_2006` against `tentusscher_panfilov_2004`, **mismatch**;
   - `initial.vm`: openCARP unmapped, cardiacFOAM −84 mV.
3. **Rules apply wherever the variables are mapped.** This is how openCARP
   gains cardiacFOAM's rules **without rewriting them**. A rule function runs
   on quantity values, so it applies to any solver whose map covers its
   `reads`:
   - `cell_type_in_model` (V5's logic) refuses by name a study that sets
     `imp_region[0].im_param "flags=XYZ"` on openCARP, which today reaches
     the binary.

   The identity map refuses requests on its own: a quantity-named request for
   `ionic_model = tentusscher_panfilov_2006` to cardiacFOAM is refused,
   because no cardiacFOAM model maps to that identity (`cardiacfoam.md` S1). The request fails
   at plan time instead of running a different cell model.
4. **Outputs by quantity.** A comparison request names `activation_time`, and
   each solver's map names the artifact format. So requests stop naming
   positional artifact ids (`record.solve.2`, audit §4.2.6). With B1 they name
   the case by its study values (`where`).

### 3.5 Deferred, deliberately

These are not needed for a two-solver EP benchmark request:
- traces, ECGs, APD and restitution curves as quantities (the results spec's scalar-at-point limit stays);
- a reader for `.sv` state files;
- frames as data (the pairing file holds them);
- rule coverage beyond `cell_type_in_model`. The χ/Cm and bidomain-completeness relations stay catalog relations (§3.3);
- the Purkinje coupling table as science;
- a mechanics vocabulary.

Electromechanics adds its own vocabulary file when the owner migrates TL-EM;
nothing here blocks that.

---
## 4. Content map

One row per module or mechanism. "Unchanged" is a destination. A row that
deletes something names where its content went, or why there is none. Steps
(S1–S10) are defined in §6.

### 4.1 Core

| existing | destination | step |
|---|---|---|
| `plugin_interface.py` | unchanged. The factory-shaped required members (`get_tutorial_catalog`, `validate_configuration`, `predict_data_artifacts`) become optional-neutral, so no plugin stubs them (final review M11). `_RETIRED_PLUGIN_MEMBERS` (about 35) is deleted: it guards a one-time rename, and every in-tree plugin is migrated, so it has no content | S1; the guard at S10 |
| `plugin_capabilities.py`, `provider_stack.py`, `capability_seams.py` | unchanged, plus one optional seam `quantity_map` (composed `single`) | S7 |
| `plugin_discovery.py` | unchanged, plus loading a supplied `solver.toml` path | S1 |
| `plugin_profile.py` | unchanged for cardiacCore's YAML. A `PluginProfile` is also built from a description's `[solver]`/`[case]` tables | S1 |
| `utility_catalog.py` | unchanged; cardiacFOAM's `[commands] utilities` points at the same manifests | — |
| `tutorial_records.py` | dataclasses unchanged. `AxisContract` gains optional `unit` and `quantity`. `sort_study_name` gains the quantity-name class. `variant_constraints` is kept and written as `[routes.admits]` | S2, S7 |
| `runtime/record_execution.py` | unchanged. The rank rule (§2.3.1) replaces the two per-solver copies. The positional `record_artifact_id` stays for provenance, but requests stop using it (B1) | S3, S8 |
| `runtime_records.py` | unchanged; the OpenFOAM duplicate is deleted (O15) | S4 |
| `quantities/units.py` | the table is unchanged; it accepts extensions from a vocabulary (integer factors, same rule) | S7 |
| `runtime/workflow*.py`, `case_write.py`, `case_transaction.py`, `strict_planning.py`, `specs/*`, `sweep/*`, CLI, provenance, remediation, post-processing | unchanged. The CLI gains `--launcher` and `describe --quantities` | S3, S7 |
| `conformance/` | gains `record_sweep`/`record_case`/`artifact_by_format`/`supplied_tree` (R1) and C13/C14 (R5). `ConformanceTarget.solver_command` is read from `[commands] solve`, and `environment` is deleted (`{}` in all six targets, so it has no content) | S6 |
| `compatibility.py` | unchanged, except the factory fallbacks (`legacy_route_sweep_case`, `legacy_materialize_sweep_case`), which go with the last factory tutorial (after 5.5) | after S10 |
| factory wiring (`spec_factories`, `make_spec`, `sweep_routing.py`, `sweep_materialize.py`, `tutorial_contracts.py`, `tutorials_display.py`, factory branches in `registry`/`introspection`/`sweep_runner`) | kept while Purkinje and 1D3D (5.5) are factory tutorials. It is mechanism, not content. Deleted whole when 5.5 migrates | after S10 |
| new: `solver_description.py`, `record_description.py`, `codecs/json_document.py`, `schemas/solver-description.schema.json`, `schemas/record.schema.json` | the interpreter | S1 |
| toy: `E2ERecordPlugin` (210), `parallel_toy.py` (47) | `tests/plugins/toy/solver.toml` plus `records/toyTutorial.toml` (S1); `[launch.parallel]` replaces `parallel_toy.py` (S3). The broken subclasses subclass the described toy. `MinimalTestPlugin` is kept for the tests that use it outside conformance. `quantity_toy.py` is kept (it tests the reader seam) | S1 |

### 4.2 OpenFOAM layer

| existing | destination | step |
|---|---|---|
| `environment.py` (hub, 379) | `DescribedPlugin` from `solver.toml`. Residual logic (`get_input_roots`, the `hex_cell_counts` special key path in the config reader) goes to `codec.py` and `time_selection`. The forwarding table disappears | S4 |
| `openfoam-environment.yaml` | `solver.toml` `[solver]`/`[case]`; `provides` is derived | S4 |
| `profile.py` (8 roles) | `[case] roles = [...]` in the OpenFOAM description, verbatim. The interpreter checks every `openfoam.*` role any stacked description uses against that list, so a misspelled role is still refused (the whitelist is content) | S4 |
| `parallel_execution.parallel_steps_for_record`, `_parallel_form`, `read_number_of_subdomains` | `[launch.parallel]` plus the core rank rule. The `-force` reason is kept as a TOML comment | S4 |
| `parallel_execution.solve_steps` | deleted with its last caller, pseudo-ECG's factory module. Its form is the template's | S9 |
| `case_runtime_conventions.py` | `[case.generated]`, verbatim; the core names it repeats are deleted (O15) | S4 |
| `command_authorization.py` | `[commands] environment` (data), plus the `FOAM_APPBIN`/`FOAM_USER_APPBIN` installed-app check in `hooks.py` | S4 |
| `openfoam_environment.py` | unchanged, named by `[environment] source` | — |
| `environment_preflight.py` | variables → `[[environment.variable]]`; `missing_executable` and `missing_mpi` → core's generic command check (the launcher is a step command after the parallel pass); `stale_build` stays in `hooks.py` | S4 |
| dict codec (`mutators`, `foam_backend`, `literals`, `effective_dictionary`, `case_rendering`, `apply_overrides`) | unchanged, fronted by a new `codec.py` (`OpenFOAMDictionaryCodec`, about 80 lines, which gathers the reader/comparator/renderer functions `environment.py` forwards today) | S4 |
| `dict_builder.py`, `mesh_geometry.py`, `dict_keys_scanner.py`, `case_dict_keys.py` | unchanged | — |
| `case_planning.py` | unchanged, except `plan_dict_block`, `plan_delta_t` and `plan_end_time`, which are deleted with their last callers (pseudo-ECG and the cable modules; `overrides.py` names them only in docstrings) | S9 |
| `axes/block_mesh_resolution.py` | kept. The three callbacks become named rules inside it (`keep_ones`, `explicit`, `from_dx`), so records name them from TOML. Its prose is cut to its contract (audit §2.9: 266 docstring lines on 96 code) | S5 |
| `mesh_provisioning.py` | unchanged | — |
| `tet_mesh_provisioning.render_tet_geo` | deleted with pseudo-ECG's factory module. Content: the `__LC__` render was replaced natively by `DefineConstant` (`60805b27`), and `lc` is an axis argument (G5) | S9 |
| `probes.py` | unchanged, plus `ProbesReader`, moved from cardiacFOAM with a field-declared unit | S4 |
| `function_object_fields.py` | unchanged, except the cardiac leak: `system/electro/controlDict` and the default region `"electro"` come from the stack's `[case] regions`, which cardiacFOAM supplies | S4 |
| `time_selection.py` | unchanged, named by `[case] input_roots`; prose cut (audit: 62 % prose) | S4 |

### 4.3 cardiacFOAM

| existing | destination | step |
|---|---|---|
| `plugin.yaml` | `solver.toml`. `runtime.backend` moves verbatim to `[environment.backend]`, and `cxx_mapping` to `[solver]`. The 68 comment lines on `provides` realness are deleted: `provides` is derived, so the disagreement they guarded cannot exist | S5 |
| `cardiacfoam_plugin.py` (598) | the hooks object for the members data does not cover: dictionaries, catalogs, `validate_configuration`, synthesis, and the factory path until it goes. Members answered by data leave it: commands, solve commands, redaction, tutorial records, the record key validator's wiring | S5 |
| `records/niederer_2011.py`, `manufactured_bidomain.py`, `manufactured_bath_bidomain.py`, `manufactured_eikonal_ecg.py`, `restitution_curves.py` | `records/*.toml`. Derived values go to `records/derived.py`: `gmsh_lc_from_cells`, the ionic-model amplitude lookup, `hex_cells_from_dx` (which wraps `cell_counts_from_dx` over the read extent). Evidence tags are kept as comments. The migration-history prose ("every write the old `_plan_case` made", about 150 lines in niederer2011) is deleted: it is in `git log` and the 5.4 reports. Every *fact* in it (the dx mapping, `-latestTime` restarting at instance `0`, the probe paths) is already in `cardiacfoam.md` N/Q or is now the TOML itself | S5 |
| `records/case_outputs.py` | `ELECTRO_PROPERTIES` is a literal in TOML; `POLY_MESH_OUTPUTS` and `gmsh_to_foam_outputs`' fixed part become the OpenFOAM `[tool.blockMesh]`/`[tool.gmshToFoam]` `produces`. The per-volume sets stay record data. `WITH_DEFAULT_VALUES` becomes a record literal on the solvers that write it (Q13 via P4 R4) | S4–S5 |
| `records/manufactured_solution_axes.py` | `dimension_axis` → a substitution axis in TOML. `hex_number_cells_axis` → `block_mesh_resolution` with `rule = "keep_ones"`. `tet_number_cells_axis` → `derived.gmsh_lc_from_cells`. `TET_DIMENSIONS` → `[routes.admits.tet]` | S5 |
| `records/ionic_model_axis.py` | `derived.ionic_model` (the catalog lookup and the no-amplitude refusal stay cardiacFOAM) | S5 |
| `records/s1_s2_protocol_axis.py` | the arithmetic goes to EP `relations:s1_s2_times`; the patch paths stay in `derived.s1_s2_protocol` | S5, S7 |
| `records/__init__.py` | the `records = "records/*.toml"` glob; the duplicate-name refusal stays in `build_tutorial_record_catalog` | S5 |
| `activation_probes.py` | the OpenFOAM `ProbesReader`, plus `[output.openfoam_probes.field] activationTime` (unit s, sentinel −1, cell-containing) | S4 |
| `validation.py` V5 | EP rule `cell_type_in_model`; the data stays in `ionic_model_catalog` | S7 |
| `validation.py` V1–V4, V6–V8 | unchanged | — |
| `dict_entries_catalog.py`, `ionic_model_catalog.py`, `active_tension_catalog.py`, `solver_coupling.py`, `common_dict_entries.py` | unchanged (the future catalog step). Fixed in S5 because each restates a fact: `HETEROGENEITY_MODELS` derived from `supports_heterogeneity`; the `sex` gate spelled `TWorldcompactBatched`; `validate_configuration`'s solver set read from the `myocardiumSolver` enum; `config_schema.py`'s tissue enum read from the catalog | S5 |
| `record_key_validation.py` | unchanged, named by `[catalog] python`. Region-aware documents (final review M3) come with electromechanics | — |
| `physics_layout.json` / `.py` | unchanged, plus `regions(case_root)` (about 5 lines over `region_of`) for `[case] regions`. The `electroMechanicalModel` row gains `"backend": "full"` when TL-EM migrates (§5) | S4; TL-EM |
| `runtime_profile.py` | unchanged; reads `[environment.backend]` instead of `plugin.yaml` `runtime:` | S5 |
| `runtime_evidence.py` | solve commands, redaction and the gmsh dependency → data; the library catalog and `libs` parsing stay | S5 |
| `command_authorization.py` | `[commands]`; utility manifests via `[commands] utilities` | S5 |
| `case_compatibility.py` | `[case] legacy_marker` plus `is_runnable_without_workflow`'s four files as `[case] runnable_without_workflow`. Both stay while case-folder entries exist | S5 |
| `dict_builder.py`, `overrides.py` (non-factory parts), `detection.py`, `system_templates.py`, `artifacts_predictor.py`, `case_introspection.py`, `planning_policy.py`, `mesh_*`, `own_context.py`, `named_catalogs.py`, `reports.py`, `config_schema.py`, `override_schema.py`, `run_document_config.py`, `sweep.py`, `dict_entries.py`, `generic_case_mutation.py`, `monorepo.py`, the C++ tooling | unchanged. These serve the generic-case and synthesize paths, which this design does not touch | — |
| `overrides.py` factory helpers (`merge_assignments`, `commit_case_overrides`, `resolve_entry_overrides`, `resolve_electro_property_{ensure,set}`) and dead ones (`remove_/ensure_electro_property_dict`, `normalize_entry_overrides`) | deleted with their last callers (the singleCell, pseudo-ECG and cable modules); the dead ones now. Their content is transaction plumbing that the record path replaced | S9, S10 |
| `spatial_pacing.py` | its `.12g` spatial stimulus formatting becomes the cable-restitution record's derived function if its native study needs it; otherwise it goes with the module | S9 |
| `tutorials/single_cell.py` + defaults | a `singleCell` TOML record; `IONIC_MODEL_CATALOG`'s amplitude through `derived.ionic_model` | S9 |
| `tutorials/cable_1d_cv_convergence.py` + defaults | a TOML record on the native cable case, with `dx` via `block_mesh_resolution` `from_dx` | S9 |
| `tutorials/cable_1d_restitution.py` + defaults | a TOML record. DI90 and S1–S2 timing → EP `s1_s2_times` plus a derived function. The two sidecar files (`.driverfoam_case_id`, `.cardiacfoam_protocol.json`) were already due for deletion (plan status 5.2): post-processing reads the case plus omniD's case record | S9 |
| `tutorials/manufactured_monodomain_pseudo_ecg.py` + defaults | a TOML record in the bidomain shape (hex `.3D` default plus the gmsh tet route); `solve_steps`, `render_tet_geo` and `plan_dict_block` die with it | S9 |
| `tutorials/manufactured_monodomain_total_lagrangian_em.py` + defaults | **retired** from the factory at S10: its default call raises today, and its content is native (§5). The owner migrates it as a record | S10 |
| `tutorials/manufactured_purkinje_graph.py`, `manufactured_monodomain_1d3d.py` | unchanged until S (supplied inputs); out of this design's scope | — |
| `tutorials/registry.py`, `ids.py`, `__init__`, `defaults/__init__`, `defaults/shared.py`, `generic_case.py`, `display.py` | registry and ids shrink to 5.5's two entries. `display.py` is unchanged: it serves records and factory tutorials alike, and its factory entries go with their tutorials (its dead preset names `TenTusscher`/`FentonKarma` are fixed in S5). `generic_case.py` stays (case folders) | S9–S10 |
| `guidance.md` | unchanged, plus the bath reference-point line; "Serial only" corrected (audit §4.1 item 7) | S5 |

### 4.4 openCARP

| existing | destination | step |
|---|---|---|
| `plugin.py` (207) | `solver.toml`, plus `ParCodec` (about 35 lines: the F1/F10 read refusals and the render loop) in `par_format.py`. The record key catalogue becomes core's generic catalog listing over `[catalog]`, filtered by the `rule` module's ownership (`read_documents`: only `+F` documents, minus keys the command line owns, as today) | S3 |
| `opencarp.yaml` | `solver.toml` `[solver]` | S3 |
| `environment.py` | `[commands]`, `[logs]`, `[[environment.probe]]` with `version` | S3 |
| `parallel.py` | `[launch.parallel]`, its `check`, and the core rank rule | S3 |
| `records/niederer_n_version.py`, `records/__init__.py` | `records/niedererNVersion.toml` | S3 |
| `validation.py` | keeps `read_documents` (now over TOML records and their `defaults`: P3 concern 2), F14 ownership and F2 `check_indices`. `_catalog_check` goes to core's generic catalog check (kind, menu, literal bounds), which is the same code, moved | S3 |
| `par_format.py`, `lat_reader.py`, `catalog.py`, `catalog_generation.py`, `opencarp_parameters.json`, `guidance.md` | unchanged (`guidance.md` gains `run.py`'s defaults and `mass_lumping`) | S3 |

### 4.5 Lost content (audit §4.1), restored

| # | content | restored as | step |
|---|---|---|---|
| 1 | `run.py`'s `--tend 50`, `--dt 20` µs, `--massLumping 0` (`run.py` 201–214, passed at 250–256) | the solve step's `defaults` plus the `tend`/`dt`/`massLumping` axes. The validator reads `defaults` first (P3 concern 2) | S3 (D2) |
| 2 | carputils solver options (`tools.carp_cmd` appends `settings.solver(...).args()`) | settled by two real runs (full options versus none) logged in `opencarp.md`. If they differ beyond tolerance, `defaults` gain the option-file arguments, with the files **supplied**, not found | S3 (D3) |
| 3 | the paper's diagonal activation profile (`run.py --plot`, cardiacFOAM's `system/Niedererlines`) | a declared quantity `activation_time` along a line: openCARP's LAT reader at the diagonal's points, and cardiacFOAM's `sampleLines` given the `openfoam_probes` format (its path is already produced). The reference's P1–P9 gains the diagonal points, pre-registered before the campaign run | S8 (D10) |
| 4 | bath's reference point, unsafe under `--parallel` | not code: one `guidance.md` line (owner Q5) and a native issue (move `phiERefPoint` into a cell interior). BB3 already logs it | S5 |
| 5 | restitutionCurves' BuenoOrovio default sweep (3 tissues × 21 S2 intervals, S1 2000 ms × 10; the pre-`46bd2f0` defaults) | a native study JSON, `setup/studies/buenoOrovio_restitution.json`, on `ionicModel`/`s1s2Protocol`, with the S2 list verbatim from `46bd2f0^` | S5 (native) |
| 6 | convergence-order aggregators (native ones read the old layout; bath's `summarize_coupling_study.py`) | an observed-order derivation in core quantities (`order(errors, spacings)`: solver-neutral numerical analysis, about 50 lines), plus a cardiacFOAM reader for the verifiers' `*_cells.dat` summaries. The READMEs' tables are then produced from a sweep | S9 |
| 7 | parallel references (Niederer 6 ranks) versus serial defaults; the stale "Serial only" guidance | the guidance is corrected; a study sets `parallel` where its reference was parallel | S5 |
| 8 | the explicit × implicit `solutionAlgorithm` sweep | a native niederer2011 study that varies `monodomainSolverCoeffs.solutionAlgorithm` | S5 (native) |
| 9 | carputils `mesher_opts` (`set_fibres(0,0,90,90)`, `-bath 0 0 0`, …) | read from carputils' source (installed at `/usr/local/lib/opencarp/share/carputils`) and logged. Arguments that are not the mesher's own defaults are added to the `mesh` step | S3 |
| 10 | native README drift | native edits, owner's branch | native |

---

## 5. Electromechanics: TL-EM without new core mechanisms

Read from native `omnid/tutorials-are-pointers`,
`tutorials/manufacturedSolutions/monodomainTotalLagrangianEM`, with
`git show`. The native case is region-split:
- `constant/physicsProperties` says `type electroMechanicalModel;`;
- `constant/electroMechanicalProperties` → `sequentialElectroMechanicalCoeffs { electroRegion electro; solidRegion solid; activeTensionModel ManufacturedElectromechanics; … verificationModel { type manufacturedElectromechanicsVerifier; … } }`;
- per-region documents are under `constant/{electro,solid}/` and `system/{electro,solid}/`;
- `0/solid/{D,f0,f0f}`;
- case-local C++ in `src/`, which `controlDict` loads as `"$FOAM_CASE/platforms/$WM_OPTIONS/lib/libmanufacturedMonodomainTotalLagrangianEM.so"`.

Its `Allrun`, serial branch, does:
1. It requires `libelectroMechanicalModels` in `FOAM_USER_LIBBIN`, i.e. the full solids4foam build.
2. It builds `src/` with `FOAM_USER_LIBBIN` set to the case's `platforms/$WM_OPTIONS/lib`, and on Darwin links `.dylib` → `.so`.
3. It runs `blockMesh` (the case ships no mesh).
4. It runs `cp -r constant/polyMesh constant/electro/polyMesh` and `cp -r constant/polyMesh constant/solid/polyMesh`.
5. On Darwin, it `find`s `libpetsc.dylib` into `DYLD_INSERT_LIBRARIES`.
6. It runs `cardiacFoam`.

Its parallel branch is `decomposePar -region electro`,
`decomposePar -region solid`, then `runParallel cardiacFoam`, with no
reconstruct. `regression/regressionTest.sh` rewrites the hex cells to
`20 20 20` and `deltaT` to `0.00224215`, then runs `Allrun`.

Today the factory module's default call raises: it writes
`electromechanicalVerificationModel.type`, but the C++ reads
`verificationModel.type`. The native file already holds the right key, so
the factory write was a wrong restatement of a native value. `display.py`
marks the tutorial "NOT CURRENTLY WORKING".

**What the owner writes to migrate it:**

1. **One record** (about 45 lines of TOML, zero Python):

```toml
# records/manufacturedMonodomainTotalLagrangianEM.toml. Native Allrun (serial) and
# regression/regressionTest.sh. Outputs: from a real run, logged in cardiacfoam.md (TL1).
name = "manufacturedMonodomainTotalLagrangianEM"
native_case = "manufacturedSolutions/monodomainTotalLagrangianEM"

[[axis]]
name = "numberCells"                # regressionTest.sh: "20 20 20"
kind = "integer"
resolve = "omnidriver.openfoam.axes:block_mesh_resolution"
with = { documents = ["system/blockMeshDict"], expected_blocks = 1, rule = "keep_ones" }
# deltaT is a direct study key, system/controlDict:deltaT (s); no axis.

[[step]]
id = "build"                        # the case-local library controlDict `libs` loads
cwd = "src"
command = ["Allwmake", "-s"]
produces = ["platforms"]            # TL1

[[step]]
id = "mesh"
command = ["blockMesh"]
consumes = ["system/blockMeshDict", "system/controlDict"]

[[step]]
id = "electroMesh"
command = ["cp", "-r", "constant/polyMesh", "constant/electro/polyMesh"]
produces = ["constant/electro/polyMesh"]

[[step]]
id = "solidMesh"
command = ["cp", "-r", "constant/polyMesh", "constant/solid/polyMesh"]
produces = ["constant/solid/polyMesh"]

[[step]]
id = "solve"
command = ["cardiacFoam"]
consumes = ["system/controlDict", "system/fvSchemes", "system/fvSolution",
            "system/electro/fvSchemes", "system/electro/fvSolution",
            "system/solid/fvSchemes", "system/solid/fvSolution", "system/solid/fvOptions",
            "constant/physicsProperties", "constant/electroMechanicalProperties",
            "constant/electro/electroProperties", "constant/solid/mechanicalProperties",
            "constant/solid/solidProperties", "constant/solid/dynamicMeshDict", "constant/solid/g",
            "0/solid/D", "0/solid/f0", "0/solid/f0f"]
produces = ["postProcessing/manufacturedElectromechanicsSummary.dat"]   # regressionTest.sh's SUMMARY_FILE; the rest by TL1
```

2. **One native change** in the owner's repository. `src/Allwmake` sets what
   the `Allrun` subshell sets today:
   - `FOAM_USER_LIBBIN` to the case's `platforms/$WM_OPTIONS/lib`, with `mkdir -p`;
   - the Darwin `.so` link.

   `Allrun` then calls `src/Allwmake -s`. The build step needs `cwd`, which
   the DAG already has (`runtime/workflow.py` validates `cwd`). A record step
   passes it through: one field in `record_description.py`, not a new
   mechanism.

   The alternative: `wmake -s libso src` with `wmake` added to the OpenFOAM
   commands, and the native `Make/files` `LIB` path changed. A real run (TL1)
   picks between them before the record is written, because it has to show
   two things:
   - how a case-local `Allwmake` resolves (core's `case_script_commands`
     resolves bare names);
   - where `$PWD` points inside `wmake`.
3. **One field of data.** `physics_layout.json`'s `electroMechanicalModel` row
   gains `"backend": "full"`. That models the relation between the physics
   type and `[environment.backend.full]`'s library list, which already exists.
   It replaces the `Allrun`'s `requireFullElectroMechanicalBuild`, and
   `runtime_profile` already refuses a missing library by name.
4. **One supplied variable** in cardiacFOAM's description:
   `[[environment.variable]] name = "DYLD_INSERT_LIBRARIES"`,
   `platform = "darwin"`, with purpose "libsolids4FoamModels needs
   `_PETSC_COMM_WORLD` at load (native Allrun)". The native `Allrun` `find`s
   the PETSc library, which is discovery, so omniD requires it supplied.
   `cardiacFoam` is executed directly, not through a script, so `env=`
   carries it (`_DYLD_VAR_NAMES` matters only for case scripts).
5. **`cp`** joins the OpenFOAM layer's `[commands] environment`. Copying
   `constant/polyMesh` into `constant/<region>/polyMesh` is OpenFOAM's
   multi-region convention; D12 covers it.
6. **The study.** `setup/driver_config.json` (legacy keys `dimensions`,
   `number_cells`, `dt_values`) is rewritten natively as a zip study on
   `numberCells` and `system/controlDict:deltaT`, like the 29 already
   rewritten.

**Nothing in core changes for a serial TL-EM run.** Study keys into region
documents (`constant/electro/electroProperties:…`) would need
`record_key_validation` to resolve a document's role through
`physics_layout.region_document` (final review M3: 25 hard-coded sites). That
is cardiacFOAM Python, and the TL-EM study above needs none of it: it only
touches `system/*`, which rule 2 accepts unvalidated.

**Parallel TL-EM needs one grammar item, deferred until then.** The native
form decomposes each region. The template would carry
`pre = [{ each = "region", command = ["decomposePar", "-region", "{region}"] }]`,
with `{region}` iterated over the stack's `[case] regions`. That is about 20
lines in the interpreter, and a real run must first settle two things:
- whether `reconstructPar -region` is needed for the summary file;
- which `decomposeParDict` the rank rule reads (the top-level one, the
  per-region ones, or all of them agreeing).

It is the only core addition electromechanics asks for, and it is not built
now. **Serial first is the native default** (`parallelRun=false`).

What the design already carries for electromechanics:
- `physics_layout` resolves region documents;
- the backend contract is data;
- region-split documents are ordinary paths in `consumes`;
- the solid fields are ordinary `produces`.

The only open electromechanics item is M3 (region-aware key validation). It
is needed only when a study varies region-document keys.

---

## 6. Migration order

Every step keeps every shape green:
- all packages;
- core alone;
- the rebuilt wheel;
- native (cardiacFOAM, with OpenFOAM sourced);
- native openCARP;
- the static gates.

Every step also keeps C1–C12, and C13/C14 from S6. Every step records the
plan's three numbers before and after (tutorials plus defaults; all package
source; all package tests), measured with the tutorials plan's command.

The deltas below are estimates from §1's measurements:
- code and prose are counted separately, as the AST classifier counts them;
- `data` is TOML/JSON;
- negative means deleted.

**What this order absorbs:**
- The drift audit's plan:
  - R1 and R5 land in S6;
  - R2 in S3 and S4;
  - R3 in S5, as `admits` (D8);
  - R4 and O15 in S4;
  - R6 as the prose rule applied to whatever each step moves (D13);
  - B1 in S2, S7 and S8;
  - B2 in S3;
  - B3 in S8.
- `2026-09-25-tutorials-are-pointers-remaining.md`'s open roadmap rows: 5.4b-P, 5.1, 5.2 and 5.3 in S9, and step C (EP scope) in S10.
- The PAR follow-up (one grammar) from `2026-09-26-core-generality.md`, in S3 and S4.
- `2026-09-26-results-as-quantities.md`'s positional-artifact concern (R1-M8, path-based ids), in S8.

**Outside it, unchanged:**
- 5.5 (Purkinje graph, 1D3D), which waits on S (supplied inputs);
- TL-EM, which the owner migrates;
- cardiacCore;
- the housekeeping backlog (M2, M8, M12, trackB m1–m3/F10, the redaction-pattern validation, B-M6, B-M9, P4's `myocardiumSolver` filter).

**openCARP goes first**, because it is already closest to the target and
exercises every interpreter table except `[case.generated]` and `requires`.

| step | what | src code | src prose | data | tests |
|---|---|---|---|---|---|
| **S0** | Owner decisions (§7), recorded in the plan. No code | 0 | 0 | 0 | 0 |
| **S1** | **Core interpreter, toy only.** `solver_description.py`, `record_description.py`, `json_document` codec, two schemas, path loading; three factory-shaped required members made optional (M11). The toy becomes TOML. **Guards A and B land here** (below) | core +480 | +80 | +230 (schemas 190, toy 40) | +260 new, −210 (`E2ERecordPlugin`) |
| **S2** | **Units on axes.** `AxisContract.unit`/`quantity`; `"0.5 mm"` values converted through `UNITS`; axis names refused a `.` | core +50 | +15 | 0 | +70 |
| **S3** | **openCARP on the description.** `solver.toml` and `records/niedererNVersion.toml`; core gains the launch template, the rank rule (R2's core half), `[[environment.probe]]`/launcher checks and the generic catalog check; the F14 validator reads `defaults` (P3 concern 2). **Then (D2)** run.py's defaults and the `tend`/`dt`/`massLumping` axes. The campaign's `nversion.par:tend/dt/mass_lumping` study keys move to those axes (D11). Lost-content items 2 and 9 are settled by logged runs | openCARP −290 (700 → about 410), core +230 | openCARP −100, core +40 | +130 (−14 YAML) | openCARP −150 (`test_parallel`, `test_environment`, `test_plugin_contract` fold into core template tests), core +160, −47 (`parallel_toy.py` becomes the toy's `[launch.parallel]`) |
| **S4** | **OpenFOAM layer on the description**, with R2's OpenFOAM half (N accepted and checked against `numberOfSubdomains`), **O15** (the duplicate runtime records and their two guard tests), **R4** (the `ProbesReader` moves with a field-declared unit), the `function_object_fields` leak, and `[tool.*] produces`. `campaign.sh`'s per-solver `--parallel` branch is deleted | openfoam −230, cardiacfoam −44, core 0 | openfoam −180, cardiacfoam −31 | +150 (−67 YAML) | about −60 (parallel-form tests into core), +40 (O15 guards) |
| **S5** | **cardiacFOAM on the description, records as TOML** (5 records). R3 as `[routes.admits]`, **not** the audit's route-aware refusal (§7, D8). The duplicated-rule and dead-name fixes from §1.3. `block_mesh_resolution` gains named rules and loses its prose (R6 on what moves). Native: the BuenoOrovio restitution study, the explicit/implicit Niederer study, the bath `phiERefPoint` issue, guidance fixes | cardiacfoam −580 (records 588 → `derived.py` about 90; plugin glue −80) | cardiacfoam −850 (records' 831 prose, less about 30 kept in `derived.py`, plus about 50 in the plugin glue), openfoam −200 | +330 records, +95 description (−160 YAML) | about −120 (Python-object record assertions become TOML-loading tests; the behaviour tests stay) |
| **S6** | **R1 + R5.** The conformance harness helpers into `omnidriver.conformance`; the cross-solver test leaves cardiacFOAM's package (no file-path import); C13 (serial equals parallel on a declared quantity) and C14 (a quantity compares across a sweep), with the four per-solver native tests deleted | core +80 | +15 | 0 | −320, +200 |
| **S7** | **Science layer.** `omnidriver-electrophysiology` (`science.toml`, `relations.py`, `rules.py`); each solver's `quantities.toml`; core's `quantity_map` seam, quantity-named study keys, `describe --quantities`; V5 moves; S1–S2 arithmetic moves; the import gate and `CLAUDE.md`'s package table gain the package's row; `campaign.sh`'s `dx_value`/`dt_where` are deleted | ep +80, core +220, cardiacfoam −70 | ep +20, core +40 | +200 vocabulary, +95 maps | +220 |
| **S8** | **B1 remainder + B3**, before the campaign's cluster run: requests name the case by `where` and the artifact by quantity/format; `compare --require-complete`; per-step durations and `resolvedEntry.parallel` in `inspect_sweep_experiment`; `benchmarks/niederer2011/pairing.json` (the frame and the probe labels); the diagonal (item 3, D10). `level_study.py`, the heredoc check and the unit tables go; the 21 requests are re-pre-registered | core +150 | +30 | +40 pairing | +80; campaign scripts about −300 |
| **S9** | **Remaining EP migrations** in this order: pseudo-ECG (the bidomain shape), singleCell (check the `single_cell_polymesh` package-data gap in the wheel first), cable1DRestitution, then cable1DCVConvergence. Each is 40–70 TOML lines plus 0–40 of derived functions; `solve_steps`, `render_tet_geo`, `plan_dict_block`, `plan_delta_t`/`plan_end_time`, `spatial_pacing` and the factory `overrides` helpers die with their last callers. The observed-order derivation and the `*_cells.dat` reader (item 6) | cardiacfoam about −1,770 (the four modules, their defaults and `spatial_pacing` are 1,767 code lines; the factory `overrides` helpers are about −100; derived functions are about +100), openfoam −180, core +50 | cardiacfoam about −460 | +250 | about −900 factory tests, +200 record tests |
| **S10** | **Step C, EP scope.** TL-EM's factory module and defaults retired (410 lines, 304 of them code; D4); the retired-member guards; the dead `overrides` helpers; `registry`/`ids` shrink to 5.5's two entries; the plan's G3 write re-inventory for the migrated tutorials. The factory machinery in core stays only for Purkinje and 1D3D, and is deleted whole when S (supplied inputs) migrates them | cardiacfoam −350, core −35 | −100 | 0 | about −250 |

**Expected end state after S10** (estimates):
- openCARP Python is about 410 code lines: the codec, the reader, the catalog tooling, F2 and F14.
- cardiacFOAM loses about 2,800 code lines and 1,450 prose lines.
- Core grows by about 1,200 code lines. In return:
  - three per-solver adapters, two parallel forms, two preflights and five record modules are gone;
  - a third solver can be added without writing any of them.
- Package source ends below today's total.

**Guards** (they land in S1 and bite from then on):
- **Guard A: the toy has zero Python.** `test_the_toy_solver_is_data_only` asserts
  two things:
  - `packages/omnidriver/tests/plugins/toy/` contains no `.py`;
  - the toy passes C1–C12 through `load_plugin_context("<path>/solver.toml")`.

  A toy that needs Python means the interpreter is missing a table.
- **Guard B: shrinking-baseline gate on solver-package Python.**
  `scripts/check-solver-python.py` with `scripts/solver-python-baseline.txt`,
  in the pattern of `check-core-shape.py`.
  - **What it counts:** AST code lines (not docstrings, comments or blanks)
    per module, in `omnidriver-openfoam`, `-cardiacfoam`, `-opencarp`,
    `-electrophysiology` and `-cardiaccore`. cardiaccore has no description
    yet, so it is counted whole.
  - **What it excludes:** modules a description names under
    `[python] codec`/`reader`/`rule`/`derived`.
  - **When it fails:**
    - on any new module outside those roles;
    - on any count higher than the baseline;
    - on a count that shrank without the baseline being edited, so the total
      can only go down;
    - on a role declaration for a module that nothing the description names
      imports, directly or transitively, so no free passes.
  - `hooks` modules are counted, not excluded. The escape hatch is visible
    and must shrink.
- **Guard C: every description and record validates** against its schema. This is
  part of C1, so any description that fails to load fails conformance.
- **Guard D: wheel artifact.** `check-wheel-artifact.py` asserts that every
  `solver.toml`, `records/*.toml`, `quantities.toml` and `science.toml` is in
  its wheel. It is the defect class the wheel shape exists to find.

---

## 7. Risks and open decisions

### 7.1 Risks

| risk | mitigation |
|---|---|
| **One interpreter bug breaks both solvers at once.** | openCARP moves first, alone (S3), with native openCARP conformance and its parallel native test. The OpenFOAM layer and cardiacFOAM follow in separate steps. The interpreter builds the *existing* member objects, so every downstream check is unchanged |
| **The framework outgrows the problem.** | The two-implementer rule (§0). There is no expression language (only `{value}` and five launch placeholders). GPU, job scripts and study-supplied steps are not built. `hooks` stay visible in guard B |
| **Content lost in translation**, above all record prose that held facts. | §4's content map checks against code. Every fact in a record docstring is already a solver-learning row, or is the TOML line itself. Migration histories go to `git log`. A record's `produces` keep their evidence tags |
| **Capability digests change once**, because `provides` is derived and the provider classes change. | Expected, and stated in each step's commit (S3, S4, S5). `stack_identity_mismatch` refuses to resume a run begun before the change, so no run is in flight across a step. No comparison request pins a stack digest (the campaign's requests hold none; checked) |
| **The benchmark campaign is running now.** S3 (openCARP axes) and S8 (request shape) change what a request says. | Neither lands before the running campaign finishes, or both land before its **cluster** run, with the 21 requests re-pre-registered (the README allows revising before the first run). The owner picks (D11). Nothing here touches `benchmarks/niederer2011/campaign/runs` |
| **Quantity maps assert facts about native keys.** | Each entry carries `evidence`. `test_quantity_map_keys_are_catalogued` (S7) checks cardiacFOAM keys against its catalog and openCARP keys against `opencarp_parameters.json`. Identity entries cite a solver-learning row. The map records `unmapped` rather than guess |
| **The wheel ships without the TOML.** | Guard D |
| **TOML's verbosity for long lists** (`consumes` in TL-EM). | Accepted: the owner prefers repetition to indirection. There is no include mechanism |

### 7.2 Open decisions, each with a recommendation

| # | decision | recommendation |
|---|---|---|
| D1 | TOML for descriptions and records; JSON for studies, requests, catalogs and references | **Yes.** Reasons in §2.1 |
| D2 | Does the openCARP record carry `run.py`'s defaults (`-tend 50 -dt 20 -mass_lumping 0`) as default arguments, with axes replacing them? | **Yes.** The native driver is `run.py`, not the binary. Today a plain run uses lumped mass (G7, G10), which moves P8 by 68 ms at 0.5 mm (J4) |
| D3 | carputils solver options (PCG + block-Jacobi/ILU parabolic, GAMG + CG elliptic)? | **Settle by two logged runs before deciding.** If they matter, carry them as default arguments with the options files supplied |
| D4 | TL-EM: retire its factory module now, and the owner migrates it as a record later (§5)? | **Retire.** It raises today, and its content is native. Keeping it keeps factory code alive for a tutorial that does not run |
| D5 | Loose pre-processing: may a study add its own pre-processing steps? | **Not yet.** Routes stay record data where the native case has them. Revisit after S9: the same TOML step grammar makes it small, but no current study needs it |
| D6 | Units on axes and quantity-named study keys (S2, S7) | **Yes.** Without them, one benchmark study cannot exist (audit §2.7) |
| D7 | The science layer as a new package `omnidriver-electrophysiology`, with core gaining only the `quantity_map` mechanism | **Yes.** §3.2 compares the alternatives |
| D8 | `variant_constraints`: keep it (as `[routes.admits]`) or replace it with the audit's R3 "route-aware refusal"? | **Keep.** R3 would refuse a contribution to a declared step the selected route does not run. But under `tet` the `dimension` axis must still patch `bidomainSolverCoeffs.dimension`, so its `-dict` argument to the unrun `mesh` step is expected. bidomain's own `tetTemporalControl/sweep_tet_dt_half.json` sets `"mesh": "tet", "dimension": "3D"`, and R3 would refuse it. As data it costs one TOML line per record, and core keeps its 80 lines |
| D9 | EP units: declared by the EP vocabulary, with core's table staying time and length? | **Yes.** Core names no EP dimension |
| D10 | The diagonal profile as a benchmark quantity (lost item 3)? | **Yes, pre-registered in S8,** before the cluster run. It is the paper's second comparison |
| D11 | When do S3 and S8 land relative to the running campaign? | **Before its cluster run,** with the 21 requests re-pre-registered. Never during a run in progress |
| D12 | `cp` for region meshes: the OpenFOAM layer's commands, or core's neutral commands? | **The OpenFOAM layer:** it is that layer's multi-region convention. Core's list stays MPI launchers only |
| D13 | Record docstrings: facts to solver-learning, histories to `git log`, under the audit's §3.3 rule | **Yes.** It is the rule that removes about 1,300 prose lines without losing a fact |
| D14 | `gmsh` sits in the OpenFOAM layer's command set (and its `omnidriver-openfoam[mesh]` extra), although the owner put gmsh outside OpenFOAM's layer (5g Q2) | **Move both to cardiacFOAM in S5** (`auxiliary`, and the extra): four cardiacFOAM records run it, and no OpenFOAM-layer code does once `render_tet_geo` goes. Low priority; it changes no behaviour |
| D15 | Allow a `hooks` escape in descriptions at all? | **Yes, gated by guard B.** Without it, cardiacFOAM's synthesis and dictionary members would force the interpreter to grow a table for each one. With guard B the escape can only shrink |
| D16 | The TNNP 2004/2006 mismatch and the −84 mV initial state, now reported as data by `describe --quantities` | **Owner's call, still open from S.** The design makes the mismatch impossible to miss. It does not decide whether the benchmark accepts it |
