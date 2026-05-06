"""
log_actuals.py  —  Post-Round Results Logger
=============================================
Appends actual results to the most recent unscored forecast file.
Works across all three jackpots from the Chronos root folder.

Location: C:/Users/User/Desktop/Chronos/log_actuals.py

Usage:
    # Option A: inline results (fastest)
    python log_actuals.py --jackpot midweek --results "1 X 2 1 X 1 2 X 1 1 2 X 1"

    # Option A with scores
    python log_actuals.py --jackpot midweek --results "1 X 2 1 X 1 2 X 1 1 2 X 1" --scores "2-1 0-0 1-2 1-0 2-2 3-1 0-1 1-1 2-0 1-0 0-2 1-1 2-1"

    # Option B: results file
    python log_actuals.py --jackpot mozzart --file mozzart/output/results.json

    # Option C: interactive prompt (default when no --results or --file)
    python log_actuals.py --jackpot sportpesa

Jackpot values: midweek | mozzart | sportpesa

What this script does:
    1. Finds most recent unscored forecast file in the jackpot output folder
    2. Accepts actual results via inline / file / interactive
    3. Computes scores for all tickets, distribution error, signal accuracy
    4. Appends 'actuals' block to the forecast JSON — original unchanged
    5. Prints a clean post-round report

What this script does NOT do:
    - Modify any prediction logic
    - Retrain any model
    - Touch any file other than the target forecast JSON
"""

import json
import glob
import os
import argparse
import re
from datetime import datetime

# ================================================================
# JACKPOT CONFIG
# ================================================================
JACKPOT_CONFIG = {
    "midweek": {
        "output_dir" : "midweek/output",
        "pattern"    : "midweek_forecast_*.json",
        "num_games"  : 13,
        "label"      : "SportPesa Mid-Week Jackpot (13 games)",
    },
    "mozzart": {
        "output_dir" : "mozzart/output",
        "pattern"    : "mozzart_forecast_*.json",
        "num_games"  : 16,
        "label"      : "Mozzart Daily Jackpot (16 games)",
    },
    "sportpesa": {
        "output_dir" : "sportpesa/output",
        "pattern"    : "sportpesa_forecast_*.json",
        "num_games"  : 17,
        "label"      : "SportPesa Mega Jackpot (17 games)",
    },
}

VALID_RESULTS = {"1", "X", "2"}


# ================================================================
# 1. FIND MOST RECENT UNSCORED FORECAST
# ================================================================
def find_unscored_forecast(output_dir, pattern):
    """
    Returns the most recent forecast file that has no 'actuals' block.
    Raises clear errors if nothing found.
    """
    files = sorted(
        glob.glob(os.path.join(output_dir, pattern)),
        key=os.path.getmtime,
        reverse=True,  # most recent first
    )

    if not files:
        raise FileNotFoundError(
            f"No forecast files found in:\n  {output_dir}\n"
            f"Run the forecast script first."
        )

    for fpath in files:
        with open(fpath, encoding="utf-8") as f:
            data = json.load(f)
        if "actuals" not in data:
            return fpath, data

    # All files already scored
    raise ValueError(
        f"All {len(files)} forecast file(s) in {output_dir} "
        f"already have actuals logged.\n"
        f"Most recent: {os.path.basename(files[0])}"
    )


# ================================================================
# 2. RESULT INPUT — THREE OPTIONS
# ================================================================
def parse_inline_results(results_str, num_games):
    """Parse space-separated results string: '1 X 2 1 X ...'"""
    parts = results_str.strip().upper().split()
    if len(parts) != num_games:
        raise ValueError(
            f"Expected {num_games} results, got {len(parts)}.\n"
            f"Input: {results_str}"
        )
    invalid = [p for p in parts if p not in VALID_RESULTS]
    if invalid:
        raise ValueError(
            f"Invalid result(s): {invalid}\n"
            f"Only 1, X, or 2 are valid."
        )
    return parts


def parse_inline_scores(scores_str, num_games):
    """
    Parse space-separated scorelines: '2-1 0-0 1-2 ...'
    Validates format but allows None for missing scores.
    """
    if not scores_str:
        return [None] * num_games

    parts = scores_str.strip().split()
    if len(parts) != num_games:
        raise ValueError(
            f"Expected {num_games} scores, got {len(parts)}.\n"
            f"Use format: '2-1 0-0 1-2' with a score per match."
        )

    validated = []
    for p in parts:
        if re.match(r'^\d+-\d+$', p):
            validated.append(p)
        elif p.lower() in ("none", "-", "?", ""):
            validated.append(None)
        else:
            raise ValueError(
                f"Invalid score format: '{p}'\n"
                f"Use '2-1' format or '-' for unknown."
            )
    return validated


