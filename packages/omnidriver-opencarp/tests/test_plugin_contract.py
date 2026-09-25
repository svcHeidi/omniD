from __future__ import annotations

from omnidriver.core.plugin_discovery import load_discovered_plugin


def test_opencarp_stack_is_one_provider_C1():
    ctx = load_discovered_plugin("opencarp")
    assert [p.plugin_id for p in ctx.providers] == ["org.omnidriver.opencarp"]


def test_record_is_registered():
    ctx = load_discovered_plugin("opencarp")
    assert "niedererNVersion" in ctx.capabilities.tutorial_records.catalog()


def test_record_key_catalog_lists_only_addressable_documents_and_keys_I1(tmp_path):
    """Review I1: only a document a record step passes with ``+F`` is read by
    openCARP, and a key the record's command line sets after it is silently
    overridden (F14); neither may be advertised to an agent."""
    from omnidriver.opencarp.plugin import OpenCARPPlugin

    (tmp_path / "nversion.par").write_text("")
    (tmp_path / "foo.par").write_text("")
    entries = OpenCARPPlugin().get_record_key_catalog(tmp_path)
    assert {e["document"] for e in entries} == {"nversion.par"}
    keys = {e["key"] for e in entries}
    assert "gregion[Int].g_il" in keys and "tend" in keys
    assert not keys & {"simID", "meshname", "imp_region[Int].im_sv_init"}
