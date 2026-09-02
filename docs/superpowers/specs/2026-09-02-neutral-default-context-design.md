# Neutral default context, and the end of core's cardiac vocabulary

**Status:** design, approved 2026-09-02. Branch `phase1-core-completion`.

Closes the last two open rows of `GITHUB_MIGRATION.md` §3 that concern
core/plugin decoupling: the "20 cardiac-gated `legacy_*` branches" row and the
"explicit `DriverContext` in core" row. Licensing, the CI matrix, and the
unused `numpy`/`gmsh` dependencies are separate rows and are **out of scope**.

## What was actually true when this was written

Both tracked rows were stale, and one was hiding a live defect. Measured
2026-09-02 against `760f5ea`.

**The twenty gates are already deleted.** `grep -c 'org\.cardiacfoam'
packages/omnidriver/src/omnidriver/core/compatibility.py` returns `0`.
`packages/omnidriver-cardiacfoam/tests/test_no_cardiac_gate_is_reached.py`
already guards the gated set at empty and records the deletion in its own
docstring ("Phase 2 Task 7 ... deleted all twenty branches"). The
`GITHUB_MIGRATION.md` row calling this "unblocked, not yet done" is wrong, as
is its claim that `test_core_context_is_explicit.py` and
`test_fallback_census.py` "are not yet ported" — both exist under
`packages/omnidriver/tests/core/` and pass.

**Two untrue sentences survive the deletion.**
`core/plugin_capabilities.py:1361` and `core/capability_seams.py:133` both
still state that a missing optional hook returns "cardiac data only for
`org.cardiacfoam` and a neutral value for every other plugin". After the
deletion there is no such branch anywhere. `capability_seams.py`'s copy is
worse than a stale comment: it is the generator input for `ARCHITECTURE.md`'s
capability-seam table, so the false claim is published.

**The import-boundary gate is red.** `scripts/check-import-boundaries.py`
exits 1 on a `KNOWN_VIOLATIONS` entry
(`dict_entries.py:80:omnidriver.cardiacfoam.common_dict_entries`) that no
longer matches anything — the PEP 562 re-export it waived was removed during
the 2026-09-02 alias cleanup and the waiver was not. The script fails on stale
waivers by design, precisely so the list cannot rot into a lie; nothing ran it
after that cleanup.

**Core launders the cardiac default through its own public edge.** All six
remaining `resolve_public_driver_context(` call sites sit at what
`test_core_context_is_explicit.py` explicitly blesses as the public edge
(`omnidriver/*.py` and cli.py), so the static guard passes. But
`core/runtime/sweep_runner.py` calls two of them from inside core:

    :268  route_case_values(..., driver_context=driver_context)   # threaded
    :273  materialize_case(case_dir=..., routed=routed)           # NOT threaded
    :449  materialize_case(case_dir=case_dir, routed=routed)      # NOT threaded

Confirmed at runtime — `materialize_case` with no context fires
`legacy_default_driver_context`. A sweep driven by an explicit non-cardiac
plugin therefore materializes its cases through cardiacFoam. Neither guard
sees it: the AST guard only looks for direct `resolve_public_driver_context`
calls inside `core/`, and `test_fallback_census.py` exercises only capability
reads, never the sweep path.

## Goal

Core contains no cardiac vocabulary and no runtime cardiac import, and
`scripts/check-import-boundaries.py`'s `KNOWN_VIOLATIONS` is empty — so that
gate stops being a list of excuses and becomes a standing proof of core's
independence. The cardiacFoam plugin keeps behaving exactly as it does today,
because it is the only installed plugin in every real install.

## Non-goal

Removing the no-argument convenience API. `get_heterogeneity_models()`,
`materialize_case(...)`, `route_case_values(...)` and cardiacfoam's
`dict_builder` entry points keep working with no context supplied. What
changes is *what* "no context supplied" resolves to.

---

## Part A — make the record true

Pure bookkeeping, no behaviour change. Lands first so the gate is green before
anything moves.

