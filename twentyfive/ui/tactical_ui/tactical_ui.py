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

import threading
from typing import TYPE_CHECKING

import pygame

from twentyfive.cards.card import Card, Rank, Suit
from twentyfive.game.rules import trick_winner
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

from .animation import FloatingCard, _CardAnim, _bezier, _ease_out
from .bg import ProceduralBackground, _pulse
from .constants import (
    _ARENA_CH,
    _ARENA_CONFIG,
    _ARENA_CW,
    _ARENA_H,
    _ARENA_Y,
    _BG_CARD,
    _BG_DARK,
    _BG_PANEL,
    _CARD_GAP,
    _CORNER,
    _CTR_W,
    _CTR_X,
    _CYAN,
    _DANGER,
    _DIVIDER,
    _EMERALD,
    _EMERALD_D,
    _GAP,
    _GOLD,
    _GOLD_D,
    _H,
    _HAND_CH,
    _HAND_CW,
    _HAND_H,
    _HAND_Y,
    _HDR_CARD_H,
    _HDR_CARD_W,
    _HDR_H,
    _PANEL_BDR,
    _SIDE_W,
    _SMALL_CH,
    _SMALL_CW,
    _SUIT_COLOUR,
    _TEXT_MUT,
    _TEXT_PRI,
    _W,
)
from .setup import setup_game as setup_game  # re-export for __init__.py
from .widgets import (
    _Button,
    _auto_play_card,
    _blend,
    _compute_tags,
    _draw_card_back,
    _draw_card_face,
    _draw_card_indicators,
    _draw_corner_border,
    _draw_rank_badge,
)

if TYPE_CHECKING:
    from twentyfive.ui.controller import GameController

