"""``omnidriver build`` hands a solver package's declared builder the parsed
selections and reports its result; it knows no solver."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from omnidriver import cli
from omnidriver.core import case_build, plugin_interface


def _declare(monkeypatch, builder, name="toy"):
    monkeypatch.setattr(
        case_build, "entry_points", lambda group: [SimpleNamespace(name=name, load=lambda: builder)]
    )
    monkeypatch.setattr(plugin_interface, "load_plugin_context", lambda selector: f"context:{selector}")


def test_the_builder_receives_the_parsed_flags_and_its_result_is_reported(monkeypatch, tmp_path, capsys):
    seen = {}

    def builder(context, out, **kwargs):
        seen.update(context=context, out=out, **kwargs)
        return {"status": "ok", "files": ["a"]}

    _declare(monkeypatch, builder)
    code = cli.main([
        "build", "--plugin", "toy", "--out", str(tmp_path / "case"), "--select", "solver=x",
        "--set", "$A.b=1", "--option", "dx=0.1", "--overwrite",
    ])

    assert code == 0
    assert seen == {
        "context": "context:toy", "out": (tmp_path / "case").resolve(), "select": {"solver": "x"},
        "set_values": {"$A.b": "1"}, "options": {"dx": "0.1"}, "overwrite": True,
    }
    assert json.loads(capsys.readouterr().out) == {"action": "build", "plugin": "toy", "status": "ok", "files": ["a"]}


@pytest.mark.parametrize("outcome", ["failed-status", "refusal"])
def test_a_failed_build_exits_non_zero_with_its_reason(monkeypatch, tmp_path, capsys, outcome):
    def builder(context, out, **kwargs):
        if outcome == "refusal":
            raise ValueError("no such solver")
        return {"status": "failed", "diagnostics": []}

    _declare(monkeypatch, builder)

    assert cli.main(["build", "--plugin", "toy", "--out", str(tmp_path / "case")]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "failed"
    assert outcome != "refusal" or report["error"] == "no such solver"


def test_a_plugin_without_a_builder_and_a_repeated_name_are_refused_in_the_one_json_shape(monkeypatch, tmp_path, capsys):
    _declare(monkeypatch, lambda *a, **k: {"status": "ok"})

    for argv, fragment in (
        (["--plugin", "other", "--out", str(tmp_path)], "declares no case builder"),
        (["--plugin", "toy", "--out", str(tmp_path), "--select", "a=1", "--select", "a=2"], "each NAME once"),
        (["--plugin", "toy"], "--out"),
    ):
        assert cli.main(["build", *argv]) == 1
        report = json.loads(capsys.readouterr().out)
        assert report["status"] == "failed" and report["action"] == "build" and fragment in report["error"]
