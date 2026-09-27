# manufactured_bidomain's factory make_spec was deleted 2026-09-26: the
# tutorial migrated onto a tutorial record (records/manufactured_bidomain.py,
# tutorials-are-pointers plan, step 5.4b-B) -- it is no longer one of
# SPEC_FACTORIES/REGISTERED_TUTORIALS below, by design: `classify_entry`
# refuses a name that is registered as both a tutorial record and a factory
# tutorial, so removing it here happens in the same commit as registering
# the record.
# manufactured_bath_bidomain's factory make_spec was deleted 2026-09-26: the
# tutorial migrated onto a tutorial record (records/manufactured_bath_bidomain.py,
# tutorials-are-pointers plan §5b, step 5.4a); `classify_entry` refuses a name
# registered as both a tutorial record and a factory tutorial.
from omnidriver.cardiacfoam.tutorials.manufactured_monodomain_total_lagrangian_em import (
    make_spec as make_manufactured_monodomain_total_lagrangian_em_spec,
)
# cable_1d_cv_convergence's factory make_spec was deleted 2026-09-27: the
# tutorial migrated onto a tutorial record
# (records/cable_1d_cv_convergence.py, tutorials-are-pointers plan §5e, step
# 5.3) -- it is no longer one of SPEC_FACTORIES/REGISTERED_TUTORIALS below,
# by design: `classify_entry` refuses a name registered as both a tutorial
# record and a factory tutorial.
# manufactured_monodomain_pseudo_ecg's factory make_spec was deleted
# 2026-09-27: the tutorial migrated onto a tutorial record
# (records/manufactured_monodomain_pseudo_ecg.py, tutorials-are-pointers
# plan §5c, step 5.4b-P) -- it is no longer one of
# SPEC_FACTORIES/REGISTERED_TUTORIALS below, by design: `classify_entry`
# refuses a name registered as both a tutorial record and a factory
# tutorial. `_build_cases`/`_case_output_filename` and the two constants
# `manufactured_monodomain_total_lagrangian_em` still needed moved into
# that tutorial's own module/defaults (the only remaining factory caller).
# niederer_2011's factory make_spec was deleted 2026-09-26: the tutorial
# migrated onto a tutorial record (records/niederer_2011.py, plan
# docs/superpowers/plans/2026-09-25-tutorials-are-pointers-remaining.md
# §5c "5.4b-N") -- it is no longer one of SPEC_FACTORIES/REGISTERED_TUTORIALS
# below, by design: `classify_entry` refuses a name registered as both a
# tutorial record and a factory tutorial.
# restitution_curves's factory make_spec was deleted 2026-09-25: the
# tutorial migrated onto a tutorial record (records/restitution_curves.py,
# docs/superpowers/specs/2026-09-24-tutorials-are-pointers-design.md, step
# 4b) -- it is no longer one of SPEC_FACTORIES/REGISTERED_TUTORIALS below,
# by design: `classify_entry` refuses a name that is registered as both a
# tutorial record and a factory tutorial, so removing it here happens in
# the same commit as registering the record.
# single_cell's factory make_spec was deleted 2026-09-27: the tutorial
# migrated onto a tutorial record (records/single_cell.py, tutorials-are-
# pointers plan, step 5.1) -- it is no longer one of
# SPEC_FACTORIES/REGISTERED_TUTORIALS below, by design: `classify_entry`
# refuses a name registered as both a tutorial record and a factory
# tutorial.
# cable_1d_restitution's factory make_spec was deleted 2026-09-27: the
# tutorial migrated onto a tutorial record (records/cable_1d_restitution.py,
# tutorials-are-pointers plan §5e, step 5.2) -- it is no longer one of
# SPEC_FACTORIES/REGISTERED_TUTORIALS below, by design: `classify_entry`
# refuses a name registered as both a tutorial record and a factory
# tutorial.
# manufactured_monodomain_1d3d's and manufactured_purkinje_graph's factory
# make_specs were both deleted 2026-09-27: the two tutorials, which pointed
# at the same native case (manufacturedSolutions/monodomain1D3D), migrated
# onto ONE tutorial record (records/manufactured_monodomain_1d3d.py) --
# the old graph-only diagnostic is that record's `graphOnly` variant, not a
# second tutorial. Neither name is one of SPEC_FACTORIES/REGISTERED_TUTORIALS
# below any more, by design: `classify_entry` refuses a name registered as
# both a tutorial record and a factory tutorial. `manufacturedPurkinjeGraph`
# is refused like any unknown entry -- there is no alias.

from omnidriver.cardiacfoam.tutorials.ids import CardiacTutorialID

SPEC_FACTORIES = {
    CardiacTutorialID.MANUFACTURED_MONODOMAIN_TOTAL_LAGRANGIAN_EM.value: make_manufactured_monodomain_total_lagrangian_em_spec,
    "manufacturedelectromechanicsbc": make_manufactured_monodomain_total_lagrangian_em_spec,
}

REGISTERED_TUTORIALS = (
    CardiacTutorialID.MANUFACTURED_MONODOMAIN_TOTAL_LAGRANGIAN_EM.value,
)