def load_results_file(fpath, num_games):
    """
    Load results from a JSON file.
    Expected format:
    {
        "results": ["1","X","2",...],
        "scores":  ["2-1","0-0","-",...]   <- optional
    }
    """
    if not os.path.exists(fpath):
        raise FileNotFoundError(f"Results file not found:\n  {fpath}")

    with open(fpath, encoding="utf-8") as f:
        data = json.load(f)

    if "results" not in data:
        raise ValueError(
            f"Results file must have a 'results' key.\n"
            f"Found keys: {list(data.keys())}"
        )

    results = [str(r).upper() for r in data["results"]]
    scores  = data.get("scores", [None] * num_games)

    if len(results) != num_games:
        raise ValueError(
            f"Expected {num_games} results, got {len(results)}."
        )

    return results, scores


def interactive_input(forecast_data, num_games):
    """
    Prompt user match by match.
    Shows match name for context. Validates each entry.
    """
    results = []
    scores  = []

    # Get match list from base ticket for display
    matches = []
    for scenario in ["base", "conservative", "draw_heavy"]:
        ticket_data = forecast_data.get("tickets", {}).get(scenario, {})
        if "matches" in ticket_data:
            matches = ticket_data["matches"]
            break

    print(f"\n  Enter results for each match (1 = Home Win, X = Draw, 2 = Away Win)")
    print(f"  For score enter format '2-1', or press Enter to skip\n")

    for i in range(num_games):
        # Build display name
        if matches and i < len(matches):
            m       = matches[i]
            matchup = f"{m.get('home', m.get('home_team', '?'))} vs {m.get('away', m.get('away_team', '?'))}"
        else:
            matchup = f"Match {i+1}"

        # Result input with validation
        while True:
            raw = input(f"  [{i+1:>2}] {matchup:<40} Result (1/X/2): ").strip().upper()
            if raw in VALID_RESULTS:
                results.append(raw)
                break
            print(f"       Invalid — enter 1, X, or 2")

        # Score input (optional)
        raw_score = input(f"       Score (e.g. 2-1, or Enter to skip): ").strip()
        if raw_score and re.match(r'^\d+-\d+$', raw_score):
            scores.append(raw_score)
        else:
            scores.append(None)

    return results, scores


# ================================================================
# 3. SCORING ENGINE
# ================================================================
def score_ticket(predicted, actuals):
    """Count correct predictions."""
    return sum(1 for p, a in zip(predicted, actuals) if p == a)


def compute_distribution_error(forecast, actuals):
    """
    Compare Chronos P50 forecast vs actual distribution.
    Returns error per outcome and whether within ±1 draw.
    """
    actual_draws = actuals.count("X")
    actual_homes = actuals.count("1")
    actual_aways = actuals.count("2")

    p50_draws = forecast.get("total_draws", {}).get("P50", 0)
    p50_homes = forecast.get("total_homes", {}).get("P50", 0)
    p50_aways = forecast.get("total_aways", {}).get("P50", 0)

    draw_error = actual_draws - round(p50_draws)
    home_error = actual_homes - round(p50_homes)
    away_error = actual_aways - round(p50_aways)

    return {
        "predicted_draws" : round(p50_draws, 1),
        "predicted_homes" : round(p50_homes, 1),
        "predicted_aways" : round(p50_aways, 1),
        "actual_draws"    : actual_draws,
        "actual_homes"    : actual_homes,
        "actual_aways"    : actual_aways,
        "draw_error"      : draw_error,
        "home_error"      : home_error,
        "away_error"      : away_error,
        "draw_within_1"   : abs(draw_error) <= 1,
        "draw_direction"  : "over" if draw_error < 0 else
                            "under" if draw_error > 0 else "exact",
    }


def evaluate_signals(card_signals, actuals):
    """
    Check whether active signal flags predicted correctly.
    Returns per-signal verdict for the prediction log.
    """
    actual_draws = actuals.count("X")
    actual_homes = actuals.count("1")
    actual_aways = actuals.count("2")
    n            = len(actuals)

    verdicts = {}

    # mirror_ge3 -> should produce draw-heavy round (draws >= 7 for 16, >= 5 for 13)
    draw_heavy_threshold = max(5, round(n * 0.40))
    decisive_threshold   = max(2, round(n * 0.20))

    if card_signals.get("mirror_ge3_flag"):
        correct = actual_draws >= draw_heavy_threshold
        verdicts["mirror_ge3"] = {
            "fired"   : True,
            "signal"  : "draw-heavy expected",
            "actual"  : f"{actual_draws} draws",
            "correct" : correct,
        }

    if card_signals.get("clear_fav_ge3_flag"):
        correct = actual_draws <= decisive_threshold
        verdicts["clear_fav_ge3"] = {
            "fired"   : True,
            "signal"  : "decisive expected",
            "actual"  : f"{actual_draws} draws",
            "correct" : correct,
        }

    if card_signals.get("away_fav_ge5_flag"):
        correct = actual_aways >= round(n * 0.35)
        verdicts["away_fav_ge5"] = {
            "fired"   : True,
            "signal"  : "away-heavy expected",
            "actual"  : f"{actual_aways} aways",
            "correct" : correct,
        }

    if card_signals.get("strong_fav_trap_flag"):
        verdicts["strong_fav_trap"] = {
            "fired"   : True,
            "signal"  : "upsets likely",
            "actual"  : f"upset rate calculable from results",
            "correct" : None,  # computed separately
        }

    return verdicts


