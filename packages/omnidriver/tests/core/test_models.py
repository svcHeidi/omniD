from __future__ import annotations

import dataclasses

from omnidriver.core.runtime.models import TutorialSpec


def test_tutorial_spec_no_longer_has_a_collect_outputs_field():
    # collect_outputs was a TutorialSpec field nothing in the runtime ever
    # called (confirmed: zero call sites for .collect_outputs anywhere,
    # zero test references) -- removed together with every tutorial's
    # per-case assignment to it.
    field_names = {f.name for f in dataclasses.fields(TutorialSpec)}
    assert "collect_outputs" not in field_names
