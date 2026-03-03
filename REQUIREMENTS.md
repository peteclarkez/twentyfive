# Requirements — Twenty-Five (25s)

For the game rules referenced throughout this document, see [RULES.md](RULES.md).
For strategy context relevant to AI player design, see [STRATEGY.md](STRATEGY.md).

---

## 1. Overview

A rules-accurate, testable Python implementation of Twenty-Five (25s), structured so that
the game engine can be used independently of how the game is presented to players.

---

## 2. Architecture

The codebase is split into four layers with a strict one-way dependency rule:

```
┌─────────────────────────────┐
│       UI Layer              │  CLI, future GUI, etc.
│  (twentyfive/ui/)           │  — depends on game + AI layers
└────────────┬────────────────┘
             │ calls
┌────────────▼────────────────┐
│       AI Layer              │  AI player implementations
│  (twentyfive/ai/)           │  — depends on game layer only
└────────────┬────────────────┘
             │ uses
┌────────────▼────────────────┐
│       Game Logic Layer      │  Irish 25s rules, state machine
│  (twentyfive/game/)         │  — depends on card layer only
└────────────┬────────────────┘
             │ uses
┌────────────▼────────────────┐
│    Card Primitives Layer    │  Generic: Card, Deck, Suit, Rank
│  (twentyfive/cards/)        │  — no game rules, no UI
└─────────────────────────────┘
```

**ARC-1** The game logic layer must have no imports from the UI or AI layers.
**ARC-2** The card primitives layer must have no imports from the game logic, AI, or UI layers.
**ARC-3** The game layer must expose game state as read-only snapshots; it must never hand
out mutable internal objects.
**ARC-4** The game layer must expose the list of legal moves for the current player as its
primary interface for the UI. The UI renders choices from this list — it does not compute
legality independently.
**ARC-5** The AI layer must depend only on the game layer. It must not be imported by the
game logic or card primitives layers.

---

## 3. Card Primitives Layer

These are generic building blocks with no knowledge of Twenty-Five rules.

**CARD-1** `Suit` is an enumeration of four values: Hearts, Diamonds, Clubs, Spades.
**CARD-2** `Rank` is an enumeration of thirteen values: 2–10, J, Q, K, A.
**CARD-3** `Card` is an immutable value object composed of `(Suit, Rank)`. Two cards with
the same suit and rank must be equal. Cards must be hashable (usable in sets and dict keys).
**CARD-4** A standard `Deck` contains exactly 52 unique `Card` instances (one per Suit × Rank combination).
**CARD-5** `Deck.shuffle()` randomises the order of remaining cards in-place.
**CARD-6** `Deck.deal(n)` removes and returns exactly `n` cards from the top of the deck.
Attempting to deal more cards than remain must raise an error.
**CARD-7** The card primitives layer must contain no Twenty-Five-specific logic (no trump
ranking, no renege rules, no rob logic).

---

## 4. Game Logic Layer

This layer encodes all Irish Twenty-Five rules. Rule definitions are in [RULES.md](RULES.md);
this section specifies what the engine must enforce.

### 4.1 Setup

**GAME-1** The game supports 2–6 players.
**GAME-2** Players are identified by a name string. Names must be unique within a game.
**GAME-3** The dealer role rotates clockwise after each round.
**GAME-4** At the start of each round, the deck is shuffled and each player is dealt 5 cards
in packets of 3 then 2 (as per [RULES.md — Setup](RULES.md)).
**GAME-5** After dealing, the top remaining card is turned face-up to determine the trump suit
for the round. This card and its suit are part of the public game state. The face-up card
becomes `None` after it is taken in a rob.
**GAME-33** The engine accepts an optional `initial_dealer` index (default 0) to allow the
first dealer to be chosen externally (e.g. at random by the caller).

### 4.2 Rob Phase

