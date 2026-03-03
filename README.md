# Twenty-Five (25s)

A Python implementation of **Twenty-Five**, Ireland's national card game.

## About the Game

Twenty-Five is a trick-taking card game with roots going back over 500 years in Ireland,
historically known as *Maw*, then *Spoil-Five*, and eventually *Twenty-Five*. It is best
played with 4–6 players, uses a standard 52-card deck, and has a unique card ranking
system unlike any other common card game — where suit colour determines card strength
and the Ace of Hearts is always a trump card regardless of the trump suit.

The goal is simple: be the first player to reach **25 points** by winning tricks worth
5 points each.

## Playing the Game

```bash
python -m twentyfive
```

You will be prompted for the number of players, their names, and whether each is a
human or an AI. Player types:

| Key | Type | Description |
|-----|------|-------------|
| `H` | Human | Interactive — prompts for card selection each turn |
| `R` | Random AI | Plays a random legal card |
| `A` | Heuristic AI | Rule-based strategy derived from STRATEGY.md |
| `E` | Enhanced AI | Heuristic + card tracking, endgame logic, and rob strategy (default) |
| `M` | MCTS AI | Monte Carlo Tree Search (strongest; slower) |

### Quick start — 1v3

Jump straight into a 4-player game as yourself against three Enhanced AI opponents,
with seats and dealer chosen at random:

```bash
python -m twentyfive --1v3 YourName
```

### View modes

| Flag | Mode | Description |
|------|------|-------------|
| _(none)_ | Hidden-hand | Each player sees only their own cards; AI moves shown inline |
| `--seeall` | Master view | All hands visible simultaneously — good for spectating or testing |

### Benchmarking AI players

```bash
python -m twentyfive.benchmark              # 20 games, all 4 AI types, MCTS at 500 sims
python -m twentyfive.benchmark --games 50 --seed 42 --mcts-sims 100
python -m twentyfive.benchmark --quiet      # suppress per-game progress output
```

See [BENCHMARKING.md](twentyfive/ai/BENCHMARKING.md) for methodology and results.

## Project Status

| Phase | Status | Description |
|-------|--------|-------------|
| Core engine | ✅ Complete | Deck, dealing, trick logic, scoring, rob phase, audit log |
| CLI | ✅ Complete | Hidden-hand and master-view modes, ANSI colour, rob display |
| AI players | ✅ Complete | Random, Heuristic, Enhanced Heuristic, MCTS |
| Benchmark | ✅ Complete | Automated multi-game comparison framework |
| Partnerships | 🔲 Planned | Team play (45s, 110 variants) |
| GUI | 🔲 Planned | To be decided |

## AI Players

The project includes four AI implementations of increasing sophistication. See the
[AI module docs](twentyfive/ai/) for full details:

| Document | Description |
|----------|-------------|
| [AI_APPROACHES.md](twentyfive/ai/AI_APPROACHES.md) | Survey of AI approaches, design rationale, and implementation roadmap |
| [BENCHMARKING.md](twentyfive/ai/BENCHMARKING.md) | Benchmark methodology, results, and cooperative game-length analysis |

## Development

```bash
pip install -e ".[dev]"   # install with dev dependencies
python -m pytest          # run all tests
python -m ruff check .    # lint
python -m mypy twentyfive/  # type check
```

## References

The following sources were used to establish the rules and strategy documented in
[RULES.md](RULES.md) and [STRATEGY.md](STRATEGY.md):

| Source | Description |
|--------|-------------|
| [Britannica — Twenty-Five](https://www.britannica.com/topic/twenty-five) | Overview, history, rules, and the Auction Forty-Fives variant |
| [Irish25s — How to Play](https://irish25s.herokuapp.com/howtoplay) | Online implementation rules including 45s mode and reneging detail |
| [GameRules — Twenty-Five](https://gamerules.com/rules/twenty-five-25/) | Card rankings by suit with full trump lookup tables |
| [OrwellianIreland — 25 (PDF)](http://www.orwellianireland.com/25.pdf) | Scholarly essay by Brian Nugent covering rules, history, etymology, and strategy; most authoritative source on traditional play and the social conventions of the game |
| [YouTube — Riffle Shuffle & Roll](https://www.youtube.com/watch?v=yhMMjVduF1k) | Video walkthrough of a full game with commentary on the ranking system and may-trump rule |
