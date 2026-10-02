# OmniD cardiacCore adapter

This package exposes the declared cardiacCore preprocessing workflows through
the `cardiaccore` plugin. Native cardiacCore remains the owner of its
executables, dictionaries, case assets and helper scripts
(`applications/scripts/`); `omnidriver describe --repo <cardiacCore>` lists the
scripts with their usage lines, beside the records.

## Start from the installed package

```python
from omnidriver.cardiaccore import CardiacCorePlugin

print(CardiacCorePlugin().get_agent_guidance()[0]["text"])
catalogs = CardiacCorePlugin().get_named_catalogs()
print(catalogs["cardiaccore_field_conventions"]["authority"])
```

`guidance.md` is a package resource: this works without a source checkout.
`describe` lists it under the record surface.

A case declares which ventricular coordinate system it uses -- `uvc` or
`cobiveco`, both first-class -- in `system/coordinatesConventionDict`, along
with its transmural and chamber reference values and, optionally, its own
field names. Read that declaration (the repository's
`coordinates_convention.py` prints it) before touching a coordinate field; do
not assume one system or hardcode canonical field names as if they were always
correct. Do not invent missing fields, reinterpret coordinates, or silently use
a different method after an error.

## Ownership within the package

| Location | Responsibility |
| --- | --- |
| `plugin.py` / `plugin.yaml` | Compose capabilities and expose public catalogs |
| `catalogs/inputs.py` | Reviewed input descriptions and conditional inputs |
| `utilities/<name>/utility.manifest.toml` | Native commands and their input/output contracts |
| `catalogs/support_boundary.py` | Field context and workflow support boundary |
| `guidance.md` | Packaged agent guidance |

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
inputs are study values, `<document>:<key>` patches in a sweep spec over the
record; `describe` lists them in `record_surface.keys`. The workflow permits
only its declared inputs and mutates a staged case.
The tree workflows retain fixed native seed/growth dictionaries; seeds are
placed by hand with `place_purkinje_seeds.py`. Coverage reports retain the
named baseline's categories, but do not return scientific acceptance.

The native generator owns endocardial-surface definition. It uses named LV/RV
endocardial patches when those are available; otherwise it uses the selected
UVC convention and natively recovers the RV-facing septum. The helper scripts
do not re-create that UVC/endoseptal logic. After `setCardiacAnatomy`, each
chamber has its own `aha_angle` frame: do not compare raw LV and RV angles.

For a selected tree study, keep this audit chain explicit: native face-set
construction → `setCardiacAnatomy` AHA fields → seed placement
(`place_purkinje_seeds.py`) → native tree generation → terminal coverage
(`purkinje_coverage.py`). The adapter does not yet schedule that chain
automatically, and it does not expose seed, growth, or density controls as
sweep axes without separately selected and validated acceptance criteria.

A runnable native case requires the explicitly supplied mesh and initial
field bundle. Clean-clone asset distribution remains pending work. Graph
hand-off remains a separate cardiacFOAM workflow.

## Maintenance and verification

Preserve named catalog IDs and the plugin entry point.

Tests exercise plugin composition, workflows and the catalogs. After changing
package resources or imports, build a fresh wheel and run these tests outside
the checkout as well. Do not infer
native or scientific acceptance from synthetic array tests.

Shared OmniD rules belong in its role guidance. This guide explains only this
adapter; it is the model for organizing another adapter, not a shared source
of cardiacFOAM solver semantics.
