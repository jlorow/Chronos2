"""
SportPesa Football Odds Scraper  v4
"""

from playwright.sync_api import sync_playwright
import json, csv
from datetime import datetime

BASE_URL    = "https://www.ke.sportpesa.com/en/sports-betting/football-1/"
HEADLESS    = True
WAIT_MS     = 30_000   # wait 30s after page starts loading — enough for API calls
OUTPUT_CSV  = "sportpesa_odds.csv"
OUTPUT_JSON = "sportpesa_odds.json"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/122.0.0.0 Safari/537.36")

class Interceptor:
    def __init__(self):
        self.highlights = None
        self.markets    = None

    def on_response(self, response):
        if response.status != 200:
            return
        if "json" not in response.headers.get("content-type", ""):
            return
        url = response.url
        try:
            data = response.json()
        except Exception:
            return

        if "/api/highlights/1" in url:
            self.highlights = data
            print(f"  ✓ highlights captured  ({len(str(data))} bytes)")

        elif "/api/games/markets" in url or "markets" in url.lower():
            self.markets = data
            print(f"  ✓ markets captured     ({len(str(data))} bytes)  URL: {url}")
            with open("_debug_markets_raw.json", "w") as f:
                json.dump(data, f, indent=2)

        else:
            # Log all JSON API calls so we can find the right URL
            if any(k in url for k in ["/api/", "sportpesa"]):
                print(f"  [API] {url[:120]}")


def parse(highlights, markets: dict) -> list:
    items = highlights if isinstance(highlights, list) else highlights.get("data", highlights.get("items", []))
    rows = []
    for e in items:
        eid   = e.get("id")
        comps = e.get("competitors", [])
        home  = comps[0]["name"] if len(comps) > 0 else None
        away  = comps[1]["name"] if len(comps) > 1 else None

        row = {
            "event_id":    eid,
            "sms_id":      e.get("smsId"),
            "competition": e.get("competition", {}).get("name"),
            "country":     e.get("country", {}).get("name"),
            "match":       f"{home} vs {away}" if home and away else None,
            "home_team":   home,
            "away_team":   away,
            "kickoff":     e.get("date"),
            "home_odd":    None,
            "draw_odd":    None,
            "away_odd":    None,
            "btts_yes":    None,
            "btts_no":     None,
            "over_2_5":    None,
            "under_2_5":   None,
            "dc_1x":       None,
            "dc_x2":       None,
            "dc_12":       None,
        }

        for market in markets.get(str(eid), []):
            mid  = market.get("id")
            sels = market.get("selections", [])

            if mid == 10:   # 1X2
                if len(sels) >= 3:
                    row["home_odd"] = sels[0].get("odds")
                    row["draw_odd"] = sels[1].get("odds")
                    row["away_odd"] = sels[2].get("odds")

            elif mid == 43:  # BTTS
                for s in sels:
                    sn = s.get("shortName", "").upper()
                    if sn in ("YES", "GG", "Y"):
                        row["btts_yes"] = s.get("odds")
                    elif sn in ("NO", "NG", "N"):
                        row["btts_no"] = s.get("odds")

            elif mid == 52:  # Over/Under 2.5
                for s in sels:
                    sn = s.get("shortName", "").upper()
                    if sn in ("OV", "O"):
                        row["over_2_5"] = s.get("odds")
                    elif sn in ("UN", "U"):
                        row["under_2_5"] = s.get("odds")

            elif mid == 46:  # Double Chance
                if len(sels) >= 3:
                    row["dc_1x"] = sels[0].get("odds")
                    row["dc_x2"] = sels[1].get("odds")
                    row["dc_12"] = sels[2].get("odds")

        rows.append(row)
    return rows


def save(rows):
    fields = ["event_id","sms_id","competition","country","match",
              "home_team","away_team","kickoff",
              "home_odd","draw_odd","away_odd",
              "btts_yes","btts_no",
              "over_2_5","under_2_5",
              "dc_1x","dc_x2","dc_12"]

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)
    print(f"💾  {OUTPUT_JSON}  ({len(rows)} rows)")

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"💾  {OUTPUT_CSV}  ({len(rows)} rows)")


def scrape():
    print(f"\n{'='*55}")
    print("  SportPesa Scraper v4")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*55}\n")

    interceptor = Interceptor()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        ctx = browser.new_context(
            user_agent=UA,
            extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
            viewport={"width": 1280, "height": 900},
        )
        page = ctx.new_page()
        page.on("response", interceptor.on_response)

        print(f"🌐  Loading page (waiting up to {WAIT_MS//1000}s for API calls)...")
        try:
            # domcontentloaded fires early — we then wait for the API calls via WAIT_MS
            page.goto(BASE_URL, wait_until="domcontentloaded", timeout=60_000)
        except Exception as e:
            print(f"⚠️  {e}")

        # Wait for the two API calls to complete
        print("⏳  Waiting for highlights + markets APIs...")
        waited = 0
        while waited < WAIT_MS:
            page.wait_for_timeout(1000)
            waited += 1000
            if interceptor.highlights and interceptor.markets:
                print(f"  ✓ Both APIs captured after {waited//1000}s")
                break
            elif waited % 3000 == 0:
                print(f"  ... {waited//1000}s elapsed, still waiting...")

        browser.close()

    if not interceptor.highlights:
        print("❌  highlights not captured. Check your internet connection and try again.")
        return []
    if not interceptor.markets:
        print("❌  markets not captured. Try increasing WAIT_MS at the top of the script.")
        return []

    rows = parse(interceptor.highlights, interceptor.markets)

    has_odds = sum(1 for r in rows if r["home_odd"] is not None)
    has_btts = sum(1 for r in rows if r["btts_yes"] is not None)
    print(f"\n✅  {len(rows)} matches  |  1X2: {has_odds}  |  BTTS: {has_btts}")

    print(f"\n{'Match':<38} {'1':>6} {'X':>6} {'2':>6} {'GG':>6} {'NG':>6} {'O2.5':>6} {'U2.5':>6}")
    print("-" * 82)
    for r in rows[:10]:
        print(
            f"{str(r['match']):<38} "
            f"{str(r['home_odd'] or '-'):>6} "
            f"{str(r['draw_odd'] or '-'):>6} "
            f"{str(r['away_odd'] or '-'):>6} "
            f"{str(r['btts_yes'] or '-'):>6} "
            f"{str(r['btts_no'] or '-'):>6} "
            f"{str(r['over_2_5'] or '-'):>6} "
            f"{str(r['under_2_5'] or '-'):>6}"
        )

    save(rows)
    print("\n✅  Done.\n")
    return rows


if __name__ == "__main__":
    scrape()