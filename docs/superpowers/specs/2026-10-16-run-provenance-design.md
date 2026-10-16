# Run provenance: which source built the binary a run used

**Status:** approved design, 2026-10-16. Implementation on `feat/run-provenance`.

## The problem

On 2026-10-16 a native-main tutorial ran to completion on a `cardiacFoam` built
from PR #59, and nothing said so. Two gaps allowed it:

- **The run document names no solver.** The binary and library digests exist,
  but only in `workflow_state.json`'s `resume_snapshot`, where they guard a
  resume. Nothing records which source those binaries came from.
- **`stale_build` compares file times.** A `git archive` tree sets every file to
  its commit time, and a binary built from another worktree is newer than all
  of them, so the check passes. It also warns wrongly the other way: a fresh
  archive of the very source a binary was built from is "newer" than the binary.

A digest of the binary cannot say which source produced it. That link must be
written when the binary is built.

## Decisions (owner, 2026-10-16)

| question | decision |
|---|---|
| who records the link | an omniD command run after the native build: `omnidriver build-record --repo <src>` |
| where the record lives | beside the built products, found from the binary on `PATH` |
| a binary recorded from other source than the plan reads | a `stale_build` warning; the run is not refused |
| a binary with no record (or rebuilt since) | a `build_source_unknown` note; no file-time fallback |

## What is recorded

### The build record

`omnidriver build-record --repo <dir>` runs in the solver's own shell after a
build. The repository is supplied, never searched for. The command:

1. asks the stack for the products the repository builds and where they land
   (`get_build_products`, below). A product whose file does not exist is
   reported as not built and not recorded;
2. asks the stack for the digest of the sources a build reads
   (`get_build_source_digest`);
3. reads the repository's git identity when `<dir>/.git` exists (a directory or
   a worktree's file): `git rev-parse HEAD`, and `dirty` when
   `git status --porcelain --untracked-files=no` prints anything. Only the
   repository root is read; no parent directory is searched. A tree with no
   `.git` (an archive) has `git: null`; its digest still identifies it;
4. hashes each built product (sha256 of its bytes, the same content hash the
   resume snapshot uses);
5. writes one entry per product into `omnidriver-build.json` in the product's
   own directory, merging with the entries already there, so two worktrees that
   build into one platform folder each replace only their own products. The
   write is atomic (a temporary file, then `os.replace`) and serialised by an
   exclusive lock file beside it.

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

The command prints one JSON report: the source identity, the products recorded
(name, path, digest, record file), and those not built. A stack that declares
no build products refuses with the new code `build_products_undeclared`.

### The run document

A plan that stages its case (`plan --strict`, `run`, `step`, a sweep case) writes an optional
`solverProvenance` section into the run document:

```json
"solverProvenance": {
  "source": {"repository": "…", "digest": "sha256:…", "git": {"commit": "…", "dirty": false}},
  "binaries": [
    {"name": "cardiacFoam", "path": "…", "digest": "sha256:…",
     "builtFrom": {"repository": "…", "digest": "sha256:…", "git": {…}, "recordedAt": "…"},
     "matchesSource": false}
  ]
}
```

- `source` is the supplied repository's identity, computed the same way as in
  a build record; `null` when no repository is supplied (openCARP through
  `--plugin`, for example).
- `binaries` lists every runtime dependency the plan's provenance enumeration
  finds: the set the resume snapshot hashes (`enumerate_case_inputs`, its
  `runtime_dependency` components), computed on the staged case at plan time.
  So every solver's run document carries its binary digests, whether or not its
  plugin knows how it is built.
- `builtFrom` is the matching entry of the record beside the binary, when one
  exists and its `digest` equals the binary's; otherwise `null`.
- `matchesSource` is `true` or `false` when both `builtFrom` and `source` exist,
  otherwise `null`.

The resume snapshot is unchanged and keeps guarding a resume: a binary rebuilt
between plan and run still invalidates it.

## The preflight

The file-time comparison is deleted (`_sources`, `_stale_build` and
`_build_staleness_diagnostics` in `openfoam/environment_preflight.py`). Core
judges every stack the same way from `solverProvenance`, for the binaries that
are products of the supplied repository:

| state | diagnostic |
|---|---|
| `matchesSource` is `true` | none |
| `matchesSource` is `false` | `stale_build` warning, one per recorded source tree, naming its products, both repositories, both commits and both digests |
| a product with no record, or whose record's digest differs from the file (rebuilt without recording) | one `build_source_unknown` info note listing them, and saying to run `omnidriver build-record --repo <repository>` after building |
| no repository supplied | none |

A warning never blocks a plan, as before.

## The plugin contract

Two optional members join `provider_stack.MEMBERS`:

| member | composition | absent answer | answers |
|---|---|---|---|
| `get_build_products(repository_root, env)` | `sequence` | `()` | `BuildProduct(name, path, kind)` for each product the repository builds; `path` is where the build puts it under `env`, `kind` is `executable` or `library` |
| `get_build_source_digest(repository_root)` | `single` | `None` | `sha256:<hex>` of the files a build of the repository reads |

`BuildProduct` is a core dataclass beside `RuntimeDependency`. No contract
version bump: both members are optional, and a provider that implements
neither is unchanged at version 3.

**The OpenFOAM layer** implements both, once, for cardiacFOAM and cardiacCore
("one reality"):

- **products:** each `Make/files` under the repository root, outside
  `tutorials/`, `lnInclude/` and `platforms/`: `EXE = $(FOAM_USER_APPBIN)/<name>`
  is an executable in `env["FOAM_USER_APPBIN"]`, and
  `LIB = $(FOAM_USER_LIBBIN)/<lib>` a library `<lib>.so` or `<lib>.dylib` in
  `env["FOAM_USER_LIBBIN"]`;
- **source digest:** every `*.C`, `*.H`, `*.cu` and `*.cuh` file and every
  `Make/files` and `Make/options` under the repository root, outside
  `tutorials/`, `lnInclude/`, `platforms/` and `.git/`, hashed in sorted
  relative-path order as path and bytes. A tutorial edit does not change it; a
  build-option edit does.

openCARP and TorchCor implement neither now: their run documents carry binary
digests and, with a repository, its identity, with `builtFrom: null`.

## Tests

No test runs a solver or a real build.

- **Core:** the record writer (merge, atomic replace, lock), the git reader on a
  `git init` repository (clean, dirty, no `.git`), `solverProvenance` and the
  preflight table above, through the toy plugin given both members.
- **OpenFOAM layer:** products and digest on a temporary repository with
  `Make/files` and sources; a tutorial edit leaves the digest unchanged, a
  `Make/options` edit changes it. The four file-time tests in
  `test_environment_preflight.py` are rewritten for digests (match, mismatch,
  no record, a system binary that no `Make/files` builds), not deleted.
- **CLI:** `build-record` with no `--repo` refuses with `usage`; a stack with no
  products refuses with `build_products_undeclared`.
- The verification shapes of `CLAUDE.md`: all packages, core alone, the
  installed wheel, the static gates.

## Documentation

- `AGENT_GUIDE.md`: the `stale_build` paragraph is rewritten for digests and the
  build record.
- `CLAUDE.md`: an invariant row, "a plan compares a binary's recorded source
  with the supplied one by digest", with its guarding tests.
- `docs/superpowers/ROADMAP.md` §5.2: the "Binary versus source" item is
  removed.

## Out of scope

- omniD running the native build itself.
- Build products of solvers without a `Make/files` (openCARP, TorchCor).
- Refusing a run on a mismatch.
