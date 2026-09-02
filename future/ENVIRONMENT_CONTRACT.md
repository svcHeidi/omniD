# The Environment Contract: what `omnidriver` core owns, and how

**Status: §5a implemented, §5b and §6 open.** Written 2026-08-27 after an
evidence-checked audit of the three-package split. Supersedes the framing in
`ARCHITECTURE.md`'s Rule 1, which this document replaces with something the
code can actually satisfy.

| section | state |
|---|---|
| §4 the restated rule | adopted; `ARCHITECTURE.md` Open Items points here |
| §5a role validation | **done** — `plugin_profile.KNOWN_ROLES`, enforced at load (Phase 1 Task 2) |
| §5a entrypoint wiring | **done** — `registry._entrypoint_relpaths()` (Phase 1 Task 3) |
| §5b trust boundary | open, deliberately deferred — Phase 3 |
| §6 `GenericEnvironmentPlugin` | open, blocked on §5b |
| §7 the cardiac `Phase` enum | **done** — `get_phases()` + `legacy_phases()` landed (Phase 2 Task 3) |
| §8 the complete binding inventory | **new** — three independent audits, 2026-09-01 |
| §11 role-vocabulary escape tier | **done** — `plugin_profile.ESCAPE_ROLE_PREFIX` (Phase 3 Task 3b), 2026-09-01 |
| §10 Tier 3, `openfoam.control_dict` lookup | **done** — `CaseIntrospectionCapability.selected_start_time()` (Phase 3), 2026-09-01 |
| §10 Tier 3, `processor*` decomposition seam | **done** — `CaseFileContractCapability.decomposition_dirname_prefix()` (Phase 3), 2026-09-01 |
| §10 Tier 3, `apply_overrides` raw-traceback crash | **done** — `legacy_apply_overrides` refuses cleanly (Phase 3), 2026-09-01 |
| §10 Tier 3, `ArtifactFormat` + `utility_catalog` vocabulary | **done** — both opened to plugin-chosen strings (Phase 3), 2026-09-02 |
| §10 Tier 3 | **closed** — all six items done, 2026-09-02. Tier 4 next |

## 1. The problem with Rule 1 as written

`ARCHITECTURE.md` currently says:

> **Core Independence:** `omnidriver.core` MUST NOT import anything from
> `openfoam` or `cardiac`. It must contain **zero** physics rules and
> **zero** OpenFOAM vocabulary.

The first sentence is a real, checkable rule and is nearly satisfied. The
second sentence is not satisfied and, as stated, should not be the goal.

Core today contains `Allrun`, `system/controlDict`, `$FOAM_APPBIN`,
`blockMesh`, `processor*`, `openfoam_time_dirs`, and a built-in plugin class
named `GenericOpenFOAMPlugin`. Reading that as failure leads to the wrong
conclusion — that core should be stripped of every one of those names.

The right reading is the one the code already half-implements: **those are not
core's vocabulary, they are one environment's *bindings* of concepts core
legitimately owns.** Every simulation framework has an entrypoint, a
time-control document, a root directory of trusted executables, and a set of
directories that constitute a case. OpenFOAM spells them `Allrun`,
`system/controlDict`, `$FOAM_APPBIN`, and `system/ + constant/`. FEniCS,
deal.II, or SU2 spell them differently. Core is entitled to model the concept;
it is not entitled to hardcode the spelling.

## 2. The seam already exists

`CaseFileRule.role` is that seam. It is namespaced deliberately, and
`plugin_capabilities.py`'s `CaseFileContractCapability` docstring already says
so: *"Roles are namespaced and the prefix is load-bearing."*

One consumer already works exactly as this document proposes.
`core/runtime/provenance_inputs.py:93`:

```python
def _case_root_dirnames(driver_context: "DriverContext") -> tuple[str, ...]:
    """Top-level case directories the active plugin's declared case files
    live under, derived from the first path segment of each ``case_files``
    rule -- e.g. ``{"system", "constant"}`` for the OpenFOAM plugin. Not
    hardcoded, so a plugin for a different environment (different top-level
    directory names entirely) is walked correctly without a core change."""
```

That is the pattern. The gap is that almost nothing else follows it.

## 3. Measured state of the seam

**Re-measured 2026-09-01 by three independent audits — static (AST over all
shipped core source), runtime (an import hook logging every reach while driving
every public API under three plugins), and contract (could a FEniCS plugin be
written today).** The table below replaces an earlier one that listed 11 rows.
It was incomplete on five of them and stale on one. Treat *this* table as
provisional too: the inventory has now been wrong four separate times, and each
correction came from executing rather than reading.

### Seamed — reached through a declared role or hook

| concept | OpenFOAM binding | seam |
|---|---|---|
| case directories to walk | `system`, `constant` | derived from declared path segments, `provenance_inputs.py:93` |
| time-control document | `system/controlDict` | role lookup, `provenance_inputs.py:111` |
| plugin vs environment file split | — | role prefix, `tutorial_contracts.py:123,127` |
| entrypoint script | `Allrun` | `registry._entrypoint_relpaths()`, Phase 1 |
| dictionary editing phases | *(cardiac)* | `get_phases()` / `legacy_phases()`, Phase 2 |

### Hardcoded — no declaration path. These are the defects.

