#!/usr/bin/env python3
"""Tables for the oblique-wall study, from the sweeps under ``runs/oblique``.

    python oblique_summarize.py [--runs runs/oblique]

Reads, and writes nothing, every sweep ``campaign.sh oblique`` wrote
(``<scheme>/<variant>/dx<mm>[_dt<ms>]``). A level that has not run, or a case
that cannot be read, is reported and the rest is still summarised. It prints:
- per run: the probes P1-P9, the diagonal line's end, the last cell to
  activate, whether every cell activated, the written wall patch type, the
  written configuration against the one the study asked for, ranks and solve time;
- the activation-time field differences A-0, AB-0 and AB-A: maximum, mean,
  where the maximum is and whether it is at the end of the activation;
- P8 against dx and dt per scheme and variant, with observed orders where three
  levels exist;
- the AB-0 gap against refinement, and Godunov against SBDF2.

Activation times are written in seconds with ``-1`` for a cell or probe that
never activated; the sentinel is never converted to milliseconds.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from summarize import sweeps  # noqa: E402

SCHEMES = ("godunov", "sbdf2")
VARIANTS = ("0", "A", "AB")
DX_MM = (0.5, 0.2, 0.1)
DT_MS = (0.05, 0.01, 0.005)
PAIRS = (("0", "AB"), ("0", "A"), ("A", "AB"))  # (reference, other); the key pair first
#: The written Vm wall patch type each sealedWallTrace asks for.
WALL_TYPE = {"zeroGradient": "zeroGradient", "conormal": "conormalZeroFlux"}
STUDY = "constant/electroProperties:monodomainSolverCoeffs."
DDT_KEY = "system/fvSchemes:ddtSchemes.default"
#: A gap that moves less than this fraction of its coarsest value across the levels "stays".
STAYS = 0.05
PROBES = "postProcessing/Niedererpoints/0/activationTime"
LINE = "postProcessing/Niedererlines/0/activationTime"
_TRUE, _FALSE = {"true", "yes", "on", "1"}, {"false", "no", "off", "0", "none"}


def _uncommented(text: str) -> str:
    return "\n".join(re.sub(r"//.*", "", line) for line in text.splitlines())


def _word(text: str, key: str) -> str | None:
    found = re.search(rf"^\s*{re.escape(key)}\s+([^\s;]+)\s*;", _uncommented(text), re.M)
    return found.group(1) if found else None


def _internal_field(path: Path, size: int) -> np.ndarray:
    text = path.read_text()
    uniform = re.search(r"internalField\s+uniform\s+([^\s;]+)\s*;", text)
    if uniform:
        return np.full(size, float(uniform.group(1)))
    found = re.search(r"internalField\s+nonuniform\s+List<scalar>\s*(\d+)\s*\(", text)
    if not found:
        raise ValueError(f"{path}: internalField is neither uniform nor an ascii scalar list")
    start = found.end()
    values = np.array(text[start:text.index(")", start)].split(), dtype=float)
    if values.size != int(found.group(1)):
        raise ValueError(f"{path}: the list states {found.group(1)} values and holds {values.size}")
    return values


def _last_row(path: Path) -> np.ndarray:
    rows = [line.split() for line in path.read_text().splitlines() if line.strip() and not line.startswith("#")]
    return np.array(rows[-1][1:], dtype=float)


def _ms(seconds: np.ndarray) -> np.ndarray:
    return np.where(seconds < 0, np.nan, seconds * 1e3)


def _latest_time(case: Path) -> Path:
    times = [p for p in case.iterdir() if p.is_dir() and re.fullmatch(r"[0-9.e+-]+", p.name) and p.name != "0"]
    if not times:
        raise ValueError(f"{case}: no time directory")
    return max(times, key=lambda p: float(p.name))


def _truth(word: str | None) -> bool | None:
    return True if word in _TRUE else False if word in _FALSE else None


def _written_problems(case: Path, base: dict, wall_types: list[str]) -> list[str]:
    """What the case's written files say against the study's own ``base`` keys."""
    electro = (case / "constant/electroProperties").read_text()
    ddt = re.search(r"ddtSchemes\s*\{\s*default\s+([^\s;]+)\s*;", _uncommented((case / "system/fvSchemes").read_text()))
    problems = []
    asked_seal = base.get(STUDY + "sealedHeartBoundary")
    if asked_seal is not None and _truth(_word(electro, "sealedHeartBoundary")) is not asked_seal:
        problems.append(f"sealedHeartBoundary written {_word(electro, 'sealedHeartBoundary')}, asked {asked_seal}")
    for key in ("sealedWallTrace", "timeCouplingScheme"):
        if STUDY + key in base and _word(electro, key) != base[STUDY + key]:
            problems.append(f"{key} written {_word(electro, key)}, asked {base[STUDY + key]}")
    if DDT_KEY in base and (ddt.group(1) if ddt else None) != base[DDT_KEY]:
        problems.append(f"ddtSchemes default written {ddt.group(1) if ddt else None}, asked {base[DDT_KEY]}")
    asked_cond = base.get(STUDY + "conductivity", {}).get("value")
    written_cond = re.search(r"conductivity\s+\[[^\]]*\]\s*\(([^)]*)\)", electro)
    if asked_cond is not None and (
        written_cond is None or not np.allclose([float(x) for x in written_cond.group(1).split()], asked_cond, rtol=0, atol=1e-12)
    ):
        problems.append("conductivity written differs from the study's")
    asked_trace = base.get(STUDY + "sealedWallTrace")
    if asked_trace in WALL_TYPE and wall_types != [WALL_TYPE[asked_trace]]:
        problems.append(f"Vm wall patch types {wall_types}, expected {WALL_TYPE[asked_trace]}")
    return problems


def read_case(case: Path, base: dict, dx_mm: float) -> dict:
    """One case's outputs. Raises OSError or ValueError when a file is missing or unreadable."""
    blocks = re.search(r"hex\s*\([^)]*\)\s*\((\d+)\s+(\d+)\s+(\d+)\)", (case / "system/blockMeshDict").read_text())
    if blocks is None:
        raise ValueError(f"{case}: no hex block with cell counts in system/blockMeshDict")
    n = tuple(int(x) for x in blocks.groups())
    latest = _latest_time(case)
    field = _internal_field(latest / "activationTime", n[0] * n[1] * n[2])
    vm = (latest / "Vm").read_text()
    wall_types = sorted(set(re.findall(r"type\s+(\w+)\s*;", vm[vm.index("boundaryField"):])))
    activated = field[field >= 0]
    last = int(field.argmax())
    probes, line = _ms(_last_row(case / PROBES)), _ms(_last_row(case / LINE))
    return {
        "n": n, "dx_mm": dx_mm, "field_ms": _ms(field),
        "probes": probes, "line_end": float(line[-1]),
        "not_activated": int(field.size - activated.size),
        "last_ms": float(field.max() * 1e3), "last_at": _centre(last, n, dx_mm),
        "wall_types": wall_types, "problems": _written_problems(case, base, wall_types),
    }


