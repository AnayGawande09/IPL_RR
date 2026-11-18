"""STEP 6 - Rajasthan Royals squad-fit analysis (data pack only).

  * RR's pressure batting and bowling in IPL 2025-2026 vs the rest of the IPL (same seasons, live balls).
  * RR results in close matches (won/lost by <= 10 runs, or chase finished with <= 6 balls left).
  * RR IPL 2026 squad (competition_team_player_mapping) and each member's pressure rank.
  * Profile of each top-10 player: phase of their pressure balls, batting hand / bowling type,
    pressure output vs pace and spin (batters) or by phase (bowlers), 2026 IPL team.
"""
import sys, os, re, json, csv, collections as C
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *

DATA, OUT = sys.argv[1], sys.argv[2]
RR = '3'
SEASONS = (2025, 2026)
raw = read_csv(os.path.join(DATA, 'ball_by_ball.csv'))
hand = C.defaultdict(C.Counter); btype = C.defaultdict(C.Counter)
for r in raw:
    hand[r['striker_id']][r['batting_type']] += 1
    btype[r['bowler_id']][r['bowling_type']] += 1
balls = read_csv(os.path.join(OUT, 'balls_pressure.csv'))
for b in balls:
    for k in ('innings', 'over', 'legal', 'faced', 'bat_runs', 'bowler_runs', 'wicket', 'bowler_wkt', 'season', 'dead', 'balls_left'):
        b[k] = int(b[k])
    for k in ('PI', 'wpa_bat', 'wpa_bowl'):
        b[k] = float(b[k])
    b['P'] = int(b['PI'] >= 1.5 and not b['dead'])
def phase(o):
    return 'Powerplay (1-6)' if o <= 6 else ('Middle (7-15)' if o <= 15 else 'Death (16-20)')
ipl = [b for b in balls if b['ctype'] == 'IPL' and b['season'] in SEASONS and not b['dead']]
res = {}

def bat_summ(rows):
    f = [r for r in rows if r['faced']]
    n = len(f)
    if not n:
        return None
    outs = sum(1 for r in f if r['wicket'] and r['dismissed_id'] == r['striker_id'])
    return {'balls': n, 'SR': round(100 * sum(r['bat_runs'] for r in f) / n, 1), 'out_pct': round(100 * outs / n, 2),
            'boundary_pct': round(100 * sum(r['bat_runs'] in (4, 6) for r in f) / n, 1),
            'WPA_per100': round(100 * sum(r['wpa_bat'] for r in f) / n, 2)}
def bowl_summ(rows):
    lg = sum(r['legal'] for r in rows)
    if not lg:
        return None
    w = sum(r['bowler_wkt'] for r in rows)
    return {'balls': lg, 'econ': round(6 * sum(r['bowler_runs'] for r in rows) / lg, 2),
            'balls_per_wkt': round(lg / w, 1) if w else None,
            'dot_pct': round(100 * sum(1 for r in rows if r['legal'] and r['bowler_runs'] == 0) / lg, 1),
            'WPA_per100': round(100 * sum(r['wpa_bowl'] for r in rows) / len(rows), 2)}

P = [b for b in ipl if b['P']]
res['bat_pressure'] = {'RR': bat_summ([b for b in P if b['bat_team'] == RR]), 'Rest of IPL': bat_summ([b for b in P if b['bat_team'] != RR])}
res['bowl_pressure'] = {'RR': bowl_summ([b for b in P if b['bowl_team'] == RR]), 'Rest of IPL': bowl_summ([b for b in P if b['bowl_team'] != RR])}
res['bat_pressure_phase'] = {ph: {'RR': bat_summ([b for b in P if b['bat_team'] == RR and phase(b['over']) == ph]),
                                  'Rest of IPL': bat_summ([b for b in P if b['bat_team'] != RR and phase(b['over']) == ph])}
                             for ph in ('Powerplay (1-6)', 'Middle (7-15)', 'Death (16-20)')}
res['bowl_pressure_type'] = {}
for t in ('Pace', 'Spin'):
    res['bowl_pressure_type'][t] = {'RR': bowl_summ([b for b in P if b['bowl_team'] == RR and b['pace_spin'] == t]),
                                    'Rest of IPL': bowl_summ([b for b in P if b['bowl_team'] != RR and b['pace_spin'] == t])}
res['bowl_pressure_phase'] = {ph: {'RR': bowl_summ([b for b in P if b['bowl_team'] == RR and phase(b['over']) == ph]),
                                   'Rest of IPL': bowl_summ([b for b in P if b['bowl_team'] != RR and phase(b['over']) == ph])}
                              for ph in ('Powerplay (1-6)', 'Middle (7-15)', 'Death (16-20)')}

