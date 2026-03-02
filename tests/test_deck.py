"""Tests for the Deck class."""

import pytest

from twentyfive.cards.card import Card, Rank, Suit
from twentyfive.cards.deck import Deck


class TestDeck:
    def test_initial_size(self) -> None:
        deck = Deck()
        assert len(deck) == 52
        assert deck.remaining == 52

    def test_contains_all_52_unique_cards(self) -> None:
        deck = Deck()
        # Access private for test purposes — we verify all suit/rank combos exist
        all_cards = deck.deal(52)
        assert len(set(all_cards)) == 52
        for suit in Suit:
            for rank in Rank:
                assert Card(rank, suit) in all_cards

    def test_shuffle_changes_order(self) -> None:
        deck1 = Deck()
        deck2 = Deck()
        deck2.shuffle()
        cards1 = deck1.deal(52)
        cards2 = deck2.deal(52)
        # With 52! orderings this will almost certainly differ
        assert cards1 != cards2

    def test_deal_removes_cards(self) -> None:
        deck = Deck()
        dealt = deck.deal(5)
        assert len(dealt) == 5
        assert deck.remaining == 47

    def test_deal_returns_top_cards(self) -> None:
        deck = Deck()
        first_five = deck.deal(5)
        assert len(first_five) == 5
        # Second deal should be different cards
        next_five = deck.deal(5)
        assert set(first_five).isdisjoint(set(next_five))

    def test_deal_too_many_raises(self) -> None:
        deck = Deck()
        with pytest.raises(ValueError):
            deck.deal(53)

    def test_deal_exactly_remaining(self) -> None:
        deck = Deck()
        deck.deal(50)
        remaining = deck.deal(2)
        assert len(remaining) == 2
        assert deck.remaining == 0

    def test_turn_up_returns_one_card(self) -> None:
        deck = Deck()
        card = deck.turn_up()
        assert isinstance(card, Card)
        assert deck.remaining == 51

    def test_deal_sequential_is_non_overlapping(self) -> None:
        deck = Deck()
        deck.shuffle()
        hand1 = deck.deal(5)
        hand2 = deck.deal(5)
        hand3 = deck.deal(5)
        # No card dealt twice
        all_dealt = hand1 + hand2 + hand3
        assert len(set(all_dealt)) == 15
