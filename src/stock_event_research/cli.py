import argparse
import csv
import hashlib
import json
import os
import re
import sys
from datetime import datetime,timezone
from decimal import Decimal
from importlib.resources import files
from pathlib import Path
from statistics import mean, median
from . import __version__
from .core import database, returns, event_windows, match_news
from .providers import csv_prices, yahoo_prices, csv_news, alpha_news


def load_config(path):
    path=Path(path).resolve(); config=json.loads(path.read_text());config['_base']=str(path.parent)
    tickers=config.get('tickers',[])
    if not tickers or len(set(tickers)) != len(tickers):
        raise ValueError('tickers must be a nonempty, unique list')
    for symbol in tickers+[config.get('benchmark','QQQ')]:
        if not re.fullmatch(r'[A-Za-z0-9.^=_-]{1,30}',symbol):
            raise ValueError('Invalid ticker identifier')
    if config.get('return_basis','price') not in {'price','adjusted'}:
        raise ValueError('return_basis must be price or adjusted')
    if config.get('threshold_pct',5)<=0:
        raise ValueError('threshold_pct must be positive')
    hs=config.get('horizons',[0,1,5,20])
    if not hs or any(type(h) is not int or h<0 for h in hs) or len(set(hs))!=len(hs):
        raise ValueError('horizons must be unique nonnegative integers')
    if config.get('direction','both') not in {'both','up','down'}:
        raise ValueError('direction must be both, up or down')
    return config


def relative_path(config,value):
    return Path(config['_base'])/value


def write_csv(path, rows):
    # Protect spreadsheet users from formula execution in externally supplied titles.
    def safe(v):
        return "'"+v if isinstance(v,str) and v.startswith(('=','+','-','@','\t','\r')) else v
    with Path(path).open('w',newline='',encoding='utf-8') as handle:
        if rows:
            writer=csv.DictWriter(handle,fieldnames=list(rows[0]));writer.writeheader()
            writer.writerows({k:safe(v) for k,v in row.items()} for row in rows)


def mysql_export(bundle):
    """Optional explicit export; no root password or local paths are stored."""
    import pymysql
    required=['MYSQL_USER','MYSQL_PASSWORD','MYSQL_DATABASE']
    if any(not os.environ.get(k) for k in required):
        raise RuntimeError('Set MYSQL_USER, MYSQL_PASSWORD and MYSQL_DATABASE')
    connection=pymysql.connect(host=os.environ.get('MYSQL_HOST','127.0.0.1'),port=int(os.environ.get('MYSQL_PORT','3306')),
                               user=os.environ['MYSQL_USER'],password=os.environ['MYSQL_PASSWORD'],database=os.environ['MYSQL_DATABASE'])
    try:
        with connection.cursor() as cursor:
            cursor.execute('CREATE TABLE IF NOT EXISTS research_runs (run_id VARCHAR(64) PRIMARY KEY, generated_at VARCHAR(40) NOT NULL, result_json JSON NOT NULL)')
            payload=json.dumps(bundle,allow_nan=False)
            run_id=hashlib.sha256(payload.encode()).hexdigest()
            cursor.execute('INSERT IGNORE INTO research_runs VALUES (%s,%s,%s)',(run_id,bundle['generated_at'],payload))
        connection.commit()
    finally:
        connection.close()


