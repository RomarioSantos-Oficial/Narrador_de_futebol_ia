"""Optional GE commentary from the public agenda and public match pages."""
import asyncio
import copy
import hashlib
import json
import re
import time
from datetime import datetime, timezone, timedelta
from uuid import uuid4

from fastapi import HTTPException
from pydantic import BaseModel, Field

from backend.comparison import normalized_name, instant
from tools.inspect_ge import parse_page, validate_url
from backend.ge_browser import GEPublicPage, GEAccessUnavailable

BRASILIA = timezone(timedelta(hours=-3))
ALIASES = {"brazil": "brasil",
           "sport recife": "sport", "sport club do recife": "sport",
           "rb bragantino": "bragantino", "red bull bragantino": "bragantino",
           "atletico mineiro": "atletico mg", "athletico paranaense": "athletico pr"}


def team_name(value):
    name = normalized_name(value)
    return ALIASES.get(name, name)


def match_key(state):
    if not state.get("kickoff") or state.get("source") == "manual":
        return None
    return (state.get("competition"), state.get("home", {}).get("name"),
            state.get("away", {}).get("name"), state["kickoff"])


def kickoff(match):
    return datetime.fromisoformat(match["startDate"] + "T" + match["startHour"]).replace(tzinfo=BRASILIA)


def matches(state, match, agenda=False):
    try:
        keys = ("firstContestant", "secondContestant") if agenda else ("homeTeam", "awayTeam")
        for side, key in zip(("home", "away"), keys):
            names = {team_name(match[key].get(n) or "") for n in ("name", "popularName", "abbreviation")}
            if team_name(state[side]["name"]) not in names:
                return False
        return abs((instant(state["kickoff"]) - kickoff(match)).total_seconds()) <= 900
    except (KeyError, TypeError, ValueError):
        return False


def agenda_games(html):
    marker = re.search(r"window\.dataSportsSchedule\s*=\s*\{\s*sport:\s*", html)
    if not marker:
        raise ValueError("Agenda do GE indisponível neste formato.")
    days, _ = json.JSONDecoder().raw_decode(html[marker.end():])
    rows = {}
    for day in days.values():
        for championship in day.get("championshipsAgenda", []):
            for group in ("now", "future", "past"):
                for event in championship.get(group, []):
                    match = event.get("match") or {}
                    url = (match.get("transmission") or {}).get("url")
                    if url:
                        try:
                            validate_url(url)
                            rows[str(match["id"])] = {"match": match, "url": url}
                        except (ValueError, KeyError):
                            pass
    return list(rows.values())


def event_from_play(play, url):
    """Keep editorial wording as plain text; omit recaps, social embeds and video."""
    typ = (play.get("playType") or play.get("type") or {}).get("id")
    if typ not in {"NORMAL", "GOAL", "CARD", "IMPORTANT", "SUBSTITUTION", "PENALTY"}:
        return None
    if "body" in play:
        text = " ".join(b.get("text", "") for b in (play.get("body") or {}).get("blocks", [])
                        if isinstance(b, dict) and b.get("type") != "atomic")
    else:
        text = play.get("text") or ""
    title = (play.get("title") or "").strip()
    text = re.sub(r"\s+", " ", text).strip()
    if not text or not play.get("id"):
        return None
    details = play.get("details") or {}
    athlete = details.get("athlete") or {}
    period = play.get("period") or {}
    moment = str(play.get("moment") or "")
    minute = moment.split(":")[0].lstrip("0") or "0"
    kind = "goal" if typ == "GOAL" and not re.search(r"anulad|cancelad", title + " " + text, re.I) else "card" if typ == "CARD" else "event"
    value = {
        "id": "ge:" + str(play["id"]), "text": (title + ". " if title else "") + text,
        "minute": minute if moment else "—", "period": period.get("abbreviation", ""),
        "icon": {"goal": "⚽", "card": "▪"}.get(kind, "●"), "kind": kind,
        "player": athlete.get("popularName") or athlete.get("name"),
        "source": {"name": "ge · tempo real", "url": url},
        "created_at": play.get("createdAt"), "editorial": True,
    }
    value["revision"] = hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
    return value


class GEOptions(BaseModel):
    enabled: bool = True
    url: str = Field(default="", max_length=1000)


