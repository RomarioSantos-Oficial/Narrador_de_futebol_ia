import asyncio
import copy
import unittest
from unittest.mock import AsyncMock, patch

from backend.player_profiles import PlayerProfiles, select_profile, safe_photo


class ProfileTests(unittest.TestCase):
    def test_identity_ambiguity_and_photo_protocol(self):
        row = {'strSport': 'Soccer', 'strPlayer': 'Pedro', 'strNationality': 'Brazil',
               'strTeam': 'Flamengo', 'strThumb': 'https://images.example/pedro.png'}
        self.assertIsNotNone(select_profile([row], {'name': 'Pedro'}, 'Brasil'))
        self.assertIsNone(select_profile([{**row, 'strNationality': 'Spain'}], {'name': 'Pedro'}, 'Brazil'))
        self.assertIsNone(select_profile([row, row], {'name': 'Pedro'}, 'Brazil'))
        self.assertIsNone(select_profile([row], {'name': 'Pedro Junior'}, 'Brazil'))
        self.assertEqual(safe_photo('javascript:alert(1)'), '')
        self.assertEqual(safe_photo('https://user:pass@example.com/a.png'), '')

    def test_cache_and_changed_match(self):
        async def check():
            state = {'source': 'ESPN', 'home': {'name': 'Brazil'}, 'away': {'name': 'Australia'},
                     'kickoff': '2026-09-25', 'lineups': {'home': {'starters': [{'id': '9', 'name': 'Pedro'}]}}}
            service = PlayerProfiles(state, AsyncMock())
            response = {'player': [{'strSport': 'Soccer', 'strPlayer': 'Pedro', 'strNationality': 'Brazil'}]}
            with patch('backend.player_profiles.request', AsyncMock(return_value=response)) as fetch:
                await service.run(copy.deepcopy(state))
                await service.run(copy.deepcopy(state))
                self.assertEqual(fetch.await_count, 1)
                self.assertIn('ESPN|9|Pedro', state['player_profiles'])
            snapshot = copy.deepcopy(state)
            state['kickoff'] = '2026-09-26'
            await service.run(snapshot)
            self.assertEqual(state['player_profiles'], {})
        asyncio.run(check())
