# omniDriver — Key Files Reference

Quick navigational map for every reader type. All paths are relative to the
repository root.

---

## For Core Maintainers

| File | Role |
|---|---|
| `packages/omnidriver/src/omnidriver/core/plugin_interface.py` | **Start here.** Defines `SolverPlugin`, `SolverPluginOptionalHooks` (the probe-based hooks), `DriverContext`, and `validate_plugin()`. |
| `packages/omnidriver/src/omnidriver/core/plugin_capabilities.py` | The capability Protocol classes (`ARCHITECTURE.md`'s capability-seam table is generated from them and CI-verified by `scripts/export-capability-seams.py --check`; treat it as the authority) + adapter dataclasses + `adapt_plugin_capabilities()`. Every plugin capability seam is documented here. |
| `packages/omnidriver/src/omnidriver/core/compatibility.py` | The `absent_*` answers core gives for optional-hook capabilities a plugin does not implement -- neutral fallbacks, not plugin-specific ones. |
| `packages/omnidriver/src/omnidriver/core/plugin_discovery.py` | Entry-point discovery via `importlib.metadata`. Explains `omnidriver.plugins` group name, ambiguity handling, and `_entry_points()` test seam. |
| `packages/omnidriver/src/omnidriver/core/strict_planning.py` | The strict planner: `strict_plan()` / `omnidriver plan --strict`. Stages a copy of the record's case under the scratch root and never writes the native case; produces machine-readable JSON with readiness score, diagnostics (including the stack's `plugin_diagnostics`), and launch command. |
| `packages/omnidriver/src/omnidriver/core/runtime_records.py` | `CORE_RUNTIME_RECORDS` — every filename/directory core itself writes into a case (`workflow_state.json`, `run_document.json`, `sweep_manifest.json`, `case_record.json`, `workflow_logs/`, ...), merged into every stack's `CaseRuntimeConventions` so staging never carries a prior run's state forward (conformance C11). |
| `packages/omnidriver/src/omnidriver/core/quantities/` | Solver-neutral `Quantity` record, unit table, sentinel handling, the `artifact_value_reader` reader contract, and `comparison.py`'s agent-stated-pairs comparison behind `omnidriver compare`. |
| `packages/omnidriver/src/omnidriver/cli.py` | `omnidriver` CLI entry-point (`pyproject.toml`'s `[project.scripts]` names the installed binary). All public subcommands, and the stack selection (`--plugin`, `--repo`), are here. |
| `packages/omnidriver/src/omnidriver/core/repository.py` | `read_repository()` / `repository_of_cases_root()`: a solver repository's `omnidriver.toml` (`plugin`, `tutorials`, `source`, `scripts`), read only from a supplied place. |
| `packages/omnidriver/src/omnidriver/core/tutorial_records.py` | `TutorialRecord` and the record study contract; `case_folder_record()` builds the ad hoc one-step record `--case` runs. |
| `benchmarks/` | Published, solver-neutral reference definitions (e.g. `niederer2011.json`) a comparison request cites by id; `scripts/check-benchmark-references.py` gates them. |
| `ARCHITECTURE.md` | Deep architectural review: layer map, claim discipline, coupling analysis, runtime flow diagrams. Read the package-independence rules and the capability-seam table first. |
| `CHANGELOG.md` | History of contract changes per phase. |

---

## For Plugin Authors

> **New to writing a plugin?** Follow `.agents/skills/omnidriver-plugin-builder/SKILL.md` (**not present in this repository** — it lives in the cardiacFoam monorepo)
> step by step — it contains the complete workflow, a contract cheat-sheet, and a worked example.

| File | Role | Why you must read it |
|---|---|---|
| `packages/omnidriver-openfoam/src/omnidriver/openfoam/environment.py` (`OpenFOAMEnvironmentPlugin`) | Closest in-repo example of a plugin with no domain-specific semantics. Not a copy-and-fill scaffold. | Shows every required method actually implemented, with no cardiac vocabulary. |
| `packages/omnidriver-openfoam/src/omnidriver/openfoam/openfoam-environment.yaml` | Real `plugin.yaml` for the plugin above. | Documents a working, minimal manifest. |
| `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/plugin.yaml` | Full `plugin.yaml` example. | Shows `cxx_mapping`, `reviewed_allowlist`, real dictionary list. |
| `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/cardiacfoam_plugin.py` | Full plugin reference. | Shows all method signatures, `@lru_cache`, `@staticmethod get_profile()`, catalog patterns. |
| `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/physics_layout.py`/`.json` | Which region(s) a case's physics type declares (single-region vs. region-split, and each region's role), one row per type, read from the case rather than exempted by tutorial name. | The single source of truth for "which `constant/electroProperties`-shaped document does this case use"; a case with no `physicsProperties` still resolves, it does not raise. |
| `packages/omnidriver/src/omnidriver/core/contracts/dictionary.py` | `DictEntry` dataclass — the vocabulary unit. | Every dictionary key your solver reads must be a `DictEntry`. |
| `packages/omnidriver/src/omnidriver/core/contracts/dictionary_catalog.py` | `DictionaryCatalog` — immutable partitioned store. | Return from `get_dictionary_catalog()`; validates uniqueness at construction. |
| `pyproject.toml` | Entry-point registration. | You must add your plugin under `[project.entry-points."omnidriver.plugins"]`. |
| `packages/omnidriver/src/omnidriver/core/plugin_interface.py` | Full contract definition. | Read `SolverPlugin` and `SolverPluginOptionalHooks`. |

