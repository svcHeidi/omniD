# Solver descriptions: TOML records on the existing runtime

**Revision 2 (2026-09-28, owner review).** This revision replaces the draft
committed as `1205dc8`. That draft remains the full inventory of the five
packages: its §1 content inventory, its §4 content map and its lost-content
table. This revision keeps only the parts of them the plan below needs.

The owner's review cut the draft back:
- The draft proposed one core interpreter, derived plugin members, launch
  templates, an electrophysiology package and solver-wide quantity maps.
  Every abstraction below now has to answer two questions:
  - Which current solver-use problem requires it?
  - Why would a small solver-specific function be insufficient?
- Anything that could not answer both is dropped (§3.2).

Written against `probe-cellpoint` at `185de60`:
- openCARP's interpolating LAT reader is `f2cd0fd`, on main.
- cardiacFOAM's `cellPoint` probe reader is `8c919cb`, not yet on main.

No code changed, and nothing was run.

## 0. The design after restraint

**What stays as it is:**
- **The runtime.** `TutorialRecord`, `WorkflowStep`, `DefaultArgument`,
  `AxisContract`, `AxisResult` and `ProducedPath` stay. So do the record
  execution path, the parallel pass and each solver's `get_parallel_steps`,
  the provider stack, the capability seams and C1–C12. The new TOML loader
  builds these existing objects and nothing else.
- **The plugin manifests.** They stay YAML (`opencarp.yaml`, cardiacFOAM's
  `plugin.yaml`, `openfoam-environment.yaml`): they are the solver
  descriptions. The plugin classes stay Python.
- **Python, which keeps everything that is behaviour:**
  - codecs: `.par`, the OpenFOAM dictionary;
  - readers: LAT, probes, time selection;
  - derived values: axis functions such as blockMesh counts from `dx`,
    `lc = 1/N`, the S1–S2 end time, and the ionic-model stimulus amplitude;
  - solver-specific rules: openCARP F1/F2/F10/F14, cardiacFOAM V1–V8 and its
    catalogs;
  - sampling and interpolation, in each solver's own reader: openCARP
    interpolates within the containing tetrahedron (`f2cd0fd`); cardiacFOAM
    requires `interpolationScheme cellPoint` from the case's own probes dict
    (`8c919cb`, native `e9439c4f`).
- **Cross-solver pairing.** It stays explicit in each pre-registered
  comparison request.

**What moves to TOML, and why: tutorial records.** A record is a pointer to a
native case, its steps, its routes and its axes. Today that is written as
Python whose content is data. cardiacFOAM's `records/` package (5 records
and their shared axis and output modules) is 1,524 lines, of which 588 are
code and 831 prose. A TOML record states the steps
and consumes/produces directly, and names each axis's Python factory with
its keyword arguments. That makes a record readable and editable without
Python, and it moves nothing that is behaviour.

**Formats.** TOML is used because core already parses TOML with the stdlib
`tomllib` for `utility.manifest.toml`, and TOML is typed: every command token
is a quoted string and keeps its exact spelling. Studies, requests, catalogs
and references stay JSON.

**Existing records.** Records already on the Python form stay valid, and the
two forms coexist. That includes pseudo-ECG and singleCell, which are in
flight on the Python `TutorialRecord` form. A record moves to TOML when that
simplifies it, not as a prerequisite for anything else.

## 1. The argument-merging fix

**The problem, reproduced by the review.** `resolve_case_patches` in
`core/tutorial_records.py` (rule "M6, second rule") accepts two axes'
`command_arguments` for one step only when they are byte-identical.
Otherwise it raises:

```
TutorialRecordError: step 'solve' receives conflicting command arguments
from axis 'dt' (['-dt', '10']) and axis 'tend' (['-tend', '100'])
```

So the `dt` and `tend` axes the draft proposed for openCARP cannot both be
set in one study. The conservative rule is right for free argument lists,
because core parses no flag grammar. It is wrong for replacements of
**declared** default arguments, whose identity core already knows.

**The fix: a structured replacement keyed by `(step, default key)`.**

1. `AxisResult` gains a new field:
   `replacements: Mapping[str, Mapping[tuple[str, ...], tuple[str, ...]]]`,
   mapping step id → {default-argument key → replacement values}. The
   existing `command_arguments` field is unchanged in meaning.
