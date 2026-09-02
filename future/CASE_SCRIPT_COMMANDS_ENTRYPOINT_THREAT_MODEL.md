# Threat model: letting a plugin's declared entrypoint resolve case-locally

**Status: implemented, 2026-09-02.** Extends `SECURITY.md`'s existing
command-boundary threat model for one narrow change — the entrypoint slice of
Tier 4 (`future/ENVIRONMENT_CONTRACT.md` §10). Written before touching code,
per that document's own instruction: Tier 4 "need[s] its own pass with a
threat model extending `SECURITY.md`", not a discovery-cleanup pass like
Tier 1–3.

All six sites in §4 landed exactly as designed, plus site 6's
`entrypoint_relpaths_from_profile` helper in §5 (extracted so
`generic_plugin.py`/`cardiacfoam_plugin.py` don't each reimplement the same
rule-filtering). Verified both by the automated suite
(`test_case_script_commands_entrypoint_seam.py`, `omnidriver-openfoam`'s
`test_a_declared_entrypoint_is_also_not_path_checked`, and a new case in
`test_trust_boundary_end_to_end.py`) and manually end to end, because
`test_trust_boundary_end_to_end.py` is entirely `skip_without_monorepo`-gated
in a standalone checkout — the automated pass alone would not have caught a
regression there, which is exactly why the new
`test_case_script_commands_entrypoint_seam.py` exists as monorepo-independent
coverage of the same invariant. Both shipped plugins produce byte-identical
`case_scripts` output before and after (verified directly), confirming zero
behavior change for `GenericOpenFOAMPlugin`/`CardiacFoamPlugin`.

## 1. The problem, verified

