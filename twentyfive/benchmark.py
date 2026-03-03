"""
AI benchmark framework for Twenty-Five.

Runs automated games with one of each AI type per game
(Random, Heuristic, Enhanced, MCTS, ISMCTS — 5 players).
Seats are shuffled randomly each game to cancel position/dealer bias.

Usage:
    python -m twentyfive.benchmark [--games N] [--seed N] [--mcts-sims N] [--quiet]
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass

from twentyfive.ai.enhanced_heuristic import EnhancedHeuristicPlayer
from twentyfive.ai.heuristic import HeuristicPlayer
from twentyfive.ai.ismcts import ISMCTSPlayer
from twentyfive.ai.mcts import MCTSPlayer
from twentyfive.ai.player import AIPlayer, RandomPlayer
from twentyfive.game.engine import GameEngine

_DEFAULT_AI_TYPES = ["random", "heuristic", "enhanced", "mcts", "ismcts"]


@dataclass
class AggregateStats:
    ai_type: str
    label: str
    games: int = 0
    wins: int = 0
    total_score: int = 0   # cumulative final score across all games
    total_rounds: int = 0  # cumulative rounds until game ended


def _make_ai(ai_type: str, engine: GameEngine, simulations: int) -> AIPlayer:
    """Instantiate an AI player by type name."""
    match ai_type:
        case "random":
            return RandomPlayer()
        case "heuristic":
            return HeuristicPlayer()
        case "enhanced":
            return EnhancedHeuristicPlayer()
        case "mcts":
            return MCTSPlayer(engine, simulations=simulations)
        case "ismcts":
            return ISMCTSPlayer(engine, simulations=simulations)
        case _:
            raise ValueError(f"Unknown AI type: {ai_type!r}")


def _ai_label(ai_type: str, simulations: int) -> str:
    if ai_type == "mcts":
        return f"MCTS ({simulations})"
    if ai_type == "ismcts":
        return f"ISMCTS ({simulations})"
    return ai_type.capitalize()


def _run_game(
    ai_types: list[str],
    simulations: int,
) -> tuple[str, dict[str, int], int]:
    """
    Run one complete game with shuffled seat assignments.

    Returns:
        (winning_ai_type, {ai_type: final_score}, rounds_played)
    """
    shuffled = list(ai_types)
    random.shuffle(shuffled)
    names = [f"P{i + 1}" for i in range(len(shuffled))]
    name_to_type = dict(zip(names, shuffled))

    engine = GameEngine(player_names=names, audit_dir=None)
    ai_players = {
        name: _make_ai(ai_type, engine, simulations)
        for name, ai_type in name_to_type.items()
    }

    while not engine.is_game_over:
        state = engine.get_state()
        move = ai_players[state.current_player.name].choose_move(state)
        engine.apply_move(move)

    state = engine.get_state()
    winner_ai = name_to_type[state.current_player.name]
    scores_by_type = {name_to_type[p.name]: p.score for p in state.players}
    return winner_ai, scores_by_type, state.round_number


def run_benchmark(
    n_games: int = 20,
    *,
    ai_types: list[str] | None = None,
    simulations: int = 500,
    seed: int | None = None,
    quiet: bool = False,
) -> dict[str, AggregateStats]:
    """
    Run n_games complete games and return aggregate stats per AI type.

    Args:
        n_games:     Number of games to play.
        ai_types:    AI types to include. Defaults to all four.
        simulations: MCTS simulations per move.
        seed:        Random seed for reproducibility (None = random).
        quiet:       Suppress progress output.

    Returns:
        Dict mapping ai_type → AggregateStats.
    """
    if ai_types is None:
        ai_types = list(_DEFAULT_AI_TYPES)

    if seed is not None:
        random.seed(seed)

    stats: dict[str, AggregateStats] = {
        t: AggregateStats(ai_type=t, label=_ai_label(t, simulations))
        for t in ai_types
    }

    for g in range(1, n_games + 1):
        if not quiet:
            print(f"\rGame {g}/{n_games}...", end="", flush=True)

        winner_type, scores_by_type, rounds = _run_game(ai_types, simulations)

        for ai_type, score in scores_by_type.items():
            s = stats[ai_type]
            s.games += 1
            s.total_score += score
            s.total_rounds += rounds
        stats[winner_type].wins += 1

    if not quiet:
        print()  # newline after progress

    return stats


def print_results(stats: dict[str, AggregateStats], *, elapsed_s: float) -> None:
    """Print a formatted results table to stdout."""
    n_games = next(iter(stats.values())).games if stats else 0
    n_players = len(stats)

    width = 62
    print("=" * width)
    print(f"  AI Benchmark — {n_games} games × {n_players} players")
    avg_s = elapsed_s / n_games if n_games else 0
    print(f"  Total time: {elapsed_s:.1f} s  |  Avg per game: {avg_s:.1f} s")
    print("=" * width)
    print()

    header = (
        f"  {'AI Type':<16} {'Games':>6}  {'Wins':>5}  {'Win%':>6}"
        f"  {'Avg Score':>10}  {'Avg Rounds':>11}"
    )
    sep    = "  " + "-" * (len(header) - 2)
    print(header)
    print(sep)

    sorted_stats = sorted(
        stats.values(),
        key=lambda s: (s.wins, s.total_score),
        reverse=True,
    )
    for s in sorted_stats:
        win_pct = 100 * s.wins / s.games if s.games else 0.0
        avg_score = s.total_score / s.games if s.games else 0.0
        avg_rounds = s.total_rounds / s.games if s.games else 0.0
        print(
            f"  {s.label:<16} {s.games:>6}  {s.wins:>5}  {win_pct:>5.1f}%"
            f"  {avg_score:>10.1f}  {avg_rounds:>11.1f}"
        )

    print()
    total_wins = sum(s.wins for s in stats.values())
    total_win_pct = 100 * total_wins / n_games if n_games else 0
    print(f"  (Win% sums to {total_win_pct:.0f}%; Avg Score = final points at game end)")
    print()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Benchmark Twenty-Five AI players")
    parser.add_argument(
        "--games", type=int, default=20, metavar="N",
        help="Number of games to play (default: 20)",
    )
    parser.add_argument(
        "--seed", type=int, default=None, metavar="N",
        help="Random seed for reproducibility",
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="Suppress per-game progress output",
    )
    parser.add_argument(
        "--mcts-sims", type=int, default=500, metavar="N",
        help="MCTS simulations per move (default: 500)",
    )
    args = parser.parse_args()

    t0 = time.monotonic()
    results = run_benchmark(
        n_games=args.games,
        simulations=args.mcts_sims,
        seed=args.seed,
        quiet=args.quiet,
    )
    elapsed = time.monotonic() - t0

    print_results(results, elapsed_s=elapsed)
