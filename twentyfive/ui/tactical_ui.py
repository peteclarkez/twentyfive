"""
Tactical Dashboard UI for Twenty-Five.

A high-contrast dark-mode "command centre" layout:
  Left sidebar  — SCORECARD (player names, scores, trick pips)
  Centre top    — ARENA     (current trick slots in 2×2 grid, history row)
  Centre bottom — HAND      (current player's cards with rank badges + tags)
  Right sidebar — TRUMP ZONE (suit icon, face-up card, ROB / AUTO-PLAY buttons)
  Header bar    — GAME ID | ROUND N | TRICK N/5 | trump indicator

Run with:
    python -m twentyfive --gui --ui tactical_ui [--1v3 NAME] [--seeall]

Requires pygame-ce:  pip install -e ".[gui]"
"""

from __future__ import annotations

import math
import threading
from typing import TYPE_CHECKING

import pygame

from twentyfive.cards.card import Card, Suit, is_trump
from twentyfive.game.rules import (
    card_global_rank,
    get_renegeable_cards,
    trick_winner,
)
from twentyfive.game.state import (
    ConfirmRoundEnd,
    GameState,
    Move,
    PassRob,
    Phase,
    PlayCard,
    PlayerSnapshot,
    Rob,
    TrickPlay,
)

if TYPE_CHECKING:
    from twentyfive.ui.controller import GameController

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

# Custom pygame event posted by the AI worker thread
_AI_DONE = pygame.USEREVENT + 1

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
# Utility: pulse factor in [0, 1] driven by elapsed time
# ---------------------------------------------------------------------------


def _pulse(t: float, speed: float = 2.5) -> float:
    """Return a value in [0.0, 1.0] that oscillates with the given speed (Hz)."""
    return (math.sin(t * speed * math.pi * 2) + 1) / 2


# ---------------------------------------------------------------------------
# Button helper
# ---------------------------------------------------------------------------


class _Button:
    def __init__(
        self,
        rect: pygame.Rect,
        label: str,
        action: str,
        *,
        enabled: bool = True,
        colour: tuple[int, int, int] = _BG_PANEL,
        pulse_colour: tuple[int, int, int] | None = None,
    ) -> None:
        self.rect = rect
        self.label = label
        self.action = action
        self.enabled = enabled
        self._base_colour = colour
        self._pulse_colour = pulse_colour

    def draw(
        self,
        surf: pygame.Surface,
        font: pygame.font.Font,
        mouse: tuple[int, int],
        t: float = 0.0,
    ) -> None:
        if not self.enabled:
            col = _blend(_BG_PANEL, (20, 20, 28), 0.5)
        elif self._pulse_colour and self.enabled:
            col = _blend(self._base_colour, self._pulse_colour, _pulse(t))
        elif self.rect.collidepoint(mouse):
            col = _blend(self._base_colour, _TEXT_PRI, 0.2)
        else:
            col = self._base_colour

        pygame.draw.rect(surf, col, self.rect, border_radius=6)
        bdr = _TEXT_PRI if self.enabled else _TEXT_MUT
        pygame.draw.rect(surf, bdr, self.rect, 1, border_radius=6)
        txt_col = _TEXT_PRI if self.enabled else _TEXT_MUT
        txt = font.render(self.label, True, txt_col)
        surf.blit(txt, txt.get_rect(center=self.rect.center))

    def clicked(self, pos: tuple[int, int]) -> bool:
        return self.enabled and self.rect.collidepoint(pos)


def _blend(
    a: tuple[int, int, int],
    b: tuple[int, int, int],
    t: float,
) -> tuple[int, int, int]:
    """Linear interpolate between two RGB colours; t=0 → a, t=1 → b."""
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


# ---------------------------------------------------------------------------
# Strategic tag computation (mirrors CLI auto-play / hint logic)
# ---------------------------------------------------------------------------


def _compute_tags(
    card: Card,
    hand: list[Card],
    legal_cards: set[Card],
    current_trick: tuple[TrickPlay, ...],
    trump: Suit,
    led_card: Card | None,
) -> list[str]:
    """Return a list of short tag strings for a card in the human player's hand."""
    tags: list[str] = []

    # Rank badge handled separately; tags are strategic/status labels
    if card not in legal_cards:
        tags.append("ILLEGAL")
        return tags

    legal_list = [c for c in hand if c in legal_cards]

    # WORST — weakest legal card
    if legal_list:
        worst = max(legal_list, key=lambda c: card_global_rank(c, trump))
        if card == worst and len(legal_list) > 1:
            tags.append("WORST")

    # BEST — strongest card in hand
    if hand:
        best = min(hand, key=lambda c: card_global_rank(c, trump))
        if card == best and len(hand) > 1:
            tags.append("BEST")

    # CAN WIN — this card would win the trick if played now.
    # Simulate appending the card and check if it becomes the winner.
    # Mirrors cli.py logic exactly (trick_winner handles all suit/trump rules).
    if current_trick:
        led_suit = current_trick[0].card.suit
        sim = list(current_trick) + [TrickPlay(player_name="_sim", card=card)]
        if trick_winner(sim, led_suit, trump).card == card:
            tags.append("CAN WIN")

    # RENEGE — top-3 trump that may legally be withheld on a trump lead
    if led_card is not None:
        renegeable = get_renegeable_cards(hand, led_card, trump)
        if card in renegeable:
            tags.append("RENEGE")

    return tags


def _auto_play_card(state: GameState) -> Card | None:
    """
    Choose the card to play for auto-play:
    1. Worst of cards that CAN WIN the current trick.
    2. Otherwise worst legal card overall.
    Mirrors CLI [A] logic.
    """
    if state.trump_suit is None:
        return None
    trump = state.trump_suit
    legal = [m.card for m in state.legal_moves if isinstance(m, PlayCard)]
    if not legal:
        return None

    if state.current_trick:
        led_suit = state.current_trick[0].card.suit
        can_win = [
            c
            for c in legal
            if trick_winner(
                list(state.current_trick) + [TrickPlay(player_name="_sim", card=c)],
                led_suit,
                trump,
            ).card
            == c
        ]
        if can_win:
            return max(can_win, key=lambda c: card_global_rank(c, trump))

    return max(legal, key=lambda c: card_global_rank(c, trump))


# ---------------------------------------------------------------------------
# Card drawing primitives
# ---------------------------------------------------------------------------


def _draw_card_face(
    surf: pygame.Surface,
    rect: pygame.Rect,
    card: Card,
    trump: Suit,
    font_rank: pygame.font.Font,
    font_sym: pygame.font.Font,
    *,
    selected: bool = False,
    hover: bool = False,
    legal: bool = True,
    is_led: bool = False,
    is_winning: bool = False,
    border_override: tuple[int, int, int] | None = None,
) -> None:
    pygame.draw.rect(surf, _CARD_FACE, rect, border_radius=_CORNER)

    # Border priority: selected > winning > led > trump > hover > default
    if selected:
        bdr, bdr_w = _CYAN, 3
    elif is_winning:
        bdr, bdr_w = _EMERALD, 3
    elif is_led:
        bdr, bdr_w = _GOLD, 2
    elif is_trump(card, trump):
        bdr, bdr_w = _GOLD, 2
    elif hover and legal:
        bdr, bdr_w = (160, 160, 180), 2
    else:
        bdr, bdr_w = (140, 140, 155), 1

    if border_override:
        bdr = border_override

    pygame.draw.rect(surf, bdr, rect, bdr_w, border_radius=_CORNER)

    col = _SUIT_COLOUR[card.suit]

    # Top-left rank + suit
    r_surf = font_rank.render(card.rank.display, True, col)
    surf.blit(r_surf, (rect.x + 4, rect.y + 3))
    s_surf = font_rank.render(card.suit.symbol, True, col)
    surf.blit(s_surf, (rect.x + 4, rect.y + 3 + r_surf.get_height()))

    # Centre suit symbol (large)
    big = font_sym.render(card.suit.symbol, True, col)
    surf.blit(big, big.get_rect(center=rect.center))

    # Bottom-right rank (inverted)
    r2 = font_rank.render(card.rank.display, True, col)
    surf.blit(r2, (rect.right - r2.get_width() - 4, rect.bottom - r2.get_height() - 3))

    # Dim illegal
    if not legal:
        dim = pygame.Surface(rect.size, pygame.SRCALPHA)
        dim.fill((0, 0, 0, 140))
        surf.blit(dim, rect.topleft)


