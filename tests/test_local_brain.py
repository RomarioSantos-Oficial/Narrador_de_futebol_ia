import asyncio
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
import httpx
from backend.local_brain import BrainRequest, LocalBrain, assemble


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

    def test_unavailable_brain_preserves_baseline_and_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            brain = LocalBrain(Path(folder))
            app = FastAPI()
            brain.install(app)
            with TestClient(app) as client:
                self.assertFalse(client.get('/api/brain/status').json()['installed'])
                self.assertEqual(client.post('/api/brain/start').status_code, 503)
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

    async def test_shutdown_only_stops_owned_process(self):
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as folder:
            brain = LocalBrain(Path(folder))
            child = Mock()
            child.poll.return_value = None
            brain.process = child
            await brain.stop()
            child.terminate.assert_called_once()
            child.wait.assert_called_once_with(timeout=8)
            await brain.stop()
            self.assertEqual(child.terminate.call_count, 1)
