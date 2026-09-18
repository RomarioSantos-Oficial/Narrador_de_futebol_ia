"""A broadcast-only rehearsal view; live provider state remains independent."""
import copy
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from fastapi import HTTPException
from pydantic import BaseModel


def now():
    return datetime.now(timezone.utc).isoformat()


class RehearsalAction(BaseModel):
    action: Literal['start', 'stop', 'kickoff', 'goal', 'yellow', 'red', 'substitution',
                    'review', 'cancel', 'halftime', 'second_half', 'finish', 'disconnect', 'reconnect']
    side: Literal['home', 'away'] = 'home'


class Rehearsal:
    def __init__(self):
        self.demo = None

    def view(self, live):
        if self.demo is None:
            return {**live, 'rehearsal': {'active': False}}
        return {**live, **copy.deepcopy(self.demo),
                'ge': {'enabled': False, 'ready': False, 'status': 'Ensaio: lances fictícios locais.'},
                'feed_health': {'active': not self.demo['rehearsal']['disconnected'], 'interval': 30,
                                'error': 'Falha simulada da fonte.' if self.demo['rehearsal']['disconnected'] else None}}

    def start(self):
        self.demo = {'competition': 'ENSAIO · Liga de demonstração', 'source': 'Ensaio local',
                     'kickoff': now(), 'phase': 'pre', 'status': 'PRÉ-JOGO', 'minute': 0, 'clock_display': '0′',
                     'venue': 'Estádio de demonstração', 'events': [], 'cards': [], 'updated_at': now(),
                     'rehearsal': {'active': True, 'disconnected': False, 'session': str(uuid4())},
                     'lineups': {}, 'recent_form': {}, 'standings': {}, 'league_table': None,
                     'field_action': None, 'data_sources': {}, 'ball': {'x': 50, 'y': 50, 'label': 'Ensaio'},
                     'stats': {key: [0, 0] for key in ['shots', 'shots_on', 'corners', 'yellow', 'red', 'fouls', 'offsides']}}
        self.demo['stats']['possession'] = [50, 50]
        for side, name, prefix in [('home', 'Equipe Verde', 'Verde'), ('away', 'Equipe Azul', 'Azul')]:
            self.demo[side] = {'name': name, 'score': 0, 'abbreviation': prefix[:3].upper(), 'logo': ''}
            players = [{'id': f'{side}-{i}', 'name': f'Jogador {prefix} {i}', 'number': str(i),
                        'position': 'GK' if i == 1 else 'D' if i < 6 else 'M' if i < 9 else 'F',
                        'yellow': 0, 'red': 0} for i in range(1, 17)]
            self.demo['lineups'][side] = {'starters': players[:11], 'bench': players[11:],
                                          'formation': '4-3-3', 'coach': f'Técnico {prefix}'}

    def apply(self, payload):
        action, side = payload.action, payload.side
        if action == 'stop':
            self.demo = None
            return
        if action == 'start':
            self.start()
            return
        if self.demo is None:
            raise HTTPException(409, 'Ative o ensaio primeiro.')
        s = self.demo
        if action in ('disconnect', 'reconnect'):
            s['rehearsal']['disconnected'] = action == 'disconnect'
            if action == 'reconnect':
                s['updated_at'] = now()
            return
        if s['rehearsal']['disconnected']:
            raise HTTPException(409, 'Reconecte a fonte simulada antes de enviar outro lance.')
        if s['phase'] == 'post':
            raise HTTPException(409, 'Este ensaio terminou. Inicie um novo ensaio.')
        s['updated_at'] = now()
        s['minute'] += 1
        player = s['lineups'][side]['starters'][9]
        name, team = player['name'], s[side]['name']
        kind, icon = 'event', '●'
        text = ''
        if action == 'goal':
            s[side]['score'] += 1
            kind, icon, text = 'goal', '⚽', f'Gol de {name}, da {team}.'
        elif action in ('yellow', 'red'):
            color, icon = ('amarelo', '🟨') if action == 'yellow' else ('vermelho', '🟥')
            kind, text = 'card', f'Cartão {color} para {name}, da {team}.'
            player[action] += 1
            s['stats'][action][0 if side == 'home' else 1] += 1
            s['cards'].append({'color': action, 'player': name, 'team': team, 'minute': s['minute']})
        elif action == 'substitution':
            reserve = next((p for p in s['lineups'][side]['bench'] if not p.get('subbed_in')), None)
            outgoing = next((p for p in reversed(s['lineups'][side]['starters']) if not p.get('subbed_out') and not p.get('red')), None)
            if not reserve or not outgoing:
                raise HTTPException(409, 'Não há jogadores disponíveis para outra substituição.')
            reserve['subbed_in'], outgoing['subbed_out'] = True, True
            name = reserve['name']
            kind, icon, text = 'substitution', '↔', f'Substituição na {team}. Sai {outgoing["name"]}, entra {name}.'
        elif action == 'review':
            kind, text = 'review', f'VAR em revisão. O gol da {team} está em análise.'
        elif action == 'cancel':
            if s[side]['score'] <= 0:
                raise HTTPException(409, 'Simule um gol desta equipe antes de anulá-lo.')
            s[side]['score'] -= 1
            kind, text = 'cancelled', f'Gol anulado da {team}, segundo a revisão informada.'
        elif action in ('kickoff', 'second_half'):
            s.update(phase='in', status='AO VIVO', minute=1 if action == 'kickoff' else 46)
            text = 'Início da partida.' if action == 'kickoff' else 'Início do segundo tempo.'
        elif action == 'halftime':
            s.update(phase='in', status='INTERVALO', minute=45)
            text = 'Intervalo da partida.'
        elif action == 'finish':
            s.update(phase='post', status='ENCERRADO', minute=90)
            text = 'Fim do segundo tempo.'
        if action in ('goal', 'yellow', 'red', 'substitution', 'review', 'cancel'):
            s.update(phase='in', status='AO VIVO')
        s['clock_display'] = str(s['minute']) + '′'
        s['events'].insert(0, {'id': 'demo:' + str(uuid4()), 'minute': s['minute'], 'text': text,
                              'kind': kind, 'icon': icon, 'side': side, 'team': team, 'player': name,
                              'source': {'name': 'Ensaio · dados fictícios'}, 'created_at': now()})
        s['events'] = s['events'][:40]

    def install(self, app, broadcast):
        @app.post('/api/rehearsal')
        async def action(payload: RehearsalAction):
            self.apply(payload)
            await broadcast()
            return {'active': self.demo is not None}
