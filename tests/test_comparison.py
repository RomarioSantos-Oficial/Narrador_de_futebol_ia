import copy
import unittest
from unittest.mock import AsyncMock, patch

from backend import comparison
from backend import providers
from backend.free_feed import Selection, FreeFeed


def sample(provider, rich=False):
    data = providers.blank(provider)
    data.update(home=providers.team('Casa', 0), away=providers.team('Fora', 0), phase='in',
                clock_display="45'+2'", kickoff='2026-09-14T14:00Z', updated_at='2026-09-14T14:47:00Z')
    if rich:
        data['stats']['shots'] = [4, 1]
        data['events'] = [{'text': 'Cartão amarelo · Jogador', 'minute': '44'}]
    return {'data': data, 'selection': {'provider': provider, 'league': 'eng.1', 'event': '1'},
            'sampled_at': data['updated_at'], 'primary': provider == 'espn'}


class RecommendationTests(unittest.IsolatedAsyncioTestCase):
    def report(self):
        return {'primary': 'espn', 'sources': {'espn': sample('espn'), 'api_football': sample('api_football', True),
                'football_data': {'error': 'Chave não configurada.'}, 'thesportsdb': sample('thesportsdb', True)}}

    def test_recommends_available_live_coverage_instead_of_unqueried_or_static_source(self):
        result = comparison.recommend(self.report())
        self.assertEqual(result['provider'], 'api_football')
        self.assertEqual(result['selection']['league'], 'eng.1')
        ranking = {item['provider']: item for item in result['ranking']}
        self.assertFalse(ranking['football_data']['eligible'])
        self.assertFalse(ranking['thesportsdb']['eligible'])
        self.assertEqual(comparison.match_minute(sample('espn')['data']), 47)

    def test_conflicting_score_phase_stale_query_and_clock_prevent_recommendation(self):
        for change in ('score', 'phase', 'clock', 'sample'):
            report = self.report()
            other = report['sources']['api_football']
            if change == 'score': other['data']['home']['score'] = 1
            if change == 'phase': other['data']['phase'] = 'pre'
            if change == 'clock': other['data']['clock_display'] = '30'
            if change == 'sample': other['sampled_at'] = '2026-09-14T14:40:00Z'
            result = comparison.recommend(report)
            self.assertEqual(result['provider'], 'espn', change)

    async def test_compare_returns_verified_fixture_and_skips_missing_keys(self):
        primary = sample('espn')['data']
        other = sample('thesportsdb')['data']
        with (patch.dict('os.environ', {}, clear=True), patch('backend.providers.games', new=AsyncMock(return_value=[
            {'id': '99', 'name': 'Casa × Fora', 'date': primary['kickoff']}])) as games,
            patch('backend.providers.match', new=AsyncMock(return_value=(other, False)))):
            result = await comparison.compare(Selection(league='eng.1', event='1'), primary, AsyncMock(), None)
        self.assertEqual(games.await_count, 1)
        self.assertEqual(result['sources']['thesportsdb']['selection']['event'], '99')
        self.assertIn('Chave', result['sources']['api_football']['error'])

    async def test_cached_comparison_refreshes_primary_without_spending_extra_queries(self):
        feed = FreeFeed({}, AsyncMock())
        selection = Selection(league='eng.1', event='1')
        report = self.report()
        with patch('backend.comparison.compare', new=AsyncMock(return_value=report)) as lookup:
            await feed.compare(selection, sample('espn')['data'])
            updated = copy.deepcopy(sample('espn')['data'])
            updated['home']['score'] = 1
            result = await feed.compare(selection, updated)
        self.assertEqual(lookup.await_count, 1)
        self.assertEqual(result['sources']['espn']['data']['home']['score'], 1)
        self.assertEqual(result['recommendation']['provider'], 'espn')

    def test_live_enrichment_skips_conflicting_or_old_statistics_but_can_fill_logo(self):
        primary = sample('espn')['data']
        entry = sample('api_football', True)
        entry['data']['home']['logo'] = 'https://example.com/logo.png'
        report = {'sources': {'api_football': entry}}
        current = comparison.enrich(primary, report)
        self.assertEqual(current['stats']['shots'], [4, 1])
        entry['data']['home']['score'] = 1
        conflicting = comparison.enrich(primary, report)
        self.assertEqual(conflicting['stats']['shots'], [None, None])
        self.assertEqual(conflicting['home']['logo'], 'https://example.com/logo.png')
        entry['data']['home']['score'] = 0
        entry['sampled_at'] = '2026-09-14T14:40:00Z'
        stale = comparison.enrich(primary, report)
        self.assertEqual(stale['stats']['shots'], [None, None])
