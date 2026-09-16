import unittest
from backend.match_context import extract_context, event_text


class ContextTests(unittest.TestCase):
    def test_recent_results_order_standings_and_location(self):
        teams = {'home': {'team': {'id': '1'}}, 'away': {'team': {'id': '2'}}}
        data = {'lastFiveGames': [{'team': {'id': '1'}, 'events': [
            {'gameDate': '2026-09-01', 'gameResult': 'L'}, {'gameDate': '2026-09-04', 'gameResult': 'W'},
            {'gameDate': '2026-09-02', 'gameResult': 'D'}, {'gameDate': '2026-09-09', 'gameResult': ''}]}],
            'standings': {'groups': [{'standings': {'entries': [{'id': '1', 'stats': [
                {'name': 'rank', 'displayValue': '6'}, {'name': 'points', 'displayValue': '5'}]}]}}]},
            'keyEvents': [{'fieldPositionX': 80, 'fieldPositionY': 30, 'team': {'displayName': 'Casa'}, 'clock': {'displayValue': "14'"}}]}
        result = extract_context(data, teams)
        self.assertEqual([g['result'] for g in result['recent_form']['home']], ['V', 'E', 'D'])
        self.assertEqual(result['standings']['home']['rank'], '6')
        self.assertIsNone(result['standings']['away'])
        self.assertEqual(result['field_action']['team'], 'Casa')
        self.assertEqual(result['field_action']['x'], 80)

    def test_no_location_is_not_guessed(self):
        self.assertIsNone(extract_context({}, {})['field_action'])

    def test_full_league_table_uses_season_totals_not_recent_form(self):
        teams = {'home': {'team': {'id': '3'}}, 'away': {'team': {'id': '18'}}}
        season = {'gamesPlayed': 26, 'wins': 16, 'ties': 6, 'losses': 4, 'points': 54,
                  'pointDifferential': '+30'}
        entries = [{'id': str(i), 'team': 'Clube '+str(i), 'logo': [{'href': '/club.png'}],
                    'stats': [{'name': name, 'displayValue': str(value)} for name, value in
                              {**season, 'rank': i}.items()]} for i in range(20, 0, -1)]
        data = {'standings': {'header': 'Brasileirão',
                             'fullViewLink': {'href': 'https://www.espn.com/soccer/standings/_/league/bra.1'},
                             'groups': [{'standings': {'entries': entries}}]},
                'lastFiveGames': [{'team': {'id': '3'}, 'events': [
                    {'gameResult': 'L', 'gameDate': '2026-09-01'}]}]}
        result = extract_context(data, teams, 'bra.1')
        rows = result['league_table']['groups'][0]['entries']
        self.assertEqual(len(rows), 20)
        self.assertEqual([int(r['rank']) for r in rows], list(range(1, 21)))
        self.assertEqual([(r['id'], r['side']) for r in rows if r['side']], [('3', 'home'), ('18', 'away')])
        self.assertEqual([rows[2][k] for k in ('played', 'wins', 'draws', 'losses', 'points', 'goal_difference')],
                         ['26', '16', '6', '4', '54', '+30'])
        self.assertEqual(result['standings']['home']['wins'], '16')
        self.assertEqual(result['recent_form']['home'][0]['result'], 'D')
        self.assertEqual(rows[0]['logo'], '/club.png')
        # A cup fixture must not inherit a league table supplied by the feed.
        cup = extract_context(data, teams, 'bra.copa_do_brazil')
        self.assertIsNone(cup['league_table'])
        self.assertEqual(cup['standings'], {'home': None, 'away': None})
        self.assertIsNone(extract_context({}, teams, 'bra.1')['league_table'])

    def test_bilingual_original_preserved(self):
        event = {'type': {'type': 'halftime'}, 'text': 'First Half ends, Home 1, Away 0.'}
        pt, en = event_text(event, event['text'])
        self.assertIn('intervalo', pt)
        self.assertEqual(en, event['text'])
