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
| Pig/morphometric terminal weighting | `setPurkinjeMorphometry` produces regional and terminal-weight fields | Implemented and executed as an explicit dependency of the named pig tree workflow | Retain |
| Explicit Purkinje tree | `generatePurkinjeTree`, tree VTKs, endocardial face sets | Human endocardial and pig morphometric/transmural contracts are declared and executed | Retain as two distinct workflow representations |
| Anatomy-portable seed deduction | `deduce_purkinje_seeds.py`, based on AHA/UVC surface data | Normalized into the adapter's canonical validation contract: LV AHA {2,3}; generator-specific recovered RV septum; His midpoint | Add VTK-backed candidate-to-dictionary reconciliation when the optional reader runtime is present |
| Density comparability and coverage | `terminalCount` convention; `check_purkinje_coverage.py` and `check_seed_distances.py` | Canonical policy requires present mid/apical AHA sectors, warns on basal gaps, and records counts/distances without a global threshold | Add VTK-backed sampling and ECG-specific optimisation criteria later |
| Graph hand-off | `1DgraphToFoam` turns generated VTK into `constant/purkinjeGraph` | Not yet declared or executed | Add after the tree vertical slice |
| Scar / Purkinje scar chain | `setCardiacScar`, `setPurkinjeScar` with explicit prerequisites | Not yet declared | Separate later workflow, not a prerequisite for the tree slice |
| VTK import / mesh creation | `newVtkUnstructuredToFoam`; optional external cleaning | The adapter accepts an explicit asset bundle but does not generate it | Keep as a separate asset-preparation pathway |

## Important interpretation

The current adapter already handles the items named as foundational inputs and
outputs:

- `fiber` and `sheet` are inputs to conductivity construction;
- `AHA_Segment` and `aha_angle` are generated and tracked outputs;
- morphometric Purkinje weight fields are generated and tracked outputs.

The adapter now includes the **explicit-tree representation**: a human
endocardial path and a pig morphometric/transmural path. The latter produces
and consumes the terminal-weight fields rather than merely cataloguing them.
It remains a bounded preprocessing/tree-generation adapter, not a complete
cardiacCore or cardiacFoam interface.

## Recommended next vertical slice

Add result interpretation rather than another broad workflow:

1. define explicit acceptance criteria for the existing seed-distance and
   coverage checkers;
2. publish a complete validation contract before exposing tree seed/growth or
   terminal-count settings as sweep axes;
3. only then add `1DgraphToFoam` as the explicit cardiacFoam hand-off.

The slab and explicit-tree branches must be selected deliberately. The
existing preflight records them as mutually exclusive for this milestone; the
adapter should preserve that solver/domain rule rather than running both by
default.

Scar, scarred-tree conversion, and VTK import remain subsequent independent
vertical slices. They should not delay the tree workflow, nor should their
larger conditional catalog be flattened into the initial user JSON.
