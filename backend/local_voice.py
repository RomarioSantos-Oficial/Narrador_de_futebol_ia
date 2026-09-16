"""Optional, offline neural speech. Keep one CPU model loaded and bound each request."""
import asyncio
import importlib.util
import io
import logging
from pathlib import Path
import threading
import sys
from typing import Literal
import wave

from fastapi import HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field


class SpeechRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    text: str = Field(min_length=1, max_length=900)
    rate: float = Field(default=1, ge=0.7, le=1.4, allow_inf_nan=False)
    voice: Literal['piper:pt_BR-faber-medium', 'kokoro:pm_alex', 'kokoro:pm_santa', 'kokoro:pf_dora'] = 'piper:pt_BR-faber-medium'
    delivery: Literal['natural', 'dynamic'] = 'natural'
    kind: Literal['event', 'analysis', 'goal', 'card'] = 'event'


class LocalVoice:
    def __init__(self, base: Path):
        self.base = base.resolve()
        self.model = base / 'models' / 'piper' / 'pt_BR-faber-medium.onnx'
        self.voice = None
        self.kokoro = None
        self.kokoro_model = base / 'models' / 'kokoro' / 'kokoro-v1.0.onnx'
        self.kokoro_voices = base / 'models' / 'kokoro' / 'voices-v1.0.bin'
        self.lock = threading.Lock()
        self.waiters = []
        self.wait_timeout = 15
        self.max_waiters = 4

    def status(self):
        package = importlib.util.find_spec('piper') is not None
        model = self.model.is_file() and self.model.with_suffix('.onnx.json').is_file()
        piper = {'available': package and model, 'engine': 'piper', 'lang': 'pt-BR',
                'name': 'Piper Faber · IA local gratuita', 'voiceURI': 'piper:pt_BR-faber-medium',
                'message': 'Voz de IA instalada. Síntese local, sem chave ou cobrança por fala.' if package and model
                else 'Execute install_voice.bat na pasta do programa para instalar a voz de IA gratuita.'}
        voices = []
        if importlib.util.find_spec('kokoro_onnx') is not None and self.kokoro_model.is_file() and self.kokoro_voices.is_file():
            for ident, label in [('pm_alex', 'Alex · masculino'), ('pm_santa', 'Santa · masculino'), ('pf_dora', 'Dora · feminino')]:
                voices.append({'engine': 'kokoro', 'lang': 'pt-BR', 'name': 'Kokoro ' + label,
                               'voiceURI': 'kokoro:' + ident, 'apiVersion': 2})
        if voices:
            piper['message'] = 'Vozes Kokoro em português instaladas. Compare Alex, Santa e Dora em Testar voz. Funcionam localmente, sem cobrança por fala.'
        if package and model:
            voices.append({key: piper[key] for key in ('engine', 'lang', 'name', 'voiceURI')} | {'apiVersion': 2})
        if not voices and (self.base / '.venv' / 'Scripts' / 'python.exe').is_file() and Path(sys.prefix).resolve() != self.base / '.venv':
            piper['message'] = 'Este servidor foi aberto com outro Python. Feche a janela antiga do servidor com Ctrl+C, abra start.bat uma vez e atualize o painel com Ctrl+F5.'
        return {**piper, 'apiVersion': 3, 'voices': voices, 'busy': self.lock.locked()}

    async def acquire_slot(self, request, kind):
        """Wait inside one request, bounded and cancel-aware; goals lead waiting analyses."""
        if len(self.waiters) >= self.max_waiters:
            raise HTTPException(429, 'Há pedidos de voz demais. Aguarde e mantenha apenas um painel narrando.',
                                headers={'Retry-After': '1'})
        priority = {'goal': 0, 'card': 1, 'event': 2, 'analysis': 3}[kind]
        ticket = {'priority': priority}
        self.waiters.append(ticket)
        self.waiters.sort(key=lambda item: item['priority'])
        deadline = asyncio.get_running_loop().time() + self.wait_timeout
        try:
            while True:
                if await request.is_disconnected():
                    return False
                if asyncio.get_running_loop().time() >= deadline:
                    raise HTTPException(429, 'A geração anterior ainda está terminando. Aguarde um instante.',
                                        headers={'Retry-After': '1'})
                if self.waiters[0] is ticket and self.lock.acquire(blocking=False):
                    return True
                await asyncio.sleep(.05)
        finally:
            self.waiters = [item for item in self.waiters if item is not ticket]

    @staticmethod
    def finish_worker(worker):
        # A disconnected caller must not cancel a running model or leak an unobserved task exception.
        if not worker.cancelled():
            worker.exception()

    def synthesize_kokoro(self, payload):
        import numpy as np
        from kokoro_onnx import Kokoro
        if self.kokoro is None:
            self.kokoro = Kokoro(str(self.kokoro_model), str(self.kokoro_voices))
        sentence_pause, clause_pause = 0.25, 0.1
        if payload.delivery == 'dynamic':
            sentence_pause, clause_pause = {'goal': (0.14, 0.06), 'card': (0.2, 0.08),
                                            'analysis': (0.32, 0.12)}.get(payload.kind, (0.25, 0.1))
        samples, sample_rate = self.kokoro.create(payload.text, voice=payload.voice.split(':')[1],
                                                 lang='pt-br', speed=payload.rate,
                                                 sentence_pause=sentence_pause, clause_pause=clause_pause)
        if not samples.size or not np.isfinite(samples).all():
            raise ValueError('A voz retornou áudio vazio ou inválido.')
        pcm = (np.clip(samples, -1, 1) * 32767).astype('<i2')
        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as output:
            output.setparams((1, 2, sample_rate, 0, 'NONE', 'not compressed'))
            output.writeframes(pcm.tobytes())
        return buffer.getvalue()

    def synthesize(self, payload: SpeechRequest):
        # The worker owns the lock until inference ends, even if the HTTP client disconnects.
        try:
            if payload.voice.startswith('kokoro:'):
                return self.synthesize_kokoro(payload)
            from piper import PiperVoice, SynthesisConfig
            if self.voice is None:
                self.voice = PiperVoice.load(str(self.model), use_cuda=False)
            buffer = io.BytesIO()
            with wave.open(buffer, 'wb') as output:
                self.voice.synthesize_wav(payload.text, output,
                                          syn_config=SynthesisConfig(length_scale=1 / payload.rate))
            return buffer.getvalue()
        finally:
            self.lock.release()

    def install(self, app):
        @app.get('/api/voice/status')
        async def voice_status():
            return self.status()

        @app.post('/api/voice/synthesize')
        async def voice_synthesize(payload: SpeechRequest, request: Request):
            status = self.status()
            available = status['available'] if payload.voice.startswith('piper:') else any(v['voiceURI'] == payload.voice for v in status.get('voices', []))
            if not available:
                raise HTTPException(503, 'Execute install_voice.bat e reinicie o programa para habilitar esta voz.')
            if not await self.acquire_slot(request, payload.kind):
                return Response(status_code=204)
            worker = asyncio.create_task(asyncio.to_thread(self.synthesize, payload))
            worker.add_done_callback(self.finish_worker)
            try:
                audio = await asyncio.shield(worker)
            except Exception as exc:
                logging.getLogger(__name__).exception('Falha na síntese de voz local')
                raise HTTPException(503, 'Não foi possível gerar a voz local. Execute install_voice.bat e reinicie o programa.') from exc
            return Response(audio, media_type='audio/wav', headers={'Cache-Control': 'no-store'})
