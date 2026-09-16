import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.appearance import Appearance, AppearanceStore


class AppearanceTests(unittest.TestCase):
    def test_persists_visual_without_modifying_live_data(self):
        with tempfile.TemporaryDirectory() as directory:
            store = AppearanceStore(Path(directory))
            state = {"source": "ESPN", "home": {"score": 2}, "appearance": store.load()}
            app = FastAPI()
            broadcast = AsyncMock()
            store.install(app, state, broadcast)
            with TestClient(app) as client:
                response = client.post('/api/appearance', json={**state['appearance'], 'background': 'gradient', 'scene': 'bench'})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(client.post('/api/appearance', json={'accent': 'invalid'}).status_code, 422)
            self.assertEqual(AppearanceStore(Path(directory)).load()['scene'], 'bench')
            self.assertEqual(state['home']['score'], 2)
            self.assertEqual(state['source'], 'ESPN')
            broadcast.assert_awaited_once()

    def test_upload_rejects_html_and_oversized_files(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / 'static').mkdir()
            app = FastAPI()
            AppearanceStore(base).install(app, {}, AsyncMock())
            with TestClient(app) as client:
                self.assertEqual(client.post('/api/appearance/upload', content=b'<html>not an image</html>').status_code, 400)
                self.assertEqual(client.post('/api/appearance/upload', content=b'x' * (5*1024*1024+1)).status_code, 413)

    def test_table_scene_accepted_and_invalid_visual_preserves_saved_state(self):
        with tempfile.TemporaryDirectory() as directory:
            store = AppearanceStore(Path(directory))
            visual = Appearance(background='solid', accent='#1e4334', scene='lineups').model_dump()
            state = {'appearance': visual.copy(), 'source': 'ESPN', 'home': {'score': 2}}
            app = FastAPI()
            broadcast = AsyncMock()
            store.install(app, state, broadcast)
            with TestClient(app) as client:
                scenes = client.get('/openapi.json').json()['components']['schemas']['Appearance']['properties']['scene']['enum']
                self.assertIn('table', scenes)
                response = client.post('/api/appearance', json={**visual, 'scene': 'table'})
                self.assertEqual(response.status_code, 200)
                expected = {**visual, 'scene': 'table'}
                self.assertEqual(response.json(), expected)
                response = client.post('/api/appearance', json={**expected, 'accent': 'invalid'})
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json()['detail'][0]['loc'], ['body', 'accent'])
            self.assertEqual(state['appearance'], expected)
            self.assertEqual(store.load(), expected)
            self.assertEqual(state['home']['score'], 2)
            self.assertEqual(state['source'], 'ESPN')
            broadcast.assert_awaited_once()

    def test_missing_or_invalid_saved_config_uses_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            store = AppearanceStore(Path(directory))
            store.path.write_text('invalid json')
            self.assertEqual(store.load(), Appearance().model_dump())
