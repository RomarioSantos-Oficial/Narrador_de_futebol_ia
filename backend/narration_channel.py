"""Shared narration preferences and an exclusive playback lease for OBS/control."""
import json
import time
from typing import Literal
from uuid import uuid4

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field


class NarrationSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    paused: bool = False
    output: Literal["control", "obs"] = "control"
    voice: str = Field(default="kokoro:pm_alex", max_length=200)
    commentaryVoice: str = Field(default="kokoro:pf_dora", max_length=200)
    rate: float = Field(default=1, ge=.7, le=1.4)
    volume: float = Field(default=1, ge=0, le=1)
    style: Literal["events", "radio"] = "radio"
    commentaryInterval: Literal[0, 30, 60, 90, 120] = 0
    delivery: Literal["natural", "dynamic"] = "dynamic"
    brain: bool = True
    curiosities: bool = True
    announceLineups: bool = False
    engagement: bool = True
    engagementInterval: Literal[300, 600, 900] = 600


class LeaseRequest(BaseModel):
    client: str = Field(min_length=16, max_length=80, pattern=r"^[a-zA-Z0-9-]+$")
    output: Literal["control", "obs"]
    status: str = Field(default="", max_length=250)
    text: str = Field(default="", max_length=1800)


class ChannelCommand(BaseModel):
    action: Literal["lineups", "skip_lineups", "panorama"]


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
                                                 "status": payload.status, "text": payload.text}
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
