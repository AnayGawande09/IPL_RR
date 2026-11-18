"""STEP 1 - Data preprocessing & match-state reconstruction (pure Python stdlib).

Rules (every one verified against the data pack, see report):
  * Super-over innings (3,4) removed from modelling; abandoned matches have no deliveries.
  * Illegal deliveries = extras_type in {wide, Overstep, other}  -> 99.3% of complete overs then have 6 legal balls.
  * `runs` = runs off the bat only. Extras = extras1_runs + extras_2_runs (updated ball file, Nov 2026, which
    stores the real extras runs). Validated: reproduces 361/362 "won by N runs" margins exactly.
  * Ball faced by batter: every delivery except wides.
  * Runs charged to bowler: bat runs + wides + no-balls ('Overstep'/'other'); byes / leg-byes are not charged.
  * Bowler wickets: Caught, Bowled, LBW, Stump, Hit Wicket (run-outs / retired / obstructing excluded).
  * Revised overs are given in balls; DLS target from `revised_target`.
  * Players keyed by ID (3 names are shared by two different IDs).
  * Scoring environment: par first-innings total per (competition type, season) used to normalise eras.
"""
import csv, sys, os, json, collections as C

DATA = sys.argv[1]
OUT = sys.argv[2]
os.makedirs(OUT, exist_ok=True)

ILLEGAL = {'wide', 'Overstep', 'other'}
NOBALL = {'Overstep', 'other'}
BOWLER_WKT = {'Caught', 'Bowled', 'LBW', 'Stump', 'Hit Wicket'}

def rd(name):
    return list(csv.DictReader(open(os.path.join(DATA, name), encoding='utf-8')))

comps = {r['comp_id']: r for r in rd('competitions.csv')}
matches = {r['match_id']: r for r in rd('matches.csv')}
bbb = rd('ball_by_ball.csv')
log = C.OrderedDict()
log['raw_deliveries'] = len(bbb)

def season_year(s):
    return int(s[:4])

def ctype(comp_id):
    c = comps[comp_id]
    return 'IPL' if c['comp_name'].startswith('IPL') else ('T20I' if c['match_format'] == 'T20I' else 'OtherT20')

# ---- group deliveries by innings, sort in delivery order
inn = C.defaultdict(list)
superover = 0
for r in bbb:
    if r['innings'] not in ('1', '2'):
        superover += 1
        continue
    inn[(r['match_id'], int(r['innings']))].append(r)
log['super_over_deliveries_removed'] = superover
for k in inn:
    inn[k].sort(key=lambda r: int(r['innings_ball_num']))

def extras_runs(r):
    return int(r['extras1_runs']) + int(r['extras_2_runs'])

# ---- innings totals (reconstructed)
tot = {}
for k, rows in inn.items():
    tot[k] = sum(int(r['runs']) + extras_runs(r) for r in rows)

# ---- match outcome
def outcome(m):
    res = m['result'].lower()
    if 'no result' in res or 'abandon' in res:
        return None
    if 'tied' in res or 'super over' in res:
        return 'tie'
    return m['win_team_id'] or None

# ---- par scores per environment (complete 20-over first innings only)
env_tot = C.defaultdict(list)
for (mid, i), rows in inn.items():
    m = matches[mid]
    if i == 1 and not m['first_inn_revised_overs'] and outcome(m) is not None:
        env_tot[(ctype(m['comp_id']), season_year(comps[m['comp_id']]['season']))].append(tot[(mid, 1)])
env_par = {k: sum(v) / len(v) for k, v in env_tot.items()}
glob_par = sum(sum(v) for v in env_tot.values()) / sum(len(v) for v in env_tot.values())

out_rows = []
skipped = C.Counter()
for (mid, i), rows in sorted(inn.items()):
    m = matches[mid]
    oc = outcome(m)
    env = (ctype(m['comp_id']), season_year(comps[m['comp_id']]['season']))
    par = env_par.get(env, glob_par)
    if i == 1:
        max_balls = int(m['first_inn_revised_overs'] or 120)
        target = None
    else:
        max_balls = int(m['second_inn_revised_overs'] or m['first_inn_revised_overs'] or 120)
        target = int(m['revised_target']) if m['revised_target'] else tot.get((mid, 1), 0) + 1
        if (mid, 1) not in inn:
            skipped['no_first_innings'] += 1
            continue
    bat_team = rows[0]['batting_team_id']
    if oc is None:
        y = ''
    elif oc == 'tie':
        y = 0.5
    else:
        y = 1.0 if oc == bat_team else 0.0
    score = wkts = legal = 0
    dots_streak = 0
    recent = []  # wickets in last 12 legal balls
    for r in rows:
        is_legal = r['extras_type'] not in ILLEGAL
        bat_runs = int(r['runs'])
        ex = extras_runs(r)
        wk = r['is_wicket'] == 'true'
        wk_counts = wk and r['dismissal_type'] not in ('Retire Out',)
        # Laws: all wide runs and the no-ball penalty are charged to the bowler; byes / leg-byes are not
        bowler_runs = bat_runs + (ex if r['extras_type'] == 'wide' else int(r['extras1_runs']) if r['extras_type'] in NOBALL else 0)
        out_rows.append({
            'match_id': mid, 'innings': i, 'ctype': env[0], 'season': env[1], 'knock_out': m['knock_out'],
            'bat_team': bat_team, 'bowl_team': r['bowling_team_id'],
            'striker_id': r['striker_id'], 'striker_name': r['striker_name'],
            'bowler_id': r['bowler_id'], 'bowler_name': r['bowler_name'],
            'dismissed_id': r['dismissed_player_id'] if wk else '',
            'over': int(r['overid']), 'legal': int(is_legal), 'faced': int(r['extras_type'] != 'wide'),
            'bat_runs': bat_runs, 'extras': ex, 'bowler_runs': bowler_runs,
            'wicket': int(wk_counts), 'bowler_wkt': int(wk and r['dismissal_type'] in BOWLER_WKT),
            'dismissal': r['dismissal_type'],
            # state BEFORE this delivery
            'score': score, 'wkts': wkts, 'balls_bowled': legal, 'balls_left': max_balls - legal,
            'max_balls': max_balls, 'target': target if target else '',
            'dots_streak': dots_streak, 'wkts_last12': sum(recent[-12:]),
            'par': round(par, 2), 'y_bat_win': y, 'pace_spin': r['pace_or_spin'],
        })
        score += bat_runs + ex
        if wk_counts:
            wkts += 1
        if is_legal:
            legal += 1
            recent.append(1 if wk_counts else 0)
            dots_streak = dots_streak + 1 if (bat_runs + ex == 0) else 0
        elif wk_counts:
            recent[-1:] = [1]

log['modelled_deliveries'] = len(out_rows)
log['innings'] = len(inn)
log['skipped'] = dict(skipped)
log['env_par'] = {f'{k[0]}-{k[1]}': round(v, 1) for k, v in sorted(env_par.items())}
log['env_n'] = {f'{k[0]}-{k[1]}': len(v) for k, v in sorted(env_tot.items())}
log['global_par'] = round(glob_par, 1)
log['matches_with_result'] = sum(1 for m in matches.values() if outcome(m) is not None and (m['match_id'], 1) in inn)

with open(os.path.join(OUT, 'balls_clean.csv'), 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
    w.writeheader(); w.writerows(out_rows)
json.dump(log, open(os.path.join(OUT, 'step1_log.json'), 'w'), indent=1)
print(json.dumps(log, indent=1))
