"""Cloud-deploy bootstrap: fetch the EASE serving tensor when absent.

The 345 MB `B_topk.npz` is gitignored (rebuilt locally; GitHub 100 MB limit),
so cloud hosts that clone the repo (Streamlit Community Cloud) start without
it. The aggregate item-item tensor is published on a public HF *model* repo
(free tier) and pulled once at boot; every other artifact ships in git.
"""

from __future__ import annotations

from pathlib import Path

EASE_ARTIFACT_REPO = "Numi76/game-rec-ease-artifact"


def ensure_ease_artifact(data_dir: str | Path) -> None:
    target = Path(data_dir) / "ease" / "B_topk.npz"
    if target.exists():
        return
    from huggingface_hub import hf_hub_download  # lazy: local runs never need it
    hf_hub_download(repo_id=EASE_ARTIFACT_REPO, filename="B_topk.npz",
                    local_dir=target.parent)  # public repo — anonymous download