2. `resolve_case_patches` merges replacements with these rules, all
   enforced there:
   - The key must be a `DefaultArgument.key` declared on that step.
     Otherwise it is refused by name ("replaces nothing").
   - Different keys on one step always compose. So `dt` and `tend` together
     give both replacements.
   - The same `(step, key)` from two axes is accepted when the values are
     equal, and refused naming both axes and the key when they differ.
   - A free `command_arguments` contribution that contains a key another
     axis replaces structurally is refused as ambiguous. The existing free
     rules are unchanged: a free contribution containing a key replaces that
     default, and two free contributions must agree byte for byte.
3. `WorkflowStep.argv(contributed, replacements)` builds a deterministic
   argv, independent of the order in which axes are listed:
   1. `command`;
   2. every default in its **declared** order, each as its key followed by
      its replacement values if replaced, else its default values;
      a default that a free contribution replaces is dropped here, as today;
   3. the free contributions, appended.

   A structurally replaced default keeps its declared position. That
   matters for openCARP, because a `-<key>` after `+F` is what overrides the
   `.par` file (F14).
4. `record_execution` carries `replacements` alongside `command_arguments`
   into `_workflow_dag_for_record` and `preview_record_case`.
5. The TOML record declares such an axis as `replaces = "solve:-tend"`. The
   loader builds its `AxisContract` with a resolve function that returns
   `AxisResult(replacements={"solve": {("-tend",): (str(value),)}})`. Python
   records can return the same field directly.
6. **Command-line ownership.** openCARP's `validation.read_documents` today
   reads `step.command` only (P3 concern 2). It must also read each step's
   `default_arguments`, so that `nversion.par:tend` is refused whenever
   `-tend` is a default after `+F`. That is the alias case: two names for one
   setting, the `.par` key and the axis.

**Tests** (core `test_record_default_arguments.py`, plus the openCARP
validator):
- `dt` + `tend` compose;
- the argv is identical whichever order the axes are listed in;
- the same key with equal values from two axes is accepted;
- the same key with different values is refused, naming both axes;
- replacing an undeclared key is refused;
- a free contribution colliding with a structural replacement is refused;
- a `.par` key owned by a default argument is refused (F14);
- existing free-argument behaviour is unchanged, pinned by the current
  `-dict` tests.

## 2. The implementation plan

Every step keeps all six verification shapes green (all packages, core alone,
the rebuilt wheel, native, native openCARP, static gates) and keeps C1–C12.

Every step records the tutorials plan's three numbers: tutorials plus
defaults, all package source, and all package tests.

Estimates below split code from prose (docstrings plus comments), and data
(TOML) from tests.

**Step 1 changes openCARP's provider digest.** The current campaign must be
frozen first, on the commit it already records, or have finished. §4.4 gives
the campaign's own revision.

### Step 1: `niedererNVersion` to TOML, format only

The record's behaviour must not change: same steps, same argv, same staged
files. Two commits in one change.

**Commit 1a: add the loader and the TOML record, with an equivalence test.**

- `core/record_description.py` (new) loads `records/*.toml` into
  `TutorialRecord`s:
  - `[[step]]`: `id`, `command`, `consumes`, `produces`, where a produces
    entry may be `{ path, format }` and becomes a `ProducedPath`;
  - `defaults = { key = [values] }` becomes `DefaultArgument`s;
  - `[[axis]]`: `name`, `factory = "module:function"` and `with = {…}`. The
    loader calls `factory(name, **with)`, converting arrays to tuples, and
    refuses by name a factory whose `AxisContract.name` differs from `name`;
  - it also sets the record's source digest (§4.1).
  - Refusals name the file and the key.
- `records/niedererNVersion.toml` (new): the two steps, verbatim from
  `records/niederer_n_version.py`.
- `opencarp/records/axes.py` (new) holds `dx_axis(name)`: today's
  `_dx_resolution` moved as-is, with the same `repr(float)` spelling and the
  same positive-length refusal. It is a factory because the argv spelling
  (`"500.0"`) and the refusal are behaviour; a `{value}` substitution would
  have changed them.
