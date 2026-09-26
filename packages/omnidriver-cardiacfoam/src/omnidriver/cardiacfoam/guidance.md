# cardiacFOAM through omniD

Study keys are `<document>:<dotted.key>`, e.g.
`constant/electroProperties:singleCellSolverCoeffs.tissue`. `describe` lists
every key a record's case accepts, in `record_surface.keys`. Each rule below
is one the record-key validator (`record_key_validation.record_key_validator`)
or the catalogue already enforces; none is new.

- **Two documents are catalogued**: `constant/electroProperties` and
  `constant/physicsProperties`. A key in either must be in the catalogue,
  which is drift-gated against the C++ (`test_strict_dict_key_scanner_allowlist_is_current`).
  A key the catalogue lacks is refused by name, never written.
- **Write the active solver's scope.** Coefficients live under
  `<myocardiumSolver>Coeffs`: for `myocardiumSolver singleCellSolver;`, write
  `singleCellSolverCoeffs.tissue`. `describe` lists the case's own scope. A
  first segment that is no `<solver>Coeffs` of the catalogue's
  `myocardiumSolver` menu is refused.
- **Shape, not meaning.** A value is checked against its entry's `value_kind`
  by shape only. An `enum` value is not checked against its `menu`, and an
  entry's conditions on other keys are not evaluated. Read the `menu` and
  `description` before choosing a value.
- **Named segments.** A `<name>` segment in a listed key (for example
  `ecgDomains.<name>.ecgSolver`) is a name the case chooses. Where the
  catalogue gives a closed set of names, a name outside it is refused.
- **OpenFOAM's `system/` documents are open.** `controlDict`, `fvSchemes`,
  `fvSolution`, `blockMeshDict` and any other `system/` document are listed
  once each, with `validated: false`. A key there is written as asked: omniD
  has no catalogue of OpenFOAM's keys, so it cannot tell whether the solver
  reads it.
- **Any other document is refused** by name, so a misspelt document is never
  taken for an OpenFOAM one.
- **Region-split cases are not catalogued yet.** An electromechanics case
  keeps its electro documents under `constant/<region>/` (`physics_layout.json`),
  which the validator does not address; `describe` refuses such a record by
  name.
