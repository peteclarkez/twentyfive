# AI Benchmarking Guide

This document describes how the AI players in Twenty-Five are evaluated, the benchmarks
that have been run, and what the results tell us about each AI's playing style.

---

## AI Players

| Key | Class | Description |
|-----|-------|-------------|
| `random` | `RandomPlayer` | Plays a random legal card every time — baseline only |
| `heuristic` | `HeuristicPlayer` | Rule-based strategy derived from STRATEGY.md |
| `enhanced` | `EnhancedHeuristicPlayer` | Heuristic + 7 enhancements (see below) |
| `mcts` | `MCTSPlayer` | Paranoid UCB1 Monte Carlo Tree Search (500 sims default) |

---

## Benchmark 1: Mixed Competition (Individual Win Rate)

**Setup:** One player of each AI type per game. Seats are shuffled randomly each game
to cancel position and dealer bias. The winner is whoever first reaches 25 points.

**Metric:** Win percentage, average final score, average rounds per game.

**Run with:**
```bash
python -m twentyfive.benchmark --games 50 --seed 42 --mcts-sims 50
```

### Results (50 games, MCTS 50 sims, seed 42)

| AI Type     | Wins | Win%  | Avg Score | Avg Rounds |
|-------------|------|-------|-----------|------------|
| MCTS (50)   |  18  | 36.0% |   15.5    |    2.6     |
| Heuristic   |  14  | 28.0% |   15.1    |    2.6     |
| Enhanced    |  11  | 22.0% |   13.9    |    2.6     |
| Random      |   7  | 14.0% |   11.4    |    2.6     |

**Interpretation:** MCTS wins most often because it plays a purely optimal individual
strategy. Enhanced underperforms Heuristic in individual competition because some of its
enhancements (E6, E7) are cooperative — they preserve collective defensive resources at
the cost of personal gain. In a free-for-all where no other player reciprocates, this
is a net loss.

---

## Benchmark 2: Cooperative / Social Play (Game Length)

**Setup:** All four seats filled with the same AI type. Each configuration is run
independently against the same seed so results are comparable.

**Metric:** Average number of rounds per game.

**Theory:** In Twenty-Five, preventing the leader from winning is a social obligation
(see STRATEGY.md — "The Core Social Contract"). A game where players cooperate
effectively to suppress the leader will naturally last longer. A game where players
chase individual points will end faster, as one player accumulates tricks unchecked.

> *Average rounds per game is therefore a proxy for how well a set of AI players
> embodies the cooperative spirit of 25s.*

**Run with:**
```python
# from twentyfive/benchmark.py internals
_run_game(["enhanced", "enhanced", "enhanced", "enhanced"], simulations=50)
_run_game(["mcts", "mcts", "mcts", "mcts"], simulations=50)
```

### Results (50 games each, MCTS 50 sims, seed 42)

| Config       | Avg Rounds | Median | Min | Max |
|--------------|------------|--------|-----|-----|
| 4 × Enhanced |    2.58    |   3.0  |  2  |  4  |
| 4 × MCTS(50) |    2.48    |   2.0  |  1  |  4  |

**Round distribution:**

| Rounds | 4 × Enhanced | 4 × MCTS(50) |
|--------|--------------|--------------|
|   1    |      0       |      2       |
|   2    |     23       |     25       |
|   3    |     25       |     20       |
|   4    |      2       |      3       |

**Interpretation:**

- Enhanced games have a **higher median (3 vs 2)** — most games go the full distance.
- MCTS produced **2 one-round blowouts** (no cooperative suppression at all); Enhanced had none.
- Enhanced games produce **more 3-round games** (25 vs 20), suggesting the leader is
  being held down for longer before winning through.

### Results (100 games each, MCTS 100 sims, seed 42)

| Config        | Avg Rounds | Median | StdDev | Min | Max |
|---------------|------------|--------|--------|-----|-----|
| 4 × Enhanced  |    2.57    |   3.0  |  0.56  |  2  |  4  |
| 4 × MCTS(100) |    2.70    |   3.0  |  0.69  |  1  |  4  |

**Round distribution:**

| Rounds | 4 × Enhanced | 4 × MCTS(100) |
|--------|--------------|---------------|
|   1    |   0  ( 0%)   |   2  ( 2%)    |
|   2    |  46  (46%)   |  37  (37%)    |
|   3    |  51  (51%)   |  50  (50%)    |
|   4    |   3  ( 3%)   |  11  (11%)    |

*t = −1.47 (not significant at p < 0.05)*

