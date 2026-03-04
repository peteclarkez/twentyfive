from __future__ import annotations

import argparse
import importlib
import random
import sys

from twentyfive.ai.enhanced_heuristic import EnhancedHeuristicPlayer
from twentyfive.ai.heuristic import HeuristicPlayer
from twentyfive.ai.ismcts import ISMCTSPlayer
from twentyfive.ai.player import AIPlayer, RandomPlayer
from twentyfive.game.engine import GameEngine
from twentyfive.ui.controller import GameController

_NAME_BANK = [
    "Alice",
    "Bob",
    "Carol",
    "Dave",
    "Eve",
    "Frank",
    "Grace",
    "Hank",
    "Iris",
    "Jack",
    "Kate",
    "Leo",
    "Mia",
    "Ned",
    "Olive",
    "Pete",
    "Quinn",
    "Rose",
    "Sam",
    "Tara",
]

_DEFAULT_PLAYER_COUNT = 4


def _prompt_player_count() -> int:
    while True:
        raw = input(f"How many players? (2-6) [{_DEFAULT_PLAYER_COUNT}]: ").strip()
        if not raw:
            return _DEFAULT_PLAYER_COUNT
        try:
            n = int(raw)
            if 2 <= n <= 6:
                return n
        except ValueError:
            pass
        print("Please enter a number between 2 and 6.")


def _prompt_player_names(n: int) -> list[str]:
    defaults = random.sample(_NAME_BANK, min(n, len(_NAME_BANK)))
    names: list[str] = []
    for i in range(n):
        default = defaults[i] if i < len(defaults) else f"Player {i + 1}"
        raw = input(f"Player {i + 1} name [{default}]: ").strip()
        names.append(raw if raw else default)
    return names


def _prompt_ai_players(names: list[str], engine: GameEngine) -> dict[str, AIPlayer]:
    """For each player, ask whether they are human or AI. Returns AI players only."""
    ai_players: dict[str, AIPlayer] = {}
    print("Player types:  [H] Human  [R] Random AI  [A] Heuristic AI  [E] Enhanced AI  [M] ISMCTS")
    print()
    for name in names:
        while True:
            raw = input(f"  {name}: (H/R/A/E/M) [E]: ").strip().upper()
            if not raw or raw == "E":
                ai_players[name] = EnhancedHeuristicPlayer()
                break
            if raw == "H":
                break
            if raw == "R":
                ai_players[name] = RandomPlayer()
                break
            if raw == "A":
                ai_players[name] = HeuristicPlayer()
                break
            if raw == "M":
                ai_players[name] = ISMCTSPlayer(engine)
                break
            print("  Please enter H, R, A, E, or M.")
    return ai_players


def _build_player_types(names: list[str], ai_players: dict[str, AIPlayer]) -> dict[str, str]:
    result: dict[str, str] = {}
    for name in names:
        player = ai_players.get(name)
        match player:
            case None:
                result[name] = "Human"
            case ISMCTSPlayer():
                result[name] = "ISMCTS AI"
            case EnhancedHeuristicPlayer():
                result[name] = "Enhanced AI"
            case HeuristicPlayer():
                result[name] = "Heuristic AI"
            case _:
                result[name] = "Random AI"
    return result


def _ai_player_from_type_str(type_str: str, engine: GameEngine) -> AIPlayer | None:
    """Convert a type label (from setup_game) to an AIPlayer, or None for Human."""
    match type_str:
        case "Human":
            return None
        case "Random":
            return RandomPlayer()
        case "Heuristic":
            return HeuristicPlayer()
        case "ISMCTS":
            return ISMCTSPlayer(engine)
        case _:  # "Enhanced" or anything unknown
            return EnhancedHeuristicPlayer()


def _setup_quick_1v3(
    human_name: str,
) -> tuple[GameEngine, dict[str, AIPlayer], list[str]]:
    """
    Build a 4-player game: human vs 3 Enhanced AI opponents.

    The human's seat and the first dealer are both chosen at random.
    Returns (engine, ai_players_dict, ordered_player_names).
    """
    available = [n for n in _NAME_BANK if n.lower() != human_name.lower()]
    ai_names = random.sample(available, 3)

    all_names = ai_names + [human_name]
    random.shuffle(all_names)  # randomise seat order (human position is random)

    initial_dealer = random.randrange(4)
    engine = GameEngine(player_names=all_names, initial_dealer=initial_dealer)
    ai_players: dict[str, AIPlayer] = {name: EnhancedHeuristicPlayer() for name in ai_names}
    return engine, ai_players, all_names


