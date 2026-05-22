# Chronos 2.0 — Implementation Prompt
*For Freebuff CLI. Run from `C:/Users/User/Desktop/Chronos2/`.*

---

## Overview

Chronos 2.0 is a clone of Chronos 1.0 with one core behavioural change:
the 5 highest-entropy matches on each card receive **Double Chance (DC) picks**
instead of single picks (1/X/2). All other matches still get single picks.
Everything else — data loading, Chronos forecasting, ticket building, Supabase,
app.py — is identical to Chronos 1.0.

---

## Step 0 — Clone the repo

Before touching any code, clone the existing Chronos folder:

```
xcopy /E /I /H "C:\Users\User\Desktop\Chronos" "C:\Users\User\Desktop\Chronos2"
```

Then work exclusively inside `C:/Users/User/Desktop/Chronos2/`.
Do NOT modify anything in the original `C:/Users/User/Desktop/Chronos/`.

---

## Files to modify

Only these three forecast scripts:

- `mozzart/mozzart_forecast.py`
- `midweek/midweek_forecast.py`
- `sportpesa/sportpesa_forecast.py`

All three receive identical changes. The logic is the same across all three —
only the `DC_COUNT` constant differs (all are 5, stated explicitly per script
for clarity).

---

## The Chronos 2.0 Change — Detailed Spec

### Concept

For each match on the card, compute **Shannon entropy** on the implied
probability distribution derived from the bookmaker odds. The 5 matches
with the highest entropy (most uncertain outcome) receive a Double Chance
pick. The remaining matches receive a single pick as normal.

Shannon entropy for a match:
```
H = -sum(p * log2(p) for p in [p1, pX, p2] if p > 0)
Maximum entropy = log2(3) ≈ 1.585 bits (all three outcomes equally likely)
```

DC pick type assignment (exclude the least likely outcome):
```
min_outcome = argmin(p1, pX, p2)
if min_outcome == "1":  DC pick = "X2"
if min_outcome == "X":  DC pick = "12"
if min_outcome == "2":  DC pick = "1X"
```

This is the same logic that currently flags `pick_type = "Speculative"` in
the existing system — Chronos 2.0 formalises it as the DC assignment rule.

---

### New constant (add near top of each script, after existing constants)

```python
# Chronos 2.0 — number of highest-entropy matches to assign DC picks
DC_COUNT = 5
```

---

### New function — `compute_entropy_dc(matches, analysis)`

Add this function in each script immediately before the `allocate_ticket()`
function. The `matches` argument is the card's match list. The `analysis`
argument is the list of per-match analysis dicts already computed by
`score_match()` (contains `impl` — the normalised implied probability dict).

```python
def compute_entropy_dc(matches, analysis):
    """
    Chronos 2.0 core: identify the DC_COUNT highest-entropy matches
    and assign their DC pick type.

    Args:
        matches  : list of match dicts from the card
        analysis : list of per-match analysis dicts from score_match()
                   each must contain 'impl': {'1': float, 'X': float, '2': float}

    Returns:
        dc_map : dict mapping match index (int) to DC pick string
                 e.g. {2: "1X", 7: "X2", 9: "12", 11: "1X", 14: "X2"}
    """
    import math

    entropies = []
    for i, ana in enumerate(analysis):
        impl = ana.get("impl", {})
        p1   = impl.get("1", 0.0)
        pX   = impl.get("X", 0.0)
        p2   = impl.get("2", 0.0)

        # Shannon entropy — skip zero-probability outcomes
        H = 0.0
        for p in [p1, pX, p2]:
            if p > 0:
                H -= p * math.log2(p)

        entropies.append((i, H, p1, pX, p2))

    # Sort by entropy descending, take top DC_COUNT
    entropies.sort(key=lambda x: x[1], reverse=True)
    top_dc = entropies[:DC_COUNT]

    dc_map = {}
    for (i, H, p1, pX, p2) in top_dc:
        # Exclude least likely outcome → assign DC pick
        min_prob = min(p1, pX, p2)
        if min_prob == p1:
            dc_pick = "X2"
        elif min_prob == pX:
            dc_pick = "12"
        else:
            dc_pick = "1X"
        dc_map[i] = dc_pick

    return dc_map
```

**Tiebreaker note:** If two matches share identical entropy (rare but possible),
the one with the lower index in the card wins. The `sort` above is stable so
this is handled automatically.

---

### Modify `allocate_ticket()`

The existing `allocate_ticket()` function builds a ticket as a list of single
picks (1/X/2). In Chronos 2.0 it must accept an optional `dc_map` argument
and override the pick for DC matches.

**Change the function signature from:**
```python
def allocate_ticket(analysis, target_counts):
```
**To:**
```python
def allocate_ticket(analysis, target_counts, dc_map=None):
```

Inside `allocate_ticket()`, find the section where the final pick per match
is written to the ticket list. It will look something like:

```python
ticket.append(pick)
```

Replace that line (or the block that determines `pick`) with:

```python
        # Chronos 2.0 — override with DC pick if this match is in dc_map
        if dc_map and i in dc_map:
            ticket.append(dc_map[i])
        else:
            ticket.append(pick)
```

Where `i` is the match index (0-based loop counter already present in the
function). Do NOT change any other logic inside `allocate_ticket()`.

---

### Modify `main()` — call sequence

