# One fact, one seam: provider composition and a single case-write channel

**Status:** design. Not yet implemented; no code in this repository behaves as
described below.
**Written:** 2026-09-20, against main at `351283e`.
**Evidence:** seven read-only audits run 2026-09-20 over all four packages —
three on the declaration side (cardiacFoam, cardiacCore, core+OpenFOAM
reception), three on the execution side (run path, materialization and sweeps,
tools and subprocess), one on the agent-facing surface.

**Relationship to existing authority.** This document does not supersede
`future/ENVIRONMENT_CONTRACT.md`; it depends on it. §9 of that document
concluded that "the seam *mechanism* is sound" and that "the defects are
concentrated in fallback bodies and closed enums, not in the architecture."
The audits confirm that conclusion and extend it in one direction §9 did not
consider: the contract has no way to express **more than one provider**, and
every consequence of that absence has been paid for by hand, twice, in two
different styles.

---

## 1. The finding

`ARCHITECTURE.md` documents 24 capability seams. They are a real, disciplined,
one-way intake: a plugin declares, a `PluginCapabilities` adapter receives, a
named `compatibility.py` fallback covers absence, and no fallback branches on
plugin identity. That part works, and the run-path audit confirms it works at
runtime: **no `if plugin_id == ...` fork survives anywhere in core.** The twenty
that once existed were deleted in Phase 2 Task 7 and are guarded by
`test_no_fallback_reaches_cardiac_code_at_all`.

The defect is not in the seams. It is that the same declaration reaches core by
**more than one route**, and the routes disagree.

There are five media by which a plugin declaration reaches core. Three are
acknowledged; two are not.

| medium | acknowledged | example |
|---|---|---|
| Python contract method → capability adapter | yes, 24 seams | `get_dict_entries` |
| `plugin.yaml` role | yes | `case_profile.dictionaries[].role` |
| `utility.manifest.toml` sidecar | yes | cardiacFoam's bundled utilities |
| **direct sibling import** | no | `system_templates`, `detection`, `openfoam.dict_builder` |
| **`getattr` back-channel** | no | `get_openfoam_bashrc`, `configure_execution_environment` |

Nothing reconciles the media. So `Allrun` is declared twice and core reads the
one that is not the declared role; "what may `config` contain" is answered by
two different capabilities; and a case-file rule appears in a `plugin.yaml` and
again, differently, in a Python constant.

### 1.1 The root cause is an unasked question

`DriverContext` holds exactly one `plugin`. That is **not** a consequence of it
being a frozen dataclass in core — a frozen dataclass holds a tuple as easily as
a single field. Its own docstring records the actual motivation:

> "A context is deliberately immutable and must be passed through planning,
> discovery, and execution. It replaces the former process-global active
> plugin, which allowed one CLI invocation or test to change another one's
> solver semantics."

The migration being performed was **process-global → per-operation isolation**.
Arity was never the subject. Nobody chose one provider over a stack; the
question was not put.

Every symptom follows from that omission:

- `plugin_discovery._default_selection` **raises** `LookupError` when more than
  one adapter resolves, because all four packages register into one flat
  `omnidriver.plugins` entry-point group. An environment adapter therefore
  *competes with* a solver plugin instead of layering under it.
- Each solver plugin embeds the environment adapter by hand, and the two do it
  differently. `CardiacCorePlugin` holds a class attribute `_openfoam =
  OpenFOAMEnvironmentPlugin()` and hand-delegates nine methods. `CardiacFoamPlugin`
  holds no instance and uses function-local imports of loose OpenFOAM functions.
- The two embeddings already disagree. `get_config_value_reader` returns
  `mutators.read_foam_entry` from one and `config_values.openfoam_config_value_reader()`
  from the other — for a seam that has no core capability at all.
  `get_selected_start_time` is copy-pasted into both, each re-deriving
  `openfoam.control_dict` from its own profile.
