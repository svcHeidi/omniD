# omniDriver — Key Files Reference

Quick navigational map for every reader type. All paths are relative to the
repository root.

---

## For Core Maintainers

| File | Role |
|---|---|
| `packages/omnidriver/src/omnidriver/core/plugin_interface.py` | **Start here.** `SolverPlugin` (the contract, member by member; only the identity is required), `DriverContext`, `validate_plugin()` and `driver_context()`. |
| `packages/omnidriver/src/omnidriver/core/provider_stack.py` | `MEMBERS`, the one table of the contract: each member's composition across providers and the stack's answer when none implements it (empty, or a refusal naming the operation). `ProviderStack.call(member, ...)` is how core reaches a plugin. |
| `packages/omnidriver/src/omnidriver/core/plugin_discovery.py` | Entry-point discovery via `importlib.metadata`. Explains `omnidriver.plugins` group name, ambiguity handling, and `_entry_points()` test seam. |
| `packages/omnidriver/src/omnidriver/core/strict_planning.py` | The strict planner: `strict_plan()` / `omnidriver plan --strict`. Stages a copy of the record's case under the scratch root and never writes the native case; produces machine-readable JSON with readiness score, diagnostics (including the stack's `plugin_diagnostics`), and launch command. |
| `packages/omnidriver/src/omnidriver/core/runtime_records.py` | `CORE_RUNTIME_RECORDS` — every filename/directory core itself writes into a case (`workflow_state.json`, `run_document.json`, `sweep_manifest.json`, `case_record.json`, `workflow_logs/`, ...), merged into every stack's `CaseRuntimeConventions` so staging never carries a prior run's state forward (conformance C11). |
| `packages/omnidriver/src/omnidriver/core/quantities/` | Solver-neutral `Quantity` record, unit table, sentinel handling, the `get_artifact_value_reader` reader contract, and `comparison.py`'s agent-stated-pairs comparison behind `omnidriver compare`. |
| `packages/omnidriver/src/omnidriver/cli.py` | `omnidriver` CLI entry-point (`pyproject.toml`'s `[project.scripts]` names the installed binary). All public subcommands, and the stack selection (`--plugin`, `--repo`), are here. |
| `packages/omnidriver/src/omnidriver/core/repository.py` | `read_repository()` / `repository_of_cases_root()`: a solver repository's `omnidriver.toml` (`plugin`, `tutorials`, `source`, `scripts`), read only from a supplied place. |
| `packages/omnidriver/src/omnidriver/core/tutorial_records.py` | `TutorialRecord` and the record study contract; `case_folder_record()` builds the ad hoc one-step record `--case` runs. |
| `benchmarks/` | Published, solver-neutral reference definitions (e.g. `niederer2011.json`) a comparison request cites by id; `scripts/check-benchmark-references.py` gates them. |
| `ARCHITECTURE.md` | The layer map, the package-independence rules and "Provider composition". |

---

## For Plugin Authors

> **New to writing a plugin?** Read `AGENT_GUIDE.md`, "Plugin Guide": the contract table and a minimal plugin that is tested against the code.

| File | Role | Why you must read it |
|---|---|---|
| `packages/omnidriver-openfoam/src/omnidriver/openfoam/environment.py` (`OpenFOAMEnvironmentPlugin`) | Closest in-repo example of a plugin with no domain-specific semantics. Not a copy-and-fill scaffold. | Shows every required method actually implemented, with no cardiac vocabulary. |
| `packages/omnidriver-openfoam/src/omnidriver/openfoam/openfoam-environment.yaml` | Real `plugin.yaml` for the plugin above. | Documents a working, minimal manifest. |
| `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/plugin.yaml` | Full `plugin.yaml` example. | Shows `cxx_mapping`, `reviewed_allowlist`, real dictionary list. |
| `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/cardiacfoam_plugin.py` | Full plugin reference. | Shows all method signatures, `@lru_cache`, `@staticmethod get_profile()`, catalog patterns. |
| `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/physics_layout.py`/`.json` | Which region(s) a case's physics type declares (single-region vs. region-split, and each region's role), one row per type, read from the case rather than exempted by tutorial name. | The single source of truth for "which `constant/electroProperties`-shaped document does this case use"; a case with no `physicsProperties` still resolves, it does not raise. |
| `packages/omnidriver/src/omnidriver/core/contracts/dictionary.py` | `DictEntry` dataclass — the vocabulary unit. | Every dictionary key your solver reads must be a `DictEntry`. |
| `packages/omnidriver/src/omnidriver/core/contracts/dictionary_catalog.py` | `DictionaryCatalog` — immutable partitioned store. | Return from `get_dictionary_catalog()`; validates uniqueness at construction. |
| `packages/omnidriver-opencarp/pyproject.toml` | Entry-point registration, one per package. | Your package adds its plugin under `[project.entry-points."omnidriver.plugins"]`. |
| `packages/omnidriver/src/omnidriver/core/plugin_interface.py` | Full contract definition. | Read `SolverPlugin`; only its identity is required. |

### Plugin Contract Quick Reference

Only the identity is required (`plugin_name`, `plugin_id`, `plugin_version`,
`plugin_api_version`). Which members each operation needs, and what a stack
answers without them, is the table in `AGENT_GUIDE.md`, "Plugin Guide"; `provider_stack.MEMBERS` is the authority.

---

## For AI Agents and Operators

| File | Role |
|---|---|
| `AGENT_GUIDE.md` | Agent CLI reference: `omnidriver` commands, stack selection, RunDocument, case folders, sweeps, post-processing, plugin guide. |

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
| `packages/omnidriver/src/omnidriver/postprocessing/__init__.py` | Generic plotting and table helpers (`style`, `plotting_common`, `table_writer`) that the native post-processing scripts import directly (`omnidriver.postprocessing`); core's own plan/run/sweep-run path never imports it. |
| `packages/omnidriver/src/omnidriver/core/runtime/postprocess_phase.py` | `build_sweep_context()` (brain, the single source of truth for a sweep result's context) and `run_postprocessing_module()`, which always refuses (`not_configured`) rather than guessing an undeclared generic analysis task. |

See `AGENT_GUIDE.md`'s "Post-processing phase" section for the full protocol.

---

*This file is a navigational aid. For authoritative contracts see the source files linked above.*