**GAME-6** After the trump card is revealed and before the first trick is led, any eligible
player may rob the pack (see [RULES.md — Robbing the Trump](RULES.md)).
**GAME-7** Exactly one player can be eligible to rob per round, by one of two mutually
exclusive conditions:
- A non-dealer player holds the Ace of the trump suit in their dealt hand; or
- The face-up card is the Ace of the trump suit, in which case the dealer may rob.
These cases are mutually exclusive: the Ace of Trump cannot simultaneously be face-up and
in a non-dealer's hand.
**GAME-8** Robbing is optional — no player is compelled to rob.
**GAME-9** To rob, a player first discards exactly one card from their current hand face-down,
then takes the face-up card. The player may not discard the face-up card itself (they choose
their discard from their original hand before taking). The discard is not revealed to other
players.
**GAME-10** At most one rob can occur per round (see GAME-7). The eligible player either
robs or passes; no further rob opportunities exist in that round.
**GAME-11** The engine must not allow trick play to begin until the rob phase is complete
(all eligible players have either robbed or passed).
**GAME-34** When a rob occurs the engine must record `rob_this_round` — a tuple of
`(player_name, card_taken)` identifying who robbed and which face-up card they took. This
field is cleared at the start of each new round and is `None` if no rob has occurred. It is
exposed in the public game state (see GAME-30).

### 4.3 Trick Play

**GAME-12** There are exactly 5 tricks per round.
**GAME-13** The player immediately left of the dealer leads the first trick. The winner of
each trick leads the next.
**GAME-14** Play proceeds clockwise. Each player plays exactly one card per trick.

#### Move Validation — Non-Trump Lead

**GAME-15** When a non-trump card leads, a player must follow suit or trump (may-trump rule)
— they must play a card of the same suit as the led card, or any trump card. They may not
freely discard a card of a different suit while holding either the led suit or a trump.
**GAME-16** A player who holds no card of the led suit and no trump may play any card.
**GAME-17** May-trump is permitted: a player holding the led suit may still choose to trump
instead of following suit. They are never required to trump.

#### Move Validation — Trump Lead

**GAME-18** When a trump card leads, each player must play a trump card — subject to the
reneging privilege described in GAME-19.
**GAME-19** The top three trump cards (5 of trumps, Jack of trumps, A♥) may be legally
withheld (reneged) according to the hierarchy in [RULES.md — Reneging](RULES.md). A card
may be reneged only if it outranks the led trump card.
**GAME-20** A player who holds none of the three protected cards and no other trump may
play any card.

#### Engine Enforcement

**GAME-21** The engine must compute and return the complete set of legal cards the current
player may play, before any input is taken. The set must be non-empty (a player always has
at least one legal card).
**GAME-22** The engine must reject any attempt to play a card not in the legal move set.
This must not advance game state.

### 4.4 Card Ranking

**GAME-23** The engine must correctly determine the winner of each trick using the trump-aware
ranking rules in [RULES.md — Card Rankings](RULES.md) and [RULES.md — Winning a Trick](RULES.md).
**GAME-24** Card rank is not a static property of a card — it is resolved dynamically based
on the current trump suit. The ranking logic must live in the game layer, not the card primitives layer.
**GAME-25** The A♥ is always a trump card regardless of the trump suit. The engine must
handle this correctly in all ranking and legality computations.

### 4.5 Scoring and Win Condition

**GAME-26** Each trick won scores 5 points for the winning player.
**GAME-27** Scores accumulate across rounds within a game.
**GAME-28** A win check must occur after each trick is fully resolved — that is, after all
players have played their card and the trick winner has been determined. The game ends
immediately if the trick winner's cumulative score reaches 25 or more, even if the current
round is unfinished. No win check occurs mid-trick; a player who would reach 25 by winning
the trick cannot be declared the winner until all cards in that trick have been played.
**GAME-29** The engine must expose the current scores for all players as part of the game
state.

### 4.6 Global Card Ranking

**GAME-32** The game layer must expose a `card_global_rank(card, trump_suit) -> int` function
that returns a card's absolute strength rank among all 52 cards for the given trump suit
(1 = strongest = 5 of trumps, 52 = weakest). Trumps are ranked first (by trump hierarchy),
non-trumps after (by their within-suit rank). The ranking must be pre-computed at module
import time as a lookup table covering all four possible trump suits and all 52 cards.

