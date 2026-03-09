"""
Pygame desktop UI for Twenty-Five.

Run with: python -m twentyfive --gui [--1v3 NAME] [--seeall]

Requires pygame-ce:  pip install -e ".[gui]"

Layout (900 × 650 window)
──────────────────────────────────────────
  Header  (title + round / trick info)        50 px
  Trump   (trump suit + face-up card)          40 px
  Scores  (all players, scores, tags)          45 px
  Trick   (current + completed tricks)        130 px
  Opps    (opponent card backs, or faces)      90 px
  Hand    (current player's cards)            175 px
  Status  (instruction / AI status text)       50 px
  Buttons (action buttons)                     70 px
──────────────────────────────────────────
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

import pygame

from twentyfive.cards.card import Card, Suit, is_trump
from twentyfive.game.rules import card_global_rank, trick_winner
from twentyfive.game.state import (
    ConfirmRoundEnd,
    GameState,
    Move,
    PassRob,
    Phase,
    PlayCard,
    Rob,
)

if TYPE_CHECKING:
    from twentyfive.ui.controller import GameController

# ---------------------------------------------------------------------------
# Window dimensions & region boundaries
# ---------------------------------------------------------------------------

_W, _H = 900, 650

_HDR_Y, _HDR_H = 0, 50
_TRUMP_Y, _TRUMP_H = 50, 40
_SCORE_Y, _SCORE_H = 90, 45
_TRICK_Y, _TRICK_H = 135, 130
_OPP_Y, _OPP_H = 265, 90
_HAND_Y, _HAND_H = 355, 175
_STATUS_Y, _STATUS_H = 530, 50
_BTN_Y, _BTN_H = 580, 70

# ---------------------------------------------------------------------------
# Card sizes
# ---------------------------------------------------------------------------

_CARD_W, _CARD_H = 74, 104        # human hand (large)
_CARD_SW, _CARD_SH = 38, 52       # opponent / trick (small)
_CARD_GAP = 12
_CORNER = 8

# ---------------------------------------------------------------------------
# Colours
# ---------------------------------------------------------------------------

_C_TABLE  = (32, 96, 48)          # green felt
_C_HDR    = (20, 60, 30)          # darker header strip
_C_STRIP  = (25, 80, 40)          # section background strips
_C_CARD   = (255, 252, 240)       # cream card face
_C_BACK   = (28, 55, 155)         # dark blue card back
_C_TEXT   = (240, 240, 230)       # general light text
_C_DARK   = (30, 30, 30)          # text on light backgrounds
_C_TRUMP  = (255, 220, 50)        # gold trump border
_C_SELECT = (30, 210, 255)        # cyan selection highlight
_C_HOVER  = (200, 200, 200)       # grey hover border
_C_STATUS = (18, 55, 28)          # status bar background
_C_BTN    = (45, 95, 55)          # button normal
_C_BTN_HV = (65, 130, 75)         # button hover
_C_BTN_DIS= (35, 60, 40)          # button disabled
_C_BTN_TX = (230, 230, 220)       # button text

_SUIT_COL = {
    Suit.HEARTS:   (210, 30, 30),
    Suit.DIAMONDS: (205, 95, 0),
    Suit.CLUBS:    (20, 80, 20),
    Suit.SPADES:   (25, 25, 130),
}

# Custom pygame event fired by the AI worker thread
_AI_DONE = pygame.USEREVENT + 1


# ---------------------------------------------------------------------------
# Button helper
# ---------------------------------------------------------------------------

class _Button:
    def __init__(self, rect: pygame.Rect, label: str, action: str, enabled: bool = True) -> None:
        self.rect = rect
        self.label = label
        self.action = action
        self.enabled = enabled

    def draw(self, surf: pygame.Surface, font: pygame.font.Font, mouse: tuple[int, int]) -> None:
        if not self.enabled:
            color = _C_BTN_DIS
        elif self.rect.collidepoint(mouse):
            color = _C_BTN_HV
        else:
            color = _C_BTN
        pygame.draw.rect(surf, color, self.rect, border_radius=6)
        pygame.draw.rect(surf, _C_BTN_TX, self.rect, 1, border_radius=6)
        txt = font.render(self.label, True, _C_BTN_TX if self.enabled else (120, 120, 110))
        surf.blit(txt, txt.get_rect(center=self.rect.center))

    def clicked(self, pos: tuple[int, int]) -> bool:
        return self.enabled and self.rect.collidepoint(pos)


# ---------------------------------------------------------------------------
# PygameUI
# ---------------------------------------------------------------------------

class PygameUI:
    """Pygame desktop UI for Twenty-Five."""

    def __init__(self, controller: GameController, *, show_all: bool = False) -> None:
        self._ctrl = controller
        self._show_all = show_all

        # Interactive state
        self._selected: Card | None = None     # card selected for trick play
        self._rob_choosing = False             # chose to rob; now selecting discard
        self._status = ""
        self._ai_thinking = False
        self._buttons: list[_Button] = []

    def run(self) -> None:
        pygame.init()
        screen = pygame.display.set_mode((_W, _H))
        pygame.display.set_caption("Twenty-Five")

        font_lg = pygame.font.SysFont("Arial", 21, bold=True)
        font_md = pygame.font.SysFont("Arial", 16)
        font_sm = pygame.font.SysFont("Arial", 13)

        self._screen = screen
        self._font_lg = font_lg
        self._font_md = font_md
        self._font_sm = font_sm

        clock = pygame.time.Clock()
        running = True

        while running:
            mouse = pygame.mouse.get_pos()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    running = False
                elif event.type == _AI_DONE:
                    self._ai_thinking = False
                    self._on_ai_done(event.dict["actor"], event.dict["move"])
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self._handle_click(event.pos)

            if self._ctrl.is_game_over:
                self._draw_game_over(mouse)
            else:
                if not self._ai_thinking and self._ctrl.is_ai_turn():
                    self._start_ai_move()
                self._draw(mouse)

            pygame.display.flip()
            clock.tick(60)

        pygame.quit()

    # -----------------------------------------------------------------------
    # AI threading
    # -----------------------------------------------------------------------

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
        trump = state.trump_suit
        if isinstance(move, PlayCard):
            self._status = f"{actor} played {move.card}"
        elif isinstance(move, Rob):
            taken = state.rob_this_round[1] if state.rob_this_round else "a card"
            self._status = f"{actor} robs — takes {taken}"
        elif isinstance(move, PassRob):
            self._status = f"{actor} passes"
        else:
            self._status = ""
        _ = trump  # used implicitly via card __str__

    # -----------------------------------------------------------------------
    # Click handling
    # -----------------------------------------------------------------------

    def _handle_click(self, pos: tuple[int, int]) -> None:
        if self._ai_thinking:
            return
        if self._ctrl.is_game_over:
            return

        # Buttons take priority
        for btn in self._buttons:
            if btn.clicked(pos):
                self._handle_action(btn.action)
                return

        # Card clicks in the hand area
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
                    except ValueError:
                        self._status = "Invalid move — please try again"
            case "auto":
                legal = [m.card for m in state.legal_moves if isinstance(m, PlayCard)]
                if legal and state.trump_suit is not None:
                    trump_suit = state.trump_suit
                    worst = max(legal, key=lambda c: card_global_rank(c, trump_suit))
                    self._ctrl.apply_move(PlayCard(worst))
                    self._selected = None
                    self._status = ""
            case "rob":
                self._rob_choosing = True
                self._status = "Click a card from your hand to discard"
            case "passrob":
                self._ctrl.apply_move(PassRob())
                self._rob_choosing = False
                self._status = ""
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
            except ValueError:
                self._status = "Cannot discard that card"
            return

        if state.phase == Phase.TRICK:
            if card not in legal_cards:
                self._status = "That card is not legal to play"
                return
            if self._selected == card:
                # Second click = instant play
                self._ctrl.apply_move(PlayCard(card))
                self._selected = None
                self._status = ""
            else:
                self._selected = card
                self._status = f"Selected {card} — click Play or click again to confirm"

    def _card_at_hand(self, pos: tuple[int, int], state: GameState) -> Card | None:
        cards = list(state.current_player.hand)
        for card, rect in zip(cards, self._hand_card_rects(len(cards))):
            if rect.collidepoint(pos):
                return card
        return None

    # -----------------------------------------------------------------------
    # Button construction
    # -----------------------------------------------------------------------

    def _build_buttons(self, state: GameState) -> list[_Button]:
        buttons: list[_Button] = []
        bw, bh = 130, 40
        y = _BTN_Y + (_BTN_H - bh) // 2
        gap = 12

        quit_btn = _Button(pygame.Rect(_W - bw - 20, y, bw, bh), "Quit", "quit")

        if state.phase == Phase.TRICK and not self._ctrl.is_ai_turn():
            play_btn = _Button(
                pygame.Rect(20, y, bw, bh), "Play Card", "play",
                enabled=self._selected is not None,
            )
            auto_btn = _Button(pygame.Rect(20 + bw + gap, y, bw, bh), "Auto-play", "auto")
            buttons = [play_btn, auto_btn, quit_btn]

        elif state.phase == Phase.ROB and not self._ctrl.is_ai_turn():
            has_rob = any(isinstance(m, Rob) for m in state.legal_moves)
            if self._rob_choosing:
                cancel_btn = _Button(pygame.Rect(20, y, bw, bh), "Cancel Rob", "cancelrob")
                buttons = [cancel_btn, quit_btn]
            else:
                rob_btn  = _Button(pygame.Rect(20, y, bw, bh), "Rob", "rob",
                                   enabled=has_rob)
                pass_btn = _Button(pygame.Rect(20 + bw + gap, y, bw, bh), "Pass", "passrob")
                buttons = [rob_btn, pass_btn, quit_btn]

        elif state.phase == Phase.ROUND_END:
            cont_btn = _Button(pygame.Rect(20, y, bw, bh), "Next Round", "continue")
            buttons = [cont_btn, quit_btn]

        else:
            buttons = [quit_btn]

        return buttons

    # -----------------------------------------------------------------------
    # Main draw
    # -----------------------------------------------------------------------

    def _draw(self, mouse: tuple[int, int]) -> None:
        state = self._ctrl.state
        self._buttons = self._build_buttons(state)

        self._screen.fill(_C_TABLE)
        self._draw_header(state)
        self._draw_trump(state)
        self._draw_scores(state)
        self._draw_trick_area(state)
        self._draw_opponent_hands(state)
        self._draw_hand(state, mouse)
        self._draw_status()
        self._draw_buttons(mouse)

    # -----------------------------------------------------------------------
    # Section renderers
    # -----------------------------------------------------------------------

    def _draw_header(self, state: GameState) -> None:
        pygame.draw.rect(self._screen, _C_HDR, (0, _HDR_Y, _W, _HDR_H))
        if state.phase == Phase.ROUND_END:
            trick_str = "Round complete"
        else:
            trick_str = f"Trick {state.trick_number}/5"
        title = self._font_lg.render("TWENTY-FIVE", True, _C_TEXT)
        info = self._font_md.render(
            f"Round {state.round_number}  |  {trick_str}  |  Game {state.game_id[:8]}",
            True, (180, 200, 180),
        )
        self._screen.blit(title, (20, _HDR_Y + 8))
        self._screen.blit(info, (_W - info.get_width() - 20, _HDR_Y + 15))

    def _draw_trump(self, state: GameState) -> None:
        pygame.draw.rect(self._screen, _C_STRIP, (0, _TRUMP_Y, _W, _TRUMP_H))
        assert state.trump_suit is not None
        trump_str = f"Trump: {state.trump_suit.symbol} {state.trump_suit}"
        if state.face_up_card and state.phase not in (Phase.GAME_OVER,):
            trump_str += f"   |   Face-up: {state.face_up_card}  (available to rob)"
        surf = self._font_md.render(trump_str, True, _C_TRUMP)
        self._screen.blit(surf, (20, _TRUMP_Y + (_TRUMP_H - surf.get_height()) // 2))

    def _draw_scores(self, state: GameState) -> None:
        pygame.draw.rect(self._screen, _C_STRIP, (0, _SCORE_Y, _W, _SCORE_H))
        max_score = max(p.score for p in state.players)
        x = 20
        for i, p in enumerate(state.players):
            parts: list[str] = [p.name]
            if i == state.dealer_index:
                parts.append("[D]")
            if max_score > 0 and p.score == max_score:
                parts.append("[★]")
            if i == state.current_player_index:
                parts.append("◀")
            label = " ".join(parts) + f"  {p.score}pt"
            colour = _C_SELECT if i == state.current_player_index else _C_TEXT
            surf = self._font_md.render(label, True, colour)
            self._screen.blit(surf, (x, _SCORE_Y + (_SCORE_H - surf.get_height()) // 2))
            x += surf.get_width() + 30

    def _draw_trick_area(self, state: GameState) -> None:
        assert state.trump_suit is not None
        trump = state.trump_suit
        y = _TRICK_Y + 6

        # Completed tricks summary (text only to save space)
        if state.completed_tricks:
            for t_idx, trick in enumerate(state.completed_tricks):
                led_suit = trick[0].card.suit
                winner = trick_winner(list(trick), led_suit, trump)
                cards_str = "  ".join(str(tp.card) for tp in trick)
                line = f"Trick {t_idx + 1}: {cards_str}  → {winner.player_name}"
                surf = self._font_sm.render(line, True, (180, 200, 180))
                self._screen.blit(surf, (20, y))
                y += surf.get_height() + 2

        # Current trick — draw small cards
        if state.current_trick:
            cy = _TRICK_Y + _TRICK_H - _CARD_SH - 10
            label = self._font_sm.render("Current trick:", True, _C_TEXT)
            self._screen.blit(label, (20, cy - label.get_height() - 2))

            led_suit = state.current_trick[0].card.suit
            winner_name: str | None = None
            if state.current_trick:
                w = trick_winner(list(state.current_trick), led_suit, trump)
                winner_name = w.player_name

            cx = 20
            for tp in state.current_trick:
                rect = pygame.Rect(cx, cy, _CARD_SW, _CARD_SH)
                winning = tp.player_name == winner_name
                self._draw_card_small(rect, tp.card, trump, winning=winning)
                name_surf = self._font_sm.render(tp.player_name, True, _C_TEXT)
                self._screen.blit(name_surf, (cx, cy + _CARD_SH + 2))
                cx += _CARD_SW + 50

    def _draw_opponent_hands(self, state: GameState) -> None:
        """Draw opponent hands — face-down backs (or face-up in show_all mode)."""
        assert state.trump_suit is not None
        trump = state.trump_suit

        my_index = state.current_player_index
        opponents = [p for i, p in enumerate(state.players) if i != my_index]
        if not opponents:
            return

        y = _OPP_Y + 4
        x_start = 20

        for opp in opponents:
            name_surf = self._font_sm.render(
                f"{opp.name} ({opp.hand_size})", True, (180, 200, 180)
            )
            self._screen.blit(name_surf, (x_start, y))
            cx = x_start
            card_y = y + name_surf.get_height() + 2

            if self._show_all:
                for card in opp.hand:
                    rect = pygame.Rect(cx, card_y, _CARD_SW, _CARD_SH)
                    self._draw_card_small(rect, card, trump)
                    cx += _CARD_SW + 4
            else:
                for _ in range(opp.hand_size):
                    rect = pygame.Rect(cx, card_y, _CARD_SW, _CARD_SH)
                    self._draw_card_back_small(rect)
                    cx += _CARD_SW + 4

            x_start += max(cx - 20, 120) + 20

    def _draw_hand(self, state: GameState, mouse: tuple[int, int]) -> None:
        """Draw the current player's hand — large, clickable cards."""
        assert state.trump_suit is not None
        trump = state.trump_suit
        current = state.current_player

        label_text = f"{current.name}'s hand"
        if state.phase == Phase.TRICK and not self._ctrl.is_ai_turn():
            label_text += " — click a card to select, then Play"
        elif state.phase == Phase.ROB and self._rob_choosing:
            label_text += " — click a card to discard"
        label = self._font_md.render(label_text, True, _C_TEXT)
        self._screen.blit(label, (20, _HAND_Y + 6))

        cards = list(current.hand)
        legal_cards = {m.card for m in state.legal_moves if isinstance(m, PlayCard)}
        rects = self._hand_card_rects(len(cards))

        for card, rect in zip(cards, rects):
            hover = rect.collidepoint(mouse)
            is_legal = card in legal_cards
            is_selected = card == self._selected
            is_rob_target = state.phase == Phase.ROB and self._rob_choosing

            self._draw_card_large(
                rect, card, trump,
                selected=is_selected,
                legal=(is_legal or is_rob_target),
                hover=hover,
            )

    def _draw_status(self) -> None:
        pygame.draw.rect(self._screen, _C_STATUS, (0, _STATUS_Y, _W, _STATUS_H))
        if self._status:
            surf = self._font_md.render(self._status, True, _C_TEXT)
            self._screen.blit(surf, (20, _STATUS_Y + (_STATUS_H - surf.get_height()) // 2))

    def _draw_buttons(self, mouse: tuple[int, int]) -> None:
        pygame.draw.rect(self._screen, _C_HDR, (0, _BTN_Y, _W, _BTN_H))
        for btn in self._buttons:
            btn.draw(self._screen, self._font_md, mouse)

    def _draw_game_over(self, mouse: tuple[int, int]) -> None:
        self._screen.fill(_C_HDR)
        state = self._ctrl.state
        sorted_players = sorted(state.players, key=lambda p: p.score, reverse=True)

        title = self._font_lg.render("GAME OVER", True, _C_TRUMP)
        self._screen.blit(title, title.get_rect(centerx=_W // 2, y=80))

        winner = sorted_players[0]
        sub = self._font_md.render(
            f"Winner: {winner.name} with {winner.score} points!", True, _C_TEXT
        )
        self._screen.blit(sub, sub.get_rect(centerx=_W // 2, y=130))

        y = 200
        for p in sorted_players:
            line = self._font_md.render(f"  {p.name:<16} {p.score} pts", True, _C_TEXT)
            self._screen.blit(line, line.get_rect(centerx=_W // 2, y=y))
            y += 30

        hint = self._font_sm.render("Click anywhere or press ESC to quit", True, (150, 170, 150))
        self._screen.blit(hint, hint.get_rect(centerx=_W // 2, y=_H - 40))

    # -----------------------------------------------------------------------
    # Card drawing helpers
    # -----------------------------------------------------------------------

    def _draw_card_large(
        self,
        rect: pygame.Rect,
        card: Card,
        trump: Suit,
        *,
        selected: bool = False,
        legal: bool = True,
        hover: bool = False,
    ) -> None:
        pygame.draw.rect(self._screen, _C_CARD, rect, border_radius=_CORNER)

        # Border
        if selected:
            pygame.draw.rect(self._screen, _C_SELECT, rect, 3, border_radius=_CORNER)
        elif is_trump(card, trump):
            pygame.draw.rect(self._screen, _C_TRUMP, rect, 3, border_radius=_CORNER)
        elif hover and legal:
            pygame.draw.rect(self._screen, _C_HOVER, rect, 2, border_radius=_CORNER)
        else:
            pygame.draw.rect(self._screen, (160, 160, 150), rect, 1, border_radius=_CORNER)

        suit_col = _SUIT_COL[card.suit]

        # Rank top-left
        rank_surf = self._font_sm.render(card.rank.display, True, suit_col)
        self._screen.blit(rank_surf, (rect.x + 5, rect.y + 4))

        # Suit symbol centre
        sym_surf = self._font_lg.render(card.suit.symbol, True, suit_col)
        self._screen.blit(sym_surf, sym_surf.get_rect(center=rect.center))

        # Rank bottom-right (mirrored label — just repeat)
        rank_surf2 = self._font_sm.render(card.rank.display, True, suit_col)
        self._screen.blit(
            rank_surf2,
            (rect.right - rank_surf2.get_width() - 5, rect.bottom - rank_surf2.get_height() - 4),
        )

        # Dim illegal cards
        if not legal:
            dim = pygame.Surface(rect.size, pygame.SRCALPHA)
            dim.fill((0, 0, 0, 130))
            self._screen.blit(dim, rect.topleft)

    def _draw_card_small(
        self,
        rect: pygame.Rect,
        card: Card,
        trump: Suit,
        *,
        winning: bool = False,
    ) -> None:
        pygame.draw.rect(self._screen, _C_CARD, rect, border_radius=4)
        border_col = _C_TRUMP if is_trump(card, trump) else (160, 160, 150)
        if winning:
            border_col = _C_SELECT
        pygame.draw.rect(self._screen, border_col, rect, 2, border_radius=4)

        suit_col = _SUIT_COL[card.suit]
        label = f"{card.rank.display}{card.suit.symbol}"
        surf = self._font_sm.render(label, True, suit_col)
        self._screen.blit(surf, surf.get_rect(center=rect.center))

    def _draw_card_back_small(self, rect: pygame.Rect) -> None:
        pygame.draw.rect(self._screen, _C_BACK, rect, border_radius=4)
        inner = rect.inflate(-6, -6)
        pygame.draw.rect(self._screen, (50, 80, 180), inner, border_radius=2)

    # -----------------------------------------------------------------------
    # Geometry helpers
    # -----------------------------------------------------------------------

    def _hand_card_rects(self, n: int) -> list[pygame.Rect]:
        """Card rects for n cards in the hand area, centred horizontally."""
        total = n * _CARD_W + max(0, n - 1) * _CARD_GAP
        x0 = (_W - total) // 2
        y = _HAND_Y + 30
        return [
            pygame.Rect(x0 + i * (_CARD_W + _CARD_GAP), y, _CARD_W, _CARD_H)
            for i in range(n)
        ]


# ---------------------------------------------------------------------------
# Module-level entry point for the --ui loader
# ---------------------------------------------------------------------------


def launch(controller: GameController, *, show_all: bool = False) -> None:
    """Run the pygame UI. Blocks until the game ends or the user closes the window."""
    PygameUI(controller, show_all=show_all).run()
