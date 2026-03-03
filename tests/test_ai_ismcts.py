"""
Tests for ISMCTSPlayer — smoke tests and determinization correctness.
"""

from __future__ import annotations

import random

import pytest

from twentyfive.ai.ismcts import ISMCTSPlayer
from twentyfive.benchmark import run_benchmark
from twentyfive.game.engine import GameEngine
from twentyfive.game.state import ConfirmRoundEnd, Phase, PlayCard

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_engine(n: int = 3, seed: int = 42) -> GameEngine:
    random.seed(seed)
    return GameEngine(player_names=[f"P{i+1}" for i in range(n)], audit_dir=None)


def make_ismcts(engine: GameEngine, simulations: int = 20) -> ISMCTSPlayer:
    """Small simulation count keeps tests fast."""
    return ISMCTSPlayer(engine, simulations=simulations)


def advance_past_rob(engine: GameEngine) -> None:
    from twentyfive.game.state import PassRob
    while not engine.is_game_over:
        state = engine.get_state()
        if state.phase != Phase.ROB:
            break
        engine.apply_move(PassRob())


# ---------------------------------------------------------------------------
# ISMCTSPlayer — basic correctness
# ---------------------------------------------------------------------------


class TestISMCTSPlayerLegal:
    def test_returns_legal_move_in_trick_phase(self) -> None:
        engine = make_engine()
        advance_past_rob(engine)
        state = engine.get_state()
        assert state.phase == Phase.TRICK

        player = make_ismcts(engine)
        move = player.choose_move(state)
        assert move in state.legal_moves

    def test_returns_legal_move_in_rob_phase(self) -> None:
        for seed in range(200):
            random.seed(seed)
            engine = GameEngine(["P1", "P2", "P3"], audit_dir=None)
            state = engine.get_state()
            if state.phase == Phase.ROB:
                player = make_ismcts(engine)
                move = player.choose_move(state)
                assert move in state.legal_moves
                return
        pytest.skip("Could not find a ROB-phase state")

    def test_single_legal_move_returned_without_search(self) -> None:
        """ROUND_END has exactly one legal move — returned immediately."""
        engine = make_engine()
        for _ in range(300):
            if engine.is_game_over:
                break
            s = engine.get_state()
            if s.phase == Phase.ROUND_END:
                player = make_ismcts(engine)
                move = player.choose_move(s)
                assert isinstance(move, ConfirmRoundEnd)
                return
            engine.apply_move(s.legal_moves[0])
        pytest.skip("Could not reach ROUND_END")

    def test_move_is_always_legal_throughout_game(self) -> None:
        """Run 5 games with all ISMCTS players; every move must be legal."""
        for seed in range(5):
            random.seed(seed)
            engine = GameEngine(["P1", "P2", "P3"], audit_dir=None)
            player = ISMCTSPlayer(engine, simulations=10)
            moves_played = 0
            while not engine.is_game_over and moves_played < 150:
                state = engine.get_state()
                move = player.choose_move(state)
                assert move in state.legal_moves, (
                    f"Seed {seed}: ISMCTSPlayer returned illegal move {move!r}"
                )
                engine.apply_move(move)
                moves_played += 1

    def test_plays_card_not_just_pass(self) -> None:
        """ISMCTS must return PlayCard (not always ConfirmRoundEnd or PassRob) in trick phase."""
        engine = make_engine()
        advance_past_rob(engine)
        state = engine.get_state()
        assert state.phase == Phase.TRICK

        player = make_ismcts(engine)
        move = player.choose_move(state)
        assert isinstance(move, PlayCard)


# ---------------------------------------------------------------------------
# ISMCTSPlayer — game completion
# ---------------------------------------------------------------------------


