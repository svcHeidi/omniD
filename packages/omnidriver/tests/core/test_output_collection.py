"""Tests Core's convention-free snapshot/diff output collector."""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from omnidriver.core.runtime.output_collection import (
    OutputCollisionError,
    collect_new_output_tree,
    snapshot_output_tree,
)


class TestSnapshotAndCollect(unittest.TestCase):
    def test_new_file_after_snapshot_is_collected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "case" / "generated-output"
            root.mkdir(parents=True)
            destination = Path(tmp) / "sweep-cases" / "10"
            before = snapshot_output_tree(root)
            (root / "result.dat").write_text("case A data")

            collected = collect_new_output_tree(root, before, destination, label="10")

            self.assertEqual([path.name for path in collected], ["result.dat"])
            self.assertEqual((destination / "result.dat").read_text(), "case A data")

    def test_unchanged_file_is_not_recollected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "case" / "generated-output"
            root.mkdir(parents=True)
            (root / "stale.dat").write_text("old")
            destination = Path(tmp) / "sweep-cases" / "10"

            self.assertEqual(collect_new_output_tree(root, snapshot_output_tree(root), destination), [])
            self.assertFalse((destination / "stale.dat").exists())

    def test_sequential_cases_keep_separate_destinations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "case" / "generated-output"
            root.mkdir(parents=True)
            destination = Path(tmp) / "sweep-cases"

            first = snapshot_output_tree(root)
            (root / "result.dat").write_text("first")
            collect_new_output_tree(root, first, destination / "first", label="first")
            second = snapshot_output_tree(root)
            (root / "result.dat").write_text("second")
            collect_new_output_tree(root, second, destination / "second", label="second")

            self.assertEqual((destination / "first" / "result.dat").read_text(), "first")
            self.assertEqual((destination / "second" / "result.dat").read_text(), "second")

    def test_different_retry_content_refuses_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "case" / "generated-output"
            root.mkdir(parents=True)
            destination = Path(tmp) / "sweep-cases" / "10"
            first = snapshot_output_tree(root)
            (root / "result.dat").write_text("first")
            collect_new_output_tree(root, first, destination, label="10")
            time.sleep(0.01)
            second = snapshot_output_tree(root)
            (root / "result.dat").write_text("second")
            with self.assertRaises(OutputCollisionError):
                collect_new_output_tree(root, second, destination, label="10")

    def test_nested_paths_are_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "case" / "generated-output"
            (root / "probe" / "10").mkdir(parents=True)
            before = snapshot_output_tree(root)
            (root / "probe" / "10" / "data.xy").write_text("xy")

            collect_new_output_tree(root, before, Path(tmp) / "archive", label="case")

            self.assertTrue((Path(tmp) / "archive" / "probe" / "10" / "data.xy").exists())

    def test_missing_declared_output_root_snapshots_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(snapshot_output_tree(Path(tmp) / "absent"), {})


if __name__ == "__main__":
    unittest.main()
