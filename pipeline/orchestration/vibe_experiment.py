"""Phase 2b — vibe mode: does W_align (and SVD) earn its keep vs simpler paths?

For natural-language ("vibe") queries we compare three ways to go from the
query to a ranked game list, holding the rest fixed:

  Vb_vibe  : parser tags -> vote-weighted tag-cosine over X   (no SVD, no W_align)
  Vc_vibe  : parser tags -> sum of SVD tag_vecs -> cosine over game_vecs (SVD, no W_align)
  Vd_vibe  : query phrases -> Gemini embed -> @ W_align -> 128d -> cosine over game_vecs
             (the production W_align path; isolates what W_align adds over just
              using the tags the parser already extracted)

The parser is the production component (Gemini + prompts/parser.txt), replicated
here via langchain_core to avoid the broken `langchain` meta-package. Retrieval is
pure numpy (FAISS IndexFlatL2 over unit vectors == this argsort).

This produces the ranked lists; the *quality* verdict comes from the blinded
pairwise judge (Phase 2c) — Claude sub-agents + Gemini — since vibe mode has no
clean non-circular label. Genre/tag-match is reported only as a demoted guardrail.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
from dotenv import load_dotenv
from sklearn.preprocessing import normalize

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from langchain_core.prompts import PromptTemplate  # noqa: E402
from langchain_core.messages import HumanMessage  # noqa: E402
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings  # noqa: E402

from pipeline.game_rec.agent.baselines import Catalog  # noqa: E402
from pipeline.game_rec.io import load_csr, load_tag_vocab, load_vectors  # noqa: E402
from pipeline.game_rec.prompts import load_prompt  # noqa: E402
from pipeline.game_rec.log import get_logger  # noqa: E402

log = get_logger("orchestration.vibe_experiment")


def parse_query(q: str, llm, tmpl: PromptTemplate) -> dict:
    """Faithful replica of llm_parser_node (Gemini + parser.txt)."""
    res = (tmpl | llm).invoke({"question": q})
    s = res.content if hasattr(res, "content") else str(res)
    a, b = s.find("{"), s.rfind("}")
    if a != -1 and b != -1:
        try:
            return json.loads(s[a:b + 1])
        except json.JSONDecodeError:
            pass
    return {"mode": "general"}


class VibeRetrievers:
    def __init__(self, data_dir: Path, weighted_x: Path, tag_vecs_path: Path,
                 game_vecs_path: Path, walign_path: Path, tag_text_path: Path, embeddings):
        self.cat = Catalog(data_dir)
        self.tags = load_tag_vocab(data_dir / "tag_vocab.json")
        self.tag2idx = {t: i for i, t in enumerate(self.tags)}
        self._alias = {t.replace("-", "").replace("_", "").lower(): t for t in self.tag2idx}
        self.Xn = normalize(load_csr(weighted_x).astype(np.float64), norm="l2", axis=1).tocsr()
        self.tag_vecs = load_vectors(tag_vecs_path, "float64")
        self.tag_vecs_n = normalize(self.tag_vecs, norm="l2", axis=1)
        self.game_vecs_n = normalize(load_vectors(game_vecs_path, "float64"), norm="l2", axis=1)
        self.W_align = load_vectors(walign_path, "float64")
        # NEWER-METHOD FIX (Ve): Gemini-space tag embeddings (447x3072) for
        # zero-shot NN tag selection — replaces the broken 3072->128 ridge.
        self.tag_text_n = normalize(load_vectors(tag_text_path, "float64"), norm="l2", axis=1)
        self.embeddings = embeddings

    def _resolve(self, name: str):
        if name in self.tag2idx:
            return name
        return self._alias.get(name.replace("-", "").replace("_", "").lower())

    def _topk(self, scores, top_k):
        k = min(top_k, len(scores))
        top = np.argpartition(-scores, k - 1)[:k]
        top = top[np.argsort(-scores[top])]
        return [int(self.cat.row2appid[int(r)]) for r in top]

    def vibe_tagcosine(self, parsed, top_k=5):
        """Vb: weighted tag indicator -> cosine over vote-weighted X (no SVD)."""
        q = np.zeros(len(self.tags))
        for ti in parsed.get("target_tags", []):
            name = self._resolve(ti.get("name", ""))
            if name:
                q[self.tag2idx[name]] += float(ti.get("weight", 1.0) or 1.0)
        if not q.any():
            return []
        q = q / np.linalg.norm(q)
        scores = self.Xn.dot(q)
        return self._topk(scores, top_k)

    def vibe_svd_tags(self, parsed, top_k=5):
        """Vc: sum of unit SVD tag_vecs -> cosine over game_vecs (SVD, no W_align)."""
        v = np.zeros(self.tag_vecs.shape[1])
        for ti in parsed.get("target_tags", []):
            name = self._resolve(ti.get("name", ""))
            if name:
                v += self.tag_vecs_n[self.tag2idx[name]] * float(ti.get("weight", 1.0) or 1.0)
        if not np.linalg.norm(v):
            return []
        v = v / np.linalg.norm(v)
        scores = self.game_vecs_n @ v
        return self._topk(scores, top_k)

    def vibe_gemini_nn(self, query_text, top_m_tags=5, top_k=5):
        """Ve (FIX): embed query in Gemini space -> cosine-NN to tag embeddings
        -> pick top tags -> retrieve via reliable tag-cosine. No ridge projection.

        Why this should beat W_align: it stays in Gemini's native 3072-d space
        for the semantic match (no lossy, memorizing 3072->128 ridge) and uses
        tag-cosine retrieval (Phase 1 winner) instead of SVD game_vecs.
        """
        q = np.array(self.embeddings.embed_query(query_text), dtype=np.float64)
        q = q / max(np.linalg.norm(q), 1e-12)
        sims = self.tag_text_n @ q
        top_tags = np.argsort(-sims)[:top_m_tags]
        qv = np.zeros(len(self.tags))
        for ti in top_tags:
            qv[ti] += float(max(sims[ti], 0.0))  # weight by Gemini-space similarity
        if not qv.any():
            return [], []
        qv = qv / np.linalg.norm(qv)
        scores = self.Xn.dot(qv)
        picked = [self.tags[int(ti)] for ti in top_tags]
        return self._topk(scores, top_k), picked

    def vibe_walign(self, parsed, query_text, top_k=5):
        """Vd: phrases -> Gemini embed -> @W_align -> 128d -> cosine over game_vecs."""
        phrases = parsed.get("phrases") or [query_text]
        embs = self.embeddings.embed_documents(phrases)
        v = np.zeros(self.W_align.shape[1])
        for e in embs:
            proj = np.dot(np.array(e, dtype=np.float64), self.W_align)
            n = np.linalg.norm(proj)
            if n > 0 and np.all(np.isfinite(proj)):
                v += proj / n
        if not np.linalg.norm(v):
            return []
        v = v / np.linalg.norm(v)
        scores = self.game_vecs_n @ v
        return self._topk(scores, top_k)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--queries", type=Path, default=REPO_ROOT / "tests" / "eval_queries.json")
    ap.add_argument("--data-dir", type=Path, default=REPO_ROOT / "serving" / "data")
    ap.add_argument("--weighted-x", type=Path, default=REPO_ROOT / "outputs" / "X_game_tag_weighted.npz")
    ap.add_argument("--tag-vecs", type=Path, default=REPO_ROOT / "serving" / "data" / "tag_vecs.npy")
    ap.add_argument("--game-vecs", type=Path, default=REPO_ROOT / "serving" / "data" / "game_vecs.npy")
    ap.add_argument("--walign", type=Path, default=REPO_ROOT / "serving" / "data" / "W_align.npy")
    ap.add_argument("--tag-text", type=Path, default=REPO_ROOT / "serving" / "data" / "tag_text_vecs.npy")
    ap.add_argument("--out", type=Path, default=REPO_ROOT / "experiments" / "vibe_lists.json")
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    load_dotenv(REPO_ROOT / ".env")
    key = os.environ["GEMINI_API_KEY"]
    llm = ChatGoogleGenerativeAI(model=os.environ.get("GEMINI_CHAT_MODEL", "gemini-2.5-pro"),
                                 google_api_key=key, temperature=0.0)
    emb = GoogleGenerativeAIEmbeddings(model=os.environ.get("GEMINI_EMBEDDING_MODEL", "models/gemini-embedding-2"),
                                       google_api_key=key)
    tmpl = PromptTemplate.from_template(load_prompt("parser"))

    R = VibeRetrievers(args.data_dir, args.weighted_x, args.tag_vecs, args.game_vecs,
                       args.walign, args.tag_text, emb)

    queries = json.loads(args.queries.read_text(encoding="utf-8"))
    # NL queries only (exclude pure similar/game-seed queries)
    nl = [q for q in queries if not q.get("category", "").startswith("similar")]
    if args.limit > 0:
        nl = nl[: args.limit]
    log.info("running vibe variants on %d NL queries", len(nl))

    def titles(appids):
        return [self_safe(R.cat.appid2title.get(a, str(a))) for a in appids]

    def self_safe(s):
        return str(s)

    out = []
    for i, q in enumerate(nl):
        parsed = parse_query(q["query"], llm, tmpl)
        ve_appids, ve_tags = R.vibe_gemini_nn(q["query"], top_m_tags=5, top_k=args.top_k)
        rec = {
            "id": q.get("id"), "category": q.get("category"), "query": q["query"],
            "parsed_tags": [t.get("name") for t in parsed.get("target_tags", [])],
            "parsed_phrases": parsed.get("phrases"),
            "Vb_tagcosine": titles(R.vibe_tagcosine(parsed, args.top_k)),
            "Vc_svd_tags": titles(R.vibe_svd_tags(parsed, args.top_k)),
            "Vd_walign": titles(R.vibe_walign(parsed, q["query"], args.top_k)),
            "Ve_gemini_nn": titles(ve_appids),
            "Ve_picked_tags": ve_tags,
        }
        out.append(rec)
        log.info("[%d/%d] %s | tags=%s | Ve_tags=%s", i + 1, len(nl), q.get("id"), rec["parsed_tags"], ve_tags)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("wrote %d vibe rec-lists -> %s", len(out), args.out)
    # quick console peek
    for r in out[:4]:
        print(f"\n[{r['id']}] {r['query']}  (tags={r['parsed_tags']}, Ve_tags={r['Ve_picked_tags']})")
        for v in ("Vb_tagcosine", "Vc_svd_tags", "Vd_walign", "Ve_gemini_nn"):
            print(f"  {v}: {r[v]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
