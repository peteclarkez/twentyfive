"""
CLI for Twenty-Five.

Two view modes:
  hidden-hand (default) — each player sees only their own hand; opponents' cards are
      masked with '??'.  AI turns are resolved silently; played cards are printed inline.
  master view (--seeall) — all hands shown simultaneously, rendering before every move.
      Designed for pass-the-terminal play, spectating AI games, or development/testing.
"""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING

from twentyfive.cards.card import Card, Rank, Suit, is_trump
from twentyfive.game.engine import GameEngine
from twentyfive.game.rules import card_global_rank, get_renegeable_cards, trick_winner
from twentyfive.game.state import (
    ConfirmRoundEnd,
    GameState,
    Move,
    PassRob,
    Phase,
    PlayCard,
    Rob,
    TrickPlay,
)

if TYPE_CHECKING:
    from twentyfive.ai.player import AIPlayer

# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------

_SUIT_COLOUR = {
    Suit.HEARTS:   "\033[91m",       # bright red
    Suit.DIAMONDS: "\033[38;5;208m", # orange (from 256-color palette)
    Suit.CLUBS:    "\033[34m",       # navy/blue
    Suit.SPADES:   "\033[32m",       # green
}
_TRUMP_COLOUR = "\033[97m"   # bright white
_RESET = "\033[0m"


def _colour_card(card: Card, trump_suit: Suit | None = None) -> str:
    if trump_suit is not None and is_trump(card, trump_suit):
        return f"{_TRUMP_COLOUR}{card}{_RESET}"
    return f"{_SUIT_COLOUR[card.suit]}{card}{_RESET}"


