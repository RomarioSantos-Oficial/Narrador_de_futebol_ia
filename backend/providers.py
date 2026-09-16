"""Adapters for optional data providers. Each match keeps a single provider."""
import os
import re
import ssl
from datetime import date, timedelta
from pathlib import Path
from typing import Literal

import httpx
from dotenv import set_key
from fastapi import HTTPException
from pydantic import BaseModel, SecretStr
from backend.leagues import LEAGUE_IDS

SOURCES = {
    "espn": {"name": "ESPN", "interval": 30, "live": True, "note": "Teste gratuito sem chave. Dados sujeitos à cobertura e ao atraso da fonte."},
    "api_football": {"name": "API-Football", "interval": 120, "live": True, "env": "API_FOOTBALL_KEY", "note": "Requer chave. Plano grátis: 100 consultas/dia e temporadas limitadas. Atualiza a cada 2 minutos para economizar consultas."},
    "football_data": {"name": "Football-Data.org", "interval": 60, "live": True, "env": "FOOTBALL_DATA_KEY", "note": "Requer chave. Plano grátis com placares atrasados. Estatísticas e escalações dependem do plano contratado."},
    "thesportsdb": {"name": "TheSportsDB", "interval": 0, "live": False, "note": "Consulta gratuita de agenda, resultados e escudos. Dados limitados. Este acesso gratuito não acompanha jogos ao vivo."},
}
STAT_NAMES = ('possession', 'shots', 'shots_on', 'corners', 'yellow', 'red', 'passes', 'pass_accuracy', 'fouls', 'offsides', 'saves')


class Credentials(BaseModel):
    provider: Literal['api_football', 'football_data']
    key: SecretStr


def install_settings(app, base: Path, leagues):
    @app.get('/api/sources')
    async def sources():
        return {key: {**{k: v for k, v in info.items() if k != 'env'},
                      'configured': bool(os.getenv(info['env'], '').strip()) if 'env' in info else True,
                      'needs_key': 'env' in info,
                      'leagues': {code: name for code, name in leagues.items() if key == 'espn' or code in LEAGUE_IDS[key]}}
                for key, info in SOURCES.items()}

    @app.post('/api/sources/key')
    async def credentials(payload: Credentials):
        value = re.sub(r'\s+', '', payload.key.get_secret_value())
        if not re.fullmatch(r'[A-Za-z0-9_-]{8,256}', value):
            raise HTTPException(400, 'Confira a chave de acesso copiada do provedor.')
        name = SOURCES[payload.provider]['env']
        try:
            set_key(str(base / '.env'), name, value)
        except OSError as exc:
            raise HTTPException(500, 'Não foi possível salvar a chave na pasta do programa.') from exc
        os.environ[name] = value
        return {'configured': True}


async def request(provider, path, **params):
    info = SOURCES[provider]
    headers = {}
    if info.get('env'):
        key = os.getenv(info['env'], '').strip()
        if not key:
            raise HTTPException(400, f"Configure a chave de {info['name']} no painel primeiro.")
        headers['x-apisports-key' if provider == 'api_football' else 'X-Auth-Token'] = key
    base = {'api_football': 'https://v3.football.api-sports.io',
            'football_data': 'https://api.football-data.org/v4',
            'thesportsdb': 'https://www.thesportsdb.com/api/v1/json/123'}[provider]
    try:
        async with httpx.AsyncClient(timeout=20, verify=ssl.create_default_context()) as client:
            response = await client.get(f'{base}/{path}', headers=headers, params=params)
            if response.status_code in (401, 403):
                raise HTTPException(403, f"{info['name']}: chave inválida ou dados não liberados pelo plano.")
            if response.status_code == 429:
                raise HTTPException(429, f"{info['name']}: limite de consultas atingido. Aguarde antes de tentar novamente.")
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(502, f"Não foi possível consultar {info['name']}. Tente novamente.") from exc
    if data.get('errors'):
        # Provider error bodies can contain account details; do not echo them.
        raise HTTPException(403, f"{info['name']} recusou a consulta. Confira chave, cota e acesso à temporada no seu plano.")
    return data


def number(value):
    try:
        return float(str(value).rstrip('%')) if value is not None else None
    except (TypeError, ValueError):
        return None


def blank(source):
    return {'source': SOURCES[source]['name'], 'competition': '', 'minute': 0, 'clock_display': '—',
            'recent_form': {'home': [], 'away': []}, 'standings': {'home': None, 'away': None}, 'field_action': None, 'league_table': None,
            'status': 'PRÉ-JOGO', 'phase': 'pre', 'venue': '',
            'stats': {key: [None, None] for key in STAT_NAMES}, 'events': [], 'cards': [],
            'lineups': {side: {'starters': [], 'bench': [], 'formation': ''} for side in ('home', 'away')},
            'ball': {'x': 50, 'y': 50, 'label': 'Posição da bola não fornecida pela fonte'}}


