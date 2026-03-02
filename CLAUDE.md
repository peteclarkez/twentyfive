# Claude Instructions — Twenty-Five Project

## Project Overview

This is a Python implementation of Twenty-Five (25s), Ireland's national card game.
See [RULES.md](RULES.md) for the full ruleset and [STRATEGY.md](STRATEGY.md) for
strategy guidance used to inform AI player behaviour.

## Recreating the generated_docs/ Folder

The `generated_docs/` folder is excluded from version control (it is in `.gitignore`).
It contains markdown extracts of the reference sources used to write RULES.md and
STRATEGY.md. If the folder is missing and needs to be recreated, follow these steps:

### Step 1 — Create the folder
```bash
mkdir -p generated_docs
```

### Step 2 — Fetch each source and save as markdown

Use the `WebFetch` tool for HTML pages and `curl` + `pdftotext` for the PDF.
Use `youtube-transcript-api` (pip install if needed) for the YouTube video.

For each URL, extract all content and save to the corresponding file in `generated_docs/`:

| URL | Output file |
|-----|-------------|
| `https://www.britannica.com/topic/twenty-five` | `generated_docs/britannica-twenty-five.md` |
| `https://irish25s.herokuapp.com/howtoplay` | `generated_docs/irish25s-how-to-play.md` |
| `https://gamerules.com/rules/twenty-five-25/` | `generated_docs/gamerules-twenty-five.md` |
| `http://www.orwellianireland.com/25.pdf` | `generated_docs/orwellianireland-25.md` |
| `https://www.youtube.com/watch?v=yhMMjVduF1k` | `generated_docs/youtube-riffle-shuffle-roll-25.md` |

### Step 3 — PDF extraction

The orwellianireland source is a PDF. Fetch it with curl and extract with pdftotext:

```bash
curl -L -o /tmp/25.pdf "http://www.orwellianireland.com/25.pdf"
pdftotext /tmp/25.pdf -   # pipe into your markdown file
```

### Step 4 — YouTube transcript

The YouTube video transcript requires `youtube-transcript-api`:

```python
from youtube_transcript_api import YouTubeTranscriptApi
api = YouTubeTranscriptApi()
transcript = api.fetch('yhMMjVduF1k')
for entry in transcript:
    print(entry.text)
```

### Step 5 — Format

Each markdown file should:
- Have a `# Title` heading
- Include a `> Source: [url](url)` line near the top linking back to the original
- Contain the full extracted content as clean markdown

---

## Development Commands

| Task | Command |
|------|---------|
| Run all tests | `python -m pytest` |
| Run a single test file | `python -m pytest tests/test_foo.py -v` |
| Format code | `ruff format .` |
| Lint code | `ruff check .` |
| Type check | `mypy twentyfive/` |
| Run the game | `python -m twentyfive` |
| Install dev dependencies | `pip install -e ".[dev]"` |

## Code Style
- Line length: 100 characters
- Formatter: **ruff** (configured in `pyproject.toml` — replaces black + isort)
- Type hints encouraged on all public functions and class signatures
- Dataclasses preferred for domain objects (Card, Deck, Player, Trick, etc.)
- Tests live in `tests/` and follow the `test_*.py` naming convention

---

## Autonomy (project-specific)

These extend the global autonomy tiers in `~/.claude/CLAUDE.md`.

**Proceed without asking:**
- Add or update tests in `tests/`
- Rewrite files in `twentyfive/` that use pyCardDeck (the decision to remove it is settled)
- Add type hints, fix ruff/mypy warnings

**Propose and wait:**
- Change the Card, Deck, or Trick data model once defined
- Add a new game phase or scoring variant
- Introduce any new dependency

**Never do:**
- Change anything in `RULES.md` or `STRATEGY.md` without explicit instruction — those are the authoritative game spec
- Guess at rule ambiguities; surface them and ask

---

## Key Architectural Decisions

- **No external card library:** The project deliberately avoids pyCardDeck and similar
  libraries. 25s has a custom ranking system that changes dynamically per trump suit;
  plain Python dataclasses give more control with less friction. pyCardDeck's `PokerCard`
  provides nothing that a simple `Card` dataclass cannot, and introduces an unnecessary
  dependency.
- **Logic first:** Game logic (deck, cards, tricks, scoring, rule validation) is built
  before any GUI is considered.
- **Phased development:** MVP is human-only CLI play. AI players and partnerships come later.

## Rule Reference

The authoritative source on traditional rules is the OrwellianIreland PDF by Brian Nugent.
Where sources conflict, prefer that source. The most commonly misunderstood rules are:

1. **Reneging hierarchy** — not simply "top-3 can always be withheld"; protection is
   relative to the rank of the led trump (see RULES.md renege table).
2. **May-trump** — on a non-trump lead, players choose between following suit OR trumping;
   they cannot discard freely if they hold the led suit or any trump.
3. **Ace of Hearts** — always a trump; never appears in the non-trump Hearts ranking.
