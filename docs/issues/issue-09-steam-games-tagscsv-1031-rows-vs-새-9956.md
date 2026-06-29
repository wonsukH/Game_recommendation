# Issue #9: `steam_games_tags.csv` 1031 rows vs 새 9956 게임 → KeyError 2855

> **유형**: bug-log · **상태**: deprecated · **갱신**: 2026-06-29
> 상위: [ISSUES.md](../ISSUES.md)


## Symptom

streamlit 첫 실행 시 vibe 쿼리 던지면 `recommend_vibe`의 line 192에서 KeyError:

```
KeyError: np.int64(2855)
File "pipeline/game_rec/agent/retriever.py", line 192:
    candidate_appids = [self.idx_to_appid[i] for i in indices[0]]
```

## Diagnosis

1. `retriever.py`의 `_load_data`:
   ```python
   self.games_df = pd.read_csv("steam_games_tags.csv").set_index('appid')
   self.idx_to_appid = {i: appid for i, appid in enumerate(self.games_df.index)}
   ```
2. `serving/data/steam_games_tags.csv` row 수 = **1031** (옛 베이스라인 시절)
3. `index_maps.json` appid 수 = **9956** (새 SteamSpy)
4. faiss search가 row 2855 반환 → `idx_to_appid[2855]` KeyError (dict에 1031개만)

## Root Cause

M3.1에서 `tag_vocab` + `game_tag_matrix`는 새 SteamSpy 기반으로 갱신했지만 **`steam_games_tags.csv` 생성 단계 누락**. 새 SteamSpy 크롤러는 `steamspy_games.csv` (raw `tags_json` dict)로 저장. 옛 베이스라인의 normalized CSV (`appid, game_title, tags, tag_count`)는 schema 다름. 두 단계 사이 변환이 안 됨.

## Fix

`scripts/build_games_tags_csv.py` 작성:

```python
def normalize_tag(tag):
    t = unicodedata.normalize("NFKC", str(tag)).lower().strip()
    t = re.sub(r"[/\s]+", "-", t)
    t = re.sub(r"-+", "-", t)
    return t

def main():
    spy = pd.read_csv("outputs/steamspy_games.csv")
    imap = json.loads(Path("outputs/index_maps.json").read_text())
    row2appid = imap["row2appid"]
    ordered_appids = [v for _, v in sorted(((int(k), v) for k, v in row2appid.items()))]
    spy_indexed = spy.set_index("appid")

    rows = []
    for appid in ordered_appids:
        if appid not in spy_indexed.index: continue
        r = spy_indexed.loc[appid]
        tags_dict = _parse_tags_json(r["tags_json"])
        tag_names = [normalize_tag(t) for t in tags_dict.keys()]
        rows.append({
            "appid": appid, "game_title": r["name"],
            "tags": ",".join(tag_names), "tag_count": len(tag_names),
        })
    pd.DataFrame(rows).to_csv("outputs/steam_games_tags.csv", index=False)
```

핵심: **`index_maps.json`의 `row2appid` 순서로 정렬**. retriever의 `idx_to_appid`와 일관성 보장.

## Verification

```powershell
python scripts/build_games_tags_csv.py
# wrote 9956 rows to outputs/steam_games_tags.csv

python scripts/sync_data.py
# serving/data/steam_games_tags.csv = 9956 rows
```

streamlit 재시작 → KeyError 사라짐. retriever가 9956 게임 다 lookup 가능.

## Lesson

- "데이터 schema 마이그레이션" 단계는 명시적으로. M3.1에서 했어야 할 일을 보완 스크립트로 따로 처리.
- 옛 산출물이 dead asset처럼 남아있으면 silent mismatch 위험. 의존 관계 명시 + sync 자동화 (Issue #5 fix와 연관).
- 추후 game_tag_matrix.py에 통합 가능 (M3.1 단계에서 자동 생성하도록).

---
