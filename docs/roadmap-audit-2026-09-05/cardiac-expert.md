# cardiacFOAM contract expert audit

Date: 2026-09-05. This supplements `simulation-team.md` and `OMNIDRIVER_ROADMAP.md`; it does not repeat their dictionary parser, scanner, or general typical-value findings. No solver runs, builds, or production edits were performed. Three tiny Python probes invoked existing validation functions, using only temporary files. No applicable AGENTS.md was found in the inspected package/source hierarchy.

Evidence identity: omniDriver HEAD `d19ea1543f1c7be7ce10084f06a2434c0901a011`, inspected working tree; selected cardiac source `/Users/simaocastro/noFrontendCardiacFoam_minor_errors`, HEAD `b39b65a25ccb8f62c861e3f6b5636274a77d44b3`, with local modifications. These are source observations, not proof of the installed binary's source identity. The other available checkout `/Users/simaocastro/cardiacFoam` has HEAD `faec7e2a4c6d0cfccca37ff99434373798b8210e`; it was inventoried but not used as the C++ semantic oracle. Below, `P/` means `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/`, and `C/` means the selected cardiac source root.

## High-value findings

### CF-01 — Build identity validation is incomplete (P0, reproduced)

`P/runtime_profile.py:349` iterates `payload.get("artifacts", ())` without requiring an artifact list, solver entry, common libraries, schema version, or plugin identity. Missing OpenFOAM/solids root values are also accepted (`:334–339`). A temporary manifest containing only backend `lightweight` and linked name `libphysicsModel.dylib` returned `None` (success) from `_validate_build_manifest`, even when passed an explicit OpenFOAM root. This proves the validator can certify a manifest without checking any compiled artifact. It does not prove another surrounding check would accept an entirely absent runtime.

There is a separate identity seam: manifest generation selects `FOAM_USER_APPBIN/cardiacFoam` (`:238–242`), whereas runtime dependency discovery selects `shutil.which("cardiacFoam", path=PATH)` (`P/runtime_evidence.py:240`). Manifest validation does not receive the dispatch executable path. A PATH-shadowed executable is therefore not bound by this validator to its manifest.

**Retain:** artifact hashing and explicit backend selection. **Refactor:** require a strict manifest schema and complete required artifact set; bind exact executable and resolved loader library paths to the plan and dispatch. **Gate:** reject omitted artifacts, duplicate artifact names, wrong plugin/schema, different PATH solver, and unresolved required libraries; verify the dispatch executable digest equals the validated artifact.

### CF-02 — Runtime inspection is presented as stronger build provenance than it establishes (P1, source verified)

`P/runtime_profile.py:224–230` claims generated manifests cannot disagree with reality. The generation trigger checks only solver mtime (`:245`); a library-only rebuild leaves the manifest unchanged, after which the digest validator reports stale artifacts instead of refreshing them. More fundamentally, OpenFOAM root/version/options come from the current environment (`:293–296`), and solids4foam revision comes from the current source checkout (`:280–300`). Neither establishes what was used when the binary was built. The generated manifest has no cardiac source revision or dirty-tree identity. Library records are chosen by directory search (`:263–272`), not by the loader-resolved path reported for the executable.

**Retain:** runtime inspection as evidence with its own provenance category. **Refactor:** separate immutable build attestation (emitted by the build, including source/dirty-state and toolchain identity) from current runtime inspection. Do not silently manufacture historical build metadata during environment configuration. **Gate:** a library-only rebuild, changed source checkout, changed environment, and loader-path substitution must produce distinct, truthful evidence states. This audit did not inspect the actual installed binary or claim its current manifest is wrong.

### CF-03 — Compatibility collapses named networks and leaves uncovered combinations silent (P1, reproduced)

`P/validation.py:32–40` selects the first conduction network solver. `_find_declared_couplers` collects all couplers (`:44–50`), then `_evaluate_solver_coupling` compares all of them against that one solver (`:59–60`, `:102–114`). This differs from C++: `C/src/electroModels/core/system/electrophysicsSystemBuilder.C:265–302` resolves each coupling's explicit `conductionNetworkDomain` and passes that named domain to the coupler factory.

A Python probe with monodomain myocardium, network A using monodomain1D/reactionDiffusion and network B using eikonal1D/eikonalMonodomain generated an incompatibility for B against A's solver. Both pairs are individually allowed by `P/solver_coupling.py:47–52` and `:73–76`. This is a proven validation scoping error, not a claim that every such mixed-network case is scientifically valid.

