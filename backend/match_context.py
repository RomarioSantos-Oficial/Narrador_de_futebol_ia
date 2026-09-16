"""Context supplied with an ESPN match: form, standings and located events."""
import math
import re


def extract_context(data, competitors, league=None):
    result = {'recent_form': {'home': [], 'away': []}, 'standings': {'home': None, 'away': None},
              'field_action': None, 'league_table': None}
    for group in data.get('lastFiveGames', []) or []:
        side = next((s for s in ('home', 'away') if str(group.get('team', {}).get('id')) == str(competitors[s]['team']['id'])), None)
        if side is None:
            continue
        events = sorted(group.get('events', []), key=lambda e: e.get('gameDate', ''), reverse=True)
        result['recent_form'][side] = [
            {'result': {'W': 'V', 'D': 'E', 'L': 'D'}[e['gameResult']], 'date': e.get('gameDate', ''),
             'opponent': e.get('opponent', {}).get('displayName', ''), 'score': e.get('score', ''),
             'competition': e.get('leagueName') or e.get('competitionName', '')}
            for e in events if e.get('gameResult') in ('W', 'D', 'L')][:5]
    table = data.get('standings') or {}
    table_link = (table.get('fullViewLink') or {}).get('href', '')
    linked_league = re.search(r'/league/([\w.]+)', table_link)
    if league and linked_league and linked_league.group(1).lower() != league.lower():
        table = {}  # Never show a domestic table for a cup match, for example.
    groups = []
    for group in table.get('groups', []) or []:
        entries = []
        seen = set()
        for entry in group.get('standings', {}).get('entries', []) or []:
            side = next((s for s in ('home', 'away') if str(entry.get('id')) == str(competitors[s]['team']['id'])), None)
            stats = {item.get('name'): item.get('displayValue', item.get('value')) for item in entry.get('stats', [])}
            record = {'rank': stats.get('rank'), 'points': stats.get('points'),
                      'played': stats.get('gamesPlayed'), 'wins': stats.get('wins'),
                      'draws': stats.get('ties'), 'losses': stats.get('losses'),
                      'goal_difference': stats.get('pointDifferential'), 'label': table.get('header', '')}
            if side:
                result['standings'][side] = record.copy()
            ident = str(entry.get('id', ''))
            if not ident or ident in seen:
                continue
            seen.add(ident)
            logos = entry.get('logo') or []
            entries.append({**record, 'id': ident, 'team': entry.get('team') or 'Time',
                            'logo': logos[0].get('href', '') if isinstance(logos, list) and logos else '', 'side': side})
        if entries:
            def ranking(row):
                try:
                    return int(row['rank'])
                except (TypeError, ValueError):
                    return 9999
            entries.sort(key=ranking)
            groups.append({'name': group.get('header') or group.get('name') or '', 'entries': entries})
    if groups:
        result['league_table'] = {'name': table.get('header', ''), 'league': league or '', 'groups': groups, 'source': 'ESPN'}
    for event in data.get('keyEvents', []) or []:
        try:
            x, y = float(event['fieldPositionX']), float(event['fieldPositionY'])
        except (KeyError, TypeError, ValueError):
            continue
        if not (math.isfinite(x) and math.isfinite(y) and 0 <= x <= 100 and 0 <= y <= 100):
            continue
        result['field_action'] = {'x': x, 'y': y, 'team': event.get('team', {}).get('displayName', ''),
                                  'minute': event.get('clock', {}).get('displayValue') or '—',
                                  'text': event.get('text') or event.get('type', {}).get('text', ''),
                                  'kind': event.get('type', {}).get('text', '')}
    return result


def event_text(event, current):
    """Portuguese summaries from structured events; preserve original narration."""
    typ = event.get('type', {}).get('type', '')
    original = event.get('text') or event.get('shortText') or event.get('type', {}).get('text', '')
    simple = {'kickoff': 'Início da partida', 'start-2nd-half': 'Início do segundo tempo',
              'halftime': 'Fim do primeiro tempo · intervalo', 'end-regular-time': 'Fim do tempo regulamentar',
              'end-after-extra-time': 'Fim da prorrogação', 'start-delay': 'Partida interrompida',
              'end-delay': 'Partida retomada', 'penalty---missed': 'Pênalti perdido',
              'own-goal': 'Gol contra', 'goal---header': 'Gol de cabeça', 'shot': 'Finalização',
              'corner-kick': 'Escanteio', 'offside': 'Impedimento', 'foul': 'Falta'}
    if typ == 'substitution':
        participants = [p.get('athlete', {}).get('displayName', '') for p in event.get('participants', [])]
        detail = ', '.join(p for p in participants if p)
        current = 'Substituição' + (' · '+event.get('team', {}).get('displayName', '') if event.get('team') else '') + (' · '+detail if detail else '')
    elif typ in simple:
        current = simple[typ]
        if event.get('scoringPlay'):
            names = [p.get('athlete', {}).get('displayName', '') for p in event.get('participants', [])]
            if names and names[0]:
                current += ' · '+names[0]
    elif current == original:
        current = 'Lance registrado na partida'
    return current, original
