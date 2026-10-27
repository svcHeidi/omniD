# cardiacCore through omniD

cardiacCore preprocesses an anatomy for cardiacFOAM: it builds conductivity,
AHA labels, the Purkinje slab and morphometry fields, and Purkinje trees, by
running native utilities over a case. Native cardiacCore owns the utilities,
dictionaries and case assets; omniD stages the case, runs the utilities and
records what they read and wrote.

## Records and their inputs

- **`idealizedHeart`, `idealizedHeartEndocardial`,
  `idealizedHeartPigTransmural`** are the native `idealizedHeart`
  tutorials' variants `humanSlab`, `humanEndocardial` and `pigMorphometricTransmural`.
  They run on the idealized biventricular mesh the variants share
  (`idealizedHeart/mesh` in the tutorials root, Git LFS), which a record reads as its
  native `mesh` input in place of the copy each `Allrun` makes, so they need
  no `--input`. They use the `cobiveco` convention (`0/tm`, `0/tv`,
  `0/apicobasal`). The endocardial and pig-transmural variants end in
  `generatePurkinjeTree`.
- No record runs `refine1Dgraph` or the Purkinje graph hand-off to
  cardiacFOAM, and no manifest declares cardiacCore's graph conversion
  utilities (`ccore1DgraphToFoam`, `ccoreVtkUnstructuredToFoam`).

## Study keys

A study addresses a utility's dictionary directly, as
`system/<utility>Dict:<dotted.key>`, e.g. `system/setPurkinjeSlabDict:thickness`.
`describe` lists every key a record accepts in `record_surface.keys`.

- **A catalogued key** (`catalogs/inputs.py`) is checked when written against
  its entry's `value_kind` (shape) and numeric bounds. Once the study is
  written, and before anything runs, the resolved case passes the entry's
  relations (`applicable_when`, `required_when`, `forbidden_when`,
  `mutually_exclusive_with`, `co_required_with`, `required_one_of`) and its enum
  menu (the names the supplied C++ registers, else the catalogue's); a break
  refuses the plan by name, quoting the rule. Read the entry's description and
  notes before choosing a value.
- **A key the catalogue lacks but the supplied C++ reads** is accepted as
  `uncatalogued` and checked against the type the C++ reads it as
  (`omnidriver catalog --uncatalogued` lists them). Any other key of a
  catalogued dictionary is refused by name.
- **`system/controlDict` and `system/fvSchemes` are the OpenFOAM layer's**, as
  for every OpenFOAM-based solver: their catalogued keys (`omnidriver catalog`
  lists each with its bounds and menu) are checked when written and, with
  their menus and relations, before the run (`writeInterval` or its older name
  `writeFrequency` is required; `endTime` when `stopAt` is `endTime`). Any
  other key of them, and every key of another `system/` document
  (`fvSolution`, `blockMeshDict`, ...), is written as asked and flagged
  `validated: false`: omniD cannot tell whether the solver reads it.
- **Any other document** (anything outside `system/`) is refused by name.

## Coordinates are case inputs

Every case declares its own convention in `system/coordinatesConventionDict`:
a required `coordinateSystem` (`uvc` or `cobiveco`), an optional `coordinates`
block naming its fields, the transmural endocardium/epicardium values and the
`intraventricularChambers` LV/RV values. Both systems are first-class; never
infer one from field names, and never convert one into the other's spelling.

- Read the declaration with the repository's `coordinates_convention.py`
  script and take field paths and values from it, including the default field
  names a `coordinates` block may omit. Orientation is case-declared, and named
  by anatomy, not by numeric order: endocardium may be the larger transmural
  value, LV/RV values are not always -1/+1 (classify a chamber by the nearest
  declared value), and apex-to-base direction is not guaranteed.
- What a utility does under each coordinate system, and what it writes, is
  its own `README.md` in `applications/utilities/<utility>/`: for
  `setCardiacAnatomy`, `AHA_Segment`, `aha_angle`, `aha_z` and its auxiliary
  fields, with the segment names in `aha_segment_names.json`; for
  `setPurkinjeMorphometry`, its classes and weights, with the segment names in
  `src/purkinjeMorphometry/purkinje_morphometry_segment_names.json`. The
  endocardial face sets `setCardiacAnatomy` and `generatePurkinjeTree` both
  build are `src/endocardialSurfaces/README.md`. A record step's outputs are
  the utility manifest's, so they follow it.

## Helper scripts

The cardiacCore repository keeps its helper scripts in `applications/scripts/`.
`describe` lists each with its usage line, next to the records, when omniD is
pointed at the repository (`--repo`). They are the repository's, not omniD's:
read a script's `--help` before running it, and run it by hand when a record
fails and one of them looks relevant (the coordinate convention a case
declares, the Purkinje seeds, a tree's AHA coverage, an electrode transfer, a
VTU selection as a `cellSet`). A record may also name one as a step, and then
it runs like any other.

What the adapter does not support yet is the named catalog
`cardiaccore_support_boundary`. A helper's output is an observation or a
proposal, never a scientific acceptance, and not permission to change a case.

## Extending the adapter

- A helper script goes in the repository's `applications/scripts/`, with a
  docstring or `--help` whose first line says what it does; omniD reads it from
  there and keeps no catalogue of it.
- A utility is declared by one `utilities/<name>/utility.manifest.toml`; the
  directory name is the utility's name.
- Native C++ behaviour, field conventions, units and supported combinations
  need source evidence or an explicit domain decision. Record a pending reader
  or an unresolved interpretation rather than inferring it from a Python
  function.
