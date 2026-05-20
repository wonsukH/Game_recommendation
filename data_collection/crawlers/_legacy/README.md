# Legacy Selenium tag crawlers

These two scripts were the original way to get Steam user-tags. They
scrape each game's Steam Store page with headless Chrome, click through
the age-gate, expand the "+ more tags" button, and harvest the
`.app_tag` elements.

## Why they're here, not in the current pipeline

They're superseded by [`steamspy.py`](../steamspy.py) which:

- Returns the same user-tag data via a stable JSON API (no HTML scraping).
- Includes **tag vote counts** — Selenium only returns the names.
- Includes owner ranges + 2-week player counts in the same call.
- Doesn't need ChromeDriver or 5 parallel browsers.
- ~3x faster (10K games in ~3 hours vs ~14 hours for Selenium).

## When to use the legacy crawlers anyway

- A game is in your appid list but SteamSpy returns nothing for it.
  (Sometimes SteamSpy lags or drops obscure releases.)
- You need a sanity check that SteamSpy's tag dict matches the live
  Steam page.
- You want region-specific tag data (Selenium can drive the browser
  to a localized Steam store).

The depth of `Path(__file__).resolve().parents[N]` was adjusted to `[3]`
when these moved into `_legacy/`, so they still resolve `REPO_ROOT`
correctly when invoked.
