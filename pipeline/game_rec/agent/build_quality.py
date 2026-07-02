"""Build a per-game QUALITY artifact from user review scores (D2).

Diagnostic finding: metacritic covers only 30.5% of the pool; the user-score
aggregate covers 86.6%. This builds a Bayesian-shrunk per-game quality from
s_round10_rec so quality_gate has a dense signal instead of a 30%-coverage one.

Shrinkage: q = (n·mean + m·global_mean) / (n + m). With m≈20 this stops
1-review games from scoring extreme; the shrunk signal rank-correlates with
metacritic at spearman≈0.37 (validated, sanity) while covering ~3× more games.

Output: serving/data/game_quality.json
  {global_mean, prior_m, games: {appid: {q, n, raw}}}
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from pipeline.game_rec.io import load_index_maps  # noqa: E402
from pipeline.game_rec.log import get_logger  # noqa: E402

log = get_logger("game_rec.agent.build_quality")


def build_quality_artifact(scores_path: Path, data_dir: Path, out_path: Path,
                           prior_m: float = 20.0) -> dict:
    pool = set(int(a) for a in load_index_maps(data_dir / "index_maps.json")["appid2row"].keys())
    ssum: dict[int, float] = collections.defaultdict(float)
    scnt: collections.Counter = collections.Counter()
    allv: list[float] = []
    with open(scores_path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            try:
                a = int(row["appid"]); s = float(row["s_round10_rec"])
            except (TypeError, ValueError, KeyError):
                continue
            if a not in pool or not np.isfinite(s):
                continue
            ssum[a] += s; scnt[a] += 1; allv.append(s)
    gmean = float(np.mean(allv)) if allv else 0.0
    games = {}
    for a in scnt:
        n = scnt[a]; raw = ssum[a] / n
        q = (n * raw + prior_m * gmean) / (n + prior_m)
        games[str(a)] = {"q": round(q, 4), "n": int(n), "raw": round(raw, 4)}
    out = {"global_mean": round(gmean, 4), "prior_m": prior_m, "games": games}
    out_path.write_text(json.dumps(out), encoding="utf-8")
    log.info("quality artifact -> %s | games=%d/%d (%.1f%%) gmean=%.3f",
             out_path, len(games), len(pool), 100 * len(games) / len(pool), gmean)
    return {"n_games": len(games), "pool": len(pool), "global_mean": gmean}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scores", type=Path, default=REPO_ROOT / "outputs" / "user_game_scores.csv")
    ap.add_argument("--data-dir", type=Path, default=REPO_ROOT / "serving" / "data")
    ap.add_argument("--out", type=Path, default=REPO_ROOT / "serving" / "data" / "game_quality.json")
    ap.add_argument("--prior-m", type=float, default=20.0)
    a = ap.parse_args()
    print(build_quality_artifact(a.scores, a.data_dir, a.out, a.prior_m))
    return 0


if __name__ == "__main__":
    sys.exit(main())