| binding | sites | what a non-OpenFOAM plugin gets |
|---|---|---|
| **`postProcessing` directory name** | **8** — `output_collection.py:83,118`, `generic_case.py:24`, `registry.py:142`, `sweep_runner.py:198,413`, `workflow_runner.py:225`, `artifacts.py:148` | sweep output archiving is a **silent no-op**. `output_collection.py` is an entire module built on this one string; `OUTPUT_DIR_NAME` exists but other sites re-declare the literal instead of using it |
| ~~`processor*` decomposition dirs~~ **fixed 2026-09-01, §10 Tier 3** | **4 code sites** — `provenance_inputs.py`, `registry.py`, `sweep_runner.py`, `workflow_runner.py` | was: no time-indexed artifact matching for its own parallel layout. Now `plugin_profile.decomposition_dirname_prefix(driver_context)`, a bare optional hook (`get_decomposition_dirname_prefix`) on `CaseFileContractCapability` — not a `CaseFileRule` role, since this names a wildcard dirname family rather than one static path. Default `"processor"`, matching OpenFOAM's own `decomposePar` convention exactly, so no shipped plugin needs to change |
| `_stage_entry_case`'s generated-name vocabulary | `sweep_runner.py:196-244` | `{postProcessing, logs, workflow_logs, cachedCasePostProcessing, polyMesh, archivedPostProcessing, results, data}` + `log.*` + `.foam/.msh/.geo` + numeric-time-dir detection. Either stale state leaks, or **its real output is silently deleted** |
| `CORE_NEUTRAL_COMMANDS` | `workflow.py:52` | 11 OpenFOAM/gmsh binaries permanently allowlisted; union-only, cannot be removed |
| `CASE_SCRIPT_COMMANDS` | `workflow.py:74` | **trust boundary** — must literally ship files named `Allrun`/`Allclean` to get PATH-shadow protection |
| `$FOAM_APPBIN` / `$FOAM_USER_APPBIN` | `workflow.py:483` | its own binary root is never recognised |
| `producer_commands = {"Allrun"}` | `workflow.py:426` | a differently-named entrypoint is never credited with producing artifacts — and this does **not** use the `openfoam.entrypoint` role that `registry.py` already resolves |
| `{"command": "Allrun"}` default DAG | `generic_case.py:137` | no `driver_context` in that module at all |
| ~~`ArtifactFormat` closed `Literal`~~ **fixed 2026-09-02, §10 Tier 3** | `models.py:36` | was: cannot name XDMF/HDF5, and forced core to **mislabel its own** per-step logs as `openfoam_log` (`artifacts.py:152`). Now `ArtifactFormat = str` — open by design, since nothing in core actually branches on the value (checked: zero `.format ==` sites in core). `CORE_ARTIFACT_FORMATS = {"json_summary", "log"}` names only the two core writes for its own artifacts; core's own step-log artifact now uses `"log"` instead of borrowing OpenFOAM's `"openfoam_log"` |
| ~~`utility_catalog` `ALLOWED_ARGUMENT_KINDS`/`ALLOWED_ARTIFACT_FORMATS`~~ **fixed 2026-09-02, §10 Tier 3** | `utility_catalog.py` | was: `{scalar, label, path, word, word_list, switch}` — OpenFOAM's primitive type names, plus `ALLOWED_ARTIFACT_FORMATS` duplicating `ArtifactFormat` verbatim, both enforced at `utility.manifest.toml` load time. Real usage (grepped every `format = "..."` across cardiacfoam's shipped manifests) confirmed the split: `openfoam_log`/`csv_probe`/`csv_sweep`/`vtk_sequence`/`openfoam_time_dirs` are all genuinely OpenFOAM/solver vocabulary (11+ real manifests use `openfoam_log` alone), only `json_summary` is core-neutral. Both constants removed; `_parse_produces_entry`/`_parse_positional_arg`/`_parse_flag` now check structural validity only (non-empty string) — same reasoning §11 already used for escape-tier roles: core has no vocabulary to validate spellings it does not own. `ALLOWED_CATEGORIES` (`mesh`/`field-setup`/`post-processing`/...) is untouched — that taxonomy is core's own, not OpenFOAM's |
| ~~`startFrom`/`startTime`/`latestTime`/`firstTime` keywords + numeric time-dir naming~~ **fixed 2026-09-01, §10 Tier 3** | `provenance_inputs.py:90,119-155` | was: even having declared `openfoam.control_dict`, the *keyword vocabulary* inside it was still OpenFOAM's. Now lives only in `compatibility.legacy_selected_start_time`, the documented default behind `CaseIntrospectionCapability.selected_start_time()` — a plugin overrides the whole computation, not just the file lookup |
| `("constant", "system")` directory guess | `strict_planning.py:230-244` | plus dead cardiac metadata keys three lines under a docstring saying core does not know `electroProperties` exists |
| ~~`--openfoam-bashrc` CLI flag + `openfoam_bashrc` parameter~~ **fixed 2026-09-02, §10 Tier 3** | `cli.py`, threaded through 11 files across all three packages once traced fully (larger than the original "6 files" estimate) | was: a FEniCS user types `--openfoam-bashrc`; the same capability was internally inconsistent, `load()` taking `explicit_bashrc` while `diagnostics()` took `openfoam_bashrc` for the identical concept. Renamed to `explicit_bashrc` everywhere in core and at the `EnvironmentPreflightCapability`/`SolverPluginOptionalHooks` boundary — not a new third name, `explicit_bashrc` was already `load()`'s and `omnidriver-openfoam`'s own established spelling, confirmed by checking `openfoam_environment.py`'s `_candidate_bashrcs`/`load_openfoam_environment`, which already used it. CLI flag is now `--environment-bashrc`; `--openfoam-bashrc` and `make_spec(openfoam_bashrc=...)`/its `cases[i]` JSON-key equivalent keep working as deprecated aliases (the JSON key was found to be write-only with zero downstream readers today, so the alias costs nothing functionally but keeps an existing `--config` file's key from erroring). The plugin-hook-level keyword (`get_environment_diagnostics(..., explicit_bashrc=...)`) was renamed without a compatibility shim -- only the test double implements that hook today, no real plugin. Files correctly kept saying "openfoam" throughout: `omnidriver-openfoam`'s own internal bashrc-discovery vocabulary (`discover_openfoam_bashrc`, `OPENFOAM_BASHRC` env var, `get_openfoam_bashrc` plugin-author hook) and `omnidriver-cardiacfoam`'s `build_and_launch(openfoam_bashrc=...)` — both packages are legitimately about OpenFOAM |
| `DictEntry.value_kind = "openfoam_literal"` | `contracts/dictionary.py:21` | a core dataclass whose **default** is OpenFOAM |
| ~~`KNOWN_ROLES` closed to 11 values, 8 `openfoam.*`~~ **fixed 2026-09-01, §11** | `plugin_profile.py:75` | was **the hard block**: `get_profile()` is REQUIRED, so a plugin declaring `fenics.mesh_file` failed at load with `ValueError`. `KNOWN_ROLES` is still an exact-match closed enum for `openfoam.*`/`plugin.*`/`case.*` — that guarantee is unchanged — but a role of the shape `x-<namespace>.<leaf>` now bypasses it for a namespace core has no vocabulary for. See §11 for the design and what a typo still costs |

