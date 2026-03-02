from __future__ import annotations

import random

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


def main() -> None:
    print("Welcome to Twenty-Five!")
    print()
    n = _prompt_player_count()
    names = _prompt_player_names(n)
    CLI(GameEngine(player_names=names)).run()


if __name__ == "__main__":
    main()
