"""A provider declares what it provides and what it layers on."""

import pytest
import yaml

from omnidriver.core import plugin_profile


def _profile(tmp_path, payload):
    path = tmp_path / "plugin.yaml"
    path.write_text(yaml.safe_dump(payload))
    return plugin_profile.load_plugin_profile(path)


BASE = {
    "schema_version": 1,
    "plugin": {"id": "org.example.thing", "api_version": "2"},
    "case_profile": {"dictionaries": []},
}


def test_provides_and_requires_default_to_empty(tmp_path):
    profile = _profile(tmp_path, dict(BASE))
    assert profile.provides == frozenset()
    assert profile.requires == ()


def test_provides_is_read(tmp_path):
    payload = dict(BASE, provides=["command_authorization", "case_files"])
    profile = _profile(tmp_path, payload)
    assert profile.provides == frozenset({"command_authorization", "case_files"})


def test_requires_preserves_order(tmp_path):
    payload = dict(BASE, requires=["org.omnidriver.openfoam", "org.example.mid"])
    profile = _profile(tmp_path, payload)
    assert profile.requires == ("org.omnidriver.openfoam", "org.example.mid")


def test_provides_rejects_an_unknown_capability(tmp_path):
    payload = dict(BASE, provides=["not_a_capability"])
    with pytest.raises(ValueError, match="not_a_capability"):
        _profile(tmp_path, payload)
