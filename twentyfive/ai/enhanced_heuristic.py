"""
EnhancedHeuristicPlayer — improved strategy-driven AI extending HeuristicPlayer.

Adds five enhancements over the base HeuristicPlayer:

  1. Card tracking  — when leading, prefer a suit where you hold the highest
                      remaining card (dominance detection using completed tricks).
  2. Endgame        — tricks 4–5: commit trump aggressively even without a danger
                      player (the round is almost over; hold nothing back).
  3. Multi-opponent — treat the current score leader as dangerous at >= 15 points
                      (not only >= 20); still flag everyone at >= 20.
  4. Rob quality    — prefer discarding from a singleton non-trump suit (goes void,
                      stripping a suit you can never follow anyway).
  5. Don't over-trump — when following, exhaust non-trump winners before spending
                        trump; don't burn a high trump to beat a low trump.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable

from twentyfive.ai.player import AIPlayer
from twentyfive.cards.card import Card, Rank, Suit, is_trump
from twentyfive.game.rules import card_global_rank, non_trump_rank, trick_winner
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


class EnhancedHeuristicPlayer(AIPlayer):
    """Enhanced strategy AI — all five improvements over the base HeuristicPlayer."""

    def choose_move(self, state: GameState) -> Move:
        match state.phase:
            case Phase.ROB:
                return self._rob(state)
            case Phase.TRICK:
                return self._trick(state)
            case _:
                return ConfirmRoundEnd()

    # ------------------------------------------------------------------
    # Rob phase (Enhancement 4: prefer singleton non-trump discard)
    # ------------------------------------------------------------------

    def _rob(self, state: GameState) -> Move:
        rob_moves = [m for m in state.legal_moves if isinstance(m, Rob)]
        if not rob_moves:
            return PassRob()
        assert state.trump_suit is not None
        trump_suit = state.trump_suit

        hand = [m.discard for m in rob_moves]

        # Enhancement 4: prefer going void in a singleton non-trump suit
        non_trumps = [c for c in hand if not is_trump(c, trump_suit)]
        suit_count: Counter[Suit] = Counter(c.suit for c in non_trumps)
        singletons = [c for c in non_trumps if suit_count[c.suit] == 1]

        if singletons:
            pool: list[Card] = singletons
        elif non_trumps:
            pool = non_trumps
        else:
            pool = hand

        discard = max(pool, key=lambda c: card_global_rank(c, trump_suit))
        return Rob(discard=discard)

    # ------------------------------------------------------------------
    # Trick phase
    # ------------------------------------------------------------------

    def _trick(self, state: GameState) -> Move:
        assert state.trump_suit is not None
        trump_suit = state.trump_suit
        my_name = state.current_player.name
        n_players = len(state.players)
        legal_cards = [m.card for m in state.legal_moves if isinstance(m, PlayCard)]
        is_endgame = state.trick_number >= 4

        def by_rank(card: Card) -> int:
            return card_global_rank(card, trump_suit)

        # Enhancement 3: danger = opponents at >= 20, plus the score leader at >= 15
        others = [p for p in state.players if p.name != my_name]
        danger_players: set[str] = {p.name for p in others if p.score >= 20}
        if others:
            leader = max(others, key=lambda p: p.score)
            if leader.score >= 15:
                danger_players.add(leader.name)

        # Card tracking: collect all cards played so far this round
        played_cards: set[Card] = {tp.card for trick in state.completed_tricks for tp in trick}
        played_cards |= {tp.card for tp in state.current_trick}

        # Cards that would make me the current trick winner
        winners: set[Card] = set()
        danger_winning = False
        if state.current_trick:
            led_suit = state.current_trick[0].card.suit
            for card in legal_cards:
                hyp = list(state.current_trick) + [TrickPlay(my_name, card)]
                if trick_winner(hyp, led_suit, trump_suit).player_name == my_name:
                    winners.add(card)
            current_winner = trick_winner(list(state.current_trick), led_suit, trump_suit)
            danger_winning = current_winner.player_name in danger_players

        five = Card(Rank.FIVE, trump_suit)

        # --- Leading ---
        if not state.current_trick:
            return self._lead(
                legal_cards, danger_players, trump_suit, by_rank, is_endgame, played_cards
            )

        # --- Following ---

        # 1. Must stop a danger player who is currently winning
        if danger_winning and winners:
            return PlayCard(card=min(winners, key=by_rank))  # strongest winner

        # Enhancement 5: use non-trump winners before spending trump
        non_trump_winners = [c for c in winners if not is_trump(c, trump_suit)]
        if non_trump_winners:
            return PlayCard(card=max(non_trump_winners, key=by_rank))  # weakest non-trump

        # 2. Non-Five trump winner available — use weakest to preserve the Five
        non_five_winners = [c for c in winners if c != five]
        if non_five_winners:
            return PlayCard(card=max(non_five_winners, key=by_rank))

        # 3. Five is the only winning card — use it only if worth it
        if five in winners:
            last_to_play = len(state.current_trick) == n_players - 1
            if danger_winning or last_to_play:
                return PlayCard(card=five)
            # else: not worth burning the Five

        # 4. Cannot win (or Five withheld) — minimise loss
        return PlayCard(card=max(legal_cards, key=by_rank))

    # ------------------------------------------------------------------
    # Lead selection (Enhancements 1, 2, 3)
    # ------------------------------------------------------------------

    def _lead(
        self,
        legal_cards: list[Card],
        danger_players: set[str],
        trump_suit: Suit,
        by_rank: Callable[[Card], int],
        is_endgame: bool,
        played_cards: set[Card],
    ) -> Move:
        trumps = [c for c in legal_cards if is_trump(c, trump_suit)]
        non_trumps = [c for c in legal_cards if not is_trump(c, trump_suit)]

        # Danger player present: smoke them out with strongest trump
        if danger_players:
            if trumps:
                return PlayCard(card=min(trumps, key=by_rank))  # strongest trump
            return PlayCard(card=max(legal_cards, key=by_rank))

        # Enhancement 2: endgame — commit trump even without a danger player
        if is_endgame:
            if trumps:
                return PlayCard(card=min(trumps, key=by_rank))  # strongest trump
            pool = non_trumps if non_trumps else legal_cards
            return PlayCard(card=max(pool, key=by_rank))

        # Enhancement 1: card tracking — lead from a suit where I'm dominant
        dominant = self._dominant_lead(legal_cards, played_cards, trump_suit, by_rank)
        if dominant is not None:
            return PlayCard(card=dominant)

        # Conservative fallback: weakest non-trump; fall back to weakest trump
        pool = non_trumps if non_trumps else legal_cards
        return PlayCard(card=max(pool, key=by_rank))

    def _dominant_lead(
        self,
        legal_cards: list[Card],
        played_cards: set[Card],
        trump_suit: Suit,
        by_rank: Callable[[Card], int],
    ) -> Card | None:
        """
        Return the best non-trump card in a suit where I hold the highest remaining card.

        A card is 'dominant' in its suit when every non-trump card of that suit that
        outranks it has already been played.
        """
        non_trumps = [c for c in legal_cards if not is_trump(c, trump_suit)]
        # Iterate best-first so we return the strongest dominant card available
        for my_card in sorted(non_trumps, key=by_rank):
            my_nr = non_trump_rank(my_card)
            # Non-trump cards of the same suit that strictly outrank my card
            suit_cards_above = [
                Card(r, my_card.suit)
                for r in Rank
                if not is_trump(Card(r, my_card.suit), trump_suit)
                and non_trump_rank(Card(r, my_card.suit)) > my_nr
            ]
            if all(c in played_cards for c in suit_cards_above):
                return my_card
        return None
