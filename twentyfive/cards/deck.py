from __future__ import annotations

import random

from twentyfive.cards.card import Card, Rank, Suit


class Deck:
    """A standard 52-card deck."""

    def __init__(self) -> None:
        self._cards: list[Card] = [Card(rank, suit) for suit in Suit for rank in Rank]

    def shuffle(self) -> None:
        """Shuffle the remaining cards in-place."""
        random.shuffle(self._cards)

    def deal(self, n: int) -> list[Card]:
        """Remove and return the top n cards from the deck."""
        if n > len(self._cards):
            raise ValueError(f"Cannot deal {n} cards; only {len(self._cards)} remain")
        dealt = self._cards[:n]
        self._cards = self._cards[n:]
        return dealt

    def turn_up(self) -> Card:
        """Remove and return the top card (used as the face-up trump card)."""
        return self.deal(1)[0]

    @property
    def remaining(self) -> int:
        return len(self._cards)

    def __len__(self) -> int:
        return len(self._cards)
