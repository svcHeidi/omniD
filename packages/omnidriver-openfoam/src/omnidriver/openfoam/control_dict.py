"""``system/controlDict`` as every OpenFOAM-based solver reads it, through ``Foam::Time``.

The catalogue lists the keys ``Foam::Time`` reads; any other key of the dictionary is written as asked.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Final

from omnidriver.core.contracts.dictionary import DictEntry
from omnidriver.core.planning_types import StrictDiagnostic, diagnostic

from .case_rules import read_leaves, rule_diagnostics
from .record_key_validation import CataloguedDocument, listed_entry

CONTROL_DICT_DOCUMENT: Final = "system/controlDict"
_SOURCE = ("src/OpenFOAM/db/Time/TimeIO.C",)

CONTROL_DICT_ENTRIES: Final[tuple[DictEntry, ...]] = (
    DictEntry(
        driver_path="deltaT",
        phases=frozenset({"solver"}),
        description=(
            "Simulation time step. Sweep it alongside mesh refinement to measure "
            "temporal order; use a large value for a smoke-test run that verifies "
            "setup before a fine-resolution sweep."
        ),
        source_refs=_SOURCE,
        value_kind="scalar",
        exclusive_minimum=0,
        unit="s",
        required=True,
        typical_value="",
    ),
    DictEntry(
        driver_path="endTime",
        phases=frozenset({"solver"}),
        description=(
            "Simulation end time. Set a small value (e.g. 1e-3) for a "
            "smoke-test run that launches and takes at least one step, before "
            "a full-length run."
        ),
        source_refs=_SOURCE,
        value_kind="scalar",
        unit="s",
        required_when={"stopAt": "endTime"},
        typical_value="",
    ),
    DictEntry(
        driver_path="startTime",
        phases=frozenset({"solver"}),
        description="Simulation start time. Almost always 0 for new runs.",
        source_refs=_SOURCE,
        value_kind="scalar",
        unit="s",
        required_when={"startFrom": "startTime"},
        typical_value="0",
    ),
    DictEntry(
        driver_path="startFrom",
        phases=frozenset({"solver"}),
        description=(
            "Which time directory to start from. "
            "startTime uses the value of startTime; "
            "latestTime restarts from the last written time directory."
        ),
        source_refs=_SOURCE,
        value_kind="enum",
        enum_values=("startTime", "firstTime", "latestTime"),
        default="latestTime",
        typical_value="startTime",
    ),
    DictEntry(
        driver_path="stopAt",
        phases=frozenset({"solver"}),
        description="Condition that halts the run.",
        source_refs=_SOURCE,
        value_kind="enum",
        enum_values=("endTime", "writeNow", "noWriteNow", "nextWrite"),
        typical_value="endTime",
    ),
    DictEntry(
        driver_path="writeControl",
        phases=frozenset({"solver"}),
        description=(
            "Trigger for writing output to disk. "
            "runTime writes every writeInterval seconds of simulation time; "
            "timeStep writes every writeInterval time steps."
        ),
        source_refs=_SOURCE,
        notes=(
            "enum_values matches Foam::Time::writeControlNames (OpenFOAM "
            "v2412 src/OpenFOAM/db/Time/Time.C): all seven names, including "
            "adjustableRunTime, which the native bathBidomain case uses."
        ),
        value_kind="enum",
        enum_values=(
            "none", "timeStep", "runTime", "adjustable", "adjustableRunTime",
            "clockTime", "cpuTime",
        ),
        typical_value="runTime",
    ),
    DictEntry(
        driver_path="writeInterval",
        phases=frozenset({"solver"}),
        description=(
            "Output writing frequency in units of writeControl. "
            "When writeControl=runTime this is seconds of simulation time."
        ),
        source_refs=_SOURCE,
        value_kind="scalar",
        unit="s (when writeControl=runTime)",
        required_one_of=("writeFrequency",),
        typical_value="5e-3",
    ),
    DictEntry(
        driver_path="writeFrequency",
        phases=frozenset({"solver"}),
        description="Older name of writeInterval, read when writeInterval is absent.",
        source_refs=_SOURCE,
        value_kind="scalar",
        unit="s (when writeControl=runTime)",
        required_one_of=("writeInterval",),
    ),
    DictEntry(
        driver_path="writeFormat",
        phases=frozenset({"solver"}),
        description="Binary or ASCII output format. ASCII is human-readable; binary is faster and smaller.",
        source_refs=_SOURCE,
        value_kind="enum",
        enum_values=("ascii", "binary"),
        typical_value="ascii",
    ),
    DictEntry(
        driver_path="purgeWrite",
        phases=frozenset({"solver"}),
        description=(
            "Number of output time directories to keep on disk (0 = keep all). "
            "Use 2-3 when disk space is limited on long convergence sweeps."
        ),
        source_refs=_SOURCE,
        value_kind="integer",
        typical_value="0",
    ),
)


CONTROL_DICT_ENTRIES_BY_PATH: Final = {entry.driver_path: entry for entry in CONTROL_DICT_ENTRIES}


def control_dict_document() -> CataloguedDocument:
    """The ``record_key_validator`` document: the catalogued keys by kind and bounds, any other key unvalidated."""
    return CataloguedDocument(
        label="controlDict", entries=CONTROL_DICT_ENTRIES_BY_PATH.values,
        match=lambda key_path: (
            (entry, {}) if (entry := CONTROL_DICT_ENTRIES_BY_PATH.get(".".join(key_path))) is not None else None
        ),
        scan=lambda key_path: key_path, open=True,
    )


def control_dict_listing(case_root: Any) -> tuple[dict[str, Any], ...]:
    """The catalogued keys a study may set in the case's ``controlDict``; none when the case has no such file."""
    if not (case_root / CONTROL_DICT_DOCUMENT).is_file():
        return ()
    return tuple(listed_entry(CONTROL_DICT_DOCUMENT, path, entry) for path, entry in CONTROL_DICT_ENTRIES_BY_PATH.items())


def control_dict_diagnostics(case_root: Path) -> tuple[StrictDiagnostic, ...]:
    """The catalogue's rules over the resolved case's ``controlDict``: what ``Foam::Time`` requires, its menus and bounds."""
    path = Path(case_root) / CONTROL_DICT_DOCUMENT
    if not path.is_file():
        return ()
    try:
        leaves = read_leaves(path)
    except (OSError, ValueError, KeyError) as exc:
        return (diagnostic("error", "case_unreadable", f"{path} cannot be read: {exc}", source=CONTROL_DICT_DOCUMENT),)
    return tuple(rule_diagnostics(CONTROL_DICT_ENTRIES, leaves, document=CONTROL_DICT_DOCUMENT))
