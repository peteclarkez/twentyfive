"""Tests for GameController."""

from __future__ import annotations

import random

import pytest

from twentyfive.ai.player import RandomPlayer
from twentyfive.game.engine import GameEngine
from twentyfive.game.state import ConfirmRoundEnd, PassRob, Phase
from twentyfive.ui.controller import GameController


def make_engine(n: int = 3, seed: int = 42) -> GameEngine:
    random.seed(seed)
    return GameEngine(player_names=[f"P{i + 1}" for i in range(n)], audit_dir=None)


def advance_past_rob(engine: GameEngine) -> None:
    while not engine.is_game_over:
        s = engine.get_state()
        if s.phase != Phase.ROB:
            break
        engine.apply_move(PassRob())


# ---------------------------------------------------------------------------
# is_ai_turn
# ---------------------------------------------------------------------------


class TestIsAiTurn:
    def test_no_ai_is_never_ai_turn(self) -> None:
        ctrl = GameController(make_engine())
        assert ctrl.is_ai_turn() is False

    def test_all_ai_is_always_ai_turn(self) -> None:
        engine = make_engine()
        names = [p.name for p in engine.get_state().players]
        ai = {n: RandomPlayer() for n in names}
        ctrl = GameController(engine, ai_players=ai)
        assert ctrl.is_ai_turn() is True

    def test_ai_turn_only_for_current_player(self) -> None:
        engine = make_engine()
        state = engine.get_state()
        current = state.current_player.name
        others = [p.name for p in state.players if p.name != current]
        # Register AI for everyone except the current player
        ctrl = GameController(engine, ai_players={n: RandomPlayer() for n in others})
        assert ctrl.is_ai_turn() is False


# ---------------------------------------------------------------------------
# step_ai
# ---------------------------------------------------------------------------


class TestStepAi:
    def test_step_ai_returns_actor_move_and_state(self) -> None:
        engine = make_engine()
        names = [p.name for p in engine.get_state().players]
        ctrl = GameController(engine, ai_players={n: RandomPlayer() for n in names})
        before = ctrl.state
        actor, move, after = ctrl.step_ai()
        assert actor == before.current_player.name
        assert move in before.legal_moves
        assert after is not before

    def test_step_ai_advances_state(self) -> None:
        engine = make_engine()
        names = [p.name for p in engine.get_state().players]
        ctrl = GameController(engine, ai_players={n: RandomPlayer() for n in names})
        before = ctrl.state
        ctrl.step_ai()
        after = ctrl.state
        # State has moved on (different object reference from get_state())
        assert after is not before

    def test_step_ai_raises_on_human_turn(self) -> None:
        ctrl = GameController(make_engine())
        with pytest.raises(RuntimeError, match="human player"):
            ctrl.step_ai()

    def test_step_ai_completes_full_ai_game(self) -> None:
        engine = make_engine(seed=0)
        names = [p.name for p in engine.get_state().players]
        ctrl = GameController(engine, ai_players={n: RandomPlayer() for n in names})
        moves = 0
        while not ctrl.is_game_over and moves < 300:
            ctrl.step_ai()
            moves += 1
        assert ctrl.is_game_over


# ---------------------------------------------------------------------------
# apply_move
# ---------------------------------------------------------------------------


class TestApplyMove:
    def test_apply_move_advances_state(self) -> None:
        engine = make_engine()
        advance_past_rob(engine)
        ctrl = GameController(engine)
        before = ctrl.state
        assert before.phase == Phase.TRICK
        move = before.legal_moves[0]
        after = ctrl.apply_move(move)
        assert after is not before

    def test_apply_move_returns_new_state(self) -> None:
        engine = make_engine()
        advance_past_rob(engine)
        ctrl = GameController(engine)
        state = ctrl.state
        new_state = ctrl.apply_move(state.legal_moves[0])
        # new_state is a fresh GameState snapshot
        assert isinstance(new_state.phase, Phase)

    def test_apply_move_raises_on_illegal_move(self) -> None:
        engine = make_engine()
        advance_past_rob(engine)
        ctrl = GameController(engine)
        state = ctrl.state
        assert state.phase == Phase.TRICK
        # ConfirmRoundEnd is only legal in ROUND_END phase
        with pytest.raises(ValueError):
            ctrl.apply_move(ConfirmRoundEnd())


# ---------------------------------------------------------------------------
# human_players
# ---------------------------------------------------------------------------


class TestHumanPlayers:
    def test_no_ai_all_human(self) -> None:
        engine = make_engine(n=3)
        ctrl = GameController(engine)
        assert ctrl.human_players == frozenset({"P1", "P2", "P3"})

    def test_all_ai_no_human(self) -> None:
        engine = make_engine(n=3)
        names = [p.name for p in engine.get_state().players]
        ctrl = GameController(engine, ai_players={n: RandomPlayer() for n in names})
        assert ctrl.human_players == frozenset()

    def test_mixed_human_and_ai(self) -> None:
        engine = make_engine(n=3)
        ctrl = GameController(engine, ai_players={"P1": RandomPlayer()})
        assert ctrl.human_players == frozenset({"P2", "P3"})


# ---------------------------------------------------------------------------
# state / is_game_over properties
# ---------------------------------------------------------------------------


class TestProperties:
    def test_state_returns_game_state(self) -> None:
        from twentyfive.game.state import GameState
        ctrl = GameController(make_engine())
        assert isinstance(ctrl.state, GameState)

    def test_is_game_over_false_initially(self) -> None:
        ctrl = GameController(make_engine())
        assert ctrl.is_game_over is False
