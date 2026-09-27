from omnidriver.cardiacfoam.tutorials.ids import CardiacTutorialID
from omnidriver.core.tutorials_display import TutorialDisplay

TUTORIALS: tuple[TutorialDisplay, ...] = (
    TutorialDisplay(
        # A literal string, not `CardiacTutorialID.SINGLE_CELL` (removed
        # 2026-09-27 alongside the factory it keyed): this tutorial is now a
        # tutorial record (records/single_cell.py), which names itself
        # directly, the same way restitutionCurves's own display entry does.
        id="singleCell",
        title="Single-cell action potential",
        summary=(
            "Run a single-cell sweep over an ionic model to inspect AP "
            "morphology. Useful for drug-effect studies."
        ),
        thumbnail="/tutorials/single-cell.png",
        tags=("single-cell", "ionic-model", "AP"),
        preset={
            "anatomy.mesh": "single-cell",
            "physics.ionic_model": "TenTusscher",
        },
    ),
    TutorialDisplay(
        id="niederer2011",
        title="Niederer 2011 verification benchmark",
        summary=(
            "The Niederer et al. 2011 N-version benchmark for cardiac "
            "tissue electrophysiology. Validates monodomain solvers."
        ),
        thumbnail="/tutorials/niederer-2011.png",
        tags=("benchmark", "verification", "monodomain"),
        preset={
            "anatomy.mesh": "niederer-slab",
            "physics.ionic_model": "TenTusscher",
        },
    ),
    TutorialDisplay(
        # A literal string, not `CardiacTutorialID.MANUFACTURED_MONODOMAIN_
        # PSEUDO_ECG` (removed 2026-09-27 alongside the factory it keyed):
        # this tutorial is now a tutorial record
        # (records/manufactured_monodomain_pseudo_ecg.py), which names
        # itself directly, the same way restitutionCurves's own display
        # entry does above.
        id="manufacturedMonodomainPseudoECG",
        title="Manufactured solution (monodomain)",
        summary=(
            "Method of manufactured solutions on the monodomain "
            "equation. Used to verify spatial/temporal convergence."
        ),
        thumbnail="/tutorials/manufactured-fda.png",
        tags=("manufactured-solution", "verification", "monodomain"),
        preset={
            "anatomy.mesh": "fda-cuboid",
            "physics.ionic_model": "FentonKarma",
        },
    ),
    TutorialDisplay(
        # A literal string, not `CardiacTutorialID.MANUFACTURED_BIDOMAIN`
        # (removed 2026-09-26 alongside the factory it keyed): this tutorial
        # is now a tutorial record (records/manufactured_bidomain.py), which
        # names itself directly, the same way restitutionCurves's own
        # display entry does above.
        id="manufacturedBidomain",
        title="Manufactured solution (bidomain)",
        summary=(
            "Same MMS verification at bidomain resolution. Pairs with "
            "the monodomain variant for cross-formulation comparison."
        ),
        thumbnail="/tutorials/manufactured-fda-bidomain.png",
        tags=("manufactured-solution", "verification", "bidomain"),
        preset={
            "anatomy.mesh": "fda-cuboid",
            "physics.ionic_model": "FentonKarma",
        },
    ),
    TutorialDisplay(
        id="manufacturedBathBidomain",
        title="Manufactured solution (bath bidomain)",
        summary=(
            "FDA bidomain-with-bath manufactured solution with a grounded "
            "bath electrode and bath ECG potential verification."
        ),
        thumbnail="/tutorials/manufactured-fda-bath-bidomain.png",
        tags=("manufactured-solution", "verification", "bidomain", "bath-ecg"),
        preset={
            "anatomy.mesh": "fda-bath-cuboid",
            "physics.ionic_model": "FentonKarma",
        },
    ),
    TutorialDisplay(
        id="manufacturedEikonalECG",
        title="Manufactured solution (eikonal ECG)",
        summary=(
            "Manufactured eikonal activation-time verification with template "
            "surrogate ECG and quadrature ECG reference."
        ),
        thumbnail="/tutorials/manufactured-eikonal-ecg.png",
        tags=("manufactured-solution", "verification", "eikonal", "ecg"),
        preset={
            "anatomy.mesh": "unit-domain",
            "physics.ionic_model": "none",
        },
    ),
    TutorialDisplay(
        id=CardiacTutorialID.MANUFACTURED_MONODOMAIN_TOTAL_LAGRANGIAN_EM.value,
        title="Manufactured electromechanics (MMS) -- NOT CURRENTLY WORKING",
        summary=(
            "NOT CURRENTLY WORKING: electromechanics is unsupported at the "
            "moment and this entry fails strict planning. Do not pick it, and "
            "do not try to repair it as a side quest -- it is a known, "
            "deliberately deferred gap, not a bug you have just found. "
            "It lays its dicts out per region (constant/electro/"
            "electroProperties, constant/solid/solidProperties) while the "
            "planner looks for constant/electroProperties, so it reports "
            "missing_electro_properties, 'myocardiumSolver is required' and "
            "empty_artifact_prediction. "
            "Intended behaviour once supported: electromechanics verification "
            "on a fully coupled manufactured field, with Vm, D, lambda and Ta "
            "as rigorous MMS targets."
        ),
        thumbnail="/tutorials/manufactured-electromechanics-bc.png",
        tags=("manufactured-solution", "verification", "electromechanics"),
        preset={
            "anatomy.mesh": "unit-domain",
            "physics.ionic_model": "monodomainFDAManufactured",
        },
    ),
    TutorialDisplay(
        # A literal string, not `CardiacTutorialID.MANUFACTURED_MONODOMAIN_
        # 1D3D` (removed 2026-09-27 alongside the factory it keyed): this
        # tutorial is now a tutorial record
        # (records/manufactured_monodomain_1d3d.py), which names itself
        # directly, the same way restitutionCurves's own display entry does
        # above. It replaces this entry AND the old, now-deleted
        # "manufacturedPurkinjeGraph" display entry: the graph-only
        # diagnostic that factory tutorial ran is this record's `graphOnly`
        # variant, not a second tutorial -- "manufacturedPurkinjeGraph" is
        # refused like any unknown entry, with no alias.
        id="manufacturedMonodomain1D3D",
        title="Manufactured Purkinje-myocardium coupling (MMS)",
        summary=(
            "Coupled 1D Purkinje graph / 3D monodomain manufactured-solution "
            "convergence, across decoupled, unidirectional, and bidirectional "
            "PVJ transfer regimes -- or the 1D graph alone, on its own "
            "mesh-refinement convergence."
        ),
        thumbnail="/tutorials/manufactured-monodomain-1d3d.png",
        tags=("manufactured-solution", "verification", "purkinje", "coupling", "1D-3D"),
        preset={
            "anatomy.mesh": "unit-domain",
            "physics.ionic_model": "monodomainFDAManufactured",
        },
    ),
    TutorialDisplay(
        id="restitutionCurves",
        title="Restitution curves (S1–S2 protocol)",
        summary=(
            "S1–S2 pacing protocol that traces APD restitution. Useful "
            "for arrhythmia substrate studies."
        ),
        thumbnail="/tutorials/restitution-curves.png",
        tags=("single-cell", "S1-S2", "restitution"),
        preset={
            "anatomy.mesh": "single-cell",
            "physics.ionic_model": "TenTusscher",
            "stimulus.protocol": "s1s2",
        },
    ),
    TutorialDisplay(
        id="cable1DCVConvergence",
        title="1D Cable CV Convergence",
        summary=(
            "1D cable verification protocol to extract continuous conduction "
            "velocity profiles and perform mesh resolution convergence sweeps."
        ),
        thumbnail="/tutorials/cable-cv-convergence.png",
        tags=("cable", "cv", "convergence", "monodomain", "eikonal"),
        preset={
            "anatomy.mesh": "cable-1d",
            "physics.ionic_model": "BuenoOrovio",
        },
    ),
    TutorialDisplay(
        id="cable1DRestitution",
        title="1D Cable Restitution",
        summary=(
            "1D cable protocol to extract continuous APD and CV restitution curves."
        ),
        thumbnail="/tutorials/cable-restitution.png",
        tags=("cable", "restitution", "apd", "cv"),
        preset={
            "anatomy.mesh": "cable-1d",
            "physics.ionic_model": "BuenoOrovio",
        },
    ),
)
