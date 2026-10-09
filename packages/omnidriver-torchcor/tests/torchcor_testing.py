from __future__ import annotations

import dataclasses
from pathlib import Path

from omnidriver.core.plugin_interface import driver_context
from omnidriver.core.repository import read_repository
from omnidriver.torchcor.plugin import TorchCorPlugin

FIXTURES = Path(__file__).parent / "fixtures"


def context_of(repository_root: Path | None = None):
    """The TorchCor stack, selected from ``repository_root`` (``--repo``) or from ``--plugin`` alone."""
    context = driver_context(TorchCorPlugin(), source="test")
    repository = read_repository(repository_root) if repository_root is not None else None
    return dataclasses.replace(context, repository=repository)


def repository_with_runner(tmp_path: Path) -> Path:
    """A solver repository whose runner prints the committed --describe output."""
    root = tmp_path / "torchcor-cases"
    (root / "scripts").mkdir(parents=True)
    (root / "torchcor" / "torchcor").mkdir(parents=True)
    (root / "cases").mkdir()
    (root / "omnidriver.toml").write_text('plugin = "torchcor"\ntutorials = "cases"\nsource = "torchcor"\nscripts = "scripts"\n')
    (root / "torchcor" / "torchcor" / "__init__.py").write_text("")
    (root / "scripts" / "run_case.py").write_text(
        f"import sys\nsys.stdout.write(open({str(FIXTURES / 'describe.json')!r}).read())\n"
    )
    return root
