"""Stage 2 -- render the static site into site/.

Plain HTML, one page per day plus an archive index. The only script on the
page is the play button, which hands the quote text to the browser's own
`speechSynthesis` -- no audio files, no server, nothing that could be
mistaken for the president's actual voice.
"""

from __future__ import annotations

import argparse
import shutil
from datetime import datetime

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .db import SITE_DIR, TEMPLATE_DIR, connect


def pretty_date(value: str) -> str:
    return datetime.strptime(value, "%Y-%m-%d").strftime("%B %-d, %Y")


def load_days(conn) -> list[dict]:
    dates = [r["date"] for r in conn.execute(
        "SELECT DISTINCT date FROM quotes ORDER BY date DESC")]

    days = []
    for date in dates:
        qotd_row = conn.execute(
            "SELECT * FROM quotes WHERE date = ? AND is_qotd = 1", (date,)
        ).fetchone()
        if not qotd_row:
            continue
        sources = conn.execute(
            "SELECT * FROM quote_sources WHERE quote_id = ? ORDER BY published_at",
            (qotd_row["id"],),
        ).fetchall()
        others = conn.execute(
            "SELECT * FROM quotes WHERE date = ? AND is_qotd = 0 "
            "ORDER BY source_count DESC LIMIT 5", (date,),
        ).fetchall()

        days.append({
            "date": date,
            "date_label": pretty_date(date),
            "text": qotd_row["text"],
            "source_count": qotd_row["source_count"],
            "sources": [dict(s) for s in sources],
            "other_quotes": [dict(o) for o in others],
            "page": f"days/{date}.html",
        })
    return days


def render(env, template: str, out_path, **context) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(env.get_template(template).render(**context), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Render the static site into site/.")
    parser.add_argument("--clean", action="store_true", help="Delete site/ before building.")
    args = parser.parse_args()

    conn = connect()
    days = load_days(conn)
    if not days:
        raise SystemExit("No quotes found. Run `fetch-quote` first.")

    if args.clean and SITE_DIR.exists():
        shutil.rmtree(SITE_DIR)
    SITE_DIR.mkdir(parents=True, exist_ok=True)

    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=select_autoescape(["html"]))
    env.globals["now"] = datetime.now().strftime("%B %d, %Y")

    latest, archive = days[0], days[1:]

    render(env, "index.html", SITE_DIR / "index.html", day=latest, archive=archive, depth="")
    for day in days:
        render(env, "day.html", SITE_DIR / day["page"], day=day, is_latest=(day is latest),
               depth="../")
    render(env, "archive.html", SITE_DIR / "archive.html", days=days, depth="")

    shutil.copy(TEMPLATE_DIR / "style.css", SITE_DIR / "style.css")

    print(f"Built {len(days)} days. Latest: {latest['date']}.")
    print(f"Open: {SITE_DIR / 'index.html'}")


if __name__ == "__main__":
    main()