class GEFeed:
    def __init__(self, state, broadcast):
        self.state, self.broadcast = state, broadcast
        self.enabled = True
        self.key = None
        self.task = None
        self.manual_url = ""
        self.agenda_cache = (0, [])
        self.generation = 0

    def observe(self):
        key = match_key(self.state) if self.enabled else None
        if key == self.key:
            return
        self.key = key
        self.manual_url = ""
        self.restart()

    def restart(self):
        self.generation += 1
        if self.task:
            self.task.cancel()
        self.state["ge"] = {"enabled": self.enabled, "ready": False, "events": [],
                            "session": str(uuid4()), "status": "Buscando cobertura no GE…" if self.key else "Selecione uma partida para buscar no GE."}
        if self.key:
            self.task = asyncio.create_task(self.run(copy.deepcopy(self.state), self.generation))

    async def discover(self, client, primary):
        if self.manual_url:
            return self.manual_url
        if time.monotonic() - self.agenda_cache[0] > 300:
            self.agenda_cache = (time.monotonic(), agenda_games(await client.load("https://ge.globo.com/agenda/")))
        candidates = [row["url"] for row in self.agenda_cache[1] if matches(primary, row["match"], agenda=True)]
        return candidates[0] if len(candidates) == 1 else None

    async def publish(self, generation, **values):
        if generation != self.generation:
            return
        if "updated_at" not in values:
            values["updated_at"] = datetime.now(timezone.utc).isoformat()
        self.state["updated_at"] = values["updated_at"]
        self.state.setdefault("ge", {})
        self.state["ge"].update(values)
        await self.broadcast()

    async def run(self, primary, generation):
        """Use the accessible public page; do not retry the refused live channel."""
        self.started_at = datetime.now(timezone.utc)
        while generation == self.generation:
            try:
                async with GEPublicPage(scripts=False) as client:
                    url = await self.discover(client, primary)
                if url:
                    await self.poll_public_page(primary, generation, url, "Consulta da página pública; o canal direto não é utilizado.")
                    return
                await self.publish(generation, ready=False, mode="page", status="Cobertura GE não encontrada. Você pode informar o link da mesma partida.")
            except asyncio.CancelledError:
                raise
            except (GEAccessUnavailable, ImportError) as exc:
                await self.publish(generation, ready=False, error=str(exc), status="GE indisponível. Os lances da fonte principal continuam ativos.")
                return
            except Exception as exc:
                await self.publish(generation, ready=False, error=str(exc)[:240], status="Não foi possível consultar a agenda GE. Verifique se o Microsoft Edge está instalado.")
            await asyncio.sleep(300)

    async def poll_public_page(self, primary, generation, url, warning):
        await self.publish(generation, ready=False, connected=False, mode="page", warning=warning,
                           status="Canal GE indisponível. Consultando a página pública a cada 30 segundos…")
        previous = {}
        initial = True
        try:
            async with GEPublicPage(scripts=False) as client:
                while generation == self.generation:
                    try:
                        snapshot = parse_page(await client.load(validate_url(url)))
                        if not matches(primary, snapshot["transmission"]["match"]):
                            raise GEAccessUnavailable("A identidade da partida GE mudou. Cobertura desvinculada.")
                        events = self.snapshot_events(snapshot["events"], url, previous, initial)
                        previous = events
                        initial = False
                        await self.publish(generation, ready=True, connected=True, mode="page", interval=30, error=None,
                                           events=self.sorted_events(events), url=url, updated_at=datetime.now(timezone.utc).isoformat(),
                                           status="GE · página pública a cada 30 s. Lances novos seguem diretamente para a voz.")
                    except GEAccessUnavailable:
                        raise
                    except (ValueError, RuntimeError) as exc:
                        await self.publish(generation, ready=False, connected=False, error=str(exc)[:240],
                                           status="Não foi possível atualizar a página GE. Nova consulta em 30 segundos.")
                    await asyncio.sleep(30)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self.publish(generation, ready=False, connected=False, error=str(exc)[:240],
                               status="Página GE indisponível. Os lances da fonte principal continuam ativos.")

    def snapshot_events(self, plays, url, previous, initial):
        result = {}
        previous_times = []
        for old_event in previous.values():
            try:
                previous_times.append(instant(old_event.get("created_at")))
            except (ValueError, TypeError, AttributeError):
                pass
        newest_previous = max(previous_times, default=None)
        for play in plays:
            event = event_from_play(play, url)
            if not event:
                continue
            old = previous.get(event["id"])
            changed = not old or old["revision"] != event["revision"]
            advances_feed = False
            try:
                created = instant(event["created_at"])
                recent = -60 <= (datetime.now(timezone.utc)-created).total_seconds() <= 90
                advances_feed = newest_previous is not None and created > newest_previous
            except (ValueError, TypeError, AttributeError):
                recent = bool(event.get("minute") and event["minute"] not in ("—", ""))
            initial_recent = initial and recent and not previous
            # Eligibility belongs to the revision, not to a single polling cycle.
            # Each audio client deduplicates what it has actually queued.
            speak = initial_recent or (not initial and (
                (bool(old) and (changed or old.get("speak", False)))
                or (not old and (recent or advances_feed))))
            corrected = bool(old and (changed or old.get("corrected", False)))
            event.update(speak=speak, corrected=corrected, _play=play)
            result[event["id"]] = event
        return result

    @staticmethod
    def sorted_events(events):
        rows = sorted(events.values(), key=lambda e: (e.get("created_at") or "", e["id"]), reverse=True)[:100]
        return [{k: v for k, v in row.items() if k != "_play"} for row in rows]

    async def stop(self):
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

    def install(self, app):
        @app.get("/api/ge/status")
        async def status():
            return self.state.get("ge", {"enabled": self.enabled, "ready": False})

        @app.post("/api/ge/options")
        async def options(payload: GEOptions):
            primary = copy.deepcopy(self.state)
            if payload.url:
                try:
                    validate_url(payload.url)
                    if not match_key(primary):
                        raise ValueError("Selecione uma partida automática antes de vincular o GE.")
                except ValueError as exc:
                    raise HTTPException(400, str(exc)) from exc
                if match_key(primary) != match_key(self.state):
                    raise HTTPException(409, "A partida mudou durante a consulta. Tente novamente.")
            self.enabled = payload.enabled
            self.key = match_key(self.state) if self.enabled else None
            self.manual_url = payload.url
            self.restart()
            await self.broadcast()
            return self.state["ge"]

        app.add_event_handler("shutdown", self.stop)
