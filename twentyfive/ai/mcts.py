"""
MCTSPlayer — Monte Carlo Tree Search AI (paranoid variant).

Uses UCB1-guided tree search with random rollouts to select moves.
Maximises this player's own win rate; treats all opponents as independent
(paranoid MCTS — simpler than max^n but works well in practice).

The player stores a reference to the live GameEngine and clones it at the
start of each simulation so the real game state is never affected.

Parameters
----------
simulations : int
    Number of MCTS iterations per move decision.  Higher = stronger but
    slower.  500 is a reasonable default for interactive play.
c : float
    UCB1 exploration constant.  sqrt(2) ≈ 1.414 is the standard default.
    Increase to explore more; decrease to exploit more.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from twentyfive.ai.player import AIPlayer
from twentyfive.game.state import ConfirmRoundEnd, GameState, Move

if TYPE_CHECKING:
    from twentyfive.game.engine import GameEngine

_DEFAULT_SIMULATIONS = 500
_DEFAULT_C = math.sqrt(2)


@dataclass
class _Node:
    """One node in the MCTS search tree."""

    parent: _Node | None = None
    visits: int = 0
    value_sum: float = 0.0  # accumulated reward from the AI player's perspective
    children: dict[Move, _Node] = field(default_factory=dict)
    untried_moves: list[Move] = field(default_factory=list)

    def ucb1(self, c: float) -> float:
        """UCB1 score; returns +inf for unvisited nodes (forces exploration)."""
        if self.visits == 0:
            return float("inf")
        assert self.parent is not None
        return (
            self.value_sum / self.visits
            + c * math.sqrt(math.log(self.parent.visits) / self.visits)
        )


class MCTSPlayer(AIPlayer):
    """Monte Carlo Tree Search player — UCB1 tree search with random rollouts."""

    def __init__(
        self,
        engine: GameEngine,
        *,
        simulations: int = _DEFAULT_SIMULATIONS,
        c: float = _DEFAULT_C,
    ) -> None:
        self._engine = engine
        self._simulations = simulations
        self._c = c

    def choose_move(self, state: GameState) -> Move:
        # No search needed when there is only one legal option
        if len(state.legal_moves) == 1:
            return state.legal_moves[0]

        my_index = state.current_player_index
        root = _Node(untried_moves=list(state.legal_moves))

        for _ in range(self._simulations):
            self._iterate(root, self._engine.clone(), my_index)

        # Most-visited child is the most robust action (standard MCTS criterion)
        return max(root.children, key=lambda m: root.children[m].visits)

    # ------------------------------------------------------------------
    # MCTS phases
    # ------------------------------------------------------------------

    def _iterate(self, root: _Node, engine: GameEngine, my_index: int) -> None:
        node = root

        # 1. Selection: walk the tree while all moves at this node are explored
        while not engine.is_game_over and not node.untried_moves and node.children:
            best_move = max(node.children, key=lambda m: node.children[m].ucb1(self._c))
            engine.apply_move(best_move)
            node = node.children[best_move]

        # 2. Expansion: try one unexplored move and create a child node.
        #    ConfirmRoundEnd triggers a new random deal (deck re-shuffle), making the
        #    resulting state non-deterministic across simulations.  Don't add a tree
        #    node after it — let the rollout handle the new round instead.
        if not engine.is_game_over and node.untried_moves:
            move = node.untried_moves.pop(random.randrange(len(node.untried_moves)))
            engine.apply_move(move)
            if not isinstance(move, ConfirmRoundEnd) and not engine.is_game_over:
                child = _Node(
                    parent=node,
                    untried_moves=list(engine.get_state().legal_moves),
                )
                node.children[move] = child
                node = child

        # 3. Rollout: play randomly to game end
        #    ConfirmRoundEnd is the only legal move in ROUND_END phase, so
        #    random.choice handles it naturally without special-casing.
        while not engine.is_game_over:
            s = engine.get_state()
            engine.apply_move(random.choice(list(s.legal_moves)))

        # 4. Backpropagation: propagate win/loss reward up to the root
        final = engine.get_state()
        my_score = final.players[my_index].score
        max_score = max(p.score for p in final.players)
        n_at_max = sum(1 for p in final.players if p.score == max_score)
        reward = (1.0 / n_at_max) if my_score == max_score else 0.0

        current: _Node | None = node
        while current is not None:
            current.visits += 1
            current.value_sum += reward
            current = current.parent
