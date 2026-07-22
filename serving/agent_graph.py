"""Hybrid game-recommendation AGENT (LangGraph) — the validated design.

router (LLM, request-type) --conditional--> {library | seed | multi_entity |
anonymous} recommend node --> filter (constraints + played) --critic/refine
cycle--> response (LLM explanation). Memory via GraphState (Streamlit session).

Engine choices are evidence-grounded (experiments/INDEX.md):
  - library / seed / multi_entity -> CF moat (beats LLM on personalization);
    multi_entity uses INTERLEAVE fusion (validated best, passes the agentic gate).
  - anonymous NL (no library/seed) -> LLM-direct (LLM wins there).
  - constraints verified from real metadata; under-fill triggers a refine cycle.

Uses langchain_core + langchain_google_genai + langgraph only (NOT the legacy
`langchain` meta-package).
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, TypedDict

import numpy as np
import pandas as pd
from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, END

from pipeline.game_rec.agent.tools import played_filter
from pipeline.game_rec.agent.orchestrators import _relax
from pipeline.game_rec.agent.content import ContentLayer
from pipeline.game_rec.agent.hybrid import HybridRecommender
from pipeline.game_rec.agent.baselines import _series_prefix
from pipeline.game_rec.log import get_logger

log = get_logger("serving.agent_graph")

_ROUTER_PROMPT = (
    "You route a Korean game-recommendation request. Output ONLY JSON:\n"
    '{"request_type": one of ["library","seed","multi_entity","explore","anonymous","general"],\n'
    ' "constraints": {"coop":bool,"multiplayer":bool,"single_player":bool,"korean":bool,"free":bool,'
    '"max_price":number|null,"released_after":int|null},\n'
    " (max_price is in KRW won — '2만원'->20000, '$10'->about 14000)\n"
    ' "seed_titles": [OFFICIAL ENGLISH titles of any games mentioned, e.g. 다크소울->"Dark Souls", 엘든링->"Elden Ring"]}\n\n'
    "request_type rules: 'seed' if a specific game is named as a reference; "
    "'multi_entity' if it mentions a friend/another person; 'explore' if the user "
    "wants to BRANCH OUT from their usual taste — a NEW/unexplored genre, something "
    "different/fresh, or more of a SPECIFIC ASPECT they liked (e.g. '안 해본 장르', "
    "'색다른 거', '전투가 좋았는데 다른 분위기', '스토리 위주로 새로운'); 'library' if it asks "
    "for personal recommendations and a library is available; 'anonymous' if it's "
    "a pure vibe/genre request with no reference game; 'general' for chit-chat.\n"
    "has_library=%s, has_friend=%s.\n\nRequest: %s\n\nJSON:"
)

_STEER_PROMPT = (
    "The user wants game recommendations STEERED in a direction, away from their "
    "usual taste. From the Korean request, extract JSON:\n"
    '{"novelty": bool,            // true if they want a NEW/unexplored genre or just "something different"\n'
    ' "novelty_strength": "low"|"medium"|"high",  // how far to push from their taste\n'
    ' "aspect_tags": [str]}       // EXACT tags (from the ALLOWED list) for a specific aspect they liked / want more of; [] if none\n\n'
    "Map liked aspects to tags, e.g. 전투/combat->['combat'], 스토리->['story-rich'], "
    "분위기/아트->['atmospheric'], 어려운->['difficult'], 오픈월드->['open-world']. "
    "Only use tags that appear in ALLOWED.\n"
    "ALLOWED: %s\n\nRequest: %s\n\nJSON:"
)
_STRENGTH_BETA = {"low": 1.0, "medium": 2.0, "high": 2.5}  # validated: b2 maxes new-genre; b3 dominated


class AgentState(TypedDict, total=False):
    user_query: str
    library: Dict[int, float]          # me: appid -> playtime
    friend_library: Dict[int, float]   # optional
    played: List[int]                  # memory: exclude
    k: int
    request_type: str
    constraints: dict
    seed_titles: List[str]
    candidates: List[int]              # ranked pool (pre-filter)
    filtered: List[int]                # post-filter
    refine_iter: int
    relaxed: List[str]
    steer: dict
    final_df: Any
    response: str


def build_agentic_graph(cf, meta, llm, data_dir, max_refine: int = 2):
    df = pd.read_csv(f"{data_dir}/steam_games_tags.csv")
    appid2title = dict(zip(df["appid"].astype(int), df["game_title"].astype(str)))
    title2appid = {str(v).lower(): int(k) for k, v in appid2title.items()}

    # CF moat + content layer (cold-start fallback D1, directional steering F).
    content = ContentLayer(data_dir)
    hybrid = HybridRecommender(cf, content, meta)
    tag_list = ", ".join(content.tag2idx.keys())

    def _interleave(libs: Dict[str, Dict[int, float]], excl: set,
                    cap: int = 600) -> List[int]:
        per = []
        for lib in libs.values():
            acc = cf.score(lib)
            order = np.argsort(-acc)
            # rank the FULL score vector — EASE's negative tail is legitimate
            # signal (T33/T35 cutoff bug; T-a ablation). Cap for cost only.
            ranked = []
            for j in order:
                if not np.isfinite(acc[int(j)]):
                    break
                a = cf.inv_col.get(int(j))
                if a is not None and a not in excl:
                    ranked.append(a)
                if len(ranked) >= cap:
                    break
            per.append(ranked)
        out, seen, i = [], set(), 0
        while any(i < len(p) for p in per):
            for p in per:
                if i < len(p) and p[i] not in seen:
                    out.append(p[i]); seen.add(p[i])
            i += 1
        return out

    # ---------- nodes ----------
    def router_node(s: AgentState):
        has_lib = bool(s.get("library")); has_friend = bool(s.get("friend_library"))
        prompt = _ROUTER_PROMPT % (has_lib, has_friend, s["user_query"])
        try:
            r = llm.invoke([HumanMessage(content=prompt)])
            t = r.content if hasattr(r, "content") else str(r)
            a, b = t.find("{"), t.rfind("}")
            parsed = json.loads(t[a:b + 1]) if a != -1 else {}
        except Exception as e:
            log.warning("router parse failed: %s", e); parsed = {}
        rt = parsed.get("request_type", "anonymous")
        if rt == "library" and not has_lib:
            rt = "anonymous"
        if rt == "multi_entity" and not has_friend:
            rt = "library" if has_lib else "anonymous"
        # explore/steer needs a library base (to be novel against); else LLM-direct
        if rt == "explore" and not has_lib:
            rt = "anonymous"
        # personalize whenever we have the user's library (anonymous only w/o library)
        if rt == "anonymous" and has_lib:
            rt = "library"
        return {"request_type": rt,
                "constraints": {k: v for k, v in (parsed.get("constraints") or {}).items() if v not in (None, False)},
                "seed_titles": parsed.get("seed_titles") or [],
                "refine_iter": 0, "relaxed": []}

    def library_node(s: AgentState):
        # CF moat + cold-start content fallback (D1): guarantees fill for thin/cold libs
        recs = hybrid.recommend(s["library"], k=300, exclude=set(s.get("played", [])))
        return {"candidates": [a for a, *_ in recs]}

    def steer_node(s: AgentState):
        # directional steering (F): adjacent novelty + liked-aspect, NL-extracted
        try:
            r = llm.invoke([HumanMessage(content=_STEER_PROMPT % (tag_list, s["user_query"]))])
            t = r.content if hasattr(r, "content") else str(r)
            a, b = t.find("{"), t.rfind("}")
            sp = json.loads(t[a:b + 1]) if a != -1 else {}
        except Exception as e:
            log.warning("steer parse failed: %s", e); sp = {}
        beta = _STRENGTH_BETA.get(str(sp.get("novelty_strength", "medium")).lower(), 2.0) \
            if sp.get("novelty") else 0.0
        aspect = content.resolve_tags(sp.get("aspect_tags") or [])
        if beta <= 0 and not aspect:   # nothing extracted -> behave like a novelty explore
            beta = 2.0
        recs = hybrid.recommend_steered(s["library"], k=300, exclude=set(s.get("played", [])),
                                        novelty_beta=beta, aspect_tags=aspect)
        return {"candidates": [a for a, *_ in recs],
                "steer": {"novelty_beta": beta, "aspect_tags": [content.idx2tag.get(i) for i in aspect]}}

    def _match_titles(t: str) -> list[int]:
        """Title -> all matching appids, expanding to the whole SERIES.
        'Dark Souls' -> every 'DARK SOULS*' entry (5 games), not just the most
        popular one. Substring both ways (len-guarded) so 'Dark Souls' catches
        'DARK SOULS: REMASTERED' and a longer LLM string still resolves."""
        tl = str(t).strip().lower()
        if len(tl) < 2:
            return []
        hits = {a for low, a in title2appid.items()
                if tl in low or (low in tl and len(low) >= 4)}
        # series-prefix expansion: 'The Witcher 3: Wild Hunt' -> prefix 'the witcher'
        # -> also catch 'The Witcher 2', 'The Witcher: Enhanced Edition' (word-bounded)
        pref = _series_prefix(tl)
        if len(pref) >= 4:
            hits |= {a for low, a in title2appid.items()
                     if low == pref or low.startswith(pref + " ") or low.startswith(pref + ":")}
        return list(hits)

    # "~같은 거" quality gate: co-play similarity DEGENERATES to a popularity/
    # demographic chart when the seed's owner base is broad (e.g. Eternal
    # Return -> Korean top-chart: Yu-Gi-Oh, Tekken...). Gate the co-play
    # candidates by TAG similarity to the seed — the Era-1-validated
    # similar-mode signal (tag-cosine Vb) — so co-play supplies "people
    # actually play these together" and tags supply "and it's actually a
    # similar game". Niche seeds (soulslikes etc.) pass mostly unchanged.
    SEED_MIN_TAG_SIM = 0.30  # user-tuned 2026-07-22 (0.25 let Tekken/DJMAX through on the ER seed)

    def _tag_gate(seed_ids: list, cand: list, min_sim: float = SEED_MIN_TAG_SIM,
                  min_keep: int = 10):
        rows = [content.appid2row[a] for a in seed_ids if a in content.appid2row]
        if not rows:
            return cand
        prof = np.asarray(content.Xn[rows].mean(axis=0)).ravel()
        nrm = np.linalg.norm(prof)
        if nrm == 0:
            return cand
        prof = prof / nrm
        sims = {}
        for a in cand:
            r = content.appid2row.get(a)
            if r is None or content.tag_sizes[r] == 0:
                sims[a] = None  # no tag data — unknown, NOT dissimilar: pass
            else:
                sims[a] = float(content.Xn.getrow(r).dot(prof)[0])
        kept = [a for a in cand if sims[a] is None or sims[a] >= min_sim]
        if len(kept) < min_keep:  # graceful fallback: best-half by tag-sim
            best = set(sorted(cand, key=lambda a: -(sims[a] or 0.0))
                       [:max(min_keep, len(cand) // 2)])
            kept = [a for a in cand if a in best]
        return kept

    def seed_node(s: AgentState):
        matched: list[int] = []
        for t in s.get("seed_titles", []):
            matched += _match_titles(t)
        matched = list(dict.fromkeys(matched))
        if not matched:
            return {"candidates": []}
        # all series entries as seeds (richer co-play signal); the whole named
        # franchise is excluded from results ("~같은 거" wants similar OTHERS).
        seeds = {a: 1.0 for a in matched}
        # equal EXPLICIT weights (not playtimes): score() would run seed values
        # through the pctl ECDF as if they were minutes played
        acc = (cf.score_with_weights(seeds) if hasattr(cf, "score_with_weights")
               else cf.score(seeds))
        order = np.argsort(-acc)
        excl = set(matched) | set(s.get("played", []))
        cand = []
        for j in order:  # full-vector ranking, no score<=0 cutoff (see _interleave)
            if not np.isfinite(acc[int(j)]):
                break
            a = cf.inv_col.get(int(j))
            if a is not None and a not in excl:
                cand.append(a)
            if len(cand) >= 300:
                break
        return {"candidates": _tag_gate(matched, cand)}

    def multi_node(s: AgentState):
        excl = set(s.get("played", [])) | set(s.get("library", {})) | set(s.get("friend_library", {}))
        cand = _interleave({"me": s["library"], "friend": s["friend_library"]}, excl)
        return {"candidates": cand[:300]}

    def anonymous_node(s: AgentState):
        # LLM-direct (the regime where the LLM wins); map to pool
        try:
            r = llm.invoke([HumanMessage(content=(
                "Recommend exactly 10 real Steam games for this Korean request. "
                "Output ONLY official English titles, one per line.\n\n" + s["user_query"]))])
            t = r.content if hasattr(r, "content") else str(r)
        except Exception:
            t = ""
        cand = []
        for line in t.split("\n"):
            c = line.strip().lstrip("-*•0123456789. ").strip()
            if c.lower() in title2appid:
                cand.append(title2appid[c.lower()])
        return {"candidates": cand}

    def filter_node(s: AgentState):
        cand = played_filter(s.get("candidates", []), set(s.get("played", [])))
        cand = meta.availability_filter(cand)  # never surface unpurchasable games
        filt = meta.constraint_filter(cand, s.get("constraints", {}))
        return {"filtered": filt}

    def critic_node(s: AgentState):
        # genuine refine cycle: if under-filled & budget remains, relax + loop
        k = s.get("k", 5)
        if len(s.get("filtered", [])) >= k or not s.get("constraints") or s.get("refine_iter", 0) >= max_refine:
            return {}
        cons, removed = _relax(s["constraints"])
        return {"constraints": cons, "refine_iter": s.get("refine_iter", 0) + 1,
                "relaxed": s.get("relaxed", []) + ([removed] if removed else [])}

    def _route_after_critic(s: AgentState):
        k = s.get("k", 5)
        if len(s.get("filtered", [])) < k and s.get("constraints") and s.get("refine_iter", 0) < max_refine:
            # the critic_node above already relaxed; re-filter
            return "filter_node"
        return "response_node"

    def response_node(s: AgentState):
        top = (s.get("filtered") or s.get("candidates") or [])[: s.get("k", 5)]
        out = df[df["appid"].isin(top)].set_index("appid").reindex(top).reset_index()
        titles = [appid2title.get(a, str(a)) for a in top]
        relaxed = s.get("relaxed", [])
        steer = s.get("steer") or {}
        steer_note = ""
        if steer:
            bits = []
            if steer.get("novelty_beta"):
                bits.append("새 장르 방향(탐색 모드 — 평소 취향에서 의도적으로 벗어남)")
            if steer.get("aspect_tags"):
                bits.append("좋아한 요소 강조: " + ", ".join(t for t in steer["aspect_tags"] if t))
            steer_note = " | ".join(bits)
        ctx = (f"Request: {s['user_query']}\nRoute: {s.get('request_type')}\n"
               f"Recommended (personalized, in order): {titles}\n"
               f"Constraints applied: {s.get('constraints')}"
               + (f" (relaxed: {relaxed})" if relaxed else "")
               + (f"\nSteering: {steer_note}" if steer_note else ""))
        try:
            r = llm.invoke([HumanMessage(content=(
                "You are a Korean game-recommendation assistant. Given the picks below (already "
                "personalized & filtered), write a friendly Korean reply that mentions ALL of them with a "
                "one-line reason each. If constraints were relaxed, say so briefly and honestly. If a "
                "Steering direction is given, frame the picks as an intentional exploration toward that "
                "direction (new genres / a liked aspect), honestly noting they branch from the usual taste."
                "\n\n" + ctx))])
            resp = r.content if hasattr(r, "content") else str(r)
        except Exception as e:
            log.warning("response gen failed: %s", e); resp = "추천: " + ", ".join(titles)
        return {"final_df": out, "response": resp}

    g = StateGraph(AgentState)
    for name, fn in [("router_node", router_node), ("library_node", library_node),
                     ("seed_node", seed_node), ("multi_node", multi_node),
                     ("steer_node", steer_node),
                     ("anonymous_node", anonymous_node), ("filter_node", filter_node),
                     ("critic_node", critic_node), ("response_node", response_node)]:
        g.add_node(name, fn)
    g.set_entry_point("router_node")
    g.add_conditional_edges("router_node", lambda s: s["request_type"], {
        "library": "library_node", "seed": "seed_node", "multi_entity": "multi_node",
        "explore": "steer_node",
        "anonymous": "anonymous_node", "general": "anonymous_node"})
    for n in ("library_node", "seed_node", "multi_node", "steer_node"):
        g.add_edge(n, "filter_node")
    g.add_edge("filter_node", "critic_node")
    g.add_conditional_edges("critic_node", _route_after_critic,
                            {"filter_node": "filter_node", "response_node": "response_node"})
    g.add_edge("anonymous_node", "filter_node")
    g.add_edge("response_node", END)
    return g.compile()
