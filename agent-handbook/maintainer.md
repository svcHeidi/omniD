# Maintainer role

Maintain OmniD's generic implementation without silently broadening a solver
adapter's scientific contract.

- Read `CLAUDE.md` for package boundaries and verification requirements.
- Preserve unrelated working-tree changes and test the narrowest affected
  package boundary.
- Put OpenFOAM conventions in `omnidriver-openfoam`, solver meaning in the
  relevant solver package, and generic orchestration only in Core.
- When a behavior change affects planning, staging, resume, evidence, or
  transactions, add a focused regression test and state the affected adapter
  contract.
