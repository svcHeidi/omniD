#!/usr/bin/env python3
"""Verify a *built and installed* omnidriver wheel actually works.

Run with the interpreter of a venv that has the wheel installed -- not an
editable install, and not this repository on ``sys.path``:

    python -m build --outdir dist packages/omnidriver
    python -m venv /tmp/wheelenv
    /tmp/wheelenv/bin/pip install "dist/omnidriver-*.whl[post]"
    /tmp/wheelenv/bin/python scripts/check-wheel-artifact.py

Why this is not covered by the test suite: an editable install leaves the
repository on the path, so a module that reads repo-relative state at import
time still works and the defect stays invisible. That exact bug shipped once --
``capability_seams.py`` evaluated ``repo_root_default()`` at module scope,
which made it unimportable from a wheel while every test passed.

Deliberately does NOT run the core pytest suite. Eight of its modules call
``repo_root_default()`` at import time and so error during collection outside a
checkout; they test repository tooling (documentation contracts, the CLI, the
capability-seam table), not the shipped library. Running them here would fail
for the wrong reason. Making them skip cleanly is worth doing separately.
"""
from __future__ import annotations

import importlib
import pkgutil
import subprocess
import sys

SIBLING_PACKAGES = (".cardiacfoam", ".openfoam")


def main() -> int:
    import omnidriver

    failures: list[str] = []

    # 1. Every core module imports with nothing but the wheel installed.
    names = [
        m.name
        for m in pkgutil.walk_packages(omnidriver.__path__, "omnidriver.")
        if not any(sib in m.name for sib in SIBLING_PACKAGES)
    ]
    if not names:
        print("FAIL: walked zero modules -- the wheel is not installed here")
        return 1
    for name in names:
        try:
            importlib.import_module(name)
        except Exception as exc:  # noqa: BLE001 -- report, do not mask
            failures.append(f"import {name}: {type(exc).__name__}: {exc}")
    print(f"modules imported            : {len(names) - len(failures)}/{len(names)}")

    # 2. The implicit default context resolves. With no plugin distribution
    #    installed this must be the built-in generic one, not an ImportError
    #    reaching for a plugin package that is not there.
    try:
        from omnidriver.core.plugin_interface import default_driver_context

        context = default_driver_context()
        print(f"default context             : {context.identity.id} ({context.identity.source})")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"default_driver_context(): {type(exc).__name__}: {exc}")

    # 3. The public edge answers without a plugin rather than raising.
    try:
        from omnidriver.dict_entries import get_heterogeneity_models

        print(f"public edge with no plugin  : {get_heterogeneity_models()!r}")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"get_heterogeneity_models(): {type(exc).__name__}: {exc}")

    # 4. The CLI is reachable. It hard-imported omnidriver.openfoam at module
    #    scope once, which made the whole command surface unusable in a
    #    core-only install.
    result = subprocess.run(
        [sys.executable, "-m", "omnidriver", "--help"], capture_output=True, text=True
    )
    print(f"`python -m omnidriver --help`: exit {result.returncode}")
    if result.returncode != 0:
        failures.append(f"CLI --help exited {result.returncode}: {result.stderr[:300]}")

    if failures:
        print("\nFAILED:")
        for f in failures:
            print(f"  {f}")
        return 1
    print("\nWheel artifact OK: core installs and runs standalone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
