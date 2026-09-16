import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from backend import providers
from backend import comparison
class ProviderTests(unittest.IsolatedAsyncioTestCase):
    def test_api_football_team_mapping_and_named_card(self):
        row = {'fixture': {'date': '2026-09-12T14:00Z', 'status': {'short': '1H', 'elapsed': 25}},
               'league': {'name': 'Liga'}, 'teams': {'home': {'id': 1, 'name': 'Casa'}, 'away': {'id': 2, 'name': 'Fora'}},
               'goals': {'home': 1, 'away': 0},
               'statistics': [{'team': {'id': 2}, 'statistics': [{'type': 'Corner Kicks', 'value': 0}]}],
               'lineups': [{'team': {'id': 1}, 'startXI': [{'player': {'id': 10, 'name': 'Jogador'}}], 'substitutes': []}],
               'events': [{'time': {'elapsed': 20}, 'type': 'Card', 'detail': 'Red Card', 'player': {'id': 10, 'name': 'Jogador'}, 'team': {'id': 1, 'name': 'Casa'}}]}
        result, done = providers.normalize_api_football(row)
        self.assertEqual(result['stats']['corners'], [None, 0])
        self.assertEqual(result['lineups']['home']['starters'][0]['red'], 1)
        self.assertFalse(done)

    def test_football_data_free_response_missing_details(self):
        row = {'competition': {'name': 'Liga'}, 'status': 'IN_PLAY', 'utcDate': '2026-09-12T14:00Z',
               'homeTeam': {'name': 'Casa', 'crest': 'https://example.com/home.svg'}, 'awayTeam': {'name': 'Fora'},
               'score': {'fullTime': {'home': 2, 'away': 1}}}
        result, done = providers.normalize_football_data(row)
        self.assertEqual(result['home']['score'], 2)
        self.assertEqual(result['clock_display'], '—')
        self.assertEqual(result['stats']['corners'], [None, None])
        self.assertFalse(done)

    def test_keys_saved_but_never_returned(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict('os.environ', {}, clear=True):
            app = FastAPI()
            providers.install_settings(app, Path(folder), {'eng.1': 'Premier League'})
            with TestClient(app) as client:
                secret = 'test_key_123456'
                result = client.post('/api/sources/key', json={'provider': 'api_football', 'key': secret})
                self.assertEqual(result.status_code, 200)
                self.assertNotIn(secret, result.text)
                result = client.get('/api/sources')
                self.assertNotIn(secret, result.text)
                self.assertTrue(result.json()['api_football']['configured'])
                self.assertTrue((Path(folder) / '.env').exists())

    async def test_missing_key_and_free_sportsdb_live_error(self):
        with patch.dict('os.environ', {}, clear=True):
            with self.assertRaises(HTTPException) as error:
                await providers.request('football_data', 'matches')
            self.assertEqual(error.exception.status_code, 400)
        with self.assertRaises(HTTPException):
            await providers.games('thesportsdb', 'eng.1', live=True)

    def test_identity_requires_same_teams_sides_and_time(self):
        primary = {'home': {'name': 'Liverpool'}, 'away': {'name': 'Fulham'}, 'kickoff': '2026-09-12T14:00Z'}
        self.assertTrue(comparison.same_match(primary, 'Liverpool FC', 'Fulham FC', '2026-09-12T14:00Z'))
        self.assertFalse(comparison.same_match(primary, 'Fulham', 'Liverpool', '2026-09-12T14:00Z'))
        self.assertFalse(comparison.same_match(primary, 'Liverpool', 'Fulham', '2026-09-13T14:00Z'))

    def test_enrichment_preserves_zero_score_and_primary_data(self):
        primary = providers.blank('espn')
        primary.update(home=providers.team('Casa', 1), away=providers.team('Fora', 0))
        primary['stats']['corners'] = [0, None]
        other = copy.deepcopy(primary)
        other['stats']['corners'] = [5, 2]
        other['home']['score'] = 9
        result = comparison.enrich(primary, {'sources': {'api_football': {'data': other}}})
        self.assertEqual(result['stats']['corners'], [0, 2])
        self.assertEqual(result['home']['score'], 1)
        self.assertEqual(primary['stats']['corners'], [0, None])
        self.assertEqual(result['data_sources']['stats.corners.1'], 'API-Football')

    def test_league_table_complement_preserves_existing_primary_table(self):
        primary = providers.blank('football_data')
        primary.update(home=providers.team('Casa', 0), away=providers.team('Fora', 0))
        espn = providers.blank('espn')
        espn.update(home=providers.team('Casa', 0), away=providers.team('Fora', 0))
        espn['league_table'] = {'league': 'bra.1', 'groups': [{'entries': [{'wins': '16'}]}]}
        report = {'sources': {'espn': {'data': espn}}}
        result = comparison.enrich(primary, report)
        self.assertEqual(result['league_table'], espn['league_table'])
        self.assertEqual(result['data_sources']['league_table'], 'ESPN')
        self.assertIsNone(primary['league_table'])
        primary['league_table'] = {'league': 'bra.1', 'groups': [{'entries': [{'wins': '17'}]}]}
        self.assertEqual(comparison.enrich(primary, report)['league_table'], primary['league_table'])
