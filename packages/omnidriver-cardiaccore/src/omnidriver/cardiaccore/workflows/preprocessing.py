"""Source-backed tutorial declarations for cardiacCore workflows."""

from __future__ import annotations

from collections.abc import Mapping
from functools import partial
from pathlib import Path
from typing import Any

from omnidriver.core.runtime.models import CaseConfig, TutorialSpec
from omnidriver.core.specs.common import resolve_spec_paths

from ..operations.coordinates_convention import (
    CoordinatesConvention,
    coordinate_field_paths,
)
from ..catalogs.inputs import CATALOG
from .overrides import declared_path_template


HUMAN_PURKINJE_SLAB_TUTORIAL_NAME = "cardiaccore-human-purkinje-slab"
HUMAN_PURKINJE_ENDOCARDIAL_TUTORIAL_NAME = (
    "cardiaccore-human-purkinje-endocardial"
)
PIG_MORPHOMETRIC_PURKINJE_TUTORIAL_NAME = (
    "cardiaccore-pig-morphometric-purkinje"
)
PIG_TRANSMURAL_PURKINJE_TUTORIAL_NAME = "cardiaccore-pig-transmural-purkinje"
#: Paths the tree workflows stage. The generatePurkinjeTreeDict entries were
#: excluded until 2026-09-17 on the grounds that "tree-parameter mutation is
#: deferred until its complete seed/growth validation contract is added"; that
#: contract is now declared (catalogs/purkinje.py TREE_VALIDATION_CONTRACT),
#: and a declared value the agent cannot set is guidance it cannot act on.
PURKINJE_TREE_INPUT_PATHS = (
    "$CARDIAC_CONDUCTIVITY.df",
    "$CARDIAC_CONDUCTIVITY.ds",
    "$CARDIAC_CONDUCTIVITY.dn",
    "$CARDIAC_CONDUCTIVITY.fiberField",
    "$CARDIAC_CONDUCTIVITY.sheetField",
    "$CARDIAC_ANATOMY.zApicalMid",
    "$CARDIAC_ANATOMY.zMidBasal",
    "$CARDIAC_ANATOMY.zApexCap",
    *tuple(
        entry.driver_path
        for entry in CATALOG.entries
        if entry.driver_path.startswith("$PURKINJE_TREE.")
    ),
)

#: Conductivity field names the native utility reads when the dictionary does
#: not name others. These are the defaults `setCardiacConductivity.C` compiles
#: in, not a recommendation.
_DEFAULT_CONDUCTIVITY_FIELDS = {
    "$CARDIAC_CONDUCTIVITY.fiberField": "fiber",
    "$CARDIAC_CONDUCTIVITY.sheetField": "sheet",
}


def conductivity_field_paths(
    input_overrides: "Mapping[str, Any] | None",
) -> tuple[str, ...]:
    """The ``0/<field>`` inputs the conductivity step actually reads.

    A field name is adapter-configurable, so a DAG that names ``0/fiber``
    literally declares an input the case may not have and omits the one it
    does. Added 2026-09-22 (audit finding S3).
    """
    overrides = dict(input_overrides or {})
    return tuple(
        f"0/{overrides.get(driver_path, default)}"
        for driver_path, default in _DEFAULT_CONDUCTIVITY_FIELDS.items()
    )


