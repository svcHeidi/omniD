"""CLI argument and exit-code wiring for sweep actions."""

import json
import unittest
from pathlib import Path
from unittest import mock

from omnidriver.cli import main
from omnidriver.core.plugin_interface import driver_context
from plugins.minimal_plugin import MinimalTestPlugin


def _patch_default_driver_context():
    # main() imports default_driver_context locally (from .core.plugin_interface
    # import default_driver_context), so there is no omnidriver.cli module
    # attribute to patch -- patch it at its defining module instead.
    return mock.patch(
        "omnidriver.core.plugin_interface.default_driver_context",
        side_effect=lambda: driver_context(
            MinimalTestPlugin(), source="test:cli-sweep",
        ),
    )


class TestCliSweepActions(unittest.TestCase):
    def test_sweep_plan_dispatches_to_sweep_runner(self):
        captured = []

        def fake_print(*args, **kwargs):
            captured.append(" ".join(str(a) for a in args))

        with mock.patch("omnidriver.cli.sweep_plan", return_value={"case_count": 2, "cases": []}) as mock_fn, \
             mock.patch("builtins.print", side_effect=fake_print), \
             _patch_default_driver_context():
            code = main(["sweep-plan", "--spec", "sweep.json", "--output-dir", "/tmp/out"])

        assert code == 0
        mock_fn.assert_called_once()
        payload = json.loads(captured[0])
        assert payload["case_count"] == 2

    def test_sweep_plan_defaults_to_workspace_scratch_output_dir(self):
        with mock.patch(
            "omnidriver.cli.sweep_plan",
            return_value={"case_count": 0, "cases": []},
        ) as mock_fn, mock.patch("builtins.print"), _patch_default_driver_context():
            assert main(["sweep-plan", "--spec", "paperI_methods.json"]) == 0

        # Was `.tmp/driverfoam/sweeps/...` INSIDE the repository, which is
        # unwritable on a read-only install and solver-branded. Scratch is
        # workspace-local now, under the resolved cases root -- deliberately
        # not the OS temp directory, since sweep outputs default here and
        # having the OS reap them would be worse.
        assert str(mock_fn.call_args.kwargs["output_dir"]) == str(
            Path.cwd() / ".omnidriver" / "sweeps" / "paperI_methods"
        )

    def test_sweep_run_defaults_to_workspace_scratch_output_dir(self):
        with mock.patch(
            "omnidriver.cli.sweep_run",
            return_value={"case_count": 0, "completed_count": 0, "failed_count": 0},
        ) as mock_fn, mock.patch("builtins.print"), _patch_default_driver_context():
            assert main(["sweep-run", "--spec", "paperI_methods.json"]) == 0

        # Was `.tmp/driverfoam/sweeps/...` INSIDE the repository, which is
        # unwritable on a read-only install and solver-branded. Scratch is
        # workspace-local now, under the resolved cases root -- deliberately
        # not the OS temp directory, since sweep outputs default here and
        # having the OS reap them would be worse.
        assert str(mock_fn.call_args.kwargs["output_dir"]) == str(
            Path.cwd() / ".omnidriver" / "sweeps" / "paperI_methods"
        )

    def test_sweep_run_passes_max_cases_and_retry_flag(self):
        captured = []

        def fake_print(*args, **kwargs):
            captured.append(" ".join(str(a) for a in args))

        with mock.patch(
            "omnidriver.cli.sweep_run",
            return_value={"case_count": 1, "completed_count": 1, "failed_count": 0, "skipped_count": 0},
        ) as mock_fn, mock.patch("builtins.print", side_effect=fake_print), \
             _patch_default_driver_context():
            code = main([
                "sweep-run", "--spec", "sweep.json", "--output-dir", "/tmp/out",
                "--max-cases", "500", "--retry-failed",
            ])

        assert code == 0
        mock_fn.assert_called_once()
        kwargs = mock_fn.call_args.kwargs
        assert kwargs["max_cases"] == 500
        assert kwargs["retry_failed"] is True

    def test_sweep_run_passes_fresh_flag(self):
        captured = []

        def fake_print(*args, **kwargs):
            captured.append(" ".join(str(a) for a in args))

        with mock.patch(
            "omnidriver.cli.sweep_run",
            return_value={"case_count": 1, "completed_count": 1, "failed_count": 0, "skipped_count": 0},
        ) as mock_fn, mock.patch("builtins.print", side_effect=fake_print), \
             _patch_default_driver_context():
            code = main([
                "sweep-run", "--spec", "sweep.json", "--output-dir", "/tmp/out", "--fresh",
            ])

        assert code == 0
        mock_fn.assert_called_once()
        assert mock_fn.call_args.kwargs["fresh"] is True

    def test_fresh_and_retry_failed_are_mutually_exclusive(self):
        with mock.patch("builtins.print"):
            with self.assertRaises(SystemExit):
                main([
                    "sweep-run", "--spec", "sweep.json", "--output-dir", "/tmp/out",
                    "--fresh", "--retry-failed",
                ])

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
        ), mock.patch("builtins.print"), _patch_default_driver_context():
            code = main(["sweep-plan", "--spec", "sweep.json", "--output-dir", "/tmp/out"])

        assert code == 1

    def test_sweep_plan_rejects_entry_flag(self):
        with mock.patch("builtins.print"):
            with self.assertRaises(SystemExit):
                main(["sweep-plan", "--spec", "sweep.json", "--output-dir", "/tmp/out", "--entry", "singleCell"])

    def test_non_sweep_action_rejects_spec_flag(self):
        with mock.patch("builtins.print"):
            with self.assertRaises(SystemExit):
                main(["plan", "--strict", "--entry", "singleCell", "--spec", "sweep.json"])


if __name__ == "__main__":
    unittest.main()
