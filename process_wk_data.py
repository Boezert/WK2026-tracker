import json, sys, os, requests
from datetime import datetime, timezone

API_KEY       = os.environ.get('FOOTBALL_API_KEY', '')
ANTHROPIC_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
BASE_URL      = 'https://api.football-data.org/v4'
HEADERS       = {'X-Auth-Token': API_KEY}

print('Standen ophalen...')
r = requests.get(f'{BASE_URL}/competitions/WC/standings?season=2026', headers=HEADERS)
if r.status_code != 200:
    print(f'Fout standen: {r.status_code}', file=sys.stderr); sys.exit(1)
standen = r.json()

print('Alle wedstrijden ophalen...')
r2 = requests.get(f'{BASE_URL}/competitions/WC/matches?season=2026', headers=HEADERS)
if r2.status_code != 200:
    print(f'Fout wedstrijden: {r2.status_code}', file=sys.stderr); sys.exit(1)
alle = r2.json().get('matches', [])

groepsfase = [m for m in alle if m.get('group')]
knockout   = [m for m in alle if not m.get('group') and m.get('stage') not in (None, 'PRELIMINARY_ROUND')]

print(f'Groepsfase: {len(groepsfase)} | Knockout: {len(knockout)} | Gespeeld: {len([m for m in alle if m["status"]=="FINISHED"])}')

from collections import Counter
per_groep = Counter(m.get('group','?') for m in groepsfase if m['status']=='FINISHED')
print('Gespeeld per groep:', dict(sorted(per_groep.items())))
per_ronde = Counter(m.get('stage') for m in knockout)
print('Knockout rondes:', dict(per_ronde))

# Verhaallijnen via Claude
team_data = []
for g in [x for x in standen.get('standings',[]) if x.get('type')=='TOTAL']:
    ltr = (g.get('group') or '').replace('GROUP_','')
    for t in g.get('table',[]):
        team_data.append({'groep':ltr,'team':t['team']['name'],'pts':t['points'],'pos':t['position'],
            'w':t['won'],'g':t['draw'],'v':t['lost'],'gf':t['goalsFor'],'gt':t['goalsAgainst'],'ds':t['goalDifference'],'gespeeld':t['playedGames']})

# Als 1 gecombineerde tabel, team_data aanmaken vanuit matches
if len(team_data) == 0 or (len([x for x in standen.get('standings',[]) if x.get('type')=='TOTAL']) == 1):
    teamToGroup = {}
    for m in groepsfase:
        if m.get('group'):
            if m['homeTeam'].get('id'): teamToGroup[m['homeTeam']['id']] = m['group'].replace('GROUP_','')
            if m['awayTeam'].get('id'): teamToGroup[m['awayTeam']['id']] = m['group'].replace('GROUP_','')
    all_table = []
    for s in standen.get('standings',[]):
        if s.get('type')=='TOTAL':
            all_table.extend(s.get('table',[]))
    for t in all_table:
        grp = teamToGroup.get(t['team']['id'],'?')
        team_data.append({'groep':grp,'team':t['team']['name'],'pts':t['points'],'pos':t['position'],
            'w':t['won'],'g':t['draw'],'v':t['lost'],'gf':t['goalsFor'],'gt':t['goalsAgainst'],'ds':t['goalDifference'],'gespeeld':t['playedGames']})

recent = [m for m in alle if m['status']=='FINISHED'][-12:]
uitslagen = [{'thuis':m['homeTeam']['name'],'uit':m['awayTeam']['name'],
    'score':f"{m['score']['fullTime']['home']}-{m['score']['fullTime']['away']}"} for m in recent]

verhaallijnen = []
if ANTHROPIC_KEY and team_data:
    prompt = (
        'Je bent een WK-verslaggever. Genereer precies 6 pakkende verhaallijnen over FIFA WK 2026 in het Nederlands. '
        'Retourneer ALLEEN een geldig JSON-array. Elk object: {"head":"koptekst max 5 woorden","body":"2-3 zinnen met concrete stats"}. '
        f'Standen: {json.dumps(team_data[:24], ensure_ascii=False)} '
        f'Recente uitslagen: {json.dumps(uitslagen, ensure_ascii=False)}'
    )
    try:
        resp = requests.post('https://api.anthropic.com/v1/messages',
            headers={'x-api-key':ANTHROPIC_KEY,'anthropic-version':'2023-06-01','content-type':'application/json'},
            json={'model':'claude-haiku-4-5-20251001','max_tokens':1500,'messages':[{'role':'user','content':prompt}]}, timeout=30)
        if resp.status_code == 200:
            t = resp.json()['content'][0]['text'].strip()
            s, e = t.find('['), t.rfind(']')+1
            if s >= 0 and e > s:
                verhaallijnen = json.loads(t[s:e])
                print(f'Verhaallijnen: {len(verhaallijnen)}')
    except Exception as ex:
        print(f'Verhaallijnen overgeslagen: {ex}', file=sys.stderr)

data = {
    'bijgewerkt':    datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
    'standen':       standen,
    'wedstrijden':   {'matches': groepsfase},
    'knockout':      {'matches': knockout},
    'verhaallijnen': verhaallijnen,
}

with open('data.json','w',encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False)
print('✓ data.json opgeslagen')
