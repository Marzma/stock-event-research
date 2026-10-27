CREATE TABLE IF NOT EXISTS prices (
    symbol TEXT NOT NULL,
    date TEXT NOT NULL,
    close REAL NOT NULL CHECK(close > 0),
    adjusted_close REAL CHECK(adjusted_close > 0),
    volume INTEGER,
    source TEXT NOT NULL,
    PRIMARY KEY(symbol, date)
);
CREATE TABLE IF NOT EXISTS macro_events (
    event_id TEXT PRIMARY KEY,
    date TEXT NOT NULL,
    title TEXT NOT NULL,
    change_bps INTEGER,
    source_url TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS articles (
    article_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    published_at TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    publisher TEXT NOT NULL,
    evidence_status TEXT NOT NULL
);
CREATE VIEW IF NOT EXISTS price_returns AS
SELECT symbol, date, close, adjusted_close, volume, source,
       LAG(date) OVER (PARTITION BY symbol ORDER BY date) AS previous_date,
       LAG(close) OVER (PARTITION BY symbol ORDER BY date) AS previous_close,
       LAG(adjusted_close) OVER (PARTITION BY symbol ORDER BY date) AS previous_adjusted_close,
       (close / LAG(close) OVER (PARTITION BY symbol ORDER BY date) - 1) * 100 AS price_return_pct,
       (adjusted_close / LAG(adjusted_close) OVER (PARTITION BY symbol ORDER BY date) - 1) * 100 AS adjusted_return_pct
FROM prices;
