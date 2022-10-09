#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
This is an example of pyCardDeck, it's not meant to be complete poker script,
but rather a showcase of pyCardDeck's usage.
"""

import pyCardDeck
# noinspection PyCompatibility
from typing import List
from pyCardDeck.cards import PokerCard
from twentyfive.common.table import Table
from twentyfive.common.game import Game
from twentyfive.common.player import Player

def run():
    
    table = Table([Player("Jack"), Player("John"), Player("Peter")])
    game = Game(table);
    game.dealCards(2)
    game.dealCards(3)

        
    for player in game.table.getPlayers():
        player.printHand()
