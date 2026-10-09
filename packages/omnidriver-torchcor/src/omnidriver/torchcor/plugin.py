"""TorchCorPlugin: TorchCor as one self-contained provider."""
from __future__ import annotations

from importlib import resources

from omnidriver.core.plugin_profile import load_plugin_profile


class TorchCorPlugin:
    plugin_name = "TorchCor"
    plugin_id = "org.omnidriver.torchcor"
    plugin_version = "0.1.0"
    plugin_api_version = "3"

    def get_profile(self):
        with resources.as_file(resources.files(__package__).joinpath("torchcor.yaml")) as path:
            return load_plugin_profile(path)
