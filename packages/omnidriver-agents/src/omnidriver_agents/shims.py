"""Wrappers first on a trial's PATH that log every launch of a solver program, in both conditions alike."""

from __future__ import annotations

from pathlib import Path

_SHIM = '''#!{python}
import json, os, shutil, subprocess, sys, time
bin_dir, log = {bin_dir!r}, {log!r}
path = os.pathsep.join(p for p in os.environ.get("PATH", "").split(os.pathsep) if os.path.realpath(p) != os.path.realpath(bin_dir))
real = shutil.which({program!r}, path=path)
ppid = os.getppid()
parent = subprocess.run(["ps", "-o", "comm=", "-p", str(ppid)], capture_output=True, text=True).stdout.strip()
start = time.monotonic()
code = 127 if real is None else subprocess.call([real, *sys.argv[1:]])
with open(log, "a") as f:
    f.write(json.dumps({{"program": {program!r}, "argv": sys.argv[1:], "cwd": os.getcwd(), "parent": {{"pid": ppid, "command": parent}}, "exit_code": code, "seconds": round(time.monotonic() - start, 3)}}) + "\\n")
sys.exit(code)
'''


def write_shims(bin_dir: Path, programs: tuple[str, ...], log: Path, python: Path | str) -> None:
    """Write one logging shim per program into ``bin_dir``, run by ``python``."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    for program in programs:
        shim = bin_dir / program
        shim.write_text(_SHIM.format(python=python, bin_dir=str(bin_dir), log=str(log), program=program))
        shim.chmod(0o755)
