"""Lightweight logging helper.

Use `get_logger(__name__)` at the top of each module. The first call
installs a single stderr handler with a stable format; subsequent calls
reuse the same root configuration so log lines from different modules
look consistent.
"""

from __future__ import annotations

import logging
import sys


_DEFAULT_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DEFAULT_LEVEL = logging.INFO


def _configure_root() -> None:
    root = logging.getLogger()
    if any(getattr(h, "_game_rec_handler", False) for h in root.handlers):
        return  # already configured by us
    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(logging.Formatter(_DEFAULT_FORMAT))
    handler._game_rec_handler = True  # type: ignore[attr-defined]
    root.addHandler(handler)
    root.setLevel(_DEFAULT_LEVEL)


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger for the given dotted name."""
    _configure_root()
    return logging.getLogger(name)
