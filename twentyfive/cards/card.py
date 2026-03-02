from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class Suit(IntEnum):
    CLUBS = 0
    DIAMONDS = 1
    HEARTS = 2
    SPADES = 3

    @property
    def symbol(self) -> str:
        return {Suit.CLUBS: "♣", Suit.DIAMONDS: "♦", Suit.HEARTS: "♥", Suit.SPADES: "♠"}[self]

    @property
    def is_red(self) -> bool:
        return self in (Suit.HEARTS, Suit.DIAMONDS)

    def __str__(self) -> str:
        return self.name.capitalize()


class Rank(IntEnum):
    ACE = 1
    TWO = 2
    THREE = 3
    FOUR = 4
    FIVE = 5
    SIX = 6
    SEVEN = 7
    EIGHT = 8
    NINE = 9
    TEN = 10
    JACK = 11
    QUEEN = 12
    KING = 13

    @property
    def display(self) -> str:
        specials = {Rank.ACE: "A", Rank.JACK: "J", Rank.QUEEN: "Q", Rank.KING: "K"}
        return specials.get(self, str(self.value))


@dataclass(frozen=True)
class Card:
    rank: Rank
    suit: Suit

    def __str__(self) -> str:
        return f"{self.rank.display}{self.suit.symbol}"

    def __repr__(self) -> str:
        return f"Card({self.rank.name}, {self.suit.name})"


# Module-level constants used throughout the game layer
ACE_OF_HEARTS = Card(Rank.ACE, Suit.HEARTS)


def is_trump(card: Card, trump_suit: Suit) -> bool:
    """A card is trump if it belongs to the trump suit OR it is the Ace of Hearts."""
    return card.suit == trump_suit or card == ACE_OF_HEARTS
