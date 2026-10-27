# TorchCor plugin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** omniD drives TorchCor's N-version benchmark end to end (plan, run, sweep, check, compare), making TorchCor the third solver on `benchmarks/niederer2011.json` and the first with no input file, no binary and no MPI.

**Architecture:** A solver-side repository `~/torchcor-cases` holds the case (`case.json`) and the runner (`scripts/run_case.py`), which runs in the TorchCor venv and imports only TorchCor, numpy, pygmsh and the standard library. The runner describes its own keys (`--describe`), so the plugin's catalogue comes from the solver's interpreter, never from omniD. `packages/omnidriver-torchcor` depends on core only: a JSON case-document writer, the `nversion` record, the catalogue read from `--describe`, validation, a nearest-node activation reader, and a conformance study.

**Tech Stack:** Python ≥3.11; TorchCor `b02daee` (MIT) in `~/torchcor-venv` (torch 2.14.1, CPU); pytest.

**Evidence:** `docs/solver-learning/torchcor.md` (probes A–F); spec `docs/superpowers/specs/2026-10-09-torchcor-plugin-design.md`.

## Global Constraints

- `omnidriver-torchcor` imports only `omnidriver.core` (and `omnidriver.conformance` types); no other adapter, and no adapter imports it. Enforced in `scripts/check-import-boundaries.py`.
- No omniD code runs in the TorchCor interpreter; the venv never needs omniD.
- No pytest test runs TorchCor. Plugin tests use committed fixtures: a real `--describe` output and a real `activation_times.dat`, both produced by the runner and committed verbatim (a fixture is real output, never invented).
- Owner decisions (2026-10-09): `et = 0.24` (the benchmark), TorchCor's `0.2` noted in the case; `source` is a git submodule of TorchCor pinned at `b02daee`, installed editable into the venv from there; licence MIT.
- Values in `case.json` each cite their source line (`verification/benchmark.py` at `b02daee`, or the benchmark paper for `et`).
- House style per `CLAUDE.md`. Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Venv for this worktree: `/tmp/od-torchcor` with all packages editable from `/Users/simaocastro/omnidriver/.claude/worktrees/torchcor` (core, openfoam, cardiacfoam, cardiacsubstrate, opencarp, torchcor). Confirm `omnidriver.core.__file__` resolves into the worktree.
- Verification after every omniD task: package tests, then whole repo `-m "not slow"`, core alone, the wheel shape and all four static gates (`CLAUDE.md` "How to verify anything"): 0 failed.

## Files

```
~/torchcor-cases/                     (a new git repository; not omniD)
  omnidriver.toml                     plugin = "torchcor", tutorials = "cases", source = "torchcor", scripts = "scripts"
  torchcor/                           git submodule, github.com/sagebei/torchcor at b02daee
  scripts/run_case.py                 the runner; --describe prints its catalogue
  cases/nversion/case.json, README.md
  README.md                           install recipe (venv from the submodule)

packages/omnidriver-torchcor/
  pyproject.toml
  src/omnidriver/torchcor/
    __init__.py
    torchcor.yaml                     identity, environment (TORCHCOR_VENV), no mpi_launcher
    plugin.py                         TorchCorPlugin
    case_json.py                      read/patch/format a case.json document
    catalog.py                        run --describe, cache by digest, Catalog
    validation.py                     record_key_validator, case_diagnostics
    activation_reader.py              ACTIVATION_FORMAT, NearestNodeReader
    environment.py                    torchcor_environment_diagnostics (venv, device)
    records/__init__.py, records/nversion.py
    conformance_studies.py
  tests/
    fixtures/describe.json            committed verbatim from run_case.py --describe
    fixtures/activation_times.dat     committed verbatim from a dx 0.5 run (the whole file, about 3.7k lines)
    test_case_json.py test_catalog.py test_validation.py test_activation_reader.py
    test_environment.py test_plugin_contract.py test_layer_ownership.py
```

