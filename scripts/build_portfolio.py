"""Publish the curated NBIS case study, without databases or private work files."""
import argparse
import json
import re
import shutil
from pathlib import Path

FILES = ('index.html', 'rally_dates.csv', 'rate_cut_windows.csv', 'event_register.csv')


def build(output):
    root = Path(__file__).resolve().parents[1]
    output = Path(output).resolve()
    if output == root or root.is_relative_to(output):
        raise ValueError('Output must be a dedicated generated directory')
    source = root / 'site'
    html = (source / 'index.html').read_text()
    match = re.search(r'window.RESEARCH_DATA = (.*?);\s*\n', html)
    if not match:
        raise ValueError('NBIS research snapshot missing')
    data = json.loads(match.group(1))
    if len(data['rallies']) != 118 or len(data['windows']) != 20 or len(data['prices']) != 505:
        raise ValueError('Unexpected NBIS snapshot coverage')
    if '/Users/' in html or 'localhost' in html:
        raise ValueError('Local machine reference in public page')
    output.mkdir(parents=True, exist_ok=True)
    allowed = set(FILES) | {'.nojekyll', 'demo'}
    if {p.name for p in output.iterdir()} - allowed:
        raise ValueError('Unexpected files in public output directory')
    demo = output / 'demo'
    if demo.exists():
        if demo.is_symlink():
            raise ValueError('Public demo cannot be a symlink')
        shutil.rmtree(demo)
    demo.mkdir()
    # Keep the previously shared /demo/ URL working with the same NBIS case.
    for name in FILES:
        shutil.copyfile(source / name, output / name)
        shutil.copyfile(source / name, demo / name)
    (output / '.nojekyll').write_text('')
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='public')
    print(build(parser.parse_args().output))
