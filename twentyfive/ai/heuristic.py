"""
HeuristicPlayer — strategy-driven AI based on STRATEGY.md priority rules.

Decision priority:
  Rob:    always rob when eligible; discard weakest card.
  Lead:   smoke out danger players with best trump; otherwise lead weakest non-trump.
  Follow: (1) stop danger player winning → strongest winner;
          (2) non-Five winner available → weakest non-Five winner;
          (3) Five is only winner → use it only if danger or last-to-play;
          (4) cannot win → weakest legal card.
"""

from __future__ import annotations

from twentyfive.ai.player import AIPlayer
from twentyfive.cards.card import Card, Rank, is_trump
from twentyfive.game.rules import card_global_rank, trick_winner
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


class HeuristicPlayer(AIPlayer):
    """Strategy-driven AI player implementing STRATEGY.md heuristics."""

    def choose_move(self, state: GameState) -> Move:
        match state.phase:
            case Phase.ROB:
                return self._rob(state)
            case Phase.TRICK:
                return self._trick(state)
            case _:
                return ConfirmRoundEnd()

    # ------------------------------------------------------------------
    # Rob phase
    # ------------------------------------------------------------------

    def _rob(self, state: GameState) -> Move:
        rob_moves = [m for m in state.legal_moves if isinstance(m, Rob)]
        if not rob_moves:
            return PassRob()
        assert state.trump_suit is not None
        trump_suit = state.trump_suit
        # Discard the weakest card (highest global rank number)
        return max(rob_moves, key=lambda m: card_global_rank(m.discard, trump_suit))

    # ------------------------------------------------------------------
    # Trick phase
    # ------------------------------------------------------------------

    def _trick(self, state: GameState) -> Move:
        assert state.trump_suit is not None
        trump_suit = state.trump_suit
        my_name = state.current_player.name
        n_players = len(state.players)
        legal_cards = [m.card for m in state.legal_moves if isinstance(m, PlayCard)]

        def by_rank(card: Card) -> int:
            return card_global_rank(card, trump_suit)

        # Danger players: opponents at >= 20 points
        danger_players = {
            p.name for p in state.players
            if p.name != my_name and p.score >= 20
        }

        # Cards that would make me the current trick winner
        winners: set[Card] = set()
        danger_winning = False
        if state.current_trick:
            led_suit = state.current_trick[0].card.suit
            for card in legal_cards:
                hyp = list(state.current_trick) + [TrickPlay(my_name, card)]
                if trick_winner(hyp, led_suit, trump_suit).player_name == my_name:
                    winners.add(card)
            current_winner = trick_winner(
                list(state.current_trick), led_suit, trump_suit
            )
            danger_winning = current_winner.player_name in danger_players

        five = Card(Rank.FIVE, trump_suit)

        # --- Leading ---
        if not state.current_trick:
            return self._lead(legal_cards, danger_players, trump_suit, by_rank)

        # --- Following ---

        # 1. Must stop a danger player who is currently winning
        if danger_winning and winners:
            return PlayCard(card=min(winners, key=by_rank))  # strongest winner

        # 2. Non-Five winner available — use weakest to preserve the Five
        non_five_winners = [c for c in winners if c != five]
        if non_five_winners:
            return PlayCard(card=max(non_five_winners, key=by_rank))

        # 3. Five is the only winning card — use it only if worth it
        if five in winners:
            last_to_play = len(state.current_trick) == n_players - 1
            if danger_winning or last_to_play:
                return PlayCard(card=five)
            # else: not worth it — fall through to weakest

        # 4. Cannot win (or Five withheld) — minimise loss
        return PlayCard(card=max(legal_cards, key=by_rank))

    def _lead(
        self,
        legal_cards: list[Card],
        danger_players: set[str],
        trump_suit,
        by_rank,
    ) -> Move:
        trumps = [c for c in legal_cards if is_trump(c, trump_suit)]
        non_trumps = [c for c in legal_cards if not is_trump(c, trump_suit)]

        if danger_players:
            # Smoke out near-winning opponents with the best trump
            if trumps:
                return PlayCard(card=min(trumps, key=by_rank))  # strongest trump
            # No trumps — play weakest card available
            return PlayCard(card=max(legal_cards, key=by_rank))

        # Conservative lead: weakest non-trump; fall back to weakest trump
        pool = non_trumps if non_trumps else legal_cards
        return PlayCard(card=max(pool, key=by_rank))