### Correctness bugs found by the same sweep — not architecture

| bug | site |
|---|---|
| `RUN_CASE_SCRIPT_RELPATH` names `applications/scripts/driverFoam/...`, a path that **does not exist** in this repo. Anyone relying on the default gets `FileNotFoundError` | `generic_case.py:25` |
| `run_case.sh` hardcodes `/Volumes/OpenFOAM-v2412/etc/bashrc` — a machine-specific absolute path in shipped source | `scripts/run_case.sh:26` |
| dead `Phase` import | `contracts/dictionary.py:12`, `dict_entries.py:31` |
| `cardiacfoam_monorepo_root()` — zero call sites in core; its docstring cites `utility_catalog.UTILITIES_ROOT`, which no longer exists | `specs/paths.py` |
| 55 of ~74 core files carry a `"This file is part of cardiacFoam"` GPL header | throughout |

**Confirmed clean:** `postprocessing/` (all four modules) and `schemas/run-document.json` carry no bindings.

## 4. Rule 1, restated

> **Rule 1 (revised). Core owns the *concepts* of a simulation environment;
> a plugin owns their *bindings*.**
>
> `omnidriver.core` MUST NOT import `omnidriver.openfoam` or
> `omnidriver.cardiacfoam` at runtime, and MUST NOT contain physics rules.
>
> Core MAY name a concrete environment binding **only** where that binding is
> reached through a declared role, a capability hook, or an explicitly
> documented and tested default that a plugin can override. A hardcoded
> string with no declaration path is a defect.

This is checkable. "Zero OpenFOAM vocabulary" was not.

## 5. Scope of the first pass — deliberately narrow

The concepts above split cleanly into two groups, and only the first is in
scope now.

### 5a. In scope: filesystem predicates

Wiring `openfoam.entrypoint` changes only **read-only questions about a
directory**:

- is this directory a case? (`registry.py:79`)
- is this case runnable without driver-owned workflow metadata? (`registry.py:88`)
- should a discovered folder keep its placeholder DAG? (`registry.py:302`)
- what single step does a case with no declared solver command run?
  (`generic_case.py:137`)

None of these decides whether something may execute. The worst outcome of a
wrong answer is a case that is not listed, or is listed as not runnable.

Also in scope: **validating the role vocabulary**, because an unenforced
namespace is not a seam. A typo must fail loudly at profile load, not silently
reclassify a file.

### 5b. Explicitly out of scope for now: the trust boundary

`CASE_SCRIPT_COMMANDS` (`workflow.py:74`) is **not** a naming convention. It is
the set of bare command names that `workflow_runner.py:127` allows to resolve
to a **case-local executable** rather than to `PATH`. Every other bare name
resolves via `PATH` only, precisely so that a case directory cannot shadow a
trusted binary.

Making that set plugin-declared means a plugin can widen which case-local
files may execute. Same for `CORE_NEUTRAL_COMMANDS` and the `$FOAM_APPBIN`
lookup: those form the command allowlist that `strict_plan` and the
RunDocument adapter both consult.

