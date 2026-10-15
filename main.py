if __name__ == '__main__':
    from launcher import main as launch
    raise SystemExit(launch())

import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn
from backend.free_feed import FreeFeed, LEAGUES
from backend.providers import install_settings
from backend.appearance import AppearanceStore
from backend.local_voice import LocalVoice
from backend.local_brain import LocalBrain
from backend.club_context import ClubContext
from backend.ge_feed import GEFeed
from backend.narration_channel import NarrationChannel
from backend.rehearsal import Rehearsal
from backend.player_profiles import PlayerProfiles
from backend.player_photos import PlayerPhotos
from backend.youtube_live import YouTubeLiveChat
from backend.news_context import NewsContext

load_dotenv()
BASE = Path(__file__).parent
appearance_store = AppearanceStore(BASE)

app = FastAPI(title="Futebol Live Overlay")

class RevalidatedStaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers['Cache-Control'] = 'no-cache'
        return response


app.mount("/static", RevalidatedStaticFiles(directory=BASE / "static"), name="static")

state: dict[str, Any] = {
    "competition": "TRANSMISSÃO AO VIVO",
    "home": {"name": "Mandante", "score": 0, "logo": "", "abbreviation": "MAN"},
    "away": {"name": "Visitante", "score": 0, "logo": "", "abbreviation": "VIS"},
    "appearance": appearance_store.load(),
    "venue": "",
    "lineups": {},
    "cards": [],
    "recent_form": {"home": [], "away": []},
    "standings": {"home": None, "away": None},
    "field_action": None,
    "league_table": None,
    "phase": "pre",
    "minute": 0,
    "status": "PRÉ-JOGO",
    "stats": {
        "possession": [50, 50],
        "shots": [0, 0],
        "shots_on": [0, 0],
        "corners": [0, 0],
        "yellow": [0, 0],
        "red": [0, 0],
        "passes": [0, 0],
        "pass_accuracy": [None, None],
        "fouls": [0, 0],
        "offsides": [0, 0],
        "saves": [0, 0],
    },
    "ball": {"x": 50, "y": 50, "label": "Meio-campo"},
    "events": [],
    "source": "manual",
}

clients: set[WebSocket] = set()
rehearsal = Rehearsal()

def broadcast_state():
    return rehearsal.view({**state, 'feed_health': {**free_feed.info, 'mode': free_feed.mode}})

class Patch(BaseModel):
    data: dict[str, Any]


class ManualEvent(BaseModel):
    minute: int | str = 0
    icon: str = "●"
    text: str = "Evento"
    kind: str = "event"
    team: str = ""
    player: str = ""
    speak: bool = True


def normalize_event_kind(payload: ManualEvent) -> str:
    if payload.kind in {"goal", "card", "substitution", "review", "cancelled", "correction", "event", "yellow", "red"}:
        return "card" if payload.kind in {"yellow", "red"} else payload.kind
    if payload.icon == "⚽":
        return "goal"
    if payload.icon in {"🟨", "🟥"}:
        return "card"
    return "event"

def deep_update(dst: dict, src: dict):
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            deep_update(dst[k], v)
        else:
            dst[k] = v

async def broadcast():
    news_context.observe()
    club_context.observe(state)
    coach_overrides.observe()
    ge_feed.observe()
    from backend.ge_feed import apply_pregame_lineups
    apply_pregame_lineups(state)
    support_feed.observe()
    player_profiles.observe()
    narration_channel.refresh()
    dead = []
    for ws in tuple(clients):
        try:
            await ws.send_json(broadcast_state())
        except Exception:
            dead.append(ws)
    for ws in dead:
        clients.discard(ws)

