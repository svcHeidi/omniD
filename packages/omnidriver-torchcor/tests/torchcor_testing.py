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


#: A stand-in runner: it prints the real runner's committed --describe output,
#: and for --check of an existing case.json its committed --check output.
_STAND_IN = """import pathlib, sys
if sys.argv[1:] == ["--describe"]:
    sys.stdout.write(open({describe!r}).read())
elif sys.argv[1] == "--check" and pathlib.Path(sys.argv[2]).name == "case.json" and pathlib.Path(sys.argv[2]).is_file():
    sys.stdout.write(open({check!r}).read())
else:
    sys.exit("stand-in runner: unexpected arguments " + repr(sys.argv[1:]))
"""


def repository_with_runner(tmp_path: Path) -> Path:
    """A solver repository whose runner stands in for the real one."""
    root = tmp_path / "torchcor-cases"
    (root / "scripts").mkdir(parents=True)
    (root / "torchcor" / "torchcor").mkdir(parents=True)
    (root / "cases").mkdir()
    (root / "omnidriver.toml").write_text('plugin = "torchcor"\ntutorials = "cases"\nsource = "torchcor"\nscripts = "scripts"\n')
    (root / "torchcor" / "torchcor" / "__init__.py").write_text("")
    (root / "scripts" / "run_case.py").write_text(
        _STAND_IN.format(describe=str(FIXTURES / "describe.json"), check=str(FIXTURES / "check-refused.json"))
    )
    return root
