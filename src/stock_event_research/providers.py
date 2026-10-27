"""Provider adapters. Downloads stay local; API responses are not causal evidence."""
import csv
import hashlib
import json
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


def number(value, *, optional=False):
    text = str(value or '').strip().replace(',', '')
    if not text or text in {'-', 'null', 'None'}:
        if optional:
            return None
        raise ValueError('Required price is missing')
    multiplier = {'K': 1e3, 'M': 1e6, 'B': 1e9}.get(text[-1].upper(), 1)
    result = float(text[:-1] if multiplier != 1 else text) * multiplier
    if not math.isfinite(result):
        raise ValueError('Non-finite numeric value')
    return result


def date_text(value):
    for fmt in ('%Y-%m-%d', '%m/%d/%Y'):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            pass
    raise ValueError(f'Unsupported date: {value}')


def csv_prices(path, symbol, cutoff):
    """Read canonical CSV or Investing.com daily exports; do not invent adjustment."""
    rows, seen = [], set()
    with Path(path).open(encoding='utf-8-sig', newline='') as handle:
        for raw in csv.DictReader(handle):
            date = date_text(raw.get('date', raw.get('Date', '')))
            if date >= cutoff:
                continue
            if date in seen:
                raise ValueError(f'Duplicate date for {symbol}: {date}')
            seen.add(date)
            close = number(raw.get('close', raw.get('Price')))
            adj = number(raw.get('adjusted_close', raw.get('Adj Close')), optional=True)
            if close <= 0 or (adj is not None and adj <= 0):
                raise ValueError(f'Non-positive price for {symbol}')
            volume = number(raw.get('volume', raw.get('Vol.')), optional=True)
            if volume is not None and volume < 0:
                raise ValueError('Volume cannot be negative')
            rows.append(dict(symbol=symbol, date=date, close=close, adjusted_close=adj,
                             volume=int(volume) if volume is not None else None, source='csv'))
    return sorted(rows, key=lambda row: row['date'])


def yahoo_prices(symbol, start, cutoff):
    try:
        import yfinance as yf
    except ImportError as exc:
        raise RuntimeError('Install the online extra: pip install -e ".[online]"') from exc
    error = None
    for attempt in range(3):
        try:
            frame = yf.download(symbol, start=start, end=cutoff, auto_adjust=False,
                                progress=False, threads=False, multi_level_index=False,
                                timeout=20)
            if frame is None or frame.empty:
                raise RuntimeError('Provider returned no rows')
            rows = []
            for index, row in frame.iterrows():
                close = number(row['Close'])
                adjusted = number(row['Adj Close']) if 'Adj Close' in frame.columns else None
                if close <= 0 or (adjusted is not None and adjusted <= 0):
                    raise ValueError('Non-positive online price')
                rows.append(dict(symbol=symbol, date=index.date().isoformat(), close=close,
                                 adjusted_close=adjusted, volume=int(row['Volume']), source='yfinance'))
            return rows
        except Exception as exc:
            error = exc
            if attempt < 2:
                time.sleep(2 ** attempt)
    raise RuntimeError(f'Price download failed for {symbol} after 3 attempts') from error


def article(raw, symbol):
    stamp = datetime.fromisoformat(raw['published_at'].replace('Z', '+00:00'))
    if stamp.tzinfo is None:
        raise ValueError('News timestamps must include a UTC offset')
    url = raw['url'].strip()
    if urlparse(url).scheme not in {'http', 'https'}:
        raise ValueError('News source must be an http(s) URL')
    status = raw.get('evidence_status', 'unreviewed_candidate')
    if status not in {'unreviewed_candidate', 'source_reviewed', 'media_attribution'}:
        raise ValueError('Unknown evidence status')
    return dict(article_id=hashlib.sha256((symbol + url).encode()).hexdigest()[:24],
                symbol=symbol, published_at=stamp.astimezone(timezone.utc).isoformat(),
                title=raw['title'], url=url, publisher=raw.get('publisher', ''), evidence_status=status)


def csv_news(path, allowed_symbols):
    with Path(path).open(encoding='utf-8-sig', newline='') as handle:
        return [article(row, row['symbol']) for row in csv.DictReader(handle)
                if row['symbol'] in allowed_symbols]


def alpha_news(symbol, start, cutoff, cache_dir, limit=1000):
    """One bounded request per ticker. API timestamp interpreted as UTC and documented."""
    key = os.environ.get('ALPHAVANTAGE_API_KEY')
    if not key:
        return [], 'not_configured'
    query = dict(function='NEWS_SENTIMENT', tickers=symbol, time_from=start.replace('-', '')+'T0000',
                 time_to=cutoff.replace('-', '')+'T0000', sort='EARLIEST', limit=limit)
    fingerprint = hashlib.sha256(json.dumps(query, sort_keys=True).encode()).hexdigest()
    cache = Path(cache_dir) / (fingerprint+'.json')
    if cache.exists():
        payload = json.loads(cache.read_text())
    else:
        url = 'https://www.alphavantage.co/query?' + urlencode({**query, 'apikey': key})
        try:
            with urlopen(Request(url, headers={'User-Agent': 'stock-event-research/0.1'}), timeout=30) as response:
                payload = json.load(response)
        except Exception:
            # Do not include the URL or upstream exception: either can contain the key.
            raise RuntimeError('News request failed; check provider access and quota') from None
        if 'feed' not in payload:
            raise RuntimeError('News provider rejected request or returned a quota/access notice')
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(payload))
    rows = []
    for item in payload.get('feed', []):
        if not any(t.get('ticker') == symbol for t in item.get('ticker_sentiment', [])):
            continue
        stamp = datetime.strptime(item['time_published'], '%Y%m%dT%H%M%S').replace(tzinfo=timezone.utc)
        rows.append(article(dict(published_at=stamp.isoformat(),title=item['title'],url=item['url'],
                                 publisher=item.get('source','')), symbol))
    return rows, 'possibly_truncated' if len(payload.get('feed', [])) >= limit else 'partial_provider_coverage'
