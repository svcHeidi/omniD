# OmniD cardiacSubstrateFOAM adapter

This package exposes cardiacSubstrateFOAM's preprocessing through the `cardiacsubstrate`
plugin. Native cardiacSubstrateFOAM owns its utilities, dictionaries, case assets and
helper scripts (`applications/scripts/`); `omnidriver describe --repo
<cardiacSubstrateFOAM>` lists the records, the scripts with their usage lines and the
utilities a step may run.

## Start from the installed package

```python
from omnidriver.cardiacsubstrate import CardiacSubstratePlugin

print(CardiacSubstratePlugin().get_agent_guidance()[0]["text"])
catalogs = CardiacSubstratePlugin().get_named_catalogs()
print(catalogs["cardiacsubstrate_support_boundary"]["pending"])
```

`guidance.md` is a package resource: this works without a source checkout.
`describe --entry` lists it under the record surface.

A case declares which ventricular coordinate system it uses -- `uvc` or
`cobiveco`, both first-class -- in `system/coordinatesConventionDict`, with
its transmural and chamber reference values and, optionally, its own field
names. Read that declaration (the repository's `coordinates_convention.py`
prints it) before touching a coordinate field.

## Ownership within the package

| Location | Responsibility |
| --- | --- |
| `plugin.py` / `plugin.yaml` | The provider and its profile |
| `records/` | The tutorial records |
| `catalogs/inputs.py` | The catalogue of the utilities' dictionary keys |
| `utilities/<name>/utility.manifest.toml` | Each native utility's flags, arguments, inputs and outputs |
| `catalogs/support_boundary.py` | What the adapter does not support yet |
| `guidance.md` | Packaged agent guidance |

## Records

Three records point at the native `idealizedHeart` tutorial's variants:
`idealizedHeart` (`humanSlab`), `idealizedHeartEndocardial`
(`humanEndocardial`) and `idealizedHeartPigTransmural`
(`pigMorphometricTransmural`). Each reads the variants' shared mesh
(`idealizedHeart/mesh`, Git LFS) as its native `mesh` input, so none needs an
`--input`. A study's values are `<document>:<key>` patches in a sweep spec over
a record; `describe --entry` lists them in `record_surface.keys`. The
endocardial and pig-transmural records end in `generatePurkinjeTree`; seeds
are placed by hand with `place_purkinje_seeds.py`, and the records expose no
seed, growth or density control as an axis.

What `generatePurkinjeTree` and `setCardiacAnatomy` write, under each
coordinate system, is in each utility's own `README.md` in cardiacSubstrateFOAM's
`applications/utilities/`. No record runs the Purkinje graph hand-off to
cardiacFOAM.

## Maintenance and verification

After changing package resources or imports, build a fresh wheel and run the
tests outside the checkout as well. Do not infer native or scientific
acceptance from synthetic array tests.
