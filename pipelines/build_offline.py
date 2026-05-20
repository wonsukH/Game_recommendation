"""Run the full offline pipeline end-to-end.

Each game_rec submodule is callable as `python -m game_rec.<sub>.<mod>`.
This script chains them in order, stops on first failure, and prints a
final summary. It's a thin orchestrator — all real logic lives in the
called modules. Hyperparameters come from config/default.yaml.

Usage:
    python -m pipelines.build_offline
    python -m pipelines.build_offline --skip-text-alignment   # for envs without Solar key
    python -m pipelines.build_offline --version v2 --backup
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
from game_rec.log import get_logger  # noqa: E402

log = get_logger("pipelines.build_offline")


@dataclass(frozen=True)
class Stage:
    module: str
    description: str
    args: tuple[str, ...] = ()


STAGES: tuple[Stage, ...] = (
    Stage("game_rec.data.user_scores",      "user_all_reviews -> user_game_scores"),
    Stage("game_rec.data.tag_vocab",        "normalize tags -> tag_vocab.json"),
    Stage("game_rec.data.game_tag_matrix",  "build Game x Tag CSR + index_maps"),
    Stage("game_rec.data.game_weights",     "MinMax + gamma -> game_weight.npy"),
    Stage("game_rec.models.tag_embeddings", "PPMI + TruncatedSVD -> tag_vecs.npy"),
    Stage("game_rec.models.tag_effects",    "Ridge regression -> tag_beta.npy"),
    Stage("game_rec.models.game_vectors",   "synthesize game vectors -> game_vecs.npy"),
    Stage("game_rec.models.text_alignment", "Ridge W_align -> W_align.npy"),
    Stage("game_rec.index.faiss_index",     "build FAISS IndexFlatL2"),
    Stage("game_rec.evaluation.quality",    "quality_report.json"),
)


def run_stage(stage: Stage, extra_args: list[str]) -> int:
    cmd = [sys.executable, "-m", stage.module, *stage.args, *extra_args]
    log.info("--- %s (%s)", stage.module, stage.description)
    log.info("    $ %s", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=REPO_ROOT)
    return proc.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-text-alignment", action="store_true",
        help="Skip game_rec.models.text_alignment (needs UPSTAGE_API_KEY or sentence-transformers).",
    )
    parser.add_argument(
        "--skip-faiss", action="store_true",
        help="Skip game_rec.index.faiss_index (needs faiss-cpu installed).",
    )
    parser.add_argument(
        "--skip-quality", action="store_true",
        help="Skip game_rec.evaluation.quality.",
    )
    args = parser.parse_args()

    skip = set()
    if args.skip_text_alignment:
        skip.add("game_rec.models.text_alignment")
    if args.skip_faiss:
        skip.add("game_rec.index.faiss_index")
    if args.skip_quality:
        skip.add("game_rec.evaluation.quality")

    for stage in STAGES:
        if stage.module in skip:
            log.info("SKIP %s", stage.module)
            continue
        rc = run_stage(stage, extra_args=[])
        if rc != 0:
            log.error("stage failed (exit=%d): %s", rc, stage.module)
            return rc

    log.info("offline pipeline completed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
