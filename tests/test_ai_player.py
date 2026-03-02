"""
Tests for AI players: RandomPlayer and HeuristicPlayer.

All tests drive the engine to specific states (using seed search or direct play)
and verify that the AI returns a legal, sensible move.
"""

from __future__ import annotations

import random

import pytest

from twentyfive.ai.heuristic import HeuristicPlayer
from twentyfive.ai.player import RandomPlayer
from twentyfive.cards.card import Card, Rank, Suit, is_trump
from twentyfive.game.engine import GameEngine
from twentyfive.game.rules import card_global_rank
from twentyfive.game.state import (
    ConfirmRoundEnd,
    PassRob,
    Phase,
    PlayCard,
    Rob,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_engine(n: int = 3, seed: int = 42) -> GameEngine:
    random.seed(seed)
    return GameEngine(player_names=[f"P{i+1}" for i in range(n)], audit_dir=None)


def find_engine_in_rob_phase(n: int = 3) -> GameEngine:
    """Return an engine where the rob phase is active."""
    for seed in range(500):
        random.seed(seed)
        engine = GameEngine([f"P{i+1}" for i in range(n)], audit_dir=None)
        if engine.get_state().phase == Phase.ROB:
            return engine
    raise RuntimeError("Could not find a seed with a rob phase")  # pragma: no cover


def advance_to_trick_phase(engine: GameEngine) -> None:
    """Pass through the rob phase so we are in TRICK."""
    while not engine.is_game_over:
        state = engine.get_state()
        if state.phase != Phase.ROB:
            break
        engine.apply_move(PassRob())


def advance_to_round_end(engine: GameEngine, *, max_moves: int = 200) -> None:
    """Play cards (always first legal) until ROUND_END is reached."""
    advance_to_trick_phase(engine)
    moves = 0
    while not engine.is_game_over and moves < max_moves:
        state = engine.get_state()
        if state.phase == Phase.ROUND_END:
            return
        engine.apply_move(state.legal_moves[0])
        moves += 1


# ---------------------------------------------------------------------------
# RandomPlayer
# ---------------------------------------------------------------------------


class TestRandomPlayer:
    def test_always_returns_legal_move_trick_phase(self) -> None:
        engine = make_engine()
        advance_to_trick_phase(engine)
        state = engine.get_state()
        assert state.phase == Phase.TRICK

        player = RandomPlayer()
        move = player.choose_move(state)
        assert move in state.legal_moves

    def test_always_returns_legal_move_round_end(self) -> None:
        engine = make_engine()
        advance_to_round_end(engine)
        state = engine.get_state()
        assert state.phase == Phase.ROUND_END

        player = RandomPlayer()
        move = player.choose_move(state)
        assert move in state.legal_moves

    def test_always_returns_legal_move_rob_phase(self) -> None:
        engine = find_engine_in_rob_phase()
        state = engine.get_state()
        assert state.phase == Phase.ROB

        player = RandomPlayer()
        move = player.choose_move(state)
        assert move in state.legal_moves


# ---------------------------------------------------------------------------
# HeuristicPlayer
# ---------------------------------------------------------------------------


class TestHeuristicPlayerRob:
    def test_robs_when_eligible(self) -> None:
        """HeuristicPlayer always robs when Rob moves are available."""
        engine = find_engine_in_rob_phase()
        state = engine.get_state()

        rob_available = any(isinstance(m, Rob) for m in state.legal_moves)
        player = HeuristicPlayer()
        move = player.choose_move(state)

        if rob_available:
            assert isinstance(move, Rob)
        else:
            assert isinstance(move, PassRob)

    def test_rob_discards_weakest_card(self) -> None:
        """The discarded card is the one with the highest global rank (weakest)."""
        engine = find_engine_in_rob_phase()
        state = engine.get_state()

        rob_moves = [m for m in state.legal_moves if isinstance(m, Rob)]
        if not rob_moves:
            pytest.skip("No Rob moves in this state")

        assert state.trump_suit is not None
        player = HeuristicPlayer()
        move = player.choose_move(state)
        assert isinstance(move, Rob)

        # The discarded card must have the highest global rank in the set of rob discards
        worst_rank = max(card_global_rank(m.discard, state.trump_suit) for m in rob_moves)
        assert card_global_rank(move.discard, state.trump_suit) == worst_rank

    def test_pass_rob_when_ineligible(self) -> None:
        """Returns PassRob when legal_moves contains only PassRob (ineligible player)."""
        # The engine never reaches this via normal play (only eligible players are queued),
        # so construct a minimal GameState directly to exercise the branch.
        from twentyfive.game.state import GameState, PlayerSnapshot

        hand = (Card(Rank.TWO, Suit.CLUBS),)
        snapshot = PlayerSnapshot(
            name="P1", score=0, tricks_won_this_round=0, hand_size=1, hand=hand
        )
        state = GameState(
            phase=Phase.ROB,
            players=(snapshot,),
            current_player_index=0,
            dealer_index=0,
            trump_suit=Suit.HEARTS,
            face_up_card=Card(Rank.ACE, Suit.HEARTS),
            current_trick=(),
            completed_tricks=(),
            trick_number=1,
            round_number=1,
            game_id="test",
            legal_moves=(PassRob(),),
        )
        player = HeuristicPlayer()
        move = player.choose_move(state)
        assert isinstance(move, PassRob)

    def test_confirm_round_end(self) -> None:
        engine = make_engine()
        advance_to_round_end(engine)
        state = engine.get_state()
        assert state.phase == Phase.ROUND_END

        player = HeuristicPlayer()
        move = player.choose_move(state)
        assert isinstance(move, ConfirmRoundEnd)


class TestHeuristicPlayerLead:
    def _get_lead_state(self, seed: int = 0) -> tuple[GameEngine, object]:
        """Return an engine+state where it's a player's turn to lead."""
        for s in range(seed, seed + 500):
            random.seed(s)
            engine = GameEngine(["P1", "P2", "P3"], audit_dir=None)
            advance_to_trick_phase(engine)
            state = engine.get_state()
            if state.phase == Phase.TRICK and not state.current_trick:
                return engine, state
        raise RuntimeError("Could not find a leading state")  # pragma: no cover

    def test_leads_weakest_non_trump_by_default(self) -> None:
        """With no danger player, leads the weakest non-trump card."""
        _, state = self._get_lead_state()
        assert state.trump_suit is not None

        # Ensure no player is at >= 20 pts (freshly dealt — all at 0)
        assert all(p.score < 20 for p in state.players)

        legal_cards = [m.card for m in state.legal_moves if isinstance(m, PlayCard)]
        non_trumps = [c for c in legal_cards if not is_trump(c, state.trump_suit)]

        player = HeuristicPlayer()
        move = player.choose_move(state)
        assert isinstance(move, PlayCard)

        if non_trumps:
            # Should play from non-trumps and should be the weakest one
            assert not is_trump(move.card, state.trump_suit)
            worst_rank = max(card_global_rank(c, state.trump_suit) for c in non_trumps)
            assert card_global_rank(move.card, state.trump_suit) == worst_rank

    def test_leads_best_trump_when_danger_player_present(self) -> None:
        """When an opponent is at >= 20 points, leads the strongest trump."""
        _, state = self._get_lead_state()
        assert state.trump_suit is not None

        # Artificially inflate an opponent's score in the snapshot — we do
        # this by constructing the state directly with a modified copy.
        # Simpler: just verify the branch logic via choosing a state where
        # we can set up a danger scenario with the engine.
        #
        # We drive an engine to a state where someone has >= 20 pts
        # by auto-playing a few rounds first.
        for seed in range(500):
            random.seed(seed)
            engine = GameEngine(["P1", "P2", "P3"], audit_dir=None)
            # Play through rounds until someone has >= 20 pts and it's a lead
            for _ in range(200):
                if engine.is_game_over:
                    break
                s = engine.get_state()
                if (
                    s.phase == Phase.TRICK
                    and not s.current_trick
                    and any(
                        p.name != s.current_player.name and p.score >= 20
                        for p in s.players
                    )
                ):
                    # Found our target state
                    legal_cards = [m.card for m in s.legal_moves if isinstance(m, PlayCard)]
                    trumps = [c for c in legal_cards if is_trump(c, s.trump_suit)]
                    ai = HeuristicPlayer()
                    move = ai.choose_move(s)
                    assert isinstance(move, PlayCard)
                    if trumps:
                        # Should lead strongest trump
                        best_rank = min(
                            card_global_rank(c, s.trump_suit) for c in trumps
                        )
                        assert card_global_rank(move.card, s.trump_suit) == best_rank
                    return  # test passed
                engine.apply_move(s.legal_moves[0])
        pytest.skip("Could not reach a danger-player lead scenario in 500 seeds")


class TestHeuristicPlayerFollow:
    def _advance_to_mid_trick(
        self, engine: GameEngine
    ) -> None:
        """Play one card into the current trick so a second player has to follow."""
        advance_to_trick_phase(engine)
        state = engine.get_state()
        assert state.phase == Phase.TRICK
        # Play the first legal card to start the trick
        engine.apply_move(state.legal_moves[0])

    def test_follow_wins_without_five(self) -> None:
        """When non-Five winners exist, plays the weakest one (not the Five)."""
        for seed in range(500):
            random.seed(seed)
            engine = GameEngine(["P1", "P2", "P3"], audit_dir=None)
            self._advance_to_mid_trick(engine)
            state = engine.get_state()
            if state.phase != Phase.TRICK or not state.current_trick:
                continue
            assert state.trump_suit is not None

            legal_cards = [m.card for m in state.legal_moves if isinstance(m, PlayCard)]
            my_name = state.current_player.name
            led_suit = state.current_trick[0].card.suit
            five = Card(Rank.FIVE, state.trump_suit)

            # Find non-Five winners
            from twentyfive.game.rules import trick_winner
            from twentyfive.game.state import TrickPlay

            non_five_winners = []
            for card in legal_cards:
                if card == five:
                    continue
                hyp = list(state.current_trick) + [TrickPlay(my_name, card)]
                if trick_winner(hyp, led_suit, state.trump_suit).player_name == my_name:
                    non_five_winners.append(card)

            if not non_five_winners:
                continue  # try next seed

            ai = HeuristicPlayer()
            move = ai.choose_move(state)
            assert isinstance(move, PlayCard)
            # Should pick from non-Five winners, and it should be the weakest
            assert move.card in non_five_winners
            worst = max(
                card_global_rank(c, state.trump_suit) for c in non_five_winners
            )
            assert card_global_rank(move.card, state.trump_suit) == worst
            return  # test passed
        pytest.skip("Could not find a suitable follow state")  # pragma: no cover

    def test_follow_weakest_when_cannot_win(self) -> None:
        """Plays the weakest legal card when no winning card exists."""
        for seed in range(500):
            random.seed(seed)
            engine = GameEngine(["P1", "P2", "P3"], audit_dir=None)
            self._advance_to_mid_trick(engine)
            state = engine.get_state()
            if state.phase != Phase.TRICK or not state.current_trick:
                continue
            assert state.trump_suit is not None

            legal_cards = [m.card for m in state.legal_moves if isinstance(m, PlayCard)]
            my_name = state.current_player.name
            led_suit = state.current_trick[0].card.suit

            from twentyfive.game.rules import trick_winner
            from twentyfive.game.state import TrickPlay

            winners = []
            for card in legal_cards:
                hyp = list(state.current_trick) + [TrickPlay(my_name, card)]
                if trick_winner(hyp, led_suit, state.trump_suit).player_name == my_name:
                    winners.append(card)

            if winners:
                continue  # can win; not what we're testing

            ai = HeuristicPlayer()
            move = ai.choose_move(state)
            assert isinstance(move, PlayCard)
            # Should be the weakest legal card
            worst_rank = max(card_global_rank(c, state.trump_suit) for c in legal_cards)
            assert card_global_rank(move.card, state.trump_suit) == worst_rank
            return  # test passed
        pytest.skip("Could not find a no-winner follow state")  # pragma: no cover

    def test_follow_uses_five_for_danger_player(self) -> None:
        """Five is played when a danger player (>=20 pts) is winning and Five is the only winner."""
        for seed in range(2000):
            random.seed(seed)
            engine = GameEngine(["P1", "P2", "P3"], audit_dir=None)
            # Advance multiple rounds to get someone near winning
            for _ in range(300):
                if engine.is_game_over:
                    break
                s = engine.get_state()
                if s.phase == Phase.TRICK and s.current_trick:
                    assert s.trump_suit is not None
                    my_name = s.current_player.name
                    five = Card(Rank.FIVE, s.trump_suit)
                    legal_cards = [m.card for m in s.legal_moves if isinstance(m, PlayCard)]

                    # Need: five in hand, danger player winning, five is only winner
                    danger_players = {
                        p.name for p in s.players
                        if p.name != my_name and p.score >= 20
                    }
                    if not danger_players or five not in legal_cards:
                        engine.apply_move(s.legal_moves[0])
                        continue

                    led_suit = s.current_trick[0].card.suit
                    from twentyfive.game.rules import trick_winner
                    from twentyfive.game.state import TrickPlay

                    current_winner = trick_winner(list(s.current_trick), led_suit, s.trump_suit)
                    if current_winner.player_name not in danger_players:
                        engine.apply_move(s.legal_moves[0])
                        continue

                    # Check five is a winner
                    hyp = list(s.current_trick) + [TrickPlay(my_name, five)]
                    if trick_winner(hyp, led_suit, s.trump_suit).player_name != my_name:
                        engine.apply_move(s.legal_moves[0])
                        continue

                    # Check no non-Five winner exists
                    non_five_winners = []
                    for card in legal_cards:
                        if card == five:
                            continue
                        h = list(s.current_trick) + [TrickPlay(my_name, card)]
                        if trick_winner(h, led_suit, s.trump_suit).player_name == my_name:
                            non_five_winners.append(card)
                    if non_five_winners:
                        engine.apply_move(s.legal_moves[0])
                        continue

                    # Perfect — Five is the only winning card vs danger player
                    ai = HeuristicPlayer()
                    move = ai.choose_move(s)
                    assert isinstance(move, PlayCard)
                    assert move.card == five
                    return  # test passed

                engine.apply_move(s.legal_moves[0])
        pytest.skip("Could not find a Five-vs-danger-player state in 2000 seeds")

    def test_move_is_always_legal(self) -> None:
        """HeuristicPlayer always returns a move from legal_moves."""
        for seed in range(50):
            random.seed(seed)
            engine = GameEngine(["P1", "P2", "P3"], audit_dir=None)
            ai = HeuristicPlayer()
            moves_played = 0
            while not engine.is_game_over and moves_played < 100:
                state = engine.get_state()
                move = ai.choose_move(state)
                assert move in state.legal_moves, (
                    f"Seed {seed}: AI returned {move!r} which is not in legal_moves"
                )
                engine.apply_move(move)
                moves_played += 1
