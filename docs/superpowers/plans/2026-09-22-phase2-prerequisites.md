# Phase 2 Prerequisites: Composition, Evidence and Addressing — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the eight audit findings that must land before any write-channel
refactor can be trusted — deterministic provider composition, truthful
resolution provenance, effective-value readback through the real public path,
native include parity, and qualified parameter addressing in cardiacCore.

**Architecture:** Nothing here is a new abstraction. Each task repairs one
existing symbol so that a guarantee the codebase already claims becomes true.
They are deliberately independent: any task can be reviewed and committed on its
own, and a failure in one does not block the others. Tasks 5–7 run in order
because Task 7 deletes a workaround Task 5 makes unnecessary.

**Tech Stack:** Python 3.11+, pytest, `graphlib`. No new runtime dependency.

**Source:** [`docs/audits/2026-09-22-implementation-roadmap.md`](../../audits/2026-09-22-implementation-roadmap.md)
§3 (findings C1, C2, C3, F1, F1b, F2, S1, S2, S3) and §5 gate **G0**.
This plan is gate G0 in full. Gates G1–G3 are
[`2026-09-20-phase2-one-write-channel.md`](2026-09-20-phase2-one-write-channel.md),
which must not start until this plan closes.

## Status

| task | finding | state | commit |
|---|---|---|---|
| 1 · deterministic provider order, duplicate identities refused | C1 | done | `9bb8c7c` |
| 2 · resolution provenance names the provider that answered | C3 | done | `0bab354` |
| 3 · `execution_env` reaches the hook; readback compares typed values | F1, F1b | done | `e2fead3` |
| 4 · `#includeEtc` follows the native search chain | F2 | done | `d0f13ed`, corrected `628e39e`, corrected again `0f9654c` |
| 5 · cardiacCore addressing keeps document scope; values are checked | S1 | done | `bd8b89e` |
| 6 · final workflow inputs are resolved once, from effective config | S3 | done | `3b1e0f5` |
| 7 · `validate_configuration` is wired to the plugin | S2 | done | `97ac44c` |
| 8 · required-check coverage blocks at the dispatch boundary | C2 | done | `75ba387` |
| 9 · four shapes, static gates, and the close-out | — | done | (this commit) |

**G0 closed 2026-09-22, after review R1 held it open once.** R1's verdict was
**not closed**, on three blockers, all now resolved:

* **B1** — `find_etc_file` still disagreed with the real `foamEtcFile` under
  `$FOAM_CONFIG_ETC` and `$FOAM_CONFIG_MODE`, measured. Closed by `0f9654c`;
  the candidate list now matches `foamEtcFile -list` entry for entry in the
  default, `o`, `u` and `go` modes, verified twice independently.
* **B2** — neither variable appeared in `environment_keys`, so a Phase 2
  precondition set could not have detected one appearing. Closed by the same
  commit; the set is now nine keys, recorded unconditionally by deliberate
  choice.
* **B3** — the Status table claimed C2 without saying the gate is wired and
  **unfed**. Closed above, with the grep evidence, in C2's own row.

R1 is the reason F2 is right. Its fixtures passed at `628e39e`; only comparison
against the real binary found the gap — the second time on this one task that a
complete, passing fixture set accompanied a wrong implementation. Weigh that
when deciding how much evidence a "confirmed" claim needs in later gates.

All eight findings reproduce no longer; four
installation shapes and both static gates pass. Phase 2
(`2026-09-20-phase2-one-write-channel.md`) may begin at G1.

### Confirmed against a native runtime, 2026-09-22

An OpenFOAM v2412 install is present at `/Volumes/OpenFOAM-v2412` on this
machine, found via `discover_openfoam_bashrc()` in
`omnidriver.openfoam.openfoam_environment` -- **not** via `command -v
foamDictionary` or `$WM_PROJECT_DIR`, both of which are empty until that
discovery runs. Batch G0-D re-ran both native probes directly, rather than
taking the earlier batches' word for them:

- **F1b:** requesting `deltaT 1e-3` resolves through the real
  `resolve_effective_foam_entry` as `'0.001'`, and `writeInterval 2.0` resolves
  as `'2'`. `effective_values_agree` reports both as agreeing. Both were false
  rejections under the old string comparison.
- **F2:** `find_etc_file` was checked against the real `foamEtcFile` binary
  (`$WM_PROJECT_DIR/bin/foamEtcFile`) for both an ordinary lookup
  (`controlDict`, `caseDicts/mesh/generation/snappyHexMeshDict.cfg` -- both
  select `/Volumes/OpenFOAM-v2412/etc/...`, agreeing exactly) and the
  shadowing case (a file written to `$HOME/.OpenFOAM/2412/controlDict`,
  removed afterward): both the native binary and `find_etc_file` select the
  user file over the distribution one. Full five-location order confirmed
  empty above the selected file in the ordinary case.

Neither F1b nor F2 remains untested against a native runtime as of this date;
Task 9 Step 5's premise that this machine cannot establish them does not
apply once the runtime is discovered correctly.

### The `provides:` finding (Task 2 Step 5), re-run 2026-09-22

```
org.cardiacfoam: implements but does not declare ['case_introspection', 'case_provenance', 'command_authorization', 'environment_preflight', 'mesh_diagnostic_policy', 'override_scopes', 'runtime_evidence']
org.omnidriver.cardiaccore: implements but does not declare ['artifacts', 'case_files', 'case_introspection', 'case_provenance', 'command_authorization', 'configuration_validator', 'run_semantic_validator', 'runtime_evidence']
org.omnidriver.openfoam.environment: implements but does not declare ['artifacts', 'case_files', 'case_introspection', 'command_authorization', 'configuration_validator', 'cxx_mapping', 'dictionaries', 'manifest', 'mesh_diagnostic_policy', 'named_catalogs', 'run_document_configuration', 'run_semantic_validator', 'runtime_evidence', 'tutorials']
```

Every installed provider implements a large set of capabilities it never
declares (the OpenFOAM environment alone: 14, including `dictionaries`,
`manifest` and `tutorials`). This is an input to the Phase 2 G1
capability-exposure decision, not a change made here: enforcing `provides:`
as an export filter today would refuse every stack that currently works.

### Plan defects found and corrected during execution

Recorded as evidence that this plan was executed against the real codebase,
not assumed correct as written:

- **Task 2:** `get_selected_start_time` maps to the `case_introspection`
  capability, not one named `selected_start_time`, and it is not digested --
  the plan's illustrative test could not have passed as written. The plan also
  had a broken fixture-inheritance shape and a wrong
  `discover_plugins()`/`load_discovered_plugin()` API shape (`discover_plugins()`
  returns `dict[str, EntryPoint]`; `load_discovered_plugin(name)` returns a
  `DriverContext`, not a plugin -- the provider objects are at `.providers`).
- **Task 3:** `_format_value([1, 2, 3])` returns the Python literal
  `"[1, 2, 3]"`, not OpenFOAM's `"(1 2 3)"` -- the task's own vector test case
  could not have passed as written. `apply_overrides` also had seven non-build
  implementers to update (three production sites plus four test fixtures), not
  three.
- **Task 4:** the original three-location search chain was wrong in four ways
  against this ESI v2412 build (API-number vs. `v`-prefixed version segment,
  missing unversioned user/site fallbacks, site deriving from `WM_PROJECT_DIR`
  rather than `WM_PROJECT_INST_DIR`) and was corrected only after the native
  probe ran. Its fixtures had all passed regardless.
- **Task 6:** the unreadable-case test assumed `read_input_values` raises; it
  does not. The test was removed with a dated note, and the concern is covered
  by Task 7's wiring instead -- an empty case now yields eight error
  diagnostics at plan time.
- **Task 7:** patching `_slice_value` alone was insufficient;
  `_evaluate_structured` reads presence through
  `_entry_value_present`/`_predicate_matches`, which also needed the qualified
  lookup. `validate_configuration` needed a composed stack, because
  cardiacCore declares `requires: [org.omnidriver.openfoam.environment]` and
  the Task 1 fix now refuses an unmet requirement.
- **Task 8:** `test_the_dag_gate_receives_the_audit`, as drafted in the plan,
  inspected `cli.py`'s source text. Batch G0-D replaced it with a behavioural
  test (`test_the_dispatch_gate_receives_the_audit` in
  `test_coverage_blocks_dispatch.py`) that drives `cli._context_from_entry`
  with a stubbed `strict_plan()` report carrying a genuinely `unavailable`
  stage, then calls `cli._refuse_environment_errors` on the resulting context
  -- with `is_launchable` never mocked, so a dropped audit anywhere in the
  path would fail the test. Reverting the production change and re-running it
  confirmed the test fails without the fix (`AttributeError`) and passes with
  it.

### Reproduction re-check, 2026-09-22 (Task 9 Step 4)