- `opencarp/records/__init__.py` registers the TOML record.
- `test_niederer_n_version_toml_equivalence.py` (openCARP) builds the Python
  `RECORD` and the TOML record side by side. The Python record's registration
  moves into this test only, through a test subclass of `OpenCARPPlugin`.
  - Record level (all-packages shape):
    - equal `workflow_steps`;
    - equal formats per produced path, compared explicitly, because
      `ProducedPath` equality ignores the format;
    - equal `AxisResult`s for `dx` at 1000, 500, 200 and 100, int and float;
    - equal refusals for 0, −1, NaN and `"x"`.
  - Case level (`native_opencarp`): two strict plans per study case, into two
    scratch roots, for the campaign study
    (`benchmarks/niederer2011/campaign/studies/opencarp_cartesianConvergence.json`,
    read-only) and the conformance base study. It asserts two things:
    - the run documents' workflow DAG (argv, consumes, produces ids) is
      byte-identical;
    - the digest of every staged file is equal.

    Only three fields may differ, and each is excluded by name: the stack
    digest, the provider digest and the record source digest.

**Commit 1b: switch and delete.**
- Delete `records/niederer_n_version.py` and the equivalence test (delete
  with the code). Commit 1b's message records the equivalence result.
- `tests/test_lat_reader.py` imports `RECORD` from the deleted module; it now
  takes the record from `TUTORIAL_RECORDS`.

| | src code | src prose | data | tests |
|---|---|---|---|---|
| core `record_description.py` + source digest (§4.1) | +125 | +30 | 0 | +170 (loader refusals, digest mutation), +30 TOML test data |
| openCARP | −20 (38 removed, 18 in `axes.py`) | −14 | +30 | +90 in 1a, −90 in 1b; +2 for `test_lat_reader` |

### Step 2: the argument-merging fix (core; no record changes behaviour)

This is §1. It changes no record's argv: no current axis returns
`replacements`, and every existing `DefaultArgument` test stays as it is.

Files:
- `core/tutorial_records.py`: `AxisResult`, `WorkflowStep.argv`, and the
  merge in `resolve_case_patches`;
- `core/runtime/record_execution.py`: plumbing;
- `core/record_description.py`: the `replaces =` form;
- `opencarp/validation.py`: `read_documents` also reads `default_arguments`.

| | src code | src prose | data | tests |
|---|---|---|---|---|
| core | +55 | +20 | 0 | +120 |
| openCARP | +4 | +2 | 0 | +25 |

### Step 3: `run.py`'s defaults (a behaviour change, reviewed on its own)

`run.py` for `03E_study_resolution` passes these arguments after `+F`, and
the record passes none of them today (drift audit §4.1, item 1):
- `-tend` (default 50 ms);
- `-dt` (default 20 µs);
- `-mass_lumping` (default 0, i.e. full mass).

Evidence: `run.py` lines 201–214 and 250–256, read 2026-09-27. Without them
a plain run takes the binary's defaults:
- tend 100 ms and dt 5 µs (G7);
- **lumped mass** (G10), which moves P8 by 68 ms at 0.5 mm (J4).

The record's `solve` step gains:

```toml
defaults = { "-tend" = ["50"], "-dt" = ["20"], "-mass_lumping" = ["0"] }
```

It also gains three axes:

| axis | replaces |
|---|---|
| `tend` | `solve:-tend` |
| `dt` | `solve:-dt` |
| `massLumping` | `solve:-mass_lumping` |

Each axis also carries its native unit (§3.1): `ms` for `tend`, `us` for `dt`.
The study states SI (`s`); the axis converts (owner, 2026-09-28).
`guidance.md` states the defaults and the F14 consequence.

**Tests:**
- native openCARP: a plain run's `out/parameters.par` records `tend`, `dt`
  and `mass_lumping` as run.py's (F16);
- plan: `dt` + `tend` in one study;
- plan: `nversion.par:tend` refused by name (F14).

**What it breaks, deliberately.** Once `-tend` is a default after `+F`, the
campaign's `nversion.par:dt`, `tend` and `mass_lumping` study keys are
refused (F14): the command line would silently override them. The campaign
therefore moves to the axes in its own revision (§4.4), not in this step.

**carputils' solver options** (lost-content item 2):
- The record's stated promise is "`run.py`'s workflow".
- The review's position: a promise to reproduce `run.py` preserves its
  effective options. Two agreeing runs cannot license dropping them.
- They are not part of this step. They need carputils' option files, which
  live outside the native case, so they would be supplied. That is a
  separate step, **3b**, after the owner confirms the promise (§6).

| | src code | src prose | data | tests |
|---|---|---|---|---|
| openCARP | 0 | 0 | +16 | +70 (native 40) |
| guidance | 0 | +6 | 0 | 0 |

### Step 4: `manufacturedBidomain` to TOML, format only

