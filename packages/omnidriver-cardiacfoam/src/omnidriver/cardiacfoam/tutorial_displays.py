"""Display metadata for cardiacFoam's tutorial records.

Relocated here 2026-09-27 (tutorials-are-pointers step C) from
``tutorials/display.py`` once the factory-tutorial package around it was
deleted. Every entry below describes a tutorial record, which names itself
directly (no factory-tutorial enum survives to key these by) -- see
``.superpowers/sdd/legacy-map.md`` §2/§4. The one entry that did key off the
old factory enum, ``manufacturedMonodomainTotalLagrangianEM``, was deleted
alongside its factory module (owner decision: electromechanics has no
tutorial at all until it is rebuilt as a record).
"""

from omnidriver.core.tutorials_display import TutorialDisplay

TUTORIALS: tuple[TutorialDisplay, ...] = (
    TutorialDisplay(
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
