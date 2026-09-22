# Quote of the Day

A daily, sourced quote from the sitting US president, read aloud by your browser's own
text-to-speech.

## Why

Presidential remarks are widely reported but rarely presented as just... a sentence, sourced
and readable in ten seconds. This picks one quote a day -- the one worded the same way by the
most news outlets that day -- and shows it plainly, with links to every outlet that reported it.

**On the voice**: the "Listen" button uses the browser's built-in `speechSynthesis`, a generic
synthetic voice. It is not a recording, and it is not built to sound like the president or
anyone else. That distinction is stated on every page.

## How a quote gets picked

1. **Fetch** ([`fetch.py`](quote_of_the_day/fetch.py)) pulls recent articles mentioning the
   president from [NewsAPI](https://newsapi.org).
2. **Extract**: a quote counts only if it appears inside quotation marks *and* the president's
   name *and* a speech verb ("said", "told", etc.) both appear in the surrounding text. Nothing
   is paraphrased, summarized, or generated -- the text stored is copied verbatim from the
   article.
3. **Group**: near-identical quotes reported by different outlets are merged into one, keeping
   every source.
4. **Pick**: the quote reported by the most distinct outlets that day becomes the quote of the
   day. Ties break toward the most recently published. Every other candidate quote from that day
   is kept too, visible under "Also reported that day," so the pick is never presented as the
   only thing said.
5. **Build** ([`build_site.py`](quote_of_the_day/build_site.py)) renders the static site.

Every quote links to the original article(s) so a reader can verify it themselves -- that link
is the actual guarantee of accuracy, not the extraction heuristic.

## Status

| Stage | Command | Status |
|---|---|---|
| Fetch + pick today's quote | `uv run python -m quote_of_the_day.fetch` | written, sanity-checked against mock articles -- not yet run live (needs a `NEWSAPI_KEY`) |
| Build the static site | `uv run python -m quote_of_the_day.build_site --clean` | working -- verified in-browser, including the Listen button |

## Run it locally

```bash
uv sync
cp .env.example .env   # then fill in NEWSAPI_KEY
uv run python -m quote_of_the_day.fetch
uv run python -m quote_of_the_day.build_site --clean
cd site && python3 -m http.server 8000
```

Then open <http://localhost:8000>.

## Setup

Requires Python 3.10+ and [uv](https://docs.astral.sh/uv/).

```bash
uv python install 3.13
uv sync
```

Copy `.env.example` to `.env` and fill in:

- `NEWSAPI_KEY` -- free, from <https://newsapi.org/register>. Free "Developer" tier: 100
  requests/day, articles delayed ~24h. That's enough for a once-a-day fetch, but that tier isn't
  licensed for a high-traffic commercial site -- check NewsAPI's terms before scaling this up.
- `PRESIDENT_NAME` -- defaults to `Trump`.

`.env` is gitignored. Never commit it.

## Publishing

`.github/workflows/publish.yml` runs once a day (13:00 UTC), fetches that day's quote, commits
the updated archive (`data/quotes.db`) back to `main`, rebuilds the site, and deploys it to
GitHub Pages. It needs a `NEWSAPI_KEY` repository secret (Settings -> Secrets and variables ->
Actions) and Pages set to deploy from GitHub Actions (Settings -> Pages -> Source).

The archive is committed rather than regenerated on every build: a day's pick depends on what
NewsAPI had available at fetch time and can't be recomputed later, so once a day is picked it's
kept permanently.

## Layout

```
quote_of_the_day/   fetch + build pipeline, schema.sql
templates/          Jinja2 templates for the static site
data/quotes.db       SQLite archive of every day's quote        (committed, not gitignored)
site/                build output -- what gets published        (gitignored, regenerable)
```

## License

TBD.
