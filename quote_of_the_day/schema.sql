-- One row per qualifying speaker turn by the president in a given day's
-- transcript(s). "text" is copied verbatim from the transcript paragraph(s)
-- between speaker labels -- nothing here is ever paraphrased, trimmed, or
-- generated.
CREATE TABLE IF NOT EXISTS quotes (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    date             TEXT NOT NULL,          -- YYYY-MM-DD, the day this was picked/seen
    speaker          TEXT NOT NULL,          -- the transcript's own label, e.g. "Donald Trump"
    text             TEXT NOT NULL,
    word_count       INTEGER NOT NULL,
    is_qotd          INTEGER NOT NULL DEFAULT 0,  -- 1 for the day's chosen (longest) turn
    transcript_title TEXT,
    transcript_url   TEXT NOT NULL,
    published_at     TEXT,                   -- the transcript's own datePublished
    first_seen_at    TEXT NOT NULL,
    UNIQUE(date, text)
);

CREATE INDEX IF NOT EXISTS idx_quotes_date ON quotes(date);
