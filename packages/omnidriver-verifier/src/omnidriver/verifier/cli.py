"""``omnidriver-verify``: the problem library and its deterministic checks, as JSON."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

from omnidriver.core.refusal import Refusal, RefusingParser, print_refusal

from .problem import ProblemError, load_problem, problem_ids


def _parser() -> RefusingParser:
    parser = RefusingParser(prog="omnidriver-verify", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True, parser_class=RefusingParser)
    commands.add_parser("problems", help="list each problem: id, title, dimensions, mesh progression")
    for name, help_text in (
        ("show", "print a problem's definition"),
        ("residual", "substitute a problem's exact fields into its equations (needs the symbolic extra)"),
    ):
        commands.add_parser(name, help=help_text).add_argument("problem_id")
    compare = commands.add_parser("compare", help="table each solver's errors per level, with observed and stated orders")
    compare.add_argument("problem_id")
    compare.add_argument("--results", nargs="+", required=True, type=Path,
                         help="one JSON per solver: solver, problem, mesh, stated, levels")
    compare.add_argument("--temporal", action="store_true",
                         help="table the problem's temporal ladder instead: one JSON per solver configuration and "
                              "reference (solver, problem, configuration, reference, stated, levels), orders in dt")
    return parser


def _answer(args: Any) -> dict[str, Any]:
    if args.command == "problems":
        listed = []
        for problem_id in problem_ids():
            problem = load_problem(problem_id)
            listed.append({key: problem[key] for key in ("id", "title", "dimensions", "mesh_progression")})
        return {"status": "ok", "problems": listed}
    problem = load_problem(args.problem_id)
    if args.command == "show":
        return {"status": "ok", "problem": problem}
    if args.command == "compare":
        from .convergence import comparison_table, temporal_table

        table = temporal_table if args.temporal else comparison_table
        return table(problem, [_results(path) for path in args.results])
    from .residual import residual_verdict

    return residual_verdict(problem)


def _results(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise ProblemError(f"{path}: not a readable results JSON ({exc})", code="results_invalid") from None


def main(argv: Sequence[str] | None = None) -> int:
    """Run one ``omnidriver-verify`` command; every answer, and every refusal, is JSON on stdout. Exit 1 on a
    refusal or a failed check."""
    try:
        answer = _answer(_parser().parse_args(argv))
    except Refusal as refusal:
        return print_refusal(refusal)
    print(json.dumps(answer, indent=2))
    return 0 if answer["status"] in ("ok", "passed") else 1
