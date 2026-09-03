# Monorepo Package Migration Implementation Plan

> **Status: executed, with one name changed in flight (noted 2026-09-03).**
> This plan names the third package `omnidriver-cardiac` / `omnidriver.cardiac`
> throughout. It shipped as `omnidriver-cardiacfoam` /
> `omnidriver.cardiacfoam`; no `omnidriver.cardiac` module has ever existed
> here. Read the package name in this document as the one that shipped. A
> survivor of that rename was still breaking
> `scripts/regenerate-ionic-catalog.py`, which built its target path through
> `omnidriver/cardiac/`, until 2026-09-03.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Copy the actively-developed `openfoam_driver` package from
`noFrontendCardiacFoam/applications/scripts/driverFoam` into this repo's three
namespace packages (`omnidriver`, `omnidriver-openfoam`, `omnidriver-cardiac`),
fixing the core/OpenFOAM coupling points identified in `MIGRATION_AUDIT_v2.md`
as part of the move rather than after it.

**Architecture:** PEP 420 namespace packages under `packages/*/src/omnidriver/`.
`omnidriver.core` contains DAG execution, provenance, schemas, and the plugin
contract — zero OpenFOAM vocabulary. `omnidriver.openfoam` contains
`foamlib`-based dict mutation, `controlDict`/`blockMeshDict` handling, and
depends on `omnidriver.core`. `omnidriver.cardiac` contains the electrophysiology
plugin and depends on both.

**Tech Stack:** Python 3.11+, setuptools (PEP 420 namespace packages),
`foamlib`, `PyYAML`, `jsonschema`, `pytest`.

## Global Constraints

- Source of truth for every file copied is
  `/Users/simaocastro/noFrontendCardiacFoam_minor_errors/applications/scripts/driverFoam/openfoam_driver`
  (1710 tests collect cleanly there as of this plan — confirmed, not the
  partially-stripped `openfoam_driver/` tree that used to live at the root of
  this repo).
- `omnidriver.core` MUST NOT import `omnidriver.openfoam` or `omnidriver.cardiac`.
  `omnidriver.openfoam` MUST NOT import `omnidriver.cardiac`.
- No file lands in `omnidriver.core` that imports `foamlib`, or that contains a
  literal `"controlDict"`, `"blockMeshDict"`, `"system"`, or `"constant"` path
  segment used as an OpenFOAM directory/file name (`system/blockMeshDict*`
  *glob patterns for display purposes* are fine if the segment name itself is
  supplied by plugin data, not hardcoded by core — check case by case, see
  Task 4).
- Every task ends with `python3 -m pytest <affected package>/tests -q` run
  from that package's own root, using its own installed environment, not the
  monorepo's.
- Namespace-parent directories (`packages/*/src/omnidriver/`) must have no
  `__init__.py` — already correct in this repo, do not add one.
- Distribution names: `omnidriver` (core), `omnidriver-openfoam`,
  `omnidriver-cardiac`. Import names: `omnidriver.core`, `omnidriver.openfoam`,
  `omnidriver.cardiac`.
- Entry-point group for solver plugins becomes `omnidriver.plugins` (was
  `driverfoam.plugins`).

---

### Task 1: Package scaffolding — three `pyproject.toml` files

**Files:**
- Create: `packages/omnidriver/pyproject.toml`
- Create: `packages/omnidriver-openfoam/pyproject.toml`
- Create: `packages/omnidriver-cardiac/pyproject.toml`
- Modify: `/Users/simaocastro/omnidriver/pyproject.toml` (convert root from a
  buildable package to a workspace root — see Step 4)

**Interfaces:**
- Produces: three independently `pip install -e`-able packages under
  `packages/*`, so Task 2/3/4 have somewhere to copy files into and something
  to run `pytest` against.

- [ ] **Step 1: Write `packages/omnidriver/pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "omnidriver"
version = "0.1.0"
description = "Solver-agnostic scientific workflow orchestrator: DAG execution, provenance, schema validation."
readme = "README.md"
requires-python = ">=3.11"
authors = [{ name = "Simao Nieto de Castro, UCD" }]
dependencies = [
  "jsonschema>=4.0",
  "PyYAML>=6.0",
]

[project.entry-points."omnidriver.plugins"]

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.setuptools.packages.find]
where = ["src"]
include = ["omnidriver*"]

[tool.setuptools.package-data]
"omnidriver.core" = ["generic-plugin.yaml"]
"omnidriver.core.schemas" = ["run-document.json"]
```

- [ ] **Step 2: Write `packages/omnidriver-openfoam/pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "omnidriver-openfoam"
version = "0.1.0"
description = "OpenFOAM environment plugin for omnidriver: controlDict/blockMeshDict handling, foamlib-based dictionary mutation."
readme = "README.md"
requires-python = ">=3.11"
authors = [{ name = "Simao Nieto de Castro, UCD" }]
dependencies = [
  "omnidriver",
  "foamlib>=1.7.5,<2",
  "gmsh>=4.15.2",
]

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.setuptools.packages.find]
where = ["src"]
include = ["omnidriver*"]
```

