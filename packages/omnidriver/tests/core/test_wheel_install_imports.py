"""Every core module must import from a real wheel, not just an editable install.

core/specs/paths.py::repo_root_default() walks up looking for a development
checkout and raises when it finds none. capability_seams.py called it at module
scope, so `import omnidriver.core.capability_seams` raised RuntimeError from
site-packages -- invisible to every editable install and to all of CI, while
release.yml built and published exactly that wheel.

Slow (builds a wheel into a throwaway venv). Marked so it can be deselected
locally with -m 'not slow'; CI runs it.
"""
from __future__ import annotations

import subprocess
import sys
import venv
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]

_WALK = """
import importlib, pkgutil, sys
import omnidriver
bad = []
for module in pkgutil.walk_packages(omnidriver.__path__, "omnidriver."):
    if "conftest" in module.name:
        continue
    try:
        importlib.import_module(module.name)
    except Exception as exc:
        bad.append(f"{module.name}: {type(exc).__name__}: {exc}")

# Modules known to fail from a wheel for a reason tracked elsewhere. This set
# may only SHRINK: an entry that stops matching fails the test, so it cannot
# rot into a lie the way a silently-broad assertion would.
KNOWN_UNIMPORTABLE = {
    # Imports PHYSICS_PROPERTY_ENTRIES from omnidriver.dict_entries, whose PEP
    # 562 __getattr__ resolves it out of omnidriver.cardiacfoam. Phase 2 moves
    # this module to omnidriver-cardiacfoam and deletes this entry.
    "omnidriver.scripts._rtst_scanner",
}

unexpected = [line for line in bad if line.split(":")[0] not in KNOWN_UNIMPORTABLE]
stale = KNOWN_UNIMPORTABLE - {line.split(":")[0] for line in bad}
if stale:
    print("KNOWN_UNIMPORTABLE entries that now import fine -- delete them: "
          + ", ".join(sorted(stale)))
    sys.exit(1)
if unexpected:
    print("\\n".join(unexpected))
    sys.exit(1)
print("all modules imported")
"""


@pytest.mark.slow
def test_every_core_module_imports_from_a_wheel(tmp_path) -> None:
    env_dir = tmp_path / "venv"
    venv.create(env_dir, with_pip=True)
    python = env_dir / "bin" / "python"

    subprocess.run(
        [str(python), "-m", "pip", "install", "-q", "build"],
        check=True, capture_output=True,
    )
    subprocess.run(
        [str(python), "-m", "build", "--wheel",
         str(_REPO_ROOT / "packages" / "omnidriver"), "-o", str(tmp_path / "dist")],
        check=True, capture_output=True,
    )
    wheel = next((tmp_path / "dist").glob("*.whl"))
    subprocess.run(
        [str(python), "-m", "pip", "install", "-q", f"{wheel}[post]"],
        check=True, capture_output=True,
    )

    # cwd must not be the repo: it would put the source tree back on sys.path
    # and re-hide exactly what this test exists to catch.
    result = subprocess.run(
        [str(python), "-c", _WALK],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
