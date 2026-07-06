@echo off
REM Continuous Steam crawl FOREVER, 2 phases round-robin (users facts -> games dimension).
REM UNBIASED mode (07-07): --user-source random draws random accountIDs (batched public
REM screening via GetPlayerSummaries) instead of the biased reviewer-snowball, tagging them
REM depth=-1 (OOD/P6 panel). --no-achievements drops per-game GetPlayerAchievements (~96% of
REM per-user cost) for ~15x more users/day; the weak completion signal (+0.0073) isn't worth it.
REM Existing biased pool (~2,900) is kept for P4 analysis; this grows an unbiased pool.
REM Budget-capped <=90k/UTC-day. Resumable. Data -> steam.db. Logs -> crawl_daily.log.
cd /d "%~dp0.."
set PY=%~dp0..\.venv\Scripts\python.exe
set PYTHONIOENCODING=utf-8
"%PY%" -m data_collection.crawl_unified --forever --limit 90000 --target 1.0 --no-achievements --user-source random --users-chunk 100 >> "data_collection\crawl_daily.log" 2>&1
