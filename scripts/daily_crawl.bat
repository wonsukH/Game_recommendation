@echo off
REM Continuous Steam crawl FOREVER, 2 phases round-robin (users facts -> games dimension).
REM Wall-clock paced (~1 req/s incl. response latency), AIMD + 429 circuit-breaker.
REM Budget-capped <=90k/UTC-day via reserve-before-call (every HTTP request counted) ->
REM never exceeds Steam's 100k. Resumable (user queue + per-game visited markers); user
REM queue = CSV steamid bootstrap (seed-shuffled) + friend snowball.
REM Data -> data_collection\steam.db (gitignored, local only). Logs -> crawl_daily.log.
cd /d "D:\YBIGTA\Newbie_project\Game_recommendation"
set PY=C:\Users\hwons\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.11_qbz5n2kfra8p0\python.exe
set PYTHONIOENCODING=utf-8
"%PY%" -m data_collection.crawl_unified --forever --limit 90000 --target 1.0 >> "data_collection\crawl_daily.log" 2>&1
