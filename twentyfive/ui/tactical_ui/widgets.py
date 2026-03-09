"""
Drawing primitives, button widget, and game helper functions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from twentyfive.cards.card import Card, Suit, is_trump
from twentyfive.game.rules import (
    card_global_rank,
    get_renegeable_cards,
    trick_winner,
)
from twentyfive.game.state import (
    GameState,
    PlayCard,
    TrickPlay,
)

from .bg import _pulse
from .constants import (
    _BG_PANEL,
    _BRACKET_LEN,
    _BRACKET_T,
    _CARD_BACK,
    _CARD_FACE,
    _CORNER,
    _CYAN,
    _DANGER,
    _EMERALD,
    _EMERALD_D,
    _GOLD,
    _INDICATOR_SLOTS,
    _SUIT_COLOUR,
    _TAG_GAP,
    _TAG_H,
    _TAG_PAD,
    _TEXT_MUT,
    _TEXT_PRI,
)

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# Colour blend utility
# ---------------------------------------------------------------------------


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
# Corner-bracket border helper
# ---------------------------------------------------------------------------


def _draw_corner_border(
    surf: pygame.Surface,
    rect: pygame.Rect,
    colour: tuple[int, int, int],
) -> None:
    """Draw bracket-style corner marks around *rect* — no full perimeter line."""
    x, y = rect.x, rect.y
    r, b = rect.right, rect.bottom
    cl = _BRACKET_LEN
    t = _BRACKET_T
    for ox, oy, sx, sy in [
        (x, y, 1, 1),  # top-left
        (r, y, -1, 1),  # top-right
        (x, b, 1, -1),  # bottom-left
        (r, b, -1, -1),  # bottom-right
    ]:
        pygame.draw.line(surf, colour, (ox, oy), (ox + sx * cl, oy), t)
        pygame.draw.line(surf, colour, (ox, oy), (ox, oy + sy * cl), t)


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
