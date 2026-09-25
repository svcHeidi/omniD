#!/usr/bin/env python3
"""Regenerate packages/omnidriver-opencarp/.../opencarp_parameters.json from the
installed openCARP (needs DYLD_LIBRARY_PATH on macOS). The native drift test
fails until the committed file matches the binary."""
import json
from pathlib import Path

from omnidriver.opencarp.catalog_generation import build_catalog

TARGET = Path(__file__).resolve().parents[1] / "packages/omnidriver-opencarp/src/omnidriver/opencarp/opencarp_parameters.json"
TARGET.write_text(json.dumps(build_catalog(), indent=1, sort_keys=True) + "\n")
print(f"wrote {TARGET}")