def compute_per_match_accuracy(tickets, actuals):
    """
    Per-outcome accuracy across all tickets.
    Useful for identifying whether homes/draws/aways are failing.
    """
    # Use base ticket for per-outcome breakdown
    base_ticket = tickets.get("base", {}).get("ticket", [])
    if not base_ticket:
        return {}

    breakdown = {}
    for outcome in ["1", "X", "2"]:
        label     = {"1": "Home", "X": "Draw", "2": "Away"}[outcome]
        predicted = [i for i, p in enumerate(base_ticket) if p == outcome]
        correct   = sum(1 for i in predicted if actuals[i] == outcome)
        total     = len(predicted)
        breakdown[label] = {
            "predicted" : total,
            "correct"   : correct,
            "accuracy"  : round(correct / total * 100, 1) if total > 0 else None,
        }

    return breakdown


# ================================================================
# 4. REPORT PRINTER
# ================================================================
def print_report(forecast_data, actuals, scores_list, actuals_block):
    num_games  = len(actuals)
    tickets    = forecast_data.get("tickets", {})
    card_file  = forecast_data.get("card_file", "unknown")
    dist       = actuals_block["distribution"]
    dist_err   = actuals_block["distribution_error"]
    sig_eval   = actuals_block["signal_accuracy"]
    per_match  = actuals_block["per_match_accuracy"]
    ticket_scores = actuals_block["ticket_scores"]

    print("\n" + "=" * 70)
    print("  POST-ROUND REPORT")
    print(f"  Card: {card_file}")
    print("=" * 70)

    # Match-by-match results
    print(f"\n  {'#':<4} {'Match':<36} {'Pred':<5} {'Act':<5} {'Score':<7} OK?")
    print("  " + "-" * 62)

    base_ticket = tickets.get("base", {}).get("ticket", [])
    base_matches = tickets.get("base", {}).get("matches", [])

    for i in range(num_games):
        pred    = base_ticket[i] if i < len(base_ticket) else "?"
        actual  = actuals[i]
        score   = scores_list[i] if scores_list else None
        correct = "✓" if pred == actual else "✗"
        matchup = ""
        if base_matches and i < len(base_matches):
            m       = base_matches[i]
            matchup = f"{m.get('home','?')} vs {m.get('away','?')}"
        score_str = score if score else "-"
        print(f"  {i+1:<4} {matchup:<36} {pred:<5} {actual:<5} {score_str:<7} {correct}")

    # Ticket scores
    print(f"\n  TICKET SCORES:")
    best_score = max(ticket_scores.values())
    for scenario, sc in ticket_scores.items():
        bar    = "█" * sc
        marker = " <- BEST" if sc == best_score else ""
        print(f"    {scenario:<14} {sc:>2}/{num_games}  {bar}{marker}")

    # Distribution accuracy
    print(f"\n  DISTRIBUTION (Chronos P50 vs Actual):")
    print(f"    {'':12} {'Predicted':>10} {'Actual':>8} {'Error':>7} {'Within ±1':>10}")
    print("    " + "-" * 48)
    for label, pred_key, act_key, err_key in [
        ("Draws", "predicted_draws", "actual_draws", "draw_error"),
        ("Homes", "predicted_homes", "actual_homes", "home_error"),
        ("Aways", "predicted_aways", "actual_aways", "away_error"),
    ]:
        pred = dist_err[pred_key]
        act  = dist_err[act_key]
        err  = dist_err[err_key]
        w1   = "YES" if abs(err) <= 1 else "no"
        print(f"    {label:<12} {pred:>10.1f} {act:>8} {err:>+7}  {w1:>10}")

    # Per-match accuracy breakdown
    if per_match:
        print(f"\n  PER-OUTCOME ACCURACY (Base ticket):")
        for outcome_label, data in per_match.items():
            acc = f"{data['accuracy']}%" if data['accuracy'] is not None else "N/A"
            print(f"    {outcome_label:<8} predicted={data['predicted']}  "
                  f"correct={data['correct']}  accuracy={acc}")

    # Signal evaluation
    if sig_eval:
        print(f"\n  SIGNAL ACCURACY:")
        for sig, v in sig_eval.items():
            correct_str = (
                "CORRECT" if v["correct"] is True else
                "WRONG"   if v["correct"] is False else
                "N/A"
            )
            print(f"    {sig:<20} {v['signal']:<25} -> {v['actual']:<15} {correct_str}")

    print(f"\n  Saved to: {actuals_block.get('_saved_to', 'forecast file')}")
    print("=" * 70)