**Why this record.** It exercises every record feature `niedererNVersion`
does not:
- routes: `hex` (the default) and `tet`;
- `variant_constraints`: tet admits only `dimension 3D`;
- a `DefaultArgument` (`-dict system/blockMeshDict.3D`) that an axis replaces
  by a free contribution;
- an axis that also patches a document (`bidomainSolverCoeffs.dimension`);
- two derived axes, one of them the OpenFOAM layer's
  `block_mesh_resolution_axis`;
- a stacked plugin (`requires` the OpenFOAM environment).

Its own tet study, `tetTemporalControl/sweep_tet_dt_half.json` (which sets
`"mesh": "tet", "dimension": "3D"`), is the case that keeps
`variant_constraints` (the draft's D8). It is also small (61 code lines, 5
steps).

The others were passed over:
- `niederer2011` is changing on `probe-cellpoint`;
- pseudo-ECG and singleCell are in flight;
- bath is a larger instance of the same shape (8 steps, 80 code lines);
- `restitutionCurves` has no routes.

**Files:**
- `records/manufacturedBidomain.toml` (new, about 55 lines). The polyMesh
  output list is written out: the owner accepts repetition over a shared
  constant.
- `cardiacfoam/records/__init__.py` registers the TOML record beside the four
  Python records. `build_tutorial_record_catalog` still refuses a duplicate
  name.
- Delete `records/manufactured_bidomain.py` in the second commit.
- The loader gains `[routes]` (`select`, `default`, one list per route, and
  `admits.<route>` as `variant_constraints`).
- The axis factories are the existing ones, named from TOML:
  `manufactured_solution_axes.dimension_axis`, `hex_number_cells_axis` and
  `tet_number_cells_axis`, each with `with = {…}`.
- `manufactured_solution_axes.py` keeps its content. `DIMENSIONS` becomes the
  `admits` literal in TOML only where the record states it; the module
  constant stays for its three other users.

**Equivalence**, commit 1 of 2, the same method as step 1:
- record level: equal steps, routes, constraints, and `AxisResult`s;
- native level: `sweep-plan` of all 7 native bidomain studies with both
  records; every case's argv, patches and staged file digests are equal, and
  the case ids are identical. This is the method of BB7, bath's 70-case
  parity;
- plus one real hex run and one real tet run through the TOML record.
  C1–C12 stay in `test_conformance_native.py`.

| | src code | src prose | data | tests |
|---|---|---|---|---|
| core loader, `[routes]` | +30 | +8 | 0 | +60 |
| cardiacFOAM | −61 | −76 | +55 | +110 in commit 1, −110 in commit 2 |

**After step 4.** The loader has met two real, different records. Shared
machinery grows only where a later migration shows a need no factory
function can meet.

## 3. Abstractions: the two questions

### 3.1 Kept

| abstraction | which current solver-use problem requires it | why a small solver-specific function is insufficient |
|---|---|---|
| **TOML record loader** (`core/record_description.py`, about 140 code over steps 1, 2 and 4) | Records are data written as Python: 588 code lines against 831 prose in cardiacFOAM's `records/`. The owner wants them authored and maintained as TOML | Both solvers have records. A loader per solver would be two copies of one parser. It builds only existing objects |
| **structured default-argument replacement** (`AxisResult.replacements`, §1) | openCARP's `dt` and `tend` cannot both be set: `resolve_case_patches` refuses them (review, reproduced) | The refusal is in core's merge, which runs before any solver code. A solver function cannot make core accept two contributions |
| **record source digest** in provider identity (§4.1) | A record changed without a version bump leaves the stack digest unchanged, because only `cxx_mapping`, `dictionaries` and `manifest` are hashed (`provider_stack._DIGESTED_CAPABILITIES`). Resume and compare cannot tell | Identity is computed by core (`_provider_identity`). A solver's alternative is bumping its version by hand, which is the failure mode |
| **SI at omniD's surface; `native_unit` on `AxisContract`, converted at the axis** (owner, 2026-09-28; about 20 code, reusing `core/quantities/units.py`) | `dx` is metres in `niederer2011` and µm in `niedererNVersion`, `dt` seconds in one and µs in the other, and `describe` cannot say so. The campaign needed per-solver lookup tables (`campaign.sh` `dx_value`, `dt_where`), and its requests state points in mm for one solver and m for the other | A per-solver conversion would copy the unit table core already has for quantities. Studies, requests and reports state SI; only a record's axis knows the solver's unit. Keys stay per solver (they differ anyway), so this normalises values, not names |
| **optional `get_effective_settings` hook** (§4.2) | openCARP's config reader returns `None` for absent keys and ignores argv, although an argv `-<key>` after `+F` wins (F14). A parameter report from it can describe a different run | The **implementation** is solver-specific, as the owner asks. The hook exists only so `describe`/`plan --strict` and the run document show it. Without a hook, each benchmark would import solver internals |
| **ranks-within-allocation flag** (§4.4, about 20 code) | The campaign's strong-scaling runs inside one 64-task allocation work around the equality check by overriding `SLURM_NTASKS=$n` (campaign README), which misstates the allocation in provenance | The policy is per run and identical for both solvers. Each solver form would otherwise parse the same flag. The forms keep their own checks |
| **`WorkflowStep.cwd`** (§5; lands with TL-EM) | TL-EM's case-local build (`src/Allwmake`) | `_workflow_dag_for_record` builds the DAG node in core and drops any field `WorkflowStep` does not have |

