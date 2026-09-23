"""Stage 1 -- pull today's transcript(s) and pick the most rambling turn.

Source is Rev.com's transcripts of the president's own speeches, rallies,
and press events (https://www.rev.com/category/donald-trump). Rev
transcribes every speaker turn verbatim, including asides, false starts,
and tangents -- exactly the material a "quote of the day" made of soundbites
would cut out.

A transcript page is a sequence of <p> tags inside <div id="main-content">.
A turn starts with a label paragraph like "Donald Trump (01:22): " (name,
then a parenthesized timestamp link, then a colon, nothing else) and
continues through every following paragraph until the next label paragraph.
`TranscriptParser` below walks that structure directly; nothing is
paraphrased or reworded -- the text stored is exactly what's between labels.

"Quote of the day" is simply the president's longest qualifying turn that
day -- the most rambling thing he said on the record, not the most quoted.
"""

from __future__ import annotations

import argparse
import os
import re
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser

import httpx
from dotenv import load_dotenv

from .db import connect

CATEGORY_URL = "https://www.rev.com/category/donald-trump"
TRANSCRIPT_LINK_RE = re.compile(r'href="(/transcripts/[a-z0-9\-]+)"')
DATE_PUBLISHED_RE = re.compile(r'"datePublished":\s*"(\d{4}-\d{2}-\d{2})')
HEADLINE_RE = re.compile(r'"headline":\s*"((?:[^"\\]|\\.)*)"')

# A turn-label paragraph, once its own inner tags are stripped to plain text:
# "Donald Trump (01:22): " or "Audience (00:52): " -- a name, a parenthesized
# timestamp, a colon, and nothing else.
LABEL_RE = re.compile(r"^([A-Za-z][A-Za-z .'\-]{1,40})\s*\(\s*\d{1,2}:\d{2}(?::\d{2})?\s*\)\s*:\s*$")
# The same timestamp marker when it prefixes a continuation paragraph instead
# of standing alone, e.g. "(00:52)God bless the USA." -- strip it, keep the text.
LEADING_TIMESTAMP_RE = re.compile(r"^\(\s*\d{1,2}:\d{2}(?::\d{2})?\s*\)\s*")

MIN_WORDS = 50  # below this, a turn is a reaction, not a ramble
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; quote-of-the-day/0.1)"}


class TranscriptParser(HTMLParser):
    """Collects the plain text of every <p> inside <div id="main-content">, in order."""

    def __init__(self):
        super().__init__()
        self.depth = 0
        self.target_depth = None
        self.in_p = False
        self._buf: list[str] = []
        self.paragraphs: list[str] = []

    def handle_starttag(self, tag, attrs):
        self.depth += 1
        if tag == "div" and self.target_depth is None and dict(attrs).get("id") == "main-content":
            self.target_depth = self.depth
        if self.target_depth is not None and tag == "p":
            self.in_p = True
            self._buf = []

    def handle_endtag(self, tag):
        if self.target_depth is not None and tag == "p" and self.in_p:
            self.paragraphs.append("".join(self._buf).strip())
            self.in_p = False
        if tag == "div" and self.target_depth is not None and self.depth == self.target_depth:
            self.target_depth = -1  # sentinel: already closed, never matches again
        self.depth -= 1

    def handle_data(self, data):
        if self.in_p:
            self._buf.append(data)


def parse_turns(html: str) -> list[dict]:
    """Group a transcript's paragraphs into (speaker, text) turns."""
    parser = TranscriptParser()
    parser.feed(html)

    turns = []
    speaker, buf = None, []
    for para in parser.paragraphs:
        label = LABEL_RE.match(para)
        if label:
            if speaker and buf:
                turns.append({"speaker": speaker, "text": " ".join(buf).strip()})
            speaker, buf = label.group(1).strip(), []
            continue
        cleaned = LEADING_TIMESTAMP_RE.sub("", para).strip()
        if cleaned:
            buf.append(cleaned)
    if speaker and buf:
        turns.append({"speaker": speaker, "text": " ".join(buf).strip()})
    return turns


def president_turns(turns: list[dict], president_name: str, min_words: int = MIN_WORDS) -> list[dict]:
    name = president_name.lower()
    out = []
    for turn in turns:
        if name not in turn["speaker"].lower():
            continue
        words = turn["text"].split()
        if len(words) >= min_words:
            out.append({**turn, "word_count": len(words)})
    return out


