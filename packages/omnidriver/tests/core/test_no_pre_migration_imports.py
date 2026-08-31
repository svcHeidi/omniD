"""No shipped module may import the pre-migration ``openfoam_driver`` package.

That package name is what everything was called before the three-way split. It
exists in no install, so any such import is a defect.

It used to be worse than a defect — it was an *invisible* defect. A retired
`openfoam_driver/` tree (193 files, a stale 186-file subset of the real
reference) was tracked at this repo's root, so running Python from the repo root
put cwd on `sys.path` and the stale name resolved. Every suite runs from the
repo root, so every suite passed.

That is not hypothetical. `omnidriver-openfoam`'s `dict_builder.py` carried

    from openfoam_driver.dict_entries import DictEntry

at module scope until Phase 2 Task 3 surfaced it. `import
omnidriver.openfoam.dict_builder` raised `ModuleNotFoundError` from any cwd
outside this repository — a shipping defect in a published package — and every
test suite passed, because every suite runs from the repo root.

Same shape as the bug that made `omnidriver.core.capability_seams` unimportable
from a built wheel: correct-looking source that only works inside a development
checkout. `test_wheel_install_imports.py` catches that class for **core**; it
builds core's wheel only, so it could never have caught this one. This guard
covers all three packages cheaply, by reading source rather than installing
anything.

The legacy tree has since been deleted, so a stray import now fails loudly
instead of resolving. This guard is kept anyway, for two reasons: it catches the
mistake in source review rather than at import time, and it fails immediately if
anyone restores that tree and reintroduces the masking.
"""
from __future__ import annotations

import ast
import pathlib

import omnidriver.core

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


def test_the_scan_root_resolves() -> None:
    assert _PACKAGES.is_dir(), _PACKAGES
    assert sorted(p.parent.name for p in _PACKAGES.glob("*/src")) == [
        "omnidriver",
        "omnidriver-cardiacfoam",
        "omnidriver-openfoam",
    ], "all three packages must be scanned, or this guard proves nothing"


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
