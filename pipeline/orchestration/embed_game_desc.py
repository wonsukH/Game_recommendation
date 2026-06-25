"""Embed game DESCRIPTIONS in Gemini space — the "skip tags entirely" baseline.

This builds the decisive comparison for "do tags earn their place?": if a pure
LLM embedding of each game's natural-language description lets us match
query -> games directly (no tag vocabulary, no vote weighting, no custom
embedding) as well as routing through the vote-weighted tag layer, then the
whole tag thesis of the project is redundant.

Caches game_desc_vecs.npy (n_games x 3072) aligned to index_maps row order,
so the Vf retriever can cosine query-embeddings against it directly.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

import numpy as np
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from langchain_google_genai import GoogleGenerativeAIEmbeddings  # noqa: E402
from pipeline.game_rec.io import load_index_maps  # noqa: E402
from pipeline.game_rec.log import get_logger  # noqa: E402

log = get_logger("orchestration.embed_game_desc")


def load_descriptions(appdetails: Path, row2appid: dict) -> list[str]:
    """One description string per row (aligned to index_maps order).

    Falls back to name + genres when short_description is missing, so every
    game gets *some* natural-language text (never tags — this is the no-tag arm).
    """
    by_appid = {}
    with open(appdetails, encoding="utf-8-sig") as f:
        r = csv.DictReader(f)
        for row in r:
            try:
                appid = int(row.get("appid") or row.get("﻿appid") or 0)
            except (TypeError, ValueError):
                continue
            desc = (row.get("short_description") or "").strip()
            if not desc:
                name = (row.get("name") or "").strip()
                genres = (row.get("genres") or "").strip()
                desc = f"{name}. {genres}".strip(". ")
            by_appid[appid] = desc or (row.get("name") or "unknown game")
    n = len(row2appid)
    out = []
    missing = 0
    for i in range(n):
        a = row2appid[i]
        d = by_appid.get(a)
        if not d:
            d = "unknown game"
            missing += 1
        out.append(d)
    log.info("descriptions aligned: %d rows, %d missing->placeholder", n, missing)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--appdetails", type=Path, default=REPO_ROOT / "outputs" / "steam_appdetails.csv")
    ap.add_argument("--data-dir", type=Path, default=REPO_ROOT / "serving" / "data")
    ap.add_argument("--out", type=Path, default=REPO_ROOT / "experiments" / "game_desc_vecs.npy")
    ap.add_argument("--batch", type=int, default=64)
    args = ap.parse_args()

    load_dotenv(REPO_ROOT / ".env")
    maps = load_index_maps(args.data_dir / "index_maps.json")
    row2appid = maps["row2appid"]
    descs = load_descriptions(args.appdetails, row2appid)

    emb = GoogleGenerativeAIEmbeddings(
        model=os.environ.get("GEMINI_EMBEDDING_MODEL", "models/gemini-embedding-2"),
        google_api_key=os.environ["GEMINI_API_KEY"],
    )
    vecs = []
    n = len(descs)
    for s in range(0, n, args.batch):
        chunk = [d[:2000] for d in descs[s:s + args.batch]]  # cap length
        vecs.extend(emb.embed_documents(chunk))
        log.info("embedded %d/%d", min(s + args.batch, n), n)
    arr = np.asarray(vecs, dtype=np.float32)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    np.save(args.out, arr)
    log.info("saved game_desc_vecs %s -> %s", arr.shape, args.out)
    print(f"saved {arr.shape} -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
