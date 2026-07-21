"""P8-C — Gemini cross-judge for the absolute-rubric evaluation (κ).

Re-judges the SAME blinded payloads the Sonnet judges rated (JUDGE_ABS_PREREG
v2 instrument) with a Gemini model, then computes Cohen's κ against the Sonnet
verdicts — the inter-judge reliability check the prereg deferred to an
attended session. Registered interpretation: κ>=0.4 moderate agreement
(instrument trust reinforced); κ<0.2 strengthens the proxy caveat. Either way
the registered 3-arm conclusions are unchanged.

Free-tier aware: direct REST calls, paced; on a daily-quota 429 the run stops
gracefully and records the partial (resume later with --skip-done).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

import requests
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
load_dotenv(REPO_ROOT / ".env")

from pipeline.game_rec.log import get_logger  # noqa: E402

log = get_logger("orchestration.p8_judge_kappa")

DIR = REPO_ROOT / "experiments" / "p6_ood" / "judge_abs"
RATINGS = ("High", "Medium", "Low")

PROMPT = """You are a blinded game-recommendation judge.

Below is ONE case describing a user's taste via three complementary signals — use ALL of them:
- taste_summary_weighted_tags: engagement-weighted tag distribution over the user's WHOLE library
- user_taste: their 8 most-engaged games (name, genres, tags, desc, engagement)
- also_plays: names of additional games they own and play

Then `candidates`: game cards (each with a `slot` number).

For EACH candidate, judge: "How likely is THIS user to be interested in THIS game?" Rate strictly:
- "High" — clear, specific fit with multiple taste signals (not just 'it's a popular game')
- "Medium" — plausible partial fit (one taste signal, or adjacent genre)
- "Low" — no meaningful fit signal

Judge each item independently. Do NOT assume list position means anything. Do NOT favor famous
games because they are famous — judge fit only.

CASE:
%s

Reply with ONLY this JSON (no prose, no markdown fences):
{"0": "High", "1": "Low", ... one entry per candidate slot ...}"""


def call_gemini(model: str, key: str, text: str, max_tries: int = 4):
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:generateContent")
    for i in range(max_tries):
        r = requests.post(url, params={"key": key},
                          json={"contents": [{"parts": [{"text": text}]}],
                                "generationConfig": {"temperature": 0.0}},
                          timeout=120)
        if r.status_code == 200:
            return r.json()["candidates"][0]["content"]["parts"][0]["text"]
        msg = r.json().get("error", {}).get("message", "")[:120]
        if r.status_code == 429 and "PerDay" in r.text:
            raise RuntimeError(f"DAILY QUOTA: {msg}")
        log.warning("HTTP %d (%s) — retry %d", r.status_code, msg, i + 1)
        time.sleep(10 * (i + 1))
    raise RuntimeError(f"gemini call failed after {max_tries} tries")


def parse_verdict(t: str) -> dict:
    s = t[t.find("{"):t.rfind("}") + 1]
    d = json.loads(s)
    return {str(k): v for k, v in d.items() if v in RATINGS}


def cohens_kappa(pairs: list[tuple[str, str]]) -> float:
    n = len(pairs)
    if n == 0:
        return float("nan")
    po = sum(a == b for a, b in pairs) / n
    ca, cb = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    pe = sum((ca[r] / n) * (cb[r] / n) for r in RATINGS)
    return (po - pe) / (1 - pe) if pe < 1 else float("nan")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--payload", default="payload_v2.json")
    ap.add_argument("--sonnet", default="verdicts_v2.json")
    ap.add_argument("--unblind", default="unblind_v2.json")
    ap.add_argument("--out", default="verdicts_gemini_v2.json")
    ap.add_argument("--model", default="gemini-3.1-flash-lite")
    ap.add_argument("--sleep", type=float, default=5.0)
    ap.add_argument("--skip-done", action="store_true")
    args = ap.parse_args()
    key = os.environ["GEMINI_API_KEY"]

    cases = json.loads((DIR / args.payload).read_text(encoding="utf-8"))
    out_path = DIR / args.out
    verdicts = (json.loads(out_path.read_text(encoding="utf-8"))
                if args.skip_done and out_path.exists() else {})
    quota_hit = False
    for case in cases:
        cid = case["case"]
        if cid in verdicts:
            continue
        try:
            txt = call_gemini(args.model, key,
                              PROMPT % json.dumps(case, ensure_ascii=False))
            verdicts[cid] = parse_verdict(txt)
            log.info("%s: %d slots judged", cid, len(verdicts[cid]))
        except RuntimeError as e:
            log.warning("%s: %s — stopping (partial saved)", cid, e)
            quota_hit = True
            break
        except (json.JSONDecodeError, KeyError) as e:
            log.warning("%s: parse fail (%s) — skipped", cid, e)
            verdicts[cid] = {}
        time.sleep(args.sleep)
    out_path.write_text(json.dumps(verdicts, indent=1), encoding="utf-8")

    # ---- kappa vs Sonnet ----
    sonnet = json.loads((DIR / args.sonnet).read_text(encoding="utf-8"))
    unblind = json.loads((DIR / args.unblind).read_text(encoding="utf-8")) \
        if (DIR / args.unblind).exists() else {}
    pairs_all, pairs_by_arm = [], {"ease": [], "pop": [], "rand": []}
    for cid, gv in verdicts.items():
        sv = sonnet.get(cid, {})
        ub = unblind.get(cid, {}).get("slots", {})
        for slot, g in gv.items():
            s = sv.get(slot)
            if s in RATINGS and g in RATINGS:
                pairs_all.append((s, g))
                arm = ub.get(slot, {}).get("arm")
                if arm in pairs_by_arm:
                    pairs_by_arm[arm].append((s, g))
    summary = {
        "model": args.model, "payload": args.payload,
        "n_cases_judged": len([c for c in verdicts.values() if c]),
        "n_pairs": len(pairs_all), "quota_hit_partial": quota_hit,
        "kappa_overall": round(cohens_kappa(pairs_all), 3),
        "agreement_pct": round(100 * sum(a == b for a, b in pairs_all)
                               / max(len(pairs_all), 1), 1),
        "kappa_by_arm": {a: round(cohens_kappa(p), 3)
                         for a, p in pairs_by_arm.items() if p},
        "gemini_rating_dist": dict(Counter(g for _, g in pairs_all)),
        "sonnet_rating_dist": dict(Counter(s for s, _ in pairs_all)),
    }
    (DIR / f"summary_kappa_{Path(args.payload).stem}.json").write_text(
        json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