Those changes are worth making, and they need their own pass with their own
threat model and tests — the same standard `SECURITY.md` applies to the
existing command boundary. They are not bundled into a discovery cleanup.

Until then, `CASE_SCRIPT_COMMANDS`, `CORE_NEUTRAL_COMMANDS`, and
`_is_installed_openfoam_app` stay hardcoded, each carrying a comment naming
it as an OpenFOAM-family default and pointing here. (`ArtifactFormat` and the
`processor*` glob were both resolved outside the trust boundary in Tier 3 —
see §10 — since none of their sites decide what may execute; they only
decide what to read, label, or prune.)

## 6. `GenericOpenFOAMPlugin` → `GenericEnvironmentPlugin`

Worth doing, and **not** in the first pass, because the rename is only honest
once the class stops declaring OpenFOAM paths of its own.

The end state: `GenericEnvironmentPlugin` declares nothing by default and
loads its case-file profile from a YAML the caller names. `generic-plugin.yaml`
becomes `openfoam-environment.yaml`, ships in `omnidriver-openfoam`, and is
what an OpenFOAM user without a solver plugin points at. Core keeps a genuinely
empty profile as the built-in.

That change is blocked on the trust-boundary work in §5b — the generic plugin's
value today is that it supplies `allowed_commands` for a plan
(`generic_plugin.py:60`), and that block comes from the hardcoded command set.
Sequence it after.

## 7. The cardiac `Phase` enum is a different problem

`run_model.py:44` — `Phase = Literal["anatomy","physics","stimulus","solver"]`
— is not an environment binding at all. It is one solver plugin's domain
vocabulary frozen into core, and `specs/validation.py:73`'s `primary_phase()`
walks it unconditionally.

It is, however, the **worked example** of the transform this document asks for
everywhere else: the legacy `driverFoam` tree already replaced it with a
`get_phases()` optional hook, a `legacy_phases()` fallback deriving phases from
the plugin's own `DictEntry` values, and a `phase_order` parameter threaded
through `primary_phase()`. Port that first and it becomes the template for
§5b's later work.

## 8. What this does not change

- The dependency direction rules (`cardiacfoam` → `openfoam` → `core`) stand
  unchanged and are already nearly satisfied.
- `scripts/check-import-boundaries.py` stays as-is in shape. It checks imports;
  this document is about strings, and strings need a different guard
  (role-enum validation, plus grep-style assertions where a binding must not
  appear).
- No new package. No new abstraction layer. Everything proposed here uses
  `CaseFileRule.role`, `PluginProfile`, or an optional plugin hook — all three
  already shipped.

## Related

- `docs/superpowers/plans/2026-08-27-core-completion.md` — the executable plan
- `GITHUB_MIGRATION.md` §3 — round-2 scope, corrected 2026-08-27
- `SECURITY.md` — the existing command-boundary threat model that §5b must extend

## 8. What only running the code revealed

Static reading has now missed something four times. This section records what
execution found that inspection did not — driven under three plugins in a
core-only venv with an import hook logging every reach.

### The nine ungated `omnidriver.openfoam` fallbacks, by escapability

| | count | which |
|---|---|---|
| hook exists, the neutral test double implements it | 6 | config value reader, environment diagnostics, loaded environment, configured environment, function-object fields, case dict keys |
| hook exists, **nothing implements it** | 2 | `apply_overrides`, `get_base_mesh_geometry_diagnostics` |
| **no hook at all** | 1 | `legacy_dict_key_scanner` |

**Correction to an earlier claim.** `legacy_dict_key_scanner` having no hook
does *not* make it unavoidable: `strict_planning._catalog_diagnostics` returns
early when the plugin declares no `cxx_mapping`, and all three plugins default
to `None`. Verified both ways — never imported for the three, imported
immediately when a `CxxMapping` is monkeypatched on. It is a gap only for a
plugin that declares a C++ mapping, which already implies OpenFOAM tooling.

**The genuinely unavoidable one is `apply_overrides`.** It raises for all three
plugins including the neutral double, has no implementation anywhere, and
crashes the CLI with a raw traceback rather than a structured error. **Fixed
2026-09-01, §10 Tier 3** — see below; the "unavoidable" part is still true (no
plugin implements the hook), only the crash-vs-structured-error part changed.

`get_base_mesh_geometry_diagnostics` also raises for all three when called
directly, but is not reached through the normal pipeline for
`GenericOpenFOAMPlugin`: that plugin registers zero tutorials, so every entry it
can plan is a bare case folder, which `strict_planning` flags `generic_case=True`
and exempts from mesh diagnostics before the capability is consulted.

### The shipped-plugin gap, operation by operation

`GenericOpenFOAMPlugin` is what core *ships*. In a core-only install:

| operation | result |
|---|---|
| `describe`, `--help`, introspection | **works** |
| `plan --strict`, `run --strict`, `step --strict` | raises `ModuleNotFoundError` |
| `sweep-plan` | does not crash; every case fails with a hookless routing refusal, exit 1 |
| `sweep-run` | crashes **before the spec is parsed** — `get_configured_environment` is line 1 |
| `step --strict --apply` | crashes, raw traceback |
| no `--plugin` at all | fails at plugin load: `ModuleNotFoundError: omnidriver.cardiacfoam`, exit 2 |

