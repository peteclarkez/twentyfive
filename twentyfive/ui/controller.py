"""
GameController — wraps GameEngine + AI players.

Both the CLI and the pygame UI use this as their single interface to the game.
UIs call state / apply_move / step_ai rather than talking to the engine directly,
which keeps each UI free of game-loop and AI-dispatch boilerplate.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from twentyfive.game.engine import GameEngine
from twentyfive.game.state import GameState, Move

if TYPE_CHECKING:
    from twentyfive.ai.player import AIPlayer


class GameController:
    """Wraps a GameEngine and its AI players for consumption by any UI."""

    def __init__(
        self,
        engine: GameEngine,
        ai_players: dict[str, AIPlayer] | None = None,
    ) -> None:
        self._engine = engine
        self._ai_players: dict[str, AIPlayer] = ai_players or {}

    @property
    def state(self) -> GameState:
        return self._engine.get_state()

    @property
    def is_game_over(self) -> bool:
        return self._engine.is_game_over

    def is_ai_turn(self) -> bool:
        """True if the current player has an AI registered."""
        return self._engine.get_state().current_player.name in self._ai_players

    def step_ai(self) -> tuple[str, Move, GameState]:
        """Compute and apply the AI move for the current player.

        Returns:
            (actor_name, move_applied, new_state)

        Raises:
            RuntimeError: If it is not the AI's turn.
        """
        state = self._engine.get_state()
        actor = state.current_player.name
        if actor not in self._ai_players:
            raise RuntimeError(f"Not an AI turn — {actor!r} is a human player.")
        move = self._ai_players[actor].choose_move(state)
        self._engine.apply_move(move)
        return actor, move, self._engine.get_state()

    def apply_move(self, move: Move) -> GameState:
        """Apply a human-chosen move and return the new state.

        Raises:
            ValueError: If the move is illegal (propagated from the engine).
        """
        self._engine.apply_move(move)
        return self._engine.get_state()

    @property
    def human_players(self) -> frozenset[str]:
        """Names of players with no AI registered."""
        state = self._engine.get_state()
        return frozenset(p.name for p in state.players if p.name not in self._ai_players)
