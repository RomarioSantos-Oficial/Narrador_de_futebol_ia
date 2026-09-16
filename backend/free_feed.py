"""Experimental, keyless ESPN feed for local overlay testing."""
import asyncio
import ssl
import re
from datetime import date, datetime, timezone
from typing import Literal
from backend import providers
from backend import comparison
import copy
import time
from backend.match_context import extract_context, event_text

import httpx
from fastapi import HTTPException
from pydantic import BaseModel, Field
from backend.leagues import LEAGUES
STAT_KEYS = {"possessionPct": "possession", "totalShots": "shots",
             "shotsOnTarget": "shots_on", "wonCorners": "corners",
             "yellowCards": "yellow", "redCards": "red", "totalPasses": "passes",
             "foulsCommitted": "fouls", "offsides": "offsides", "saves": "saves"}


class Selection(BaseModel):
    league: str
    event: str = Field(pattern=r"^\d{1,15}$")
    provider: Literal['espn', 'api_football', 'football_data', 'thesportsdb'] = 'espn'


class FeedOptions(BaseModel):
    enrich: bool = False


async def request(league, endpoint, **params):
    if league not in LEAGUES:
        raise HTTPException(400, "Campeonato inválido.")
    try:
        async with httpx.AsyncClient(timeout=20, verify=ssl.create_default_context()) as client:
            response = await client.get(
                f"https://site.api.espn.com/apis/site/v2/sports/soccer/{league}/{endpoint}",
                params=params,
            )
            response.raise_for_status()
            return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(502, "Não foi possível consultar a ESPN. Tente novamente.") from exc


