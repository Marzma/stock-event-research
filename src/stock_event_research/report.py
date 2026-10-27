"""English research report and self-contained interactive dashboard."""
import html
import json
from importlib.resources import files


def fmt(value):return 'unavailable' if value is None else f'{value:+.2f}'


def render(bundle, output):
    lines=['# Stock Event Research',f'Generated: {bundle["generated_at"]}',
           f'Period: {bundle["start"]} to {bundle["end_exclusive"]} (exclusive). Benchmark: {bundle["benchmark"]}. Return basis: {bundle["return_basis"]}.']
    if bundle['synthetic']:lines.append('**SYNTHETIC DEMO DATA. These are not real security prices or real news.**')
    for result in bundle['results']:
        lines.extend([f'## {result["symbol"]}',f'Observed sessions: {result["observed_sessions"]}; large moves: {result["large_moves"]}; news coverage: {result["news_coverage"]}.',
                      f'Period return: {fmt(result["period_return_pct"])}%. Missing benchmark returns: {result["missing_benchmark_returns"]}.',
                      '### Largest absolute daily moves','| Date | Asset % | Benchmark % | Relative pp | News candidates |','|---|---:|---:|---:|---:|'])
        for move in sorted(result['moves'],key=lambda m:abs(m['return_pct']),reverse=True)[:15]:
            lines.append(f'| {move["date"]} | {fmt(move["return_pct"])} | {fmt(move["benchmark_return_pct"])} | {fmt(move["relative_return_pp"])} | {move["candidate_count"]} |')
        lines.extend(['### Macro event windows','| Horizon | Available / total | Mean % | Median % | Positive |','|---|---:|---:|---:|---:|'])
        for summary in result['summaries']:
            n=summary['available_asset_windows'];lines.append(f'| {summary["horizon"]} | {n}/{summary["total_events"]} | {fmt(summary["mean_return_pct"])} | {fmt(summary["median_return_pct"])} | {summary["positive_windows"]}/{n} |')
        lines.append('### Candidate source links (not verified causes)')
        seen=set()
        for move in result['moves']:
            for article in move['articles']:
                if article['article_id'] in seen:continue
                seen.add(article['article_id'])
                title=article['title'].replace('[','(').replace(']',')').replace('\n',' ')
                lines.append(f'- {article["published_at"]}: [{title}]({article["url"]}) - {article["evidence_status"]}')
    lines.append('## Method and limitations')
    lines.extend('- '+item for item in bundle['limitations'])
    lines.extend(['- Daily returns use SQL LAG within each ticker before benchmark matching. A missing benchmark day cannot be silently bridged.',
                  '- Event-window baseline is the immediately preceding observed asset session. Missing baselines/endpoints remain null.',
                  '- Prior-close to current-close news matching accounts for time zones and weekends, but uses a configured closing time.',
                  '- API errors, quotas, truncation and absent keys remain explicit coverage states. No LLM-generated causal attribution is used.',
                  '- Scope depends on ticker/provider support, historical coverage, quotas, market settings and curated event coverage.'])
    (output/'report.md').write_text('\n\n'.join(lines)+'\n')
    template=files(__package__).joinpath('dashboard.html').read_text()
    data=json.dumps(bundle,allow_nan=False).replace('<','\\u003c').replace('&','\\u0026')
    (output/'index.html').write_text(template.replace('__RESULT_DATA__',data))
