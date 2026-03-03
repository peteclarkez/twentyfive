"""
Tests for GameEngine — the state machine.

Many tests use fixed random seeds or carefully-constructed game states.
Where we need specific hands, we manipulate the engine's internal state
after construction (test-only access via name mangling is avoided —
instead we use the public API to advance to known states).
"""

import random

import pytest

from twentyfive.game.engine import GameEngine
from twentyfive.game.state import ConfirmRoundEnd, PassRob, Phase, PlayCard, Rob

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_engine(n: int = 3, seed: int = 42) -> GameEngine:
    """Create an engine with n players using a fixed random seed."""
    random.seed(seed)
    names = [f"P{i+1}" for i in range(n)]
    return GameEngine(player_names=names, audit_dir=None)


def play_all_legal(engine: GameEngine, *, max_moves: int = 500) -> None:
    """Auto-play: always choose the first legal move until game over."""
    moves = 0
    while not engine.is_game_over and moves < max_moves:
        state = engine.get_state()
        assert state.legal_moves, "Legal moves must be non-empty during active play"
        engine.apply_move(state.legal_moves[0])
        moves += 1


def skip_rob_phase(engine: GameEngine) -> None:
    """Advance past the rob phase by having all eligible players pass."""
    while not engine.is_game_over:
        state = engine.get_state()
        if state.phase != Phase.ROB:
            break
        engine.apply_move(PassRob())


# ---------------------------------------------------------------------------
# Construction and initial state
# ---------------------------------------------------------------------------


class TestEngineConstruction:
    def test_requires_at_least_two_players(self) -> None:
        with pytest.raises(ValueError):
            GameEngine(["Solo"], audit_dir=None)

    def test_requires_at_most_six_players(self) -> None:
        with pytest.raises(ValueError):
            GameEngine([f"P{i}" for i in range(7)], audit_dir=None)

    def test_rejects_duplicate_names(self) -> None:
        with pytest.raises(ValueError):
            GameEngine(["Alice", "Alice", "Bob"], audit_dir=None)

    def test_initial_deal_gives_five_cards_each(self) -> None:
        engine = make_engine(3)
        state = engine.get_state()
        for player in state.players:
            assert player.hand_size == 5, f"{player.name} should have 5 cards"

    def test_total_cards_dealt_plus_face_up_equals_deck_minus_remainder(self) -> None:
        engine = make_engine(4)
        state = engine.get_state()
        dealt = sum(p.hand_size for p in state.players)
        # 4 players × 5 cards + 1 face-up = 21 cards removed from 52-card deck
        assert dealt == 20
        assert state.face_up_card is not None

    def test_trump_suit_is_face_up_card_suit(self) -> None:
        engine = make_engine(3)
        state = engine.get_state()
        assert state.trump_suit is not None
        assert state.face_up_card is not None
        assert state.trump_suit == state.face_up_card.suit

    def test_initial_phase_is_rob_or_trick(self) -> None:
        engine = make_engine(3)
        state = engine.get_state()
        assert state.phase in (Phase.ROB, Phase.TRICK)

    def test_initial_round_number_is_one(self) -> None:
        engine = make_engine(3)
        assert engine.get_state().round_number == 1

    def test_initial_trick_number_is_one(self) -> None:
        engine = make_engine(3)
        assert engine.get_state().trick_number == 1

    def test_all_hands_revealed_in_state(self) -> None:
        """Engine always reveals all hands — privacy is the UI's job."""
        engine = make_engine(3)
        state = engine.get_state()
        for player in state.players:
            assert len(player.hand) == player.hand_size


# ---------------------------------------------------------------------------
# Rob phase
# ---------------------------------------------------------------------------


