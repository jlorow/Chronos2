"""
sofascore_parser.py
Extracts stats from saved SofaScore pages (.html / .mhtml).

Supports two page types:
  1. Team page  — schedule & player stats (original behaviour)
  2. Match page — live score / H2H and lineups

Usage:
  python sofascore_parser.py
  (processes all Sofascore.html/.mhtml files in the Stats directory)

IMPORTANT — saving pages for H2H data:
  H2H history is loaded dynamically when you click the H2H tab.
  Save the page as .mhtml AFTER clicking that tab and waiting for it to load.
"""

import re
import json
import os
import email
from email import policy
from pathlib import Path

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
STATS_DIR = Path(__file__).parent / "sofa-stats"
OUTPUT_FILE = STATS_DIR / "sofascore_parsed_batch.json"
# ─────────────────────────────────────────────


def load_html_from_mhtml(filepath):
    """
    Read HTML from an .mhtml or plain .html file.

    For .mhtml files the raw bytes contain MIME headers and base64-encoded
    resources before the actual HTML.  Using Python's email module to decode
    the MHTML properly avoids picking up noise from MIME boundaries.
    """
    if filepath.lower().endswith(".mhtml"):
        with open(filepath, "rb") as f:
            msg = email.message_from_binary_file(f, policy=policy.default)
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                content = part.get_content()
                if len(content) > 10_000:          # skip tiny fragments / inline frames
                    return content
        # fallback: treat as plain text (some browsers save mhtml without proper encoding)
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def find_sofascore_files(stats_dir: Path) -> list[Path]:
    """Find all Sofascore .html and .mhtml files in the stats directory."""
    files = []
    for pattern in ("*.html", "*.mhtml"):
        for fp in stats_dir.glob(pattern):
            if "Sofascore" in fp.name or "sofascore" in fp.name.lower():
                files.append(fp)
    return sorted(files)


