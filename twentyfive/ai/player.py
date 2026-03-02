"""
AI player base class and RandomPlayer.

All AI players implement the AIPlayer interface: given a GameState snapshot,
return a legal Move. The engine enforces legality — the AI just has to pick from
state.legal_moves (or a subset of it).
"""

from __future__ import annotations

import random
from abc import ABC, abstractmethod

from twentyfive.game.state import GameState, Move


class AIPlayer(ABC):
    """Abstract base class for all AI player implementations."""

    @abstractmethod
    def choose_move(self, state: GameState) -> Move:
        """Return a legal move for the current player in the given state."""
        ...


class RandomPlayer(AIPlayer):
    """AI player that selects uniformly at random from the legal moves."""

    def choose_move(self, state: GameState) -> Move:
        return random.choice(list(state.legal_moves))