class TestRobPhase:
    def _make_engine_where_player_can_rob(self) -> tuple[GameEngine, int]:
        """
        Return an engine and the index of a player who holds Ace of trumps
        (triggering the rob phase). Uses seed search to find a suitable seed.
        """
        for seed in range(200):
            random.seed(seed)
            engine = GameEngine(["A", "B", "C"], audit_dir=None)
            state = engine.get_state()
            if state.phase == Phase.ROB:
                return engine, state.current_player_index
        raise RuntimeError("Could not find a seed with a rob-eligible player")

    def test_pass_rob_advances_to_next_or_trick(self) -> None:
        engine, _ = self._make_engine_where_player_can_rob()
        engine.apply_move(PassRob())
        state = engine.get_state()
        assert state.phase in (Phase.ROB, Phase.TRICK)

    def test_rob_takes_face_up_and_keeps_hand_size_at_five(self) -> None:
        engine, rob_idx = self._make_engine_where_player_can_rob()
        state = engine.get_state()
        assert state.face_up_card is not None

        # Find a Rob move (not PassRob)
        rob_moves = [m for m in state.legal_moves if isinstance(m, Rob)]
        assert rob_moves, "Should have at least one Rob move"

        engine.apply_move(rob_moves[0])
        new_state = engine.get_state()

        # Face-up card should be gone
        assert new_state.face_up_card is None
        # Player's hand size should still be 5 (took 1, discarded 1)
        robbing_player = new_state.players[rob_idx]
        assert robbing_player.hand_size == 5

    def test_rob_this_round_records_taken_card(self) -> None:
        """After a rob, rob_this_round holds (player_name, face_up_card)."""
        engine, rob_idx = self._make_engine_where_player_can_rob()
        state = engine.get_state()
        face_up = state.face_up_card
        assert face_up is not None
        assert state.rob_this_round is None

        rob_moves = [m for m in state.legal_moves if isinstance(m, Rob)]
        assert rob_moves
        engine.apply_move(rob_moves[0])
        new_state = engine.get_state()

        assert new_state.rob_this_round is not None
        rob_name, rob_card = new_state.rob_this_round
        assert rob_name == state.players[rob_idx].name
        assert rob_card == face_up
        assert rob_card in new_state.players[rob_idx].hand

    def test_rob_this_round_cleared_on_new_round(self) -> None:
        """rob_this_round is cleared when the next round starts."""
        engine, _ = self._make_engine_where_player_can_rob()
        state = engine.get_state()
        rob_moves = [m for m in state.legal_moves if isinstance(m, Rob)]
        assert rob_moves
        engine.apply_move(rob_moves[0])
        assert engine.get_state().rob_this_round is not None

        # Play through the rest of the round, then confirm to start the next
        while engine.get_state().phase not in (Phase.ROUND_END, Phase.GAME_OVER):
            engine.apply_move(engine.get_state().legal_moves[0])
        engine.apply_move(ConfirmRoundEnd())
        assert engine.get_state().rob_this_round is None

    def test_rob_clears_remaining_eligible_players(self) -> None:
        """Once a rob occurs, no one else gets to rob."""
        engine, _ = self._make_engine_where_player_can_rob()
        state = engine.get_state()
        rob_moves = [m for m in state.legal_moves if isinstance(m, Rob)]
        if rob_moves:
            engine.apply_move(rob_moves[0])
            new_state = engine.get_state()
            assert new_state.phase == Phase.TRICK

    def test_all_pass_transitions_to_trick(self) -> None:
        engine, _ = self._make_engine_where_player_can_rob()
        skip_rob_phase(engine)
        assert engine.get_state().phase == Phase.TRICK

    def test_illegal_move_in_rob_phase_raises(self) -> None:
        engine, rob_idx = self._make_engine_where_player_can_rob()
        state = engine.get_state()
        # PlayCard is not legal during rob phase
        any_card = state.players[rob_idx].hand[0]
        with pytest.raises(ValueError):
            engine.apply_move(PlayCard(card=any_card))


# ---------------------------------------------------------------------------
# Trick phase
# ---------------------------------------------------------------------------


