# OmniD cardiacCore adapter experiment

This source-backed onboarding slice owns the four preprocessing utilities in
`cases/bivCase/Allrun`, their reviewed dictionary inputs, and their declared
field artifacts. A user supplies a normal run request through `--config`:

```json
{
  "input_overrides": {
    "$PURKINJE_SLAB.thickness": 0.05
  }
}
```

The adapter validates each path and value, writes only a disposable
materialized case, and records the effective values in the RunDocument's
`preprocessing` phase. It does not change the checked-in tutorial defaults.

The committed source fixture alone is not a complete runnable case: it lacks
`constant/polyMesh` and the initial `0/` fibre/UVC field bundle. A user must
supply the canonical asset bundle or a declared native generator before a
clean-clone run can be claimed. Conditional manual-AHA, pig-morphometry, and
bidomain tensor inputs remain explicitly unsupported in this first auto-mode
workflow slice.
