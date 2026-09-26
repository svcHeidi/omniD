# Results as comparable quantities: the benchmarker's step 2

**Date:** 2026-09-26 · **Status:** design decisions made by the owner in
conversation (2026-09-26). The written form is written from them.
**Goal:** step 2 of the benchmarker. omniD reads each solver's results as the
same named quantities, so an agent can run the Niederer 2011 N-version
benchmark on openCARP and cardiacFOAM and compare activation times at P1–P9.
**Evidence:** a read-only map of result handling (2026-09-26) and
`docs/solver-learning/opencarp.md` (F6, G4). The reference comes from the
paper, researched separately into
`.superpowers/sdd/niederer-benchmark-definition.md`.

**Status, 2026-09-26:** plan `docs/superpowers/plans/2026-09-26-results-as-quantities.md`;
Tasks 1–6 landed (Task 1 `26a8da6`; Task 2 `3f16fe8`; Task 3 `13ba8b6`,
`5259160`; Task 4 `767f70a`; Task 5 `422d549`, `ff6331e`; Task 6 is this
commit, on branch `qoi-b6`); Tasks 7–8 wait on the tutorial stream's 5.4b.

## 1. What exists

- **In core:** no code reads a value from a result file or compares numbers.
- **Declared everywhere, never called:** `RuntimeEvidenceCapability.artifact_value_reader`
  exists in every plugin and always returns `None`.
- **Can't dispatch:** record outputs all have `format="file"`, so a reader
  cannot tell them apart.
- **Reusable:**
  - the `experiments.py` envelope (`ComparisonRequest`/`ComparisonOutcome`,
    run-evidence association);
  - reconciliation as a precondition (a missing artifact means
    `not_evaluated`);
  - the pre-registration rule from the tests' `protocol.py` (never edit a
    tolerance after seeing a result).
- **Solver facts:**
  - cardiacFOAM writes probe files in **seconds**, uses `-1` for never
    activated, samples the **cell containing** the point, and works in its own
    frame (slab 20 × 3 × 7 mm, metres).
  - openCARP writes a per-**node** LAT file in **ms**, uses `-1`, and its
    `.pts` file is in µm, in the paper's frame.

## 2. Decisions (owner, 2026-09-26)

| item | decision |
|---|---|
| reference | **one reference, from the paper**: `benchmarks/niederer2011.json`, holding labels P1–P9, the paper's coordinates and units, the activation-time rule, and the tolerances. Both solvers use it |
| frames and pairing | **no frame-conversion functions anywhere.** Orientation and pairing (e.g. cardiacFOAM probe 0 = P1) are the agent's step. It writes each solver's inputs from the reference (openCARP sampling points; cardiacFOAM probes, which already exist in `system/Niedererpoints`) and states the pairing in its comparison request. Rotating cardiacFOAM's native case is not needed |
| units | not hardcoded per solver. Each reader **declares** the unit of what it returns, and core converts with a small table. Sentinels (`-1` = never activated) are resolved **before** any conversion |
| sampling | handled with care and **reported, never hidden**. Every value carries its sampling rule (cell-containing, node) and the coordinates the solver says it sampled, so a wrong pairing or rotation is visible in the report |
| stale references | cardiacFOAM's stale Niederer tolerance rows and reference paths (`equivalence_protocol.yaml`, `regression_equivalence/registry.py`) are fixed with the tutorial stream's `niederer2012` migration (its step 5.4b), not here |

**Corrected 2026-09-26 (Task 6, forced by evidence):** the "reference" row
above says the reference holds "the paper's coordinates ... and the
tolerances" for P1–P9. Neither is quite true of the committed
`benchmarks/niederer2011.json` (Task 4):
1. **The paper prints no coordinates at all** (research §1, §3). The
   reference declares a frame convention instead (`stated_by_source: false`:
   origin at P1, axes along the 20/7/3 mm edges) and gives coordinates only
   for the points the paper itself settles (P1, P4, P8, P9). P2, P3, P5, P6
   and P7 are not paper coordinates either — they come from the project
   owner's own (unpublished) manuscript appendix, frame-converted into this
   file's convention; the P2/P3 (and hence P6/P7) naming order is that
   appendix's convention, not independently checked against niederer2011's
   own ESM (not retrieved). See the reference's own `sources` and Controller
   resolution recorded in `.superpowers/sdd/niederer-benchmark-definition.md`,
   section "Resolution of P2-P7".