| finding | still reproduces? |
|---|---|
| C1 (Task 1) | no -- `order_providers` gives one order across 8 `PYTHONHASHSEED` values, confirmed by calling the real function under subprocess seeds (the plan's own Step-1 script exercises bare `graphlib.TopologicalSorter` directly and will always show hash variance regardless of the fix -- that variance is inherent to Python, not a residual defect; the fixed function is what was re-checked) |
| C3 (Task 2) | no -- `resolutions` no longer contains `answering[-1]`; uses `resolve_with_provenance` |
| F1 (Task 3) | no -- `execution_env` is forwarded to the plugin hook |
| F1b (Task 3) | no -- comparison uses `effective_values_agree`, not raw text equality |
| F2 (Task 4) | no -- `_inspect_source_closure` uses `find_etc_file`, not `FOAM_ETC` alone |
| S1 (Task 5) | no -- undeclared `banana` segment refused; non-vector string refused; `nan` refused |
| S3 (Task 6) | no -- qualified key resolves the override (`myFibre`) and DAG `consumes` follows it (`0/myFibre`) |
| S2 (Task 7) | no -- `test_validate_configuration.py` is 3 passed; `validate_configuration` delegates instead of `del spec; return ()` |
| C2 (Task 8) | no -- `is_launchable`'s docstring no longer says "not yet wired"; one `is_launchable` call site in `cli.py` now passes `simulation_audit`. **But the gate is wired and UNFED:** nothing in the codebase can emit an `unavailable` outcome, so `coverage_ok` cannot be false in a real run. `SimulationAuditItem(` is constructed only in `core/runtime/strict_audit.py`, and every site passes `blocked`/`warning`/`passed`/`not_applicable`/`not_requested`; the only route to `unavailable` is `_score_from_diagnostics(outcome=...)` with an outcome in `UNCOVERED_OUTCOMES`, which no caller passes. The behavioural test exercises the gate through a stubbed report, which is the only way it can be exercised today. Phase 2 Task 7's post-write readback is what starts feeding it. Recorded 2026-09-22 by review R1, which held G0 open until this said so. |

### Installation shapes and static gates, final revision (both venvs rebuilt from scratch)

| shape | result |
|---|---|
| all four (`/tmp/od311/bin/python -m pytest packages/ -q -m "not slow"`) | 2112 passed, 259 skipped, 2 deselected, 40 subtests passed -- 0 failed |
| core alone (`/tmp/od311/bin/python -m pytest packages/omnidriver/tests -q -m "not slow"`) | 911 passed, 83 skipped -- 0 failed |
| core-only venv (`/tmp/odcore/bin/python -m pytest packages/omnidriver/tests -q -m "not slow"`) | 900 passed, 94 skipped -- 0 failed |
| static: `check-import-boundaries.py` | exit 0 |
| static: `export-capability-seams.py --check` | exit 0 |

**Manual wheel shape (`python -m build` / install / `check-wheel-artifact.py`
/ pytest): PASSED**, distinct from the item below. `check-wheel-artifact.py`
exits 0 (78/78 modules import; the two documented `LookupError`s are the
expected no-adapter-installed messages). `pytest packages/omnidriver/tests -q`
against the wheel-installed venv: 739 passed, 256 skipped -- 0 failed.

**`test_every_core_module_imports_from_a_wheel` (marked `@pytest.mark.slow`,
so absent from every `-m "not slow"` shape above) behaves differently
depending on which venv runs it, confirmed on this revision:**
- Under an editable install (`/tmp/od311`, `/tmp/odcore`), it can see the repo
  checkout and attempts to build its own comparison venv inside the test,
  which dies with `subprocess.CalledProcessError: ... ensurepip --upgrade
  --default-pip ... died with <Signals.SIGABRT: 6>`. This was confirmed
  environmental (not caused by any task in this plan) by G0-A via `git stash`
  against unmodified `db93cc4`, and reconfirmed unchanged on this final
  revision.
- Under the wheel-installed venv (`/tmp/wheelenv`) itself, it self-skips:
  `"Requires a repository checkout (this module reads files from it). Not
  available when running against an installed distribution."` It is simply
  not applicable there -- it needs the checkout to build the comparison wheel
  it tests against, and a wheel-installed `omnidriver` cannot supply one.

**Correction, 2026-09-22 (this batch).** The plan's Task 9 Step 2 paragraph
telling the implementer to weigh whether the wheel shape is "unrunnable here"
and to consider recording **wheel shape blocked** was written before this
evidence existed. The manual wheel shape runs cleanly end to end; only the
self-contained slow test's internal `ensurepip` step is broken on this
machine, and that test does not gate on `-m "not slow"` in the first place.
Recorded here as **wheel shape passed; the slow test's internal-venv failure
is a known, separately-tracked environmental issue**, not as a blocked gate.

### Untested

Nothing from this plan's own list (F1b, F2) remains untested as of this date
-- see "Confirmed against a native runtime" above. No other native-runtime
claim was in scope for G0.

## Verified baseline, 2026-09-22

Every finding below was reproduced against `db93cc4` before this plan was
written. Reproduce it again yourself before fixing it — the plan's own rule is
that audit claims are claims until measured.

| finding | reproduction |
|---|---|
| C1 | `PYTHONHASHSEED=0..5` over a 3-dependency graph fed to `TopologicalSorter` yields 4 distinct orders. |
| C3 | `resolutions()` picks `answering[-1]` by `callable(getattr(provider, member))` — declaration, not the value that won `_first_non_none`. |
| F1 | `_OverrideScopeAdapter.apply` calls `hook(overrides, case_root=…, driver_context=…)`; `execution_env` is accepted and dropped. `OpenFOAMEnvironment.apply_overrides` has no such parameter. `apply_overrides` returns `()` when it is `None`. |
| F1b | `result.value == _effective_value_text(override["value"])` — string equality. |
| F2 | `_inspect_source_closure` resolves `#includeEtc` as `$FOAM_ETC/<name>` only; no user/site/version chain. |
| S1 | `validate_input_overrides` accepts `$PURKINJE_TREE.banana.seed`, accepts `'not a vector at all'` for a `vector3`, and accepts `nan`/`inf` for a `scalar`. |
| S2 | `CardiacCorePlugin.validate_configuration` is `del spec; return ()`. `tests/test_validate_configuration.py` — 1 failed, 2 passed. |
| S3 | `make_human_purkinje_slab_spec(input_overrides={"$CARDIAC_CONDUCTIVITY.fiberField": "myFibre"})` → `config["preprocessing"]["fiberField"] is None`, **no diagnostic**. |

**Corrected 2026-09-22 (review R1).** Both gate scripts import `omnidriver`, so
bare `python3` fails with `ModuleNotFoundError` on a machine where the packages
are installed only into the task virtualenvs. Run them with
`/tmp/od311/bin/python` (or `/tmp/odcore/bin/python` for the core-only shape).
The plan previously wrote `python3` throughout, which would have made both gates
look unrunnable rather than passing.

## Execution batches and review points

Four batches, **run in sequence, not in parallel**. The tasks touch disjoint
packages and would look parallelisable, but they are not: the four verification
shapes are shared absolute-path virtualenvs (`/tmp/od311`, `/tmp/odcore`)
holding editable installs of this one working tree, so a batch mid-edit poisons
another batch's suite run. cardiacCore's tests import `omnidriver.openfoam`
directly, and Task 1 changes composition order, which the plan warns may move
existing expectations. One tree, one batch at a time, one `git` index.

| batch | tasks | packages touched | review after |
|---|---|---|---|
| G0-A · core composition | 1, 2 | `core/provider_stack.py`, `core/provider_identity.py` | no |
| G0-B · OpenFOAM evidence | 3, 4 | `openfoam/*`, `core/plugin_interface.py`, `core/plugin_capabilities.py` | no |
| G0-C · cardiacCore addressing | 5, 6, 7 | `cardiaccore/*`, possibly `core/specs/validation.py` | no |
| G0-D · dispatch gate and close-out | 8, 9 | `core/runtime/*`, `cli.py` | **yes — R1** |

**R1, the G0 exit review**, is the only review in this plan, and it reviews the
gate rather than any one task. It must check, on evidence and not on the
implementer's report:

1. Every Step-1 reproduction in Tasks 1–8 now fails to reproduce.
2. No guard was weakened and no skip was added. `git log -p` for `pytest.mark.skip`,
   `xfail`, relaxed assertions, and any growth in the import-boundary waiver list.
3. Where a task's fix moved an existing test's expectation, the new expectation
   is correct for the fixed behaviour — not restored to what passed before.
4. The pre-existing WIP (`run_config.py`, `test_validate_configuration.py`,
   `docs/OMNIDRIVER_ROADMAP.md`, the Phase 2 plan) was preserved, and Task 6/7's
   unavoidable inclusion of the first two is declared in their commit bodies.
5. Both static gates and all four installation shapes pass at the final revision.
6. What is recorded as **untested against a native runtime** is accurate — F1b's
   `1e-3` → `0.001` premise and F2's search chain, if no OpenFOAM was available.

Reviewing per task would not catch items 3, 5 or 6, which are gate-level facts.

## Global Constraints

- Python floor is **3.11**. Keep lazy annotations in `plugin_interface.py`.
- `omnidriver.core` MUST NOT import from any adapter package; the waiver list in
  `scripts/check-import-boundaries.py` stays empty.
- `omnidriver.cardiaccore` MUST NOT import `omnidriver.cardiacfoam`, nor the reverse.
- No production module in core or an adapter may touch `driver_context.providers` directly.
- Do not weaken or skip a guard to make a change pass. If a guard fails, fix the cause.
- Do not quote suite totals. The durable claim is `0 failed`.
- Prefer naming a **symbol** over a `file.py:123` line number.
- Record a document correction with a date rather than overwriting it silently.
- Do not add a `LICENSE` file or a `license` field to any `pyproject.toml`.
- Rebuild the wheel after every source change before running the wheel shape.
- Do not invent a physiological range, unit, or scientific default. Every task
  here is mechanical: addressing, typing, determinism, and evidence. A task that
  finds itself choosing a number for a physical quantity has left its scope.
- **Do not stage pre-existing work.** `docs/OMNIDRIVER_ROADMAP.md`,
  `docs/superpowers/plans/2026-09-20-phase2-one-write-channel.md`,
  `packages/omnidriver-cardiaccore/src/omnidriver/cardiaccore/workflows/run_config.py`
  and `packages/omnidriver-cardiaccore/tests/test_validate_configuration.py` were
  modified before this plan started. Tasks 6 and 7 do touch the last two; they
  say so explicitly and say what to preserve. Never `git add -A`.

## How to execute a task in this plan

**Reproduce before you repair.** Each task opens with a reproduction step. If
the reproduction does not reproduce, stop and report that as the finding — do
not write the fix anyway.

**Verify every factual claim before acting on it.** The claims in these tasks
were measured on 2026-09-22 against `db93cc4`. The codebase moves.

**"Expected: PASS" has been wrong twice.** A correct fix can expose a real gap
downstream. When that happens, do not narrow the fix and do not weaken a test.
Investigate the gap, decide the remedy on evidence, and report.

**Fixture and helper names in these snippets are illustrative.** Check what
already exists in the target test file and its conftest before adding one.
Known trap: `plugin_discovery.discover_plugins()` returns `EntryPoint` objects,
not plugin classes — use `load_discovered_plugin(name)`.

**`from conftest import X` is unreliable.** Both packages' `tests` directories
are reachable when the whole repo is collected, and core's conftest wins. For a
package-specific helper use a uniquely named module inside an importable
package.

**Report being wrong as a finding.** A plan that mis-describes the codebase is
information, not a failure.

---

## File Structure

**Core — modified:**
- `core/provider_stack.py` — `order_providers` becomes hash-independent and
  refuses duplicate identities (Task 1); `resolutions` reports the provider that
  actually answered (Task 2).
- `core/provider_identity.py` — `COMPOSITION_RULE_VERSION` bumps with the
  resolution-payload change (Task 2).
- `core/plugin_capabilities.py` — `_OverrideScopeAdapter.apply` forwards
  `execution_env` (Task 3).
- `core/plugin_interface.py` — the `apply_overrides` protocol member gains
  `execution_env` (Task 3).
- `core/runtime/launch_readiness.py` — the stale "not yet wired" note is
  replaced by a dated record of what is now wired (Task 8).
- `core/runtime/run_document_exec.py`, `cli.py` — carry the simulation audit to
  the dispatch gate (Task 8).

**Core — created:**
- `tests/core/test_provider_order_is_hash_independent.py` (Task 1)
- `tests/core/test_resolution_provenance.py` (Task 2)
- `tests/core/test_override_apply_forwards_execution_env.py` (Task 3)
- `tests/core/test_coverage_blocks_dispatch.py` (Task 8)

**OpenFOAM — modified:**
- `openfoam/environment.py` — `apply_overrides` accepts and forwards
  `execution_env` (Task 3).
- `openfoam/apply_overrides.py` — typed readback comparison (Task 3).
- `openfoam/effective_dictionary.py` — `find_etc_file` search chain (Task 4).

**OpenFOAM — created:**
- `tests/test_effective_value_comparison.py` (Task 3)
- `tests/test_etc_search_chain.py` (Task 4)

**cardiacCore — modified:**
- `cardiaccore/workflows/overrides.py` — scope-preserving addressing, dynamic
  binding validation, finite/vector value checks (Task 5).
- `cardiaccore/workflows/run_config.py` — one resolution of effective inputs
  (Task 6); `_relevant_catalog_paths`'s collision workaround retired (Task 7).
- `cardiaccore/workflows/preprocessing.py` — DAG `consumes` derives from the
  resolved field names (Task 6).
- `cardiaccore/plugin.py` — `validate_configuration` delegates instead of
  returning `()` (Task 7).
- `cardiaccore/plugin.yaml` — the comment claiming the hook is a stub is
  corrected with a date (Task 7).

**cardiacCore — created:**
- `tests/test_qualified_addressing.py` (Task 5)
- `tests/test_workflow_inputs_follow_overrides.py` (Task 6)

---

## Task 1: Provider order is hash-independent, and duplicate identities are refused

**Finding:** C1. **Files:**
- Modify: `packages/omnidriver/src/omnidriver/core/provider_stack.py` — `order_providers`
- Create: `packages/omnidriver/tests/core/test_provider_order_is_hash_independent.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `order_providers(providers) -> tuple` — same signature, now total and
  hash-independent; raises `ValueError` naming every repeated `plugin_id`.
  Task 2 and every stack-digest consumer depend on this being stable.

- [ ] **Step 1: Reproduce the defect**

```bash
for seed in 0 1 2 3 4 5; do PYTHONHASHSEED=$seed python3 -c "
from graphlib import TopologicalSorter
ids=['org.top','org.x','org.y','org.z']
req={'org.top':('org.x','org.y','org.z'),'org.x':(),'org.y':(),'org.z':()}
g={i:set(req[i]) for i in sorted(ids)}
print(tuple(TopologicalSorter(g).static_order()))
"; done
```

Expected: at least two distinct orders across the six runs. `order_providers`
builds exactly this shape — `graph[plugin_id] = set(requires)` — and
`TopologicalSorter` registers nodes in predecessor-set iteration order, which is
string-hash order for nodes first seen as a predecessor.

If all six agree, your interpreter's `PYTHONHASHSEED` handling differs; widen
the seed range before concluding the finding is stale.

- [ ] **Step 2: Write the failing test**

Create `packages/omnidriver/tests/core/test_provider_order_is_hash_independent.py`:

```python
"""Composition order must not depend on string hashing.

`order_providers` fed `set(requires)` to `TopologicalSorter`, which registers a
node first seen as a predecessor in set-iteration order. With two or more
dependencies that order is `PYTHONHASHSEED`-dependent, so the same installation
composed differently between processes -- and `build_stack_identity` hashes this
order, so a reviewed plan's stack digest was not reproducible either.

An in-process test cannot see this: one process has one hash seed. The only
honest test spawns interpreters with different seeds.
"""

import subprocess
import sys
import textwrap

import pytest

from omnidriver.core import provider_stack

_PROBE = textwrap.dedent(
    """
    from omnidriver.core.provider_stack import order_providers


    class _Profile:
        def __init__(self, requires):
            self.requires = requires


    class _Provider:
        def __init__(self, plugin_id, requires=()):
            self.plugin_id = plugin_id
            self._requires = tuple(requires)

        def get_profile(self):
            return _Profile(self._requires)


    providers = [
        _Provider("org.top", ("org.x", "org.y", "org.z")),
        _Provider("org.x"),
        _Provider("org.y"),
        _Provider("org.z"),
    ]
    print(",".join(p.plugin_id for p in order_providers(providers)))
    """
)


def _order_under_seed(seed: str) -> str:
    result = subprocess.run(
        [sys.executable, "-c", _PROBE],
        capture_output=True, text=True, check=True,
        env={"PYTHONHASHSEED": seed, "PATH": "/usr/bin:/bin"},
    )
    return result.stdout.strip()


def test_order_is_identical_across_hash_seeds():
    orders = {_order_under_seed(str(seed)) for seed in range(8)}
    assert len(orders) == 1, f"composition order varies with PYTHONHASHSEED: {orders}"


def test_independent_providers_keep_sorted_by_id_order():
    """The docstring's own promise, now actually enforced."""
    order = _order_under_seed("3")
    assert order == "org.x,org.y,org.z,org.top"


class _Profile:
    def __init__(self, requires=()):
        self.requires = tuple(requires)


class _Provider:
    def __init__(self, plugin_id, requires=()):
        self.plugin_id = plugin_id
        self._requires = tuple(requires)

    def get_profile(self):
        return _Profile(self._requires)


def test_a_duplicate_plugin_id_is_refused():
    """`by_id = {p.plugin_id: p for p in providers}` silently kept the last one.

    Two distributions claiming one identity is a packaging error: which object
    answers a capability then depends on discovery order, and the stack digest
    records an identity that does not identify one implementation.
    """
    with pytest.raises(ValueError, match="org.dup"):
        provider_stack.order_providers([
            _Provider("org.dup"), _Provider("org.other"), _Provider("org.dup"),
        ])
```

- [ ] **Step 3: Run to verify it fails**

```bash
/tmp/od311/bin/python -m pytest packages/omnidriver/tests/core/test_provider_order_is_hash_independent.py -v
```

Expected: FAIL. `test_order_is_identical_across_hash_seeds` reports more than
one order; `test_a_duplicate_plugin_id_is_refused` fails because no `ValueError`
is raised.

- [ ] **Step 4: Implement**

Replace the body of `order_providers` in
`packages/omnidriver/src/omnidriver/core/provider_stack.py`:

```python
def order_providers(providers) -> tuple:
    """Order providers least-specific first, by declared `requires:`.

    Stable and hash-independent: every node is registered in sorted-id order
    before any edge is added, and each node's predecessors are added sorted, so
    `TopologicalSorter` sees one insertion order regardless of `PYTHONHASHSEED`.
    Independent providers therefore keep sorted-by-id order. That matters
    because `build_stack_identity` hashes this order into the stack digest,
    which a reviewed plan is bound to.

    Corrected 2026-09-22 (audit finding C1): the previous implementation passed
    `set(requires)` to `TopologicalSorter`, which registers a node first seen as
    a predecessor in set-iteration order. A three-dependency provider therefore
    composed in four different orders across eight hash seeds.
    """
    providers = tuple(providers)
    seen: dict[str, int] = {}
    for provider in providers:
        seen[provider.plugin_id] = seen.get(provider.plugin_id, 0) + 1
    duplicates = sorted(plugin_id for plugin_id, count in seen.items() if count > 1)
    if duplicates:
        raise ValueError(
            f"provider identities are not unique: {duplicates}; two "
            f"distributions claiming one id make the answering implementation "
            f"depend on discovery order, and the stack digest then records an "
            f"identity that does not identify one implementation"
        )
    by_id = {provider.plugin_id: provider for provider in providers}
    requirements: dict[str, tuple[str, ...]] = {}
    for plugin_id in sorted(by_id):
        requires = tuple(by_id[plugin_id].get_profile().requires)
        missing = sorted(set(requires) - set(by_id))
        if missing:
            raise ValueError(
                f"provider {plugin_id!r} requires {missing}, which "
                f"{'is' if len(missing) == 1 else 'are'} not installed"
            )
        requirements[plugin_id] = tuple(sorted(set(requires)))
    sorter = TopologicalSorter()
    # Two passes, both in sorted order: registration first, so no node is ever
    # created by an edge, then the edges themselves.
    for plugin_id in sorted(requirements):
        sorter.add(plugin_id)
    for plugin_id in sorted(requirements):
        sorter.add(plugin_id, *requirements[plugin_id])
    try:
        ordered = tuple(sorter.static_order())
    except Exception as exc:  # graphlib.CycleError
        raise ValueError(
            f"provider requirements form a cycle: {exc}"
        ) from exc
    return tuple(by_id[plugin_id] for plugin_id in ordered)
```

- [ ] **Step 5: Run the new test and the whole core suite**

```bash
/tmp/od311/bin/python -m pytest packages/omnidriver/tests/core/test_provider_order_is_hash_independent.py -v
/tmp/od311/bin/python -m pytest packages/omnidriver/tests -q
```

Expected: the new file PASSES; the core suite reports `0 failed`.

A pre-existing test that asserted a specific composition order may now assert a
different one. That is the fix working. Confirm the new order is the sorted one,
update the expectation, and say so in your report — do not restore the old
order.

- [ ] **Step 6: Run the static gates and the full suite**

```bash
/tmp/od311/bin/python scripts/check-import-boundaries.py
/tmp/od311/bin/python scripts/export-capability-seams.py --check
/tmp/od311/bin/python -m pytest packages/ -q -m "not slow"
```

Expected: both gates exit 0. The full suite reports one failure — the
pre-existing `test_validate_configuration.py` regression, which Task 7 closes.
Any other failure is yours.

- [ ] **Step 7: Commit**

```bash
git add packages/omnidriver/src/omnidriver/core/provider_stack.py packages/omnidriver/tests/core/test_provider_order_is_hash_independent.py
git commit -m "fix(core): compose providers in a hash-independent order (C1)

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 2: Resolution provenance names the provider that answered

**Finding:** C3. **Files:**
- Modify: `packages/omnidriver/src/omnidriver/core/provider_stack.py` — `resolutions`, plus a new `resolve_with_provenance`
- Modify: `packages/omnidriver/src/omnidriver/core/provider_identity.py` — `COMPOSITION_RULE_VERSION`
- Create: `packages/omnidriver/tests/core/test_resolution_provenance.py`

**Interfaces:**
- Consumes: `order_providers` from Task 1 (a stable order is what makes a
  recorded winner reproducible).
- Produces: `resolve_with_provenance(ordered, member, *args, **kwargs) -> tuple[Any, str | None]`
  — the `single` rule's value and the id of the provider that supplied it,
  `None` when every implementer returned `None`. `resolutions()` keeps its
  `dict[str, tuple[str, str]]` signature. Phase 2's reviewed plan records the
  actual responsible provider from this.

- [ ] **Step 1: Reproduce the defect**

```bash
/tmp/od311/bin/python - <<'PY'
import inspect
from omnidriver.core import provider_stack
src = inspect.getsource(provider_stack.resolutions)
assert "callable(getattr(provider, member, None))" in src
print("winner is chosen by DECLARATION:")
print("\n".join(l for l in src.splitlines() if "answering" in l or "winner" in l))
PY
```

Expected: the printed lines show `answering` filtered by `callable(getattr(...))`
and `winner = (answering[-1] if answering else ordered[-1]).plugin_id`. A
provider that defines a `single`-shaped member and returns `None` is therefore
recorded as the winner even though `_first_non_none` fell through to a less
specific provider.

- [ ] **Step 2: Write the failing test**

Create `packages/omnidriver/tests/core/test_resolution_provenance.py`:

```python
"""A resolution record must name the provider whose value was used.

`resolutions()` chose the most specific provider that *declared* a member.
Under the `single` rule the composed value comes from the most specific
provider that returned something other than `None`. A provider that declares a
hook and declines to answer was therefore recorded as the source of an answer
it did not give -- and that record is what `build_stack_identity` hashes and
what a reviewed plan cites as its responsible provider.
"""

from omnidriver.core import provider_stack


class _Profile:
    def __init__(self, requires=()):
        self.requires = tuple(requires)
        self.case_files = ()


class _Base:
    plugin_id = "org.base"

    def get_profile(self):
        return _Profile()

    def get_selected_start_time(self, *args, **kwargs):
        return "0"


class _Declines(_Base):
    plugin_id = "org.declines"

    def get_profile(self):
        return _Profile(requires=("org.base",))

    def get_selected_start_time(self, *args, **kwargs):
        return None


def test_the_provider_that_returned_none_is_not_recorded_as_the_winner():
    ordered = provider_stack.order_providers([_Base(), _Declines()])
    value, provider_id = provider_stack.resolve_with_provenance(
        ordered, "get_selected_start_time",
    )
    assert value == "0"
    assert provider_id == "org.base"


def test_no_implementer_answering_reports_no_provider():
    class _AlsoDeclines(_Declines):
        plugin_id = "org.also"

    ordered = provider_stack.order_providers([_Declines(), _AlsoDeclines()])
    value, provider_id = provider_stack.resolve_with_provenance(
        ordered, "get_selected_start_time",
    )
    assert value is None
    assert provider_id is None


def test_resolutions_records_the_answering_provider_for_a_single_member():
    ordered = provider_stack.order_providers([_Base(), _Declines()])
    recorded = provider_stack.resolutions(ordered)
    winner, _digest = recorded["selected_start_time"]
    assert winner == "org.base"


def test_a_capability_no_provider_implements_is_recorded_as_unclaimed():
    """Recording the most specific provider as the winner of a capability
    nobody implements asserts an ownership that does not exist."""
    ordered = provider_stack.order_providers([_Base()])
    recorded = provider_stack.resolutions(ordered)
    for capability, (winner, _digest) in recorded.items():
        implementers = [
            provider for provider in ordered
            if any(
                callable(getattr(provider, member, None))
                for member in provider_stack.capability_members()[capability]
            )
        ]
        if not implementers:
            assert winner == provider_stack.UNCLAIMED, capability
```

Before running this, confirm `"selected_start_time"` is the capability name that
`capability_members()` maps `get_selected_start_time` into. If the name differs,
use the real one — do not add an alias.

- [ ] **Step 3: Run to verify it fails**

```bash
/tmp/od311/bin/python -m pytest packages/omnidriver/tests/core/test_resolution_provenance.py -v
```

Expected: FAIL — `resolve_with_provenance` and `UNCLAIMED` do not exist, and
`resolutions` records `org.declines`.

- [ ] **Step 4: Implement**

In `packages/omnidriver/src/omnidriver/core/provider_stack.py`, add the sentinel
and the provenance-reporting resolver beside `_first_non_none`:

```python
#: Recorded in place of a winner when no provider in the stack implements any
#: member of a capability. Naming the most specific provider there asserted an
#: ownership that did not exist; the capability adapter runs its declared
#: fallback, which belongs to no provider. Added 2026-09-22 (audit finding C3).
UNCLAIMED = "<unclaimed>"


def resolve_with_provenance(ordered, member, *args, **kwargs):
    """Run the ``single`` rule and report which provider actually answered.

    Returns ``(value, provider_id)``; ``(None, None)`` when every implementer
    returned ``None``. This is the same traversal :func:`_first_non_none`
    performs -- most specific first -- so the reported provider is the one whose
    value a caller would have received, not the one that merely declared the
    hook.
    """
    for provider in reversed(_implementers(tuple(ordered), member)):
        answer = getattr(provider, member)(*args, **kwargs)
        if answer is not None:
            return answer, provider.plugin_id
    return None, None
```

Then replace the winner selection inside `resolutions`:

```python
    for capability in members:
        implementers = [
            provider
            for provider in ordered
            if any(
                callable(getattr(provider, member, None))
                for member in members[capability]
            )
        ]
        digested_member = _DIGESTED_CAPABILITIES.get(capability)
        if not implementers:
            resolved[capability] = (UNCLAIMED, RESOLUTION_PLACEHOLDER)
            continue
        if digested_member is None or not callable(
            getattr(composed, digested_member, None)
        ):
            # Not digested, or digested through a member this stack does not
            # implement: the declared most-specific implementer is the best
            # available claim, and the placeholder digest already says the
            # content behind it is not bound. Recorded, not asserted.
            resolved[capability] = (implementers[-1].plugin_id, RESOLUTION_PLACEHOLDER)
            continue
        if _SHAPE.get(digested_member) == "single":
            value, answering_id = resolve_with_provenance(ordered, digested_member)
            winner = answering_id or UNCLAIMED
        else:
            value = getattr(composed, digested_member)()
            winner = implementers[-1].plugin_id
        content = (
            getattr(value, "digest", None)
            if digested_member == "get_profile"
            else _content_digest(value)
        )
        resolved[capability] = (winner, content or RESOLUTION_PLACEHOLDER)
```

The payload `build_stack_identity` hashes now differs for a stack that
previously recorded a declining provider, so bump the rule version in
`packages/omnidriver/src/omnidriver/core/provider_identity.py`:

```python
#: Bumped 2026-09-22: `resolutions()` records the provider that supplied the
#: value under the `single` rule, and `<unclaimed>` where no provider
#: implements the capability at all (audit finding C3). A digest computed
#: before this date is not comparable with one computed after it.
COMPOSITION_RULE_VERSION = "2"
```

Read the current value before editing; increment it rather than assuming `"1"`.

- [ ] **Step 5: Decide and record capability exposure**

The second half of C3 is that a profile's declared `provides:` is not an export
filter — a provider can implement a classified member it never declared, and
composition will use it.

Do not change that behaviour in this task. Instead, measure it and record the
result, so the G1 contract work decides on evidence:

```bash
/tmp/od311/bin/python - <<'PY'
from omnidriver.core.plugin_discovery import discover_plugins, load_discovered_plugin
from omnidriver.core.provider_stack import capability_members
members = capability_members()
# Corrected 2026-09-22 by batch G0-A: `discover_plugins()` returns
# `dict[str, EntryPoint]`, so iterating it yields NAME STRINGS, and
# `load_discovered_plugin(name)` returns a `DriverContext`, not a plugin --
# the provider objects carrying `.plugin_id`/`.get_profile()` are at
# `.providers`. The plan previously wrote `for entry in discover_plugins():
# plugin = load_discovered_plugin(entry.name)`, which fails twice over.
providers = {}
for name in discover_plugins():
    for provider in load_discovered_plugin(name).providers:
        providers[provider.plugin_id] = provider
for plugin_id, plugin in sorted(providers.items()):
    declared = set(plugin.get_profile().provides)
    implemented = {
        capability
        for capability, names in members.items()
        if any(callable(getattr(plugin, name, None)) for name in names)
    }
    undeclared = sorted(implemented - declared)
    if undeclared:
        print(f"{plugin_id}: implements but does not declare {undeclared}")
PY
```

Append the output verbatim to the Task 2 entry in this plan's Status table as a
dated note. Whether `provides:` becomes an enforced export filter is a G1
decision in the Phase 2 plan, not a change to make here — enforcing it now would
refuse a stack that works today, before the contract that replaces it exists.

- [ ] **Step 6: Run everything**

```bash
/tmp/od311/bin/python -m pytest packages/omnidriver/tests/core/test_resolution_provenance.py -v
/tmp/od311/bin/python -m pytest packages/omnidriver/tests -q
/tmp/od311/bin/python scripts/export-capability-seams.py --check
```

Expected: the new file PASSES; core reports `0 failed`; the seam gate exits 0.
A test asserting a hard-coded `capability_digest` will now fail — the rule
version changed on purpose. Recompute the expectation and note the reason.

- [ ] **Step 7: Commit**

```bash
git add packages/omnidriver/src/omnidriver/core/provider_stack.py packages/omnidriver/src/omnidriver/core/provider_identity.py packages/omnidriver/tests/core/test_resolution_provenance.py
git commit -m "fix(core): record the provider that answered, not the one that declared (C3)

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 3: `execution_env` reaches the hook, and readback compares typed values

**Findings:** F1 and F1b — **one task by instruction.** The roadmap: "Fix typed
comparison in the same batch as environment forwarding, or the newly enabled
check will reject valid edits." Forwarding the environment is what first makes
the comparison run at all; shipping it alone turns a silent gap into a false
rejection.

**Files:**
- Modify: `packages/omnidriver/src/omnidriver/core/plugin_interface.py` — `apply_overrides`
- Modify: `packages/omnidriver/src/omnidriver/core/plugin_capabilities.py` — `_OverrideScopeAdapter.apply`
- Modify: `packages/omnidriver-openfoam/src/omnidriver/openfoam/environment.py` — `OpenFOAMEnvironment.apply_overrides`
- Modify: `packages/omnidriver-openfoam/src/omnidriver/openfoam/apply_overrides.py` — the evidence loop
- Create: `packages/omnidriver/tests/core/test_override_apply_forwards_execution_env.py`
- Create: `packages/omnidriver-openfoam/tests/test_effective_value_comparison.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `PluginCapabilities.override_scopes.apply(overrides, *, case_root,
  driver_context, execution_env=None) -> tuple[dict, ...]` — when
  `execution_env` is not `None`, every returned record carries
  `matches_requested`, and the tuple is never empty for a non-empty override
  list. `effective_values_agree(requested, resolved) -> bool` in
  `openfoam/apply_overrides.py`. Phase 2's post-write check calls both.

- [ ] **Step 1: Reproduce both defects**

```bash
/tmp/od311/bin/python - <<'PY'
import inspect
from omnidriver.core.plugin_capabilities import _OverrideScopeAdapter
from omnidriver.openfoam import environment, apply_overrides

apply_src = inspect.getsource(_OverrideScopeAdapter.apply)
hook_call = [l for l in apply_src.splitlines() if "hook(overrides" in l or "driver_context=driver_context" in l]
print("F1 -- adapter forwards to hook:", hook_call)
print("F1 -- plugin hook signature:", inspect.signature(environment.OpenFOAMEnvironment.apply_overrides))
cmp_line = [l.strip() for l in inspect.getsource(apply_overrides.apply_overrides).splitlines()
            if "_effective_value_text" in l]
print("F1b -- comparison:", cmp_line)
PY
```

Expected: the adapter's hook call names only `overrides`, `case_root` and
`driver_context`; the plugin hook signature has no `execution_env`; the
comparison is `result.value == _effective_value_text(...)`.

- [ ] **Step 2: Write the failing tests**

Create `packages/omnidriver/tests/core/test_override_apply_forwards_execution_env.py`:

```python
"""The composed override path must carry the execution environment.

`_OverrideScopeAdapter.apply` accepted `execution_env` and forwarded it only to
the legacy fallback. Every real adapter implements `apply_overrides`, so on the
path that actually runs, the environment was dropped -- and the OpenFOAM
implementation returns an empty evidence tuple when it is absent. A required
post-write readback was therefore satisfied by having no evidence at all.

Phase 2 makes that readback blocking, which is why this is a prerequisite: an
empty tuple must not be able to pass a check it never performed.
"""

from pathlib import Path

import pytest

from omnidriver.core import plugin_capabilities


class _RecordingPlugin:
    plugin_id = "org.recording"

    def __init__(self):
        self.seen = None

    def apply_overrides(self, overrides, *, case_root, driver_context, execution_env=None):
        self.seen = execution_env
        return ({"driver_path": "a", "matches_requested": True},)


def test_the_environment_reaches_the_plugin_hook():
    plugin = _RecordingPlugin()
    adapter = plugin_capabilities._OverrideScopeAdapter(plugin=plugin)
    adapter.apply(
        [{"driver_path": "a", "value": 1}],
        case_root=Path("/tmp/case"),
        driver_context=object(),
        execution_env={"FOAM_ETC": "/opt/openfoam/etc"},
    )
    assert plugin.seen == {"FOAM_ETC": "/opt/openfoam/etc"}


def test_an_environment_was_supplied_but_no_evidence_returned_is_refused():
    """"I applied it and can say nothing about the result" is not a pass."""

    class _Silent(_RecordingPlugin):
        def apply_overrides(self, overrides, *, case_root, driver_context, execution_env=None):
            return ()

    adapter = plugin_capabilities._OverrideScopeAdapter(plugin=_Silent())
    with pytest.raises(ValueError, match="no effective-value evidence"):
        adapter.apply(
            [{"driver_path": "a", "value": 1}],
            case_root=Path("/tmp/case"),
            driver_context=object(),
            execution_env={"FOAM_ETC": "/opt/openfoam/etc"},
        )


def test_no_environment_supplied_still_returns_whatever_the_hook_reports():
    """Offline application must keep working; it simply proves nothing."""
    adapter = plugin_capabilities._OverrideScopeAdapter(plugin=_RecordingPlugin())
    records = adapter.apply(
        [{"driver_path": "a", "value": 1}],
        case_root=Path("/tmp/case"),
        driver_context=object(),
    )
    assert records == ({"driver_path": "a", "matches_requested": True},)
```

Create `packages/omnidriver-openfoam/tests/test_effective_value_comparison.py`:

```python
"""A requested value and its native resolution are compared as values.

`1e-3` written into a dictionary resolves through `foamDictionary` as `0.001`.
Compared as text those differ, so the post-write check reported a mismatch for a
correct edit. Compared as numbers they agree.

This must not become a tolerance. `0.001` and `0.0010000001` are different
configurations and a check that hides that is worse than no check. Equality of
the parsed value, exactly -- nothing looser.
"""

import pytest

from omnidriver.openfoam.apply_overrides import effective_values_agree


@pytest.mark.parametrize("requested,resolved", [
    (1e-3, "0.001"),
    (0.001, "1e-3"),
    (1, "1"),
    (1, "1.0"),
    (-2.5e-4, "-0.00025"),
    ("TT06", "TT06"),
    (True, "true"),
    (False, "false"),
    ([1, 2, 3], "(1 2 3)"),
    ("(1 2 3)", "(1 2 3)"),
])
def test_equal_values_agree(requested, resolved):
    assert effective_values_agree(requested, resolved)


@pytest.mark.parametrize("requested,resolved", [
    (0.001, "0.0010000001"),
    (1e-3, "0.002"),
    ("TT06", "TT04"),
    (1, "2"),
    ([1, 2, 3], "(1 2 4)"),
    (1e-3, "uniform 0.001"),
])
def test_different_values_do_not_agree(requested, resolved):
    assert not effective_values_agree(requested, resolved)


def test_an_unparseable_resolution_does_not_agree_silently():
    """Unknown is not agreement. A resolution the comparison cannot read must
    be reported as a non-match, so the caller sees an unverified edit rather
    than a passed check."""
    assert not effective_values_agree(1e-3, None)
    assert not effective_values_agree(1e-3, "")
```

- [ ] **Step 3: Run to verify they fail**

```bash
/tmp/od311/bin/python -m pytest packages/omnidriver/tests/core/test_override_apply_forwards_execution_env.py packages/omnidriver-openfoam/tests/test_effective_value_comparison.py -v
```

Expected: FAIL — the environment is `None` at the hook, no `ValueError` is
raised for empty evidence, and `effective_values_agree` does not exist.

- [ ] **Step 4: Implement the forwarding**

In `packages/omnidriver/src/omnidriver/core/plugin_interface.py`, extend the
protocol member:

```python
    def apply_overrides(
        self, overrides: Any, *, case_root: "Path", driver_context: Any,
        execution_env: Any | None = None,
    ) -> tuple[dict[str, Any], ...]:
        """Validate and apply a ``--apply`` override document to a case.

        One call, not two: core has only ever validated and applied together,
        and separating them would let a caller apply without validating. Raise
        a ``ValueError`` subclass to reject. ``driver_context`` is the
        caller's context -- an adapter must thread it through, not build a
        substitute from itself.

        ``execution_env`` is the selected runtime's environment. When it is
        supplied the adapter MUST read each written value back under it and
        return one evidence record per override; returning ``()`` with an
        environment in hand is refused by the capability adapter, because "I
        wrote it and can say nothing about the result" is not a passed check.
        When it is absent the write still happens and the adapter reports
        whatever it can, which may be nothing. Absent -> applying overrides is
        unsupported for this adapter.

        Added 2026-09-22 (audit finding F1): the parameter existed on the
        capability adapter and was never forwarded here."""
        ...
```

In `packages/omnidriver/src/omnidriver/core/plugin_capabilities.py`, replace the
body of `_OverrideScopeAdapter.apply`:

```python
    def apply(
        self, overrides: Any, *, case_root: Any, driver_context: Any,
        execution_env: Any | None = None,
    ) -> tuple[dict[str, Any], ...]:
        """Apply adapter-owned overrides, or leave them unsupported.

        The context and the execution environment are both passed through to
        the hook -- not just held here -- so an adapter can resolve its own
        transaction and provenance requirements under the caller's context, and
        read each written value back under the caller's runtime, rather than
        substituting either from itself. Core does not delegate to a
        solver-specific mutator when the hook is absent.

        Corrected 2026-09-22 (audit finding F1): ``execution_env`` was accepted
        and forwarded only to ``legacy_apply_overrides``. Every real adapter
        implements the hook, so on the path that runs it was silently dropped,
        and the OpenFOAM implementation answers an absent environment with an
        empty evidence tuple. A required readback was satisfied by evidence
        that was never gathered.
        """
        hook = getattr(self.plugin, "apply_overrides", None)
        if callable(hook):
            records = tuple(
                hook(
                    overrides,
                    case_root=case_root,
                    driver_context=driver_context,
                    execution_env=execution_env,
                )
            )
        else:
            from .compatibility import legacy_apply_overrides

            records = legacy_apply_overrides(
                overrides, case_root=case_root, driver_context=driver_context,
                execution_env=execution_env,
            )
        if execution_env is not None and overrides and not records:
            raise ValueError(
                f"provider {self.plugin.plugin_id!r} applied "
                f"{len(tuple(overrides))} override(s) under an explicit "
                f"execution environment but returned no effective-value "
                f"evidence; an empty record set must not satisfy a required "
                f"readback"
            )
        return records
```

In `packages/omnidriver-openfoam/src/omnidriver/openfoam/environment.py`:

```python
    def apply_overrides(
        self, overrides, *, case_root, driver_context, execution_env=None,
    ):
        from .apply_overrides import apply_overrides

        return apply_overrides(
            overrides, case_root=case_root, driver_context=driver_context,
            execution_env=execution_env,
        )
```

- [ ] **Step 5: Implement the typed comparison**

In `packages/omnidriver-openfoam/src/omnidriver/openfoam/apply_overrides.py`,
add the comparison beside `_effective_value_text`:

```python
def _as_comparable(text: str):
    """Parse one native scalar/word/vector spelling into a comparable value.

    **Corrected 2026-09-22:** this sketch originally rendered the REQUESTED
    side through ``_effective_value_text``/``_format_value`` before reparsing
    it. ``_format_value([1, 2, 3])`` returns the Python literal
    ``"[1, 2, 3]"``, not OpenFOAM's ``"(1 2 3)"``, so this task's own
    ``([1, 2, 3], "(1 2 3)")`` test case could not have passed. Dispatch on the
    requested value's own Python type instead of round-tripping it through
    dictionary-writing text.

    Returns a float for a number, a bool for an OpenFOAM boolean word, a tuple
    of floats for a parenthesised vector, and the stripped text otherwise.
    """
    stripped = text.strip().rstrip(";").strip()
    if not stripped:
        return None
    if stripped in {"true", "yes", "on"}:
        return True
    if stripped in {"false", "no", "off"}:
        return False
    if stripped.startswith("(") and stripped.endswith(")"):
        parts = stripped[1:-1].split()
        try:
            return tuple(float(part) for part in parts)
        except ValueError:
            return stripped
    try:
        return float(stripped)
    except ValueError:
        return stripped


def effective_values_agree(requested: Any, resolved: str | None) -> bool:
    """Whether a native resolution is the value that was requested.

    Compared as parsed values, not as text: a requested ``1e-3`` resolves
    through ``foamDictionary`` as ``0.001``, and rejecting that is rejecting a
    correct edit. Added 2026-09-22 (audit finding F1b).

    Deliberately NOT a tolerance. ``0.001`` and ``0.0010000001`` are different
    configurations, and a comparison that calls them equal hides exactly the
    drift this check exists to find. The raw spellings are preserved in the
    evidence record either way, so a reader can always see what was written and
    what came back.

    An unparseable or absent resolution is not agreement. "I could not read it"
    is reported as a non-match so the caller sees an unverified edit, never a
    passed check.
    """
    if resolved is None:
        return False
    left = _as_comparable(_effective_value_text(requested))
    right = _as_comparable(resolved)
    if left is None or right is None:
        return False
    if isinstance(left, bool) != isinstance(right, bool):
        return False
    return left == right
```

Then replace the `matches_requested` expression in the evidence loop:

```python
        evidence.append({
            "driver_path": driver_path,
            "requested_value": override["value"],
            # Raw spellings are preserved on both sides: `requested_value`
            # above and `value` from `asdict(result)` below. `matches_requested`
            # is a typed comparison of the two, not a rewrite of either.
            "matches_requested": (
                result.status == "resolved"
                and effective_values_agree(override["value"], result.value)
            ),
            **asdict(result),
        })
```

- [ ] **Step 6: Run the new tests, then every suite**

```bash
/tmp/od311/bin/python -m pytest packages/omnidriver/tests/core/test_override_apply_forwards_execution_env.py packages/omnidriver-openfoam/tests/test_effective_value_comparison.py -v
/tmp/od311/bin/python -m pytest packages/ -q -m "not slow"
/tmp/od311/bin/python scripts/export-capability-seams.py --check
```

Expected: the new files PASS. The full suite reports only the pre-existing
`test_validate_configuration.py` failure. The seam gate exits 0 — if it does
not, the `apply_overrides` docstring changed a seam and the table needs
regenerating with `scripts/export-capability-seams.py`.

Any adapter outside this repository implementing `apply_overrides` with the old
signature will now receive an unexpected keyword argument. Search for other
implementers before committing:

```bash
grep -rn "def apply_overrides" packages/ | grep -v "/build/"
```

**Corrected 2026-09-22:** this said "exactly the three sites this task touches".
There are **seven** non-build matches — the three production sites plus four
test fixtures in `test_case_file_contract.py`, `test_override_apply_threads_a_context.py`
(twice) and `test_step_candidate.py`. The adapter forwards `execution_env`
unconditionally, so a fixture lacking the parameter raises `TypeError`. Update
every implementer, fixtures included, and report the count before and after.

- [ ] **Step 7: Probe a native runtime if one is available**

```bash
command -v foamDictionary >/dev/null && /tmp/od311/bin/python - <<'PY' || echo "no native OpenFOAM on PATH -- record this as untested"
import os, tempfile
from pathlib import Path
from omnidriver.openfoam.effective_dictionary import resolve_effective_foam_entry
case = Path(tempfile.mkdtemp())
(case / "system").mkdir()
d = case / "system" / "controlDict"
d.write_text("FoamFile{version 2.0;format ascii;class dictionary;object controlDict;}\ndeltaT 1e-3;\n")
result = resolve_effective_foam_entry(d, "deltaT", bashrc=None, env=dict(os.environ))
print("status:", result.status, "value:", repr(result.value))
PY
```

If a native runtime answers, record the exact spelling it returns for `1e-3` in
your report. That is the evidence F1b rests on. If none is available, say so —
"untested against a native runtime" is a real result and this task does not
claim otherwise.

- [ ] **Step 8: Commit**

```bash
git add packages/omnidriver/src/omnidriver/core/plugin_interface.py packages/omnidriver/src/omnidriver/core/plugin_capabilities.py packages/omnidriver/tests/core/test_override_apply_forwards_execution_env.py packages/omnidriver-openfoam/src/omnidriver/openfoam/environment.py packages/omnidriver-openfoam/src/omnidriver/openfoam/apply_overrides.py packages/omnidriver-openfoam/tests/test_effective_value_comparison.py
git commit -m "fix: thread execution_env to the override hook and compare readback typed (F1, F1b)

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 4: `#includeEtc` follows the native search chain

**Finding:** F2. **Files:**
- Modify: `packages/omnidriver-openfoam/src/omnidriver/openfoam/effective_dictionary.py` — `_inspect_source_closure`, plus a new `find_etc_file`
- Create: `packages/omnidriver-openfoam/tests/test_etc_search_chain.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `find_etc_file(name, environment) -> tuple[Path | None, tuple[Path, ...]]`
  — the selected file and every candidate location searched, in order. Phase 2's
  precondition set records the candidates so a later file appearing earlier in
  the chain invalidates a plan.

- [ ] **Step 1: Reproduce the defect**

```bash
/tmp/od311/bin/python - <<'PY'
import inspect
from omnidriver.openfoam import effective_dictionary as ed
src = inspect.getsource(ed._inspect_source_closure)
etc = [l.strip() for l in src.splitlines() if "FOAM_ETC" in l or "etc_root" in l]
print("\n".join(etc))
PY
```

Expected: the only location consulted is `Path(etc_root) / expanded`, where
`etc_root = environment.get("FOAM_ETC")`. Native `Foam::findEtcFile` searches a
chain — user, then site, then the distribution's own `etc` — so a site file that
shadows the vendor file is the one the solver reads while the inspector records
the vendor path. Every dependency digest and precondition built on that closure
then names a file the run did not use.

- [ ] **Step 2: Write the failing test**

Create `packages/omnidriver-openfoam/tests/test_etc_search_chain.py`:

```python
"""An etc dependency must be the file the native runtime would select.

`#includeEtc "caseDicts/x"` was resolved as `$FOAM_ETC/caseDicts/x` and nothing
else. Native `findEtcFile` searches user, then site, then distribution
locations, so a site override is read by the solver while the inspector records
the vendor file. Dependency closure then names a file the run did not use --
and a precondition digest over that file proves nothing about the run.

These fixtures are directory layouts, not an OpenFOAM installation. They assert
which candidate is selected and which candidates were searched, not what
foamDictionary would print.
"""

from pathlib import Path

from omnidriver.openfoam.effective_dictionary import find_etc_file


def _layout(tmp_path: Path) -> dict[str, Path]:
    user = tmp_path / "home" / ".OpenFOAM" / "2412"
    site = tmp_path / "site" / "2412" / "etc"
    dist = tmp_path / "opt" / "openfoam2412" / "etc"
    for directory in (user, site, dist):
        (directory / "caseDicts").mkdir(parents=True)
    return {"user": user, "site": site, "dist": dist}


def _environment(tmp_path: Path, dirs: dict[str, Path]) -> dict[str, str]:
    return {
        "HOME": str(tmp_path / "home"),
        "WM_PROJECT_VERSION": "2412",
        "WM_PROJECT_SITE": str(tmp_path / "site"),
        "WM_PROJECT_DIR": str(tmp_path / "opt" / "openfoam2412"),
        "FOAM_ETC": str(dirs["dist"]),
    }


def test_the_distribution_file_is_selected_when_it_is_the_only_one(tmp_path):
    dirs = _layout(tmp_path)
    (dirs["dist"] / "caseDicts" / "x").write_text("vendor\n")
    selected, candidates = find_etc_file("caseDicts/x", _environment(tmp_path, dirs))
    assert selected == dirs["dist"] / "caseDicts" / "x"
    assert selected in candidates


def test_a_site_file_shadows_the_distribution_file(tmp_path):
    dirs = _layout(tmp_path)
    (dirs["dist"] / "caseDicts" / "x").write_text("vendor\n")
    (dirs["site"] / "caseDicts" / "x").write_text("site\n")
    selected, candidates = find_etc_file("caseDicts/x", _environment(tmp_path, dirs))
    assert selected == dirs["site"] / "caseDicts" / "x"
    assert selected.read_text() == "site\n"


def test_a_user_file_shadows_both(tmp_path):
    dirs = _layout(tmp_path)
    for key in ("dist", "site", "user"):
        (dirs[key] / "caseDicts" / "x").write_text(f"{key}\n")
    selected, _ = find_etc_file("caseDicts/x", _environment(tmp_path, dirs))
    assert selected == dirs["user"] / "caseDicts" / "x"


def test_every_candidate_is_reported_in_search_order(tmp_path):
    """A file appearing at a higher-priority location later changes which file
    the run reads. Phase 2 records the absent candidates as preconditions, so
    they must be reported even when nothing is there."""
    dirs = _layout(tmp_path)
    (dirs["dist"] / "caseDicts" / "x").write_text("vendor\n")
    _, candidates = find_etc_file("caseDicts/x", _environment(tmp_path, dirs))
    assert candidates == (
        dirs["user"] / "caseDicts" / "x",
        dirs["site"] / "caseDicts" / "x",
        dirs["dist"] / "caseDicts" / "x",
    )


def test_a_missing_dependency_selects_nothing_but_still_reports_candidates(tmp_path):
    dirs = _layout(tmp_path)
    selected, candidates = find_etc_file("caseDicts/absent", _environment(tmp_path, dirs))
    assert selected is None
    assert len(candidates) == 3


def test_the_closure_records_the_shadowing_file(tmp_path):
    """The public consequence: `inspected_files` must name the selected file."""
    from omnidriver.openfoam.effective_dictionary import resolve_effective_foam_entry

    dirs = _layout(tmp_path)
    (dirs["dist"] / "caseDicts" / "x").write_text("deltaT 1e-3;\n")
    (dirs["site"] / "caseDicts" / "x").write_text("deltaT 2e-3;\n")
    case = tmp_path / "case" / "system"
    case.mkdir(parents=True)
    dictionary = case / "controlDict"
    dictionary.write_text('#includeEtc "caseDicts/x"\n')

    result = resolve_effective_foam_entry(
        dictionary, "deltaT", bashrc=None, env=_environment(tmp_path, dirs),
    )
    assert str(dirs["site"] / "caseDicts" / "x") in result.inspected_files
    assert str(dirs["dist"] / "caseDicts" / "x") not in result.inspected_files
```

`test_the_closure_records_the_shadowing_file` does not need `foamDictionary`:
the closure walk runs before the native process, and `inspected_files` is
populated on the unresolved path too. If the result's status is
`runtime_unavailable`, `inspected_files` must still be correct — assert that, and
say so in your report.

- [ ] **Step 3: Run to verify it fails**

```bash
/tmp/od311/bin/python -m pytest packages/omnidriver-openfoam/tests/test_etc_search_chain.py -v
```

Expected: FAIL — `find_etc_file` does not exist.

- [ ] **Step 4: Implement**

In `packages/omnidriver-openfoam/src/omnidriver/openfoam/effective_dictionary.py`,
add above `_inspect_source_closure`:

```python
def find_etc_file(
    name: str, environment: Mapping[str, str],
) -> tuple[Path | None, tuple[Path, ...]]:
    """Locate an ``#includeEtc`` dependency the way the native runtime does.

    Returns ``(selected, candidates)``: the first existing file in search order,
    and every location searched whether or not it exists. The absent candidates
    matter as much as the selected one -- a file appearing at a higher-priority
    location changes which file the next run reads, so a plan's preconditions
    must record that those locations were empty.

    Search order mirrors ``Foam::findEtcFile``: versioned user, unversioned
    user, versioned site, unversioned site, distribution. Added 2026-09-22
    (audit finding F2): resolution previously consulted ``$FOAM_ETC`` alone, so
    a site file that shadowed the vendor file was read natively while the vendor
    file was recorded as the dependency.

    The version segment is ``$FOAM_API``, falling back to
    ``$WM_PROJECT_VERSION`` when it is unset. ESI builds set both and they
    DIFFER -- ``FOAM_API=2412`` against ``WM_PROJECT_VERSION=v2412`` -- while
    OpenFOAM.org Foundation builds set only the latter.
    """
    version = environment.get("FOAM_API") or environment.get("WM_PROJECT_VERSION", "")
    candidates: list[Path] = []

    home = environment.get("HOME")
    if home:
        if version:
            candidates.append(Path(home) / ".OpenFOAM" / version / name)
        candidates.append(Path(home) / ".OpenFOAM" / name)

    project_dir = environment.get("WM_PROJECT_DIR")
    site = environment.get("WM_PROJECT_SITE")
    if not site and project_dir:
        site = str(Path(project_dir) / "site")
    if site:
        if version:
            candidates.append(Path(site) / version / "etc" / name)
        candidates.append(Path(site) / "etc" / name)

    if project_dir:
        candidates.append(Path(project_dir) / "etc" / name)
    etc_root = environment.get("FOAM_ETC")
    if etc_root:
        distribution = Path(etc_root) / name
        if distribution not in candidates:
            candidates.append(distribution)

    resolved = tuple(dict.fromkeys(candidates))
    for candidate in resolved:
        if candidate.is_file():
            return candidate, resolved
    return None, resolved
```

Then replace the `#includeEtc` branch inside `_inspect_source_closure`:

```python
        for match in _ETC_INCLUDE.finditer(lexical_text):
            environment_keys.add("FOAM_ETC")
            environment_keys.update(
                ("HOME", "WM_PROJECT_VERSION", "WM_PROJECT_SITE",
                 "WM_PROJECT_INST_DIR", "WM_PROJECT_DIR")
            )
            include_name = match.group("path")
            expanded, keys, error = _expand_include(include_name, environment)
            environment_keys.update(keys)
            if error is not None:
                return tuple(inspected), tuple(absent_optional), tuple(sorted(environment_keys)), error
            assert expanded is not None
            selected, candidates = find_etc_file(expanded, environment)
            if selected is None:
                searched = ", ".join(str(candidate) for candidate in candidates) or "<no location configured>"
                return tuple(inspected), tuple(absent_optional), tuple(sorted(environment_keys)), (
                    f"#includeEtc dependency is missing: {expanded}; searched {searched}"
                )
            # Higher-priority locations that are empty today are recorded as
            # absent: a file appearing at one of them changes which file the
            # next run reads, which is a precondition, not a detail.
            for candidate in candidates:
                if candidate == selected:
                    break
                absent_optional.append(candidate)
            pending.append(selected.resolve())
```

The unconditional `FOAM_ETC`-is-set guard above this loop no longer decides
whether resolution is possible — a stack with `WM_PROJECT_DIR` and no
`FOAM_ETC` is resolvable. Remove that early return and let `find_etc_file`'s
empty-candidate message carry the reason. Read the surrounding code and confirm
that is what it does before deleting anything.

**Corrected 2026-09-22, after the native probe ran.** The first version of
this task searched three locations and derived the version segment from
``$WM_PROJECT_VERSION``. Against the ESI v2412 install on this machine that was
wrong in four ways, and `foamEtcFile -list` is the authority:

```
FOAM_API=2412   WM_PROJECT_VERSION=v2412   WM_PROJECT_SITE=<unset>

$HOME/.OpenFOAM/2412              <- API number, not v2412
$HOME/.OpenFOAM                   <- unversioned user fallback, was missing
$WM_PROJECT_DIR/site/2412/etc     <- site defaults from WM_PROJECT_DIR, not WM_PROJECT_INST_DIR
$WM_PROJECT_DIR/site/etc          <- unversioned site fallback, was missing
$WM_PROJECT_DIR/etc
```

The consequence was worse than the defect F2 describes. With a shadowing file
at ``$HOME/.OpenFOAM/v2412/controlDict``, native selected the distribution file
and the first implementation selected the user file -- so a plan's precondition
digest would have been taken over a file with no bearing on the run. F2's
original form recorded the wrong file; that form would have *read* the wrong
file.

**Corrected again 2026-09-22, after review R1.** The five-location chain above
was still incomplete. Two ESI mechanisms were unmodelled, and review R1 measured
both against the real binary:

* `$FOAM_CONFIG_ETC` is a candidate, inserted immediately **before** the
  distribution entry — not at the top. It only changes the answer when nothing
  higher in the chain matches, which is why a first reproduction attempt with a
  user shadow present showed a false match.
* `$FOAM_CONFIG_MODE` selects which of the three groups are searched at all
  (default `ugo`; `u` user, `g` group/site, `o` other). Only membership matters,
  not the letters' order — `foamEtcFile` tests `case "$optMode" in (*[u]*) ...`
  in a fixed u, g, o sequence. Under `FOAM_CONFIG_MODE=o` the implementation was
  reading a user file that native deliberately skips: selecting a file with no
  bearing on the run, the same class of error as the `v2412` bug.

Both now join `environment_keys`, which is recorded unconditionally (nine keys)
rather than narrowed to what a given install happens to set. Over-declaration is
the conservative direction — a spurious invalidation, never a missed one — and
the docstring states that as a deliberate choice.

**The Foundation (openfoam.org) branch is source-verified, not runtime-verified.**
No such install exists on this machine. Foundation's published `bin/foamEtcFile`
derives its site root from `${WM_PROJECT_SITE:-$prefixDir/site}` where
`prefixDir` is the **parent** of the versioned install — genuinely different
from ESI's `$projectDir/site`, so the ESI correction had broken Foundation.
`FOAM_API` is absent from Foundation's source entirely and is used as the
discriminator. Where neither site hint is set, no site candidate is added rather
than one being guessed. Record this as **modelled and source-verified, not
confirmed against a runtime** — it is a fixture asserting a reading of published
source, which is better than a belief and weaker than a measurement.

The lesson generalises past this task: the fixture tests all passed. Only
comparison against the real ``foamEtcFile`` binary caught it. Where a task's
subject is "what does the native runtime do", a fixture proves the code does
what its author believed, not what the runtime does.

- [ ] **Step 5: Run the new test and the OpenFOAM suite**

```bash
/tmp/od311/bin/python -m pytest packages/omnidriver-openfoam/tests/test_etc_search_chain.py -v
/tmp/od311/bin/python -m pytest packages/omnidriver-openfoam/tests -q
```

Expected: the new file PASSES; the OpenFOAM suite reports `0 failed`.

A test asserting the old `"#includeEtc requires unset environment variable
'FOAM_ETC'"` message will now fail. The message changed because the condition
changed. Update it and explain why in your report.

- [ ] **Step 6: Probe a native runtime if one is available**

```bash
/tmp/od311/bin/python - <<'PY'
import os
from omnidriver.openfoam.effective_dictionary import find_etc_file
env = dict(os.environ)
if not env.get("WM_PROJECT_DIR"):
    print("no OpenFOAM environment loaded -- record this as untested")
else:
    selected, candidates = find_etc_file("controlDict", env)
    print("selected:", selected)
    for candidate in candidates:
        print("  candidate:", candidate, "exists" if candidate.is_file() else "absent")
PY
```

Record the output. If the selected file is not the one `foamEtcFile
controlDict` reports, the chain is wrong for this installation — that is a
finding, not a reason to adjust the test.

**Do not conclude "no native runtime" from `command -v foamDictionary` or an
unset `WM_PROJECT_DIR`.** Both are empty on this machine and an OpenFOAM v2412
install is nonetheless present at `/Volumes/OpenFOAM-v2412`. Use
`discover_openfoam_bashrc()` from `omnidriver.openfoam.openfoam_environment`
(note: **not** `openfoam.environment`), which is what the production code uses.
Skipping this probe on a wrong availability check is how the defect corrected
above reached a commit.

- [ ] **Step 7: Commit**

```bash
git add packages/omnidriver-openfoam/src/omnidriver/openfoam/effective_dictionary.py packages/omnidriver-openfoam/tests/test_etc_search_chain.py
git commit -m "fix(openfoam): resolve #includeEtc through the native search chain (F2)

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 5: cardiacCore addressing keeps document scope, and values are checked

**Finding:** S1. **Files:**
- Modify: `packages/omnidriver-cardiaccore/src/omnidriver/cardiaccore/workflows/overrides.py` — `_template_for`, `_check_value`, plus a new `qualified_slot_key`
- Create: `packages/omnidriver-cardiaccore/tests/test_qualified_addressing.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `qualified_slot_key(driver_path) -> str` — a slot key that keeps the
  `$SCOPE` token, so two documents declaring the same leaf name do not collide.
  Tasks 6 and 7 use it. `validate_input_overrides` now refuses an undeclared
  dynamic segment, a non-vector string for a `vector3`, and a non-finite
  `scalar`/`integer`.

**Do not invent a physiological range.** This task adds *syntactic and
finiteness* checks only: is the binding one the catalog declares, is a vector
three numbers, is a scalar a real finite number. Whether `df = 0.4` is
physiologically sensible is a domain question with a domain owner, and it is not
in this plan.

- [ ] **Step 1: Reproduce all three holes**

```bash
cd /tmp && /tmp/od311/bin/python - <<'PY'
from omnidriver.cardiaccore.workflows.overrides import (
    validate_input_overrides, declared_path_template,
)
print("undeclared vent segment matches a template:",
      declared_path_template("$PURKINJE_TREE.banana.seed"))
print("accepted:", validate_input_overrides({"$PURKINJE_TREE.banana.seed": [1, 2, 3]}))
print("non-vector string accepted:",
      validate_input_overrides({"$PURKINJE_TREE.hisBundleSeed": "not a vector at all"}))
print("nan accepted:", validate_input_overrides({"$CARDIAC_CONDUCTIVITY.df": float("nan")}))
print("inf accepted:", validate_input_overrides({"$CARDIAC_CONDUCTIVITY.ds": float("inf")}))
PY
```

Expected: every line prints an accepted value. `banana` matches the
`<ventKey>` placeholder because `_template_for` substitutes the placeholder into
*any* segment position without checking the segment against `VENT_KEYS`.

```bash
cd /tmp && /tmp/od311/bin/python - <<'PY'
from omnidriver.core.specs.validation import slot_key
print(slot_key("$CARDIAC_CONDUCTIVITY.fiberField"),
      slot_key("$CARDIAC_SCAR.fiberField"))
PY
```

Expected: both print `fiberField`. Two documents, one slot.

- [ ] **Step 2: Write the failing test**

Create `packages/omnidriver-cardiaccore/tests/test_qualified_addressing.py`:

```python
"""A parameter address identifies one parameter.

Three defects, one cause -- an address that drops information:

* `slot_key` strips the `$SCOPE.` prefix, so `$CARDIAC_SCAR.fiberField` and
  `$CARDIAC_CONDUCTIVITY.fiberField` land in one slot. Which value survives
  depends on catalog iteration order.
* `_template_for` matches `<ventKey>` against any segment, so an undeclared
  binding such as `banana` is accepted as a ventricle.
* `_check_value` accepts any non-empty string for a `vector3` and any `Real`
  for a `scalar`, including `nan` and `inf`.

These are syntactic and finiteness checks. No physiological range is asserted
here; that has a domain owner and is not this module's to decide.
"""

import math

import pytest

from omnidriver.cardiaccore.workflows.overrides import (
    VENT_KEYS,
    declared_path_template,
    qualified_slot_key,
    validate_input_overrides,
)


def test_two_documents_declaring_one_leaf_name_do_not_collide():
    assert qualified_slot_key("$CARDIAC_CONDUCTIVITY.fiberField") != qualified_slot_key(
        "$CARDIAC_SCAR.fiberField"
    )


def test_a_qualified_key_keeps_its_scope_token():
    assert qualified_slot_key("$CARDIAC_CONDUCTIVITY.fiberField") == (
        "$CARDIAC_CONDUCTIVITY.fiberField"
    )


def test_a_nested_leaf_keeps_its_full_path():
    """The reason the unqualified key kept multi-segment paths intact in the
    first place -- a nested leaf must not overwrite a top-level key."""
    assert qualified_slot_key("$CARDIAC_SCAR.channels.channelMultiplier") == (
        "$CARDIAC_SCAR.channels.channelMultiplier"
    )


def test_an_undeclared_dynamic_segment_is_refused():
    assert declared_path_template("$PURKINJE_TREE.banana.seed") is None
    with pytest.raises(ValueError, match="banana"):
        validate_input_overrides({"$PURKINJE_TREE.banana.seed": [1, 2, 3]})


@pytest.mark.parametrize("vent", sorted(VENT_KEYS))
def test_every_declared_ventricle_binding_is_still_accepted(vent):
    path = f"$PURKINJE_TREE.{vent}.seed"
    assert declared_path_template(path) == "$PURKINJE_TREE.<ventKey>.seed"
    assert validate_input_overrides({path: [1.0, 2.0, 3.0]}) == {path: [1.0, 2.0, 3.0]}


def test_a_non_vector_string_is_refused_for_a_vector_entry():
    with pytest.raises(TypeError, match="three numbers"):
        validate_input_overrides({"$PURKINJE_TREE.hisBundleSeed": "not a vector at all"})


def test_a_well_formed_vector_string_is_still_accepted():
    value = "(0.1 0.2 0.3)"
    assert validate_input_overrides({"$PURKINJE_TREE.hisBundleSeed": value}) == {
        "$PURKINJE_TREE.hisBundleSeed": value
    }


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_a_non_finite_scalar_is_refused(value):
    with pytest.raises(ValueError, match="finite"):
        validate_input_overrides({"$CARDIAC_CONDUCTIVITY.df": value})


@pytest.mark.parametrize("bad", [
    [float("nan"), 0.0, 0.0],
    [0.0, float("inf"), 0.0],
    "(1 nan 3)",
])
def test_a_non_finite_vector_component_is_refused(bad):
    with pytest.raises(ValueError, match="finite"):
        validate_input_overrides({"$PURKINJE_TREE.hisBundleSeed": bad})


def test_an_ordinary_finite_scalar_is_still_accepted():
    assert validate_input_overrides({"$CARDIAC_CONDUCTIVITY.df": 0.1}) == {
        "$CARDIAC_CONDUCTIVITY.df": 0.1
    }
```

- [ ] **Step 3: Run to verify it fails**

```bash
/tmp/od311/bin/python -m pytest packages/omnidriver-cardiaccore/tests/test_qualified_addressing.py -v
```

Expected: FAIL — `qualified_slot_key` does not exist, `banana` is accepted, the
non-vector string is accepted, and the non-finite values are accepted.

- [ ] **Step 4: Implement**

In `packages/omnidriver-cardiaccore/src/omnidriver/cardiaccore/workflows/overrides.py`:

```python
def qualified_slot_key(driver_path: str) -> str:
    """The slot key for a declared path, keeping its document scope.

    ``core.specs.validation.slot_key`` strips the ``$SCOPE.`` prefix, which
    makes ``$CARDIAC_SCAR.fiberField`` and ``$CARDIAC_CONDUCTIVITY.fiberField``
    one slot. Which one survives a flatten then depends on catalog iteration
    order, and the surviving value can be ``None`` from a dictionary the case
    does not even have.

    This keeps the whole path, so a slot identifies one parameter in one
    document. Added 2026-09-22 (audit findings S1, S3).

    ``slot_key`` itself is core's and is unchanged: core cannot know that two
    adapter documents share a leaf name, and the unqualified form is still what
    a caller wants when it has already fixed the document.
    """
    return driver_path
```

Replace `_template_for` so a dynamic segment must be a declared binding:

```python
def _template_for(driver_path: str) -> str | None:
    """The declared path this concrete path instantiates, if any.

    A declared ``<ventKey>`` entry covers every key in ``VENT_KEYS``, so the
    concrete path is matched back to its template to find the declaration that
    describes it.

    Corrected 2026-09-22 (audit finding S1): the segment was previously
    substituted without being checked, so ``$PURKINJE_TREE.banana.seed`` matched
    ``$PURKINJE_TREE.<ventKey>.seed`` and was written into a ``banana`` block no
    native utility reads. A dynamic segment is now valid only when it is one of
    the bindings the placeholder declares.
    """
    if driver_path in _ENTRIES:
        return driver_path
    parts = driver_path.split(".")
    for index in range(1, len(parts)):
        if parts[index] not in VENT_KEYS:
            continue
        candidate = ".".join(
            [*parts[:index], VENT_KEY_PLACEHOLDER, *parts[index + 1:]]
        )
        if candidate in _ENTRIES:
            return candidate
    return None
```

Add a finiteness helper and tighten `_check_value`:

```python
_VECTOR_TEXT = re.compile(r"^\(\s*(\S+)\s+(\S+)\s+(\S+)\s*\)$")


def _require_finite(driver_path: str, value: Any) -> None:
    if isinstance(value, Real) and not math.isfinite(float(value)):
        raise ValueError(
            f"input override {driver_path!r} must be a finite number, not {value!r}; "
            f"a dictionary accepts the text and the solver fails at read time"
        )
```

and, inside `_check_value`, after the `scalar` and `integer` type checks:

```python
    if kind == "integer":
        if isinstance(value, bool) or not isinstance(value, Integral):
            raise TypeError(f"input override {driver_path!r} must be a JSON integer")
        _require_finite(driver_path, value)
    elif kind == "scalar":
        if isinstance(value, bool) or not isinstance(value, Real):
            raise TypeError(f"input override {driver_path!r} must be a JSON number")
        _require_finite(driver_path, value)
```

and replace the `vector3` branch:

```python
    elif kind == "vector3":
        # A dictionary spells a vector "(x y z)"; a caller may hand over
        # either that text or three numbers. Both reach the dictionary
        # unchanged, as they do in omnidriver-cardiacfoam.
        #
        # Corrected 2026-09-22 (audit finding S1): any non-empty string was
        # accepted, so "not a vector at all" was written into a vector entry
        # and failed natively at read time with no reference back to the
        # override that caused it.
        if isinstance(value, str):
            match = _VECTOR_TEXT.match(value.strip())
            if match is None:
                raise TypeError(
                    f"input override {driver_path!r} must be three numbers or a "
                    f"'(x y z)' string, not {value!r}"
                )
            for component in match.groups():
                try:
                    number = float(component)
                except ValueError:
                    raise TypeError(
                        f"input override {driver_path!r} component {component!r} "
                        f"is not a number"
                    ) from None
                _require_finite(driver_path, number)
        elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
            if len(value) != 3 or any(
                isinstance(item, bool) or not isinstance(item, Real) for item in value
            ):
                raise TypeError(
                    f"input override {driver_path!r} must be three numbers or a '(x y z)' string"
                )
            for component in value:
                _require_finite(driver_path, component)
        else:
            raise TypeError(
                f"input override {driver_path!r} must be three numbers or a '(x y z)' string"
            )
```

Add `import math` and `import re` at the top of the module if they are not
already there.

- [ ] **Step 5: Give the undeclared binding a useful refusal**

`_template_for` returning `None` currently produces "is not declared; no native
utility reads that key". For a path whose only problem is the binding, name the
bindings that exist. In `validate_input_overrides`, before the generic message:

```python
        template = _template_for(driver_path)
        if template is None:
            parts = driver_path.split(".")
            for index in range(1, len(parts)):
                probe = ".".join(
                    [*parts[:index], VENT_KEY_PLACEHOLDER, *parts[index + 1:]]
                )
                if probe in _ENTRIES:
                    raise ValueError(
                        f"input override {driver_path!r} binds "
                        f"{parts[index]!r} where {probe!r} declares one of "
                        f"{sorted(VENT_KEYS)}"
                    )
            raise ValueError(
                f"input override {driver_path!r} is not declared; no native utility reads "
                "that key, and OpenFOAM would ignore it rather than report it"
            )
```

- [ ] **Step 6: Run the new test and both adapter suites**

```bash
/tmp/od311/bin/python -m pytest packages/omnidriver-cardiaccore/tests/test_qualified_addressing.py -v
/tmp/od311/bin/python -m pytest packages/omnidriver-cardiaccore/tests -q
/tmp/od311/bin/python -m pytest packages/omnidriver-cardiacfoam/tests -q
```

Expected: the new file PASSES. cardiacCore reports one failure — the
pre-existing `test_validate_configuration.py`, which Task 7 closes. cardiacFoam
reports `0 failed`.

`qualified_slot_key` is added but not yet used by any caller. That is correct:
Task 6 is where the flatten switches to it, and switching it here would mix two
reviewable changes.

- [ ] **Step 7: Commit**

`workflows/overrides.py` had no pre-existing uncommitted changes as of
2026-09-22. Confirm with `git status` before staging; if it does now, leave your
edit unstaged and say so.

```bash
git add packages/omnidriver-cardiaccore/src/omnidriver/cardiaccore/workflows/overrides.py packages/omnidriver-cardiaccore/tests/test_qualified_addressing.py
git commit -m "fix(cardiaccore): qualify parameter addresses and check value syntax (S1)

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 6: Final workflow inputs are resolved once, from effective configuration

**Finding:** S3. **Files:**
- Modify: `packages/omnidriver-cardiaccore/src/omnidriver/cardiaccore/workflows/run_config.py` — `build_config` (**pre-existing uncommitted changes — see below**)
- Modify: `packages/omnidriver-cardiaccore/src/omnidriver/cardiaccore/workflows/preprocessing.py` — the DAG `consumes` lists
- Create: `packages/omnidriver-cardiaccore/tests/test_workflow_inputs_follow_overrides.py`

**Interfaces:**
- Consumes: `qualified_slot_key` from Task 5.
- Produces: `resolve_workflow_inputs(spec) -> tuple[dict[str, Any], tuple[StrictDiagnostic, ...]]`
  in `run_config.py` — the effective configuration, resolved once, plus any
  diagnostics. `build_config` and the DAG both read it, so a field-name override
  reaches staging, validation, DAG edges and provenance from one place.

**`run_config.py` has pre-existing uncommitted changes.** They add
`_relevant_catalog_paths` and a `validate_configuration` body. **Preserve both.**
This task changes `build_config` and adds a new function; it does not touch
`validate_configuration`. Task 7 does. If you cannot make your change without
altering that function, stop and report rather than rewriting someone's WIP.

- [ ] **Step 1: Reproduce the defect**

```bash
cd /tmp && /tmp/od311/bin/python - <<'PY'
from pathlib import Path
import tempfile
from omnidriver.cardiaccore.workflows.preprocessing import make_human_purkinje_slab_spec
from omnidriver.cardiaccore.workflows.run_config import build_config

root = Path(tempfile.mkdtemp())
spec = make_human_purkinje_slab_spec(
    cases_root=root,
    input_overrides={"$CARDIAC_CONDUCTIVITY.fiberField": "myFibre"},
)
case = Path(spec.case_root)
(case / "system").mkdir(parents=True, exist_ok=True)
(case / "system" / "setCardiacConductivityDict").write_text(
    "df 0.1;\nds 0.05;\ndn 0.05;\nfiberField f;\nsheetField s;\n"
)
(case / "system" / "setCardiacAnatomyDict").write_text(
    "zApicalMid 0.3;\nzMidBasal 0.6;\nzApexCap 0.1;\n"
)
config, diagnostics = build_config(spec)
print("fiberField ->", repr(config["preprocessing"].get("fiberField")))
print("diagnostics:", diagnostics)
steps = spec.metadata["workflow_dag"]["steps"]
print("conductivity consumes:", steps[0]["consumes"])
PY
```

Expected: `fiberField -> None`, `diagnostics: ()`, and `consumes` still naming
`0/fiber` and `0/sheet`. Two failures in one: an accepted override is reported
as `None` with no diagnostic, and the declared workflow inputs do not follow the
field names the case will actually use.

The slab spec sets no `active_input_paths`, so `build_config` reads the whole
catalog, `$CARDIAC_SCAR.fiberField` collides with
`$CARDIAC_CONDUCTIVITY.fiberField` under the unqualified `slot_key`, and the
absent scar dictionary's `None` wins.

- [ ] **Step 2: Write the failing test**

Create `packages/omnidriver-cardiaccore/tests/test_workflow_inputs_follow_overrides.py`:

```python
"""One resolution of the effective configuration feeds everything.

Two consequences of resolving inputs more than once, or not at all:

* A requested conductivity field name came back as `None`, because a
  scar-dictionary entry with the same leaf name collided with it under the
  unqualified slot key and the absent scar document's `None` won. No
  diagnostic was raised -- the caller was told the write succeeded.
* The workflow DAG's `consumes` named `0/fiber` and `0/sheet` literally, so a
  case renaming those fields declared inputs it does not read and omitted the
  ones it does.

`resolve_workflow_inputs` resolves once; staging, validation, DAG edges and
provenance all read that one answer.
"""

from pathlib import Path

import pytest

from omnidriver.cardiaccore.workflows.preprocessing import (
    make_human_purkinje_slab_spec,
)
from omnidriver.cardiaccore.workflows.run_config import build_config


def _case(root: Path, **overrides) -> object:
    spec = make_human_purkinje_slab_spec(cases_root=root, input_overrides=overrides or None)
    system = Path(spec.case_root) / "system"
    system.mkdir(parents=True, exist_ok=True)
    (system / "setCardiacConductivityDict").write_text(
        "df 0.1;\nds 0.05;\ndn 0.05;\nfiberField f;\nsheetField s;\n"
    )
    (system / "setCardiacAnatomyDict").write_text(
        "zApicalMid 0.3;\nzMidBasal 0.6;\nzApexCap 0.1;\n"
    )
    return spec


def test_a_requested_field_name_is_not_replaced_by_none(tmp_path):
    spec = _case(tmp_path, **{"$CARDIAC_CONDUCTIVITY.fiberField": "myFibre"})
    config, diagnostics = build_config(spec)
    assert not [d for d in diagnostics if d.level == "error"], diagnostics
    assert config["preprocessing"]["$CARDIAC_CONDUCTIVITY.fiberField"] == "myFibre"


def test_an_absent_document_does_not_overwrite_a_present_one(tmp_path):
    """The scar dictionary is not in this case at all. Its absence must not
    reach into the conductivity dictionary's slot."""
    spec = _case(tmp_path)
    config, _ = build_config(spec)
    assert config["preprocessing"]["$CARDIAC_CONDUCTIVITY.fiberField"] == "f"
    assert "$CARDIAC_SCAR.fiberField" not in config["preprocessing"]


def test_the_dag_consumes_the_field_names_the_case_will_use(tmp_path):
    spec = _case(tmp_path, **{
        "$CARDIAC_CONDUCTIVITY.fiberField": "myFibre",
        "$CARDIAC_CONDUCTIVITY.sheetField": "mySheet",
    })
    steps = {step["id"]: step for step in spec.metadata["workflow_dag"]["steps"]}
    consumes = steps["conductivity"]["consumes"]
    assert "0/myFibre" in consumes
    assert "0/mySheet" in consumes
    assert "0/fiber" not in consumes
    assert "0/sheet" not in consumes


def test_the_default_field_names_are_unchanged_without_an_override(tmp_path):
    spec = _case(tmp_path)
    steps = {step["id"]: step for step in spec.metadata["workflow_dag"]["steps"]}
    consumes = steps["conductivity"]["consumes"]
    assert "0/fiber" in consumes
    assert "0/sheet" in consumes


def test_an_unreadable_case_reports_a_diagnostic_rather_than_a_silent_none(tmp_path):
    spec = make_human_purkinje_slab_spec(cases_root=tmp_path)
    config, diagnostics = build_config(spec)
    assert any(d.level == "error" for d in diagnostics), (config, diagnostics)
```

`test_the_dag_consumes_...` reads `spec.metadata` directly, so the resolution
has to happen inside the spec factory, where `input_overrides` is already known.
Confirm that `make_human_purkinje_slab_spec` can see the overrides before the
DAG literal is built — it can, they are its own parameter — and keep the
resolution there rather than mutating the spec afterwards.

- [ ] **Step 3: Run to verify it fails**

```bash
/tmp/od311/bin/python -m pytest packages/omnidriver-cardiaccore/tests/test_workflow_inputs_follow_overrides.py -v
```

Expected: FAIL on the qualified key, on the DAG `consumes`, and on the missing
diagnostic.

- [ ] **Step 4: Implement the single resolution**

In `packages/omnidriver-cardiaccore/src/omnidriver/cardiaccore/workflows/run_config.py`,
replace `build_config` and add the shared resolver above it. Leave
`_relevant_catalog_paths` and `validate_configuration` exactly as they are.

```python
def resolve_workflow_inputs(spec):
    """Resolve the effective configuration for a spec, once.

    Returns ``(values, diagnostics)`` keyed by
    :func:`~omnidriver.cardiaccore.workflows.overrides.qualified_slot_key`, so a
    leaf name declared by two documents occupies two slots. Staging, validation,
    the workflow DAG and provenance all read this one answer; resolving twice is
    how a DAG came to declare inputs the case does not read.

    Added 2026-09-22 (audit finding S3).
    """
    active_paths = (spec.metadata or {}).get("active_input_paths")
    paths = None if active_paths is None else tuple(active_paths)
    try:
        values = read_input_values(Path(spec.case_root), paths=paths)
    except (FileNotFoundError, KeyError, ValueError, RuntimeError) as exc:
        return {}, (
            diagnostic(
                "error", "unreadable_preprocessing_input", str(exc),
                source=str(spec.case_root),
            ),
        )
    requested = (spec.metadata or {}).get("input_overrides", {})
    try:
        values.update(validate_input_overrides(requested, allowed_paths=paths))
    except (TypeError, ValueError) as exc:
        return {}, (diagnostic("error", "invalid_input_overrides", str(exc)),)
    # An absent document contributes no slot at all. Recording it as `None`
    # is how an absent scar dictionary came to overwrite a present
    # conductivity dictionary's field name.
    return (
        {
            qualified_slot_key(driver_path): value
            for driver_path, value in values.items()
            if value is not None
        },
        (),
    )


def build_config(spec):
    config = {"preprocessing": {}}
    values, diagnostics = resolve_workflow_inputs(spec)
    if diagnostics:
        return config, diagnostics
    config["preprocessing"] = values
    return config, ()
```

Import `qualified_slot_key` from `.overrides` alongside the existing imports.
`slot_key` is no longer used by `build_config`; leave the import in place if
`validate_configuration` still uses it — Task 7 removes it.

- [ ] **Step 5: Derive the DAG's field inputs**

In `packages/omnidriver-cardiaccore/src/omnidriver/cardiaccore/workflows/preprocessing.py`,
add a helper near `coordinate_field_paths`:

```python
#: Conductivity field names the native utility reads when the dictionary does
#: not name others. These are the defaults `setCardiacConductivity.C` compiles
#: in, not a recommendation.
_DEFAULT_CONDUCTIVITY_FIELDS = {
    "$CARDIAC_CONDUCTIVITY.fiberField": "fiber",
    "$CARDIAC_CONDUCTIVITY.sheetField": "sheet",
}


def conductivity_field_paths(
    input_overrides: "Mapping[str, Any] | None",
) -> tuple[str, ...]:
    """The ``0/<field>`` inputs the conductivity step actually reads.

    A field name is adapter-configurable, so a DAG that names ``0/fiber``
    literally declares an input the case may not have and omits the one it
    does. Added 2026-09-22 (audit finding S3).
    """
    overrides = dict(input_overrides or {})
    return tuple(
        f"0/{overrides.get(driver_path, default)}"
        for driver_path, default in _DEFAULT_CONDUCTIVITY_FIELDS.items()
    )
```

Then in each of the three spec factories, replace the literal pair inside the
conductivity step's `consumes`:

```python
                        "consumes": [
                            "system/setCardiacConductivityDict",
                            *conductivity_field_paths(input_overrides),
                        ],
```

There are three such sites. Find them all:

```bash
grep -n '"0/fiber"' packages/omnidriver-cardiaccore/src/omnidriver/cardiaccore/workflows/preprocessing.py
```

Expected before the edit: three matches. Expected after: none.

`catalogs/utilities.py` also names `("system/setCardiacConductivityDict",
"0/fiber", "0/sheet")` as the utility's declared inputs. That is a *manifest*
describing the utility's defaults, not a per-case DAG edge, so leave it — but
check whether any consumer treats the manifest as the run's actual inputs, and
report what you find. If one does, that is a second occurrence of this defect
and belongs in your report rather than in a silent extra edit.

- [ ] **Step 6: Run the new test and the cardiacCore suite**

```bash
/tmp/od311/bin/python -m pytest packages/omnidriver-cardiaccore/tests/test_workflow_inputs_follow_overrides.py -v
/tmp/od311/bin/python -m pytest packages/omnidriver-cardiaccore/tests -q
```

Expected: the new file PASSES; cardiacCore reports one failure — the
pre-existing `test_validate_configuration.py`.

The `preprocessing` slice keys are now qualified (`$CARDIAC_CONDUCTIVITY.df`
rather than `df`). Any test or consumer reading an unqualified key from
`run.config["preprocessing"]` will fail. That is the fix reaching its consumers.
Find them before assuming there are none:

```bash
grep -rn 'config\["preprocessing"\]\|"preprocessing"\]\[' packages/
```

Update each to the qualified key, and list them in your report.

- [ ] **Step 7: Check the resume-fingerprint consequence**

The roadmap flags a limit on S3: it proves the declared DAG inputs disagree with
the accepted edit, but not that the changed field is omitted from resume
fingerprints, because another provenance path walks case inputs. Settle it:

```bash
/tmp/od311/bin/python -m pytest packages/omnidriver/tests -q -k "resume or fingerprint or provenance"
grep -rn "consumes" packages/omnidriver/src/omnidriver/core/runtime/provenance_inputs.py packages/omnidriver/src/omnidriver/core/runtime/resume.py
```

If `consumes` feeds the fingerprint, the fix above closes that too — write a test
that proves it and add it to the new file. If a separate walk over case inputs
feeds it, say so explicitly in your report: the DAG defect was real and the
fingerprint was not affected. Do not claim either without the grep result.

- [ ] **Step 8: Commit**

```bash
git add packages/omnidriver-cardiaccore/src/omnidriver/cardiaccore/workflows/run_config.py packages/omnidriver-cardiaccore/src/omnidriver/cardiaccore/workflows/preprocessing.py packages/omnidriver-cardiaccore/tests/test_workflow_inputs_follow_overrides.py
git commit -m "fix(cardiaccore): resolve workflow inputs once from effective config (S3)

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

`run_config.py` carried pre-existing uncommitted work. This commit includes it,
which is unavoidable — the file is the one being changed. Say so in your report
and name what was pre-existing: `_relevant_catalog_paths` and the
`validate_configuration` body.

---

## Task 7: `validate_configuration` is wired to the plugin

**Finding:** S2. **Files:**
- Modify: `packages/omnidriver-cardiaccore/src/omnidriver/cardiaccore/plugin.py` — `validate_configuration`
- Modify: `packages/omnidriver-cardiaccore/src/omnidriver/cardiaccore/workflows/run_config.py` — `_relevant_catalog_paths` (**pre-existing WIP**)
- Modify: `packages/omnidriver-cardiaccore/src/omnidriver/cardiaccore/plugin.yaml` — the stub comment
- Modify: `packages/omnidriver-cardiaccore/tests/test_validate_configuration.py` (**pre-existing WIP**)

**Interfaces:**
- Consumes: `qualified_slot_key` (Task 5) and `resolve_workflow_inputs` (Task 6).
- Produces: `CardiacCorePlugin.validate_configuration(spec) -> tuple[StrictDiagnostic, ...]`
  — delegating to `workflows.run_config.validate_configuration`.

**Two files here are someone else's work in progress.** Review before changing.
The WIP is a genuine fix: it reads the spec's own workflow-relevant catalog
entries rather than only what a tutorial exposes as overridable. Its one
weakness is `_relevant_catalog_paths`'s docstring, which scopes reads to the
running utilities *in order to dodge the `slot_key` collision*. Task 5 removed
that collision, so the workaround's justification is gone — but the scoping
itself is independently right, for the reason the docstring gives second
("a case that never runs `setCardiacScar` still report a value from a scar
dictionary that does not exist"). Keep the scoping; correct the docstring.

- [ ] **Step 1: Reproduce the defect**

```bash
/tmp/od311/bin/python -m pytest packages/omnidriver-cardiaccore/tests/test_validate_configuration.py -v
/tmp/od311/bin/python -c "
import inspect
from omnidriver.cardiaccore.plugin import CardiacCorePlugin
print(inspect.getsource(CardiacCorePlugin.validate_configuration))"
```

Expected: one failure — `assert 'conductivityIntracellular.df' in ''` — and a
method body of `del spec; return ()`. The implementation in
`workflows/run_config.py` is complete and unreachable.

- [ ] **Step 2: Wire the hook**

In `packages/omnidriver-cardiaccore/src/omnidriver/cardiaccore/plugin.py`:

```python
    def validate_configuration(self, spec: Any) -> tuple[Any, ...]:
        """Check this spec's workflow-relevant catalog entries at plan time.

        Wired 2026-09-22 (audit finding S2). This returned ``()``
        unconditionally while a complete implementation sat unreachable in
        ``workflows/run_config.py``, so a co-required pair left half-set in the
        resolved case went unreported until a RunDocument happened to expose it
        at run/step time.
        """
        from .workflows.run_config import validate_configuration

        return validate_configuration(spec, self)
```

- [ ] **Step 3: Run the WIP test**

```bash
/tmp/od311/bin/python -m pytest packages/omnidriver-cardiaccore/tests/test_validate_configuration.py -v
```

Expected: all three PASS. If `test_a_half_set_bidomain_pair_...` still fails,
the cause is now inside `validate_configuration` rather than in the wiring —
debug it there and report what you found. If
`test_generic_case_folder_entries_are_not_checked_against_this_catalog` fails,
the `generic_case` bypass is not reached; do not remove the test.

- [ ] **Step 4: Make `validate_configuration` use the single resolution**

`validate_configuration` currently builds its own `fake_run` with an unqualified
`slot_key` flatten. After Task 6 that disagrees with what `build_config`
produces — two flattens, two vocabularies, which is the defect class this plan
exists to remove. Replace that block:

```python
    fake_run = SimpleNamespace(config={"preprocessing": {
        qualified_slot_key(driver_path): value
        for driver_path, value in values.items()
        if value is not None
    }})
```

and change the import at the top of the function from `slot_key` to
`qualified_slot_key`, imported from `.overrides`.

`validate_run` in `core.specs.validation` looks slots up through `_slice_value`,
which calls core's unqualified `slot_key`. With qualified keys in the slice, that
lookup will miss. Two honest options, and the choice is yours on evidence:

1. Teach `_slice_value` to try the qualified key first and fall back to the
   unqualified one, with a dated note. Core stays generic — it is looking up a
   `driver_path` in a slice, and both spellings are legitimate keys.
2. Have the adapter supply its own lookup.

Option 1 is the smaller change and keeps one validator. If you take it, the core
edit is:

```python
def _slice_value(run, phase: str, driver_path: str):
    """Look up the slot value for a driver_path inside a phase slice.

    Both spellings are legitimate slot keys: an adapter whose documents share
    leaf names must qualify, and one whose documents do not may not. Try the
    full path first, then the scope-stripped form. Added 2026-09-22 alongside
    cardiacCore's qualified addressing (audit findings S1, S3).
    """
    slice_ = run.config.get(phase, {}) or {}
    if driver_path in slice_:
        return slice_[driver_path]
    return slice_.get(slot_key(driver_path))
```

That is a core change in a task otherwise scoped to an adapter. It is in scope
because core owns `_slice_value` and the generality is core's, not cardiac — but
say so in your report, and check `scripts/check-import-boundaries.py` still
passes.

- [ ] **Step 5: Correct the WIP docstring**

In `_relevant_catalog_paths`, the first justification for scoping is now stale.
Replace it, keeping the second, and record the correction:

```python
def _relevant_catalog_paths(spec, plugin) -> tuple[str, ...]:
    """Declared entries whose document the spec's own workflow steps touch.

    Scoping to *every* catalog entry (``paths=None``) is wrong: several
    documents (``setCardiacScarDict``, ``setPurkinjeScarDict``,
    ``coordinatesConventionDict``) are declared-only -- no current tutorial
    runs their utility -- so reading the whole catalog would let a case that
    never runs ``setCardiacScar`` report a value from a scar dictionary that
    does not exist. Scoping to what the spec's own utilities read keeps this a
    per-workflow check, matching what actually gets staged and run.

    **Corrected 2026-09-22:** this also cited a ``slot_key`` collision between
    ``$CARDIAC_SCAR.fiberField`` and ``$CARDIAC_CONDUCTIVITY.fiberField``,
    where iteration order could overwrite a real value with an absent one. That
    collision was real (audit findings S1, S3) and is now fixed at its cause by
    ``qualified_slot_key``, which keeps the scope token. The scoping below is
    kept for the declared-only reason above, which stands on its own.
    """
```

- [ ] **Step 6: Correct `plugin.yaml`**

Two comments there describe the hook as `del spec; return ()`. Replace both with
a dated correction rather than deleting them:

```yaml
# validate_configuration (configuration_validator) was `del spec; return ()`
# until 2026-09-22, when it was wired to
# workflows/run_config.validate_configuration (audit finding S2). It now
# checks the spec's own workflow-relevant catalog entries against the resolved
# case at plan time, and exempts a generic case_folder run.
```

Read both comment blocks first; match the surrounding style rather than pasting
this verbatim.

- [ ] **Step 7: Run everything**

```bash
/tmp/od311/bin/python -m pytest packages/omnidriver-cardiaccore/tests -q
/tmp/od311/bin/python -m pytest packages/ -q -m "not slow"
/tmp/od311/bin/python scripts/check-import-boundaries.py
/tmp/od311/bin/python scripts/export-capability-seams.py --check
```

Expected: **`0 failed` across the whole non-slow suite.** This is the task that
makes that true — the pre-existing failure is now closed. If anything else
fails, it is a consequence of wiring a check that never ran, which means the
check found something. Investigate it; do not disable the hook.

In particular, `test_generic_contract.py::test_controlled_allrun_executes_without_domain_claims`
is the case the WIP's `generic_case` bypass exists to protect. Confirm it passes.

- [ ] **Step 8: Commit**

```bash
git add packages/omnidriver-cardiaccore/src/omnidriver/cardiaccore/plugin.py packages/omnidriver-cardiaccore/src/omnidriver/cardiaccore/plugin.yaml packages/omnidriver-cardiaccore/src/omnidriver/cardiaccore/workflows/run_config.py packages/omnidriver-cardiaccore/tests/test_validate_configuration.py
git commit -m "fix(cardiaccore): wire validate_configuration to the plugin (S2)

Closes the pre-existing untracked regression test. The implementation existed
in workflows/run_config.py and was unreachable.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

If Step 4 took option 1, add
`packages/omnidriver/src/omnidriver/core/specs/validation.py` to the stage and
say so in the commit body.

---

## Task 8: Required-check coverage blocks at the dispatch boundary

**Finding:** C2. **Files:**
- Modify: `packages/omnidriver/src/omnidriver/core/runtime/launch_readiness.py` — the docstring's stale claim
- Modify: `packages/omnidriver/src/omnidriver/core/runtime/run_document_exec.py` — carry the audit to the gate
- Modify: `packages/omnidriver/src/omnidriver/cli.py` — pass `simulation_audit` at the dispatch-time call site
- Create: `packages/omnidriver/tests/core/test_coverage_blocks_dispatch.py`

**Interfaces:**
- Consumes: nothing.
- Produces: the dispatch-time `is_launchable` call receives `simulation_audit`,
  so a stage whose required check reported `unavailable` blocks launch. Phase 2's
  G2 exit criterion — "post-write unknown evidence blocks the appropriate
  execution" — is this gate plus Task 3's evidence.

- [ ] **Step 1: Reproduce the defect**

```bash
/tmp/od311/bin/python -c "
import inspect
from omnidriver.core.runtime.launch_readiness import is_launchable
doc = inspect.getdoc(is_launchable)
print([l for l in doc.splitlines() if 'not yet wired' in l.lower() or 'No caller passes' in l])"
grep -n "is_launchable(" -A 6 packages/omnidriver/src/omnidriver/cli.py | grep -c "simulation_audit"
```

Expected: the docstring's own admission — "**Not yet wired to dispatch, as of
2026-09-19.** No caller passes `simulation_audit`" — and a count of `0`. The
predicate models the check; nothing supplies its input, so `coverage_ok` is
always `True` at the one gate that matters.

- [ ] **Step 2: Identify the dispatch-time call site**

```bash
grep -n "is_launchable(" -B 8 packages/omnidriver/src/omnidriver/cli.py
grep -n "_refuse_environment_errors" -B 4 -A 12 packages/omnidriver/src/omnidriver/cli.py
```

There are several `is_launchable` call sites. Only the dispatch-time one must
gain coverage — planning call sites read `structural_ok` and must keep working
with no runtime installed. The comment at the first call site
("`is_launchable` is relevant at this dispatch-time gate") names it. Record
which line numbers you found and which you chose, and why, in your report.

- [ ] **Step 3: Write the failing test**

Create `packages/omnidriver/tests/core/test_coverage_blocks_dispatch.py`:

```python
"""A required check that could not run must block the launch it covers.

`is_launchable` has modelled this since 2026-09-19 and its own docstring
recorded that nothing supplied `simulation_audit`, so `coverage_ok` was always
True at the gate. An introspection field that always says yes is worse than no
field: it reads as a guarantee.

Phase 2 makes post-write effective-value readback a required check. If an
unavailable check cannot block, a write whose result could not be verified
dispatches anyway.
"""

import pytest

from omnidriver.core.planning_types import SimulationAuditItem, diagnostic
from omnidriver.core.runtime.launch_readiness import is_launchable


def test_an_unavailable_required_check_blocks():
    readiness = is_launchable(
        plan_status="ok",
        simulation_audit=(
            SimulationAuditItem(stage="effective_configuration", status="unavailable"),
        ),
    )
    assert not readiness.launchable
    assert not readiness.coverage_ok
    assert "effective_configuration" in readiness.blocking_reason


@pytest.mark.parametrize("status", ["not_requested", "not_applicable"])
def test_a_declined_or_inapplicable_check_does_not_block(status):
    readiness = is_launchable(
        plan_status="ok",
        simulation_audit=(SimulationAuditItem(stage="scientific", status=status),),
    )
    assert readiness.launchable


def test_omitting_the_audit_still_never_blocks():
    """Offline planning must keep working with no runtime installed."""
    assert is_launchable(plan_status="ok").launchable


def test_the_dispatch_gate_receives_the_audit():
    """The half that was missing: the predicate was correct and unfed.

    Asserts against the call site rather than the predicate, because the
    predicate already passed every test above while the gate was blind.
    """
    import inspect

    from omnidriver import cli

    source = inspect.getsource(cli)
    dispatch_calls = [
        block for block in source.split("is_launchable(")[1:]
        if "simulation_audit" in block.split(")")[0]
    ]
    assert dispatch_calls, (
        "no is_launchable call site passes simulation_audit; the coverage half "
        "of the predicate cannot fire"
    )
```

`test_the_dispatch_gate_receives_the_audit` inspects source text, which is a
weak test. Replace it with a behavioural one as soon as you can construct a
dispatch whose audit carries an `unavailable` stage — a CLI invocation against a
case with the runtime absent is the likely shape. Look for an existing harness in
`packages/omnidriver/tests` that already drives dispatch before writing a new
one, and say in your report which form you shipped.

- [ ] **Step 4: Run to verify it fails**

```bash
/tmp/od311/bin/python -m pytest packages/omnidriver/tests/core/test_coverage_blocks_dispatch.py -v
```

Expected: the first three PASS (the predicate is already correct) and
`test_the_dispatch_gate_receives_the_audit` FAILS. That split is the finding:
the logic was never the problem.

- [ ] **Step 5: Carry the audit to the gate**

Find where the simulation audit is produced — `strict_audit.py` and
`SimulationAuditItem`'s constructors are the places to look:

```bash
grep -rn "SimulationAuditItem(" packages/omnidriver/src/
grep -rn "simulation_audit" packages/omnidriver/src/
```

Thread it from there to the dispatch-time `is_launchable` call. Do not
manufacture an audit at the call site: if the execution context does not carry
one, add the field to the context rather than building one locally, or the gate
checks a value it invented. `StepExecutionContext` in
`core/runtime/execution_context.py` is named in the docstring as the type that
does not carry it.

Then correct the docstring in `launch_readiness.py`:

```python
    **Wired to dispatch 2026-09-22** (audit finding C2). The dispatch-time gate
    passes ``simulation_audit``; planning call sites still omit it and read
    ``structural_ok`` only, so offline planning keeps working with the runtime
    absent. Read ``coverage_ok`` as "no required check reported ``unavailable``
    to this call" -- for a call that was given no audit, that remains a
    statement about the call, not a guarantee about the run.
```

Replace the old paragraph; do not leave both.

- [ ] **Step 6: Run everything**

```bash
/tmp/od311/bin/python -m pytest packages/omnidriver/tests/core/test_coverage_blocks_dispatch.py -v
/tmp/od311/bin/python -m pytest packages/ -q -m "not slow"
/tmp/od311/bin/python scripts/export-capability-seams.py --check
```

Expected: the new file PASSES and the full non-slow suite reports `0 failed`.

If wiring the audit newly blocks an existing test's dispatch, a required check
in that test genuinely could not run. Find out which stage and why. Emitting
`not_applicable` for a stage that truly does not apply is a correct fix;
suppressing the gate is not.

- [ ] **Step 7: Commit**

```bash
git add packages/omnidriver/src/omnidriver/core/runtime/launch_readiness.py packages/omnidriver/src/omnidriver/core/runtime/run_document_exec.py packages/omnidriver/src/omnidriver/cli.py packages/omnidriver/tests/core/test_coverage_blocks_dispatch.py
git commit -m "fix(core): block dispatch when a required check could not run (C2)

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

Adjust the staged paths to the files you actually changed — Step 5's threading
may touch `execution_context.py` or `strict_audit.py` instead.

---

## Task 9: Four shapes, static gates, and the close-out

**Files:** none created; this task changes only this plan's Status table and, if
a claim in it turned out wrong, the documents that carry that claim.

- [ ] **Step 1: Rebuild both environments from scratch**

An editable install leaves the repository on `sys.path`, so a module reading
repo-relative state at import time still works. That class of defect is only
visible from a wheel — and a stale wheel tests stale code.

```bash
rm -rf /tmp/od311 /tmp/odcore
uv venv --python 3.11 /tmp/od311 && VIRTUAL_ENV=/tmp/od311 uv pip install -q \
  -e "packages/omnidriver[post]" -e packages/omnidriver-openfoam \
  -e packages/omnidriver-cardiacfoam -e packages/omnidriver-cardiaccore pytest
uv venv --python 3.11 /tmp/odcore && VIRTUAL_ENV=/tmp/odcore uv pip install -q \
  -e "packages/omnidriver[post]" pytest
```

- [ ] **Step 2: Run all four shapes**

```bash
/tmp/od311/bin/python -m pytest packages/ -q -m "not slow"
/tmp/od311/bin/python -m pytest packages/omnidriver/tests -q
/tmp/odcore/bin/python -m pytest packages/omnidriver/tests -q -m "not slow"
/tmp/od311/bin/python scripts/check-import-boundaries.py
/tmp/od311/bin/python scripts/export-capability-seams.py --check
```

Expected: `0 failed` in all three suites; both gates exit 0.

The core-only shape matters here specifically: Task 7 may have edited
`core/specs/validation.py`, and `/tmp/odcore` has no adapter installed. If
`_slice_value`'s qualified-key lookup imported anything cardiac, the import
gate would have caught it — but run the shape anyway.

**Known pre-existing failure, found by batch G0-A 2026-09-22.**
`test_every_core_module_imports_from_a_wheel` fails on this machine with an
`ensurepip ... SIGABRT` during venv creation *inside* the test. It was
confirmed to fail identically on unmodified `db93cc4` via `git stash`, so it is
environmental and not caused by any task in this plan. It carries
`@pytest.mark.slow`, so it does not appear in the `-m "not slow"` shapes.

Before running the wheel shape below, establish whether that failure is this
machine's toolchain or a real defect: the wheel shape is the one the repository
calls "the shape people skip and the one that found the worst defects", and
closing G0 on a wheel check that cannot run is closing it on nothing. If it
remains unrunnable here, record it in the Status table as **wheel shape blocked
by a local `ensurepip` failure**, with the exact error, rather than reporting
the gate as passed.

- [ ] **Step 3: Run the wheel shape**

```bash
rm -rf /tmp/wheeltest /tmp/wheelenv
python -m build --outdir /tmp/wheeltest packages/omnidriver
uv venv --python 3.11 /tmp/wheelenv
VIRTUAL_ENV=/tmp/wheelenv uv pip install -q "/tmp/wheeltest/omnidriver-*.whl[post]" pytest
/tmp/wheelenv/bin/python scripts/check-wheel-artifact.py
/tmp/wheelenv/bin/python -m pytest packages/omnidriver/tests -q
```

Expected: the artifact gate exits 0 and the suite reports `0 failed`.

- [ ] **Step 4: Confirm every finding is closed, by reproduction**

Re-run each Step 1 reproduction from Tasks 1–8. Each must now fail to reproduce.
Record the result per finding in the Status table — a finding whose reproduction
still reproduces is not closed, whatever the tests say.

- [ ] **Step 5: Record what remains untested**

Two things this plan cannot establish on a machine without OpenFOAM:

- F1b's premise, that `foamDictionary` prints `0.001` for a requested `1e-3`.
- F2's chain, that `find_etc_file` selects what `foamEtcFile` selects.

If Tasks 3 and 4 could not probe a native runtime, write that into the Status
table as **untested against a native runtime** rather than leaving it implied.
The roadmap's G5 gate requires native evidence; an honest gap recorded now is
what makes that gate reachable.

- [ ] **Step 6: Update the Status table and unblock Phase 2**

Set every task's state to its commit hash. Then add, under the table:

```markdown
**G0 closed <date>.** All eight findings reproduce no longer; four
installation shapes and both static gates pass. Phase 2
(`2026-09-20-phase2-one-write-channel.md`) may begin at G1.
```

Add the same date to that plan's own review-checkpoint note, so a reader
arriving there sees the prerequisite is met rather than inferring it.

- [ ] **Step 7: Commit**

```bash
git add docs/superpowers/plans/2026-09-22-phase2-prerequisites.md docs/superpowers/plans/2026-09-20-phase2-one-write-channel.md
git commit -m "docs: close G0 -- composition, evidence and addressing prerequisites

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

`docs/superpowers/plans/2026-09-20-phase2-one-write-channel.md` had pre-existing
uncommitted changes as of 2026-09-22 (the review checkpoint). Check `git status`
first; if they are still unstaged and not yours, edit only the date line and say
so in your report.
