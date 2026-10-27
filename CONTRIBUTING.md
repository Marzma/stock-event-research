# Contributing

Contributions are welcome. Open an issue describing the research or engineering problem before proposing a substantial change.

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m unittest discover -s tests -v
python scripts/build_portfolio.py --output public
```

Please include meaningful tests for changes to return calculations, session matching, news timestamps or missing-data handling. Keep the demo offline and reproducible. Use synthetic fixtures rather than committing provider price histories or article bodies.

## Research standards

- Cite an original source where possible; preserve announcement timestamps and time zones.
- Distinguish candidate matches, reviewed sources and media attribution.
- Never replace missing data with a zero return or invent a reason for a price move.
- Keep corporate-action adjustment and benchmark conventions explicit.
- Do not claim causal effects from descriptive event windows.

## Pull requests

Explain the problem, changed behavior, validation and remaining limitations. Never include API keys, local credentials, `.env` files, database snapshots or personal paths. By contributing, you agree to license your contribution under this project's MIT license. Data from third-party services remains subject to its own terms.