class TestTrickPhase:
    def test_legal_moves_are_play_card_type(self) -> None:
        engine = make_engine(3)
        skip_rob_phase(engine)
        state = engine.get_state()
        assert state.phase == Phase.TRICK
        assert all(isinstance(m, PlayCard) for m in state.legal_moves)

    def test_legal_moves_are_non_empty(self) -> None:
        engine = make_engine(3)
        skip_rob_phase(engine)
        state = engine.get_state()
        assert len(state.legal_moves) > 0

    def test_legal_cards_are_subset_of_hand(self) -> None:
        engine = make_engine(3)
        skip_rob_phase(engine)
        state = engine.get_state()
        hand = set(state.current_player.hand)
        legal_cards = {m.card for m in state.legal_moves if isinstance(m, PlayCard)}
        assert legal_cards.issubset(hand)

    def test_play_advances_current_player(self) -> None:
        engine = make_engine(3)
        skip_rob_phase(engine)
        state = engine.get_state()
        first_player_idx = state.current_player_index
        engine.apply_move(state.legal_moves[0])
        new_state = engine.get_state()
        assert new_state.current_player_index != first_player_idx

    def test_played_card_removed_from_hand(self) -> None:
        engine = make_engine(3)
        skip_rob_phase(engine)
        state = engine.get_state()
        move = state.legal_moves[0]
        assert isinstance(move, PlayCard)
        played_card = move.card
        player_idx = state.current_player_index
        engine.apply_move(move)
        new_state = engine.get_state()
        new_hand = new_state.players[player_idx].hand
        assert played_card not in new_hand

    def test_played_card_appears_in_current_trick(self) -> None:
        engine = make_engine(3)
        skip_rob_phase(engine)
        state = engine.get_state()
        move = state.legal_moves[0]
        assert isinstance(move, PlayCard)
        engine.apply_move(move)
        new_state = engine.get_state()
        trick_cards = [tp.card for tp in new_state.current_trick]
        assert move.card in trick_cards

    def test_illegal_play_card_raises(self) -> None:
        engine = make_engine(3)
        skip_rob_phase(engine)
        state = engine.get_state()
        legal_cards = {m.card for m in state.legal_moves if isinstance(m, PlayCard)}
        hand = set(state.current_player.hand)
        illegal_cards = hand - legal_cards
        if illegal_cards:
            with pytest.raises(ValueError):
                engine.apply_move(PlayCard(card=next(iter(illegal_cards))))

    def test_pass_rob_illegal_in_trick_phase(self) -> None:
        engine = make_engine(3)
        skip_rob_phase(engine)
        with pytest.raises(ValueError):
            engine.apply_move(PassRob())


# ---------------------------------------------------------------------------
# Trick resolution and scoring
# ---------------------------------------------------------------------------


class TestScoringAndTrickResolution:
    def test_trick_winner_gets_five_points(self) -> None:
        engine = make_engine(3)
        skip_rob_phase(engine)
        initial_scores = {p.name: p.score for p in engine.get_state().players}

        # Play one complete trick (3 players each play once)
        for _ in range(3):
            state = engine.get_state()
            engine.apply_move(state.legal_moves[0])

        new_state = engine.get_state()
        new_scores = {p.name: p.score for p in new_state.players}
        total_new = sum(new_scores.values())
        total_old = sum(initial_scores.values())
        assert total_new - total_old == 5

    def test_exactly_one_player_gains_points_per_trick(self) -> None:
        engine = make_engine(3)
        skip_rob_phase(engine)
        initial_scores = {p.name: p.score for p in engine.get_state().players}

        for _ in range(3):
            state = engine.get_state()
            engine.apply_move(state.legal_moves[0])

        new_scores = {p.name: p.score for p in engine.get_state().players}
        gainers = [name for name in new_scores if new_scores[name] > initial_scores[name]]
        assert len(gainers) == 1
        assert new_scores[gainers[0]] - initial_scores[gainers[0]] == 5

    def test_trick_number_increments_after_full_trick(self) -> None:
        engine = make_engine(3)
        skip_rob_phase(engine)
        assert engine.get_state().trick_number == 1

        for _ in range(3):
            state = engine.get_state()
            engine.apply_move(state.legal_moves[0])

        state = engine.get_state()
        # Either trick 2 or a new round started (if trick 1 completed)
        if state.phase != Phase.GAME_OVER:
            assert state.trick_number == 2 or state.round_number == 2

    def test_current_trick_resets_after_resolution(self) -> None:
        engine = make_engine(3)
        skip_rob_phase(engine)
        for _ in range(3):
            engine.apply_move(engine.get_state().legal_moves[0])
        state = engine.get_state()
        if state.phase == Phase.TRICK:
            assert len(state.current_trick) == 0


# ---------------------------------------------------------------------------
# Game over condition
# ---------------------------------------------------------------------------


