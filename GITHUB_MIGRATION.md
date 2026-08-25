# GitHub Migration Guide

This document explains how to migrate active Python development from the monolithic `noFrontendCardiacFoam` repository into this new `omniDriver` Monorepo.

## The Goal
Currently, the Python orchestrator is actively developed inside `noFrontendCardiacFoam/applications/scripts/driverFoam`. Because the C++ OpenFOAM environment is heavy, we are moving *only the Python framework* into this standalone repository. 

To achieve a universal scientific workflow engine, this repository uses a **Namespace Monorepo** architecture. This means the Python code you copy over must be split into three distinct, decoupled packages.

## Migration Steps (When you are ready to copy)

When you finish your current round of development in `noFrontendCardiacFoam`, follow these steps to migrate the code here:

### 1. Migrate the Core (`omnidriver`)
Copy all solver-agnostic core logic (DAG execution, schemas, cryptographic provenance) into:
`packages/omnidriver/src/omnidriver/core/`

*Rule:* This code must contain zero OpenFOAM vocabulary and zero physics rules.

### 2. Migrate the Environment (`omnidriver-openfoam`)
Copy all OpenFOAM-specific parsing logic (e.g., `mesh_provisioning.py`, `foamlib` mutators) into:
`packages/omnidriver-openfoam/src/omnidriver/openfoam/`

*Rule:* This package depends on the core, but knows nothing about Cardiology.

### 3. Migrate the Domain (`omnidriver-cardiac`)
Copy the `plugins/cardiacfoam` directory (containing electrophysiology logic and ionic models) into:
`packages/omnidriver-cardiac/src/omnidriver/cardiac/`

*Rule:* This package depends on both the core and the OpenFOAM environment to execute its physics rules.

---
Once the files are moved into these packages, you can safely commit and push this repository, keeping your Python orchestrator completely clean and decoupled from the C++ solvers!
