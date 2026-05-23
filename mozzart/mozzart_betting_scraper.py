"""
Mozzart Daily Football Betting Scraper — COMPLETE v5
======================================================
Extracts today's football matches with all odds columns:
  Final Result    : 1 / X / 2
  Double Chance   : 1X / 12 / X2
  Total Goals U/O : under_2.5 / over_2.5 / over_1.5
  BTTS            : gg / ng / gg_ov_2.5
  First to Score  : fts_1 / fts_x / fts_2

Method:
  1. POST /betOffer2       → all today's match IDs + team names
  2. POST /getBettingOdds  → full odds using explicit subgameIds

Requirements:  pip install requests
Run:           python mozzart_betting_scraper.py
"""

import requests
import json
import csv
from datetime import date, datetime, timezone

# ── Config ─────────────────────────────────────────────────────────────────────
BASE  = "https://www.mozzartbet.co.ke"
TODAY = date.today().strftime("%Y-%m-%d")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": f"https://www.mozzartbet.co.ke/en#/date/{TODAY}?sid=1",
    "Origin": "https://www.mozzartbet.co.ke",
}

# ── Subgame IDs to request (confirmed from /getAllGames decode) ────────────────
# Format: 1001{gameId:03d}{subGameId:03d}
SUBGAME_IDS = [
    # Final Result (gameId=1)
    1001001001,   # 1
    1001001002,   # X
    1001001003,   # 2
    # Double Chance (gameId=2)
    1001002001,   # 1X
    1001002002,   # 12
    1001002003,   # X2
    # Total Goals U/O (gameId=3)
    1001003004,   # over 2.5   (subGame=4)
    1001003005,   # under 2.5  (subGame=5)
    1001003001,   # over 0.5   (subGame=1) — may contain over 1.5
    1001003002,   # under 0.5  (subGame=2)
    # gameId=89 — in "Final Result" group, likely over/under 1.5
    1001089001,   # sub=1
    1001089003,   # sub=3
    # BTTS (gameId=130)
    1001130001,   # gg
    1001130002,   # ng
    1001130003,   # gg & over 2.5
    # First to Score (gameId=7)
    1001007001,   # team 1
    1001007000,   # draw / no score
    1001007002,   # team 2
]

# ── (gameId, subGameId) → CSV column  ─────────────────────────────────────────
# Confirmed from decode output: subGameName is the label
KODD_MAP = {
    # Final Result
    (1,   1): "1",
    (1,   2): "X",
    (1,   3): "2",
    # Double Chance
    (2,   1): "1X",
    (2,   2): "12",
    (2,   3): "X2",
    # Total Goals — we'll use subGameName to map dynamically (see parse_kodds)
    # BTTS
    (130, 1): "gg",
    (130, 2): "ng",
    (130, 3): "gg_ov_2.5",
    # First to Score
    (7,   1): "fts_1",
    (7,   0): "fts_x",
    (7,   2): "fts_2",
}

# Goals U/O — map by subGameName since there are many lines
GOALS_NAMES = {
    "OV 0.5": "over_0.5",   "UN 0.5": "under_0.5",
    "OV 1.5": "over_1.5",   "UN 1.5": "under_1.5",
    "OV 2.5": "over_2.5",   "UN 2.5": "under_2.5",
    "OV 3.5": "over_3.5",   "UN 3.5": "under_3.5",
    # gameId=89 variants
    "1+": "over_0.5_alt",   "2+": "over_1.5_alt",
}

CSV_COLUMNS = [
    "match_id", "league", "home", "away", "kick_off",
    "1", "X", "2",
    "1X", "12", "X2",
    "over_2.5", "under_2.5", "over_1.5", "under_1.5",
    "gg", "ng", "gg_ov_2.5",
    "fts_1", "fts_x", "fts_2",
]


# ── API helpers ────────────────────────────────────────────────────────────────

def post(endpoint, payload):
    try:
        r = requests.post(f"{BASE}/{endpoint}", json=payload, headers=HEADERS, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"  ⚠  POST /{endpoint}: {e}")
        return None


def fetch_all_matches() -> list:
    all_matches = []
    offset = 0
    total  = None
    while True:
        data = post("betOffer2", {
            "date": TODAY, "sportIds": [1], "competitionIds": [],
            "sort": "bycompetition", "specials": None, "subgames": [],
            "size": 500, "mostPlayed": False, "type": "betting",
            "numberOfGames": 0, "activeCompleteOffer": False,
            "lang": "en", "offset": offset,
        })
        if not data:
            break
        batch = data.get("matches", [])
        if total is None:
            total = data.get("total", 0)
            print(f"  Total available: {total}")
        all_matches.extend(batch)
        offset += len(batch)
        print(f"  Fetched {len(all_matches)}/{total}...")
        if offset >= total or not batch:
            break

    # Exclude player specials (e.g. "England - Premier - players")
    real = [m for m in all_matches
            if "- players" not in m.get("competition_name_en", "").lower()]
    print(f"  Real matches: {len(real)}/{len(all_matches)}")
    return real


