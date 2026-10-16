"""Which source a build came from: digests, git identity and the contract member."""
from __future__ import annotations

import subprocess
from pathlib import Path

from omnidriver.core import provider_stack
from omnidriver.core.plugin_interface import KNOWN, SolverBuild, SolverEntry, SourceIdentity
from omnidriver.core.runtime.build_identity import file_digest, git_identity, tree_digest


def _git(root: Path, *args: str) -> None:
    subprocess.run(("git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", *args),
                   check=True, capture_output=True)


def test_file_digest_is_the_content_hash_and_none_for_an_absent_file(tmp_path):
    binary = tmp_path / "solver"
    binary.write_bytes(b"one")
    import hashlib
    assert file_digest(binary) == "sha256:" + hashlib.sha256(b"one").hexdigest()
    assert file_digest(tmp_path / "absent") is None


def test_tree_digest_depends_on_paths_and_bytes_not_on_listing_order(tmp_path):
    (tmp_path / "a.C").write_text("a")
    (tmp_path / "b.H").write_text("b")
    files = [tmp_path / "a.C", tmp_path / "b.H"]
    first = tree_digest(tmp_path, files)
    assert first == tree_digest(tmp_path, list(reversed(files)))
    assert first.startswith("sha256:") and len(first) == 7 + 64
    (tmp_path / "b.H").write_text("changed")
    assert tree_digest(tmp_path, files) != first


def test_git_identity_reads_commit_and_dirty_only_at_the_given_root(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "a.C").write_text("a")
    _git(repo, "add", "a.C")
    _git(repo, "commit", "-q", "-m", "one")
    head = subprocess.run(("git", "-C", str(repo), "rev-parse", "HEAD"), capture_output=True, text=True).stdout.strip()
    assert git_identity(repo) == {"commit": head, "dirty": False}
    (repo / "a.C").write_text("edited")
    assert git_identity(repo) == {"commit": head, "dirty": True}
    (repo / "sub").mkdir()
    assert git_identity(repo / "sub") is None


def test_a_git_file_that_is_no_repository_gives_no_identity(tmp_path):
    (tmp_path / ".git").write_text("gitdir: /nowhere/at/all\n")
    assert git_identity(tmp_path) is None


def test_source_identity_serialises_every_field():
    identity = SourceIdentity(repository="/r", digest="sha256:" + "0" * 64, git={"commit": "abc", "dirty": False})
    assert identity.to_json() == {"repository": "/r", "digest": "sha256:" + "0" * 64,
                                  "git": {"commit": "abc", "dirty": False}}
    assert SourceIdentity().to_json() == {"repository": None, "digest": None, "git": None}


def test_get_solver_builds_is_optional_and_answers_nothing_when_absent():
    assert provider_stack.MEMBERS["get_solver_builds"] == ("sequence", None)

    class _None:
        plugin_id = "org.none"
        plugin_api_version = "3"

    stack = provider_stack.ProviderStack(provider_stack.order_providers((_None(),)))
    assert stack.call("get_solver_builds", {}, repository=None, used_paths=None) == ()


def test_solver_entries_compose_as_a_list_over_providers():
    entry = SolverEntry(solver="s", repository=None,
                        builds=(SolverBuild(name="x", path=None, digest=None, known="unknown"),))

    class _One:
        plugin_id = "org.one"
        plugin_api_version = "3"

        def get_solver_builds(self, env, *, repository, used_paths):
            return (entry,)

    stack = provider_stack.ProviderStack(provider_stack.order_providers((_One(),)))
    assert stack.call("get_solver_builds", {}, repository=None, used_paths=None) == (entry,)
    assert KNOWN == ("recorded", "self_reported", "live", "unknown")
