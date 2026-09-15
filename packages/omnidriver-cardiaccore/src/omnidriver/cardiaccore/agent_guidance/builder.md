# cardiacCore builder guidance

Use the plugin's public catalogs as the discovery surface. Keep schema and
operation descriptions free of simulation, case mutation, and analysis.

Add callable usage records in `catalogs/operations.py`, implementations in
`operations/`, and staged integration in `workflows/` only when supported.
Keep exact module:function references and argument names aligned with code.
Each record needs an example, preconditions, outputs, side effects, evidence,
and distinct mechanical/missing-capability/scientific limits. Do not copy
operation status into another independently maintained table.

Shared Purkinje method constants and baseline categories belong to
`catalogs/purkinje.py`; changing them is a method/policy change, not formatting.
Test catalog-driven invocation and packaged guidance outside the checkout.

Reusable transformations belong in `operations/`; workflow-specific scientific
acceptance criteria must be named and versioned separately. Native C++ behavior,
field conventions, units, and supported combinations require source evidence or
an explicit domain decision. Record pending readers and unresolved scientific
interpretation instead of inferring them from a Python function.
