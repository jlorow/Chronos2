"""
Mozzart Jackpot Scraper — COMPLETE
====================================
All data comes from a single GET /predefined-tickets call.
- Away team  → game['visitor']
- Odds       → game['odds'] list with bettingSubGameId 1/2/3 = 1/X/2
- Kick-off   → game['time'] (Unix ms → human readable)
- League     → game['competition']

No Playwright, no secondary API calls needed.

Requirements:  pip install requests
Run:           python mozzart_jackpot_complete.py
"""

import requests
import json
import os
from datetime import datetime, timezone

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.mozzartbet.co.ke/en",
    "Origin": "https://www.mozzartbet.co.ke",
}
BASE = "https://www.mozzartbet.co.ke"


def fetch_tickets():
    r = requests.get(f"{BASE}/predefined-tickets", headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r.json()


def parse_odds(odds_list: list) -> dict:
    """
    Parse the embedded odds array.
    Structure: [{"bettingGameId":1, "bettingSubGameId":1, "odd":X, ...}, ...]
    bettingSubGameId: 1 = home (1), 2 = draw (X), 3 = away (2)
    Also handles shortName/pick fields as fallback.
    """
    result = {"1": "-", "X": "-", "2": "-"}
    if not isinstance(odds_list, list):
        return result

    for item in odds_list:
        if not isinstance(item, dict):
            continue
        # Get the odd value — try multiple field names
        for key in ("bettingSubGameOdds", "odd", "odds", "value", "coefficient", "kv", "koeficijent"):
            odd_val = item.get(key)
            if odd_val is not None:
                break
        else:
            continue
        odd_str = str(odd_val)

        # Map to 1/X/2 via bettingSubGameId (1=home, 2=draw, 3=away)
        sub_id = item.get("bettingSubGameId")
        if sub_id == 1:
            result["1"] = odd_str
        elif sub_id == 2:
            result["X"] = odd_str
        elif sub_id == 3:
            result["2"] = odd_str
        else:
            # Fallback: use shortName or pick field
            short = (
                item.get("shortName") or item.get("pick") or
                item.get("betName") or item.get("name") or ""
            ).upper().strip()
            if short in ("1", "HOME"):
                result["1"] = odd_str
            elif short in ("X", "DRAW"):
                result["X"] = odd_str
            elif short in ("2", "AWAY"):
                result["2"] = odd_str

    return result


def ms_to_time(ms) -> str:
    """Convert Unix milliseconds to readable local time string."""
    try:
        dt = datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc)
        return dt.strftime("%d %b %Y %H:%M UTC")
    except Exception:
        return str(ms)


def parse_match(m: dict) -> dict:
    odds_raw = m.get("odds", [])
    # Filter to Final Result only (bettingGameId == 1)
    fr_odds = [o for o in odds_raw if isinstance(o, dict) and o.get("bettingGameId") == 1]
    if not fr_odds:
        fr_odds = odds_raw  # fallback: use all

    competition = m.get("competition", "")
    if isinstance(competition, dict):
        competition = competition.get("name") or competition.get("title") or str(competition)

    return {
        "match_id": m.get("id"),
        "home":     m.get("home", "?"),
        "away":     m.get("visitor", "?"),   # KEY: 'visitor' not 'away'
        "league":   competition,
        "kick_off": ms_to_time(m.get("time", 0)),
        "odds":     parse_odds(fr_odds),
    }


def parse_tickets(raw) -> dict:
    """Split tickets into daily (16 matches) and weekly (20 matches)."""
    buckets = {"daily": [], "weekly": []}
    items = raw if isinstance(raw, list) else [raw]

    for ticket in items:
        matches_raw = ticket.get("matches", [])
        matches = [parse_match(m) for m in matches_raw]

        # Use ticketType/description fields first, then count
        tt   = str(ticket.get("ticketType", "")).lower()
        desc = str(ticket.get("description", "")).lower()

        if "daily" in tt or "daily" in desc:
            ticket_type = "daily"
        elif "weekly" in tt or "weekly" in desc or "grand" in desc:
            ticket_type = "weekly"
        elif len(matches) <= 16:
            ticket_type = "daily"
        else:
            ticket_type = "weekly"

        print(f"  Ticket: {len(matches)} matches | ticketType='{tt}' | desc='{desc[:40]}' -> {ticket_type}")
        buckets[ticket_type].extend(matches)

    return buckets


def display(matches: list, label: str):
    has_odds = sum(1 for m in matches if any(v != "-" for v in m["odds"].values()))
    print(f"\n{'='*66}")
    print(f"  MOZZART {label}")
    print(f"  Date: {datetime.today().strftime('%d %b %Y')}  |  "
          f"Matches: {len(matches)}  |  Odds: {has_odds}/{len(matches)}")
    print(f"{'='*66}\n")
    for i, m in enumerate(matches, 1):
        o = m["odds"]
        print(f"#{i:02d}  {m['home']}  vs  {m['away']}")
        print(f"      League : {m['league']}")
        print(f"      Kick-off: {m['kick_off']}")
        print(f"      Odds   : 1={o['1']}  X={o['X']}  2={o['2']}")
        print()


def save(data, filename: str):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"✅ Saved → {filename}")


OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "cards")


def main():
    print("=" * 66)
    print("  MOZZART JACKPOT SCRAPER — Complete")
    print("=" * 66)

    print("\nFetching /predefined-tickets ...")
    try:
        raw = fetch_tickets()
    except Exception as e:
        print(f"ERROR: {e}")
        return

    # Debug: show the raw odds structure for the first match
    items = raw if isinstance(raw, list) else [raw]
    if items and items[0].get("matches"):
        first_match = items[0]["matches"][0]
        print(f"\nFirst match raw odds sample:")
        print(json.dumps(first_match.get("odds", [])[:4], indent=2))
        print()

    buckets = parse_tickets(raw)
    daily, weekly = buckets["daily"], buckets["weekly"]

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")

    if daily:
        display(daily, "DAILY JACKPOT (16 matches)")
        save(daily, os.path.join(OUTPUT_DIR, f"mozzart_daily_{ts}.json"))

    if weekly:
        display(weekly, "WEEKLY JACKPOT (20 matches)")
        save(weekly, os.path.join(OUTPUT_DIR, f"mozzart_weekly_{ts}.json"))

    if not daily and not weekly:
        print("No matches found. Saving raw response for inspection...")
        save(raw, os.path.join(OUTPUT_DIR, "predefined_tickets_raw.json"))


if __name__ == "__main__":
    main()