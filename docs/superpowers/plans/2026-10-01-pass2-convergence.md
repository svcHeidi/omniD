# Pass 2: convergence

Owner decisions of 2026-10-01. Findings G1–G18 are in `.superpowers/sdd/generality-review.md`.

## Decisions

| id | decision |
|---|---|
| A | The C++ is scanned once per source state, not once per simulation. The scan is cached under the scratch root, keyed by a hash of the source tree. A recompile changes the hash, and the next plan rescans; `omnidriver scan --plugin P` forces a rescan. |
| B | The catalogs stay the source of truth: descriptions, units, rules and menus. A key the C++ reads but the catalog lacks is accepted, with the type and default the scan read, and reported as `uncatalogued`. That is a note, never a failure. `omnidriver catalog --uncatalogued` lists those keys so an agent can describe them and add them to the catalog. A key the C++ no longer reads is a note too, and a type or menu disagreement is a warning stating both sides; only an invalid case value refuses. |
| G1 | One source of truth: a tutorial's native pipeline is the default, and records are the only entry kind. The case-folder entry, both non-record sweeps, `--entry-kind`, `--config` and the `TutorialSpec` validators are deleted. |
| G4 | `step --apply` takes the same `document:key` patches a study takes, through `commit_case_write`. The second grammar and the second journal are deleted. |
| G7 | The catalog's rules run on every record before it runs. The cross-field science rules are a pre-run step for records. The C++'s own checks stay. |
| G13 | Solver-side helper scripts live in each solver repository's `applications/scripts/`. omnidriver lists them, each with its usage line. An agent uses a script as a record step when the record declares it, or as an auxiliary tool. cardiacCore's `operations/` moves there, and cardiacCore's `scripts/` becomes `applications/scripts/`. |
| G15 | `regression_equivalence/` is deleted. Regression runs through omnidriver with the native `tutorials/Alltest-regression`. |
| G18 | Each solver repository has an `omnidriver.toml` at its root, naming `plugin`, `tutorials`, `source` and `scripts`. omnidriver reads it from the repository it is pointed at. The default-plugin selection graph is deleted. `--plugin` remains for a solver with no repository; when both are given, they must agree. |

**Added 2026-10-02 (owner):**
- **No tests on development code.** Solver runs live in `omnidriver check`, which reports and never gates; pytest tests omnidriver itself.
- **Before a run, the case passes the catalogue's rules and the C++'s required keys.** A key that appears in or disappears from the C++ is explained, never a failure.
- **Case synthesis, launch and the dictionary builder are kept** as a clearly separate build with its own command, outside the record path.
- **`omnidriver.postprocessing` stays in core** as generic helpers; anything OpenFOAM-specific moves to its package.
- **All GPL licence headers are removed.** The licence itself is still open.
- **cardiacCore's `operations/` moves to `applications/scripts/`,** as G13 says.

The cardiacFOAM native branch stays on `omnid/tutorials-are-pointers`. Merging native `main` waits for the owner. A later rescan then shows its new keys as `uncatalogued`, which is the intended behaviour.

## Tracks

Tracks within a wave touch disjoint files and can run in parallel. Every track lands with all shapes at 0 failed, including the native shapes it touches.

**Wave 1**
1. **Scan and catalog (A, B).**
   - One scanner in `omnidriver-openfoam` reads key, type, default, required or optional, dictionary scope, and the selection-table registrations.
   - The cache is keyed by the source hash.
   - The strict plan reports `uncatalogued` as a note, and the drift error goes.
   - `omnidriver scan` and `catalog --uncatalogued` are added.
   - cardiacFOAM and cardiacCore use it the same way. openCARP's baseline is its `+Help` dump.
   - The tests that pin key lists go; tests of the scanner on real C++ replace them.
2. **Dead code:** the repair loop (G3) and compatibility residue (G17).
3. **Parallel and harness:** one MPI helper (G9) and one native harness (G10).

**Wave 2**
4. **Records only (G1)** and the `omnidriver.toml` repository file (G18).
5. **Catalog rules before every run (G7).**
6. **One edit format (G4).**
7. **One reality in the OpenFOAM layer (G6),** shared route helpers (G11), OpenFOAM supplied only (G12), and plan diagnostics through one hook (G5).

**Wave 1 landed** `6b9ff91`. **Wave 2 landed** with the `omnidriver check` command and the pre-run rules. **Wave 3 landed**: package source 30,467 non-blank lines, tests 29,824.

**Wave 3**
8. **The plugin contract collapsed (G2).**
9. **Script discovery (G13)**, with cardiacCore's native move. **Toy plugins merged (G14).** **Always-skipping tests deleted or made native (G8).** **`regression_equivalence/` deleted (G15).**
10. **The separate build** (synthesis, launch and the dictionary builder behind one command). **The post-processing split. The licence headers removed. N-rank evidence in `check`'s C13.**
11. **The final prose sweep.**

**Target:** package source at most 31,000 non-blank lines, from 48,209; tests at most 45,000. After these: electrophysiology testing and training, then electromechanics.
