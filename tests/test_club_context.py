import unittest
from unittest.mock import AsyncMock, patch
from backend.club_context import ClubContext, identify, facts_for, player_facts, stadium_facts

TEAM = {'idTeam': '133602', 'strTeam': 'Liverpool', 'strTeamAlternate': 'Liverpool FC, LFC',
        'strSport': 'Soccer', 'intFormedYear': '1892', 'strStadium': 'Anfield', 'strKeywords': 'The Reds'}


class ClubContextTests(unittest.TestCase):
    def test_similar_ambiguous_and_other_sports_are_not_matched(self):
        self.assertEqual(identify([TEAM], 'Liverpool FC'), TEAM)
        for rows in [[TEAM, {**TEAM, 'idTeam': '2'}], [{**TEAM, 'strSport': 'Basketball'}],
                     [{**TEAM, 'strTeam': 'Liverpool Women', 'strTeamAlternate': ''}]]:
            self.assertIsNone(identify(rows, 'Liverpool'))

    def test_facts_are_attributed_and_missing_fields_are_omitted(self):
        facts = facts_for(TEAM, 'Liverpool')
        self.assertEqual(len(facts), 3)
        self.assertIn('1892', facts[0]['text'])
        self.assertTrue(all(f['source']['url'] == 'https://www.thesportsdb.com/team/133602' for f in facts))
        self.assertEqual(facts_for({'idTeam': '1', 'intFormedYear': '9999'}, 'Clube'), [])

    def test_profiles_match_players_in_lineup_without_inventing_details(self):
        row = {'idPlayer': '10', 'idTeam': '133602', 'idESPN': '123', 'strPlayer': 'Nome completo',
               'strSport': 'Soccer', 'dateBorn': '1999-01-02', 'strNationality': 'Brazil'}
        lineup = {'starters': [{'id': '123', 'name': 'N. Completo'}], 'bench': []}
        result = player_facts([row], lineup, 'home', 'ESPN (teste gratuito)', '133602')
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['player_id'], '123')
        self.assertIn('1999', result[0]['text'])
        self.assertIn('Brasil', result[0]['text'])
        self.assertEqual(player_facts([row], lineup, 'home', 'Other source', '133602'), [])
        self.assertEqual(player_facts([row, row], lineup, 'home', 'ESPN', '133602'), [])
        self.assertEqual(stadium_facts({'idVenue': '1', 'strVenue': 'Teste', 'intFormedYear': ''}), [])

    def test_player_profiles_use_broadcast_style_without_truncating_voice_text(self):
        player_name = 'Dani Olmo ' * 30
        row = {'idPlayer': '11', 'idTeam': '133602', 'idESPN': '20', 'strPlayer': player_name,
               'strSport': 'Soccer', 'dateBorn': '1998-05-07', 'strNationality': 'Spain'}
        lineup = {'starters': [{'id': '20', 'name': player_name, 'number': '20'}], 'bench': []}
        result = player_facts([row], lineup, 'home', 'ESPN (teste gratuito)', '133602')
        self.assertEqual(len(result), 1)
        self.assertIn('Olho no lance com', result[0]['text'])
        self.assertIn('7 de maio de 1998', result[0]['text'])
        self.assertIn('Espanha', result[0]['text'])
        self.assertGreater(len(result[0]['text']), 350)


class ClubCacheTests(unittest.IsolatedAsyncioTestCase):
    async def test_same_club_reuses_cache_and_failures_remain_optional(self):
        from fastapi import HTTPException
        context = ClubContext()
        with patch('backend.providers.request', new_callable=AsyncMock, return_value={'teams': [TEAM]}) as request:
            first = await context.team('Liverpool')
            self.assertEqual(first, await context.team('Liverpool'))
            request.assert_awaited_once()
        with patch('backend.providers.request', side_effect=HTTPException(429, 'quota')) as request:
            self.assertEqual(await context.team('Outro'), [])
            self.assertEqual(await context.team('Outro'), [])
            request.assert_awaited_once()
