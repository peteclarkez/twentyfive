# Twenty-Five (25s)

A Python implementation of **Twenty-Five**, Ireland's national card game.

## About the Game

Twenty-Five is a trick-taking card game with roots going back over 500 years in Ireland,
historically known as *Maw*, then *Spoil-Five*, and eventually *Twenty-Five*. It is best
played with 4–6 players, uses a standard 52-card deck, and has a unique card ranking
system unlike any other common card game — where suit colour determines card strength
and the Ace of Hearts is always a trump card regardless of the trump suit.

The goal is simple: be the first player to reach **25 points** by winning tricks worth
5 points each.

## Project Goals

This project aims to build a complete, rules-accurate simulation of 25s in Python,
starting with the core game logic and working towards a playable interface. Planned
stages:

- **MVP:** Core game engine (deck, dealing, trick logic, scoring) with command-line play
- **Phase 2:** AI / robotic players with configurable strategy
- **Phase 3:** Partnership play and variants (45s, 110)
- **Phase 4:** GUI (to be decided)

## References

The following sources were used to establish the rules and strategy documented in
[RULES.md](RULES.md) and [STRATEGY.md](STRATEGY.md):

| Source | Description |
|--------|-------------|
| [Britannica — Twenty-Five](https://www.britannica.com/topic/twenty-five) | Overview, history, rules, and the Auction Forty-Fives variant |
| [Irish25s — How to Play](https://irish25s.herokuapp.com/howtoplay) | Online implementation rules including 45s mode and reneging detail |
| [GameRules — Twenty-Five](https://gamerules.com/rules/twenty-five-25/) | Card rankings by suit with full trump lookup tables |
| [OrwellianIreland — 25 (PDF)](http://www.orwellianireland.com/25.pdf) | Scholarly essay by Brian Nugent covering rules, history, etymology, and strategy; most authoritative source on traditional play and the social conventions of the game |
| [YouTube — Riffle Shuffle & Roll](https://www.youtube.com/watch?v=yhMMjVduF1k) | Video walkthrough of a full game with commentary on the ranking system and may-trump rule |

