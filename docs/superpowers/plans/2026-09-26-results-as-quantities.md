# Results as Comparable Quantities Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Step 2 of the benchmarker. omniD reads each solver's results as the same named quantities, so an agent can compare activation times at the Niederer 2011 points across runs and solvers. Every value carries its unit, its status, the location the solver sampled and the rule it used.

**Architecture:**
- Core gets a solver-neutral `omnidriver.core.quantities` package:
  - the `Quantity` record;
  - a unit table;
  - the reader contract behind `RuntimeEvidenceCapability.artifact_value_reader`, dispatched by artifact format;
  - a point-sampling reference schema;
  - a comparison over agent-stated pairs, with its report written in the `experiments.py` checker-report envelope and bound to each run's evidence;
  - one entry point, `omnidriver compare`, or `run_quantity_comparison()` from Python.
- Record `produces` entries can name their format through `ProducedPath`, a `str` subclass. Every existing reader of `produces` keeps seeing plain paths.
- openCARP gets a reader for its per-node LAT file, which samples at points the agent supplies in the request. cardiacFOAM's probe reader is specified here but blocked on the tutorial stream.
- Core does no frame conversion and no pairing, and invents no tolerance. The agent states orientation, pairing and tolerance in its request. The report shows enough that a wrong one is visible.

**Tech Stack:** Python ≥ 3.11, pytest, jsonschema ≥ 4 (already a core dependency; Draft 2020-12), openCARP v18.1 (`openCARP`, `mesher`), uv.

**Spec:** `docs/superpowers/specs/2026-09-26-results-as-quantities-design.md`.
**Evidence:**
- `docs/solver-learning/opencarp.md`: F3, F5, F6, D5, G4, plus F16 and F17 added by Task 5;
- the code map `.superpowers/sdd/map-B.md`;
- the paper research `.superpowers/sdd/niederer-benchmark-definition.md`, which is not committed (the directory is git-ignored). Task 4 transcribes from it.
**Runs alongside:** topic A, `docs/superpowers/specs/2026-09-26-core-generality-design.md`. See "Coordination with topic A" below.


> **Corrected 2026-09-26 (controller): P2–P7 are resolved.** This plan was written
> before the owner's own labelled table was found:
> `~/Documents/Latex_papers/ElectrophysiologySolver/sections/paperI_methods_publication/appendices/niederer_protocol.qmd`.
> The resolution, with its derivation into the Niederer frame, is appended to
> `.superpowers/sdd/niederer-benchmark-definition.md` under "Resolution of P2–P7".
> Task 4 therefore gives **every point P1–P9 its coordinates**, and nothing is
> `unresolved`:
> P1 (0,0,0) · P2 (0,7,0) · P3 (20,0,0) · P4 (20,7,0) · P5 (0,0,3) · P6 (0,7,3) · P7 (20,0,3) · P8 (20,7,3) · P9 (10,3.5,1.5) mm.
> P1, P8 and P9 cite the Niederer paper. The rest cite the owner's paper I
> appendix as "labelling convention consistent with Niederer 2011's P1/P8/P9 and
> vertical pairings", and state that the P2/P3 naming order is not independently
> checked against the ESM. The `unresolved` machinery (schema, loader, refusal
> of pairs naming an unresolved point) stays: it is a general feature for future
> references, tested with the toy reference only.

> **Corrected 2026-09-26 (R1 review, I4), after topic A's A5 landed:** A5 wrote its own F15 into `docs/solver-learning/opencarp.md` and prepended `"out"` to the openCARP solve step's `produces`. So this plan's probe rows are **F16 and F17** (they were F15 and F16), the solve step keeps `"out"` first, and the LAT artifact id in the request example is `record.solve.2` (record artifact ids are index-based, `record.<step>.<index>`).

## Status

Added 2026-09-26 (final whole-topic review, finding M13: CLAUDE.md tells a
reader to start here, and there was no table). Built from `git log`.

| item | commit(s) | status |
|---|---|---|
| Task 1: record outputs name their format (`ProducedPath`) | `26a8da6` | done |
| Task 2: quantities, units, reader contract; C12 | `3f16fe8` | done |
| Task 3: comparison (reference/request/report), `omnidriver compare` | `13ba8b6`, `5259160` | done |
| Task 4: reference `benchmarks/niederer2011.json` | `767f70a` | done |
| Task 5: openCARP reads its LAT file as quantities (F16/F17) | `422d549`, `ff6331e` | done |
| Task 6: openCARP-vs-openCARP proof end to end; docs and CI gate | `5a0778e` | done |
| Opus review fixes (location guards, pre-registration, unit-carrying reports; M11) | `04a1093`, `206de29`, `9923621` | done |
| Task 7 (cardiacFOAM's probe reader) | — | **blocked** on the tutorial stream's step 5.4b (`niederer2012` as a record) |
| Task 8 (openCARP vs cardiacFOAM end to end) | — | **blocked** on Task 7 |

## Global Constraints

- Python floor 3.11; CI matrixes 3.11/3.12/3.13.
- Core names no solver or physics:
  - `scripts/check-import-boundaries.py` keeps its empty waiver list;
  - `scripts/check-core-shape.py` accepts no new token;
  - the cardiac-token tests (`test_generic_plan_has_no_cardiac_semantics`, `test_override_schema_capability`) stay green.
  - Nothing under `packages/omnidriver/src` says *activation*, *probe*, *node*, *cell*, *ionic* or a solver's name. Core's words are *quantity*, *value*, *sample*, *point*, *unit* and *sentinel*. Sampling-rule strings (`node`, `cell-containing`) are declared by plugins, and core only carries them.
- **No skips, no fallbacks.** A check that cannot run is a failure that names why. `native_opencarp` tests (openCARP) and `native` tests (cardiacFOAM) **fail, not skip**, when their environment variables are unset.
  - Where a declared default exists (a plain `produces` path means format `"file"`), it is the data model's stated meaning, not a fallback.
  - An absent reader is reported as `not_evaluated` with a reason, never as a pass.
- **Supplied, never discovered** (`future/ENVIRONMENT_CONTRACT.md` §12):
  - native trees come from `OMNIDRIVER_OPENCARP_TUTORIALS` (openCARP) and `OMNIDRIVER_NATIVE_TUTORIALS` (cardiacFOAM);
  - openCARP's library path is the ambient `DYLD_LIBRARY_PATH`;
  - the reference file's path, each run's sweep output, case and plugin, the sampling points, the pairing and the tolerance all come from the agent's comparison request. Core finds none of them itself.
  - The one thing a reader reads without being told is the solver's own record of the run it is reading: openCARP's `<simID>/parameters.par` states `meshname` (D5, F16). That is ambient truth, and the reader declares where it looks.
- **A supplied scratch root is required.** Every `plan --strict`, `sweep-plan`/`sweep-run` without `--output-dir`, and every test that stages a record passes `--scratch-dir <dir>` (or `scratch_root=`), outside the tutorials tree. There is no default.
- **No frame-conversion functions anywhere** (owner, 2026-09-26). Orientation and pairing are the agent's step. The report shows reference coordinates, requested points and sampled locations side by side.
- **Units are declared by readers, never hardcoded per solver.** Sentinels (`-1` = never reached) are resolved **before** any conversion, so `-1 s` is `not_reached` and never `-1000 ms`.
- **Pre-registration** (the rule from `tests/equivalence/protocol.py`):
  - a tolerance is stated in the request, with a rationale, before any value is read;
  - the report is written once, to a path that must not exist;
  - a changed request is a new report, and the request's digest is in it.
- Claims about a solver come from the real binary. Every probe goes into its evidence log (command, observed output, conclusion). Fixtures cannot settle a claim about external behaviour, and no test uses invented geometry: openCARP reader tests read files that `mesher` and `openCARP` wrote.
- The native tree is never written. Every run stages a copy under the scratch root.
- **Stale cardiacFOAM Niederer references are not fixed here.** The tolerance rows and reference paths in `equivalence_protocol.yaml` and `regression_equivalence/registry.py` belong to the tutorial stream's `niederer2012` migration (its step 5.4b).
- Evaluate defaults lazily (CLAUDE.md). Name a symbol, not a line number. Correct a docstring or comment claim with a date; do not silently overwrite it.
- Verify in all shapes before any "done":
  - all packages;
  - core alone;
  - the installed wheel;
  - `-m native_opencarp`, plus `-m native` for cardiacFOAM once Task 7 runs;
  - the static gates.

  The durable claim is **0 failed**. Suite totals are never quoted.
- Every commit message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Working beside topic A and the tutorial stream:**
  - Core files are shared ground (see the next section). Every core change here lands on `main` as its own small commit, soon after review.
  - Each core change adds a row to the generality log (`docs/superpowers/plans/2026-09-25-tutorials-are-pointers-remaining.md` §5): stream `results-as-quantities`, what the change is, why, and a verdict.
  - Never hand-build an `omnidriver run` command; use `core.runtime.run_command.omnidriver_run_command(ctx, *args)`. This plan runs only `sweep-run` and `compare` as subprocesses, the way conformance C7 does.
  - `main` changes only by fast-forward, never force. Nothing goes to `origin` without the owner's go-ahead.
- **One venv per worktree.** A shared venv imports another checkout and gives false greens. Each executing agent builds these from its own worktree, and uses them wherever this plan writes `/tmp/odB` and `/tmp/odBcore`:
  - `/tmp/odB-<worktree-name>`: all five packages;
  - `/tmp/odBcore-<worktree-name>`: core only;
  - `/tmp/odBwheel-<worktree-name>`: the installed core wheel.

## Coordination with topic A

| shared file | this plan | topic A | how B stays rebase-safe |
|---|---|---|---|
| `core/runtime/models.py` (`DataArtifact`, `{time}`, `time_indexed`) | **not edited** | A2 renames `{time}`/`time_indexed` to `{instance}` instance directories | B only reads `DataArtifact.artifact_id`, `.path_pattern` and `.format`, which already exist. It refuses any `path_pattern` containing `{` rather than naming a placeholder, so A2 can land before or after B |
| `core/runtime/record_execution.py` | Task 1 changes one argument in `record_step_artifacts` (`format="file"` → `step.produced_format(path)`) | A5 excludes every record step's `produces` from record staging; A2 may touch nearby code | `ProducedPath` is a `str`, so A5's loop over `step.produces` needs no change. **B's Task 1 lands first**, as a small commit before A2 (A2 runs after A's parallel tracks and A1, so Task 1 is naturally earlier). If A5 lands first, the hunks are in different functions |
| `core/runtime/reconciler.py` | not edited; Task 3 calls `reconcile_artifacts(case_root, (artifact,), case_id=...)` | A2 renames `time_directory_names` | B never passes that keyword |
| `core/plugin_capabilities.py`, `core/plugin_interface.py` | Task 2: signature and docstring of `artifact_value_reader` / `get_artifact_value_reader` only | A1 (environment source), A3 (optional dictionary members) | the edits are in different Protocols and adapters. Rebase onto whatever of A1/A3 has landed before committing Task 2 |
| `conformance/checks.py` | Task 2 adds check **C12** | A5 adds **C11** (decided 2026-09-26) | whichever lands second rebases; both only append to `CHECKS` |
| `ARCHITECTURE.md` (generated seam table) | Tasks 2 and 3 regenerate it | A3 changes tiers | always regenerate with `scripts/export-capability-seams.py` after rebasing, never hand-merge the table |
| `cli.py` | Task 3 adds action `compare` and two flags | A1 renames `--environment-bashrc`; A6 scrubs `--config` help | different lines; rebase |
| `packages/omnidriver-opencarp/.../plugin.py` | Task 5 adds `get_artifact_value_reader` | A1 deletes the bashrc parameter; A3 deletes the dictionary stubs | additive method; rebase |
| `tests/plugins/*` | Task 2 adds `quantity_toy.py` (new file, subclasses only) | A1 edits `del explicit_bashrc` in toy plugins | new file only |

## Spec items and where they land

| spec item | where |
|---|---|
| §3 `Quantity(name, value, unit, status, source_artifact, sampled_at, sampling_rule)`, statuses `evaluated`/`not_reached`/`not_evaluated` | Task 2 (plus `sampled_at_unit` and `reason`; see the deviations below) |
| §3 reader contract, dispatch by format; `produces` gains an optional per-path format | Task 1 (`ProducedPath`), Task 2 (`ArtifactValueReader`) |
| §3 unit normalisation, sentinels first | Task 2 (`units.py`, `read_quantities`, `converted`) |
| §3 tolerance comparison over agent-supplied pairs | Task 3 |
| §3 generic point-sampling reference schema | Task 3 (`point-reference.schema.json`) |
| §3 report in the `experiments.py` envelope, tied to run evidence | Task 3 (`run_evidence` as a list; `experiment_comparisons`) |
| §3 CLI/API entry point | Task 3 (`omnidriver compare`, `run_quantity_comparison`) |
| §3 openCARP reader | Task 5 |
| §3 cardiacFOAM reader | Task 7 (**blocked** on tutorial 5.4b) |
| §2 reference `benchmarks/niederer2011.json`, from the paper | Task 4 |
| §4 native openCARP test at coarse dx | Task 5 (dx 500, against G4) |
| §4 core test: `-1 s` → `not_reached`, tolerance, refusal of inconvertible units | Tasks 2, 3 |
| §4 end-to-end agent-style comparison | Task 6 (openCARP dx 500 vs dx 250, now), Task 8 (openCARP vs cardiacFOAM, **blocked**) |
| §4 conformance extension "a record that declares quantity outputs returns them through the reader contract" | Task 2, check C12 |
| §2 stale cardiacFOAM references | **not here** (tutorial stream 5.4b) |

**Deviations from the spec, each forced by evidence.** Task 6 records them in the spec as a dated correction.

1. **The paper prints no coordinates** (research §1, §3).
   - The reference cannot hold "the paper's coordinates". It declares a frame convention (`stated_by_source: false`: origin at P1, the stimulus corner; axes along the 20, 7 and 3 mm edges), and gives coordinates only for points whose position the paper settles: P1, P4, P8 and P9, the research's verified list.
   - P2, P3, P6 and P7 are carried with `coordinates: null` and the reason. The paper does not say which of P1's neighbours along the 7 mm and 20 mm edges each one is; the numbers are in the ESM, which was not retrieved.
   - P5 rests on the same vertical pairing as P4, but is not on the research's verified list. It stays unresolved until the owner confirms (Task 4 Step 1).
