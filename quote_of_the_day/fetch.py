"""Stage 1 -- pull today's candidate quotes from the news and pick one.

Every quote stored here is text that appeared inside quotation marks in a
real news article, next to the president's name and a speech verb ("said",
"told", etc). Nothing is paraphrased or generated: the heuristic in
`extract_quotes` decides what *counts* as a quote, but never changes the
words. Every quote keeps a link back to the source article so a reader can
check it themselves -- that link is the actual guarantee of accuracy, not
the heuristic.

"Quote of the day" is the candidate reported, worded the same way, by the
most distinct outlets that day. Ties break toward the most recently
published.
"""

from __future__ import annotations

import argparse
import os
import re
from datetime import datetime, timedelta, timezone

import httpx
from dotenv import load_dotenv

from .db import connect

NEWSAPI_URL = "https://newsapi.org/v2/everything"

# Straight or curly double quotes around 15-300 chars of inner text.
QUOTE_RE = re.compile(r'[“"]([^"“”]{15,300})[”"]')
SPEECH_VERB_RE = re.compile(r"\b(said|says|saying|wrote|writes|posted|told|tells|"
                            r"tweeted|claimed|claims|added|continued|argued|insisted)\b",
                            re.IGNORECASE)

# NewsAPI truncates `content` on the free tier with a trailing marker like
# "... [+1234 chars]" -- strip it so it can't be mistaken for article text.
TRUNCATION_RE = re.compile(r"\s*\[\+\d+ chars\]\s*$")


def _article_text(article: dict) -> str:
    parts = [article.get("title") or "", article.get("description") or "",
             TRUNCATION_RE.sub("", article.get("content") or "")]
    return "\n".join(p for p in parts if p)


def extract_quotes(text: str, president_name: str) -> list[str]:
    """Quoted spans that sit near both the president's name and a speech verb.

    Both checks look within a fixed window of the quote rather than the
    quote's own contents, so a quote never has to *mention* the president by
    name to count -- it just has to be attributed to him in the surrounding
    sentence.
    """
    name = president_name.lower()
    found = []
    for match in QUOTE_RE.finditer(text):
        quote = re.sub(r"\s+", " ", match.group(1)).strip()
        if len(quote) < 15:
            continue
        start, end = match.span()
        wide = text[max(0, start - 200):end + 200].lower()
        near = text[max(0, start - 60):start] + text[end:end + 60]
        if name in wide and SPEECH_VERB_RE.search(near):
            found.append(quote)
    return found


def _normalize_key(quote: str) -> str:
    return re.sub(r"\s+", " ", quote.strip().lower()).strip("\"'“” .,")


def fetch_articles(client: httpx.Client, api_key: str, president_name: str,
                    from_date: str) -> list[dict]:
    resp = client.get(NEWSAPI_URL, params={
        "q": f'"{president_name}"',
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": 100,
        "from": from_date,
        "apiKey": api_key,
    }, timeout=30)
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("status") != "ok":
        raise RuntimeError(f"NewsAPI error: {payload.get('message', payload)}")
    return payload.get("articles", [])


def group_quotes(articles: list[dict], president_name: str) -> list[dict]:
    """Dedupe near-identical quotes across articles, keeping every source."""
    groups: dict[str, dict] = {}
    for article in articles:
        text = _article_text(article)
        source_name = (article.get("source") or {}).get("name") or "Unknown outlet"
        for quote in extract_quotes(text, president_name):
            key = _normalize_key(quote)
            group = groups.setdefault(key, {"text": quote, "sources": {}})
            if len(quote) > len(group["text"]):
                group["text"] = quote
            # keyed by (outlet, url) so a re-run doesn't double-count a source
            group["sources"][(source_name, article.get("url") or "")] = {
                "outlet": source_name,
                "article_title": article.get("title"),
                "article_url": article.get("url"),
                "published_at": article.get("publishedAt"),
            }
    return [
        {"text": g["text"], "sources": list(g["sources"].values()),
         "outlet_count": len({s["outlet"] for s in g["sources"].values()})}
        for g in groups.values()
    ]


def choose_qotd(groups: list[dict]) -> dict | None:
    if not groups:
        return None
    def sort_key(g):
        latest = max((s["published_at"] or "" for s in g["sources"]), default="")
        return (g["outlet_count"], latest)
    return max(groups, key=sort_key)


def store_day(conn, date: str, groups: list[dict], qotd_text: str | None) -> None:
    now = datetime.now(timezone.utc).isoformat()
    for group in groups:
        cur = conn.execute(
            "INSERT INTO quotes (date, text, is_qotd, source_count, first_seen_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(date, text) DO UPDATE SET "
            "source_count=excluded.source_count, is_qotd=excluded.is_qotd "
            "RETURNING id",
            (date, group["text"], 1 if group["text"] == qotd_text else 0,
             group["outlet_count"], now),
        )
        quote_id = cur.fetchone()[0]
        for source in group["sources"]:
            conn.execute(
                "INSERT OR IGNORE INTO quote_sources "
                "(quote_id, outlet, article_title, article_url, published_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (quote_id, source["outlet"], source["article_title"],
                 source["article_url"], source["published_at"]),
            )
    conn.commit()


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Fetch today's candidate presidential quotes.")
    parser.add_argument("--date", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                         help="Date to file the pick under (YYYY-MM-DD). Default: today (UTC).")
    parser.add_argument("--lookback-days", type=int, default=1,
                         help="How many days back to search for articles. Default: 1.")
    args = parser.parse_args()

    api_key = os.environ.get("NEWSAPI_KEY")
    if not api_key:
        raise SystemExit("NEWSAPI_KEY is not set. Copy .env.example to .env and fill it in.")
    president_name = os.environ.get("PRESIDENT_NAME", "Trump")

    from_date = (datetime.now(timezone.utc) - timedelta(days=args.lookback_days)).strftime("%Y-%m-%d")

    with httpx.Client() as client:
        articles = fetch_articles(client, api_key, president_name, from_date)

    groups = group_quotes(articles, president_name)
    if not groups:
        print(f"No attributable quotes found in {len(articles)} articles for {args.date}. "
              "Nothing written.")
        return

    qotd = choose_qotd(groups)
    conn = connect()
    store_day(conn, args.date, groups, qotd["text"])

    print(f"{args.date}: {len(articles)} articles, {len(groups)} distinct quotes.")
    print(f"Quote of the day ({qotd['outlet_count']} outlets): {qotd['text']!r}")


if __name__ == "__main__":
    main()
