# Stock Event Research

[![Tests](https://github.com/Marzma/stock-event-research/actions/workflows/test.yml/badge.svg)](https://github.com/Marzma/stock-event-research/actions/workflows/test.yml)
[![Portfolio](https://github.com/Marzma/stock-event-research/actions/workflows/pages.yml/badge.svg)](https://github.com/Marzma/stock-event-research/actions/workflows/pages.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**[Live portfolio](https://marzma.github.io/stock-event-research/)** · **[Interactive synthetic demo](https://marzma.github.io/stock-event-research/demo/)** · **[Case study](docs/case-study.md)**

A portfolio project by **Marz Ma**. Implementation and documentation were developed with AI assistance, with calculation checks and automated tests made explicit below.

A reproducible, SQL-based research pipeline for configurable equities: download or import prices, detect large positive **and negative** moves, match news candidates, compare macro-event windows with a benchmark, and generate an English report and a portable dashboard.

Built from a Nebius (NBIS) case study. The public repository contains **code and synthetic examples**, not the original downloaded price files, local database, passwords, or private analysis outputs.

## What runs automatically

```text
Watchlist configuration
  -> CSV or online daily prices
  -> validation + SQLite tables
  -> SQL LAG returns + benchmark alignment
  -> strict unrounded large-move screening
  -> timestamp-based news candidate matching
  -> macro-event windows + missing-data statuses
  -> CSV + Markdown report + self-contained HTML dashboard
  -> optional MySQL snapshot export
```

Supports one ticker or a list supported by your data provider. It does **not** promise complete global stock coverage, unlimited news history or verified causal explanations. Run small watchlists first; change market timezone and close time for other exchanges.

## Quick start: no API key or database server

Python 3.10+ is required (3.11 is used in GitHub Actions).

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
stock-research --config examples/demo.json --output artifacts/demo
python -m unittest discover -s tests -v
```

Open `artifacts/demo/index.html` in your browser. The dashboard includes a ticker selector, move-direction and headline filters, candidate evidence links, macro-window metrics, and CSV export. `report.md` is the generated research report.

**The demo uses fictional tickers, synthetic weekday price series and fictional news. It is explicitly labeled and must not be presented as NBIS results or exchange-calendar-validated history.**

## Analyze real equities

```bash
python -m pip install -e '.[online]'
stock-research --config examples/watchlist.json --output artifacts/watchlist
```

The supplied watchlist contains NBIS, AAPL, MSFT and NVDA, with QQQ as benchmark. Modify `tickers`, `benchmark`, `start`, thresholds and horizons. For a fixed historical run, add `end_exclusive` in ISO date format. Without it, the current UTC calendar date is excluded conservatively, even after a market closes. Provider end dates are exclusive.

The Yahoo adapter explicitly requests `auto_adjust=False` and reads `Adj Close` separately. `return_basis: "adjusted"` requires adjusted values for every row; it never silently substitutes raw prices. `price` basis uses raw closing prices, which can exhibit corporate-action jumps. The unofficial yfinance adapter can fail or be rate-limited; it retries three times, then reports failure. See [yfinance API documentation](https://ranaroussi.github.io/yfinance/reference/api/yfinance.download.html) and the [project's data-use notice](https://github.com/ranaroussi/yfinance#readme). A public code license does not grant rights to redistribute provider data.

### Import your Investing.com exports

Copy `examples/demo.json` to **`config.local.json`** (gitignored). Use `price_provider: "csv"`, your tickers and benchmark, and a `price_files` mapping:

```json
{
  "tickers": ["NBIS"],
  "benchmark": "QQQ",
  "price_provider": "csv",
  "price_files": {"NBIS": "data/NBIS.csv", "QQQ": "data/QQQ.csv"},
  "start": "2024-10-21",
  "return_basis": "price",
  "threshold_pct": 5,
  "direction": "both",
  "horizons": [0, 1, 5, 20],
  "macro_events": "examples/fed_cuts.csv",
  "news_provider": "none",
  "market": {"timezone": "America/New_York", "close_time": "16:00:00"}
}
```

Paths resolve relative to the configuration file. Canonical price fields are `date,close,adjusted_close,volume`; `adjusted_close` and volume can be blank. Investing.com's `Date,Price,Open,High,Low,Vol.,Change %` format is also accepted. Its percentage column is not trusted for calculations. Duplicate dates, nonpositive prices and nonfinite numbers fail validation. K/M/B volume values retain the source's rounding. Prices are not independently verified against a second vendor.

## News: automatic collection, explicit review states

Choose `news_provider: "alpha_vantage"` and set the key in your environment:

```bash
export ALPHAVANTAGE_API_KEY='your-local-key'
```

Never put a real key in a JSON file or commit it. The adapter issues at most one bounded request per ticker/run and honors `max_news_requests`. It caches responses locally using a key-free request fingerprint. Missing keys, quota/provider failures, potential 1,000-result truncation and partial coverage are reported explicitly. A single query cannot guarantee a complete long-history news archive. See [Alpha Vantage NEWS_SENTIMENT documentation](https://www.alphavantage.co/documentation/).

Alternatively, use `news_provider: "csv"` with `news_file`. Columns:

```text
symbol,published_at,title,url,publisher,evidence_status
```

`published_at` must contain a timezone offset. Alpha Vantage timestamps are interpreted as UTC, an adapter assumption that should be confirmed for your data entitlement. News matching uses `(previous observed session close, current observed session close]`, handling weekends and after-close publication. It uses a configured close time; **early-close sessions are not modeled**. Use `markets` to override timezone/close time by ticker.

Articles begin as `unreviewed_candidate`. CSV review states can also be `source_reviewed` or `media_attribution`; neither means causal proof. The pipeline does not write LLM-generated explanations or treat sentiment scores as causes. A zero candidate count means no match in the available sources, not no news.

## Macro events and event-study method

The file `examples/fed_cuts.csv` is a **curated, static** announcement calendar verified for this case study. It contains five in-sample cuts; it is not a complete historical series or an automatically refreshed calendar. Update it before extending the study. Use announcement dates, not effective dates. Other event calendars use the same columns:

```text
event_id,date,title,change_bps,source_url
```

- Daily returns are computed with SQL `LAG()` within each symbol **before** joining the benchmark. A benchmark gap does not silently become a two-day daily return.
- Large-move filtering uses Decimal comparison of stored prices so an exactly 5% move is not included because of floating-point noise. Returns are rounded only for display.
- Event windows start at the close before the announcement. Horizon 0 ends on announcement day, and 1/5/20 end that many observed asset sessions afterward.
- Missing event sessions, baselines, adjusted values, endpoints and benchmark endpoints remain unavailable with separate statuses. Summary denominators count available windows explicitly.
- Relative return is asset minus benchmark in **percentage points**, not beta-adjusted alpha.
- Session rows have not been validated against an independent exchange calendar. Missing asset rows can affect observed-session horizons. Add a calendar adapter before relying on this across markets.
- Expected policy, announcement surprises, intraday timing, overlapping company news, selection bias and multiple testing are not modeled. A causal conclusion requires further design.

## GitHub Actions

**Test and demo** runs on pushes and pull requests: unit tests plus a dependency-free synthetic report. It uploads the demo report as a seven-day artifact.

**Analyze watchlist** supports manual runs from the Actions tab. Choose a tracked config under `examples/`. Add `ALPHAVANTAGE_API_KEY` as a repository **secret** for news; it is optional, and absent news is clearly labeled.

Daily runs are **opt-in**: set repository variable `ENABLE_SCHEDULE=true`. The workflow is configured for **02:17 UTC Tuesday-Saturday**, generally after the previous US trading day and after the UTC date changes. GitHub schedules can be delayed; holidays can produce repeated snapshots. Downloads and artifacts follow provider entitlements and repository visibility. In this public repository, review data-sharing rights before enabling real-data artifacts. No real-data results are committed. A separate Pages workflow deploys only the synthetic demo and portfolio on pushes to main.

## Optional MySQL

SQLite makes local runs and Actions reproducible without a server. To keep a snapshot in an existing MySQL database:

```bash
python -m pip install -e '.[mysql]'
# Set MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE locally.
stock-research --config config.local.json --output artifacts/local --mysql
```

The exporter creates `research_runs` if needed and inserts a content-addressed JSON snapshot using parameterized SQL. It does not modify the original NBIS tables. Use a dedicated account with only the needed permissions. `.env.example` documents variable names; this project does not automatically load `.env` files.

## Outputs and repository layout

| Output | Purpose |
|---|---|
| `index.html` | Standalone dashboard; no external JavaScript or live DB access |
| `report.md` | English findings, candidate links and limitations |
| `large_moves.csv` | Both positive/negative qualifying moves and evidence state |
| `daily_returns.csv` | Daily asset/benchmark results |
| `event_windows.csv` | Per-event windows with missing-data status |
| `results.json` | Machine-readable snapshot and provider coverage |
| `research.sqlite` | Local source tables and SQL return view |

```text
src/stock_event_research/
  providers.py     # CSV, Yahoo and Alpha Vantage adapters
  analysis.sql     # schema and window-function calculations
  core.py         # benchmark, event windows and timestamp matching
  cli.py          # validation and orchestration
  report.py       # report generation
  dashboard.html  # portable dashboard template
tests/            # meaningful boundary and integration tests
examples/         # synthetic fixtures and watchlist/calendar configs
.github/workflows/# CI, manual runs and opt-in schedule
```

This is an initial research framework, not a trading strategy, complete news database or production data service. Provider coverage and source review remain part of the research workflow.

## Open source and portfolio

Code and documentation are licensed under [MIT](LICENSE), copyright 2026 Marz Ma. Third-party data, news and service access are not covered by this license.

The [public portfolio](https://marzma.github.io/stock-event-research/) explains the problem, approach, validation and limitations; its embedded dashboard uses only synthetic fixtures. The public build does not need API keys.

```bash
python scripts/build_portfolio.py --output public
```

In repository Settings > Pages, choose **GitHub Actions** as the publishing source. `Publish portfolio` tests the project, builds the synthetic demo and publishes only the explicitly allowlisted public files. Real-data watchlist runs remain separate and opt-in.

See [CONTRIBUTING.md](CONTRIBUTING.md) for development and evidence standards.