ge_feed = GEFeed(state, broadcast)
ge_feed.install(app)
narration_channel = NarrationChannel(BASE, state, broadcast)
narration_channel.install(app)
free_feed = FreeFeed(state, broadcast)
free_feed.install(app)
rehearsal.install(app, broadcast)
appearance_store.install(app, state, broadcast)
install_settings(app, BASE, LEAGUES)
local_voice = LocalVoice(BASE)
local_voice.install(app)
local_brain = LocalBrain(BASE)
local_brain.install(app)
club_context = ClubContext()
club_context.install(app, state, broadcast)
player_profiles = PlayerProfiles(state, broadcast)
player_profiles.install(app)
from backend.support_feed import SupportFeed
support_feed = SupportFeed(state, broadcast)
support_feed.install(app)
player_photos = PlayerPhotos(BASE, state, broadcast)
player_photos.install(app)
from backend.coach_overrides import CoachOverrides
coach_overrides = CoachOverrides(BASE, state, broadcast)
coach_overrides.install(app)
youtube_chat = YouTubeLiveChat(state, broadcast, BASE)
youtube_chat.install(app)
news_context = NewsContext(state, broadcast, BASE, local_brain)
news_context.install(app)

@app.get("/favicon.ico", include_in_schema=False, status_code=204)
async def favicon():
    return Response(status_code=204)

@app.get("/")
async def root():
    return FileResponse(BASE / "static" / "control.html", headers={'Cache-Control': 'no-cache'})

@app.get("/control")
async def control():
    return FileResponse(BASE / "static" / "control.html", headers={'Cache-Control': 'no-cache'})

@app.get("/overlay")
async def overlay():
    return FileResponse(BASE / "static" / "overlay.html", headers={'Cache-Control': 'no-cache'})

@app.get("/partida")
@app.get("/em-campo")
@app.get("/em_campo")
@app.get("/reservas")
@app.get("/tabela")
@app.get("/formacao")
@app.get("/formação")
@app.get("/mais-comentados")
@app.get("/chat")
async def overlay_scene():
    """Dedicated OBS browser sources; the client fixes the requested scene by URL."""
    return FileResponse(BASE / "static" / "overlay.html", headers={'Cache-Control': 'no-cache'})

@app.get("/audio")
async def audio_channel():
    return FileResponse(BASE / "static" / "audio.html", headers={'Cache-Control': 'no-cache'})

@app.get("/api/state")
async def get_state():
    narration_channel.refresh()
    return broadcast_state()

@app.post("/api/state")
async def patch_state(patch: Patch):
    await free_feed.stop()
    state.pop("clock_display", None)
    state["phase"] = "manual"
    deep_update(state, patch.data)
    state["source"] = "manual"
    await broadcast()
    return state

