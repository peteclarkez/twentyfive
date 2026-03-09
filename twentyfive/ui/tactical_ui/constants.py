"""
Layout, colour, and configuration constants for the Tactical Dashboard UI.
"""

from __future__ import annotations

from twentyfive.cards.card import Suit

# ---------------------------------------------------------------------------
# Window & layout constants
# ---------------------------------------------------------------------------

_W, _H = 1200, 800

_HDR_H = 72  # taller to hold face-up card thumbnail
_SIDE_W = 220  # left and right sidebar width
_CTR_W = _W - 2 * _SIDE_W  # 760 px centre column
_CTR_X = _SIDE_W
_ARENA_Y = _HDR_H
_ARENA_H = 340
_HAND_Y = _HDR_H + _ARENA_H
_HAND_H = _H - _HAND_Y  # 400 px

# ---------------------------------------------------------------------------
# Card sizes
# ---------------------------------------------------------------------------

_HAND_CW, _HAND_CH = 90, 126  # large hand cards
_ARENA_CW, _ARENA_CH = 70, 98  # arena / trick slot cards
_SMALL_CW, _SMALL_CH = 44, 62  # small (scorecard / opponent row)
_TRICK_CW, _TRICK_CH = 44, 62  # trick-zone history cards
_HDR_CARD_W, _HDR_CARD_H = 32, 45  # tiny face-up card in header
_CARD_GAP = 14
_CORNER = 8
_GAP = 4  # transparent gap between layout sections (lets background show through)

# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------

_BG_DARK = (18, 18, 30)
_BG_PANEL = (30, 30, 48)
_BG_CARD = (42, 42, 64)
_EMERALD = (80, 200, 120)
_EMERALD_D = (40, 120, 70)
_GOLD = (255, 191, 0)
_GOLD_D = (160, 110, 0)
_CYAN = (30, 210, 255)
_RED_SUIT = (232, 64, 64)
_BLK_SUIT = (200, 200, 210)
_CARD_FACE = (248, 244, 236)
_CARD_BACK = (28, 40, 100)
_TEXT_PRI = (232, 232, 240)
_TEXT_MUT = (120, 120, 144)
_PANEL_BDR = (60, 60, 90)
_DIVIDER = (50, 50, 76)
_DANGER = (232, 64, 64)

_SUIT_COLOUR: dict[Suit, tuple[int, int, int]] = {
    Suit.HEARTS: _RED_SUIT,
    Suit.DIAMONDS: (220, 100, 20),
    Suit.CLUBS: (80, 160, 80),
    Suit.SPADES: (80, 100, 210),
}

# ---------------------------------------------------------------------------
# Arena slot layout — clockwise from top-left for each player count.
# Each entry: (grid_cols, grid_rows, [(col, row), ...] in clockwise order)
# ---------------------------------------------------------------------------

_ARENA_CONFIG: dict[int, tuple[int, int, list[tuple[int, int]]]] = {
    2: (2, 1, [(0, 0), (1, 0)]),
    3: (2, 2, [(0, 0), (1, 0), (1, 1)]),
    4: (2, 2, [(0, 0), (1, 0), (1, 1), (0, 1)]),  # TL → TR → BR → BL
    5: (3, 2, [(0, 0), (1, 0), (2, 0), (2, 1), (0, 1)]),  # TL → TM → TR → BR → BL
    6: (3, 2, [(0, 0), (1, 0), (2, 0), (2, 1), (1, 1), (0, 1)]),  # full perimeter
}

# ---------------------------------------------------------------------------
# Setup screen constants
# ---------------------------------------------------------------------------

_SETUP_NAMES = [
    "Alice",
    "Bob",
    "Carol",
    "Dave",
    "Eve",
    "Frank",
    "Grace",
    "Hank",
    "Iris",
    "Jack",
    "Kate",
    "Leo",
]
_SETUP_AI_TYPES = ["Human", "Random", "Heuristic", "Enhanced", "ISMCTS"]

# ---------------------------------------------------------------------------
# Tag display order and colours.
# ---------------------------------------------------------------------------

_INDICATOR_SLOTS: list[tuple[str, tuple[int, int, int], tuple[int, int, int]]] = [
    ("WORST", _DANGER, (240, 220, 220)),
    ("CAN WIN", _EMERALD, (220, 240, 225)),
    ("BEST", _EMERALD, (220, 240, 225)),
    ("RENEGE", _GOLD, (240, 235, 200)),
]
_TAG_H = 13  # chip height
_TAG_PAD = 3  # horizontal padding inside each chip
_TAG_GAP = 2  # gap between chips

# ---------------------------------------------------------------------------
# Corner-bracket border helper constants
# ---------------------------------------------------------------------------

_BRACKET_LEN = 14  # length of each corner arm (px)
_BRACKET_T = 1  # line thickness
