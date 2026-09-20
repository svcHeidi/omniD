"""Parse and render the plugin capability seam table.

This sits beside :mod:`plugin_capabilities` (whose Protocol docstrings are the
single source of truth) and :mod:`compatibility` (which owns the fallbacks a
seam names), because it is a library over both -- not a build script. Each
capability Protocol ends with four fields -- ``:adapts:``, ``:consumed-by:``,
``:fallback:``, ``:status:`` -- whose meaning is documented on
``PluginCapabilities`` itself. There is no parallel registry to drift.

``scripts/export-capability-seams.py`` is a thin CLI over this module, and the
conformance tests in ``tests/core/test_capability_seam_documentation.py`` use
:func:`parse_fields` directly -- one parser, not two.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .specs.paths import repo_root_default


def architecture_path() -> Path:
    """Path to ARCHITECTURE.md in a development checkout.

    A function, not a module constant: ``repo_root_default()`` raises when no
    checkout is found, and evaluating it at import time made this module
    unimportable from an installed wheel. Only the export script calls this,
    and that script only ever runs inside a checkout.
    """
    return repo_root_default() / "ARCHITECTURE.md"


BEGIN_MARKER = "<!-- BEGIN GENERATED: capability-seams -->"
END_MARKER = "<!-- END GENERATED: capability-seams -->"

_FIELD_RE = re.compile(r"^\s*:(?P<name>[a-z-]+):\s*(?P<value>.+?)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class Seam:
    field: str
    protocol: str
    adapts: str
    consumed_by: str
    fallback: str
    status: str


#: The enforcement tier a capability member sits in. Exactly one per member.
#:
#: ``required``          -- ``validate_plugin`` rejects absence; NO fallback
#:                          may exist; the adapter calls unconditionally.
#: ``optional-neutral``  -- probed; the named fallback returns a documented
#:                          neutral value (``False``, ``{}``, ``()``).
#: ``optional-refusing`` -- probed; the named fallback RAISES, naming the hook.
#:                          Correct where a neutral answer would silently
#:                          produce the wrong result rather than no result.
#:
#: Added 2026-09-20. Before this, ``:status:`` was free text and carried
#: ``mandatory``/``optional``/``mixed``, while ``_REQUIRED_PLUGIN_MEMBERS``
#: separately decided enforcement -- so fifteen members were both enforced and
#: probed, and nine ``legacy_*`` fallbacks were unreachable in production.
TIERS: frozenset[str] = frozenset({
    "required",
    "optional-neutral",
    "optional-refusing",
})


def status_tiers(status: str) -> tuple[str, ...]:
    """Extract the tier(s) a seam's raw ``:status:`` text declares.

    Most seams declare exactly one tier and this returns it unchanged. A
    capability whose members genuinely differ (``case_files``,
    ``override_scopes``) cannot declare one tier for the whole seam without
    re-inventing the ``mixed`` free text this closes off -- so it declares
    one ``member=tier`` entry per member instead, comma-separated, e.g.
    ``"get_profile=required, get_config_resolution_description=optional-
    neutral"``. This splits that back into the tiers alone, dropping the
    member name, so :func:`validate_tiers` can check both shapes the same
    way without the caller telling them apart.
    """
    tiers = []
    for part in (p.strip() for p in status.split(",")):
        if not part:
            continue
        tiers.append(part.split("=", 1)[1].strip() if "=" in part else part)
    return tuple(tiers)


def validate_tiers(seams) -> list[str]:
    """Return one problem string per seam whose ``:status:`` is not a tier."""
    return [
        f"capability {seam.field!r} declares :status: {seam.status!r}, "
        f"which is not one of {sorted(TIERS)}"
        for seam in seams
        if any(tier not in TIERS for tier in status_tiers(seam.status))
    ]


def parse_fields(docstring: str | None) -> dict[str, str]:
    """Extract the four structured fields from a capability docstring.

    Continuation lines (an indented line following a field, not itself a
    field) are folded into the preceding field's value, so a long
    ``:consumed-by:`` list may wrap.
    """
    if not docstring:
        return {}
    fields: dict[str, str] = {}
    current: str | None = None
    for line in docstring.splitlines():
        match = _FIELD_RE.match(line)
        if match:
            current = match.group("name")
            fields[current] = match.group("value")
            continue
        stripped = line.strip()
        if current and stripped and line[:1].isspace():
            fields[current] = f"{fields[current]} {stripped}"
            continue
        current = None
    return fields


def collect_seams() -> list[Seam]:
    """Read the seams in the order PluginCapabilities declares its fields."""
    from . import plugin_capabilities as pc

    seams: list[Seam] = []
    for field_name, annotation in pc.PluginCapabilities.__annotations__.items():
        protocol = (
            annotation
            if isinstance(annotation, str)
            else getattr(annotation, "__name__", str(annotation))
        )
        protocol_cls = getattr(pc, protocol, None)
        fields = parse_fields(getattr(protocol_cls, "__doc__", None))
        seams.append(
            Seam(
                field=field_name,
                protocol=protocol,
                adapts=fields.get("adapts", ""),
                consumed_by=fields.get("consumed-by", ""),
                fallback=fields.get("fallback", ""),
                status=fields.get("status", ""),
            )
        )
    return seams


def _cell(value: str) -> str:
    if not value:
        return "—"
    return value.replace("|", r"\|")


def _code_list(value: str) -> str:
    """Render a comma-separated field as inline code, one item per entry."""
    if not value or value.strip() == "none":
        return "none"
    items = [item.strip() for item in value.split(",") if item.strip()]
    return ", ".join(f"`{_cell(item)}`" for item in items)


def render(seams: list[Seam]) -> str:
    lines = [
        BEGIN_MARKER,
        "",
        "<!-- Generated by scripts/export-capability-seams.py -- do not edit by",
        "     hand. The source of truth is the structured field block in each",
        "     capability Protocol's docstring in core/plugin_capabilities.py. -->",
        "",
        "`SolverPlugin` (plus the optional",
        "`SolverPluginOptionalHooks`) in `core/plugin_interface.py` is the **public**",
        "contract a plugin author implements. `PluginCapabilities` in",
        "`core/plugin_capabilities.py` is core's **internal** view *over* a loaded",
        "plugin — it points the opposite way and is not an authoring surface.",
        "",
        "A capability marked `optional-neutral` or `optional-refusing` degrades when",
        "the plugin does not implement its hook: the named `compatibility.py`",
        "fallback runs instead. No fallback branches on plugin identity, so a given",
        "fallback answers the same for every plugin. An `optional-refusing` member's",
        "fallback cannot be neutral and refuses by hook name instead.",
        "",
        "| capability | protocol | adapts | consumed by | fallback | status |",
        "|---|---|---|---|---|---|",
    ]
    for seam in seams:
        lines.append(
            f"| `{seam.field}` | `{seam.protocol}` | {_code_list(seam.adapts)} "
            f"| {_code_list(seam.consumed_by)} | {_code_list(seam.fallback)} "
            f"| {_cell(seam.status)} |"
        )
    lines += ["", f"{len(seams)} capability seams.", "", END_MARKER]
    return "\n".join(lines)


def splice(document: str, table: str) -> str:
    if BEGIN_MARKER in document and END_MARKER in document:
        head = document.split(BEGIN_MARKER)[0]
        tail = document.split(END_MARKER, 1)[1]
        return f"{head}{table}{tail}"
    separator = "" if document.endswith("\n\n") else "\n"
    return f"{document}{separator}\n## Plugin capability seams\n\n{table}\n"