**Local fixes, not abstractions:**
- OpenFOAM's `parallel_steps_for_record` accepts `parallel: N` and refuses it
  unless N equals `numberOfSubdomains`, instead of refusing every N. That is
  one request grammar across both solvers, in about 8 lines of OpenFOAM
  Python.
- O15, which deletes the OpenFOAM copy of core's runtime record names, stays
  as planned in Python.

### 3.2 Dropped

Each failed the second question: a solver-specific function already does the
job, or no current use needs it.

| dropped | why |
|---|---|
| core `DescribedPlugin`, `solver.toml`, and `provides` derived from data | The plugin classes work. openCARP's is 141 code lines, mostly constant returns. Replacing them with an interpreter moves code; it does not simplify |
| launch templates (`pre`/`wrap`/`post`), the core rank rule, the launcher-check and environment-probe grammars, `srun` as core data | The two parallel forms (71 and 95 code lines) and openCARP's launcher check are small, correct and solver-specific. Only one grammar difference mattered, and it is fixed locally (§3.1) |
| `[case.generated]`, `[tool.*] produces`, `[output.*]` reader tables, the `json_document` codec | Each replaces a few lines of working Python or restates a constant |
| **the `omnidriver-electrophysiology` package, its units, relations and rules**, including V5 moving | One benchmark consumes it. Its bindings are case-scoped (the review), so they live in that benchmark's comparison configuration (§4.3). V5 stays in `validation.py` |
| solver-wide quantity maps, quantity-named study keys | The Niederer file names, region indices and stimulus indices are case facts, not solver facts. Studies stay per solver, because the keys differ anyway |
| the "problem identity" report | It proves less than it claimed (review §3). It is replaced by a benchmark-local mapped-parameter check with declared known differences (§4.3) |
| a general sampling, interpolation, pairing or output-selector framework | Each solver owns its sampling (`f2cd0fd`, `8c919cb`). Requests pair explicitly. An ambiguous output is fixed locally by its path |
| substitution axes (`{value}`, `arguments`, `patch`) | Every current axis is an existing Python factory, and a substitution grammar would have changed `dx`'s argv spelling (step 1) |
| Guard A (a toy with zero Python) and Guard B (a shrinking solver-Python gate) | The toy is a fixture, not evidence. Python growth is judged in review, directly |
| folding the YAML manifests into TOML; moving `gmsh` (D14); the GPU schema reservation | No current problem |
| C13/C14 and the conformance harness helpers (the drift audit's R1/R5) | Real duplication, but independent of this design. It stays on the audit's backlog |

## 4. Where things live

### 4.1 Description-resource hashing

- The loader sets `TutorialRecord.source_digest`, a new optional field
  defaulting to `None`. Its value is the sha256 of the loader's schema
  version plus the canonical JSON of the parsed TOML.
- Comments do not affect it; a change to any value does.
- `plugin_interface._provider_identity` folds the sorted digests of the
  provider's records into `provider_digest`, so the stack digest changes and
  `stack_identity_mismatch` refuses a resume.
- The run document records the case's `record_source_digest`, so `compare`
  can name the record version that planned the case.
- Python records have no source digest and are covered by `plugin_version`,
  as today. That is stated as a limit, not hidden. The same applies to the
  Python functions a TOML record names.

**Tests:**
- change a step argument in a TOML record without a version bump: the
  provider digest changes, and resume is refused;
- change only a comment: the digest is unchanged;
- change an axis's `with` value: the digest changes.

### 4.2 The effective-settings report

**Hook.** The optional `get_effective_settings(case_root, workflow_dag)`
returns rows of `document:key`, value, and source. The source is one of:
`argv` (with the step), `document`, `default@<catalog tag>`, or `unknown`.
Core prints the rows in `describe` and `plan --strict`, and stores them in
the run document.

**openCARP implementation.** About 60 lines in
`opencarp/effective_settings.py`, using `par_format`, `catalog` and the
argument parser in `validation`:
- the last `.par` assignment wins (F8);
- an argv `-<key>` after `+F` wins over the file (F14);
- an absent key takes the catalog default, tied to the catalog's `GIT tag`
  (`v18.1`), which preflight already compares against the binary.

**cardiacFOAM implementation.**
- Pre-run: values as `foamDictionary` resolves them
  (`effective_dictionary.resolve_effective_foam_entry`). An absent key is
  `unknown`.
- Post-run: `constant/electroProperties.withDefaultValues`, which the solver
  writes itself for the solvers that call `electroModel::end`
  (`records/case_outputs.py`).

### 4.3 The Niederer comparison configuration

**File:** `benchmarks/niederer2011/comparison.json`. It is benchmark data,
and it states that it is a **mapped-parameter check, not a proof of
equivalence**. It holds three things.

**1. Bindings, scoped to the two records.**
- Each parameter row gives a `document:key` per record, the expected
  effective value **in that solver's own unit**, and the evidence.
- The cross-solver match was established in `cardiacfoam.md` section S and
  is recorded here with the conversion shown. So the check needs no unit
  conversion.
- It supports one region and one stimulus, and says so.

**2. Known differences, each accepted by the owner (2026-09-27/28):**
- the ionic model: TNNP 2004 (cardiacFOAM `TNNPcompactBatched`) against
  2006 (openCARP);
- the initial Vm: −84 mV against the `.sv` state's −85.23 mV;
- the stimulus volume: 27 cells, exactly (1.5 mm)³, against 64 nodes
  reaching 1.75 mm;
- the stimulus end step: cardiacFOAM includes it;
- the PDE time scheme: BDF2 against Crank–Nicolson;
- the mass matrix: finite volume against full FE (`mass_lumping 0`);
- the sampling: `cellPoint` (native `e9439c4f`) against linear-in-tetrahedron
  (`f2cd0fd`);
- the stimulus strength: 49,994 against 50,000 µA/cm³, a **0.012 %**
  difference. The draft wrongly called this a match within 0.01 %; it is
  listed here as a difference with that figure.

**3. Acceptance criteria.**
- The tolerances stay in the pre-registered requests; the configuration
  points to them.
- A required parameter that is unbound or `unknown` leaves the comparison
  **unresolved**, never matched.

**Check script:** `benchmarks/niederer2011/check_parameters.py`, about 60
lines. It reads each case's effective settings (§4.2) from its run document
and compares them with the bindings. It writes a report beside the
comparison. Pairing stays in each request.

### 4.4 The scheduler workflow

**The invariant: decomposition equals launched ranks.** It is enforced where
the decomposition lives: OpenFOAM's `parallel_steps_for_record`
(`numberOfSubdomains`). openCARP has no decomposition; PETSc partitions at
launch (I6).

**Whole-allocation is a supported-mode restriction, and the default.**
Launched ranks must equal `SLURM_NTASKS`. The refusal message now names it as
the default mode, not as an invariant.

**`--ranks-within-allocation`** is supplied per run. Core then:
- records the allocation in provenance, but does not pass it to the
  solver's form, so no equality is checked;
- refuses `parallel: true` in this mode, because N must be stated.

Core adds no comparison beyond that: placement and threads belong to the
site's launcher environment, which the user supplies. This replaces the
campaign README's `SLURM_NTASKS=$n` override. No submission framework is
built.

**Campaign revision.** A separate, versioned change:
- the current campaign is frozen on its commit, and its results keep their
  interpretation;
- the new revision moves the openCARP studies to the step 3 axes and uses
  the flag;
- its requests are re-pre-registered.

| | src code | src prose | data | tests |
|---|---|---|---|---|
| core flag and policy | +20 | +8 | 0 | +50 |
| OpenFOAM: N accepted when equal | +8 | +3 | 0 | +20 |

## 5. TL-EM: the corrected `cwd` estimate

The draft said `cwd` was "one field in `record_description.py`". It is not.
It is a record-contract extension, carried through three objects:

1. **`TutorialRecord`/`WorkflowStep`.** `WorkflowStep` gains
   `cwd: str = "."`, validated case-relative with the existing
   `_check_case_relative`. The case root is allowed, and escaping it is
   refused. `consumes` and `produces` stay **case-relative**, independent of
   `cwd`: provenance and staging (A5, C8, C11) read them from the case root.
2. **The DAG node.** `_workflow_dag_for_record` sets `step_entry["cwd"]`. The
   runner already resolves it (`_resolve_case_cwd`), and `workflow_state`,
   `resume` and `provenance_inputs` already carry it.
3. **Script resolution.** `_resolve_command` resolves a bare case-script name
   relative to `cwd`, but only for names in the conventions' `case_scripts`.
   `Allwmake` is not among them, so the OpenFOAM layer's
   `case_runtime_conventions.py` gains it.

Estimate: core +18 code, +8 prose; loader +2; OpenFOAM +1; tests about +80.
The tests are:
- a step with `cwd` writes a file whose case-relative `produces` is found;
- a `cwd` escaping the case is refused;
- a case script resolves from `cwd`;
- a restage (C11) carries nothing the step wrote.

The native Allwmake change (§5 of `1205dc8`) and a real serial TL-EM run must
settle the build before anyone claims TL-EM works.

It lands when the owner migrates TL-EM, which is the owner's own test (D4,
answered). The factory module is retired then, with an unsupported-entry
diagnostic in its place.

