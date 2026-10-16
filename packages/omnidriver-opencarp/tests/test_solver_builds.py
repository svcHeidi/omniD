"""openCARP's build identity comes from the binary itself (-buildinfo's tag and hash)."""
from __future__ import annotations

import subprocess
from pathlib import Path

from omnidriver.opencarp import environment
from omnidriver.opencarp.environment import buildinfo_identity, opencarp_solver_builds

FIXTURE = Path(__file__).parent / "fixtures" / "buildinfo-v18.1.txt"


def test_buildinfo_gives_the_tag_and_the_hash():
    assert buildinfo_identity(FIXTURE.read_text()) == {
        "tag": "v18.1", "commit": "6eaa147d18b69a6037d05a90b841e23301048a59",
    }
    assert buildinfo_identity("dyld: Library not loaded\n") is None


def _solver(tmp_path, monkeypatch, stdout):
    binary = tmp_path / "bin" / "openCARP"
    binary.parent.mkdir()
    binary.write_bytes(b"opencarp")
    binary.chmod(0o755)
    monkeypatch.setattr(environment.subprocess, "run",
                        lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=stdout, stderr=""))
    return binary, {"PATH": str(binary.parent)}


def test_the_solver_is_self_reported_when_it_prints_its_build(tmp_path, monkeypatch):
    binary, env = _solver(tmp_path, monkeypatch, FIXTURE.read_text())
    (entry,) = opencarp_solver_builds(env, used_paths=frozenset({binary.resolve()}))
    (build,) = entry.builds
    assert (entry.solver, entry.repository, entry.recordable) == ("org.omnidriver.opencarp", None, False)
    assert (build.name, build.known) == ("openCARP", "self_reported")
    assert build.source.git == {"tag": "v18.1", "commit": "6eaa147d18b69a6037d05a90b841e23301048a59"}
    assert build.digest.startswith("sha256:")


def test_a_silent_binary_is_unknown_and_an_unused_one_is_not_listed(tmp_path, monkeypatch):
    binary, env = _solver(tmp_path, monkeypatch, "")
    (entry,) = opencarp_solver_builds(env, used_paths=None)
    assert entry.builds[0].known == "unknown"
    assert opencarp_solver_builds(env, used_paths=frozenset({tmp_path / "mesher"})) == ()
    assert opencarp_solver_builds({"PATH": ""}, used_paths=None) == ()
