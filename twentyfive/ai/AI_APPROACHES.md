# AI Player Approaches — Twenty-Five

Reference document for current and planned AI player implementations.

---

## 0. HeuristicPlayer (baseline rule-based AI) ← implemented in Phase 3

`twentyfive/ai/heuristic.py` — a stateless, rule-based player that follows a fixed
priority list derived from STRATEGY.md. No search, no memory — just pattern matching
on the current game state.

### Rob phase
- **Always robs** when a `Rob` move is available (holds Ace of trumps or is dealer
  with the Ace face-up).
- **Discard selection**: throws away the weakest card by `card_global_rank` (highest
  rank number = lowest strength). No regard for suit void-creation.
- Falls back to `PassRob()` when ineligible.

### Trick phase — helper values computed once per call
```python
danger_players = {p.name for p in players if p.name != mine and p.score >= 20}

winners = {card for card in legal_cards
           if trick_winner(current_trick + [TrickPlay(me, card)], ...).player_name == me}

danger_winning = trick_winner(current_trick, ...).player_name in danger_players
five = Card(Rank.FIVE, trump_suit)
```

### Leading (first to play in the trick)
| Condition | Action |
|-----------|--------|
| Danger player exists AND I have trumps | Lead **strongest** trump (smoke them out) |
| Danger player exists, no trumps | Lead **weakest** card overall |
| No danger player | Lead **weakest non-trump**; fall back to weakest trump |

### Following (cards already played)
Priority applied in order — first matching branch wins:

