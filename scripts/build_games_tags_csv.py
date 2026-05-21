"""Build steam_games_tags.csv from steamspy_games.csv + index_maps.json.

The legacy baseline produced steam_games_tags.csv directly from Selenium
crawl; the new SteamSpy crawler stores raw data in steamspy_games.csv
(with tags as a JSON dict). The retriever still expects steam_games_tags.csv
with columns (appid, game_title, tags, tag_count) ordered to match
index_maps.json's row2appid mapping.

This script reconciles those: it iterates index_maps's row order, looks up
SteamSpy data per appid, and writes a normalized CSV.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]


def normalize_tag(tag: str) -> str:
    t = unicodedata.normalize("NFKC", str(tag)).lower().strip()
    t = re.sub(r"[/\s]+", "-", t)
    t = re.sub(r"-+", "-", t)
    return t


def _parse_tags_json(raw) -> dict:
    if not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        import ast
        try:
            v = ast.literal_eval(raw)
            return v if isinstance(v, dict) else {}
        except (ValueError, SyntaxError):
            return {}


def main() -> None:
    spy_path = REPO_ROOT / "outputs" / "steamspy_games.csv"
    imap_path = REPO_ROOT / "outputs" / "index_maps.json"
    out_path = REPO_ROOT / "outputs" / "steam_games_tags.csv"

    spy = pd.read_csv(spy_path)
    imap = json.loads(imap_path.read_text(encoding="utf-8"))
    row2appid = imap["row2appid"]
    items = sorted(((int(k), v) for k, v in row2appid.items()), key=lambda x: x[0])
    ordered_appids = [v for _, v in items]

    spy_indexed = spy.set_index("appid")
    missing = 0
    rows = []
    for appid in ordered_appids:
        if appid not in spy_indexed.index:
            missing += 1
            continue
        r = spy_indexed.loc[appid]
        tags_dict = _parse_tags_json(r.get("tags_json"))
        tag_names = [normalize_tag(t) for t in tags_dict.keys()]
        rows.append({
            "appid": appid,
            "game_title": r["name"],
            "tags": ",".join(tag_names),
            "tag_count": len(tag_names),
        })

    df = pd.DataFrame(rows)
    df.to_csv(out_path, index=False)
    print(f"wrote {len(df)} rows to {out_path}")
    if missing:
        print(f"warning: {missing} appids from index_maps not found in steamspy_games.csv")


if __name__ == "__main__":
    main()
