"""Source-backed tutorial declarations for cardiacCore workflows."""

from __future__ import annotations

from collections.abc import Mapping
from functools import partial
from pathlib import Path
from typing import Any

from omnidriver.core.runtime.models import CaseConfig, TutorialSpec
from omnidriver.core.specs.common import resolve_spec_paths


TUTORIAL_NAME = "cardiaccore-biv-preprocessing"
HUMAN_TREE_TUTORIAL_NAME = "cardiaccore-human-endocardial-tree"
PIG_MORPHOMETRIC_TREE_TUTORIAL_NAME = "cardiaccore-pig-morphometric-tree"
HUMAN_TREE_INPUT_PATHS = (
    "$CARDIAC_CONDUCTIVITY.df",
    "$CARDIAC_CONDUCTIVITY.ds",
    "$CARDIAC_CONDUCTIVITY.dn",
    "$CARDIAC_CONDUCTIVITY.fiberField",
    "$CARDIAC_CONDUCTIVITY.sheetField",
    "$CARDIAC_ANATOMY.zApicalMid",
    "$CARDIAC_ANATOMY.zMidBasal",
    "$CARDIAC_ANATOMY.zApexCap",
    "$CARDIAC_ANATOMY.grooveMode",
)
PIG_MORPHOMETRIC_TREE_INPUT_PATHS = (
    *HUMAN_TREE_INPUT_PATHS,
    "$PURKINJE_MORPHOMETRY.grooveMode",
)


def _single_case() -> list[CaseConfig]:
    return [CaseConfig(case_id="bivCase", params={})]


def _apply_case(
    case_root: Path,
    case: CaseConfig,
    *,
    input_overrides: Mapping[str, Any] | None,
) -> None:
    del case
    from .overrides import apply_input_overrides

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


def _apply_human_tree_case(
    case_root: Path,
    case: CaseConfig,
    *,
    input_overrides: Mapping[str, Any] | None,
) -> None:
    requested = dict(input_overrides or {})
    unsupported = sorted(set(requested).difference(HUMAN_TREE_INPUT_PATHS))
    if unsupported:
        raise ValueError(
            "The human endocardial-tree workflow currently supports the observed "
            "native tree dictionary as a fixed contract. Tree-parameter mutation is "
            "deferred until its complete seed/growth validation contract is added: "
            + ", ".join(unsupported)
        )
    _apply_case(case_root, case, input_overrides=requested)


def make_human_endocardial_tree_spec(
    *,
    cases_root: Path | None = None,
    case_dir_name: str = "bivCase",
    setup_dir_name: str | None = None,
    output_dir_name: str | Path | None = ".",
    input_overrides: Mapping[str, Any] | None = None,
) -> TutorialSpec:
    """Declare the native human endocardial explicit-tree wrapper.

    The selected case uses the fixed observed ``allLeaves``/``endocardial``
    mode. Tree inputs are intentionally not yet user-mutable: the next
    adapter increment must establish seed and growth validation before it
    exposes them as sweep axes.
    """

    case_root, setup_root, output_dir = resolve_spec_paths(
        cases_root=cases_root,
        case_dir_name=case_dir_name,
        setup_dir_name=setup_dir_name,
        output_dir_name=output_dir_name,
        default_output_dir_name=".",
    )
    return TutorialSpec(
        name=HUMAN_TREE_TUTORIAL_NAME,
        case_root=case_root,
        setup_root=setup_root,
        output_dir=output_dir,
        build_cases=_single_case,
        apply_case=partial(_apply_human_tree_case, input_overrides=input_overrides),
        metadata={
            "notes": (
                "Source-backed declaration of the human endocardial tree wrapper. "
                "The generator writes VTK outputs relative to the staged case cwd."
            ),
            "input_overrides": dict(input_overrides or {}),
            "active_input_paths": HUMAN_TREE_INPUT_PATHS,
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
                        "depends_on": [],
                        "consumes": [
                            "system/setCardiacAnatomyDict",
                            "0/uvc_longitudinal",
                            "0/uvc_intraventricular",
                        ],
                    },
                    {
                        "id": "purkinje_tree",
                        "command": "generatePurkinjeTree",
                        "args": ["-case", "."],
                        "depends_on": ["conductivity", "anatomy"],
                        "consumes": [
                            "system/generatePurkinjeTreeDict",
                            "system/uvcConventionDict",
                            "0/uvc_transmural",
                            "0/uvc_intraventricular",
                            "0/uvc_longitudinal",
                        ],
                    },
                ],
            },
        },
    )


