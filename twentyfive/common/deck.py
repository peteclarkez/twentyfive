import pyCardDeck
from pyCardDeck.cards import PokerCard
from typing import List
from player import Player

class Deck:

    def __init__(self, name: str):
        self.cards = self.generate_deck()
        self.name = name