class TestISMCTSPlayerGameCompletion:
    def test_game_reaches_game_over(self) -> None:
        """A game with all ISMCTS players must reach GAME_OVER without error."""
        random.seed(0)
        engine = GameEngine(["P1", "P2", "P3"], audit_dir=None)
        player = ISMCTSPlayer(engine, simulations=10)
        moves = 0
        while not engine.is_game_over and moves < 500:
            state = engine.get_state()
            engine.apply_move(player.choose_move(state))
            moves += 1
        assert engine.is_game_over, "Game did not reach GAME_OVER"


# ---------------------------------------------------------------------------
# ISMCTSPlayer — determinization correctness
# ---------------------------------------------------------------------------


class TestDeterminization:
    def test_opponent_hand_sizes_match_state(self) -> None:
        """After determinization, each opponent's hand size must match state hand_size."""
        engine = make_engine()
        advance_past_rob(engine)
        state = engine.get_state()
        assert state.phase == Phase.TRICK

        player = ISMCTSPlayer(engine, simulations=5)
        det = player._determinize(state)  # noqa: SLF001
        det_state = det.get_state()

        my_index = state.current_player_index
        for i, (snap, det_snap) in enumerate(zip(state.players, det_state.players)):
            if i == my_index:
                continue
            assert det_snap.hand_size == snap.hand_size, (
                f"Player {i} hand size mismatch: {snap.hand_size} → {det_snap.hand_size}"
            )

    def test_my_hand_unchanged_after_determinization(self) -> None:
        """The current player's hand must be preserved exactly by _determinize."""
        engine = make_engine()
        advance_past_rob(engine)
        state = engine.get_state()
        assert state.phase == Phase.TRICK

        player = ISMCTSPlayer(engine, simulations=5)
        det = player._determinize(state)  # noqa: SLF001
        det_state = det.get_state()

        my_index = state.current_player_index
        my_hand = set(state.players[my_index].hand)
        det_hand = set(det_state.players[my_index].hand)
        assert my_hand == det_hand, (
            f"Current player's hand changed: {my_hand} → {det_hand}"
        )

    def test_determinized_hands_contain_no_known_cards(self) -> None:
        """Opponent hands must not contain any card already known to the AI
        (my hand, played cards, face-up card)."""
        engine = make_engine()
        advance_past_rob(engine)
        state = engine.get_state()
        assert state.phase == Phase.TRICK

        my_index = state.current_player_index
        my_hand = set(state.players[my_index].hand)

        played: set = set()
        for trick in state.completed_tricks:
            for tp in trick:
                played.add(tp.card)
        for tp in state.current_trick:
            played.add(tp.card)

        forbidden = my_hand | played
        if state.face_up_card is not None:
            forbidden.add(state.face_up_card)

        player = ISMCTSPlayer(engine, simulations=5)
        for _ in range(10):  # run multiple determinizations
            det = player._determinize(state)  # noqa: SLF001
            det_state = det.get_state()
            for i, snap in enumerate(det_state.players):
                if i == my_index:
                    continue
                for card in snap.hand:
                    assert card not in forbidden, (
                        f"Player {i} received forbidden card {card}"
                    )

    def test_determinized_all_cards_unique(self) -> None:
        """No card should appear in more than one hand in a determinization."""
        engine = make_engine()
        advance_past_rob(engine)
        state = engine.get_state()
        assert state.phase == Phase.TRICK

        player = ISMCTSPlayer(engine, simulations=5)
        for _ in range(10):
            det = player._determinize(state)  # noqa: SLF001
            det_state = det.get_state()
            all_cards: list = []
            for snap in det_state.players:
                all_cards.extend(snap.hand)
            assert len(all_cards) == len(set(all_cards)), "Duplicate cards found across hands"


# ---------------------------------------------------------------------------
# ISMCTSPlayer — benchmark integration
# ---------------------------------------------------------------------------


class TestISMCTSInBenchmark:
    def test_ismcts_in_benchmark(self) -> None:
        """ISMCTS must complete 1 game via the benchmark framework."""
        random.seed(0)
        stats = run_benchmark(n_games=1, ai_types=["random", "ismcts"], simulations=5, quiet=True)
        assert stats["ismcts"].games == 1