### Plugin Contract Quick Reference

**Required (`validate_plugin` rejects a plugin lacking any)**

| Member | Returns |
|---|---|
| `plugin_name` | `str` — human display name |
| `plugin_id` | `str` — reverse-DNS id, matches `plugin.yaml` |
| `plugin_version` | `str` — plugin semantics version |
| `plugin_api_version` | `str` — `"2"`, the only supported contract version |
| `get_profile()` | `PluginProfile` loaded from `plugin.yaml` |
| `get_capabilities()` | `CapabilityManifest` — call `build_capability_manifest()` |
| `validate_configuration(spec)` | `tuple[StrictDiagnostic, ...]` — plan-time checks |
| `validate_run_semantics(context)` | `tuple[...]` — execution-time checks |
| `predict_data_artifacts(case_root, spec)` | `tuple[DataArtifact, ...]` — never raise |

**Optional members commonly implemented (probed with `getattr`; absent, each answers a neutral value or refuses by name)**

| Member | Returns |
|---|---|
| `get_solver_commands()` | `frozenset[str]` — artifact-producing binaries |
| `get_auxiliary_commands()` | `frozenset[str]` — meshers, decomposers |
| `get_environment_commands()` | `frozenset[str]` — optional static commands supplied by the execution environment |
| `is_installed_environment_command(command)` | `bool` — runtime lookup for an environment-provided application |
| `get_utility_manifests()` | `dict[str, Any]` — per-utility pre-flight declarations |
| `get_utility_roots()` | `tuple[Path, ...]` — utility source dirs |
| `resolve_case_models(case_root)` | `dict` — best-effort, never raise |
| `get_samplable_fields(resolved)` | `dict[str, tuple[str, ...]]` — by region |
| `get_dict_entries()` / `get_dictionary_catalog()` / `get_dict_groups()` | the dictionary vocabulary; a plugin without dictionaries omits them |
| `get_dict_entry_catalog()` | `dict` — entries by document name (unserialized) |
| `get_solve_step_commands()` | `frozenset[str]` — for telemetry attribution |
| `get_telemetry_source_globs(command)` | `tuple[str, ...]` — solver log locations |
| `get_extra_provenance_paths(case_root)` | `tuple[RuntimeDependency, ...]` |
| `get_artifact_value_reader(format)` | `Any | None` |

**Key optional hooks (`SolverPluginOptionalHooks`)**