def run(config_path, output, *, mysql=False):
    c=load_config(config_path);output=Path(output);output.mkdir(parents=True,exist_ok=True)
    cutoff=c.get('end_exclusive') or datetime.now(timezone.utc).date().isoformat()
    # Always discard the current UTC date, even if an earlier market has closed.
    cutoff=min(cutoff,datetime.now(timezone.utc).date().isoformat())
    datetime.fromisoformat(cutoff)
    start=c.get('start','2024-01-01');datetime.fromisoformat(start)
    if start>=cutoff:raise ValueError('start must be before end_exclusive')
    benchmark=c.get('benchmark','QQQ');basis=c.get('return_basis','price')
    symbols=list(dict.fromkeys(c['tickers']+[benchmark]));prices=[]
    for symbol in symbols:
        if c.get('price_provider','csv')=='csv':
            if symbol not in c.get('price_files',{}):raise ValueError(f'No CSV configured for {symbol}')
            rows=csv_prices(relative_path(c,c['price_files'][symbol]),symbol,cutoff)
            rows=[r for r in rows if r['date']>=start]
        elif c['price_provider']=='yfinance':rows=yahoo_prices(symbol,start,cutoff)
        else:raise ValueError('Unknown price_provider')
        if len(rows)<2:raise ValueError(f'Need at least two price rows for {symbol}')
        if basis=='adjusted' and any(r['adjusted_close'] is None for r in rows):
            raise ValueError(f'Adjusted basis requested, but adjusted prices are missing for {symbol}')
        prices.extend(rows)
    events=[]
    if c.get('macro_events'):
        with relative_path(c,c['macro_events']).open(newline='') as handle:
            events=list(csv.DictReader(handle))
        for event in events:
            datetime.fromisoformat(event['date'])
            event['change_bps']=int(event['change_bps']) if event['change_bps'] else None
    articles=[];coverage={};provider=c.get('news_provider','none')
    if provider=='csv':
        articles=csv_news(relative_path(c,c['news_file']),c['tickers'])
        coverage={s:'supplied_partial_coverage' for s in c['tickers']}
    elif provider=='alpha_vantage':
        budget=c.get('max_news_requests',5)
        for i,symbol in enumerate(c['tickers']):
            if i>=budget:coverage[symbol]='request_budget_exhausted';continue
            try:
                items,state=alpha_news(symbol,start,cutoff,output/'cache')
                articles.extend(items);coverage[symbol]=state
            except RuntimeError:
                coverage[symbol]='provider_error_or_quota'
    elif provider=='none':coverage={s:'not_configured' for s in c['tickers']}
    else:raise ValueError('Unknown news_provider')
    # A temporary database avoids exposing partially rebuilt results on failure.
    temporary=output/'research.building.sqlite';connection=database(temporary,prices,events,articles)
    results=[];all_moves=[];all_windows=[];all_daily=[]
    try:
        for symbol in c['tickers']:
            daily=returns(connection,symbol,benchmark,basis)
            threshold=c.get('threshold_pct',5);direction=c.get('direction','both')
            def qualifies(row):
                if row['return_pct'] is None:return False
                numerator=row['adjusted_close'] if basis=='adjusted' else row['close']
                denominator=row['previous_adjusted_close'] if basis=='adjusted' else row['previous_close']
                change=(Decimal(str(numerator))/Decimal(str(denominator))-1)*100
                bound=Decimal(str(threshold))
                return ((direction in {'up','both'} and change>bound) or
                        (direction in {'down','both'} and change < -bound))
            moves=[r for r in daily if qualifies(r)]
            market=c.get('markets',{}).get(symbol,c.get('market',{'timezone':'America/New_York','close_time':'16:00:00'}))
            moves=match_news(moves,[a for a in articles if a['symbol']==symbol],market,coverage.get(symbol,'not_configured'))
            windows=event_windows(connection,symbol,benchmark,events,c.get('horizons',[0,1,5,20]),basis)
            valid=[r['return_pct'] for r in daily if r['return_pct'] is not None]
            summaries=[]
            for h in c.get('horizons',[0,1,5,20]):
                ws=[w for w in windows if w['horizon']==h];own=[w['return_pct'] for w in ws if w['return_pct'] is not None]
                rel=[w['relative_return_pp'] for w in ws if w['relative_return_pp'] is not None]
                summaries.append(dict(horizon=h,total_events=len(ws),available_asset_windows=len(own),available_relative_windows=len(rel),
                                      mean_return_pct=mean(own) if own else None,median_return_pct=median(own) if own else None,
                                      mean_relative_pp=mean(rel) if rel else None,positive_windows=sum(v>0 for v in own)))
            results.append(dict(symbol=symbol,daily=daily,moves=moves,windows=windows,summaries=summaries,
                                observed_sessions=len(daily),large_moves=len(moves),news_coverage=coverage.get(symbol),
                                missing_benchmark_returns=sum(r['return_pct'] is not None and r['benchmark_return_pct'] is None for r in daily),
                                market=market,period_return_pct=((next(r for r in reversed(prices) if r['symbol']==symbol)['adjusted_close' if basis=='adjusted' else 'close']/
                                  next(r for r in prices if r['symbol']==symbol)['adjusted_close' if basis=='adjusted' else 'close'])-1)*100))
            for row in moves:
                all_moves.append({'symbol':symbol,**{k:v for k,v in row.items() if k!='articles'},'candidate_urls':' | '.join(a['url'] for a in row['articles'])})
            all_windows.extend(windows);all_daily.extend({'symbol':symbol,**r} for r in daily)
    finally:connection.close()
    temporary.replace(output/'research.sqlite')
    config_public={k:c[k] for k in ('tickers','benchmark','price_provider','return_basis','threshold_pct','direction','horizons','news_provider','market','markets') if k in c}
    bundle=dict(version=__version__,generated_at=datetime.now(timezone.utc).isoformat(),start=start,end_exclusive=cutoff,
                benchmark=benchmark,return_basis=basis,config=config_public,synthetic=bool(c.get('synthetic',False)),results=results,
                limitations=['Descriptive associations, not causal estimates.','Candidate news requires source review.',
                             'Configured close time does not model early closes.','Observed sessions are not validated against an exchange calendar.',
                             'Macro event CSV is a curated snapshot, not an automatically refreshed Fed calendar.',
                             'QQQ subtraction is not beta-adjusted alpha.'])
    (output/'results.json').write_text(json.dumps(bundle,indent=2,allow_nan=False))
    write_csv(output/'large_moves.csv',all_moves);write_csv(output/'event_windows.csv',all_windows);write_csv(output/'daily_returns.csv',all_daily)
    from .report import render
    render(bundle,output)
    if mysql:mysql_export(bundle)
    return bundle


def main():
    parser=argparse.ArgumentParser(description='Analyze configured equities with SQL and explicit news evidence states.')
    parser.add_argument('--config',required=True);parser.add_argument('--output',default='artifacts/latest')
    parser.add_argument('--mysql',action='store_true',help='Also export the result snapshot to an existing MySQL database using environment variables')
    args=parser.parse_args()
    try:
        bundle=run(args.config,args.output,mysql=args.mysql)
    except Exception as exc:
        print(f'Analysis failed ({type(exc).__name__}): {exc}',file=sys.stderr);return 1
    print(f'Completed {len(bundle["results"])} ticker(s). Dashboard: {Path(args.output)/"index.html"}')
    return 0


if __name__=='__main__':raise SystemExit(main())
