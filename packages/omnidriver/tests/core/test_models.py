from __future__ import annotations

import dataclasses

from omnidriver.core.runtime.models import TutorialSpec


def test_tutorial_spec_no_longer_has_a_collect_outputs_field():
    # Nothing in the runtime calls a collect_outputs field, so TutorialSpec
    # carries none.
    field_names = {f.name for f in dataclasses.fields(TutorialSpec)}
    assert "collect_outputs" not in field_names