| Hook | If absent | Unlocks |
|---|---|---|
| `get_tutorial_records()` | `--entry` refuses every name | Records for `describe`/`plan`/`run`/`sweep-run` |
| `get_plan_diagnostics(...)` | `()` | The stack's own checks in a strict plan's `plugin_diagnostics` |
| `get_case_runtime_conventions()` | neutral declaration | `case_entrypoints`: the file `--case` runs |
| `get_parallel_steps(...)` | `parallel` refused by name | `--parallel` / the `parallel` study value |
| `get_override_scopes()` | `()` | `--apply` patch overrides |
| `get_regeneration_scopes()` | `()` | `--apply` regenerating overrides |
| `get_report_catalog()` | `()` | Post-run report listing |
| `get_named_catalogs()` | `{}` | `describe` plugin catalogs |

---

## For AI Agents and Operators

| File | Role |
|---|---|
| `AGENT_GUIDE.md` | Agent CLI reference: `omnidriver` commands, stack selection, RunDocument, case folders, sweeps, post-processing, plugin guide. |
| `.agents/skills/omnidriver-assistant/SKILL.md` (**not present in this repository** — it lives in the cardiacFoam monorepo) | Agent workflow skill: case scaffolding, sweep generation, strict diagnostics loop, post-processing. |
| `.agents/skills/omnidriver-plugin-builder/SKILL.md` (**not present in this repository** — it lives in the cardiacFoam monorepo) | **Plugin builder skill:** complete step-by-step guide for integrating a new solver. |

### Environment Variables

| Variable | Purpose |
|---|---|
| `OMNIDRIVER_ALLOWED_RUNS_ROOT` | Restrict where `--fresh` may delete and where a run document's `caseRoot`/`outputDir` may resolve; recommended in production. |
| `OMNIDRIVER_SCRATCH_DIR` | The scratch root a staging command writes under, when `--scratch-dir` is not given. No default. |
| `OMNIDRIVER_CASES_ROOT` | The cases root when `--cases-root` is not given; a repository's tutorials folder selects that repository. |
| `FOAM_APPBIN` | Standard OpenFOAM binary path; required for environment preflight. |
| `FOAM_USER_APPBIN` | User-compiled binary path; also checked during preflight. |
| `WM_PROJECT_DIR` | OpenFOAM installation root; sourced by `etc/bashrc`. |

### Common Troubleshooting

**Plugin not found (`KeyError: 'mysolver'`)**

```bash
# Verify the entry-point is registered under the exact group name:
python -c "from importlib.metadata import entry_points; print(list(entry_points(group='omnidriver.plugins')))"
```

**Profile id mismatch (`TypeError: SolverPlugin profile id does not match plugin_id`)**
Check that `plugin_id` property and `plugin.yaml → plugin.id` are identical strings.

**Duplicate `driver_path` (`TypeError: duplicate paths`)**
Each `DictEntry.driver_path` must be globally unique across your entire catalog.

---

## For Post-Processing Authors

| File | Role |
|---|---|
| `packages/omnidriver/src/omnidriver/postprocessing/__init__.py` | Plotting and table utilities (`PostprocessingProtocol`, `PlotSpec`, `TraceSpec`, `build_line_traces`, `load_csv_folder`, `apply_plotly_layout`, `write_plotly_html`, `DEFAULT_PALETTE`, `TableWriter`) that the native cardiacFOAM post-processing scripts import directly (`omnidriver.postprocessing`); core's own plan/run/sweep-run path never imports it. |
| `packages/omnidriver/src/omnidriver/core/runtime/postprocess_phase.py` | `build_sweep_context()` (brain, the single source of truth for a sweep result's context) and `run_postprocessing_module()`, which always refuses (`not_configured`) rather than guessing an undeclared generic analysis task. |

See `AGENT_GUIDE.md`'s "Post-processing phase" section for the full protocol.

---

*This file is a navigational aid. For authoritative contracts see the source files linked above.*
