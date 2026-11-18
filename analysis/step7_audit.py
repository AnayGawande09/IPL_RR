"""STEP 7 - Deeper accuracy audit (pure Python stdlib).

  A. Raw-data integrity: duplicate / missing deliveries, wicket counts, player-in-XI checks, and
     "won by N wickets" / "won by N runs" results reproduced from the ball-by-ball reconstruction.
  B. Recount: the top-10 pressure numbers re-derived directly from the ball file.
  C. Robustness: leave-one-component-out composites and eligibility thresholds 40 / 100 balls.
  D. Out-of-sample test: ratings built on 2022-24 only (step4 mode pre25) against what the same
     players did on pressure balls in 2025-26, compared with naive predictors.
"""
import sys, os, re, json, math, random, collections as C
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import read_csv

DATA, OUT = sys.argv[1], sys.argv[2]
rd = lambda n: read_csv(os.path.join(DATA, n))
log = C.OrderedDict()

# ------------------------------------------------------------ A. raw integrity
bbb = rd('ball_by_ball.csv'); matches = {m['match_id']: m for m in rd('matches.csv')}
xi = C.defaultdict(set)
for r in rd('playing_eleven.csv'):
    xi[(r['match_id'], r['team_id'])].add(r['player_id'])
keys = C.Counter((r['match_id'], r['innings'], r['innings_ball_num']) for r in bbb)
inn = C.defaultdict(list)
for r in bbb:
    if r['innings'] in ('1', '2'):
        inn[(r['match_id'], int(r['innings']))].append(r)
gaps = 0
for k, rows in inn.items():
    nums = sorted(int(r['innings_ball_num']) for r in rows)
    gaps += nums != list(range(1, len(nums) + 1))
wk = {k: sum(r['is_wicket'] == 'true' for r in rows) for k, rows in inn.items()}
xr = lambda r: int(r['extras1_runs']) + int(r['extras_2_runs'])
tot = {k: sum(int(r['runs']) + xr(r) for r in rows) for k, rows in inn.items()}
in_xi = C.Counter()
for r in bbb:
    if r['innings'] not in ('1', '2'):
        continue
    in_xi['striker'] += r['striker_id'] in xi[(r['match_id'], r['batting_team_id'])]
    in_xi['non_striker'] += r['non_striker_id'] in xi[(r['match_id'], r['batting_team_id'])]
    in_xi['bowler'] += r['bowler_id'] in xi[(r['match_id'], r['bowling_team_id'])]
    in_xi['n'] += 1
    if r['is_wicket'] == 'true' and r['dismissed_player_id']:
        in_xi['dismissed_n'] += 1
        in_xi['dismissed_ok'] += r['dismissed_player_id'] in (r['striker_id'], r['non_striker_id'])
four_ok = sum((r['is_four'] == 'true') <= (r['runs'] == '4') and (r['is_six'] == 'true') <= (r['runs'] == '6') for r in bbb)
wkt_res = [0, 0]; run_err = []
for mid, m in matches.items():
    if (mid, 2) not in inn or m['revised_target'] or 'super' in m['result'].lower():
        continue
    chase_team = inn[(mid, 2)][0]['batting_team_id']
    g = re.search(r'won by (\d+) ?wicket', m['result'], re.I)
    if g and m['win_team_id'] == chase_team:
        wkt_res[0] += 1
        wkt_res[1] += (10 - int(g.group(1))) == wk[(mid, 2)]
    g = re.search(r'won by (\d+) ?run', m['result'], re.I)
    if g and m['win_team_id'] != chase_team:
        run_err.append(abs((tot[(mid, 1)] - tot[(mid, 2)]) - int(g.group(1))))
log['A_integrity'] = {
    'deliveries': len(bbb), 'duplicate_delivery_keys': sum(v > 1 for v in keys.values()),
    'innings_with_ball_number_gaps': gaps, 'innings_over_10_wickets': sum(v > 10 for v in wk.values()),
    'ball_matches_missing_from_matches_csv': len({r['match_id'] for r in bbb} - set(matches)),
    'striker_in_XI_pct': round(100 * in_xi['striker'] / in_xi['n'], 3),
    'non_striker_in_XI_pct': round(100 * in_xi['non_striker'] / in_xi['n'], 3),
    'bowler_in_XI_pct': round(100 * in_xi['bowler'] / in_xi['n'], 3),
    'dismissed_is_on_strike_or_non_striker_pct': round(100 * in_xi['dismissed_ok'] / max(in_xi['dismissed_n'], 1), 3),
    'four_six_flags_consistent_pct': round(100 * four_ok / len(bbb), 3),
    'won_by_wickets_reproduced': f'{wkt_res[1]}/{wkt_res[0]}',
    'won_by_runs_n': len(run_err),
    'won_by_runs_exact_pct': round(100 * sum(e == 0 for e in run_err) / len(run_err), 1),
    'won_by_runs_within_5_pct': round(100 * sum(e <= 5 for e in run_err) / len(run_err), 1),
    'won_by_runs_MAE': round(sum(run_err) / len(run_err), 2),
    'note': 'extras = extras1_runs + extras_2_runs from the updated ball file (Nov 2026), which stores the real '
            'extras runs; innings totals now reproduce official margins.'}