- [ ] **Step 3: Write `packages/omnidriver-cardiac/pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "omnidriver-cardiac"
version = "0.1.0"
description = "cardiacFoam electrophysiology domain plugin for omnidriver."
readme = "README.md"
requires-python = ">=3.11"
authors = [{ name = "Simao Nieto de Castro, UCD" }]
dependencies = [
  "omnidriver",
  "omnidriver-openfoam",
  "numpy>=1.24",
]

[project.entry-points."omnidriver.plugins"]
cardiacfoam = "omnidriver.cardiac.cardiacfoam_plugin:CardiacFoamPlugin"

[project.optional-dependencies]
post = [
  "matplotlib>=3.7",
  "pandas>=2.0",
  "plotly>=5.0",
  "prompt-toolkit>=3.0",
  "openpyxl>=3.1",
]

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.setuptools.packages.find]
where = ["src"]
include = ["omnidriver*"]

[tool.setuptools.package-data]
"omnidriver.cardiac" = ["plugin.yaml", "dict_key_allowlist.json"]
```

- [ ] **Step 4: Replace the root `pyproject.toml` with a workspace marker**

The current root `pyproject.toml` still describes the old flat
`cardiacfoam-tutorials-driver` package (`openfoam_driver.cli:main` entry
point, `driverfoam.plugins` group, `openfoam_driver*` package find). Once
Tasks 2-4 finish, nothing under the repo root is importable Python anymore —
everything lives under `packages/*`. Replace it with a minimal workspace
file so `pip install -e packages/*` is the supported install path and no
stale `openfoam_driver` distribution can shadow the new packages:

```toml
[project]
name = "omnidriver-workspace"
version = "0.1.0"
description = "Monorepo workspace root. Install individual packages: pip install -e packages/omnidriver -e packages/omnidriver-openfoam -e packages/omnidriver-cardiac"
requires-python = ">=3.11"

[tool.pytest.ini_options]
markers = [
    "integration: tests requiring a real cardiacFoam binary (skipped by default in CI)",
]
```

- [ ] **Step 5: Install all three in editable mode and verify they resolve**

```bash
cd /Users/simaocastro/omnidriver
pip install -e packages/omnidriver -e packages/omnidriver-openfoam -e packages/omnidriver-cardiac
python3 -c "import omnidriver.core, omnidriver.openfoam, omnidriver.cardiac; print('ok')"
```

Expected: `ok` (all three currently-empty namespace packages import — they
have nothing in them yet, that's fine, this only proves the namespace
wiring and dependency graph are correct before Task 2 puts real code in).

- [ ] **Step 6: Commit**

```bash
git add packages/*/pyproject.toml pyproject.toml
git commit -m "chore: scaffold three-package pyproject.toml workspace"
```

---

### Task 2: Bulk-copy the cardiac domain subtree

**Files:**
- Create: `packages/omnidriver-cardiac/src/omnidriver/cardiac/` (from
  `openfoam_driver/plugins/cardiacfoam/` and
  `openfoam_driver/plugins/cardiacfoam_plugin.py` in the monorepo)
- Create: `packages/omnidriver-cardiac/tests/` (from
  `openfoam_driver/tests/` files that import `plugins.cardiacfoam*` — identify
  with the grep in Step 3 below)

**Interfaces:**
- Consumes: `omnidriver.core` (Task 3) and `omnidriver.openfoam` (Task 4) —
  this task only copies files and rewrites their import statements; it does
  not need Tasks 3/4 finished first, but the package won't *import* cleanly
  until they are. Do the copy now, defer the import-clean verification to
  after Task 4.
- Produces: `omnidriver.cardiac.cardiacfoam_plugin.CardiacFoamPlugin` — the
  class Task 1's entry-point declaration already names.

- [ ] **Step 1: Copy the cardiac plugin source tree**

```bash
MONO=/Users/simaocastro/noFrontendCardiacFoam_minor_errors/applications/scripts/driverFoam/openfoam_driver
DEST=/Users/simaocastro/omnidriver/packages/omnidriver-cardiac/src/omnidriver/cardiac

cp -R "$MONO/plugins/cardiacfoam/." "$DEST/"
cp "$MONO/plugins/cardiacfoam_plugin.py" "$DEST/cardiacfoam_plugin.py"
find "$DEST" -name "__pycache__" -type d -exec rm -rf {} +
```

- [ ] **Step 2: Rewrite import statements**

Every file under `$DEST` currently imports as if it were still
`openfoam_driver.plugins.cardiacfoam` / `..plugins.cardiacfoam` /
`openfoam_driver.core` / `..core` / `..runtime.mutators`. Rewrite package
prefixes:

