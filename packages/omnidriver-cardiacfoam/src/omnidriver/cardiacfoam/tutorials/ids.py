from enum import Enum


class CardiacTutorialID(str, Enum):
    # SINGLE_CELL ("singleCell") removed 2026-09-27: migrated onto a tutorial
    # record (records/single_cell.py, tutorials-are-pointers plan, step
    # 5.1), which names itself directly rather than through this
    # factory-tutorial enum -- see RESTITUTION_CURVES's identical removal
    # note below.
    # CABLE_1D_CV_CONVERGENCE ("cable1DCVConvergence") removed 2026-09-27:
    # migrated onto a tutorial record (records/cable_1d_cv_convergence.py,
    # tutorials-are-pointers plan §5e, step 5.3), which names itself
    # directly rather than through this factory-tutorial enum -- see
    # RESTITUTION_CURVES's identical removal note below.
    # NIEDERER_2011 ("niederer2011") removed 2026-09-26: migrated onto a
    # tutorial record (records/niederer_2011.py, plan docs/superpowers/
    # plans/2026-09-25-tutorials-are-pointers-remaining.md §5c "5.4b-N"),
    # which names itself directly rather than through this factory-tutorial
    # enum -- same reasoning as RESTITUTION_CURVES's removal below.
    # MANUFACTURED_MONODOMAIN_PSEUDO_ECG ("manufacturedMonodomainPseudoECG")
    # removed 2026-09-27: migrated onto a tutorial record
    # (records/manufactured_monodomain_pseudo_ecg.py, tutorials-are-pointers
    # plan §5c, task 5.4b-P), which names itself directly rather than
    # through this factory-tutorial enum -- see RESTITUTION_CURVES's
    # identical removal note below.
    # MANUFACTURED_BIDOMAIN ("manufacturedBidomain") removed 2026-09-26:
    # migrated onto a tutorial record (records/manufactured_bidomain.py,
    # tutorials-are-pointers plan, step 5.4b-B), which names itself directly
    # rather than through this factory-tutorial enum -- a record is data,
    # not a factory, and this ID existed only to key
    # SPEC_FACTORIES/REGISTERED_TUTORIALS for the now-deleted factory.
    # MANUFACTURED_BATH_BIDOMAIN ("manufacturedBathBidomain") removed
    # 2026-09-26: migrated onto a tutorial record
    # (records/manufactured_bath_bidomain.py, tutorials-are-pointers plan
    # §5b, step 5.4a) -- see RESTITUTION_CURVES's removal note below.
    # MANUFACTURED_EIKONAL_ECG ("manufacturedEikonalECG") removed 2026-09-26:
    # migrated onto a tutorial record (records/manufactured_eikonal_ecg.py,
    # docs/superpowers/plans/2026-09-25-tutorials-are-pointers-remaining.md
    # §5c, task 5.4b-E), which names itself directly rather than through
    # this factory-tutorial enum -- see RESTITUTION_CURVES's identical
    # removal note below.
    MANUFACTURED_MONODOMAIN_TOTAL_LAGRANGIAN_EM = "manufacturedMonodomainTotalLagrangianEM"
    MANUFACTURED_MONODOMAIN_1D3D = "manufacturedMonodomain1D3D"
    MANUFACTURED_PURKINJE_GRAPH = "manufacturedPurkinjeGraph"
    # RESTITUTION_CURVES ("restitutionCurves") removed 2026-09-25: migrated
    # onto a tutorial record (docs/superpowers/specs/2026-09-24-tutorials-
    # are-pointers-design.md, step 4b), which names itself directly
    # (records/restitution_curves.py) rather than through this factory-
    # tutorial enum -- a record is data, not a factory, and this ID existed
    # only to key SPEC_FACTORIES/REGISTERED_TUTORIALS for the now-deleted
    # factory.
    # CABLE_1D_RESTITUTION ("cable1DRestitution") removed 2026-09-27:
    # migrated onto a tutorial record (records/cable_1d_restitution.py,
    # tutorials-are-pointers plan §5e, step 5.2), which names itself
    # directly rather than through this factory-tutorial enum -- see
    # RESTITUTION_CURVES's identical removal note above.
