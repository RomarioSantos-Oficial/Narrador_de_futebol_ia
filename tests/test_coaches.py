import unittest
from pathlib import Path
from playwright.sync_api import sync_playwright
from backend import providers
from backend.coaches import normalize_coach
from backend.comparison import complement_coaches
from backend.ge_feed import match_coaches


class CoachTests(unittest.TestCase):
    def test_provider_coaches_and_missing_values(self):
        row = {'fixture': {'status': {'short': 'NS'}}, 'league': {'name': 'League'},
               'teams': {'home': {'id': 1, 'name': 'Home'}, 'away': {'id': 2, 'name': 'Away'}},
               'lineups': [{'team': {'id': 1}, 'coach': {'name': 'Home coach', 'photo': 'https://example.com/coach.png'}}]}
        result, _ = providers.normalize_api_football(row)
        self.assertEqual(result['coaches']['home']['photo'], 'https://example.com/coach.png')
        self.assertNotIn('away', result['coaches'])
        result, _ = providers.normalize_football_data({'competition': {'name': 'League'}, 'status': 'SCHEDULED',
            'homeTeam': {'name': 'Home', 'coach': {'name': 'Home coach'}}, 'awayTeam': {'name': 'Away'}})
        self.assertEqual(result['coaches']['home']['name'], 'Home coach')
        self.assertNotIn('photo', result['coaches']['home'])
        self.assertEqual(providers.blank('espn')['coaches'], {})

    def test_ge_photo_and_safe_url(self):
        result = match_coaches({'transmission': {'match': {'squads': {'homeTeam': {'coach': {
            'popularName': 'Coach', 'photo': 'https://example.com/photo.png'}}}}}})
        self.assertTrue(result['home']['photo'])
        self.assertNotIn('photo', normalize_coach({'name': 'Coach', 'photo': 'javascript:alert(1)'}, 'GE'))
        self.assertIsNone(normalize_coach({}, 'GE'))

    def test_complement_requires_same_match(self):
        primary = {'home': {'name': 'Home'}, 'away': {'name': 'Away'}, 'kickoff': '2026-09-27T16:00Z'}
        other = {**primary, 'coaches': {'away': {'name': 'Coach', 'source': 'API-Football'}}}
        report = {'sources': {'api_football': {'data': other}}}
        self.assertEqual(complement_coaches(primary, report)['coaches']['away']['name'], 'Coach')
        other['kickoff'] = '2026-09-28T16:00Z'
        self.assertFalse(complement_coaches(primary, report).get('coaches'))

    def test_browser_renders_available_coaches_without_ge(self):
        with sync_playwright() as p:
            browser = p.chromium.launch(channel='msedge', headless=True)
            page = browser.new_page()
            for file in ('shared.js', 'formation.js'):
                page.add_script_tag(path=str(Path('static', file).resolve()))
            result = page.evaluate('''() => {
                const s={home:{name:'Home'},away:{name:'Away'},coaches:{
                    home:{name:'Coach <A>',photo:'https://example.com/a.png',source:'API-Football'},
                    away:{name:'Coach B',source:'Football-Data.org'}}};
                document.body.innerHTML=formationBenchHTML(s);
                return {names:[...document.querySelectorAll('.formation-coach strong')].map(e=>e.textContent),
                    photos:document.querySelectorAll('.formation-coach-photo').length,
                    absent:formationBenchHTML({...s,coaches:{}}).includes('Coach B')};
            }''')
            browser.close()
        self.assertEqual(result, {'names': ['Coach <A>', 'Coach B'], 'photos': 1, 'absent': False})
