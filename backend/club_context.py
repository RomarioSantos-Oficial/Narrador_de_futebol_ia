"""Small, attributed club facts from the free catalogue; no generated club history."""
import asyncio
import copy
from datetime import datetime, timezone
import hashlib
import re
import time

from backend.comparison import normalized_name
from fastapi import HTTPException
from backend import providers
COUNTRIES = {'England': 'Inglaterra', 'Scotland': 'Escócia', 'Wales': 'País de Gales', 'Northern Ireland': 'Irlanda do Norte',
             'Brazil': 'Brasil', 'Portugal': 'Portugal', 'France': 'França', 'Germany': 'Alemanha', 'Spain': 'Espanha',
             'Italy': 'Itália', 'Argentina': 'Argentina', 'Uruguay': 'Uruguai', 'Colombia': 'Colômbia', 'Egypt': 'Egito',
             'Netherlands': 'Países Baixos', 'Sweden': 'Suécia', 'Denmark': 'Dinamarca', 'Norway': 'Noruega',
             'Belgium': 'Bélgica', 'Japan': 'Japão', 'South Korea': 'Coreia do Sul', 'United States': 'Estados Unidos',
             'Mexico': 'México', 'Ecuador': 'Equador', 'Senegal': 'Senegal', 'Nigeria': 'Nigéria', 'Ghana': 'Gana',
             'Cameroon': 'Camarões', 'Ireland': 'Irlanda', 'Poland': 'Polônia', 'Serbia': 'Sérvia', 'Croatia': 'Croácia',
             'Austria': 'Áustria', 'Switzerland': 'Suíça', 'Australia': 'Austrália'}
MONTHS = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro']

# Historical notes verified on club-owned pages. Applied only after the catalogue identifies the club.
CLUB_NOTES = {
    '133602': [
        ('kop', 'Uma curiosidade da torcida do Liverpool: a arquibancada que ficou conhecida como Kop foi inaugurada em 1906. Seu nome tem ligação com a batalha de Spion Kop.',
         'Liverpool FC', 'https://www.liverpoolfc.com/news/125-years-story-spion-kop'),
        ('flags', 'Na tradição da torcida do Liverpool, o grupo Spion Kop 1906 organiza bandeiras e faixas na Kop antes das partidas.',
         'Liverpool FC', 'https://www.liverpoolfc.com/news/story-behind-special-new-banner-kop'),
    ],
    '133600': [
        ('cottage', 'Um capítulo da história do Fulham: o clube passou a jogar em Craven Cottage em 1896, depois de dois anos de preparação do local.',
         'Fulham FC', 'https://www.fulhamfc.com/club/history/history-of-fulham-football-club'),
    ],
}


def stadium_facts(row):
    if not row or not str(row.get('idVenue', '')).isdigit():
        return []
    name, year = row.get('strVenue', ''), str(row.get('intFormedYear') or '')
    if not name or not year.isdigit() or not 1700 <= int(year) <= datetime.now(timezone.utc).year:
        return []
    return [{'id': 'venue:' + str(row['idVenue']),
             'text': f'História dos estádios: {name} tem {year} como ano de fundação informado no cadastro do TheSportsDB.',
             'source': {'name': 'TheSportsDB', 'url': 'https://www.thesportsdb.com/venue/' + str(row['idVenue'])}}]


