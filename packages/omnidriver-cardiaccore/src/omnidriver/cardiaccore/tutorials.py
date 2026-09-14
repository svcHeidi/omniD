"""Source-backed tutorial declarations for cardiacCore."""

from __future__ import annotations

from collections.abc import Mapping
from functools import partial
from pathlib import Path
from typing import Any

from omnidriver.core.runtime.models import CaseConfig, TutorialSpec
from omnidriver.core.specs.common import resolve_spec_paths


TUTORIAL_NAME = "cardiaccore-biv-preprocessing"


def _single_case() -> list[CaseConfig]:
    return [CaseConfig(case_id="bivCase", params={})]


def _apply_case(
    case_root: Path,
    case: CaseConfig,
    *,
    input_overrides: Mapping[str, Any] | None,
) -> None:
    del case
    from .input_overrides import apply_input_overrides

    apply_input_overrides(case_root, input_overrides)


def make_biv_preprocessing_spec(
    *,
    cases_root: Path | None = None,
    case_dir_name: str = "bivCase",
    setup_dir_name: str | None = None,
    output_dir_name: str | Path | None = ".",
    input_overrides: Mapping[str, Any] | None = None,
) -> TutorialSpec:
    """Declare the exact four-utility order of ``cases/bivCase/Allrun``.

    This is intentionally a preprocessing workflow, not a cardiac solver
    model.  Its only inputs and outputs are the files named by the native
    case wrapper and the corresponding utility sources.
    """

    case_root, setup_root, output_dir = resolve_spec_paths(
        cases_root=cases_root,
        case_dir_name=case_dir_name,
        setup_dir_name=setup_dir_name,
        output_dir_name=output_dir_name,
        default_output_dir_name=".",
    )
    return TutorialSpec(
        name=TUTORIAL_NAME,
        case_root=case_root,
        setup_root=setup_root,
        output_dir=output_dir,
        build_cases=_single_case,
        apply_case=partial(_apply_case, input_overrides=input_overrides),
        metadata={
            "notes": (
                "Source-backed declaration of cardiacCore cases/bivCase/Allrun. "
                "The native wrapper runs these utilities serially."
            ),
            "input_overrides": dict(input_overrides or {}),
            "workflow_dag": {
                "steps": [
                    {
                        "id": "conductivity",
                        "command": "setCardiacConductivity",
                        "args": ["-case", "."],
                        "depends_on": [],
                        "consumes": [
                            "system/setCardiacConductivityDict",
                            "0/fiber",
                            "0/sheet",
                        ],
                    },
                    {
                        "id": "anatomy",
                        "command": "setCardiacAnatomy",
                        "args": ["-case", "."],
                        "depends_on": ["conductivity"],
                        "consumes": [
                            "system/setCardiacAnatomyDict",
                            "0/uvc_longitudinal",
                            "0/uvc_intraventricular",
                        ],
                    },
                    {
                        "id": "purkinje_slab",
                        "command": "setPurkinjeSlab",
                        "args": ["-case", "."],
                        "depends_on": ["anatomy"],
                        "consumes": [
                            "system/setPurkinjeSlabDict",
                            "0/uvc_transmural",
                            "0/Conductivity",
                        ],
                    },
                    {
                        "id": "purkinje_morphometry",
                        "command": "setPurkinjeMorphometry",
                        "args": ["-case", "."],
                        "depends_on": ["purkinje_slab"],
                        "consumes": [
                            "system/setPurkinjeMorphometryDict",
                            "0/uvc_longitudinal",
                            "0/uvc_intraventricular",
                        ],
                    },
                ],
            },
        },
    )