def _reject_unstaged(requested: Mapping[str, Any], workflow: str) -> None:
    """Refuse a path this workflow does not stage.

    This is scheduling, not permission: the scar dictionaries are declared
    and movable, but no workflow here runs setCardiacScar, so staging a value
    into a case nothing reads would be a silent no-op. A `<ventKey>` path is
    matched through its declared template.
    """
    unstaged = sorted(
        path for path in requested
        if path not in PURKINJE_TREE_INPUT_PATHS
        and declared_path_template(path) not in PURKINJE_TREE_INPUT_PATHS
    )
    if unstaged:
        raise ValueError(
            f"The {workflow} workflow does not stage: " + ", ".join(unstaged)
            + ". Paths it stages: " + ", ".join(PURKINJE_TREE_INPUT_PATHS)
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


def make_human_purkinje_slab_spec(
    *,
    convention: CoordinatesConvention | None = None,
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
    _COORD = coordinate_field_paths(convention)


    case_root, setup_root, output_dir = resolve_spec_paths(
        cases_root=cases_root,
        case_dir_name=case_dir_name,
        setup_dir_name=setup_dir_name,
        output_dir_name=output_dir_name,
        default_output_dir_name=".",
    )
    return TutorialSpec(
        name=HUMAN_PURKINJE_SLAB_TUTORIAL_NAME,
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
                            *conductivity_field_paths(input_overrides),
                        ],
                    },
                    {
                        "id": "anatomy",
                        "command": "setCardiacAnatomy",
                        "args": ["-case", "."],
                        "depends_on": ["conductivity"],
                        "consumes": [
                            "system/setCardiacAnatomyDict",
                            _COORD["longitudinal"],
                            _COORD["intraventricular"],
                        ],
                    },
                    {
                        "id": "purkinje_slab",
                        "command": "setPurkinjeSlab",
                        "args": ["-case", "."],
                        "depends_on": ["anatomy"],
                        "consumes": [
                            "system/setPurkinjeSlabDict",
                            _COORD["transmural"],
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
                            _COORD["longitudinal"],
                            _COORD["intraventricular"],
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
    _reject_unstaged(requested, "human Purkinje endocardial")
    _apply_case(case_root, case, input_overrides=requested)


def make_human_purkinje_endocardial_spec(
    *,
    convention: CoordinatesConvention | None = None,
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
    _COORD = coordinate_field_paths(convention)


    case_root, setup_root, output_dir = resolve_spec_paths(
        cases_root=cases_root,
        case_dir_name=case_dir_name,
        setup_dir_name=setup_dir_name,
        output_dir_name=output_dir_name,
        default_output_dir_name=".",
    )
    return TutorialSpec(
        name=HUMAN_PURKINJE_ENDOCARDIAL_TUTORIAL_NAME,
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
            "active_input_paths": PURKINJE_TREE_INPUT_PATHS,
            "workflow_dag": {
                "steps": [
                    {
                        "id": "conductivity",
                        "command": "setCardiacConductivity",
                        "args": ["-case", "."],
                        "depends_on": [],
                        "consumes": [
                            "system/setCardiacConductivityDict",
                            *conductivity_field_paths(input_overrides),
                        ],
                    },
                    {
                        "id": "anatomy",
                        "command": "setCardiacAnatomy",
                        "args": ["-case", "."],
                        "depends_on": [],
                        "consumes": [
                            "system/setCardiacAnatomyDict",
                            _COORD["longitudinal"],
                            _COORD["intraventricular"],
                        ],
                    },
                    {
                        "id": "purkinje_tree",
                        "command": "generatePurkinjeTree",
                        "args": ["-case", "."],
                        "depends_on": ["conductivity", "anatomy"],
                        "consumes": [
                            "system/generatePurkinjeTreeDict",
                            "system/coordinatesConventionDict",
                            _COORD["transmural"],
                            _COORD["intraventricular"],
                            _COORD["longitudinal"],
                        ],
                    },
                ],
            },
        },
    )


def _apply_pig_purkinje_case(
    case_root: Path,
    case: CaseConfig,
    *,
    input_overrides: Mapping[str, Any] | None,
) -> None:
    requested = dict(input_overrides or {})
    _reject_unstaged(requested, "pig Purkinje")
    _apply_case(case_root, case, input_overrides=requested)


def _make_pig_purkinje_spec(
    *,
    convention: CoordinatesConvention | None = None,
    tutorial_name: str,
    weighted_lv: bool,
    cases_root: Path | None = None,
    case_dir_name: str = "bivCase",
    setup_dir_name: str | None = None,
    output_dir_name: str | Path | None = ".",
    input_overrides: Mapping[str, Any] | None = None,
) -> TutorialSpec:
    _COORD = coordinate_field_paths(convention)

    case_root, setup_root, output_dir = resolve_spec_paths(
        cases_root=cases_root,
        case_dir_name=case_dir_name,
        setup_dir_name=setup_dir_name,
        output_dir_name=output_dir_name,
        default_output_dir_name=".",
    )
    tree_consumes = [
        "system/generatePurkinjeTreeDict",
        "system/coordinatesConventionDict",
        _COORD["transmural"],
        _COORD["intraventricular"],
        _COORD["longitudinal"],
    ]
    if weighted_lv:
        tree_consumes.extend(
            [
                "0/PurkinjeTerminalWeightSubendocardial",
                "0/PurkinjeTerminalWeightIntramural",
            ]
        )
    selection_note = (
        "The LV weightedField selector consumes the two morphometry weight fields."
        if weighted_lv
        else "The LV allLeaves selector does not consume morphometry weight fields."
    )
    return TutorialSpec(
        name=tutorial_name,
        case_root=case_root,
        setup_root=setup_root,
        output_dir=output_dir,
        build_cases=_single_case,
        apply_case=partial(
            _apply_pig_purkinje_case, input_overrides=input_overrides
        ),
        metadata={
            "notes": (
                "Source-backed pig Purkinje tree declaration with transmural "
                f"terminal extension. {selection_note}"
            ),
            "input_overrides": dict(input_overrides or {}),
            "active_input_paths": PURKINJE_TREE_INPUT_PATHS,
            "workflow_dag": {
                "steps": [
                    {
                        "id": "conductivity",
                        "command": "setCardiacConductivity",
                        "args": ["-case", "."],
                        "depends_on": [],
                        "consumes": [
                            "system/setCardiacConductivityDict",
                            *conductivity_field_paths(input_overrides),
                        ],
                    },
                    {
                        "id": "anatomy",
                        "command": "setCardiacAnatomy",
                        "args": ["-case", "."],
                        "depends_on": [],
                        "consumes": [
                            "system/setCardiacAnatomyDict",
                            _COORD["longitudinal"],
                            _COORD["intraventricular"],
                        ],
                    },
                    {
                        "id": "purkinje_morphometry",
                        "command": "setPurkinjeMorphometry",
                        "args": ["-case", "."],
                        "depends_on": [],
                        "consumes": [
                            "system/setPurkinjeMorphometryDict",
                            _COORD["longitudinal"],
                            _COORD["intraventricular"],
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
                        "consumes": tree_consumes,
                    },
                ],
            },
        },
    )


def make_pig_morphometric_purkinje_spec(
    *,
    convention: CoordinatesConvention | None = None,
    cases_root: Path | None = None,
    case_dir_name: str = "bivCase",
    setup_dir_name: str | None = None,
    output_dir_name: str | Path | None = ".",
    input_overrides: Mapping[str, Any] | None = None,
) -> TutorialSpec:
    """Declare the pig tree with weighted LV terminal selection."""

    return _make_pig_purkinje_spec(
        tutorial_name=PIG_MORPHOMETRIC_PURKINJE_TUTORIAL_NAME,
        weighted_lv=True,
        convention=convention,
        cases_root=cases_root,
        case_dir_name=case_dir_name,
        setup_dir_name=setup_dir_name,
        output_dir_name=output_dir_name,
        input_overrides=input_overrides,
    )


def make_pig_transmural_purkinje_spec(
    *,
    convention: CoordinatesConvention | None = None,
    cases_root: Path | None = None,
    case_dir_name: str = "bivCase",
    setup_dir_name: str | None = None,
    output_dir_name: str | Path | None = ".",
    input_overrides: Mapping[str, Any] | None = None,
) -> TutorialSpec:
    """Declare the pig tree with all-leaves LV terminal selection."""

    return _make_pig_purkinje_spec(
        tutorial_name=PIG_TRANSMURAL_PURKINJE_TUTORIAL_NAME,
        weighted_lv=False,
        convention=convention,
        cases_root=cases_root,
        case_dir_name=case_dir_name,
        setup_dir_name=setup_dir_name,
        output_dir_name=output_dir_name,
        input_overrides=input_overrides,
    )
