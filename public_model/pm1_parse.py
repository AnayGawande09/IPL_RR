"""PUBLIC MODEL 1 - parse Cricsheet IPL ball-by-ball (2008-2026) into per-ball rows with the model's OWN pressure flag.

This model is separate from the main SupeRR method: it does not use the data pack, the Leverage Index or any
of our ratings. Its pressure rule is a simple public one:
    pressure ball = overs 16-20 (either innings)  OR  2nd innings with required run rate >= 9
    excluded as decided: chases needing more than 18 an over, or fewer runs than balls left with 6+ wickets in hand
usage: python -I pm1_parse.py <ipl_json.zip> <out_dir>
"""
import sys, os, json, zipfile, csv

ZIP, OUT = sys.argv[1], sys.argv[2]
os.makedirs(OUT, exist_ok=True)
BOWLER_WKT = {'caught', 'bowled', 'lbw', 'stumped', 'caught and bowled', 'hit wicket'}

def season_of(d):
    return int(d['info']['dates'][0][:4])

z = zipfile.ZipFile(ZIP)
rows, matches = [], []
for name in sorted(z.namelist()):
    if not name.endswith('.json'):
        continue
    d = json.loads(z.read(name))
    info = d['info']; mid = name[:-5]; season = season_of(d)
    inns = [i for i in d.get('innings', []) if not i.get('super_over')]
    if len(inns) < 1:
        continue
    total1 = sum(dl['runs']['total'] for o in inns[0]['overs'] for dl in o['deliveries'])
    tgt = inns[1].get('target', {}) if len(inns) > 1 else {}
    target = tgt.get('runs', total1 + 1)
    max_balls = int(round(float(tgt.get('overs', info.get('overs', 20))) * 6)) if tgt.get('overs') else 6 * info.get('overs', 20)
    out = info.get('outcome', {})
    matches.append({'match': mid, 'season': season, 'date': info['dates'][0], 'team1': info['teams'][0], 'team2': info['teams'][1],
                    'winner': out.get('winner', ''), 'players1': '|'.join(info['players'][info['teams'][0]]),
                    'players2': '|'.join(info['players'][info['teams'][1]])})
    for ix, inn in enumerate(inns[:2]):
        score = wk = legal = 0
        for o in inn['overs']:
            over = o['over'] + 1
            for dl in o['deliveries']:
                ex = dl.get('extras', {})
                is_legal = 'wides' not in ex and 'noballs' not in ex
                need = target - score if ix == 1 else None
                left = max_balls - legal
                if ix == 1 and left > 0:
                    rrr = 6 * need / left
                    decided = rrr > 18 or (need <= left and wk <= 4)
                    pressure = (over >= 16 or rrr >= 9) and not decided and need > 0
                else:
                    pressure = over >= 16
                w = dl.get('wickets', [])
                bat_out = any(x['player_out'] == dl['batter'] for x in w)
                bwk = sum(1 for x in w if x['kind'] in BOWLER_WKT)
                brun = dl['runs']['batter'] + ex.get('wides', 0) + ex.get('noballs', 0)
                rows.append([mid, season, ix + 1, over, dl['batter'], dl['bowler'], dl['runs']['batter'], int('wides' not in ex),
                             int(is_legal), brun, int(bat_out), bwk, int(pressure), inn['team']])
                score += dl['runs']['total']; wk += len(w); legal += is_legal
with open(os.path.join(OUT, 'pm_balls.csv'), 'w', newline='', encoding='utf-8') as f:
    wr = csv.writer(f)
    wr.writerow(['match', 'season', 'innings', 'over', 'batter', 'bowler', 'bat_runs', 'faced', 'legal', 'bowler_runs',
                 'batter_out', 'bowler_wkt', 'pressure', 'bat_team'])
    wr.writerows(rows)
with open(os.path.join(OUT, 'pm_matches.csv'), 'w', newline='', encoding='utf-8') as f:
    wr = csv.DictWriter(f, fieldnames=list(matches[0])); wr.writeheader(); wr.writerows(matches)
P = sum(r[12] for r in rows)
print(f'{len(matches)} matches, {len(rows)} deliveries, pressure share {P / len(rows):.3f}')
