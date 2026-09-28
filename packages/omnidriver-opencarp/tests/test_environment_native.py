"""openCARP's preflight against the real binary: the version guard (final
review S-M3). The catalogue the validator certifies keys against is pinned to
one openCARP build; a different binary is warned about, naming both tags.
No second binary is needed: the test patches the catalogue's identity."""
from __future__ import annotations

import os
import shutil

import pytest

from omnidriver.opencarp import environment
from omnidriver.opencarp.catalog import Catalog, load_catalog
from opencarp_native import require_opencarp_binary

pytestmark = pytest.mark.native_opencarp

_DAG = {"steps": [{"command": "openCARP"}]}


def _env() -> dict[str, str]:
    require_opencarp_binary()
    return dict(os.environ)


def test_the_committed_catalogue_matches_the_binary_so_no_version_warning():
    diagnostics = environment.opencarp_environment_diagnostics(_DAG, _env())
    assert [d for d in diagnostics if d.code == "opencarp_version_mismatch"] == []
    assert [d for d in diagnostics if d.level == "error"] == []


def test_a_binary_whose_tag_differs_from_the_catalogue_is_warned_naming_both(monkeypatch):
    env = _env()
    real = load_catalog()
    patched = Catalog(identity={**real.identity, "tag": "v0.0-catalogue"}, parameters=real.parameters)
    monkeypatch.setattr(environment, "load_catalog", lambda: patched)
    diagnostics = environment.opencarp_environment_diagnostics(_DAG, env)
    warnings = [d for d in diagnostics if d.code == "opencarp_version_mismatch"]
    assert len(warnings) == 1, diagnostics
    assert warnings[0].level == "warning"
    assert f"'{real.identity['tag']}'" in warnings[0].message
    assert "'v0.0-catalogue'" in warnings[0].message
    assert [d for d in diagnostics if d.level == "error"] == []
    assert shutil.which("openCARP", path=env.get("PATH", ""))


def test_the_declared_shell_checks_clean_in_the_native_shape():
    """Added 2026-09-28: ``omnidriver env --plugin opencarp`` over the real
    binary and launcher, in the shell this shape runs in (its MPI first on
    PATH, the library path and, here, HYDRA_IFACE supplied)."""
    from omnidriver.core.environment_connection import environment_report
    from omnidriver.core.plugin_interface import load_plugin_context

    report = environment_report(load_plugin_context("opencarp"), _env())
    assert report["status"] == "ok", report["preflight"]
    assert report["launcher"]["path"] is not None
    assert report["commands"]["openCARP"] is not None
