from __future__ import annotations

from omnidriver.core.runtime.workflow_runner import redact_step_logs


def test_patterns_replace_the_secret_and_nothing_else(tmp_path):
    log = tmp_path / "s.stdout.log"
    log.write_text("*** GIT repo: https://user:SECRET@host/x.git\nTime = 1\n")
    redact_step_logs((log,), (r"(https?://)[^/\s@]+(?=@)",))
    assert log.read_text() == "*** GIT repo: https://[REDACTED]@host/x.git\nTime = 1\n"


def test_no_patterns_leave_the_file_untouched(tmp_path):
    log = tmp_path / "s.stdout.log"
    log.write_text("x\n")
    before = log.stat().st_mtime_ns
    redact_step_logs((log,), ())
    assert log.stat().st_mtime_ns == before


def test_a_plugin_declared_pattern_redacts_the_real_workflow_runner_s_kept_log(tmp_path):
    """K9 end to end: no openCARP plugin exists on this branch (Task 11 is
    still in flight in a sibling worktree), so this exercises the same
    mechanism through a toy plugin whose solve step prints a fake credential
    URL -- standing in for openCARP's build header, which embeds a real CI
    token in every run (G3) -- and declares ``get_log_redaction_patterns``.
    Runs through the real, unmodified workflow runner (conformance C6, the
    same path ``omnidriver run`` takes), not a direct call to
    ``redact_step_logs``, so a wiring mistake in ``workflow_runner`` itself
    would still be caught here."""
    from omnidriver.conformance import run_check
    from plugins.conformance_toy import FAKE_CREDENTIAL_URL, LOG_REDACTION_PLUGIN, toy_conformance_target

    target = toy_conformance_target(tmp_path, plugin=LOG_REDACTION_PLUGIN)
    verdict = run_check("C6", target)
    assert verdict.passed, verdict.detail

    logs = list(target.scratch_root.rglob("workflow_logs/*.log"))
    assert logs, "C6 wrote no step logs"
    contents = [p.read_text(errors="ignore") for p in logs]
    assert any("[REDACTED]" in text for text in contents)
    assert not any("SECRET" in text for text in contents)
    assert not any(FAKE_CREDENTIAL_URL in text for text in contents)
