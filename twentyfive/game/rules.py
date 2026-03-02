"""
All Irish Twenty-Five rule logic.

This module has no imports from engine.py, player.py, or state.py.
It imports only from the cards layer.
"""

from __future__ import annotations

from twentyfive.cards.card import ACE_OF_HEARTS, Card, Rank, Suit, is_trump
from twentyfive.game.state import Move, PassRob, Rob, TrickPlay

# ---------------------------------------------------------------------------
# Trump rank lookup table — built once at import time
# ---------------------------------------------------------------------------
# Integer values: higher = stronger. Range 1–14.
# Only trump cards have entries. KeyError on a non-trump card = caller bug.

_TRUMP_RANKS: dict[tuple[Suit, Card], int] = {}


def _build_trump_rank_table() -> None:
    for trump in Suit:
        five = Card(Rank.FIVE, trump)
        jack = Card(Rank.JACK, trump)
        ace_trump = Card(Rank.ACE, trump)
        king = Card(Rank.KING, trump)
        queen = Card(Rank.QUEEN, trump)

        _TRUMP_RANKS[(trump, five)] = 14
        _TRUMP_RANKS[(trump, jack)] = 13
        _TRUMP_RANKS[(trump, ACE_OF_HEARTS)] = 12
        # Ace of trumps occupies rank 11 only when trump is not Hearts
        # (when trump IS Hearts, ACE_OF_HEARTS already covers the ace at rank 12)
        if trump != Suit.HEARTS:
            _TRUMP_RANKS[(trump, ace_trump)] = 11
        _TRUMP_RANKS[(trump, king)] = 10
        _TRUMP_RANKS[(trump, queen)] = 9

        # Remaining trump cards ranked 8→1 by suit colour
        if trump.is_red:
            # Red suits: high numerics win (natural order after face cards)
            # Order: 10, 9, 8, 7, 6, 4, 3, 2  (5 and face cards already assigned above)
            remaining = [
                Rank.TEN, Rank.NINE, Rank.EIGHT, Rank.SEVEN,
                Rank.SIX, Rank.FOUR, Rank.THREE, Rank.TWO,
            ]
        else:
            # Black suits: low numerics win (inverted order after face cards)
            # Order: 2, 3, 4, 6, 7, 8, 9, 10
            remaining = [
                Rank.TWO, Rank.THREE, Rank.FOUR, Rank.SIX,
                Rank.SEVEN, Rank.EIGHT, Rank.NINE, Rank.TEN,
            ]

        # remaining is listed strongest-first; enumerate reversed so rank 1 = weakest
        for rank_val, rank in enumerate(reversed(remaining), start=1):
            card = Card(rank, trump)
            # Hearts trump: skip A♥ here (already assigned via ACE_OF_HEARTS above)
            if card != ACE_OF_HEARTS:
                _TRUMP_RANKS[(trump, card)] = rank_val


_build_trump_rank_table()


def trump_rank(card: Card, trump_suit: Suit) -> int:
    """
    Return the trump strength of a card (higher = stronger).
    Only valid when is_trump(card, trump_suit) is True.
    Raises KeyError if called on a non-trump card — this is a caller bug.
    """
    return _TRUMP_RANKS[(trump_suit, card)]


# ---------------------------------------------------------------------------
# Non-trump rank tables
# ---------------------------------------------------------------------------

_RED_NON_TRUMP: dict[Rank, int] = {
    Rank.KING: 13,
    Rank.QUEEN: 12,
    Rank.JACK: 11,
    Rank.TEN: 10,
    Rank.NINE: 9,
    Rank.EIGHT: 8,
    Rank.SEVEN: 7,
    Rank.SIX: 6,
    Rank.FIVE: 5,
    Rank.FOUR: 4,
    Rank.THREE: 3,
    Rank.TWO: 2,
    Rank.ACE: 1,
}