def process_sofascore_batch(stats_dir: Path, output_file: Path) -> dict:
    """Process all Sofascore HTML/MHTML files and return batch results."""
    sofascore_files = find_sofascore_files(stats_dir)

    if not sofascore_files:
        print("No Sofascore HTML/MHTML files found in stats directory")
        return {"files_processed": 0, "results": []}

    print(f"Found {len(sofascore_files)} Sofascore file(s) to process")

    results = []
    processed_count = 0

    for file_path in sofascore_files:
        try:
            print(f"Processing: {file_path.name}")

            html = load_html_from_mhtml(str(file_path))
            page_type = detect_page_type(html)

            if page_type == "match":
                result = parse_match_page(str(file_path))
                result["page_type"] = "match"
            else:
                team_name = detect_team_name_from_title(html)
                if not team_name:
                    print(f"  ⚠️  Could not detect team name for {file_path.name}, skipping")
                    continue
                result = parse_team_page(str(file_path), team_name)
                result["page_type"] = "team"

            results.append(result)
            processed_count += 1
            print(f"  ✅ Processed as {page_type} page")

        except Exception as e:
            print(f"  ❌ Error processing {file_path.name}: {e}")
            continue

    batch_data = {
        "batch_info": {
            "total_files_found": len(sofascore_files),
            "files_processed": processed_count,
            "files_skipped": len(sofascore_files) - processed_count,
            "output_file": str(output_file),
        },
        "results": results,
    }

    output_file.parent.mkdir(exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(batch_data, f, indent=2, ensure_ascii=False)

    print(f"\n📁 Saved batch results to: {output_file}")
    print(f"✅ Processed: {processed_count} files")
    print(f"⚠️  Skipped:   {len(sofascore_files) - processed_count} files")

    return batch_data


# ─────────────────────────────────────────────
# Page-type detection
# ─────────────────────────────────────────────

def detect_page_type(html: str) -> str:
    """
    Return 'match' if this is a live-score/H2H match page, 'team' otherwise.

    Saved .mhtml pages rarely contain the __NEXT_DATA__ JSON blob or the
    SportsEvent JSON-LD (the browser strips dynamic script content on save),
    so we fall back to title-based heuristics which are always present.
    """
    # Primary signal: Next.js JSON blob with SportsEvent schema
    if re.search(r'"@type"\s*:\s*"SportsEvent"', html):
        return "match"

    # Secondary signal: page title pattern for match/H2H pages
    # e.g. "Team A vs Team B live score, H2H and lineups | Sofascore"
    m = re.search(r"<title[^>]*>([^<]+)", html)
    if m:
        title = m.group(1).strip()
        # Match pages have "vs" AND one of these keywords in the title
        if re.search(r"\bvs\b", title, re.IGNORECASE) and re.search(
            r"\b(H2H|lineups|live score)\b", title, re.IGNORECASE
        ):
            # Extra guard: team pages can say "live score" too, but they never
            # say "H2H" or "lineups". If only "live score" is present, also
            # check for "vs" + "schedule" absence (team pages say "schedule").
            if re.search(r"\b(H2H|lineups)\b", title, re.IGNORECASE):
                return "match"
            if "vs" in title.lower() and "schedule" not in title.lower():
                return "match"

    return "team"


# ─────────────────────────────────────────────
# Match-page parser (live score / H2H)
# ─────────────────────────────────────────────

def _get_nextjs_data(html: str) -> dict:
    """
    Extract and parse the Next.js __NEXT_DATA__ JSON blob.

    Tries the canonical id="__NEXT_DATA__" attribute first (reliable across
    Next.js versions), then falls back to size + keyword heuristics.
    """
    # Canonical selector — always present when Next.js injects the blob
    m = re.search(
        r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
        html,
        re.DOTALL,
    )
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass

    # Fallback heuristic (rendered/hydrated pages may omit the id attribute)
    for m in re.finditer(r"<script[^>]*>(.*?)</script>", html, re.DOTALL):
        s = m.group(1).strip()
        if len(s) > 5_000 and '"pageProps"' in s:
            try:
                return json.loads(s)
            except Exception:
                pass

    return {}


def _team_dict(t: dict) -> dict:
    return {
        "name":       t.get("name"),
        "short_name": t.get("shortName"),
        "id":         t.get("id"),
        "country":    t.get("country", {}).get("name"),
        "manager":    t.get("manager", {}).get("name"),
        "home_venue": t.get("venue", {}).get("name"),
    }


def _derive_wdl(our_goals: int, opp_goals: int) -> str:
    if our_goals > opp_goals:
        return "W"
    if our_goals == opp_goals:
        return "D"
    return "L"


def _extract_match_teams_from_title(html: str) -> tuple[str, str]:
    """
    Pull home/away team names from a match page title.
    Title format: "<Home> vs <Away> live score, H2H …"
    Returns ("", "") if not found.
    """
    m = re.search(r"<title[^>]*>([^<]+)", html)
    if m:
        raw = m.group(1).strip()
        vs_match = re.match(r"^(.+?)\s+vs\s+(.+?)\s+(live|H2H)", raw, re.IGNORECASE)
        if vs_match:
            return vs_match.group(1).strip(), vs_match.group(2).strip()
    return "", ""


def extract_h2h_history(html: str, home_team: str) -> list[dict]:
    """
    Parse H2H match rows from a Sofascore match page saved with the H2H tab open.

    Each row is anchored by  <a data-id="…">  and contains:
      - bdi[0] = date  (DD/MM/YY)
      - bdi[1] = status ("FT", "AET", kick-off time for upcoming, …)
      - bdi[2] = home team name
      - bdi[3] = away team name
      - bdi[4] = competition  (optional)

    Scores appear as pairs of <span class="…score…">N</span>:
      - scores[0], scores[1] = full-time home / away
      - scores[2], scores[3] = half-time home / away  (when present)

    W/D/L is derived from the scores relative to `home_team` so we don't
    depend on a badge class that Sofascore may change at any time.

    The first anchor is the upcoming fixture (no scores) — it is skipped.
    """
    row_anchors = list(re.finditer(r'<a data-id="(\d+)"[^>]+href="([^"]+)"', html))
    results = []

    for i, anchor in enumerate(row_anchors):
        start = anchor.start()
        end = row_anchors[i + 1].start() if i + 1 < len(row_anchors) else start + 3_000
        chunk = html[start:end]

        bdis = re.findall(r"<bdi[^>]*>([^<]+)</bdi>", chunk)
        all_scores = re.findall(r'class="[^"]*\bscore\b[^"]*"[^>]*>(\d+)<', chunk)

        # Need at least date + status + 2 team names, plus 2 FT scores
        if len(bdis) < 4 or len(all_scores) < 2:
            continue

        date   = bdis[0].strip()
        status = bdis[1].strip()
        home   = bdis[2].strip()
        away   = bdis[3].strip()
        competition = bdis[4].strip() if len(bdis) > 4 else ""

        # Skip upcoming/live matches (no final score yet)
        if status.upper() not in ("FT", "AET", "AP", "AOT"):
            continue

        home_score = int(all_scores[0])
        away_score = int(all_scores[1])
        ht_home    = int(all_scores[2]) if len(all_scores) > 2 else None
        ht_away    = int(all_scores[3]) if len(all_scores) > 3 else None

        is_home   = home_team.lower() in home.lower()
        our_goals = home_score if is_home else away_score
        opp_goals = away_score if is_home else home_score

        results.append({
            "date":        date,
            "status":      status,
            "home":        home,
            "away":        away,
            "home_score":  home_score,
            "away_score":  away_score,
            "ht_home":     ht_home,
            "ht_away":     ht_away,
            "competition": competition,
            "result":      _derive_wdl(our_goals, opp_goals),
            "our_goals":   our_goals,
            "opp_goals":   opp_goals,
            "is_home":     is_home,
        })

    return results


def parse_match_page(filepath: str) -> dict:
    """
    Parse a Sofascore live-score / H2H match page.
    Returns a dict with match context, both teams, and H2H history.

    H2H history will be populated only when the page was saved with the
    H2H tab open (i.e. saved as .mhtml after clicking the H2H tab).
    """
    html = load_html_from_mhtml(filepath)
    raw  = _get_nextjs_data(html)

    initial_props = raw.get("props", {}).get("pageProps", {}).get("initialProps", {})
    event   = initial_props.get("event", {})
    meta    = initial_props.get("eventMeta", {})

    home   = event.get("homeTeam", {})
    away   = event.get("awayTeam", {})
    tourn  = event.get("tournament", {})
    season = event.get("season", {})
    status = event.get("status", {})
    venue  = event.get("venue", {})
    ref    = event.get("referee", {})
    round_info = event.get("roundInfo", {})

    home_score = event.get("homeScore", {}).get("current")
    away_score = event.get("awayScore", {}).get("current")

    # Team names: prefer __NEXT_DATA__, fall back to page title
    home_name = home.get("name") or ""
    away_name = away.get("name") or ""
    if not home_name or not away_name:
        home_name, away_name = _extract_match_teams_from_title(html)

    # H2H history — extracted directly from the rendered DOM
    h2h = extract_h2h_history(html, home_name)

    return {
        "page_type":   "match",
        "source_file": os.path.basename(filepath),
        "match_context": {
            "home_team":        home_name,
            "away_team":        away_name,
            "tournament":       tourn.get("name"),
            "season":           season.get("name"),
            "round":            round_info.get("round"),
            "status":           status.get("description"),
            "start_timestamp":  event.get("startTimestamp"),
            "venue":            venue.get("name"),
            "referee":          ref.get("name"),
        },
        "score": {
            "home": home_score,
            "away": away_score,
        },
        "standings": {
            "home_position": meta.get("homeTeamStandingsPosition"),
            "away_position": meta.get("awayTeamStandingsPosition"),
        },
        "home_team": _team_dict(home) if home else {"name": home_name},
        "away_team": _team_dict(away) if away else {"name": away_name},
        # Per-team form — each team gets its own W/D/L perspective
        "home_team_form": _team_form_from_h2h(h2h, home_name),
        "away_team_form": _team_form_from_h2h(h2h, away_name),
        # Raw H2H history (neutral — home/away scores as played)
        "h2h_history": h2h,
        "h2h_summary": _h2h_summary(h2h, home_name),
    }


def _team_form_from_h2h(h2h: list[dict], team_name: str) -> dict:
    """
    Build per-team form, goal tallies and last-5 summary from H2H history.

    Each entry in `h2h` already has W/D/L attributed to the HOME team of the
    match page (whichever team was used as the reference when `extract_h2h_history`
    was called).  Here we re-derive per `team_name` so both home and away get
    their own correct view.
    """
    team_matches = []
    for m in h2h:
        is_this_team_home = team_name.lower() in m["home"].lower()
        our_goals = m["home_score"] if is_this_team_home else m["away_score"]
        opp_goals = m["away_score"] if is_this_team_home else m["home_score"]
        result = _derive_wdl(our_goals, opp_goals)
        team_matches.append({
            "date":      m["date"],
            "home":      m["home"],
            "away":      m["away"],
            "home_score": m["home_score"],
            "away_score": m["away_score"],
            "is_home":   is_this_team_home,
            "our_goals": our_goals,
            "opp_goals": opp_goals,
            "result":    result,
            "competition": m.get("competition", ""),
        })

    last5 = team_matches[:5]
    return {
        "team":                  team_name,
        "form_last5":            ",".join(r["result"] for r in last5),
        "goals_scored_last5":    sum(r["our_goals"] for r in last5),
        "goals_conceded_last5":  sum(r["opp_goals"] for r in last5),
        "match_history":         team_matches,
    }


def _h2h_summary(h2h: list[dict], home_team: str) -> dict:
    """Compute aggregate W/D/L and goal tallies from H2H history (home team perspective)."""
    if not h2h:
        return {}
    wins = sum(1 for m in h2h if m["result"] == "W")
    draws = sum(1 for m in h2h if m["result"] == "D")
    losses = sum(1 for m in h2h if m["result"] == "L")
    gf = sum(m["our_goals"] for m in h2h)
    ga = sum(m["opp_goals"] for m in h2h)
    return {
        "team":   home_team,
        "played": len(h2h),
        "wins":   wins,
        "draws":  draws,
        "losses": losses,
        "goals_for":     gf,
        "goals_against": ga,
    }


# ─────────────────────────────────────────────
# Team-page parser (schedule & season stats)
# ─────────────────────────────────────────────

def detect_team_name_from_title(html: str) -> str | None:
    """
    Pull the team name from the page <title> tag.
    Title format: "TeamName live score, schedule & player stats | Sofascore"
    """
    match = re.search(r"<title[^>]*>([^<|&]+)", html)
    if match:
        raw = match.group(1).strip()
        for suffix in [" live score, schedule ", " live score", " scores"]:
            if suffix in raw:
                return raw.split(suffix)[0].strip()
    return None


def extract_match_history(html: str, team_name: str) -> list[dict]:
    """
    Parse all completed match rows from the fixtures list on a team page.

    Returns a list of dicts ordered most-recent first:
      { date, home, away, home_score, away_score, result,
        our_goals, opp_goals, is_home }

    W/D/L is derived from the scores relative to `team_name` so the parser
    does not depend on the badge CSS class name (which varies by tab/row type).
    """
    row_anchors = list(re.finditer(r'<a data-id="(\d+)"[^>]+href="([^"]+)"', html))
    results = []

    for i, anchor in enumerate(row_anchors):
        start = anchor.start()
        end = row_anchors[i + 1].start() if i + 1 < len(row_anchors) else start + 3_000
        chunk = html[start:end]

        bdis   = re.findall(r"<bdi[^>]*>([^<]+)</bdi>", chunk)
        scores = re.findall(r'class="[^"]*\bscore\b[^"]*"[^>]*>(\d+)<', chunk)

        if len(bdis) < 4 or len(scores) < 2:
            continue

        date   = bdis[0].strip()
        status = bdis[1].strip()
        home   = bdis[2].strip()
        away   = bdis[3].strip()

        # Skip upcoming / live fixtures
        if status.upper() not in ("FT", "AET", "AP", "AOT"):
            continue

        home_score = int(scores[0])
        away_score = int(scores[1])

        is_home   = team_name.lower() in home.lower()
        our_goals = home_score if is_home else away_score
        opp_goals = away_score if is_home else home_score

        results.append({
            "date":       date,
            "home":       home,
            "away":       away,
            "home_score": home_score,
            "away_score": away_score,
            "result":     _derive_wdl(our_goals, opp_goals),
            "our_goals":  our_goals,
            "opp_goals":  opp_goals,
            "is_home":    is_home,
        })

    return results


def extract_season_stats(html: str) -> dict:
    """
    Pull the large display-card numbers: Matches, Goals scored, Goals conceded, Assists.
    Uses the textStyle_assistive.default (label) + textStyle_display.large (value) pattern.
    """
    pattern = (
        r"textStyle_assistive\.default[^>]*>([^<]+)</span>"
        r".*?"
        r"textStyle_display\.large[^>]*>(\d+)</span>"
    )
    pairs = re.findall(pattern, html, re.DOTALL)
    stats = {}
    for label, value in pairs:
        key = label.strip().lower()
        stats[key] = int(value)
    return stats


def parse_team_page(filepath: str, team_name: str | None = None) -> dict:
    """
    Parse a Sofascore team page.
    Returns a dict with form, goals, and full match history.
    """
    html = load_html_from_mhtml(filepath)

    if not team_name:
        team_name = detect_team_name_from_title(html)
        if not team_name:
            raise ValueError("Could not detect team name from page title. Pass it explicitly.")

    history = extract_match_history(html, team_name)

    last5                = history[:5]
    form_last5           = ",".join(r["result"] for r in last5)
    goals_scored_last5   = sum(r["our_goals"] for r in last5)
    goals_conceded_last5 = sum(r["opp_goals"] for r in last5)

    season                = extract_season_stats(html)
    season_goals_scored   = season.get("goals scored")
    season_goals_conceded = season.get("goals conceded")

    return {
        "team":                    team_name,
        "source_file":             os.path.basename(filepath),
        "form_last5":              form_last5,
        "goals_scored_last5":      goals_scored_last5,
        "goals_conceded_last5":    goals_conceded_last5,
        "season_goals_scored":     season_goals_scored,
        "season_goals_conceded":   season_goals_conceded,
        "match_history":           history,
    }


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    print("SofaScore Batch Parser")
    print("=" * 40)

    batch_result = process_sofascore_batch(STATS_DIR, OUTPUT_FILE)

    print("\n" + "=" * 40)
    print("BATCH PROCESSING COMPLETE")
    print("=" * 40)
    print(f"Files found:     {batch_result['batch_info']['total_files_found']}")
    print(f"Files processed: {batch_result['batch_info']['files_processed']}")
    print(f"Files skipped:   {batch_result['batch_info']['files_skipped']}")
    print(f"Output file:     {batch_result['batch_info']['output_file']}")

    if batch_result["results"]:
        print("\nProcessed files:")
        for result in batch_result["results"]:
            if result["page_type"] == "match":
                ctx = result["match_context"]
                h2h = result.get("h2h_history", [])
                summ = result.get("h2h_summary", {})
                print(
                    f"  📊 {result['source_file']} → "
                    f"{ctx['home_team']} vs {ctx['away_team']} ({ctx['tournament']}) | "
                    f"H2H: {len(h2h)} match(es) found"
                )
                if summ:
                    print(
                        f"      {summ['team']}: "
                        f"W{summ['wins']} D{summ['draws']} L{summ['losses']} "
                        f"GF{summ['goals_for']} GA{summ['goals_against']}"
                    )
                for m in h2h:
                    print(
                        f"      {m['date']}  {m['home']} {m['home_score']}-{m['away_score']} {m['away']}"
                        f"  [{m['result']}]  {m.get('competition','')}"
                    )
            else:
                print(
                    f"  👥 {result['source_file']} → {result['team']} "
                    f"(form: {result['form_last5']})"
                )