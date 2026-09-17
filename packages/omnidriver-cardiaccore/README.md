# OmniD cardiacCore adapter

This package exposes the declared cardiacCore preprocessing workflows and
Python operations through the `cardiaccore` plugin. Native cardiacCore remains
the owner of its executables, dictionaries and case assets.

## Start from the installed package

```python
from omnidriver.cardiaccore import CardiacCorePlugin
from omnidriver.cardiaccore.agent_guidance import read_guidance

print(read_guidance("runner"))
catalogs = CardiacCorePlugin().get_named_catalogs()
operation = catalogs["cardiaccore_operations"]["cardiaccore.cobiveco.normalize.v1"]
print(operation["preconditions"])
print(operation["entrypoints"])
```

The guide and its manifest are package resources: this works without a source
checkout. The manifest identifies required catalogs for each role. It does
not itself inject instructions into an agent; provider integration remains
outside this adapter.

An operation has an exact primary `module:function` reference and separate
`entrypoints` for preparation, calculation or writing. Read each entrypoint's
arguments and side effects before calling it. Array availability, native-file
reading and workflow integration are separate status fields. An available
array method does not imply that an arbitrary native case can be processed.

For CObiveco, read the selected target convention before calculation:

```python
from pathlib import Path
from omnidriver.cardiaccore.operations.cobiveco import (
    normalize_cobiveco_coordinates,
    read_cobiveco_target_convention,
)

# case_root and aligned tv/tm/ab arrays are supplied by the caller.
target = read_cobiveco_target_convention(Path(case_root))
fields = normalize_cobiveco_coordinates(tv, tm, ab, target_convention=target)
```

Do not invent missing fields, reinterpret coordinates, or silently use a
different method after an error. Distinguish invalid input, an unavailable
reader, and unresolved scientific interpretation. Read the operation record
for its limits and correct the identified prerequisite first.

## Ownership within the package

| Location | Responsibility |
| --- | --- |
| `plugin.py` / `plugin.yaml` | Compose capabilities and expose public catalogs |
| `catalogs/inputs.py` | Reviewed input descriptions and conditional inputs |
| `catalogs/utilities.py` | Native commands and their input/output contracts |
| `catalogs/operations.py` | Canonical callable usage contracts |
| `catalogs/purkinje.py` | Shared method constants and named baseline categories |
| `catalogs/support_boundary.py` | Field context and workflow support boundary |
| `workflows/` | Workflow order, allowed overrides and RunDocument configuration |
| `operations/` | Python transformations, proposals and observations |
| `agent_guidance/` | Packaged role manifest and short usage guidance |

`cardiaccore_python_utilities` remains a convenience index, derived from
`cardiaccore_operations`; it is not another maintained set of claims.
Catalog results are independent snapshots so caller annotations cannot change
what another agent sees.

Native source and historical scripts explain the origin of a method. They
are not fallback imports or instructions to bypass the supported adapter.
Reference geometry, meshes, fibre/UVC fields and other required assets remain
explicit inputs; moving code does not make those assets optional.

## Supported workflows and limits

The plugin advertises four workflows:

- `cardiaccore-human-purkinje-slab` runs the human slab preparation chain.
- `cardiaccore-human-purkinje-endocardial` generates the human endocardial tree.
- `cardiaccore-pig-morphometric-purkinje` uses the morphometry weight fields
  for LV terminal selection and extends the selected terminals transmurally.
- `cardiaccore-pig-transmural-purkinje` uses `allLeaves` for LV terminal
  selection and extends the terminals transmurally.

The two pig workflows otherwise declare the same utility sequence. Reviewed
inputs are passed through `input_overrides` in the normal run configuration,
for example:

```json
{"input_overrides": {"$PURKINJE_SLAB.thickness": 0.05}}
```

This is a request example, not a new default or scientific recommendation.
The workflow permits only its declared inputs and mutates a staged case.
The tree workflows retain fixed native seed/growth dictionaries; array seed
proposals are not automatically applied. Coverage reports retain the named
baseline's categories, but do not return scientific acceptance.

The native generator owns endocardial-surface definition. It uses named LV/RV
endocardial patches when those are available; otherwise it uses the selected
UVC convention and natively recovers the RV-facing septum. Python operations
do not re-create that UVC/endoseptal logic. After `setCardiacAnatomy`, each
chamber has its own `aha_angle` frame: do not compare raw LV and RV angles.

`cardiaccore.coordinates.ring_closure.v1` is the upstream geometry
check for a VTK volume or boundary mesh. It expects declared binary LV/RV
intraventricular values, a varying longitudinal coordinate, and a transmural
coordinate with a declared endocardial boundary value. It extracts each
candidate endocardial boundary, contours it at requested longitudinal values,
and reports whether every contour is a single closed loop. It needs no
pre-exported face sets and does not use AHA angles. A failed coordinate
contract or open ring is a prerequisite to investigate, not permission to
change the native UVC/CObiveco implementation or a Purkinje parameter.
When the caller has not declared coordinate fields, it assesses scalar-field
behaviour and ring topology rather than field names: it reports any unique,
topology-supported two-chamber candidate, ambiguity, or the missing numerical
prerequisite. The generic result does not invent which numeric chamber is LV
or RV; callers declare that mapping only when it is needed downstream.

For a selected tree study, keep this audit chain explicit: coordinate-ring
closure → native face-set construction → `setCardiacAnatomy` AHA fields → seed
proposal from native face sets plus AHA segments → native tree generation →
terminal coverage/density observation. The adapter does not yet schedule that
chain automatically, and it does not expose seed, growth, or density controls
as sweep axes without separately selected and validated acceptance criteria.

A runnable native case requires the explicitly supplied mesh and initial
field bundle. Clean-clone asset distribution, native surface/field sampling,
reviewed seed writing, and graph hand-off remain separate pending work.
The VTU selection reader supports ASCII data with base dependencies; encoded
or multi-piece data requires the optional `omnidriver-cardiaccore[vtk]` extra.
Installing that extra does not implement the other pending VTK readers.

## Maintenance and verification

Preserve operation IDs, named catalog IDs and the plugin entry point.
The in-progress flat-module reorganization intentionally uses the callable
paths now advertised by the catalog; no old-module forwarding layer is added.
This is an import-path migration, not a claim that previous direct imports
continue working. Existing callers must select the advertised paths.

Tests exercise plugin composition, workflows, operation behavior, and
catalog-driven invocation. After changing package resources or imports, build
a fresh wheel and run these tests outside the checkout as well. Do not infer
native or scientific acceptance from synthetic array tests.

Shared OmniD rules belong in its role guidance. This guide explains only this
adapter; it is the model for organizing another adapter, not a shared source
of cardiacFOAM solver semantics.
