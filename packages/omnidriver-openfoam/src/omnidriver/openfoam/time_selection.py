"""OpenFOAM restart-time selection for adapter-owned provenance."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from omnidriver.core.tutorial_records import TutorialRecordError


class TimeSelectionError(TutorialRecordError):
    """``controlDict``'s ``startFrom``/``startTime`` cannot be resolved to a
    single time directory: ``startFrom`` names a value real OpenFOAM does not
    recognise, or is ``startTime`` with no ``startTime`` entry set. Both are
    a ``FatalIOError`` in ``Foam::Time::setControls`` (OpenFOAM v2412,
    ``src/OpenFOAM/db/Time/Time.C``) -- refused here by name rather than
    silently answered.

    Subclasses :class:`TutorialRecordError` (the house pattern --
    ``physics_layout.PhysicsLayoutError`` does the same) so this reaches the
    CLI's existing ``except TutorialRecordError`` handling around
    ``strict_plan`` the same way any other named refusal does, when it is
    hit during planning. **It can also surface later, mid-run**, because
    ``get_input_roots`` (this function's only caller) is read by
    ``core.runtime.provenance_inputs.enumerate_case_inputs``, which runs from
    ``core.runtime.resume`` during an actual step's checkpoint/resume
    validation -- not from ``strict_plan``. There, ``cli._execute_run``'s
    ``except Exception`` around ``run_workflow`` (and the same pattern in
    ``_execute_step``) already turns any exception into a clean JSON
    ``{"status": "failed", ..., "error": str(exc)}`` payload rather than a
    traceback, so this still reaches the caller as a named, readable
    refusal even though no ``except TutorialRecordError`` names it
    specifically at that call site.
    """


def selected_start_time(
    case_root: Path,
    *,
    control_dict_relpath: str,
    read_value: Callable[[Path, str], str | None],
    instance_directory_pattern: str,
) -> str | None:
    """Resolve OpenFOAM's ``startFrom``/``startTime`` to one time directory,
    exactly as ``Foam::Time::setControls`` does (OpenFOAM v2412,
    ``src/OpenFOAM/db/Time/Time.C``).

    Returns ``None`` when ``control_dict_relpath`` names no file at all --
    the owner's rule (2026-09-26, verbatim): "``controlDict`` is how we know
    an OpenFOAM case exists; that is what we use. The rule is mandatory and
    the same for every case, with no exceptions." A case with no
    ``controlDict`` is not a malformed OpenFOAM case to refuse -- it may not
    be OpenFOAM-shaped at all. cardiacCore has no time concept of its own: it
    always writes to ``0/``, and every one of its cases sets ``startFrom
    startTime; startTime 0;`` explicitly, so this function never invents
    time semantics for one of its (rare, deliberately non-OpenFOAM,
    ``Allrun``-only) cases either -- ``None`` here is what lets
    ``OpenFOAMEnvironmentPlugin.get_input_roots`` answer ``()``, no start
    folder and no replica start folders at all, instead of inventing the
    literal string ``"0"`` for a case whose start time is not this hook's to
    know.

    **Corrected 2026-09-26 (owner decision, superseding the M5 revert noted
    below).** Two more bugs, found by reading ``setControls`` itself rather
    than guessing:

    - ``startFrom`` absent used to default here to ``"startTime"``.
      ``setControls`` reads it with ``controlDict_.getOrDefault<word>
      ("startFrom", "latestTime")`` -- the comment directly above that call
      says so too: "default is to resume calculation from 'latestTime'".
    - ``startFrom startTime`` with no ``startTime`` entry, and any
      ``startFrom`` other than ``startTime``/``firstTime``/``latestTime``,
      both used to fall through to the silent ``"0"`` default answered when
      time directories are absent. Real OpenFOAM raises ``FatalIOError`` for
      both instead: ``controlDict_.readEntry("startTime", startTime_)`` for
      the first, the explicit ``else`` branch's
      ``FatalIOErrorInFunction(controlDict_) << "expected startTime,
      firstTime or latestTime"`` for the second. Both are now
      :class:`TimeSelectionError`, refused by name, never silently answered.

    ``firstTime``/``latestTime`` with no time directories present still
    answers ``"0"`` -- not a fallback, but ``Time``'s own constructor
    default: every ``Time`` constructor initialises ``startTime_(0)``, and
    when ``findTimes`` returns nothing, ``setControls``'s ``if (nTimes)``
    guards around both the ``firstTime`` and ``latestTime`` branches never
    assign ``startTime_``, so it simply keeps the value the constructor gave
    it. This is OpenFOAM's real behaviour, not this function inventing one.

    ``instance_directory_pattern`` is the stack's merged
    ``CaseRuntimeConventions.instance_directory_pattern`` -- the same regex
    staging, discovery and snapshots use to recognise a time/instance
    directory. **Corrected 2026-09-26 (final review M5):** this used to
    decide "is this a candidate time directory" with a bare ``float(name)``,
    a second, independent rule that disagreed with the conventions regex on
    names like ``inf``, ``nan``, ``1_0``, ``+1``, ``.5`` or ``1E-05``
    (regex: not an instance; ``float()``: parses, so ``latestTime`` could
    pick ``inf``). The time-directory rule is now stated once, here, by
    reading the same value staging/discovery already read instead of
    re-deriving it. This regex also never matches ``constant``, so it
    already excludes it the way ``setControls``'s explicit ``findTimes``
    handling (skipping ``constant``, and ``firstTime``'s own
    ``timeDirs.front().name() == constant()`` check) does -- nothing extra
    is needed here to reproduce that skip.

    **M5's other half -- refusing a missing ``controlDict`` outright instead
    of answering the silent default ``"0"`` -- was attempted and reverted
    the same day.** It broke a real, pre-existing capability:
    `omnidriver-cardiaccore`'s `test_controlled_allrun_executes_without_
    domain_claims` runs `omnidriver run --strict` against a case that is
    deliberately NOT OpenFOAM-shaped (an `Allrun`-only folder, no
    `controlDict` at all) through the composed
    `OpenFOAMEnvironmentPlugin`+`CardiacCorePlugin` stack, and it must keep
    succeeding -- that is the test's whole point ("without domain claims").
    The owner's 2026-09-26 rule above settles it: this case is answered
    ``None``, not refused and not ``"0"`` -- a third option this function did
    not have before, because until ``get_input_roots`` learned to treat
    ``None`` as "contribute nothing", "refuse" and "answer 0" were the only
    two shapes available.
    """
    control_dict = case_root / control_dict_relpath
    if not control_dict.is_file():
        return None

    start_from = (read_value(control_dict, "startFrom") or "latestTime").strip()
    if start_from == "startTime":
        value = read_value(control_dict, "startTime")
        if value is None:
            raise TimeSelectionError(
                f"{control_dict}: startFrom is 'startTime' but no startTime "
                "entry is set -- OpenFOAM's Foam::Time::setControls reads it "
                'with controlDict_.readEntry("startTime", startTime_), a '
                "FatalIOError when the key is absent"
            )
        return value.strip()

    if start_from not in {"firstTime", "latestTime"}:
        raise TimeSelectionError(
            f"{control_dict}: startFrom must be 'startTime', 'firstTime' or "
            f"'latestTime', found {start_from!r} -- OpenFOAM's "
            'Foam::Time::setControls: "expected startTime, firstTime or '
            'latestTime"'
        )

    pattern = re.compile(instance_directory_pattern)
    candidates: list[str] = []
    try:
        children = case_root.iterdir()
    except OSError:
        children = ()
    for child in children:
        if not child.is_dir():
            continue
        if not pattern.fullmatch(child.name):
            continue
        candidates.append(child.name)
    if not candidates:
        return "0"
    selector = max if start_from == "latestTime" else min
    return selector(candidates, key=float)