# ------------------------------------------------------------ B. recount top-10 from the ball file
balls = read_csv(os.path.join(OUT, 'balls_pressure.csv'))
for b in balls:
    for k in ('dead', 'season', 'faced', 'legal', 'bat_runs', 'bowler_runs', 'bowler_wkt'):
        b[k] = int(b[k])
    for k in ('PI', 'rv_bat', 'rv_bowl', 'wpa_bat', 'wpa_bowl'):
        b[k] = float(b[k])
live = [b for b in balls if not b['dead']]
P = [b for b in live if b['PI'] >= 1.5]
final = json.load(open(os.path.join(OUT, 'FINAL_top10.json')))
main = {r: {x['player_id']: x for x in read_csv(os.path.join(OUT, f'rank_{r}_main.csv'))} for r in ('bat', 'bowl')}
mism = []
for role in ('bat', 'bowl'):
    for f in final[role]:
        p = f['player_id']
        if role == 'bat':
            mine = [b for b in P if b['faced'] and b['striker_id'] == p]
            got = (len(mine), sum(b['bat_runs'] for b in mine))
            want = (int(main[role][p]['P_balls']), int(main[role][p]['P_runs']))
        else:
            mine = [b for b in P if b['bowler_id'] == p]
            got = (len(mine), sum(b['bowler_wkt'] for b in mine))
            want = (int(main[role][p]['P_balls']), int(main[role][p]['P_wkts']))
        if got != want:
            mism.append((f['player'], got, want))
log['B_recount'] = {'players_checked': 20, 'mismatches': mism}

# ------------------------------------------------------------ C. robustness
def top(role, mode, k=10):
    rows = read_csv(os.path.join(OUT, f'rank_{role}_{mode}.csv'))
    return [r['player'] for r in rows[:k]]
rob = {}
for role in ('bat', 'bowl'):
    ref = [f['player'] for f in final[role]]
    rows = read_csv(os.path.join(OUT, f'rank_{role}_main.csv'))
    loo = {}; keep = set(ref)
    for k, lab in enumerate(['C1 WPA', 'C2 pressure RV', 'C3 clutch', 'C4 consistency']):
        sc = sorted(rows, key=lambda r: -sum(float(r[f'z{j + 1}']) for j in range(4) if j != k))
        t10 = {r['player'] for r in sc[:10]}
        loo['without ' + lab] = len(set(ref) & t10); keep &= t10
    every = [p for p in ref if p in keep]
    th = {m: len(set(ref) & set(top(role, m))) for m in ('min40', 'min100')}
    rob[role] = {'leave_one_component_out_overlap_of_10': loo, 'threshold_overlap_of_10': th,
                 'in_top10_under_every_leave_one_out': every,
                 'eligible_min40': len(read_csv(os.path.join(OUT, f'rank_{role}_min40.csv'))),
                 'eligible_min100': len(read_csv(os.path.join(OUT, f'rank_{role}_min100.csv')))}
log['C_robustness'] = rob

# ------------------------------------------------------------ D. out-of-sample (2022-24 -> 2025-26)
def spearman(a, b):
    def rk(v):
        o = sorted(range(len(v)), key=lambda i: v[i]); r = [0.0] * len(v); i = 0
        while i < len(o):
            j = i
            while j + 1 < len(o) and v[o[j + 1]] == v[o[i]]:
                j += 1
            for t in range(i, j + 1):
                r[o[t]] = (i + j) / 2
            i = j + 1
        return r
    x, y = rk(a), rk(b); mx, my = sum(x) / len(x), sum(y) / len(y)
    num = sum((p - mx) * (q - my) for p, q in zip(x, y))
    den = math.sqrt(sum((p - mx) ** 2 for p in x) * sum((q - my) ** 2 for q in y))
    return num / den if den else 0.0   # a constant predictor (component with no signal) has no rank information