def format_player_profile(player_name, birthday_text, nationality, number=None, position=''):
    intro = f'Olho no lance com {player_name}!'
    role_label = ''
    if position:
        normalized = str(position).upper().replace('-', '').replace('_', '')
        role_map = {
            'GK': 'como goleiro', 'G': 'como goleiro', 'Goalkeeper': 'como goleiro',
            'DF': 'na defesa', 'D': 'na defesa', 'LB': 'na lateral esquerda', 'RB': 'na lateral direita',
            'MF': 'no meio de campo', 'M': 'no meio de campo', 'CM': 'no meio de campo', 'DM': 'no meio de campo',
            'AM': 'no setor criativo', 'FW': 'na frente', 'F': 'na frente', 'ST': 'na frente', 'LW': 'na ponta esquerda', 'RW': 'na ponta direita',
            'CF': 'como centroavante', 'CB': 'na zaga', 'CD': 'na zaga'
        }
        role_label = role_map.get(normalized, '').strip()
    chunks = []
    if birthday_text:
        chunks.append(f'Nascido em {birthday_text}')
    if nationality:
        chunks.append(f'na {nationality}')
    if number:
        chunks.append(f'o camisa {number}')
    if role_label:
        chunks.append(role_label)
    variants = {
        'como goleiro': [
            'traz segurança, leitura de jogo e coragem para sair jogando. É o ponto de equilíbrio do time.',
            'tem organização defensiva, calma na saída e boa leitura de jogadas. Ajuda a dar segurança ao bloco.',
            'acompanha a linha, fecha espaços e distribui a bola com calma na saída.'
        ],
        'na defesa': [
            'tem presença, leitura de jogo e firmeza na marcação. Dá estabilidade para a linha defensiva.',
            'faz bons cortes, antecipa os movimentos e organiza a saída de bola com inteligência.',
            'ajuda a segurar o bloco, marcar e ligar a defesa com o meio.'
        ],
        'na frente': [
            'tem presença ofensiva, mobilidade e capacidade de criar perigo na área. Gera ameaça constante.',
            'faz a diferença em avanço, mobilidade e chegada no último passe. Sempre entra em zonas importantes.',
            'aproveita bem os espaços, aparece na área e tenta desequilibrar a defesa.'
        ],
        'no meio de campo': [
            'controla o ritmo, liga a defesa ao ataque e aparece em zonas importantes.',
            'tem visão de jogo, toque e presença para ordenar o time em diferentes fases da partida.',
            'ajuda a controlar o jogo e a levar a bola para frente com inteligência.'
        ],
    }
    variant = (variants.get(role_label) or [
        'traz categoria, visão de jogo e presença no setor. É bola no pé e qualidade pura!',
        'tem leitura de jogo, entrega e presença no setor. Ajuda a construir e resolve bem a saída de bola.',
        'sabe controlar a fase, procurar espaço e dar opção. Tem qualidade no toque e presença decorativa no setor.',
        'influencia o jogo com inteligência e presença. Ajuda a ligar o time e a criar perigo com calma.'
    ])[int(hashlib.md5(player_name.encode('utf-8')).hexdigest(), 16) % len((variants.get(role_label) or [
        'traz categoria, visão de jogo e presença no setor. É bola no pé e qualidade pura!',
        'tem leitura de jogo, entrega e presença no setor. Ajuda a construir e resolve bem a saída de bola.',
        'sabe controlar a fase, procurar espaço e dar opção. Tem qualidade no toque e presença decorativa no setor.',
        'influencia o jogo com inteligência e presença. Ajuda a ligar o time e a criar perigo com calma.'
    ]))]
    if not chunks:
        return f'{intro} Uma peça importante no time, com qualidade, leitura de jogo e presença no setor.'
    lead = ', '.join(chunks)
    return f'{intro} {lead}. {variant}'


def player_facts(rows, lineup, side, source, team_id):
    result = []
    roster = [row for row in rows or [] if row.get('strSport') == 'Soccer' and str(row.get('idTeam')) == str(team_id)]
    for group in ('starters', 'bench'):
        for player in lineup.get(group, []) or []:
            matches = []
            for row in roster:
                external_id = row.get('idESPN') if 'ESPN' in source else row.get('idAPIfootball') if 'API-Football' in source else None
                aliases = [row.get('strPlayer', ''), *(row.get('strPlayerAlternate') or '').split(',')]
                if (external_id and str(external_id) == str(player.get('id'))) or normalized_name(player.get('name', '')) in {normalized_name(n) for n in aliases if n}:
                    matches.append(row)
            if len(matches) != 1 or not str(matches[0].get('idPlayer', '')).isdigit():
                continue
            row = matches[0]
            birthday_text = ''
            try:
                birthday = datetime.strptime(row.get('dateBorn', ''), '%Y-%m-%d')
                if 1940 <= birthday.year <= datetime.now().year - 12:
                    birthday_text = f'{birthday.day} de {MONTHS[birthday.month - 1]} de {birthday.year}'
            except (TypeError, ValueError):
                pass
            country = COUNTRIES.get(row.get('strNationality'))
            number = player.get('number') or player.get('shirt_number') or player.get('camisa') or player.get('jersey')
            if birthday_text or country or number or player.get('position'):
                result.append({'id': 'player:' + row['idPlayer'],
                               'text': format_player_profile(player['name'], birthday_text, country, number, player.get('position')),
                               'side': side, 'player_id': str(player.get('id', '')), 'player_name': player['name'],
                               'source': {'name': 'TheSportsDB', 'url': 'https://www.thesportsdb.com/player/' + row['idPlayer']}})
    managers = [row for row in roster if row.get('strPosition') == 'Manager' and row.get('strPlayer')]
    if len(managers) == 1 and str(managers[0].get('idPlayer', '')).isdigit():
        coach = managers[0]
        # Explicitly a catalogue claim; it is not treated as the match's confirmed starting lineup.
        result.append({'id': 'coach:' + coach['idPlayer'],
                       'text': f"Na comissão técnica cadastrada de {coach.get('strTeam', '')}, o TheSportsDB informa {coach['strPlayer']} como treinador.",
                       'source': {'name': 'TheSportsDB', 'url': 'https://www.thesportsdb.com/player/' + coach['idPlayer']}})
    return result