def phase(status):
    if status in ('FT', 'AET', 'PEN', 'FINISHED', 'Match Finished'):
        return 'post', 'ENCERRADO'
    if status in ('HT', 'PAUSED', 'Halftime'):
        return 'in', 'INTERVALO'
    if status in ('1H', '2H', 'ET', 'BT', 'P', 'IN_PLAY', 'LIVE'):
        return 'in', 'AO VIVO'
    return 'pre', {'PST': 'ADIADO', 'POSTPONED': 'ADIADO', 'CANC': 'CANCELADO', 'CANCELLED': 'CANCELADO', 'SUSP': 'SUSPENSO', 'SUSPENDED': 'SUSPENSO'}.get(status, 'PRÉ-JOGO')


def team(name, score=None, logo='', abbreviation=''):
    return {'name': name or 'Time', 'score': int(number(score) or 0),
            'logo': logo or '', 'abbreviation': abbreviation or (name or 'Time')[:3].upper()}


def player(info):
    return {'id': str(info.get('id', '')), 'name': info.get('name', 'Jogador'),
            'number': info.get('number', info.get('shirtNumber', '')), 'position': info.get('pos', info.get('position', '')) or '',
            'yellow': 0, 'red': 0, 'subbed_in': False, 'subbed_out': False}


def add_card(result, minute, person, team_info, red):
    color = 'red' if red else 'yellow'
    name = person.get('name') or 'Jogador não informado'
    result['cards'].append({'minute': minute, 'player': name, 'player_id': str(person.get('id', '')),
                            'team': team_info.get('name', ''), 'color': color})
    result['events'].append({'minute': minute, 'icon': '🟥' if red else '🟨',
                             'text_en': ('Red card' if red else 'Yellow card') + ' · ' + name,
                             'text': f"Cartão {'vermelho' if red else 'amarelo'} · {name} ({team_info.get('name', '')})"})
    for lineup in result['lineups'].values():
        for row in lineup['starters'] + lineup['bench']:
            if person.get('id') is not None and row['id'] == str(person['id']):
                row[color] += 1


def normalize_api_football(row):
    out = blank('api_football')
    fx = row['fixture']
    out.update(competition=row['league']['name'], venue=(fx.get('venue') or {}).get('name') or '', kickoff=fx.get('date', ''))
    out['phase'], out['status'] = phase(fx['status']['short'])
    out['minute'] = fx['status'].get('elapsed') or 0
    extra = fx['status'].get('extra')
    out['clock_display'] = str(out['minute']) + (f'+{extra}' if extra else '') + "′"
    for side in ('home', 'away'):
        info = row['teams'][side]
        out[side] = team(info['name'], row.get('goals', {}).get(side), info.get('logo'))
    mapping = {'Ball Possession': 'possession', 'Total Shots': 'shots', 'Shots on Goal': 'shots_on', 'Corner Kicks': 'corners',
               'Yellow Cards': 'yellow', 'Red Cards': 'red', 'Total passes': 'passes', 'Passes %': 'pass_accuracy',
               'Fouls': 'fouls', 'Offsides': 'offsides', 'Goalkeeper Saves': 'saves'}
    for group in row.get('statistics', []) or []:
        side = next((i for i, s in enumerate(('home', 'away')) if str(group['team']['id']) == str(row['teams'][s]['id'])), None)
        if side is not None:
            for item in group.get('statistics', []):
                if item.get('type') in mapping:
                    out['stats'][mapping[item['type']]][side] = number(item.get('value'))
    for group in row.get('lineups', []) or []:
        side = next((s for s in ('home', 'away') if str(group['team']['id']) == str(row['teams'][s]['id'])), None)
        if side:
            out['lineups'][side] = {'formation': group.get('formation') or '',
                                    'starters': [player(p['player']) for p in group.get('startXI', [])],
                                    'bench': [player(p['player']) for p in group.get('substitutes', [])]}
    for event in row.get('events', []) or []:
        minute = event.get('time', {}).get('elapsed', '—')
        if event.get('type') == 'Card':
            add_card(out, minute, event.get('player') or {}, event.get('team') or {}, 'Red' in event.get('detail', ''))
        elif event.get('type') == 'Goal':
            detail = event.get('detail', '')
            out['events'].append({'minute': minute, 'icon': '⚽', 'text': ('Pênalti perdido' if detail == 'Missed Penalty' else 'Gol') + ' · ' + (event.get('player', {}).get('name') or 'Jogador não informado')})
    out['events'] = out['events'][-6:][::-1]
    return out, out['phase'] == 'post'


