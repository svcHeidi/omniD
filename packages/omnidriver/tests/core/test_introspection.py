"""Core introspection guarantees."""

from __future__ import annotations

import json
import stat

from omnidriver.core.introspection import _run_state_schema


def test_run_state_schema_does_not_advertise_unwritten_action_events_file() -> None:
    schema = _run_state_schema()
    assert "companion_file" not in schema
    assert "action_events.jsonl" not in json.dumps(schema)