2. **The paper states no tolerance.** Tolerances therefore live in the comparison request, pre-registered with a rationale, and not in the reference: one source for a tolerance, and nothing inferred into a paper-derived file. The reference schema has no `tolerances` field. The paper's one published number, P8's 37.8–48.7 ms range across codes at the finest resolution (§6), goes in as a `published_values` entry.
3. **The reader signature changes.** `(case_root, artifact) -> Quantity` becomes a reader object:
   - it declares `value_unit`, `sentinels`, `sampling_rule`, `coordinate_unit` and `takes_points`;
   - its `read(case_root, artifact, request)` gets a third argument, the request's points.
   
   Core then resolves sentinels and converts, so no reader can get the order wrong. `Quantity` gains `sampled_at_unit` (openCARP coordinates are µm and cardiacFOAM's are m, so a bare triple is ambiguous) and `reason` (a `not_evaluated` without a why is useless; `cardiacfoam/runtime_evidence.py` already demands one).
4. **The probe file format belongs to OpenFOAM.** cardiacFOAM's reader is split. The parser for OpenFOAM's probes output goes in `omnidriver-openfoam`, which knows the layout; the reader in `omnidriver-cardiacfoam` declares the unit, the sentinel and what the field means.

## File structure

```
packages/omnidriver/src/omnidriver/core/
  tutorial_records.py              MODIFY (T1): ProducedPath, PLAIN_FILE_FORMAT, WorkflowStep.produced_format
  runtime/record_execution.py      MODIFY (T1): record_step_artifacts passes the declared format
  quantities/__init__.py           CREATE (T2, T3): re-exports
  quantities/errors.py             CREATE (T2): QuantityError and subclasses
  quantities/units.py              CREATE (T2): UNITS, dimension_of, check_convertible, convert
  quantities/model.py              CREATE (T2): Quantity, RawSample, ReadRequest, ArtifactValueReader, not_evaluated
  quantities/reading.py            CREATE (T2): check_reader, read_quantities, converted
  quantities/reference.py          CREATE (T3): PointReference, load_point_reference, schema_errors
  quantities/comparison.py         CREATE (T3): Tolerance, compare_pair, run_quantity_comparison, experiment_comparisons
  plugin_capabilities.py           MODIFY (T2, T3): artifact_value_reader signature, docstring, :consumed-by:
  plugin_interface.py              MODIFY (T2): get_artifact_value_reader docstring and annotation
  experiments.py                   MODIFY (T3): run_evidence may be a list
packages/omnidriver/src/omnidriver/conformance/checks.py   MODIFY (T2): C12
packages/omnidriver/src/omnidriver/schemas/
  point-reference.schema.json      CREATE (T3)
  quantity-comparison.schema.json  CREATE (T3)
packages/omnidriver/src/omnidriver/cli.py                  MODIFY (T3): action `compare`
packages/omnidriver/pyproject.toml                         MODIFY (T3): package-data for both schemas
packages/omnidriver/tests/
  plugins/quantity_toy.py          CREATE (T2, T3): toy readers, QuantityToyPlugin, fixtures writers
  core/test_record_step_io.py      MODIFY (T1)
  core/test_quantities.py          CREATE (T2)
  core/test_conformance_toy.py     MODIFY (T2): C12
  core/test_point_reference.py     CREATE (T3)
  core/test_quantity_comparison.py CREATE (T3)
  core/test_experiments.py         MODIFY (T3)
benchmarks/niederer2011.json                               CREATE (T4)
scripts/check-benchmark-references.py                      CREATE (T4)
packages/omnidriver-opencarp/
  src/omnidriver/opencarp/lat_reader.py        CREATE (T5)
  src/omnidriver/opencarp/plugin.py            MODIFY (T5)
  src/omnidriver/opencarp/records/niederer_n_version.py   MODIFY (T5)
  src/omnidriver/opencarp/guidance.md          MODIFY (T5)
  tests/opencarp_native.py                     MODIFY (T5): niederer_sweep, niederer_run
  tests/test_lat_reader.py                     CREATE (T5)
  tests/test_lat_reader_native.py              CREATE (T5)
  tests/test_quantity_comparison_native.py     CREATE (T6; extended in T8)
docs/solver-learning/opencarp.md               MODIFY (T5): F16, F17
AGENT_GUIDE.md, CLAUDE.md, .github/workflows/ci.yml, the spec   MODIFY (T6)
packages/omnidriver-openfoam/src/omnidriver/openfoam/probes.py            CREATE (T7, blocked)
packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/activation_probes.py  CREATE (T7, blocked)
```

## Order and parallelism

- Task 1 → Task 2 → Task 3 (core; sequential, each its own commit on `main`).
- Task 5 (openCARP) can start after Task 2, **in parallel with Task 3**; it touches only `packages/omnidriver-opencarp` and `docs/solver-learning/opencarp.md`.
- Task 4 needs Task 3's schema; it can run in parallel with Task 5.
- Task 6 needs 3, 4 and 5.
- Task 7 is **blocked** until the tutorial stream's step 5.4b has made `niederer2012` a tutorial record on `main`. Task 8 is blocked on Task 7.
- An Opus review follows Task 3 (the core contract) and Task 6 (the whole unblocked topic).

---

### Task 1: Record outputs name their format (`ProducedPath`)

**Files:**
- Modify: `packages/omnidriver/src/omnidriver/core/tutorial_records.py` (`WorkflowStep`, new `ProducedPath`, `PLAIN_FILE_FORMAT`)
- Modify: `packages/omnidriver/src/omnidriver/core/runtime/record_execution.py` (`record_step_artifacts`)
- Test: `packages/omnidriver/tests/core/test_record_step_io.py`

**Why this shape.** The reader has to be able to tell a record's outputs apart, and today every one is `format="file"`. Options considered:
- (a) Normalise `produces` to a tuple of dataclasses. Every reader of `step.produces` changes: `record_execution`, A5's staging exclusion, and the tutorial stream's records and tests.
- (b) Add a side mapping `formats={path: format}`. It restates each path, and the two can drift.
- (c) **Chosen:** `ProducedPath(str)`, a path that *is* its string and carries `.format`.
  - Plain strings still work, and `step.produces` is still a tuple of `str` for every existing reader, so A5 and the tutorial stream need no rebase edits.
  - The format sits on the entry it describes, stated once.
  - `dataclasses.replace`, `copy.deepcopy` and `json.dumps` all keep working (`__reduce__` is defined).
  - The cost: equality and string operations ignore the format, so a format is read only through `WorkflowStep.produced_format`. The class docstring says so.

**Interfaces:**
- Produces:
  - `PLAIN_FILE_FORMAT: str = "file"`;
  - `class ProducedPath(str)` with `ProducedPath(path: str, format: str)` and attribute `.format: str`;
  - `WorkflowStep.produced_format(path: str) -> str`.
- `record_step_artifacts` gives each record artifact its declared format.
- Consumes: `WorkflowStep`, `TutorialRecordError`, `record_step_artifacts`, `record_artifact_id` (all on `main`).

- [ ] **Step 1: Preconditions (no code)**

  ```bash
  cd <worktree>
  grep -n 'format="file"' packages/omnidriver/src/omnidriver/core/runtime/record_execution.py
  grep -n "class WorkflowStep" packages/omnidriver/src/omnidriver/core/tutorial_records.py
  git log --oneline main -20 | grep -iE "instance|A2|A5|K3 core" || echo "topic A's A2/A5 not on main yet"
  uv venv --python 3.11 /tmp/odB-<wt> && VIRTUAL_ENV=/tmp/odB-<wt> uv pip install -q \
    -e "packages/omnidriver[post]" -e packages/omnidriver-openfoam -e packages/omnidriver-cardiacfoam \
    -e packages/omnidriver-cardiaccore -e packages/omnidriver-opencarp pytest build
  uv venv --python 3.11 /tmp/odBcore-<wt> && VIRTUAL_ENV=/tmp/odBcore-<wt> uv pip install -q -e "packages/omnidriver[post]" pytest
  /tmp/odB-<wt>/bin/python -c "import omnidriver, pathlib; print(pathlib.Path(omnidriver.__path__[0]).resolve())"
  ```
  Expected:
  - one `format="file"` line inside `record_step_artifacts`;
  - the printed package path is inside this worktree.
  
  If A5 has landed, read its staging exclusion and confirm it iterates `step.produces` as strings; `ProducedPath` keeps that working unchanged.

- [ ] **Step 2: Write the failing tests** (append to `test_record_step_io.py`)

  ```python
  import copy
  import dataclasses
  import json

  from omnidriver.core.tutorial_records import PLAIN_FILE_FORMAT, ProducedPath


  def test_a_plain_produces_path_is_an_unread_file():
      step = WorkflowStep(step_id="solve", command=("s",), produces=("out/v.igb",))
      assert step.produces == ("out/v.igb",)
      assert step.produced_format("out/v.igb") == PLAIN_FILE_FORMAT == "file"


  def test_a_produced_path_is_its_path_and_names_its_format():
      step = WorkflowStep(step_id="solve", command=("s",),
                          produces=("out/v.igb", ProducedPath("out/lat.dat", format="toy_lat")))
      # every existing reader of `produces` still sees plain paths
      assert step.produces == ("out/v.igb", "out/lat.dat")
      assert all(isinstance(path, str) for path in step.produces)
      assert json.dumps(list(step.produces)) == '["out/v.igb", "out/lat.dat"]'
      assert step.produced_format("out/lat.dat") == "toy_lat"
      # the format survives the copies core and tests make
      assert copy.deepcopy(step).produced_format("out/lat.dat") == "toy_lat"
      assert dataclasses.replace(step, command=("t",)).produced_format("out/lat.dat") == "toy_lat"


  def test_record_artifacts_carry_the_declared_format():
      record = TutorialRecord(
          name="fmt", native_case_relpath="fmt", allowed_axes=frozenset(),
          workflow_steps=(WorkflowStep(step_id="solve", command=("s",),
                                       produces=("out/v.igb", ProducedPath("out/lat.dat", format="toy_lat"))),),
      )
      assert [(a.path_pattern, a.format) for a in record_step_artifacts(record, ("solve",))] == [
          ("out/v.igb", "file"), ("out/lat.dat", "toy_lat"),
      ]


  @pytest.mark.parametrize("bad", ["", " toy", "file"])
  def test_a_format_must_be_named_and_not_the_plain_meaning(bad):
      with pytest.raises(TutorialRecordError, match="format"):
          ProducedPath("out/lat.dat", format=bad)


  @pytest.mark.parametrize("second", [ProducedPath("out/lat.dat", format="other"), "out/lat.dat"])
  def test_a_formatted_path_is_declared_once(second):
      with pytest.raises(TutorialRecordError, match="more than once"):
          WorkflowStep(step_id="solve", command=("s",),
                       produces=(ProducedPath("out/lat.dat", format="toy_lat"), second))


  def test_a_format_on_consumes_is_refused():
      with pytest.raises(TutorialRecordError, match="belongs on the step that produces"):
          WorkflowStep(step_id="solve", command=("s",), consumes=(ProducedPath("in.dat", format="toy"),))


  def test_the_format_of_a_path_the_step_does_not_produce_is_refused_by_name():
      step = WorkflowStep(step_id="solve", command=("s",), produces=("out/v.igb",))
      with pytest.raises(TutorialRecordError, match="'out/lat.dat'"):
          step.produced_format("out/lat.dat")
  ```

- [ ] **Step 3: Run them to verify they fail**

  Run: `/tmp/odB-<wt>/bin/python -m pytest packages/omnidriver/tests/core/test_record_step_io.py -q`
  
  Expected: collection error, `ImportError: cannot import name 'PLAIN_FILE_FORMAT'`.

- [ ] **Step 4: Implement**

  In `tutorial_records.py`, just above `class WorkflowStep`:
  ```python
  PLAIN_FILE_FORMAT = "file"
  """The format of a ``produces`` path that names none: a file that exists or
  not, which no reader reads (``record_execution.record_step_artifacts``)."""


  class ProducedPath(str):
      """A ``produces`` path that also names the format of what it holds.

      It *is* its path: a ``str`` equal to the path, so every reader of
      ``WorkflowStep.produces`` (the DAG's artifact ids, record staging,
      provenance, a JSON dump) sees paths exactly as before. The format rides
      on the entry and is read only through :meth:`WorkflowStep.produced_format`:
      a string operation on the path returns a plain ``str`` without it, and
      two entries compare equal by path alone. Core never interprets the
      format. It names the reader a plugin returns from
      ``get_artifact_value_reader`` (docs/superpowers/specs/2026-09-26-results-
      as-quantities-design.md §3). Added 2026-09-26.
      """

      format: str

      def __new__(cls, path: str, format: str) -> "ProducedPath":
          if not isinstance(path, str):
              raise TutorialRecordError(f"a produced path must be a str, not {type(path).__name__}")
          if not isinstance(format, str) or not format or format != format.strip():
              raise TutorialRecordError(
                  f"produced path {path!r} must name a non-empty format without surrounding spaces, got {format!r}"
              )
          if format == PLAIN_FILE_FORMAT:
              raise TutorialRecordError(
                  f"produced path {path!r}: format {PLAIN_FILE_FORMAT!r} is what a plain path already means; write the path alone"
              )
          entry = super().__new__(cls, path)
          entry.__dict__["format"] = format
          return entry

      def __setattr__(self, name: str, value: object) -> None:
          raise AttributeError(f"ProducedPath is immutable; cannot set {name!r}")

      def __reduce__(self):
          return (ProducedPath, (str(self), self.format))

      def __repr__(self) -> str:
          return f"ProducedPath({str(self)!r}, format={self.format!r})"
  ```

  In `WorkflowStep`, add to the docstring:
  > A ``produces`` entry may be a :class:`ProducedPath`, which also names its
  > format. A plain path means :data:`PLAIN_FILE_FORMAT`. Added 2026-09-26.
  
  At the end of `__post_init__`:
  ```python
          formatted: set[str] = set()
          plain: set[str] = set()
          for path in self.produces:
              if isinstance(path, ProducedPath):
                  if path in formatted or path in plain:
                      raise TutorialRecordError(
                          f"workflow step {self.step_id!r} produces {str(path)!r} more than once with a format; a path has one format"
                      )
                  formatted.add(str(path))
              else:
                  if path in formatted:
                      raise TutorialRecordError(
                          f"workflow step {self.step_id!r} produces {path!r} more than once with a format; a path has one format"
                      )
                  plain.add(path)
          for path in self.consumes:
              if isinstance(path, ProducedPath):
                  raise TutorialRecordError(
                      f"workflow step {self.step_id!r} consumes {str(path)!r} with a format; a format belongs on the step that produces the file"
                  )

      def produced_format(self, path: str) -> str:
          """The declared format of one of this step's ``produces`` paths."""
          for entry in self.produces:
              if entry == path:
                  return entry.format if isinstance(entry, ProducedPath) else PLAIN_FILE_FORMAT
          raise TutorialRecordError(
              f"workflow step {self.step_id!r} does not produce {path!r}; it produces {[str(p) for p in self.produces]}"
          )
  ```

  In `record_execution.record_step_artifacts`, replace `format="file",` with `format=step.produced_format(path),`.

- [ ] **Step 5: Run the tests to verify they pass, in both shapes**

  ```bash
  /tmp/odB-<wt>/bin/python -m pytest packages/omnidriver/tests/core/test_record_step_io.py -q
  /tmp/odBcore-<wt>/bin/python -m pytest packages/omnidriver/tests -q
  /tmp/odB-<wt>/bin/python -m pytest packages/ -q -m "not slow and not native and not native_opencarp"
  python3 scripts/check-import-boundaries.py && python3 scripts/check-core-shape.py
  ```
  Expected: 0 failed everywhere.

- [ ] **Step 6: Generality-log row and commit**

  Append this row to §5 of `docs/superpowers/plans/2026-09-25-tutorials-are-pointers-remaining.md`:
  ```
  | 2026-09-26 | results-as-quantities | `ProducedPath(str)`: a record step's `produces` entry may name its format; `record_step_artifacts` passes it (`format` was always `"file"`) | a result reader is chosen by artifact format, and every record output looked the same | neutral: the format string is plugin vocabulary core never reads; a `ProducedPath` is its path, so every existing reader of `produces` (A5's staging exclusion included) is untouched |
  ```
  ```bash
  git add packages/omnidriver/src/omnidriver/core/tutorial_records.py packages/omnidriver/src/omnidriver/core/runtime/record_execution.py packages/omnidriver/tests/core/test_record_step_io.py docs/superpowers/plans/2026-09-25-tutorials-are-pointers-remaining.md
  git commit -m "feat(core): a record's produces entry may name its format (ProducedPath)

  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
  ```
  Fast-forward `main` after review. It should land before topic A's A2.

---

### Task 2: Quantities, units and the reader contract (core), plus conformance C12

**Files:**
- Create: `packages/omnidriver/src/omnidriver/core/quantities/{__init__,errors,units,model,reading}.py`
- Modify: `packages/omnidriver/src/omnidriver/core/plugin_capabilities.py` (`RuntimeEvidenceCapability`)
- Modify: `packages/omnidriver/src/omnidriver/core/plugin_interface.py` (`get_artifact_value_reader`)
- Modify: `packages/omnidriver/src/omnidriver/conformance/checks.py` (C12)
- Create: `packages/omnidriver/tests/plugins/quantity_toy.py`
- Create: `packages/omnidriver/tests/core/test_quantities.py`
- Modify: `packages/omnidriver/tests/core/test_conformance_toy.py`
- Regenerate: `ARCHITECTURE.md` seam table

**Interfaces:**
- Consumes: `PLAIN_FILE_FORMAT`, `ProducedPath`, `WorkflowStep.produced_format` (Task 1); `DataArtifact` (`core.runtime.models`); `E2ERecordPlugin` and `MinimalTestPlugin` (tests).
- Produces, all re-exported from `omnidriver.core.quantities`:
  - errors: `QuantityError(ValueError)`, `UnitError`, `ReaderDeclarationError`, `QuantityReadError`, `QuantityComparisonError`, `PointReferenceError`;
  - units: `UNITS: dict[str, tuple[str, int]]`, `dimension_of(unit) -> str`, `check_convertible(from_unit, to_unit) -> None`, `convert(value, from_unit, to_unit) -> float`;
  - model: `Point = tuple[float, float, float]`, `QUANTITY_STATUSES`;
    - `Quantity(name, value, unit, status, source_artifact, sampled_at, sampled_at_unit, sampling_rule, reason=None)` with `.to_json()`;
    - `RawSample(name, value, sampled_at=None)`;
    - `ReadRequest(names, points=MappingProxyType({}))`;
    - `ArtifactValueReader` (Protocol: `value_unit`, `sentinels`, `sampling_rule`, `coordinate_unit`, `takes_points`, and `read(case_root, artifact, request) -> tuple[RawSample, ...]`);
    - `not_evaluated(names, *, source_artifact, reason) -> tuple[Quantity, ...]`;
  - reading: `check_reader(reader, *, artifact_format)`, `read_quantities(reader, case_root, artifact, request) -> tuple[Quantity, ...]`, `converted(quantity, to_unit) -> Quantity`;
  - conformance: `check_readable_quantities(target) -> CheckVerdict`, registered as `"C12"`;
  - in tests (`plugins.quantity_toy`):
    - formats `VALUES_FORMAT = "toy_named_values"` and `GRID_FORMAT = "toy_grid_values"`;
    - readers `ToyRowReader` and `ToyNearestRowReader`;
    - `QuantityToyPlugin`, plus `QUANTITY_TOY_PLUGIN = "plugins.quantity_toy:QuantityToyPlugin"`;
    - `UnreadableFormatPlugin` and `BadDeclarationPlugin`;
    - `write_toy_values(path, rows)`.

- [ ] **Step 1: Preconditions**

  ```bash
  grep -n '"C1[0-9]"' packages/omnidriver/src/omnidriver/conformance/checks.py
  grep -n "def artifact_value_reader\|def get_artifact_value_reader" packages/omnidriver/src/omnidriver/core/plugin_capabilities.py packages/omnidriver/src/omnidriver/core/plugin_interface.py
  git log --oneline main -1 -- packages/omnidriver/src/omnidriver/core/plugin_capabilities.py
  ```
  - **Decided 2026-09-26:** topic A's A5 owns `C11` (the second-staging check); this plan's check is `C12` everywhere.
  - Rebase onto `main` first if A1 or A3 changed `plugin_capabilities.py` since this branch started.

- [ ] **Step 2: Write the toy readers and plugins**

  `packages/omnidriver/tests/plugins/quantity_toy.py`:
  ```python
  """Toy readers and a toy record for the quantities contract.

  Core-owned claims only (units, sentinels, the reader contract, the
  comparison): no geometry and no solver behaviour is asserted from these
  files. Solver claims are tested against real binaries in each plugin's
  package.
  """
  from __future__ import annotations

  import math
  from pathlib import Path
  from typing import Mapping

  from omnidriver.core.quantities import RawSample
  from omnidriver.core.tutorial_records import ProducedPath, TutorialRecord, WorkflowStep

  from plugins.e2e_record_plugin import (
      E2ERecordPlugin, _known_catalog_validator, _number_cells_axis, _typed_agree,
  )
  from plugins.minimal_plugin import MinimalTestPlugin

  VALUES_FORMAT = "toy_named_values"
  GRID_FORMAT = "toy_grid_values"
  QUANTITY_TOY_PLUGIN = "plugins.quantity_toy:QuantityToyPlugin"
  UNREADABLE_PLUGIN = "plugins.quantity_toy:UnreadableFormatPlugin"
  BAD_DECLARATION_PLUGIN = "plugins.quantity_toy:BadDeclarationPlugin"


  class ToyRowReader:
      """``<name> <value> <x> <y> <z>`` rows: seconds, ``-1`` never reached, metres.
      Samples where the file says it sampled, so it takes no points."""

      value_unit = "s"
      sentinels = frozenset({-1.0})
      sampling_rule = "toy-row"
      coordinate_unit = "m"
      takes_points = False

      def read(self, case_root, artifact, request):
          rows = {}
          for line in (Path(case_root) / artifact.path_pattern).read_text().splitlines():
              if line.strip():
                  name, value, x, y, z = line.split()
                  rows[name] = RawSample(name=name, value=float(value), sampled_at=(float(x), float(y), float(z)))
          return tuple(rows[name] for name in request.names if name in rows)


  class ToyNearestRowReader:
      """``<x> <y> <z> <value>`` rows in mm and ms; samples the row nearest each supplied point."""

      value_unit = "ms"
      sentinels = frozenset({-1.0})
      sampling_rule = "toy-nearest-row"
      coordinate_unit = "mm"
      takes_points = True

      def read(self, case_root, artifact, request):
          rows = []
          for line in (Path(case_root) / artifact.path_pattern).read_text().splitlines():
              if line.strip():
                  x, y, z, value = (float(v) for v in line.split())
                  rows.append(((x, y, z), value))
          samples = []
          for name in request.names:
              target = request.points[name]
              point, value = min(rows, key=lambda row: math.dist(row[0], target))
              samples.append(RawSample(name=name, value=value, sampled_at=point))
          return tuple(samples)


  class _FurlongReader(ToyRowReader):
      value_unit = "furlong"


  def write_toy_values(path: Path, rows: Mapping[str, tuple[str, tuple[float, float, float]]]) -> Path:
      path.parent.mkdir(parents=True, exist_ok=True)
      path.write_text("".join(f"{name} {value} {x} {y} {z}\n" for name, (value, (x, y, z)) in rows.items()))
      return path


  TOY_QUANTITY_RECORD = TutorialRecord(
      name="toyQuantities",
      native_case_relpath="toyQuantities",
      allowed_axes=frozenset({"number_cells"}),
      workflow_steps=(WorkflowStep(
          step_id="solve", command=("cp", "seed/values.txt", "values.txt"),
          consumes=("constant/mesh.json", "seed/values.txt"),
          produces=(ProducedPath("values.txt", format=VALUES_FORMAT),),
      ),),
  )


  def write_quantity_toy_case(cases_root: Path, values_text: str) -> Path:
      import json

      native = cases_root / "toyQuantities"
      (native / "constant").mkdir(parents=True)
      (native / "constant" / "mesh.json").write_text(json.dumps({"cells": "1", "label": "toy"}))
      (native / "seed").mkdir()
      (native / "seed" / "values.txt").write_text(values_text)
      return native


  class QuantityToyPlugin(E2ERecordPlugin):
      _READERS = {VALUES_FORMAT: ToyRowReader(), GRID_FORMAT: ToyNearestRowReader()}

      def __init__(self) -> None:
          MinimalTestPlugin.__init__(
              self,
              solver_commands=frozenset({"cp"}),
              tutorial_records={"toyQuantities": TOY_QUANTITY_RECORD},
              axis_catalog={"number_cells": _number_cells_axis()},
              record_key_validator=_known_catalog_validator,
              case_value_comparator=_typed_agree,
          )

      def get_artifact_value_reader(self, artifact_format: str):
          return self._READERS.get(artifact_format)


  class UnreadableFormatPlugin(E2ERecordPlugin):
      """Declares a format on toyTutorial's output and has no reader for it."""

      def get_tutorial_records(self) -> dict:
          record = super().get_tutorial_records()["toyTutorial"]
          step = record.workflow_steps[0]
          import dataclasses

          step = dataclasses.replace(step, produces=(ProducedPath("solved.marker", format="toy_unreadable"),))
          return {"toyTutorial": dataclasses.replace(record, workflow_steps=(step,))}


  class BadDeclarationPlugin(UnreadableFormatPlugin):
      """Has a reader for the format, whose value unit is not in core's table."""

      def get_artifact_value_reader(self, artifact_format: str):
          return _FurlongReader() if artifact_format == "toy_unreadable" else None
  ```
  `E2ERecordPlugin`'s helpers `_known_catalog_validator`, `_number_cells_axis` and `_typed_agree` already exist at module level, so the import above works. Check that `TutorialRecord` is a frozen dataclass with `workflow_steps` as a field; `dataclasses.replace` needs that.

- [ ] **Step 3: Write the failing tests**

  `packages/omnidriver/tests/core/test_quantities.py`:
  ```python
  """The quantities contract: units, sentinels before conversion, the reader
  declaration (spec 2026-09-26 §3, §4)."""
  from __future__ import annotations

  import pytest

  from omnidriver.core.quantities import (
      Quantity, QuantityReadError, ReadRequest, ReaderDeclarationError, UnitError,
      check_reader, convert, converted, read_quantities,
  )
  from omnidriver.core.runtime.models import DataArtifact
  from plugins.quantity_toy import (
      GRID_FORMAT, VALUES_FORMAT, ToyNearestRowReader, ToyRowReader, _FurlongReader, write_toy_values,
  )

  ROWS = DataArtifact(artifact_id="record.solve.0", path_pattern="values.txt", format=VALUES_FORMAT)
  GRID = DataArtifact(artifact_id="record.solve.0", path_pattern="grid.txt", format=GRID_FORMAT)


  def test_the_table_converts_within_a_dimension():
      assert convert(1.5, "s", "ms") == pytest.approx(1500.0)
      assert convert(250.0, "us", "ms") == pytest.approx(0.25)
      assert convert(3.5, "mm", "um") == 3500.0
      assert convert(0.007, "m", "mm") == pytest.approx(7.0)
      assert convert(2.0, "cm", "mm") == 20.0


  def test_a_conversion_across_dimensions_is_refused():
      with pytest.raises(UnitError, match=r"'ms' \(time\).*'mm' \(length\)"):
          convert(1.0, "ms", "mm")


  def test_an_unknown_unit_is_refused_by_name():
      with pytest.raises(UnitError, match="'msec'"):
          convert(1.0, "msec", "ms")


  def test_a_sentinel_is_resolved_before_conversion(tmp_path):
      """-1 s means never reached. It is never -1000 ms."""
      write_toy_values(tmp_path / "values.txt", {"a": ("0.0015", (0, 0, 0.007)), "b": ("-1", (0.02, 0.003, 0))})
      a, b = read_quantities(ToyRowReader(), tmp_path, ROWS, ReadRequest(names=("a", "b")))
      assert (b.status, b.value, b.unit) == ("not_reached", None, "s")
      shown = converted(b, "ms")
      assert (shown.status, shown.value, shown.unit) == ("not_reached", None, "ms")
      assert converted(a, "ms").value == pytest.approx(1.5)
      assert (a.sampled_at, a.sampled_at_unit, a.sampling_rule, a.source_artifact) == (
          (0.0, 0.0, 0.007), "m", "toy-row", "values.txt",
      )


  def test_a_not_reached_quantity_still_refuses_an_inconvertible_unit(tmp_path):
      write_toy_values(tmp_path / "values.txt", {"b": ("-1", (0, 0, 0))})
      (b,) = read_quantities(ToyRowReader(), tmp_path, ROWS, ReadRequest(names=("b",)))
      with pytest.raises(UnitError):
          converted(b, "mm")


  def test_a_name_the_reader_does_not_return_is_refused_by_name(tmp_path):
      write_toy_values(tmp_path / "values.txt", {"a": ("0.1", (0, 0, 0))})
      with pytest.raises(QuantityReadError, match="'z'"):
          read_quantities(ToyRowReader(), tmp_path, ROWS, ReadRequest(names=("a", "z")))


  def test_points_given_to_a_reader_that_takes_none_are_refused(tmp_path):
      write_toy_values(tmp_path / "values.txt", {"a": ("0.1", (0, 0, 0))})
      with pytest.raises(QuantityReadError, match="takes no points"):
          read_quantities(ToyRowReader(), tmp_path, ROWS, ReadRequest(names=("a",), points={"a": (0, 0, 0)}))


  def test_a_point_reader_needs_a_point_for_every_name(tmp_path):
      (tmp_path / "grid.txt").write_text("0 0 0 1.0\n1 0 0 2.0\n")
      with pytest.raises(QuantityReadError, match="'far'"):
          read_quantities(ToyNearestRowReader(), tmp_path, GRID, ReadRequest(names=("far",)))
      (q,) = read_quantities(ToyNearestRowReader(), tmp_path, GRID,
                             ReadRequest(names=("far",), points={"far": (0.9, 0.0, 0.0)}))
      assert (q.value, q.unit, q.sampled_at, q.sampled_at_unit) == (2.0, "ms", (1.0, 0.0, 0.0), "mm")


  def test_a_reader_declaration_core_cannot_use_is_refused():
      with pytest.raises(ReaderDeclarationError, match="'furlong'"):
          check_reader(_FurlongReader(), artifact_format="toy")

      class NoPoints(ToyNearestRowReader):
          coordinate_unit = None

      with pytest.raises(ReaderDeclarationError, match="takes points"):
          check_reader(NoPoints(), artifact_format="toy")

      class TimeCoordinates(ToyRowReader):
          coordinate_unit = "ms"

      with pytest.raises(ReaderDeclarationError, match="length"):
          check_reader(TimeCoordinates(), artifact_format="toy")


  @pytest.mark.parametrize(("kwargs", "match"), [
      ({"status": "evaluated", "value": None}, "exactly when"),
      ({"status": "not_reached", "value": 1.0}, "exactly when"),
      ({"status": "not_evaluated", "value": None, "reason": None}, "reason"),
      ({"status": "done", "value": None}, "status"),
  ])
  def test_a_quantity_states_its_status_consistently(kwargs, match):
      base = dict(name="a", unit="s", source_artifact="values.txt", sampled_at=None,
                  sampled_at_unit=None, sampling_rule="toy-row")
      with pytest.raises(ValueError, match=match):
          Quantity(**{**base, **kwargs})
  ```

  Append to `packages/omnidriver/tests/core/test_conformance_toy.py`:
  ```python
  from plugins.quantity_toy import BAD_DECLARATION_PLUGIN, QUANTITY_TOY_PLUGIN, UNREADABLE_PLUGIN


  def test_c11_passes_a_record_whose_formats_have_readers(tmp_path):
      target = dataclasses.replace(toy_conformance_target(tmp_path), plugin=QUANTITY_TOY_PLUGIN, record="toyQuantities")
      verdict = run_check("C12", target)
      assert verdict.passed, verdict.detail
      assert "toy_named_values" in verdict.detail


  def test_c11_says_so_when_nothing_declares_a_format(tmp_path):
      verdict = run_check("C12", toy_conformance_target(tmp_path))
      assert verdict.passed and "nothing to read" in verdict.detail


  @pytest.mark.parametrize(("plugin", "named"), [(UNREADABLE_PLUGIN, "no reader"), (BAD_DECLARATION_PLUGIN, "furlong")])
  def test_c11_bites_a_declared_format_it_cannot_read(plugin, named, tmp_path):
      verdict = run_check("C12", toy_conformance_target(tmp_path, plugin=plugin))
      assert not verdict.passed
      assert named in verdict.detail and "toy_unreadable" in verdict.detail
  ```
  Also add `"C12"` to the id list of `test_toy_passes`.

- [ ] **Step 4: Run them to verify they fail**

  Run: `/tmp/odB-<wt>/bin/python -m pytest packages/omnidriver/tests/core/test_quantities.py packages/omnidriver/tests/core/test_conformance_toy.py -q`
  
  Expected: collection error, `ModuleNotFoundError: No module named 'omnidriver.core.quantities'`.

- [ ] **Step 5: Implement the package**

  `quantities/errors.py`:
  ```python
  """Every refusal in the quantities package is a ValueError that names why."""
  from __future__ import annotations


  class QuantityError(ValueError):
      """Base class: a quantity, unit, reader, reference or comparison refused by name."""


  class UnitError(QuantityError):
      """A unit is not in the table, or two units measure different things."""


  class ReaderDeclarationError(QuantityError):
      """A reader's declaration (unit, sentinels, rule, coordinates) core cannot use."""


  class QuantityReadError(QuantityError):
      """A read that does not answer the request it was given."""


  class PointReferenceError(QuantityError):
      """A point-sampling reference file that is malformed or cites nothing."""


  class QuantityComparisonError(QuantityError):
      """A comparison request refused before its report is written."""
  ```

  `quantities/units.py`:
  ```python
  """Unit normalisation: a small declared table, nothing inferred.

  Each unit maps to (dimension, factor in the dimension's smallest listed
  unit). The factors are integers, so a conversion between listed units is one
  multiply and one divide. A unit outside the table is refused by name, and
  so is a conversion between dimensions. Spellings are ASCII (``us``, ``um``);
  a reader declares one of these strings and a request writes one.
  Design: docs/superpowers/specs/2026-09-26-results-as-quantities-design.md §2.
  """
  from __future__ import annotations

  from typing import Final

  from .errors import UnitError

  UNITS: Final[dict[str, tuple[str, int]]] = {
      "s": ("time", 1_000_000),
      "ms": ("time", 1_000),
      "us": ("time", 1),
      "m": ("length", 1_000_000),
      "cm": ("length", 10_000),
      "mm": ("length", 1_000),
      "um": ("length", 1),
  }


  def dimension_of(unit: str) -> str:
      try:
          return UNITS[unit][0]
      except (KeyError, TypeError):
          raise UnitError(f"unit {unit!r} is not in the unit table; known: {sorted(UNITS)}") from None


  def check_convertible(from_unit: str, to_unit: str) -> None:
      source, target = dimension_of(from_unit), dimension_of(to_unit)
      if source != target:
          raise UnitError(f"cannot convert {from_unit!r} ({source}) to {to_unit!r} ({target})")


  def convert(value: float, from_unit: str, to_unit: str) -> float:
      check_convertible(from_unit, to_unit)
      return value * UNITS[from_unit][1] / UNITS[to_unit][1]
  ```

  `quantities/model.py`:
  ```python
  """A value read from a result, with everything needed to judge it.

  Design: docs/superpowers/specs/2026-09-26-results-as-quantities-design.md §3.
  Nothing here names a solver or a physical quantity. A reader declares the
  unit of what it returns, its sentinels (raw values meaning "never reached"),
  its sampling rule and the unit of its coordinates. Core resolves sentinels
  first and converts after (``reading.read_quantities``, ``reading.converted``).
  """
  from __future__ import annotations

  import math
  from dataclasses import dataclass, field
  from pathlib import Path
  from types import MappingProxyType
  from typing import TYPE_CHECKING, Any, Mapping, Protocol

  from .units import dimension_of

  if TYPE_CHECKING:
      from ..runtime.models import DataArtifact

  Point = tuple[float, float, float]
  QUANTITY_STATUSES = frozenset({"evaluated", "not_reached", "not_evaluated"})


  @dataclass(frozen=True)
  class Quantity:
      """One named value from one artifact.

      ``status``: ``evaluated`` (``value`` is a finite number in ``unit``),
      ``not_reached`` (the reader's sentinel: the solver says it never
      happened) or ``not_evaluated`` (nothing was read; ``reason`` says why).
      ``sampled_at`` is where the solver says it sampled, in
      ``sampled_at_unit``, in the solver's own frame. ``sampling_rule`` is the
      reader's declared rule, e.g. the nearest mesh point or the containing
      cell: plugin vocabulary, carried and never interpreted.
      ``sampled_at_unit`` and ``reason`` go beyond the spec's field list
      (2026-09-26): a coordinate triple without a unit is ambiguous, and a
      ``not_evaluated`` without a reason cannot be acted on.
      """

      name: str
      value: float | None
      unit: str | None
      status: str
      source_artifact: str
      sampled_at: Point | None
      sampled_at_unit: str | None
      sampling_rule: str | None
      reason: str | None = None

      def __post_init__(self) -> None:
          label = f"quantity {self.name!r}"
          if self.status not in QUANTITY_STATUSES:
              raise ValueError(f"{label}: status {self.status!r} is not one of {sorted(QUANTITY_STATUSES)}")
          if (self.value is not None) != (self.status == "evaluated"):
              raise ValueError(
                  f"{label}: a value is present exactly when the status is 'evaluated' "
                  f"(status {self.status!r}, value {self.value!r})"
              )
          if self.value is not None and not math.isfinite(self.value):
              raise ValueError(f"{label}: value {self.value!r} is not finite")
          if self.status == "not_evaluated":
              if not self.reason:
                  raise ValueError(f"{label} is not_evaluated without a reason")
          elif self.unit is None or not self.sampling_rule:
              raise ValueError(f"{label}: a read quantity carries its unit and sampling rule")
          if self.unit is not None:
              dimension_of(self.unit)
          if (self.sampled_at is None) != (self.sampled_at_unit is None):
              raise ValueError(f"{label}: sampled_at and sampled_at_unit are given together or not at all")
          if self.sampled_at_unit is not None and dimension_of(self.sampled_at_unit) != "length":
              raise ValueError(f"{label}: sampled_at_unit {self.sampled_at_unit!r} is not a length")

      def to_json(self) -> dict[str, Any]:
          return {
              "name": self.name, "value": self.value, "unit": self.unit, "status": self.status,
              "source_artifact": self.source_artifact,
              "sampled_at": list(self.sampled_at) if self.sampled_at is not None else None,
              "sampled_at_unit": self.sampled_at_unit, "sampling_rule": self.sampling_rule,
              "reason": self.reason,
          }


  @dataclass(frozen=True)
  class RawSample:
      """What a reader returns: a raw number, before sentinels or units."""

      name: str
      value: float
      sampled_at: Point | None = None


  @dataclass(frozen=True)
  class ReadRequest:
      """The names to read and, for a reader that samples at supplied points,
      where: each point is in the reader's ``coordinate_unit`` (core converted
      it from the request's unit). Empty for a reader that samples where the
      solver chose."""

      names: tuple[str, ...]
      points: Mapping[str, Point] = field(default_factory=lambda: MappingProxyType({}))


  class ArtifactValueReader(Protocol):
      """What ``get_artifact_value_reader(format)`` returns.

      ``read`` refuses by raising ``ValueError`` naming why. It returns one
      ``RawSample`` per requested name, in any order; core checks the names.
      """

      value_unit: str
      sentinels: frozenset[float]
      sampling_rule: str
      coordinate_unit: str | None
      takes_points: bool

      def read(self, case_root: Path, artifact: "DataArtifact", request: ReadRequest) -> tuple[RawSample, ...]: ...


  def not_evaluated(names: tuple[str, ...], *, source_artifact: str, reason: str) -> tuple[Quantity, ...]:
      return tuple(
          Quantity(name=name, value=None, unit=None, status="not_evaluated", source_artifact=source_artifact,
                   sampled_at=None, sampled_at_unit=None, sampling_rule=None, reason=reason)
          for name in names
      )
  ```

  `quantities/reading.py`:
  ```python
  """Reading quantities through a plugin's reader: sentinels first, then units."""
  from __future__ import annotations

  import math
  from dataclasses import replace
  from pathlib import Path
  from typing import Any

  from .errors import QuantityReadError, ReaderDeclarationError, UnitError
  from .model import Quantity, ReadRequest
  from .units import check_convertible, convert, dimension_of

  _DECLARED = ("value_unit", "sentinels", "sampling_rule", "coordinate_unit", "takes_points")


  def check_reader(reader: Any, *, artifact_format: str) -> None:
      """Refuse, by name, a reader whose declaration core cannot use."""
      label = f"the reader for format {artifact_format!r}"
      missing = [name for name in _DECLARED if not hasattr(reader, name)]
      if missing or not callable(getattr(reader, "read", None)):
          raise ReaderDeclarationError(f"{label} does not declare {missing or ['read']}")
      try:
          dimension_of(reader.value_unit)
          if reader.coordinate_unit is not None and dimension_of(reader.coordinate_unit) != "length":
              raise ReaderDeclarationError(f"{label}: coordinate_unit {reader.coordinate_unit!r} is not a length")
      except UnitError as exc:
          raise ReaderDeclarationError(f"{label}: {exc}") from exc
      if not isinstance(reader.sampling_rule, str) or not reader.sampling_rule:
          raise ReaderDeclarationError(f"{label} declares no sampling rule")
      if reader.takes_points and reader.coordinate_unit is None:
          raise ReaderDeclarationError(f"{label} takes points but declares no coordinate_unit to take them in")
      if any(not isinstance(s, (int, float)) or not math.isfinite(s) for s in reader.sentinels):
          raise ReaderDeclarationError(f"{label}: every sentinel must be a finite number, got {sorted(map(repr, reader.sentinels))}")


  def read_quantities(reader: Any, case_root: Path, artifact: Any, request: ReadRequest) -> tuple[Quantity, ...]:
      """Read ``request.names`` from one artifact, in request order.

      A sentinel is a statement ("never reached"), not a number, so it becomes
      ``not_reached`` here, before anything could convert it: ``-1 s`` is never
      ``-1000 ms`` (spec §2)."""
      check_reader(reader, artifact_format=artifact.format)
      if reader.takes_points:
          missing = [name for name in request.names if name not in request.points]
          if missing:
              raise QuantityReadError(f"the {artifact.format!r} reader samples at supplied points; none given for {missing}")
      elif request.points:
          raise QuantityReadError(
              f"the {artifact.format!r} reader samples where the solver chose, so it takes no points; "
              f"got points for {sorted(request.points)}"
          )
      by_name: dict[str, Any] = {}
      for sample in reader.read(Path(case_root), artifact, request):
          if sample.name in by_name:
              raise QuantityReadError(f"the {artifact.format!r} reader returned {sample.name!r} twice")
          by_name[sample.name] = sample
      absent = [name for name in request.names if name not in by_name]
      extra = sorted(set(by_name) - set(request.names))
      if absent or extra:
          raise QuantityReadError(
              f"the {artifact.format!r} reader did not answer the request: missing {absent}, unrequested {extra}"
          )
      quantities = []
      for name in request.names:
          sample = by_name[name]
          if sample.value in reader.sentinels:
              status, value = "not_reached", None
          elif not math.isfinite(sample.value):
              raise QuantityReadError(f"{name!r} in {artifact.path_pattern}: value {sample.value!r} is not finite")
          else:
              status, value = "evaluated", float(sample.value)
          sampled_at = tuple(float(c) for c in sample.sampled_at) if sample.sampled_at is not None else None
          quantities.append(Quantity(
              name=name, value=value, unit=reader.value_unit, status=status,
              source_artifact=artifact.path_pattern, sampled_at=sampled_at,
              sampled_at_unit=reader.coordinate_unit if sampled_at is not None else None,
              sampling_rule=reader.sampling_rule,
          ))
      return tuple(quantities)


  def converted(quantity: Quantity, to_unit: str) -> Quantity:
      """The same quantity in ``to_unit``. A quantity with no value keeps none,
      but its unit must still convert: a mismatch is refused either way."""
      if quantity.unit is None:
          return quantity
      check_convertible(quantity.unit, to_unit)
      value = None if quantity.value is None else convert(quantity.value, quantity.unit, to_unit)
      return replace(quantity, value=value, unit=to_unit)
  ```

  `quantities/__init__.py`:
  ```python
  """Results as comparable quantities (solver-neutral).

  Design: docs/superpowers/specs/2026-09-26-results-as-quantities-design.md."""
  from .errors import (
      PointReferenceError, QuantityComparisonError, QuantityError, QuantityReadError,
      ReaderDeclarationError, UnitError,
  )
  from .model import QUANTITY_STATUSES, ArtifactValueReader, Point, Quantity, RawSample, ReadRequest, not_evaluated
  from .reading import check_reader, converted, read_quantities
  from .units import UNITS, check_convertible, convert, dimension_of

  __all__ = [
      "ArtifactValueReader", "Point", "PointReferenceError", "QUANTITY_STATUSES", "Quantity",
      "QuantityComparisonError", "QuantityError", "QuantityReadError", "RawSample", "ReadRequest",
      "ReaderDeclarationError", "UNITS", "UnitError", "check_convertible", "check_reader", "convert",
      "converted", "dimension_of", "not_evaluated", "read_quantities",
  ]
  ```
  (Task 3 adds the reference and comparison names.)

- [ ] **Step 6: Give the capability its real signature**

  In `plugin_capabilities.py`, `RuntimeEvidenceCapability`:
  - Replace the docstring's first paragraph: `observable extraction will consume artifact_value_reader; both remain declaration-only for now` becomes:
    > ``artifact_value_reader(format)`` returns the reader for one artifact
    > format (``core.quantities.ArtifactValueReader``) or ``None``. A ``None``
    > makes that artifact's quantities ``not_evaluated`` with the format
    > named, never an implicit pass. Corrected 2026-09-26 (results as
    > quantities): it was declaration-only.
  - Keep "telemetry collection consumes ``solve_step_commands``/``telemetry_source_globs``" as it is.
  - Add `omnidriver/conformance/checks.py` to `:consumed-by:`.
  - Change the member's annotation to `def artifact_value_reader(self, artifact_format: str) -> "ArtifactValueReader | None": ...`, with `from .quantities.model import ArtifactValueReader` under the module's `TYPE_CHECKING` block (add one if absent).

  In `plugin_interface.py`, `get_artifact_value_reader`: annotate `-> "ArtifactValueReader | None"` and replace the docstring with:
  > The reader for one of this plugin's artifact formats, or ``None``.
  > Composed ``single`` (the most specific provider with a reader for the
  > format answers). Contract: ``core.quantities.ArtifactValueReader``.

- [ ] **Step 7: Write C11**

  In `conformance/checks.py`:
  ```python
  from omnidriver.core.quantities import ReaderDeclarationError, check_reader
  from omnidriver.core.tutorial_records import PLAIN_FILE_FORMAT


  def check_readable_quantities(target: ConformanceTarget) -> CheckVerdict:
      """C11: every record output that declares a format has a reader for it,
      through the reader contract, with a declaration core can use (results
      as quantities, spec 2026-09-26 §4). A record whose outputs declare no
      format passes and says so: not every record is compared."""
      ctx = _context(target)
      record = _record(ctx, target.record)
      formats = sorted({step.produced_format(path) for step in record.workflow_steps for path in step.produces}
                       - {PLAIN_FILE_FORMAT})
      if not formats:
          return _verdict("C12", True, "no output declares a format, so there is nothing to read")
      problems = []
      for artifact_format in formats:
          reader = ctx.capabilities.runtime_evidence.artifact_value_reader(artifact_format)
          if reader is None:
              problems.append(f"no reader for format {artifact_format!r}")
              continue
          try:
              check_reader(reader, artifact_format=artifact_format)
          except ReaderDeclarationError as exc:
              problems.append(str(exc))
      return _verdict("C12", not problems, "; ".join(problems) or f"readers for {formats}")
  ```
  Register `"C12": check_readable_quantities,` in `CHECKS`.

- [ ] **Step 8: Run the tests, regenerate the seam table, run every shape**

  ```bash
  /tmp/odB-<wt>/bin/python -m pytest packages/omnidriver/tests/core/test_quantities.py packages/omnidriver/tests/core/test_conformance_toy.py -q
  /tmp/odB-<wt>/bin/python scripts/export-capability-seams.py && /tmp/odB-<wt>/bin/python scripts/export-capability-seams.py --check
  /tmp/odBcore-<wt>/bin/python -m pytest packages/omnidriver/tests -q
  /tmp/odB-<wt>/bin/python -m pytest packages/ -q -m "not slow and not native and not native_opencarp"
  python3 scripts/check-import-boundaries.py && python3 scripts/check-core-shape.py
  ```
  Expected: 0 failed. `test_runtime_evidence.py` still passes, because every shipped plugin still returns `None`.

- [ ] **Step 9: Generality-log row and commit**

  ```
  | 2026-09-26 | results-as-quantities | `omnidriver.core.quantities`: `Quantity`, a seven-unit table, `read_quantities` (sentinels resolved before conversion), the `ArtifactValueReader` contract behind `RuntimeEvidenceCapability.artifact_value_reader` (was declaration-only), and conformance C12 | no core code read a value or compared numbers; a reader could not declare its units | neutral: no solver or physics vocabulary (shape and vocabulary gates pass); sampling rules and formats are plugin strings core only carries; every shipped plugin still returns `None`, which C11 and the comparison report as a named gap, never a pass |
  ```
  ```bash
  git add packages/omnidriver/src/omnidriver/core/quantities packages/omnidriver/src/omnidriver/core/plugin_capabilities.py packages/omnidriver/src/omnidriver/core/plugin_interface.py packages/omnidriver/src/omnidriver/conformance/checks.py packages/omnidriver/tests/plugins/quantity_toy.py packages/omnidriver/tests/core/test_quantities.py packages/omnidriver/tests/core/test_conformance_toy.py ARCHITECTURE.md docs/superpowers/plans/2026-09-25-tutorials-are-pointers-remaining.md
  git commit -m "feat(core): quantities, units and the artifact value reader contract; conformance C12

  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
  ```

---

### Task 3: The comparison: reference schema, request, report, `omnidriver compare`

**Files:**
- Create: `packages/omnidriver/src/omnidriver/schemas/point-reference.schema.json`, `quantity-comparison.schema.json`
- Create: `packages/omnidriver/src/omnidriver/core/quantities/reference.py`, `comparison.py`
- Modify: `packages/omnidriver/src/omnidriver/core/quantities/__init__.py`
- Modify: `packages/omnidriver/src/omnidriver/core/experiments.py` (`_association_status`, `ComparisonRequest` docstring)
- Modify: `packages/omnidriver/src/omnidriver/cli.py` (action `compare`, `--comparison-request`, `--report`)
- Modify: `packages/omnidriver/pyproject.toml` (package-data)
- Modify: `packages/omnidriver/src/omnidriver/core/plugin_capabilities.py` (`:consumed-by:` gains `omnidriver/core/quantities/comparison.py`)
- Modify: `packages/omnidriver/tests/plugins/quantity_toy.py` (`write_toy_sweep`, `write_toy_reference`)
- Create: `packages/omnidriver/tests/core/test_point_reference.py`, `test_quantity_comparison.py`
- Modify: `packages/omnidriver/tests/core/test_experiments.py`

**Interfaces:**
- Consumes: everything Task 2 produces; `build_sweep_context`, `CaseRecord` (`core.runtime.postprocess_phase`); `data_artifact_from_json`; `reconcile_artifacts`; `load_plugin_context`; `ComparisonRequest`, `inspect_sweep_experiment` (`core.experiments`).
- Produces:
  - reference: `ReferencePoint(label, coordinates, unresolved)`, `PointReference(reference_id, version, path, digest, quantity_name, quantity_unit, length_unit, points)`, `load_point_reference(path) -> PointReference`, `schema_errors(document, schema) -> list[str]`;
  - comparison: `CHECKER_ID = "omnidriver.quantities"`, `CHECKER_VERSION = "1"`;
    - `Tolerance(kind, value, unit, rationale)` with `.bound(left, right, unit)`, `.to_json()` and `Tolerance.from_json(raw, *, where)`;
    - `compare_pair(left, right, *, unit, tolerance) -> tuple[str, float | None, float | None]`;
    - `overall_status(statuses) -> str`;
    - `run_quantity_comparison(request_path, report_path) -> dict`;
    - `experiment_comparisons(report_path, *, sweep_output) -> tuple[ComparisonRequest, ...]`;
  - CLI: `omnidriver compare --comparison-request <request.json> --report <report.json>`. It prints the report and exits 0 once the report is written, whatever its status. A refusal prints `{"status": "failed", "action": "compare", "error": ...}` and exits 1.
  - Pair statuses: `within_tolerance`, `outside_tolerance`, `both_not_reached`, `reached_on_one_side`, `sampled_off_point`, `not_evaluated`.
  - Report status, which is the experiments envelope's vocabulary:
    - `failed` if any pair is outside tolerance, reached on one side only, or sampled off point;
    - else `unavailable` if any pair is `not_evaluated`;
    - else `passed`.

**The request an agent writes** (validated by `quantity-comparison.schema.json`):
```json
{
  "schema_version": 1,
  "reference": "benchmarks/niederer2011.json",
  "tolerance": {"kind": "absolute", "value": 5.0, "unit": "ms", "rationale": "declared before any run was read; ..."},
  "runs": {
    "coarse": {"plugin": "opencarp", "sweep_output": "/scratch/sweeps/n", "case_id": "<id>",
               "artifact_id": "record.solve.2",
               "points": {"unit": "mm", "at": {"P1": [0, 0, 0], "P8": [20, 7, 3]}},
               "max_sampling_offset": 0.001},
    "other":  {"plugin": "cardiacfoam", "sweep_output": "...", "case_id": "...", "artifact_id": "..."}
  },
  "pairs": [
    {"reference_label": "P8", "left": {"run": "coarse", "quantity": "P8"}, "right": {"run": "other", "quantity": "7"},
     "note": "probe 7 is (20, 3, 0) mm in cardiacFOAM's frame: P8 after the agent's orientation"}
  ]
}
```
- Relative `reference` and `sweep_output` paths resolve against the request file's directory.
- A pair may carry its own `tolerance`.
- `points` is required exactly when the artifact's reader takes points. It must name exactly the quantities that run's pairs use.

- [ ] **Step 1: Write the schemas**

  `schemas/point-reference.schema.json`:
  ```json
  {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "omnidriver/point-reference.schema.json",
    "title": "Point-sampling reference",
    "description": "Named points where one quantity is compared, the frame their coordinates are in, and where every fact came from. Solver-neutral. A point the source does not settle has null coordinates and says why; no comparison may use it. Tolerances are not here: they are pre-registered in each comparison request.",
    "type": "object",
    "additionalProperties": false,
    "required": ["schema_version", "id", "version", "sources", "quantity", "frame", "points"],
    "properties": {
      "schema_version": {"const": 1},
      "id": {"type": "string", "minLength": 1},
      "version": {"type": "string", "minLength": 1},
      "title": {"type": "string"},
      "sources": {"type": "array", "minItems": 1, "items": {"$ref": "#/$defs/source"}},
      "quantity": {
        "type": "object", "additionalProperties": false,
        "required": ["name", "definition", "unit", "source"],
        "properties": {
          "name": {"type": "string", "minLength": 1},
          "definition": {"type": "string", "minLength": 1},
          "unit": {"type": "string", "minLength": 1},
          "source": {"$ref": "#/$defs/citation"}
        }
      },
      "frame": {
        "type": "object", "additionalProperties": false,
        "required": ["length_unit", "definition", "stated_by_source", "source"],
        "properties": {
          "length_unit": {"type": "string", "minLength": 1},
          "definition": {"type": "string", "minLength": 1},
          "stated_by_source": {"type": "boolean"},
          "source": {"$ref": "#/$defs/citation"}
        }
      },
      "points": {"type": "array", "minItems": 1, "items": {"$ref": "#/$defs/point"}},
      "published_values": {"type": "array", "items": {"$ref": "#/$defs/published_value"}}
    },
    "$defs": {
      "citation": {
        "type": "object", "additionalProperties": false, "required": ["source_id", "where"],
        "properties": {"source_id": {"type": "string", "minLength": 1}, "where": {"type": "string", "minLength": 1}}
      },
      "source": {
        "type": "object", "additionalProperties": false, "required": ["id", "citation", "accessed"],
        "properties": {
          "id": {"type": "string", "minLength": 1},
          "citation": {"type": "string", "minLength": 1},
          "doi": {"type": "string"},
          "url": {"type": "string"},
          "retrieved": {"type": "string"},
          "accessed": {"type": "boolean"},
          "note": {"type": "string"}
        }
      },
      "point": {
        "type": "object", "additionalProperties": false,
        "required": ["label", "definition", "coordinates", "source"],
        "properties": {
          "label": {"type": "string", "minLength": 1},
          "definition": {"type": "string", "minLength": 1},
          "coordinates": {"oneOf": [
            {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
            {"type": "null"}
          ]},
          "unresolved": {"type": "string", "minLength": 1},
          "source": {"$ref": "#/$defs/citation"}
        },
        "if": {"properties": {"coordinates": {"type": "null"}}, "required": ["coordinates"]},
        "then": {"required": ["unresolved"]},
        "else": {"not": {"required": ["unresolved"]}}
      },
      "published_value": {
        "type": "object", "additionalProperties": false,
        "required": ["label", "kind", "unit", "conditions", "source"],
        "properties": {
          "label": {"type": "string", "minLength": 1},
          "kind": {"type": "string", "minLength": 1},
          "unit": {"type": "string", "minLength": 1},
          "conditions": {"type": "string", "minLength": 1},
          "value": {"type": "number"},
          "range": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2},
          "source": {"$ref": "#/$defs/citation"}
        },
        "oneOf": [{"required": ["value"]}, {"required": ["range"]}]
      }
    }
  }
  ```

  `schemas/quantity-comparison.schema.json`:
  ```json
  {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "omnidriver/quantity-comparison.schema.json",
    "title": "Quantity comparison request",
    "description": "An agent's comparison: which runs, which artifact of each, where to sample, the reference, the pairs, and the tolerance declared before any value is read. Core adds no frame conversion, pairing or tolerance of its own.",
    "type": "object",
    "additionalProperties": false,
    "required": ["schema_version", "reference", "tolerance", "runs", "pairs"],
    "properties": {
      "schema_version": {"const": 1},
      "reference": {"type": "string", "minLength": 1},
      "tolerance": {"$ref": "#/$defs/tolerance"},
      "runs": {"type": "object", "minProperties": 1, "additionalProperties": {"$ref": "#/$defs/run"}},
      "pairs": {"type": "array", "minItems": 1, "items": {"$ref": "#/$defs/pair"}}
    },
    "$defs": {
      "tolerance": {
        "type": "object", "additionalProperties": false, "required": ["kind", "value", "rationale"],
        "properties": {
          "kind": {"enum": ["absolute", "relative"]},
          "value": {"type": "number", "minimum": 0},
          "unit": {"type": "string", "minLength": 1},
          "rationale": {"type": "string", "minLength": 1}
        },
        "if": {"properties": {"kind": {"const": "absolute"}}, "required": ["kind"]},
        "then": {"required": ["unit"]},
        "else": {"not": {"required": ["unit"]}}
      },
      "run": {
        "type": "object", "additionalProperties": false,
        "required": ["plugin", "sweep_output", "case_id", "artifact_id"],
        "properties": {
          "plugin": {"type": "string", "minLength": 1},
          "sweep_output": {"type": "string", "minLength": 1},
          "case_id": {"type": "string", "minLength": 1},
          "artifact_id": {"type": "string", "minLength": 1},
          "points": {
            "type": "object", "additionalProperties": false, "required": ["unit", "at"],
            "properties": {
              "unit": {"type": "string", "minLength": 1},
              "at": {"type": "object", "minProperties": 1, "additionalProperties": {
                "type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3
              }}
            }
          },
          "max_sampling_offset": {"type": "number", "minimum": 0}
        }
      },
      "side": {
        "type": "object", "additionalProperties": false, "required": ["run", "quantity"],
        "properties": {"run": {"type": "string", "minLength": 1}, "quantity": {"type": "string", "minLength": 1}}
      },
      "pair": {
        "type": "object", "additionalProperties": false, "required": ["reference_label", "left", "right"],
        "properties": {
          "reference_label": {"type": "string", "minLength": 1},
          "left": {"$ref": "#/$defs/side"},
          "right": {"$ref": "#/$defs/side"},
          "tolerance": {"$ref": "#/$defs/tolerance"},
          "note": {"type": "string"}
        }
      }
    }
  }
  ```
  In `packages/omnidriver/pyproject.toml`, change the schemas package-data line to:
  ```toml
  "omnidriver.schemas" = ["run-document.json", "sweep-spec.schema.json", "point-reference.schema.json", "quantity-comparison.schema.json"]
  ```

- [ ] **Step 2: Write the test fixtures' writers** (append to `quantity_toy.py`)

  ```python
  import dataclasses
  import json

  from omnidriver.core.runtime.models import DataArtifact
  from omnidriver.core.runtime.sweep_manifest import CaseManifestEntry, SweepManifest, write_manifest

  _CITE = {"source_id": "toy", "where": "this file"}


  def write_toy_reference(path: Path, *, quantity_unit: str = "ms") -> Path:
      path.write_text(json.dumps({
          "schema_version": 1, "id": "toy-reference", "version": "1",
          "sources": [{"id": "toy", "citation": "the toy's own definition", "accessed": True}],
          "quantity": {"name": "first crossing", "definition": "the toy's value", "unit": quantity_unit, "source": _CITE},
          "frame": {"length_unit": "m", "definition": "the toy's frame", "stated_by_source": True, "source": _CITE},
          "points": [
              {"label": "A", "definition": "row a", "coordinates": [0, 0, 0.007], "source": _CITE},
              {"label": "B", "definition": "row b", "coordinates": [0.02, 0.003, 0], "source": _CITE},
              {"label": "Q", "definition": "not settled", "coordinates": None, "unresolved": "the toy never says", "source": _CITE},
          ],
      }))
      return path


  def write_toy_sweep(output_dir: Path, cases: Mapping[str, str | None], *, plugin: str = QUANTITY_TOY_PLUGIN,
                      status: str = "completed", artifact_format: str = VALUES_FORMAT) -> Path:
      """A sweep output in the shape sweep_run leaves: manifest, run documents
      carrying the planning stack's identity, workflow states with digests,
      and each case's ``values.txt`` (``None``: the run wrote none)."""
      from omnidriver.core.plugin_interface import load_plugin_context

      identity = load_plugin_context(plugin).identity.to_json()
      artifact = DataArtifact(artifact_id="record.solve.0", path_pattern="values.txt",
                              format=artifact_format, produced_by="solve")
      entries = []
      for case_id, text in cases.items():
          case_root = output_dir / "cases" / case_id
          case_root.mkdir(parents=True)
          if text is not None:
              (case_root / "values.txt").write_text(text)
          (case_root / "run_document.json").write_text(json.dumps({
              "plugin": identity, "launch": {"caseRoot": str(case_root)},
              "expectedArtifacts": [dataclasses.asdict(artifact)],
          }))
          (case_root / "workflow_state.json").write_text(json.dumps({
              "status": status, "workflow_digest": f"sha256:plan-{case_id}",
              "resume_snapshot": {"aggregate_digest": f"sha256:inputs-{case_id}"},
          }))
          entries.append(CaseManifestEntry(
              case_id=case_id, resolved_axis_values={}, override_hash="sha256:none",
              run_document_path=f"cases/{case_id}/run_document.json",
              workflow_state_path=f"cases/{case_id}/workflow_state.json",
              status=status, outcome="fresh", started_at=None, updated_at="2026-09-26T00:00:00+00:00",
          ))
      write_manifest(output_dir / "sweep_manifest.json", SweepManifest(
          schema_version="1.0", sweep_spec_hash="sha256:toy", created_at="2026-09-26T00:00:00+00:00",
          updated_at="2026-09-26T00:00:00+00:00", cases=entries,
      ))
      return output_dir
  ```

- [ ] **Step 3: Write the failing tests**

  `packages/omnidriver/tests/core/test_point_reference.py`:
  ```python
  """The point-sampling reference loader: form and citations, never truth."""
  from __future__ import annotations

  import json

  import pytest

  from omnidriver.core.quantities import PointReferenceError, load_point_reference
  from plugins.quantity_toy import write_toy_reference


  def _edit(path, change):
      document = json.loads(path.read_text())
      change(document)
      path.write_text(json.dumps(document))
      return path


  def test_a_reference_loads_with_its_digest_and_unresolved_points(tmp_path):
      reference = load_point_reference(write_toy_reference(tmp_path / "r.json"))
      assert (reference.reference_id, reference.quantity_unit, reference.length_unit) == ("toy-reference", "ms", "m")
      assert reference.points["A"].coordinates == (0.0, 0.0, 0.007)
      assert reference.points["Q"].coordinates is None and reference.points["Q"].unresolved == "the toy never says"
      assert reference.digest.startswith("sha256:")


  @pytest.mark.parametrize(("change", "match"), [
      (lambda d: d["points"][2].pop("unresolved"), "unresolved"),
      (lambda d: d["points"][0].update(unresolved="but it has coordinates"), "points/0"),
      (lambda d: d["points"].append(dict(d["points"][0])), "'A'.*more than once"),
      (lambda d: d["points"][0]["source"].update(source_id="elsewhere"), "'elsewhere'"),
      (lambda d: d["frame"].update(length_unit="ms"), "length"),
      (lambda d: d["quantity"].update(unit="msec"), "'msec'"),
      (lambda d: d.update(published_values=[{"label": "A", "kind": "range", "unit": "ms", "conditions": "c",
                                              "range": [2.0, 1.0], "source": {"source_id": "toy", "where": "x"}}]), "range"),
      (lambda d: d.update(published_values=[{"label": "Z", "kind": "value", "unit": "ms", "conditions": "c",
                                              "value": 1.0, "source": {"source_id": "toy", "where": "x"}}]), "'Z'"),
      (lambda d: d.update(tolerances=[]), "tolerances"),
  ])
  def test_a_malformed_reference_is_refused_by_name(tmp_path, change, match):
      path = _edit(write_toy_reference(tmp_path / "r.json"), change)
      with pytest.raises(PointReferenceError, match=match):
          load_point_reference(path)
  ```

  `packages/omnidriver/tests/core/test_quantity_comparison.py`:
  ```python
  """Comparison over agent-stated pairs: pre-registered, sentinel-aware,
  bound to run evidence, refusing before it reads (spec 2026-09-26 §3, §4)."""
  from __future__ import annotations

  import json
  import os
  import subprocess
  import sys
  from pathlib import Path

  import pytest

  from omnidriver.core.experiments import inspect_sweep_experiment
  from omnidriver.core.quantities import QuantityComparisonError, experiment_comparisons, run_quantity_comparison
  from omnidriver.core.runtime.postprocess_phase import build_sweep_context
  from plugins.quantity_toy import (
      GRID_FORMAT, QUANTITY_TOY_PLUGIN, write_quantity_toy_case, write_toy_reference, write_toy_sweep,
  )

  TESTS_ROOT = Path(__file__).resolve().parents[1]
  SAME = "a 0.0015 0 0 0.007\nb -1 0.02 0.003 0\n"
  TOL = {"kind": "absolute", "value": 0.5, "unit": "ms", "rationale": "declared before reading, for this test"}


  def _run(sweep, case_id, **extra):
      return {"plugin": QUANTITY_TOY_PLUGIN, "sweep_output": str(sweep), "case_id": case_id,
              "artifact_id": "record.solve.0", **extra}


  def _request(tmp_path, runs, pairs, *, tolerance=TOL, reference=None):
      reference = reference or write_toy_reference(tmp_path / "reference.json")
      path = tmp_path / "request.json"
      path.write_text(json.dumps({"schema_version": 1, "reference": str(reference), "tolerance": tolerance,
                                  "runs": runs, "pairs": pairs}))
      return path


  def _pair(label, left, right, lq=None, rq=None, **extra):
      return {"reference_label": label, "left": {"run": left, "quantity": lq or label.lower()},
              "right": {"run": right, "quantity": rq or label.lower()}, **extra}


  def _two_runs(tmp_path, first=SAME, second=SAME, **sweep_kwargs):
      sweep = write_toy_sweep(tmp_path / "sweep", {"one": first, "two": second}, **sweep_kwargs)
      return sweep, {"one": _run(sweep, "one"), "two": _run(sweep, "two")}


  def test_equal_runs_pass_in_the_reference_unit_with_their_evidence(tmp_path):
      sweep, runs = _two_runs(tmp_path)
      report = run_quantity_comparison(_request(tmp_path, runs, [_pair("A", "one", "two")]), tmp_path / "report.json")
      assert report["status"] == "passed"
      (metric,) = report["metrics"]
      assert metric["status"] == "within_tolerance" and metric["difference"] == 0.0 and metric["bound"] == 0.5
      assert (metric["left"]["value"], metric["left"]["unit"], metric["left"]["declared_unit"]) == (pytest.approx(1.5), "ms", "s")
      assert (metric["left"]["sampled_at"], metric["left"]["sampled_at_unit"], metric["left"]["sampling_rule"]) == ([0.0, 0.0, 0.007], "m", "toy-row")
      assert metric["reference_coordinates"] == [0, 0, 0.007]
      assert {e["case_id"] for e in report["run_evidence"]} == {"one", "two"}
      assert report["request"]["digest"].startswith("sha256:")
      assert json.loads((tmp_path / "report.json").read_text()) == report


  def test_a_difference_beyond_the_tolerance_fails(tmp_path):
      sweep, runs = _two_runs(tmp_path, second="a 0.0025 0 0 0.007\nb -1 0.02 0.003 0\n")
      report = run_quantity_comparison(_request(tmp_path, runs, [_pair("A", "one", "two")]), tmp_path / "report.json")
      assert report["status"] == "failed"
      assert report["metrics"][0]["status"] == "outside_tolerance"
      assert report["metrics"][0]["difference"] == pytest.approx(1.0)


  def test_a_relative_tolerance_scales_with_the_larger_value(tmp_path):
      sweep, runs = _two_runs(tmp_path, second="a 0.00155 0 0 0.007\nb -1 0.02 0.003 0\n")
      tolerance = {"kind": "relative", "value": 0.05, "rationale": "five per cent, declared before reading"}
      report = run_quantity_comparison(_request(tmp_path, runs, [_pair("A", "one", "two")], tolerance=tolerance),
                                       tmp_path / "report.json")
      assert report["metrics"][0]["status"] == "within_tolerance"
      assert report["metrics"][0]["bound"] == pytest.approx(0.05 * 1.55)


  def test_sentinels_compare_as_statements_not_numbers(tmp_path):
      sweep, runs = _two_runs(tmp_path, second="a -1 0 0 0.007\nb -1 0.02 0.003 0\n")
      report = run_quantity_comparison(_request(tmp_path, runs, [_pair("A", "one", "two"), _pair("B", "one", "two")]),
                                       tmp_path / "report.json")
      by_label = {m["reference_label"]: m for m in report["metrics"]}
      assert by_label["B"]["status"] == "both_not_reached" and by_label["B"]["left"]["value"] is None
      assert by_label["A"]["status"] == "reached_on_one_side"
      assert report["status"] == "failed"


  def test_a_missing_artifact_is_not_evaluated_with_its_reason(tmp_path):
      sweep, runs = _two_runs(tmp_path, second=None)
      report = run_quantity_comparison(_request(tmp_path, runs, [_pair("A", "one", "two")]), tmp_path / "report.json")
      assert report["status"] == "unavailable"
      right = report["metrics"][0]["right"]
      assert right["status"] == "not_evaluated" and "missing" in right["reason"]


  def test_a_report_is_written_once(tmp_path):
      sweep, runs = _two_runs(tmp_path)
      request = _request(tmp_path, runs, [_pair("A", "one", "two")])
      run_quantity_comparison(request, tmp_path / "report.json")
      with pytest.raises(QuantityComparisonError, match="already exists"):
          run_quantity_comparison(request, tmp_path / "report.json")


  @pytest.mark.parametrize(("edit", "match"), [
      (lambda runs, pairs: pairs.append(_pair("Q", "one", "two", "a", "a")), "'Q'.*the toy never says"),
      (lambda runs, pairs: pairs.append(_pair("Z", "one", "two", "a", "a")), "'Z'"),
      (lambda runs, pairs: pairs.append(_pair("A", "one", "three")), "'three'"),
      (lambda runs, pairs: pairs.append(_pair("A", "one", "one")), "itself"),
      (lambda runs, pairs: runs["one"].update(case_id="nine"), "'nine'"),
      (lambda runs, pairs: runs["one"].update(artifact_id="record.solve.7"), "record.solve.7"),
      (lambda runs, pairs: runs["one"].update(points={"unit": "m", "at": {"a": [0, 0, 0]}}), "takes no points"),
      (lambda runs, pairs: runs.update(spare=dict(runs["one"])), "'spare'.*no pair"),
  ])
  def test_a_malformed_request_is_refused_before_anything_is_read(tmp_path, edit, match):
      sweep, runs = _two_runs(tmp_path)
      pairs = [_pair("A", "one", "two")]
      edit(runs, pairs)
      with pytest.raises(QuantityComparisonError, match=match):
          run_quantity_comparison(_request(tmp_path, runs, pairs), tmp_path / "report.json")
      assert not (tmp_path / "report.json").exists()


  def test_a_tolerance_in_the_wrong_dimension_is_refused(tmp_path):
      sweep, runs = _two_runs(tmp_path)
      tolerance = {"kind": "absolute", "value": 1.0, "unit": "mm", "rationale": "wrong on purpose"}
      with pytest.raises(QuantityComparisonError, match="'mm'"):
          run_quantity_comparison(_request(tmp_path, runs, [_pair("A", "one", "two")], tolerance=tolerance),
                                  tmp_path / "report.json")


  def test_a_reader_unit_that_cannot_become_the_reference_unit_is_refused(tmp_path):
      sweep, runs = _two_runs(tmp_path)
      reference = write_toy_reference(tmp_path / "reference.json", quantity_unit="mm")
      tolerance = {"kind": "absolute", "value": 1.0, "unit": "mm", "rationale": "length reference, time reader"}
      with pytest.raises(QuantityComparisonError, match="run 'one'.*'s'.*'mm'"):
          run_quantity_comparison(_request(tmp_path, runs, [_pair("A", "one", "two")], tolerance=tolerance,
                                           reference=reference), tmp_path / "report.json")


  def test_a_run_planned_with_another_stack_is_refused(tmp_path):
      sweep = write_toy_sweep(tmp_path / "sweep", {"one": SAME, "two": SAME},
                              plugin="plugins.e2e_record_plugin:E2ERecordPlugin")
      runs = {"one": _run(sweep, "one"), "two": _run(sweep, "two")}
      with pytest.raises(QuantityComparisonError, match="was planned with"):
          run_quantity_comparison(_request(tmp_path, runs, [_pair("A", "one", "two")]), tmp_path / "report.json")


  def test_points_are_converted_to_the_reader_unit_and_an_off_point_sample_fails(tmp_path):
      grid = "0 0 0 1.0\n1 0 0 2.0\n"
      sweep = write_toy_sweep(tmp_path / "sweep", {"one": grid, "two": grid}, artifact_format=GRID_FORMAT)
      points = {"unit": "m", "at": {"a": [0.0009, 0, 0]}}
      runs = {"one": _run(sweep, "one", points=points), "two": _run(sweep, "two", points=points, max_sampling_offset=0.00005)}
      report = run_quantity_comparison(_request(tmp_path, runs, [_pair("A", "one", "two")]), tmp_path / "report.json")
      (metric,) = report["metrics"]
      assert metric["left"]["requested_at"] == [pytest.approx(0.9), 0.0, 0.0]
      assert metric["left"]["sampled_at"] == [1.0, 0.0, 0.0] and metric["left"]["sampled_at_unit"] == "mm"
      assert metric["right"]["sampling_offset"] == pytest.approx(0.1)
      assert metric["status"] == "sampled_off_point" and report["status"] == "failed"


  def test_the_report_attaches_to_each_run_in_the_experiment_envelope(tmp_path):
      sweep, runs = _two_runs(tmp_path)
      report_path = tmp_path / "report.json"
      run_quantity_comparison(_request(tmp_path, runs, [_pair("A", "one", "two")]), report_path)
      experiment = inspect_sweep_experiment(sweep, comparisons=experiment_comparisons(report_path, sweep_output=sweep))
      assert {case.comparison.association_status for case in experiment.cases} == {"run_verified"}
      assert {case.comparison.status for case in experiment.cases} == {"passed"}
      assert {case.comparison.checker_id for case in experiment.cases} == {"omnidriver.quantities"}


  def test_an_agent_compares_two_real_runs_through_the_cli(tmp_path):
      """End to end: sweep-run the toy record, then `omnidriver compare`."""
      cases_root = tmp_path / "native"
      write_quantity_toy_case(cases_root, SAME)
      spec = tmp_path / "sweep.json"
      spec.write_text(json.dumps({"base": {"entry": "toyQuantities", "cases_root": str(cases_root)},
                                  "sweep": {"mode": "cross_product", "independent": {"number_cells": [2, 3]}}}))
      env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(TESTS_ROOT), os.environ.get("PYTHONPATH", "")])}
      out = tmp_path / "sweep"
      swept = subprocess.run(
          [sys.executable, "-m", "omnidriver", "sweep-run", "--plugin", QUANTITY_TOY_PLUGIN, "--spec", str(spec),
           "--output-dir", str(out), "--scratch-dir", str(tmp_path / "scratch")],
          capture_output=True, text=True, env=env,
      )
      assert swept.returncode == 0, swept.stdout[-2000:] + swept.stderr[-2000:]
      first, second = sorted(case.case_id for case in build_sweep_context(out).cases)
      request = _request(tmp_path, {"two": _run(out, first), "three": _run(out, second)},
                         [_pair("A", "two", "three"), _pair("B", "two", "three")])
      report_path = tmp_path / "report.json"
      command = [sys.executable, "-m", "omnidriver", "compare", "--comparison-request", str(request), "--report", str(report_path)]
      compared = subprocess.run(command, capture_output=True, text=True, env=env)
      assert compared.returncode == 0, compared.stdout[-2000:] + compared.stderr[-2000:]
      report = json.loads(report_path.read_text())
      assert report["status"] == "passed"
      by_label = {m["reference_label"]: m for m in report["metrics"]}
      assert by_label["A"]["left"]["value"] == pytest.approx(1.5) and by_label["B"]["status"] == "both_not_reached"
      experiment = inspect_sweep_experiment(out, comparisons=experiment_comparisons(report_path, sweep_output=out))
      assert {case.comparison.association_status for case in experiment.cases} == {"run_verified"}
      again = subprocess.run(command, capture_output=True, text=True, env=env)
      assert again.returncode == 1 and "already exists" in json.loads(again.stdout)["error"]
  ```

  Append to `packages/omnidriver/tests/core/test_experiments.py`:
  ```python
  def test_a_report_comparing_several_runs_verifies_each_by_its_own_evidence(tmp_path: Path) -> None:
      _manifest(tmp_path, [_case(tmp_path, "a", status="completed")])
      report = tmp_path / "reports" / "multi.json"
      report.parent.mkdir()
      report.write_text(json.dumps({"status": "failed", "run_evidence": [
          {"case_id": "elsewhere", "workflow_digest": "sha256:x", "input_provenance_digest": "sha256:y"},
          {"case_id": "a", "workflow_digest": "sha256:plan-a", "input_provenance_digest": "sha256:inputs-a"},
      ]}))
      experiment = inspect_sweep_experiment(tmp_path, comparisons=[ComparisonRequest(
          case_id="a", checker_id="omnidriver.quantities", checker_version="1",
          reference_id="r", reference_version="1", report_path="reports/multi.json",
      )])
      assert experiment.cases[0].comparison.association_status == "run_verified"


  def test_a_run_evidence_list_without_this_case_is_unverified(tmp_path: Path) -> None:
      _manifest(tmp_path, [_case(tmp_path, "a", status="completed")])
      report = tmp_path / "reports" / "multi.json"
      report.parent.mkdir()
      report.write_text(json.dumps({"status": "passed", "run_evidence": [
          {"case_id": "a", "workflow_digest": "sha256:another-plan", "input_provenance_digest": "sha256:inputs-a"},
      ]}))
      experiment = inspect_sweep_experiment(tmp_path, comparisons=[ComparisonRequest(
          case_id="a", checker_id="c", checker_version="1", reference_id="r", reference_version="1",
          report_path="reports/multi.json",
      )])
      assert experiment.cases[0].comparison.association_status == "unverified"
  ```

- [ ] **Step 4: Run them to verify they fail**

  Run: `/tmp/odB-<wt>/bin/python -m pytest packages/omnidriver/tests/core/test_point_reference.py packages/omnidriver/tests/core/test_quantity_comparison.py packages/omnidriver/tests/core/test_experiments.py -q`
  
  Expected:
  - an import error for `load_point_reference` / `run_quantity_comparison`;
  - in `test_experiments.py`, only the list test fails (`unverified` != `run_verified`).

- [ ] **Step 5: Implement the reference loader**

  `quantities/reference.py`:
  ```python
  """A point-sampling reference: named points, and where every fact came from.

  Schema: ``omnidriver/schemas/point-reference.schema.json`` (packaged). The
  loader checks form and citations, and computes nothing. Whether a value is
  the source's own is a review question, answered by each file's ``sources``.
  A point the source does not settle has ``coordinates: null`` and says why;
  the comparison refuses to use it.
  """
  from __future__ import annotations

  import hashlib
  import json
  from dataclasses import dataclass
  from importlib import resources
  from pathlib import Path
  from typing import Any, Iterator, Mapping

  import jsonschema

  from .errors import PointReferenceError, UnitError
  from .model import Point
  from .units import check_convertible, dimension_of

  _SCHEMA = json.loads(resources.files("omnidriver.schemas").joinpath("point-reference.schema.json").read_text())


  @dataclass(frozen=True)
  class ReferencePoint:
      label: str
      coordinates: Point | None
      unresolved: str | None


  @dataclass(frozen=True)
  class PointReference:
      reference_id: str
      version: str
      path: str
      digest: str
      quantity_name: str
      quantity_unit: str
      length_unit: str
      points: Mapping[str, ReferencePoint]


  def schema_errors(document: Any, schema: Mapping[str, Any]) -> list[str]:
      validator = jsonschema.Draft202012Validator(schema)
      return sorted(
          f"{'/'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
          for error in validator.iter_errors(document)
      )


  def _citations(document: Mapping[str, Any]) -> Iterator[tuple[str, Mapping[str, str]]]:
      yield "quantity", document["quantity"]["source"]
      yield "frame", document["frame"]["source"]
      for point in document["points"]:
          yield f"point {point['label']!r}", point["source"]
      for index, value in enumerate(document.get("published_values", ())):
          yield f"published value {index}", value["source"]


  def load_point_reference(path: str | Path) -> PointReference:
      path = Path(path)
      try:
          raw = path.read_bytes()
          document = json.loads(raw)
      except (OSError, json.JSONDecodeError) as exc:
          raise PointReferenceError(f"cannot read the reference {path}: {exc}") from exc
      errors = schema_errors(document, _SCHEMA)
      if errors:
          raise PointReferenceError(f"{path} is not a point reference: " + "; ".join(errors))
      source_ids = [source["id"] for source in document["sources"]]
      if len(set(source_ids)) != len(source_ids):
          raise PointReferenceError(f"{path}: source ids repeat: {source_ids}")
      for where, citation in _citations(document):
          if citation["source_id"] not in source_ids:
              raise PointReferenceError(
                  f"{path}: {where} cites {citation['source_id']!r}, which 'sources' does not declare ({source_ids})"
              )
      labels = [point["label"] for point in document["points"]]
      repeated = sorted({label for label in labels if labels.count(label) > 1})
      if repeated:
          raise PointReferenceError(f"{path}: point {repeated[0]!r} is declared more than once")
      unit = document["quantity"]["unit"]
      try:
          dimension_of(unit)
          if dimension_of(document["frame"]["length_unit"]) != "length":
              raise PointReferenceError(f"{path}: frame length_unit {document['frame']['length_unit']!r} is not a length")
          for value in document.get("published_values", ()):
              check_convertible(value["unit"], unit)
      except UnitError as exc:
          raise PointReferenceError(f"{path}: {exc}") from exc
      for value in document.get("published_values", ()):
          if value["label"] not in labels:
              raise PointReferenceError(f"{path}: a published value names point {value['label']!r}, which is not declared")
          if "range" in value and value["range"][0] > value["range"][1]:
              raise PointReferenceError(f"{path}: published range {value['range']} for {value['label']!r} is reversed")
      points = {
          point["label"]: ReferencePoint(
              label=point["label"],
              coordinates=tuple(float(c) for c in point["coordinates"]) if point["coordinates"] is not None else None,
              unresolved=point.get("unresolved"),
          )
          for point in document["points"]
      }
      return PointReference(
          reference_id=document["id"], version=document["version"], path=str(path),
          digest="sha256:" + hashlib.sha256(raw).hexdigest(), quantity_name=document["quantity"]["name"],
          quantity_unit=unit, length_unit=document["frame"]["length_unit"], points=points,
      )
  ```
  The `tolerances` test case is refused by the schema's `additionalProperties: false` (the error names `tolerances`).

- [ ] **Step 6: Implement the comparison**

  `quantities/comparison.py`:
  ```python
  """Compare quantities read from runs, over pairs an agent states.

  Design: docs/superpowers/specs/2026-09-26-results-as-quantities-design.md.
  Everything comes from the agent's request: which runs, which artifact of
  each, where to sample (for a reader that samples at points), which
  reference, which pairs, and the tolerance, declared before any value is
  read. Core adds no frame conversion, pairing or tolerance of its own
  (owner, 2026-09-26). The report shows every value with its unit, sampling
  rule, sampled location and requested point, so a wrong pairing or
  orientation is visible.

  Order, so that nothing is decided after a value is seen:
  1. the request and the reference are validated and digested;
  2. every run's evidence, stack, artifact and reader are resolved, and every
     unit is checked convertible. A refusal here reads no artifact;
  3. artifacts are read (sentinels resolved, then units converted) and the
     pairs compared, location first, then value;
  4. the report is written once, to a path that must not exist.

  The report is a checker report for ``experiments.inspect_sweep_experiment``:
  ``status``, ``metrics`` (one per pair) and ``run_evidence`` (one per run).
  """
  from __future__ import annotations

  import hashlib
  import json
  import math
  import os
  from dataclasses import dataclass
  from importlib import resources
  from pathlib import Path
  from typing import Any, Iterable, Mapping

  from ..experiments import ComparisonRequest
  from ..plugin_interface import load_plugin_context
  from ..runtime.models import DataArtifact, data_artifact_from_json
  from ..runtime.postprocess_phase import CaseRecord, build_sweep_context
  from ..runtime.reconciler import reconcile_artifacts
  from .errors import QuantityComparisonError, QuantityError
  from .model import Point, Quantity, ReadRequest, not_evaluated
  from .reading import check_reader, converted, read_quantities
  from .reference import PointReference, load_point_reference, schema_errors
  from .units import check_convertible, convert

  CHECKER_ID = "omnidriver.quantities"
  CHECKER_VERSION = "1"
  _FAILING = frozenset({"outside_tolerance", "reached_on_one_side", "sampled_off_point"})
  _REQUEST_SCHEMA = json.loads(
      resources.files("omnidriver.schemas").joinpath("quantity-comparison.schema.json").read_text()
  )


  @dataclass(frozen=True)
  class Tolerance:
      kind: str
      value: float
      unit: str | None
      rationale: str

      @classmethod
      def from_json(cls, raw: Mapping[str, Any], *, where: str, reference_unit: str) -> "Tolerance":
          tolerance = cls(kind=raw["kind"], value=float(raw["value"]), unit=raw.get("unit"), rationale=raw["rationale"])
          if tolerance.unit is not None:
              try:
                  check_convertible(tolerance.unit, reference_unit)
              except QuantityError as exc:
                  raise QuantityComparisonError(f"{where}: tolerance unit {tolerance.unit!r}: {exc}") from exc
          return tolerance

      def bound(self, left: float, right: float, unit: str) -> float:
          if self.kind == "absolute":
              return convert(self.value, self.unit, unit)
          return self.value * max(abs(left), abs(right))

      def to_json(self) -> dict[str, Any]:
          payload = {"kind": self.kind, "value": self.value, "rationale": self.rationale}
          if self.unit is not None:
              payload["unit"] = self.unit
          return payload


  def compare_pair(left: Quantity, right: Quantity, *, unit: str, tolerance: Tolerance) -> tuple[str, float | None, float | None]:
      """``(status, difference, bound)``, both numbers in ``unit``."""
      a, b = converted(left, unit), converted(right, unit)
      if "not_evaluated" in (a.status, b.status):
          return "not_evaluated", None, None
      if a.status == b.status == "not_reached":
          return "both_not_reached", None, None
      if "not_reached" in (a.status, b.status):
          return "reached_on_one_side", None, None
      difference = abs(a.value - b.value)
      bound = tolerance.bound(a.value, b.value, unit)
      return ("within_tolerance" if difference <= bound else "outside_tolerance"), difference, bound


  def overall_status(statuses: Iterable[str]) -> str:
      statuses = tuple(statuses)
      if any(status in _FAILING for status in statuses):
          return "failed"
      if "not_evaluated" in statuses:
          return "unavailable"
      return "passed"


  @dataclass(frozen=True)
  class _Pair:
      reference_label: str
      left_run: str
      left_quantity: str
      right_run: str
      right_quantity: str
      tolerance: Tolerance
      note: str | None


  @dataclass(frozen=True)
  class _Run:
      name: str
      plugin: str
      stack: tuple[str, ...]
      sweep_output: Path
      case: CaseRecord
      artifact: DataArtifact
      reader: Any | None
      points: Mapping[str, Point]
      max_offset: float | None
      evidence: dict[str, str] | None


  def _resolve(base: Path, raw: str) -> Path:
      path = Path(raw)
      return path if path.is_absolute() else base / path


  def _json_object(path: Path) -> dict[str, Any]:
      try:
          payload = json.loads(path.read_text())
      except (OSError, json.JSONDecodeError):
          return {}
      return payload if isinstance(payload, dict) else {}


  def _pairs(request: Mapping[str, Any], reference: PointReference, default: Tolerance) -> tuple[_Pair, ...]:
      pairs = []
      for index, raw in enumerate(request["pairs"]):
          label = raw["reference_label"]
          point = reference.points.get(label)
          if point is None:
              raise QuantityComparisonError(f"pair {index} names {label!r}; reference {reference.reference_id!r} has {sorted(reference.points)}")
          if point.coordinates is None:
              raise QuantityComparisonError(
                  f"pair {index} names {label!r}, which reference {reference.reference_id!r} leaves unresolved: {point.unresolved}"
              )
          for side in ("left", "right"):
              if raw[side]["run"] not in request["runs"]:
                  raise QuantityComparisonError(f"pair {index} {side} names run {raw[side]['run']!r}; the request has {sorted(request['runs'])}")
          if raw["left"] == raw["right"]:
              raise QuantityComparisonError(f"pair {index} compares {raw['left']} with itself")
          tolerance = default if "tolerance" not in raw else Tolerance.from_json(
              raw["tolerance"], where=f"pair {index}", reference_unit=reference.quantity_unit)
          pairs.append(_Pair(label, raw["left"]["run"], raw["left"]["quantity"], raw["right"]["run"],
                             raw["right"]["quantity"], tolerance, raw.get("note")))
      return tuple(pairs)


  def _artifact(name: str, document: Mapping[str, Any], artifact_id: str) -> DataArtifact:
      declared = [raw for raw in document.get("expectedArtifacts", ()) if isinstance(raw, dict)]
      for raw in declared:
          if raw.get("artifact_id") == artifact_id:
              artifact = data_artifact_from_json(raw)
              if "{" in artifact.path_pattern:
                  raise QuantityComparisonError(
                      f"run {name!r}: artifact {artifact_id!r} has the pattern {artifact.path_pattern!r}; a quantity is read from one literal path"
                  )
              return artifact
      raise QuantityComparisonError(
          f"run {name!r}: the run declares no artifact {artifact_id!r}; it declares {[raw.get('artifact_id') for raw in declared]}"
      )


  def _points(name: str, raw: Mapping[str, Any], reader: Any, names: tuple[str, ...]) -> tuple[Mapping[str, Point], float | None]:
      supplied = raw.get("points")
      if not reader.takes_points:
          if supplied is not None or raw.get("max_sampling_offset") is not None:
              raise QuantityComparisonError(
                  f"run {name!r}: this artifact's reader ({reader.sampling_rule!r}) samples where the solver chose, so it takes no points; remove 'points' and 'max_sampling_offset'"
              )
          return {}, None
      if supplied is None:
          raise QuantityComparisonError(f"run {name!r}: this artifact's reader samples at supplied points; give 'points' for {list(names)}")
      if set(supplied["at"]) != set(names):
          raise QuantityComparisonError(f"run {name!r}: points are given for {sorted(supplied['at'])}, but its pairs use {sorted(names)}")
      try:
          points = {label: tuple(convert(float(v), supplied["unit"], reader.coordinate_unit) for v in xyz)
                    for label, xyz in supplied["at"].items()}
          offset = raw.get("max_sampling_offset")
          max_offset = None if offset is None else convert(float(offset), supplied["unit"], reader.coordinate_unit)
      except QuantityError as exc:
          raise QuantityComparisonError(f"run {name!r}: {exc}") from exc
      return points, max_offset


  def _run_evidence(case: CaseRecord) -> dict[str, str] | None:
      state = _json_object(Path(case.workflow_state_path))
      snapshot = state.get("resume_snapshot")
      digest = state.get("workflow_digest")
      aggregate = snapshot.get("aggregate_digest") if isinstance(snapshot, Mapping) else None
      if not isinstance(digest, str) or not isinstance(aggregate, str):
          return None
      return {"case_id": case.case_id, "workflow_digest": digest, "input_provenance_digest": aggregate}


  def _resolve_run(name: str, raw: Mapping[str, Any], *, base: Path, reference_unit: str, names: tuple[str, ...]) -> _Run:
      sweep_output = _resolve(base, raw["sweep_output"])
      try:
          context = build_sweep_context(sweep_output)
      except (OSError, ValueError, KeyError) as exc:
          raise QuantityComparisonError(f"run {name!r}: {sweep_output} is not a readable sweep output: {exc}") from exc
      case = next((c for c in context.cases if c.case_id == raw["case_id"]), None)
      if case is None:
          raise QuantityComparisonError(
              f"run {name!r}: sweep {sweep_output} has no case {raw['case_id']!r}; it has {sorted(c.case_id for c in context.cases)}"
          )
      document = _json_object(_resolve(sweep_output, case.run_document_path or ""))
      if not document:
          raise QuantityComparisonError(f"run {name!r}: case {case.case_id!r} has no readable run document")
      try:
          ctx = load_plugin_context(raw["plugin"])
      except Exception as exc:  # a plugin that does not load is refused by name
          raise QuantityComparisonError(f"run {name!r}: plugin {raw['plugin']!r} does not load: {type(exc).__name__}: {exc}") from exc
      stack = tuple(p["id"] for p in ctx.identity.to_json()["providers"])
      recorded = tuple(p.get("id") for p in (document.get("plugin") or {}).get("providers", ()))
      if recorded != stack:
          raise QuantityComparisonError(
              f"run {name!r}: plugin {raw['plugin']!r} loads the stack {list(stack)}, but case {case.case_id!r} was planned with {list(recorded) or 'no recorded stack'}"
          )
      artifact = _artifact(name, document, raw["artifact_id"])
      reader = ctx.capabilities.runtime_evidence.artifact_value_reader(artifact.format)
      points: Mapping[str, Point] = {}
      max_offset = None
      if reader is not None:
          try:
              check_reader(reader, artifact_format=artifact.format)
              check_convertible(reader.value_unit, reference_unit)
          except QuantityError as exc:
              raise QuantityComparisonError(f"run {name!r}: {exc}") from exc
          points, max_offset = _points(name, raw, reader, names)
      return _Run(name, raw["plugin"], stack, sweep_output, case, artifact, reader, points, max_offset, _run_evidence(case))


  def _quantities(run: _Run, names: tuple[str, ...]) -> dict[str, Quantity]:
      source = run.artifact.path_pattern

      def gap(reason: str) -> dict[str, Quantity]:
          return {q.name: q for q in not_evaluated(names, source_artifact=source, reason=reason)}

      if run.case.status != "completed":
          return gap(f"case {run.case.case_id!r} did not complete (status {run.case.status!r})")
      if run.reader is None:
          return gap(f"the stack has no reader for format {run.artifact.format!r} (artifact {run.artifact.artifact_id!r})")
      if run.case.case_root is None:
          return gap(f"the run document of case {run.case.case_id!r} records no caseRoot")
      case_root = _resolve(run.sweep_output, run.case.case_root)
      entry = reconcile_artifacts(case_root, (run.artifact,), case_id=run.case.case_id).artifacts[0]
      if entry["status"] != "matched":
          return gap(f"artifact {run.artifact.artifact_id!r} ({source}) is missing under {case_root}")
      try:
          read = read_quantities(run.reader, case_root, run.artifact, ReadRequest(names=names, points=run.points))
      except ValueError as exc:  # a reader refuses by ValueError, naming why
          return gap(f"the reader refused: {exc}")
      return {q.name: q for q in read}


  def _side(run: _Run, quantity: Quantity, unit: str) -> dict[str, Any]:
      shown = converted(quantity, unit)
      requested = run.points.get(quantity.name)
      offset = math.dist(requested, quantity.sampled_at) if requested is not None and quantity.sampled_at is not None else None
      return {
          "run": run.name, "quantity": quantity.name, "status": shown.status, "value": shown.value,
          "unit": shown.unit, "declared_unit": quantity.unit, "sampling_rule": quantity.sampling_rule,
          "sampled_at": list(quantity.sampled_at) if quantity.sampled_at is not None else None,
          "sampled_at_unit": quantity.sampled_at_unit,
          "requested_at": list(requested) if requested is not None else None,
          "sampling_offset": offset, "source_artifact": quantity.source_artifact, "reason": quantity.reason,
      }


  def _metric(pair: _Pair, runs: Mapping[str, _Run], quantities: Mapping[str, Mapping[str, Quantity]],
              reference: PointReference) -> dict[str, Any]:
      unit = reference.quantity_unit
      left_run, right_run = runs[pair.left_run], runs[pair.right_run]
      left_q, right_q = quantities[pair.left_run][pair.left_quantity], quantities[pair.right_run][pair.right_quantity]
      status, difference, bound = compare_pair(left_q, right_q, unit=unit, tolerance=pair.tolerance)
      left, right = _side(left_run, left_q, unit), _side(right_run, right_q, unit)
      if any(run.max_offset is not None and side["sampling_offset"] is not None and side["sampling_offset"] > run.max_offset
             for run, side in ((left_run, left), (right_run, right))):
          status = "sampled_off_point"  # location is checked before value
      return {
          "reference_label": pair.reference_label,
          "reference_coordinates": list(reference.points[pair.reference_label].coordinates),
          "reference_length_unit": reference.length_unit, "status": status, "unit": unit,
          "difference": difference, "bound": bound, "tolerance": pair.tolerance.to_json(),
          "left": left, "right": right, "note": pair.note,
      }


  def _run_json(run: _Run) -> dict[str, Any]:
      reader = run.reader
      return {
          "plugin": run.plugin, "stack": list(run.stack), "sweep_output": str(run.sweep_output),
          "case_id": run.case.case_id, "execution_status": run.case.status,
          "artifact_id": run.artifact.artifact_id, "artifact_path": run.artifact.path_pattern,
          "artifact_format": run.artifact.format, "max_sampling_offset": run.max_offset,
          "reader": None if reader is None else {
              "value_unit": reader.value_unit, "sampling_rule": reader.sampling_rule,
              "coordinate_unit": reader.coordinate_unit, "takes_points": reader.takes_points,
              "sentinels": sorted(reader.sentinels),
          },
      }


  def _write_once(path: Path, report: Mapping[str, Any]) -> None:
      path.parent.mkdir(parents=True, exist_ok=True)
      temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
      temporary.write_text(json.dumps(report, indent=2) + "\n")
      try:
          os.link(temporary, path)
      except FileExistsError:
          raise QuantityComparisonError(
              f"report {path} already exists; a report is written once, and a changed request is a new report"
          ) from None
      finally:
          temporary.unlink()


  def run_quantity_comparison(request_path: str | Path, report_path: str | Path) -> dict[str, Any]:
      """Read, compare and report, once. Raises ``QuantityComparisonError``,
      naming why, for anything refused before the report is written."""
      request_path, report_path = Path(request_path), Path(report_path)
      if report_path.exists():
          raise QuantityComparisonError(
              f"report {report_path} already exists; a report is written once, and a changed request is a new report"
          )
      try:
          raw_bytes = request_path.read_bytes()
          request = json.loads(raw_bytes)
      except (OSError, json.JSONDecodeError) as exc:
          raise QuantityComparisonError(f"cannot read the comparison request {request_path}: {exc}") from exc
      errors = schema_errors(request, _REQUEST_SCHEMA)
      if errors:
          raise QuantityComparisonError(f"{request_path} is not a comparison request: " + "; ".join(errors))
      base = request_path.parent
      try:
          reference = load_point_reference(_resolve(base, request["reference"]))
      except QuantityError as exc:
          raise QuantityComparisonError(str(exc)) from exc
      default = Tolerance.from_json(request["tolerance"], where="the request", reference_unit=reference.quantity_unit)
      pairs = _pairs(request, reference, default)
      names_by_run: dict[str, list[str]] = {}
      for pair in pairs:
          for run_name, quantity in ((pair.left_run, pair.left_quantity), (pair.right_run, pair.right_quantity)):
              names = names_by_run.setdefault(run_name, [])
              if quantity not in names:
                  names.append(quantity)
      unused = sorted(set(request["runs"]) - set(names_by_run))
      if unused:
          raise QuantityComparisonError(f"run {unused[0]!r} is named but no pair uses it")
      runs = {
          name: _resolve_run(name, raw, base=base, reference_unit=reference.quantity_unit, names=tuple(names_by_run[name]))
          for name, raw in request["runs"].items()
      }
      # Nothing above read an artifact; everything below does.
      quantities = {name: _quantities(run, tuple(names_by_run[name])) for name, run in runs.items()}
      metrics = [_metric(pair, runs, quantities, reference) for pair in pairs]
      report = {
          "schema_version": 1,
          "status": overall_status(metric["status"] for metric in metrics),
          "checker": {"id": CHECKER_ID, "version": CHECKER_VERSION},
          "reference": {"id": reference.reference_id, "version": reference.version, "path": reference.path,
                        "digest": reference.digest, "quantity": reference.quantity_name, "unit": reference.quantity_unit},
          "request": {"path": str(request_path), "digest": "sha256:" + hashlib.sha256(raw_bytes).hexdigest()},
          "run_evidence": [run.evidence for run in runs.values() if run.evidence is not None],
          "runs": {name: _run_json(run) for name, run in runs.items()},
          "metrics": metrics,
      }
      _write_once(report_path, report)
      return report


  def experiment_comparisons(report_path: str | Path, *, sweep_output: str | Path) -> tuple[ComparisonRequest, ...]:
      """The requests that attach one written report to every case it compared
      in one sweep (``experiments.inspect_sweep_experiment(..., comparisons=)``)."""
      report_path = Path(report_path).resolve()
      report = json.loads(report_path.read_text())
      target = Path(sweep_output).resolve()
      by_case: dict[str, ComparisonRequest] = {}
      for run in report["runs"].values():
          if Path(run["sweep_output"]).resolve() == target:
              by_case[run["case_id"]] = ComparisonRequest(
                  case_id=run["case_id"], checker_id=report["checker"]["id"], checker_version=report["checker"]["version"],
                  reference_id=report["reference"]["id"], reference_version=report["reference"]["version"],
                  report_path=str(report_path),
              )
      return tuple(by_case.values())
  ```

  Add to `quantities/__init__.py`:
  ```python
  from .comparison import (
      CHECKER_ID, CHECKER_VERSION, Tolerance, compare_pair, experiment_comparisons, overall_status,
      run_quantity_comparison,
  )
  from .reference import PointReference, ReferencePoint, load_point_reference, schema_errors
  ```
  Extend `__all__` with these ten names.
  
  If importing `comparison` from `__init__` makes an import cycle (`experiments` imports `runtime.sweep_runner`), keep the names in `__all__` and load `comparison` lazily with a module `__getattr__`. Record why in a comment. Do not restructure `experiments.py`.

- [ ] **Step 7: Let `run_evidence` be a list in the envelope**

  In `experiments.py`, `_association_status`, after `expected` is built and before the mapping check:
  ```python
      if isinstance(evidence, list):
          # A report comparing several runs (core.quantities, added 2026-09-26)
          # lists one evidence object per run; this case is verified when
          # exactly one entry carries all three of its identifiers.
          matches = [item for item in evidence if isinstance(item, Mapping)
                     and all(item.get(key) == value for key, value in expected.items())]
          evidence = matches[0] if len(matches) == 1 else None
  ```
  Add to the `ComparisonRequest` docstring:
  > ``run_evidence`` may also be a list of such objects, for a report that
  > compares several runs; the case is verified when exactly one entry
  > matches it (added 2026-09-26).

- [ ] **Step 8: The CLI action**

  In `cli.py`:
  - Add `"compare"` to the `action` choices.
  - Add the flags:
  ```python
      parser.add_argument(
          "--comparison-request",
          help="For action=compare: an agent's quantity comparison request (JSON; schema omnidriver/schemas/quantity-comparison.schema.json).",
      )
      parser.add_argument(
          "--report",
          help="For action=compare: where to write the comparison report. Must not exist: a report is written once.",
      )
  ```
  - In `_validate_args`, before the final `--entry is required` check:
  ```python
      if args.action == "compare":
          if not args.comparison_request or not args.report:
              parser.error("action=compare requires --comparison-request and --report")
          if any((args.entry, args.run_document, args.config, args.cases_root, args.spec, args.output_dir,
                  args.plugin, args.scratch_dir)):
              parser.error("--entry/--run-document/--config/--cases-root/--spec/--output-dir/--plugin/--scratch-dir "
                           "are not valid with action=compare: each run in the request names its own plugin and sweep")
      elif args.comparison_request or args.report:
          parser.error("--comparison-request/--report are only valid with action=compare")
  ```
    Also add `"compare"` to the set in that final check (`{"recover", "sweep-plan", "sweep-run", "compare"}`).
  - In `main`, right after the `recover` dispatch:
  ```python
      if args.action == "compare":
          return _compare_quantities(args)
  ```
  - And the handler itself:
  ```python
  def _compare_quantities(args) -> int:
      """``compare``: read, compare and report once. The report is the result:
      exit 0 once it is written, whatever its status; exit 1 on a refusal."""
      from .core.quantities import QuantityComparisonError, run_quantity_comparison

      try:
          report = run_quantity_comparison(Path(args.comparison_request), Path(args.report))
      except QuantityComparisonError as exc:
          print(json.dumps({"status": "failed", "action": "compare", "error": str(exc)}, indent=2))
          return 1
      print(json.dumps(report, indent=2))
      return 0
  ```

  Add `omnidriver/core/quantities/comparison.py` to `RuntimeEvidenceCapability`'s `:consumed-by:`.

- [ ] **Step 9: Run the tests, then every shape including the wheel**

  ```bash
  /tmp/odB-<wt>/bin/python -m pytest packages/omnidriver/tests/core/test_point_reference.py packages/omnidriver/tests/core/test_quantity_comparison.py packages/omnidriver/tests/core/test_experiments.py -q
  /tmp/odB-<wt>/bin/python scripts/export-capability-seams.py && /tmp/odB-<wt>/bin/python scripts/export-capability-seams.py --check
  /tmp/odBcore-<wt>/bin/python -m pytest packages/omnidriver/tests -q
  /tmp/odB-<wt>/bin/python -m pytest packages/ -q -m "not slow and not native and not native_opencarp"
  rm -rf /tmp/odBwheel-<wt> /tmp/wheeltest-<wt>
  /tmp/odB-<wt>/bin/python -m build --outdir /tmp/wheeltest-<wt> packages/omnidriver
  uv venv --python 3.11 /tmp/odBwheel-<wt>
  VIRTUAL_ENV=/tmp/odBwheel-<wt> uv pip install -q "$(ls /tmp/wheeltest-<wt>/omnidriver-*.whl)[post]" pytest
  /tmp/odBwheel-<wt>/bin/python scripts/check-wheel-artifact.py
  /tmp/odBwheel-<wt>/bin/python -m pytest packages/omnidriver/tests -q
  python3 scripts/check-import-boundaries.py && python3 scripts/check-core-shape.py
  ```
  Expected: 0 failed everywhere.
  - The wheel shape proves both schemas ship. A missing package-data line fails every comparison test at import.
  - If the toy CLI test shows `association_status == "unverified"` on a real sweep, print the case's `workflow_state.json` keys. Fix the evidence source in `_run_evidence`; do not loosen the association.

- [ ] **Step 10: Generality-log row, commit, then an Opus review of Tasks 1–3**

  ```
  | 2026-09-26 | results-as-quantities | the comparison: `point-reference` and `quantity-comparison` schemas (packaged), `run_quantity_comparison` / `omnidriver compare`, and `experiments._association_status` accepting a list of `run_evidence` | an agent needs one call that reads named quantities from runs of any solver, compares agent-stated pairs against a pre-registered tolerance, and leaves a report bound to each run's evidence | neutral: no frame conversion, pairing or tolerance of core's own (owner, 2026-09-26); every input is supplied in the request; a report is written once; the envelope change is additive (a single object still works) |
  ```
  ```bash
  git add packages/omnidriver/src/omnidriver/schemas packages/omnidriver/src/omnidriver/core/quantities packages/omnidriver/src/omnidriver/core/experiments.py packages/omnidriver/src/omnidriver/core/plugin_capabilities.py packages/omnidriver/src/omnidriver/cli.py packages/omnidriver/pyproject.toml packages/omnidriver/tests ARCHITECTURE.md docs/superpowers/plans/2026-09-25-tutorials-are-pointers-remaining.md
  git commit -m "feat(core): compare quantities over agent-stated pairs; omnidriver compare

  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
  ```
  Dispatch an Opus reviewer over `main..HEAD` against the spec and this plan's Global Constraints before fast-forwarding.

---

### Task 4: The reference, `benchmarks/niederer2011.json`, strictly from the paper

**Files:**
- Create: `benchmarks/niederer2011.json`
- Create: `scripts/check-benchmark-references.py`
- Modify (in Task 6): `.github/workflows/ci.yml` static-gates job

**Interfaces:**
- Consumes: `load_point_reference`, `PointReferenceError` (Task 3).
- Produces: `benchmarks/niederer2011.json`, with `id` `niederer2011` and `version` `1`:
  - quantity unit `ms`, frame length unit `mm`;
  - points P1–P9, of which **P1, P4, P8 and P9** have coordinates;
  - one published value (P8's range across codes).
  
  It also produces `scripts/check-benchmark-references.py [--dir DIR]`, which exits 0 when every `*.json` loads.

- [ ] **Step 1: Read the research file and settle the owner's open point (no code)**

  Read `.superpowers/sdd/niederer-benchmark-definition.md` in full. If it has changed since 2026-09-26, recheck every row of the table in Step 3 against it before writing. Every value in the file comes from it; nothing else is inferred.
  
  ~~One question goes to the owner before commit: **P5**.~~ Superseded 2026-09-26: see the banner at the top. All nine points take the coordinates listed there.
  - The research verifies P1, P4, P8 and P9.
  - P4 is placed by the vertical pairing P4–P8 in Figure 1b. The same pairing places P5 above P1, at (0, 0, 3) mm in this file's frame, but the research's verified list does not name it.
  - Default: P5 stays unresolved.
  - If the owner confirms, give P5 `"coordinates": [0, 0, 3]`, a `definition` citing the P1–P5 construction line, and no `unresolved`. Record the decision, dated, in the commit message.
  
  ~~P2, P3, P6 and P7 stay unresolved in any case.~~ Superseded 2026-09-26: resolved from the owner's paper I appendix (banner at the top).

- [ ] **Step 2: Write the gate script, and check it bites**

  `scripts/check-benchmark-references.py`:
  ```python
  #!/usr/bin/env python3
  """Every benchmark reference under benchmarks/ is a valid point reference.

  A reference is supplied data: an agent passes its path in a comparison
  request. This gate keeps the committed ones loadable, their citations
  resolvable and their units in core's table
  (omnidriver.core.quantities.load_point_reference). It checks form, not
  truth. Whether a value is the source's own is a review question, answered
  in each file's `sources` and in the review table of the task that wrote it.
  """
  from __future__ import annotations

  import argparse
  import sys
  from pathlib import Path

  from omnidriver.core.quantities import PointReferenceError, load_point_reference

  REPO_ROOT = Path(__file__).resolve().parents[1]


  def main(argv: list[str] | None = None) -> int:
      parser = argparse.ArgumentParser(description=__doc__)
      parser.add_argument("--dir", type=Path, default=REPO_ROOT / "benchmarks")
      args = parser.parse_args(argv)
      files = sorted(args.dir.glob("*.json"))
      if not files:
          print(f"FAIL no references under {args.dir}; this gate would check nothing", file=sys.stderr)
          return 1
      failures = []
      for path in files:
          try:
              reference = load_point_reference(path)
          except PointReferenceError as exc:
              failures.append(str(exc))
              continue
          if reference.reference_id != path.stem:
              failures.append(f"{path.name}: id {reference.reference_id!r} is not the file name")
              continue
          resolved = sorted(label for label, point in reference.points.items() if point.coordinates is not None)
          print(f"ok {path.name}: {len(reference.points)} points, coordinates for {resolved}")
      for failure in failures:
          print(f"FAIL {failure}", file=sys.stderr)
      return 1 if failures else 0


  if __name__ == "__main__":
      sys.exit(main())
  ```
  Bite check, which also confirms the gate refuses an empty directory:
  ```bash
  mkdir -p /tmp/odB-bite && /tmp/odB-<wt>/bin/python scripts/check-benchmark-references.py --dir /tmp/odB-bite; echo "rc=$?"
  ```
  Expected: `rc=1`, `FAIL no references`.

- [ ] **Step 3: Write the reference**

  `benchmarks/niederer2011.json`. Paraphrase only: the paper's sentences are not quoted.
  ```json
  {
    "schema_version": 1,
    "id": "niederer2011",
    "version": "1",
    "title": "Niederer et al. 2011 N-version benchmark: activation time at P1-P9",
    "sources": [
      {
        "id": "niederer2011",
        "citation": "Niederer SA, Kerfoot E, Benson AP, et al. Verification of cardiac tissue electrophysiology simulators using an N-version benchmark. Phil. Trans. R. Soc. A 369(1954):4331-4351 (2011)",
        "doi": "10.1098/rsta.2011.0139",
        "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC3263775/",
        "retrieved": "2026-09-26",
        "accessed": true,
        "note": "open-access full text (PMC3263775, mirrored by Europe PMC) and Figure 1 (rsta20110139-g1.jpg)"
      },
      {
        "id": "niederer2011-esm",
        "citation": "Electronic supplementary material of the same article: the per-code activation times at P1-P9",
        "url": "https://royalsocietypublishing.org/doi/10.1098/rsta.2011.0139",
        "accessed": false,
        "note": "behind a bot check on 2026-09-26; not retrieved. Holds the numbers that would settle P2, P3, P6 and P7"
      }
    ],
    "quantity": {
      "name": "activation time",
      "definition": "the time at which the membrane potential first passes through 0 mV",
      "unit": "ms",
      "source": {"source_id": "niederer2011", "where": "section 3f (metric); milliseconds throughout, section 3d and Figures 2-4"}
    },
    "frame": {
      "length_unit": "mm",
      "definition": "A convention adopted by this file; the paper prints no coordinates. Origin at P1, the stimulus corner. Axis 1 runs along the 20 mm edge (the fibre direction), axis 2 along the 7 mm edge, axis 3 along the 3 mm edge, each pointing into the slab. The slab's dimensions (20 x 7 x 3 mm), its fibre axis and the stimulus corner are the paper's.",
      "stated_by_source": false,
      "source": {"source_id": "niederer2011", "where": "section 3b and Table 3 (dimensions, fibres along the 20 mm axis); section 3c (stimulus at one corner); Figure 1b (P1 at that corner)"}
    },
    "points": [
      {"label": "P1", "definition": "the corner where the stimulus is delivered; the P1-P8 line starts here", "coordinates": [0, 0, 0],
       "source": {"source_id": "niederer2011", "where": "Figure 1b; section 3c; section 5b (the initial corner)"}},
      {"label": "P2", "definition": "a corner adjacent to P1 on P1's 3 mm-axis face", "coordinates": null,
       "unresolved": "the paper does not say whether P2 lies from P1 along the 7 mm or the 20 mm edge; the numbers are in the ESM, not retrieved",
       "source": {"source_id": "niederer2011", "where": "Figure 1b"}},
      {"label": "P3", "definition": "the other corner adjacent to P1 on P1's 3 mm-axis face", "coordinates": null,
       "unresolved": "the paper does not say whether P3 lies from P1 along the 20 mm or the 7 mm edge; the numbers are in the ESM, not retrieved",
       "source": {"source_id": "niederer2011", "where": "Figure 1b"}},
      {"label": "P4", "definition": "the corner of P1's 3 mm-axis face diagonally opposite P1; P8 lies directly above it along the 3 mm edge", "coordinates": [20, 7, 0],
       "source": {"source_id": "niederer2011", "where": "Figure 1b (construction line P4-P8)"}},
      {"label": "P5", "definition": "the corner above P1 along the 3 mm edge", "coordinates": null,
       "unresolved": "placed by the P1-P5 construction line of Figure 1b, the same evidence that places P4, but not on the research's verified list; awaiting the owner's confirmation",
       "source": {"source_id": "niederer2011", "where": "Figure 1b (construction line P1-P5)"}},
      {"label": "P6", "definition": "the corner above P2 along the 3 mm edge", "coordinates": null,
       "unresolved": "follows P2, which is unresolved",
       "source": {"source_id": "niederer2011", "where": "Figure 1b (construction line P2-P6)"}},
      {"label": "P7", "definition": "the corner above P3 along the 3 mm edge", "coordinates": null,
       "unresolved": "follows P3, which is unresolved",
       "source": {"source_id": "niederer2011", "where": "Figure 1b (construction line P3-P7)"}},
      {"label": "P8", "definition": "the corner diagonally opposite P1 through the slab; the P1-P8 line ends here, and it activates last", "coordinates": [20, 7, 3],
       "source": {"source_id": "niederer2011", "where": "Figure 1 caption; section 5; section 5b (the far corner); section 6"}},
      {"label": "P9", "definition": "the centre of the slab", "coordinates": [10, 3.5, 1.5],
       "source": {"source_id": "niederer2011", "where": "section 5b (the centre of the cuboid)"}}
    ],
    "published_values": [
      {"label": "P8", "kind": "range of last activation across the participating codes", "unit": "ms", "range": [37.8, 48.7],
       "conditions": "the highest spatial and temporal resolutions (dx 0.1 mm, dt 0.005 ms)",
       "source": {"source_id": "niederer2011", "where": "section 6 (Discussion); resolutions from section 3d"}}
    ]
  }
  ```

  Review table: the reviewer ticks each row against the research file.

  | field | research-file section |
  |---|---|
  | dimensions 20×7×3 mm; fibres along 20 mm | §1 |
  | stimulus at one corner; P1 is that corner | §2, §3, "Comparison" P1 |
  | P8 = the far corner; the last to activate | §3, "Comparison" P8 |
  | P9 = the centre (10, 3.5, 1.5) | §3, "Comparison" P9 |
  | P4 shares P8's 20 mm and 7 mm coordinates | §3, "Comparison" (vertical pairing) |
  | P2/P3/P6/P7 not assignable; ESM not retrieved | §3, §5, "Comparison" |
  | 0 mV first crossing; ms | §4 |
  | 37.8–48.7 ms at P8, finest resolution | §3, §5 |
  | no numeric origin: the frame is a convention | §1, "Comparison" (origin) |

- [ ] **Step 4: Run the gate**

  Run: `/tmp/odB-<wt>/bin/python scripts/check-benchmark-references.py`
  
  Expected: `ok niederer2011.json: 9 points, coordinates for ['P1', 'P4', 'P8', 'P9']` (plus `P5` if the owner confirmed it), and exit 0.

- [ ] **Step 5: Commit**

  ```bash
  git add benchmarks/niederer2011.json scripts/check-benchmark-references.py
  git commit -m "feat: benchmarks/niederer2011.json from the paper, and its static gate

  P1, P4, P8, P9 have coordinates in a declared convention frame; P2, P3,
  P5, P6, P7 are unresolved with the reason (the paper prints no
  coordinates; the ESM was not retrieved). No tolerance: the paper states
  none, so each comparison request pre-registers its own.

  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
  ```

---

### Task 5: openCARP reads its LAT file as quantities at supplied points

**Files:**
- Create: `packages/omnidriver-opencarp/src/omnidriver/opencarp/lat_reader.py`
- Modify: `packages/omnidriver-opencarp/src/omnidriver/opencarp/plugin.py` (`get_artifact_value_reader`)
- Modify: `packages/omnidriver-opencarp/src/omnidriver/opencarp/records/niederer_n_version.py` (the LAT path becomes a `ProducedPath`)
- Modify: `packages/omnidriver-opencarp/src/omnidriver/opencarp/guidance.md`
- Modify: `packages/omnidriver-opencarp/tests/opencarp_native.py` (`niederer_sweep`, `niederer_run`, `NiedererRun`)
- Create: `packages/omnidriver-opencarp/tests/test_lat_reader.py`, `test_lat_reader_native.py`
- Modify: `docs/solver-learning/opencarp.md` (F16, F17)

**How the points reach the reader.** They are in the agent's comparison request (`runs.<name>.points`), never in a record edit. Core converts them from the request's length unit to the reader's `um` and passes them as `ReadRequest.points`. The record changes only to name the LAT file's format.

**Interfaces:**
- Consumes: `ProducedPath` (Task 1); `RawSample`, `ReadRequest`, `read_quantities` (Task 2); `par_format.read_raw`, `par_format.unquote`; `build_sweep_context`, `data_artifact_from_json`.
- Produces:
  - `LAT_FORMAT = "opencarp_lat_per_node"`;
  - `LatPerNodeReader`, declaring `value_unit="ms"`, `sentinels={-1.0}`, `sampling_rule="node"`, `coordinate_unit="um"` and `takes_points=True`;
  - `OpenCARPPlugin.get_artifact_value_reader(format)`;
  - in tests: `niederer_sweep(tmp_path, *, dx_values, tend, extra=None) -> Path` and `niederer_run(tmp_path, *, dx, tend, extra=None) -> NiedererRun(output_dir, case_id, case_root, lat_artifact)`.

- [ ] **Step 1: Settle F16 and F17 against the real binary, and log them**

  Both were observed while this plan was written (2026-09-26, openCARP v18.1, scratchpad, `nversion.par` from `03E_study_resolution`, `mesher` slab at dx 1000). Re-run them and write both rows into `docs/solver-learning/opencarp.md` §F with the output you see:
  ```bash
  S=$(mktemp -d) && cd "$S" && export DYLD_LIBRARY_PATH=/opt/homebrew/lib
  T=/usr/local/lib/opencarp/share/tutorials/02_EP_tissue/03E_study_resolution && cp "$T/nversion.par" "$T/singlecell.sv" .
  mesher '-size[0]' 2.0 '-size[1]' 0.7 '-size[2]' 0.3 '-center[0]' 1.0 '-center[1]' 0.35 '-center[2]' 0.15 \
    '-resolution[0]' 1000 '-resolution[1]' 1000 '-resolution[2]' 1000 -mesh slab >/dev/null
  head -3 slab.pts; wc -l slab.pts
  openCARP +F nversion.par -meshname slab -simID out '-imp_region[0].im_sv_init' singlecell.sv -tend 10 -dt 50 >/dev/null
  grep -n "^meshname" out/parameters.par; wc -l out/init_acts_vm_act-thresh.dat; grep -c '^-1.000000' out/init_acts_vm_act-thresh.dat
  openCARP +F nversion.par -meshname slab -simID outall '-imp_region[0].im_sv_init' singlecell.sv -tend 10 -dt 50 '-lats[0].all' 1 >/dev/null
  ls outall; head -3 outall/vm_act-thresh.dat
  ```
  Observed while planning:
  - `slab.pts`: `672`, then integer µm coordinates (`0 0 0`, `1000 0 0`, …); 673 lines, i.e. 21 × 8 × 4 points;
  - `out/parameters.par`: `meshname = slab` (padded before the `=`). `par_format.parse_par` reads the whole file (40 assignments), and `read_raw(text, "meshname")` gives `'slab'`;
  - the LAT file has 672 lines, one column; `-1.000000 ` means never activated (658 of them at tend 10);
  - with `lats[0].all = 1`, there is **no** `init_acts_*` file. openCARP writes `vm_act-thresh.dat` instead: two tab-separated columns, `node index` then `time`.

  Rows to add (fill the observed column from your run):
  ```
  | F16 | Does openCARP record which mesh a solve used? | the dx-1000 slab, `openCARP +F nversion.par -meshname slab -simID out ... -tend 10 -dt 50`; `grep meshname out/parameters.par`; `par_format.read_raw(text, "meshname")` | `meshname = slab`; the whole file parses (40 assignments) | **yes: `<simID>/parameters.par` states `meshname`**, relative to the working directory (F5). The LAT reader reads the mesh from there, the solver's own record of the run, rather than from an argument |
  | F17 | What does `lats[0].all = 1` write for nversion? | as F16 plus `-lats[0].all 1`, `-simID outall` | no `init_acts_vm_act-thresh.dat`; `vm_act-thresh.dat`, two columns (node index, time), one line per activation event | the per-node file the record declares exists only with `all = 0`. With `all = 1` the declared artifact is missing (reconciliation says so), and the reader refuses a two-column file by name |
  ```
  If the binary disagrees with the observations above, stop and report. Do not write the reader against the plan's expectation.

- [ ] **Step 2: Write the failing pure tests**

  `packages/omnidriver-opencarp/tests/test_lat_reader.py` (no binary; nothing here claims solver behaviour):
  ```python
  """The plugin declares its LAT reader and the record names the LAT format."""
  from __future__ import annotations

  from omnidriver.core.quantities import check_reader
  from omnidriver.opencarp.lat_reader import LAT_FORMAT, LatPerNodeReader
  from omnidriver.opencarp.plugin import OpenCARPPlugin
  from omnidriver.opencarp.records.niederer_n_version import RECORD


  def test_the_plugin_reads_its_lat_format_and_nothing_else():
      plugin = OpenCARPPlugin()
      assert isinstance(plugin.get_artifact_value_reader(LAT_FORMAT), LatPerNodeReader)
      assert plugin.get_artifact_value_reader("opencarp_par") is None
      check_reader(LatPerNodeReader(), artifact_format=LAT_FORMAT)


  def test_the_record_names_the_lat_files_format():
      solve = {step.step_id: step for step in RECORD.workflow_steps}["solve"]
      assert solve.produced_format("out/init_acts_vm_act-thresh.dat") == LAT_FORMAT
      assert solve.produced_format("out/vm.igb") == "file"
  ```

- [ ] **Step 3: Write the failing native tests**

  Append to `packages/omnidriver-opencarp/tests/opencarp_native.py`:
  ```python
  import json
  import subprocess
  import sys
  from dataclasses import dataclass
  from typing import Any, Mapping

  from omnidriver.core.runtime.models import DataArtifact, data_artifact_from_json
  from omnidriver.core.runtime.postprocess_phase import build_sweep_context

  LAT_PATH = "out/init_acts_vm_act-thresh.dat"


  def niederer_sweep(tmp_path: Path, *, dx_values: tuple[float, ...], tend: float,
                     extra: Mapping[str, Any] | None = None) -> Path:
      """Run niedererNVersion over ``dx_values`` through ``omnidriver sweep-run``
      (dt 50 us, G4/G7). Returns the sweep's output directory."""
      require_opencarp_binary()
      spec = {
          "base": {"entry": "niedererNVersion", "cases_root": str(opencarp_tutorials_root()),
                   "nversion.par:tend": tend, "nversion.par:dt": 50.0, **(extra or {})},
          "sweep": {"mode": "cross_product", "independent": {"dx": list(dx_values)}},
      }
      spec_path = tmp_path / "sweep.json"
      spec_path.write_text(json.dumps(spec))
      output = tmp_path / "sweep"
      proc = subprocess.run(
          [sys.executable, "-m", "omnidriver", "sweep-run", "--plugin", "opencarp", "--spec", str(spec_path),
           "--output-dir", str(output), "--scratch-dir", str(tmp_path / "scratch")],
          capture_output=True, text=True, timeout=600,
      )
      try:
          payload = json.loads(proc.stdout)
      except ValueError:
          pytest.fail(f"sweep-run printed no JSON (rc={proc.returncode}): {proc.stderr[-2000:]}")
      if proc.returncode != 0 or payload.get("failed_count"):
          pytest.fail(f"sweep-run failed (rc={proc.returncode}): {proc.stdout[-2000:]} {proc.stderr[-2000:]}")
      return output


  @dataclass(frozen=True)
  class NiedererRun:
      output_dir: Path
      case_id: str
      case_root: Path
      lat_artifact: DataArtifact


  def niederer_run(tmp_path: Path, *, dx: float, tend: float, extra: Mapping[str, Any] | None = None) -> NiedererRun:
      output = niederer_sweep(tmp_path, dx_values=(dx,), tend=tend, extra=extra)
      (case,) = build_sweep_context(output).cases
      document = json.loads((output / case.run_document_path).read_text())
      artifact = next(data_artifact_from_json(raw) for raw in document["expectedArtifacts"]
                      if raw["path_pattern"] == LAT_PATH)
      return NiedererRun(output, case.case_id, Path(case.case_root), artifact)
  ```

  `packages/omnidriver-opencarp/tests/test_lat_reader_native.py`:
  ```python
  """The LAT reader against the real binary: values at supplied points, in ms,
  at the mesh nodes the solve used (F6, F16, F17, G4). Every file read here
  was written by mesher and openCARP; no mesh is invented."""
  from __future__ import annotations

  import dataclasses

  import pytest

  from omnidriver.core.quantities import ReadRequest, read_quantities
  from omnidriver.opencarp.lat_reader import LatPerNodeReader
  from opencarp_native import niederer_run

  pytestmark = pytest.mark.native_opencarp

  CORNERS = {f"x{x}y{y}z{z}": (float(x), float(y), float(z)) for x in (0, 20000) for y in (0, 7000) for z in (0, 3000)}
  CENTRE = {"centre": (10000.0, 3500.0, 1500.0)}


  def test_the_slab_corners_and_centre_at_dx_500_match_g4(tmp_path):
      run = niederer_run(tmp_path, dx=500.0, tend=150.0)
      points = {**CORNERS, **CENTRE}
      quantities = {q.name: q for q in read_quantities(
          LatPerNodeReader(), run.case_root, run.lat_artifact, ReadRequest(names=tuple(points), points=points))}
      assert all(q.status == "evaluated" and q.unit == "ms" and q.sampling_rule == "node" for q in quantities.values())
      # at dx 500 every requested point is a node (F3: 41 x 15 x 7), so each is sampled where asked
      assert all(q.sampled_at == points[name] and q.sampled_at_unit == "um" for name, q in quantities.items())
      assert quantities["x0y0z0"].value == pytest.approx(1.355, abs=5e-4)             # G4: P1, 1.355 ms
      assert quantities["x20000y7000z3000"].value == pytest.approx(126.45, abs=5e-3)  # G4: P8, 126.45 ms
      assert quantities["x0y0z0"].value < quantities["centre"].value < quantities["x20000y7000z3000"].value


  def test_a_node_never_reached_is_not_reached_never_minus_one(tmp_path):
      run = niederer_run(tmp_path, dx=1000.0, tend=10.0)
      far = {"far": (20000.0, 7000.0, 3000.0)}
      (quantity,) = read_quantities(LatPerNodeReader(), run.case_root, run.lat_artifact,
                                    ReadRequest(names=("far",), points=far))
      assert (quantity.status, quantity.value) == ("not_reached", None)


  def test_a_point_equidistant_from_nodes_is_refused_by_name(tmp_path):
      """At dx 1000 the centre (10000, 3500, 1500) um lies midway between nodes
      on two axes (21 x 8 x 4 points, F16's run)."""
      run = niederer_run(tmp_path, dx=1000.0, tend=10.0)
      with pytest.raises(ValueError, match="'centre'.*equidistant"):
          LatPerNodeReader().read(run.case_root, run.lat_artifact, ReadRequest(names=("centre",), points=CENTRE))


  def test_the_per_event_layout_is_refused_by_name(tmp_path):
      """F17: with lats[0].all = 1 the declared per-node file is absent, and the
      file openCARP does write has two columns, which the reader refuses."""
      run = niederer_run(tmp_path, dx=1000.0, tend=10.0, extra={"nversion.par:lats[0].all": True})
      assert not (run.case_root / run.lat_artifact.path_pattern).exists()
      per_event = dataclasses.replace(run.lat_artifact, path_pattern="out/vm_act-thresh.dat")
      with pytest.raises(ValueError, match=r"lats\[\]\.all = 1"):
          LatPerNodeReader().read(run.case_root, per_event,
                                  ReadRequest(names=("origin",), points={"origin": (0.0, 0.0, 0.0)}))
  ```

- [ ] **Step 4: Run them to verify they fail**

  ```bash
  /tmp/odB-<wt>/bin/python -m pytest packages/omnidriver-opencarp/tests/test_lat_reader.py -q
  OMNIDRIVER_OPENCARP_TUTORIALS=/usr/local/lib/opencarp/share/tutorials DYLD_LIBRARY_PATH=/opt/homebrew/lib \
    /tmp/odB-<wt>/bin/python -m pytest packages/omnidriver-opencarp/tests/test_lat_reader_native.py -q -m native_opencarp
  ```
  Expected: `ModuleNotFoundError: No module named 'omnidriver.opencarp.lat_reader'`.

- [ ] **Step 5: Implement**

  `lat_reader.py`:
  ```python
  """Activation times from openCARP's per-node LAT file, at points an agent supplies.

  Each fact below comes from the real binary (docs/solver-learning/opencarp.md):
  - ``init_acts_<lats[].ID>-thresh.dat`` with ``lats[].all = 0``: one value per
    mesh point, in point order, ``-1`` for never activated, in ms (F6, G4). With
    ``all = 1`` openCARP writes a two-column per-event file instead (F17),
    which this reader refuses;
  - the mesh the solve used is ``meshname`` as the solver recorded it in
    ``<simID>/parameters.par`` (D5, F16), relative to the case root, which is
    the solve step's working directory (F5);
  - ``<meshname>.pts`` holds a point count, then ``x y z`` per point, in µm (F3).

  Sampling rule ``node``: the mesh point nearest each supplied point, whose
  coordinates are reported as ``sampled_at``. A tie is refused by name.
  Points come from the agent's comparison request, already converted to µm
  by core. This reader orients nothing: openCARP's frame is whatever the mesh
  says.
  """
  from __future__ import annotations

  import math
  from pathlib import Path

  from omnidriver.core.quantities import RawSample, ReadRequest

  from .par_format import read_raw, unquote

  LAT_FORMAT = "opencarp_lat_per_node"


  def _mesh_name(parameters: Path) -> str:
      try:
          text = parameters.read_text()
      except OSError as exc:
          raise ValueError(f"cannot read {parameters}, where openCARP records the mesh a solve used (F16): {exc}") from exc
      raw = read_raw(text, "meshname")
      if raw is None:
          raise ValueError(f"{parameters} records no meshname (F16)")
      return unquote(raw)


  def _read_pts(path: Path) -> list[tuple[float, float, float]]:
      try:
          rows = [line.split() for line in path.read_text().splitlines() if line.strip()]
      except OSError as exc:
          raise ValueError(f"cannot read the mesh points {path}: {exc}") from exc
      if not rows or len(rows[0]) != 1:
          raise ValueError(f"{path} does not start with a point count (F3)")
      count = int(rows[0][0])
      points = []
      for number, row in enumerate(rows[1:], start=2):
          if len(row) != 3:
              raise ValueError(f"{path} line {number} has {len(row)} fields, expected x y z")
          points.append((float(row[0]), float(row[1]), float(row[2])))
      if len(points) != count:
          raise ValueError(f"{path} declares {count} points but lists {len(points)}")
      return points


  def _read_lat(path: Path, *, point_count: int) -> list[float]:
      rows = [line.split() for line in path.read_text().splitlines() if line.strip()]
      if any(len(row) != 1 for row in rows):
          raise ValueError(
              f"{path} has more than one column: openCARP's per-event layout (lats[].all = 1, F17), "
              f"not one value per node; set nversion.par:lats[0].all to false"
          )
      if len(rows) != point_count:
          raise ValueError(f"{path} has {len(rows)} values for a mesh of {point_count} points (F6: one per node)")
      return [float(row[0]) for row in rows]


  def _nearest(points: list[tuple[float, float, float]], target: tuple[float, float, float], *, name: str) -> int:
      distances = [math.dist(point, target) for point in points]
      best = min(distances)
      tied = [index for index, distance in enumerate(distances) if distance == best]
      if len(tied) > 1:
          raise ValueError(
              f"point {name!r} at {list(target)} um is equidistant ({best} um) from nodes "
              f"{[list(points[i]) for i in tied[:8]]}; supply a point nearer one node"
          )
      return tied[0]


  class LatPerNodeReader:
      value_unit = "ms"
      sentinels = frozenset({-1.0})
      sampling_rule = "node"
      coordinate_unit = "um"
      takes_points = True

      def read(self, case_root: Path, artifact, request: ReadRequest) -> tuple[RawSample, ...]:
          case_root = Path(case_root)
          lat_path = case_root / artifact.path_pattern
          points = _read_pts(case_root / f"{_mesh_name(lat_path.parent / 'parameters.par')}.pts")
          values = _read_lat(lat_path, point_count=len(points))
          samples = []
          for name in request.names:
              index = _nearest(points, request.points[name], name=name)
              samples.append(RawSample(name=name, value=values[index], sampled_at=points[index]))
          return tuple(samples)
  ```
  Exact float ties are sound because `mesher` writes integer µm coordinates (F16's run).

  `plugin.py`, in `OpenCARPPlugin` beside the other runtime-evidence hooks:
  ```python
      def get_artifact_value_reader(self, artifact_format: str):
          """The LAT reader for the record's per-node LAT file; no other format is read."""
          return LatPerNodeReader() if artifact_format == LAT_FORMAT else None
  ```
  with `from .lat_reader import LAT_FORMAT, LatPerNodeReader`.

  `records/niederer_n_version.py`:
  - import `ProducedPath` from `omnidriver.core.tutorial_records`, and `LAT_FORMAT` from `..lat_reader`;
  - the solve step's `produces` becomes `("out", "out/vm.igb", ProducedPath("out/init_acts_vm_act-thresh.dat", format=LAT_FORMAT))`, keeping its `# F6` comment. **Corrected 2026-09-26 (R1 I4):** this dropped A5's `"out"` entry, which C11 needs; keep it first;
  - add to the module docstring: "The LAT file names its format so omniD reads it through `LatPerNodeReader` (results as quantities, 2026-09-26)."

  `guidance.md`: add a section.
  ```markdown
  ## Reading activation times as quantities

  `out/init_acts_vm_act-thresh.dat` has format `opencarp_lat_per_node`. `omnidriver
  compare` reads it at points you supply in the request (`runs.<name>.points`, any
  length unit; omniD converts to µm). The reader takes the value of the nearest mesh
  node and reports that node's coordinates as `sampled_at`, with rule `node`, unit
  `ms`, and `-1` as `not_reached`. It refuses a point equidistant from two nodes: at
  dx 1000 the slab centre is one. Pick a dx whose nodes include your points (dx 500
  and 250 contain the Niederer corners and centre). The mesh is the one openCARP
  records in `out/parameters.par` (F16). `lats[0].all` must stay `0`: with `1`
  there is no per-node file (F17). openCARP's slab is 0–20000 × 0–7000 × 0–3000 µm
  with the stimulus cube at the origin and fibres along x (F3). That is the frame
  of `benchmarks/niederer2011.json`, so its coordinates are written unchanged.
  ```

- [ ] **Step 6: Run the tests, the whole native tier and every shape**

  ```bash
  /tmp/odB-<wt>/bin/python -m pytest packages/omnidriver-opencarp/tests -q -m "not native_opencarp"
  OMNIDRIVER_OPENCARP_TUTORIALS=/usr/local/lib/opencarp/share/tutorials DYLD_LIBRARY_PATH=/opt/homebrew/lib \
    /tmp/odB-<wt>/bin/python -m pytest packages/omnidriver-opencarp/tests -q -m native_opencarp
  /tmp/odB-<wt>/bin/python -m pytest packages/ -q -m "not slow and not native and not native_opencarp"
  python3 scripts/check-case-writes.py && python3 scripts/check-import-boundaries.py
  ```
  Expected: 0 failed. `test_conformance_native.py::test_niederer_passes[C11]` now passes with detail `readers for ['opencarp_lat_per_node']`.

- [ ] **Step 7: Commit**

  ```bash
  git add packages/omnidriver-opencarp docs/solver-learning/opencarp.md
  git commit -m "feat(opencarp): read the per-node LAT file as quantities at supplied points (F16, F17)

  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
  ```
  No core file changed in this task, so there is no generality-log row. If one did change, it needs its own commit and row.

---

### Task 6: The proof, openCARP vs openCARP end to end; docs and verification

**Files:**
- Create: `packages/omnidriver-opencarp/tests/test_quantity_comparison_native.py`
- Modify: `AGENT_GUIDE.md` (new section), `CLAUDE.md` (invariants and static-gates rows), `.github/workflows/ci.yml` (static-gates step)
- Modify: `docs/superpowers/specs/2026-09-26-results-as-quantities-design.md` (dated status and corrections)

**Interfaces:**
- Consumes: `niederer_sweep` (Task 5); `load_point_reference`, `experiment_comparisons` (Task 3); `inspect_sweep_experiment`; `benchmarks/niederer2011.json` (Task 4).

- [ ] **Step 1: Write the agent-style end-to-end test**

  `packages/omnidriver-opencarp/tests/test_quantity_comparison_native.py`:
  ```python
  """An agent compares two openCARP resolutions at the paper's points, end to
  end, exactly as it would: sweep-run, read the run documents, write a
  request from the reference, `omnidriver compare`, attach the report to the
  experiment (spec 2026-09-26 §4)."""
  from __future__ import annotations

  import json
  import subprocess
  import sys
  from pathlib import Path

  import pytest

  from omnidriver.core.experiments import inspect_sweep_experiment
  from omnidriver.core.quantities import experiment_comparisons, load_point_reference
  from omnidriver.core.runtime.postprocess_phase import build_sweep_context
  from omnidriver.opencarp.lat_reader import LAT_FORMAT
  from opencarp_native import niederer_sweep

  pytestmark = pytest.mark.native_opencarp

  REFERENCE = Path(__file__).resolve().parents[3] / "benchmarks" / "niederer2011.json"
  TOLERANCE_MS = 5.0


  def _lat_artifact_id(output: Path, case) -> str:
      document = json.loads((output / case.run_document_path).read_text())
      (artifact,) = [a for a in document["expectedArtifacts"] if a["format"] == LAT_FORMAT]
      return artifact["artifact_id"]


  def test_an_agent_compares_dx_500_with_dx_250_at_the_paper_points(tmp_path):
      output = niederer_sweep(tmp_path, dx_values=(500.0, 250.0), tend=150.0)
      cases = {case.resolved_axis_values["dx"]: case for case in build_sweep_context(output).cases}
      reference = load_point_reference(REFERENCE)
      # The agent's orientation step: openCARP's slab is the reference frame
      # (F3: 0-20000 x 0-7000 x 0-3000 um, stimulus cube at the origin, fibres
      # along x), so the reference coordinates are written unchanged, in the
      # reference's own unit; core converts mm to the reader's um.
      labels = [label for label, point in reference.points.items() if point.coordinates is not None]
      points = {"unit": reference.length_unit, "at": {label: list(reference.points[label].coordinates) for label in labels}}

      def run(dx: float) -> dict:
          case = cases[dx]
          return {"plugin": "opencarp", "sweep_output": str(output), "case_id": case.case_id,
                  "artifact_id": _lat_artifact_id(output, case), "points": points, "max_sampling_offset": 0.001}

      request = tmp_path / "request.json"
      request.write_text(json.dumps({
          "schema_version": 1, "reference": str(REFERENCE),
          "tolerance": {"kind": "absolute", "value": TOLERANCE_MS, "unit": "ms",
                        "rationale": "declared before either run was read; exploratory, not a benchmark acceptance claim"},
          "runs": {"dx500": run(500.0), "dx250": run(250.0)},
          "pairs": [{"reference_label": label, "left": {"run": "dx500", "quantity": label},
                     "right": {"run": "dx250", "quantity": label}} for label in labels],
      }))
      report_path = tmp_path / "report.json"
      proc = subprocess.run([sys.executable, "-m", "omnidriver", "compare", "--comparison-request", str(request),
                             "--report", str(report_path)], capture_output=True, text=True, timeout=600)
      assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-2000:]
      report = json.loads(report_path.read_text())
      assert report["status"] in {"passed", "failed"}          # every pair was evaluated
      by_label = {m["reference_label"]: m for m in report["metrics"]}
      assert set(by_label) == set(labels)
      for metric in by_label.values():
          for side in (metric["left"], metric["right"]):
              assert (side["status"], side["unit"], side["declared_unit"], side["sampling_rule"], side["sampled_at_unit"]) == (
                  "evaluated", "ms", "ms", "node", "um")
              assert side["sampling_offset"] == 0.0 and side["source_artifact"] == "out/init_acts_vm_act-thresh.dat"
          difference = abs(metric["left"]["value"] - metric["right"]["value"])
          assert metric["difference"] == pytest.approx(difference)
          assert metric["status"] == ("within_tolerance" if difference <= TOLERANCE_MS else "outside_tolerance")
      for side in ("left", "right"):
          assert by_label["P1"][side]["value"] < by_label["P9"][side]["value"] < by_label["P8"][side]["value"]
      assert by_label["P8"]["left"]["value"] == pytest.approx(126.45, abs=5e-3)   # G4, dx 500
      experiment = inspect_sweep_experiment(output, comparisons=experiment_comparisons(report_path, sweep_output=output))
      assert {case.comparison.association_status for case in experiment.cases} == {"run_verified"}
      assert {case.comparison.status for case in experiment.cases} == {report["status"]}
  ```
  If `resolved_axis_values` is not keyed by `"dx"` with float values, print one `CaseRecord` and key the map by what is actually there. Do not add an index-based fallback.

- [ ] **Step 2: Run it**

  ```bash
  OMNIDRIVER_OPENCARP_TUTORIALS=/usr/local/lib/opencarp/share/tutorials DYLD_LIBRARY_PATH=/opt/homebrew/lib \
    /tmp/odB-<wt>/bin/python -m pytest packages/omnidriver-opencarp/tests/test_quantity_comparison_native.py -q -m native_opencarp
  ```
  Expected: PASS. Record the report's P1/P4/P8/P9 values at both dx, and its status, in `docs/solver-learning/opencarp.md` §G as **G8**: evidence for the benchmarker, not a reference value, like G4.

- [ ] **Step 3: Documentation**

  - `AGENT_GUIDE.md`: a section "Comparing results as quantities". Cover:
    - the request's shape (link the schema);
    - that orientation, pairing and tolerance are the agent's step and stated in the request;
    - "the report is written once";
    - the pair statuses;
    - `experiment_comparisons` for attaching the report;
    - the openCARP-vs-openCARP example from Step 1, as commands.
  - `CLAUDE.md`, invariants table, two rows:
    - `| a sentinel is never converted (-1 s is never -1000 ms) | test_a_sentinel_is_resolved_before_conversion |`
    - `| a comparison report is written once | test_a_report_is_written_once |`
    
    Also add `scripts/check-benchmark-references.py` to the "static gates" row.
  - `.github/workflows/ci.yml`, static-gates job, after "Install omnidriver":
  ```yaml
      - name: Check benchmark references load and cite their sources
        run: python3 scripts/check-benchmark-references.py
  ```
  - The spec: under **Status**, add the dated line "2026-09-26: plan `docs/superpowers/plans/2026-09-26-results-as-quantities.md`; Tasks 1–6 landed (`<hashes>`); Tasks 7–8 wait on the tutorial stream's 5.4b". Under §2 and §3, add dated corrections for the four deviations listed in this plan's "Spec items" section. Do not rewrite the original rows.

- [ ] **Step 4: Verify in every shape**

  ```bash
  /tmp/odB-<wt>/bin/python -m pytest packages/ -q -m "not slow and not native and not native_opencarp"
  /tmp/odBcore-<wt>/bin/python -m pytest packages/omnidriver/tests -q
  # the wheel, rebuilt from this tree (Task 3 Step 9's commands)
  OMNIDRIVER_OPENCARP_TUTORIALS=/usr/local/lib/opencarp/share/tutorials DYLD_LIBRARY_PATH=/opt/homebrew/lib \
    /tmp/odB-<wt>/bin/python -m pytest packages/omnidriver-opencarp/tests -q -m native_opencarp
  OMNIDRIVER_NATIVE_TUTORIALS=<cardiacFOAM tutorials> /tmp/odB-<wt>/bin/python -m pytest packages/ -q -m native
  python3 scripts/check-import-boundaries.py && python3 scripts/check-core-shape.py && python3 scripts/check-case-writes.py
  /tmp/odB-<wt>/bin/python scripts/export-capability-seams.py --check
  /tmp/odB-<wt>/bin/python scripts/check-benchmark-references.py
  ```
  Expected: **0 failed** in each. The cardiacFOAM `native` tier is run to show nothing regressed there; no cardiacFOAM file changed.

- [ ] **Step 5: Commit, and an Opus review of the whole unblocked topic**

  ```bash
  git add packages/omnidriver-opencarp/tests/test_quantity_comparison_native.py docs/solver-learning/opencarp.md AGENT_GUIDE.md CLAUDE.md .github/workflows/ci.yml docs/superpowers/specs/2026-09-26-results-as-quantities-design.md
  git commit -m "test(opencarp): an agent compares two resolutions at the paper points end to end; docs, CI gate

  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
  ```

---

### Task 7 (**BLOCKED** until the tutorial stream's step 5.4b lands `niederer2012` as a record): cardiacFOAM's probe reader

**Why blocked.** `niederer2012` is still a factory tutorial on `main`. The tutorial stream owns its migration to a record (step 5.4b), including the stale Niederer tolerance rows and reference paths, which this plan does not touch. The reader needs a record `produces` entry to carry its format.

**Files (when unblocked):**
- Create: `packages/omnidriver-openfoam/src/omnidriver/openfoam/probes.py` (the probes layout; OpenFOAM's format, with no field meaning)
- Create: `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/activation_probes.py` (unit, sentinel and rule for `activationTime` probes)
- Modify: `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/runtime_evidence.py` (`artifact_value_reader` returns the reader for its format, with a dated correction of its "empty today" docstring)
- Modify: the `niederer2012` record module that 5.4b creates, so the probe output is a `ProducedPath`
- Create: `packages/omnidriver-cardiacfoam/tests/test_activation_probes_native.py`

**Contract:**
- Format `ACTIVATION_PROBES_FORMAT = "cardiacfoam_activation_probes"`, declared on the record's probe output. From the native case, that is `postProcessing/Niedererpoints/0/activationTime`: function `Niedererpoints` in `system/Niedererpoints`, field `activationTime`, start time `0`. Confirm the literal path against 5.4b's record.
- `openfoam.probes.parse_probe_series(text: str, *, source: str) -> ProbeSeries(locations: tuple[tuple[int, Point], ...], times: tuple[float, ...], rows: tuple[tuple[float, ...], ...])`:
  - reads the `# Probe <k> (<x> <y> <z>)` lines, the `# Time` header, and one row per written time;
  - refuses by name: no probe lines, a repeated probe index, a row whose column count is not 1 + probes, a vector or tensor value (parentheses), and no data rows.
- `ActivationProbeReader`:
  - declares `value_unit="s"`, `sentinels={-1.0}`, `sampling_rule="cell-containing"`, `coordinate_unit="m"`, `takes_points=False`;
  - `read` returns one `RawSample` per requested probe, named by its index as a string (`"0"`…`"8"`), with `value` from the **last** data row and `sampled_at` = the probe's header location (the requested probe location as the solver echoes it; the containing cell's centre is not in the file, and the rule says so).
  - Each of these facts (seconds, `-1`, cell-containing, last row) is from map B. Step 2 re-checks them on a real run before any code is written.

**Corrected 2026-09-26 (controller review of the whole unblocked topic,
finding I3; recorded here, not implemented -- this task is still blocked):**
the `sampled_at` bullet above is wrong as written. OpenFOAM's `probes`
function (no `interpolationScheme`) samples the **containing cell**, not
the header's configured location, so reporting the header location as
`sampled_at` would restate the agent's own `system/Niedererpoints` entry,
not say where the value actually came from -- exactly the class of defect
the owner's rule ("the coordinates the solver says it sampled") exists to
catch. When Step 4 implements this:
- `sampled_at` must be the **containing cell's centre**, read from the
  case's own mesh or cell-centre field (e.g. `C`), never the probe header;
- the agent's request gives the expected probe locations, in cardiacFOAM's
  own frame, as `points`, with a required `max_sampling_offset`. Core's
  `comparison._points`/`_quantities` (fixed by the same controller review,
  finding I3) support this for any `takes_points = False` reader: `points`
  means "expected location", checked against the reported `sampled_at`, and
  never handed to the reader itself.
- **Open item:** `comparison._artifact` refuses any `path_pattern`
  containing `{`. If 5.4b's `niederer2012` record ends up declaring the
  probe artifact with topic A's `{instance}` placeholder, this task needs a
  core change first. Check this at Step 1's unblock check.

**Deferred (M9, controller review 2026-09-26; not this task's job to fix):**
neither this reader nor `LatPerNodeReader` reports the parameters that
define what "activation" means for its solver (openCARP:
`nversion.par:lats[0].threshold`/`mode`; cardiacFOAM: whatever
`electroProperties`/ionic setting defines the 0 mV crossing this probe
function is fed). A study that changes one gives a value that compares
against the same reference with no word in the report. Worth a reader
enhancement later -- not scoped into Task 7 or Task 8.

- [ ] **Step 1: Unblock check.** `git log main` shows the tutorial stream's 5.4b `niederer2012` record. Read its record module, its coarse study values from its native test, and its step ids. Use those names wherever this task writes `niederer2012`. Build `/tmp/odB-<wt>` fresh.
- [ ] **Step 2: Settle the facts on a real run.** Run 5.4b's `niederer2012` record through `sweep-run` at its coarse settings with `--scratch-dir`, and inspect `postProcessing/Niedererpoints/0/activationTime`. Log each fact in the cardiacFOAM evidence (or 5.4b's own log), as command, observed and conclusion:
  - the header lines;
  - the units, from `activationTime`'s `dimensions` in the run's field file;
  - the `-1` spelling;
  - that `probes` samples the containing cell (OpenFOAM `probes` without `interpolationScheme`);
  - which row is final.
  
  Stop and report if anything differs from the contract above.
- [ ] **Step 3: Failing native tests** (`-m native`; they read only files the run wrote, and the native `system/Niedererpoints`):
  - `test_the_probe_file_is_read_as_seconds_with_its_header_locations`: nine quantities `"0"`…`"8"`, unit `s`, rule `cell-containing`, `sampled_at_unit` `m`. `sampled_at` equals the native `system/Niedererpoints` `probeLocations`, parsed from the native file in the test; that is the drift gate against the native source. Probe `"0"` is evaluated.
  - `test_a_probe_never_reached_is_not_reached`: at a `tend` short enough (from Step 2) that the far probe is `-1`, it reads as `not_reached` with value `None`.
  - `test_the_probe_parser_refuses_a_vector_field`: run the same record's probes on a vector field, only if 5.4b's case writes one; otherwise refuse via a real file from another native case that does. No invented file.
  - C11 for the cardiacFOAM target passes. This needs solver-conformance Task 14, which is gated on the same step 5.
- [ ] **Step 4: Implement** `probes.py`, `activation_probes.py`, the `runtime_evidence` hook and the record's `ProducedPath`, to the contract above.
- [ ] **Step 5: Verify every shape** (`-m native` included) and commit: `feat(cardiacfoam): read activationTime probes as quantities`. Add a generality-log row only if core changed; this task should change none.

### Task 8 (**BLOCKED** on Task 7): openCARP vs cardiacFOAM, end to end

- [ ] **Step 1: The agent's orientation, written down before any run is read**
  - Read the cardiacFOAM native stimulus definition (its `electroProperties` stimulus box) to confirm the stimulus corner. Do not take it from `niederer_protocol.qmd` or from map B.
  - Write the mapping from the reference frame (a: 20 mm, b: 7 mm, c: 3 mm, origin at P1) to cardiacFOAM's frame (x: 20, y: 3, z: 7 mm, in metres) in the request's `pairs[].note`.
  - Under the expected result (stimulus at (0, 0, 7) mm), x = a, y = c, z = 7 − b. That gives P1 ↔ probe `"0"` (0 0 0.007), P4 ↔ `"3"` (0.019999 0 0), P8 ↔ `"7"` (0.019999 0.003 0) and P9 ↔ `"8"` (0.01 0.0015 0.0035); also P5 ↔ `"4"` if Task 4 resolved P5.
  - If the stimulus is elsewhere, derive the pairing again from what the file says.
- [ ] **Step 2: Failing native test** (both markers; appended to `test_quantity_comparison_native.py`, or a new module needing both environments):
  - openCARP dx 500 against the cardiacFOAM record at its native resolution;
  - request with openCARP `points` from the reference and cardiacFOAM runs with no points (its reader takes none);
  - absolute tolerance pre-registered with a rationale.
  
  Assert:
  - the CLI exit is 0 and the status is in {passed, failed};
  - each cardiacFOAM side has `declared_unit` `s`, `unit` `ms`, `sampling_rule` `cell-containing`, `sampled_at_unit` `m`, and `sampled_at` equal to its probe location;
  - each openCARP side has `sampled_at_unit` `um`;
  - every metric carries its `note`;
  - both runs are `run_verified` in their own sweep's `inspect_sweep_experiment`.
- [ ] **Step 3: Run it, record the numbers as evidence (not a reference), and commit.**

---

## Self-review

**1. Spec coverage.**

| spec item | where |
|---|---|
| §3 Quantity | Task 2 |
| §3 reader contract and dispatch by format | Tasks 1, 2 |
| §3 per-path format | Task 1 |
| §3 units, sentinels first | Task 2 |
| §3 tolerance over agent pairs | Task 3 |
| §3 reference schema | Task 3 |
| §3 envelope report with evidence | Task 3 |
| §3 entry point | Task 3 |
| §3 openCARP reader | Task 5 |
| §3 cardiacFOAM reader | Task 7, blocked |
| §2 reference file from the paper, with sources | Task 4 |
| §2 no frame conversion | Global Constraints; none in any task. Tasks 6 and 8 put orientation in the request |
| §2 units declared, sentinels resolved before conversion | Task 2 `read_quantities`/`converted`, tested |
| §2 sampling reported | `Quantity.sampled_at`, `sampled_at_unit`, `sampling_rule`, and the report's `requested_at`/`sampling_offset` |
| §2 stale references untouched | Global Constraints, Task 7 "Why blocked" |
| §4 native coarse-dx openCARP test | Task 5, against G4 |
| §4 core tests (`-1 s`, tolerance, inconvertible units) | Tasks 2, 3 |
| §4 end-to-end openCARP vs openCARP | Task 6 |
| §4 end-to-end openCARP vs cardiacFOAM | Task 8, blocked |
| §4 conformance extension | C11, Task 2 |
| §5 out of scope (diagonal line, consensus values, acceptability) | nothing here. The one published P8 range is data in the reference, not a pass criterion |

Gaps: none left open. The P5 owner question and the ESM for P2/P3/P6/P7 are stated as data gaps, not as missing tasks.

**2. Placeholder scan.**
- No "TBD" or "similar to". Every code step shows its code.
- Tasks 7 and 8 are specified by contract, with named tests and assertions rather than full code. Their record module, step ids and coarse study values do not exist until the tutorial stream's 5.4b, and writing code against guessed names would be an invented contract. Their Step 1 reads the real names first.
- `<wt>`, `<hashes>` and `<cardiacFOAM tutorials>` are per-executor values, named where they are used.

**3. Type and name consistency.**
- `ProducedPath(path, format)`, `PLAIN_FILE_FORMAT` and `WorkflowStep.produced_format(path)`: Tasks 1, 2, 5.
- `ReadRequest(names, points)` and `RawSample(name, value, sampled_at)`: Tasks 2, 5, 7.
- `read_quantities(reader, case_root, artifact, request)` and `converted(quantity, to_unit)`: Tasks 2, 3, 5.
- `check_reader(reader, *, artifact_format=)`: Tasks 2, 3, 5.
- `Tolerance.from_json(raw, *, where, reference_unit)`: used only inside `comparison.py`.
- `run_quantity_comparison(request_path, report_path)` and `experiment_comparisons(report_path, *, sweep_output=)`: Tasks 3, 6, 8.
- `load_point_reference(path)`, with `.points[label].coordinates` and `.length_unit`: Tasks 3, 4, 6.
- `LAT_FORMAT` and `LatPerNodeReader`: Tasks 5, 6.
- `niederer_sweep` and `niederer_run`: Tasks 5, 6.
- The check id is `C11` throughout, with the rename rule if topic A takes it first.
- Pair statuses and report statuses match between `comparison.py` and the tests.

**4. Risks checked against the code on `main` @ fd21fe7.**
- `build_sweep_context` reads `caseRoot` from `launch.caseRoot`; `write_toy_sweep` writes it there.
- The CLI's JSON-failure shape is `{"status": "failed", "action", "error"}`, matching `_sweep_output_dir`.
- `provider_stack` composes `get_artifact_value_reader` as `single` (first non-`None`, most specific first), so per-format dispatch across a stack works unchanged.
- The seam-documentation test requires each `:consumed-by:` module to contain `capabilities.runtime_evidence`. Both `checks.py` and `comparison.py` do.
- A missing declared artifact does not fail a sweep case: status comes from `workflow_state`. So F17's run completes, and the comparison reports `not_evaluated`. **Corrected 2026-09-26 (Task 5, F17 run):** wrong -- a missing declared (non-optional) artifact does fail the step, and so the case. Running the real `lats[0].all = 1` case (dx 1000, tend 10) produced `workflow_state.json` with `"steps": [..., {"step_id": "solve", "status": "failed", ..., "diagnostics": [{"level": "error", "code": "missing_artifacts", "message": "Step 'solve' exited successfully but has missing expected artifacts: record.solve.2"}]}]` and the case-level summary `"status": "failed"`, even though openCARP's own exit code was 0. `sweep-run`'s `failed_count` counts this case as failed too. Task 5's `niederer_sweep`/`niederer_run` (`packages/omnidriver-opencarp/tests/opencarp_native.py`) therefore take an explicit `allow_missing_declared_artifact` keyword, default `False`; only the F17 test passes `True`, and it does so knowing the case's own status is `failed`, not that the run "completes".
- The one assumption to check at execution time is that a real sweep's `workflow_state.json` carries `workflow_digest` and `resume_snapshot.aggregate_digest`. `experiments._association_status` already relies on them, and Task 3 Step 9 says what to do if it does not.
