# omniDriver — Key Files Reference

Quick navigational map for every reader type. All paths are relative to the
repository root.

> **Corrected 2026-09-03.** Every path in this file named the pre-package-split
> layout (`applications/scripts/driverFoam/openfoam_driver/…`), which exists
> nowhere in this repository — following any of them failed immediately. They
> now name real, verified locations under `packages/`. A navigational map with
> stale paths is worse than no map, so this was the highest-severity item in
> the 2026-09-03 documentation audit. Note `postprocess_phase.py` also *moved*,
> from `postprocessing/` to `core/runtime/`; it was not merely renamed.

---

## For Core Maintainers

| File | Role |
|---|---|
| `packages/omnidriver/src/omnidriver/core/plugin_interface.py` | **Start here.** Defines `SolverPlugin` (the single 27-member contract), `SolverPluginOptionalHooks`, `DriverContext`, and `validate_plugin()`. |
| `packages/omnidriver/src/omnidriver/core/plugin_capabilities.py` | 17 capability Protocol classes + adapter dataclasses + `adapt_plugin_capabilities()`. Every plugin capability seam is documented here. |
| `packages/omnidriver/src/omnidriver/core/compatibility.py` | Backward-compatibility shims for optional-hook capabilities: cardiac-shaped fallbacks for the built-in cardiac plugin, neutral fallbacks for every other plugin. |
| `packages/omnidriver/src/omnidriver/core/plugin_discovery.py` | Entry-point discovery via `importlib.metadata`. Explains `omnidriver.plugins` group name, ambiguity handling, and `_entry_points()` test seam. |
| `packages/omnidriver/src/omnidriver/core/strict_planning.py` | The strict planner: `strict_plan()` / `driverFoam plan --strict`. Non-mutating; produces machine-readable JSON with readiness score, diagnostics, and launch command. |
| `packages/omnidriver/src/omnidriver/cli.py` | `driverFoam` / `driverFoam` CLI entry-point. All public subcommands are here. |
| `ARCHITECTURE.md` | Deep architectural review: layer map, claim discipline, coupling analysis, runtime flow diagrams. Read the package-independence rules and the capability-seam table first. |
| `CHANGELOG.md` | History of contract changes per phase. |

---

## For Plugin Authors

> **New to writing a plugin?** Follow `.agents/skills/driverfoam-plugin-builder/SKILL.md` (**not present in this repository** — it lives in the cardiacFoam monorepo)
> step by step — it contains the complete workflow, a contract cheat-sheet, and a worked example.

| File | Role | Why you must read it |
|---|---|---|
| `packages/omnidriver/src/omnidriver/core/generic_plugin.py` | **Canonical scaffold.** Copy this file as `my_solver_plugin.py`. | Shows every required method with minimal stubs. |
| `packages/omnidriver/src/omnidriver/core/generic-plugin.yaml` | Minimal `plugin.yaml` template. | Documents all valid `kind`, `role`, `required` values inline. |
| `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/plugin.yaml` | Full `plugin.yaml` example. | Shows `cxx_mapping`, `reviewed_allowlist`, real dictionary list. |
| `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/cardiacfoam_plugin.py` | Full plugin reference (428 lines). | Shows all method signatures, `@lru_cache`, `@staticmethod get_profile()`, catalog patterns. |
| `packages/omnidriver/src/omnidriver/core/contracts/dictionary.py` | `DictEntry` dataclass — the vocabulary unit. | Every dictionary key your solver reads must be a `DictEntry`. |
| `packages/omnidriver/src/omnidriver/core/contracts/dictionary_catalog.py` | `DictionaryCatalog` — immutable partitioned store. | Return from `get_dictionary_catalog()`; validates uniqueness at construction. |
| `pyproject.toml` | Entry-point registration. | You must add your plugin under `[project.entry-points."omnidriver.plugins"]`. |
| `packages/omnidriver/src/omnidriver/core/plugin_interface.py` | Full contract definition. | Read `SolverPlugin` and `SolverPluginOptionalHooks`. |

### Plugin Contract Quick Reference

**Required (27 members — all plugins)**