1. **Danger player is currently winning AND I can beat them** → play **strongest** winner
   (including the Five if that's all I have)
2. **Non-Five winner available** → play **weakest** non-Five winner (preserve the Five)
3. **Five is the only winning card** → play Five only if a danger player is winning
   OR this is the last card to be played in the trick; otherwise fall through
4. **Cannot win (or Five withheld)** → play **weakest** legal card

### Round-end phase
Returns `ConfirmRoundEnd()` unconditionally.

### Limitations (addressed by EnhancedHeuristicPlayer in §1)
- Discards weakest card regardless of suit distribution; misses void-creation opportunities
- Only treats opponents at ≥ 20 pts as dangerous; ignores the rising score leader below that
- No memory of which high cards have been played; may lead into an already-stripped suit
- Commits trump aggressively only vs danger players; no endgame escalation in tricks 4–5
- No preference for non-trump winners; may burn trump unnecessarily

---

## 1. Enhanced Heuristics (natural next step from HeuristicPlayer)

The current `HeuristicPlayer` is a first-pass rule-based player. A stronger heuristic
would add:

- **Card tracking** — note which high cards have been played; don't lead a suit that's
  already been stripped from the field
- **Endgame awareness** — tricks 4–5 warrant different strategy (commit trump earlier
  when the round is nearly over)
- **Multi-opponent awareness** — current code only reacts to the *leading* opponent; a
  smarter player weighs all opponents' scores and positions simultaneously
- **Rob discard quality** — currently discards weakest by global rank; a smarter player
  would prefer to discard from a suit where they're already void (intentional suit-stripping)
  or to preserve a specific card for a later trick
- **Don't over-trump** — avoid spending a high trump just to beat a low trump already
  winning the trick

STRATEGY.md has the material for all of the above. This stays fully rule-based and is
cheaply testable.

---

## 2. Monte Carlo Tree Search (MCTS) ← implemented in Phase 2

**Why it fits Twenty-Five particularly well:**
- The current engine already has the exact interface MCTS needs: `get_state()` →
  `legal_moves`, `apply_move()`
- In master-view mode all hands are already visible — no imperfect-information complications
- MCTS naturally handles the "keep the leader down" dynamic — simulations where the leader
  wins score poorly, so the algorithm learns to block
- No training data required; works out of the box
- Strength scales with simulation count

### Algorithm
1. From the current state, clone the engine and build a search tree
2. **Selection**: walk the tree using UCB1 (`value/visits + C * sqrt(ln(parent_visits)/visits)`)
   to balance exploration vs. exploitation
3. **Expansion**: add one new child node by applying an unexplored move
4. **Rollout**: play randomly to game end
5. **Backpropagation**: update visit counts and accumulated reward up the tree
6. Return the move with the most visits (most robust child criterion)

### Variant used: Paranoid MCTS
The reward is from the AI player's own perspective only (win = 1, loss = 0). This
treats all opponents as independent rather than modelling coalition play. It works
well in practice and is significantly simpler to implement than max^n MCTS.

### Performance
- Default: 500 simulations per move
- Each rollout ≈ 20 moves (5 remaining tricks × 4 players)
- 500 simulations ≈ 10,000 `apply_move` calls per decision
- Typically < 1 second per move on modern hardware

---

## 3. Information Set MCTS (ISMCTS) ← implemented

`twentyfive/ai/ismcts.py` — Single-Observer ISMCTS (SO-ISMCTS) as described in
Cowling, Powley & Whitehouse (2012).

Unlike `MCTSPlayer`, which has full visibility of all hands, `ISMCTSPlayer` uses only
**public information**. Before each simulation it *determinizes* — randomly assigns
plausible cards to opponents consistent with public knowledge — then runs UCB-guided
tree search on that complete-information state. A shared tree is maintained across all
determinizations.

### What counts as public information
- The current player's own hand
- All cards played in completed and current tricks
- The face-up card (if not yet taken by a rob)
- After a rob: the card the robber took, and (for non-dealer robs) the Ace of Trump
  they held as eligibility proof

### ISMCTS innovation vs regular MCTS: `availability` counter
The key difference is in the UCB formula. In standard MCTS the exploration term is
`sqrt(ln(parent.visits) / visits)`. In ISMCTS each node also tracks `availability` —
the number of times it was a *legal* option across determinizations — and this replaces
`parent.visits`:

```
UCB = value_sum / visits  +  c * sqrt(log(availability) / availability)
```

This normalises for the fact that different determinizations expose different subsets
of moves at each node. A move that is only legal in some determinizations should not
be penalised for being under-explored when it wasn't even a legal option.

### Algorithm (per simulation)
1. **Determinize** — sample one plausible hand assignment for opponents
2. **Clone** the engine and replace opponent hands with the sample
3. **Selection** — walk the shared tree; at each node increment `availability` on all
   compatible (legal-in-this-determinization) children; select by UCB; stop on unexplored legal move
4. **Expansion** — create one new child for a legal-but-unexpanded move
   (skip `ConfirmRoundEnd` — non-deterministic; handled in rollout)
5. **Rollout** — random play to game end
6. **Backpropagation** — same win/loss reward formula as `MCTSPlayer`

### Relationship to MCTSPlayer
`mcts.py` is kept unchanged. It remains correct for full-information use (master view)
and is a useful reference implementation of the simpler algorithm.

---

## 4. Double-Dummy Solver (DDS) — from Bridge AI

Bridge is the most-studied trick-taking game for AI. The central technique is the
**double-dummy solver**: given all hands face-up, compute the optimal play for all
sides using minimax.

For Twenty-Five (with all hands visible in master view), a DDS gives a **theoretically
optimal** play sequence. With 5 tricks × N players the search space is tiny compared
to bridge (13 tricks × 4 players).

**Usefulness:** primarily as a benchmark/oracle to measure how close MCTS or heuristic
players are to optimal, and to generate test fixtures with known correct play.

**Library:** Bo Haglund's `dds` (C++, open source, with Python ctypes bindings). Not
easily importable as-is for 25s but the algorithm is straightforward to reimplement
for a simpler game.

---

## 5. OpenSpiel (DeepMind)

[OpenSpiel](https://github.com/deepmind/open_spiel) is a framework of ~80 games with
a common API, plus implementations of MCTS, CFR, deep RL, and more.

**What it provides:**
- `MCTSBot` (with or without neural net guidance)
- `CFRSolver` (counterfactual regret — what Libratus/Pluribus use for poker)
- `AlphaZeroBot` (self-play RL)

**Tradeoff:** Twenty-Five would need to be implemented as an OpenSpiel game (different
API from the current engine). Also an external dependency. Best deferred until the
engine is stable and there is a clear need for research-grade algorithms.

---

## 6. Reinforcement Learning / Neural Networks

The AlphaZero approach: a neural network trained entirely by self-play, using MCTS
guided by the network's value and policy heads.

For Twenty-Five this would mean:
- Encode game state as a fixed-size feature vector (hands, scores, trick history, trump)
- Train value head: "how likely am I to win from this state?"
- Train policy head: "which move should I pick?"
- Use MCTS guided by the network during play

Produces very strong play but requires significant engineering (training loop, self-play
infrastructure). Appropriate for a later phase once MCTS baseline is established.

---

## Practical Roadmap

| Step | Approach | Effort | Strength |
|------|----------|--------|----------|
| 0 ✅ | `HeuristicPlayer` — rule-based | Low | Moderate |
| 1 ✅ | `MCTSPlayer` — UCB1 + random rollouts | Medium | Strong |
| 2 ✅ | `EnhancedHeuristicPlayer` — card tracking, endgame, multi-opponent | Low | Moderate+ |
| 3 ✅ | `ISMCTSPlayer` — SO-ISMCTS for hidden-hand mode | Medium | Strong (fair) |
| 4 | DDS oracle for benchmarking | Medium | Benchmark only |
| 5 | Neural net (AlphaZero-style) | High | Very strong |

---

## Implementation Notes

### Engine interface used by AI players
```python
state = engine.get_state()   # GameState snapshot (all hands visible)
legal = state.legal_moves    # tuple[Move, ...] — pre-computed
engine.apply_move(move)      # raises ValueError if illegal
engine.clone()               # deep copy with audit disabled (for simulation)
engine.is_game_over          # bool
```

### AIPlayer interface
```python
class AIPlayer(ABC):
    def choose_move(self, state: GameState) -> Move: ...
```

All AI players receive only the `GameState` snapshot. `MCTSPlayer` and `ISMCTSPlayer`
additionally store a reference to the live `GameEngine` (passed in `__init__`) so they
can clone the engine for simulation without affecting the real game.

### Files
```
twentyfive/ai/
  player.py              AIPlayer ABC, RandomPlayer
  heuristic.py           HeuristicPlayer (rule-based)
  enhanced_heuristic.py  EnhancedHeuristicPlayer (5 improvements over HeuristicPlayer)
  mcts.py                MCTSPlayer (UCB1 MCTS, full-information)
  ismcts.py              ISMCTSPlayer (SO-ISMCTS, public-info only)
  __init__.py            re-exports all five
```