```bash
cd /Users/simaocastro/omnidriver/packages/omnidriver-cardiac/src/omnidriver/cardiac
grep -rl "openfoam_driver\.plugins\.cardiacfoam\|from \.\.plugins\.cardiacfoam\|from \. import\|from \.\." . --include="*.py" \
  | xargs sed -i '' \
      -e 's/openfoam_driver\.plugins\.cardiacfoam_plugin/omnidriver.cardiac.cardiacfoam_plugin/g' \
      -e 's/openfoam_driver\.plugins\.cardiacfoam/omnidriver.cardiac/g' \
      -e 's/from \.\.\.plugins\.cardiacfoam_plugin/from .cardiacfoam_plugin/g' \
      -e 's/from \.\.\.plugins\.cardiacfoam/from ./g' \
      -e 's/openfoam_driver\.core\.runtime\.mutators/omnidriver.openfoam.mutators/g' \
      -e 's/openfoam_driver\.core\.specs\.mesh_provisioning/omnidriver.openfoam.mesh_provisioning/g' \
      -e 's/openfoam_driver\.core/omnidriver.core/g'
```

This is a mechanical first pass, not the final word — Step 3 catches what it
missed.

- [ ] **Step 3: Grep for anything the sed pass missed**

```bash
grep -rn "openfoam_driver" /Users/simaocastro/omnidriver/packages/omnidriver-cardiac/src --include="*.py"
```

Expected: no output. Anything printed is a relative import (`from ...core`,
`from ....runtime`) the sed patterns above didn't anticipate — fix each one
by hand, following the same target-name mapping (`..core` → `omnidriver.core`
absolute import; `..runtime.mutators` → `omnidriver.openfoam.mutators`
absolute import — relative imports crossing a package boundary must become
absolute, since `omnidriver.cardiac` and `omnidriver.openfoam` are separate
distributions now, not siblings under the same package tree).

- [ ] **Step 4: Copy the cardiac-touching tests**

```bash
MONO_TESTS=/Users/simaocastro/noFrontendCardiacFoam_minor_errors/applications/scripts/driverFoam/openfoam_driver/tests
grep -rl "plugins\.cardiacfoam\|CardiacFoamPlugin" "$MONO_TESTS" --include="*.py" > /tmp/cardiac_test_files.txt
wc -l /tmp/cardiac_test_files.txt
```

For each path in `/tmp/cardiac_test_files.txt`, copy it to the matching
relative path under
`packages/omnidriver-cardiac/tests/`, then apply the same import rewrite as
Step 2 to the copied test files (`sed` over the copied files, not in place on
the monorepo originals).

- [ ] **Step 5: Commit**

```bash
cd /Users/simaocastro/omnidriver
git add packages/omnidriver-cardiac
git commit -m "feat: copy cardiacfoam plugin into omnidriver-cardiac package"
```

Do not run this package's tests yet — it depends on `omnidriver.openfoam`,
which does not exist until Task 4. Verification happens at the end of Task 4.

---

### Task 3: Bulk-copy the solver-agnostic core

**Files:**
- Create: `packages/omnidriver/src/omnidriver/core/` from
  `openfoam_driver/core/**` in the monorepo, **excluding** the files listed
  in Task 4 (they go to `omnidriver-openfoam` instead)
- Create: `packages/omnidriver/src/omnidriver/` top-level modules from
  `openfoam_driver/{__init__.py,__main__.py,cli.py,conftest.py,dict_entries.py,sweep_materialize.py,sweep_routing.py}`
- Create: `packages/omnidriver/tests/` from the remaining
  `openfoam_driver/tests/**` not already claimed by Task 2 Step 4

**Interfaces:**
- Produces: `omnidriver.core.plugin_interface.DriverContext`,
  `omnidriver.core.plugin_capabilities.*`, `omnidriver.core.runtime.registry`,
  `omnidriver.core.runtime.run_document_exec`, `omnidriver.cli.main` — the
  names Task 1's `[project.scripts]` and Task 2/4's cross-package imports
  depend on.

- [ ] **Step 1: Copy `core/` minus the OpenFOAM-coupled files**

```bash
MONO=/Users/simaocastro/noFrontendCardiacFoam_minor_errors/applications/scripts/driverFoam/openfoam_driver
DEST=/Users/simaocastro/omnidriver/packages/omnidriver/src/omnidriver/core

cp -R "$MONO/core/." "$DEST/"
find "$DEST" -name "__pycache__" -type d -exec rm -rf {} +

# Remove the files that belong in omnidriver-openfoam instead (Task 4 copies
# these from $MONO directly, not from here):
rm "$DEST/runtime/mutators.py"
rm "$DEST/runtime/foam_backend.py"
rm "$DEST/runtime/openfoam_environment.py"
rm "$DEST/runtime/environment_preflight.py"
rm "$DEST/specs/mesh_provisioning.py"
rm "$DEST/specs/tet_mesh_provisioning.py"
rm "$DEST/specs/mesh_geometry.py"
rm "$DEST/specs/dict_builder.py"
rm "$DEST/specs/apply_overrides.py"
```

`provenance_inputs.py` and `compatibility.py` stay in `$DEST` — they're
mixed-concern files that get edited in place by Tasks 5 and 6, not moved
wholesale.

- [ ] **Step 2: Copy the remaining top-level modules**

