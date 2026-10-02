"""Tests CLI wiring for sweep-plan/sweep-run actions."""

import json
import unittest
from pathlib import Path
from unittest import mock

from omnidriver.cli import main


_PLUGIN = "plugins.minimal_plugin:MinimalTestPlugin"


class TestCliSweepActions(unittest.TestCase):
    def test_sweep_plan_dispatches_to_sweep_runner(self):
        captured = []

        def fake_print(*args, **kwargs):
            captured.append(" ".join(str(a) for a in args))

        with mock.patch("omnidriver.cli.sweep_plan", return_value={"case_count": 2, "cases": []}) as mock_fn, \
             mock.patch("builtins.print", side_effect=fake_print):
            code = main(["sweep-plan", "--plugin", _PLUGIN, "--spec", "sweep.json", "--output-dir", "/tmp/out"])

        assert code == 0
        mock_fn.assert_called_once()
        payload = json.loads(captured[0])
        assert payload["case_count"] == 2

    def test_sweep_plan_defaults_to_the_supplied_scratch_output_dir(self):
        with mock.patch(
            "omnidriver.cli.sweep_plan",
            return_value={"case_count": 0, "cases": []},
        ) as mock_fn, mock.patch("builtins.print"):
            assert main([
                "sweep-plan", "--plugin", _PLUGIN, "--spec", "paperI_methods.json", "--scratch-dir", "/tmp/od-scratch",
            ]) == 0

        # Not the OS temp directory by default: sweep outputs default under
        # the scratch root, so having the OS reap it would be worse.
        assert str(mock_fn.call_args.kwargs["output_dir"]) == str(
            Path("/tmp/od-scratch") / "sweeps" / "paperI_methods"
        )

    def test_sweep_run_defaults_to_the_supplied_scratch_output_dir(self):
        with mock.patch(
            "omnidriver.cli.sweep_run",
            return_value={"case_count": 0, "completed_count": 0, "failed_count": 0},
        ) as mock_fn, mock.patch("builtins.print"):
            assert main([
                "sweep-run", "--plugin", _PLUGIN, "--spec", "paperI_methods.json", "--scratch-dir", "/tmp/od-scratch",
            ]) == 0

        # Not the OS temp directory by default: sweep outputs default under
        # the scratch root, so having the OS reap it would be worse.
        assert str(mock_fn.call_args.kwargs["output_dir"]) == str(
            Path("/tmp/od-scratch") / "sweeps" / "paperI_methods"
        )

    def test_sweep_run_passes_max_cases(self):
        captured = []

        def fake_print(*args, **kwargs):
            captured.append(" ".join(str(a) for a in args))

        with mock.patch(
            "omnidriver.cli.sweep_run",
            return_value={"case_count": 1, "completed_count": 1, "failed_count": 0, "skipped_count": 0},
        ) as mock_fn, mock.patch("builtins.print", side_effect=fake_print):
            code = main([
                "sweep-run", "--plugin", _PLUGIN, "--spec", "sweep.json", "--output-dir", "/tmp/out",
                "--max-cases", "500",
            ])

        assert code == 0
        mock_fn.assert_called_once()
        kwargs = mock_fn.call_args.kwargs
        assert kwargs["max_cases"] == 500

    def test_sweep_run_passes_fresh_flag(self):
        captured = []

        def fake_print(*args, **kwargs):
            captured.append(" ".join(str(a) for a in args))

        with mock.patch(
            "omnidriver.cli.sweep_run",
            return_value={"case_count": 1, "completed_count": 1, "failed_count": 0, "skipped_count": 0},
        ) as mock_fn, mock.patch("builtins.print", side_effect=fake_print):
            code = main([
                "sweep-run", "--plugin", _PLUGIN, "--spec", "sweep.json", "--output-dir", "/tmp/out", "--fresh",
            ])

        assert code == 0
        mock_fn.assert_called_once()
        assert mock_fn.call_args.kwargs["fresh"] is True

    def test_fresh_rejected_for_describe_action(self):
        with mock.patch("builtins.print"):
            with self.assertRaises(SystemExit):
                main(["describe", "--entry", "singleCell", "--fresh"])

    def test_sweep_plan_exits_nonzero_when_a_case_failed(self):
        with mock.patch(
            "omnidriver.cli.sweep_plan",
            return_value={
                "case_count": 2,
                "cases": [
                    {"case_id": "caseA", "status": "ok"},
                    {"case_id": "caseB", "status": "failed", "materialization_error": "bad axis value"},
                ],
            },
        ), mock.patch("builtins.print"):
            code = main(["sweep-plan", "--plugin", _PLUGIN, "--spec", "sweep.json", "--output-dir", "/tmp/out"])

        assert code == 1

    def test_sweep_plan_rejects_entry_flag(self):
        with mock.patch("builtins.print"):
            with self.assertRaises(SystemExit):
                main(["sweep-plan", "--plugin", _PLUGIN, "--spec", "sweep.json", "--output-dir", "/tmp/out", "--entry", "singleCell"])

    def test_non_sweep_action_rejects_spec_flag(self):
        with mock.patch("builtins.print"):
            with self.assertRaises(SystemExit):
                main(["plan", "--strict", "--entry", "singleCell", "--spec", "sweep.json"])


if __name__ == "__main__":
    unittest.main()
