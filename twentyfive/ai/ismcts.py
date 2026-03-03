"""
ISMCTSPlayer — Information Set Monte Carlo Tree Search AI.

Implements Single-Observer ISMCTS (Cowling, Powley & Whitehouse 2012).

Unlike the basic MCTSPlayer, which has full visibility of all hands,
ISMCTSPlayer only uses public information.  Before each simulation it
*determinizes* — randomly assigns plausible cards to opponents consistent
with what is publicly known — then runs standard UCB-guided tree search on
that complete-information state.  The shared tree is updated across all
determinizations, with an `availability` counter replacing the `parent.visits`
term in the UCB exploration formula.

Parameters
----------
simulations : int
    Number of ISMCTS iterations per move decision (default 500).
c : float
    UCB exploration constant (default sqrt(2)).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from twentyfive.ai.player import AIPlayer
from twentyfive.cards.card import Card, Rank, Suit
from twentyfive.game.state import ConfirmRoundEnd, GameState, Move

if TYPE_CHECKING:
    from twentyfive.game.engine import GameEngine

_DEFAULT_SIMULATIONS = 500
_DEFAULT_C = math.sqrt(2)


@dataclass
class _Node:
    """One node in the ISMCTS search tree."""

    parent: _Node | None = None
    visits: int = 0
    availability: int = 0      # times this node was a legal option across determinizations
    value_sum: float = 0.0
    children: dict[Move, _Node] = field(default_factory=dict)

    def ucb(self, c: float) -> float:
        """ISMCTS UCB score.

        Uses `availability` (not parent.visits) in the exploration term because
        different determinizations expose different moves at each node.
        """
        if self.visits == 0:
            return float("inf")
        return (
            self.value_sum / self.visits
            + c * math.sqrt(math.log(self.availability) / self.availability)
        )


class ISMCTSPlayer(AIPlayer):
    """ISMCTS player — fair hidden-hand AI using determinized tree search."""

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
        if len(state.legal_moves) == 1:
            return state.legal_moves[0]

        my_index = state.current_player_index
        root = _Node()

        for _ in range(self._simulations):
            det_engine = self._determinize(state)
            self._iterate(root, det_engine, my_index)

        # Most-visited child is the most robust action (standard MCTS criterion)
        return max(root.children, key=lambda m: root.children[m].visits)

    # ------------------------------------------------------------------
    # Determinization
    # ------------------------------------------------------------------

    def _determinize(self, state: GameState) -> GameEngine:
        """
        Return a cloned engine with opponent hands randomly re-dealt.

        Only public information is used:
        - My own hand (exact)
        - Cards already played in tricks
        - Face-up card (if not yet taken)
        - Cards publicly revealed by a rob (taken card + ace-of-trump for non-dealer robs)

        Opponent hand *sizes* are taken from state.players[i].hand_size.
        Opponent hand *contents* are NOT read (that would be cheating).
        """
        my_index = state.current_player_index
        assert state.trump_suit is not None

        # --- Collect all publicly known cards ---
        played: set[Card] = set()
        for trick in state.completed_tricks:
            for tp in trick:
                played.add(tp.card)
        for tp in state.current_trick:
            played.add(tp.card)

        my_hand: set[Card] = set(state.current_player.hand)
        known: set[Card] = played | my_hand
        if state.face_up_card is not None:
            known.add(state.face_up_card)

        # Cards publicly known to be in a specific opponent's hand (from rob)
        opp_fixed: dict[int, set[Card]] = {}
        if state.rob_this_round is not None:
            rob_name, card_taken = state.rob_this_round
            rob_idx = next(i for i, p in enumerate(state.players) if p.name == rob_name)
            if rob_idx != my_index:
                fixed: set[Card] = set()
                if card_taken not in played:
                    fixed.add(card_taken)
                    known.add(card_taken)
                if rob_idx != state.dealer_index:
                    ace = Card(Rank.ACE, state.trump_suit)
                    if ace not in played:
                        fixed.add(ace)
                        known.add(ace)
                if fixed:
                    opp_fixed[rob_idx] = fixed

        # --- Build and shuffle the pool of unknown cards ---
        full_deck = {Card(rank, suit) for rank in Rank for suit in Suit}
        pool = list(full_deck - known)
        random.shuffle(pool)

        # --- Clone engine and replace opponent hands ---
        cloned = self._engine.clone()
        pool_idx = 0
        for i, (player, snap) in enumerate(zip(cloned._players, state.players)):
            if i == my_index:
                continue
            fixed_cards = opp_fixed.get(i, set())
            n_random = snap.hand_size - len(fixed_cards)
            new_hand = list(fixed_cards) + pool[pool_idx : pool_idx + n_random]
            pool_idx += n_random
            player.clear_hand()
            for card in new_hand:
                player.add_card(card)

        return cloned

    # ------------------------------------------------------------------
    # ISMCTS phases
    # ------------------------------------------------------------------

    def _iterate(self, root: _Node, engine: GameEngine, my_index: int) -> None:
        node = root

        # 1. Selection: walk tree choosing compatible children by UCB-availability.
        #    "Compatible" = move is legal in this determinization.
        #    Increment availability on ALL compatible children at each level
        #    (even those not selected), as required by SO-ISMCTS.
        while not engine.is_game_over:
            legal = set(engine.get_state().legal_moves)
            compatible = {m: ch for m, ch in node.children.items() if m in legal}

            for child in compatible.values():
                child.availability += 1

            unexplored = legal - set(node.children)
            if unexplored:
                break  # proceed to expansion
            if not compatible:
                break  # fully terminal or no legal moves (shouldn't occur mid-game)

            best_move = max(compatible, key=lambda m: compatible[m].ucb(self._c))
            engine.apply_move(best_move)
            node = compatible[best_move]

        # 2. Expansion: add one unexplored-but-legal child.
        #    Skip ConfirmRoundEnd — it triggers a new random deal, making the
        #    resulting state non-deterministic; let the rollout handle it instead.
        if not engine.is_game_over:
            legal = set(engine.get_state().legal_moves)
            unexplored = legal - set(node.children)
            if unexplored:
                move = random.choice(list(unexplored))
                engine.apply_move(move)
                if not isinstance(move, ConfirmRoundEnd):
                    child = _Node(parent=node, availability=1)
                    node.children[move] = child
                    node = child

        # 3. Rollout: play randomly to game end
        while not engine.is_game_over:
            s = engine.get_state()
            engine.apply_move(random.choice(list(s.legal_moves)))

        # 4. Backpropagation: propagate reward up to root
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
