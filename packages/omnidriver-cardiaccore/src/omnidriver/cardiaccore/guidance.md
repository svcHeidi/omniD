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
- **`system/controlDict`** is partly catalogued, as for every OpenFOAM-based
  solver: the keys `Foam::Time` reads that the catalogue lists are checked by
  shape and bounds (`omnidriver catalog` lists them), and any other key is
  written as asked and flagged `validated: false`.
- **Any other `system/` document** (`fvSchemes`, ...) is written as asked and
  flagged `validated: false`: omniD has no catalogue of OpenFOAM's keys.
- **Any other document** (anything outside `system/`) is refused by name.

## Coordinates are case inputs

Every case declares its own convention in `system/coordinatesConventionDict`:
a required `coordinateSystem` (`uvc` or `cobiveco`), an optional `coordinates`
block naming its fields, the transmural endocardium/epicardium values and the
`intraventricularChambers` LV/RV values. Both systems are first-class; never
infer one from field names, and never convert one into the other's spelling.

- Read the declaration with the repository's `coordinates_convention.py`
  script and take field paths and values from it. Orientation is case-declared:
  endocardium may be the larger transmural value, and LV/RV values are not
  always -1/+1.
- `generatePurkinjeTree` recovers the RV-facing septum and applies a
  per-vertex transmural flip only under `uvc`; under `cobiveco` neither runs.
  Hence `RVSeptalEndoFaces` is produced under `uvc` only.
- `setCardiacAnatomy` writes `AHA_Segment` and `aha_angle` in separate LV/RV
  angle frames; do not compare raw angles across chambers.

## Helper scripts

The cardiacCore repository keeps its helper scripts in `applications/scripts/`.
`describe` lists each with its usage line, next to the records, when omniD is
pointed at the repository (`--repo`). They are the repository's, not omniD's:
read a script's `--help` before running it, and run it by hand when a record
fails and one of them looks relevant (the coordinate convention a case
declares, the Purkinje seeds, a tree's AHA coverage, an electrode transfer, a
VTU selection as a `cellSet`). A record may also name one as a step, and then
it runs like any other.

Read the plugin's named catalogs for the rest: `cardiaccore_field_conventions`,
`cardiaccore_support_boundary` and `cardiaccore_conditional_inputs`. A helper's
output is an observation or a proposal, never a scientific acceptance, and not
permission to change a case.

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