An unlisted pair returns `[]`: the loop only handles matching rules and then returns errors (`P/validation.py:64–72`, `:118`). A probe using `unreviewedNetworkSolver` demonstrated that behavior. Additionally, repository search found `compatible_solvers` only in catalog declarations/tests, with no production consumer enforcing that ionic-model field. `P/cardiacfoam_plugin.py:325–352` checks solver and ionic-model membership separately.

**Refactor:** validate each named coupling edge against its actual source/target models, build capabilities and required fields. Represent uncovered combinations explicitly as unknown/unsupported, with declared policy. **Gate:** two-network order-invariance fixtures; every advertised solver/model pair has evidence; every absent pair yields unknown or unsupported; review compatibility restrictions against C++ before enforcing currently informational catalog metadata.

### CF-04 — An ionic recommendation crosses a units/meaning boundary (P1, source verified)

`P/ionic_model_catalog.py:86–97` explicitly defines recommended stimulus values as PDE volumetric stimulus (intensity in A/m³). The AlievPanfilov entry instead describes dimensionless stimulus intensity about 0.5 and duration about 1.0, then sets those same recommendation fields to 0.5 and 1.0 (`:140–144`). The dictionary catalog describes duration in seconds with typical value 0.002 (`P/dict_entries_catalog.py:576–586`). Selected C++ reads the PDE entries using `dimTime` and `dimCurrent/dimVolume` (`C/src/genericWriter/stimulusIO.C:350–352`, `:374–376`).

This proves inconsistent metadata semantics; it does not establish that those numerical values are always invalid or that an observed run was affected. No automatic unit conversion or validated physiological calibration was established in this audit.

**Refactor:** distinguish model-internal dimensionless quantities, dimensional solver inputs, tutorial protocol values and validated numerical recommendations. Recommendations require units, model/solver scope, protocol, evidence and applicability. **Gate:** each supported recommendation can be traced to a dimensionally correct input and named validation protocol; do not silently interpret a dimensionless example as an SI PDE recommendation.

### CF-05 — Useful live catalog verification is narrower than advertised authority (P1, source verified)

The static catalog claims build-time generation and exact guaranteed names (`P/ionic_model_catalog.py:31–36`). Its own verification module explains static extraction cannot guarantee the runtime vocabulary (`P/ionic_catalog_verification.py:32–60`). The live checker is valuable: it compares against the utility and explicitly makes skipped checks non-passing (`:350–365`). However, it enumerates catalog entries only (`:348`), so a newly registered runtime model absent from the catalog is not discovered by that loop. Production-source search found no caller of `verify_ionic_catalog` outside its defining module; the live tests call it and skip when the utility is absent (`packages/omnidriver-cardiacfoam/tests/test_ionic_catalog_live_verification.py:64–83`). A checked-in catalog has no per-entry build/source digest binding.

Tutorial scope is coupled to the catalog: single-cell defaults automatically select all nonmanufactured catalog models and assign stimuli through Fabbri-name/model-class branches (`P/tutorials/defaults/single_cell.py:45–66`). This makes new catalog entries expand tutorial coverage without a separate validated protocol declaration. Registration should not imply tested readiness.

**Retain:** runtime vocabulary verification, distinction between native and approximate tissue labels, tutorial factories and explicit skip states. **Refactor:** export structured runtime model inventory and parameter metadata from a build-matched utility; reconcile both missing and extra models; bind generated catalog artifacts to the executable/libraries and preserve curated scientific annotations separately. Mark tutorials by validated profile/build instead of allowing registration to imply validation. **Gate:** runtime-extra and catalog-extra model drift both fail the supported-profile release check; utility/build mismatch fails; missing native checks cannot release that profile; adding a catalog model cannot silently declare a tutorial validated.

## Bounded roadmap addition

1. Repair manifest completeness/executable binding and network-scoped compatibility before claiming dependable preflight.
2. Establish build attestation plus structured native inspection for the first declared cardiacFOAM/OpenFOAM profile.
3. Reconcile generated runtime facts and curated physics metadata with separate provenance and uncertainty states.
4. Validate a small supported tutorial matrix (single cell, monodomain, bidomain, selected coupling and mechanics backend) using named scientific checks; expand coverage only as evidence is added.

The existing package boundary remains useful. The necessary change is to make solver evidence authoritative and scoped, rather than add more parallel descriptions of solver behavior.
