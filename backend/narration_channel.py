"""Shared narration preferences and an exclusive playback lease for OBS/control."""
import json
import time
from typing import Literal
from uuid import uuid4

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator


class NarrationSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    paused: bool = False
    output: Literal["control", "obs"] = "control"
    voice: str = Field(default="kokoro:pm_alex", max_length=200)
    commentaryVoice: str = Field(default="kokoro:pf_dora", max_length=200)
    rate: float = Field(default=1, ge=.7, le=1.4)
    volume: float = Field(default=1, ge=0, le=1)
    commentaryRate: float | None = Field(default=None, ge=.7, le=1.4)
    commentaryVolume: float | None = Field(default=None, ge=0, le=1)
    pronunciations: dict[str, str] = Field(default_factory=dict, max_length=100)
    stageScripts: bool = True
    eventGraphics: bool = True
    style: Literal["events", "radio"] = "radio"
    commentaryInterval: Literal[0, 30, 60, 90, 120] = 0
    delivery: Literal["natural", "dynamic"] = "dynamic"
    brain: bool = True
    curiosities: bool = True
    announceLineups: bool = False
    engagement: bool = True
    engagementInterval: Literal[300, 600, 900] = 600
    customComments: list[str] = Field(default_factory=list)
    sponsorReads: list[str] = Field(default_factory=list)
    playerFocus: str = Field(default="", max_length=80)
    commentLibrary: list[dict[str, str]] = Field(default_factory=list)

    @field_validator('pronunciations')
    @classmethod
    def validate_pronunciations(cls, value):
        clean = {}
        for name, spoken in value.items():
            name, spoken = name.strip(), spoken.strip()
            if not name or not spoken or max(len(name), len(spoken)) > 100 or any(c in name + spoken for c in '\n\r\t'):
                raise ValueError('Use nomes e pronúncias de 1 a 100 caracteres, em uma linha.')
            if name.casefold() in {key.casefold() for key in clean}:
                raise ValueError('Nome repetido no dicionário.')
            clean[name] = spoken
        return clean

    @field_validator('customComments', 'sponsorReads')
    @classmethod
    def validate_comment_lists(cls, value, info):
        cleaned = []
        seen = set()
        for item in value or []:
            text = str(item).strip()
            if not text or len(text) > 300 or any(ch in text for ch in '\n\r\t'):
                continue
            key = text.casefold()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(text)
        if info.field_name == 'customComments' and len(cleaned) > 12:
            cleaned = cleaned[:12]
        if info.field_name == 'sponsorReads' and len(cleaned) > 8:
            cleaned = cleaned[:8]
        return cleaned

    @field_validator('playerFocus')
    @classmethod
    def validate_player_focus(cls, value):
        return str(value).strip()[:80]

    @field_validator('commentLibrary')
    @classmethod
    def validate_comment_library(cls, value):
        cleaned = []
        seen = set()
        for item in value or []:
            if not isinstance(item, dict):
                continue
            team = str(item.get('team', '')).strip()[:80]
            player = str(item.get('player', '')).strip()[:80]
            text = str(item.get('text', '')).strip()
            if not text or len(text) > 350 or any(ch in text for ch in '\n\r\t'):
                continue
            key = (team.casefold(), player.casefold(), text.casefold())
            if key in seen:
                continue
            seen.add(key)
            cleaned.append({'team': team, 'player': player, 'text': text})
        return cleaned[:50]


class QueueItem(BaseModel):
    text: str = Field(max_length=900)
    kind: str = Field(max_length=30)
    role: str = Field(max_length=30)
    label: str = Field(default='', max_length=80)


class LeaseRequest(BaseModel):
    client: str = Field(min_length=16, max_length=80, pattern=r"^[a-zA-Z0-9-]+$")
    output: Literal["control", "obs"]
    status: str = Field(default="", max_length=250)
    text: str = Field(default="", max_length=1800)
    queue: list[QueueItem] = Field(default_factory=list, max_length=40)
    current: QueueItem | None = None
    can_repeat: bool = False


class ChannelCommand(BaseModel):
    action: Literal["lineups", "skip_lineups", "panorama", "skip", "repeat", "stage"]


class NarrationChannel:
    TTL = 6

    def __init__(self, base, state, broadcast):
        self.path = base / "narration.json"
        self.state, self.broadcast = state, broadcast
        try:
            self.settings = NarrationSettings.model_validate_json(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.settings = NarrationSettings()
        self.owner = None
        self.expiry = 0
        self.state["narration"] = self.settings.model_dump()
        self.state["narration_playback"] = {"connected": False, "status": "Saída de áudio aguardando conexão."}

    def acquire(self, payload):
        now = time.monotonic()
        eligible = payload.output == self.settings.output
        granted = eligible and (self.owner == payload.client or self.expiry <= now)
        if granted:
            self.owner, self.expiry = payload.client, now + self.TTL
            self.state["narration_playback"] = {"connected": True, "output": payload.output,
                "status": payload.status, "text": payload.text,
                "queue": [item.model_dump() for item in payload.queue],
                "current": payload.current.model_dump() if payload.current else None,
                "can_repeat": payload.can_repeat}
        return {"granted": granted, "ttl": self.TTL, "settings": self.settings.model_dump()}

    def refresh(self):
        if self.expiry <= time.monotonic():
            self.state["narration_playback"]["connected"] = False

    def install(self, app):
        @app.get("/api/narration/settings")
        async def settings():
            self.refresh()
            return self.settings.model_dump()

        @app.post("/api/narration/settings")
        async def update(payload: dict):
            try:
                candidate = NarrationSettings.model_validate({**self.settings.model_dump(), **payload})
            except ValueError as exc:
                raise HTTPException(422, "Configuração de narração inválida.") from exc
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(candidate.model_dump_json(indent=2), encoding="utf-8")
            temporary.replace(self.path)
            self.settings = candidate
            self.state["narration"] = candidate.model_dump()
            await self.broadcast()
            return candidate.model_dump()

        @app.post("/api/narration/lease")
        async def lease(payload: LeaseRequest):
            result = self.acquire(payload)
            if result["granted"]:
                await self.broadcast()
            return result

        @app.post("/api/narration/release")
        async def release(payload: LeaseRequest):
            if payload.client == self.owner:
                self.owner, self.expiry = None, 0
                self.state["narration_playback"]["connected"] = False
                await self.broadcast()
            return {"ok": True}

        @app.post("/api/narration/command")
        async def command(payload: ChannelCommand):
            self.state["narration_command"] = {"id": str(uuid4()), "action": payload.action}
            await self.broadcast()
            return {"ok": True}