# ================================================================
# 5. MAIN
# ================================================================
def main():
    parser = argparse.ArgumentParser(
        description="Log actual results for a Chronos jackpot forecast."
    )
    parser.add_argument(
        "--jackpot", required=True,
        choices=["midweek", "mozzart", "sportpesa"],
        help="Which jackpot to log results for"
    )
    parser.add_argument(
        "--results", default=None,
        help="Space-separated results string: '1 X 2 1 X 1 2 X 1 1 2 X 1'"
    )
    parser.add_argument(
        "--scores", default=None,
        help="Space-separated scorelines: '2-1 0-0 1-2 ...' (optional)"
    )
    parser.add_argument(
        "--file", default=None,
        help="Path to a JSON results file with 'results' and optional 'scores' keys"
    )
    parser.add_argument(
        "--target", default=None,
        help="Specific forecast filename to score (default: most recent unscored)"
    )
    args = parser.parse_args()

    config    = JACKPOT_CONFIG[args.jackpot]
    num_games = config["num_games"]

    print("=" * 70)
    print(f"  LOG ACTUALS — {config['label']}")
    print("=" * 70)

    # --- Find forecast file ---
    if args.target:
        fpath = os.path.join(config["output_dir"], args.target)
        if not os.path.exists(fpath):
            raise FileNotFoundError(f"Target file not found:\n  {fpath}")
        with open(fpath, encoding="utf-8") as f:
            forecast_data = json.load(f)
        if "actuals" in forecast_data:
            print(f"  WARNING: This file already has actuals logged.")
            confirm = input("  Overwrite? (yes/no): ").strip().lower()
            if confirm != "yes":
                print("  Aborted.")
                return
    else:
        fpath, forecast_data = find_unscored_forecast(
            config["output_dir"], config["pattern"]
        )

    print(f"\n  Forecast file : {os.path.basename(fpath)}")
    print(f"  Generated at  : {forecast_data.get('generated_at','unknown')}")
    print(f"  Card          : {forecast_data.get('card_file','unknown')}")
    print(f"  Expected games: {num_games}")

    # --- Get results ---
    scores_list = None

    if args.file:
        print(f"\n  Loading results from file: {args.file}")
        results, scores_list = load_results_file(args.file, num_games)

    elif args.results:
        print(f"\n  Parsing inline results ...")
        results = parse_inline_results(args.results, num_games)
        if args.scores:
            scores_list = parse_inline_scores(args.scores, num_games)

    else:
        print(f"\n  Interactive mode — enter results match by match:")
        results, scores_list = interactive_input(forecast_data, num_games)

    if scores_list is None:
        scores_list = [None] * num_games

    print(f"\n  Results accepted: {' - '.join(results)}")

    # --- Compute scores ---
    tickets       = forecast_data.get("tickets", {})
    ticket_scores = {}
    for scenario, ticket_data in tickets.items():
        predicted = ticket_data.get("ticket", [])
        if predicted:
            ticket_scores[scenario] = score_ticket(predicted, results)

    best_ticket = max(ticket_scores, key=ticket_scores.get) if ticket_scores else None

    # --- Distribution error ---
    forecast   = forecast_data.get("forecast", {})
    dist_error = compute_distribution_error(forecast, results)

    # --- Signal accuracy ---
    card_signals = forecast_data.get("card_signals", {})
    sig_accuracy = evaluate_signals(card_signals, results)

    # --- Per-match accuracy ---
    per_match_acc = compute_per_match_accuracy(tickets, results)

    # --- Build actuals block ---
    actuals_block = {
        "logged_at"         : datetime.now().strftime("%Y-%m-%d_%H%M%S"),
        "results"           : results,
        "scores"            : scores_list,
        "distribution"      : {
            "actual_draws"  : results.count("X"),
            "actual_homes"  : results.count("1"),
            "actual_aways"  : results.count("2"),
        },
        "ticket_scores"     : ticket_scores,
        "best_ticket"       : best_ticket,
        "best_score"        : ticket_scores.get(best_ticket, 0) if best_ticket else 0,
        "distribution_error": dist_error,
        "signal_accuracy"   : sig_accuracy,
        "per_match_accuracy": per_match_acc,
    }

    # --- Write back to forecast file ---
    forecast_data["actuals"] = actuals_block
    actuals_block["_saved_to"] = os.path.basename(fpath)

    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(forecast_data, f, indent=2)

    # --- Print report ---
    print_report(forecast_data, results, scores_list, actuals_block)


if __name__ == "__main__":
    main()
