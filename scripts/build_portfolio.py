"""Build a public portfolio using only the explicitly synthetic demo."""
import argparse
import json
import shutil
from pathlib import Path

from stock_event_research.cli import run


def build(output):
    root = Path(__file__).resolve().parents[1]
    output = Path(output).resolve()
    if output == root or root.is_relative_to(output):
        raise ValueError('Output must be a dedicated generated directory')
    config = root / 'examples/demo.json'
    settings = json.loads(config.read_text())
    if settings.get('synthetic') is not True or settings.get('price_provider') != 'csv':
        raise ValueError('Public portfolio must use the synthetic offline demo')
    if settings.get('tickers') != ['DEMO', 'ALT'] or settings.get('benchmark') != 'BENCH':
        raise ValueError('Public portfolio ticker allowlist does not match')
    # Build outside the published directory: do not publish the SQLite DB or cache.
    staging = root / 'artifacts/portfolio-build'
    result = run(config, staging)
    if not result['synthetic']:
        raise ValueError('Synthetic provenance marker missing')
    output.mkdir(parents=True, exist_ok=True)
    # The deploy workflow starts clean. Fail on unexpected preexisting files rather
    # than accidentally publishing a previous real-data output directory.
    allowed = {'index.html', '.nojekyll', 'demo'}
    unexpected = {p.name for p in output.iterdir()} - allowed
    if unexpected:
        raise ValueError('Unexpected files in public output directory')
    demo = output / 'demo'
    if demo.exists():
        if demo.is_symlink():
            raise ValueError('Public demo cannot be a symlink')
        shutil.rmtree(demo)
    demo.mkdir()
    for name in ['index.html', 'report.md', 'large_moves.csv', 'event_windows.csv', 'daily_returns.csv']:
        shutil.copyfile(staging / name, demo / name)
    shutil.copyfile(root / 'site/index.html', output / 'index.html')
    (output / '.nojekyll').write_text('')
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='public')
    print(build(parser.parse_args().output))
