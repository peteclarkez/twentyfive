# Tactical Dashboard UI

High-contrast dark-mode "command centre" layout for Twenty-Five, built with pygame-ce.

## Layout

```
┌──────────────────────────────────────────────────────────┐
│  HEADER — Game ID | Round N | Trick N/5 | Trump suit     │
├────────────┬────────────────────────────┬────────────────┤
│ SCORECARD  │         ARENA              │  TRICK ZONE    │
│            │   (current trick slots)    │  (trick log)   │
│ names      │                            │                │
│ scores     ├────────────────────────────┤  status msg    │
│ trick pips │         HAND               │                │
│            │  (current player's cards)  │  ROB / PLAY    │
│            │                            │  buttons       │
└────────────┴────────────────────────────┴────────────────┘
```

## Usage

```bash
pip install -e ".[gui]"                        # installs pygame-ce

python -m twentyfive --gui --ui tactical_ui    # interactive setup lobby
python -m twentyfive --gui --ui tactical_ui --1v3 YourName   # quick 1v3
python -m twentyfive --gui --ui tactical_ui --1v3 YourName --seeall
```

## Keyboard shortcuts (in-game)

| Key | Action |
|-----|--------|
| `1`–`5` | Select hand card by slot |
| `ENTER` | Confirm selected card / advance round |
| `A` | Auto-play (weakest winning card, or worst) |
| `R` | Rob the face-up card |
| `P` | Pass rob |
| `SPACE` | Skip trick/round overlay |
| `ESC` | Quit |

## Public names

| Name | Description |
|------|-------------|
| `TacticalUI(controller, *, show_all)` | Main UI class — call `.run()` to start |
| `launch(controller, *, show_all)` | Convenience wrapper used by `__main__` |
| `setup_game()` | Pygame setup lobby; returns `([names], {name: type})` or `None` |

## File map

| File | Contents | Lines |
|------|----------|-------|
| `__init__.py` | Re-exports `TacticalUI`, `launch`, `setup_game` | 3 |
| `constants.py` | Window layout, card sizes, colour palette, arena configs | 118 |
| `bg.py` | `ProceduralBackground` (value-noise lava-lamp), `_pulse()` | 119 |
| `animation.py` | `FloatingCard` (bob + tilt physics), `_CardAnim`, `_bezier()` | 90 |
| `widgets.py` | Card-drawing primitives, `_Button`, `_compute_tags()`, `_auto_play_card()` | 341 |
| `setup.py` | `setup_game()` — standalone pygame lobby (player count, names, AI types) | 242 |
| `tactical_ui.py` | `TacticalUI` class (main game loop, rendering, input) + `launch()` | 1428 |

## Dependencies

- `pygame-ce >= 2.5` (install via `pip install -e ".[gui]"`)
- `twentyfive.game` (state, rules, engine)
- `twentyfive.ui.controller.GameController`
