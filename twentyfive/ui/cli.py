"""
CLI for Twenty-Five — master view mode.

All players' hands are shown simultaneously (privacy is not enforced).
Designed for pass-the-terminal play around one screen, or for development/testing.
"""

from __future__ import annotations

import os
import sys

from twentyfive.cards.card import Card, Suit, is_trump
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
    def __init__(self, engine: GameEngine) -> None:
        self._engine = engine

    def run(self) -> None:
        """Main game loop."""
        while not self._engine.is_game_over:
            state = self._engine.get_state()
            self._render(state)
            move = self._prompt_move(state)
            self._engine.apply_move(move)

        # Show the final game state, then pause before the summary screen
        state = self._engine.get_state()
        self._render(state)
        self._wait_for_continue("  Press A or SPACE to see the final results...")
        self._render_game_over(state)

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render(self, state: GameState) -> None:
        self._clear()
        width = 60
        print("=" * width)
        if state.phase == Phase.ROUND_END:
            trick_info = "Round complete"
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
        if state.face_up_card:
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

        # All hands (master view)
        print("  Hands:")
        for i, player in enumerate(state.players):
            marker = "* " if i == state.current_player_index else "  "
            hand_str = "  ".join(_colour_card(c, state.trump_suit) for c in player.hand)
            print(f"  {marker}{player.name:<12} {hand_str}")
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
        if state.phase == Phase.ROB:
            return self._prompt_rob(state)
        if state.phase == Phase.ROUND_END:
            return self._prompt_round_end(state)
        return self._prompt_trick(state)

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
        return Rob(discard=hand_cards[idx - 1])

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
        print("    [A] Auto-play (first legal card)")
        print()

        n = len(legal_cards)
        result = self._get_card_input(f"  Play card (1-{n} or A): ", n)
        if isinstance(result, str):
            return PlayCard(card=legal_cards[0])
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
