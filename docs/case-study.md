# Case study: from NBIS research to a reusable pipeline

## Question

How did NBIS perform around Federal Reserve rate cuts, and which dated announcements coincided with its largest daily price moves?

## Starting point

The original analysis imported NBIS and QQQ CSVs into MySQL, calculated returns with window functions, and connected a manually reviewed event register to a dashboard. It covered 505 completed common sessions from October 21, 2024 through October 26, 2026. The public repository does not redistribute those downloaded files.

## Engineering work

The workflow was generalized into provider adapters, reusable SQL calculations, configuration-driven ticker selection, explicit news evidence states, macro-event window calculations, English report generation and a self-contained dashboard. SQLite makes CI reproducible without a database server; an optional MySQL exporter supports snapshot storage.

The portfolio implementation and documentation were developed with AI assistance. Calculations were checked against the original NBIS study, automated tests were added, and GitHub Actions runs the tests and synthetic demo independently.

## Validation

- The general pipeline reproduced all 118 strictly greater-than-5% NBIS rally dates from the original CSV study.
- All 20 original macro windows matched within 0.00002 percentage points.
- Separate tests cover exact thresholds, adjusted prices through splits, benchmark date gaps, missing windows, after-close/weekend news and untrusted source text.
- An online AAPL/QQQ price-download smoke test completed locally. The live Alpha Vantage news API and optional MySQL exporter have not received end-to-end online validation.

These regression results refer to the private original inputs, not to the public synthetic demo. They are author-reported checks; the published fixture tests can be reproduced directly in CI.

## Findings and limits

In the original five-cut sample, NBIS rose on three announcement days and four twenty-day windows. Every twenty-day window contained at least one recorded overlapping event. These results describe association, not a policy effect. Initial searches across 118 rally dates did not constitute complete source review.

The public dashboard displays the original NBIS/QQQ case study and its recorded evidence, including incomplete-review states. Separate synthetic fixtures remain available for reproducible pipeline tests. Macro calendars are curated inputs; early closes, market-calendar validation, policy surprises and beta-adjusted abnormal returns remain outside the initial implementation.

## Reuse

Change a ticker list and benchmark in a JSON configuration, choose a price/news provider, and run one command to produce a new study. Global coverage depends on provider support and market settings; this is not a universal-market or production-grade data service.