def discover_transcript_urls(client: httpx.Client, limit: int = 20) -> list[str]:
    resp = client.get(CATEGORY_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    seen, urls = set(), []
    for path in TRANSCRIPT_LINK_RE.findall(resp.text):
        if path not in seen:
            seen.add(path)
            urls.append(f"https://www.rev.com{path}")
        if len(urls) >= limit:
            break
    return urls


def fetch_transcript(client: httpx.Client, url: str) -> dict | None:
    resp = client.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    html = resp.text

    date_match = DATE_PUBLISHED_RE.search(html)
    if not date_match:
        return None
    headline_match = HEADLINE_RE.search(html)
    headline = headline_match.group(1).encode().decode("unicode_escape") if headline_match else None

    return {
        "url": url,
        "published_date": date_match.group(1),
        "title": headline,
        "turns": parse_turns(html),
    }


def choose_qotd(candidates: list[dict]) -> dict | None:
    """The longest qualifying turn wins -- the most rambling thing said, full stop."""
    if not candidates:
        return None
    return max(candidates, key=lambda c: c["word_count"])


def store_day(conn, date: str, candidates: list[dict], qotd_text: str | None) -> None:
    now = datetime.now(timezone.utc).isoformat()
    for c in candidates:
        conn.execute(
            "INSERT INTO quotes (date, speaker, text, word_count, is_qotd, "
            "transcript_title, transcript_url, published_at, first_seen_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(date, text) DO UPDATE SET "
            "word_count=excluded.word_count, is_qotd=excluded.is_qotd",
            (date, c["speaker"], c["text"], c["word_count"],
             1 if c["text"] == qotd_text else 0,
             c["transcript_title"], c["transcript_url"], c["published_date"], now),
        )
    conn.commit()


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Fetch the longest presidential ramble per day.")
    parser.add_argument("--date", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                         help="Most recent day to consider (YYYY-MM-DD). Default: today (UTC).")
    parser.add_argument("--lookback-days", type=int, default=1,
                         help="Also consider transcripts published up to this many days before "
                              "--date -- each gets its OWN pick under its own real date, never "
                              "relabeled as --date. Default: 1.")
    parser.add_argument("--scan", type=int, default=20,
                         help="How many of the most recent transcript pages to check. Default: 20.")
    args = parser.parse_args()

    president_name = os.environ.get("PRESIDENT_NAME", "Trump")
    target = datetime.strptime(args.date, "%Y-%m-%d").date()
    earliest = target - timedelta(days=args.lookback_days)

    with httpx.Client(follow_redirects=True) as client:
        urls = discover_transcript_urls(client, limit=args.scan)
        by_date: dict[str, list] = {}
        checked_dates = []
        for url in urls:
            transcript = fetch_transcript(client, url)
            if not transcript:
                continue
            pub_date_str = transcript["published_date"]
            pub_date = datetime.strptime(pub_date_str, "%Y-%m-%d").date()
            checked_dates.append(pub_date)
            if not (earliest <= pub_date <= target):
                continue
            turns = president_turns(transcript["turns"], president_name)
            if not turns:
                continue
            by_date.setdefault(pub_date_str, []).extend(
                {**turn, "transcript_url": transcript["url"],
                 "transcript_title": transcript["title"],
                 "published_date": pub_date_str}
                for turn in turns
            )

    if not by_date:
        newest = max(checked_dates) if checked_dates else None
        print(f"No qualifying {president_name} turns found between {earliest} and {target} "
              f"(newest transcript checked: {newest}). Nothing written.")
        return

    conn = connect()
    for date, candidates in sorted(by_date.items()):
        qotd = choose_qotd(candidates)
        store_day(conn, date, candidates, qotd["text"])
        print(f"{date}: {len(candidates)} qualifying turns across "
              f"{len({c['transcript_url'] for c in candidates})} transcript(s).")
        print(f"  Quote of the day ({qotd['word_count']} words, from {qotd['transcript_title']!r}):")
        print(f"    {qotd['text'][:200]}{'...' if len(qotd['text']) > 200 else ''}")


if __name__ == "__main__":
    main()