- `omnidriver.openfoam.openfoam_environment` reaches **backwards** into
  `driver_context.plugin` via `getattr` for two hooks that appear in no
  Protocol. Core's own `test_plugin_dependency_boundary` forbids exactly this,
  and core is clean — but the guard does not cover `omnidriver.openfoam`, so a
  private, unversioned plugin ABI grew there unnoticed.
- `CardiacCorePlugin` is refused `step --strict --apply` — `legacy_apply_overrides`
  raises — because six one-line delegations to `_openfoam` were never written,
  while the same package maintains parallel override machinery in
  `workflows/overrides` reachable only through `TutorialSpec.apply_case`.

That last item is the whole thesis in one line. **A missing composition
primitive is being paid for in duplicated declarations and missing capability.**

### 1.2 What is already correct, and must survive

The redesign must not damage these. Each was verified by audit, not assumed.

| property | evidence |
|---|---|
| one executor | `runtime.workflow_runner.run_workflow_step` is the only `subprocess.Popen` for a workflow step; `openfoam`, `cardiacfoam` and `cardiaccore` do not import `subprocess` for invocation at all |
| one authorization point | `runtime.workflow.validate_workflow_commands`, reached from `strict_planning`, `run_document_exec`, and `dict_builder.build_and_launch` |
| one environment path | `EnvironmentPreflightCapability`, in two modes — `load` (source fresh) and `configure` (overlay ambient), correctly implementing `ENVIRONMENT_CONTRACT.md` §12 |
| one run pipeline | CLI → `strict_plan` → `normalize_workflow_dag` → `run_workflow` → `run_workflow_step`; `--run-document` rejoins at `_dispatch_context` |
| no identity forks | grep for `plugin_id ==` in core returns only a docstring recording their deletion |
| the four same-named file pairs | `command_authorization`, `dict_builder`, `mesh_geometry`, `mesh_provisioning` are one concern split correctly at the environment/vocabulary boundary; in every case the cardiac half *imports* the OpenFOAM half rather than restating it |
| refusing fallbacks | `legacy_route_sweep_case` / `legacy_materialize_sweep_case` raise rather than return neutral, because an empty routing would silently produce a case that is not the one the sweep asked for |

The last row is a deliberate design decision documented in
`SweepMaterializerCapability`'s docstring. This specification does not weaken
it; §3.3 gives it a name.

---

## 2. The principle

Two sentences, in priority order.

> **One fact, one medium, one seam, one enforcement tier.** A second route to
> the same declaration is a defect, not a convenience.

> **Providers contribute declarations; core composes providers.** A provider
> never embeds another provider.

The first extends the repository's existing one-source-of-truth rule by one
level. That rule forbids restating a **fact** another layer owns. This forbids
restating the **route**. Every defect in §1 is the second violation.

The second sentence describes something that does not exist today and is the
subject of §4.

### 2.1 A corollary that settles several open questions

A *tolerant* merge — "identical declarations dedup silently, differing ones
error" — was considered and rejected. Tolerance permits duplication, and
duplication is how cardiacCore's `plugin.yaml` and its `catalogs/inputs.DOCUMENTS`
drifted into disagreeing about which `system/*Dict` files a case has. Therefore:

> **A case-file rule is declared by exactly one provider. A duplicate path
> across providers is an error, always.**

Migration consequence: cardiacCore's `plugin.yaml` loses `system/controlDict`
and `constant`, which belong to the environment provider. All three plugin
manifests lose `Allrun`. This closes the duplicate-entrypoint intake (§3.2) by
construction rather than by rule.

---

## 3. Phase 0 — contract coherence

Phase 0 is a prerequisite for both later phases and does not fully close on its
own; §3.1 explains why, and that incompleteness is deliberate.

### 3.1 One enforcement model, three tiers

The same question is answered in three places that disagree:
`_REQUIRED_PLUGIN_MEMBERS` names 27; the `SolverPlugin` Protocol body declares
29; `SolverPluginOptionalHooks` declares 27 while its module docstring says
"14 probe-based optional hooks" and its class docstring says "fifteen hooks."

