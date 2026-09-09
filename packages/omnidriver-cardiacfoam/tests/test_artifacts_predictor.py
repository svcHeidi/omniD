from __future__ import annotations

import fnmatch
from pathlib import Path

from omnidriver.cardiacfoam.artifacts_predictor import _predict_verification


def _electro_properties(
    tmp_path: Path, *, myocardium_solver: str, verifier_type: str
) -> Path:
    path = tmp_path / "constant" / "electroProperties"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""FoamFile
{{
    version 2.0;
    format ascii;
    class dictionary;
    object electroProperties;
}}
myocardiumSolver {myocardium_solver};
{myocardium_solver}Coeffs
{{
    verificationModel
    {{
        type {verifier_type};
    }}
}}
"""
    )
    return path


# Regression coverage for a real false-positive "missing_artifacts" failure:
# every non-Eikonal manufactured verifier writes "<...>_<N>_cells.dat" (no
# trailing token after "cells" before the extension), confirmed directly
# against each verifier's own OFstream call --
#   3D_19_cells.dat                   manufacturedFDAMonodomainVerifier.C:186
#   rotatedAnisotropy_3D_19_cells.dat manufacturedAnisotropicMonodomainVerifier.C:416
#   bathBidomain_3D_19_cells.dat      manufacturedFDABathBidomainVerifier.C:426
#   <dimension>_19_cells.dat          manufacturedFDABidomainVerifier.C:285
# The previously declared pattern, "*_*_cells_*.dat", required a further
# "_<token>" between "cells" and ".dat" that none of them have, so a
# successful solve was always reported as missing this artifact.
_CASES = (
    ("monodomainSolver", "manufacturedFDAMonodomainVerifier", "3D_19_cells.dat"),
    (
        "monodomainSolver",
        "manufacturedAnisotropicMonodomainVerifier",
        "rotatedAnisotropy_3D_19_cells.dat",
    ),
    ("bidomainSolver", "manufacturedFDABidomainVerifier", "3D_19_cells.dat"),
    (
        "bidomainSolver",
        "manufacturedFDABathBidomainVerifier",
        "bathBidomain_3D_19_cells.dat",
    ),
)


def test_verification_artifact_pattern_matches_every_real_verifier_filename(tmp_path):
    for index, (myocardium_solver, verifier_type, real_filename) in enumerate(_CASES):
        case_root = tmp_path / f"case{index}"
        _electro_properties(
            case_root, myocardium_solver=myocardium_solver, verifier_type=verifier_type
        )

        artifacts = _predict_verification(case_root)
        assert len(artifacts) == 1
        pattern = artifacts[0].path_pattern

        assert fnmatch.fnmatch(f"postProcessing/{real_filename}", pattern), (
            f"{verifier_type}: pattern {pattern!r} does not match real "
            f"filename {real_filename!r}"
        )
        # Document the bug this replaces: the old pattern required a token
        # after "cells" that no real filename has.
        assert not fnmatch.fnmatch(
            f"postProcessing/{real_filename}", "postProcessing/*_*_cells_*.dat"
        )


def test_eikonal_verification_artifact_pattern_is_unaffected(tmp_path):
    case_root = tmp_path / "eikonal"
    _electro_properties(
        case_root,
        myocardium_solver="eikonalSolver",
        verifier_type="manufacturedEikonalECGVerifier",
    )

    artifacts = _predict_verification(case_root)
    assert artifacts[0].path_pattern == "postProcessing/manufactured*Summary*.dat"
