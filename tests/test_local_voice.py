import io
import asyncio
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import wave

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from backend.local_voice import LocalVoice


class VoiceRouteTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.voice = LocalVoice(Path(self.folder.name))
        app = FastAPI()
        self.voice.install(app)
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.folder.cleanup()

    def test_absent_model_and_invalid_input_have_actionable_responses(self):
        self.assertFalse(self.client.get('/api/voice/status').json()['available'])
        result = self.client.post('/api/voice/synthesize', json={'text': 'Teste'})
        self.assertEqual(result.status_code, 503)
        self.assertIn('install_voice.bat', result.json()['detail'])
        for payload in ({'text': ' '}, {'text': 'x' * 901}, {'text': 'Olá', 'rate': 2}, {'text': 'Olá', 'model': '../file'}):
            self.assertEqual(self.client.post('/api/voice/synthesize', json=payload).status_code, 422)

    def test_wav_response_and_busy_request_do_not_accumulate_jobs(self):
        class Voice:
            def synthesize_wav(self, text, output, syn_config):
                output.setparams((1, 2, 22050, 0, 'NONE', 'not compressed'))
                output.writeframes(b'\x00\x00' * 2205)
        self.voice.voice = Voice()
        with patch.object(self.voice, 'status', return_value={'available': True}):
            self.voice.lock.acquire()
            self.voice.wait_timeout = .02
            busy = self.client.post('/api/voice/synthesize', json={'text': 'Teste'})
            self.assertEqual(busy.status_code, 429)
            self.assertEqual(busy.headers['retry-after'], '1')
            self.assertEqual(self.voice.waiters, [])
            self.voice.lock.release()
            self.voice.wait_timeout = 15
            with patch.dict('sys.modules', {'piper': type('Piper', (), {'PiperVoice': Voice, 'SynthesisConfig': lambda **kwargs: kwargs})}):
                result = self.client.post('/api/voice/synthesize', json={'text': 'Teste'})
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.headers['content-type'], 'audio/wav')
            self.assertEqual(result.headers['cache-control'], 'no-store')
            with wave.open(io.BytesIO(result.content)) as audio:
                self.assertEqual(audio.getnframes(), 2205)
            self.assertFalse(self.voice.lock.locked())

    def test_failed_inference_releases_lock(self):
        class BrokenVoice:
            def synthesize_wav(self, *args, **kwargs):
                raise RuntimeError('test failure')
        self.voice.voice = BrokenVoice()
        with patch.object(self.voice, 'status', return_value={'available': True}), patch('backend.local_voice.logging.getLogger'):
            with patch.dict('sys.modules', {'piper': type('Piper', (), {'PiperVoice': BrokenVoice, 'SynthesisConfig': lambda **kwargs: kwargs})}):
                result = self.client.post('/api/voice/synthesize', json={'text': 'Teste'})
        self.assertEqual(result.status_code, 503)
        self.assertFalse(self.voice.lock.locked())

    def test_unknown_voice_and_delivery_are_rejected(self):
        for extra in ({'voice': '../voice.onnx'}, {'voice': 'kokoro:unknown'}, {'delivery': 'shout'}, {'kind': 'unknown'}):
            self.assertEqual(self.client.post('/api/voice/synthesize', json={'text': 'Teste', **extra}).status_code, 422)
        unavailable = self.client.post('/api/voice/synthesize', json={'text': 'Teste', 'voice': 'kokoro:pm_alex'})
        self.assertEqual(unavailable.status_code, 503)

    def test_ge_event_kinds_are_accepted_by_voice_api(self):
        class Voice:
            def synthesize_wav(self, text, output, syn_config):
                output.setparams((1, 2, 22050, 0, 'NONE', 'not compressed'))
                output.writeframes(b'\x00\x00' * 2205)
        self.voice.voice = Voice()
        with patch.object(self.voice, 'status', return_value={'available': True}), patch.dict('sys.modules', {'piper': type('Piper', (), {'PiperVoice': Voice, 'SynthesisConfig': lambda **kwargs: kwargs})}):
            for kind in ('substitution', 'review', 'cancelled', 'correction'):
                result = self.client.post('/api/voice/synthesize', json={'text': 'Teste', 'voice': 'piper:pt_BR-faber-medium', 'kind': kind})
                self.assertEqual(result.status_code, 200, msg=f'kind={kind} should be accepted')

    @unittest.skipUnless(importlib.util.find_spec('numpy'), 'Requires optional voice dependencies')
    def test_kokoro_routes_selected_voice_with_portuguese_and_dynamic_pauses(self):
        from unittest.mock import Mock
        import numpy as np
        self.voice.kokoro = Mock()
        self.voice.kokoro.create.return_value = (np.zeros(2400), 24000)
        status = {'available': False, 'voices': [{'voiceURI': 'kokoro:pf_dora'}]}
        with patch.object(self.voice, 'status', return_value=status), patch.dict('sys.modules', {'kokoro_onnx': type('Module', (), {'Kokoro': Mock()})}):
            result = self.client.post('/api/voice/synthesize', json={'text': 'Teste', 'voice': 'kokoro:pf_dora', 'delivery': 'dynamic', 'kind': 'goal', 'rate': 1.08})
        self.assertEqual(result.status_code, 200)
        self.voice.kokoro.create.assert_called_once_with('Teste', voice='pf_dora', lang='pt-br', speed=1.08, sentence_pause=0.14, clause_pause=0.06)
        with wave.open(io.BytesIO(result.content)) as audio:
            self.assertEqual(audio.getframerate(), 24000)
        self.assertFalse(self.voice.lock.locked())