---

### Task 1: The solver-side repository and the runner (outside omniD)

**Files:** everything under `~/torchcor-cases/`.

**Interfaces:**
- Produces: `python3 scripts/run_case.py <case.json>` writes, beside `case.json` (the staged case root): `out/activation_times.dat` (first line: node count; then one line per node `x_mm y_mm z_mm t_ms`, `t_ms` = `-1` when never activated, six decimals), `out/run_info.json` (`torchcor_version`, `torchcor_commit` from `git -C <torchcor package dir> rev-parse HEAD` or null, `torch_version`, `device`, `dtype`, `threads` = `torch.get_num_threads()`, `nodes`, `steps`, `setup_s`, `solve_s`), `mesh/slab.{pts,elem,lon}` and `stim.vtx`. Exit non-zero, message on stderr, for any refused value.
- Produces: `python3 scripts/run_case.py --describe` prints one JSON object: `{"keys": {<key>: {"kind": "scalar"|"integer"|"string"|"boolean"|"vector"|"mapping", "unit": str|null, "description": str, "default": any|null, "minimum": num|null, "maximum": num|null, "menu": [..]|null, "required": bool}}, "ionic_models": {<name>: {"options": {<param>: {"default": .., "menu": [..]|null}}, "init": [<attribute names ending _init>]}}, "devices": ["cpu", ...], "torchcor": {"version": .., "commit": ..}}`. Menus: `ionic_model` from `torchcor.ionic.__all__`; `cell_type` from the literals compared in that model's source (as B4 found: EPI, MCELL, ENDO for TTP), read by `ast` from `inspect.getsource`; `init` from the attributes of an instance ending in `_init`; `devices`: `cpu`, plus `cuda` when `torch.cuda.is_available()`, plus `mps` only if a 1-node sparse CSR conversion succeeds on it (D12).

