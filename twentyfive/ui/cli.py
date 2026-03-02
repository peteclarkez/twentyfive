"""
CLI for Twenty-Five — master view mode.

All players' hands are shown simultaneously (privacy is not enforced).
Designed for pass-the-terminal play around one screen, or for development/testing.
"""

from __future__ import annotations

import os

from twentyfive.cards.card import Card
from twentyfive.game.engine import GameEngine
from twentyfive.game.state import GameState, Move, PassRob, Phase, PlayCard, Rob


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

        self._render_game_over(self._engine.get_state())

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render(self, state: GameState) -> None:
        self._clear()
        width = 60
        print("=" * width)
        print(f"  TWENTY-FIVE  |  Round {state.round_number}  |  Trick {state.trick_number}/5")
        print("=" * width)

        # Trump
        assert state.trump_suit is not None
        trump_str = f"Trump: {state.trump_suit.symbol} {state.trump_suit}"
        if state.face_up_card:
            trump_str += f"  |  Face-up: {state.face_up_card}  (available to rob)"
        print(f"  {trump_str}")
        print()

        # Scores
        print("  Scores:")
        for i, player in enumerate(state.players):
            marker = "* " if i == state.current_player_index else "  "
            dealer_tag = " [dealer]" if i == state.dealer_index else ""
            print(
                f"  {marker}{player.name:<12} {player.score:>3} pts"
                f"  ({player.tricks_won_this_round} tricks this round){dealer_tag}"
            )
        print()

        # Current trick
        if state.current_trick:
            print("  Current trick:")
            for tp in state.current_trick:
                print(f"    {tp.player_name} → {tp.card}")
            print()

        # All hands (master view)
        print("  Hands:")
        for i, player in enumerate(state.players):
            marker = "* " if i == state.current_player_index else "  "
            hand_str = "  ".join(str(c) for c in player.hand)
            print(f"  {marker}{player.name:<12} {hand_str}")
        print()

    def _render_game_over(self, state: GameState) -> None:
        self._clear()
        width = 60
        print("=" * width)
        print("  GAME OVER")
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
        return self._prompt_trick(state)

    def _prompt_rob(self, state: GameState) -> Move:
        """Two-step prompt for the rob phase."""
        current = state.current_player

        # Check if this player actually has a real choice (not just PassRob)
        has_rob_option = any(isinstance(m, Rob) for m in state.legal_moves)

        if not has_rob_option:
            # Engine shouldn't set this player as current if ineligible, but handle gracefully
            return PassRob()

        print(f"  Rob phase — {current.name}'s turn")
        print(f"  Face-up card: {state.face_up_card}")
        print()
        print("  Options:")
        print("    [1] Rob (take the face-up card, discard one from your hand)")
        print("    [2] Pass (do not rob)")
        print()

        choice = self._get_int_input("  Enter choice (1-2): ", 1, 2)

        if choice == 2:
            return PassRob()

        # Player wants to rob — choose a card to discard
        assert state.face_up_card is not None
        print()
        print(f"  You take {state.face_up_card}. Choose a card to discard:")
        # The augmented hand is current hand + face_up_card
        augmented: list[Card] = list(current.hand) + [state.face_up_card]
        for i, card in enumerate(augmented, 1):
            print(f"    [{i}] {card}")
        print()

        idx = self._get_int_input(f"  Discard card (1-{len(augmented)}): ", 1, len(augmented))
        return Rob(discard=augmented[idx - 1])

    def _prompt_trick(self, state: GameState) -> Move:
        """Prompt the current player to select a card to play."""
        current = state.current_player
        legal_cards = [m.card for m in state.legal_moves if isinstance(m, PlayCard)]

        print(f"  {current.name}'s turn to play:")
        for i, card in enumerate(legal_cards, 1):
            print(f"    [{i}] {card}")
        print()

        idx = self._get_int_input(f"  Play card (1-{len(legal_cards)}): ", 1, len(legal_cards))
        return PlayCard(card=legal_cards[idx - 1])

    def _get_int_input(self, prompt: str, lo: int, hi: int) -> int:
        """Prompt until valid integer in [lo, hi] is entered."""
        while True:
            raw = input(prompt).strip()
            try:
                value = int(raw)
                if lo <= value <= hi:
                    return value
            except ValueError:
                pass
            print(f"  Please enter a number between {lo} and {hi}.")

    def _clear(self) -> None:
        os.system("clear" if os.name != "nt" else "cls")