In `main()`, after `score_match()` has been called for all matches and
`analysis` is fully populated, add the DC computation:

```python
    # Chronos 2.0 — compute entropy-based DC map
    dc_map = compute_entropy_dc(card, analysis)
    print(f"\n  [Chronos 2.0] DC matches (top {DC_COUNT} by entropy):")
    for idx, dc_pick in sorted(dc_map.items()):
        home = card[idx].get("home", card[idx].get("home_team", f"Match {idx+1}"))
        away = card[idx].get("away", card[idx].get("away_team", ""))
        print(f"    [{idx+1:2d}] {home} vs {away}  →  {dc_pick}")
```

Then pass `dc_map` into every `allocate_ticket()` call. Find all three calls
(conservative, base, draw_heavy tickets) and update each:

```python
# BEFORE (existing pattern):
conservative_ticket = allocate_ticket(analysis, conservative_counts)
base_ticket         = allocate_ticket(analysis, base_counts)
draw_heavy_ticket   = allocate_ticket(analysis, draw_heavy_counts)

# AFTER:
conservative_ticket = allocate_ticket(analysis, conservative_counts, dc_map=dc_map)
base_ticket         = allocate_ticket(analysis, base_counts,         dc_map=dc_map)
draw_heavy_ticket   = allocate_ticket(analysis, draw_heavy_counts,   dc_map=dc_map)
```

Note: The exact variable names for the three count dicts may differ slightly
across the three scripts — match them to what already exists, do not rename.

---

### Add DC metadata to output JSON

In the output JSON dict that gets saved at the end of `main()`, add a
top-level `"chronos2"` key:

```python
"chronos2": {
    "version"  : "2.0",
    "dc_count" : DC_COUNT,
    "dc_matches": [
        {
            "match_index" : idx,
            "home"        : card[idx].get("home", card[idx].get("home_team", "")),
            "away"        : card[idx].get("away", card[idx].get("away_team", "")),
            "dc_pick"     : dc_pick,
            "entropy"     : round(entropies_for_json[idx], 4),
        }
        for idx, dc_pick in sorted(dc_map.items())
    ],
},
```

To make `entropies_for_json` available, update `compute_entropy_dc()` to also
return the full entropy list as a second return value:

```python
    # at the end of compute_entropy_dc(), replace:
    return dc_map
    # with:
    entropy_by_index = {e[0]: e[1] for e in entropies}
    return dc_map, entropy_by_index
```

And update the call in `main()`:
```python
dc_map, entropies_for_json = compute_entropy_dc(card, analysis)
```

---

### Update `pick_type` labelling in `classify_match()` (or equivalent)

In the existing system, DC picks are labelled `"Double Chance"` in the
analysis. In Chronos 2.0, DC matches assigned via entropy should be labelled
`"DC-Entropy"` to distinguish them from any legacy DC logic.

Find where `pick_type` is set in `classify_match()` or inside the match
analysis loop. Add this override after `score_match()` is called for each
match, using the dc_map:

```python
        # Chronos 2.0 — label entropy DC matches distinctly
        if dc_map and i in dc_map:
            analysis[i]["pick_type"] = "DC-Entropy"
            analysis[i]["dc_pick"]   = dc_map[i]
```

Note: `dc_map` must be computed before this labelling step. If `classify_match()`
runs inside `score_match()` in the current code, compute `dc_map` first using
a preliminary `analysis` pass, then apply labels in a second pass. If
`pick_type` is set after `score_match()` returns in `main()`, apply the
override there directly.

---

## What NOT to change

- Do not modify `app.py`, `db.py`, `log_actuals.py`, or any utility scripts
- Do not modify batch loading, card loading, or feature engineering
- Do not modify the Chronos forecast section — homes/aways/draws forecasting
  is unchanged
- Do not modify `render_ticket()` in `app.py` — it already handles DC picks
  (picks like "1X", "X2", "12" render correctly as-is in the dataframe)
- Do not modify the Supabase save logic
- Do not change any file paths or output directory structure
- Do not rename any existing functions — only add new ones and extend signatures
  with default-None parameters

---

## Verification checklist after implementation

Run from `C:/Users/User/Desktop/Chronos2/`:

1. `python mozzart/mozzart_forecast.py --model tiny --samples 50`
   - Terminal should print `[Chronos 2.0] DC matches (top 5 by entropy):` with
     exactly 5 matches listed, each showing a DC pick (1X / X2 / 12)
   - Output JSON should have a top-level `"chronos2"` key with 5 entries

2. Open the output JSON and confirm:
   - The 5 DC matches have picks like `"1X"`, `"X2"`, or `"12"` in all 3 tickets
   - The remaining 11 matches have single picks `"1"`, `"X"`, or `"2"`
   - `"chronos2".dc_count` = 5

3. Confirm `C:/Users/User/Desktop/Chronos/` (original) is untouched —
   run `python mozzart/mozzart_forecast.py --model tiny --samples 50` there
   and confirm no DC-Entropy picks appear in its output

4. Repeat step 1 for `midweek/midweek_forecast.py` and
   `sportpesa/sportpesa_forecast.py` — both should show exactly 5 DC matches

5. Confirm the 5 DC matches are the most evenly-matched fixtures on the card
   (eyeball check — they should be games where neither team is a clear favourite)
