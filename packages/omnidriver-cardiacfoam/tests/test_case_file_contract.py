"""Required case files the cardiac plugin declares.

Moved from packages/omnidriver/tests/core/test_case_file_contract.py: this
names the cardiac plugin's own required dictionaries
(``electroProperties``, ``physicsProperties``) -- cardiac vocabulary, not a
property of core's case-file-contract mechanism. The generic-plugin test in
that file (which already passed without cardiacfoam installed) and the
always/conditional split test (reworked there to use a minimal non-cardiac
fixture) both stayed in core.
"""

from __future__ import annotations

from omnidriver.core.plugin_interface import default_driver_context


def test_cardiac_required_files_include_its_dictionaries() -> None:
    contract = default_driver_context().capabilities.case_files
    required = contract.required_files()
    assert "constant/electroProperties" in required
    assert "constant/physicsProperties" in required
    assert "system/controlDict" in required
