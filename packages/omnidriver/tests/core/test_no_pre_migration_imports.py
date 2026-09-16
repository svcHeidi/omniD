"""Shipped modules never import the retired ``openfoam_driver`` package."""
from __future__ import annotations

import ast
import pathlib

import omnidriver.core

from conftest import skip_without_repo

#: .../packages — parents[4] of core/__init__.py: core, omnidriver, src,
#: omnidriver (the package dir), packages. Asserted below rather than trusted:
#: a guard whose root does not resolve passes by scanning nothing, which this
#: repository has now produced twice.
_PACKAGES = pathlib.Path(omnidriver.core.__file__).resolve().parents[4]

_FORBIDDEN = "openfoam_driver"


def _offenders() -> list[str]:
    found: list[str] = []
    for src in sorted(_PACKAGES.glob("*/src")):
        for path in sorted(src.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            tree = ast.parse(path.read_text(), filename=str(path))
            for node in ast.walk(tree):
                names: list[str] = []
                if isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module]
                elif isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                for name in names:
                    if name == _FORBIDDEN or name.startswith(_FORBIDDEN + "."):
                        found.append(
                            f"{path.relative_to(_PACKAGES)}:{node.lineno}: {name}"
                        )
    return found


@skip_without_repo
def test_the_scan_root_resolves() -> None:
    assert _PACKAGES.is_dir(), _PACKAGES
    assert sorted(p.parent.name for p in _PACKAGES.glob("*/src")) == [
        "omnidriver",
        "omnidriver-cardiaccore",
        "omnidriver-cardiacfoam",
        "omnidriver-openfoam",
    ], "all four packages must be scanned, or this guard proves nothing"


def test_no_shipped_module_imports_the_pre_migration_package() -> None:
    offenders = _offenders()
    assert offenders == [], (
        "shipped modules importing the retired 'openfoam_driver' package:\n"
        + "\n".join(f"  {o}" for o in offenders)
        + "\n\nThat package ships in no install. It resolves here only because "
        "the legacy tree is still tracked at the repo root and pytest runs "
        "from there. Import from omnidriver.* instead — and if the name is "
        "only needed for annotations, put it under TYPE_CHECKING."
    )
