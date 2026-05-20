"""Prompt loader.

Prompts live in `<repo>/prompts/<name>.txt` so they can be edited and
version-controlled independently of the Python code that consumes them.
"""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PROMPTS_DIR = REPO_ROOT / "prompts"


def load_prompt(name: str) -> str:
    """Return the contents of prompts/<name>.txt as a single string.

    Caller is responsible for wrapping in a langchain PromptTemplate or
    similar — this just gives the raw template text.
    """
    p = PROMPTS_DIR / f"{name}.txt"
    return p.read_text(encoding="utf-8")
