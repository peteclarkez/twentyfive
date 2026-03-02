"""Tests for the cards/ primitive layer."""

import pytest

from twentyfive.cards.card import ACE_OF_HEARTS, Card, Rank, Suit, is_trump


class TestSuit:
    def test_symbols(self) -> None:
        assert Suit.CLUBS.symbol == "♣"
        assert Suit.DIAMONDS.symbol == "♦"
        assert Suit.HEARTS.symbol == "♥"
        assert Suit.SPADES.symbol == "♠"

    def test_is_red(self) -> None:
        assert Suit.HEARTS.is_red is True
        assert Suit.DIAMONDS.is_red is True
        assert Suit.CLUBS.is_red is False
        assert Suit.SPADES.is_red is False


class TestRank:
    def test_display_specials(self) -> None:
        assert Rank.ACE.display == "A"
        assert Rank.JACK.display == "J"
        assert Rank.QUEEN.display == "Q"
        assert Rank.KING.display == "K"

    def test_display_numerics(self) -> None:
        assert Rank.TWO.display == "2"
        assert Rank.TEN.display == "10"
        assert Rank.FIVE.display == "5"


class TestCard:
    def test_str(self) -> None:
        assert str(Card(Rank.FIVE, Suit.CLUBS)) == "5♣"
        assert str(Card(Rank.ACE, Suit.HEARTS)) == "A♥"
        assert str(Card(Rank.KING, Suit.SPADES)) == "K♠"
        assert str(Card(Rank.TEN, Suit.DIAMONDS)) == "10♦"

    def test_equality(self) -> None:
        assert Card(Rank.ACE, Suit.HEARTS) == Card(Rank.ACE, Suit.HEARTS)
        assert Card(Rank.FIVE, Suit.CLUBS) != Card(Rank.FIVE, Suit.HEARTS)

    def test_hashable(self) -> None:
        cards = {Card(Rank.ACE, Suit.HEARTS), Card(Rank.ACE, Suit.HEARTS)}
        assert len(cards) == 1

    def test_usable_as_dict_key(self) -> None:
        d = {Card(Rank.KING, Suit.SPADES): "winner"}
        assert d[Card(Rank.KING, Suit.SPADES)] == "winner"

    def test_immutable(self) -> None:
        card = Card(Rank.ACE, Suit.HEARTS)
        with pytest.raises((AttributeError, TypeError)):
            card.rank = Rank.KING  # type: ignore[misc]

    def test_ace_of_hearts_constant(self) -> None:
        assert ACE_OF_HEARTS == Card(Rank.ACE, Suit.HEARTS)
        assert ACE_OF_HEARTS.rank == Rank.ACE
        assert ACE_OF_HEARTS.suit == Suit.HEARTS


class TestIsTrump:
    def test_trump_suit_card_is_trump(self) -> None:
        for suit in Suit:
            assert is_trump(Card(Rank.KING, suit), suit)

    def test_non_trump_suit_card_is_not_trump(self) -> None:
        # King of Hearts when trump is Clubs — but A♥ special case doesn't apply to King
        assert not is_trump(Card(Rank.KING, Suit.HEARTS), Suit.CLUBS)
        assert not is_trump(Card(Rank.KING, Suit.DIAMONDS), Suit.CLUBS)

    def test_ace_of_hearts_always_trump(self) -> None:
        for suit in Suit:
            assert is_trump(ACE_OF_HEARTS, suit), f"A♥ should be trump when trump is {suit}"

    def test_ace_of_hearts_trump_when_hearts_trump(self) -> None:
        # A♥ is trump even when hearts is already the trump suit
        assert is_trump(ACE_OF_HEARTS, Suit.HEARTS)

    def test_non_hearts_ace_not_always_trump(self) -> None:
        assert not is_trump(Card(Rank.ACE, Suit.CLUBS), Suit.HEARTS)
        assert not is_trump(Card(Rank.ACE, Suit.SPADES), Suit.DIAMONDS)
