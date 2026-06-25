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
from pathlib import Path

from pipeline.game_rec.io import save_stats


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

    def write_report(self, md: str) -> None:
        (self.dir / "report.md").write_text(md, encoding="utf-8")

    def write_text(self, name: str, text: str) -> None:
        (self.dir / name).write_text(text, encoding="utf-8")

    def append_registry(self, summary: dict) -> None:
        reg = self.root / "registry.jsonl"
        reg.parent.mkdir(parents=True, exist_ok=True)
        with open(reg, "a", encoding="utf-8") as f:
            f.write(json.dumps(summary, ensure_ascii=False) + "\n")
