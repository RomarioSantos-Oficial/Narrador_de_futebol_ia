"""Persistent user-selected portraits, separate from automatic match data."""
import json
import re
from pathlib import Path

from fastapi import HTTPException
from pydantic import BaseModel, Field

from backend.player_profiles import player_key


class PhotoSelection(BaseModel):
    key: str = Field(min_length=1, max_length=500)
    url: str = Field(default='', max_length=200)


class PlayerPhotos:
    def __init__(self, base: Path, state, broadcast):
        self.base, self.state, self.broadcast = base, state, broadcast
        self.path = base / 'player_photos.json'
        try:
            saved = json.loads(self.path.read_text(encoding='utf-8'))
            self.photos = {key: url for key, url in saved.items() if isinstance(key, str) and self.valid_url(url)}
        except (OSError, ValueError, AttributeError):
            self.photos = {}
        state['player_photo_overrides'] = self.photos.copy()

    def valid_url(self, url):
        return (isinstance(url, str) and re.fullmatch(r'/static/uploads/[a-f0-9]{64}\.(png|jpg|webp)', url)
                and (self.base / url.lstrip('/')).is_file())

    def install(self, app):
        @app.post('/api/players/photo')
        async def select(payload: PhotoSelection):
            players = [p for lineup in self.state.get('lineups', {}).values()
                       for p in [*lineup.get('starters', []), *lineup.get('bench', [])]]
            if not any(player_key(self.state, p) == payload.key for p in players):
                raise HTTPException(409, 'A partida mudou ou o jogador não está mais na lista. Selecione novamente.')
            if payload.url and not self.valid_url(payload.url):
                raise HTTPException(400, 'Envie uma foto PNG, JPG ou WebP pelo painel primeiro.')
            updated = self.photos.copy()
            if payload.url:
                updated[payload.key] = payload.url
            else:
                updated.pop(payload.key, None)
            try:
                temp = self.path.with_suffix('.tmp')
                temp.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding='utf-8')
                temp.replace(self.path)
            except OSError as exc:
                raise HTTPException(500, 'Não foi possível salvar a foto deste jogador.') from exc
            self.photos = updated
            self.state['player_photo_overrides'] = updated.copy()
            await self.broadcast()
            return {'saved': True}
