"""How a record is exercised briefly against the real solver: the data a
record declares (``TutorialRecord.conformance``) for ``omnidriver check``. It
imports nothing of the checks, so a plugin's records can carry it for free."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping


@dataclass(frozen=True, kw_only=True)
class QuantityTarget:
    """A quantity a record's run yields, and what C13 and C14 compare.

    ``study`` overlays the target's ``base_study`` for those runs, so the
    quantity occurs (an end time past the slowest activation). ``at`` is where
    each named quantity is sampled, or expected, in ``at_unit``, in the
    solver's own frame; ``pairs`` names, for each label of the point
    ``reference``, the quantity that answers it. A relative ``reference`` is a
    benchmark under the directory :meth:`resolved` is given; without ``at`` and
    ``pairs``, each of its points that has coordinates is a quantity of the
    same name, at those coordinates. The tolerances are the
    solver's own physics: ``parallel_tolerance`` bounds, in the reader's unit,
    how far a parallel run may sit from the serial one; ``tolerance`` is the
    declared bound of C14's comparison, in ``tolerance_unit``.
    ``parallel_study`` adds what a parallel run needs beyond ``parallel: ranks``.
    """

    artifact_format: str
    reference: Path
    at_unit: str | None
    max_sampling_offset: float
    study: Mapping[str, Any]
    sweep_values: tuple[Any, Any]
    tolerance: float
    tolerance_unit: str
    parallel_tolerance: float
    parallel_study: Mapping[str, Any] = field(default_factory=dict)
    ranks: int = 2
    both_not_reached: str = "agree"
    pairs: Mapping[str, str] | None = None
    at: Mapping[str, tuple[float, float, float]] | None = None

    def resolved(self, benchmarks: Path | None) -> "QuantityTarget":
        """This target with its reference found under ``benchmarks`` and its
        ``at`` and ``pairs`` filled in from that reference where undeclared."""
        from dataclasses import replace

        from omnidriver.core.quantities import load_point_reference

        reference = self.reference
        if not reference.is_absolute():
            if benchmarks is None:
                raise FileNotFoundError(
                    f"the quantity compares against benchmark {reference}, which needs --benchmarks <directory>"
                )
            reference = Path(benchmarks) / reference
        points = load_point_reference(reference)
        at = self.at if self.at is not None else {
            label: point.coordinates for label, point in points.points.items() if point.coordinates is not None
        }
        return replace(
            self, reference=reference, at=at, pairs=self.pairs if self.pairs is not None else {label: label for label in at},
            at_unit=self.at_unit or points.length_unit,
        )


@dataclass(frozen=True, kw_only=True)
class ConformanceStudy:
    """How a record is exercised briefly, declared by the record itself.

    ``requires`` are the commands its pipeline runs, on ``PATH`` from the
    solver's own shell. ``base_study`` pins values (e.g. mesh resolution, time
    step) that keep a real run short. A ``patch`` is a catalogued key the
    native case sets to something else, ``untouched`` a sibling it must leave
    alone, ``sweep_name`` and ``sweep_values`` what C7 varies, and
    ``unknown_name`` a typo of a real key. ``timeout_s`` bounds each child
    process a check starts (C6's run, C7's sweep-run) and each sweep case
    (``sweep-run --case-timeout-s``): a child that outlives it is a failed
    verdict naming the timeout. ``quantity``, when declared, is what C13 and
    C14 compare; without it they have nothing to compare and pass saying so.
    ``probes`` name what the record's solver can say about its own catalogues
    that no static scan can: each is given the stack's execution environment
    and returns whether the catalogue matches the built solver, and what it saw. They run beside the checks and report in
    the same way.
    """

    base_study: Mapping[str, Any]
    patch: tuple[str, Any]
    untouched: tuple[str, tuple[str, ...]]
    sweep_name: str
    sweep_values: tuple[Any, Any]
    unknown_name: str
    requires: tuple[str, ...] = ()
    timeout_s: float = 600.0
    quantity: QuantityTarget | None = None
    probes: Mapping[str, Callable[[Mapping[str, str]], tuple[bool, str]]] = field(default_factory=dict)
