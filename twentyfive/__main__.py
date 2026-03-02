from __future__ import annotations

import random

from twentyfive.ai.enhanced_heuristic import EnhancedHeuristicPlayer
from twentyfive.ai.heuristic import HeuristicPlayer
from twentyfive.ai.mcts import MCTSPlayer
from twentyfive.ai.player import AIPlayer, RandomPlayer
from twentyfive.game.engine import GameEngine
from twentyfive.ui.cli import CLI

_NAME_BANK = [
    "Alice", "Bob", "Carol", "Dave", "Eve", "Frank",
    "Grace", "Hank", "Iris", "Jack", "Kate", "Leo",
    "Mia", "Ned", "Olive", "Pete", "Quinn", "Rose",
    "Sam", "Tara",
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
    print("Player types:  [H] Human  [R] Random AI  [A] Heuristic AI  [E] Enhanced AI  [M] MCTS AI")
    print()
    for name in names:
        while True:
            raw = input(f"  {name}: (H/R/A/E/M) [H]: ").strip().upper()
            if not raw or raw == "H":
                break
            if raw == "R":
                ai_players[name] = RandomPlayer()
                break
            if raw == "A":
                ai_players[name] = HeuristicPlayer()
                break
            if raw == "E":
                ai_players[name] = EnhancedHeuristicPlayer()
                break
            if raw == "M":
                ai_players[name] = MCTSPlayer(engine)
                break
            print("  Please enter H, R, A, E, or M.")
    return ai_players


def main() -> None:
    print("Welcome to Twenty-Five!")
    print()
    n = _prompt_player_count()
    names = _prompt_player_names(n)
    print()
    engine = GameEngine(player_names=names)
    ai_players = _prompt_ai_players(names, engine)
    CLI(engine, ai_players=ai_players).run()


if __name__ == "__main__":
    main()
