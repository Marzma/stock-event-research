import csv
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from stock_event_research.core import database,returns,event_windows,match_news
from stock_event_research.providers import csv_prices,article,alpha_news
from stock_event_research.cli import run


def price(symbol,date,close,adjusted=None):
    return dict(symbol=symbol,date=date,close=close,adjusted_close=adjusted,volume=100,source='test')


class AnalysisTests(unittest.TestCase):
    def test_returns_do_not_bridge_missing_benchmark_date(self):
        prices=[price('A','2025-01-02',100),price('A','2025-01-03',110),price('A','2025-01-06',121),
                price('B','2025-01-02',100),price('B','2025-01-06',120)]
        con=database(':memory:',prices,[],[])
        rows=returns(con,'A','B','price');self.assertAlmostEqual(rows[2]['return_pct'],10)
        self.assertIsNone(rows[2]['benchmark_return_pct']);con.close()

    def test_window_uses_asset_sessions_and_same_baseline_for_benchmark(self):
        prices=[price(s,d,v) for s in ['A','B'] for d,v in [('2025-01-02',100),('2025-01-03',110),('2025-01-06',121)]]
        con=database(':memory:',prices,[],[]);event=dict(event_id='e',date='2025-01-03',title='test',source_url='https://example.com')
        rows=event_windows(con,'A','B',[event],[0,1,5],'price')
        self.assertAlmostEqual(rows[1]['return_pct'],21);self.assertEqual(rows[1]['end_date'],'2025-01-06')
        self.assertEqual(rows[1]['relative_return_pp'],0);self.assertIsNone(rows[2]['return_pct'])
        self.assertEqual(rows[2]['status'],'endpoint_missing');con.close()

    def test_announcement_without_prior_session_stays_unavailable(self):
        con=database(':memory:',[price('A','2025-01-02',100),price('A','2025-01-03',110)],[],[])
        event=dict(event_id='e',date='2025-01-02',title='test',source_url='https://example.com')
        self.assertEqual(event_windows(con,'A','B',[event],[0],'price')[0]['status'],'baseline_missing');con.close()

    def test_after_close_and_weekend_match_next_session(self):
        a=article(dict(published_at='2025-01-03T21:30:00Z',title='After close',url='https://example.com/news'),'A')
        moves=[dict(date='2025-01-03',previous_date='2025-01-02'),dict(date='2025-01-06',previous_date='2025-01-03')]
        rows=match_news(moves,[a],dict(timezone='America/New_York',close_time='16:00:00'),'test')
        self.assertEqual(rows[0]['candidate_count'],0);self.assertEqual(rows[1]['candidate_count'],1)

    def test_offsetless_news_rejected(self):
        with self.assertRaises(ValueError):article(dict(published_at='2025-01-03T12:00:00',title='x',url='https://example.com'),'A')

    def test_duplicate_dates_and_unknown_adjustment(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'prices.csv';p.write_text('Date,Price,Vol.\n01/02/2025,100,1.2M\n01/03/2025,105,2M\n')
            rows=csv_prices(p,'A','2025-01-04');self.assertIsNone(rows[0]['adjusted_close']);self.assertEqual(rows[0]['volume'],1200000)
            p.write_text(p.read_text()+'01/03/2025,105,2M\n')
            with self.assertRaises(ValueError):csv_prices(p,'A','2025-01-04')

    def test_adjusted_basis_handles_split(self):
        con=database(':memory:',[price('A','2025-01-02',100,50),price('A','2025-01-03',50,50)],[],[])
        self.assertEqual(returns(con,'A','A','price')[1]['return_pct'],-50)
        self.assertEqual(returns(con,'A','A','adjusted')[1]['return_pct'],0);con.close()

    def test_demo_is_repeatable_and_contains_no_live_prices(self):
        config=Path(__file__).parents[1]/'examples/demo.json'
        with tempfile.TemporaryDirectory() as directory:
            a=run(config,directory);b=run(config,directory)
            self.assertEqual(a['results'],b['results']);self.assertTrue(a['synthetic'])
            self.assertEqual(len(a['results']),2)
            self.assertTrue((Path(directory)/'index.html').exists())
            self.assertTrue((Path(directory)/'report.md').exists())

    def test_strict_threshold_and_current_day_exclusion(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory);(p/'a.csv').write_text('date,close\n2025-01-02,100\n2025-01-03,105\n2025-01-06,110.26\n2025-01-07,130\n')
            c=dict(tickers=['A'],benchmark='A',price_provider='csv',price_files={'A':'a.csv'},start='2025-01-02',end_exclusive='2025-01-07',threshold_pct=5)
            (p/'c.json').write_text(json.dumps(c));b=run(p/'c.json',p/'out')
            self.assertEqual([m['date'] for m in b['results'][0]['moves']],['2025-01-06'])

    def test_missing_news_key_is_explicit(self):
        with patch.dict('os.environ',{},clear=True):
            self.assertEqual(alpha_news('A','2025-01-01','2025-02-01','unused'),([], 'not_configured'))

    def test_adjusted_config_rejects_unadjusted_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory);(p/'a.csv').write_text('date,close\n2025-01-02,100\n2025-01-03,110\n')
            c=dict(tickers=['A'],benchmark='A',price_provider='csv',price_files={'A':'a.csv'},start='2025-01-02',end_exclusive='2025-01-04',return_basis='adjusted')
            (p/'c.json').write_text(json.dumps(c))
            with self.assertRaisesRegex(ValueError,'Adjusted basis requested'):run(p/'c.json',p/'out')

    def test_report_escapes_external_script_markup(self):
        from stock_event_research.report import render
        with tempfile.TemporaryDirectory() as directory:
            b=run(Path(__file__).parents[1]/'examples/demo.json',directory)
            b['results'][0]['moves'][0]['articles'].append(dict(article_id='evil',title='</script><script>alert(1)</script>',url='https://example.com',published_at='2025-01-03T12:00:00Z',publisher='test',evidence_status='unreviewed_candidate'))
            render(b,Path(directory));text=(Path(directory)/'index.html').read_text()
            self.assertNotIn('</script><script>alert(1)',text)


if __name__=='__main__':unittest.main()
