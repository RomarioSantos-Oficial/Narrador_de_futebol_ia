import asyncio
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
import httpx
from backend.local_brain import BrainRequest, BrainSettingsRequest, LocalBrain, assemble
from backend.narration_channel import NarrationSettings


class BrainTests(unittest.TestCase):
    def test_planner_cannot_change_zero_corners_or_names(self):
        payload = BrainRequest(text='Original.', kind='analysis', anchor='Liverpool, 1. Fulham, 0.',
                               choices=['Escanteios: Liverpool, 0. Fulham, 0.', 'Posse: 60 a 40.'])
        text = assemble(payload, {'opening': 'Vamos ao panorama.', 'facts': [0]})
        self.assertIn('Escanteios: Liverpool, 0. Fulham, 0.', text)
        self.assertIn(payload.anchor, text)
        for plan in [{'opening': 'Liverpool fez 8 gols!', 'facts': [0]}, {'opening': '', 'facts': [8]},
                     {'opening': '', 'facts': [True]}, {'opening': '', 'facts': [0, 0]},
                     {'opening': '', 'facts': []}]:
            with self.assertRaises(ValueError):
                assemble(payload, plan)

    def test_event_cannot_be_replaced_by_an_optional_fact(self):
        payload = BrainRequest(text='Cartão vermelho para João.', kind='card', choices=['Inventado.'])
        self.assertEqual(assemble(payload, {'opening': '', 'facts': [0]}), payload.text)

    def test_custom_notes_and_sponsor_reads_are_supported(self):
        settings = NarrationSettings(customComments=['Atenção ao camisa 10.'], sponsorReads=['Patrocínio do canal.'])
        self.assertEqual(settings.customComments, ['Atenção ao camisa 10.'])
        self.assertEqual(settings.sponsorReads, ['Patrocínio do canal.'])

    def test_saved_team_and_player_notes_are_reused_across_matches(self):
        settings = NarrationSettings(commentLibrary=[{
            'team': 'Chelsea',
            'player': 'Pedro Neto',
            'text': 'Pedro Neto tem conforto no lado direito.'
        }])
        self.assertEqual(settings.commentLibrary[0]['team'], 'Chelsea')
        self.assertEqual(settings.commentLibrary[0]['player'], 'Pedro Neto')
        self.assertIn('Pedro Neto', settings.commentLibrary[0]['text'])

    def test_unavailable_brain_preserves_baseline_and_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            brain = LocalBrain(Path(folder))
            app = FastAPI()
            brain.install(app)
            with TestClient(app) as client:
                self.assertFalse(client.get('/api/brain/status').json()['installed'])
                self.assertEqual(client.post('/api/brain/start').status_code, 400)
                fallback = client.post('/api/brain/compose', json={'text': 'Placar, 0 a 0.'}).json()
                self.assertEqual(fallback['text'], 'Placar, 0 a 0.')
                self.assertEqual(fallback['source'], 'facts')
                self.assertEqual(client.post('/api/brain/compose', json={'text': 'Teste', 'choices': ['x' * 601]}).status_code, 422)


class BrainAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_busy_timeout_and_invalid_model_response_fall_back(self):
        with tempfile.TemporaryDirectory() as folder:
            brain = LocalBrain(Path(folder))
            brain.ready = True
            brain.url = 'http://127.0.0.1:1'
            payload = BrainRequest(text='Placar, 0 a 0.')
            async with brain.compose_lock:
                self.assertEqual((await brain.compose(payload))['source'], 'facts')
            for side_effect in [httpx.ReadTimeout('test'), ValueError('bad json')]:
                with patch('httpx.AsyncClient.post', side_effect=side_effect):
                    result = await brain.compose(payload)
                self.assertEqual(result['text'], payload.text)
                self.assertFalse(brain.compose_lock.locked())

    async def test_stop_clears_api_ready_state(self):
        with tempfile.TemporaryDirectory() as folder:
            brain = LocalBrain(Path(folder))
            brain.ready = True
            await brain.stop()
            self.assertFalse(brain.ready)

    def test_api_configuration_is_persisted_without_exposing_key(self):
        with tempfile.TemporaryDirectory() as folder:
            brain = LocalBrain(Path(folder))
            payload = BrainSettingsRequest(connection='local', base_url='http://127.0.0.1:1234/v1', model='qwen-local')
            result = brain.save_settings(payload)
            self.assertTrue(result['configured'])
            self.assertFalse(result['has_api_key'])
            self.assertNotIn('api_key', result)