1. Delete the stale `dict_entries.py:80` entry from `KNOWN_VIOLATIONS` in
   `scripts/check-import-boundaries.py`. Gate returns to exit 0.
2. Correct `core/plugin_capabilities.py:1361` and
   `core/capability_seams.py:133` to describe what the fallbacks now do: a
   missing optional hook runs the named fallback, which returns a neutral
   value for every plugin, with the two sweep fallbacks refusing by hook name
   instead. Regenerate `ARCHITECTURE.md` via
   `scripts/export-capability-seams.py`.
3. Rewrite the `GITHUB_MIGRATION.md` gate row and its §-intro summary to
   record the row as closed, citing the `grep -c` result and
   `test_no_cardiac_gate_is_reached.py` as the evidence. Correct the "two
   guard tests not yet ported" claim in the `DriverContext` row.

**Verify:** `scripts/check-import-boundaries.py` exits 0;
`scripts/export-capability-seams.py --check` reports up to date; full suite
unchanged at 1542 passed.

## Part B — close the laundering

Independent of Part C; this is a defect fix that stands on its own.

4. Thread `driver_context=driver_context` into the `materialize_case` calls at
   `core/runtime/sweep_runner.py:273` and `:449`, matching the adjacent
   `route_case_values` calls that already do.
5. Add both guards, because each existing one alone missed this:
   - **Behavioural.** Extend `test_fallback_census.py` with a generic (non-entry)
     sweep driven by an explicit non-cardiac context, asserting
     `legacy_default_driver_context` fires zero times. This is the check that
     would have caught the defect.
   - **Static.** Extend `test_core_context_is_explicit.py` so that a call in
     `core/` to a public-edge function accepting `driver_context`
     (`materialize_case`, `route_case_values`, and `dict_entries`'
     `get_heterogeneity_models` / `get_electro_property_entry_groups` /
     `all_documented_driver_paths`) must pass it. The guard currently reasons
     only about direct `resolve_public_driver_context` calls, which is why
     laundering through `omnidriver/*.py` was invisible.

     The set of guarded names is written as an explicit list in the test, not
     inferred. An inferred rule would either miss functions or fire on
     unrelated ones; an explicit list is greppable and fails loudly when a
     name it mentions stops existing.

**Verify:** the new census case fails before step 4 and passes after; full
suite green.

## Part C — neutral default resolution

6. Rewrite `compatibility.legacy_default_driver_context()` to resolve the
   default through entry-point discovery rather than importing
   `CardiacFoamPlugin`:

   - exactly one plugin registered in the `omnidriver.plugins` group → load it
     via `load_discovered_plugin`, which already records the installing
     distribution and version in `DriverContext.source`;
   - zero registered → `generic_openfoam_context()`;
   - more than one, with none selected → `LookupError` naming every candidate
     and pointing at `--plugin` / an explicit `DriverContext`.

   **Behaviour is preserved in every real install.** Measured in the
   all-packages venv, exactly one plugin registers the group
   (`cardiacfoam -> omnidriver.cardiacfoam.cardiacfoam_plugin:CardiacFoamPlugin`,
   from `omnidriver-cardiacfoam`). Core declares the group but registers
   nothing in it; `omnidriver-openfoam` registers nothing. So the
   one-plugin rule resolves to cardiacFoam today, unchanged.

   **The name stays `legacy_default_driver_context`.** It is the token every
   census assertion keys on, and its meaning — "an implicit resolution
   happened at the public edge" — is still exactly right. Only its docstring
   and body change. Renaming would churn the instrumentation, the seam table,
   and the waiver list for no gain.

   **No new configuration surface.** No env var, no config key for choosing
   among several plugins. The multi-plugin case raises and names the
   candidates. If a declared default turns out to be needed, that is a later
   decision made against real evidence rather than anticipated here.