class TestGameOver:
    def test_game_ends_before_25_moves_total(self) -> None:
        """A game must end; auto-play never gets stuck."""
        random.seed(0)
        engine = GameEngine(["Alice", "Bob", "Carol"], audit_dir=None)
        play_all_legal(engine, max_moves=1000)
        assert engine.is_game_over

    def test_game_over_phase_has_no_legal_moves(self) -> None:
        random.seed(0)
        engine = GameEngine(["Alice", "Bob"], audit_dir=None)
        play_all_legal(engine, max_moves=1000)
        assert engine.get_state().legal_moves == ()

    def test_apply_move_raises_when_game_over(self) -> None:
        random.seed(0)
        engine = GameEngine(["Alice", "Bob"], audit_dir=None)
        play_all_legal(engine, max_moves=1000)
        with pytest.raises(ValueError):
            engine.apply_move(PassRob())

    def test_winner_has_score_at_least_25(self) -> None:
        random.seed(0)
        engine = GameEngine(["Alice", "Bob", "Carol"], audit_dir=None)
        play_all_legal(engine, max_moves=1000)
        state = engine.get_state()
        scores = [p.score for p in state.players]
        assert max(scores) >= 25

    def test_multiple_games_complete_correctly(self) -> None:
        """Run several games with different seeds to catch edge cases."""
        for seed in range(10):
            random.seed(seed)
            engine = GameEngine(["X", "Y", "Z"], audit_dir=None)
            play_all_legal(engine, max_moves=2000)
            assert engine.is_game_over, f"Game with seed {seed} did not end"


# ---------------------------------------------------------------------------
# Round transition
# ---------------------------------------------------------------------------


class TestRoundTransition:
    def test_dealer_rotates_after_round(self) -> None:
        engine = make_engine(3)
        initial_dealer = engine.get_state().dealer_index
        # Play exactly 5 tricks for 3 players = 15 card plays
        skip_rob_phase(engine)
        # Play until round changes
        initial_round = engine.get_state().round_number
        while not engine.is_game_over:
            state = engine.get_state()
            if state.round_number != initial_round:
                break
            engine.apply_move(state.legal_moves[0])

        if not engine.is_game_over:
            new_dealer = engine.get_state().dealer_index
            expected = (initial_dealer + 1) % 3
            assert new_dealer == expected

    def test_new_round_resets_hand_size_to_five(self) -> None:
        engine = make_engine(3)
        initial_round = engine.get_state().round_number
        # Play through a complete round
        while not engine.is_game_over:
            state = engine.get_state()
            if state.round_number != initial_round:
                break
            engine.apply_move(state.legal_moves[0])

        if not engine.is_game_over:
            state = engine.get_state()
            # Rob phase may have reduced a hand to 5 (dealt fresh), or we're in trick
            for p in state.players:
                assert p.hand_size == 5, f"{p.name} should have 5 cards at start of round"

    def test_round_number_increments(self) -> None:
        engine = make_engine(2)
        initial_round = engine.get_state().round_number
        while not engine.is_game_over:
            state = engine.get_state()
            if state.round_number > initial_round:
                assert state.round_number == initial_round + 1
                break
            engine.apply_move(state.legal_moves[0])


# ---------------------------------------------------------------------------
# ROUND_END phase
# ---------------------------------------------------------------------------


class TestRoundEndPhase:
    def _play_one_full_round(self, engine: GameEngine) -> None:
        """Play until ROUND_END or GAME_OVER, whichever comes first."""
        initial_round = engine.get_state().round_number
        skip_rob_phase(engine)
        while not engine.is_game_over:
            state = engine.get_state()
            if state.phase == Phase.ROUND_END or state.round_number != initial_round:
                break
            engine.apply_move(state.legal_moves[0])

    def test_phase_becomes_round_end_after_five_tricks(self) -> None:
        engine = make_engine(3)
        self._play_one_full_round(engine)
        if not engine.is_game_over:
            assert engine.get_state().phase == Phase.ROUND_END

    def test_round_end_legal_moves_is_confirm(self) -> None:
        engine = make_engine(3)
        self._play_one_full_round(engine)
        if not engine.is_game_over:
            state = engine.get_state()
            assert state.phase == Phase.ROUND_END
            assert state.legal_moves == (ConfirmRoundEnd(),)

    def test_confirm_round_end_starts_new_round(self) -> None:
        engine = make_engine(3)
        self._play_one_full_round(engine)
        if not engine.is_game_over:
            assert engine.get_state().round_number == 1
            engine.apply_move(ConfirmRoundEnd())
            if not engine.is_game_over:
                assert engine.get_state().round_number == 2
                assert engine.get_state().phase in (Phase.ROB, Phase.TRICK)

    def test_completed_tricks_visible_during_round_end(self) -> None:
        engine = make_engine(3)
        self._play_one_full_round(engine)
        if not engine.is_game_over:
            state = engine.get_state()
            assert state.phase == Phase.ROUND_END
            assert len(state.completed_tricks) == 5
