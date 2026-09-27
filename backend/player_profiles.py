"""Optional player biographies; never replace match or lineup data."""
import asyncio
import copy
import time
import re
import ssl
import httpx
from urllib.parse import urlsplit

from backend.comparison import normalized_name
from backend.team_names import canonical_name
from backend.providers import request


def identity(state):
    return (state.get('source'), state.get('kickoff'),
            state.get('home', {}).get('name'), state.get('away', {}).get('name'))


def player_key(state, player):
    return '|'.join(str(v or '') for v in (state.get('source'), player.get('id'), player.get('name')))


def safe_photo(value):
    try:
        parsed = urlsplit(value or '')
        return value if parsed.scheme == 'https' and parsed.hostname and not parsed.username and not parsed.password else ''
    except ValueError:
        return ''


def select_profile(rows, player, team):
    """Require exact name and team/nationality, and reject ambiguous matches."""
    def norm(value):
        return canonical_name(value)

    candidates = []
    for row in rows or []:
        names = [row.get('strPlayer'), *(row.get('strPlayerAlternate') or '').split(';')]
        expected = {norm(n) for n in (player.get('name'), player.get('full_name')) if n}
        if row.get('strSport') != 'Soccer' or not expected.intersection(norm(n) for n in names if n):
            continue
        if norm(team) not in {norm(row.get('strTeam')), norm(row.get('strNationality'))}:
            continue
        candidates.append(row)
    if len(candidates) != 1:
        return None
    row = candidates[0]
    return {'photo': safe_photo(row.get('strCutout')) or safe_photo(row.get('strThumb')),
            'nationality': row.get('strNationality') or '', 'birth_date': row.get('dateBorn') or '',
            'height': row.get('strHeight') or '', 'weight': row.get('strWeight') or '',
            'club': row.get('strTeam') or '', 'source': 'TheSportsDB'}


async def espn_profile(player):
    identifier = str(player.get('id') or '')
    if not re.fullmatch(r'\d{1,15}', identifier):
        return {}
    async with httpx.AsyncClient(timeout=15, verify=ssl.create_default_context()) as client:
        response = await client.get('https://site.web.api.espn.com/apis/common/v3/sports/soccer/all/athletes/' + identifier)
        response.raise_for_status()
        athlete = response.json().get('athlete') or {}
    if str(athlete.get('id')) != identifier:
        return {}
    names = {normalized_name(athlete.get(k) or '') for k in ('displayName', 'fullName')}
    if normalized_name(player['name']) not in names:
        return {}
    headshot = athlete.get('headshot') or {}
    return {'photo': safe_photo(headshot.get('href') if isinstance(headshot, dict) else headshot),
            'full_name': athlete.get('fullName') or '',
            'nationality': athlete.get('citizenship') or '', 'birth_date': athlete.get('displayDOB') or '',
            'height': athlete.get('displayHeight') or '', 'weight': athlete.get('displayWeight') or '',
            'club': (athlete.get('team') or {}).get('displayName') or '', 'source': 'ESPN'}


class PlayerProfiles:
    def __init__(self, state, broadcast):
        self.state, self.broadcast = state, broadcast
        self.cache = {}
        self.task = None
        self.last_request = 0
        self.observed_match = None
        self.observed_roster = None

    def observe(self):
        match = identity(self.state)
        if match != self.observed_match:
            if self.task and not self.task.done():
                self.task.cancel()
            self.observed_match, self.observed_roster = match, None
            self.state['player_profiles'] = {}
        roster = tuple(sorted(player_key(self.state, p)
                       for lineup in self.state.get('lineups', {}).values()
                       for p in [*lineup.get('starters', []), *lineup.get('bench', [])]))
        if not roster or self.state.get('source') == 'manual':
            return
        if roster != self.observed_roster and (not self.task or self.task.done()):
            self.observed_roster = roster
            self.task = asyncio.create_task(self.run(copy.deepcopy(self.state)))

    async def run(self, snapshot):
        match = identity(snapshot)
        self.state['player_profiles'] = {}
        self.state['profile_status'] = 'Buscando fotos e informações…'
        await self.broadcast()
        failed = False
        try:
            for side in ('home', 'away'):
                lineup = snapshot.get('lineups', {}).get(side, {})
                for player in [*lineup.get('starters', []), *lineup.get('bench', [])][:40]:
                    if identity(self.state) != match:
                        return
                    team = snapshot[side]['name']
                    key = player_key(snapshot, player)
                    cache_key = (key, team)
                    cached = self.cache.get(cache_key)
                    if cached and time.monotonic() - cached[0] < 86400:
                        profile = cached[1]
                    else:
                        profile = {}
                        if str(snapshot.get('source', '')).startswith('ESPN'):
                            try:
                                profile = await espn_profile(player)
                            except (httpx.HTTPError, ValueError, TypeError):
                                pass
                        lookup_player = {**player, 'full_name': profile.get('full_name') or player.get('full_name')}
                        try:
                            queries = list(dict.fromkeys(n for n in (player['name'], lookup_player.get('full_name')) if n))
                            if failed:
                                queries = []  # Continue ESPN when the complementary source is unavailable.
                            for query in queries:
                                # Public API permits 30 calls/minute; serialize lookups.
                                await asyncio.sleep(max(0, 2.1 - (time.monotonic() - self.last_request)))
                                self.last_request = time.monotonic()
                                if identity(self.state) != match:
                                    return
                                data = await request('thesportsdb', 'searchplayers.php', p=query)
                                extra = select_profile(data.get('player'), lookup_player, team)
                                if extra:
                                    sources = [profile.get('source'), extra['source']]
                                    profile = {**profile, **{k: v for k, v in extra.items() if v}}
                                    profile['source'] = ' + '.join(dict.fromkeys(s for s in sources if s))
                                    if profile.get('photo'):
                                        break
                            self.cache[cache_key] = (time.monotonic(), profile)
                        except Exception:
                            failed = True
                            # Preserve verified ESPN details even if the photo source fails.
                            if profile:
                                self.cache[cache_key] = (time.monotonic(), profile)
                    if identity(self.state) != match:
                        return
                    if profile:
                        self.state['player_profiles'][key] = profile
                    count = len(self.state['player_profiles'])
                    self.state['profile_status'] = f'Consultando jogadores · {count} perfis encontrados.'
                    await self.broadcast()
            if identity(self.state) == match:
                count = len(self.state['player_profiles'])
                self.state['profile_status'] = (f'{count} perfis encontrados. ' +
                    ('Fonte indisponível; tente novamente mais tarde.' if failed else
                     'Jogadores sem correspondência confirmada usam um ícone neutro.'))
                await self.broadcast()
        finally:
            pass  # A superseded task must not clear the new match's profiles.

    def install(self, app):
        @app.post('/api/players/profiles')
        async def start():
            if not self.task or self.task.done():
                self.task = asyncio.create_task(self.run(copy.deepcopy(self.state)))
            return {'status': 'Busca iniciada. As fotos aparecem conforme forem encontradas.'}

        @app.on_event('shutdown')
        async def stop():
            if self.task and not self.task.done():
                self.task.cancel()
                try:
                    await self.task
                except asyncio.CancelledError:
                    pass