### 4.7 Game State

**GAME-30** The engine must expose a game state object containing at minimum:
- Current phase (rob / trick / round-end / game-over)
- Current dealer index and current player index
- Trump suit and face-up card (face-up card is `None` once taken)
- Each player's hand (see GAME-31 on privacy)
- Cards played in the current trick, in order
- Completed tricks for the current round (full history, in order)
- Running scores and tricks won this round for each player
- Current trick number (1–5) and round number
- Game ID (UUID, stable for the lifetime of the game)
- Legal moves for the current player
- Rob tracking: `rob_this_round` — see GAME-34

**GAME-31** The game state must include all players' hands. Privacy (hiding hands from other
players) is a UI concern, not an engine concern.

---

## 5. CLI User Interface

### 5.1 Display Modes

**UI-1** The CLI supports two display modes:
- **Hidden-hand mode** *(default)* — each player sees only their own hand. Opponents' cards
  are masked with `??`. AI players take their turns silently with a one-line summary printed
  inline; the screen is cleared only when a human player's turn begins.
- **Master view** *(`--seeall` flag)* — all players' hands are shown simultaneously.
  Intended for development, testing, and spectating all-AI games.

**UI-2** Hidden-hand mode is the default. Master view is enabled with the `--seeall` flag.
When all players are AI the CLI automatically enables master view for spectating.

### 5.2 Screen Layout

**UI-3** Each rendered turn must display, at minimum:
- Trump suit and face-up card (if not yet taken)
- Current scores (all players, in seat order), with dealer and leader tagged
- All hands (all players, in seat order) — with the active player's hand highlighted
- Cards already played in the current trick, in order
- In hidden-hand mode: opponents' hands are masked with `??` (see also UI-17)
- The current player's legal moves as a numbered list

**UI-4** The screen must be refreshed (cleared and redrawn) at the start of each human
player's turn so the display is not cluttered with prior turns.

### 5.3 Input

**UI-5** The player selects a move by entering the number corresponding to a card from the
legal move list. Free-form card entry is not required.
**UI-6** Invalid input (non-numeric, out-of-range) must prompt the player to re-enter
without advancing game state.
**UI-7** The rob phase must prompt eligible players to either select a card to take or pass.
If a player robs, they must select a card to discard from their current hand.

### 5.4 End of Trick / Round / Game

**UI-8** At the end of each trick, the result (winner, cards played) must be displayed before
the next trick begins. A brief pause or keypress must allow players to read it.
**UI-9** At the end of each round, a round summary (tricks won per player, points scored,
running totals) must be shown before the next round begins.
**UI-10** When a player reaches 25 points, the game must display the winner and final scores,
then exit cleanly.

### 5.5 Colour and Readability

**UI-11** Card suits must be rendered in colour using ANSI terminal codes:
Hearts → red, Spades → green, Diamonds → orange (256-color), Clubs → navy (blue).

### 5.6 Trick Visibility

**UI-12** The current trick display must indicate which player led the trick (played the
first card of the trick).
**UI-13** Completed tricks from the current round must remain visible on screen. The display
must show a history of all tricks played so far in the round, not just the current one.

### 5.7 Autoplay

**UI-14** The player must have the option to auto-play the current player's move. The
auto-play strategy must be: (1) if any legal card would make this player the current trick
winner, play the weakest such card (highest `#N` rank); otherwise (2) play the weakest
legal card overall (highest `#N` rank). The option must be accessible via the `[A]` input
in the card selection prompt.

### 5.8 Renege Indicator

**UI-15** When a player is selecting a card to play and a legal move would constitute a
renege (legally withholding a top-3 trump while other trumps are forced), the UI must mark
that card visually (e.g. with a `(renegeable)` label) so the player can make an informed choice.

### 5.9 Game Identity in UI

