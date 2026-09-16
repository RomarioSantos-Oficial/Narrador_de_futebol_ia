"""Match identity checks and conservative enrichment across providers."""
import asyncio
import copy
import os
import re
import unicodedata
from datetime import datetime, timezone

from fastapi import HTTPException
from backend import providers
def normalized_name(name):
    name = ''.join(c for c in unicodedata.normalize('NFKD', name.lower()) if not unicodedata.combining(c))
    words = re.findall(r'[a-z0-9]+', name)
    return ' '.join(w for w in words if w not in ('fc', 'cf', 'sc', 'afc', 'ac'))


def instant(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


def same_match(primary, home, away, kickoff):
    try:
        return (normalized_name(primary['home']['name']) == normalized_name(home)
                and normalized_name(primary['away']['name']) == normalized_name(away)
                and abs((instant(primary['kickoff']) - instant(kickoff)).total_seconds()) <= 900)
    except (KeyError, TypeError, ValueError):
        return False


async def compare(selection, primary, espn_request, espn_normalize):
    async def lookup(provider):
        info = providers.SOURCES[provider]
        if provider == selection.provider:
            return provider, {'data': copy.deepcopy(primary), 'primary': True, 'selection': selection.model_dump(),
                              'sampled_at': primary.get('updated_at') or datetime.now(timezone.utc).isoformat()}
        if info.get('env') and not os.getenv(info['env'], '').strip():
            return provider, {'error': 'Chave não configurada.'}
        if provider != 'espn' and selection.league not in providers.LEAGUE_IDS[provider]:
            return provider, {'error': 'Campeonato não disponível nesta integração.'}
        try:
            day = instant(primary['kickoff']).date()
            if provider == 'espn':
                rows = (await espn_request(selection.league, 'scoreboard', dates=day.strftime('%Y%m%d'), limit=100)).get('events', [])
                candidates = []
                for row in rows:
                    sides = {c['homeAway']: c['team']['displayName'] for c in row['competitions'][0]['competitors']}
                    if same_match(primary, sides['home'], sides['away'], row['date']):
                        candidates.append(row['id'])
            else:
                rows = await providers.games(provider, selection.league, day)
                candidates = [row['id'] for row in rows if len(row['name'].split(' × ')) == 2
                              and same_match(primary, *row['name'].split(' × '), row['date'])]
            if len(candidates) != 1:
                return provider, {'error': 'Não foi possível identificar esta partida com segurança (nomes e horário).'}
            if provider == 'espn':
                data, _ = espn_normalize(await espn_request(selection.league, 'summary', event=candidates[0]), selection.league)
            else:
                data, _ = await providers.match(provider, candidates[0])
            if not same_match(primary, data['home']['name'], data['away']['name'], data['kickoff']):
                return provider, {'error': 'A identidade da partida retornada não confere.'}
            return provider, {'data': data, 'primary': False,
                              'selection': {'provider': provider, 'league': selection.league, 'event': str(candidates[0])},
                              'sampled_at': datetime.now(timezone.utc).isoformat()}
        except HTTPException as exc:
            return provider, {'error': exc.detail}
        except (KeyError, TypeError, ValueError):
            return provider, {'error': 'Dados insuficientes para comparar esta partida.'}
    results = dict(await asyncio.gather(*(lookup(provider) for provider in providers.SOURCES)))
    report = {'checked_at': datetime.now(timezone.utc).isoformat(), 'primary': selection.provider, 'sources': results}
    report['recommendation'] = recommend(report)
    return report


def match_minute(data):
    value = re.sub(r"['′\s]", '', str(data.get('clock_display') or data.get('minute') or ''))
    found = re.fullmatch(r"(\d+)(?:\+(\d+))?", value)
    return int(found[1]) + int(found[2] or 0) if found else None


def recommend(report):
    """Rank observable narration coverage, never claim a vote proves match facts."""
    primary_entry = report['sources'].get(report['primary'], {})
    primary = primary_entry.get('data', {})
    ranking = []
    for provider, entry in report['sources'].items():
        info = providers.SOURCES[provider]
        item = {'provider': provider, 'name': info['name'], 'eligible': False, 'score': 0}
        data = entry.get('data')
        if not data:
            item['reason'] = entry.get('error', 'Fonte não consultada.')
            ranking.append(item)
            continue
        stats = sum(isinstance(pair, list) and len(pair) == 2 and all(v is not None for v in pair)
                    for pair in data.get('stats', {}).values())
        events = sum(bool(e.get('text')) and e['text'] != 'Lance registrado na partida'
                     for e in data.get('events', []))
        starters = sum(min(11, len(data.get('lineups', {}).get(side, {}).get('starters', []))) for side in ('home', 'away'))
        minute = match_minute(data)
        cadence = f'Consulta a cada {info["interval"]} s.' if info['interval'] else 'Sem consulta automática neste acesso.'
        item.update(stats=stats, events=events, starters=starters, interval=info['interval'],
                    score=min(30, events * 5) + min(22, stats * 2) + round(starters / 22 * 10)
                    + (15 if minute is not None else 0) + (8 if info['interval'] == 30 else 5 if info['interval'] == 60 else 2 if info['interval'] else 0),
                    reason=f'{events} lances recentes, {stats} estatísticas completas e {starters} titulares. {cadence}')
        blocked = []
        if not info['live']:
            blocked.append('Este acesso não fornece acompanhamento ao vivo.')
        if any(data.get(side, {}).get('score') is None for side in ('home', 'away')):
            blocked.append('Placar incompleto.')
        if provider != report['primary']:
            if primary.get('phase') != data.get('phase'):
                blocked.append('A fase da partida diverge da fonte principal.')
            if any(primary.get(side, {}).get('score') != data.get(side, {}).get('score') for side in ('home', 'away')):
                blocked.append('O placar diverge; confira a comparação antes de trocar manualmente.')
            reference_minute = match_minute(primary)
            if primary.get('phase') == 'in' and reference_minute is not None and (minute is None or minute < reference_minute - 3):
                blocked.append('Relógio ausente ou mais de 3 minutos atrás da fonte principal.')
            try:
                age = (instant(primary_entry['sampled_at']) - instant(entry['sampled_at'])).total_seconds()
                if primary.get('phase') == 'in' and age > 120:
                    blocked.append('Comparação antiga para trocar a fonte ao vivo. Aguarde a próxima consulta.')
            except (KeyError, ValueError, TypeError):
                blocked.append('Horário da consulta indisponível.')
        item['eligible'] = not blocked and bool(entry.get('selection'))
        if blocked:
            item['reason'] += ' ' + ' '.join(blocked)
        ranking.append(item)
    ranking.sort(key=lambda item: (item['eligible'], item['score'], item['provider'] == report['primary']), reverse=True)
    best = next((item for item in ranking if item['eligible']), None)
    return {'provider': best['provider'] if best else None, 'ranking': ranking,
            'selection': report['sources'][best['provider']]['selection'] if best else None,
            'reason': 'Melhor cobertura observada para narrar entre as fontes consultadas. A pontuação mede dados disponíveis, não a exatidão nem a licença de transmissão.' if best
            else 'Nenhuma fonte consultada ficou apta para recomendar acompanhamento ao vivo.'}


def enrich(primary, comparison):
    result = copy.deepcopy(primary)
    origins = {}
    for provider, entry in comparison['sources'].items():
        if entry.get('primary') or not entry.get('data'):
            continue
        other = entry['data']
        stats_current = True
        if primary.get('phase') == 'in':
            current_minute, other_minute = match_minute(primary), match_minute(other)
            stats_current = (other.get('phase') == 'in' and current_minute is not None and other_minute is not None
                             and abs(current_minute - other_minute) <= 3
                             and all(primary[side].get('score') == other[side].get('score') for side in ('home', 'away')))
            try:
                stats_current = stats_current and abs((instant(primary['updated_at']) - instant(entry['sampled_at'])).total_seconds()) <= 120
            except (KeyError, TypeError, ValueError):
                stats_current = False
        if not result.get('league_table') and other.get('league_table'):
            result['league_table'] = copy.deepcopy(other['league_table'])
            origins['league_table'] = providers.SOURCES[provider]['name']
        for field, values in result['stats'].items():
            for i in range(2):
                alternative = other.get('stats', {}).get(field, [None, None])[i]
                if stats_current and values[i] is None and alternative is not None:
                    values[i] = alternative
                    origins[f'stats.{field}.{i}'] = providers.SOURCES[provider]['name']
        for side in ('home', 'away'):
            for field in ('recent_form', 'standings'):
                if not result.get(field, {}).get(side) and other.get(field, {}).get(side):
                    result.setdefault(field, {})[side] = copy.deepcopy(other[field][side])
                    origins[f'{field}.{side}'] = providers.SOURCES[provider]['name']
            if not result[side].get('logo') and other[side].get('logo'):
                result[side]['logo'] = other[side]['logo']
                origins[f'{side}.logo'] = providers.SOURCES[provider]['name']
            for group in ('starters', 'bench'):
                if not result['lineups'][side][group] and other['lineups'][side][group]:
                    result['lineups'][side][group] = copy.deepcopy(other['lineups'][side][group])
                    origins[f'lineups.{side}.{group}'] = providers.SOURCES[provider]['name']
        if not result.get('venue') and other.get('venue'):
            result['venue'] = other['venue']
            origins['venue'] = providers.SOURCES[provider]['name']
    result['data_sources'] = origins
    return result
