from enum import Enum


class CardiacTutorialID(str, Enum):
    SINGLE_CELL = "singleCell"
    CABLE_1D_CV_CONVERGENCE = "cable1DCVConvergence"
    NIEDERER_2011 = "niederer2011"
    MANUFACTURED_MONODOMAIN_PSEUDO_ECG = "manufacturedMonodomainPseudoECG"
    # MANUFACTURED_BIDOMAIN ("manufacturedBidomain") removed 2026-09-26:
    # migrated onto a tutorial record (records/manufactured_bidomain.py,
    # tutorials-are-pointers plan, step 5.4b-B), which names itself directly
    # rather than through this factory-tutorial enum -- a record is data,
    # not a factory, and this ID existed only to key
    # SPEC_FACTORIES/REGISTERED_TUTORIALS for the now-deleted factory.
    MANUFACTURED_BATH_BIDOMAIN = "manufacturedBathBidomain"
    MANUFACTURED_EIKONAL_ECG = "manufacturedEikonalECG"
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
    CABLE_1D_RESTITUTION = "cable1DRestitution"