class CLI:
    def __init__(
        self,
        engine: GameEngine,
        ai_players: dict[str, AIPlayer] | None = None,
        *,
        show_all: bool = False,  # False = hidden-hand (default); True = master view
    ) -> None:
        self._engine = engine
        self._ai_players: dict[str, AIPlayer] = ai_players or {}
        self._show_all = show_all

    def run(self) -> None:
        """Main game loop."""
        while not self._engine.is_game_over:
            state = self._engine.get_state()
            if self._should_render(state):
                self._render(state)
            move = self._prompt_move(state)
            if (not self._show_all
                    and state.current_player.name in self._ai_players
                    and state.phase in (Phase.TRICK, Phase.ROB)):
                self._print_ai_action(state, move)
            self._engine.apply_move(move)

        # After a rob (hidden mode), pause so the player can read the rob message
        # before the screen clears for the next render.
        if not self._show_all and isinstance(move, Rob):
            self._wait_for_continue("  Press A or SPACE to continue...")

        # Show the final game state, then pause before the summary screen
        state = self._engine.get_state()
        self._render(state)
        self._wait_for_continue("  Press A or SPACE to see the final results...")
        self._render_game_over(state)

    def _should_render(self, state: GameState) -> bool:
        if self._show_all:
            return True  # master mode: always render
        return (
            state.current_player.name not in self._ai_players
            or state.phase == Phase.ROUND_END
        )

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render(self, state: GameState) -> None:
        self._clear()
        width = 60
        print("=" * width)
        if state.phase == Phase.ROUND_END:
            trick_info = "Round complete"
        elif state.phase == Phase.GAME_OVER:
            trick_info = "Game over"
        else:
            trick_info = f"Trick {state.trick_number}/5"
        print(
            f"  TWENTY-FIVE  |  Round {state.round_number}  |  {trick_info}"
            f"  |  Game {state.game_id[:8]}"
        )
        print("=" * width)

        # Trump
        assert state.trump_suit is not None
        trump_str = f"Trump: {state.trump_suit.symbol} {state.trump_suit}"
        if state.face_up_card and state.phase != Phase.GAME_OVER:
            face_up_coloured = _colour_card(state.face_up_card, state.trump_suit)
            trump_str += f"  |  Face-up: {face_up_coloured}  (available to rob)"
        print(f"  {trump_str}")
        print()

        # Scores — [leader] marks the player(s) with the highest score
        max_score = max(p.score for p in state.players)
        print("  Scores:")
        for i, player in enumerate(state.players):
            marker = "* " if i == state.current_player_index else "  "
            dealer_tag = " [dealer]" if i == state.dealer_index else ""
            leader_tag = " [leader]" if max_score > 0 and player.score == max_score else ""
            print(
                f"  {marker}{player.name:<12} {player.score:>3} pts"
                f"  ({player.tricks_won_this_round} tricks this round){dealer_tag}{leader_tag}"
            )
        print()

        # Completed tricks this round
        if state.completed_tricks:
            print(f"  Completed tricks this round ({len(state.completed_tricks)}):")
            for trick_idx, trick in enumerate(state.completed_tricks, 1):
                led_suit = trick[0].card.suit
                winner = trick_winner(list(trick), led_suit, state.trump_suit)
                plays_str = "  ".join(
                    f"{tp.player_name}:{_colour_card(tp.card, state.trump_suit)}"
                    for tp in trick
                )
                print(f"    Trick {trick_idx}: {plays_str}  → {winner.player_name} wins")
            print()

        # Current trick — show [led] on lead card; [winning] on the current best card
        if state.current_trick:
            print("  Current trick:")
            led_suit = state.current_trick[0].card.suit
            current_winner_name: str | None = None
            if len(state.current_trick) >= 1:
                current_winner = trick_winner(
                    list(state.current_trick), led_suit, state.trump_suit
                )
                current_winner_name = current_winner.player_name
            for i, tp in enumerate(state.current_trick):
                led_tag = "  [led]" if i == 0 else ""
                win_tag = "  [winning]" if tp.player_name == current_winner_name else ""
                print(
                    f"    {tp.player_name} → "
                    f"{_colour_card(tp.card, state.trump_suit)}{led_tag}{win_tag}"
                )
            print()

        # Hands — master view shows all; hidden view shows only the current player's hand
        print("  Hands:")
        for i, player in enumerate(state.players):
            marker = "* " if i == state.current_player_index else "  "
            show_hand = (
                self._show_all
                or state.phase in (Phase.ROUND_END, Phase.GAME_OVER)  # reveal all at round/game end
                or i == state.current_player_index  # current player always sees their own hand
            )
            if show_hand:
                hand_str = "  ".join(_colour_card(c, state.trump_suit) for c in player.hand)
            elif state.rob_this_round and state.rob_this_round[0] == player.name:
                # Build the set of cards publicly known to be in this player's hand:
                #   • the face-up card they took (card_taken)
                #   • for a non-dealer rob: the Ace of Trump they revealed as eligibility
                rob_name, card_taken = state.rob_this_round
                rob_idx = next(
                    i for i, p in enumerate(state.players) if p.name == rob_name
                )
                publicly_known: set[Card] = set()
                if card_taken in player.hand:
                    publicly_known.add(card_taken)
                if rob_idx != state.dealer_index:
                    ace_of_trump = Card(Rank.ACE, state.trump_suit)
                    if ace_of_trump in player.hand:
                        publicly_known.add(ace_of_trump)
                hand_str = "  ".join(
                    _colour_card(c, state.trump_suit) if c in publicly_known else "??"
                    for c in player.hand
                ) + f"  ({player.hand_size} cards)"
            else:
                hand_str = "  ".join("??" for _ in player.hand) + f"  ({player.hand_size} cards)"
            print(f"  {marker}{player.name:<12}  {hand_str}")
        print()

    def _render_game_over(self, state: GameState) -> None:
        self._clear()
        width = 60
        print("=" * width)
        print(f"  GAME OVER  |  Game {state.game_id[:8]}")
        print("=" * width)
        print()
        sorted_players = sorted(state.players, key=lambda p: p.score, reverse=True)
        winner = sorted_players[0]
        print(f"  Winner: {winner.name} with {winner.score} points!")
        print()
        print("  Final scores:")
        for player in sorted_players:
            print(f"    {player.name:<12} {player.score} pts")
        print()

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------

    def _prompt_move(self, state: GameState) -> Move:
        # In hidden mode, ROUND_END is always handled by a human keypress — an AI
        # current player would return ConfirmRoundEnd instantly, skipping the summary.
        if state.phase == Phase.ROUND_END and not self._show_all:
            return self._prompt_round_end(state)
        current_name = state.current_player.name
        if current_name in self._ai_players:
            return self._ai_players[current_name].choose_move(state)
        if state.phase == Phase.ROB:
            return self._prompt_rob(state)
        if state.phase == Phase.ROUND_END:
            return self._prompt_round_end(state)
        return self._prompt_trick(state)

    def _print_ai_action(self, state: GameState, move: Move) -> None:
        """Print a one-line summary of an AI move (hidden mode only, no screen clear)."""
        name = state.current_player.name
        assert state.trump_suit is not None
        if isinstance(move, PlayCard):
            print(f"  {name} plays {_colour_card(move.card, state.trump_suit)}")
        elif isinstance(move, Rob):
            face_up = state.face_up_card
            card_str = _colour_card(face_up, state.trump_suit) if face_up else "the face-up card"
            print(f"  {name} robs — takes {card_str}")
        elif isinstance(move, PassRob):
            # Only mention if they had a real choice (could have robbed)
            if any(isinstance(m, Rob) for m in state.legal_moves):
                print(f"  {name} passes")

    def _prompt_round_end(self, state: GameState) -> ConfirmRoundEnd:
        """Show round summary and wait for the player to continue."""
        print(f"  Round {state.round_number} complete.")
        print()
        self._wait_for_continue("  Press A or SPACE to deal the next hand...")
        return ConfirmRoundEnd()

    def _prompt_rob(self, state: GameState) -> Move:
        """Two-step prompt for the rob phase."""
        current = state.current_player

        # Check if this player actually has a real choice (not just PassRob)
        has_rob_option = any(isinstance(m, Rob) for m in state.legal_moves)

        if not has_rob_option:
            return PassRob()

        assert state.trump_suit is not None
        print(f"  Rob phase — {current.name}'s turn")
        face_up_str = (
            _colour_card(state.face_up_card, state.trump_suit)
            if state.face_up_card
            else "none"
        )
        print(f"  Face-up card: {face_up_str}")
        print()
        print("  Options:")
        print("    [1] Rob (take the face-up card, discard one from your hand)")
        print("    [2] Pass (do not rob)")
        print()

        choice = self._get_int_input("  Enter choice (1-2): ", 1, 2)

        if choice == 2:
            return PassRob()

        # Player wants to rob — discard from hand first, then take face-up card
        assert state.face_up_card is not None
        print()
        face_up_coloured = _colour_card(state.face_up_card, state.trump_suit)
        print(f"  Choose a card to discard (you will then take {face_up_coloured}):")
        hand_cards = list(current.hand)
        worst_rob_rank = max(card_global_rank(c, state.trump_suit) for c in hand_cards)
        for i, card in enumerate(hand_cards, 1):
            r = card_global_rank(card, state.trump_suit)
            minus_tag = "  (-)" if len(hand_cards) > 1 and r == worst_rob_rank else ""
            rank_tag  = f"  #{r}"
            print(f"    [{i}] {_colour_card(card, state.trump_suit)}{minus_tag}{rank_tag}")
        print()

        idx = self._get_int_input(f"  Discard card (1-{len(hand_cards)}): ", 1, len(hand_cards))
        discard_card = hand_cards[idx - 1]
        print()
        print(
            f"  Robbing — taking {face_up_coloured}, "
            f"discarding {_colour_card(discard_card, state.trump_suit)}"
        )
        return Rob(discard=discard_card)

    def _prompt_trick(self, state: GameState) -> Move:
        """Prompt the current player to select a card to play."""
        current = state.current_player
        legal_cards = [m.card for m in state.legal_moves if isinstance(m, PlayCard)]

        led_card = state.current_trick[0].card if state.current_trick else None
        assert state.trump_suit is not None
        renegeable = get_renegeable_cards(list(current.hand), led_card, state.trump_suit)

        ranks = {card: card_global_rank(card, state.trump_suit) for card in legal_cards}
        worst_rank = max(ranks.values())

        # (+): cards that would make this player the current winner if played now
        winners: set[Card] = set()
        if state.current_trick:
            led_suit = state.current_trick[0].card.suit
            for card in legal_cards:
                hyp = list(state.current_trick) + [TrickPlay(current.name, card)]
                if trick_winner(hyp, led_suit, state.trump_suit).player_name == current.name:
                    winners.add(card)

        action = "to lead" if led_card is None else "to play"
        print(f"  {current.name}'s turn {action}:")
        for i, card in enumerate(legal_cards, 1):
            plus_tag   = "  (+)" if card in winners else ""
            minus_tag  = "  (-)" if len(legal_cards) > 1 and ranks[card] == worst_rank else ""
            renege_tag = "  (renegeable)" if card in renegeable else ""
            rank_tag   = f"  #{ranks[card]}"
            print(
                f"    [{i}] {_colour_card(card, state.trump_suit)}"
                f"{plus_tag}{minus_tag}{renege_tag}{rank_tag}"
            )
        print("    [A] Auto-play (worst winning card, or worst card)")
        print()

        n = len(legal_cards)
        result = self._get_card_input(f"  Play card (1-{n} or A): ", n)
        if isinstance(result, str):
            if winners:
                auto_card = max(winners, key=lambda c: ranks[c])
            else:
                auto_card = max(legal_cards, key=lambda c: ranks[c])
            return PlayCard(card=auto_card)
        return PlayCard(card=legal_cards[result - 1])

    # ------------------------------------------------------------------
    # Input primitives
    # ------------------------------------------------------------------

    def _wait_for_continue(self, msg: str) -> None:
        """Print a message and block until the player presses A, SPACE, or Enter."""
        print(msg)
        print()
        while True:
            ch = self._getkey()
            if ch in (" ", "a", "A", "\r", "\n"):
                print()
                return

    def _getkey(self) -> str:
        """Read a single keypress without requiring Enter (Unix); falls back on Windows."""
        if os.name == "nt":
            import msvcrt
            ch = msvcrt.getwch()  # type: ignore[attr-defined]
        else:
            import termios
            import tty
            fd = sys.stdin.fileno()
            old = termios.tcgetattr(fd)
            try:
                tty.setraw(fd)
                ch = sys.stdin.read(1)
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
        if ch == "\x03":  # Ctrl+C
            raise KeyboardInterrupt
        return ch

    def _get_int_input(self, prompt: str, lo: int, hi: int) -> int:
        """Prompt until a valid single-keypress integer in [lo, hi] is entered."""
        while True:
            print(prompt, end="", flush=True)
            ch = self._getkey()
            print(ch)  # echo the key
            try:
                value = int(ch)
                if lo <= value <= hi:
                    return value
            except ValueError:
                pass
            print(f"  Please enter a number between {lo} and {hi}.")

    def _get_card_input(self, prompt: str, n: int) -> int | str:
        """Prompt until a valid single-keypress card number (1–n) or 'A' is entered."""
        while True:
            print(prompt, end="", flush=True)
            ch = self._getkey()
            print(ch)  # echo the key
            if ch.upper() == "A":
                return "A"
            try:
                value = int(ch)
                if 1 <= value <= n:
                    return value
            except ValueError:
                pass
            print(f"  Please enter a number between 1 and {n}, or A to auto-play.")

    def _clear(self) -> None:
        os.system("clear" if os.name != "nt" else "cls")
