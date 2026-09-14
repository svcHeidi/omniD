# cardiacCore Capability Comparison

This compares the existing user-authored cardiacCore agent material at
`cardiacCoreStandalone/agent/` with the evidence-backed OmniD
`cardiaccore-biv-preprocessing` adapter created for CC-1.  It is a scope
comparison, not a claim that either representation should replace the other.

## Current coverage

| Capability | Existing cardiacCore material | Current OmniD slice | Decision |
| --- | --- | --- | --- |
| Fibre/sheet conductivity | `setCardiacConductivity`; fibre and sheet are configurable inputs | Implemented and executed; `fiberField`/`sheetField` and `df`/`ds`/`dn` are reviewed x values | Retain |
| AHA segmentation | `setCardiacAnatomy` produces `AHA_Segment` and `aha_angle` | Implemented and executed; both are declared artifacts | Retain |
| Field-based Purkinje slab | `setPurkinjeSlab` | Implemented and executed; thickness/multiplier are reviewed x values | Retain as one representation |
| Pig/morphometric terminal weighting | `setPurkinjeMorphometry` produces regional and terminal-weight fields | Implemented and executed, but no explicit tree currently consumes those fields | Retain and connect to tree workflow |
| Explicit Purkinje tree | `generatePurkinjeTree`, tree VTKs, endocardial face sets | Not yet declared or executed | **Next priority** |
| Anatomy-portable seed deduction | `deduce_purkinje_seeds.py`, based on AHA/UVC surface data | Not yet staged, invoked, or recorded as evidence | Add as a conditional preparation/validation step for new anatomies |
| Density comparability and coverage | `terminalCount` convention; `check_purkinje_coverage.py` and `check_seed_distances.py` | No result metric/checker declaration | Add after native tree generation is running |
| Graph hand-off | `1DgraphToFoam` turns generated VTK into `constant/purkinjeGraph` | Not yet declared or executed | Add after the tree vertical slice |
| Scar / Purkinje scar chain | `setCardiacScar`, `setPurkinjeScar` with explicit prerequisites | Not yet declared | Separate later workflow, not a prerequisite for the tree slice |
| VTK import / mesh creation | `newVtkUnstructuredToFoam`; optional external cleaning | The adapter accepts an explicit asset bundle but does not generate it | Keep as a separate asset-preparation pathway |

## Important interpretation

The current adapter already handles the items named as foundational inputs and
outputs:

- `fiber` and `sheet` are inputs to conductivity construction;
- `AHA_Segment` and `aha_angle` are generated and tracked outputs;
- morphometric Purkinje weight fields are generated and tracked outputs.

What is absent is the **explicit-tree representation** that uses those
products to make a density-controlled Purkinje network. Therefore calling the
current four-step workflow “cardiacCore support” would be too broad. It is
accurately a tested field-preprocessing adapter.

## Recommended next vertical slice

Add one explicit-tree workflow rather than every historical tool at once:

1. select a named existing tree case and its asset bundle;
2. stage its native `generatePurkinjeTreeDict` plus required UVC/AHA and,
   for morphometric mode, weight fields;
3. declare the `generatePurkinjeTree` utility, face-set and VTK artifacts;
4. validate a native run and then declare the exact `terminalCount` / model
   inputs that the chosen mode actually reads;
5. run the existing seed-distance and coverage checks as result interpretation
   evidence, not as generic Core behavior;
6. only then add `1DgraphToFoam` as the explicit cardiacFoam hand-off.

The slab and explicit-tree branches must be selected deliberately. The
existing preflight records them as mutually exclusive for this milestone; the
adapter should preserve that solver/domain rule rather than running both by
default.

Scar, scarred-tree conversion, and VTK import remain subsequent independent
vertical slices. They should not delay the tree workflow, nor should their
larger conditional catalog be flattened into the initial user JSON.
