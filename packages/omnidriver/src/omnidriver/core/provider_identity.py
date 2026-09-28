"""Identity over a composed stack of providers, not a single plugin.

Two different stacks must never produce the same provenance record; the
digest here is what makes a run reproducible.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

#: The keys ``stack_identity_mismatch`` compares. ``capability_digest`` alone
#: is necessary and sufficient to detect a real mismatch: it changes whenever
#: the stack (which providers, their versions, their order) or the
#: composition result changes. ``composition_rule_version``/``resolutions``
#: add no detection power on top of it, but let a diagnostic name which
#: aspect of the stack moved -- the specificity the retired single-plugin
#: id/version/api_version comparison gave. ``providers`` is deliberately
#: EXCLUDED: each entry embeds ``source`` (an install/import path), and
#: comparing it wholesale would flag reloading the same provider from a
#: different source as a mismatch, which it is not.
STACK_IDENTITY_COMPARISON_KEYS = ("composition_rule_version", "capability_digest", "resolutions")

#: Bumped whenever a composition rule in `provider_stack` changes meaning.
#: Without it, the same providers at the same versions would digest
#: identically across a semantic change core made -- the one case no other
#: element of the digest covers. A digest computed under a different version
#: is not comparable.
COMPOSITION_RULE_VERSION = "2"


@dataclass(frozen=True)
class ProviderIdentity:
    """What `PluginIdentity` was, now one per provider."""

    id: str
    version: str
    api_version: str
    source: str
    provider_digest: str

    def to_json(self) -> dict[str, str]:
        return {
            "id": self.id,
            "version": self.version,
            "api_version": self.api_version,
            "source": self.source,
            "provider_digest": self.provider_digest,
        }


@dataclass(frozen=True)
class StackIdentity:
    """Identity of a composed stack.

    `resolutions` maps each capability to the provider that answered it. It is
    what lets a provenance record say WHICH adapter answered -- which the
    single-plugin identity could not.
    """

    providers: tuple[ProviderIdentity, ...]
    composition_rule_version: str
    capability_digest: str
    resolutions: dict[str, str]

    def to_json(self) -> dict:
        return {
            "providers": [p.to_json() for p in self.providers],
            "composition_rule_version": self.composition_rule_version,
            "capability_digest": self.capability_digest,
            "resolutions": dict(sorted(self.resolutions.items())),
        }


def build_stack_identity(
    *,
    providers: tuple[ProviderIdentity, ...],
    resolutions: dict[str, tuple[str, str]],
    composition_rule_version: str = COMPOSITION_RULE_VERSION,
) -> StackIdentity:
    """Hash the composition RESULT, not merely its inputs.

    `resolutions` is capability -> (winning provider id, that capability's
    resolved-content digest). Only the three capabilities the single-plugin
    digest already covered carry a real content digest; the rest carry a
    placeholder and contribute only their winner.

    Known limit: a content change inside a non-digested capability, in an
    editable install with no version bump, is invisible here. See spec §4.4.
    """
    payload = {
        "composition_rule_version": composition_rule_version,
        "providers": [
            [p.id, p.version, p.provider_digest] for p in providers
        ],
        "resolutions": [
            [capability, winner, content]
            for capability, (winner, content) in sorted(resolutions.items())
        ],
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return StackIdentity(
        providers=providers,
        composition_rule_version=composition_rule_version,
        capability_digest=digest,
        resolutions={
            capability: winner for capability, (winner, _) in resolutions.items()
        },
    )


def stack_identity_mismatch(planned: Mapping[str, Any], selected: Mapping[str, Any]) -> list[str]:
    """The ``STACK_IDENTITY_COMPARISON_KEYS`` on which two ``StackIdentity.to_json()``
    payloads disagree, empty when they agree on every one.

    This is the rule for *plan/run/compare* stack binding only --
    ``run_document_exec.build_execution_inputs``, ``cli.py``'s
    ``_context_from_run_document``, and ``quantities.comparison._resolve_run``
    all call this rather than each keeping its own copy of the key list and
    reasoning, which would risk comparing full provider records (``source``
    included) and refusing two same-content stacks loaded from different
    import paths -- not a real mismatch. *Resume* is a separate, deliberately
    stricter rule -- see ``runtime.provenance.compare`` and
    ``runtime.resume.checkpoint_snapshot``.
    """
    return [key for key in STACK_IDENTITY_COMPARISON_KEYS if planned.get(key) != selected.get(key)]
