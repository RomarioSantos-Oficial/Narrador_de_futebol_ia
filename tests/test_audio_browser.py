"""Exercise independent browser contexts, shared settings and actual Web Audio."""
import asyncio
import copy
import io
import socket
import tempfile
import threading
import time
import unittest
import wave
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from backend.narration_channel import NarrationChannel
from tests.test_narration_browser import BROWSER_AVAILABLE, EDGE


@unittest.skipUnless(BROWSER_AVAILABLE, 'Requires Edge and Playwright')
class AudioChannelBrowserTests(unittest.TestCase):
    def test_obs_continues_without_control_and_second_page_cannot_duplicate(self):
        from playwright.sync_api import sync_playwright
        from main import state as initial
        base = Path(__file__).resolve().parents[1]
        state = copy.deepcopy(initial)
        state.update(competition='Teste', kickoff='2026-09-16T00:00:00Z', source='ESPN', phase='in',
                     ge={'ready': True, 'session': 'test', 'events': []})
        clients = set()
        calls = []
        app = FastAPI()
        app.mount('/static', StaticFiles(directory=base/'static'))

        async def broadcast():
            for ws in tuple(clients):
                try:
                    await ws.send_json(state)
                except Exception:
                    clients.discard(ws)

        temp = tempfile.TemporaryDirectory()
        channel = NarrationChannel(Path(temp.name), state, broadcast)
        channel.install(app)

        @app.get('/api/state')
        async def get_state():
            return state

        @app.get('/{page}')
        async def page(page: str):
            return FileResponse(base/'static'/('audio.html' if page == 'audio' else 'control.html'))

        @app.get('/api/voice/status')
        async def voices():
            return {'apiVersion': 3, 'voices': [{'name': name, 'voiceURI': ident, 'engine': 'kokoro', 'lang': 'pt-BR', 'apiVersion': 2}
                                               for ident, name in [('kokoro:pm_alex', 'Alex'), ('kokoro:pf_dora', 'Dora')]]}

        @app.get('/api/brain/status')
        async def brain():
            return {'installed': False, 'ready': False, 'message': 'Teste sem modelo.'}

        @app.get('/api/narration/context')
        async def context():
            return {'teams': [state['home']['name'], state['away']['name']], 'facts': []}

        @app.get('/api/sources')
        async def sources():
            return {}

        @app.get('/api/free/status')
        async def free_status():
            return {'active': False, 'selected': None, 'leagues': {}}

        @app.post('/api/voice/synthesize')
        async def voice(payload: dict):
            calls.append(payload['text'])
            data = io.BytesIO()
            with wave.open(data, 'wb') as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(24000)
                wav.writeframes(b'\0\0'*(9600 if 'escalação' in payload['text'].lower() else 2400))
            return Response(data.getvalue(), media_type='audio/wav')

        @app.post('/__test/event')
        async def event(payload: dict):
            state['ge']['events'].insert(0, payload)
            await broadcast()
            return {'ok': True}

        @app.post('/__test/finish')
        async def finish():
            state.update(phase='post', status='ENCERRADO')
            state['lineups']={side:{'starters':[{'name':side+' Player '+str(i), 'number':str(i), 'position':'CD-L'} for i in range(1,12)]} for side in ('home','away')}
            await broadcast()
            return {'ok': True}

        @app.websocket('/ws')
        async def websocket(ws: WebSocket):
            await ws.accept()
            clients.add(ws)
            await ws.send_json(state)
            try:
                while True:
                    await ws.receive_text()
            except WebSocketDisconnect:
                clients.discard(ws)

        sock = socket.socket()
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(app, log_level='error'))
        def serve():
            with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
                runner.run(server.serve(sockets=[sock]))
        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        for _ in range(100):
            if server.started:
                break
            time.sleep(.05)
        url = f'http://127.0.0.1:{port}'
        try:
            with httpx.Client(base_url=url) as api, sync_playwright() as p:
                api.post('/api/narration/settings', json={'output': 'obs', 'enabled': True, 'brain': False, 'curiosities': False})
                browser = p.chromium.launch(executable_path=str(EDGE), headless=True,
                                            args=['--autoplay-policy=no-user-gesture-required', '--mute-audio'])
                control, audio, duplicate = [browser.new_page() for _ in range(3)]
                errors = []
                for page in (control, audio, duplicate):
                    page.on('pageerror', lambda e: errors.append(str(e)))
                control.goto(url+'/control')
                audio.goto(url+'/audio')
                audio.wait_for_function('window.audioSession !== undefined || typeof audioSession !== "undefined"')
                audio.wait_for_function('audioSession.narrator.enabled && audioSession.started', timeout=15000)
                duplicate.goto(url+'/audio')
                duplicate.wait_for_timeout(2500)
                self.assertFalse(control.evaluate('matchNarrator.enabled'))
                self.assertFalse(duplicate.evaluate('audioSession.narrator.enabled'))
                control.close()
                baseline = len(calls)
                payload = {'id': 'ge:new', 'revision': 'one', 'text': 'Lance exclusivo depois de fechar o painel.',
                           'editorial': True, 'speak': True, 'minute': '25', 'kind': 'event'}
                api.post('/__test/event', json=payload)
                audio.wait_for_function('audioSession.narrator.lastText.includes("Lance exclusivo")', timeout=10000)
                audio.wait_for_timeout(1500)
                self.assertEqual(sum('Lance exclusivo' in x for x in calls), 1)
                self.assertGreater(len(calls), baseline)
                self.assertEqual(audio.evaluate('getComputedStyle(document.body).backgroundColor'), 'rgba(0, 0, 0, 0)')
                api.post('/api/narration/command', json={'action': 'skip_lineups'})
                api.post('/api/narration/settings', json={'style': 'events', 'announceLineups': False})
                api.post('/__test/finish')
                audio.wait_for_function('!audioSession.narrator.enabled', timeout=10000)
                api.post('/api/narration/command', json={'action': 'lineups'})
                audio.wait_for_function('audioSession.narrator.lastText.includes("away Player 11")', timeout=15000)
                audio.wait_for_function('!audioSession.narrator.enabled', timeout=10000)
                for side in ('home','away'):
                    self.assertEqual(sum(side+' Player 11' in text for text in calls), 1)
                audio.close()
                duplicate.wait_for_function('audioSession.narrator.enabled', timeout=12000)
                self.assertEqual(sum('Lance exclusivo' in x for x in calls), 1)
                self.assertEqual(errors, [])
                browser.close()
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            sock.close()
            temp.cleanup()


if __name__ == '__main__':
    unittest.main()
