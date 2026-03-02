# Requirements — Twenty-Five (25s)

For the game rules referenced throughout this document, see [RULES.md](RULES.md).
For strategy context relevant to AI player design, see [STRATEGY.md](STRATEGY.md).

---

## 1. Overview

A rules-accurate, testable Python implementation of Twenty-Five (25s), structured so that
the game engine can be used independently of how the game is presented to players.

**In scope for this document:** Phase 1 (MVP) only — core game engine and a pass-the-terminal
CLI. Future phases (AI players, partnerships, GUI) are listed in [Section 7](#7-out-of-scope).

---

## 2. Architecture

The codebase is split into three layers with a strict one-way dependency rule:

```
┌─────────────────────────────┐
│       UI Layer              │  CLI, future GUI, etc.
│  (twentyfive/ui/)           │  — depends on game layer
└────────────┬────────────────┘
             │ calls
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

**ARC-1** The game logic layer must have no imports from the UI layer.
**ARC-2** The card primitives layer must have no imports from the game logic layer or UI layer.
**ARC-3** The game layer must expose game state as read-only snapshots; it must never hand
out mutable internal objects.
**ARC-4** The game layer must expose the list of legal moves for the current player as its
primary interface for the UI. The UI renders choices from this list — it does not compute
legality independently.

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
for the round. This card and its suit are part of the public game state.

### 4.2 Rob Phase

**GAME-6** After the trump card is revealed and before the first trick is led, any eligible
player may rob the pack (see [RULES.md — Robbing the Trump](RULES.md)).
**GAME-7** Eligibility: a player holding the Ace of the trump suit may rob. If the face-up
card is itself the Ace of the trump suit, the dealer may rob.
**GAME-8** Robbing is optional — no player is compelled to rob.
**GAME-9** To rob, a player first discards exactly one card from their current hand face-down,
then takes the face-up card. The player may not discard the face-up card itself (they choose
their discard from their original hand before taking). The discard is not revealed to other
players.
**GAME-10** Robbing opportunities are resolved in seat order (starting from the player
immediately left of the dealer). Only one rob per face-up card is possible.
**GAME-11** The engine must not allow trick play to begin until the rob phase is complete
(all eligible players have either robbed or passed).

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
**GAME-28** A win check must occur after every trick. The first player to reach 25 points
wins the game immediately — even if the current round is unfinished.
**GAME-29** The engine must expose the current scores for all players as part of the game
state.

### 4.6 Game State

**GAME-30** The engine must expose a game state object containing at minimum:
- Current phase (setup / rob / trick / game-over)
- Current dealer
- Current player (whose turn it is)
- Trump suit and face-up card (while it exists)
- Each player's hand (see note on privacy below)
- Cards played in the current trick, in order
- Running scores
- Current trick number (1–5)

**GAME-31** The game state must include all players' hands. Privacy (hiding hands from other
players) is a UI concern, not an engine concern.

---

## 5. CLI User Interface

### 5.1 Display Modes

**UI-1** The CLI supports two display modes:
- **Master view** — all players' hands are shown simultaneously. Intended for development,
  testing, and small-group play around one screen.
- **Normal view** — each player sees only their own hand. A "pass the terminal" prompt
  appears between turns. *(Normal view is deferred; master view is the default for the MVP.)*

**UI-2** Master view is the active default mode for the MVP. Normal view is a planned
enhancement and must be designed for but need not be implemented initially.

### 5.2 Screen Layout (Master View)

**UI-3** Each turn must display, at minimum:
- Trump suit and face-up card (if not yet taken)
- Current scores (all players, in seat order)
- All hands (all players, in seat order) — with the active player's hand highlighted
- Cards already played in the current trick, in play order
- The current player's legal moves as a numbered list

**UI-4** The screen must be refreshed (cleared and redrawn) at the start of each turn so the
display is not cluttered with prior turns.

### 5.3 Input

**UI-5** The player selects a move by entering the number corresponding to a card from the
legal move list. Free-form card entry is not required.
**UI-6** Invalid input (non-numeric, out-of-range) must prompt the player to re-enter
without advancing game state.
**UI-7** The rob phase must prompt eligible players to either select a card to take or pass.
If a player robs, they must select a card to discard from their updated hand.

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

**UI-14** In master view mode, the player must have the option to auto-play the current
player's first legal move (rapid advance for testing). This must be accessible as a numbered
option in the move selection list.

### 5.8 Renege Indicator

**UI-15** When a player is selecting a card to play and a legal move would constitute a
renege (legally withholding a top-3 trump while other trumps are forced), the UI must mark
that card visually (e.g. with a `(renege)` label) so the player can make an informed choice.

### 5.9 Game Identity in UI

**UI-16** The game header must display the current game ID, round number, and trick number
on every screen so players can reference specific scenarios in the audit log.

### 5.10 Rob Visibility (Normal View)

**UI-17** In normal (hidden-hand) view, when a player robs the face-up card, all other players
must be shown a rob-reveal screen before their own turn begins. This screen must display:
- The name of the player who robbed
- The Ace of trumps they hold (confirming their eligibility)
- The face-up card they took

The discard remains face-down and is not revealed to other players. This mirrors the physical
game, where the rob is a visible table action — all players see who robbed and what card they
gained, even though the discarded card is hidden.

This requirement applies to normal view only. In master view all hands are already visible,
so no additional reveal is needed.

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

---

## 7. Non-Functional Requirements

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

## 8. Out of Scope

The following are explicitly deferred to later phases. They should not be designed against
in the MVP, but the architecture must not actively prevent them.

| Feature | Phase |
|---------|-------|
| AI / robotic players | Phase 2 |
| Partnerships (2v2, 3v3) | Phase 3 |
| GUI (web, desktop, or otherwise) | Phase 4 |
| 45s and 110 variants | Phase 3+ |
| Network / online play | Phase 4+ |
| Normal (hidden-hand) pass-the-terminal mode | Phase 1b |

---

## 9. Open Questions

Issues that may affect requirements as development proceeds. Update this section as
decisions are made.

| # | Question | Status |
|---|----------|--------|
| OQ-1 | When multiple players are eligible to rob in seat order, can more than one player rob per round? (Traditional rules say only one rob per face-up card — GAME-10 assumes this.) | Assumed: one rob per round |
| OQ-2 | If a player reaches exactly 25 mid-trick (before all players have played), does the round end immediately or does the trick finish? | Assumed: game ends immediately on reaching 25 |
| OQ-3 | Is the discard during a rob shown to other players? | Resolved: discard is face-down (not revealed). The Ace held and the card taken are shown publicly in normal view — see UI-17. |
