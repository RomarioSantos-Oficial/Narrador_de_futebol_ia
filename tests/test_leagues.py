from datetime import date
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from dotenv import dotenv_values
from backend.leagues import LEAGUES, LEAGUE_IDS
from backend import providers
class LeagueTests(unittest.IsolatedAsyncioTestCase):
    def test_sources_only_offer_their_mapped_competitions(self):
        with tempfile.TemporaryDirectory() as folder:
            app = FastAPI()
            providers.install_settings(app, Path(folder), LEAGUES)
            with TestClient(app) as client:
                sources = client.get('/api/sources').json()
        self.assertIn('bra.camp.paulista', sources['espn']['leagues'])
        self.assertIn('uefa.wchampions', sources['espn']['leagues'])
        self.assertIn('ger.1', sources['football_data']['leagues'])
        self.assertNotIn('bra.camp.paulista', sources['football_data']['leagues'])
        self.assertNotIn('conmebol.libertadores', sources['football_data']['leagues'])
        for provider, mapping in LEAGUE_IDS.items():
            self.assertEqual(set(sources[provider]['leagues']), set(mapping))
            self.assertEqual(len(set(mapping.values())), len(mapping))

    async def test_new_football_data_competition_uses_its_code_and_date(self):
        row = {'id': 55, 'homeTeam': {'name': 'Casa'}, 'awayTeam': {'name': 'Fora'},
               'utcDate': '2026-09-12T14:00Z', 'status': 'TIMED'}
        with patch('backend.providers.request', new=AsyncMock(return_value={'matches': [row]})) as request:
            result = await providers.games('football_data', 'ger.1', date(2026, 9, 12))
        request.assert_awaited_once_with('football_data', 'matches', competitions='BL1', dateFrom='2026-09-12', dateTo='2026-09-13')
        self.assertEqual(result[0]['id'], '55')
        self.assertEqual(result[0]['status'], 'PRÉ-JOGO')

    async def test_date_range_includes_full_day_at_year_boundary(self):
        with patch('backend.providers.request', new=AsyncMock(return_value={'matches': []})) as request:
            await providers.games('football_data', 'eng.1', date(2026, 12, 31))
        request.assert_awaited_once_with('football_data', 'matches', competitions='PL', dateFrom='2026-12-31', dateTo='2027-01-01')

    async def test_live_search_uses_live_filter_and_unmapped_league_is_not_queried(self):
        with patch('backend.providers.request', new=AsyncMock(return_value={'matches': []})) as request:
            await providers.games('football_data', 'ita.1', live=True)
            request.assert_awaited_once_with('football_data', 'matches', competitions='SA', status='LIVE')
            with self.assertRaises(HTTPException):
                await providers.games('football_data', 'bra.camp.paulista')
        self.assertEqual(request.await_count, 1)

    def test_pasted_key_whitespace_is_removed_and_secret_is_not_returned(self):
        value = 'abcdef0123456789abcdef0123456789'
        with tempfile.TemporaryDirectory() as folder, patch.dict('os.environ', {}, clear=True):
            app = FastAPI()
            providers.install_settings(app, Path(folder), LEAGUES)
            with TestClient(app) as client:
                response = client.post('/api/sources/key', json={'provider': 'football_data', 'key': value[:30] + ' ' + value[30:] + '\n'})
                self.assertEqual(response.status_code, 200)
                self.assertNotIn(value, response.text)
                listing = client.get('/api/sources')
                self.assertNotIn(value, listing.text)
                self.assertTrue(listing.json()['football_data']['configured'])
            self.assertEqual(dotenv_values(Path(folder) / '.env')['FOOTBALL_DATA_KEY'], value)