| Member | Returns |
|---|---|
| `plugin_name` | `str` — human display name |
| `plugin_id` | `str` — reverse-DNS id, matches `plugin.yaml` |
| `plugin_version` | `str` — plugin semantics version |
| `plugin_api_version` | `str` — `"2"`, the only supported contract version |
| `get_profile()` | `PluginProfile` loaded from `plugin.yaml` |
| `get_dict_entries()` | `tuple[DictEntry, ...]` — flat; unique `driver_path` |
| `get_dictionary_catalog()` | `DictionaryCatalog` — entries by document name |
| `get_dict_groups()` | `dict[str, tuple[DictEntry, ...]]` — by logical group |
| `get_capabilities()` | `CapabilityManifest` — call `build_capability_manifest()` |
| `get_tutorial_catalog()` | `dict` with `spec_factories`, `registered_tutorials` |
| `get_tutorial_displays()` | `tuple[TutorialDisplay, ...]` — UI cards |
| `validate_configuration(spec)` | `tuple[StrictDiagnostic, ...]` — plan-time checks |
| `validate_run_semantics(context)` | `tuple[...]` — execution-time checks |
| `predict_data_artifacts(case_root, spec)` | `tuple[DataArtifact, ...]` — never raise |
| `get_solver_commands()` | `frozenset[str]` — artifact-producing binaries |
| `get_auxiliary_commands()` | `frozenset[str]` — meshers, decomposers |
| `get_utility_manifests()` | `dict[str, Any]` — per-utility pre-flight declarations |
| `get_utility_roots()` | `tuple[Path, ...]` — utility source dirs |
| `resolve_case_models(case_root)` | `dict` — best-effort, never raise |
| `get_samplable_fields(resolved)` | `dict[str, tuple[str, ...]]` — by region |
| `get_override_schema(tutorial, info)` | `dict` — `--config` vocabulary |
| `get_run_document_config_schema()` | `dict` — JSON Schema for `RunDocument.config` |
| `get_dict_entry_catalog()` | `dict` — entries by document name (unserialized) |
| `get_solve_step_commands()` | `frozenset[str]` — for telemetry attribution |
| `get_telemetry_source_globs(command)` | `tuple[str, ...]` — solver log locations |
| `get_extra_provenance_paths(case_root)` | `tuple[RuntimeDependency, ...]` |
| `get_artifact_value_reader(format)` | `Any | None` |

**Key Optional Hooks (`SolverPluginOptionalHooks` — probed with `getattr`)**

| Hook | If absent | Unlocks |
|---|---|---|
| `route_sweep_case_values(...)` | **Sweeps refused** | `driverFoam sweep-run` |
| `materialize_sweep_case(...)` | **Sweeps refused** | `driverFoam sweep-run` |
| `has_case_marker(case_root)` | `False` | Case auto-detection |
| `is_nondimensional_case(spec)` | `False` (diagnostics on) | Skip SI mesh checks |
| `get_mesh_geometry_diagnostics(case_root)` | `()` | Custom geometry checks |
| `build_run_document_config(spec)` | `({}, ())` | RunDocument config builder |
| `get_override_scopes()` | `()` | `--apply` patch overrides |
| `get_regeneration_scopes()` | `()` | `--apply` regenerating overrides |
| `get_report_catalog()` | `()` | Post-run report listing |
| `get_named_catalogs()` | `{}` | `describe` plugin catalogs |

---

## For AI Agents and Operators

| File | Role |
|---|---|
| `AGENT_GUIDE.md` | Full agent CLI reference: `driverFoam` commands, RunDocument, sweeps, post-processing, PLUGIN_GUIDE section. |
| `.agents/skills/driverfoam-assistant/SKILL.md` (**not present in this repository** — it lives in the cardiacFoam monorepo) | Agent workflow skill: case scaffolding, sweep generation, strict diagnostics loop, post-processing. |
| `.agents/skills/driverfoam-plugin-builder/SKILL.md` (**not present in this repository** — it lives in the cardiacFoam monorepo) | **Plugin builder skill:** complete step-by-step guide for integrating a new solver. |

### Environment Variables

| Variable | Purpose |
|---|---|
| `DRIVERFOAM_ALLOWED_RUNS_ROOT` | Restrict where `--fresh` may delete; recommended in production. |
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
| `packages/omnidriver/src/omnidriver/postprocessing/__init__.py` | Public surface: `PostprocessingProtocol`, `PlotSpec`, `TraceSpec`, `build_line_traces`, `load_csv_folder`, `apply_plotly_layout`, `write_plotly_html`, `DEFAULT_PALETTE`. |
| `packages/omnidriver/src/omnidriver/core/runtime/postprocess_phase.py` | `build_sweep_context()` (brain) and `run_postprocessing_module()`. The brain is the single source of truth; the module never re-reads manifests. |
| Tutorial `run_postprocessing` scripts | Expose `run_postprocessing(*, output_dir, setup_root=None, **kwargs) -> list[dict]`. Discovery is driven by the function's docstring. |

See `AGENT_GUIDE.md §5 Post-Processing Phase` for the full protocol.

---

*This file is a navigational aid. For authoritative contracts see the source files linked above.*
