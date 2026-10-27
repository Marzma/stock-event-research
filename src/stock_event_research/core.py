"""SQL calculations and explicit evidence matching, independent of data providers."""
import json
import sqlite3
from collections import defaultdict
from datetime import datetime, time, timezone
from importlib.resources import files
from zoneinfo import ZoneInfo


def database(path, prices, events, articles):
    connection = sqlite3.connect(str(path))
    connection.row_factory = sqlite3.Row
    connection.executescript(files(__package__).joinpath('analysis.sql').read_text())
    with connection:
        for table in ('prices', 'macro_events', 'articles'):
            connection.execute('DELETE FROM '+table)
        connection.executemany('INSERT INTO prices VALUES (:symbol,:date,:close,:adjusted_close,:volume,:source)',prices)
        connection.executemany('INSERT INTO macro_events VALUES (:event_id,:date,:title,:change_bps,:source_url)',events)
        unique = {a['article_id']:a for a in articles}
        connection.executemany('INSERT INTO articles VALUES (:article_id,:symbol,:published_at,:title,:url,:publisher,:evidence_status)',unique.values())
    return connection


def returns(connection, symbol, benchmark, basis):
    """Calculate each series before joining. Never bridge missing benchmark sessions."""
    field = {'price':'price_return_pct', 'adjusted':'adjusted_return_pct'}[basis]
    query = f'''SELECT a.date,a.previous_date,a.close,a.adjusted_close,a.previous_close,a.previous_adjusted_close,a.volume,a.{field} AS return_pct,
        CASE WHEN a.previous_date=b.previous_date THEN b.{field} END AS benchmark_return_pct,
        CASE WHEN a.previous_date=b.previous_date THEN a.{field}-b.{field} END AS relative_return_pp
        FROM price_returns a LEFT JOIN price_returns b ON b.symbol=? AND a.date=b.date
        WHERE a.symbol=? ORDER BY a.date'''
    return [dict(row) for row in connection.execute(query,(benchmark,symbol))]


def event_windows(connection, symbol, benchmark, events, horizons, basis):
    field = 'adjusted_close' if basis == 'adjusted' else 'close'
    prices = [dict(row) for row in connection.execute('SELECT * FROM prices WHERE symbol=? ORDER BY date',(symbol,))]
    indexes = {p['date']:i for i,p in enumerate(prices)}
    bench = {p['date']:dict(p) for p in connection.execute('SELECT * FROM prices WHERE symbol=?',(benchmark,))}
    rows=[]
    for event in events:
        i=indexes.get(event['date'])
        for horizon in horizons:
            result=dict(symbol=symbol,event_id=event['event_id'],event_date=event['date'],title=event['title'],
                        horizon=horizon,baseline_date=None,end_date=None,return_pct=None,
                        benchmark_return_pct=None,relative_return_pp=None,status='event_session_missing',source_url=event['source_url'])
            if i is not None and i == 0:
                result['status']='baseline_missing'
            elif i is not None and i > 0:
                baseline=prices[i-1];result['baseline_date']=baseline['date']
                if i+horizon >= len(prices):
                    result['status']='endpoint_missing'
                else:
                    end=prices[i+horizon];result['end_date']=end['date']
                    b0,b1=bench.get(baseline['date']),bench.get(end['date'])
                    if baseline[field] is None or end[field] is None:
                        result['status']='adjusted_price_missing'
                    else:
                        result['return_pct']=(end[field]/baseline[field]-1)*100
                        if not b0 or not b1 or b0[field] is None or b1[field] is None:
                            result['status']='benchmark_endpoint_missing'
                        else:
                            result['benchmark_return_pct']=(b1[field]/b0[field]-1)*100
                            result['relative_return_pp']=result['return_pct']-result['benchmark_return_pct']
                            result['status']='complete'
            rows.append(result)
    return rows


def match_news(moves, articles, market, coverage):
    """Match prior-close -> current-close by published time, not calendar date alone.

    Configured close time is an approximation: early closes and intraday reactions
    are NOT inferred. Candidate matching is deliberately not causal attribution.
    """
    zone=ZoneInfo(market['timezone']);closing=time.fromisoformat(market['close_time'])
    stamps=[(datetime.fromisoformat(a['published_at']),a) for a in articles]
    matched=[]
    for move in moves:
        start=datetime.combine(datetime.fromisoformat(move['previous_date']).date(),closing,zone).astimezone(timezone.utc)
        end=datetime.combine(datetime.fromisoformat(move['date']).date(),closing,zone).astimezone(timezone.utc)
        candidates=[a for stamp,a in stamps if start < stamp <= end]
        matched.append({**move,'news_window_start_utc':start.isoformat(),'news_window_end_utc':end.isoformat(),
                        'candidate_count':len(candidates),'articles':candidates,'news_coverage':coverage,
                        'research_status':'candidates_need_review' if candidates else 'no_match_in_available_sources'})
    return matched
