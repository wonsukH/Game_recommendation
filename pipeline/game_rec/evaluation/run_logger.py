"""Append-only experiment logging — never overwrite, always fingerprint.

The old eval scripts overwrote outputs/llm_vs_system.{csv,md} every run, so
slide numbers drifted away from what the shipped artifacts produce and could
not be traced back. This logger fixes that:

- one append-only `experiments/registry.jsonl` (one line per run)
- one `experiments/<run_id>/` dir per run holding manifest (config +
  artifact sha256 fingerprints), per-query CSV, aggregate JSON, report.md
- refuses to clobber an existing run_id

Artifact fingerprints matter here because there are many game_vecs_*.npy
variants; the manifest records exactly which bytes produced each number.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from pipeline.game_rec.io import save_stats


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def fingerprint(path: str | Path) -> dict:
    """sha256 + size for an artifact file (so a run is traceable to bytes)."""
    p = Path(path)
    if not p.exists():
        return {"path": str(p), "exists": False}
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return {"path": str(p), "exists": True, "sha256": h.hexdigest()[:16], "bytes": p.stat().st_size}


class RunLogger:
    def __init__(self, run_id: str, out_root: str | Path):
        self.run_id = run_id
        self.root = Path(out_root)
        self.dir = self.root / run_id
        if self.dir.exists():
            raise FileExistsError(f"run dir already exists, refusing to overwrite: {self.dir}")
        self.dir.mkdir(parents=True)

    def write_manifest(self, manifest: dict) -> None:
        save_stats(manifest, self.dir / "manifest.json")

    def write_per_query(self, df) -> None:
        df.to_csv(self.dir / "per_query.csv", index=False, encoding="utf-8")

    def write_aggregate(self, agg: dict) -> None:
        save_stats(agg, self.dir / "aggregate.json")

    def write_report(self, md: str, decision: str | None = None) -> None:
        """Write report.md, auto-injecting the STYLEGUIDE meta-block right after
        the first H1 (answer-first: an optional `결정(TL;DR)` line on top). Callers
        keep building their own body; this just standardizes the header so a future
        agent can read the verdict + run/status in the first lines. Idempotent: skips
        injection if a meta-block is already present."""
        lines = md.split("\n")
        out, injected = [], False
        for i, ln in enumerate(lines):
            out.append(ln)
            has_meta = any(l.lstrip().startswith("> **유형**") for l in lines[i + 1:i + 4])
            if not injected and ln.startswith("# ") and not has_meta:
                block = ["", f"> **유형**: experiment-report · **상태**: active · "
                             f"**run**: `{self.run_id}` · **갱신**: {_today()}"]
                if decision:
                    block.append(f"> **결정(TL;DR)**: {decision}")
                out.extend(block)
                injected = True
        (self.dir / "report.md").write_text("\n".join(out), encoding="utf-8")

    def write_text(self, name: str, text: str) -> None:
        (self.dir / name).write_text(text, encoding="utf-8")

    def append_registry(self, summary: dict) -> None:
        reg = self.root / "registry.jsonl"
        reg.parent.mkdir(parents=True, exist_ok=True)
        with open(reg, "a", encoding="utf-8") as f:
            f.write(json.dumps(summary, ensure_ascii=False) + "\n")

    def append_deliberation(self, topic: str, body: str) -> None:
        """Append a standardized entry to DELIBERATION_LOG.md (append-only):
        `## (<topic>) — run <run_id>` + body. Uniform header across all
        orchestration scripts so the log stays scannable. Does not rewrite history."""
        dlog = self.root / "DELIBERATION_LOG.md"
        if not dlog.exists():
            return
        entry = f"\n\n## ({topic}) — run `{self.run_id}`\n{body.rstrip()}\n"
        with open(dlog, "a", encoding="utf-8") as f:
            f.write(entry)
