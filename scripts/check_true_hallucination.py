"""Cross-check LLM-recommended games against Steam Storefront API.

Computes:
  - Pool Coverage Miss Rate: % of LLM raw recs that aren't in our pool (9956)
  - True Hallucination Rate: % of LLM raw recs that don't exist on Steam at all

Pool miss != hallucination — a game might exist on Steam but be outside our
(SteamSpy popularity top ~10K) pool.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd
import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
CSV = REPO_ROOT / "outputs" / "llm_vs_system.csv"
OUT = REPO_ROOT / "outputs" / "true_hallucination.md"


def _split(s):
    if not isinstance(s, str) or not s.strip():
        return []
    return [t.strip() for t in s.split("|") if t.strip() and t.strip().lower() != "nan"]


def steam_exists(title: str, retries: int = 2) -> bool | None:
    """Returns True if Steam Storefront search returns any hit. None on error."""
    url = "https://store.steampowered.com/api/storesearch/"
    params = {"term": title, "l": "english", "cc": "US"}
    for _ in range(retries):
        try:
            r = requests.get(url, params=params, timeout=15)
            if r.status_code == 200:
                data = r.json()
                return int(data.get("total", 0)) > 0
        except Exception as e:
            print(f"  [err] {title}: {e}", file=sys.stderr)
        time.sleep(2)
    return None


def main():
    df = pd.read_csv(CSV)
    print(f"Loaded {len(df)} eval rows")

    # 1) Build set of LLM raw recs that aren't in matched (= out-of-pool)
    pool_miss = []
    all_raw = []
    for _, r in df.iterrows():
        raw = _split(r.get("llm_top5_raw"))
        matched = set(_split(r.get("llm_top5_matched")))
        all_raw.extend(raw)
        for game in raw:
            # heuristic: exact title not in matched -> pool miss
            # (matched may differ in casing; use lower for safety)
            if game.lower() not in {m.lower() for m in matched}:
                pool_miss.append({"query_id": r["query_id"], "title": game})

    total_recs = len(all_raw)
    n_pool_miss = len(pool_miss)
    print(f"\nTotal LLM raw recs: {total_recs}")
    print(f"Pool miss (not in our pool 9956): {n_pool_miss} ({n_pool_miss/total_recs*100:.1f}%)")

    if not pool_miss:
        print("\nNo pool-miss games to verify. True hallucination rate = 0%.")
        OUT.write_text("# True Hallucination Check\n\nNo pool-miss games. True hallucination rate = 0%.\n",
                       encoding="utf-8")
        return

    # 2) For each pool-miss game, verify via Steam Search API
    print(f"\nVerifying {n_pool_miss} pool-miss games against Steam Storefront API...")
    results = []
    for i, item in enumerate(pool_miss, 1):
        exists = steam_exists(item["title"])
        results.append({**item, "steam_exists": exists})
        marker = "✓" if exists else ("✗" if exists is False else "?")
        print(f"  [{i}/{n_pool_miss}] {marker}  {item['title']}")
        time.sleep(0.4)  # polite rate limit

    out_df = pd.DataFrame(results)
    out_df.to_csv(REPO_ROOT / "outputs" / "true_hallucination.csv", index=False)

    n_exist = (out_df["steam_exists"] == True).sum()
    n_hallu = (out_df["steam_exists"] == False).sum()
    n_unknown = out_df["steam_exists"].isna().sum()

    print("\n=== Summary ===")
    print(f"Pool miss            : {n_pool_miss} / {total_recs} = {n_pool_miss/total_recs*100:.2f}%")
    print(f"  Exists on Steam    : {n_exist} (실존, hallucination 아님)")
    print(f"  True hallucination : {n_hallu} ({n_hallu/total_recs*100:.2f}% of all recs)")
    print(f"  Unknown (api err)  : {n_unknown}")

    # Markdown report
    lines = [
        "# True Hallucination Check — Steam Storefront cross-check\n",
        f"- 평가 전체 LLM 추천: **{total_recs}**\n",
        f"- 우리 풀(9956) 외부 추천 (Pool Miss): **{n_pool_miss} ({n_pool_miss/total_recs*100:.2f}%)**\n",
        f"  - Steam에 실존 (단지 우리 풀 밖): **{n_exist}**\n",
        f"  - **진짜 hallucination (Steam에도 없음): {n_hallu} ({n_hallu/total_recs*100:.2f}%)**\n",
        f"  - 확인 불가 (API error): {n_unknown}\n",
        "\n## 상세\n",
        out_df.to_markdown(index=False),
    ]
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nSaved: {OUT}")


if __name__ == "__main__":
    main()
