@echo off
REM Daily unified Steam crawl (resumable, budget-capped <=90k/day, rate-safe 1 req/s).
REM Registered as a daily Windows Scheduled Task; also runnable by hand.
REM Stores into data_collection\steam.db (gitignored). Logs append to crawl_daily.log.
cd /d "D:\YBIGTA\Newbie_project\Game_recommendation"
set PY=C:\Users\hwons\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.11_qbz5n2kfra8p0\python.exe
REM AIMD self-tunes the rate; shared 90k/day budget across both phases. Users first, then bulk-summaries (country).
"%PY%" -m data_collection.crawl_unified --phase users     --limit 90000 >> "data_collection\crawl_daily.log" 2>&1
"%PY%" -m data_collection.crawl_unified --phase summaries  --limit 90000 >> "data_collection\crawl_daily.log" 2>&1