**UI-16** The game header must display the current game ID, round number, and trick number
on every screen so players can reference specific scenarios in the audit log.

### 5.10 Card Ranking Indicators

**UI-18** When a player is selecting a card to play (trick phase) or a card to discard (rob
phase), each card must display its global rank as `#N` at the end of the line, where N=1 is
the strongest card in the deck (5 of trumps) and N=52 is the weakest, given the current trump
suit.

**UI-19** When a player is selecting a card to play and at least one card has already been
played in the current trick, any card that would make this player the current winning player
(if played now, ignoring future plays) must be marked with `(+)`. The `(+)` indicator is not
shown when the player is leading (no cards have been played yet in the trick).

**UI-20** When a player is selecting a card to play or discard and two or more legal cards are
available, the single weakest card (highest `#N` value) must be marked with `(-)` as a hint
for the best discard candidate. Not shown when only one card is legal.

### 5.11 Rob Visibility (Hidden-Hand Mode)

**UI-17** In hidden-hand mode, when a player robs the face-up card, the rob must be made
visible to all players before the next human turn. This is achieved in two ways:

1. **Inline message** — immediately after the rob, a one-line summary is printed:
   `{name} robs — takes {card}`. A keypress pause follows so the message is readable
   before the screen clears.
2. **Persistent hand display** — from the moment of the rob until the end of the round,
   the robbing player's masked hand display reveals the publicly known cards:
   - For a non-dealer rob: the face-up card taken *and* the Ace of Trump the player held
     to establish eligibility are shown; all other cards remain masked as `??`.
   - For a dealer rob: only the face-up card (which is the Ace of Trump) is shown.
   If either known card is subsequently played in a trick, it drops back to `??`.

The discard remains face-down and is never revealed to other players. This mirrors the
physical game: all players see who robbed and what card was gained, even though the
discarded card is hidden.

This requirement applies to hidden-hand mode. In master view all hands are already visible.

### 5.12 CLI Arguments

**UI-21** The CLI must support a `--seeall` flag to enable master view (see UI-1).

**UI-22** The CLI must support a `--1v3 NAME` argument for a quick-start 4-player game:
the named human player versus three Enhanced AI opponents, with seat order and first dealer
chosen at random. A brief setup summary (seat number, opponent names, first dealer) must
be printed before play begins.

---

## 6. Audit Log

**AUD-1** Every player decision (rob choice, card played) must be recorded as a structured
audit event immediately after it is applied to the game state.

**AUD-2** Each audit event must include at minimum:
- `game_id` — unique identifier for the game (UUID)
- `timestamp` — ISO 8601 wall-clock time of the event
- `round_number`, `trick_number`
- `player_name`, `player_index`
- `event_type` — one of `deal`, `trump`, `rob`, `pass_rob`, `play_card`
- `card` — the card involved (where applicable)
- `legal_moves` — the full set of legal moves available to the player at decision time

**AUD-3** A `deal` event must be emitted at the start of each round recording the full
initial hand for every player and the face-up trump card, so the game can be replayed in
full from the log alone.

**AUD-4** Audit data must be written in newline-delimited JSON (one JSON object per line, no
trailing comma) to a file in the `logs/` directory. The filename must incorporate the game
ID and start timestamp: `logs/game_<id>_<YYYYMMDD_HHMMSS>.jsonl`.

**AUD-5** The `logs/` directory must be listed in `.gitignore`.

**AUD-6** Each event must be flushed to disk immediately after being written (append mode,
explicit flush) so partial logs are recoverable if the process is interrupted.

**AUD-7** The audit subsystem must live in the game layer (not the UI layer) so that it
captures all decisions regardless of which UI is used.

**AUD-8** The `play_card` audit event must include a `card_rank` field containing the global
rank (1 = best, 52 = worst — see GAME-32) of the card played, so audit analysis tools do not
need to re-derive rankings from raw card names.

---

## 7. AI Players

Full design rationale and implementation details are in
[AI_APPROACHES.md](twentyfive/ai/AI_APPROACHES.md).

