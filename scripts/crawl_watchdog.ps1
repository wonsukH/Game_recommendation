# Crawl watchdog — relaunch the Steam crawler if it's not running (one-shot check).
# NOTE: intentionally NOT registered as a Windows Scheduled Task (user declined). Invoke it
# manually or from an active session to self-heal the crawl after crashes / throttle-deaths.
# The crawler loads .env itself (crawl_unified.py load_dotenv), so no env needed here.
$ErrorActionPreference = "SilentlyContinue"
$repo = "D:\YBIGTA\Newbie_project\Game_recommendation"
$log  = Join-Path $repo "data_collection\crawl_watchdog.log"
$proc = Get-CimInstance Win32_Process -Filter "Name like 'python%'" |
        Where-Object { $_.CommandLine -like '*crawl_unified*' }
if (-not $proc) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $log -Value "$ts  crawler DOWN -> relaunching daily_crawl.bat"
    Start-Process -WindowStyle Hidden (Join-Path $repo "scripts\daily_crawl.bat")
}