_BLACK_NON_TRUMP: dict[Rank, int] = {
    Rank.KING: 13,
    Rank.QUEEN: 12,
    Rank.JACK: 11,
    Rank.ACE: 10,
    Rank.TWO: 9,
    Rank.THREE: 8,
    Rank.FOUR: 7,
    Rank.FIVE: 6,
    Rank.SIX: 5,
    Rank.SEVEN: 4,
    Rank.EIGHT: 3,
    Rank.NINE: 2,
    Rank.TEN: 1,
}


def non_trump_rank(card: Card) -> int:
    """
    Return the strength of a non-trump card within its own suit.
    A♥ should never be passed here — it is always trump.
    """
    table = _RED_NON_TRUMP if card.suit.is_red else _BLACK_NON_TRUMP
    return table[card.rank]


# ---------------------------------------------------------------------------
# Legal move computation
# ---------------------------------------------------------------------------


def get_legal_cards(
    hand: list[Card],
    led_card: Card | None,
    trump_suit: Suit,
) -> list[Card]:
    """
    Return the cards the current player may legally play.

    led_card=None means this player is leading the trick (all cards legal).

    Non-trump lead:
        Must follow suit OR trump. If void in both, any card is legal.

    Trump lead:
        "Forced" trumps are those that do NOT outrank the led trump — they must be played
        if held. If the player has at least one forced trump, all their trumps are legal
        (renegeable top-3 may be played voluntarily). If the player has only renegeable
        trumps (or none), any card is legal.
    """
    if led_card is None:
        return list(hand)

    if not is_trump(led_card, trump_suit):
        # Non-trump lead: follow suit or trump
        candidates = [c for c in hand if c.suit == led_card.suit or is_trump(c, trump_suit)]
        return candidates if candidates else list(hand)

    # Trump lead
    led_rank = trump_rank(led_card, trump_suit)
    # Forced = trumps that don't outrank the led card (cannot be reneged)
    forced = [c for c in hand if is_trump(c, trump_suit) and trump_rank(c, trump_suit) <= led_rank]
    if forced:
        # Must play a trump; renegeable top-3 are optional extras
        return [c for c in hand if is_trump(c, trump_suit)]
    else:
        # Player has only renegeable top-3 trumps, or no trumps — any card is legal
        return list(hand)


def get_legal_rob_moves(
    hand: list[Card],
    face_up_card: Card,
    trump_suit: Suit,
    is_dealer: bool,
) -> list[Move]:
    """
    Return the legal moves for a player during the rob phase.

    Eligibility:
    - Non-dealer: holds the Ace of the trump suit.
    - Dealer: the face-up card IS the Ace of the trump suit.

    If eligible: [PassRob()] + [Rob(discard=c) for every card in hand + face_up_card].
    If not eligible: [PassRob()] — the engine will auto-advance past this player.
    """
    ace_of_trump = Card(Rank.ACE, trump_suit)

    if is_dealer:
        eligible = face_up_card == ace_of_trump
    else:
        eligible = ace_of_trump in hand

    if not eligible:
        return [PassRob()]

    # After robbing, the player holds hand + face_up_card (6 cards) and discards one.
    # Any card from that augmented hand is a legal discard.
    possible_discards = hand + [face_up_card]
    return [PassRob()] + [Rob(discard=c) for c in possible_discards]


# ---------------------------------------------------------------------------
# Trick winner
# ---------------------------------------------------------------------------


def trick_winner(
    plays: list[TrickPlay],
    led_suit: Suit,
    trump_suit: Suit,
) -> TrickPlay:
    """
    Determine the winner of a completed trick.

    If any trump was played: highest trump wins.
    If no trump was played: highest card of the led suit wins.
    """
    trump_plays = [p for p in plays if is_trump(p.card, trump_suit)]
    if trump_plays:
        return max(trump_plays, key=lambda p: trump_rank(p.card, trump_suit))
    led_suit_plays = [p for p in plays if p.card.suit == led_suit]
    return max(led_suit_plays, key=lambda p: non_trump_rank(p.card))