def normalize(data, league):
    competition = data["header"]["competitions"][0]
    competitors = {c["homeAway"]: c for c in competition["competitors"]}
    status = competition["status"]
    kind = status["type"]
    phase = kind.get("state")
    label = {"pre": "PRÉ-JOGO", "post": "ENCERRADO", "in": "AO VIVO"}.get(phase, kind.get("description", ""))
    if kind.get("name") == "STATUS_HALFTIME":
        label = "INTERVALO"
    elif not kind.get("completed") and phase != "in" and kind.get("name") != "STATUS_SCHEDULED":
        label = kind.get("description", label)
    clock = status.get("displayClock") or ("0'" if phase == "pre" else kind.get("shortDetail", "—"))
    stats = {key: [None, None] for key in STAT_KEYS.values()}
    stats["pass_accuracy"] = [None, None]
    if phase != "pre":
        for team in data.get("boxscore", {}).get("teams", []):
            side = next((i for i, name in enumerate(("home", "away"))
                         if str(competitors[name]["team"]["id"]) == str(team["team"]["id"])), None)
            if side is None:
                continue
            for item in team.get("statistics", []):
                key = STAT_KEYS.get(item.get("name"))
                if key:
                    try:
                        stats[key][side] = float(str(item["displayValue"]).rstrip("%"))
                    except (ValueError, KeyError):
                        pass
            raw = {item.get("name"): item.get("displayValue") for item in team.get("statistics", [])}
            try:
                passes = float(raw["totalPasses"])
                if passes > 0:
                    stats["pass_accuracy"][side] = round(float(raw["accuratePasses"]) / passes * 100, 1)
            except (KeyError, TypeError, ValueError):
                pass
    clock_numbers = re.findall(r"\d+", clock.split(":")[0])
    minute = sum(map(int, clock_numbers)) if clock_numbers else 0
    result = {"competition": LEAGUES[league], "minute": minute,
              "kickoff": competition.get('date', ''),
              "clock_display": clock, "status": label, "phase": phase, "stats": stats,
              "venue": data.get("gameInfo", {}).get("venue", {}).get("fullName", ""),
              "events": [], "source": "ESPN (teste gratuito)",
              "ball": {"x": 50, "y": 50, "label": "Posição da bola não fornecida pela fonte"}}
    for side in ("home", "away"):
        team = competitors[side]
        info = team["team"]
        logos = info.get("logos") or []
        result[side] = {"name": info["displayName"], "score": int(team.get("score") or 0),
                        "abbreviation": info.get("abbreviation", info["displayName"][:3].upper()),
                        "logo": logos[0].get("href", "") if logos else info.get("logo", "")}
    result["lineups"] = {"home": {"starters": [], "bench": [], "formation": ""},
                         "away": {"starters": [], "bench": [], "formation": ""}}
    result["cards"] = []
    for group in data.get("rosters", []) or []:
        side = next((side for side in ("home", "away")
                     if str(group.get("team", {}).get("id")) == str(competitors[side]["team"]["id"])), None)
        if side is None:
            continue
        lineup = result["lineups"][side]
        formation = group.get("formation", "")
        lineup["formation"] = formation.get("displayName", "") if isinstance(formation, dict) else str(formation or "")
        for entry in group.get("roster", []) or []:
            athlete = entry.get("athlete", {})
            if not athlete.get("displayName"):
                continue
            player_stats = {item.get("name"): item.get("value", item.get("displayValue")) for item in entry.get("stats", [])}
            def count(name):
                try:
                    return int(float(player_stats.get(name) or 0))
                except (ValueError, TypeError):
                    return 0
            player = {"id": str(athlete.get("id", "")), "name": athlete["displayName"],
                      "number": entry.get("jersey", ""), "position": entry.get("position", {}).get("abbreviation", ""),
                      "yellow": count("yellowCards"), "red": count("redCards"),
                      "captain": bool(entry.get("captain") or entry.get("isCaptain")),
                      "subbed_in": bool(entry.get("subbedIn")), "subbed_out": bool(entry.get("subbedOut"))}
            lineup["starters" if entry.get("starter") else "bench"].append(player)
    for event in data.get("keyEvents", []) or []:
        typ = event.get("type", {}).get("type", "")
        participants = event.get("participants", []) or []
        athlete = participants[0].get("athlete", {}) if participants else {}
        player_name = athlete.get("displayName", "")
        team_name = event.get("team", {}).get("displayName", "")
        minute_text = event.get("clock", {}).get("displayValue", "—").rstrip("'")
        icon = "●"
        text = event.get("text") or event.get("type", {}).get("text", "Evento")
        if "card" in typ:
            red = "red" in typ or "second-yellow" in typ or "yellow-red" in typ
            icon = "🟥" if red else "🟨"
            if player_name:
                text = f"Cartão {'vermelho' if red else 'amarelo'} · {player_name}" + (f" ({team_name})" if team_name else "")
            result["cards"].append({"minute": minute_text, "player": player_name or "Jogador não informado",
                                    "player_id": str(athlete.get("id", "")), "team": team_name,
                                    "team_id": str(event.get("team", {}).get("id", "")), "color": "red" if red else "yellow"})
        elif event.get("scoringPlay"):
            icon = "⚽"
            if player_name:
                text = f"Gol · {player_name}" + (f" ({team_name})" if team_name else "")
        elif typ == "kickoff":
            text = "Início do segundo tempo" if event.get("period", {}).get("number") == 2 else "Início da partida"
            minute_text = minute_text or "0"
        text, original = event_text(event, text)
        result["events"].append({"minute": minute_text or '—', "icon": icon, "text": text, "text_en": original,
                                 "players": [{'id': str(p.get('athlete', {}).get('id', '')), 'name': p.get('athlete', {}).get('displayName', '')} for p in participants]})
    # Card events supplement player statistics when a provider omits the latter.
    for side in ("home", "away"):
        lineup = result["lineups"][side]
        for player in lineup["starters"] + lineup["bench"]:
            for color in ("yellow", "red"):
                received = [c for c in result["cards"] if player["id"] and c["player_id"] == player["id"]
                            and c["team_id"] == str(competitors[side]["team"]["id"]) and c["color"] == color]
                player[color] = max(player[color], len(received))
                if player[color] and not received:
                    result["cards"].append({"minute": "—", "player": player["name"], "player_id": player["id"],
                                            "team": result[side]["name"], "team_id": str(competitors[side]["team"]["id"]), "color": color})
    result["events"] = result["events"][-6:][::-1]
    result.update(extract_context(data, competitors, league))
    if result['league_table']:
        result['league_table']['name'] = LEAGUES[league]
    return result, bool(kind.get("completed"))


