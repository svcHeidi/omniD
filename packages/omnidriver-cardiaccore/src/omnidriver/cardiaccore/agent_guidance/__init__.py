"""Read packaged adapter guidance without locating a source checkout."""

from importlib.resources import files

import yaml


def describe_guidance() -> dict:
    """Expose the packaged manifest and role resources through the plugin."""
    manifest = yaml.safe_load(files(__package__).joinpath("manifest.yaml").read_text(encoding="utf-8"))
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