def _apply_pig_morphometric_tree_case(
    case_root: Path,
    case: CaseConfig,
    *,
    input_overrides: Mapping[str, Any] | None,
) -> None:
    requested = dict(input_overrides or {})
    unsupported = sorted(set(requested).difference(PIG_MORPHOMETRIC_TREE_INPUT_PATHS))
    if unsupported:
        raise ValueError(
            "The pig morphometric-tree workflow keeps the observed tree dictionary "
            "fixed until its complete seed/growth validation contract is added: "
            + ", ".join(unsupported)
        )
    _apply_case(case_root, case, input_overrides=requested)


def make_pig_morphometric_tree_spec(
    *,
    cases_root: Path | None = None,
    case_dir_name: str = "bivCase",
    setup_dir_name: str | None = None,
    output_dir_name: str | Path | None = ".",
    input_overrides: Mapping[str, Any] | None = None,
) -> TutorialSpec:
    """Declare the native pig weighted-field/transmural-tree wrapper.

    Unlike the human endocardial branch, this case first produces pig
    morphometry weight fields.  The LV tree consumes those fields through
    ``terminalSelectionModel weightedField`` and extends terminals
    transmurally; the tree settings remain an observed fixed contract.
    """

    case_root, setup_root, output_dir = resolve_spec_paths(
        cases_root=cases_root,
        case_dir_name=case_dir_name,
        setup_dir_name=setup_dir_name,
        output_dir_name=output_dir_name,
        default_output_dir_name=".",
    )
    return TutorialSpec(
        name=PIG_MORPHOMETRIC_TREE_TUTORIAL_NAME,
        case_root=case_root,
        setup_root=setup_root,
        output_dir=output_dir,
        build_cases=_single_case,
        apply_case=partial(
            _apply_pig_morphometric_tree_case, input_overrides=input_overrides
        ),
        metadata={
            "notes": (
                "Source-backed declaration of the pig morphometric explicit-tree "
                "wrapper. The generator writes VTK outputs relative to the staged "
                "case cwd. Its LV weighted-field mode consumes the preceding "
                "morphometry weight fields."
            ),
            "input_overrides": dict(input_overrides or {}),
            "active_input_paths": PIG_MORPHOMETRIC_TREE_INPUT_PATHS,
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
                        "depends_on": [],
                        "consumes": [
                            "system/setCardiacAnatomyDict",
                            "0/uvc_longitudinal",
                            "0/uvc_intraventricular",
                        ],
                    },
                    {
                        "id": "purkinje_morphometry",
                        "command": "setPurkinjeMorphometry",
                        "args": ["-case", "."],
                        "depends_on": [],
                        "consumes": [
                            "system/setPurkinjeMorphometryDict",
                            "0/uvc_longitudinal",
                            "0/uvc_intraventricular",
                        ],
                    },
                    {
                        "id": "purkinje_tree",
                        "command": "generatePurkinjeTree",
                        "args": ["-case", "."],
                        "depends_on": [
                            "conductivity",
                            "anatomy",
                            "purkinje_morphometry",
                        ],
                        "consumes": [
                            "system/generatePurkinjeTreeDict",
                            "system/uvcConventionDict",
                            "0/uvc_transmural",
                            "0/uvc_intraventricular",
                            "0/uvc_longitudinal",
                            "0/PurkinjeTerminalWeightSubendocardial",
                            "0/PurkinjeTerminalWeightIntramural",
                        ],
                    },
                ],
            },
        },
    )
