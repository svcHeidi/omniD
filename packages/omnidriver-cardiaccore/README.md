# OmniD cardiacCore adapter experiment

This source-backed onboarding slice owns three deliberately distinct native
workflows: the four-stage `bivCase` preprocessing wrapper, a human
endocardial explicit-tree workflow, and a pig morphometric/transmural-tree
workflow. Each declares its reviewed dictionary inputs and generated
artifacts. A user supplies a normal run request through `--config`:

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

The explicit-tree workflows deliberately keep their tree seeds, growth, and
terminal-selection dictionaries fixed until their complete validation rules
are published. The human path needs the shared conductivity/anatomy inputs;
the pig path additionally runs morphometry and declares its two generated
terminal-weight fields as tree inputs. `generatePurkinjeTree` must run with
the staged case as its working directory because its VTK outputs are relative
to that directory.

The committed source fixture alone is not a complete runnable case: it lacks
`constant/polyMesh` and the initial `0/` fibre/UVC field bundle. A user must
supply the canonical asset bundle or a declared native generator before a
clean-clone run can be claimed. Manual-AHA and bidomain tensor branches remain
explicitly unsupported. Pig morphometry is supported only by the named pig
tree workflow; a user-facing tree-parameter sweep, coverage acceptance
criterion, and graph hand-off remain later increments.

## Canonical tree-validation contract

For an OmniD agent, the sole adapter-owned contract is
`omnidriver.cardiaccore.tree_validation` and the
`cardiaccore_tree_validation` named catalog exposed by the plugin. It defines
the basal-septal LV root criterion (AHA segments 2/3), the generator-specific
recovered-RV-septal UVC criterion, and the default coverage policy: occupied
mid/apical sectors where endocardium exists; basal gaps recorded as warnings.
Node/terminal counts and surface-distance measures are observations for later
ECG-driven optimisation, never universal acceptance thresholds.

The standalone `agent/` Python files, tutorial notes, and old run logs are
external provenance only. They are not separate instructions for an OmniD
agent.
