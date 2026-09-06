from dataclasses import replace

from omnidriver.core.runtime.provenance import (
    ProvenanceComponent, compare, snapshot_from_components,
)


def _snapshot(component):
    return snapshot_from_components([component], workflow_digest="workflow", plugin_identity={})


def test_metadata_changes_are_visible_and_never_certify_content():
    before = ProvenanceComponent(
        kind="input", path="large.dat", method="metadata", strength="metadata",
        size=300_000_000, mtime_ns=1,
    )
    old, new = _snapshot(before), _snapshot(replace(before, mtime_ns=2))
    assert not old.is_complete
    assert not new.is_complete
    assert old.aggregate_digest != new.aggregate_digest
    assert len(compare(old, new)) == 1


def test_content_identity_ignores_timestamp_only_changes():
    before = ProvenanceComponent(
        kind="input", path="small.dat", method="sha256", strength="content",
        digest="sha256:unchanged", size=2, mtime_ns=1,
    )
    old, new = _snapshot(before), _snapshot(replace(before, mtime_ns=2))
    assert old.is_complete and new.is_complete
    assert old.aggregate_digest == new.aggregate_digest
    assert compare(old, new) == ()