def normalize_football_data(row):
    out = blank('football_data')
    out.update(competition=row['competition']['name'], venue=row.get('venue') or '', kickoff=row.get('utcDate', ''))
    out['phase'], out['status'] = phase(row['status'])
    out['minute'] = row.get('minute') or 0
    out['clock_display'] = str(row['minute'])+'′' if row.get('minute') is not None else '—'
    mapping = {'ball_possession': 'possession', 'shots': 'shots', 'shots_on_goal': 'shots_on', 'corner_kicks': 'corners',
               'yellow_cards': 'yellow', 'red_cards': 'red', 'fouls': 'fouls', 'offsides': 'offsides', 'saves': 'saves'}
    for i, side in enumerate(('home', 'away')):
        info = row[side+'Team']
        out[side] = team(info['name'], row.get('score', {}).get('fullTime', {}).get(side), info.get('crest'), info.get('tla'))
        out['lineups'][side] = {'formation': info.get('formation') or '',
                                'starters': [player(p) for p in info.get('lineup', []) or []],
                                'bench': [player(p) for p in info.get('bench', []) or []]}
        for key, value in (info.get('statistics') or {}).items():
            if key in mapping:
                out['stats'][mapping[key]][i] = number(value)
    for event in row.get('bookings', []) or []:
        add_card(out, event.get('minute', '—'), event.get('player') or {}, event.get('team') or {}, 'RED' in event.get('card', ''))
    for event in row.get('goals', []) or []:
        out['events'].append({'minute': event.get('minute', '—'), 'icon': '⚽', 'text': 'Gol · ' + ((event.get('scorer') or {}).get('name') or 'Jogador não informado')})
    out['events'].sort(key=lambda e: int(e['minute']) if str(e['minute']).isdigit() else -1, reverse=True)
    out['events'] = out['events'][:6]
    return out, out['phase'] == 'post'


def normalize_sportsdb(row):
    out = blank('thesportsdb')
    out.update(competition=row.get('strLeague', ''), venue=row.get('strVenue') or '', kickoff=(row.get('strTimestamp') or row.get('dateEvent', '')+'T00:00:00').rstrip('Z')+'Z')
    out['phase'], out['status'] = phase(row.get('strStatus', ''))
    for side in ('home', 'away'):
        title = side.title()
        out[side] = team(row.get(f'str{title}Team'), row.get(f'int{title}Score'), row.get(f'str{title}TeamBadge'))
    return out, True  # The free v1 endpoint is a lookup, not a live feed.


async def games(provider, league, day=None, live=False):
    if league not in LEAGUE_IDS[provider]:
        raise HTTPException(400, 'Campeonato indisponível nesta fonte.')
    code = LEAGUE_IDS[provider][league]
    day = day or date.today()
    if provider == 'api_football':
        params = {'live': code} if live else {'date': day.isoformat()}
        rows = (await request(provider, 'fixtures', **params)).get('response', [])
        rows = [r for r in rows if str(r['league']['id']) == code]
        return [{'id': str(r['fixture']['id']), 'name': r['teams']['home']['name']+' × '+r['teams']['away']['name'],
                 'date': r['fixture']['date'], 'status': phase(r['fixture']['status']['short'])[1],
                 'clock': str(r['fixture']['status'].get('elapsed') or '')} for r in rows]
    if provider == 'football_data':
        # v4 excludes dateTo. Using the same date for both ends yields an empty day.
        params = {'competitions': code, 'status': 'LIVE'} if live else {'competitions': code, 'dateFrom': day.isoformat(), 'dateTo': (day + timedelta(days=1)).isoformat()}
        rows = (await request(provider, 'matches', **params)).get('matches', [])
        return [{'id': str(r['id']), 'name': r['homeTeam']['name']+' × '+r['awayTeam']['name'],
                 'date': r['utcDate'], 'status': phase(r['status'])[1], 'clock': str(r.get('minute') or '')} for r in rows]
    if live:
        raise HTTPException(400, 'TheSportsDB gratuito não fornece busca ao vivo. Use a busca por data ou escolha ESPN.')
    rows = (await request(provider, 'eventsday.php', d=day.isoformat(), l=code)).get('events') or []
    return [{'id': str(r['idEvent']), 'name': r['strHomeTeam']+' × '+r['strAwayTeam'],
             'date': r['dateEvent']+'T'+(r.get('strTime') or '00:00:00').rstrip('Z')+'Z',
             'status': phase(r.get('strStatus', ''))[1], 'clock': ''} for r in rows]


async def match(provider, event):
    if provider == 'api_football':
        # The IDs endpoint includes events, lineups and stats in one request.
        rows = (await request(provider, 'fixtures', ids=event)).get('response') or []
        if rows:
            return normalize_api_football(rows[0])
    elif provider == 'football_data':
        return normalize_football_data(await request(provider, f'matches/{event}'))
    else:
        rows = (await request(provider, 'lookupevent.php', id=event)).get('events') or []
        if rows:
            return normalize_sportsdb(rows[0])
    raise HTTPException(404, 'Partida não encontrada ou não liberada pelo plano desta fonte.')