@app.post("/api/event")
async def add_event(payload: ManualEvent):
    kind = normalize_event_kind(payload)
    event = {
        "id": "manual:" + str(uuid4()),
        "minute": payload.minute if payload.minute != "" else state.get("minute", 0),
        "text": payload.text.strip()[:900] or "Evento",
        "icon": ("🟨" if payload.kind == "yellow" else "🟥" if payload.kind == "red" else "⚽" if payload.kind == "goal" else "↔" if payload.kind == "substitution" else "●" if payload.kind == "event" else "🔎"),
        "kind": kind,
        "team": payload.team.strip()[:120],
        "player": payload.player.strip()[:120],
        "speak": payload.speak,
        "urgent": kind in {"goal", "review", "cancelled", "correction"},
        "source": {"name": "Lance manual"},
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    state["events"] = ([event] + state["events"])[:6]
    await broadcast()
    return state

@app.post("/api/reset")
async def reset():
    await free_feed.stop()
    state.pop("clock_display", None)
    state["source"] = "manual"
    state["phase"] = "pre"
    state["home"]["score"] = 0
    state["away"]["score"] = 0
    state["minute"] = 0
    state["status"] = "PRÉ-JOGO"
    for k in state["stats"]:
        if k == "possession":
            state["stats"][k] = [50, 50]
        else:
            state["stats"][k] = [0, 0]
    state["events"] = []
    state["cards"] = []
    for lineup in state.get("lineups", {}).values():
        for player in lineup.get("starters", []) + lineup.get("bench", []):
            player["yellow"] = player["red"] = 0
    state["ball"] = {"x": 50, "y": 50, "label": "Meio-campo"}
    await broadcast()
    return state

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    clients.add(ws)
    await ws.send_json(broadcast_state())
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        clients.discard(ws)

def stat_map(stats):
    out = {}
    mapping = {
        "Ball Possession": "possession",
        "Total Shots": "shots",
        "Shots on Goal": "shots_on",
        "Corner Kicks": "corners",
        "Yellow Cards": "yellow",
        "Red Cards": "red",
    }
    for item in stats:
        typ = item.get("type")
        if typ in mapping:
            val = item.get("value")
            if isinstance(val, str) and val.endswith("%"):
                val = val[:-1]
            try:
                val = int(val or 0)
            except Exception:
                val = 0
            out[mapping[typ]] = val
    return out

async def fetch_api_football():
    if free_feed.mode != "legacy":
        return
    key = os.getenv("API_FOOTBALL_KEY", "").strip()
    fixture_id = os.getenv("FIXTURE_ID", "").strip()
    if not key or not fixture_id:
        return
    headers = {"x-apisports-key": key}
    base = "https://v3.football.api-sports.io"
    async with httpx.AsyncClient(timeout=20) as client:
        fx = await client.get(f"{base}/fixtures", params={"id": fixture_id}, headers=headers)
        fx.raise_for_status()
        rows = fx.json().get("response", [])
        if free_feed.mode != "legacy":
            return
        if not rows:
            return
        row = rows[0]
        state["competition"] = row.get("league", {}).get("name", state["competition"])
        state["home"]["name"] = row.get("teams", {}).get("home", {}).get("name", state["home"]["name"])
        state["away"]["name"] = row.get("teams", {}).get("away", {}).get("name", state["away"]["name"])
        state["home"]["score"] = row.get("goals", {}).get("home") or 0
        state["away"]["score"] = row.get("goals", {}).get("away") or 0
        for side in ("home", "away"):
            state[side]["logo"] = row.get("teams", {}).get(side, {}).get("logo") or ""
            state[side]["abbreviation"] = state[side]["name"][:3].upper()
        state["venue"] = row.get("fixture", {}).get("venue", {}).get("name") or ""
        status = row.get("fixture", {}).get("status", {})
        state["minute"] = status.get("elapsed") or 0
        state["status"] = status.get("short") or "AO VIVO"
        state["phase"] = "post" if state["status"] in ("FT", "AET", "PEN") else "pre" if state["status"] in ("NS", "TBD", "PST") else "in"

        st = await client.get(f"{base}/fixtures/statistics", params={"fixture": fixture_id}, headers=headers)
        st.raise_for_status()
        stat_rows = st.json().get("response", [])
        if free_feed.mode != "legacy":
            return
        if len(stat_rows) >= 2:
            a = stat_map(stat_rows[0].get("statistics", []))
            b = stat_map(stat_rows[1].get("statistics", []))
            for k in state["stats"]:
                state["stats"][k] = [a.get(k, 0), b.get(k, 0)]

        state["source"] = "API-Football"
        await broadcast()

async def api_loop():
    sec = max(30, int(os.getenv("API_REFRESH_SECONDS", "60")))
    while True:
        try:
            await fetch_api_football()
        except Exception as exc:
            print("API-Football:", exc)
        await asyncio.sleep(sec)

@app.on_event("startup")
async def startup():
    if os.getenv("API_FOOTBALL_KEY", "").strip() and os.getenv("FIXTURE_ID", "").strip():
        asyncio.create_task(api_loop())
    if youtube_chat.configured():
        await youtube_chat.start()


@app.on_event("shutdown")
async def shutdown():
    await youtube_chat.stop()
