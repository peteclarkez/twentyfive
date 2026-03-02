"""
Tests for MCTSPlayer and GameEngine.clone().
"""

from __future__ import annotations

import random

import pytest

from twentyfive.ai.mcts import MCTSPlayer
from twentyfive.game.engine import GameEngine
from twentyfive.game.state import ConfirmRoundEnd, Phase, PlayCard

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_engine(n: int = 3, seed: int = 42) -> GameEngine:
    random.seed(seed)
    return GameEngine(player_names=[f"P{i+1}" for i in range(n)], audit_dir=None)


def make_mcts(engine: GameEngine, simulations: int = 20) -> MCTSPlayer:
    """Small simulation count keeps tests fast."""
    return MCTSPlayer(engine, simulations=simulations)


def advance_past_rob(engine: GameEngine) -> None:
    from twentyfive.game.state import PassRob
    while not engine.is_game_over:
        state = engine.get_state()
        if state.phase != Phase.ROB:
            break
        engine.apply_move(PassRob())


# ---------------------------------------------------------------------------
# GameEngine.clone()
# ---------------------------------------------------------------------------


class TestEngineClone:
    def test_clone_produces_independent_engine(self) -> None:
        engine = make_engine()
        clone = engine.clone()

        state_orig = engine.get_state()
        state_clone = clone.get_state()

        assert state_orig.game_id == state_clone.game_id
        assert state_orig.phase == state_clone.phase
        assert state_orig.trump_suit == state_clone.trump_suit

    def test_modifying_clone_does_not_affect_original(self) -> None:
        engine = make_engine()
        clone = engine.clone()

        # Play all moves on the clone
        while not clone.is_game_over:
            s = clone.get_state()
            clone.apply_move(s.legal_moves[0])

        # Original engine should be unchanged (still at move 1)
        state = engine.get_state()
        assert state.phase in (Phase.ROB, Phase.TRICK)
        assert state.trick_number == 1

    def test_clone_has_no_audit(self) -> None:
        """Clone must never write to disk."""
        engine = make_engine()
        clone = engine.clone()
        assert clone._audit is None  # noqa: SLF001

    def test_original_audit_preserved_after_clone(self) -> None:
        """The live engine's audit must be restored after clone()."""
        engine = make_engine()
        original_audit = engine._audit  # noqa: SLF001
        engine.clone()
        assert engine._audit is original_audit  # noqa: SLF001

    def test_clone_hands_are_independent(self) -> None:
        """Mutating a player's hand in the clone must not affect the original."""
        engine = make_engine()
        clone = engine.clone()

        orig_state = engine.get_state()
        orig_hand = set(orig_state.players[0].hand)

        # Advance the clone past the rob phase and play one card
        advance_past_rob(clone)
        clone_state = clone.get_state()
        if clone_state.phase == Phase.TRICK:
            clone.apply_move(clone_state.legal_moves[0])

        # Original player's hand should be unchanged
        assert set(engine.get_state().players[0].hand) == orig_hand


# ---------------------------------------------------------------------------
# MCTSPlayer — basic correctness
# ---------------------------------------------------------------------------


class TestMCTSPlayerLegal:
    def test_always_returns_legal_move_trick_phase(self) -> None:
        engine = make_engine()
        advance_past_rob(engine)
        state = engine.get_state()
        assert state.phase == Phase.TRICK

        player = make_mcts(engine)
        move = player.choose_move(state)
        assert move in state.legal_moves

    def test_always_returns_legal_move_rob_phase(self) -> None:
        for seed in range(200):
            random.seed(seed)
            engine = GameEngine(["P1", "P2", "P3"], audit_dir=None)
            state = engine.get_state()
            if state.phase == Phase.ROB:
                player = make_mcts(engine)
                move = player.choose_move(state)
                assert move in state.legal_moves
                return
        pytest.skip("Could not find a ROB-phase state")

    def test_single_legal_move_returned_without_search(self) -> None:
        """ROUND_END has exactly one legal move — returned immediately."""
        engine = make_engine()
        # Play to round end
        for _ in range(300):
            if engine.is_game_over:
                break
            s = engine.get_state()
            if s.phase == Phase.ROUND_END:
                player = make_mcts(engine)
                move = player.choose_move(s)
                assert isinstance(move, ConfirmRoundEnd)
                return
            engine.apply_move(s.legal_moves[0])
        pytest.skip("Could not reach ROUND_END")

    def test_move_is_always_legal_throughout_game(self) -> None:
        """Run 5 games with all MCTS players; every move must be legal."""
        for seed in range(5):
            random.seed(seed)
            engine = GameEngine(["P1", "P2", "P3"], audit_dir=None)
            player = MCTSPlayer(engine, simulations=10)
            moves_played = 0
            while not engine.is_game_over and moves_played < 150:
                state = engine.get_state()
                move = player.choose_move(state)
                assert move in state.legal_moves, (
                    f"Seed {seed}: MCTSPlayer returned illegal move {move!r}"
                )
                engine.apply_move(move)
                moves_played += 1


# ---------------------------------------------------------------------------
# MCTSPlayer — game completion
# ---------------------------------------------------------------------------


class TestMCTSPlayerGameCompletion:
    def test_all_mcts_game_reaches_game_over(self) -> None:
        """A game with all MCTS players must reach GAME_OVER without error."""
        random.seed(0)
        engine = GameEngine(["P1", "P2", "P3"], audit_dir=None)
        player = MCTSPlayer(engine, simulations=10)
        moves = 0
        while not engine.is_game_over and moves < 500:
            state = engine.get_state()
            engine.apply_move(player.choose_move(state))
            moves += 1
        assert engine.is_game_over, "Game did not reach GAME_OVER"

    def test_mcts_plays_card_not_just_pass(self) -> None:
        """MCTS must return PlayCard (not always ConfirmRoundEnd or PassRob) in trick phase."""
        engine = make_engine()
        advance_past_rob(engine)
        state = engine.get_state()
        assert state.phase == Phase.TRICK

        player = make_mcts(engine)
        move = player.choose_move(state)
        assert isinstance(move, PlayCard)
