from __future__ import annotations

from twentyfive.game.engine import GameEngine
from twentyfive.ui.cli import CLI


def _prompt_player_count() -> int:
    while True:
        raw = input("How many players? (2-6): ").strip()
        try:
            n = int(raw)
            if 2 <= n <= 6:
                return n
        except ValueError:
            pass
        print("Please enter a number between 2 and 6.")


def _prompt_player_names(n: int) -> list[str]:
    names: list[str] = []
    for i in range(n):
        raw = input(f"Player {i + 1} name: ").strip()
        name = raw if raw else f"Player {i + 1}"
        names.append(name)
    return names


def main() -> None:
    print("Welcome to Twenty-Five!")
    print()
    n = _prompt_player_count()
    names = _prompt_player_names(n)
    CLI(GameEngine(player_names=names)).run()


if __name__ == "__main__":
    main()
