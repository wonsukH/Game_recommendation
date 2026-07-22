"""Assemble the Hugging Face Space payload for the game-recommendation app.

Usage:  python scripts/build_space.py  [--out deploy/space]

Copies ONLY what the serving path needs (code + aggregate artifacts) into a
standalone folder that is pushed to the HF Space git repo:

    deploy/space/
      README.md            <- HF front matter (sdk: streamlit) + visitor intro
      requirements.txt     <- minimal serving deps (no torch/faiss/selenium...)
      .gitattributes       <- *.npz/*.npy via LFS (B_topk is ~345 MB)
      serving/             <- app + graph + guard + data (aggregates only)
      pipeline/            <- game_rec agent subset the app imports
      docs/technical_reference.html

Hard privacy gate: after assembly the whole payload is scanned for SteamID64
patterns (operations.md rule) — any hit beyond the known code constants aborts
the build. The crawl DB, panels/unblind evidence, and graph_users.json are
never copied in the first place; the gate is the belt on top of suspenders.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SERVING_DATA_EXCLUDE = {
    "graph_users.json",   # raw SteamIDs — LOCAL-ONLY (ToU)
    "_llm_quota.json",    # runtime state
    "cf",                 # legacy P4 artifacts, unused by the serving path
}
AGENT_EXCLUDE = {"nodes", "__pycache__", "build_quality.py"}

ID_PAT = re.compile(rb"7656119\d{10}")
ID_BENIGN = {
    b"76561197960265728",  # STEAMID_BASE code constant
    b"76561198000000000",  # synthetic test id
    b"76561198346330208",  # the AUTHOR's own public account — self-consented
                           # in-app sample (user directive 2026-07-22)
}

SPACE_README = """\
---
title: Steam Game Recommendation Agent
emoji: \U0001F3AE
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 8501
pinned: false
---

# 게임 추천 에이전트 (라이브 데모)

**내 Steam ID를 입력하면 내 라이브러리(플레이 기록) 기반 개인화 추천**을,
없으면 채팅("차분한 인디 게임")으로 추천을 받습니다.
행동 데이터 2만+ 유저의 co-play로 학습한 EASE 랭커 + LangGraph 라우팅.

- 소스/검증 기록: https://github.com/wonsukH/Game_recommendation
- 입력한 Steam ID·라이브러리는 서버에 저장되지 않습니다.
- AI 설명 문장은 일일 무료 쿼터가 있어 소진 시 "추천 목록만" 모드로 동작합니다.
"""

SPACE_REQUIREMENTS = """\
streamlit==1.48.1
numpy==2.3.2
pandas==2.3.1
scipy==1.16.1
scikit-learn==1.7.1
requests==2.32.4
python-dotenv==1.1.1
langgraph==0.6.6
langchain-core==0.3.74
langchain-google-genai>=2,<3
"""

GITATTRIBUTES = """\
*.npz filter=lfs diff=lfs merge=lfs -text
*.npy filter=lfs diff=lfs merge=lfs -text
"""

# HF dropped the native streamlit SDK (gradio|docker|static only) -> Docker
# Space. HF runs the container as uid 1000 with an app-owned WORKDIR; HOME must
# be writable (streamlit config) and serving/data too (_llm_quota.json).
DOCKERFILE = """\
FROM python:3.13-slim
RUN useradd -m -u 1000 user
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN chown -R user:user /app
USER user
ENV HOME=/home/user
EXPOSE 8501
CMD ["streamlit", "run", "serving/main_agent.py", \\
     "--server.port=8501", "--server.address=0.0.0.0", \\
     "--server.headless=true", "--server.enableCORS=false", \\
     "--server.enableXsrfProtection=false"]
"""


def _copy_tree(src: Path, dst: Path, exclude: set[str]) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for p in src.iterdir():
        if p.name in exclude or p.name == "__pycache__":
            continue
        if p.is_dir():
            _copy_tree(p, dst / p.name, exclude)
        else:
            shutil.copy2(p, dst / p.name)


def build(out: Path) -> None:
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    (out / "README.md").write_text(SPACE_README, encoding="utf-8")
    (out / "requirements.txt").write_text(SPACE_REQUIREMENTS, encoding="utf-8")
    (out / "Dockerfile").write_text(DOCKERFILE, encoding="utf-8")
    (out / ".gitattributes").write_text(GITATTRIBUTES, encoding="utf-8")
    (out / ".gitignore").write_text("_llm_quota.json\n__pycache__/\n", encoding="utf-8")

    # serving code + data (aggregates only)
    sv = out / "serving"
    sv.mkdir()
    for f in ("main_agent.py", "agent_graph.py", "llm_guard.py", "bootstrap.py"):
        shutil.copy2(ROOT / "serving" / f, sv / f)
    _copy_tree(ROOT / "serving" / "data", sv / "data", SERVING_DATA_EXCLUDE)

    # pipeline subset the app imports (init files are docstring-only)
    pkg = out / "pipeline"
    (pkg / "game_rec").mkdir(parents=True)
    shutil.copy2(ROOT / "pipeline" / "__init__.py", pkg / "__init__.py")
    shutil.copy2(ROOT / "pipeline" / "game_rec" / "__init__.py",
                 pkg / "game_rec" / "__init__.py")
    for f in ("log.py", "io.py"):
        shutil.copy2(ROOT / "pipeline" / "game_rec" / f, pkg / "game_rec" / f)
    _copy_tree(ROOT / "pipeline" / "game_rec" / "agent",
               pkg / "game_rec" / "agent", AGENT_EXCLUDE)
    # evaluation subset: tools -> metrics; cf_recommender -> coplay_labels
    ev = pkg / "game_rec" / "evaluation"
    ev.mkdir()
    for f in ("__init__.py", "metrics.py", "coplay_labels.py"):
        shutil.copy2(ROOT / "pipeline" / "game_rec" / "evaluation" / f, ev / f)

    manual = ROOT / "docs" / "technical_reference.html"
    if manual.exists():
        (out / "docs").mkdir()
        shutil.copy2(manual, out / "docs" / "technical_reference.html")

    # ---- hard privacy gate: no SteamID64 may ship ----
    dirty = []
    for p in sorted(out.rglob("*")):
        if not p.is_file():
            continue
        ids = set(ID_PAT.findall(p.read_bytes())) - ID_BENIGN
        if ids:
            dirty.append((p.relative_to(out), len(ids)))
    if dirty:
        for rel, n in dirty:
            print(f"ABORT: {rel} carries {n} SteamID64(s)", file=sys.stderr)
        shutil.rmtree(out)
        sys.exit(1)

    total = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    print(f"OK: space payload at {out}  ({total / 1e6:.1f} MB, ID-clean)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "deploy" / "space"))
    build(Path(ap.parse_args().out))