## 6. Deferred until a real integration shows the need

- **More TOML records.** Each moves when it simplifies. None is required.
- **Loader features beyond steps, defaults, `replaces`, factory axes and
  routes.** They are added only when a record cannot be written without them.
- **carputils solver options and `mesher_opts` (step 3b).** They need the
  owner to confirm that the record reproduces `run.py` (D3, revised), and
  the option files supplied.
- **The diagonal profile** (lost-content item 3). It needs a cardiacFOAM
  `Niedererlines` probe set to `cellPoint` natively, and its format
  declared. openCARP's reader already samples any point. The requests pair
  the points explicitly.
- **Parallel TL-EM.** Per-region `decomposePar -region` is solver-specific,
  so it belongs in cardiacFOAM's own form when the owner needs it.
- **Region-aware key validation (final review M3).** Needed when a study
  varies region-document keys.
- **A shared electrophysiology vocabulary.** Added when a second benchmark,
  or a rule used by two solvers, needs the same names.
- **A site launcher configuration (for example `srun`).** Added when the
  cluster run shows that `mpirun` does not work there.
- **Everything else in the draft's §3.2 and the drift audit's backlog.**

## 7. Open decisions

| # | decision | recommendation |
|---|---|---|
| D2 | Step 3: the record reproduces `run.py`'s defaults | Yes, as its own reviewed change |
| D3 | Does "reproduces `run.py`" include carputils' solver options (step 3b)? | Yes if that is the promise, with the options files supplied. Otherwise name the record's policy "binary defaults" in `guidance.md` |
| D11 | Freeze the current campaign on its commit before step 1, and revise it separately | Yes |
| D17 | Axis units | **Decided (owner, 2026-09-28): SI is the normalisation.** Studies, requests and reports state SI; each axis declares its solver's native unit and converts with core's existing table. Limits: only dimensioned values (unitless keys such as `mass_lumping` pass through); sentinels are never converted; the written text must be the exact decimal (`1e-4 m` writes `100`, and an inexact conversion is refused); the table grows beyond time and length only when a real axis needs it (mV, S/m, µA/cm²); frames stay explicit in each request; the current campaign is frozen (D11), so SI requests are new requests. **Any key with a unit is sweepable in SI** (owner, 2026-09-28): the existing direct-key path (`file:key`, `DefaultArgument` keys) converts from SI to the unit the solver's catalog declares for that key; one path, not an axis per variable. A key with no catalogued unit is written as given and flagged, like uncatalogued OpenFOAM keys today. Catalog units today: cardiacFOAM 39 of about 160 entries (`dict_entries_catalog.py`, some in `ms`); openCARP 0 of 266 (its `+Help` rarely states one), so its units are added from `openCARP.prm` and the manual, with evidence, for the keys a study sweeps |