**AI-1** The project must include at least one AI player implementation. All AI players must
implement a common interface (`AIPlayer`) with a single `choose_move(state: GameState) -> Move`
method. AI players must be stateless between calls except for optional internal bookkeeping.

**AI-2** Four AI implementations are provided, in increasing order of sophistication:
- **RandomPlayer** — selects a uniformly random legal move.
- **HeuristicPlayer** — applies rule-based strategy derived from [STRATEGY.md](STRATEGY.md).
- **EnhancedHeuristicPlayer** — extends HeuristicPlayer with card-tracking, endgame logic,
  multi-opponent danger assessment, and rob quality heuristics. This is the default AI type.
- **MCTSPlayer** — Monte Carlo Tree Search with UCB1 selection and paranoid rollouts
  (treats all opponents as a coalition). Accepts a configurable `simulations` count.

**AI-3** Any number of players in a game may be AI-controlled. A game may consist entirely
of AI players (all-AI games automatically enable master view for spectating).

**AI-4** The `GameEngine` must expose a `clone()` method returning a deep copy with audit
disabled, so AI implementations can simulate future game states without affecting the real
game or the audit log.

---

## 8. Benchmark

**BENCH-1** A benchmark module (`python -m twentyfive.benchmark`) must run automated
multi-game comparisons between AI types and report aggregate statistics.

**BENCH-2** The default benchmark runs one of each AI type per game (four players), with
seats shuffled randomly each game to cancel position and dealer bias.

**BENCH-3** The benchmark must report per-AI-type: games played, wins, win percentage,
average final score, and average rounds per game.

**BENCH-4** The benchmark must accept CLI arguments: `--games N`, `--seed N`,
`--mcts-sims N`, and `--quiet`. It must also be callable as a library via `run_benchmark()`.

---

## 9. Non-Functional Requirements

**NFR-1** Python 3.12 or later.
**NFR-2** No external card or game libraries. All card and game logic must be implemented
in this project using the Python standard library only.
**NFR-3** The card primitives layer and game logic layer must have comprehensive unit tests.
Tests live in `tests/` and follow the conventions in [CLAUDE.md](CLAUDE.md).
**NFR-4** The UI layer does not require unit tests for the MVP; it is covered by manual testing.
**NFR-5** Type hints are required on all public functions, methods, and class signatures in
the game and card layers.
**NFR-6** Code must pass `ruff format` and `ruff check` (configuration in `pyproject.toml`)
with no errors or warnings.
**NFR-7** The project must be runnable with `python -m twentyfive` from the project root.
**NFR-8** The audit log must use only the Python standard library (`json`, `uuid`,
`datetime`, `pathlib`). No third-party logging frameworks.

---

## 10. Out of Scope

The following are explicitly deferred. The architecture must not actively prevent them.

| Feature | Phase |
|---------|-------|
| Partnerships (2v2, 3v3) | Future |
| GUI (web, desktop, or otherwise) | Future |
| 45s and 110 variants | Future |
| Network / online play | Future |
| ISMCTS for fair hidden-hand AI (currently AI sees all hands) | Future |

---

## 11. Open Questions

Issues that may affect requirements as development proceeds.

| # | Question | Status |
|---|----------|--------|
| OQ-1 | When multiple players are eligible to rob in seat order, can more than one player rob per round? | Resolved: only one player is ever eligible per round. The Ace of Trump cannot be simultaneously face-up and in a non-dealer's hand, so the two eligibility cases (GAME-7) are mutually exclusive. At most one rob occurs per round. |
| OQ-2 | If a player reaches exactly 25 mid-trick (before all players have played), does the round end immediately or does the trick finish? | Resolved: the trick must complete. All players play their card; the trick is resolved normally. Only then is the win condition checked. A following player could beat the potential winner and prevent them from scoring. See GAME-28. |
| OQ-3 | Is the discard during a rob shown to other players? | Resolved: discard is face-down (not revealed). The Ace held and the card taken are shown publicly in hidden-hand view — see UI-17. |
