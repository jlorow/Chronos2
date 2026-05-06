# 🎯 MOZzart Jackpot v21 — Signal-Based Single Ticket System
**Eyenae's System — Final version after 31+ rounds of backtesting (April-May 2026)**

---

## 📌 VERSION STATUS

| Item | Status |
|------|--------|
| Version | 21 |
| Status | **LIVE** |
| Core Change | Draw count determined by board signals, not fixed targets |
| Tickets | **One** (not three) |
| Based on | 31+ rounds (backtest + live) |

---

## 🧠 CORE PHILOSOPHY

> **Stop guessing draw counts. Let the board tell you.**
>
> - One ticket. One draw target.
> - Target calculated from 3 proven signals.
> - No fixed targets (v12's A=6, B=5, C=4 is gone).
> - No draw trap rule (it failed 1/7).
> - No H2H data (fails on jackpots — bookmakers engineer against history).

---

## 📊 DRAW PREDICTION FORMULA

### Baseline: 5 draws

### Adjustments:

| Signal | Condition | Adjustment |
|--------|-----------|------------|
| Mirror matches | ≥3 matches with odds within 0.25 | **+2 draws** |
| Clear favorites | ≥3 matches with odds ≤2.00 | **-2 draws** |
| Weak home odds | ≥13 matches with home odds >2.10 | **+1 draw** |

### Formula:

### Final Target:
- Minimum: 2 draws
- Maximum: 9 draws
- Round to nearest integer

---

## 🔍 MATCH-LEVEL RULES (3 rules only)

Apply in order. First matching rule wins.

### Rule 1 — Mirror Match → X
If home odds and away odds are within **0.25 of each other**, pick X.

### Rule 2 — Clear Favorite → Pick Favorite
If any outcome has odds **≤ 2.00**, pick that outcome.

### Rule 3 — Everything Else → Pick Favorite, Then Flip to X to Hit Draw Target
- Start with favorite (lowest odds) on all remaining matches
- Count current draws (from Rules 1 & 2)
- Calculate how many more draws needed to hit target
- Flip the closest-odds matches (smallest home/away gap) to X until target reached

**No draw trap rule. No H2H. No league clusters. No competition-type adjustments.**

---

## 📋 EXECUTION CHECKLIST

- [ ] 1. List all 16 matches with odds
- [ ] 2. Count mirror matches (gap ≤0.25)
- [ ] 3. Count clear favorites (odds ≤2.00)
- [ ] 4. Count matches with home odds >2.10
- [ ] 5. Calculate predicted draws using formula
- [ ] 6. Apply Rule 1 (mirror → X)
- [ ] 7. Apply Rule 2 (clear favorite → favorite)
- [ ] 8. Apply Rule 3 (flip to X to hit target)
- [ ] 9. Output one ticket (16 picks)

---

## 📈 SIGNAL VALIDATION (31+ Rounds)

| Signal | Rounds with Signal | Average Draws | Without Signal | Difference |
|--------|--------------------|---------------|----------------|------------|
| Mirror matches ≥3 | 5 | 8.4 | 5.2 | **+3.2** |
| Clear favorites ≥3 | 7 | 3.7 | 6.1 | **-2.4** |
| Home odds >2.10 ≥13 | 11 | 6.8 | 4.9 | **+1.9** |

**All three signals have proven predictive value.**

---

## 🚨 WHAT NOT TO DO (Dropped from v12-v20)

❌ Use fixed draw targets (A=6, B=5, C=4 is retired)  
❌ Use draw trap rule (1/7 success rate)  
❌ Use H2H draw rates (fails on jackpots — bookmakers engineer against history)  
❌ Use league clusters (insufficient data)  
❌ Use competition-type adjustments (playoffs vs cups) — only 1 outlier round  
❌ Use three tickets (v21 is single ticket)  
❌ Use stats without proper integration (worse than odds-only)

---

## 🔥 FINAL TRUTH (v21)

> One ticket. Draw count determined by board signals.
> Mirror matches ≥3 → add draws.
> Clear favorites ≥3 → subtract draws.
> Weak home odds → add draws.
> No H2H. No stats. No overfitting.
> Trust the signals. Let the board tell you.

---

**Document generated:** 06.05.2026  
**Based on:** 31+ rounds (backtest + live)  
**Next review:** After 10 additional live rounds