- [ ] **Step 1:** `git init ~/torchcor-cases`; `git -C ~/torchcor-cases submodule add https://github.com/sagebei/torchcor torchcor`; check out `b02daee`. Reinstall the venv from it: `rm -rf ~/torchcor-venv && uv venv --python 3.11 ~/torchcor-venv && VIRTUAL_ENV=~/torchcor-venv uv pip install -e ~/torchcor-cases/torchcor`. Confirm `~/torchcor-venv/bin/python -c "import torchcor; print(torchcor.__file__)"` is inside the submodule (settles F1).
- [ ] **Step 2:** Write `scripts/run_case.py` from the verified step-loop probe (`~/omnid-runs/2026-10-09/torchcor/d11_library_step_loop/run_library.py`, D10): every hard-coded value becomes a `case.json` key from the table in `docs/solver-learning/torchcor.md` §E; keys and their kinds/units/descriptions are one `KEYS` dict at the top of the script, the only place they are declared, used both to validate `case.json` (unknown key → refuse; missing required → refuse; wrong kind → refuse) and to print `--describe`. `ionic_init` keys must be attributes of the model instance (refuse otherwise, B6). `stimulus.box_mm` selects nodes with all coordinates within the box, as D5. Points for the output are all nodes. Use `assemble()`/`step()`, not `solve()` (D10). Set `theta` as an attribute (B8).
- [ ] **Step 3:** Write `cases/nversion/case.json` with the §E values, except `conductivity_S_per_m.et = 0.24`; a `"_sources"` key is NOT allowed (unknown keys are refused) — the citations go in `cases/nversion/README.md` as a table key → value → source line, including the line "`et`: 0.24 per Niederer et al. 2011; TorchCor's `verification/benchmark.py` l. 231 uses 0.2, a likely typo (F6)". `omnidriver.toml` as in Files. Top-level `README.md`: the install recipe from Step 1.
- [ ] **Step 4: Real run.** `cd /tmp/x && cp -r ~/torchcor-cases/cases/nversion . && ~/torchcor-venv/bin/python ~/torchcor-cases/scripts/run_case.py nversion/case.json`. Expect exit 0, P1 ≈ 0.955 ms and P8 near 40.4 ms at dx 0.5 (the step-loop convention; the exact P8 moves with `et` 0.24, so record it, don't assert it). Log the run as a new probe in `docs/solver-learning/torchcor.md` (G1) in the omniD worktree. Run `--describe` and save it.
- [ ] **Step 5:** Refusal probes: an unknown key, `ionic_init` with a misspelt attribute, `cell_type: "EPIC"`, `device: "mps"` → each exits non-zero naming the key. Log as G2.
- [ ] **Step 6:** Commit in `~/torchcor-cases` (`git add -A && git commit`). Copy the `--describe` output and the run's `out/activation_times.dat` verbatim into `packages/omnidriver-torchcor/tests/fixtures/` in the omniD worktree (Task 2 commits them).

### Task 2: Package skeleton, manifest, boundaries

**Files:** `packages/omnidriver-torchcor/pyproject.toml`, `src/omnidriver/torchcor/{__init__.py,torchcor.yaml,plugin.py}`, `tests/test_layer_ownership.py`, `tests/fixtures/*`; modify `scripts/check-import-boundaries.py`, `.github/workflows/ci.yml`, root `pyproject.toml` (pytest `pythonpath`), `packages/omnidriver/tests/core/test_no_pre_migration_imports.py` (the package list), `CLAUDE.md` (venv recipes and the package table: a row for `omnidriver-torchcor`: may know TorchCor, its runner and case.json; must not know OpenFOAM, openCARP).

**Interfaces:**
- Produces: entry point `[project.entry-points."omnidriver.plugins"] torchcor = "omnidriver.torchcor.plugin:TorchCorPlugin"`; `TorchCorPlugin` with `plugin_name = "TorchCor"`, `plugin_id = "org.omnidriver.torchcor"`, `plugin_version = "0.1.0"`, `plugin_api_version = "3"`, `get_profile()`.

`torchcor.yaml`:

```yaml
# TorchCor is its own environment and solver: no requires, no MPI.
schema_version: 1
plugin:
  id: org.omnidriver.torchcor
  api_version: "3"
case_profile:
  dictionaries: []
environment:
  supplied:
    - name: TORCHCOR_VENV
      required: true
      why: the venv TorchCor is installed in (from the solver repository's submodule); its bin goes first on PATH, so a record's python3 is TorchCor's (docs/solver-learning/torchcor.md A1)
  path_prepend:
    - TORCHCOR_VENV_BIN
```

`path_prepend` takes variable names whose value is a directory; check how `core/environment_connection.py` renders `path_prepend` (openCARP prepends `OPENCARP_MPI_BIN` itself). If it cannot take `$TORCHCOR_VENV/bin`, declare the supplied variable as `TORCHCOR_BIN` (the venv's `bin`) instead — do not add a core feature for it.

- [ ] Steps: boundary rule in `adapter_rules` (`TORCHCOR_SRC: ("foamlib", "omnidriver.openfoam", "omnidriver.cardiacfoam", "omnidriver.cardiacsubstrate", "omnidriver.opencarp")`, and add `"omnidriver.torchcor"` to every other adapter's forbidden tuple); `test_layer_ownership.py` mirroring openCARP's; CI job copying `test-opencarp`; guards updated; gates + whole repo green; commit.

### Task 3: The case.json document writer

**Files:** `case_json.py`, `tests/test_case_json.py`; `plugin.py` gains `get_supported_mutation_modes` (`{"clone_and_patch"}`), `get_rendered_formats` (`{"torchcor_case_json"}`), `resolve_case_mutation`, `render_case_files`, `get_config_value_reader`, `get_case_value_comparator`, mirroring `omnidriver/opencarp/plugin.py` member for member.

**Interfaces:**
- Produces: `read_value(text: str, key: str) -> Any | None` (dotted key into nested objects; `None` when absent); `patch(text: str, values: dict[str, Any]) -> str` (sets dotted keys, creating no new top-level key the document lacks — refuse with `CaseJsonError` naming it; output `json.dumps(indent=2) + "\n"`, key order preserved); `values_agree(a, b) -> bool` (numbers compared as floats exactly, others by equality); `CaseJsonError(ValueError)`.

- [ ] Tests first: read nested; patch nested scalar; patch preserves order and other keys; patch of an unknown top-level key refused; patch of a list element by index `probe` not supported → refused by name; render produces a `RenderedFile` with `format="torchcor_case_json"`, digest of the before bytes. Implement; commit.

### Task 4: The catalogue from the runner's --describe

**Files:** `catalog.py`, `tests/test_catalog.py`; `plugin.py` gains `get_record_key_catalog`.

**Interfaces:**
- Produces: `describe(repository_scripts: Path, env: Mapping[str, str], scratch_root: Path) -> dict` — runs `python3 <scripts>/run_case.py --describe` with `env` (the stack's environment, so `python3` is TorchCor's), caches the JSON at `<scratch_root>/torchcor-describe/<digest>.json` where digest = SHA-256 over `run_case.py`'s bytes and every `*.py` under the repository's `source` (the submodule), sorted by path. `Catalog.from_describe(data: dict)`; `Catalog.keys` (name → spec), `Catalog.ionic_models`, `Catalog.devices`. When no repository is supplied: `describe` is not called and validation says once `torchcor_runner_not_supplied` (a note, like `plugin_cxx_source_not_supplied`).
- `get_record_key_catalog(case_root)`: one entry per `case.json` key, `source_refs: ["<repository>/scripts/run_case.py --describe"]`.

- [ ] Tests (with `tests/fixtures/describe.json`): catalogue built from the fixture; the digest changes when a source file changes and not when its mtime changes; a cached describe is reused (monkeypatch `subprocess.run` to fail on a second call); describe failure is a refusal naming the command and its stderr. Implement; commit.

### Task 5: Validation before a run

**Files:** `validation.py`, `tests/test_validation.py`; `plugin.py` gains `get_record_key_validator`, `validate_run_semantics`, `get_plan_diagnostics`.

**Rules (each from the catalogue, none invented):** unknown key → error; missing required key → error; kind mismatch → error; value outside `minimum`/`maximum` → error; `ionic_model` not in the menu → error; `ionic_options` key not a parameter of that model, or `cell_type` not in its menu → error; `ionic_init` name not in the model's `init` list → error (B6: TorchCor would accept it silently); `device` not in `devices` → error naming the devices this host has. Each diagnostic names the key and the rule.

- [ ] Tests with the fixture catalogue and a copy of the real `case.json`: one passing case; one test per rule. Implement; commit.

### Task 6: Activation reader

**Files:** `activation_reader.py`, `tests/test_activation_reader.py`; `plugin.py` gains `get_artifact_value_reader`.

**Interfaces:**
- Produces: `ACTIVATION_FORMAT = "torchcor_activation_times"`; `NearestNodeReader` with `value_unit = "ms"`, `sentinels = frozenset({-1.0})`, `sampling_rule = "nearest"`, `coordinate_unit = "mm"`, `takes_points = True`, `read(case_root, artifact, request) -> tuple[RawSample, ...]` (reads `artifact.path_pattern`; for each requested point the nearest node by Euclidean distance; ties broken by lowest node index; the sample carries the node's coordinates so core's `max_sampling_offset` judges distance). Look at `omnidriver.core.quantities` (`RawSample`, `ReadRequest`) and the toy's `ToyNearestRowReader` (`packages/omnidriver/tests/plugins/toy.py`) for the exact `RawSample` fields.

- [ ] Tests with `tests/fixtures/activation_times.dat`: P1 (0,0,0) and P8 (20,7,3) are exact nodes with the run's values; a point between nodes picks the nearest and reports its offset; a malformed count line is refused; `-1` passes through as the sentinel. Implement; commit.

### Task 7: The nversion record, environment and conformance study

**Files:** `records/__init__.py`, `records/nversion.py`, `environment.py`, `conformance_studies.py`, `tests/test_environment.py`, `tests/test_plugin_contract.py`; `plugin.py` gains `get_tutorial_records`, `get_solver_commands` (`frozenset({"python3"})`), `get_environment_diagnostics`, `get_agent_guidance` (a short `guidance.md`: the device, mass lumping changes P8 by 28 ms at dx 0.5 (D14), the compile cache is ambient (D6)).

`records/nversion.py`:

```python
RECORD = TutorialRecord(
    name="nversion",
    native_case_relpath="nversion",
    serial_only=True,
    workflow_steps=(
        WorkflowStep(
            step_id="solve",
            command=("run_case.py", "case.json"),     # a repository script, run under the stack's python3
            consumes=("case.json",),
            produces=("out", ProducedPath("out/activation_times.dat", format=ACTIVATION_FORMAT), "out/run_info.json"),
        ),
    ),
)
```

Check `core/scripts.py` for exactly how a step names a repository script (a bare name, or a prefix) and use that form.

`conformance_studies.py`: `requires=("python3",)`, `base_study={"case.json:t_end_ms": 5.0}`, `patch=("case.json:chi_per_mm", 150)`, `untouched=("case.json", ("cm_uF_per_mm2",))`, `sweep_name="case.json:dx_mm"`, `sweep_values=(1.0, 0.5)`, `unknown_name="case.json:chi_per_m"`, `quantity=QuantityTarget(artifact_format=ACTIVATION_FORMAT, reference=Path("niederer2011.json"), at_unit=None, max_sampling_offset=1e-9, study={"case.json:t_end_ms": 60.0}, sweep_values=(0.5, 0.25), tolerance=5.0, tolerance_unit="ms", parallel_tolerance=0.0, rank_evidence=RankEvidence(log_pattern=r"never(\d+)"))` — `rank_evidence` is required by the type but C13 is not applicable to a serial-only record. Check how openCARP's `conformance_studies.py` is registered with the stack and do the same.

`environment.py`: `TORCHCOR_VENV` (or `TORCHCOR_BIN`, Task 2) missing or its `python3` absent → error; the case's `device` not in the catalogue's `devices` → error.

- [ ] Tests: the contract test mirroring openCARP's `test_plugin_contract.py` (every public callable names a member; the stack builds); environment diagnostics. Implement; commit.

### Task 8: Real runs and the cross-solver comparison

- [ ] `omnidriver describe --repo ~/torchcor-cases` lists `nversion` (serial-only).
- [ ] `omnidriver check --repo ~/torchcor-cases --scratch-dir ~/omnid-runs/2026-10-09/scratch-tc --benchmarks <omniD>/benchmarks` from the shell `omnidriver env --plugin torchcor` prints. Expect C1–C12 and C14 passed, C13 not_applicable. Save the JSON to `~/omnid-runs/2026-10-09/torchcor-nversion-check.json`.
- [ ] `omnidriver run --repo ~/torchcor-cases --entry nversion` at dx 0.5 and openCARP's `niedererNVersion` at dx 500 µm (same dt 0.005 ms where openCARP's record allows it); write a `compare` request pairing P1–P8 of the two runs against `niederer2011.json` (follow `benchmarks/niederer2011/campaign/requests/cross_dx0.5_dt0.01.json`'s shape) and run `omnidriver compare`. Record the table in `docs/solver-learning/torchcor.md` (G3) — informal, one resolution, not the campaign.
- [ ] Opus review of the branch; fix; ROADMAP §5 entry for TorchCor (state, open F-questions); commit.