def main() -> None:
    parser = argparse.ArgumentParser(description="Twenty-Five card game")
    parser.add_argument(
        "--seeall",
        action="store_true",
        help="Show all players' hands (master view). Default: hidden-hand mode.",
    )
    parser.add_argument(
        "--1v3",
        dest="one_v_three",
        metavar="NAME",
        help="Quick setup: you (NAME) vs 3 Enhanced AI opponents with random seats.",
    )
    parser.add_argument(
        "--ui",
        default="cli",
        metavar="MODULE",
        help=(
            "UI module to use (default: cli). "
            "Must be a module under twentyfive/ui/ that exports a launch() function. "
            "Example: --ui pygame_ui"
        ),
    )
    args = parser.parse_args()

    # Load UI module early so setup_game() can be called if available.
    ui_name = args.ui
    try:
        ui_mod = importlib.import_module(f"twentyfive.ui.{ui_name}")
    except ModuleNotFoundError:
        print(f"Unknown UI module: {ui_name!r}")
        print("Available built-in UIs: cli, pygame_ui, tactical_ui")
        sys.exit(1)
    except ImportError as exc:
        print(f"UI module {ui_name!r} is missing a dependency: {exc}")
        print("For pygame_ui / tactical_ui run: pip install -e '.[gui]'")
        sys.exit(1)

    if not hasattr(ui_mod, "launch"):
        print(f"UI module {ui_name!r} has no launch() function.")
        print("See twentyfive/ui/UI_DEVELOPMENT.md for the interface contract.")
        sys.exit(1)

    print("Welcome to Twenty-Five!")
    print()

    if args.one_v_three:
        human_name = args.one_v_three
        engine, ai_players, names = _setup_quick_1v3(human_name)

        state = engine.get_state()
        dealer_name = state.players[state.dealer_index].name
        seat_num = next(i + 1 for i, p in enumerate(state.players) if p.name == human_name)
        opponent_names = ", ".join(n for n in names if n != human_name)

        print(f"  Playing as : {human_name}  (seat {seat_num} of 4)")
        print(f"  Opponents  : {opponent_names}  (Enhanced AI)")
        print(f"  First deal : {dealer_name}")
        print()

        human_names = [human_name]
        show_all = args.seeall

    elif hasattr(ui_mod, "setup_game"):
        # GUI setup lobby — the UI module handles player selection.
        setup_result = ui_mod.setup_game()
        if setup_result is None:
            return  # user closed the window without starting

        names, type_map = setup_result
        n = len(names)
        initial_dealer = random.randrange(n)
        engine = GameEngine(player_names=names, initial_dealer=initial_dealer)

        ai_players: dict[str, AIPlayer] = {}
        for name, type_str in type_map.items():
            player = _ai_player_from_type_str(type_str, engine)
            if player is not None:
                ai_players[name] = player

        human_names = [name for name in names if name not in ai_players]
        show_all = args.seeall or len(human_names) == 0

    else:
        n = _prompt_player_count()
        names = _prompt_player_names(n)
        print()
        initial_dealer = random.randrange(n)
        engine = GameEngine(player_names=names, initial_dealer=initial_dealer)
        ai_players = _prompt_ai_players(names, engine)

        human_names = [name for name in names if name not in ai_players]
        show_all = args.seeall or len(human_names) == 0

    player_types = _build_player_types(names, ai_players)
    engine.record_game_start(player_types)

    controller = GameController(engine, ai_players)

    try:
        ui_mod.launch(controller, show_all=show_all)
    except ImportError as exc:
        print(f"UI module {ui_name!r} is missing a dependency: {exc}")
        print("For pygame_ui / tactical_ui run: pip install -e '.[gui]'")
        sys.exit(1)


if __name__ == "__main__":
    main()
