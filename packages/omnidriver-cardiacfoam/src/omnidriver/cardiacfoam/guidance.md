# cardiacFOAM through omniD

Study keys are `<document>:<dotted.key>`, e.g.
`constant/electroProperties:singleCellSolverCoeffs.tissue`. `describe` lists
the keys a record's case accepts that its own solver allows, in
`record_surface.keys` (`omnidriver catalog --entry <record>` lists every one). A study goes in a
sweep spec (`sweep-plan`/`sweep-run --spec`, whose `base` names `entry` and
`cases_root`; a one-case study is a one-value axis). A single `plan`/`run`
takes the native case as it is, plus `--parallel`. Each rule in
this first part is one the record-key validator
(`record_key_validation.record_key_validator`) or the catalogue already
enforces; none is new. The last section is about the mesh.

- **Three documents are catalogued**: `constant/electroProperties`,
  `constant/physicsProperties` and `constant/prePacingProperties` (its keys at
  the root or under `regions.<region_name>`, which the file's presence turns
  on; its `singleCellStimulus` takes electroProperties' protocol keys, each
  listed under it, or a map of them). A key in any of them must be in the catalogue, or
  read by the supplied C++ source at exactly that path: then it is
  `uncatalogued`, accepted (and added if the case lacks it), and checked
  against the type the C++ reads it as (`omnidriver catalog --uncatalogued`
  lists them). Any other key is refused by name, with where the C++ reads it.
- **A key the C++ requires must be set.** A key the supplied C++ reads with
  no default (`get<T>`, `lookup`) that the catalogue lacks refuses the case
  that does not set it, naming the key, its type and where the C++ reads it;
  an `uncatalogued` note's `required` says which are. When the scan cannot tell
  whether the case builds the class that reads it, the plan says so in a note
  instead.
- **Write the active solver's scope.** Coefficients live under
  `<myocardiumSolver>Coeffs`: for `myocardiumSolver singleCellSolver;`, write
  `singleCellSolverCoeffs.tissue`. `describe` lists the case's own scope. A
  first segment that is no `<solver>Coeffs` of the catalogue's
  `myocardiumSolver` menu is refused.
- **Shape when written, meaning before the run.** Writing a value checks it
  against its entry's `value_kind` and numeric bounds. Once the study is
  written, and before anything runs, the resolved case passes the catalogue's
  relations (`applicable_when`, `required_when`, `forbidden_when`,
  `mutually_exclusive_with`, `co_required_with`, `required_one_of`), its enum
  menus (the names the supplied C++'s selection table registers, else the
  catalogue's menu and the literals the C++ compares the value against) and
  cardiacFOAM's cross-field rules, over `electroProperties`,
  `prePacingProperties` and `system/controlDict`. A break refuses the plan or
  the sweep case by name, quoting the rule: `tissue` outside its menu, say.
  Read the `menu` and `description` of an entry before choosing a value.
- **Named segments.** A `<name>` segment in a listed key (for example
  `ecgDomains.<name>.ecgSolver`) is a name the case chooses. Where the
  catalogue gives a closed set of names, a name outside it is refused.
- **A map replaces a whole sub-dictionary.** Where a listed key ends in a
  `<name>` segment (`bathPotentialDomain.groundPatches.<patch>`), the key
  without it takes a map, `{"xMin": 0}`: each member is checked as that
  entry, and the case's sub-dictionary is replaced by exactly the map's
  members. This is how a patch moves from one map to another.
- **`system/controlDict` is partly catalogued.** The keys the catalogue lists
  are the ones `Foam::Time` reads (`omnidriver catalog` shows each with its
  bounds): checked by shape and bounds when written, and with their menus and
  relations before the run (`writeInterval` or its older name `writeFrequency`
  is required; `endTime` when `stopAt` is `endTime`). Any other key of it, and
  every key of `fvSchemes`, `fvSolution`, `blockMeshDict` and any other
  `system/` document, is listed once with `validated: false` and written as
  asked: omniD has no catalogue of OpenFOAM's other keys, so it cannot tell
  whether the solver reads them.
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
  Every cardiacFOAM record today generates its mesh, and none declares a
  supplied input.
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
- **Serial by default.** Ask for the solve in parallel with the study value
  `parallel` or `--parallel`. The OpenFOAM layer then decomposes, runs the
  solve under `mpirun` and reconstructs; N is the case's
  `system/decomposeParDict:numberOfSubdomains`, and `parallel: N` must equal
  it. A record's routes do not change.
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
- **A Purkinje graph is data, selected and never edited.** The file
  `graphFile` names is the catalogue's `purkinjeGraph` document, whose entries
  state each key, its unit and its constraints; no study key addresses it, so
  write a new graph with a graph tool and select it. The graph the case holds
  is judged against those entries before the run; one a later step writes is
  judged by the solver alone. Beside the entries, omniD refuses an edge of no
  positive length or of negative conductance, a node index with a fraction, a
  `pvjResistances` or `rPvj` not above 0, a `rootStimulus.node` past the
  graph's last node, and a `pvjLocations` more than `pvjRadius` outside the
  mesh's bounding box (a graph in other units than its mesh). A junction with
  no cell in its sphere is coupled to its nearest cell, as a tree grown on the
  endocardial surface needs; omniD leaves that to the solver. The mesh is read where `constant/polyMesh`
  exists when the case is judged, so a plan of a case that has yet to make its
  mesh does not judge the locations, and `step` does once the mesh step has run.
