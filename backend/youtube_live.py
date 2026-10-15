"""Optional YouTube Live chat reader.

Uses the official liveChatMessages.list endpoint when YOUTUBE_API_KEY and
YOUTUBE_LIVE_CHAT_ID are configured. It never changes the match score.
"""
import asyncio
import json
import os
import re
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import httpx


COMMANDS = {"placar", "jogador", "pergunta", "narrar", "escalação", "escalacao", "vota", "enquete"}


def clean_text(value: Any, limit: int = 240) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


class YouTubeLiveChat:
    def __init__(self, state, broadcast, base=None):
        self.state = state
        self.broadcast = broadcast
        self.settings_path = (base / "youtube_live.json") if base else None
        try:
            self.saved_settings = json.loads(self.settings_path.read_text(encoding="utf-8")) if self.settings_path else {}
        except (OSError, ValueError):
            self.saved_settings = {}
        self.task = None
        self.next_page = ""
        self.seen: set[str] = set()
        self.last_user: dict[str, float] = {}
        self.mentions: dict[str, dict[str, Any]] = {}
        self.votes: dict[str, int] = {}
        self.vote_users: dict[str, str] = {}
        self.poll_users: dict[str, str] = {}
        self.poll = {"question": "Quem foi o destaque da partida?", "options": [], "votes": {}}
        self.message_fingerprints: dict[str, float] = {}
        self.info = {"enabled": False, "connected": False, "messages": 0, "error": None}
        self.state["youtube_chat"] = dict(self.info)

    def match_key(self):
        return "|".join(str(self.state.get(key, "")) if key == "competition" else str(self.state.get(key, {}).get("name", "")) for key in ("competition", "home", "away"))

    def config(self):
        saved = self.saved_settings.get(self.match_key(), {})
        return {"api_key": str(saved.get("api_key") or os.getenv("YOUTUBE_API_KEY", "")).strip(), "live_chat_id": str(saved.get("live_chat_id") or os.getenv("YOUTUBE_LIVE_CHAT_ID", "")).strip(), "live_url": str(saved.get("live_url", "")).strip(), "video_id": str(saved.get("video_id", "")).strip()}

    def configured(self):
        current = self.config()
        return bool(current["api_key"] and current["live_chat_id"]) or bool(current["live_url"] and self.extract_video_id(current["live_url"]))

    @staticmethod
    def extract_video_id(value):
        text = clean_text(value, 500)
        if re.fullmatch(r"[A-Za-z0-9_-]{11}", text):
            return text
        match = re.search(r"(?:[?&]v=|youtu\.be/|youtube\.com/(?:live/|embed/|watch\?v=))([A-Za-z0-9_-]{11})", text)
        return match.group(1) if match else ""

    @classmethod
    def canonical_live_url(cls, value):
        video_id = cls.extract_video_id(value)
        return f"https://www.youtube.com/watch?v={video_id}" if video_id else value.strip()

    @staticmethod
    def extract_channel_handle(value):
        text = clean_text(value, 300).strip()
        match = re.fullmatch(r"@([A-Za-z0-9._-]{3,100})", text)
        if match:
            return match.group(1)
        match = re.search(r"youtube\.com/@([A-Za-z0-9._-]{3,100})", text)
        return match.group(1) if match else ""

    async def resolve_live_chat_id(self, api_key, value):
        video_id = self.extract_video_id(value)
        if not video_id:
            return value.strip(), ""
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get("https://www.googleapis.com/youtube/v3/videos", params={"part": "liveStreamingDetails", "id": video_id, "key": api_key})
            if response.status_code in (400, 401, 403):
                try:
                    reason = response.json().get("error", {}).get("errors", [{}])[0].get("reason", "")
                except (AttributeError, IndexError, TypeError, ValueError):
                    reason = ""
                messages = {
                    "keyInvalid": "A chave informada não é uma chave válida do Google. Ela normalmente começa com AIza.",
                    "accessNotConfigured": "Ative a YouTube Data API v3 no mesmo projeto Google Cloud da chave.",
                    "forbidden": "A chave foi bloqueada pelas restrições do Google Cloud ou não pode acessar a YouTube Data API v3.",
                }
                raise ValueError(messages.get(reason, "A chave da API do YouTube foi rejeitada. Confirme a chave, a API YouTube Data v3 e as restrições no Google Cloud."))
            response.raise_for_status()
            items = response.json().get("items", [])
            if not items:
                raise ValueError("O vídeo não foi encontrado. Confira o link e a chave da API.")
            details = items[0].get("liveStreamingDetails", {})
            chat_id = details.get("activeLiveChatId")
            if not chat_id:
                raise ValueError("Essa live não está ativa ou o chat ao vivo está desativado. Abra a transmissão ao vivo e tente novamente.")
            return chat_id, video_id

    async def resolve_channel_live_chat(self, api_key, value):
        handle = self.extract_channel_handle(value)
        if not handle:
            return value.strip(), ""
        async with httpx.AsyncClient(timeout=20) as client:
            channel_response = await client.get("https://www.googleapis.com/youtube/v3/channels", params={"part": "id", "forHandle": handle, "key": api_key})
            if channel_response.status_code in (400, 401, 403):
                raise ValueError("Não foi possível consultar o canal. Confirme a chave e se a YouTube Data API v3 está ativada.")
            channel_response.raise_for_status()
            channels = channel_response.json().get("items", [])
            if not channels:
                raise ValueError(f"O canal @{handle} não foi encontrado.")
            channel_id = channels[0].get("id", "")
            live_response = await client.get("https://www.googleapis.com/youtube/v3/search", params={"part": "snippet", "channelId": channel_id, "eventType": "live", "type": "video", "maxResults": 5, "key": api_key})
            if live_response.status_code in (400, 401, 403):
                raise ValueError("A chave não pode buscar lives do canal. Ative a YouTube Data API v3 e confira as restrições da chave.")
            live_response.raise_for_status()
            videos = [item.get("id", {}).get("videoId") for item in live_response.json().get("items", []) if item.get("id", {}).get("videoId")]
            if not videos:
                raise ValueError(f"Não encontrei uma live ativa no canal @{handle}.")
            video_response = await client.get("https://www.googleapis.com/youtube/v3/videos", params={"part": "liveStreamingDetails", "id": ",".join(videos), "key": api_key})
            video_response.raise_for_status()
            for item in video_response.json().get("items", []):
                chat_id = item.get("liveStreamingDetails", {}).get("activeLiveChatId")
                if chat_id:
                    return chat_id, item.get("id", "")
            raise ValueError(f"A live ativa de @{handle} não está com o chat habilitado.")

    async def resolve_chat_reference(self, api_key, value):
        if self.extract_video_id(value):
            return await self.resolve_live_chat_id(api_key, value)
        if self.extract_channel_handle(value):
            return await self.resolve_channel_live_chat(api_key, value)
        return value.strip(), ""

    def roster(self):
        return self._player_names()

    def _find_player(self, value):
        folded = clean_text(value, 80).casefold()
        players = self.roster()
        return (next((name for name in players if name.casefold() == folded), None)
                or next((name for name in players if folded and folded in name.casefold()), None))

    def votes_ranking(self):
        total = sum(self.votes.values())
        rows = [{"name": name, "votes": count, "percentage": round(count * 100 / total, 1) if total else 0}
                for name, count in self.votes.items() if count and name in self.roster()]
        return sorted(rows, key=lambda item: (-item["votes"], item["name"].casefold()))[:3]

    def poll_status(self):
        total = sum(self.poll.get("votes", {}).values())
        return {"question": self.poll.get("question", ""), "options": [
            {"name": name, "votes": count, "percentage": round(count * 100 / total, 1) if total else 0}
            for name, count in self.poll.get("votes", {}).items()]}

    def status(self):
        config = self.config()
        return {**self.info, "configured": self.configured(), "mode": "sem_api" if config["live_url"] and not config["api_key"] else "api", "chat_id": bool(config["live_chat_id"]), "top_players": self.top_players(), "top_players_by_window": {str(window): self.top_players(window) for window in (5, 15, 30)}, "votes": self.votes_ranking(), "vote_total": sum(self.votes.values()), "poll": self.poll_status()}

    def _player_names(self):
        names = []
        for lineup in (self.state.get("lineups") or {}).values():
            for player in (lineup or {}).get("starters", []) + (lineup or {}).get("bench", []):
                name = clean_text(player.get("name", ""), 80)
                if len(name) >= 3:
                    names.append(name)
        return names

    def track_mentions(self, text: str):
        now = time.time()
        folded = text.casefold()
        for name in self._player_names():
            aliases = [name.casefold()] + [part for part in re.findall(r"[\wÀ-ÿ]+", name.casefold()) if len(part) >= 3]
            if not any(re.search(r"(?<![\wÀ-ÿ])" + re.escape(alias) + r"(?![\wÀ-ÿ])", folded) for alias in aliases):
                continue
            entry = self.mentions.setdefault(name, {"name": name, "count": 0, "times": deque()})
            if entry["times"] and now - entry["times"][-1] < 2:
                continue
            entry["times"].append(now)
            entry["count"] += 1

    def top_players(self, window_minutes=0):
        now = time.time()
        result = []
        for entry in self.mentions.values():
            if window_minutes:
                while entry["times"] and now - entry["times"][0] > window_minutes * 60:
                    entry["times"].popleft()
            count = len(entry["times"]) if window_minutes else entry["count"]
            if count:
                result.append({"name": entry["name"], "count": count})
        return sorted(result, key=lambda item: (-item["count"], item["name"].casefold()))[:3]

    def make_event(self, text: str, author: str, kind: str = "event"):
        return {
            "id": "youtube:" + str(uuid4()), "minute": self.state.get("minute", 0),
            "icon": "💬", "kind": kind, "text": text, "player": "", "team": "",
            "speak": True, "urgent": False, "source": {"name": "YouTube Live Chat"},
            "author": author, "created_at": datetime.now(timezone.utc).isoformat(),
        }

    def response_for(self, message: str, author: str):
        raw = clean_text(message)
        if not raw.startswith("!"):
            return None
        parts = raw[1:].split(maxsplit=1)
        command = parts[0].casefold() if parts else ""
        argument = parts[1] if len(parts) > 1 else ""
        if command not in COMMANDS:
            return None
        now = time.monotonic()
        if command != "vota" and now - self.last_user.get(author, 0) < 30:
            return None
        if command != "vota":
            self.last_user[author] = now
        if command == "placar":
            h, a = self.state["home"], self.state["away"]
            return f"Placar: {h['name']} {h['score']}, {a['name']} {a['score']}. {self.state.get('status', '')}."
        if command in {"escalação", "escalacao"}:
            return "As escalações e os jogadores em campo estão disponíveis no painel da transmissão."
        if command == "jogador":
            top = ", ".join(f"{item['name']} ({item['count']} menções)" for item in self.top_players()) or "ainda não há menções suficientes"
            return f"Os três jogadores mais comentados são: {top}. Pedido recebido sobre {argument or 'o jogador'}; vou usar apenas dados confirmados."
        if command == "vota":
            poll_option = next((option for option in self.poll.get("options", []) if option.casefold() == argument.casefold()), None)
            if poll_option:
                previous = self.poll_users.get(author)
                if previous == poll_option:
                    return f"Seu voto em {poll_option} já foi registrado."
                if previous:
                    self.poll["votes"][previous] = max(0, self.poll["votes"].get(previous, 1) - 1)
                self.poll_users[author] = poll_option
                self.poll["votes"][poll_option] = self.poll["votes"].get(poll_option, 0) + 1
                return f"Voto registrado na enquete para {poll_option}."
            player = self._find_player(argument)
            if not player:
                return "Votação ignorada: informe um titular ou reserva confirmado nesta partida."
            previous = self.vote_users.get(author)
            if previous == player:
                return f"Seu voto em {player} já foi registrado."
            if previous:
                self.votes[previous] = max(0, self.votes.get(previous, 1) - 1)
            self.vote_users[author] = player
            self.votes[player] = self.votes.get(player, 0) + 1
            return f"Voto registrado para {player}."
        if command == "enquete":
            return "A enquete oficial da partida está disponível no painel da transmissão."
        if command == "pergunta":
            return f"Pergunta recebida: {argument or 'sem texto'}. A resposta será baseada nos dados disponíveis da partida."
        if command == "narrar":
            return "Pedido de narração recebido. Os lances importantes têm prioridade na fila."
        return None

    async def fetch_chat_messages(self):
        config = self.config()
        key, chat_id = config["api_key"], config["live_chat_id"]
        if self.extract_video_id(chat_id) or self.extract_channel_handle(chat_id):
            chat_id, video_id = await self.resolve_chat_reference(key, chat_id)
            self.saved_settings[self.match_key()] = {"api_key": key, "live_chat_id": chat_id, "video_id": video_id}
            if self.settings_path:
                self.settings_path.write_text(json.dumps(self.saved_settings, ensure_ascii=False, indent=2), encoding="utf-8")
        params = {"liveChatId": chat_id, "part": "snippet,authorDetails", "maxResults": 200, "key": key}
        if self.next_page:
            params["pageToken"] = self.next_page
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get("https://www.googleapis.com/youtube/v3/liveChat/messages", params=params)
            response.raise_for_status()
            return response.json()

    @staticmethod
    def _next_unofficial(iterator):
        try:
            return next(iterator)
        except StopIteration:
            return None

    async def unofficial_loop(self):
        try:
            from chat_downloader import ChatDownloader
        except ImportError:
            self.info.update(connected=False, error="Instale a dependência chat-downloader e reinicie o programa.")
            return
        live_url = self.canonical_live_url(self.config()["live_url"])
        try:
            chat = await asyncio.to_thread(ChatDownloader().get_chat, live_url)
            self.info.update(enabled=True, connected=True, error=None)
            while self.configured():
                item = await asyncio.to_thread(self._next_unofficial, chat)
                if not item:
                    break
                message_id = str(item.get("message_id", item.get("id", "")))
                if message_id and message_id in self.seen:
                    continue
                if message_id:
                    self.seen.add(message_id)
                text = clean_text(item.get("message", item.get("message_text", "")))
                author_data = item.get("author") or {}
                author = clean_text(author_data.get("name", "espectador") if isinstance(author_data, dict) else author_data, 80)
                self.track_mentions(text)
                response = self.response_for(text, author)
                self.info["messages"] += 1
                if response:
                    self.state["events"] = ([self.make_event(response, author)] + self.state.get("events", []))[:6]
                self.state["youtube_chat"] = self.status()
                await self.broadcast()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.info.update(connected=False, error=clean_text(exc, 240))
            self.state["youtube_chat"] = self.status()
            await self.broadcast()

    async def loop(self):
        if self.config().get("live_url") and not self.config().get("api_key"):
            await self.unofficial_loop()
            self.info.update(enabled=False, connected=False)
            self.state["youtube_chat"] = self.status()
            return
        self.info.update(enabled=True)
        while self.configured():
            try:
                data = await self.fetch_chat_messages()
                self.next_page = data.get("nextPageToken", self.next_page)
                for item in data.get("items", []):
                    message_id = str(item.get("id", ""))
                    if not message_id or message_id in self.seen:
                        continue
                    self.seen.add(message_id)
                    snippet = item.get("snippet", {})
                    author = clean_text(item.get("authorDetails", {}).get("displayName", "espectador"), 80)
                    text = clean_text(snippet.get("displayMessage", ""))
                    fingerprint = (author + ":" + text).casefold()
                    now = time.time()
                    self.message_fingerprints = {key: stamp for key, stamp in self.message_fingerprints.items() if now - stamp < 30}
                    if fingerprint in self.message_fingerprints:
                        continue
                    self.message_fingerprints[fingerprint] = now
                    self.track_mentions(text)
                    response = self.response_for(text, author)
                    self.info["messages"] += 1
                    if response:
                        self.state["events"] = ([self.make_event(response, author)] + self.state.get("events", []))[:6]
                self.info.update(connected=True, error=None)
                self.state["youtube_chat"] = self.status()
                await self.broadcast()
                await asyncio.sleep(max(2, int(data.get("pollingIntervalMillis", 5000) / 1000)))
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.info.update(connected=False, error=clean_text(exc, 180))
                self.state["youtube_chat"] = self.status()
                await self.broadcast()
                await asyncio.sleep(10)
        self.info.update(enabled=False, connected=False)
        self.state["youtube_chat"] = self.status()

    async def start(self):
        if not self.configured() or self.task and not self.task.done():
            return self.status()
        self.task = asyncio.create_task(self.loop())
        return self.status()

    async def stop(self):
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
            self.task = None
        self.info.update(enabled=False, connected=False)
        self.state["youtube_chat"] = self.status()

    def install(self, app):
        @app.get("/api/youtube/status")
        async def status():
            return self.status()

        @app.post("/api/youtube/config")
        async def config(payload: dict):
            api_key = clean_text(payload.get("api_key"), 300)
            live_chat_id = clean_text(payload.get("live_chat_id"), 500)
            if api_key and (not api_key.startswith("AIza") or len(api_key) < 30):
                return {"error": "O valor informado não parece uma Google API Key. Crie uma chave em Google Cloud > APIs e serviços > Credenciais; ela normalmente começa com AIza.", **self.status()}
            if api_key and len(api_key) < 10:
                return {"error": "A chave do YouTube parece incompleta.", **self.status()}
            if live_chat_id and len(live_chat_id) < 3:
                return {"error": "O liveChatId parece incompleto.", **self.status()}
            video_id = self.extract_video_id(live_chat_id)
            if not api_key:
                if not video_id:
                    return {"error": "No modo sem API, cole o link completo da live do YouTube. Um @canal ou somente o liveChatId precisa da API oficial.", **self.status()}
                self.saved_settings[self.match_key()] = {"api_key": "", "live_chat_id": "", "live_url": live_chat_id, "video_id": video_id}
                if self.settings_path:
                    self.settings_path.write_text(json.dumps(self.saved_settings, ensure_ascii=False, indent=2), encoding="utf-8")
                await self.stop()
                return self.status()
            reference = video_id or self.extract_channel_handle(live_chat_id)
            if reference:
                try:
                    live_chat_id, video_id = await self.resolve_chat_reference(api_key, live_chat_id)
                except (httpx.HTTPError, ValueError) as exc:
                    return {"error": clean_text(exc, 240), **self.status()}
            self.saved_settings[self.match_key()] = {"api_key": api_key, "live_chat_id": live_chat_id, "live_url": "", "video_id": video_id}
            if self.settings_path:
                self.settings_path.write_text(json.dumps(self.saved_settings, ensure_ascii=False, indent=2), encoding="utf-8")
            await self.stop()
            return self.status()

        @app.get("/api/youtube/top-players")
        async def top_players():
            return {"players": self.top_players()}

        @app.post("/api/youtube/reset-votes")
        async def reset_votes():
            self.votes.clear()
            self.vote_users.clear()
            self.state["youtube_chat"] = self.status()
            await self.broadcast()
            return self.status()

        @app.post("/api/youtube/poll")
        async def create_poll(payload: dict):
            question = clean_text(payload.get("question"), 160)
            options = []
            for value in payload.get("options", []):
                option = clean_text(value, 80)
                if option and option.casefold() not in {item.casefold() for item in options}:
                    options.append(option)
            if not question or len(options) < 2 or len(options) > 6:
                return {"error": "Informe uma pergunta e de 2 a 6 opções.", **self.status()}
            self.poll = {"question": question, "options": options, "votes": {option: 0 for option in options}}
            self.state["youtube_chat"] = self.status()
            await self.broadcast()
            return self.status()

        @app.post("/api/youtube/reset-poll")
        async def reset_poll():
            self.poll = {"question": "Quem foi o destaque da partida?", "options": [], "votes": {}}
            self.poll_users.clear()
            self.state["youtube_chat"] = self.status()
            await self.broadcast()
            return self.status()

        @app.post("/api/youtube/start")
        async def start():
            return await self.start()

        @app.post("/api/youtube/stop")
        async def stop():
            await self.stop()
            return self.status()
