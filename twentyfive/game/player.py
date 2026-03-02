from __future__ import annotations

from dataclasses import dataclass, field

from twentyfive.cards.card import Card
from twentyfive.game.state import PlayerSnapshot


@dataclass
class Player:
    """Mutable game object — never exposed to the UI directly."""

    name: str
    hand: list[Card] = field(default_factory=list)
    score: int = 0
    tricks_won_this_round: int = 0

    def add_card(self, card: Card) -> None:
        self.hand.append(card)

    def remove_card(self, card: Card) -> None:
        self.hand.remove(card)  # raises ValueError if not present — intentional

    def clear_hand(self) -> None:
        self.hand.clear()

    def reset_round_stats(self) -> None:
        self.tricks_won_this_round = 0

    def snapshot(self) -> PlayerSnapshot:
        """Return an immutable view of this player (all fields revealed)."""
        return PlayerSnapshot(
            name=self.name,
            score=self.score,
            tricks_won_this_round=self.tricks_won_this_round,
            hand_size=len(self.hand),
            hand=tuple(self.hand),
        )
