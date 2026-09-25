# Independent OpenFOAM mechanics review

2026-09-22. Maintainer role. Reviewed the OpenFOAM lead report and consolidated roadmap, the maintainer guidance, and the relevant implementation. This was an independent bounded reproduction, not a production repair or a solver simulation.

## Verdict

All three tested claims are confirmed. Keep the proposed package boundaries and revise Phase 2. **Effective-value comparison must join environment forwarding in G0**: repairing forwarding alone exposes a false rejection of valid scientific-notation scalar requests. The present consolidated findings table does not make this dependency explicit enough.

## Reproductions

Used `.venv/bin/python`, temporary directories removed on exit, and the real OpenFOAM provider/override adapter. The override fixture used a minimal catalog context and the explicit `system/controlDict:deltaT` route; it did not exercise provider-stack construction or the full candidate dispatcher. These limits matter when designing the permanent public-edge regression.

| Claim | Independent observation | Assessment |
|---|---|---|
| O1 / F1: execution environment disappears | `_OverrideScopeAdapter(OpenFOAMEnvironmentPlugin()).apply(...)` with `execution_env={"PATH": "/deliberately/no/runtime"}` wrote `deltaT 0.0005` and returned `()`. Calling the lower `apply_overrides` with the same request/environment returned `status="runtime_unavailable"`, `matches_requested=False`. | Confirmed by differential behavior through the real adapter and provider. |
| O2 / F2: `includeEtc` records the wrong dependency | Under v2412, a temporary `WM_PROJECT_SITE/etc/caseDicts/profiling/parallel.cfg` containing `siteProbe 123;` was selected by native resolution. Result: `status="resolved"`, `value="123"`; inspected files named the temporary root dictionary and `/Volumes/OpenFOAM-v2412/etc/caseDicts/profiling/parallel.cfg`. The actual site file was absent. `environment_keys` contained only `FOAM_ETC`. | Confirmed. Both file provenance and relevant environment dependency evidence are incomplete. |
| O3: scalar spelling is confused with value equality | Direct helper request `value="1e-3"` produced `status="resolved"`, `value="0.001"`, `matches_requested=False`. | Confirmed for this scalar request/build. Other types still need their own declared comparison rules. |

Native environment was loaded using the lead's documented recipe:

```python
runtime = load_openfoam_environment(
    explicit_bashrc="/Volumes/OpenFOAM-v2412/etc/bashrc"
)
env = runtime.env
```

Queries used `bashrc=None, env=env`; the site reproduction overrode only `WM_PROJECT_SITE`. No executable dictionary directives were used. The native result identified `/Volumes/OpenFOAM-v2412` as runtime. This corroborates the lead's selected local build, not portability to other releases or distributions.

## Source cross-check and qualifications

- `core/plugin_capabilities.py::_OverrideScopeAdapter.apply` accepts `execution_env` and omits it from the real hook call. `openfoam/environment.py::OpenFOAMEnvironmentPlugin.apply_overrides` also lacks that argument. Correcting only one site cannot complete the repair.
- `openfoam/apply_overrides.py::apply_overrides` returns `()` when no execution environment arrives. Its native comparison is literal string equality against `_effective_value_text`. The write helper's local restore context ends before effective readback; effective-check rollback belongs to the caller's transaction. Tests must establish which boundary promises rollback.
- `core/runtime/step_candidate.py::execute_candidate` filters returned records for non-resolved or mismatched results. An empty collection yields no failed checks; a resolved scalar with `matches_requested=False` raises rejection. The latter dispatcher consequence was verified by source inspection, not a dispatched run.
- Installed native `src/OpenFOAM/global/etcFiles/etcFiles.C::findEtcEntries` considers user, site and project resources, including version-qualified directories. `groupResourceDir` reads the configured site environment name and fallbacks. Current `_inspect_source_closure` instead constructs one path from `FOAM_ETC`. The mismatch therefore has a concrete native mechanism; it is not inferred solely from filenames.
- Dependency-screening consequences follow because screening reads a different file from native evaluation. This review did not run an executable payload and makes no claim that one was observed executing.
- Canonical comparison needs a declared value type and runtime representation. This one scalar counterexample does not justify generic coercion of arbitrary words, dimensions, vectors or nested lists, or an unbounded floating-point tolerance.

## Recommended changes to roadmap gates

1. Add O3 to G0 and the first OpenFOAM repair batch beside F1. The exit test must traverse composed/public capability → exact environment → prepared mutation → native readback → transaction outcome. Include numeric-equivalent and genuinely different values; distinguish missing evidence from verified equality.
2. Keep F2 as a prerequisite for claiming complete dependency evidence. Until actual precedence can be established safely for a supported runtime, return unresolved for `includeEtc`; do not replace one guessed path with a guessed expanded search list.
3. Test environment-sensitive and negative lookup dependencies. Creation of a previously absent higher-precedence user/site file must invalidate a prior resolution. Record relevant runtime/build identity and source/environment inputs, not merely the installed vendor root.
4. Define required verification policy explicitly. An empty result cannot establish that all required targets were checked. Tests should include a provider emitting partial records, runtime unavailability, unsupported comparisons, and successful optional offline inspection.
5. Separate helper rollback from caller transaction rollback in G2. Inject effective-check failure after a successful write, verify restoration through the public operation, and retain the roadmap's interrupted-journal and stale-input gates.
6. Keep numerical-control/default discovery bounded by source/build and evidence origin. Nothing in these reproductions warrants moving solver meaning or domain recommendations into the OpenFOAM package.

No production source, existing cases, or user WIP was edited. No broad test suite or complete native solver run was performed. This review adds only this report; the lead's wider tests and other findings were not independently repeated here.