def identify(rows, name):
    matches = []
    for row in rows or []:
        names = [row.get('strTeam', ''), *(row.get('strTeamAlternate') or '').split(',')]
        if row.get('strSport') == 'Soccer' and normalized_name(name) in {normalized_name(n) for n in names if n.strip()}:
            matches.append(row)
    return matches[0] if len(matches) == 1 else None


def facts_for(row, name):
    if not row or not str(row.get('idTeam', '')).isdigit():
        return []
    result = []
    source = {'name': 'TheSportsDB', 'url': 'https://www.thesportsdb.com/team/' + str(row['idTeam'])}
    def add(key, text):
        result.append({'id': str(row['idTeam']) + ':' + key, 'text': text, 'source': source})
    year = str(row.get('intFormedYear') or '')
    if year.isdigit() and 1800 <= int(year) <= datetime.now(timezone.utc).year:
        add('founded', f'Um pouco da história do {name}: o cadastro do clube informa sua fundação em {year}.')
    for key, field, phrase in [('stadium', 'strStadium', 'o estádio associado ao clube'),
                               ('location', 'strLocation', 'a localização do clube'),
                               ('nickname', 'strKeywords', 'o apelido registrado do clube')]:
        value = row.get(field)
        if isinstance(value, str) and 1 <= len(value.strip()) <= 100 and not re.search(r'[<>\r\n]', value):
            add(key, f'Sobre o {name}: {phrase} é {value.strip()}, segundo o TheSportsDB.')
    return result


class ClubContext:
    def __init__(self):
        self.cache = {}
        self.teams = {}
        self.lookup_cache = {}
        self.lock = asyncio.Lock()

    async def team(self, name):
        if not isinstance(name, str) or not 2 <= len(name) <= 150 or name in ('Mandante', 'Visitante'):
            return []
        key = normalized_name(name)
        async with self.lock:
            cached = self.cache.get(key)
            if cached and time.monotonic() < cached[0]:
                return cached[1]
            try:
                data = await providers.request('thesportsdb', 'searchteams.php', t=name)
                row = identify(data.get('teams'), name)
                self.teams[key] = row
                result = facts_for(row, name)
                for ident, text, label, url in CLUB_NOTES.get(str((row or {}).get('idTeam')), []):
                    result.append({'id': str(row['idTeam']) + ':' + ident, 'text': text, 'source': {'name': label, 'url': url}})
                ttl = 86400 if result else 600
            except HTTPException:
                result, ttl = [], 300
            if len(self.cache) >= 128:
                oldest = next(iter(self.cache))
                self.cache.pop(oldest)
                self.teams.pop(oldest, None)
            self.cache[key] = (time.monotonic() + ttl, result)
            return result

    async def lookup(self, path, ident):
        key = (path, ident)
        async with self.lock:
            cached = self.lookup_cache.get(key)
            if cached and time.monotonic() < cached[0]:
                return cached[1]
            try:
                data = await providers.request('thesportsdb', path, id=ident)
                ttl = 86400
            except HTTPException:
                data, ttl = {}, 300
            if len(self.lookup_cache) >= 128:
                self.lookup_cache.pop(next(iter(self.lookup_cache)))
            self.lookup_cache[key] = (time.monotonic() + ttl, data)
            return data

    async def match_team(self, name, lineup, side, source):
        facts = list(await self.team(name))
        team = self.teams.get(normalized_name(name))
        if not team:
            return facts
        team_id = str(team.get('idTeam', ''))
        if team_id.isdigit():
            data = await self.lookup('lookup_all_players.php', team_id)
            facts.extend(player_facts(data.get('player'), lineup, side, source, team_id))
        venue_id = str(team.get('idVenue', ''))
        if venue_id.isdigit():
            data = await self.lookup('lookupvenue.php', venue_id)
            venues = [v for v in data.get('venues') or [] if str(v.get('idVenue')) == venue_id]
            if len(venues) == 1:
                facts.extend(stadium_facts(venues[0]))
        return facts

    def install(self, app, state):
        @app.get('/api/narration/context')
        async def context():
            snapshot = copy.deepcopy(state)
            names = [snapshot.get(side, {}).get('name', '') for side in ('home', 'away')]
            facts = await asyncio.gather(*(self.match_team(name, snapshot.get('lineups', {}).get(side, {}), side, snapshot.get('source', '')) for name, side in zip(names, ('home', 'away'))))
            # Alternate teams instead of exhausting every fact about the home club first.
            alternating = [rows[index] for index in range(max(map(len, facts), default=0)) for rows in facts if index < len(rows)]
            return {'teams': names, 'facts': alternating,
                    'message': f'{len(alternating)} informações dos clubes disponíveis.' if alternating else
                    'A fonte não forneceu curiosidades com identificação suficiente para estes times.'}