2. **The paper states no tolerance.** Tolerances live only in the agent's
   comparison request, pre-registered with a rationale, never in the
   reference — the reference schema has no `tolerances` field. The paper's
   one published number (P8, a 37.8–48.7 ms range across codes at the finest
   resolution, §6) is recorded as a `published_values` entry, not a
   tolerance: one source for a tolerance, nothing inferred into a
   paper-derived file.

## 3. What gets built

**Core (solver-neutral):**
- `Quantity(name, value, unit, status, source_artifact, sampled_at, sampling_rule)`,
  where status is `evaluated`, `not_reached` or `not_evaluated`.
- A reader contract. `artifact_value_reader` gets a real signature: roughly
  `(case_root, artifact) -> tuple[Quantity, ...]`, with reader dispatch by
  artifact format. Record `produces` entries gain an optional per-path format,
  so each output can name the reader that understands it.
- Unit normalisation, with sentinels first, and tolerance comparison
  (absolute or relative) over **agent-supplied pairs**.
- A generic schema for a point-sampling reference file.
- A report in the `experiments.py` envelope, tied to each run's evidence.
- A CLI or API entry point an agent calls with two runs, the reference file and
  its pairing.

**openCARP:** a reader for `init_acts_*-thresh.dat` together with the mesh
`.pts`. The sampling points are supplied by the agent, from the reference. The
reader returns node values at those points, with their node coordinates and
the rule `node`. Unit `ms`.

**cardiacFOAM:** a reader for probe files: it parses the `# Probe k (x y z)`
headers and the last data row. Unit `s`, rule `cell-containing`. It lands when
`niederer2012` is a tutorial record (the tutorial stream's 5.4b). Until then,
the core contract and the openCARP half are proved alone.

**The reference file:** built from the paper's own definition. Nothing is
inferred.

**Corrected 2026-09-26 (Task 6, forced by evidence):**
3. **The reader signature above undersold what shipped.** `(case_root,
   artifact) -> tuple[Quantity, ...]` became a reader *object*
   (`ArtifactValueReader`) declaring `value_unit`, `sentinels`,
   `sampling_rule`, `coordinate_unit` and `takes_points`, whose
   `read(case_root, artifact, request)` takes a third argument — the
   request's points — so core, not the reader, resolves sentinels and
   converts units in the right order (sentinels first). `Quantity` also
   gained `sampled_at_unit` (openCARP's coordinates are µm, cardiacFOAM's are
   m; a bare coordinate triple would be ambiguous) and `reason` (a
   `not_evaluated` without one is useless; `cardiacfoam/runtime_evidence.py`
   already required a reason elsewhere).
4. **"A reader for probe files" undersold the split cardiacFOAM's reader
   will need** (still blocked on the tutorial stream's 5.4b): the parser for
   OpenFOAM's probes output format belongs in `omnidriver-openfoam`
   (`openfoam/probes.py`), which knows the layout; the reader that declares
   the unit, the sentinel and what the field means
   (`cardiacfoam/activation_probes.py`) belongs in `omnidriver-cardiacfoam`,
   which knows the physics. Neither exists yet.

## 4. Proof

- A native test, openCARP only: `niedererNVersion` at a coarse `dx` gives
  P1–P9 quantities in ms, sampled at the paper's points with node coordinates
  reported. P1 < P8, and P8 is on the order of G4's 126.45 ms at 500 µm.
- A core test: unit and sentinel handling (`-1 s` → `not_reached`, never
  `-1000 ms`), tolerance comparison, and refusal of a pair whose units cannot
  be converted.
- Once cardiacFOAM's reader lands: the cross-solver comparison run end to end
  by an agent-style request. The report shows each pair's values, units,
  sampled locations and rules.
- A conformance extension, considered in the plan: "a record that declares
  quantity outputs returns them through the reader contract".

## 5. Out of scope

- Judging scientific acceptability. Core reports differences against declared
  tolerances; the benchmark's meaning stays with the agent and the owner.
- The diagonal line (21.4 mm), after P1–P9 works.
- Consensus values from the paper's 11 codes, unless the paper publishes them
  as data (the research will say).
