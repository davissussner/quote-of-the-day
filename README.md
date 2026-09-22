# Quote of the Day

The president's longest unbroken ramble each day, read aloud by your browser's own
text-to-speech.

## Why

Presidential remarks reach most people as soundbites -- a clipped sentence, stripped of the
tangents and asides that surround it. This does the opposite: it finds his single longest
uninterrupted turn of speech each day, straight from a professional transcript, and shows the
whole thing, unedited.

**On the voice**: the "Listen" button uses the browser's built-in `speechSynthesis`, a generic
synthetic voice. It is not a recording, and it is not built to sound like the president or
anyone else. That distinction is stated on every page.

## How a quote gets picked

1. **Discover** ([`fetch.py`](quote_of_the_day/fetch.py)) checks Rev.com's most recent Trump
   transcripts (<https://www.rev.com/category/donald-trump>) for one published on the target day.
2. **Parse**: a transcript page is a sequence of speaker-labeled paragraphs
   (`Donald Trump (01:22): ...`). `TranscriptParser` walks that structure directly and groups
   the paragraphs between labels into turns -- nothing is paraphrased, trimmed, or generated,
   the text stored is exactly what's between labels.
3. **Filter**: only turns labeled as the president (`PRESIDENT_NAME`, default `Trump`) and at
   least 50 words long qualify -- long enough to be a real passage, not a one-line reaction.
4. **Pick**: the day's quote is simply his longest qualifying turn. Every other qualifying turn
   from that day is kept too, visible under "Other long passages from the same day."
5. **Build** ([`build_site.py`](quote_of_the_day/build_site.py)) renders the static site.

Every quote links to the full transcript so a reader can check it in context -- that link is
the actual guarantee of accuracy, not the parsing logic.

## Status

| Stage | Command | Status |
|---|---|---|
| Fetch + pick today's quote | `uv run python -m quote_of_the_day.fetch` | working -- run live against Rev.com, verified against real transcripts |
| Build the static site | `uv run python -m quote_of_the_day.build_site --clean` | working -- verified in-browser, including the Listen button |

## Run it locally

```bash
uv sync
uv run python -m quote_of_the_day.fetch
uv run python -m quote_of_the_day.build_site --clean
cd site && python3 -m http.server 8000
```

Then open <http://localhost:8000>. No API key or `.env` file needed -- Rev.com's transcripts
are public pages, fetched directly.

## Setup

Requires Python 3.10+ and [uv](https://docs.astral.sh/uv/).

```bash
uv python install 3.13
uv sync
```

Optionally copy `.env.example` to `.env` to override `PRESIDENT_NAME` (defaults to `Trump`) --
matched as a case-insensitive substring against the transcript's own speaker label.

## Publishing

`.github/workflows/publish.yml` runs once a day (13:00 UTC), fetches that day's pick, commits
the updated archive (`data/quotes.db`) back to `main`, rebuilds the site, and deploys it to
GitHub Pages. No secrets needed. Pages just needs to be set to deploy from GitHub Actions
(Settings -> Pages -> Source).

The archive is committed rather than regenerated on every build: which transcripts existed at
fetch time can't be recomputed later, so once a day is picked it's kept permanently.

## A note on the source

Rev.com is a third-party transcription service, not an official government record. It's used
here because it transcribes speeches and rallies in full, promptly, and consistently --
whitehouse.gov's own `/remarks/` transcripts turned out to be sparse in practice (most recent
events there are published as video-only, with no accompanying text). Every quote still links
to its Rev.com source so it can be checked against the video itself.

## Layout

```
quote_of_the_day/   fetch + build pipeline, schema.sql
templates/          Jinja2 templates for the static site
data/quotes.db      SQLite archive of every day's quote        (committed, not gitignored)
site/                build output -- what gets published        (gitignored, regenerable)
```

## License

TBD.
