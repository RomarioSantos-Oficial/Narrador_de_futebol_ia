"""Optional support data; never supplies the score, clock or live incidents."""
import asyncio
import copy
import re
import ssl
import time
from urllib.parse import urlsplit

import httpx
from backend.comparison import same_match, normalized_name
from backend.player_profiles import identity
from backend.coaches import normalize_coach


def missing(state):
    if state.get('source') == 'manual' or not state.get('kickoff'):
        return False
    for side in ('home', 'away'):
        lineup = state.get('lineups', {}).get(side) or {}
        if not state.get('coaches', {}).get(side) and not (state.get('ge', {}).get('coaches') or {}).get(side):
            return True
        if state.get('phase') == 'pre' and len(lineup.get('starters', [])) != 11:
            return True
        if any(not p.get('photo') for p in lineup.get('starters', []) + lineup.get('bench', [])):
            return True
    return False


def apply_support(state, payload):
    """Only merge confirmed data for this exact fixture. Primary fields win."""
    match = payload.get('match') or {}
    if not same_match(state, match.get('home', ''), match.get('away', ''), match.get('time', '')):
        return False
    used = False
    sheet = match.get('lineups') or {}
    for side in ('home', 'away'):
        coach = sheet.get(side + '_coach')
        if isinstance(coach, str):
            coach = {'name': coach}
        coach = normalize_coach(coach, 'SportScore')
        current = state.setdefault('coaches', {}).get(side)
        ge_coach = (state.get('ge', {}).get('coaches') or {}).get(side) if state.get('ge', {}).get('ready') else None
        if coach and not current and not ge_coach:
            state['coaches'][side] = coach
            used = True
        elif coach and current and not current.get('photo') and coach.get('photo') and normalized_name(current['name']) == normalized_name(coach['name']):
            current['photo'] = coach['photo']
            used = True
        current_lineup = state.setdefault('lineups', {}).setdefault(side, {})
        xi, subs = sheet.get(side + '_xi') or [], sheet.get(side + '_subs') or []
        if (state.get('phase') == 'pre' and match.get('status') == 'upcoming'
                and sheet.get('confirmed') is True and len(xi) == 11
                and len(current_lineup.get('starters', [])) != 11):
            def player(row):
                return {'id': 'sportscore:' + side + ':' + str(row.get('number', '')) + ':' + row['name'],
                        'name': row['name'], 'number': row.get('number'), 'position': row.get('position') or '',
                        'photo': row.get('photo') or '', 'captain': row.get('captain') is True,
                        'subbed_in': False, 'subbed_out': False}
            if all(isinstance(p.get('name'), str) and p['name'] for p in xi + subs):
                state['lineups'][side] = {'starters': [player(p) for p in xi], 'bench': [player(p) for p in subs],
                    'formation': sheet.get(side + '_formation') or '', 'source': 'SportScore'}
                used = True
        else:
            # Photos require an unambiguous name and jersey match on the same team.
            for p in current_lineup.get('starters', []) + current_lineup.get('bench', []):
                candidates = [q for q in xi + subs if normalized_name(q.get('name') or '') == normalized_name(p.get('name') or '')
                              and str(q.get('number')) == str(p.get('number'))]
                if not p.get('photo') and len(candidates) == 1:
                    photo = normalize_coach({'name': 'photo', 'photo': candidates[0].get('photo')}, 'SportScore')
                    if photo and photo.get('photo'):
                        p['photo'] = photo['photo']
                        used = True
    if used:
        state['support_sources'] = ['SportScore']
    return used


class SupportFeed:
    def __init__(self, state, broadcast):
        self.state, self.broadcast = state, broadcast
        self.key, self.task, self.payload = None, None, None
        self.checked = 0

    def observe(self):
        key = identity(self.state)
        if key != self.key:
            if self.task and not self.task.done():
                self.task.cancel()
            self.key, self.payload, self.checked = key, None, 0
            self.state['support_sources'] = []
            self.state['support_status'] = ''
        if self.payload:
            apply_support(self.state, self.payload)
        if missing(self.state) and (not self.task or self.task.done()) and time.monotonic() - self.checked >= 300:
            self.checked = time.monotonic()
            self.task = asyncio.create_task(self.run(copy.deepcopy(self.state), key))

    async def run(self, snapshot, key):
        try:
            async with httpx.AsyncClient(timeout=15, verify=ssl.create_default_context()) as client:
                async def get(path, **params):
                    r = await client.get('https://sportscore.com' + path, params={'sport': 'football', **params})
                    r.raise_for_status()
                    return r.json()
                name = snapshot['home'].get('source_name') or snapshot['home']['name']
                slug = normalized_name(name).replace(' ', '-')
                schedule = await get('/api/widget/team/', slug=slug, limit=30)
                rows = [m for m in schedule.get('matches', []) if same_match(snapshot, m.get('home', ''), m.get('away', ''), m.get('time', ''))]
                if len(rows) != 1:
                    return
                path = urlsplit(rows[0].get('url', '')).path
                match_slug = re.fullmatch(r'/football/match/([a-z0-9-]+)/?', path)
                if not match_slug:
                    return
                payload = await get('/api/widget/match/', slug=match_slug[1])
            if identity(self.state) != key:
                return
            self.payload = payload
            used = apply_support(self.state, payload)
            self.state['support_status'] = ('SportScore: informações ausentes complementadas.' if used else
                                           'SportScore consultado; sem informações adicionais disponíveis.')
            await self.broadcast()
        except asyncio.CancelledError:
            raise
        except (httpx.HTTPError, ValueError, TypeError, KeyError):
            if identity(self.state) == key:
                self.state['support_status'] = 'Apoio indisponível; dados principais mantidos.'

    def install(self, app):
        @app.on_event('shutdown')
        async def stop():
            if self.task and not self.task.done():
                self.task.cancel()
                try:
                    await self.task
                except asyncio.CancelledError:
                    pass
