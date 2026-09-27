import asyncio
import copy
import unittest
from unittest.mock import AsyncMock, patch

from backend.ge_feed import matches, match_lineups, apply_pregame_lineups
from backend.player_profiles import PlayerProfiles, select_profile
from backend.free_feed import normalize
from tests.test_free_feed import fixture


class PregameTests(unittest.TestCase):
    def test_alternative_provider_supplies_complete_sheet_only_for_same_pregame_match(self):
        from backend.comparison import pregame_lineups
        primary = {'phase': 'pre', 'home': {'name': 'Italy'}, 'away': {'name': 'Belgium'},
                   'kickoff': '2026-09-25T18:45:00Z', 'lineups': {}}
        other = copy.deepcopy(primary)
        other['lineups'] = {'home': {'formation': '4-3-3',
            'starters': [{'id': str(i), 'name': str(i)} for i in range(11)], 'bench': [{'name': 'Reserve'}]}}
        report = {'sources': {'api_football': {'data': other}}}
        result = pregame_lineups(primary, report)
        self.assertEqual(len(result['lineups']['home']['starters']), 11)
        self.assertEqual(result['lineups']['home']['formation'], '4-3-3')
        self.assertEqual(result['lineups']['home']['bench'][0]['name'], 'Reserve')
        self.assertEqual(primary['lineups'], {})
        other['kickoff'] = '2026-09-26T18:45:00Z'
        self.assertEqual(pregame_lineups(primary, report)['lineups'], {})
        other['kickoff'] = primary['kickoff']
        other['phase'] = 'in'
        self.assertEqual(pregame_lineups(primary, report)['lineups'], {})

    def test_goias_atletico_go_lineup_is_applied_before_kickoff(self):
        primary = {'phase': 'pre', 'home': {'name': 'Goiás'},
                   'away': {'name': 'Atlético Goianiense'}, 'kickoff': '2026-09-26T21:30:00Z',
                   'lineups': {'home': {'starters': []}, 'away': {'starters': []}}}
        match = {'homeTeam': {'popularName': 'Goiás'}, 'awayTeam': {'popularName': 'Atlético-GO'},
                 'startDate': '2026-09-26', 'startHour': '18:30:00', 'squads': {}}
        for side in ('home', 'away'):
            match['squads'][side + 'Team'] = {'formation': '4-3-3', 'lineUp': [
                {'popularName': f'Player {i}', 'slug': f'{side}-{i}', 'shirtNumber': str(i),
                 'position': {'initials': 'GOL' if i == 1 else 'ATA'}} for i in range(1, 12)]}
        self.assertTrue(matches(primary, match))
        primary['ge'] = {'ready': True, 'lineups': match_lineups({'transmission': {'match': match}})}
        apply_pregame_lineups(primary)
        for side in ('home', 'away'):
            self.assertEqual(len(primary['lineups'][side]['starters']), 11)
            self.assertEqual(primary['lineups'][side]['formation'], '4-3-3')
        self.assertEqual(primary['phase'], 'pre')
        primary['lineups']['home'] = {'starters': [{'name': 'Partial primary'}], 'formation': '4-2-3-1'}
        apply_pregame_lineups(primary)
        self.assertEqual(len(primary['lineups']['home']['starters']), 11)
        self.assertEqual(primary['lineups']['home']['source'], 'GE')
        self.assertFalse(matches({**primary, 'away': {'name': 'Atlético Mineiro'}}, match))

    def test_translated_identity_keeps_date_and_orientation_checks(self):
        primary = {'home': {'name': 'Italy'}, 'away': {'name': 'Belgium'},
                   'kickoff': '2026-09-25T18:45:00Z'}
        match = {'homeTeam': {'popularName': 'Itália'}, 'awayTeam': {'popularName': 'Bélgica'},
                 'startDate': '2026-09-25', 'startHour': '15:45:00'}
        self.assertTrue(matches(primary, match))
        self.assertFalse(matches({**primary, 'kickoff': '2026-09-26T18:45:00Z'}, match))
        self.assertFalse(matches({**primary, 'home': primary['away'], 'away': primary['home']}, match))
        self.assertIsNotNone(select_profile([{'strSport': 'Soccer', 'strPlayer': 'Player',
            'strNationality': 'Italy'}], {'name': 'Player'}, 'Itália'))

    def test_ge_starters_available_before_kickoff_without_overwriting_primary(self):
        snapshot = {'transmission': {'match': {'squads': {'homeTeam': {'formation': '4-3-3',
            'lineUp': [{'popularName': 'Keeper', 'slug': 'keeper', 'shirtNumber': '1',
                        'position': {'initials': 'GOL'}, 'photo': 'https://example.com/p.png'}]}}}}}
        lineups = match_lineups(snapshot)
        state = {'phase': 'pre', 'ge': {'ready': True, 'lineups': lineups}, 'lineups': {}}
        apply_pregame_lineups(state)
        self.assertEqual(state['lineups']['home']['starters'][0]['position'], 'GK')
        self.assertTrue(state['lineups']['home']['starters'][0]['photo'])
        state['lineups']['home'] = {'starters': [{'name': 'Primary'}]}
        apply_pregame_lineups(state)
        self.assertEqual(state['lineups']['home']['starters'][0]['name'], 'Primary')
        state['phase'], state['lineups'] = 'in', {}
        apply_pregame_lineups(state)
        self.assertEqual(state['lineups'], {})

    def test_pre_game_formation_places_are_starters_not_whole_squad(self):
        data = fixture()
        data['header']['competitions'][0]['status']['type']['state'] = 'pre'
        data['header']['competitions'][0]['competitors'][1]['team']['displayName'] = 'Italy'
        data['rosters'] = [{'team': {'id': '1'}, 'roster': [
            {'formationPlace': 1, 'athlete': {'id': '1', 'displayName': 'Keeper'}},
            {'formationPlace': 0, 'athlete': {'id': '2', 'displayName': 'Bench'}}]}]
        state, _ = normalize(data, 'bra.1')
        self.assertEqual(state['home']['name'], 'Itália')
        self.assertEqual(len(state['lineups']['home']['starters']), 1)
        self.assertEqual(len(state['lineups']['home']['bench']), 1)


class AutomaticProfilesTests(unittest.IsolatedAsyncioTestCase):
    async def test_auto_waits_for_roster_deduplicates_and_cancels_old_match(self):
        state = {'source': 'ESPN', 'kickoff': 'one', 'home': {'name': 'Italy'}, 'away': {'name': 'Belgium'}}
        service = PlayerProfiles(state, AsyncMock())
        with patch.object(service, 'run', AsyncMock()) as run:
            service.observe()
            self.assertIsNone(service.task)
            state['lineups'] = {'home': {'starters': [{'id': '1', 'name': 'Player'}]}}
            service.observe()
            await service.task
            service.observe()
            self.assertEqual(run.await_count, 1)
            state['lineups']['home']['starters'].append({'id': '2', 'name': 'Second'})
            service.observe()
            await service.task
            self.assertEqual(run.await_count, 2)
        started = asyncio.Event()
        async def slow(snapshot):
            started.set()
            await asyncio.sleep(60)
        with patch.object(service, 'run', slow):
            state['kickoff'] = 'two'
            service.observe()
            old = service.task
            await started.wait()
            state['kickoff'], state['lineups'] = 'three', {}
            service.observe()
            with self.assertRaises(asyncio.CancelledError):
                await old
            self.assertEqual(state['player_profiles'], {})
