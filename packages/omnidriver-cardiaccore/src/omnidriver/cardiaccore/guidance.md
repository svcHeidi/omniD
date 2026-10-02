# cardiacCore through omniD

cardiacCore preprocesses an anatomy for cardiacFOAM: it builds conductivity,
AHA labels, the Purkinje slab and morphometry fields, and Purkinje trees, by
running native utilities over a case. Native cardiacCore owns the utilities,
dictionaries and case assets; omniD stages the case, runs the utilities and
records what they read and wrote.

## Records and their inputs

- **`humanSlab`** runs `setCardiacConductivity`, `setCardiacAnatomy`,
  `setPurkinjeSlab` and `setPurkinjeMorphometry` over `cases/bivCase`, in the
  native `Allrun`'s order. It needs one supplied input, `anatomy`
  (`--input anatomy=<dir>`): the mesh (`constant/polyMesh`), `0/fiber`,
  `0/sheet` and the `0/uvc_*` fields, none of which are in the tracked case
  folder. It is supplied, never discovered.
- **`idealizedHeart`, `idealizedHeartEndocardial`,
  `idealizedHeartPigTransmural`** run on cardiacFOAM's idealized
  biventricular mesh, committed natively, so they need no `--input`. They use
  the `cobiveco` convention (`0/tm`, `0/tv`, `0/apicobasal`). The endocardial
  and pig-transmural variants end in `generatePurkinjeTree`.
- No record runs `refine1Dgraph` or the Purkinje graph hand-off to
  cardiacFOAM; the graph conversion utilities are declared, not sequenced.

## Study keys

A study addresses a utility's dictionary directly, as
`system/<utility>Dict:<dotted.key>`, e.g. `system/setPurkinjeSlabDict:thickness`.
`describe` lists every key a record accepts in `record_surface.keys`.

- **A catalogued key** (`catalogs/inputs.py`) is checked against its entry's
  `value_kind`, by shape only: an `enum` value is not checked against its
  menu, and conditions on other keys are not evaluated. Read the entry's
  description and notes before choosing a value.
- **A key the catalogue lacks but the supplied C++ reads** is accepted as
  `uncatalogued` and checked against the type the C++ reads it as
  (`omnidriver catalog --uncatalogued` lists them). Any other key of a
  catalogued dictionary is refused by name.
- **Any other `system/` document** (`controlDict`, `fvSchemes`, ...) is
  written as asked and flagged `validated: false`: omniD has no catalogue of
  OpenFOAM's keys.
- **Any other document** (anything outside `system/`) is refused by name.

## Coordinates are case inputs

Every case declares its own convention in `system/coordinatesConventionDict`:
a required `coordinateSystem` (`uvc` or `cobiveco`), an optional `coordinates`
block naming its fields, the transmural endocardium/epicardium values and the
`intraventricularChambers` LV/RV values. Both systems are first-class; never
infer one from field names, and never convert one into the other's spelling.

- Read the declaration with
  `omnidriver.cardiaccore.operations.coordinates_convention.read_coordinates_convention`
  and take field paths and values from it. Orientation is case-declared:
  endocardium may be the larger transmural value, and LV/RV values are not
  always -1/+1.
- `generatePurkinjeTree` recovers the RV-facing septum and applies a
  per-vertex transmural flip only under `uvc`; under `cobiveco` neither runs.
  Hence `RVSeptalEndoFaces` is produced under `uvc` only.
- `setCardiacAnatomy` writes `AHA_Segment` and `aha_angle` in separate LV/RV
  angle frames; do not compare raw angles across chambers.

## Python operations and named catalogs

Read the plugin's named catalogs rather than this file for contracts:
`cardiaccore_operations` (the canonical callable contract and example of each
operation), `cardiaccore_field_conventions`, `cardiaccore_support_boundary`,
`cardiaccore_python_utilities` (an index derived from the operations),
`cardiaccore_conditional_inputs` and `cardiaccore_tree_validation`.

1. Select an operation by its ID and read its applicability, status,
   preconditions and failure conditions. Preparation/read, calculation and
   write entrypoints have separate inputs and side effects; use their exact
   `module:function` references.
2. The selected case supplies the actual values; do not hardcode matching
   values to satisfy a validator.
3. An array method is not a native-file reader, and a proposal is not
   permission to change a case. Report what was computed and any missing
   capability.
4. On failure, address the declared prerequisite. Do not search old
   standalone scripts for another algorithm, and do not read an operation
   returning successfully as scientific acceptance. Coverage categories are a
   named baseline; electrode transfer needs an explicit comparative-study
   selection; neither establishes general scientific acceptance.

## Extending the adapter

- Add an operation's usage record in `catalogs/operations.py` and its
  implementation in `operations/`. Keep `module:function` references and
  argument names aligned with the code. Each record needs an example,
  preconditions, outputs, side effects, evidence, and distinct
  mechanical, missing-capability and scientific limits. Do not copy an
  operation's status into another table.
- A utility is declared by one `utilities/<name>/utility.manifest.toml`; the
  directory name is the utility's name.
- Shared Purkinje method constants and baseline categories live in
  `catalogs/purkinje.py`; changing them is a method change, not formatting.
- Native C++ behaviour, field conventions, units and supported combinations
  need source evidence or an explicit domain decision. Record a pending reader
  or an unresolved interpretation rather than inferring it from a Python
  function.