So core's suite passing at 615/0 rests on `NeutralEnvironmentPlugin`, a double
that lives in the **test tree**. "Core's tests pass alone" and "core works
alone" are different statements and only the first is currently true.

The failures are at least **loud** — uncaught tracebacks, not silent degradation.

### The one silent path, and an asymmetry worth knowing

`sweep_run`'s per-case loop wraps materialisation *and* the per-case
`strict_plan` call in a single `except Exception`, folding any error into a
`plan_error` string. A plugin that clears `sweep_run`'s first-line check but
lacks one of the other five environment hooks has its `ModuleNotFoundError`
downgraded to an ordinary-looking per-case failure — no traceback, nothing
distinguishing it from a genuine planning error.

**`sweep_plan` does not have that try/except around `strict_plan`.** The same
reach crashes it outright. So `sweep-plan` is *not* a reliable dry-run proxy for
what `sweep-run` will do — they differ in failure behaviour, not just in
side effects.

## 9. Verdict on the architecture claim

`ARCHITECTURE.md` opens by describing a shift to "a universal scientific
workflow engine capable of orchestrating... FEniCS, deal.II, OpenFOAM."

**As of 2026-09-01 that is aspirational.** What exists is an **OpenFOAM engine
with a solver-plugin seam** — which is a coherent and useful thing, and is what
cardiacFoam demonstrates. A FEniCS plugin cannot be written today: it fails at
`get_profile()`, a required member, because the role vocabulary has no non-
OpenFOAM tier.

The seam *mechanism* is sound. The 24 capability Protocols, the `getattr`-probed
optional hooks, the `:adapts:/:fallback:/:status:` discipline, and the rule that
no production module touches `driver_context.plugin` directly are all correct
multi-solver design. Six fallbacks already default the right way — `False`,
`{}`, `()`, or refuse-by-name — and `get_phases()` is the worked example of the
transform the rest need.

The defects are concentrated in **fallback bodies and closed enums**, not in the
architecture. That is the good news, and it is why this is a work list rather
than a redesign.

## 10. The work list, sequenced

Ordered by cost and risk, not by how offensive each binding looks. Tiers 1 and
2 are most of the value; tier 4 is the one that needs a threat model.

### Tier 1 — not architecture, just broken *(closed 2026-09-01)*

Two of the five were real. Three were misreadings in the audit, corrected here
rather than deleted, because the reasoning that produced them is the kind that
recurs: **"no callers in core" is not "no callers", and "unused in this module"
is not "unused"** when the module is a re-export seam.

| item | outcome |
|---|---|
| `RUN_CASE_SCRIPT_RELPATH` names a nonexistent path (`generic_case.py:25`) | **fixed**, and larger than reported. Latent, not live: `resolve_run_script_path` has **zero call sites** in any package, so nothing raises today — the value's one real consumer is the `run_script_relpath` entry in spec metadata. Resolving it against the installed package was only half a fix: `omnidriver.scripts` was not in `package-data`, so `run_case.sh` shipped in no wheel and the new path was wrong in exactly the old way. `cardiacfoam` also carried **its own copy** of the constant — still spelling the retired `openfoam_driver` name — and all ten tutorial defaults chain to *that* one, so the core fix alone would not have reached the live path |
| `run_case.sh` hardcodes `/Volumes/OpenFOAM-v2412/etc/bashrc` | **fixed** — fallback removed; `WM_PROJECT_DIR` and the existing `OPENFOAM_BASHRC` error already covered it |
| ~~dead `Phase` imports~~ | **not dead.** Both are re-export seams pinned by tests: `test_run_model.py` asserts `contracts.dictionary.Phase is run_model.Phase` to catch a type-distinct redeclaration, and `test_dict_entries.py` imports `Phase` from `omnidriver.dict_entries`. Left alone |
| ~~`cardiacfoam_monorepo_root()` — zero call sites~~ | **live.** Zero callers *in core*; real callers in both sibling packages' `conftest.py` and in root-level `scripts/`. Only the stale `utility_catalog.UTILITIES_ROOT` citation in its docstring was wrong, and that is fixed |
| ~~dead cardiac metadata keys (`strict_planning.py:230`)~~ | **live.** Eleven `omnidriver-cardiacfoam` tutorials set them on spec metadata; core reading generic metadata keys the plugin populates is the seam working as designed, not a leak |

The guard that should have caught the packaging half of item 1 could not:
`test_wheel_install_imports.py` only *imports* modules, so a module that
imports cleanly and then points at a data file the wheel never shipped passed
it. It now asserts the bundled file is present, verified by removing the
`package-data` line and watching it fail *after* `all modules imported`
succeeds.

### Tier 2 — the seam exists; wire it *(closed 2026-09-01)*

