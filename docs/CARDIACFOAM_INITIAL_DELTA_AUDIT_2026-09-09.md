# Initial cardiacFOAM catalog delta audit

Date: 2026-09-09
Comparison: historical driverFOAM at `3c6b5e1640ef0f22e1099bf91bca1fbce2b94c92`, OmniDriver's current cardiac adapter, and the selected cardiacFOAM checkout at current gold `HEAD` `c3a852e957d23077ce1b2712331dfe45489c4386`.

This is the Batch 1 path-and-source inventory required by the reconciliation plan. It is read-only: a catalog path match is an inventory signal, not authorization to change a solver default or an applicability rule.

## Where the path differences live

The historical catalog has 161 distinct `driver_path` records and the current adapter has 151. There are 21 historical-only paths and 11 current-only paths.

| Delta | Location | Selected-solver evidence | Disposition |
| --- | --- | --- | --- |
| 15 historical-only `ecgDomains.<name>.personalizedTemplates.*` records | Historical catalog: `applications/scripts/driverFoam/openfoam_driver/plugins/cardiacfoam/dict_entries_catalog.py:927-1125`. Absent from the current adapter's `dict_entries_catalog.py` and its tests. | The selected solver implements the feature in `src/electroModels/ecgModels/eikonalECG/eikonalECG.C:61-190,588-679`; its tracked `tutorials/electrophysiologyProtocols/eikonalECGPersonalized/constant/electroProperties:67` configures it. | Missing cardiac-adapter catalog and fixture coverage. Do not copy blindly: preserve its exclusions (not combinable with manufactured ECG) and validate all nested keys against the selected source. |
| `conductionNetworkDomains.<name>.purkinjeGraphModelCoeffs.rootStimulus.startTimeList` | Historical catalog only; absent from current `dict_entries_catalog.py` and current template fixture. | `src/electroModels/electroDomains/conductionSystemDomain/conductionSystemDomain.C:245-251` reads `startTimeList`; the tracked Niederer Purkinje tutorial uses it at `tutorials/NiedererEtAl2011/purkinjeNiedererEtAl2011/constant/electroProperties.monodomain:66`. | Missing cardiac-adapter catalog entry and a targeted parsing/validation fixture. |
| `batchedIntegrator` applicability, not its path | Both catalogs expose `$ELECTRO_MODEL_COEFFS.batchedIntegrator`. Historical applicability also listed `LandNiedererBatched`, `LandNiedererTWorldBatched`, and `NashPanfilovBatched`; current `dict_entries_catalog.py:304-305` limits it to compact batched ionic models. | `src/activeTensionModels/activeTensionModel/batchedActiveTensionModel.C:50-92` reads and validates `batchedIntegrator`; all three active-tension runtime names are built in `src/activeTensionModels/Make/files:13-15`. | Missing active-tension activation condition. Verify each model's Rush--Larsen support before restoring the allowed enum combination; do not infer it from the common base class alone. |
| Active-tension selector identity | The adapter advertised `GoktepeKuhl` and `GoktepeKuhlBatched`, while the selected source had no corresponding source files or Make-file entries. It also selected `LandNiedererTWorld` variants without scientific metadata. | `src/activeTensionModels/Make/files:7-15` lists Nash, Land-Niederer, both T-World variants, and ManufacturedElectromechanics—never either Goktepe variant. | Remove stale Goktepe claims; add T-World scientific records and a selector/catalog identity assertion. |
| Five old `ecgDomains.<name>.verificationModel.*` paths | Historical-only: `type`, `enabled`, `dimension`, `referenceQuadratureOrder`, and `checkQuadratureOrders`. | `ecgVerificationModel::selectedType` still accepts a nested `verificationModel` at `src/electroModels/core/verificationModels/ecgVerificationModel.C:45-58`. | Unresolved compatibility surface. Current adapter replaces these with model-specific `manufactured.*` and `manufacturedEikonalECG.*` records; retain that normalized surface, then decide whether legacy nested form is a supported alias or intentionally unsupported. |
| Four `manufacturedBidomain.*` paths | Current-only: `alpha`, `enabled`, `fdaBathVariant`, and `k` in `dict_entries_catalog.py:1046-1078`. | Current selected source separates bidomain's manufactured sub-dictionary from the bath verifier's `verificationModel` input. | Intentional ownership correction; retain pending a source-reference verification pass. |
| Seven current ECG `manufactured.*` / `manufacturedEikonalECG.*` paths | Current-only, at `dict_entries_catalog.py:895-991`. | ECG model selection supports several shapes, including the old nested `verificationModel` form. | Intentional normalized replacement, but currently lacks an explicit legacy-alias decision and test. |
| `named_catalogs.py` | Same semantic location in historical driver and current cardiac adapter. | A byte-for-byte diff is empty. | Retained; no reconciliation work. |

## Verification-model note

The apparent `verificationModel.alpha` / `k` difference is predominantly a **path-ownership correction**, not a safe parity regression:

- Current adapter: `verificationModel.alpha` and `verificationModel.k` are restricted to `manufacturedFDABathBidomainVerifier` at `dict_entries_catalog.py:649-664`.
- Current adapter exposes the bidomain equivalents as `manufacturedBidomain.alpha` and `.k` at `dict_entries_catalog.py:1046-1060`.
- The selected source reads bath-bidomain values from the nested verification dictionary at `src/verificationModels/bathBidomainVerification/manufacturedFDABathBidomainVerifier.C:102-106`.

The historical broad predicates must therefore not be restored merely for path parity. The remaining ECG compatibility decision is separate from this correction.

## Test differences live in the cardiac adapter

The historical suite included `test_eikonal_ecg_personalized_templates_regression.py`; no corresponding current cardiac-adapter test exists. The current tests cover the template contract and dictionary catalog generally, but not personalized-template keys, their activation conditions, or the solver's manufactured-ECG exclusion.

The catalog-level fixes above belong in `packages/omnidriver-cardiacfoam/`. They require no Core or OpenFOAM behavior change. A future execution fixture may use OpenFOAM dictionary inspection, while Core supplies its usual transaction, provenance, and result-record mechanisms.

## Next bounded batch

1. Add the `rootStimulus.startTimeList` record with a fixture from the selected solver and a focused catalog/validation test.
2. Add a source-backed `personalizedTemplates` subcatalog and a fixture proving both valid configuration and the manufactured-ECG conflict.
3. Extend `batchedIntegrator` applicability only after a model-by-model Rush--Larsen support audit.
4. Record an explicit legacy-alias decision for ECG `verificationModel.*` before adding or rejecting it.

No defaults, dimensions, numerical tolerances, or solver execution behavior were changed by this audit.
