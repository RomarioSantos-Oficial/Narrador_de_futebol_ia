"""Free RSS headline discovery for match context; headlines are never live events."""
import asyncio
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
from pathlib import Path
import re
import time
from typing import Literal
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

import httpx
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field


PUBLISHERS = {
    'ge': ('GE', ('ge.globo.com',)),
    'espn': ('ESPN', ('espn.com.br', 'espn.com')),
    'uol': ('UOL', ('uol.com.br',)),
    'official': ('Clubes e entidades', ('cbf.com.br', 'fifa.com', 'premierleague.com', 'uefa.com', 'conmebol.com')),
    'other': ('Outros veículos gratuitos', ('lance.com.br', 'terra.com.br', 'band.uol.com.br', 'cnnbrasil.com.br')),
}
KNOWN_DOMAINS = {domain for _, domains in PUBLISHERS.values() for domain in domains}


class NewsSettingsRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    auto_refresh: bool = False
    include_in_voice: bool = False
    publishers: list[Literal['ge', 'espn', 'uol', 'official', 'other']] = Field(
        default_factory=lambda: ['ge', 'espn', 'uol', 'official', 'other'], min_length=1, max_length=5)


class NewsContext:
    TRUSTED_DOMAINS = KNOWN_DOMAINS
    AUTO_REFRESH_SECONDS = 1800

    def __init__(self, state, broadcast=None, base=None, brain=None):
        self.state = state
        self.broadcast = broadcast
        self.brain = brain
        self.base = Path(base or Path.cwd())
        self.settings_path = self.base / 'news_context.json'
        self.settings = {'auto_refresh': False, 'include_in_voice': False,
                         'publishers': ['ge', 'espn', 'uol', 'official', 'other']}
        self._load_settings()
        self._match_key = None
        self._last_auto = 0.0
        self._fetch_lock = asyncio.Lock()
        self._task = None
        self.state['news_context'] = self._empty_status()

    def _load_settings(self):
        try:
            data = json.loads(self.settings_path.read_text(encoding='utf-8'))
            self.settings.update({key: data[key] for key in ('auto_refresh', 'include_in_voice', 'publishers') if key in data})
            valid = [key for key in self.settings['publishers'] if key in PUBLISHERS]
            self.settings['publishers'] = valid or list(PUBLISHERS)
        except (OSError, ValueError, TypeError):
            pass

    def _empty_status(self):
        return {'configured': True, 'provider': 'rss', **self.settings, 'articles': [], 'facts': [], 'error': None,
                'updated_at': None, 'match_key': None}

    def status(self):
        return self.state.get('news_context', self._empty_status())

    def configured(self):
        """RSS gratuito não depende de chave; a disponibilidade da consulta é separada do status."""
        return True

    @staticmethod
    def clean(value, limit=500):
        return re.sub(r'\s+', ' ', str(value or '')).strip()[:limit]

    @classmethod
    def trust_label(cls, url):
        host = (urlparse(url).hostname or '').removeprefix('www.').casefold()
        return 'alta' if any(host == domain or host.endswith('.' + domain) for domain in cls.TRUSTED_DOMAINS) else 'não verificada'

    def _teams(self):
        return [self.clean(self.state.get(side, {}).get('name'), 100) for side in ('home', 'away')]

    def _player_names(self):
        names = []
        for side in ('home', 'away'):
            players = self.state.get('lineups', {}).get(side, {})
            for player in [*(players.get('starters') or []), *(players.get('bench') or [])]:
                name = self.clean(player.get('name'), 80) if isinstance(player, dict) else ''
                if name and name not in names:
                    names.append(name)
                if len(names) >= 10:
                    return names
        return names

    def _current_match_key(self):
        names = self._teams()
        if any(len(name) < 3 or name in {'Mandante', 'Visitante'} for name in names):
            return None
        return '|'.join([self.clean(self.state.get('competition'), 100), *names])

    def observe(self):
        key = self._current_match_key()
        if key != self._match_key:
            self._match_key = key
            self._last_auto = 0.0
            self.state['news_context'] = {**self._empty_status(), 'match_key': key}
        if (key and self.settings['auto_refresh'] and time.monotonic() - self._last_auto >= self.AUTO_REFRESH_SECONDS
                and (self._task is None or self._task.done())):
            self._last_auto = time.monotonic()
            self._task = asyncio.create_task(self._fetch_automatic())

    async def _fetch_automatic(self):
        try:
            await self.fetch(days=3, automatic=True)
        except HTTPException as exc:
            self.state['news_context'] = {**self.status(), 'error': str(exc.detail)}
            if self.broadcast:
                await self.broadcast()
        except Exception:
            self.state['news_context'] = {**self.status(), 'error': 'A atualização automática de notícias falhou; os dados do jogo continuam ativos.'}
            if self.broadcast:
                await self.broadcast()

    def save_settings(self, payload: NewsSettingsRequest):
        self.base.mkdir(parents=True, exist_ok=True)
        publishers = list(dict.fromkeys(payload.publishers))
        if not publishers:
            raise HTTPException(400, 'Marque ao menos uma fonte de notícias.')
        self.settings = {'auto_refresh': payload.auto_refresh, 'include_in_voice': payload.include_in_voice,
                         'publishers': publishers}
        try:
            temporary = self.settings_path.with_suffix('.tmp')
            temporary.write_text(json.dumps(self.settings, ensure_ascii=False, indent=2), encoding='utf-8')
            temporary.replace(self.settings_path)
        except OSError as exc:
            raise HTTPException(500, 'Não foi possível salvar as preferências de notícias.') from exc
        current = self.status()
        articles = current.get('articles', [])
        self.state['news_context'] = {**current, **self.settings, 'configured': True, 'provider': 'rss',
                                      'facts': self._facts(articles) if payload.include_in_voice else [], 'error': None}
        self.observe()
        return self.status()

    def _domains(self):
        return sorted({domain for publisher in self.settings['publishers'] for domain in PUBLISHERS[publisher][1]})

    def _season_year(self):
        kickoff = str(self.state.get('kickoff') or '')
        try:
            return datetime.fromisoformat(kickoff.replace('Z', '+00:00')).year
        except ValueError:
            return datetime.now(timezone.utc).year

    def _competition_names(self, year):
        names = [self.clean(self.state.get('competition'), 100)]
        for group in (self.state.get('league_table') or {}).get('groups', []):
            competition = self.clean(group.get('name'), 100) if isinstance(group, dict) else ''
            if competition and competition not in names:
                names.append(competition)
        for side in ('home', 'away'):
            for row in (self.state.get('recent_form', {}).get(side) or [])[:5]:
                competition = self.clean(row.get('competition'), 100)
                date = str(row.get('date') or '')
                if competition and date.startswith(str(year)) and competition not in names:
                    names.append(competition)
        return [name for name in names if name]

    @staticmethod
    def _normalize_term(value):
        import unicodedata
        value = unicodedata.normalize('NFKD', str(value or '').casefold())
        value = ''.join(char for char in value if not unicodedata.combining(char))
        return re.sub(r'[^a-z0-9]+', ' ', value).strip()

    def _relevance_terms(self):
        aliases = {
            'flamengo': ['Flamengo', 'rubro negro carioca'],
            'estudiantes de la plata': ['Estudiantes de La Plata', 'Estudiantes', 'Pincha'],
            'fluminense': ['Fluminense', 'Tricolor das Laranjeiras'],
            'palmeiras': ['Palmeiras', 'Verdao'],
            'corinthians': ['Corinthians', 'Timao'],
            'sao paulo': ['Sao Paulo', 'Tricolor Paulista'],
            'gremio': ['Gremio'],
            'internacional': ['Internacional', 'Inter de Porto Alegre'],
            'botafogo': ['Botafogo', 'Fogao'],
        }
        team_terms = []
        for team in self._teams():
            team_terms.append(team)
            team_terms.extend(aliases.get(self._normalize_term(team), []))
        competitions = self._competition_names(self._season_year())
        competition_terms = list(competitions)
        for competition in competitions:
            normalized = self._normalize_term(competition)
            if 'libertadores' in normalized:
                competition_terms.extend(['Libertadores', 'Copa Libertadores', 'CONMEBOL Libertadores'])
            elif 'brasileirao' in normalized or 'serie a' in normalized:
                competition_terms.extend(['Brasileirao', 'Campeonato Brasileiro Serie A'])
        unique = lambda values: list(dict.fromkeys(term for term in values if term))
        return {'times': unique(team_terms), 'jogadores': unique(self._player_names()),
                'competicoes': unique(competition_terms)}

    def _article_categories(self, title):
        normalized = ' ' + self._normalize_term(title) + ' '
        categories = []
        for category, candidates in self._relevance_terms().items():
            if any(' ' + self._normalize_term(term) + ' ' in normalized for term in candidates):
                categories.append(category)
        return categories

    def _search_queries(self, days=3):
        categories = self._relevance_terms()
        sites = ' OR '.join(f'site:{domain}' for domain in self._domains())
        queries = {}
        for category, terms in categories.items():
            quoted = ' OR '.join('"' + term.replace('"', '') + '"' for term in dict.fromkeys(terms) if term)
            if quoted:
                queries[category] = f'({quoted}) ({sites}) when:3d'
        return queries

    @staticmethod
    def _facts(articles):
        def spoken_title(item):
            title = item['title']
            return re.sub(r'^\s*(?:GE|UOL|ESPN|Lance|Terra|Band)\s*[:|·–—-]\s*', '', title, flags=re.IGNORECASE)
        return [{'id': 'news:' + hashlib.sha256(item['url'].encode('utf-8')).hexdigest()[:16],
                 'text': f"Notícia recente: {spoken_title(item)} — publicada em {item['published_at'] or 'data não informada'}.",
                 'source': {'name': item['source'], 'url': item['url']}}
                for item in articles]

    @staticmethod
    def _rss_date(value):
        try:
            parsed = parsedate_to_datetime(value)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).isoformat()
        except (TypeError, ValueError, OverflowError):
            return ''

    async def fetch(self, days=3, automatic=False):
        async with self._fetch_lock:
            # Keep the requested coverage strictly bounded to the previous 72 hours.
            days = 3
            match_key = self._current_match_key()
            if not match_key:
                raise HTTPException(400, 'Carregue uma partida antes de buscar notícias.')
            queries = self._search_queries(days)
            common_params = {'hl': 'pt-BR', 'gl': 'BR', 'ceid': 'BR:pt-419'}
            try:
                async with httpx.AsyncClient(timeout=20, follow_redirects=True, trust_env=False) as client:
                    responses = await asyncio.gather(*(
                        client.get('https://news.google.com/rss/search', params={**common_params, 'q': query},
                                   headers={'User-Agent': 'FutebolLiveOverlay/1.0 RSS reader'})
                        for query in queries.values()), return_exceptions=True)
                roots = []
                for response in responses:
                    if isinstance(response, Exception):
                        continue
                    response.raise_for_status()
                    roots.append(ET.fromstring(response.content))
                if not roots:
                    raise httpx.RequestError('Nenhuma consulta RSS respondeu.')
            except (httpx.HTTPError, ET.ParseError, ValueError) as exc:
                self.state['news_context'] = {**self.status(), 'error': 'Não foi possível consultar os feeds gratuitos. Confira sua conexão e tente novamente.'}
                raise HTTPException(502, self.state['news_context']['error']) from exc

            domains, articles, seen = self._domains(), [], set()
            fresh_after = datetime.now(timezone.utc) - timedelta(days=3)
            fresh_before = datetime.now(timezone.utc) + timedelta(minutes=5)
            items = [item for root in roots for item in root.findall('./channel/item')]
            for item in items:
                title = self.clean(item.findtext('title'), 220)
                url = self.clean(item.findtext('link'), 800)
                source_node = item.find('source')
                source = self.clean(source_node.text if source_node is not None else '', 100)
                source_url = self.clean(source_node.get('url') if source_node is not None else '', 800)
                host = (urlparse(source_url).hostname or '').removeprefix('www.').casefold()
                published_at = self._rss_date(item.findtext('pubDate'))
                if not title or not source or not url.startswith('https://') or not published_at:
                    continue
                published = datetime.fromisoformat(published_at)
                if published < fresh_after or published > fresh_before:
                    continue
                if not source_url or not any(host == domain or host.endswith('.' + domain) for domain in domains):
                    continue
                categories = self._article_categories(title)
                if not categories:
                    continue
                normalized = title.casefold()
                if normalized in seen:
                    continue
                seen.add(normalized)
                articles.append({'title': title, 'url': url, 'source': source, 'publisher_url': source_url,
                                 'trust': self.trust_label(source_url),
                                 'published_at': published_at,
                                 'description': '', 'categories': categories})
            articles.sort(key=lambda item: item['published_at'], reverse=True)
            if match_key != self._current_match_key():
                return self.status()
            facts = self._facts(articles) if self.settings['include_in_voice'] else []
            self._match_key = match_key
            self.state['news_context'] = {'configured': True, 'provider': 'rss', **self.settings, 'days': days,
                                          'updated_at': datetime.now(timezone.utc).isoformat(), 'match_key': match_key,
                                          'articles': articles[:40], 'facts': facts, 'error': None,
                                          'automatic': automatic, 'source_domains': domains,
                                          'player_terms': self._player_names(),
                                          'competition_terms': self._competition_names(self._season_year()),
                                          'season_year': self._season_year(), 'max_age_days': 3,
                                          'search_categories': list(queries)}
            if self.broadcast:
                await self.broadcast()
            return self.status()

    async def start(self):
        self.observe()

    async def stop(self):
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def install(self, app):
        @app.get('/api/context/news')
        async def news():
            return await self.fetch(days=3)

        @app.post('/api/context/script')
        async def script():
            current = self.status()
            if not current.get('include_in_voice'):
                raise HTTPException(400, 'Ative “Incluir manchetes na voz” e salve antes de gerar o roteiro.')
            match_key = self._current_match_key()
            if not match_key or current.get('match_key') != match_key:
                raise HTTPException(409, 'Pesquise novamente as notícias da partida atual antes de gerar o roteiro.')
            articles = current.get('articles') or []
            if not articles:
                raise HTTPException(400, 'Não há notícias recentes para montar o roteiro. Faça a pesquisa primeiro.')
            if not self.brain:
                raise HTTPException(503, 'A integração com a LLM não está disponível neste servidor.')
            facts = self._facts(articles)
            script_articles = [{**article, 'id': fact['id']} for article, fact in zip(articles, facts)]
            # RSS supplies headlines and metadata only; match data is not news evidence.
            context = {'teams': self._teams(), 'competition': self.clean(self.state.get('competition'), 100),
                       'season': self._season_year()}
            segments = await self.brain.news_script(script_articles, context)
            if match_key != self._current_match_key():
                raise HTTPException(409, 'A partida mudou durante a geracao. Pesquise as noticias novamente.')
            script_id = hashlib.sha256((match_key + str(current.get('updated_at')) +
                                         ''.join(item.get('id', '') for item in script_articles)).encode('utf-8')).hexdigest()[:24]
            return {'script_id': script_id, 'match_key': match_key, 'segments': segments,
                    'segment_count': len(segments), 'headline_count': len(articles), 'max_age_days': 3}

        @app.get('/api/context/status')
        async def status():
            return {**self.status(), 'publishers_available': {key: label for key, (label, _) in PUBLISHERS.items()}}

        @app.post('/api/context/settings')
        async def settings(payload: NewsSettingsRequest):
            result = self.save_settings(payload)
            if self.broadcast:
                await self.broadcast()
            return result

        app.add_event_handler('startup', self.start)
        app.add_event_handler('shutdown', self.stop)