**Interpretation at 100 sims:** With more MCTS simulations, the picture becomes more
nuanced. MCTS's avg rounds edge slightly higher (2.70 vs 2.57), driven by more 4-round
games — suggesting that at higher sim counts MCTS produces more genuine back-and-forth
as each player finds better defensive moves. However, the difference is not statistically
significant (|t| < 2), and MCTS still produces occasional 1-round blowouts while Enhanced
never does. Enhanced's tighter standard deviation (0.56 vs 0.69) reflects more
consistent game lengths, which aligns with its explicit anti-blowout design.

**Overall conclusion:** Enhanced and MCTS produce comparable game lengths. Enhanced
consistently avoids blowouts (zero 1-round games across both runs); MCTS at higher
sim counts generates more very long games but also more very short ones. For the most
socially authentic 25s experience, Enhanced's consistency is the stronger signal.

---

## Enhanced Player Enhancements

The `EnhancedHeuristicPlayer` adds seven improvements over `HeuristicPlayer`:

| # | Name | Description | Impact |
|---|------|-------------|--------|
| E1 | Card tracking | When leading, prefer a suit where you hold the highest remaining card (dominance detection) | More efficient non-trump leads |
| E2 | Endgame commit | In tricks 4–5, lead trump aggressively even without a danger player | Prevents wasted hands late |
| E3 | Multi-opponent | Treat the score leader as dangerous at ≥15 pts, not only ≥20 pts | Earlier defensive response |
| E4 | Rob quality | Prefer discarding a singleton non-trump when robbing (go void in that suit) | Better hand structure after rob |
| E5 | Don't over-trump | Use non-trump winners before spending trump when following | Preserves trump for later tricks |
| E6 | Let safe player win | When following, if a ≥20 pt danger player has played and is *losing*, don't spend trump to win — let the safe current leader keep it. **Disabled by default** (`_e6_enabled = False`). | Intended for cooperative / personality variants |
| E7 | Weak trump lead | In tricks 4–5 only: when leading against a ≥20 pt danger player and I'm not close to winning myself (<15 pts), only lead trump if it is Queen-rank or stronger | Preserves collective defensive trump |

### Trade-off: Cooperative vs Competitive

E6 and E7 reflect the social contract of 25s — avoiding moves that waste collective
defensive resources. In a mixed game against purely competitive AIs, these behaviours
hurt Enhanced's individual win rate because no other player reciprocates. In human play
(or in homogeneous Enhanced games), they produce longer, more contested games.

**E6** is disabled by default so Enhanced remains competitive in mixed benchmarks.
It is available as an opt-in flag (`player._e6_enabled = True`) for future cooperative
personality variants.

**E7** is restricted to tricks 4–5 to avoid hurting early-game trump pressure while
still influencing the critical endgame decisions.

---

## Running Benchmarks

### Standard mixed benchmark (recommended baseline)

```bash
python -m twentyfive.benchmark --games 50 --seed 42 --mcts-sims 50
```

### Reproducible full run (slower — MCTS at 500 sims)

```bash
python -m twentyfive.benchmark --games 20 --seed 42
```

### Cooperative comparison (inline script)

```python
import random, statistics
from twentyfive.benchmark import _run_game

for label, ai_types in [
    ("4 × Enhanced", ["enhanced"] * 4),
    ("4 × MCTS(50)", ["mcts"] * 4),
]:
    random.seed(42)
    rounds = [_run_game(ai_types, simulations=50)[2] for _ in range(50)]
    print(f"{label}: avg={statistics.mean(rounds):.2f}  median={statistics.median(rounds)}")
```

---

## Historical Results

### Mixed competition (Benchmark 1)

| Date       | Run            | Enhanced Win% | Heuristic Win% | Notes |
|------------|----------------|---------------|----------------|-------|
| 2026-03-03 | 50g, MCTS 100s | 24% | 30% | First run after E6/E7 added |
| 2026-03-03 | 50g, MCTS 100s | 18% | 26% | After hard_danger / my_score threshold fixes |
| 2026-03-03 | 200g, MCTS 50s | 19.5% | 29.5% | Large run; E6 on, E7 not endgame-gated |
| 2026-03-03 | 50g, MCTS 50s  | 22%  | 28%  | **Current** — E6 off by default, E7 endgame-only |

### Cooperative game length (Benchmark 2)

| Date       | Run              | 4×Enhanced avg | 4×MCTS avg | Notes |
|------------|------------------|----------------|------------|-------|
| 2026-03-03 | 50g, MCTS 50s    | 2.58           | 2.48       | First cooperative run; Enhanced longer |
| 2026-03-03 | 100g, MCTS 100s  | 2.57           | 2.70       | Difference not significant (t = −1.47); Enhanced has tighter distribution, zero blowouts |
