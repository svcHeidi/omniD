# Run provenance: which source built what a run used

**Status:** approved design, 2026-10-16. Implementation on `feat/run-provenance`.

## The problem

On 2026-10-16 a native-main tutorial ran to completion on a `cardiacFoam` built
from PR #59, and nothing said so. Two gaps allowed it:

- **The run document names no solver build.** The binary and library digests
  exist, but only in `workflow_state.json`'s `resume_snapshot`, where they guard
  a resume. Nothing records which source those binaries came from.
- **`stale_build` compares file times.** A `git archive` tree sets every file to
  its commit time, and a binary built from another worktree is newer than all
  of them, so the check passes. It also warns wrongly the other way: a fresh
  archive of the very source a binary was built from is "newer" than the binary.

omniD drives four solvers, and each knows its own build differently. Provenance
has to cover every solver a run uses.

## Decisions (owner, 2026-10-16)

| question | decision |
|---|---|
| scope | every solver omniD drives, each through its own plugin |
| shape in the run document | a JSON list, one entry per solver, each listing its builds |
| where the link is written, for a build that cannot identify itself | `omnidriver build-record --repo <src>`, run after the native build, writes a record beside the products |
| a build recorded from other source than the plan reads | a `stale_build` warning; the run is not refused |
| a build whose source nothing states | a `build_source_unknown` note; no file-time fallback |
| cardiacFOAM's `cardiacFoam.build.json` | unchanged: it inspects the backend (full or lightweight, the linked libraries), and its digests are only its own cache key. The build record is the one place for provenance |

## How each solver knows its build

