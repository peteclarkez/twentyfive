# UI Development Guide

This guide explains how to write a new UI for the Twenty-Five game engine.

---

## Overview

UIs live under `twentyfive/ui/`. The launcher (`python -m twentyfive`) loads the
UI by name:

```bash
python -m twentyfive --ui cli          # default
python -m twentyfive --ui pygame_ui   # desktop
python -m twentyfive --ui my_ui       # your new UI
```

The name passed to `--ui` must be the filename (without `.py`) of a module under
`twentyfive/ui/`. The module is loaded dynamically via `importlib`.

---

## The `launch()` contract

Every UI module must expose exactly one top-level function:

```python
from twentyfive.ui.controller import GameController

def launch(controller: GameController, *, show_all: bool = False) -> None:
    """Run the UI. Blocks until the game ends or the user quits."""
    ...
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `controller` | `GameController` | The game controller — the only object a UI needs |
| `show_all` | `bool` | When `True`, reveal all players' hands (spectator/debug mode) |

`launch()` must block until the game is finished or the player quits. Return
normally on clean exit.

That is the **complete contract**. Your module needs no other public symbols.

---

## GameController API

`GameController` is your single interface to the game.

```python
from twentyfive.ui.controller import GameController
```

| Member | Type | Description |
|--------|------|-------------|
| `ctrl.state` | `GameState` | Snapshot of the current game state (read-only) |
| `ctrl.is_game_over` | `bool` | `True` once a player reaches 25 points |
| `ctrl.is_ai_turn()` | `bool` | `True` if the current player has an AI registered |
| `ctrl.step_ai()` | `tuple[str, Move, GameState]` | Compute + apply the AI's move; returns `(actor_name, move, new_state)`. Raises `RuntimeError` if it's a human turn. |
| `ctrl.apply_move(move)` | `GameState` | Apply a human-chosen move; returns the new state. Raises `ValueError` if the move is illegal. |
| `ctrl.human_players` | `frozenset[str]` | Names of players that have no AI (i.e., human-controlled) |

---

## GameState fields

`GameState` is a frozen dataclass — all fields are read-only.

```python
from twentyfive.game.state import GameState, Phase, Move, PlayerSnapshot, TrickPlay
```

| Field | Type | Description |
|-------|------|-------------|
| `phase` | `Phase` | Current game phase (see below) |
| `players` | `tuple[PlayerSnapshot, ...]` | All players in seat order |
| `current_player_index` | `int` | Index into `players` of the active player |
| `current_player` | `PlayerSnapshot` | Shortcut: `players[current_player_index]` |
| `dealer_index` | `int` | Index of the current dealer |
| `trump_suit` | `Suit \| None` | The trump suit for this round; `None` during rob phase |
| `face_up_card` | `Card \| None` | The turned-up trump card available to rob; `None` after a rob |
| `current_trick` | `tuple[TrickPlay, ...]` | Cards played so far in the current trick |
| `completed_tricks` | `tuple[tuple[TrickPlay, ...], ...]` | Tricks completed this round |
| `trick_number` | `int` | Current trick number, 1–5 |
| `round_number` | `int` | Current round number, starting at 1 |
| `game_id` | `str` | UUID identifying this game (for logging/audit) |
| `legal_moves` | `tuple[Move, ...]` | All moves the current player may make |
| `rob_this_round` | `tuple[str, Card] \| None` | `(player_name, card_taken)` if a rob happened this round, else `None` |

### PlayerSnapshot

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Player name |
| `score` | `int` | Cumulative score (0–25+) |
| `tricks_won_this_round` | `int` | Tricks won in the current round |
| `hand_size` | `int` | Number of cards in hand |
| `hand` | `tuple[Card, ...]` | The player's actual cards (see **Privacy model** below) |

### Phase enum

| Value | Meaning |
|-------|---------|
| `Phase.ROB` | Rob phase — the dealer may take the face-up card |
| `Phase.TRICK` | Trick phase — players take turns playing cards |
| `Phase.ROUND_END` | All 5 tricks done; wait for `ConfirmRoundEnd` before next round |
| `Phase.GAME_OVER` | A player reached 25 points; game is finished |

---

## Move types

All moves are frozen dataclasses importable from `twentyfive.game.state`.

```python
from twentyfive.game.state import PlayCard, Rob, PassRob, ConfirmRoundEnd
```

| Move | Legal when | Fields |
|------|-----------|--------|
| `PlayCard(card=c)` | `Phase.TRICK` | `card: Card` — must be in `legal_moves` |
| `Rob(discard=c)` | `Phase.ROB`, player is eligible | `discard: Card` — card from hand to give back |
| `PassRob()` | `Phase.ROB` | none |
| `ConfirmRoundEnd()` | `Phase.ROUND_END` | none |

Always choose from `state.legal_moves` — do not construct moves yourself unless
you are certain of legality, as the engine will raise `ValueError` on illegal moves.

---

## Privacy model

`GameState` always populates every player's `hand` with their real cards — the
engine does not hide information. **The UI is responsible for deciding what to
show.**

Typical convention (matching the built-in UIs):

- **Hidden-hand mode** (`show_all=False`): show cards only for the current human
  player; display back-of-card placeholders for everyone else.
- **Master view** (`show_all=True`): show all hands (useful for spectating
  AI-vs-AI games or debugging).

---

## Canonical turn loop

```python
while not ctrl.is_game_over:
    state = ctrl.state

    if ctrl.is_ai_turn():
        actor, move, state = ctrl.step_ai()
        # optionally: display what the AI did
        continue

    # Human turn — prompt the user, then:
    move = ...  # a Move from state.legal_moves
    state = ctrl.apply_move(move)
```

### AI threading note

For UIs with an event loop (e.g. pygame), **do not call `step_ai()` on the main
thread** — MCTS can take ~1 second per move and will freeze the UI.

Recommended pattern:

```python
import threading

def _run_ai_in_background(ctrl, on_done):
    actor, move, new_state = ctrl.step_ai()
    on_done(actor, move, new_state)   # post result to UI thread (e.g. via a queue or event)

thread = threading.Thread(target=_run_ai_in_background, args=(ctrl, callback), daemon=True)
thread.start()
```

See `pygame_ui.py` for a working example using `pygame.event.post`.

---

## Minimal working example

Below is the smallest compliant UI — it plays a full AI game and prints one line
per move. Save it as `twentyfive/ui/print_ui.py` and run with
`python -m twentyfive --ui print_ui`.

```python
"""Minimal print UI — plays an all-AI game, printing one line per move."""

from twentyfive.ui.controller import GameController


def launch(controller: GameController, *, show_all: bool = False) -> None:
    while not controller.is_game_over:
        state = controller.state
        if controller.is_ai_turn():
            actor, move, state = controller.step_ai()
            print(f"  {actor}: {move}")
        else:
            # For a pure-AI game this branch is never hit.
            # For human players, prompt here and call controller.apply_move(move).
            raise RuntimeError("Human player encountered in minimal UI")

    # Print final scores
    for p in controller.state.players:
        print(f"{p.name}: {p.score} pts")
```

---

## Checklist for a new UI

- [ ] File is at `twentyfive/ui/<name>.py`
- [ ] Exports `launch(controller: GameController, *, show_all: bool = False) -> None`
- [ ] `launch()` blocks until game over or user quits
- [ ] Does not import from `twentyfive.game.engine` directly — use `GameController`
- [ ] Heavy computation (e.g. MCTS AI moves) runs off the main/UI thread
- [ ] Respects `show_all` — hide opponent hands when `False`
- [ ] Works with `python -m ruff check .` and `python -m mypy twentyfive/`
