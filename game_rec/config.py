"""Configuration loader for the pipeline.

`load_config()` returns the parsed YAML as a nested dict. Callers
typically grab a specific section (e.g. `cfg['fe']['step6']`) and pass
its values into argparse defaults. The argparse layer still wins when
the user passes an explicit CLI flag.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "default.yaml"


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Load YAML config. Defaults to <repo>/config/default.yaml."""
    p = Path(path) if path else DEFAULT_CONFIG_PATH
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
