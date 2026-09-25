# Independent adapter contract review

2026-09-22. Maintainer role; read the maintainer routing, adapter lead report, consolidated roadmap, and relevant implementation. Bounded independent falsification of A1–A3; no production changes, no native solver execution, no broad suite rerun. All fixtures used `TemporaryDirectory` and `/tmp/od311/bin/python` with the installed editable packages.

## Verdict

The adapter lead's strongest mechanical findings are reproducible. Retain the roadmap's decision to revise Phase 2 before migration. Normalize qualified addresses, value shapes, lifecycle and evidence; do not normalize away the difference between a preprocessing workflow and a solver simulation.

## Confirmed claims

**A1: configuration identity loss is committed and observable after a real write.** A disposable slab case with `setCardiacConductivityDict` containing `fiberField originalFiber; sheetField originalSheet;` and the requested override `$CARDIAC_CONDUCTIVITY.fiberField = customFiber` produced:

- `read_input_values`: conductivity `fiberField='originalFiber'`, scar `fiberField=None`.
- `build_config`: `preprocessing.fiberField=None`, `sheetField=None`, diagnostics `()`.
- After `apply_input_overrides`, the actual conductivity dictionary contained `fiberField customFiber;`.
- A second `build_config` still reported `fiberField=None`.

Thus this is not just a proposed-plan display problem or a failure to apply the override. `build_config` first updates qualified values, then collapses keys using `slot_key`; the later absent scar value wins. The three current collisions independently enumerated from `CATALOG.entries` are `fiberField`, `sheetField`, and `severityField`. `git show HEAD:.../workflows/run_config.py` contains the defective `build_config` unchanged. The user's working-tree diff only appends validator helpers.

**A2: unsupported bindings and malformed shapes pass the override validator.** All of these independently returned their input mapping without exception under `allowed_paths=PURKINJE_TREE_INPUT_PATHS`:

```python
{'$PURKINJE_TREE.nonsense.N_it': 3}
{'$PURKINJE_TREE.lv.seed': 'not a vector'}
{'$CARDIAC_CONDUCTIVITY.df': float('nan')}
{'$PURKINJE_TREE.lv.seed': [float('inf'), 0, 0]}
```

`_template_for` does not restrict the substituted segment to `VENT_KEYS`; `_check_value` checks string nonemptiness for vectors and numeric class membership without finiteness checks. The adapter's declared binding domain is `('lv', 'rv')`, explicitly linked in the catalog to native `readVentParams` calls. Native source/runtime behavior was not independently re-executed here, so the directly established claim is violation of the adapter's declared native contract. Add vector component finiteness to the existing S1 regression gate. Strict JSON cannot express these nonfinite literals, but Python callers can.

**A3: dictionary effect and declared workflow input disagree.** The same successful `customFiber` mutation leaves the slab conductivity DAG step at:

```python
{'command': 'setCardiacConductivity',
 'consumes': ['system/setCardiacConductivityDict', '0/fiber', '0/sheet'], ...}
```

The catalog explicitly identifies `fiberField`/`sheetField` as field names. Utility manifests also contain those default field paths. In addition, the slab factory retains `$CARDIAC_SCAR.selection='scar.vtu'`; its advertised schema exposes all catalog entries and the standalone validator accepts that override. No active-input filter is supplied by this factory. This establishes disagreement between accepted edits and selected workflow consumption, without claiming a particular native runtime outcome.

**A4: preserve the WIP attribution.** `CardiacCorePlugin.validate_configuration` remains `del spec; return ()`; calling it returned `()`. The appended helper in the dirty file is not wired by that method. The untracked test invokes the plugin method. This review did not rerun that known failing test; the lead/root executions already establish its result. The helper also reads original case values without overlaying requested overrides, so merely connecting it would not meet the roadmap's effective-configuration requirement. Generic case bypass remains a legitimate support difference.

## Qualifications and minimal roadmap amendments

1. Keep the DAG mismatch as a confirmed adapter defect, but do not promote it to a proven missing resume hash or false preflight rejection. Core's `runtime.provenance_inputs.enumerate_case_inputs` path also walks declared case roots and fingerprints fallback inputs; a renamed field can therefore be included even though `consumes` is wrong. The final consumed-path pass also records default paths. Exact public-route failure or incorrect digest needs its own fixture before editing Core. The lead correctly marked this consequence as conditional; retain that qualification.
2. Separate request type normalization from physiological validation. Reject malformed vectors and enforce declared placeholder bindings using the format and adapter contracts. Do not infer new physiological ranges from this audit. Declare any finite-only policy explicitly and apply it consistently to scalar and vector components.
3. Repair qualified identity at the adapter record boundary without immediately redesigning every catalog. Workflow scoping reduces irrelevant inputs, but cannot generally replace collision-safe identities when a workflow legitimately consumes two documents with the same leaf. Test both cases.
4. Keep supported mutation, workflow consumption and general native-key discovery distinct. Agents may inspect keys outside a selected workflow, but an accepted workflow edit must disclose or reject a no-effect change. Fix stale claims that tree inputs are frozen; current routing explicitly permits them.
5. The existing WIP is evidence of in-progress repair, not a regression caused by this audit. Coordinate its completion before changing the same file. Public composed-context validation should test source values plus requested overrides and preserve the generic-case bypass.

No changes to the overall gate ordering are needed. S1/S2 are justified prerequisites; one transactional write channel remains useful after these defects have executable regression gates.