# ---- results and close matches
matches = {m['match_id']: m for m in read_csv(os.path.join(DATA, 'matches.csv'))}
comps = {c['comp_id']: c for c in read_csv(os.path.join(DATA, 'competitions.csv'))}
end = {}
for b in balls:
    if b['innings'] == 2:
        end[b['match_id']] = b
rec = C.defaultdict(lambda: C.Counter())
for mid, m in matches.items():
    c = comps[m['comp_id']]
    if not c['comp_name'].startswith('IPL') or int(c['season']) not in SEASONS:
        continue
    if RR not in (m['home_team_id'], m['away_team_id']):
        continue
    resu = m['result'].lower()
    if 'no result' in resu or 'abandon' in resu:
        rec[c['season']]['no result'] += 1
        continue
    won = m['win_team_id'] == RR
    rec[c['season']]['won' if won else 'lost'] += 1
    mr = re.search(r'by (\d+)\s*run', resu)
    close = False
    if 'tied' in resu or 'super over' in resu:
        close = True
    elif mr:
        close = int(mr.group(1)) <= 10
    elif mid in end:
        e = end[mid]
        close = e['balls_left'] - e['legal'] <= 6
    if close:
        rec[c['season']]['close_won' if won else 'close_lost'] += 1
res['rr_results'] = {k: dict(v) for k, v in sorted(rec.items())}

# ---- RR 2026 squad and their pressure ranks
mapping = read_csv(os.path.join(DATA, 'competition_team_player_mapping.csv'))
squad = [(r['player_id'], r['player_name']) for r in mapping if r['comp_id'] == '3298' and r['team_id'] == RR]
team26 = {}
for r in mapping:
    if r['comp_id'] == '3298':
        team26[r['player_id']] = r['team_name']
FB = {r['player_id']: r for r in read_csv(os.path.join(OUT, 'FINAL_bat.csv'))}
FW = {r['player_id']: r for r in read_csv(os.path.join(OUT, 'FINAL_bowl.csv'))}
res['rr_squad_2026'] = [{'player': n, 'bat_rank': FB[p]['final_rank'] if p in FB else '', 'bowl_rank': FW[p]['final_rank'] if p in FW else '',
                         'bat_P_balls': FB[p]['P_balls'] if p in FB else '', 'bowl_P_balls': FW[p]['P_balls'] if p in FW else ''}
                        for p, n in squad]
res['rr_squad_size'] = len(squad)
res['pool_sizes'] = {'bat': len(FB), 'bowl': len(FW)}

# ---- profiles of top-10 players (all competitions, live pressure balls)
allP = [b for b in balls if b['P']]
prof = {}
for role, F in (('bat', FB), ('bowl', FW)):
    top = sorted(F.values(), key=lambda r: int(r['final_rank']))[:10]
    out = []
    for r in top:
        pid = r['player_id']
        if role == 'bat':
            mine = [b for b in allP if b['striker_id'] == pid and b['faced']]
            vs = {t: bat_summ([b for b in mine if b['pace_spin'] == t]) for t in ('Pace', 'Spin')}
            style = hand[pid].most_common(1)[0][0]
        else:
            mine = [b for b in allP if b['bowler_id'] == pid]
            vs = {ph: bowl_summ([b for b in mine if phase(b['over']) == ph]) for ph in ('Powerplay (1-6)', 'Middle (7-15)', 'Death (16-20)')}
            style = btype[pid].most_common(1)[0][0]
        ph = C.Counter(phase(b['over']) for b in mine)
        n = sum(ph.values())
        out.append({'rank': r['final_rank'], 'player': r['player'], 'style': style, 'team_2026': team26.get(pid, 'not in IPL 2026 data'),
                    'in_rr_2026': pid in dict(squad),
                    'phase_share': {k: round(v / n, 3) for k, v in ph.items()}, 'split': vs, 'P_balls': r['P_balls'],
                    'P_SR': r.get('P_SR'), 'B_SR': r.get('B_SR'), 'P_econ': r.get('P_econ'), 'B_econ': r.get('B_econ'),
                    'P_avg': r.get('P_avg'), 'P_balls_per_wkt': r.get('P_balls_per_wkt'), 'ptop10': r['ens_boot_p_top10']})
    prof[role] = out
res['profiles'] = prof
json.dump(res, open(os.path.join(OUT, 'rr_fit.json'), 'w'), indent=1)
print(json.dumps({k: v for k, v in res.items() if k != 'profiles'}, indent=1))
for role in prof:
    for p in prof[role]:
        print(role, p['rank'], p['player'], p['style'], p['team_2026'], p['phase_share'], json.dumps(p['split']))