```bash
DEST_ROOT=/Users/simaocastro/omnidriver/packages/omnidriver/src/omnidriver
for f in __init__.py __main__.py cli.py conftest.py dict_entries.py sweep_materialize.py sweep_routing.py; do
  cp "$MONO/$f" "$DEST_ROOT/$f"
done
cp -R "$MONO/postprocessing" "$DEST_ROOT/postprocessing"
cp -R "$MONO/schemas" "$DEST_ROOT/schemas"
cp -R "$MONO/scripts" "$DEST_ROOT/scripts"
find "$DEST_ROOT" -name "__pycache__" -type d -exec rm -rf {} +
```

- [ ] **Step 3: Rewrite the package prefix everywhere**

```bash
cd /Users/simaocastro/omnidriver/packages/omnidriver/src/omnidriver
grep -rl "openfoam_driver" . --include="*.py" | xargs sed -i '' 's/openfoam_driver/omnidriver/g'
```

This turns `omnidriver.core.X` references into themselves correctly (they
were already `openfoam_driver.core.X` → `omnidriver.core.X`), and top-level
`openfoam_driver.dict_entries` → `omnidriver.dict_entries`, matching the new
layout. It does **not** yet fix the lazy `omnidriver.plugins.cardiacfoam.*`
imports left over in `compatibility.py`, `dict_entries.py`,
`sweep_materialize.py`, `sweep_routing.py` — those are handled explicitly in
Task 6, because they need to become `omnidriver.cardiac.*` (a different
distribution), which a blind prefix-swap would get wrong (it would produce
`omnidriver.plugins.cardiacfoam`, a module that no longer exists anywhere).

- [ ] **Step 4: Confirm nothing here imports `foamlib` or OpenFOAM-specific literals**

```bash
grep -rln "foamlib" /Users/simaocastro/omnidriver/packages/omnidriver/src --include="*.py"
grep -rln '"controlDict"\|"blockMeshDict"\|/ "system" /\|/ "constant"' /Users/simaocastro/omnidriver/packages/omnidriver/src --include="*.py"
```