| item | payoff |
|---|---|
| ~~**open `KNOWN_ROLES` with a non-OpenFOAM tier**~~ **done 2026-09-01, §11** | removed the hard block, *for loading only* — `tutorial_contracts.py`, `provenance_inputs.py` and `registry.py` still branch on literal `openfoam.*` roles, so a foreign environment's files now load and are then ignored by those three. Generalising them is the rest of this tier. Original rationale: `get_profile()` is required, so *nothing* else about non-OpenFOAM plugins can be attempted until this lands. Also fixes `CaseFileRule`, `PluginProfile` and `ResolvedInput` in one place — their dataclasses are already neutral; only the enum's values were not |
| ~~**an output-directory role for `postProcessing`**~~ **withdrawn 2026-09-01 — owner's decision** | `postProcessing` is taken as universal: every simulation environment in scope has one, so it needs no plugin-declared role. The eight sites were never one thing anyway — see below. What *was* real in them is fixed |
| ~~`producer_commands = {"Allrun"}`~~ **done 2026-09-01** | `workflow.py:426`. The literal meant a plugin whose entrypoint has any other name had its own run step left out of the producer set, so unclaimed artifacts were credited to **no step at all** |
| ~~`generic_case.py:137`'s `Allrun`~~ **done 2026-09-01** | the one-step DAG invoked a script the case need not contain. `make_spec` and `_workflow_dag_for` take an optional `driver_context`; with none, both fall back to the same documented default `registry.py` uses, so the two agree by construction rather than by coincidence |
| ~~`tutorial_contracts.py`'s `openfoam.` prefix split~~ **done 2026-09-01** | not in the original list — found while wiring the above. `role.startswith("openfoam.")` answered "is this the environment's file?" correctly for every shipped role and wrongly for every escape role, filing a foreign environment's required inputs under **core's own**. Now `is_environment_role()`, which asks the closed question (is the namespace `plugin` or `case`?) rather than the open one |

#### What Tier 2 leaves behind

~~One literal survives deliberately. `provenance_inputs.py:111` matches
`rule.role == "openfoam.control_dict"` to find the case's control file, and
there is no generalisation available: core needs *the* control file, and a
foreign environment's escape role (`x-fenics.something`) does not tell it
which of several declared files that is. Fixing it needs either a
namespace-neutral role name or a capability hook — a contract to design, not
a wiring job, so it belongs in Tier 3 and has been moved there.~~ **done
2026-09-01, Tier 3** — resolved by a capability hook, not a role rename; see
below. `provenance_inputs.py` no longer names `openfoam.control_dict` at all.

`workflow.py`'s `missing_workflow_dag` diagnostic also still says "A case
folder needs an executable Allrun" in user-facing prose. Cosmetic, but it will
read as a lie to the first non-OpenFOAM plugin author.

**A note on how the three fixed sites were verified.** Each was reverted to its
literal to confirm the new tests fail. Two were caught immediately; the
`tutorial_contracts` revert was **not** — the parametrized test covered
`is_environment_role` itself, which passes whether or not the call site invokes
it. That needed a separate test driving `describe_tutorial_contract` end to end
with a foreign plugin. Fifth instance in this repository of a guard that looks
correct and checks nothing, and the reason every new guard here is mutated
before it is trusted.

#### Why the eight `postProcessing` sites were not one item

Kept because the miscount is instructive, not because the work is pending.
They carried three different meanings behind one string:

1. **the solver's output directory** — genuinely OpenFOAM's convention, not
   core presuming anything. Every C++ verifier and every OpenFOAM
   `functionObject` independently computes `<time>.globalPath()/"postProcessing"`,
   which is exactly why `output_collection.py` can archive a case's output
   without knowing what produced it. Correctly hardcoded.
2. **core's own bookkeeping** (`workflow_state.json`, `workflow_logs/`) — core's
   entirely, and *already* parameterised: `execution_context.py:62` defines it
   as `output_dir / "workflow_state.json"` and never names `postProcessing`. A
   plugin-declared role here would have been actively wrong; it would let a
   plugin relocate core's own state file.
3. **exclusion vocabulary** — `registry.py`'s "not a case directory" and
   `sweep_runner.py`'s "generated directory" are two different predicates that
   merely overlap. Neither is an output-directory role.

The real defect was in none of those categories: **three sites hardcoded the
default *value* of `output_dir_name` instead of reading it**, so overriding it
made core write `results/workflow_state.json` while `artifacts.py` kept
promising `postProcessing/workflow_state.json`. Reachable today with no second
plugin. Fixed 2026-09-01; `workflow_runner.py`'s `log_dir` default — a dead
third copy that also anchored on the wrong root — is gone with it.

The lesson worth keeping: **a count of grep hits is not a count of concepts.**
The `Allrun` entrypoint role really did close five sites, because `Allrun` meant
one thing at all five.

### Tier 3 — needs a contract designed

