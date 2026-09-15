# cardiacCore package review — 2026-09-15

## Scope and stopping point

The package now separates composition, catalogs, workflows, Python operations
and installed agent guidance. This builds on the existing working-tree
reorganization. It does not change the DAG, native scientific methods, solver
defaults or provider skills.

`cardiaccore_operations` is the canonical callable contract. The Python utility
index is derived from it. Shared CObiveco conventions and Purkinje baseline
constants live in catalogs and are consumed by implementations. Guidance
explains selection and use without maintaining another parameter catalog.

The five operation records distinguish callable array methods, native readers,
workflow integration and scientific limits. Packaged guidance can be read
without a repository checkout. Old flat-module import paths have no forwarding
layer; callers must use the paths advertised in the operation catalog.

Mechanical fixes reject malformed coordinate inputs and invalid cell IDs.
Encoded or multi-piece VTU input delegates to the optional VTK reader instead
of silently returning an empty selection. No new scientific operation was added.

## Verification

| Check | Result |
| --- | --- |
| cardiacCore source tests | 37 passed |
| cardiacCore tests against fresh installed wheels, outside checkout | 37 passed |
| Core source suite with adapters available | 822 passed, 82 skipped, 1 deselected |
| OpenFOAM source suite | 214 passed, 72 skipped |
| Import boundaries and capability seam export | Passed |
| Core-only wheel imports and CLI help | 76/76 imports; help exited 0 |

The installed cardiacCore smoke check resolved Core, OpenFOAM and cardiacCore
from the temporary environment's site-packages and discovered all five
operation records. Native solver acceptance was not repeated. Encoded VTU
dispatch was tested with a stub; the real optional PyVista reader was not
exercised against native files.

Core-only verification is **not fully green**. With the Core wheel and its
postprocessing dependencies installed, 27 Core test modules fail collection
because they import OpenFOAM. The wheel-check script also expects
`default_driver_context()` and `get_heterogeneity_models()` to work without an
installed adapter. The current runtime correctly requires an explicit context
or installed adapter. These test/harness assumptions are separate follow-up
work, not a reason to restore an implicit OpenFOAM fallback.

## Next bounded task

Have a lower-reasoning maintainer audit Core test ownership and the wheel-check
script. Classify the 27 modules as neutral contract tests or explicit adapter
integration tests. Use small fake capabilities for neutral tests where needed;
keep tests of actual OpenFOAM behavior in an explicitly provisioned adapter
integration suite. First fix the wheel-check expectations and one representative
test module, then verify Core-only imports, CLI help, missing-adapter errors and
explicit-context behavior. Do not change runtime fallback behavior, weaken
assertions, or skip tests merely to make collection pass.

For cardiacCore, the next functional increment should be one concrete native
reader or case-input bridge required by an actual experiment. Select its file
format, conventions and evidence before implementation. Further scientific
helpers, cardiacFOAM reorganization and skills are separate batches.