Expected: no output from the first command. The second may still show
`provenance_inputs.py` — that's expected and is fixed by Task 5, not this
task. If any *other* file shows up, move it to
`packages/omnidriver-openfoam/src/omnidriver/openfoam/` instead (repeat Task
4's copy pattern for it) and remove it from here.

- [ ] **Step 5: Copy the remaining tests**

```bash
MONO_TESTS=/Users/simaocastro/noFrontendCardiacFoam_minor_errors/applications/scripts/driverFoam/openfoam_driver/tests
DEST_TESTS=/Users/simaocastro/omnidriver/packages/omnidriver/tests

comm -23 \
  <(find "$MONO_TESTS" -name "*.py" | sed "s|$MONO_TESTS/||" | sort) \
  <(sort /tmp/cardiac_test_files.txt | sed "s|$MONO_TESTS/||") \
  > /tmp/core_test_files.txt

while read -r rel; do
  mkdir -p "$DEST_TESTS/$(dirname "$rel")"
  cp "$MONO_TESTS/$rel" "$DEST_TESTS/$rel"
done < /tmp/core_test_files.txt

find "$DEST_TESTS" -name "__pycache__" -type d -exec rm -rf {} +
cd /Users/simaocastro/omnidriver/packages/omnidriver
grep -rl "openfoam_driver" tests --include="*.py" | xargs sed -i '' 's/openfoam_driver/omnidriver/g'
```

Some of these copied tests will actually be `omnidriver-openfoam` tests (e.g.
`test_mutators.py`, `test_mesh_provisioning.py`) — Task 4 Step 4 moves those
out into the openfoam package's own `tests/` directory; leave them here for
now, this step's only job is "copy everything not already claimed by cardiac."

- [ ] **Step 6: Commit**

```bash
cd /Users/simaocastro/omnidriver
git add packages/omnidriver
git commit -m "feat: copy solver-agnostic core into omnidriver package"
```

Do not run `pytest` yet — `compatibility.py`'s lazy cardiac imports and
`provenance_inputs.py`'s `mutators` import are still broken. Verification
happens after Task 6.

---

### Task 4: Bulk-copy the OpenFOAM environment subtree

**Files:**
- Create: `packages/omnidriver-openfoam/src/omnidriver/openfoam/` from the
  eight files removed from `omnidriver.core` in Task 3 Step 1
- Create: `packages/omnidriver-openfoam/tests/`

**Interfaces:**
- Produces: `omnidriver.openfoam.mutators.read_foam_entry` /
  `update_foam_entry`, `omnidriver.openfoam.mesh_provisioning.default_block_mesh_dict_text`
  — the names Task 5 and Task 6 wire back into core through the capability
  interface, and the names Task 2's cardiac plugin now imports absolutely.

- [ ] **Step 1: Copy the eight files**

```bash
MONO=/Users/simaocastro/noFrontendCardiacFoam_minor_errors/applications/scripts/driverFoam/openfoam_driver
DEST=/Users/simaocastro/omnidriver/packages/omnidriver-openfoam/src/omnidriver/openfoam

mkdir -p "$DEST"
cp "$MONO/core/runtime/mutators.py" "$DEST/mutators.py"
cp "$MONO/core/runtime/foam_backend.py" "$DEST/foam_backend.py"
cp "$MONO/core/runtime/openfoam_environment.py" "$DEST/openfoam_environment.py"
cp "$MONO/core/runtime/environment_preflight.py" "$DEST/environment_preflight.py"
cp "$MONO/core/specs/mesh_provisioning.py" "$DEST/mesh_provisioning.py"
cp "$MONO/core/specs/tet_mesh_provisioning.py" "$DEST/tet_mesh_provisioning.py"
cp "$MONO/core/specs/mesh_geometry.py" "$DEST/mesh_geometry.py"
cp "$MONO/core/specs/dict_builder.py" "$DEST/dict_builder.py"
cp "$MONO/core/specs/apply_overrides.py" "$DEST/apply_overrides.py"
touch "$DEST/__init__.py"
```

- [ ] **Step 2: Rewrite import statements**

```bash
cd /Users/simaocastro/omnidriver/packages/omnidriver-openfoam/src/omnidriver/openfoam
grep -rl "openfoam_driver" . --include="*.py" | xargs sed -i '' \
  -e 's/openfoam_driver\.core\.runtime\.mutators/omnidriver.openfoam.mutators/g' \
  -e 's/openfoam_driver\.core\.specs\.mesh_provisioning/omnidriver.openfoam.mesh_provisioning/g' \
  -e 's/openfoam_driver\.core\.specs\.mesh_geometry/omnidriver.openfoam.mesh_geometry/g' \
  -e 's/openfoam_driver\.core\.specs\.dict_builder/omnidriver.openfoam.dict_builder/g' \
  -e 's/openfoam_driver\.core\.specs\.apply_overrides/omnidriver.openfoam.apply_overrides/g' \
  -e 's/openfoam_driver\.core/omnidriver.core/g'
```

These 8 files import each other with relative imports (`from .mutators
import ...`, `from ..runtime.mutators import ...`) — since they're all now
siblings in the same flat `omnidriver/openfoam/` package, collapse any
`..runtime.` or `..specs.` segment down to `.` (same-package relative
import):

```bash
grep -rn "from \.\." . --include="*.py"
```

Fix each hit by hand: `from ..runtime.mutators import X` becomes `from
.mutators import X`; `from ..specs.mesh_provisioning import X` becomes `from
.mesh_provisioning import X`.

- [ ] **Step 3: Confirm no `omnidriver.core.specs`/`omnidriver.core.runtime` references remain**

```bash
grep -rn "omnidriver\.core\.specs\|omnidriver\.core\.runtime" /Users/simaocastro/omnidriver/packages/omnidriver-openfoam/src --include="*.py"
```

Expected: no output. If something shows up, it's importing a symbol that's
still in `omnidriver.core` proper (e.g. `DriverContext`,
`CaseCompatibilityRequest`) — that's a legitimate `omnidriver.core.X` import
(not `core.specs`/`core.runtime`) and doesn't need fixing; only
`core.specs.*` / `core.runtime.*` targets are wrong here, since those modules
no longer exist at that path.

- [ ] **Step 4: Move the OpenFOAM-side tests out of the core test copy**

```bash
CORE_TESTS=/Users/simaocastro/omnidriver/packages/omnidriver/tests
DEST_TESTS=/Users/simaocastro/omnidriver/packages/omnidriver-openfoam/tests
mkdir -p "$DEST_TESTS/core"

for f in test_mutators.py test_mutators_differential.py test_mesh_provisioning.py \
         test_tet_mesh_provisioning.py test_foam_backend.py test_apply_overrides.py; do
  find "$CORE_TESTS" -name "$f" -exec sh -c 'mv "$1" "'"$DEST_TESTS"'/core/$(basename "$1")"' _ {} \;
done

cd "$DEST_TESTS"
grep -rl "openfoam_driver\|omnidriver\.core\.specs\.mesh_provisioning\|omnidriver\.core\.runtime\.mutators" . --include="*.py" | xargs sed -i '' \
  -e 's/omnidriver\.core\.runtime\.mutators/omnidriver.openfoam.mutators/g' \
  -e 's/omnidriver\.core\.specs\.mesh_provisioning/omnidriver.openfoam.mesh_provisioning/g' \
  -e 's/omnidriver\.core\.specs\.apply_overrides/omnidriver.openfoam.apply_overrides/g'
```

- [ ] **Step 5: Install and run this package's tests standalone**

```bash
cd /Users/simaocastro/omnidriver
pip install -e packages/omnidriver -e packages/omnidriver-openfoam
python3 -m pytest packages/omnidriver-openfoam/tests -q
```

Expected: all copied tests pass. If a test fails on an import, it's almost
always a leftover `from ..core.specs...` or `from ..core.runtime...` relative
import Step 2/3 missed — fix and re-run.

- [ ] **Step 6: Commit**

```bash
git add packages/omnidriver-openfoam
git commit -m "feat: copy OpenFOAM environment plugin into omnidriver-openfoam package"
```

---

### Task 5: Give core a plugin-routed way to read/write config values

**Why this task exists:** `provenance_inputs.py::_select_start_time` needs
the *value* of `startFrom`/`startTime` out of `system/controlDict` to decide
which time directory is the real start state — not just the *path* to that
file. Resolving the path by `role` (already possible via `case_files`, no new
code needed) is not enough on its own: reading the value still means calling
`foamlib`, and `foamlib` now lives in `omnidriver-openfoam`, a package `core`
must not depend on. This task adds a capability so the *plugin* reads its own
config format and hands core the value, instead of core importing the
parser.

**Files:**
- Modify: `packages/omnidriver/src/omnidriver/core/plugin_capabilities.py`
- Modify: `packages/omnidriver/src/omnidriver/core/compatibility.py`
- Create: `packages/omnidriver-openfoam/src/omnidriver/openfoam/config_values.py`
- Test: `packages/omnidriver/tests/core/test_provenance_inputs.py`

**Interfaces:**
- Produces: `driver_context.capabilities.config_values.read(path: Path, key:
  str) -> str | None`, consumed by Task 6's rewrite of `provenance_inputs.py`.

- [ ] **Step 1: Add the capability protocol**

Append to `packages/omnidriver/src/omnidriver/core/plugin_capabilities.py`
(near the other `Capability` Protocol classes, e.g. next to
`CaseFileContractCapability`):

```python
class ConfigValueCapability(Protocol):
    """Read a single key out of a plugin-format configuration file.

    core resolves *which* file by role (``CaseFileContractCapability``);
    this capability resolves the *value* inside it, so core never needs to
    know the file's syntax. The OpenFOAM plugin implements this over
    ``foamlib``; a FEniCS plugin would implement it over its own XML/JSON
    reader.

    :adapts: get_config_value_reader
    :consumed-by: omnidriver/core/runtime/provenance_inputs.py
    :fallback: legacy_config_value_reader
    :status: optional
    """

    def read(self, path: Path, key: str) -> str | None: ...
```

- [ ] **Step 2: Add the adapter**

In the same file, next to `_CaseFileContractAdapter`:

```python
@dataclass(frozen=True)
class _ConfigValueAdapter:
    plugin: "SolverPlugin"

    def read(self, path: Path, key: str) -> str | None:
        hook = getattr(self.plugin, "get_config_value_reader", None)
        if callable(hook):
            reader = hook()
            return reader(path, key)
        from .compatibility import legacy_config_value_reader

        return legacy_config_value_reader(path, key)
```

Wire it into whatever function builds the full `CapabilityManifest` (search
`build_capability_manifest` in the same file for where the other adapters —
`_CaseFileContractAdapter`, `_CaseProvenanceAdapter` — get instantiated, and
add `config_values=_ConfigValueAdapter(plugin)` alongside them).

- [ ] **Step 3: Add the legacy fallback in `compatibility.py`**

```python
@_instrumented
def legacy_config_value_reader(path, key: str) -> str | None:
    """Preserve the historical direct-foamlib read for plugins that don't
    implement get_config_value_reader. Why: every existing plugin call site
    read entries via mutators.read_foam_entry before this capability
    existed. Activation: a plugin has no get_config_value_reader hook.
    Plan 2 seam: a non-OpenFOAM plugin must implement the hook explicitly —
    this fallback assumes OpenFOAM syntax and is not a safe default for
    other environments."""

    from omnidriver.openfoam.mutators import read_foam_entry

    return read_foam_entry(path, key)
```

This keeps `compatibility.py`'s existing "cardiac/OpenFOAM-shaped legacy
fallback, neutral otherwise" pattern (see the file's own docstring) — it does
import `omnidriver.openfoam` here, same as it already imports
`omnidriver.cardiac.*` elsewhere for other legacy fallbacks. That's a
`core → openfoam` dependency inside a `legacy_*` fallback function, which
Task 6's dependency check treats as acceptable (see Task 6 Step 4) precisely
*because* it's confined to `compatibility.py`'s documented compatibility
boundary and never reached when a plugin implements its own hook.

- [ ] **Step 4: Implement the OpenFOAM plugin's own hook**

Create `packages/omnidriver-openfoam/src/omnidriver/openfoam/config_values.py`:

```python
from __future__ import annotations

from pathlib import Path

from .mutators import read_foam_entry


def openfoam_config_value_reader():
    def _read(path: Path, key: str) -> str | None:
        return read_foam_entry(path, key)

    return _read
```

Then in `packages/omnidriver-cardiac/src/omnidriver/cardiac/cardiacfoam_plugin.py`
(the class the entry point in Task 1 names), add the hook method:

```python
def get_config_value_reader(self):
    from omnidriver.openfoam.config_values import openfoam_config_value_reader

    return openfoam_config_value_reader()
```

- [ ] **Step 5: Run the core test suite for this file**

```bash
cd /Users/simaocastro/omnidriver
python3 -m pytest packages/omnidriver/tests/core/test_plugin_profile.py -q
```

Expected: passes (this only added a new capability, nothing consumes it yet
— Task 6 is where `provenance_inputs.py` starts calling it).

- [ ] **Step 6: Commit**

```bash
git add packages/omnidriver/src/omnidriver/core/plugin_capabilities.py \
        packages/omnidriver/src/omnidriver/core/compatibility.py \
        packages/omnidriver-openfoam/src/omnidriver/openfoam/config_values.py \
        packages/omnidriver-cardiac/src/omnidriver/cardiac/cardiacfoam_plugin.py
git commit -m "feat: add ConfigValueCapability so core reads config values without importing foamlib"
```

---

### Task 6: Fix `provenance_inputs.py` and `compatibility.py` to use the new capability

**Files:**
- Modify: `packages/omnidriver/src/omnidriver/core/runtime/provenance_inputs.py:83,95-116,327`
- Modify: `packages/omnidriver/src/omnidriver/core/compatibility.py` (the
  `..plugins.cardiacfoam*` import targets — rewrite to `omnidriver.cardiac.*`)
- Modify: `packages/omnidriver/src/omnidriver/dict_entries.py`,
  `sweep_materialize.py`, `sweep_routing.py` (same rewrite)
- Test: `packages/omnidriver/tests/core/test_provenance_inputs.py`,
  `packages/omnidriver/tests/core/test_trust_boundary_end_to_end.py`

**Interfaces:**
- Consumes: `driver_context.capabilities.config_values.read(path, key)` from
  Task 5, and `case_files` filtered by `role` (already existing core
  vocabulary, see `MIGRATION_AUDIT_v2.md` §2-3).

- [ ] **Step 1: Replace the `mutators` import and the two hardcoded reads**

In `provenance_inputs.py`, remove:

```python
from .mutators import read_foam_entry
```

Replace `_select_start_time` (currently lines 95-116):

```python
def _select_start_time(case_root: Path, driver_context: "DriverContext") -> str:
    """The **selected** start-time directory, per the plugin's control file.

    ``startFrom latestTime`` selects the latest written time, not ``0``;
    ``firstTime`` selects the earliest. Anything else (including an absent
    control file) falls back to the literal ``startTime`` value, or ``"0"``
    if that too is absent -- the common case, but never assumed without
    checking.
    """
    control_path = _control_file_path(case_root, driver_context)
    if control_path is None:
        return _DEFAULT_START_TIME

    read = driver_context.capabilities.config_values.read
    start_from = (read(control_path, "startFrom") or "startTime").strip()

    if start_from in ("latestTime", "firstTime"):
        candidates = _list_time_dir_names(case_root)
        if not candidates:
            return _DEFAULT_START_TIME
        selector = max if start_from == "latestTime" else min
        return selector(candidates, key=float)

    start_time = read(control_path, "startTime")
    return start_time.strip() if start_time is not None else _DEFAULT_START_TIME


def _control_file_path(case_root: Path, driver_context: "DriverContext") -> Path | None:
    for rule in driver_context.capabilities.case_files.required_rules():
        if rule.role == "openfoam.control_dict":
            return case_root / rule.path
    return None
```

Every existing caller of `_select_start_time(case_root)` needs the
`driver_context` argument added — find them with:

```bash
grep -n "_select_start_time(" /Users/simaocastro/omnidriver/packages/omnidriver/src/omnidriver/core/runtime/provenance_inputs.py
```

and thread `driver_context` through from `enumerate_case_inputs`'s own
`driver_context` parameter (it already has one — check its signature at line
288 before assuming; the file's `TYPE_CHECKING` import of `DriverContext`
confirms this is expected to be plumbed through, not resolved locally).

- [ ] **Step 2: Fix `walk_roots` (was line 327)**

Replace the literal `["system", "constant", ...]` construction with a role
lookup over the plugin's full `case_files` list (not just `required_rules()`
— a role can be declared `conditional`):