`CASE_SCRIPT_COMMANDS = frozenset({"Allrun", "Allclean", "Allrun.pre",
"Allrun.post"})` (`core/runtime/workflow.py`) is a hardcoded literal,
completely decoupled from `entrypoint_relpaths(driver_context)` — the
generalized entrypoint accessor Phase 1/2 already built and wired into case
detection (`registry.py`) and DAG generation (`generic_case.py`'s
`_workflow_dag_for`, `workflow.py`'s producer-command heuristic).

Consequence, confirmed by reading (not assumed): a plugin that declares
`openfoam.entrypoint` on a path other than exactly `"Allrun"` gets correct
case detection and a correct DAG, then dies at the command allowlist — the
step's command is in neither `CORE_NEUTRAL_COMMANDS`, `plugin_commands`, nor
`CASE_SCRIPT_COMMANDS`, so `validate_workflow_commands` rejects it with
`unknown_workflow_command`. Even if a plugin worked around this by also
declaring the name via `CommandAuthorizationCapability.auxiliary_commands()`,
`_resolve_command` would still only try PATH (`CASE_SCRIPT_COMMANDS` gates
case-local resolution too), and a case-local script is never on PATH — so it
would fail differently, not run.

**Currently invisible.** Both shipped plugins declare `path: Allrun` for
`openfoam.entrypoint` (`core/generic-plugin.yaml`, `cardiacfoam/plugin.yaml`),
which is already in the hardcoded set. Zero observable breakage exists today;
this is a gap for the first plugin that names its entrypoint anything else.

## 2. Trust-boundary analysis (why this is lower-risk than it looks)

`SECURITY.md` names exactly two untrusted-input classes: the agent-authored
`RunDocument` (validated once at ingestion) and case-authored script content
("untrusted, unsandboxed by design — running a case runs its scripts").
Everything else — `omnidriver`/`openfoam_driver` itself, and by extension any
loaded plugin, since a plugin is arbitrary in-process Python with no sandbox
boundary from core — is **Trusted**.

The value this change lets flow into `CASE_SCRIPT_COMMANDS` — the plugin's
declared entrypoint path — is set in the plugin's own static profile
(`get_profile().case_files`, a `CaseFileRule` list authored by the plugin's
developer). It is never influenced by `RunDocument` content or case-folder
content, the two things `SECURITY.md` actually distrusts. So this change does
not expand *who* can make a bare name resolve case-locally — it only lets an
already-trusted plugin author choose their own name from a namespace whose
size and shape (a handful of role-declared paths) doesn't change. The
attacker model `SECURITY.md` is built against — a malicious `RunDocument`, or
a case folder trying to shadow a PATH binary — is unaffected: neither can
name an arbitrary plugin's own entrypoint role.

**What is a genuine (but pre-existing, not newly introduced) residual risk:**
a plugin author who carelessly names their entrypoint role e.g. `"python"` or
`"bash"` would make case-local shadowing apply to that name for their plugin.
This is a plugin-author footgun, not an escalation — the same trust level
already lets a plugin author do far worse (arbitrary code executes on load).
Not mitigated by this change, same as `SECURITY.md`'s existing "Explicitly
NOT mitigated: arbitrary code inside an invoked `Allrun`" already accepts.

## 3. Scope

**In scope:** the entrypoint name only (`openfoam.entrypoint` /
`entrypoint_relpaths()`), reusing existing, already-shipped machinery.

**Explicitly out of scope, deferred:**
- `Allclean` / `Allrun.pre` / `Allrun.post`. `openfoam.cleanup` is declared
  in `KNOWN_ROLES` and both shipped plugins mark `Allclean` with it, but
  **nothing in core reads that role anywhere** — there is no
  `cleanup_relpaths()` equivalent to `entrypoint_relpaths()`. Generalizing
  these needs new role-reading infrastructure designed from scratch, not a
  wiring pass reusing an existing accessor. A separate, later task.
- `CORE_NEUTRAL_COMMANDS` — a foreign plugin already has a working escape
  hatch (`CommandAuthorizationCapability.solver_commands()`/
  `.auxiliary_commands()`, confirmed plugin-owned via
  `cardiacfoam/command_authorization.py`), so this being OpenFOAM-shaped
  costs nothing; a foreign plugin's DAG simply never references these 11
  names.
- `_is_installed_openfoam_app` (`$FOAM_APPBIN`/`$FOAM_USER_APPBIN`) — one
  call site, harmlessly returns `False` for a foreign plugin and falls
  through to the other allowlist paths already. Low value, not touched here.

## 4. The six sites, and exactly what each needs

All must move together — landing a subset creates a worse bug than doing
nothing (e.g. fixing execution but not the preflight PATH-existence check
would make a *working* plan get refused before it starts).

| # | site | today | change needed |
|---|---|---|---|
| 1 | `workflow.py: validate_workflow_commands` | checks bare `CASE_SCRIPT_COMMANDS` (2 sites: bare-name branch, `./<name>` explicit-path branch) | already takes `driver_context`; swap both checks for the new accessor |
| 2 | `workflow_runner.py: _resolve_command(command, cwd)` | no `driver_context` param | add `driver_context: Any | None = None`; both existing callers already have one in scope (see below) |
| 3 | `workflow_runner.py: _argv_for_execution(command, executable, args, env)` | no `driver_context` param | add it; its one caller (`run_workflow_step`) already has one in scope |
| 4 | `provenance_inputs.py: _is_case_local_script(...)` | no `driver_context` param | add it; its one caller (`_register_step_executable`, itself called from `enumerate_case_inputs`, which already has `driver_context`) needs the param threaded one level further |
| 5 | `omnidriver-openfoam/environment_preflight.py: _required_executables(workflow_dag)` | no `driver_context` param | add it; both call sites are inside `_environment_diagnostics`, which already takes `driver_context` |
| 6 | `capability_manifest.py: build_capability_manifest(...)` | no `driver_context`, no case-script param at all — pure assembly from explicit plugin-supplied inputs by design | **cannot** thread `driver_context` cleanly (see §5) — needs a different shape |

Sites 1–5 all resolve the same way: a new free function,
`case_script_commands(driver_context: Any | None) -> frozenset[str]`, living
in `plugin_profile.py` next to `entrypoint_relpaths`/
`decomposition_dirname_prefix` (same file, same "documented default,
`None`-safe" shape those two already use):

```python
def case_script_commands(driver_context: Any | None) -> frozenset[str]:
    """Bare command names that may resolve to a case-LOCAL executable.

    The Allrun-family fixed names always qualify -- OpenFOAM's own
    convention, and every shipped plugin's default -- unioned with the
    active plugin's declared entrypoint path(s), so a plugin naming its
    entrypoint anything else still gets case-local resolution for that
    exact name. Allclean/Allrun.pre/Allrun.post stay fixed: no role exists
    yet for a plugin to name its own cleanup/pre/post scripts (see
    future/CASE_SCRIPT_COMMANDS_ENTRYPOINT_THREAT_MODEL.md §3).
    """
    return CASE_SCRIPT_COMMANDS | frozenset(entrypoint_relpaths(driver_context))
```

`CASE_SCRIPT_COMMANDS` itself stays exactly as it is today (still exported,
still the base/fixed set) — this is additive, not a rename, so any other
reader that still wants "the fixed OpenFOAM-family names only" keeps working
unchanged. `workflow.py` already imports `entrypoint_relpaths` from
`plugin_profile` (used at line 428 for the producer-command heuristic, the
Tier 2 fix this mirrors exactly) — precedent, not a new pattern.

Threading is mechanical for sites 1–5 (every intermediate function already
has `driver_context` one call away, confirmed by reading each caller):

- `run_workflow_step` (already takes `driver_context`, added for the
  `processor*` seam) passes it to both `_resolve_command` and
  `_argv_for_execution`.
- `enumerate_case_inputs` (already takes `driver_context`) passes it through
  `_register_step_executable` (new param) down to `_resolve_command` and
  `_is_case_local_script`.
- `_environment_diagnostics` (already takes `driver_context`) passes it to
  `_required_executables`.

## 5. Site 6 needs a different shape, not `driver_context`

`build_capability_manifest`'s two real callers are
`GenericOpenFOAMPlugin.get_capabilities(self)` and
`CardiacFoamPlugin.get_capabilities(self)` — plugin methods called with only
`self`, before any `DriverContext` necessarily wraps them (a `DriverContext`
is constructed *from* a validated plugin; `get_capabilities()` doesn't
receive one back). Threading `driver_context` into
`build_capability_manifest` would need a `DriverContext` at a point in the
lifecycle where one doesn't reliably exist yet.

The clean fix doesn't need one: each plugin already has direct access to its
own declared entrypoint via `self.get_profile().case_files` — no
`DriverContext` indirection required for a plugin to introspect its own
profile. Add a plain parameter instead:

```python
def build_capability_manifest(
    *,
    plugin_commands: Iterable[str] = (),
    utility_manifests: dict[str, Any] | None = None,
    samplable_fields: dict[str, tuple[str, ...]] | None = None,
    case_script_commands: frozenset[str] = CASE_SCRIPT_COMMANDS,
) -> dict[str, Any]:
```

and at each `get_capabilities()` call site, compute the entrypoint-aware set
from `self.get_profile().case_files` directly (the same rule
`entrypoint_relpaths` applies, just reading the profile instead of a
`DriverContext`) and pass it in. Lower priority than sites 1–5 — this is
advertisement (what `describe` shows an agent), not enforcement — but should
land in the same change so the manifest doesn't lie about what the allowlist
actually accepts.

**Implementation note:** rather than inline the rule-filtering twice (once
per plugin), `plugin_profile.py`'s `entrypoint_relpaths(driver_context)` was
split into a shared `_entrypoint_relpaths_from_rules(rules)` plus a new
`entrypoint_relpaths_from_profile(profile)` that both `entrypoint_relpaths`
and each plugin's `get_capabilities()` call — one place owns "what counts as
a declared entrypoint", read from either a `DriverContext` or a
`PluginProfile` directly.

## 6. What must not regress

`packages/omnidriver/tests/core/test_trust_boundary_end_to_end.py` encodes
every `SECURITY.md` claim as a runnable assertion (17 tests). Two are
load-bearing for this specific change:

- `test_case_directory_cannot_shadow_a_trusted_path_binary` — asserts
  `_resolve_command("blockMesh", case_root)` stays PATH-only even with a
  case-local `blockMesh` shadow file present, while `_resolve_command("Allrun",
  case_root)` resolves case-locally. This exact asymmetry — fixed
  `CORE_NEUTRAL_COMMANDS` names never resolve case-locally, only the
  (now-extended) entrypoint set does — must survive unchanged. Extend this
  test with a third case: a plugin declaring a differently-named entrypoint
  gets case-local resolution for *that* name, while `blockMesh` still doesn't.
- `test_command_allowlist_has_one_owner_shared_by_both_producers` — the
  single-owner property. A third caller of `validate_workflow_commands`
  exists beyond the two `SECURITY.md` names it explicitly calls out
  (`strict_planning.py`, `run_document_exec.py`): `cardiacfoam/dict_builder.py`'s
  `build_and_launch`. All three must keep agreeing; none may special-case the
  allowlist.

Also affected, needs a same-plugin regression case (both shipped plugins
still declare `"Allrun"`, so `case_script_commands(driver_context)` returns
exactly `CASE_SCRIPT_COMMANDS` unchanged for them today — the new test needs
a plugin fixture declaring a different entrypoint name, matching how Tier 3's
`test_plugin_implemented_start_time_hook_overrides_the_openfoam_default` and
`test_plugin_implemented_decomposition_prefix_hook_overrides_processor`
proved their respective seams with a genuinely foreign-shaped test plugin,
not just an assertion against the shipped ones).

## 7. Sequencing

**Done.** Sites 1–6 landed together in one change, including the extended
`test_case_directory_cannot_shadow_a_trusted_path_binary` coverage (as a new
sibling test, not a rewrite of the existing one) and the manifest
advertisement. `Allclean`/`Allrun.pre`/`Allrun.post`, `CORE_NEUTRAL_COMMANDS`,
and `_is_installed_openfoam_app` stay exactly as
`future/ENVIRONMENT_CONTRACT.md` §10 Tier 4 already scoped them: deferred,
each carrying a comment naming it as an OpenFOAM-family default and pointing
here.
