# Contributing to driverFOAM

Thank you for considering contributing to **driverFOAM**!

This project is a typed planning, validation, provenance, and workflow orchestration layer for reproducible OpenFOAM simulation studies.

## How Can I Contribute?

### 1. Reporting Bugs

If you encounter a bug, please open a GitHub issue and include the following:

- A concise and descriptive title.
- Steps to reproduce the issue, along with explaining the expected behavior.
- Relevant details, such as error logs, stack traces, and an environment description:

  ```plaintext
  - OS version:
  - Python version:
  - driverFOAM version: 0.1.0
  - OpenFOAM version:
  ```

### 2. Suggesting Features

To suggest a feature:

- Open a GitHub issue with the title: **Feature request: [feature title]**.
- Provide a detailed description of the proposed feature.
- Explain its potential benefits for the driverFOAM ecosystem.

### 3. Submitting Code Changes

#### Step 1: Fork and Clone

1. Fork the repository on GitHub.
2. Clone your fork locally.

#### Step 2: Make Your Changes

- Follow the existing Python code structure and organization.
- We require Python >= 3.11. CI matrixes 3.11, 3.12 and 3.13.
- Ensure all structural and semantic contracts are preserved (e.g. `run-document.json` schemas).

**Running `pytest` once is not enough.** The suites must pass in four different
shapes, and each catches something the others cannot — an editable install
leaves the repository on `sys.path`, so a module that reads repo-relative state
at import time still works, and that class of defect is visible only from a
built wheel. [`CLAUDE.md`](CLAUDE.md) has the recipe for building each
environment; in short:

| shape | catches |
|---|---|
| all three packages installed | ordinary regressions |
| core installed alone | core reaching into a sibling package |
| **core installed from a built wheel** | core reading repo-relative state at import time |
| `scripts/check-import-boundaries.py`, `scripts/export-capability-seams.py --check` | import direction; a stale generated table |

CI runs all four. The wheel shape is the one contributors skip and the one that
has found the worst defects.

If a guard test fails, fix the cause — do not weaken the guard and do not add a
skip. `CLAUDE.md` lists each invariant and the test that protects it, and
explains why a skip there hides exactly what the guard exists to find.

#### Step 3: Commit and Push

Write clear, descriptive commit messages and open a Pull Request against the main development branch.

## Plugin Development

driverFOAM is designed to be extensible. External solvers or pipelines should ideally be developed as separate Python packages exposing a `omnidriver.plugins` entry point. Please check the documentation on how to scaffold and link your own plugins without modifying the core `driverFOAM` repository.