7. Close the other two cardiac-shaped defaults on the same generic-case path.
   Both have the identical shape — *the caller said nothing, so be cardiacFoam*:

   - `legacy_generic_case_mutation` (`compatibility.py:86`) imports
     `omnidriver.cardiacfoam.generic_case_mutation`. It backs
     `core/runtime/generic_case.py:215`'s `_apply_case_mutation` default.
   - `legacy_generic_case_dict_file_relpaths` (`compatibility.py:93`)
     hardcodes `constant/electroProperties` and `constant/physicsProperties`
     as core's default dictionary files.

   Both become the plugin's business, and the seam already exists:
   `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/tutorials/generic_case.py:13`
   already does `kwargs.setdefault("_apply_case_mutation", apply_case_mutation)`.
   Add a matching `setdefault` for `dict_file_relpaths` carrying the two
   cardiac paths, then delete both core fallbacks. This is a move of two
   values from core into the plugin that already owns them, not a change to
   either.

   The neutral defaults are already specified by core, not invented here.
   `dict_file_relpaths` becomes `{}`, which `generic_case.py:238-243` already
   defines: *"Declaring no dictionary files at all leaves the folder
   generic."* With an empty mapping, `primary_relpaths` is empty, the
   marker-file `any(...)` is `False`, and a folder is generic unless one of
   the other conditions says otherwise — the correct reading for a core that
   knows no solver's vocabulary. `_apply_case_mutation` becomes a no-op when
   no caller and no plugin supplies one.

   `legacy_generic_case_dict_file_relpaths`' own docstring already anticipates
   this: *"Plan 2 seam: a plugin declaring its own dictionary files makes this
   default unnecessary."*

8. Empty `KNOWN_VIOLATIONS` in `scripts/check-import-boundaries.py`. With 6
   and 7 done, both remaining waivers
   (`core/compatibility.py:59`, `core/compatibility.py:86`) name imports that
   no longer exist. The script fails on stale waivers, so this step is forced
   rather than optional — which is the point.

**Verify:**

- `grep -rn 'cardiacfoam' packages/omnidriver/src --include='*.py'` returns
  only docstring/comment references, no runtime import.
- `scripts/check-import-boundaries.py` exits 0 with `KNOWN_VIOLATIONS` empty.
- In a core-only venv, `from omnidriver.dict_entries import
  get_heterogeneity_models; get_heterogeneity_models()` returns `()` instead
  of raising `ModuleNotFoundError: No module named 'omnidriver.cardiacfoam'`.
- In the all-packages venv, `default_driver_context().identity.id` is still
  `org.cardiacfoam`, and its `source` now reads
  `entry-point:omnidriver-cardiacfoam=<version>` rather than
  `trusted-import:...`.
- Full suite green; core-only suite green.

### Risk

The one real risk is the zero-plugin fallback: a *missing* plugin install now
degrades to generic semantics instead of announcing itself with an
ImportError. The mitigation is provenance, not prevention —
`DriverContext.source` records `built-in:generic-openfoam`, and every plan
already states the source it was built against, so a run that silently went
generic says so in its own output. This was weighed against raising a
`LookupError` and chosen deliberately: "core alone is a working generic
driver" is the property this whole decoupling effort exists to establish, and
a core-only install that refuses to run does not demonstrate it.

A second, smaller risk: `DriverContext.source` changes string form for
implicit resolutions (`trusted-import:` → `entry-point:`). Any test asserting
that literal must be updated rather than worked around; provenance strings are
observable output.

## Baselines (2026-09-02, at `760f5ea`)

| suite | command | result |
|---|---|---|
| full | `/tmp/od_all/bin/python -m pytest packages/ -q -m "not slow"` | 1542 passed, 276 skipped, 1 deselected, 40 subtests |
| core-only | `/tmp/od_core/bin/python -m pytest packages/omnidriver/tests -q` | 676 passed, 93 skipped |

Note the core-only suite is already green. It is green because its tests
thread explicit contexts, not because the default is neutral — Part C fixes
the contract, not a currently-red test. The core-only public-edge probe above
is the check that actually distinguishes the two.

## Landing

Three commits on `phase1-core-completion`, each independently revertable and
each verified before the next: **A** (record + gate green), **B** (sweep
laundering fix + both guards), **C** (neutral default + generic-case defaults
+ empty waiver list).
