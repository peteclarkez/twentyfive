"""
Tests for the --ui module loader and the cli.launch() entry point.

Coverage:
  - cli.launch() invokes CLI.run() and passes show_all correctly
  - Every built-in UI module exports launch()
  - --ui with an unknown module exits 1 with a helpful message
  - --ui with a module that has no launch() exits 1 with a helpful message
"""

from __future__ import annotations

import importlib
import random
import subprocess
import sys
from unittest.mock import patch

from twentyfive.ai.player import RandomPlayer
from twentyfive.game.engine import GameEngine
from twentyfive.ui.controller import GameController

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_all_ai_controller(n: int = 3, seed: int = 0) -> GameController:
    random.seed(seed)
    engine = GameEngine(player_names=[f"P{i + 1}" for i in range(n)], audit_dir=None)
    names = [p.name for p in engine.get_state().players]
    return GameController(engine, {name: RandomPlayer() for name in names})


def _run_main(*extra: str) -> subprocess.CompletedProcess[str]:
    """Run __main__ via subprocess using --1v3 to skip interactive prompts."""
    return subprocess.run(
        [sys.executable, "-m", "twentyfive", "--1v3", "Tester", *extra],
        capture_output=True,
        text=True,
    )


# ---------------------------------------------------------------------------
# cli.launch()
# ---------------------------------------------------------------------------


class TestCliLaunch:
    def test_launch_invokes_cli_run(self) -> None:
        from twentyfive.ui import cli as cli_mod

        ctrl = _make_all_ai_controller()
        with patch.object(cli_mod.CLI, "run") as mock_run:
            cli_mod.launch(ctrl, show_all=False)
        mock_run.assert_called_once()

    def test_launch_passes_show_all_false(self) -> None:
        from twentyfive.ui import cli as cli_mod

        ctrl = _make_all_ai_controller()
        captured: list[bool] = []
        real_init = cli_mod.CLI.__init__

        def spy_init(self, controller, *, show_all: bool = False) -> None:  # type: ignore[override]
            captured.append(show_all)
            real_init(self, controller, show_all=show_all)

        with patch.object(cli_mod.CLI, "__init__", spy_init):
            with patch.object(cli_mod.CLI, "run"):
                cli_mod.launch(ctrl, show_all=False)
        assert captured == [False]

    def test_launch_passes_show_all_true(self) -> None:
        from twentyfive.ui import cli as cli_mod

        ctrl = _make_all_ai_controller()
        captured: list[bool] = []
        real_init = cli_mod.CLI.__init__

        def spy_init(self, controller, *, show_all: bool = False) -> None:  # type: ignore[override]
            captured.append(show_all)
            real_init(self, controller, show_all=show_all)

        with patch.object(cli_mod.CLI, "__init__", spy_init):
            with patch.object(cli_mod.CLI, "run"):
                cli_mod.launch(ctrl, show_all=True)
        assert captured == [True]


# ---------------------------------------------------------------------------
# Built-in UI modules expose launch()
# ---------------------------------------------------------------------------


class TestBuiltinUiModules:
    def test_cli_has_launch(self) -> None:
        mod = importlib.import_module("twentyfive.ui.cli")
        assert callable(getattr(mod, "launch", None))

    def test_pygame_ui_has_launch(self) -> None:
        mod = importlib.import_module("twentyfive.ui.pygame_ui")
        assert callable(getattr(mod, "launch", None))


# ---------------------------------------------------------------------------
# --ui loader error paths  (subprocess — no interactive input needed)
# ---------------------------------------------------------------------------


class TestUiLoaderErrors:
    def test_unknown_module_exits_nonzero(self) -> None:
        result = _run_main("--ui", "nonexistent_ui_xyz")
        assert result.returncode == 1

    def test_unknown_module_names_the_module(self) -> None:
        result = _run_main("--ui", "nonexistent_ui_xyz")
        assert "nonexistent_ui_xyz" in result.stdout

    def test_unknown_module_lists_builtins(self) -> None:
        result = _run_main("--ui", "nonexistent_ui_xyz")
        assert "cli" in result.stdout
        assert "pygame_ui" in result.stdout

    def test_module_without_launch_exits_nonzero(self) -> None:
        # 'controller' lives under twentyfive/ui/ but has no launch()
        result = _run_main("--ui", "controller")
        assert result.returncode == 1

    def test_module_without_launch_prints_error(self) -> None:
        result = _run_main("--ui", "controller")
        assert "launch()" in result.stdout
        assert "controller" in result.stdout
