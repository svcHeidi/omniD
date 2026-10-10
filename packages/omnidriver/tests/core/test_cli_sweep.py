"""Tests CLI wiring for sweep-plan/sweep-run actions."""

import json
import unittest
from pathlib import Path
from unittest import mock

from omnidriver.cli import main


_PLUGIN = "plugins.toy:ToyProvider"


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
                "sweep-plan", "--plugin", _PLUGIN, "--spec", "methods_study.json", "--scratch-dir", "/tmp/od-scratch",
            ]) == 0

        # Not the OS temp directory by default: sweep outputs default under
        # the scratch root, so having the OS reap it would be worse.
        assert str(mock_fn.call_args.kwargs["output_dir"]) == str(
            Path("/tmp/od-scratch") / "sweeps" / "methods_study"
        )

    def test_sweep_run_defaults_to_the_supplied_scratch_output_dir(self):
        with mock.patch(
            "omnidriver.cli.sweep_run",
            return_value={"case_count": 0, "completed_count": 0, "failed_count": 0},
        ) as mock_fn, mock.patch("builtins.print"):
            assert main([
                "sweep-run", "--plugin", _PLUGIN, "--spec", "methods_study.json", "--scratch-dir", "/tmp/od-scratch",
            ]) == 0

        # Not the OS temp directory by default: sweep outputs default under
        # the scratch root, so having the OS reap it would be worse.
        assert str(mock_fn.call_args.kwargs["output_dir"]) == str(
            Path("/tmp/od-scratch") / "sweeps" / "methods_study"
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
            assert main(["describe", "--entry", "singleCell", "--fresh"]) == 1

    def test_sweep_plan_exits_nonzero_when_a_case_failed(self):
        with mock.patch(
            "omnidriver.cli.sweep_plan",
            return_value={
                "case_count": 2,
                "cases": [
                    {"case_id": "caseA", "status": "ok"},
                    {"case_id": "caseB", "status": "failed", "code": "axis_rule", "error": "bad axis value"},
                ],
            },
        ), mock.patch("builtins.print"):
            code = main(["sweep-plan", "--plugin", _PLUGIN, "--spec", "sweep.json", "--output-dir", "/tmp/out"])

        assert code == 1

    def _plan_report(self, *cases):
        with mock.patch("omnidriver.cli.sweep_plan", return_value={"case_count": len(cases), "cases": list(cases)}), \
                mock.patch("builtins.print") as printed:
            code = main(["sweep-plan", "--plugin", _PLUGIN, "--spec", "sweep.json", "--output-dir", "/tmp/out"])
        return code, json.loads(printed.call_args.args[0])

    def test_a_sweep_plan_whose_every_failure_is_blocked_is_blocked(self):
        code, report = self._plan_report(
            {"case_id": "a", "status": "ok"},
            {"case_id": "b", "status": "blocked", "code": "plan_blocked"},
        )

        assert code == 1 and (report["status"], report["code"]) == ("blocked", "cases_blocked")

    def test_a_sweep_plan_with_a_failed_case_among_blocked_ones_is_failed(self):
        code, report = self._plan_report(
            {"case_id": "a", "status": "blocked", "code": "plan_blocked"},
            {"case_id": "b", "status": "failed", "code": "axis_rule"},
        )

        assert code == 1 and (report["status"], report["code"]) == ("failed", "cases_failed")

    def test_sweep_plan_rejects_entry_flag(self):
        with mock.patch("builtins.print"):
            assert main(["sweep-plan", "--plugin", _PLUGIN, "--spec", "sweep.json", "--output-dir", "/tmp/out", "--entry", "singleCell"]) == 1

    def test_non_sweep_action_rejects_spec_flag(self):
        with mock.patch("builtins.print"):
            assert main(["plan", "--strict", "--entry", "singleCell", "--spec", "sweep.json"]) == 1


if __name__ == "__main__":
    unittest.main()
