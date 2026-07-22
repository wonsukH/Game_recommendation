"""Daily-quota guard around the serving LLM (deploy-safe degradation).

The agent graph already wraps every ``llm.invoke`` in try/except with safe
fallbacks (router -> library route, response -> plain title list). This guard
leans on that contract: when the LLM is unavailable (no key) or the daily call
budget is spent, ``invoke`` RAISES and the graph degrades gracefully instead of
dying — recommendations keep working, only NL routing/explanations drop.

The counter persists to a small JSON file (date + count). On ephemeral hosts
(HF Space restart) it resets — acceptable: the true enforcement is Google's own
429, which the same except-paths absorb.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import threading
from pathlib import Path


class LLMUnavailable(RuntimeError):
    """Raised instead of calling the LLM: no key, or daily cap reached."""


class QuotaGuardedLLM:
    def __init__(self, llm, cap: int, state_path: str | Path):
        self._llm = llm
        self.cap = int(cap)
        self._path = Path(state_path)
        self._lock = threading.Lock()

    # ---- state ----
    @property
    def has_llm(self) -> bool:
        return self._llm is not None

    def _today(self) -> str:
        return _dt.date.today().isoformat()

    def _load(self) -> dict:
        try:
            d = json.loads(self._path.read_text())
            if d.get("date") == self._today():
                return d
        except Exception:
            pass
        return {"date": self._today(), "count": 0}

    def used_today(self) -> int:
        return int(self._load().get("count", 0))

    def exhausted(self) -> bool:
        return (not self.has_llm) or self.used_today() >= self.cap

    # ---- the guarded call ----
    def invoke(self, *args, **kwargs):
        if self._llm is None:
            raise LLMUnavailable("no GEMINI_API_KEY — no-LLM mode")
        with self._lock:
            d = self._load()
            if d["count"] >= self.cap:
                raise LLMUnavailable(f"daily LLM quota spent ({self.cap})")
            d["count"] += 1
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                self._path.write_text(json.dumps(d))
            except Exception:
                pass  # counting is best-effort; Google's 429 is the backstop
        return self._llm.invoke(*args, **kwargs)


def build_guarded_llm(data_dir: str | Path) -> QuotaGuardedLLM:
    """Serving factory: optional key -> optional LLM, always a guard."""
    key = os.environ.get("GEMINI_API_KEY")
    llm = None
    if key:
        from langchain_google_genai import ChatGoogleGenerativeAI
        # default flash: the free-tier key has ZERO 2.5-pro quota (P8 finding)
        llm = ChatGoogleGenerativeAI(
            model=os.environ.get("GEMINI_CHAT_MODEL", "gemini-2.5-flash"),
            google_api_key=key, temperature=0.3)
    cap = int(os.environ.get("GEMINI_DAILY_CAP", "150"))
    return QuotaGuardedLLM(llm, cap, Path(data_dir) / "_llm_quota.json")