```python
def _openfoam_root_dirnames(driver_context: "DriverContext") -> tuple[str, ...]:
    """Top-level case directories the active plugin's config lives under,
    derived from the first path segment of every declared case file rule."""
    profile = driver_context.plugin.get_profile()
    segments = {Path(rule.path).parts[0] for rule in profile.case_files if rule.path}
    return tuple(sorted(segments))
```

then in the function that builds `walk_roots`, replace the hardcoded
`case_root / "system"`, `case_root / "constant"` pair with:

```python
walk_roots = [case_root / d for d in _openfoam_root_dirnames(driver_context)] + [
    case_root / selected_start_time,
]
```

- [ ] **Step 3: Run the two tests this file's behavior is pinned by**

```bash
cd /Users/simaocastro/omnidriver
python3 -m pytest packages/omnidriver/tests/core/test_provenance_inputs.py \
                   packages/omnidriver/tests/core/test_trust_boundary_end_to_end.py -q
```

Expected: some failures here are expected on the first run — the copied
tests still call `_select_start_time(case_root)` with the old one-argument
signature, and still assert against `"system"`/`"constant"` as if they were
special-cased rather than derived from `case_files`. Fix each failing test by
updating the call site to pass `driver_context` (the fixture already
constructs one — check `conftest.py` for the fixture name) and by confirming
the fixture's `plugin.yaml` (or its `GenericOpenFOAMPlugin` test double)
declares `case_profile.dictionaries` entries with `path` starting `system/`
and `constant/` — if it doesn't, add them, since `_openfoam_root_dirnames`
now derives the walked directories from exactly that declaration instead of
assuming it.

