"""
Smoke tests for the benchmark module.

Tests verify structural correctness (right keys, win counts add up) rather than
which AI wins — that's inherently statistical and seed-dependent.
MCTS simulations are set very low (5–10) to keep tests fast.
"""

from __future__ import annotations

from twentyfive.benchmark import run_benchmark


class TestRunBenchmark:
    def test_returns_all_four_ai_types(self) -> None:
        stats = run_benchmark(n_games=2, seed=42, quiet=True, simulations=5)
        assert set(stats.keys()) == {"random", "heuristic", "enhanced", "mcts"}

    def test_win_count_equals_game_count(self) -> None:
        """Exactly one winner per game."""
        stats = run_benchmark(n_games=3, seed=42, quiet=True, simulations=5)
        assert sum(s.wins for s in stats.values()) == 3

    def test_game_count_per_type(self) -> None:
        """Every AI type plays in every game."""
        n = 4
        stats = run_benchmark(n_games=n, seed=0, quiet=True, simulations=5)
        for s in stats.values():
            assert s.games == n

    def test_wins_non_negative(self) -> None:
        stats = run_benchmark(n_games=3, seed=7, quiet=True, simulations=5)
        for s in stats.values():
            assert 0 <= s.wins <= 3

    def test_scores_positive(self) -> None:
        """Winner always has score >= 25; all players have score >= 0."""
        stats = run_benchmark(n_games=2, seed=1, quiet=True, simulations=5)
        for s in stats.values():
            assert s.total_score >= 0

    def test_seed_reproducibility(self) -> None:
        """Same seed → identical results."""
        a = run_benchmark(n_games=3, seed=99, quiet=True, simulations=5)
        b = run_benchmark(n_games=3, seed=99, quiet=True, simulations=5)
        for ai_type in a:
            assert a[ai_type].wins == b[ai_type].wins
            assert a[ai_type].total_score == b[ai_type].total_score

    def test_custom_game_count(self) -> None:
        stats = run_benchmark(n_games=2, seed=0, quiet=True, simulations=5)
        assert sum(s.wins for s in stats.values()) == 2

    def test_labels_set(self) -> None:
        """Labels are non-empty strings."""
        stats = run_benchmark(n_games=1, seed=0, quiet=True, simulations=5)
        for s in stats.values():
            assert isinstance(s.label, str) and s.label