# Custom pygame event posted by the AI worker thread
_AI_DONE = pygame.USEREVENT + 1


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
        self._trick_pause_until: float = 0.0  # time when trick pause expires (cards clear)
        self._trick_overlay_from: float = 0.0  # time when trick result overlay appears
        self._trick_pause_pending: bool = False  # defer until anims land
        self._frozen_trick: "tuple[TrickPlay, ...] | None" = None  # displayed during anim + pause
        self._round_pause_until: float = 0.0  # time when round-end overlay expires
        self._round_pause_pending: bool = False  # defer round overlay until anims land
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
        # Floating card physics (one per hand slot)
        self._floating: list[FloatingCard] = [FloatingCard(i) for i in range(5)]
        # In-flight card animations (bezier arcs from hand to arena)
        self._anims: list[_CardAnim] = []
        # Procedural background (initialised in run() after pygame.init())
        self._bg: ProceduralBackground | None = None
        # Time when the game-over board-summary starts (-1 = not yet; -2 = waiting for anims).
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

        # Procedural background — baked after pygame.init()
        self._bg = ProceduralBackground(_W, _H)

        # Build scanline overlay once (1px black lines every 3px, alpha=20)
        self._scanlines = pygame.Surface((_W, _H), pygame.SRCALPHA)
        self._scanlines.fill((0, 0, 0, 0))
        for _sl_y in range(0, _H, 3):
            pygame.draw.line(self._scanlines, (0, 0, 0, 20), (0, _sl_y), (_W, _sl_y))

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
                        self._trick_overlay_from = 0.0
                        self._trick_pause_pending = False
                        self._frozen_trick = None
                        self._round_pause_until = 0.0
                        self._round_pause_pending = False
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
                        self._trick_overlay_from = 0.0
                        self._trick_pause_pending = False
                        self._frozen_trick = None
                    elif round_pausing:
                        self._round_pause_until = 0.0
                        self._round_pause_pending = False
                    else:
                        self._handle_click(event.pos)

            if self._ctrl.is_game_over and not self._ai_thinking:
                # First detection: ensure the last trick is frozen for the summary board,
                # then defer the timer until any flying card has landed (-2 = pending).
                # Guard on not self._ai_thinking: the worker thread sets is_game_over before
                # posting _AI_DONE, so without this guard we'd detect game-over before the
                # animation is launched (self._anims still empty) and skip the -2 sentinel.
                if self._game_over_show_after == -1.0:
                    go_state = self._ctrl.state
                    if self._frozen_trick is None and go_state.completed_tricks:
                        self._frozen_trick = go_state.completed_tricks[-1]
                    self._game_over_show_after = -2.0 if self._anims else self._t + 5.0
                    if self._game_over_show_after > 0:
                        self._round_pause_until = self._game_over_show_after
                # Pending: animations just cleared — start the 5 s board summary now.
                if self._game_over_show_after == -2.0 and not self._anims:
                    self._game_over_show_after = self._t + 5.0
                    self._round_pause_until = self._game_over_show_after

                if self._game_over_show_after < 0:
                    # Still animating — draw the board normally (card in flight).
                    state = self._ctrl.state
                    self._buttons = self._build_buttons(state)
                    self._draw(state, mouse, round_pausing=False)
                elif self._t < self._game_over_show_after:
                    # Final-round summary pause — draw the board with round-end overlay.
                    state = self._ctrl.state
                    round_pausing = True
                    self._buttons = self._build_buttons(state)
                    self._draw(state, mouse, round_pausing=round_pausing)
                else:
                    self._draw_game_over()
            else:
                state = self._ctrl.state

                # Detect trick completion (any trick, any phase)
                curr_count = len(state.completed_tricks)
                if curr_count < self._last_trick_count:
                    self._last_trick_count = 0  # new round reset
                    self._frozen_trick = None
                elif curr_count > self._last_trick_count:
                    self._last_trick_count = curr_count
                    # Always freeze the completed trick so the arena stays populated
                    self._frozen_trick = (
                        state.completed_tricks[-1] if state.completed_tricks else None
                    )
                    # Show trick-complete overlay for every trick (including the last)
                    if self._anims:
                        self._trick_pause_pending = True  # defer until flight lands
                    else:
                        self._trick_overlay_from = self._t + 0.4
                        self._trick_pause_until = self._trick_overlay_from + 2.5
                else:
                    self._last_trick_count = curr_count

                # Fire deferred trick pause once all animations have landed
                if self._trick_pause_pending and not self._anims:
                    self._trick_pause_pending = False
                    self._trick_overlay_from = self._t + 0.4
                    self._trick_pause_until = self._trick_overlay_from + 2.5

                # Detect ROUND_END entry — mark round pause as pending
                if state.phase == Phase.ROUND_END and self._last_phase != Phase.ROUND_END:
                    self._round_pause_pending = True
                # Fire deferred round pause once animations AND trick overlay are both done
                if (
                    self._round_pause_pending
                    and not self._anims
                    and self._t >= self._trick_pause_until
                ):
                    self._round_pause_pending = False
                    self._round_pause_until = self._t + 4.0
                self._last_phase = state.phase

                trick_pausing = self._t < self._trick_pause_until
                round_pausing = self._t < self._round_pause_until
                pausing = trick_pausing or round_pausing
                # Auto-advance past ROUND_END once the overlay is dismissed or expires.
                # Must happen BEFORE the frozen-trick clear so we know if game ended.
                if (
                    not round_pausing
                    and not self._round_pause_pending
                    and not self._anims
                    and state.phase == Phase.ROUND_END
                    and not self._ctrl.is_game_over
                ):
                    try:
                        self._ctrl.apply_move(ConfirmRoundEnd())
                        self._ai_move_after = self._t + 0.5
                    except ValueError:
                        pass
                # Clear frozen trick once all overlays and animations are done.
                # Keep it if the game just ended — the 5s summary board needs it.
                if (
                    not trick_pausing
                    and not round_pausing
                    and not self._anims
                    and not self._ctrl.is_game_over
                ):
                    self._frozen_trick = None
                if (
                    not pausing
                    and not self._ai_thinking
                    and not self._anims
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
            # Launch a bezier animation: card drops in from above the arena slot
            player_idx = next((i for i, p in enumerate(state.players) if p.name == actor), 0)
            target = self._arena_slot_centre(player_idx, len(state.players))
            start = (target[0], float(-_HAND_CH))
            self._launch_anim(move.card, player_idx, start, state)
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
                        card = self._selected
                        start = self._hand_slot_centre(card)
                        player_idx = next(
                            i
                            for i, p in enumerate(state.players)
                            if p.name == state.current_player.name
                        )
                        self._ctrl.apply_move(PlayCard(card))
                        self._selected = None
                        self._status = ""
                        self._ai_move_after = self._t + 1.0
                        if start is not None:
                            self._launch_anim(card, player_idx, start, state)
                    except ValueError:
                        self._status = "Invalid move — try again"
            case "auto":
                auto_card = _auto_play_card(state)
                if auto_card is not None:
                    card = auto_card
                    start = self._hand_slot_centre(card)
                    player_idx = next(
                        i
                        for i, p in enumerate(state.players)
                        if p.name == state.current_player.name
                    )
                    self._ctrl.apply_move(PlayCard(card))
                    self._selected = None
                    self._status = ""
                    self._ai_move_after = self._t + 1.0
                    if start is not None:
                        self._launch_anim(card, player_idx, start, state)
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
                start = self._hand_slot_centre(card)
                player_idx = next(
                    i for i, p in enumerate(state.players) if p.name == state.current_player.name
                )
                self._ctrl.apply_move(PlayCard(card))
                self._selected = None
                self._status = ""
                if start is not None:
                    self._launch_anim(card, player_idx, start, state)
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
        if self._bg is not None:
            self._bg.draw(self._screen, self._t)
        else:
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
        if self._trick_overlay_from < self._t < self._trick_pause_until:
            self._draw_trick_pause(state)
        if round_pausing:
            self._draw_round_end_pause(state)
        # Flying card animations (bezier arcs from hand to arena)
        self._draw_anims(state)
        # Post-processing: scanline overlay (retro-arcade texture)
        self._screen.blit(self._scanlines, (0, 0))

    # ------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------

    def _draw_header(self, state: GameState) -> None:
        pygame.draw.rect(
            self._screen,
            _BG_PANEL,
            (_GAP, _GAP, _W - 2 * _GAP, _HDR_H - _GAP),
            border_radius=8,
        )

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
        # Inset all edges by _GAP so background shows through on every side
        panel = pygame.Rect(_GAP, _HDR_H + _GAP, _SIDE_W - 2 * _GAP, _H - _HDR_H - 2 * _GAP)
        pygame.draw.rect(self._screen, _BG_PANEL, panel, border_radius=_CORNER)

        title = self._font_sm.render("SCORECARD", True, _TEXT_MUT)
        self._screen.blit(title, (_GAP + 12, _HDR_H + 10))

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

            row_rect = pygame.Rect(_GAP + 6, y, _SIDE_W - 2 * _GAP - 12, row_h - 6)

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
            pygame.draw.circle(self._screen, dot_col, (_GAP + 18, y + 14), 5)

            # Name + [D] dealer badge
            name_parts = [player.name]
            if is_dealer:
                name_parts.append("[D]")
            name_str = "  ".join(name_parts)
            name_surf = self._font_md.render(name_str, True, _EMERALD if is_active else _TEXT_PRI)
            self._screen.blit(name_surf, (_GAP + 28, y + 6))

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
            self._screen.blit(sc_surf, (_GAP + 28, y + 28))

            bar_rect = pygame.Rect(_GAP + 28, y + 44, _SIDE_W - _GAP - 44, 7)
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
            pip_x = _GAP + 28
            pip_y = y + 58
            for _ in range(player.tricks_won_this_round):
                pygame.draw.rect(
                    self._screen, _EMERALD, pygame.Rect(pip_x, pip_y, 12, 12), border_radius=3
                )
                pip_x += 16
            if player.tricks_won_this_round == 0:
                nd = self._font_xs.render("no tricks", True, _TEXT_MUT)
                self._screen.blit(nd, (_GAP + 28, pip_y))

            y += row_h

    # ------------------------------------------------------------------
    # Trick zone sidebar (right) — shows completed trick history
    # ------------------------------------------------------------------

    def _draw_trick_zone(self, state: GameState) -> None:
        assert state.trump_suit is not None
        trump = state.trump_suit

        # Inset all edges by _GAP so background shows through on every side
        panel = pygame.Rect(
            _W - _SIDE_W + _GAP, _HDR_H + _GAP, _SIDE_W - 2 * _GAP, _H - _HDR_H - 2 * _GAP
        )
        pygame.draw.rect(self._screen, _BG_PANEL, panel, border_radius=_CORNER)

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

        # Semi-transparent overlay inset by _GAP on all sides (background shows in the gaps)
        arena_rect = pygame.Rect(
            _CTR_X + _GAP, _ARENA_Y + _GAP, _CTR_W - 2 * _GAP, _ARENA_H - 2 * _GAP
        )
        _arena_overlay = pygame.Surface(arena_rect.size, pygame.SRCALPHA)
        pygame.draw.rect(
            _arena_overlay, (10, 10, 20, 160), _arena_overlay.get_rect(), border_radius=_CORNER
        )
        self._screen.blit(_arena_overlay, arena_rect.topleft)

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

        # Use frozen trick (last completed) while animating or paused; live trick otherwise
        display_trick = (
            self._frozen_trick if self._frozen_trick is not None else state.current_trick
        )
        played: dict[str, TrickPlay] = {tp.player_name: tp for tp in display_trick}
        led_name = display_trick[0].player_name if display_trick else None

        # Cards still in-flight — suppress from arena slot until the animation lands
        animating_cards: set[Card] = {a.card for a in self._anims}

        # Determine current winner from the displayed trick
        winner_name: str | None = None
        if display_trick:
            led_suit = display_trick[0].card.suit
            w = trick_winner(list(display_trick), led_suit, trump)
            winner_name = w.player_name

        for idx in range(n):
            player = state.players[idx]
            cx, cy = slot_centres[idx]
            slot_rect = pygame.Rect(cx - _ARENA_CW // 2, cy - _ARENA_CH // 2, _ARENA_CW, _ARENA_CH)

            tp = played.get(player.name)
            is_led = tp is not None and player.name == led_name
            is_winning = tp is not None and player.name == winner_name

            # Suppress card while its bezier flight is still in progress
            in_flight = tp is not None and tp.card in animating_cards

            if tp and not in_flight:
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
                # [WINNING] badge above card
                if is_winning:
                    p_factor = _pulse(self._t, 2.0)
                    wc = _blend(_EMERALD_D, _EMERALD, p_factor)
                    wt = self._font_xs.render("WINNING", True, wc)
                    self._screen.blit(
                        wt, wt.get_rect(centerx=cx, y=slot_rect.top - wt.get_height() - 2)
                    )
            else:
                # Empty slot: dark filled background
                pygame.draw.rect(self._screen, _BG_CARD, slot_rect, border_radius=6)

            # Corner bracket border — inflated 5 px outward so there's a gap around the card.
            # Gold when this player led, muted otherwise.
            bracket_col = _GOLD if is_led else _PANEL_BDR
            bracket_rect = slot_rect.inflate(10, 10)  # 5 px gap on each side
            _draw_corner_border(self._screen, bracket_rect, bracket_col)

            # Player name in the gap at the bottom edge of the bracket border
            name_lbl = self._font_xs.render(player.name.upper(), True, _TEXT_MUT)
            # Erase a strip of the arena background behind the name to create the gap
            gap_w = name_lbl.get_width() + 8
            gap_rect = pygame.Rect(
                cx - gap_w // 2,
                bracket_rect.bottom - name_lbl.get_height() // 2,
                gap_w,
                name_lbl.get_height(),
            )
            # Semi-transparent gap behind the player-name label (lets background bleed through)
            _gap_surf = pygame.Surface(gap_rect.size, pygame.SRCALPHA)
            _gap_surf.fill((10, 10, 20, 160))
            self._screen.blit(_gap_surf, gap_rect.topleft)
            self._screen.blit(name_lbl, name_lbl.get_rect(centerx=cx, centery=bracket_rect.bottom))

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

        # Panel background — semi-transparent, inset by _GAP on all sides
        hand_rect = pygame.Rect(
            _CTR_X + _GAP, _HAND_Y + _GAP, _CTR_W - 2 * _GAP, _HAND_H - 2 * _GAP
        )
        _hand_overlay = pygame.Surface(hand_rect.size, pygame.SRCALPHA)
        pygame.draw.rect(
            _hand_overlay, (30, 30, 48, 210), _hand_overlay.get_rect(), border_radius=_CORNER
        )
        self._screen.blit(_hand_overlay, hand_rect.topleft)

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

            # Update floating card physics
            fc = self._floating[slot_idx]
            fc.update(pygame.time.get_ticks(), mouse, rect, hover and (is_legal or is_rob_target))

            # Bob offset applies only when it's the human's turn (replaces static hover lift)
            if is_my_turn:
                bob_offset = fc.bob_y
                if is_selected:
                    bob_offset -= 20
            else:
                bob_offset = 0.0

            # Render card to a temp surface, then rotozoom for scale+rotation
            tmp = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
            tmp_rect = tmp.get_rect()
            _draw_card_face(
                tmp,
                tmp_rect,
                card,
                trump,
                self._font_md,
                self._font_sym_hand,
                selected=is_selected,
                hover=hover,
                legal=(is_legal or is_rob_target),
            )
            if state.phase not in (Phase.ROUND_END,):
                _draw_rank_badge(tmp, tmp_rect, card, trump, self._font_xs)

            rotated = pygame.transform.rotozoom(tmp, fc.rotation, fc.scale)
            draw_rect = rotated.get_rect(center=(rect.centerx, rect.centery + int(bob_offset)))
            self._screen.blit(rotated, draw_rect)

            # Key-number hint below card
            lbl = self._font_xs.render(key_hint, True, _TEXT_MUT)
            self._screen.blit(lbl, lbl.get_rect(centerx=draw_rect.centerx, y=draw_rect.bottom + 4))

            # Strategic indicators (bottom-left corner of card, on the screen surface)
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
    # Card flight animations
    # ------------------------------------------------------------------

    def _draw_anims(self, state: GameState) -> None:
        """Draw in-flight bezier card animations and prune completed ones."""
        if not self._anims or state.trump_suit is None:
            return
        now = pygame.time.get_ticks()
        still_flying: list[_CardAnim] = []
        for anim in self._anims:
            elapsed = now - anim.start_ms
            raw_t = min(1.0, elapsed / anim.duration_ms)
            t = _ease_out(raw_t)
            cx, cy = _bezier(anim.p0, anim.p1, anim.p2, t)
            trump = anim.trump if anim.trump is not None else state.trump_suit
            # Scale shrinks slightly as card approaches target
            scale = 1.0 - 0.2 * t
            tmp = pygame.Surface((_ARENA_CW, _ARENA_CH), pygame.SRCALPHA)
            _draw_card_face(
                tmp,
                tmp.get_rect(),
                anim.card,
                trump,
                self._font_sm,
                self._font_lg,
            )
            if scale != 1.0:
                scaled = pygame.transform.smoothscale(
                    tmp, (int(_ARENA_CW * scale), int(_ARENA_CH * scale))
                )
            else:
                scaled = tmp
            self._screen.blit(scaled, scaled.get_rect(center=(int(cx), int(cy))))
            if raw_t < 1.0:
                still_flying.append(anim)
        self._anims = still_flying

    # ------------------------------------------------------------------
    # Game over overlay
    # ------------------------------------------------------------------

    def _draw_game_over(self) -> None:
        if self._bg is not None:
            self._bg.draw(self._screen, self._t)
        else:
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
        self._screen.blit(self._scanlines, (0, 0))

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

    def _hand_slot_centre(self, card: Card) -> tuple[float, float] | None:
        """Return the screen centre of the hand slot containing card, or None if not found."""
        rects = self._hand_card_rects(5)
        for slot_card, rect in zip(self._hand_slots, rects):
            if slot_card == card:
                return (float(rect.centerx), float(rect.centery))
        return None

    def _arena_slot_centre(self, player_idx: int, n_players: int) -> tuple[float, float]:
        """Return the pixel centre of a player's arena slot (mirrors _draw_arena layout)."""
        slot_area_h = _ARENA_H - 30
        slot_area_y = _ARENA_Y + 30
        cols, rows, slot_positions = _ARENA_CONFIG.get(n_players, _ARENA_CONFIG[4])
        col_w = _CTR_W // cols
        row_h = slot_area_h // rows
        cp = slot_positions[player_idx % len(slot_positions)]
        cx = _CTR_X + cp[0] * col_w + col_w // 2
        cy = slot_area_y + cp[1] * row_h + row_h // 2
        return (float(cx), float(cy))

    def _launch_anim(
        self,
        card: Card,
        player_idx: int,
        start: tuple[float, float],
        state: GameState,
    ) -> None:
        """Launch a bezier card-flight animation from start to the player's arena slot."""
        if state.trump_suit is None:
            return
        n = len(state.players)
        p0 = start
        p2 = self._arena_slot_centre(player_idx, n)
        mid = ((p0[0] + p2[0]) / 2, (p0[1] + p2[1]) / 2)
        p1 = (mid[0], mid[1] - 280)
        self._anims.append(
            _CardAnim(
                card=card,
                p0=p0,
                p1=p1,
                p2=p2,
                start_ms=pygame.time.get_ticks(),
                trump=state.trump_suit,
            )
        )


# ---------------------------------------------------------------------------
# Module-level entry point for the --ui loader
# ---------------------------------------------------------------------------


def launch(controller: GameController, *, show_all: bool = False) -> None:
    """Run the Tactical Dashboard UI. Blocks until the game ends or window is closed."""
    TacticalUI(controller, show_all=show_all).run()
