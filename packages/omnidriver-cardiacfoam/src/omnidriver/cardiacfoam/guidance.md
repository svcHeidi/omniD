# cardiacFOAM through omniD

Study keys are `<document>:<dotted.key>`, e.g.
`constant/electroProperties:singleCellSolverCoeffs.tissue`. `describe` lists
every key a record's case accepts, in `record_surface.keys`. Each rule in
this first part is one the record-key validator
(`record_key_validation.record_key_validator`) or the catalogue already
enforces; none is new. The last section is about the mesh.

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
- **A map replaces a whole sub-dictionary.** Where a listed key ends in a
  `<name>` segment (`bathPotentialDomain.groundPatches.<patch>`), the key
  without it takes a map, `{"xMin": 0}`: each member is checked as that
  entry, and the case's sub-dictionary is replaced by exactly the map's
  members. This is how a patch moves from one map to another.
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

## Where a case's mesh comes from: the pre-processing stage

How records are built and used. Unlike the rules above, a validator does not
check it; the refusals it names are the record's own.

- **What the solver starts from.** Before the solve, a case needs a
  starting state: a mesh, and possibly fields or graphs. The steps that
  produce it are the record's pre-processing stage. Its source is either
  **generated**, from a recipe the case owns and every run rebuilds, or
  **supplied**, a finished artifact brought in and not rebuilt. Anything
  from outside the native tree is supplied by you and never discovered.
  Every cardiacFOAM record today generates its mesh. Supplied inputs for a
  record are a later item.
- **blockMesh is the default route.** A record runs its native case's own
  route unless the study picks another: `blockMesh` with
  `system/blockMeshDict`, or the dictionary the case's own scripts name. For
  bidomain and eikonalECG that is `-dict system/blockMeshDict.3D`, from their
  `regression/regressionTest.sh`. A record mirrors the native commands and
  never calls `./Allrun`. `describe`'s `record_preview.workflow_variant`
  says which route runs and whether the study or the record chose it.
  `record_preview.workflow_commands` shows each step's command line.
- **gmsh is the alternative generator**, where a case ships a
  `.geo.template`: `gmsh -3 <template> -setnumber lc <v>`, then
  `gmshToFoam`. A study selects it through the record's route selector,
  `"mesh"` (`"mesh": "tet"`). With no resolution value, gmsh uses the
  template's own `DefineConstant` default. `tetNumberCells` (lc = 1/N on
  the unit cube) or niederer2011's `tetDx` (lc in metres) adds
  `-setnumber lc`.
- **A study value replaces the default argument it names.** `dimension`
  passes `-dict system/blockMeshDict.<dim>`, which replaces the default
  `-dict system/blockMeshDict.3D` rather than adding a second `-dict`.
- **A route admits only what it can build.** Every tet template is a 3D
  geometry, so a tet route accepts `dimension` only as `3D`, or unset. Any
  other value is refused by name before anything is written. A route the
  record does not declare is refused by name too.
- **Keep it loose.** A record declares its default route and the routes its
  native studies use; it does not list every possible one. To do something
  else, read the native case: its `Allrun`, `regression/regressionTest.sh`,
  README and `setup/studies/`. Then choose one of the record's routes and
  shape it with study values and step arguments, for example a `-dict`
  naming a dictionary you composed, or any `-setnumber lc`. What ran, what
  it read and wrote, and the fingerprints are recorded. The choice is yours.
- **Serial only.** Running the solve in parallel belongs to the OpenFOAM
  layer (a later item), not to a record's routes.
- **A route selector need not choose a mesh.**
  `manufacturedMonodomain1D3D`'s selector, `"solver"`, instead picks which
  solve command runs after the same `blockMesh` step: `"coupled"` (the
  default, `cardiacFoam`, the coupled 1D-3D myocardium/Purkinje solve) or
  `"graphOnly"` (`"solver": "graphOnly"`, `runPurkinjeGraph`, the graph
  alone with no myocardium coupling -- the case's own README "Graph-Only
  Diagnostic"). `graphFile` (a direct `constant/electroProperties` key,
  `purkinjeGraphModelCoeffs.graphFile`) picks which committed
  `constant/purkinjeGraph*` file either route reads, by name, checked
  against the staged case.