def _draw_card_back(surf: pygame.Surface, rect: pygame.Rect) -> None:
    pygame.draw.rect(surf, _CARD_BACK, rect, border_radius=_CORNER)
    inner = rect.inflate(-8, -8)
    pygame.draw.rect(surf, (50, 70, 160), inner, border_radius=max(0, _CORNER - 4))
    # Simple cross-hatch suggestion
    pygame.draw.rect(surf, (35, 50, 130), inner, 1, border_radius=max(0, _CORNER - 4))


def _draw_rank_badge(
    surf: pygame.Surface,
    rect: pygame.Rect,
    card: Card,
    trump: Suit,
    font: pygame.font.Font,
) -> None:
    """Draw #N rank badge in the top-RIGHT corner so it doesn't cover rank/suit."""
    rank = card_global_rank(card, trump)
    label = f"#{rank}"
    txt = font.render(label, True, (20, 20, 30))
    badge_w = txt.get_width() + 6
    badge_h = txt.get_height() + 2
    badge_rect = pygame.Rect(rect.right - badge_w - 2, rect.y + 2, badge_w, badge_h)
    badge_surf = pygame.Surface((badge_w, badge_h), pygame.SRCALPHA)
    badge_surf.fill((220, 220, 210, 210))
    surf.blit(badge_surf, badge_rect.topleft)
    surf.blit(txt, (badge_rect.x + 3, badge_rect.y + 1))


# Tag display order and colours.
_INDICATOR_SLOTS: list[tuple[str, tuple[int, int, int], tuple[int, int, int]]] = [
    ("WORST", _DANGER, (240, 220, 220)),
    ("CAN WIN", _EMERALD, (220, 240, 225)),
    ("BEST", _EMERALD, (220, 240, 225)),
    ("RENEGE", _GOLD, (240, 235, 200)),
]
_TAG_H = 13  # chip height
_TAG_PAD = 3  # horizontal padding inside each chip
_TAG_GAP = 2  # gap between chips


def _draw_card_indicators(
    surf: pygame.Surface,
    rect: pygame.Rect,
    tags: set[str],
    font: pygame.font.Font,
) -> None:
    """
    Render active tag labels as chips stacked bottom-to-top on the left of the card.
    """
    x = rect.x + 3
    y = rect.bottom - _TAG_H - 3
    for tag, bg, fg in _INDICATOR_SLOTS:
        if tag not in tags:
            continue
        txt = font.render(tag, True, fg)
        chip_w = txt.get_width() + _TAG_PAD * 2
        chip = pygame.Rect(x, y, chip_w, _TAG_H)
        chip_surf = pygame.Surface(chip.size, pygame.SRCALPHA)
        r, g, b = bg
        chip_surf.fill((r, g, b, 210))
        surf.blit(chip_surf, chip.topleft)
        surf.blit(txt, txt.get_rect(center=chip.center))
        y -= _TAG_H + _TAG_GAP


# ---------------------------------------------------------------------------
# TacticalUI — main class
# ---------------------------------------------------------------------------