| solver | how the source of what runs is known | `known` |
|---|---|---|
| cardiacFOAM, cardiacCore (wmake) | nothing in a binary says where it came from: the build record beside it | `recorded` |
| openCARP | the binary reports its own git tag and hash (`-buildinfo`'s tag and hash lines, which the plugin already reads; the repository line embeds a CI token and is never read) | `self_reported` |
| TorchCor | an editable install: the code that runs is the repository's own package (`torchcor.__file__` inside `repository.source`), read when the plan is made | `live` |
| any of them, when that evidence is missing | — | `unknown` |

## The contract

One optional member joins `provider_stack.MEMBERS`:

| member | composition | absent answer |
|---|---|---|
| `get_solver_builds(env, *, repository)` | `sequence` | `()` |

It answers a `SolverBuild` for each product the stack's plans run (the solver,
its libraries, the stack's own utilities), and nothing for a binary it did not
build (a system `blockMesh`). `SolverBuild` is a core dataclass beside
`RuntimeDependency`:

| field | meaning |
|---|---|
| `solver` | the provider id that answered |
| `name`, `path` | the product and where it is under `env`; `path` is `None` when it is not there |
| `digest` | `sha256:<hex>` of the file, `None` when absent |
| `known` | `recorded`, `self_reported`, `live` or `unknown` |
| `source` | a `SourceIdentity` (`repository`, `digest`, `git`: `{commit, tag, dirty}` with each part optional), or `None` |

`repository` is the supplied `Repository` or `None`. No contract version bump:
the member is optional, and a provider that does not implement it is
unchanged at version 3.

Core owns the shared parts, so no plugin re-implements them:

- **`SourceIdentity` of a repository:** `git rev-parse HEAD` and `dirty` when
  `git status --porcelain --untracked-files=no` prints anything, read only when
  `<repository>/.git` exists (a directory or a worktree's file); no parent is
  searched. A tree with no `.git` (an archive) has `git: null`. The digest is the
  plugin's (which files a build reads is the solver's knowledge).
- **The build record** (below): reading, writing and matching it.

## The build record (wmake)

`omnidriver build-record --repo <dir>` runs in the solver's own shell after a
build. The repository is supplied, never searched for. For each product the
stack lists for it whose file exists, it writes an entry into
`omnidriver-build.json` in the product's own directory, merging with the
entries there, so two worktrees that build into one platform folder each
replace only their own products. The write is atomic (a temporary file, then
`os.replace`) and serialised by an exclusive lock file beside it.

```json
{
  "version": 1,
  "products": {
    "cardiacFoam": {
      "digest": "sha256:91b1e705f…",
      "recordedAt": "2026-10-16T14:02:11+01:00",
      "source": {
        "repository": "/Users/…/noFrontend_pr",
        "digest": "sha256:4c0e…",
        "git": {"commit": "04e6bd84…", "dirty": false}
      }
    }
  }
}
```

It prints one JSON report: the repository's identity, the products recorded
(name, path, digest, record file) and those not built. A stack that lists no
recordable product for the repository refuses with the new code
`build_products_undeclared`.

A recorded entry applies only while its `digest` equals the file's: a binary
rebuilt without recording is `unknown`.

**The OpenFOAM layer** implements the member once, for cardiacFOAM and
cardiacCore ("one reality"):

- **products:** each `Make/files` under the repository root, outside
  `tutorials/`, `lnInclude/` and `platforms/`: `EXE = $(FOAM_USER_APPBIN)/<name>`
  is an executable in `env["FOAM_USER_APPBIN"]`, `LIB = $(FOAM_USER_LIBBIN)/<lib>`
  a library `<lib>.so` or `<lib>.dylib` in `env["FOAM_USER_LIBBIN"]`;
- **source digest:** every `*.C`, `*.H`, `*.cu`, `*.cuh` file and every
  `Make/files` and `Make/options` under the repository root, outside
  `tutorials/`, `lnInclude/`, `platforms/` and `.git/`, hashed in sorted
  relative-path order as path and bytes. A tutorial edit does not change it; a
  build-option edit does.

**openCARP** answers `openCARP` (and each other program a plan runs that prints
`-buildinfo`) as `self_reported`, `source.git` holding the tag and hash.
**TorchCor** answers its package as `live` when `torchcor.__file__`, read with
the stack's `python3`, lies inside `repository.source`: the digest of that
tree's `*.py` files and the repository's git identity. Otherwise `unknown`.

## The run document

A plan that stages its case (`plan --strict`, `run`, `step`, a sweep case)
writes an optional `solverProvenance` list into the run document, one entry per
solver that answered:

```json
"solverProvenance": [
  {
    "solver": "org.cardiacfoam",
    "repository": {"repository": "…", "digest": "sha256:…", "git": {"commit": "…", "dirty": false}},
    "builds": [
      {"name": "cardiacFoam", "path": "…", "digest": "sha256:…", "known": "recorded",
       "source": {"repository": "…", "digest": "sha256:…", "git": {"commit": "04e6bd84…", "dirty": false}},
       "matchesRepository": false}
    ]
  }
]
```

- `repository` is the supplied repository's identity (its digest from that
  solver's own rule), or `null` with none supplied.
- `matchesRepository` is `true` or `false` when the build's `source.digest` and
  the repository's digest both exist, otherwise `null`. A `self_reported` build
  carries a commit and no digest, so it is `null`; its tag and hash are recorded.
- A solver that implements no `get_solver_builds` has no entry; its binaries
  stay hashed in the resume snapshot, as today.

Several solvers used in one session, a cross-solver comparison or a
cardiacCore-then-cardiacFOAM chain, each leave their entries in their own runs'
documents, so the solvers behind every result are listed.

The resume snapshot is unchanged and keeps guarding a resume.

## The preflight

The file-time comparison is deleted (`_sources`, `_stale_build` and
`_build_staleness_diagnostics` in `openfoam/environment_preflight.py`). Core
judges every solver the same way from `solverProvenance`:

| state | diagnostic |
|---|---|
| `matchesRepository` is `true`, or a `self_reported` or `live` build | none |
| `matchesRepository` is `false` | `stale_build` warning, one per solver and recorded source, naming its builds, both repositories, both commits and both digests |
| `known` is `unknown` | one `build_source_unknown` info note per solver listing the builds, and, for a recording stack, saying to run `omnidriver build-record --repo <repository>` after building |

A warning never blocks a plan, as before.

## Tests

No test runs a solver or a real build.

- **Core:** the record writer (merge, atomic replace, lock); the git reader on a
  `git init` repository (clean, dirty, no `.git`); `solverProvenance` and the
  preflight table above through a test provider that answers each `known`.
- **OpenFOAM layer:** products and digest on a temporary repository with
  `Make/files` and sources; a tutorial edit leaves the digest unchanged, a
  `Make/options` edit changes it; a recorded, a mismatched, an unrecorded and a
  rebuilt product. The file-time tests in `test_environment_preflight.py` are
  rewritten for digests, not deleted.
- **openCARP:** `-buildinfo` output (verbatim lines from the installed v18.1,
  committed as a fixture) parsed into tag and hash; a binary that prints none is
  `unknown`.
- **TorchCor:** a package location inside and outside `repository.source`.
- **CLI:** `build-record` with no `--repo` refuses with `usage`; a stack with no
  recordable products refuses with `build_products_undeclared`.
- The verification shapes of `CLAUDE.md`: all packages, core alone, the
  installed wheel, the static gates.

## Documentation

- `AGENT_GUIDE.md`: the `stale_build` paragraph is rewritten for digests, the
  build record and the per-solver `known`.
- `CLAUDE.md`: an invariant row, "a plan compares each solver build's source
  with the supplied repository by digest", with its guarding tests.
- `docs/superpowers/ROADMAP.md` §5.2: the "Binary versus source" item is
  removed; a follow-up is added: whether cardiacFOAM's backend inspection
  (`cardiacFoam.build.json`, with its file-time self-heal) moves into the build
  record.

## Out of scope

- omniD running the native build itself.
- A session-level summary beyond each run document's list.
- Refusing a run on a mismatch.
