"""Optional player biographies; never replace match or lineup data."""
import asyncio
import copy
import time
from urllib.parse import urlsplit

from backend.comparison import normalized_name
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
        name = normalized_name(value or '')
        return {'brasil': 'brazil'}.get(name, name)

    candidates = []
    for row in rows or []:
        names = [row.get('strPlayer'), *(row.get('strPlayerAlternate') or '').split(';')]
        if row.get('strSport') != 'Soccer' or norm(player['name']) not in [norm(n) for n in names if n]:
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


class PlayerProfiles:
    def __init__(self, state, broadcast):
        self.state, self.broadcast = state, broadcast
        self.cache = {}
        self.task = None
        self.last_request = 0

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
                        # Public API permits 30 calls/minute; serialize all lookups.
                        await asyncio.sleep(max(0, 2.1 - (time.monotonic() - self.last_request)))
                        self.last_request = time.monotonic()
                        try:
                            data = await request('thesportsdb', 'searchplayers.php', p=player['name'])
                            profile = select_profile(data.get('player'), player, team)
                            self.cache[cache_key] = (time.monotonic(), profile)
                        except Exception:
                            failed = True
                            break
                    if identity(self.state) != match:
                        return
                    if profile:
                        self.state['player_profiles'][key] = profile
                    count = len(self.state['player_profiles'])
                    self.state['profile_status'] = f'Consultando jogadores · {count} perfis encontrados.'
                    await self.broadcast()
                if failed:
                    break
            if identity(self.state) == match:
                count = len(self.state['player_profiles'])
                self.state['profile_status'] = (f'{count} perfis encontrados. ' +
                    ('Fonte indisponível; tente novamente mais tarde.' if failed else
                     'Jogadores sem correspondência confirmada usam um ícone neutro.'))
                await self.broadcast()
        finally:
            if identity(self.state) != match:
                self.state['player_profiles'] = {}
                self.state['profile_status'] = 'Partida alterada. Busque os perfis desta partida.'
                await self.broadcast()

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