def parse_kodds(kodds: dict) -> dict:
    """Parse kodds dict into {column: value}."""
    odds = {}
    for kodd in kodds.values():
        if not isinstance(kodd, dict):
            continue
        if kodd.get("winStatus") not in ("ACTIVE", None, ""):
            continue
        sg      = kodd.get("subGame", {})
        gid     = sg.get("gameId")
        sid     = sg.get("subGameId")
        name    = sg.get("subGameName", "")
        val     = kodd.get("value")
        if not val:
            continue

        # Fixed map first
        col = KODD_MAP.get((gid, sid))
        if col:
            odds[col] = str(val)
            continue

        # Goals U/O — map by subGameName
        if gid == 3:
            col = GOALS_NAMES.get(name)
            if col:
                odds[col] = str(val)
            continue

        # gameId=89 — figure out from subGameName
        if gid == 89:
            col = GOALS_NAMES.get(name)
            if col:
                odds[col] = str(val)

    return odds


def fetch_odds(match_ids: list) -> dict:
    """Fetch odds using explicit subgameIds — returns {match_id: {col: val}}."""
    BATCH  = 50   # smaller batches are more reliable
    result = {}

    for i in range(0, len(match_ids), BATCH):
        batch = match_ids[i:i + BATCH]
        data  = post("getBettingOdds", {
            "matchIds": batch,
            "subgames": SUBGAME_IDS,
        })
        if not data or not isinstance(data, list):
            continue
        for item in data:
            mid   = item.get("id")
            kodds = item.get("kodds", {})
            if mid and kodds:
                result[mid] = parse_kodds(kodds)

    return result


# ── Parsing ────────────────────────────────────────────────────────────────────

def ms_to_time(ms) -> str:
    try:
        dt = datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc)
        return dt.strftime("%d %b %Y %H:%M UTC")
    except Exception:
        return str(ms)


def parse_match(m: dict, all_odds: dict) -> dict:
    mid  = m.get("id")
    p    = m.get("participants", [])
    home = p[0].get("name", "?") if len(p) > 0 else "?"
    away = p[1].get("name", "?") if len(p) > 1 else "?"

    row = {
        "match_id": mid,
        "league":   m.get("competition_name_en", ""),
        "home":     home,
        "away":     away,
        "kick_off": ms_to_time(m.get("startTime", 0)),
    }
    odds = all_odds.get(mid, {})
    for col in CSV_COLUMNS[5:]:
        row[col] = odds.get(col, "")
    return row


# ── Output ─────────────────────────────────────────────────────────────────────

def display_sample(matches, n=5):
    print(f"\n{'='*72}")
    print(f"  MOZZART FOOTBALL  —  {TODAY}  |  {len(matches)} matches")
    print(f"{'='*72}")
    for m in matches[:n]:
        print(f"\n  {m['home']}  vs  {m['away']}  [{m['league']}]  {m['kick_off']}")
        print(f"  1/X/2     : {m.get('1','–')} / {m.get('X','–')} / {m.get('2','–')}")
        print(f"  DC        : 1X={m.get('1X','–')}  12={m.get('12','–')}  X2={m.get('X2','–')}")
        print(f"  U/O       : o2.5={m.get('over_2.5','–')}  u2.5={m.get('under_2.5','–')}  o1.5={m.get('over_1.5','–')}")
        print(f"  BTTS      : gg={m.get('gg','–')}  ng={m.get('ng','–')}  gg_ov2.5={m.get('gg_ov_2.5','–')}")
        print(f"  FTS       : 1={m.get('fts_1','–')}  x={m.get('fts_x','–')}  2={m.get('fts_2','–')}")


def save_json(data, fname):
    with open(fname, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"  ✅ JSON → {fname}")


def save_csv(data, fname):
    with open(fname, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(data)
    print(f"  ✅ CSV  → {fname}")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print("=" * 72)
    print(f"  MOZZART FOOTBALL BETTING SCRAPER  —  {TODAY}")
    print("=" * 72)

    print(f"\n[1/3] Fetching matches ...")
    matches_raw = fetch_all_matches()
    if not matches_raw:
        print("ERROR: No matches returned.")
        return

    match_ids = [m["id"] for m in matches_raw if m.get("id")]

    print(f"\n[2/3] Fetching odds for {len(match_ids)} matches ...")
    all_odds = fetch_odds(match_ids)
    has_1x2  = sum(1 for o in all_odds.values() if o.get("1"))
    has_uo   = sum(1 for o in all_odds.values() if o.get("over_2.5"))
    has_btts = sum(1 for o in all_odds.values() if o.get("gg"))
    print(f"  1X2: {has_1x2}  |  U/O: {has_uo}  |  BTTS: {has_btts}  (of {len(match_ids)})")

    print(f"\n[3/3] Parsing & saving ...")
    parsed = [parse_match(m, all_odds) for m in matches_raw]

    display_sample(parsed, n=5)

    print("\nSaving...")
    save_json(parsed, f"mozzart_betting_{TODAY}.json")
    save_csv(parsed,  f"mozzart_betting_{TODAY}.csv")
    print(f"\nDone — {len(parsed)} matches saved.")


if __name__ == "__main__":
    main()