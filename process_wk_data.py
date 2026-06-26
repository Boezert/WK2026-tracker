import json
import sys
import os
import requests
from datetime import datetime, timezone

API_KEY      = os.environ.get('FOOTBALL_API_KEY', '')
ANTHROPIC_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
BASE_URL     = 'https://api.football-data.org/v4'
HEADERS      = {'X-Auth-Token': API_KEY}

# ── Data ophalen ───────────────────────────────────────────
print('Standen ophalen...')
r_standen = requests.get(f'{BASE_URL}/competitions/WC/standings?season=2026', headers=HEADERS)
if r_standen.status_code != 200:
    print(f'Fout standen: {r_standen.status_code}', file=sys.stderr)
    sys.exit(1)
standen = r_standen.json()

print('Wedstrijden ophalen...')
r_wed = requests.get(f'{BASE_URL}/competitions/WC/matches?season=2026', headers=HEADERS)
if r_wed.status_code != 200:
    print(f'Fout wedstrijden: {r_wed.status_code}', file=sys.stderr)
    sys.exit(1)
wedstrijden_raw = r_wed.json()

# ── Filter groepsfase ──────────────────────────────────────
alle_matches   = wedstrijden_raw.get('matches', [])
groepsfase     = [m for m in alle_matches if m.get('group')]
finished       = [m for m in groepsfase if m['status'] == 'FINISHED']

print(f'Totaal wedstrijden: {len(alle_matches)}')
print(f'Groepsfase:         {len(groepsfase)}')
print(f'Gespeeld:           {len(finished)}')

from collections import Counter
per_groep = Counter(m.get('group','?') for m in finished)
print('Gespeeld per groep:', dict(sorted(per_groep.items())))

wedstrijden = dict(wedstrijden_raw)
wedstrijden['matches'] = groepsfase

# ── Verhaallijnen via Claude ───────────────────────────────
groepen = [g for g in standen.get('standings', []) if g.get('type') == 'TOTAL' and g.get('group')]
team_data = []
for g in groepen:
    letter = g.get('group', '').replace('GROUP_', '')
    for t in g.get('table', []):
        team_data.append({
            'groep': letter,
            'team':  t['team']['name'],
            'pts':   t['points'],
            'pos':   t['position'],
            'w': t['won'], 'g': t['draw'], 'v': t['lost'],
            'gf': t['goalsFor'], 'gt': t['goalsAgainst'],
            'ds': t['goalDifference'],
            'gespeeld': t['playedGames'],
        })

recente_uitslagen = [
    {
        'thuis': m['homeTeam']['name'],
        'uit':   m['awayTeam']['name'],
        'score': f"{m['score']['fullTime']['home']}-{m['score']['fullTime']['away']}",
    }
    for m in finished[-12:]
]

verhaallijnen = []
if ANTHROPIC_KEY and team_data:
    prompt = (
        'Je bent een WK-verslaggever. Genereer precies 6 pakkende verhaallijnen '
        'over de FIFA WK 2026 groepsfase in het Nederlands. '
        'Retourneer ALLEEN een geldig JSON-array, geen extra tekst. '
        'Elk object: {"head": "koptekst max 5 woorden", "body": "2-3 zinnen met concrete stats en namen"}. '
        'Varieer de themas: records, dominantie, verrassingen, spannende duels, ploegen in nood. '
        f'Standen: {json.dumps(team_data, ensure_ascii=False)} '
        f'Recente uitslagen: {json.dumps(recente_uitslagen, ensure_ascii=False)}'
    )
    try:
        resp = requests.post(
            'https://api.anthropic.com/v1/messages',
            headers={
                'x-api-key': ANTHROPIC_KEY,
                'anthropic-version': '2023-06-01',
                'content-type': 'application/json',
            },
            json={
                'model': 'claude-haiku-4-5-20251001',
                'max_tokens': 1500,
                'messages': [{'role': 'user', 'content': prompt}],
            },
            timeout=30,
        )
        if resp.status_code == 200:
            tekst = resp.json()['content'][0]['text'].strip()
            start = tekst.find('[')
            eind  = tekst.rfind(']') + 1
            if start >= 0 and eind > start:
                verhaallijnen = json.loads(tekst[start:eind])
                print(f'Verhaallijnen gegenereerd: {len(verhaallijnen)}')
        else:
            print(f'Claude API fout: {resp.status_code}', file=sys.stderr)
    except Exception as e:
        print(f'Verhaallijnen overgeslagen: {e}', file=sys.stderr)
else:
    print('Geen Anthropic API key — verhaallijnen overgeslagen')

# ── Opslaan ────────────────────────────────────────────────
data = {
    'bijgewerkt':    datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
    'standen':       standen,
    'wedstrijden':   wedstrijden,
    'verhaallijnen': verhaallijnen,
}

with open('data.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False)

print('data.json opgeslagen')