- [ ] **Step 4: Rewrite the remaining `plugins.cardiacfoam` references**

```bash
cd /Users/simaocastro/omnidriver/packages/omnidriver/src/omnidriver
grep -rln "plugins\.cardiacfoam" . --include="*.py"
```

For each hit (`compatibility.py`, `dict_entries.py`, `sweep_materialize.py`,
`sweep_routing.py`), change the import target from
`..plugins.cardiacfoam_plugin` / `..plugins.cardiacfoam.X` to
`omnidriver.cardiac.cardiacfoam_plugin` / `omnidriver.cardiac.X` (absolute
import — these now cross a package boundary, matching the pattern in Task 5
Step 3).

`sweep_materialize.py::_materialize_case_legacy` is dead code (nothing calls
it — confirmed in `MIGRATION_AUDIT_v2.md` §Task 4). Delete the function
instead of fixing its import:

```bash
grep -n "_materialize_case_legacy" /Users/simaocastro/omnidriver/packages/omnidriver/src/omnidriver/sweep_materialize.py
```

Remove the function body found there.

- [ ] **Step 5: Full test run for the core package**

```bash
cd /Users/simaocastro/omnidriver
python3 -m pytest packages/omnidriver/tests -q
```

Expected: 0 collection errors. Some individual test failures are still
possible if a fixture elsewhere assumed the old cardiac-default
`legacy_default_driver_context()` — track those down by reading the
traceback; every one should resolve to either "test needs the
`omnidriver-cardiac` package installed to use the cardiac default" (install
it: `pip install -e packages/omnidriver-cardiac`) or "test needs updating to
construct an explicit `GenericOpenFOAMPlugin`-based `driver_context` instead
of relying on the default."