| item | outcome |
|---|---|
| ~~`provenance_inputs.py`'s `openfoam.control_dict` lookup~~ **done 2026-09-01** | moved from Tier 2: needed a namespace-neutral role or a capability hook, not wiring. Landed as `CaseIntrospectionCapability.selected_start_time()` — a new optional hook, `get_selected_start_time(case_root, resolved_case)`, alongside `resolve_case_models`/`get_samplable_fields`. `openfoam.control_dict`'s only consumer in the whole codebase was this one question ("what start time does this run resume from?"), so rather than generalise the role, core now lets the plugin answer the question outright. The fallback (`legacy_selected_start_time`) is today's OpenFOAM-shaped logic verbatim — `KNOWN_ROLES` is untouched, zero behaviour change for a plugin that implements nothing new. As a side effect this also resolves the adjacent `startFrom`/`startTime`/`latestTime`/`firstTime` keyword-vocabulary defect from §3/§8: that logic now lives entirely in the fallback, not in core proper. Proven by `test_plugin_implemented_start_time_hook_overrides_the_openfoam_default` in `packages/omnidriver/tests/core/test_provenance_inputs.py` — a plugin declaring **no** `openfoam.control_dict` role at all still gets its own start time honoured end to end |
| ~~a seam for `processor*`~~ **done 2026-09-01** | four sites — `provenance_inputs.py` (I9 decomposed-restart walk), `workflow_runner.py` (accepting a not-yet-reconstructed parallel location as evidence a time-indexed artifact was produced), `registry.py` (pruning it during tutorial discovery), `sweep_runner.py` (excluding it when staging a fresh sweep case, where *not* recognising a foreign plugin's differently-named decomposition dir would have re-copied stale output — exactly the bug that staging boundary exists to prevent). Unlike `control_dict`, this didn't need a capability hook computing a value from case state — `processor*` names a wildcard family, not a single static path a `CaseFileRule` role can hold, so it is a bare no-argument optional hook (`get_decomposition_dirname_prefix()`) on `CaseFileContractCapability`, the same shape as `get_phases()`. Default `"processor"`; `plugin_profile.decomposition_dirname_prefix(driver_context)` wraps it and returns the default directly when `driver_context` is `None`, mirroring `entrypoint_relpaths()`. `run_workflow_step()`/`_stage_entry_case()` gained a `driver_context` parameter they didn't carry before (threaded from `cli.py`/`_materialize_entry_case()`, both of which already had it in scope) |
| ~~`apply_overrides` raw-traceback crash~~ **done 2026-09-01** | `legacy_apply_overrides` (`compatibility.py`) did an unconditional `from omnidriver.openfoam.apply_overrides import ...`; in a core-only install (or any plugin without that package and without its own `apply_overrides()` hook) this raised `ModuleNotFoundError` uncaught — `cli.py`'s `except (OSError, ValueError)` around the call does not catch it. Reproduced directly by blocking the import via `sys.modules[name] = None` before the fix, confirmed clean after. The fix is deliberately narrow and does **not** add a neutral default: applying an override means writing bytes into a dict file whose syntax only `omnidriver-openfoam`'s mutators understand, so there is no safe universal answer the way there is for e.g. environment diagnostics — same shape as `route_sweep_case_values`/`materialize_sweep_case` already refusing by name rather than pretending to be neutral. The import is now wrapped in `try/except ImportError`, re-raised as a plain `ValueError` (not `OverrideError`, which lives in the package that may not be importable) naming the plugin via `driver_context.identity.id` — not `driver_context.plugin.plugin_id`, which `test_plugin_dependency_boundary.py` forbids outside `plugin_capabilities.py`/`plugin_interface.py`. `apply_overrides.py` itself needed no change — it already lives in `omnidriver-openfoam`, not core; only core's fallback *wiring* was the defect. Proven by `test_the_fallback_refuses_cleanly_when_openfoam_is_not_installed` in `packages/omnidriver/tests/core/test_override_apply_threads_a_context.py` |
| ~~`ArtifactFormat` + `utility_catalog` vocabulary~~ **done 2026-09-02** | see §3 rows above. Two files, no capability/hook needed — this one really was mechanical once the real-usage grep confirmed which values were core's and which were the plugins' |
| ~~`--openfoam-bashrc` rename + `EnvironmentPreflightCapability` naming split~~ **done 2026-09-02** | see §3 row above. Sized as "~6 files, mechanical" going in; tracing every real site found 11 across all three packages once `runtime/generic_case.py`'s `CaseConfig.params` JSON key was accounted for — genuinely mechanical once scoped correctly, but the scoping itself was the work |

**Tier 3 closed 2026-09-02.** All six items landed; every one turned out to be either a bare optional hook (`selected_start_time`, `decomposition_dirname_prefix`) or a rename/removal (`ArtifactFormat`, `utility_catalog` vocabulary, `apply_overrides`'s fallback wiring, `--openfoam-bashrc`) — none needed the heavier "registration" or namespace-neutral-role machinery §11 considered and rejected for role vocabulary. Next: Tier 4.

### Tier 4 — the trust boundary, unchanged from §5b

`CASE_SCRIPT_COMMANDS`, `CORE_NEUTRAL_COMMANDS`, `_is_installed_openfoam_app`.
These decide what may execute and what may resolve to a case-local binary
rather than PATH. They need their own pass with a threat model extending
`SECURITY.md`, and they are correctly deferred until the tiers above are done.

## 11. The role-vocabulary escape tier (Phase 3 Task 3b, landed 2026-09-01)

§3's hard block is fixed. The fix is deliberately narrow: it opens a tier for
a role core cannot possibly own the vocabulary for, and touches nothing else
about `KNOWN_ROLES`.

| tier | shape | validated how | status |
|---|---|---|---|
| Tier 1 — core-owned namespaces | `openfoam.*`, `plugin.*`, `case.*` | exact string membership in `KNOWN_ROLES`, a closed `frozenset` | unchanged, Phase 1 Task 2 |
| Tier 2 — foreign-environment escape | `x-<namespace>.<leaf>` | shape only: both segments non-empty, `<namespace>` not one of the three reserved words. `<namespace>`/`<leaf>` spelling is never checked | **new**, this task |

Rejected outright, no tier accepts them: a role with no dot at all (`control_dict`),
and any role that isn't in `KNOWN_ROLES` and doesn't carry the `x-` marker.

### Reservation: the marker privileges OpenFOAM, and the goal is that it should not

Recorded against this design rather than deferred silently. The brief's stated
acceptance was that a bare `fenics.mesh_file` load; what landed requires
`x-fenics.mesh_file`. The reasoning for the change is sound -- bare
unknown-namespace acceptance would have swallowed `opnefoam.control_dict` -- but
the shape it produces says `openfoam.*` is the standard vocabulary and every
other environment is an extension. That is backwards relative to where this is
going: the end state has OpenFOAM as *a* plugin, peer to any other, not the
namespace the enum is built around.

The third option in the brief avoids both problems and was rejected only on the
cost of a schema field: a profile that declares its own namespaces
(`namespaces: [fenics]`) may then use `fenics.mesh_file` unmarked, and
`opnefoam.control_dict` still fails -- because `opnefoam` was never declared.
That is strictly stronger typo-catching *and* peer status, for one key.

Not changed now: there are zero non-OpenFOAM plugins, so the migration cost is
near zero today and rises only once the first one exists. Revisit before that,
not after.

### Why a marker prefix, not a bare "unknown namespace passes" rule

The design brief for this (§10's Tier 2 first row) offered three shapes: a namespace-based rule with no
marker (an unrecognised dotted prefix is accepted outright), an explicit
escape prefix, or a registration step where a plugin lists its own
namespaces. The first was rejected specifically because of what it does to
the typo case that Phase 1 Task 2 exists to catch.

Under a bare namespace rule, `openfoam.control_dict` misspelled as
`opnefoam.control_dict` is **not** a typo of a known namespace as far as the
validator can tell — `opnefoam` is just another unrecognised prefix, so it
would load silently, exactly the failure mode the closed enum was built to
prevent (`plugin_capabilities.py:461`). A registration step (the plugin
lists `custom_role_namespaces: [fenics]` in its own YAML) closes that gap
almost as well, but only by adding a second field a plugin author could
equally typo, and by making every profile schema change carry a new
required/optional key.

The `x-` marker gets the same protection more cheaply: getting through the
escape hatch requires typing two characters (`x-`) that no fat-fingering of
`openfoam.`, `plugin.`, or `case.` produces by accident. It also composes
directly with `tutorial_contracts.py:123,127`'s `role.startswith("openfoam.")`
split — an escaped role never starts with `openfoam.`, so it is never
misfiled as solver-owned, with no change needed at that call site.

### What a typo costs now, compared to before

- **A typo inside a known namespace — unchanged, still a load-time
  `ValueError`.** `openfoam.controldict`, `openfoam.control_dickt`, and bare
  `control_dict` all still raise, verified by
  `test_a_typo_in_a_known_namespace_still_raises_under_the_escape_tier` in
  `packages/omnidriver/tests/core/test_plugin_profile.py`. This is the
  guarantee Phase 1 Task 2 introduced, and it is 100% intact.
- **A typo of the escape marker itself against a reserved namespace — also
  caught.** `x-openfoam.control_dict`, `x-plugin.configuration`, and
  `x-case.documentation` are rejected: the namespace-after-`x-` may not be
  one of the three reserved words, so the escape hatch cannot be used to
  quietly dodge the closed-enum check on something that looks like it
  should be core's.
- **A typo *inside* an escaped foreign namespace or leaf — genuinely not
  caught, and cannot be**, e.g. `x-fenics.msh_file` (missing an `e`) loads
  without complaint. Core has no FEniCS vocabulary to check that spelling
  against; validating it would mean core inventing and owning a vocabulary
  for an environment it is explicitly not supposed to know about, which is
  the exact thing this whole document argues against. This is the residual
  gap under every shape considered, escape-prefix or otherwise — a
  registration step narrows it slightly (a *consistent* typo across both the
  registration list and the role string is required to slip through) but
  does not close it, at the cost noted above.
- **A typo that produces something that merely looks like a new environment's
  own namespace but is actually a typo of `openfoam`/`plugin`/`case` — the
  one gap a bare "unknown namespace passes" rule would have had — does not
  arise under the chosen design**, because nothing except the `x-` marker is
  ever treated as an escape. A role with no marker and no exact `KNOWN_ROLES`
  match is rejected regardless of how namespace-shaped it looks.

### Where this is proven

`packages/omnidriver/tests/core/test_plugin_profile.py`:
`test_an_escape_role_for_a_foreign_environment_loads` (the literal acceptance
test — `x-fenics.mesh_file` loads via `load_plugin_profile`),
`test_a_typo_in_a_known_namespace_still_raises_under_the_escape_tier`,
`test_a_malformed_or_shadowing_escape_role_still_raises`, and
`test_a_non_openfoam_role_survives_driver_context_end_to_end` (constructs a
`PluginProfile` with an escape-tier role directly, passes it through
`driver_context(...)`, and confirms the rule comes back out of
`capabilities.case_files.all_rules()`/`required_rules()` unchanged).
