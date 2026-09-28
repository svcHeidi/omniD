"""Read packaged adapter guidance without locating a source checkout."""

from copy import deepcopy
from functools import lru_cache
from importlib.resources import files

import yaml


@lru_cache(maxsize=1)
def _load_manifest() -> dict:
    """Parse the guidance manifest once per process: cheap for
    `describe_guidance`'s current per-catalog-listing caller, not for a
    hypothetical per-step caller."""
    return yaml.safe_load(files(__package__).joinpath("manifest.yaml").read_text(encoding="utf-8"))


def describe_guidance() -> dict:
    """Expose the packaged manifest and role resources through the plugin."""
    manifest = deepcopy(_load_manifest())
    return {
        **manifest,
        "package": __package__,
        "manifest": "agent_guidance/manifest.yaml",
        "reader": "omnidriver.cardiaccore.agent_guidance:read_guidance",
        **{role: f"agent_guidance/{entry['resource']}" for role, entry in manifest["roles"].items()},
    }


def read_guidance(role: str) -> str:
    """Read one declared role. Unknown roles fail rather than select a default."""
    roles = describe_guidance()["roles"]
    if role not in roles:
        raise ValueError(f"Unknown cardiacCore guidance role {role!r}; choose {', '.join(roles)}")
    return files(__package__).joinpath(roles[role]["resource"]).read_text(encoding="utf-8")
