"""Identity over a composed stack, not a single plugin.

`PluginIdentity` covered one plugin, because `DriverContext` held one. Under
composition two different stacks could otherwise produce the same provenance
record, and the digest is what makes a run reproducible.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

#: Bumped whenever a composition rule in `provider_stack` changes meaning.
#: Without it, the same providers at the same versions would digest
#: identically across a semantic change core made -- the one case no other
#: element of the digest covers.
#:
#: Bumped 2026-09-22: `resolutions()` records the provider that supplied the
#: value under the `single` rule, and `<unclaimed>` where no provider
#: implements the capability at all (audit finding C3). A digest computed
#: before this date is not comparable with one computed after it.
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
    editable install with no version bump, is invisible here. Recorded
    2026-09-20 rather than discovered later; see spec §4.4.
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