class TacticalUI:
    """Tactical Dashboard UI for Twenty-Five."""

    def __init__(self, controller: GameController, *, show_all: bool = False) -> None:
        self._ctrl = controller
        self._show_all = show_all

        self._selected: Card | None = None
        self._rob_choosing = False
        self._status = ""
        self._ai_thinking = False
        self._buttons: list[_Button] = []
        self._t: float = 0.0  # elapsed seconds for animations
        self._last_trick_count: int = 0  # detect trick completions
        self._trick_pause_until: float = 0.0  # time when trick pause expires
        self._round_pause_until: float = 0.0  # time when round-end pause expires
        self._last_phase: Phase | None = None  # for phase-transition detection
        # Fixed hand slots — cards keep their initial position throughout the round.
        # _my_name is the human player; None = all-AI spectating (follow current player).
        self._my_name: str | None = (
            next(iter(controller.human_players)) if controller.human_players else None
        )
        self._hand_slots: list[Card | None] = [None] * 5
        self._last_round: int = -1
        # Delay before the next AI move fires (seconds) — gives 1 s between plays.
        self._ai_move_after: float = 0.0
        # Time when the game-over screen is shown; set when game ends so we show
        # the final round summary first.
        self._game_over_show_after: float = -1.0

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def run(self) -> None:
        pygame.init()
        screen = pygame.display.set_mode((_W, _H))
        pygame.display.set_caption("Twenty-Five — Tactical Dashboard")

        self._screen = screen
        self._font_title = pygame.font.SysFont("Arial", 22, bold=True)
        self._font_lg = pygame.font.SysFont("Arial", 20, bold=True)
        self._font_md = pygame.font.SysFont("Arial", 16)
        self._font_sm = pygame.font.SysFont("Arial", 13)
        self._font_xs = pygame.font.SysFont("Arial", 11)
        self._font_mono = pygame.font.SysFont("Courier New", 13)
        self._font_sym_lg = pygame.font.SysFont("Arial", 36, bold=True)
        self._font_sym_xl = pygame.font.SysFont("Arial", 56, bold=True)
        self._font_sym_hand = pygame.font.SysFont("Arial", 56, bold=True)  # hand card centre

        clock = pygame.time.Clock()
        running = True

        while running:
            dt = clock.tick(60) / 1000.0
            self._t += dt
            mouse = pygame.mouse.get_pos()
            trick_pausing = self._t < self._trick_pause_until
            round_pausing = self._t < self._round_pause_until
            pausing = trick_pausing or round_pausing

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

                elif event.type == pygame.KEYDOWN:
                    key = event.key
                    if key == pygame.K_ESCAPE:
                        running = False
                    elif key == pygame.K_SPACE:
                        # Space skips any active pause (including game-over pre-screen)
                        self._trick_pause_until = 0.0
                        self._round_pause_until = 0.0
                        self._game_over_show_after = 0.0
                    elif not pausing and not self._ai_thinking and not self._ctrl.is_game_over:
                        state = self._ctrl.state
                        is_human = not self._ctrl.is_ai_turn()
                        if key == pygame.K_RETURN:
                            if is_human and state.phase == Phase.TRICK and self._selected:
                                self._handle_action("play")
                            elif is_human and state.phase == Phase.ROUND_END:
                                self._handle_action("continue")
                        elif key == pygame.K_a and is_human and state.phase == Phase.TRICK:
                            self._handle_action("auto")
                        elif key == pygame.K_r and is_human and state.phase == Phase.ROB:
                            self._handle_action("rob")
                        elif key == pygame.K_p and is_human and state.phase == Phase.ROB:
                            self._handle_action("passrob")
                        elif key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5):
                            self._handle_slot_key(key - pygame.K_1, state)

                elif event.type == _AI_DONE:
                    self._ai_thinking = False
                    self._on_ai_done(event.dict["actor"], event.dict["move"])

                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if trick_pausing:
                        self._trick_pause_until = 0.0
                    elif round_pausing:
                        self._round_pause_until = 0.0
                    else:
                        self._handle_click(event.pos)

            if self._ctrl.is_game_over:
                # First time we detect game over: show the final round summary for 5 s.
                if self._game_over_show_after < 0:
                    self._game_over_show_after = self._t + 5.0
                    self._round_pause_until = self._game_over_show_after

                if self._t < self._game_over_show_after:
                    # Still in the final-round summary pause — draw the regular board.
                    state = self._ctrl.state
                    round_pausing = True
                    self._buttons = self._build_buttons(state)
                    self._draw(state, mouse, round_pausing=round_pausing)
                else:
                    self._draw_game_over()
            else:
                state = self._ctrl.state

                # Detect trick completion (triggers pause for tricks 1–4)
                curr_count = len(state.completed_tricks)
                if curr_count < self._last_trick_count:
                    self._last_trick_count = 0  # new round reset
                elif curr_count > self._last_trick_count and state.phase == Phase.TRICK:
                    self._trick_pause_until = self._t + 2.5
                    self._last_trick_count = curr_count
                else:
                    self._last_trick_count = curr_count

                # Detect ROUND_END entry — show round summary pause
                if state.phase == Phase.ROUND_END and self._last_phase != Phase.ROUND_END:
                    self._round_pause_until = self._t + 4.0
                self._last_phase = state.phase

                trick_pausing = self._t < self._trick_pause_until
                round_pausing = self._t < self._round_pause_until
                pausing = trick_pausing or round_pausing
                if (
                    not pausing
                    and not self._ai_thinking
                    and self._ctrl.is_ai_turn()
                    and self._t >= self._ai_move_after
                ):
                    self._start_ai_move()
                self._buttons = self._build_buttons(state)
                self._draw(state, mouse, round_pausing=round_pausing)

            pygame.display.flip()

        pygame.quit()

    # ------------------------------------------------------------------
    # AI threading
    # ------------------------------------------------------------------

    def _start_ai_move(self) -> None:
        self._ai_thinking = True
        name = self._ctrl.state.current_player.name
        self._status = f"{name} is thinking…"

        def _worker() -> None:
            actor, move, _ = self._ctrl.step_ai()
            pygame.event.post(pygame.event.Event(_AI_DONE, {"actor": actor, "move": move}))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_ai_done(self, actor: str, move: Move) -> None:
        state = self._ctrl.state
        if isinstance(move, PlayCard):
            self._status = f"{actor} played {move.card}"
        elif isinstance(move, Rob):
            taken = state.rob_this_round[1] if state.rob_this_round else "a card"
            self._status = f"{actor} robs — takes {taken}"
        elif isinstance(move, PassRob):
            self._status = f"{actor} passes"
        else:
            self._status = ""

        # Stagger: wait 1 s before firing the next AI move so each play is visible.
        self._ai_move_after = self._t + 1.0

    # ------------------------------------------------------------------
    # Click handling
    # ------------------------------------------------------------------

    def _handle_click(self, pos: tuple[int, int]) -> None:
        if self._ai_thinking:
            return
        if self._ctrl.is_game_over:
            return

        for btn in self._buttons:
            if btn.clicked(pos):
                self._handle_action(btn.action)
                return

        state = self._ctrl.state
        if not self._ctrl.is_ai_turn() and state.phase in (Phase.TRICK, Phase.ROB):
            card = self._card_at_hand(pos, state)
            if card is not None:
                self._handle_card_click(card, state)

    def _handle_action(self, action: str) -> None:
        state = self._ctrl.state
        match action:
            case "play":
                if self._selected is not None:
                    try:
                        self._ctrl.apply_move(PlayCard(self._selected))
                        self._selected = None
                        self._status = ""
                        self._ai_move_after = self._t + 1.0
                    except ValueError:
                        self._status = "Invalid move — try again"
            case "auto":
                card = _auto_play_card(state)
                if card is not None:
                    self._ctrl.apply_move(PlayCard(card))
                    self._selected = None
                    self._status = ""
                    self._ai_move_after = self._t + 1.0
            case "rob":
                self._rob_choosing = True
                self._status = "Click a card in your hand to discard"
            case "passrob":
                self._ctrl.apply_move(PassRob())
                self._rob_choosing = False
                self._status = ""
                self._ai_move_after = self._t + 1.0
            case "cancelrob":
                self._rob_choosing = False
                self._status = ""
            case "continue":
                self._ctrl.apply_move(ConfirmRoundEnd())
                self._selected = None
                self._status = ""
            case "quit":
                pygame.event.post(pygame.event.Event(pygame.QUIT))

    def _handle_card_click(self, card: Card, state: GameState) -> None:
        legal_cards = {m.card for m in state.legal_moves if isinstance(m, PlayCard)}

        if state.phase == Phase.ROB and self._rob_choosing:
            try:
                self._ctrl.apply_move(Rob(discard=card))
                self._rob_choosing = False
                self._status = ""
                self._ai_move_after = self._t + 1.0
            except ValueError:
                self._status = "Cannot discard that card"
            return

        if state.phase == Phase.TRICK:
            if card not in legal_cards:
                self._status = "That card is not legal to play"
                return
            if self._selected == card:
                self._ctrl.apply_move(PlayCard(card))
                self._selected = None
                self._status = ""
            else:
                self._selected = card
                self._status = f"Selected {card} — click again or [PLAY] to confirm"

    def _card_at_hand(self, pos: tuple[int, int], state: GameState) -> Card | None:
        for card, rect in zip(self._hand_slots, self._hand_card_rects()):
            if card is not None and rect.collidepoint(pos):
                return card
        return None

    def _sync_hand_slots(self, state: GameState, my_player: PlayerSnapshot) -> None:
        """Keep _hand_slots in sync with my_player's hand, preserving card positions."""
        if state.round_number != self._last_round:
            # Fresh round: initialise 5 slots from dealt hand (order preserved)
            hand = list(my_player.hand)
            self._hand_slots = hand + [None] * (5 - len(hand))
            self._last_round = state.round_number
        else:
            hand_set = set(my_player.hand)
            # Null out cards that have been played
            for i, c in enumerate(self._hand_slots):
                if c is not None and c not in hand_set:
                    self._hand_slots[i] = None
            # Place any new card (after ROB) into the first empty slot
            slot_set = {c for c in self._hand_slots if c is not None}
            for card in my_player.hand:
                if card not in slot_set:
                    for i in range(5):
                        if self._hand_slots[i] is None:
                            self._hand_slots[i] = card
                            break

    def _handle_slot_key(self, slot: int, state: GameState) -> None:
        """Handle key press 1–5 (0-indexed slot). Select then confirm, matching click behaviour."""
        if self._ctrl.is_ai_turn():
            return
        if slot < 0 or slot >= 5:
            return
        card = self._hand_slots[slot]
        if card is not None:
            self._handle_card_click(card, state)

    # ------------------------------------------------------------------
    # Button construction
    # ------------------------------------------------------------------

    def _build_buttons(self, state: GameState) -> list[_Button]:
        """Build context-sensitive buttons in the right sidebar, anchored to the bottom."""
        buttons: list[_Button] = []
        bw = _SIDE_W - 24
        bh = 42
        x = _W - _SIDE_W + 12
        gap = 12
        # Anchor at bottom: up to 3 buttons stacked from near the bottom
        y_start = _H - 3 * (bh + gap) - 12

        def _btn(
            label: str,
            action: str,
            *,
            enabled: bool = True,
            colour: tuple[int, int, int] = _BG_PANEL,
            pulse: tuple[int, int, int] | None = None,
            y_offset: int = 0,
        ) -> _Button:
            return _Button(
                pygame.Rect(x, y_start + y_offset, bw, bh),
                label,
                action,
                enabled=enabled,
                colour=colour,
                pulse_colour=pulse,
            )

        y = 0
        if state.phase == Phase.TRICK and not self._ctrl.is_ai_turn():
            play_label = f"PLAY {self._selected}" if self._selected else "PLAY CARD"
            buttons.append(
                _btn(
                    play_label,
                    "play",
                    enabled=self._selected is not None,
                    colour=_EMERALD_D,
                    y_offset=y,
                )
            )
            y += bh + gap
            buttons.append(_btn("AUTO-PLAY", "auto", colour=_EMERALD_D, y_offset=y))
            y += bh + gap
            buttons.append(_btn("QUIT", "quit", y_offset=y))

        elif state.phase == Phase.ROB and not self._ctrl.is_ai_turn():
            has_rob = any(isinstance(m, Rob) for m in state.legal_moves)
            face = state.face_up_card
            rob_label = f"ROB {face}" if face else "ROB"
            if self._rob_choosing:
                buttons.append(_btn("CANCEL ROB", "cancelrob", y_offset=y))
                y += bh + gap
            else:
                buttons.append(
                    _btn(
                        rob_label,
                        "rob",
                        enabled=has_rob,
                        colour=_GOLD_D,
                        pulse=_GOLD if has_rob else None,
                        y_offset=y,
                    )
                )
                y += bh + gap
                buttons.append(_btn("PASS", "passrob", y_offset=y))
                y += bh + gap
            buttons.append(_btn("QUIT", "quit", y_offset=y))

        elif state.phase == Phase.ROUND_END:
            buttons.append(_btn("NEXT ROUND", "continue", colour=_EMERALD_D, y_offset=y))
            y += bh + gap
            buttons.append(_btn("QUIT", "quit", y_offset=y))

        else:
            buttons.append(_btn("QUIT", "quit", y_offset=y))

        return buttons

    # ------------------------------------------------------------------
    # Main draw
    # ------------------------------------------------------------------

    def _draw(
        self, state: GameState, mouse: tuple[int, int], *, round_pausing: bool = False
    ) -> None:
        assert state.trump_suit is not None
        self._screen.fill(_BG_DARK)
        self._draw_header(state)
        self._draw_scorecard(state)
        self._draw_trick_zone(state)
        self._draw_arena(state)
        self._draw_hand_panel(state, mouse)
        # Buttons are hidden during round-end pause (overlay covers the centre)
        if not round_pausing:
            for btn in self._buttons:
                btn.draw(self._screen, self._font_md, mouse, self._t)
        if self._t < self._trick_pause_until:
            self._draw_trick_pause(state)
        if round_pausing:
            self._draw_round_end_pause(state)

    # ------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------

    def _draw_header(self, state: GameState) -> None:
        pygame.draw.rect(self._screen, _BG_PANEL, (0, 0, _W, _HDR_H))
        pygame.draw.line(self._screen, _PANEL_BDR, (0, _HDR_H - 1), (_W, _HDR_H - 1))

        # Left: Game ID
        gid = self._font_mono.render(f"GAME ID: {state.game_id[:8]}", True, _TEXT_MUT)
        self._screen.blit(gid, (16, (_HDR_H - gid.get_height()) // 2))

        # Centre: Round | Trick
        if state.phase == Phase.ROUND_END:
            trick_str = "ROUND COMPLETE"
        elif state.phase == Phase.GAME_OVER:
            trick_str = "GAME OVER"
        else:
            trick_str = f"TRICK {state.trick_number}/5"
        centre_text = f"ROUND {state.round_number}  |  {trick_str}"
        ct = self._font_lg.render(centre_text, True, _TEXT_PRI)
        self._screen.blit(ct, ct.get_rect(centerx=_W // 2, centery=_HDR_H // 2))

        # Right cluster: face-up card thumbnail + trump indicator
        if state.trump_suit is not None:
            trump = state.trump_suit
            col = _SUIT_COLOUR[trump]
            trump_text = f"{trump.symbol}  {trump.name.upper()} TRUMPS"
            tt = self._font_md.render(trump_text, True, col)

            # Face-up card thumbnail (if still in play)
            right_margin = 12
            card_x = _W - right_margin - _HDR_CARD_W
            card_y = (_HDR_H - _HDR_CARD_H) // 2
            if state.face_up_card:
                fup_rect = pygame.Rect(card_x, card_y, _HDR_CARD_W, _HDR_CARD_H)
                _draw_card_face(
                    self._screen,
                    fup_rect,
                    state.face_up_card,
                    trump,
                    self._font_xs,
                    self._font_xs,
                    border_override=_GOLD,
                )
                # Trump text to the left of the card
                self._screen.blit(
                    tt,
                    (
                        card_x - tt.get_width() - 8,
                        (_HDR_H - tt.get_height()) // 2,
                    ),
                )
            else:
                # No face-up card: just show trump text right-aligned
                self._screen.blit(
                    tt,
                    (
                        _W - tt.get_width() - right_margin,
                        (_HDR_H - tt.get_height()) // 2,
                    ),
                )

    # ------------------------------------------------------------------
    # Scorecard sidebar (left)
    # ------------------------------------------------------------------

    def _draw_scorecard(self, state: GameState) -> None:
        panel = pygame.Rect(0, _HDR_H, _SIDE_W, _H - _HDR_H)
        pygame.draw.rect(self._screen, _BG_PANEL, panel)
        pygame.draw.line(self._screen, _PANEL_BDR, (_SIDE_W - 1, _HDR_H), (_SIDE_W - 1, _H))

        title = self._font_sm.render("SCORECARD", True, _TEXT_MUT)
        self._screen.blit(title, (12, _HDR_H + 10))

        max_score = max(p.score for p in state.players) if state.players else 0
        n_players = len(state.players)
        available_h = _H - _HDR_H - 40  # space below the "SCORECARD" title
        row_h = min(90, max(60, available_h // max(n_players, 1)))
        y = _HDR_H + 36
        _ROB_CW, _ROB_CH = 26, 37  # tiny inline rob-card size

        for i, player in enumerate(state.players):
            is_active = i == state.current_player_index
            is_dealer = i == state.dealer_index
            is_leader = max_score > 0 and player.score == max_score

            row_rect = pygame.Rect(6, y, _SIDE_W - 12, row_h - 6)

            # Active player: glowing emerald border
            if is_active and state.phase not in (Phase.ROUND_END, Phase.GAME_OVER):
                p_factor = _pulse(self._t, 1.5)
                border_col = _blend(_EMERALD_D, _EMERALD, p_factor)
                pygame.draw.rect(self._screen, border_col, row_rect, 2, border_radius=6)

            # Leader: gold border (skipped when also active — emerald takes priority)
            if is_leader and not is_active:
                pygame.draw.rect(self._screen, _GOLD, row_rect, 1, border_radius=6)

            # Status dot
            dot_col = _EMERALD if is_active else _TEXT_MUT
            pygame.draw.circle(self._screen, dot_col, (18, y + 14), 5)

            # Name + [D] dealer badge
            name_parts = [player.name]
            if is_dealer:
                name_parts.append("[D]")
            name_str = "  ".join(name_parts)
            name_surf = self._font_md.render(name_str, True, _EMERALD if is_active else _TEXT_PRI)
            self._screen.blit(name_surf, (28, y + 6))

            # Post-rob card: tiny thumbnail to the right of the name on the same row.
            # Shown for the entire round once a rob is known — even after the card is played.
            if (
                state.rob_this_round
                and state.rob_this_round[0] == player.name
                and state.trump_suit is not None
            ):
                _, card_taken = state.rob_this_round
                rob_x = _SIDE_W - _ROB_CW - 8
                trect = pygame.Rect(rob_x, y + 4, _ROB_CW, _ROB_CH)
                _draw_card_face(
                    self._screen,
                    trect,
                    card_taken,
                    state.trump_suit,
                    self._font_xs,
                    self._font_xs,
                    border_override=_GOLD,
                )

            # Score + progress bar  (leader row is gold)
            score_str = f"{player.score} / 25"
            score_col = _GOLD if is_leader else _TEXT_MUT
            sc_surf = self._font_sm.render(score_str, True, score_col)
            self._screen.blit(sc_surf, (28, y + 28))

            bar_rect = pygame.Rect(28, y + 44, _SIDE_W - 44, 7)
            pygame.draw.rect(self._screen, _BG_DARK, bar_rect, border_radius=4)
            filled = int(bar_rect.width * min(player.score, 25) / 25)
            if filled > 0:
                bar_col = _GOLD if player.score >= 20 else _EMERALD
                pygame.draw.rect(
                    self._screen,
                    bar_col,
                    pygame.Rect(bar_rect.x, bar_rect.y, filled, bar_rect.height),
                    border_radius=4,
                )

            # Trick pips
            pip_x = 28
            pip_y = y + 58
            for _ in range(player.tricks_won_this_round):
                pygame.draw.rect(
                    self._screen, _EMERALD, pygame.Rect(pip_x, pip_y, 12, 12), border_radius=3
                )
                pip_x += 16
            if player.tricks_won_this_round == 0:
                nd = self._font_xs.render("no tricks", True, _TEXT_MUT)
                self._screen.blit(nd, (28, pip_y))

            y += row_h

    # ------------------------------------------------------------------
    # Trick zone sidebar (right) — shows completed trick history
    # ------------------------------------------------------------------

    def _draw_trick_zone(self, state: GameState) -> None:
        assert state.trump_suit is not None
        trump = state.trump_suit

        panel = pygame.Rect(_W - _SIDE_W, _HDR_H, _SIDE_W, _H - _HDR_H)
        pygame.draw.rect(self._screen, _BG_PANEL, panel)
        pygame.draw.line(self._screen, _PANEL_BDR, (_W - _SIDE_W, _HDR_H), (_W - _SIDE_W, _H))

        title = self._font_sm.render("TRICK ZONE", True, _TEXT_MUT)
        self._screen.blit(title, (_W - _SIDE_W + 12, _HDR_H + 10))

        # Status message just below title
        if self._status:
            st = self._font_xs.render(self._status, True, _EMERALD)
            self._screen.blit(st, (_W - _SIDE_W + 12, _HDR_H + 28))

        # ------------------------------------------------------------------
        # Completed tricks — one block per trick, most-recent at top
        # Each block: "Trick N — WinnerName" + row of 4 small cards
        # ------------------------------------------------------------------
        # Adapt mini-card width so all players' cards fit in the sidebar
        n_players = len(state.players)
        side_x = _W - _SIDE_W + 6
        inner_w = _SIDE_W - 12
        trick_cw = max(24, min(44, (inner_w - n_players * 2) // n_players))
        trick_ch = int(trick_cw * 62 / 44)
        trick_row_h = trick_ch + 20  # card height + label row

        # Buttons are anchored to the bottom (_build_buttons handles y_start).
        # Leave _TRICK_BTN_AREA px at the bottom for buttons.
        _TRICK_BTN_AREA = 160
        trick_start_y = _HDR_H + 50

        for t_idx, trick in enumerate(state.completed_tricks):
            ty = trick_start_y + t_idx * (trick_row_h + 8)
            if ty + trick_row_h > _H - _TRICK_BTN_AREA - 4:
                break  # no space above button area

            led_suit = trick[0].card.suit
            winner_tp = trick_winner(list(trick), led_suit, trump)

            # Block background
            block = pygame.Rect(side_x, ty, inner_w, trick_row_h + 6)
            pygame.draw.rect(self._screen, _BG_DARK, block, border_radius=4)

            # "Trick N — Winner" header
            hdr = self._font_xs.render(
                f"Trick {t_idx + 1}  —  {winner_tp.player_name}", True, _EMERALD
            )
            self._screen.blit(hdr, (side_x + 4, ty + 3))

            # Mini cards in player order — width adapted to player count
            card_y = ty + 3 + hdr.get_height() + 3
            cx = side_x + 4
            played_map = {tp.player_name: tp.card for tp in trick}
            for player in state.players:
                played_card = played_map.get(player.name)
                card_rect = pygame.Rect(cx, card_y, trick_cw, trick_ch)
                if played_card:
                    is_win = player.name == winner_tp.player_name
                    _draw_card_face(
                        self._screen,
                        card_rect,
                        played_card,
                        trump,
                        self._font_xs,
                        self._font_sm,
                        is_winning=is_win,
                    )
                    # Player name initial below card
                    init = self._font_xs.render(
                        player.name[:3].upper(), True, _EMERALD if is_win else _TEXT_MUT
                    )
                    self._screen.blit(
                        init, init.get_rect(centerx=card_rect.centerx, y=card_rect.bottom + 1)
                    )
                else:
                    pygame.draw.rect(self._screen, _BG_CARD, card_rect, border_radius=4)
                cx += trick_cw + 3

        # Show a placeholder when no tricks yet
        if not state.completed_tricks:
            ph = self._font_xs.render("No tricks yet", True, _TEXT_MUT)
            self._screen.blit(ph, (side_x + 8, trick_start_y + 4))

    # ------------------------------------------------------------------
    # Arena (centre, upper half)
    # ------------------------------------------------------------------

    def _draw_arena(self, state: GameState) -> None:
        assert state.trump_suit is not None
        trump = state.trump_suit

        arena_rect = pygame.Rect(_CTR_X, _ARENA_Y, _CTR_W, _ARENA_H)
        pygame.draw.rect(self._screen, _BG_DARK, arena_rect)

        title = self._font_sm.render("ARENA", True, _TEXT_MUT)
        self._screen.blit(title, (_CTR_X + 12, _ARENA_Y + 8))

        # -- Trick slots in a dynamic grid: 2–6 players supported --
        slot_area_h = _ARENA_H - 30  # full height minus title strip
        slot_area_y = _ARENA_Y + 30

        n = len(state.players)
        # Use clockwise slot ordering from _ARENA_CONFIG
        cols, rows, slot_positions = _ARENA_CONFIG.get(n, _ARENA_CONFIG[4])
        col_w = _CTR_W // cols
        row_h = slot_area_h // rows

        slot_centres = [
            (_CTR_X + cp[0] * col_w + col_w // 2, slot_area_y + cp[1] * row_h + row_h // 2)
            for cp in slot_positions[:n]
        ]

        # Build lookup: player_name → TrickPlay (from current trick)
        played: dict[str, TrickPlay] = {tp.player_name: tp for tp in state.current_trick}
        led_name = state.current_trick[0].player_name if state.current_trick else None

        # Determine current winner
        winner_name: str | None = None
        if state.current_trick:
            led_suit = state.current_trick[0].card.suit
            w = trick_winner(list(state.current_trick), led_suit, trump)
            winner_name = w.player_name

        for idx in range(n):
            player = state.players[idx]
            cx, cy = slot_centres[idx]
            slot_rect = pygame.Rect(cx - _ARENA_CW // 2, cy - _ARENA_CH // 2, _ARENA_CW, _ARENA_CH)

            tp = played.get(player.name)
            if tp:
                is_led = player.name == led_name
                is_winning = player.name == winner_name
                _draw_card_face(
                    self._screen,
                    slot_rect,
                    tp.card,
                    trump,
                    self._font_sm,
                    self._font_lg,
                    is_led=is_led,
                    is_winning=is_winning,
                )
                # [LED] label
                if is_led:
                    lt = self._font_xs.render("[LED]", True, _GOLD)
                    self._screen.blit(lt, lt.get_rect(centerx=cx, y=slot_rect.bottom + 2))
                # [WINNING] badge
                if is_winning:
                    p_factor = _pulse(self._t, 2.0)
                    wc = _blend(_EMERALD_D, _EMERALD, p_factor)
                    wt = self._font_xs.render("WINNING", True, wc)
                    self._screen.blit(
                        wt, wt.get_rect(centerx=cx, y=slot_rect.top - wt.get_height() - 2)
                    )
            else:
                # Empty slot
                pygame.draw.rect(self._screen, _BG_CARD, slot_rect, border_radius=6)
                pygame.draw.rect(self._screen, _PANEL_BDR, slot_rect, 1, border_radius=6)

            # Player name label below slot
            name_lbl = self._font_xs.render(player.name.upper(), True, _TEXT_MUT)
            name_y = slot_rect.bottom + (20 if tp and state.current_trick else 4)
            self._screen.blit(name_lbl, name_lbl.get_rect(centerx=cx, y=name_y))

    # ------------------------------------------------------------------
    # Hand panel (centre, lower half)
    # ------------------------------------------------------------------

    def _draw_hand_panel(self, state: GameState, mouse: tuple[int, int]) -> None:
        assert state.trump_suit is not None
        trump = state.trump_suit

        # Always show the human player's hand (or current player in all-AI mode)
        if self._my_name:
            my_player = next(
                (p for p in state.players if p.name == self._my_name),
                state.current_player,
            )
        else:
            my_player = state.current_player

        # Sync fixed slot positions
        self._sync_hand_slots(state, my_player)

        is_my_turn = not self._ctrl.is_ai_turn() and my_player.name == state.current_player.name

        # Panel background
        hand_rect = pygame.Rect(_CTR_X, _HAND_Y, _CTR_W, _HAND_H)
        pygame.draw.rect(self._screen, _BG_PANEL, hand_rect)
        pygame.draw.line(self._screen, _PANEL_BDR, (_CTR_X, _HAND_Y), (_CTR_X + _CTR_W, _HAND_Y))

        # Title
        rob_choosing_mine = state.phase == Phase.ROB and self._rob_choosing and is_my_turn
        if rob_choosing_mine:
            title_str = f"{my_player.name.upper()}'S HAND  —  CLICK CARD TO DISCARD"
            title_col = _GOLD
        elif state.phase == Phase.ROUND_END:
            title_str = "ROUND SUMMARY"
            title_col = _TEXT_MUT
        else:
            title_str = f"{my_player.name.upper()}'S HAND"
            title_col = _TEXT_MUT
        title = self._font_sm.render(title_str, True, title_col)
        self._screen.blit(title, (_CTR_X + 12, _HAND_Y + 10))

        # Opponent hands at top of hand panel (compact backs or faces)
        opp_y = _HAND_Y + 34
        self._draw_opponent_row(state, opp_y, trump, my_player)

        # Divider
        div_y = opp_y + _SMALL_CH + 14
        pygame.draw.line(self._screen, _DIVIDER, (_CTR_X + 8, div_y), (_CTR_X + _CTR_W - 8, div_y))

        # Hand: always 5 fixed slots regardless of cards remaining
        hand_cards = [c for c in self._hand_slots if c is not None]
        if not hand_cards and state.phase not in (Phase.ROUND_END,):
            return

        # Legal cards — only valid when it's the human's turn
        if is_my_turn:
            legal_cards: set[Card] = {m.card for m in state.legal_moves if isinstance(m, PlayCard)}
        else:
            # Not the human's turn: treat all hand cards as "legal" (no ILLEGAL dim)
            legal_cards = set(hand_cards)

        led_card = state.current_trick[0].card if state.current_trick else None
        rects = self._hand_card_rects(5)  # always 5 fixed rects

        for slot_idx, (slot_card, rect) in enumerate(zip(self._hand_slots, rects)):
            key_hint = str(slot_idx + 1)

            if slot_card is None:
                # Empty slot: dim placeholder
                pygame.draw.rect(self._screen, _BG_CARD, rect, border_radius=8)
                pygame.draw.rect(self._screen, _PANEL_BDR, rect, 1, border_radius=8)
                lbl = self._font_xs.render(key_hint, True, _TEXT_MUT)
                self._screen.blit(lbl, lbl.get_rect(center=rect.center))
                continue

            card = slot_card
            hover = rect.collidepoint(mouse)
            is_legal = card in legal_cards
            is_selected = card == self._selected
            is_rob_target = rob_choosing_mine

            # Hover lift animation
            draw_rect = rect.copy()
            if is_selected:
                draw_rect.y -= 20
            elif hover and (is_legal or is_rob_target):
                draw_rect.y -= 10

            _draw_card_face(
                self._screen,
                draw_rect,
                card,
                trump,
                self._font_md,
                self._font_sym_hand,
                selected=is_selected,
                hover=hover,
                legal=(is_legal or is_rob_target),
            )

            # Rank badge
            if state.phase not in (Phase.ROUND_END,):
                _draw_rank_badge(self._screen, draw_rect, card, trump, self._font_xs)

            # Key-number hint below card
            lbl = self._font_xs.render(key_hint, True, _TEXT_MUT)
            self._screen.blit(lbl, lbl.get_rect(centerx=draw_rect.centerx, y=draw_rect.bottom + 4))

            # Strategic indicators (bottom-left corner of card)
            tags = _compute_tags(
                card,
                hand_cards,
                legal_cards,
                state.current_trick,
                trump,
                led_card,
            )
            _draw_card_indicators(self._screen, draw_rect, set(tags), self._font_xs)

    def _draw_opponent_row(
        self, state: GameState, y: int, trump: Suit, my_player: PlayerSnapshot
    ) -> None:
        """Compact row of opponent hands across the top of the hand panel."""
        my_name = my_player.name
        opps = [(i, p) for i, p in enumerate(state.players) if p.name != my_name]
        if not opps:
            return

        total_opps = len(opps)
        segment_w = _CTR_W // total_opps

        # Scale card width to fit 5 cards per segment with a small gap
        max_hand = 5
        card_gap = 3
        opp_cw = min(_SMALL_CW, max(14, (segment_w - 8 - (max_hand - 1) * card_gap) // max_hand))
        opp_ch = int(opp_cw * _SMALL_CH / _SMALL_CW)

        for seg_idx, (_, opp) in enumerate(opps):
            seg_x = _CTR_X + seg_idx * segment_w
            name_s = self._font_xs.render(f"{opp.name}  ({opp.hand_size})", True, _TEXT_MUT)
            self._screen.blit(name_s, (seg_x + 4, y))
            cx = seg_x + 4
            card_y = y + name_s.get_height() + 2
            if self._show_all:
                for card in opp.hand:
                    r = pygame.Rect(cx, card_y, opp_cw, opp_ch)
                    _draw_card_face(self._screen, r, card, trump, self._font_xs, self._font_xs)
                    cx += opp_cw + card_gap
            else:
                # Hidden: backs + public rob info
                shown_cards: set[Card] = set()
                if state.rob_this_round and state.rob_this_round[0] == opp.name:
                    _, card_taken = state.rob_this_round
                    from twentyfive.cards.card import Rank

                    ace_of_trump = Card(Rank.ACE, trump)
                    if card_taken in opp.hand:
                        shown_cards.add(card_taken)
                    is_dealer_rob = any(
                        i == state.dealer_index
                        for i, p in enumerate(state.players)
                        if p.name == opp.name
                    )
                    if not is_dealer_rob and ace_of_trump in opp.hand:
                        shown_cards.add(ace_of_trump)

                for card in opp.hand:
                    r = pygame.Rect(cx, card_y, opp_cw, opp_ch)
                    if card in shown_cards:
                        _draw_card_face(
                            self._screen,
                            r,
                            card,
                            trump,
                            self._font_xs,
                            self._font_sm,
                            border_override=_GOLD,
                        )
                    else:
                        _draw_card_back(self._screen, r)
                    cx += opp_cw + card_gap

    # ------------------------------------------------------------------
    # Game over overlay
    # ------------------------------------------------------------------

    def _draw_game_over(self) -> None:
        self._screen.fill(_BG_DARK)
        state = self._ctrl.state
        sorted_p = sorted(state.players, key=lambda p: p.score, reverse=True)

        title = self._font_title.render("GAME OVER", True, _GOLD)
        self._screen.blit(title, title.get_rect(centerx=_W // 2, y=120))

        winner = sorted_p[0]
        sub = self._font_lg.render(
            f"Winner: {winner.name}  with  {winner.score} points", True, _EMERALD
        )
        self._screen.blit(sub, sub.get_rect(centerx=_W // 2, y=180))

        y = 260
        for p in sorted_p:
            line = self._font_md.render(f"{p.name:<20} {p.score} pts", True, _TEXT_PRI)
            self._screen.blit(line, line.get_rect(centerx=_W // 2, y=y))
            y += 34

        hint = self._font_sm.render("Press ESC or click to quit", True, _TEXT_MUT)
        self._screen.blit(hint, hint.get_rect(centerx=_W // 2, y=_H - 50))

    # ------------------------------------------------------------------
    # Trick-pause overlay
    # ------------------------------------------------------------------

    def _draw_trick_pause(self, state: GameState) -> None:
        """Semi-transparent banner shown for 2.5 s after each trick completes."""
        assert state.trump_suit is not None
        trump = state.trump_suit

        # The trick that just finished is the last entry in completed_tricks
        if not state.completed_tricks:
            return
        trick = state.completed_tricks[-1]
        led_suit = trick[0].card.suit
        winner_tp = trick_winner(list(trick), led_suit, trump)

        # Dark semi-transparent overlay across the centre column
        overlay_h = 130
        overlay_y = _ARENA_Y + (_ARENA_H - overlay_h) // 2
        overlay = pygame.Surface((_CTR_W, overlay_h), pygame.SRCALPHA)
        overlay.fill((10, 10, 20, 210))
        self._screen.blit(overlay, (_CTR_X, overlay_y))

        # "TRICK N — WinnerName wins!" text
        t_num = len(state.completed_tricks)
        msg = self._font_title.render(
            f"Trick {t_num}  —  {winner_tp.player_name} wins!", True, _EMERALD
        )
        self._screen.blit(msg, msg.get_rect(centerx=_CTR_X + _CTR_W // 2, y=overlay_y + 14))

        # Show winning card
        win_rect = pygame.Rect(
            _CTR_X + _CTR_W // 2 - _ARENA_CW // 2,
            overlay_y + 44,
            _ARENA_CW,
            _ARENA_CH,
        )
        _draw_card_face(
            self._screen,
            win_rect,
            winner_tp.card,
            trump,
            self._font_md,
            self._font_sym_lg,
            is_winning=True,
        )

        # Skip hint (fades in after 0.5 s)
        if self._trick_pause_until - self._t < 2.0:
            hint = self._font_xs.render("SPACE or click to continue", True, _TEXT_MUT)
            self._screen.blit(
                hint,
                hint.get_rect(
                    centerx=_CTR_X + _CTR_W // 2, y=overlay_y + overlay_h - hint.get_height() - 4
                ),
            )

    # ------------------------------------------------------------------
    # Round-end pause overlay
    # ------------------------------------------------------------------

    def _draw_round_end_pause(self, state: GameState) -> None:
        """Overlay shown for 4 s at round end — displays per-player trick/score summary."""
        # Semi-transparent overlay across the centre column
        overlay_h = _ARENA_H + _HAND_H
        overlay = pygame.Surface((_CTR_W, overlay_h), pygame.SRCALPHA)
        overlay.fill((10, 10, 20, 220))
        self._screen.blit(overlay, (_CTR_X, _ARENA_Y))

        cy = _ARENA_Y + 30
        title = self._font_title.render(f"ROUND {state.round_number} COMPLETE", True, _GOLD)
        self._screen.blit(title, title.get_rect(centerx=_CTR_X + _CTR_W // 2, y=cy))
        cy += title.get_height() + 24

        # Per-player summary rows
        for p in state.players:
            pip_str = "●" * p.tricks_won_this_round + "○" * (5 - p.tricks_won_this_round)
            line_str = f"{p.name:<16}  {pip_str}  →  {p.score} pts"
            col = _EMERALD if p.tricks_won_this_round > 0 else _TEXT_MUT
            line = self._font_lg.render(line_str, True, col)
            self._screen.blit(line, line.get_rect(centerx=_CTR_X + _CTR_W // 2, y=cy))
            cy += line.get_height() + 10

        # Skip hint (shows after 1 s)
        if self._round_pause_until - self._t < 3.0:
            hint = self._font_xs.render("SPACE or click to continue", True, _TEXT_MUT)
            self._screen.blit(
                hint,
                hint.get_rect(centerx=_CTR_X + _CTR_W // 2, y=_ARENA_Y + overlay_h - 28),
            )

    # ------------------------------------------------------------------
    # Geometry helpers
    # ------------------------------------------------------------------

    def _hand_card_rects(self, n: int = 5) -> list[pygame.Rect]:
        """Return 5 fixed slot rects (n is ignored — slots are always 5)."""
        total = 5 * _HAND_CW + 4 * _CARD_GAP
        x0 = _CTR_X + (_CTR_W - total) // 2
        y = _HAND_Y + (_HAND_H - _HAND_CH) // 2 + 20
        return [
            pygame.Rect(x0 + i * (_HAND_CW + _CARD_GAP), y, _HAND_CW, _HAND_CH) for i in range(5)
        ]


# ---------------------------------------------------------------------------
# Setup lobby — called by __main__.py before the game engine is created
# ---------------------------------------------------------------------------


def setup_game() -> tuple[list[str], dict[str, str]] | None:
    """
    Show a pygame setup lobby.

    Returns ``(player_names, {name: type_string})`` where *type_string* is one
    of "Human", "Random", "Heuristic", "Enhanced", "ISMCTS".
    Returns ``None`` if the user closes the window without starting.
    """
    pygame.init()
    screen = pygame.display.set_mode((_W, _H))
    pygame.display.set_caption("Twenty-Five — Setup")
    clock = pygame.time.Clock()

    font_title = pygame.font.SysFont("monospace", 40, bold=True)
    font_hdr = pygame.font.SysFont("monospace", 22, bold=True)
    font_md = pygame.font.SysFont("monospace", 20)
    font_sm = pygame.font.SysFont("monospace", 16)

    # --- State ---
    n = 4
    names: list[str] = list(_SETUP_NAMES[:6])  # always keep 6 slots; use names[:n]
    ai_types: list[str] = ["Enhanced"] * 6
    focused = -1  # index of name field being edited, or -1

    # --- Layout ---
    TBL_X = 180
    NUM_COL_W = 50
    NAME_COL_X = TBL_X + NUM_COL_W
    NAME_COL_W = 360
    TYPE_COL_X = NAME_COL_X + NAME_COL_W + 20
    TYPE_COL_W = 300
    ROW_H = 52
    ROWS_Y = 285
    HDR_Y = ROWS_Y - 34
    COUNT_Y = 158
    COUNT_X0 = _W // 2 - (5 * 70) // 2

    BTN_Y = ROWS_Y + 6 * ROW_H + 24
    start_rect = pygame.Rect(_W // 2 - 130, BTN_Y, 230, 46)
    quit_rect = pygame.Rect(_W // 2 + 115, BTN_Y, 110, 46)

    def _count_rect(n_val: int) -> pygame.Rect:
        return pygame.Rect(COUNT_X0 + (n_val - 2) * 70, COUNT_Y, 60, 36)

    def _name_rect(i: int) -> pygame.Rect:
        return pygame.Rect(NAME_COL_X, ROWS_Y + i * ROW_H + 10, NAME_COL_W, 32)

    def _type_prev_rect(i: int) -> pygame.Rect:
        return pygame.Rect(TYPE_COL_X, ROWS_Y + i * ROW_H + 10, 30, 32)

    def _type_next_rect(i: int) -> pygame.Rect:
        return pygame.Rect(TYPE_COL_X + TYPE_COL_W - 30, ROWS_Y + i * ROW_H + 10, 30, 32)

    t_start = pygame.time.get_ticks() / 1000.0
    running = True
    result: tuple[list[str], dict[str, str]] | None = None

    while running:
        t = pygame.time.get_ticks() / 1000.0 - t_start
        mouse = pygame.mouse.get_pos()
        screen.fill(_BG_DARK)

        # Title
        title_s = font_title.render("TWENTY-FIVE", True, _GOLD)
        screen.blit(title_s, title_s.get_rect(centerx=_W // 2, y=38))
        sub_s = font_hdr.render("Player Setup", True, _TEXT_MUT)
        screen.blit(sub_s, sub_s.get_rect(centerx=_W // 2, y=86))
        pygame.draw.line(screen, _DIVIDER, (80, 120), (_W - 80, 120), 1)

        # Player count selector
        lbl_s = font_md.render("Number of Players:", True, _TEXT_PRI)
        screen.blit(lbl_s, lbl_s.get_rect(centerx=_W // 2, y=130))
        for n_val in range(2, 7):
            r = _count_rect(n_val)
            sel = n_val == n
            pygame.draw.rect(screen, _EMERALD_D if sel else _BG_PANEL, r, border_radius=6)
            pygame.draw.rect(screen, _EMERALD if sel else _PANEL_BDR, r, 1, border_radius=6)
            cs = font_hdr.render(str(n_val), True, _EMERALD if sel else _TEXT_PRI)
            screen.blit(cs, cs.get_rect(center=r.center))

        # Column headers
        pygame.draw.line(
            screen, _DIVIDER, (TBL_X, HDR_Y + 26), (TYPE_COL_X + TYPE_COL_W, HDR_Y + 26), 1
        )
        screen.blit(font_hdr.render("#", True, _TEXT_MUT), (TBL_X + 12, HDR_Y))
        screen.blit(font_hdr.render("Name", True, _TEXT_MUT), (NAME_COL_X + 4, HDR_Y))
        screen.blit(font_hdr.render("Type", True, _TEXT_MUT), (TYPE_COL_X + 4, HDR_Y))

        # Player rows
        for i in range(6):
            active_row = i < n
            row_y = ROWS_Y + i * ROW_H

            if not active_row:
                dim = font_sm.render(f"— slot {i + 1} inactive —", True, _DIVIDER)
                screen.blit(dim, dim.get_rect(x=NAME_COL_X, y=row_y + 16))
                continue

            # Row number
            num_s = font_md.render(str(i + 1), True, _GOLD if i == 0 else _TEXT_MUT)
            screen.blit(num_s, num_s.get_rect(centerx=TBL_X + NUM_COL_W // 2, y=row_y + 18))

            # Name input field
            nr = _name_rect(i)
            is_focused = i == focused
            pygame.draw.rect(screen, _BG_CARD if is_focused else _BG_PANEL, nr, border_radius=4)
            pygame.draw.rect(screen, _CYAN if is_focused else _PANEL_BDR, nr, 1, border_radius=4)
            cursor = "|" if is_focused and int(t * 2) % 2 == 0 else ""
            nm_s = font_md.render(names[i] + cursor, True, _TEXT_PRI)
            screen.blit(nm_s, (nr.x + 6, nr.y + 6))

            # Type selector: [<]  TypeLabel  [>]
            pv = _type_prev_rect(i)
            nx = _type_next_rect(i)
            type_label_x = pv.right + 4
            type_label_w = nx.left - pv.right - 8

            for btn_r, lbl in [(pv, "<"), (nx, ">")]:
                hov = btn_r.collidepoint(mouse)
                pygame.draw.rect(
                    screen,
                    _blend(_BG_PANEL, _TEXT_PRI, 0.15) if hov else _BG_PANEL,
                    btn_r,
                    border_radius=4,
                )
                pygame.draw.rect(screen, _PANEL_BDR, btn_r, 1, border_radius=4)
                ls = font_md.render(lbl, True, _TEXT_PRI)
                screen.blit(ls, ls.get_rect(center=btn_r.center))

            type_str = ai_types[i]
            type_col = _EMERALD if type_str == "Human" else _GOLD
            ts = font_md.render(type_str, True, type_col)
            screen.blit(ts, ts.get_rect(center=(type_label_x + type_label_w // 2, pv.centery)))

        # Divider before buttons
        div_y = ROWS_Y + 6 * ROW_H + 10
        pygame.draw.line(screen, _DIVIDER, (80, div_y), (_W - 80, div_y), 1)

        # Start / Quit buttons
        for r, lbl, col, bdr_col in [
            (start_rect, "START GAME", _EMERALD_D, _EMERALD),
            (quit_rect, "QUIT", _BG_PANEL, _DANGER),
        ]:
            hov = r.collidepoint(mouse)
            pygame.draw.rect(
                screen, _blend(col, _TEXT_PRI, 0.15) if hov else col, r, border_radius=8
            )
            pygame.draw.rect(screen, bdr_col, r, 1, border_radius=8)
            ls = font_hdr.render(lbl, True, _TEXT_PRI)
            screen.blit(ls, ls.get_rect(center=r.center))

        # Hint
        hint = font_sm.render(
            "Click a name to edit  ·  < > to change type  ·  ESC to quit", True, _TEXT_MUT
        )
        screen.blit(hint, hint.get_rect(centerx=_W // 2, y=BTN_Y + 56))

        # --- Events ---
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif focused >= 0:
                    if event.key == pygame.K_BACKSPACE:
                        names[focused] = names[focused][:-1]
                    elif event.key in (pygame.K_RETURN, pygame.K_TAB):
                        focused = (focused + 1) % n
                    elif event.unicode.isprintable() and len(names[focused]) < 18:
                        names[focused] += event.unicode

            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                pos = event.pos

                # Player count buttons
                for n_val in range(2, 7):
                    if _count_rect(n_val).collidepoint(pos):
                        n = n_val
                        focused = -1
                        break

                # Name fields — clicking sets focus; clicking elsewhere clears it
                new_focus = -1
                for i in range(n):
                    if _name_rect(i).collidepoint(pos):
                        new_focus = i
                        break
                focused = new_focus

                # Type < / > buttons
                for i in range(n):
                    if _type_prev_rect(i).collidepoint(pos):
                        idx = _SETUP_AI_TYPES.index(ai_types[i])
                        ai_types[i] = _SETUP_AI_TYPES[(idx - 1) % len(_SETUP_AI_TYPES)]
                    elif _type_next_rect(i).collidepoint(pos):
                        idx = _SETUP_AI_TYPES.index(ai_types[i])
                        ai_types[i] = _SETUP_AI_TYPES[(idx + 1) % len(_SETUP_AI_TYPES)]

                # Start / Quit
                if start_rect.collidepoint(pos):
                    final_names = [nm.strip() or _SETUP_NAMES[i] for i, nm in enumerate(names[:n])]
                    type_map = {final_names[i]: ai_types[i] for i in range(n)}
                    result = (final_names, type_map)
                    running = False
                elif quit_rect.collidepoint(pos):
                    running = False

        pygame.display.flip()
        clock.tick(60)

    return result


# ---------------------------------------------------------------------------
# Module-level entry point for the --ui loader
# ---------------------------------------------------------------------------


def launch(controller: GameController, *, show_all: bool = False) -> None:
    """Run the Tactical Dashboard UI. Blocks until the game ends or window is closed."""
    TacticalUI(controller, show_all=show_all).run()
