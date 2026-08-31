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
| §7 the cardiac `Phase` enum | open — Phase 2 Task 3 ports `get_phases()` |

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

| Generic concept | OpenFOAM binding | Role declared? | Consumed by core? |
|---|---|---|---|
| case directories to walk | `system`, `constant` | `openfoam.case_directory` | **yes** — `provenance_inputs.py:93` derives from declared path segments |
| time-control document | `system/controlDict` | `openfoam.control_dict` | **yes** — `provenance_inputs.py:111` |
| plugin vs environment file split | — | prefix `openfoam.` / `plugin.` | **yes** — `tutorial_contracts.py:123,127` |
| entrypoint script | `Allrun` | `openfoam.entrypoint` | **yes, since Phase 1** — `registry._entrypoint_relpaths()` resolves it by role, falling back to `("Allrun",)` when a plugin declares none. `generic_case.py:137` is still hardcoded: it has no `driver_context` at all (Phase 2) |
| cleanup script | `Allclean` | `openfoam.cleanup` | **no** — declared, read nowhere |
| mesh generation input | `system/blockMeshDict` | `openfoam.mesh_generation` | **no** — declared, read nowhere |
| trusted executable roots | `$FOAM_APPBIN`, `$FOAM_USER_APPBIN` | — | **no seam** — `os.environ` read directly at `workflow.py:483` |
| environment-neutral commands | 11 OpenFOAM/gmsh binaries | — | **no seam** — frozenset literal at `workflow.py:52`; `CommandAuthorizationCapability` is union-only, a plugin can add but never replace |
| case-local executable names | `Allrun`-family | — | **no seam** — `CASE_SCRIPT_COMMANDS`, `workflow.py:74` |
| parallel decomposition dirs | `processor*` | — | **no seam** — glob at `provenance_inputs.py:356` |
| artifact formats | `openfoam_time_dirs`, `openfoam_log` | — | **closed `Literal`**, `models.py:36` |
| dictionary editing phases | *(cardiac, not OpenFOAM)* | — | **closed `Literal`**, `run_model.py:44` |

Two further facts:

- ~~**`role` is unvalidated.**~~ **Fixed in Phase 1 Task 2.**
  `plugin_profile.KNOWN_ROLES` is the eleven-role enum, enforced at profile
  load, so `control_dict` instead of `openfoam.control_dict` now fails loudly
  instead of being silently reclassified as plugin-owned. Both shipped profiles
  loaded unchanged — the enum described reality rather than constraining it.
- **A binding can hide in a helper's *location*, not just its name.**
  `catalogued_paths` parses core's own `DictEntry.driver_path`; it reads no
  file and knows no C++. It lived in the OpenFOAM C++ dict-key scanner, so
  moving that scanner out of core (Phase 2 Task 2) silently made core's
  `strict_plan` depend on `omnidriver.openfoam` — and unavoidably, because it
  is called *eagerly* to build an argument, before the capability can dispatch
  to a plugin's own hook. Fixed by splitting the vocabulary
  (`core/contracts/catalogue_paths.py`) from the scanning. The rule in §4 has
  to be applied to what a function *does*, not to the module it happens to
  sit in.
- **`generic-plugin.yaml` declares OpenFOAM paths.** `system/controlDict` and
  `constant`. So renaming `GenericOpenFOAMPlugin` without changing what it
  declares would be cosmetic.

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

Until then, `CASE_SCRIPT_COMMANDS`, `CORE_NEUTRAL_COMMANDS`,
`_is_installed_openfoam_app`, the `processor*` glob, and `ArtifactFormat` stay
hardcoded, each carrying a comment naming it as an OpenFOAM-family default and
pointing here.

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
