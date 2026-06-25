@echo off
REM Continuous Steam crawl: steady ~1 req/s FOREVER (does users + bulk summaries,
REM loops the queue for freshness). Resumable (per-user cursor), budget-capped
REM (<=90k/UTC-day, never exceeds 100k), 429 circuit-breaker. Registered to start on
REM logon (single instance); also runnable by hand. Data -> data_collection\steam.db
REM (gitignored). Logs append to crawl_daily.log.
cd /d "D:\YBIGTA\Newbie_project\Game_recommendation"
set PY=C:\Users\hwons\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.11_qbz5n2kfra8p0\python.exe
"%PY%" -m data_collection.crawl_unified --phase users --forever --limit 90000 >> "data_collection\crawl_daily.log" 2>&1
