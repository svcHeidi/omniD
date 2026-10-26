# Solver-onboarding builder: evidence contract

The builder turns a user's description of a solver and one native workflow
into a bounded omniD plugin: a few objects core already defines, each holding
facts with their evidence. It never claims that every option in a codebase is
understood or safe to vary.

## The objects a plugin publishes

| object | what it holds | where it is defined | how an agent reads it |
|---|---|---|---|
| **Record** | a pointer at one native case: its steps, routes, axes, derived values, supplied inputs and conformance study, and nothing that restates a native value | `TutorialRecord`, `WorkflowStep`, `AxisContract`, `Derivation`, `RecordInput` (`omnidriver.core.tutorial_records`); `ConformanceStudy`, `QuantityTarget` (`omnidriver.core.conformance_study`) | `describe`, `describe --entry` |
| **Dictionary catalogue** | each key a solver reads: `value_kind`, unit, bounds, menu, `default`, relations (`applicable_when`, `required_when`, `forbidden_when`, `mutually_exclusive_with`, `co_required_with`, `required_one_of`), `source_refs` | `DictEntry`, `DictionaryCatalog` (`omnidriver.core.contracts`) | `catalog`, `describe --entry`'s `record_surface.keys` |
| **Utility manifest** | a native command's flags, positional arguments, inputs and `produces` (path, format, optional) | `utility.manifest.toml`, parsed as `UtilityManifest` and `ProducesEntry` (`omnidriver.core.utility_catalog`) | `describe`'s `utility_manifests` |
| **Scan notes** | where the catalogue or a manifest and the solver's source disagree: `uncatalogued`, `unread`, `disagreement` | the OpenFOAM layer's `dict_keys_scanner` and `utility_scanner` | `catalog --uncatalogued`, `catalog --unread`, a strict plan's `plugin_diagnostics` |
| **Reader** | how a declared output format becomes a quantity, with its unit and sampling rule | `get_artifact_value_reader` | `describe --entry`'s `record_surface.readers` |
| **Guidance** | the why: the solver's rules an agent cannot read from the fields above | `guidance.md`, served by `get_agent_guidance` | `describe --entry`'s `record_surface.guidance` |

A fact an agent acts on goes in a field of one of these. Prose is for the why.

## Evidence

Each fact keeps where it came from (an entry's `source_refs`, a record's
native case path). Prefer the strongest evidence and never treat a
weaker source as equal to a stronger one:

| evidence | establishes | does not establish |
|---|---|---|
| a native case, its `Allrun` and dictionaries | one workflow and the values it was authored with | that another value is supported |
| documentation, command help (`+Help`, `--describe`) | option names, formats, stated outputs | the installed build's behaviour |
| source code, through the scanners | keys read, their types, defaults, scopes and registered models | runtime branches, loaded libraries |
| a controlled run | one runtime path and its observed artifacts | general compatibility or scientific validity |

What no evidence settles stays empty: an entry with no unit leaves `unit`
empty, a key with no stated default leaves `default` empty. A familiar
convention (SI conductivity, say) is not evidence.

Source states mechanical facts. It does not always state what a branch means.
When the code cannot name a condition ("which workflow needs these paired
tensor dictionaries?"), ask the owner once, and write the answer as a relation
on the entry, not as reasoning in the agent.

## Building an OpenFOAM-based plugin

Reuse the OpenFOAM layer; write no solver-specific parser:

- start from the scan: `omnidriver catalog --repo <repository> --uncatalogued`
  lists each read the catalogue lacks with the arguments of its entry, and
  `--unread` each entry the source no longer reads. Both also list the utility
  manifests' drift under `utility_manifests`. A scan is an inventory, not an
  accepted catalogue;
- `DictEntry.dynamic_path` with `<name>` segments covers instance-named blocks;
- `dict_key_allowlist.json` holds only what the scan cannot see:
  `unseen_reads`, `caller_guarded` and, for an enum, the selection table its
  menu comes from (`runtime_selection`) and the values that build a class no
  table registers (`built_when`);
- `omnidriver.openfoam.dictionary_reader.read_foam_entry` reads a value;
  `omnidriver.openfoam.effective_dictionary` resolves includes; a study's
  `document:key` patches go through the case writer (`commit_case_write`),
  after the plugin's validator accepts the key;
- `omnidriver.openfoam.case_rules` judges a resolved case against the
  catalogue's relations, menus and bounds; `system/controlDict` and
  `system/fvSchemes` are the layer's own catalogue.

## Building a plugin with no source

openCARP's catalogue is generated from the binary's `+Help`
(`scripts/generate-opencarp-catalog.py`) and TorchCor's from its runner's
`--describe`. The objects are the same, and claims are scoped to the evidence
there is: missing detail stays unknown.

## Case assets

A native case may read what is not in Git: a mesh, initial fields, an anatomy.
Each is a `RecordInput`: its `native_relpath` when it has one in the
repository, or supplied with `--input NAME=PATH`, refused by name when absent.
A local run does not turn an untracked asset into a default.

## Before a slice is done

1. The native case is staged, never written.
2. Each step's command, `consumes` and `produces` are declared.
3. `plan --strict` passes in the solver's shell (`omnidriver env`).
4. The staged case runs, and its declared artifacts reconcile.
5. `omnidriver check` runs the record's conformance study and reports.
6. Each corrected contract has a focused test on real fixtures.

This validates orchestration and declared artifacts, not numerical
convergence or physiological validity.

## Ownership

- **Core** owns staging, planning, execution, reconciliation and provenance.
- **The environment layer** (the OpenFOAM layer) owns its file formats, the
  scanners and the shared documents.
- **A solver plugin** owns its records, catalogues, manifests, readers and
  rules.
- **The builder agent** writes and tests those declarations from evidence; it
  infers no scientific meaning beyond the user's stated purpose.
