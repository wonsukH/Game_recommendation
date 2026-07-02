"""Doc-format checker (STYLEGUIDE enforcement).

Validates that every tracked Markdown doc follows the STYLEGUIDE meta-block
convention so a future agent can rely on it (status flags, dates, etc.). Read-only;
exits non-zero on any violation. Run: `python scripts/check_doc_format.py`.

Checks per doc (in the first few lines):
  1. an H1 (`# ...`)
  2. a meta-block `> **유형**: <type> · **상태**: <status> · **갱신**: YYYY-MM-DD`
     with type in the STYLEGUIDE vocabulary and status in {active,deprecated,frozen}
  3. deprecated/frozen docs carry a 폐기 banner or a `정본:` pointer near the top

Excludes gitignored/non-prose paths (outputs/, docs/portfolio/, .venv/, memory).
"""
import re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VOCAB = {"behavior-rules", "overview", "roadmap", "design-spec", "bug-log", "runbook",
         "index", "reasoning-log", "experiment-report", "metric-report", "eval-output",
         "portfolio", "html-reference"}
STATUS = {"active", "deprecated", "frozen"}
# meta-block fields may appear with extra fields between them (e.g. · **run**: ..,
# · **브랜치**: ..), so parse each field independently rather than requiring adjacency.
RE_TYPE = re.compile(r"\*\*유형\*\*:\s*([a-z-]+)")
RE_STATUS = re.compile(r"\*\*상태\*\*:\s*(\w+)")
RE_DATE = re.compile(r"\*\*갱신\*\*:\s*(\d{4}-\d{2}-\d{2})")

def tracked_docs():
    pats = ["README.md", "docs/**/*.md", "experiments/**/*.md"]
    skip = ("/.venv/", "/outputs/", "/docs/portfolio/", "/node_modules/")
    seen = []
    for p in pats:
        for f in ROOT.glob(p):
            rp = "/" + f.relative_to(ROOT).as_posix()
            if any(s in rp for s in skip):
                continue
            seen.append(f)
    return sorted(set(seen))

def check(f):
    head = f.read_text(encoding="utf-8").split("\n")[:8]
    errs = []
    if not any(l.startswith("# ") for l in head):
        errs.append("no H1 in first 8 lines")
    metaline = next((l for l in head if l.lstrip().startswith("> **유형**")), None)
    if not metaline:
        errs.append("no meta-block (> **유형**: .. · **상태**: .. · **갱신**: YYYY-MM-DD)")
        return errs
    t, s, d = RE_TYPE.search(metaline), RE_STATUS.search(metaline), RE_DATE.search(metaline)
    if not (t and s and d):
        errs.append("meta-block missing 유형/상태/갱신(YYYY-MM-DD)")
        return errs
    typ, status = t.group(1), s.group(1)
    if typ not in VOCAB:
        errs.append(f"unknown 유형 '{typ}'")
    if status not in STATUS:
        errs.append(f"unknown 상태 '{status}'")
    if status in ("deprecated", "frozen"):
        top = "\n".join(head)
        if "[폐기·이력]" not in top and "정본" not in top:
            errs.append(f"{status} but no 폐기 banner / 정본 pointer near top")
    return errs

def main():
    docs = tracked_docs()
    bad = 0
    for f in docs:
        errs = check(f)
        rel = f.relative_to(ROOT).as_posix()
        if errs:
            bad += 1
            print(f"FAIL {rel}")
            for e in errs:
                print(f"      - {e}")
    print(f"\nchecked {len(docs)} docs, {bad} failing")
    return 1 if bad else 0

if __name__ == "__main__":
    sys.exit(main())