class FreeFeed:
    def __init__(self, state, broadcast):
        self.state, self.broadcast = state, broadcast
        self.task = None
        self.selected = None
        self.mode = "legacy"
        self.enrich = False
        self.primary_state = None
        self.comparison = None
        self.comparison_key = None
        self.comparison_time = 0
        self.info = {"active": False, "error": None, "updated_at": None, "interval": 30}

    async def stop(self):
        self.mode = "manual"
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
            self.task = None
        self.info["active"] = False

    async def update(self, selection):
        try:
            if selection.provider == 'espn':
                data = await request(selection.league, "summary", event=selection.event)
                result, completed = normalize(data, selection.league)
            else:
                result, completed = await providers.match(selection.provider, selection.event)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise HTTPException(502, "A fonte retornou dados incompletos para esta partida.") from exc
        result['data_sources'] = {}
        result['updated_at'] = datetime.now(timezone.utc).isoformat()
        self.primary_state = copy.deepcopy(result)
        if self.enrich:
            report = await self.compare(selection, result)
            result = comparison.enrich(result, report)
        self.state.update(result)
        self.info.update(error=None, updated_at=datetime.now(timezone.utc).isoformat())
        self.state["updated_at"] = self.info["updated_at"]
        await self.broadcast()
        return completed

    async def compare(self, selection, primary):
        key = (selection.provider, selection.league, selection.event)
        if self.comparison_key != key or time.monotonic() - self.comparison_time >= 300:
            report = await comparison.compare(selection, primary, request, normalize)
            self.comparison, self.comparison_key = report, key
            self.comparison_time = time.monotonic()
        else:
            self.comparison['sources'][selection.provider].update(data=copy.deepcopy(primary), sampled_at=primary.get('updated_at'))
            self.comparison['recommendation'] = comparison.recommend(self.comparison)
        return self.comparison

    async def loop(self, selection):
        try:
            while True:
                await asyncio.sleep(self.info['interval'])
                try:
                    if await self.update(selection):
                        break
                except HTTPException as exc:
                    self.info["error"] = exc.detail
                    if exc.status_code in (401, 403, 429):
                        break
                except Exception:
                    self.info["error"] = f"Falha na atualização. Nova tentativa em {self.info['interval']} segundos."
        finally:
            self.info["active"] = False

    def install(self, app):
        @app.post('/api/feed/options')
        async def options(payload: FeedOptions):
            self.enrich = payload.enrich
            return {'enrich': self.enrich}

        @app.post('/api/feed/compare')
        async def compare_sources():
            if not self.selected or self.primary_state is None:
                raise HTTPException(400, 'Carregue uma partida primeiro.')
            selection = Selection(**self.selected)
            return await self.compare(selection, copy.deepcopy(self.primary_state))

        @app.get("/api/free/status")
        async def status():
            return {**self.info, "selected": self.selected, "leagues": LEAGUES, "enrich": self.enrich}

        @app.get("/api/free/games")
        async def games(league: str = "bra.1", day: date | None = None, live: bool = False,
                        provider: Literal['espn', 'api_football', 'football_data', 'thesportsdb'] = 'espn'):
            if provider != 'espn':
                return await providers.games(provider, league, day, live)
            params = {"limit": 100}
            if not live:
                params["dates"] = (day or date.today()).strftime("%Y%m%d")
            data = await request(league, "scoreboard", **params)
            return [{"id": e["id"], "name": e["name"], "date": e["date"],
                     "status": {"in": "AO VIVO", "pre": "AGENDADO", "post": "ENCERRADO"}.get(e.get("status", {}).get("type", {}).get("state"), ""),
                     "clock": e.get("status", {}).get("displayClock", "")}
                    for e in data.get("events", [])
                    if not live or e.get("status", {}).get("type", {}).get("state") == "in"]

        @app.post("/api/free/select")
        async def select(selection: Selection):
            await self.stop()
            self.info['interval'] = providers.SOURCES[selection.provider]['interval']
            completed = await self.update(selection)
            self.mode = "free"
            self.selected = selection.model_dump()
            self.info["active"] = not completed and self.info['interval'] > 0
            if self.info['active']:
                self.task = asyncio.create_task(self.loop(selection))
            return self.info

        @app.post("/api/free/stop")
        async def stop():
            await self.stop()
            return self.info

        app.add_event_handler("shutdown", self.stop)