def _centre(index: int, n: tuple[int, int, int], dx_mm: float) -> tuple[float, float, float]:
    # blockMesh numbers a single block's cells i + nx (j + ny k)
    i, j, k = index % n[0], (index // n[0]) % n[1], index // (n[0] * n[1])
    return tuple(round((q + 0.5) * dx_mm, 6) for q in (i, j, k))


def collect(runs: Path) -> tuple[dict, list[str]]:
    """``{(scheme, variant): {(dx_mm, dt_ms): case}}`` and one message per case that cannot be read."""
    cases: dict = {}
    errors = []
    bases = {}
    for manifest in runs.rglob("sweep_manifest.json"):
        bases[manifest.parent.resolve()] = json.loads(manifest.read_text()).get("base_study", {})
    for (output, case_id), row in sweeps(runs).items():
        where = Path(row["sweep"]).parts
        label = f"{'/'.join(where)}/{case_id}"
        if len(where) < 3 or where[0] not in SCHEMES or where[1] not in VARIANTS:
            errors.append(f"{label}: not under <scheme>/<variant>/dx<mm>")
            continue
        try:
            dx_mm = round(float(row["values"]["dx"]) * 1e3, 6)
            dt_ms = round(float(row["values"]["system/controlDict:deltaT"]) * 1e3, 6)
        except (KeyError, TypeError, ValueError):
            errors.append(f"{label}: the sweep states no dx and deltaT for it")
            continue
        end_ms = row["values"].get("system/controlDict:endTime")
        entry = {"status": row["status"], "ranks": row["ranks"], "solve": row["solve"], "case": output / "cases" / case_id,
                 "end_ms": None if end_ms is None else float(end_ms) * 1e3}
        try:
            entry |= read_case(entry["case"], bases[output], dx_mm)
        except (OSError, ValueError, KeyError, IndexError) as exc:
            errors.append(f"{label} (dx {dx_mm} dt {dt_ms}, {row['status']}): not readable: {exc}")
            continue
        cases.setdefault((where[0], where[1]), {})[(dx_mm, dt_ms)] = entry
    return cases, errors


def _f(value, digits: int = 3, sign: bool = False) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "—"
    return f"{value:+.{digits}f}" if sign else f"{value:.{digits}f}"


def difference(first: dict, second: dict) -> dict:
    """``second - first`` over the cells both activated, and where its maximum lies."""
    a, b = first["field_ms"], second["field_ms"]
    both = ~np.isnan(a) & ~np.isnan(b)
    d = np.where(both, b - a, np.nan)
    at = int(np.nanargmax(d))
    order = np.argsort(np.where(np.isnan(a), np.inf, a))
    rank = np.empty(a.size)
    rank[order] = np.arange(a.size)
    activated = int((~np.isnan(a)).sum())
    spearman = float(np.corrcoef(rank[both], np.argsort(np.argsort(d[both])))[0, 1])
    p8 = second["probes"][7] - first["probes"][7]
    return {
        "p8": float(p8), "max": float(d[at]), "min": float(np.nanmin(d)), "mean": float(np.nanmean(d)),
        "mean_abs": float(np.nanmean(np.abs(d))), "at": _centre(at, first["n"], first["dx_mm"]),
        "t_ref": float(a[at]), "percentile": float(100 * rank[at] / max(activated - 1, 1)),
        "at_last_cell": at == int(np.nanargmax(b)), "spearman": spearman,
        "last": second["last_ms"] - first["last_ms"], "excluded": int((~both).sum()),
        "d": d, "a": a,
    }


def observed_order(h: tuple[float, ...], f: tuple[float, ...]) -> float | None:
    """The p for which (f1-f2)/(f2-f3) = (h1^p-h2^p)/(h2^p-h3^p), by bisection; None when the three do not converge monotonically."""
    (h1, h2, h3), (f1, f2, f3) = h, f
    if any(np.isnan(x) for x in f) or f2 == f3 or (f1 - f2) / (f2 - f3) <= 0:
        return None
    ratio = (f1 - f2) / (f2 - f3)

    def gap(p: float) -> float:
        return (h1**p - h2**p) / (h2**p - h3**p) - ratio

    low, high = 0.05, 8.0
    if gap(low) * gap(high) > 0:
        return None
    for _ in range(200):
        mid = 0.5 * (low + high)
        low, high = (low, mid) if gap(low) * gap(mid) <= 0 else (mid, high)
    return 0.5 * (low + high)


def _trend(values: list[float | None]) -> str:
    known = [v for v in values if v is not None and not np.isnan(v)]
    if len(known) < 2:
        return "—"
    coarse, fine = known[0], known[-1]
    if coarse == 0:
        return "—"
    change = (fine - coarse) / abs(coarse)
    word = "stays" if abs(change) < STAYS else "shrinks" if abs(fine) < abs(coarse) else "grows"
    return f"{word} ({change:+.1%})"


def _runs_tables(cases: dict) -> list[str]:
    runs = ["## Runs\n",
            "| scheme | variant | Δx (mm) | Δt (ms) | status | ranks | solve (s) | cells | not activated | last cell (ms) | at (mm) "
            "| end (ms) | margin (ms) | Vm wall type | checks |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    probes = ["\n## Probes (ms; — is never activated)\n",
              "| scheme | variant | Δx (mm) | Δt (ms) | " + " | ".join(f"P{i}" for i in range(1, 10)) + " | line end |",
              "|---|---|---|---|" + "---|" * 10]
    for scheme in SCHEMES:
        for variant in VARIANTS:
            for (dx, dt), c in sorted(cases.get((scheme, variant), {}).items(), key=lambda kv: (-kv[0][0], -kv[0][1])):
                checks = "; ".join(c["problems"] + ([f"{c['not_activated']} cell(s) never activated"] if c["not_activated"] else [])
                                   + ([] if c["status"] == "completed" else [f"{c['status']}: left out of the comparisons"]))
                runs.append(f"| {scheme} | {variant} | {dx:g} | {dt:g} | {c['status']} | {c['ranks']} | {_f(c['solve'], 1)} | {np.prod(c['n']):,} "
                            f"| {c['not_activated']} | {_f(c['last_ms'])} | {c['last_at']} | {_f(c['end_ms'], 0)} "
                            f"| {_f(None if c['end_ms'] is None else c['end_ms'] - c['last_ms'], 1)} | `{','.join(c['wall_types'])}` | {checks or 'ok'} |")
                probes.append(f"| {scheme} | {variant} | {dx:g} | {dt:g} | " + " | ".join(_f(float(x)) for x in c["probes"]) + f" | {_f(c['line_end'])} |")
    return runs + probes


def _difference_tables(cases: dict, pairs: dict) -> list[str]:
    out = ["\n## Field differences (ms; second − first, over cells both activated)\n",
           "| scheme | Δx (mm) | Δt (ms) | pair | P8 | max | min | mean | mean abs | max at (mm) | its reference time | its rank % | max is the last cell | Spearman(t, diff) | Δ last activation |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for scheme in SCHEMES:
        for dx in DX_MM:
            for dt in DT_MS:
                for ref, other in PAIRS:
                    p = pairs.get((scheme, ref, other, dx, dt))
                    if p is None:
                        continue
                    out.append(f"| {scheme} | {dx:g} | {dt:g} | {other} − {ref} | {_f(p['p8'], sign=True)} | {_f(p['max'], sign=True)} "
                               f"| {_f(p['min'], sign=True)} | {_f(p['mean'], sign=True)} | {_f(p['mean_abs'])} | {p['at']} "
                               f"| {_f(p['t_ref'], 1)} | {_f(p['percentile'], 1)} | {'yes' if p['at_last_cell'] else 'no'} "
                               f"| {_f(p['spearman'], 2)} | {_f(p['last'], sign=True)} |")
    bins = ["\n## AB − 0 against the activation time of 0 (10 equal bins of [0, last]; mean / max abs, ms; first Δt available)\n"]
    for scheme in SCHEMES:
        for dx in DX_MM:
            dt = next((dt for dt in DT_MS if (scheme, "0", "AB", dx, dt) in pairs), None)
            if dt is None:
                continue
            p = pairs[(scheme, "0", "AB", dx, dt)]
            a, d = p["a"], p["d"]
            edges = np.linspace(0, np.nanmax(a) * (1 + 1e-12), 11)
            which = np.digitize(a, edges) - 1
            cells = []
            for q in range(10):
                chosen = (which == q) & ~np.isnan(d)
                cells.append(f"{edges[q]:.0f}–{edges[q + 1]:.0f}: " + (f"{d[chosen].mean():.2f} / {np.abs(d[chosen]).max():.2f}" if chosen.any() else "—"))
            bins.append(f"- {scheme}, Δx {dx:g}, Δt {dt:g}: " + "; ".join(cells))
    return out + bins


def _convergence_tables(cases: dict) -> list[str]:
    out = ["\n## P8 (ms) against Δx and Δt\n"]
    for scheme in SCHEMES:
        for variant in VARIANTS:
            level = cases.get((scheme, variant), {})
            p8 = {k: float(c["probes"][7]) for k, c in level.items()}
            if not p8:
                continue
            out += [f"\n### {scheme}, variant {variant}\n",
                    "| Δt (ms) | " + " | ".join(f"Δx {dx:g}" for dx in DX_MM) + " | observed order in Δx |", "|---|" + "---|" * 4]
            for dt in DT_MS:
                row = tuple(p8.get((dx, dt)) for dx in DX_MM)
                order = observed_order(DX_MM, row) if None not in row else None
                out.append(f"| {dt:g} | " + " | ".join(_f(v) for v in row) + f" | {_f(order, 2)} |")
            out += ["\n| Δx (mm) | " + " | ".join(f"Δt {dt:g}" for dt in DT_MS) + " | observed order in Δt |", "|---|" + "---|" * 4]
            for dx in DX_MM:
                row = tuple(p8.get((dx, dt)) for dt in DT_MS)
                order = observed_order(DT_MS, row) if None not in row else None
                out.append(f"| {dx:g} | " + " | ".join(_f(v) for v in row) + f" | {_f(order, 2)} |")
    return out


def _gap_tables(pairs: dict) -> list[str]:
    out = ["\n## The wall-variant gap against refinement (ms; second − first)\n",
           f"The trend compares the finest level present with the coarsest; within ±{STAYS:.0%} it stays.\n",
           "| scheme | pair | quantity | Δt (ms) | " + " | ".join(f"Δx {dx:g}" for dx in DX_MM) + " | trend |", "|---|---|---|---|" + "---|" * 4]
    for scheme in SCHEMES:
        for ref, other in PAIRS:
            for quantity, label in (("p8", "P8"), ("max", "field max")):
                for dt in DT_MS:
                    row = [pairs[key][quantity] if (key := (scheme, ref, other, dx, dt)) in pairs else None for dx in DX_MM]
                    if all(v is None for v in row):
                        continue
                    out.append(f"| {scheme} | {other} − {ref} | {label} | {dt:g} | " + " | ".join(_f(v, sign=True) for v in row) + f" | {_trend(row)} |")
    return out


def _scheme_tables(cases: dict, pairs: dict) -> list[str]:
    out = ["\n## Godunov against SBDF2 (ms)\n",
           "| variant | Δx (mm) | Δt (ms) | P8 godunov | P8 sbdf2 | sbdf2 − godunov |", "|---|---|---|---|---|---|"]
    for variant in VARIANTS:
        for dx in DX_MM:
            for dt in DT_MS:
                g, s = (cases.get((scheme, variant), {}).get((dx, dt)) for scheme in SCHEMES)
                if g is not None and s is not None:
                    out.append(f"| {variant} | {dx:g} | {dt:g} | {_f(g['probes'][7])} | {_f(s['probes'][7])} | {_f(s['probes'][7] - g['probes'][7], sign=True)} |")
    out += ["\n| quantity (AB − 0) | Δx (mm) | Δt (ms) | godunov | sbdf2 | sbdf2 − godunov |", "|---|---|---|---|---|---|"]
    for quantity, label in (("p8", "P8"), ("max", "field max")):
        for dx in DX_MM:
            for dt in DT_MS:
                g, s = (pairs.get((scheme, "0", "AB", dx, dt)) for scheme in SCHEMES)
                if g is not None and s is not None:
                    out.append(f"| {label} | {dx:g} | {dt:g} | {_f(g[quantity], sign=True)} | {_f(s[quantity], sign=True)} | {_f(s[quantity] - g[quantity], sign=True)} |")
    return out


def _missing(cases: dict) -> list[str]:
    absent = []
    for scheme in SCHEMES:
        for variant in VARIANTS:
            for dx in DX_MM:
                lacking = [f"{dt:g}" for dt in DT_MS if (dx, dt) not in cases.get((scheme, variant), {})]
                if lacking:
                    absent.append(f"- {scheme}/{variant}/dx{dx:g}: Δt {', '.join(lacking)}")
    return ["\n## Missing, or not completed\n"] + (absent or ["none: all 54 cases completed and were read"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--runs", type=Path, default=HERE / "runs" / "oblique")
    args = parser.parse_args(argv)
    if not args.runs.is_dir():
        print(f"oblique_summarize: {args.runs} is not a directory", file=sys.stderr)
        return 1
    everything, errors = collect(args.runs.resolve())
    # A case that did not complete holds a partial field, so it enters no comparison.
    cases = {key: {k: c for k, c in level.items() if c["status"] == "completed"} for key, level in everything.items()}
    pairs = {}
    for (scheme, variant), level in cases.items():
        for ref, other in PAIRS:
            if variant != ref:
                continue
            for key, first in level.items():
                second = cases.get((scheme, other), {}).get(key)
                if second is not None:
                    pairs[(scheme, ref, other, *key)] = difference(first, second)
    lines = _runs_tables(everything) + _difference_tables(cases, pairs) + _convergence_tables(cases) + _gap_tables(pairs) + _scheme_tables(cases, pairs)
    lines += _missing(cases)
    if errors:
        lines += ["\n## Cases that could not be read\n"] + [f"- {e}" for e in errors]
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