- [ ] **Step 6: Commit**

```bash
git add packages/omnidriver
git commit -m "fix: resolve provenance paths by plugin role instead of hardcoded OpenFOAM strings"
```

---

### Task 7: Full-workspace verification and entry-point registration

**Files:**
- Modify: `packages/omnidriver/pyproject.toml` (`[project.scripts]`)
- Test: all three packages' `tests/`

**Interfaces:**
- Produces: a working `omnidriver` console command, and a fully installed
  three-package workspace where `driver_context()` with no explicit plugin
  resolves the cardiac plugin through the `omnidriver.plugins` entry-point
  group (Task 1 registered it there in Step 3) rather than a hardcoded
  import.

- [ ] **Step 1: Add the console script**

In `packages/omnidriver/pyproject.toml`, add:

```toml
[project.scripts]
omnidriver = "omnidriver.cli:main"
```

- [ ] **Step 2: Install everything fresh and confirm entry-point discovery**

```bash
cd /Users/simaocastro/omnidriver
pip install -e packages/omnidriver -e packages/omnidriver-openfoam -e packages/omnidriver-cardiac
python3 -c "
from importlib.metadata import entry_points
print(list(entry_points(group='omnidriver.plugins')))
"
```

Expected: `[EntryPoint(name='cardiacfoam', value='omnidriver.cardiac.cardiacfoam_plugin:CardiacFoamPlugin', group='omnidriver.plugins')]`

- [ ] **Step 3: Run every package's suite from the workspace root**

```bash
cd /Users/simaocastro/omnidriver
python3 -m pytest packages/omnidriver/tests packages/omnidriver-openfoam/tests packages/omnidriver-cardiac/tests -q
```

Expected: 0 collection errors, pass count close to the monorepo's original
1710 (some tests legitimately don't port over — anything marked
`skip_without_monorepo`, since this repo no longer has `tutorials/` /
`applications/` siblings to read real tutorial cases from).

- [ ] **Step 4: Commit**

```bash
git add packages/omnidriver/pyproject.toml
git commit -m "feat: register omnidriver console script and confirm cross-package entry-point discovery"
```

---

## Self-Review

**Spec coverage:** GITHUB_MIGRATION.md's three migration steps map to Tasks
2/3/4 (copy) plus Tasks 5/6 (fix boundary). ARCHITECTURE.md's "Immediate
Migration Goals" Task 0 (default context) is resolved by Task 5's capability
plus Task 7's entry-point discovery replacing the hardcoded import; Task 1
(role vocabulary) needs no new work — it's already correct in the copied
`plugin_profile.py`/`plugin_capabilities.py`, verified during Task 3 Step 4's
grep; Task 2 (case-runnability) is untouched by design; Task 3/3b/4 from
`ARCHITECTURE.md` are this plan's Tasks 5/6 (provenance role lookup) and
Task 4 (mesh/mutators extraction) respectively; the package rename item
becomes moot — this plan produces `omnidriver.*` directly rather than
renaming `openfoam_driver` in place.

**Gaps deliberately left open for a follow-up plan, not this one:** the
`GenericOpenFOAMPlugin` vs. `CardiacFoamPlugin` default-selection policy
(Task 5/6 make the read-path plugin-routed, but `legacy_default_driver_context`
still defaults to cardiac when no plugin is given — that's a product
decision, not a mechanical migration step, and changing it changes observable
CLI behavior); CI configuration for the new multi-package layout; publishing
the three packages to a package index.
