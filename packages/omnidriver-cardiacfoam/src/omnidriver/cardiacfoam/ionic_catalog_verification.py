"""Verify the static ionic catalog against the names the built solver exposes.

Run as the ``omnidriver check`` probe; without the utility on ``PATH`` every model is ``skipped``, and a skip is never a pass."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# An unknown override name is a FatalError at solver startup, and no static
# rule describes the names: most carry an AC_ prefix (CellML-generated
# constants), hand-added ones do not, and one model mixes both (TWorld's
# gnalTissueScale). The utility prints the same constant names the solver's
# override matcher accepts, so it is the authority.
_UTILITY = "listCellModelsVariables"

# Sections the report exposes, in the order the utility prints them.
_FIELDS = ("constants", "states", "algebraic")


@dataclass(frozen=True)
class ModelVerificationResult:
    """One model's catalog-vs-runtime comparison.

    ``missing_from_catalog`` is the dangerous direction: the solver exposes a
    name the catalog does not, so an agent never learns the override exists.
    ``extra_in_catalog`` is the loud one: the catalog advertises a name the
    solver lacks, so an agent writes an override that fatals at startup.

    Only non-empty fields appear in either mapping.
    """

    model: str
    status: str  # "match" | "mismatch" | "skipped" | "error"
    missing_from_catalog: dict[str, tuple[str, ...]] = field(default_factory=dict)
    extra_in_catalog: dict[str, tuple[str, ...]] = field(default_factory=dict)
    reason: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "status": self.status,
            "missing_from_catalog": {k: list(v) for k, v in self.missing_from_catalog.items()},
            "extra_in_catalog": {k: list(v) for k, v in self.extra_in_catalog.items()},
            "reason": self.reason,
        }


@dataclass(frozen=True)
class VerificationResult:
    """Whole-run result. ``all_match`` is True only when every model was
    actually compared and agreed -- a skipped model makes it False, because a
    check that did not run is not a check that passed."""

    utility_available: bool
    results: dict[str, ModelVerificationResult]

    @property
    def all_match(self) -> bool:
        return bool(self.results) and all(
            result.status == "match" for result in self.results.values()
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "utility_available": self.utility_available,
            "all_match": self.all_match,
            "results": {name: r.to_json() for name, r in self.results.items()},
        }


def parse_report_text(text: str) -> dict[str, Any]:
    """Parse a listCellModelsVariables report into name lists.

    ``algebraic`` entries carry no ``-->`` value, unlike constants and states.
    Unparseable text yields empty lists rather than raising, so the caller
    reports a mismatch and garbage never reads as agreement.
    """
    result: dict[str, Any] = {
        "ionic_model": None,
        "states": [],
        "algebraic": [],
        "constants": [],
    }

    model_match = re.search(r"Selected ionicModel:\s*(\w+)", text)
    if model_match:
        result["ionic_model"] = model_match.group(1)

    for section, value_suffix in (
        ("constants", r"\s*-->"),
        ("states", r"\s*-->"),
        ("algebraic", ""),
    ):
        header = "Ionic " + section
        block = re.search(
            rf"{header}\s*\(\d+\)[^\n]*\n((?:[ \t]+{section}[ \t]*\[\d+\][^\n]*\n)*)",
            text,
        )
        if not block:
            continue
        for line in block.group(1).split("\n"):
            match = re.search(rf"{section}\s*\[\d+\]\s+(\w+){value_suffix}", line)
            if match:
                result[section].append(match.group(1))

    return result


def diff_report(model: str, parsed: dict[str, Any], entry: Any) -> ModelVerificationResult:
    """Compare one parsed report against its catalog entry.

    Order is preserved from the source rather than sorted, so a diff reads in
    the same order as the file it came from.
    """
    missing: dict[str, tuple[str, ...]] = {}
    extra: dict[str, tuple[str, ...]] = {}

    for section in _FIELDS:
        runtime = list(parsed.get(section) or [])
        catalogued = list(getattr(entry, section, ()) or ())
        runtime_set, catalog_set = set(runtime), set(catalogued)

        only_runtime = tuple(n for n in runtime if n not in catalog_set)
        only_catalog = tuple(n for n in catalogued if n not in runtime_set)
        if only_runtime:
            missing[section] = only_runtime
        if only_catalog:
            extra[section] = only_catalog

    status = "match" if not missing and not extra else "mismatch"
    return ModelVerificationResult(
        model=model,
        status=status,
        missing_from_catalog=missing,
        extra_in_catalog=extra,
    )


def find_listCellModelsVariables_binary(env: Mapping[str, str] | None = None) -> Path | None:
    """Locate the utility on the ``PATH`` of ``env`` (the process's, by
    default), or None when OpenFOAM is not sourced."""
    found = shutil.which(_UTILITY, path=(os.environ if env is None else env).get("PATH"))
    return Path(found) if found else None


def _synthesize_case(case_dir: Path, model: str, entry: Any) -> None:
    """Build a single-cell case for one ionic model with the case builder."""
    from omnidriver.cardiacfoam.case_builder import build_case
    from omnidriver.core.plugin_interface import load_plugin_context

    # The selector takes a tissue the model itself defines; the others are
    # applied through heterogeneity.
    tissues = tuple(entry.native_tissue_labels or entry.compatible_tissues or ("myocyte",))

    # The *compactBatched models require batchedIntegrator, and the FDA
    # manufactured models select their analytical solution by dimensionality
    # and fatal without it (ionicSelector.C). Any valid choice exposes the same
    # variable set.
    overrides: dict[str, str] = {}
    if "Batched" in model:
        overrides["$ELECTRO_MODEL_COEFFS.batchedIntegrator"] = "rushLarsen"
    if "Manufactured" in model:
        overrides["$ELECTRO_MODEL_COEFFS.dimension"] = "3D"

    built = build_case(
        {"myocardiumSolver": "singleCellSolver", "ionicModel": model, "tissue": tissues[0]},
        case_dir=case_dir, electro_overrides=overrides or None, overwrite=True,
        # The probe takes no context; the stack it checks is this package's, under its own entry-point name.
        driver_context=load_plugin_context("cardiacfoam"),
    )
    if built["status"] != "ok":
        raise ValueError("; ".join(item["message"] for item in built["diagnostics"] if item["level"] == "error"))


def _verify_one(
    model: str, entry: Any, binary: Path, case_root: Path, env: Mapping[str, str] | None,
) -> ModelVerificationResult:
    """Run the utility for one model; a failure is that model's status, never raised, so it cannot blind the rest."""
    case_dir = case_root / model
    try:
        _synthesize_case(case_dir, model, entry)
    except Exception as exc:  # noqa: BLE001 - reported, not swallowed
        return ModelVerificationResult(
            model=model, status="error", reason=f"could not synthesize a case: {exc}"
        )

    try:
        subprocess.run(
            ["blockMesh", "-case", str(case_dir)],
            capture_output=True, text=True, timeout=120, check=True, env=env,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return ModelVerificationResult(
            model=model, status="error", reason=f"blockMesh failed to run: {exc}"
        )

    try:
        completed = subprocess.run(
            [str(binary), "-case", str(case_dir)],
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return ModelVerificationResult(
            model=model, status="error", reason=f"{_UTILITY} failed to run: {exc}"
        )

    report = completed.stdout
    # The utility also writes postProcessing/listCellModelsVariables.txt; prefer
    # it when stdout was redirected or truncated.
    written = case_dir / "postProcessing" / f"{_UTILITY}.txt"
    if written.is_file():
        report = written.read_text()

    parsed = parse_report_text(report)
    if not any(parsed[section] for section in _FIELDS):
        return ModelVerificationResult(
            model=model,
            status="error",
            reason=(
                f"{_UTILITY} produced no parseable report "
                f"(exit {completed.returncode}); stderr: {completed.stderr[:400]}"
            ),
        )
    return diff_report(model, parsed, entry)


def verify_ionic_catalog(
    model: str | None = None,
    *,
    case_dir: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> VerificationResult:
    """Verify one model, or every catalogued model, against the built solver.

    Raises ``KeyError`` for an unknown model name -- that is a caller bug and
    must not be reported as a skip.
    """
    from omnidriver.cardiacfoam.ionic_model_catalog import (
        IONIC_MODEL_CATALOG,
    )

    if model is not None and model not in IONIC_MODEL_CATALOG:
        raise KeyError(
            f"unknown ionic model {model!r}; known models: "
            + ", ".join(sorted(IONIC_MODEL_CATALOG))
        )
    targets = {model: IONIC_MODEL_CATALOG[model]} if model else dict(IONIC_MODEL_CATALOG)

    binary = find_listCellModelsVariables_binary(env)
    if binary is None:
        return VerificationResult(
            utility_available=False,
            results={
                name: ModelVerificationResult(
                    model=name,
                    status="skipped",
                    reason=(
                        f"{_UTILITY} not on PATH -- source the OpenFOAM bashrc and "
                        "build it. A skip is not a pass."
                    ),
                )
                for name in targets
            },
        )

    if case_dir is not None:
        root = Path(case_dir)
        root.mkdir(parents=True, exist_ok=True)
        results = {
            name: _verify_one(name, entry, binary, root, env)
            for name, entry in targets.items()
        }
    else:
        with tempfile.TemporaryDirectory(prefix="verify_ionic_catalog_") as tmp:
            root = Path(tmp)
            results = {
                name: _verify_one(name, entry, binary, root, env)
                for name, entry in targets.items()
            }

    return VerificationResult(utility_available=True, results=results)


def catalogue_probe(env: Mapping[str, str]) -> tuple[bool, str]:
    """``omnidriver check``'s probe: every catalogued ionic model against the
    built solver, run in the stack's ``env``, as (all matched, what was
    compared or what differs)."""
    result = verify_ionic_catalog(env=env)
    if not result.utility_available:
        return False, f"{_UTILITY} is not on PATH; run from the solver's shell"
    differ = {name: model.reason or model.status for name, model in sorted(result.results.items()) if model.status != "match"}
    if differ:
        first = next(iter(differ.items()))
        return False, (
            f"the catalogue disagrees with the built solver for {len(differ)} of {len(result.results)} models; "
            f"{first[0]}: {first[1][:300]}"
        )
    return True, f"{len(result.results)} ionic models match the built solver"
