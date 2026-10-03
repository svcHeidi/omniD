from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from omnidriver.postprocessing.table_writer import TableWriter


class TestTableWriter(unittest.TestCase):
    def test_writes_csv_with_envelope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            rows = [
                {"case_id": "case_A", "DX_mm": 0.1, "activation_ms": 42.3},
                {"case_id": "case_B", "DX_mm": 0.2, "activation_ms": 55.1},
            ]
            TableWriter.write(
                rows, output_dir, "test_summary", "Test label", "TestTutorial",
                units={"activation_ms": "ms", "DX_mm": "mm"},
            )

            csv_path = output_dir / "test_summary.csv"
            self.assertTrue(csv_path.exists())
            text = csv_path.read_text()
            self.assertIn("# entry: TestTutorial", text)
            self.assertIn("# generated_at:", text)
            self.assertIn('"activation_ms": "ms"', text)
            self.assertIn("case_id,DX_mm,activation_ms", text)
            self.assertIn("case_A,0.1,42.3", text)
            self.assertIn("case_B,0.2,55.1", text)

    def test_writes_html_with_metadata_and_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            rows = [{"col_a": "x", "col_b": 1}]
            TableWriter.write(rows, output_dir, "html_test", "HTML label", "HtmlTest", units={"col_b": "ms"})

            html_text = (output_dir / "html_test.html").read_text()
            self.assertIn("HtmlTest", html_text)
            self.assertIn("col_a", html_text)
            self.assertIn("<td>x</td>", html_text)

    def test_returns_two_artifacts_with_correct_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            artifacts = TableWriter.write([{"x": 1}], output_dir, "art_stem", "Art label", "ArtifactTest")
            self.assertEqual(len(artifacts), 2)
            by_format = {a["format"]: a for a in artifacts}
            self.assertIn("csv", by_format)
            self.assertIn("html", by_format)
            for a in artifacts:
                self.assertEqual(a["kind"], "table")
                self.assertEqual(a["label"], "Art label")
                self.assertIn("path", a)

    def test_handles_empty_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            artifacts = TableWriter.write([], output_dir, "empty_stem", "Empty", "EmptyTest")
            self.assertEqual(len(artifacts), 2)
            csv_text = (output_dir / "empty_stem.csv").read_text()
            self.assertIn("# entry: EmptyTest", csv_text)

    def test_the_envelope_records_a_parseable_utc_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            TableWriter.write([{"a": 1}], tmp, "stem", "L", "T")
            line = next(
                line for line in (Path(tmp) / "stem.csv").read_text().splitlines()
                if line.startswith("# generated_at: ")
            )
            stamp = datetime.fromisoformat(line.removeprefix("# generated_at: "))
            self.assertEqual(stamp.utcoffset().total_seconds(), 0)

    def test_artifact_paths_are_relative_filenames(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            artifacts = TableWriter.write([{"a": 1}], output_dir, "stem", "L", "T")
            for a in artifacts:
                # path must be just the filename, not absolute
                self.assertFalse(Path(a["path"]).is_absolute())
                self.assertIn("stem", a["path"])


if __name__ == "__main__":
    unittest.main()
