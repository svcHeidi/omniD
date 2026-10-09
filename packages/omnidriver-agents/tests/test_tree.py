import subprocess

from omnidriver_agents.tree import digest_tree, export_tree


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def test_export_is_the_committed_tree_only(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _git(src, "init", "-q")
    (src / "a.txt").write_text("a")
    _git(src, "add", "a.txt")
    _git(src, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "a")
    (src / "untracked.txt").write_text("u")
    commit = export_tree(src, "HEAD", tmp_path / "out")
    assert len(commit) == 40
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == ["a.txt"]


def test_digest_changes_with_content_and_not_with_mtime(tmp_path):
    (tmp_path / "f").write_text("x")
    before = digest_tree(tmp_path)
    (tmp_path / "f").touch()
    assert digest_tree(tmp_path) == before
    (tmp_path / "f").write_text("y")
    assert digest_tree(tmp_path) != before


def test_digest_changes_with_the_mode_bits(tmp_path):
    (tmp_path / "f").write_text("x")
    (tmp_path / "f").chmod(0o644)
    before = digest_tree(tmp_path)
    (tmp_path / "f").chmod(0o755)
    assert digest_tree(tmp_path) != before
