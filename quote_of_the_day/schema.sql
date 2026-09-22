-- One row per distinct quote text seen on a given day. "text" is normalized
-- whitespace/quote-marks but otherwise verbatim from the source article --
-- nothing here is ever paraphrased or reworded.
CREATE TABLE IF NOT EXISTS quotes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    date          TEXT NOT NULL,          -- YYYY-MM-DD, the day this was picked/seen
    text          TEXT NOT NULL,
    is_qotd       INTEGER NOT NULL DEFAULT 0,  -- 1 for the day's chosen quote
    source_count  INTEGER NOT NULL DEFAULT 0,
    first_seen_at TEXT NOT NULL,
    UNIQUE(date, text)
);

CREATE INDEX IF NOT EXISTS idx_quotes_date ON quotes(date);

-- Every outlet that reported a given quote, so a reader can verify it
-- against more than one source and click through to the original article.
CREATE TABLE IF NOT EXISTS quote_sources (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    quote_id      INTEGER NOT NULL REFERENCES quotes(id),
    outlet        TEXT NOT NULL,
    article_title TEXT,
    article_url   TEXT NOT NULL,
    published_at  TEXT,
    UNIQUE(quote_id, article_url)
);
