# CLI UI

Terminal-based interface for Twenty-Five. Renders the board state to the terminal
and reads input from the keyboard with single-keypress prompts.

## Usage

```bash
python -m twentyfive                       # interactive setup (choose players/AI)
python -m twentyfive --1v3 YourName        # quick 1v3 vs Enhanced AI
python -m twentyfive --1v3 YourName --seeall   # all hands visible (debug)
```

No extra dependencies — stdlib only.

## View modes

| Mode | Flag | Description |
|------|------|-------------|
| Hidden-hand | *(default)* | Only the current human player's hand is shown; AI actions print as one-liners |
| Master view | `--seeall` | All hands visible at all times; also auto-enabled for all-AI games |

## Keyboard shortcuts

### During a trick

| Key | Action |
|-----|--------|
| `1`–`5` | Select a card by number |
| `A` | Auto-play (weakest winning card, or worst legal card) |

### During rob phase

| Key | Action |
|-----|--------|
| `1` | Rob (take face-up card, then choose a discard) |
| `2` | Pass (do not rob) |

### Round end / continue prompts

| Key | Action |
|-----|--------|
| `A`, `SPACE`, `ENTER` | Advance |

## Public names

| Name | Description |
|------|-------------|
| `CLI(controller, *, show_all)` | Main CLI class — call `.run()` to start |
| `launch(controller, *, show_all)` | Convenience wrapper used by `__main__` |

## File map

| File | Contents | Lines |
|------|----------|-------|
| `__init__.py` | Re-exports `CLI`, `launch` | 3 |
| `cli.py` | `CLI` class — rendering, input, game loop | 428 |

## Dependencies

- `twentyfive.game` (state, rules)
- `twentyfive.ui.controller.GameController`
- stdlib: `os`, `sys`, `termios`/`tty` (Unix) or `msvcrt` (Windows)
