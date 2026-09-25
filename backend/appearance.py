"""Persistent overlay presentation, independent from live match updates."""
import hashlib
import json
from pathlib import Path
from typing import Literal

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field, field_validator


class Appearance(BaseModel):
    background: Literal["transparent", "solid", "gradient", "image"] = "transparent"
    background_color: str = Field(default="#101c2c", pattern=r"^#[0-9a-fA-F]{6}$")
    background_image: str = ""
    accent: str = Field(default="#ffffff", pattern=r"^#[0-9a-fA-F]{6}$")
    away_accent: str = Field(default="#72aaff", pattern=r"^#[0-9a-fA-F]{6}$")
    panel_opacity: float = Field(default=0.94, ge=0.3, le=1)
    image_dim: float = Field(default=0.35, ge=0, le=0.9)
    layout: Literal["center", "compact"] = "center"
    show_stats: bool = True
    show_events: bool = True
    show_pitch: bool = False
    show_lineups: bool = True
    show_context: bool = True
    show_logos: bool = True
    home_logo: str = ""
    away_logo: str = ""
    channel_name: str = Field(default="FUTEBOL LIVE", max_length=50)
    scene: Literal["match", "lineups", "bench", "table", "formation"] = "match"

    @field_validator("background_image", "home_logo", "away_logo")
    @classmethod
    def local_image(cls, value):
        if value and (not value.startswith("/static/uploads/") or ".." in value or "\\" in value):
            raise ValueError("Use uma imagem enviada pelo painel.")
        return value


class AppearanceStore:
    def __init__(self, base: Path):
        self.base = base
        self.path = base / "appearance.json"

    def load(self):
        try:
            return Appearance.model_validate_json(self.path.read_text(encoding="utf-8")).model_dump()
        except (OSError, ValueError):
            return Appearance().model_dump()

    def save(self, value):
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self.path)

    def install(self, app, state, broadcast):
        @app.post("/api/appearance")
        async def update(appearance: Appearance):
            value = appearance.model_dump()
            try:
                self.save(value)
            except OSError as exc:
                raise HTTPException(500, "Não foi possível salvar o visual nesta pasta.") from exc
            state["appearance"] = value
            await broadcast()
            return value

        @app.post("/api/appearance/upload")
        async def upload(request: Request):
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 5 * 1024 * 1024:
                    raise HTTPException(413, "A imagem deve ter no máximo 5 MB.")
            if body.startswith(b"\x89PNG\r\n\x1a\n"):
                ext = "png"
            elif body.startswith(b"\xff\xd8\xff"):
                ext = "jpg"
            elif body[:4] == b"RIFF" and body[8:12] == b"WEBP":
                ext = "webp"
            else:
                raise HTTPException(400, "Escolha uma imagem PNG, JPG ou WebP.")
            folder = self.base / "static" / "uploads"
            try:
                folder.mkdir(exist_ok=True)
                name = f"{hashlib.sha256(body).hexdigest()}.{ext}"
                (folder / name).write_bytes(body)
            except OSError as exc:
                raise HTTPException(500, "Não foi possível guardar a imagem nesta pasta.") from exc
            return {"url": f"/static/uploads/{name}"}