The consequence is measurable. **Fifteen members are both enforced and
`getattr`-probed.** `validate_plugin` rejects a plugin lacking any of them and
`driver_context` is the only way to build a `DriverContext`, so the probe can
never fail — which makes nine `legacy_*` functions unreachable in production:
`legacy_solver_commands`, `legacy_auxiliary_commands`, `legacy_utility_manifests`,
`legacy_utility_roots`, `legacy_resolve_case_models`, `legacy_samplable_fields`,
`legacy_override_schema`, `legacy_dict_entry_catalog`,
`legacy_run_document_config_schema`. The generated seam table advertises all
nine in its `fallback` column, and `test_fallback_census` is partly measuring
the impossible.

**Corrected 2026-09-20, by the guard this section asked for.** The paragraph
above is factually right and its remedy was wrong. Those nine fallbacks *are*
unreachable today. But deleting them makes their members mandatory for every
provider -- and under §4 an *environment* provider legitimately has no solver
commands, no tutorials and no samplable fields. `OpenFOAMEnvironmentPlugin`
already carries hollow stubs for all of them, returning `frozenset()` and `{}`,
which exist only to satisfy `validate_plugin`.

The correct remedy is the opposite one: **demote the members**, so the
fallbacks become reachable and the stubs can go. `_REQUIRED_PLUGIN_MEMBERS`
over-declares -- it names thirteen members the seams tag `optional-neutral`,
while omitting `get_phases`, which no capability tags optional either. Deriving
the required set from the tiers (§3.1's own proposal) fixes both directions at
once and deletes no fallback.

Every contract member carries exactly one tier:

| tier | validator | fallback | adapter |
|---|---|---|---|
| `required` | rejects absence | **none may exist** | calls unconditionally |
| `optional-neutral` | ignores | documented neutral (`False`, `{}`, `()`) | probes |
| `optional-refusing` | ignores | raises, naming the hook | probes |

`optional-refusing` already exists in behaviour — the two sweep hooks,
`apply_overrides`, `get_override_target_paths`. It has no name, which is why it
reads as inconsistency rather than as design. Naming it is most of the fix.

**Guard.** One test asserting that every member sits in exactly one tier, that
no `required` member has a `legacy_*`, and that the seam table's `fallback`
column is empty exactly for `required`.

**Why Phase 0 cannot close alone.** Two members — `get_environment_commands`
and `is_installed_environment_command` — sit in the Protocol but not in the
validator, and they are precisely the *environment* ones. There is no correct
global tier for them: they should be required of an environment provider and
absent from a solver provider. That cannot be expressed until §4 defines what a
provider provides. Phase 0 therefore does the mechanical half — one tier per
member, delete the unreachable fallbacks, install the guard — and defers
per-capability assignment to Phase 1.

### 3.2 Collapse the duplicate intakes

| duplicate | today | resolution |
|---|---|---|
| `config_schema` ×2 | `OverrideSchemaCapability.config_schema()` and `RunDocumentConfigurationCapability.schema()` answer the same question through different hooks with different fallbacks | one derived from the other; a single authored source |
| entrypoint ×2 | `plugin.yaml`'s `openfoam.entrypoint` role is validated at load by `plugin_profile.KNOWN_ROLES` and then **never read**; `CaseRuntimeConventions.case_entrypoints` is what every core consumer consults | the declared role becomes authoritative and conventions derive from it — §5a of the environment contract built that vocabulary deliberately. Closed by §2.1 in any case |
| case marker ×3 | `registry._is_case_directory` is `has_case_marker(...)` **or** `_has_entrypoint(...)`; `CaseRuntimeConventions.generated_case_markers` is a third related declaration | one predicate, one declaration |
| `get_profile` ×2 capabilities | feeds both `CxxMappingCapability` and `CaseFileContractCapability` | acceptable; the seam table must say so rather than leaving it to be rediscovered |
| `get_capabilities()` round trip | the plugin builds its answer by calling core's own `build_capability_manifest`, so six declarations arrive at core twice — and the *manifest copy* is what lands in `describe` and in the identity digest | core builds the manifest from the seams it already holds; the plugin stops assembling it |

The last row is the highest-value entry. It removes a class of drift, and it is
what currently permits `CardiacFoamPlugin.get_capabilities()` to hand out the
**live mutable** `IONIC_MODEL_CATALOG` — verified by identity — inside a payload
core treats as authoritative. `get_utility_manifests` was hardened against
exactly this hazard with a `MappingProxyType` and a defensive copy; the model
catalogs were not, and are additionally mutated at import by the `BATCHED_MODELS`
loop.

### 3.3 Defects to fix in passing

Each is independent and small. Several are live bugs.

- `get_dict_entries()` omits `CONTROL_DICT_ENTRIES`. Measured: `get_dict_entries()`
  yields 162 entries, `get_dictionary_catalog().entries` yields 171. Consumers
  reaching through `capabilities.dictionaries.entries()` cannot see nine
  `controlDict` keys that consumers reaching through `.catalog()` can. One
  capability, two answers.
- **`mpirun`-wrapped payloads bypass authorization.** `validate_workflow_commands`
  inspects only `step["command"]`. For `{"command": "mpirun", "args": ["-np", n,
  solve_command, "-parallel"]}`, `mpirun` is in `CORE_NEUTRAL_COMMANDS`, so the
  step is accepted unconditionally and the wrapped binary is never checked
  against `solver_commands()`. `workflow._unwrap_mpi_program` already exists and
  is imported into `strict_planning` **unused**; its only live caller uses it to
  fingerprint the payload for provenance. The wrapped binary is therefore
  provenance-visible and allowlist-invisible.
- `_OverrideScopeAdapter.apply` calls the hook and then `return ()`, discarding
  the plugin's return value. `openfoam.apply_overrides.apply_overrides` really
  does return records, and `legacy_apply_overrides` is typed to return them.
- `openfoam.apply_overrides` and `get_override_target_paths` each build
  `make_driver_context(self, source="adapter:openfoam-environment")`, **discarding
  the caller's context**. A cardiacFoam-contexted `--apply` reaching these
  silently loses cardiac semantics.
- `_RuntimeEvidenceAdapter.extra_provenance_paths` is annotated
  `tuple[Path, ...]` while both `RuntimeEvidenceCapability` and `SolverPlugin`
  say `tuple[RuntimeDependency, ...]`. `RuntimeDependency`'s docstring is
  explicit that a bare path "can only omit" — the gap it exists to close.
- `get_config_value_reader` is declared in `plugin_interface` under a
  `# -- ConfigValueCapability --` heading naming a Protocol that **does not
  exist**. No adapter, no field on `PluginCapabilities`. Two plugins implement
  it; core never reads it.
- `legacy_dict_key_scanner` has no capability, no hook and no probe.
  `strict_planning._catalog_diagnostics` imports it at module scope and calls it
  unconditionally. It is a permanently-active "fallback" no adapter can override.
- cardiacCore's `plugin.yaml` declares no rule for `setCardiacScarDict`,
  `setPurkinjeScarDict`, `coordinatesConventionDict` or
  `generatePurkinjeTreeDict`, though `catalogs/inputs` declares `DictEntry`s for
  all four and `workflows/preprocessing` names two of them in a `workflow_dag`
  step's `consumes`.
- cardiacCore's `catalogs/inputs.GRAPH_FILE_KEYS` and `UTILITY_CLI_OPTIONS` have
  zero references repo-wide. `UTILITY_CLI_OPTIONS` additionally contradicts
  `catalogs/utilities.UTILITY_MANIFESTS` on `-internalRole`'s default.
- `tutorial_contracts` hardcodes five reception slots to `[]` — `mesh_files`,
  `constant_files`, `system_files`, `reference_cases`, `postprocess_modules` —
  retained for API compatibility after OpenFOAM discovery was retired.

### 3.4 Caching, which Phase 1 turns into a prerequisite

`get_named_catalogs()` is the most expensive method on `CardiacCorePlugin`: per
call it re-parses `agent_guidance/manifest.yaml` from package resources,
recomputes `utility_index()`, and deep-copies the whole payload.
`CardiacFoamPlugin.get_named_catalogs()` rebuilds the entire capability manifest,
which re-walks `get_utility_manifests()`, `get_samplable_fields()` and
`get_case_runtime_conventions()`; `_CapabilityManifestAdapter.manifest()` is a
bare pass-through with no cache. `cardiacfoam.runtime_profile._profile_contract()`
re-reads `plugin.yaml` from disk on every call rather than reusing
`PluginProfile.payload`, which already holds the same parsed document — and
therefore places the `runtime.backend` contract outside the profile digest.

This is ordinary hygiene in Phase 0 and becomes load-bearing in §4.4.

---

## 4. Phase 1 — the provider stack

### 4.1 The unit of composition is the capability

A closed `kind` enum (`environment` | `solver` | …) is rejected. That is the
shape `ENVIRONMENT_CONTRACT.md` §9 identifies as where the defects concentrate,
and a better unit already exists: the 24 capabilities.

A provider declares **which capabilities it provides**, must fully implement
every member of those, and core composes per capability. This also resolves
§3.1's loose end: "required" stops being a property of every plugin and becomes
"every member of a capability you declared."

**Declared or discovered?** `ENVIRONMENT_CONTRACT.md` §12 settles it. The set of
methods present on a class is genuinely ambient — core can discover it. Intent
is not ambient, so it must be supplied. Therefore `plugin.yaml` declares
`provides:`, core discovers what is actually implemented, and a guard errors
when the two disagree. This catches the misspelled-hook case, which today is
silent: a typo'd hook name routes to a fallback and nothing reports it.

### 4.2 Ordering is declared, never inferred

Stack order must not come from install order or entry-point name. `plugin.yaml`
gains `requires: [<provider id>]`; core topologically sorts. Most specific last.

### 4.3 Composition rule per declaration shape

The *mechanism* is deferred (§4.6). The *semantics* are not — any mechanism must
satisfy these.

| shape | rule | conflict |
|---|---|---|
| set — `solver_commands`, `auxiliary_commands`, `environment_commands` | union | impossible |
| map — `utility_manifests`, `dict_groups`, `named_catalogs`, dictionary catalog | merge in stack order | duplicate key is an **error** unless overridden (below) |
| single value — `selected_start_time`, `config_value_reader`, `case_runtime_conventions` | first non-`None`, most-specific → least | — |
| diagnostics — `environment_diagnostics`, mesh diagnostics, validators | concatenate all, in stack order | none |
| refusing hooks — sweep `route`/`materialize`, `apply_overrides` | **exactly one** provider may implement | two = error; zero = refuse by name |
| case-file rules — `get_profile().case_files` | §2.1: exactly one declarer | duplicate path = error, always |

**How an override is declared.** Silence must never resolve a map collision —
that is how two providers come to name the same field differently without
anyone noticing. The more specific provider's entry carries an explicit
`overrides: <provider id>` marker naming whose declaration it replaces. An
unmarked duplicate is an error; a marker naming a provider that did not declare
that key is also an error, so a stale override surfaces when the declaration it
shadowed is removed.

The map row implements the cardiacCore/cardiacFOAM seam decision recorded on
2026-09-18 and shelved before a spec existed: where cardiacFOAM's entries
duplicate a name cardiacCore already declares for the same physical artifact,
the cardiacFOAM value defaults from cardiacCore's declaration, with an explicit
override still allowed. Not a hard equality gate.

### 4.4 Identity and the digest

`PluginIdentity.capability_digest` covers one plugin. Under composition it must
cover the **stack**, or two different stacks produce the same provenance record.

Requirements: different stacks never collide; the same stack is stable;
order-sensitive, because composition is order-dependent; and it must cover the
composition *result*, not merely its inputs — because core changing a merge rule
changes semantics without any provider changing.

Two levels. Per provider, reusing the `sha256` `PluginProfile` already snapshots
in `__post_init__`:

```
provider_digest = sha256(id, version, api_version, source, profile.digest, content digests)
```

Then the stack:

```
stack_digest = sha256(
    composition_rule_version,                                  # core's own; bumped when a rule changes
    [(provider_id, provider_version, provider_digest), ...],   # in composition order
    [(capability, resolving_provider_id, resolved_digest), ...]
)
```

The third element is what makes this a digest over the result. It records, per
capability, **who won** and **what the merged value was**. The same providers in
a different order produce a different winner for every single-valued capability,
hence a different digest. A provider that lost every resolution still changes the
digest, because the ordered provider list is hashed.

`composition_rule_version` covers the case no other element does: same providers,
same versions, core changes a merge rule, semantics change, digest must change.

**Identity becomes plural.** `PluginIdentity` splits into `ProviderIdentity`
(today's shape, per provider) and `StackIdentity` (the ordered tuple, the rule
version, the composed digest). `to_json()` emits all of it, so a provenance
record can state *which adapter answered which capability* — which today it
cannot.

**Cost, and a named limit.** Computing `resolved_digest` for all 24 capabilities
means materializing every one at context construction; today `driver_context()`
eagerly calls three. Given §3.4's uncached re-parsing, doing this naively makes
context construction slow. Therefore: §3.4 is a prerequisite, and the digest
keeps content digests only for the three capabilities today's digest already
covers, recording resolution *decisions* for the rest.

> **Limit, stated rather than discovered:** a content change inside a
> non-digested capability, in an editable install with no version bump, is
> invisible to the digest.

### 4.5 What Phase 1 deletes, and what it fixes

Deletes: `CardiacCorePlugin._openfoam` and its nine hand-delegations;
cardiacFoam's function-local `omnidriver.openfoam` imports for the same
concerns; both `getattr` back-channels, because core asks providers in order
rather than OpenFOAM reaching backwards; the copy-pasted
`get_selected_start_time`; the divergent `get_config_value_reader`;
`_default_selection`'s `LookupError` when two adapters are installed.

Fixes as a consequence rather than as separate work: cardiacCore's six silently
neutral methods — `get_base_mesh_geometry_diagnostics`, `get_config_value_reader`,
`apply_overrides`, `get_override_target_paths`, `inspect_effective_configuration`,
`get_override_scopes` — become the environment provider's declarations, so
`step --strict --apply` works with **zero new cardiacCore code**.

**Blast radius.** Small, and this is the strongest argument for doing it. The
run-path audit found that no production core module touches
`driver_context.plugin` directly; everything goes through `.capabilities`,
guarded by `test_plugin_dependency_boundary`. Only `adapt_plugin_capabilities`,
`driver_context()` and `load_plugin_context` change arity. One exception the
implementation must handle: that guard does **not** cover `omnidriver.openfoam`,
which is why the back-channels grew there. Phase 1 extends it to adapters.

### 4.6 Deferred: the mechanism

Two candidates, decided by a spike rather than by argument.

1. **Own it.** Keep the `Protocol`-based seams and write an explicit composition
   rule per declaration shape. No runtime dependency; the docstring-generated
   seam table keeps working.
2. **Adopt `pluggy`**, the plugin manager underneath pytest, which has already
   resolved this arity question — multiple implementations per hook,
   `firstresult` for single-valued hooks, hook wrappers. Cost: a runtime
   dependency in a core that has nearly none, rewriting 24 Protocols as
   hookspecs, and losing the seam table in its present form.

**Spike.** Prototype both against cardiacCore's six missing delegations.
**Success criterion:** `step --strict --apply` succeeds on a cardiacCore case
with no new cardiacCore code.

Read how `pluggy` resolved this before inventing, whichever is chosen. Verify
its current API directly; this document's summary of it is from memory and is
not a specification.

---

## 5. Phase 2 — one case-write channel

### 5.1 The finding

There are **two** materialization mechanisms, and they do not meet.

| | `TutorialSpec.build_cases` / `apply_case` | `SweepMaterializerCapability.route` / `materialize` |
|---|---|---|
| used by | every registered tutorial; entry-based sweeps | generic cross-product `sweep.json` sweeps only |
| constructs a `TutorialSpec`? | yes | **no — bypasses it entirely** |
| cardiacFoam | yes | yes, straight to `dict_builder.build_and_launch` |
| cardiacCore | yes | **no** — `legacy_materialize_sweep_case` raises |

cardiacFoam therefore has two materialization paths of its own, and which runs
depends on how the sweep was invoked. cardiacCore can be entry-swept but not
cross-product swept — not by design, but because one hook pair is absent.

Alongside this, "apply an override" has **three shapes**, one of them entirely
off the capability grid:

| | `openfoam.apply_overrides` | `cardiacfoam.overrides` | `cardiaccore.workflows.overrides` |
|---|---|---|---|
| registered as a capability | yes | yes (it *is* OpenFOAM's implementation for cardiacFoam) | **no** |
| reachable from `step --strict --apply` | yes | yes | **no** |
| rollback | `_restore_on_failure` | none of its own | **none** |
| transaction ledger | yes | yes | **not wired** |
| value-kind vocabulary | catalog enums | catalog enums | **its own** — integer/scalar/word/enum/vector3 |
| path templating | — | — | **its own** `<ventKey>` placeholder |

cardiacCore's is a parallel, self-contained reimplementation of the same
`$SCOPE.path → dict key` idea, reached only through `apply_case` at
materialization time — before any `step --strict --apply` transaction exists.

Counting mechanisms that decide what bytes go where, there are roughly **seven**
independent case-authoring implementations across the four packages. They
converge on exactly one shared primitive, `openfoam.mutators.update_foam_entry`,
and only for the narrow case of *patch one key in an existing dictionary*. Every
from-scratch or bespoke-format write is its own implementation, including
cardiacCore's `operations.vtu_selection.write_cell_set` and
`operations.electrodes.write_*`, which bypass `mutators` entirely and perform no
atomic rename.

### 5.2 The design

`TutorialSpec.apply_case` and `SweepMaterializerCapability.materialize` are the
same operation at different arities. A `CaseWriter` capability with two members:

- **`plan_case(request) -> CaseWritePlan`** — pure, no writes. Input is resolved
  values whatever their source: a sweep axis combination, a tutorial's
  `CaseConfig`, or an agent's `--config`. Output is declarative — target path,
  operation, value, and the provider owning each.
- **`write_case(plan) -> CaseWriteRecord`** — impure, core-owned, executing the
  plan through one shared transactional writer.

Four consequences justify the work:

1. cardiacCore's parallel override module stops being parallel.
   `workflows/overrides` becomes its `plan_case` implementation and gains
   rollback and the transaction ledger, having neither today.
2. **`CaseWritePlan` is inspectable before execution.** `plan --strict` can show
   an agent exactly what will be written; `--dry-run` becomes a property of the
   type rather than a flag threaded through `build_and_launch`. This is the
   largest agent-integration gain in this specification: today an agent's repair
   loop discovers write problems by writing.
3. Two operations in the plan vocabulary, not one — `patch` (existing key, today
   `mutators.update_foam_entry`) and `synthesize` (whole file from catalog,
   today `build_electro_properties` and `regenerate_electro_properties`). Only
   `synthesize` need be provider-supplied, because only it needs vocabulary.
4. cardiacCore's two bespoke writers route through the shared atomic writer.

### 5.3 Two vocabularies promoted to core

By §2.1, both already have a home and are being restated:

- cardiacCore's `_check_value` value kinds (integer/scalar/word/enum/vector3) →
  `DictEntry.value_kind`, which exists.
- cardiacCore's `<ventKey>` placeholder, spelled independently in
  `workflows/overrides.VENT_KEY_PLACEHOLDER` and inside the catalog's
  `driver_path` strings → `DictEntry.dynamic_path`, which exists.

### 5.4 The agent-surface gaps, folded in

These are consequences of the three phases, not a fourth phase.

| gap | lands in |
|---|---|
| four distinct diagnostic shapes reach an agent — `StrictDiagnostic`; `ValidationError` (`phase` not `source`, no `code`, Protocol return weakened to `tuple[Any, ...]`); `run_document_exec._diag`, which **drops `source`** even when re-serializing a `StrictDiagnostic` that has one; and an unstructured `{status, error, run_document}` envelope from a blanket `except Exception` | Phase 0 |
| `config_schema` answered by two capabilities | Phase 0 (§3.2) |
| the sweep spec has **no schema mechanism at all** — no file, no hook; an agent learns it from `spec_error` failures | Phase 2, derived from the same declarations |
| two live "what can I do here" entrypoints (`describe`, `plan --strict`) that overlap and diverge, plus five catalogs reachable only through dev-time export scripts — report catalog, tutorial displays, utility manifests, dict catalog, capability seams | Phase 0 (§3.2), extending `describe` |
| `$TOKEN.`-scoped override syntax never appears in `describe` | Phase 2, via `CaseWritePlan` |
| in-process "operations" — cardiacCore's seven Python callables — have **no core type**; `utility_catalog` models only binaries, so they travel as an opaque blob through `get_named_catalogs` | Phase 2 |

### 5.5 The largest risk in this specification

`cardiacfoam.dict_builder` is 1007 lines, and `build_and_launch` at the bottom
of it mixes dictionary synthesis with orchestration — mesh provisioning, environment
loading, running the solver — inside a module named `dict_builder`. Phase 2
cannot be done without splitting it: synthesis into `plan_case`, orchestration
out. This is the single largest refactor here and the place an estimate is most
likely to be wrong.

---

## 6. Ordering, and why

| phase | depends on | reason |
|---|---|---|
| 0 | — | composition cannot be built on a contract where "required" is decided twice |
| 1 | 0 (mechanical half), 3.4 | per-capability tier assignment needs provider kinds; the digest needs the caching fixed |
| 2 | 1 | the composition rule determines who owns the writer when two providers could |

Phase 0 does not fully close before Phase 1 begins, by construction (§3.1).

---

## 7. What this does not change

- The dependency direction rules — `cardiacfoam` → `openfoam` → `core`,
  `cardiaccore` → `openfoam` → `core`, and the sibling prohibition between the
  two cardiac adapters. `scripts/check-import-boundaries.py` keeps its empty
  waiver list.
- The single executor, the single authorization point, the single environment
  path, and the single run pipeline (§1.2).
- The refusing-fallback decision for sweeps. §3.1 names the tier it already
  occupies; it does not weaken it.
- The four same-named file pairs across `openfoam` and `cardiacfoam`. They are
  correct layering and the naming convention makes the pairing legible.
- The licence question, which remains open and untouched.

---

## 8. How to verify

Per `CLAUDE.md`, in all four shapes, with the wheel shape rebuilt after every
source change. The durable claim is **0 failed**; this document quotes no suite
totals.

New guards this specification requires:

| guard | asserts |
|---|---|
| tier coherence | every contract member in exactly one tier; no `required` member has a `legacy_*`; the seam table's `fallback` column is empty exactly for `required` |
| provides-vs-implements | a provider's declared `provides:` matches what it actually implements |
| single declarer | no case-file path is declared by two providers |
| stack digest | two different stacks never produce the same digest; the same stack is stable across processes |
| adapter dependency boundary | `test_plugin_dependency_boundary` extended to cover `omnidriver.openfoam` — no adapter reaches `driver_context.plugin` |
| mpi authorization | an `mpirun`-wrapped payload is checked against the allowlist |

---

## 9. Open questions

1. **The composition mechanism** (§4.6) — own it, or adopt `pluggy`. Decided by
   the spike, not by this document.
2. **Whether `describe` should absorb all five export-script catalogs, or
   whether some are legitimately dev-time only.** The audit established that an
   agent driving an installed CLI cannot see them; it did not establish that all
   five belong in a runtime payload.
3. **A second non-OpenFOAM provider.** `ENVIRONMENT_CONTRACT.md` §9 states that
   a FEniCS plugin cannot be written today because `get_profile()` fails on the
   role vocabulary. Nothing in this specification verifies that Phases 0–2 make
   one writable; that claim needs a real second provider before it is made.