oos = {}
MIN_TEST = 30
for role in ('bat', 'bowl'):
    pre = {r['player_id']: r for r in read_csv(os.path.join(OUT, f'rank_{role}_pre25.csv'))}
    sel = (lambda b: b['faced']) if role == 'bat' else (lambda b: True)
    pid = (lambda b: b['striker_id']) if role == 'bat' else (lambda b: b['bowler_id'])
    rv = 'rv_bat' if role == 'bat' else 'rv_bowl'; wp = 'wpa_bat' if role == 'bat' else 'wpa_bowl'
    test = C.defaultdict(lambda: [0, 0.0, 0.0]); trainP = C.defaultdict(lambda: [0, 0.0, 0.0]); trainB = C.defaultdict(lambda: [0, 0.0])
    for b in live:
        if not sel(b):
            continue
        p = pid(b)
        if b['season'] >= 2025:
            if b['PI'] >= 1.5:
                t = test[p]; t[0] += 1; t[1] += b[rv]; t[2] += 100 * b[wp]
        else:
            tb = trainB[p]; tb[0] += 1; tb[1] += b[rv]
            if b['PI'] >= 1.5:
                t = trainP[p]
                t[0] += 1; t[1] += b[rv]
                t[2] += b['bat_runs'] if role == 'bat' else b['bowler_runs']
    ids = [p for p in pre if test[p][0] >= MIN_TEST]
    y_rv = [test[p][1] / test[p][0] for p in ids]
    y_wp = [test[p][2] / test[p][0] for p in ids]
    preds = {'Our composite (2022-24 only)': [float(pre[p]['composite']) for p in ids],
             'Naive: raw pressure run value per ball': [trainP[p][1] / trainP[p][0] for p in ids],
             ('Naive: raw pressure strike rate' if role == 'bat' else 'Naive: raw pressure economy (lower = better)'):
                 [(1 if role == 'bat' else -1) * trainP[p][2] / trainP[p][0] for p in ids],
             'Naive: overall run value (ignores pressure)': [trainB[p][1] / trainB[p][0] for p in ids]}
    random.seed(7)
    res = {}
    for lab, x in preds.items():
        r_rv, r_wp = spearman(x, y_rv), spearman(x, y_wp)
        bs = []
        for _ in range(1000):
            s = [random.randrange(len(ids)) for _ in ids]
            bs.append(spearman([x[i] for i in s], [y_rv[i] for i in s]))
        bs.sort()
        res[lab] = {'rho_vs_2025_26_pressure_RV': round(r_rv, 3), 'ci90': [round(bs[50], 3), round(bs[949], 3)],
                    'rho_vs_2025_26_pressure_WPA': round(r_wp, 3)}
    order = sorted(range(len(ids)), key=lambda i: -preds['Our composite (2022-24 only)'][i])
    topq = order[:max(len(ids) // 4, 1)]; rest = order[len(topq):]
    res['components'] = {lab: round(spearman([float(pre[p][f'z{k + 1}']) for p in ids], y_rv), 3)
                         for k, lab in enumerate(['C1 WPA', 'C2 pressure RV', 'C3 clutch', 'C4 consistency'])}
    res['top_quarter_by_composite_mean_2025_26_RV'] = round(sum(y_rv[i] for i in topq) / len(topq), 4)
    res['other_three_quarters_mean_2025_26_RV'] = round(sum(y_rv[i] for i in rest) / len(rest), 4)
    res['players_tested'] = len(ids)
    oos[role] = res
log['D_out_of_sample'] = {'design': f'rated on 2022-24 live balls only; tested on players with >= {MIN_TEST} '
                                    'pressure balls in 2025-26. The win-probability model itself was fitted on '
                                    'all seasons (context model only, no player terms).', **oos}

# ------------------------------------------------------------ E. confidence tier per top-10 player
# C2 (pressure run value shrunk toward the player's own baseline) is the component that carried forward
# out of sample; players also top-10 on C2 alone are 'Core', the rest lean on the clutch / consistency parts.
tiers = {}
for role in ('bat', 'bowl'):
    rows = read_csv(os.path.join(OUT, f'rank_{role}_main.csv'))
    c2 = {r['player_id']: i + 1 for i, r in enumerate(sorted(rows, key=lambda r: -float(r['z2'])))}
    fin = {r['player_id']: r for r in read_csv(os.path.join(OUT, f'FINAL_{role}.csv'))}
    tiers[role] = [{'rank': f['final_rank'], 'player': f['player'], 'C2_rank': c2[f['player_id']],
                    'boot_p_top10': float(fin[f['player_id']]['ens_boot_p_top10']),
                    'all_leave_one_out': f['player'] in rob[role]['in_top10_under_every_leave_one_out'],
                    'tier': 'Core' if c2[f['player_id']] <= 10 else 'Clutch-dependent'} for f in final[role]]
log['E_tiers'] = tiers

json.dump(log, open(os.path.join(OUT, 'audit.json'), 'w'), indent=1)
print(json.dumps(log, indent=1))