class VoiceWaitTests(unittest.IsolatedAsyncioTestCase):
    class Request:
        disconnected = False

        async def is_disconnected(self):
            return self.disconnected

    def setUp(self):
        self.voice = LocalVoice(Path('unused-test-path'))
        self.voice.wait_timeout = 1
        self.voice.lock.acquire()

    async def queued(self, count):
        async with asyncio.timeout(1):
            while len(self.voice.waiters) < count:
                await asyncio.sleep(.001)

    async def test_next_request_waits_for_active_synthesis_without_retry(self):
        pending = asyncio.create_task(self.voice.acquire_slot(self.Request(), 'goal'))
        await self.queued(1)
        self.assertFalse(pending.done())
        self.voice.lock.release()
        self.assertTrue(await pending)
        self.assertTrue(self.voice.lock.locked())
        self.assertEqual(self.voice.waiters, [])
        self.voice.lock.release()

    async def test_disconnected_waiter_does_not_generate_or_take_the_lock(self):
        request = self.Request()
        pending = asyncio.create_task(self.voice.acquire_slot(request, 'analysis'))
        await self.queued(1)
        request.disconnected = True
        self.assertFalse(await pending)
        self.assertTrue(self.voice.lock.locked())
        self.assertEqual(self.voice.waiters, [])
        self.voice.lock.release()

    async def test_goal_leads_waiting_analysis_and_queue_is_bounded(self):
        self.voice.max_waiters = 2
        analysis = asyncio.create_task(self.voice.acquire_slot(self.Request(), 'analysis'))
        goal = asyncio.create_task(self.voice.acquire_slot(self.Request(), 'goal'))
        await self.queued(2)
        with self.assertRaises(HTTPException) as error:
            await self.voice.acquire_slot(self.Request(), 'event')
        self.assertEqual(error.exception.status_code, 429)
        self.voice.lock.release()
        self.assertTrue(await goal)
        self.assertFalse(analysis.done())
        self.voice.lock.release()
        self.assertTrue(await analysis)
        self.voice.lock.release()
        self.assertEqual(self.voice.waiters, [])

    async def test_canceled_waiter_releases_queue_capacity(self):
        pending = asyncio.create_task(self.voice.acquire_slot(self.Request(), 'analysis'))
        await self.queued(1)
        pending.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await pending
        self.assertEqual(self.voice.waiters, [])
        self.voice.lock.release()

