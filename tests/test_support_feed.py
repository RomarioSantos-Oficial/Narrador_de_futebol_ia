import copy
import unittest
from unittest.mock import AsyncMock, patch
from backend.support_feed import apply_support, SupportFeed


def fixture():
    state = {'source': 'ESPN', 'phase': 'pre', 'kickoff': '2026-09-27T16:00Z',
             'home': {'name': 'Denmark', 'score': 0}, 'away': {'name': 'Wales', 'score': 0},
             'lineups': {}, 'events': [{'text': 'Primary event'}], 'clock_display': '0', 'coaches': {}}
    sheet = {'confirmed': True}
    for side in ('home', 'away'):
        sheet[side + '_formation'] = '4-3-3'
        sheet[side + '_xi'] = [{'name': side + str(i), 'number': i, 'position': 'G' if i == 1 else 'D'} for i in range(1, 12)]
        sheet[side + '_coach'] = {'name': side + ' Coach', 'photo': 'https://example.com/c.png'}
    payload = {'match': {'home': 'Denmark', 'away': 'Wales', 'time': state['kickoff'], 'status': 'upcoming', 'lineups': sheet}}
    return state, payload


class SupportTests(unittest.TestCase):
    def test_fills_absent_data_without_changing_primary_match(self):
        state, payload = fixture()
        before = copy.deepcopy(state)
        self.assertTrue(apply_support(state, payload))
        self.assertEqual(len(state['lineups']['home']['starters']), 11)
        self.assertEqual(state['coaches']['home']['name'], 'home Coach')
        for key in ('home', 'away', 'events', 'clock_display', 'source', 'phase'):
            self.assertEqual(state[key], before[key])
        self.assertEqual(state['support_sources'], ['SportScore'])

    def test_preserves_primary_and_ge_and_rejects_wrong_match(self):
        state, payload = fixture()
        state['coaches']['home'] = {'name': 'Primary coach'}
        state['ge'] = {'ready': True, 'coaches': {'away': {'name': 'GE coach'}}}
        state['lineups'] = {side: {'starters': [{'name': 'Primary'}] * 11, 'formation': '4-4-2'} for side in ('home', 'away')}
        before = copy.deepcopy(state)
        self.assertFalse(apply_support(state, payload))
        self.assertEqual(state['coaches'], before['coaches'])
        self.assertEqual(state['lineups'], before['lineups'])
        payload['match']['time'] = '2026-09-28T16:00Z'
        self.assertFalse(apply_support(state, payload))

    def test_no_unconfirmed_or_live_lineup_replacement(self):
        state, payload = fixture()
        payload['match']['lineups']['confirmed'] = False
        apply_support(state, payload)
        self.assertFalse(state['lineups']['home'].get('starters'))
        payload['match']['lineups']['confirmed'] = True
        state['phase'] = 'in'
        apply_support(state, payload)
        self.assertFalse(state['lineups']['home'].get('starters'))


class SupportLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_cached_lookup_not_restarted_on_every_broadcast_and_match_reset(self):
        state, payload = fixture()
        service = SupportFeed(state, AsyncMock())
        with patch.object(service, 'run', AsyncMock()) as run:
            service.observe()
            await service.task
            service.observe()
            self.assertEqual(run.await_count, 1)
            service.payload = payload
            service.observe()
            self.assertEqual(len(state['lineups']['home']['starters']), 11)
            state.update(kickoff='2026-09-28T16:00Z', lineups={}, coaches={})
            service.observe()
            await service.task
            self.assertEqual(run.await_count, 2)
            self.assertIsNone(service.payload)
            self.assertEqual(state['support_sources'], [])
