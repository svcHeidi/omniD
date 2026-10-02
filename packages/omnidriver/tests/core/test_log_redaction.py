from __future__ import annotations

from omnidriver.core.runtime.workflow_runner import redact_step_logs


def test_patterns_replace_the_secret_and_nothing_else(tmp_path):
    log = tmp_path / "s.stdout.log"
    log.write_text("*** GIT repo: https://user:SECRET@host/x.git\nTime = 1\n")
    redact_step_logs((log,), (r"(?<=://)[^/\s@]+(?=@)",))
    assert log.read_text() == "*** GIT repo: https://[REDACTED]@host/x.git\nTime = 1\n"


def test_the_whole_match_is_replaced_and_no_capture_group_is_kept_I3(tmp_path):
    log = tmp_path / "s.stdout.log"
    log.write_text("login password=hunter2 ok\nrepo https://user:SECRET@host/x.git\n")
    redact_step_logs((log,), (r"password=(\S+)", r"(https?://)[^/\s@]+(?=@)"))
    text = log.read_text()
    assert "hunter2" not in text and "SECRET" not in text
    assert text == "login [REDACTED] ok\nrepo [REDACTED]@host/x.git\n"


def test_no_patterns_leave_the_file_untouched(tmp_path):
    log = tmp_path / "s.stdout.log"
    log.write_text("x\n")
    before = log.stat().st_mtime_ns
    redact_step_logs((log,), ())
    assert log.stat().st_mtime_ns == before


def test_a_plugin_declared_pattern_redacts_the_real_workflow_runner_s_kept_log(tmp_path):
    """Runs through the real workflow runner (conformance C6), not a direct call to `redact_step_logs`, so a wiring mistake there is still caught."""
    from omnidriver.conformance import run_check
    from plugins.toy import FAKE_CREDENTIAL_URL, LOG_REDACTION_PLUGIN, toy_conformance_target

    target = toy_conformance_target(tmp_path, plugin=LOG_REDACTION_PLUGIN)
    verdict = run_check("C6", target)
    assert verdict.passed, verdict.detail

    logs = list(target.scratch_root.rglob("workflow_logs/*.log"))
    assert logs, "C6 wrote no step logs"
    contents = [p.read_text(errors="ignore") for p in logs]
    assert any("[REDACTED]" in text for text in contents)
    assert not any("SECRET" in text for text in contents)
    assert not any(FAKE_CREDENTIAL_URL in text for text in contents)
