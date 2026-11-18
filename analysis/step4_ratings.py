"""STEP 4 - Player ratings under pressure.

For every live delivery (dead balls excluded):
  * Opponent adjustment: ridge regression  rv = ctx + batter_i + bowler_j  fitted by backfitting
    (Gauss-Seidel coordinate updates; ridge lambda = balls-equivalent prior). Batter values are then
    corrected for the bowlers faced, bowler values for the batters bowled to.
  * Components (per player, on HIGH-pressure balls; baseline = live low/medium balls):
      C1  WPA per 100 pressure balls                (impact when it matters)
      C2  opponent-adjusted run value per ball      (quality under pressure, context-neutral)
      C3  clutch delta = C2(pressure) - C2(baseline) (rises vs dips relative to own usual level)
      C4  consistency = share of pressure innings with positive WPA (beta-binomial)
    C1-C3 shrunk by empirical-Bayes normal-normal (James-Stein / Efron-Morris), C4 by beta-binomial EB.
  * Composite = mean of z-scores. Cross-checks: Borda count, SMAA (random Dirichlet weights),
    Poisson bootstrap over matches (rank stability), split-half reliability (odd/even matches).
"""
import sys, os, math, json, random, collections as C
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *

OUT = sys.argv[1]
MODE = sys.argv[2] if len(sys.argv) > 2 else 'main'   # main | alt | ipl | recent | li2 | pre25 | min40 | min100
balls = read_csv(os.path.join(OUT, 'balls_pressure.csv'))
for b in balls:
    for k in ('innings', 'over', 'legal', 'faced', 'bat_runs', 'bowler_runs', 'wicket', 'bowler_wkt', 'season',
              'dead', 'PI_alt', 'knock_out'):
        b[k] = int(b[k])
    for k in ('rv_bat', 'rv_bowl', 'wpa_bat', 'wpa_bowl', 'PI'):
        b[k] = float(b[k])
live = [b for b in balls if not b['dead']]
if MODE == 'ipl':
    live = [b for b in live if b['ctype'] == 'IPL']
if MODE == 'pre25':   # out-of-sample test: rate on 2022-24 only, validated against 2025-26 in step7
    live = [b for b in live if b['season'] <= 2024]
for b in live:
    b['P'] = b['PI_alt'] if MODE == 'alt' else int(b['PI'] >= (2.0 if MODE == 'li2' else 1.5))
    b['w'] = 0.5 ** ((2026 - b['season']) / 2) if MODE == 'recent' else 1.0
log = {'mode': MODE, 'live_balls': len(live)}
name = {}
for b in balls:
    name[b['striker_id']] = b['striker_name']
    name[b['bowler_id']] = b['bowler_name']

# ------------------------------------------------------------ 1. opponent adjustment (backfitting ridge)
def phase(o):
    return 'PP' if o <= 6 else ('MID' if o <= 15 else 'DEATH')
fit = [b for b in live if b['faced']]
for b in fit:
    b['ctx'] = (b['ctype'], b['innings'], phase(b['over']))
LAM = 150.0
ctx = C.defaultdict(float); bat = C.defaultdict(float); bowl = C.defaultdict(float)
for it in range(500):
    s = C.defaultdict(float); n = C.Counter()
    for b in fit:
        s[b['ctx']] += b['rv_bat'] - bat[b['striker_id']] - bowl[b['bowler_id']]; n[b['ctx']] += 1
    ctx = {k: s[k] / n[k] for k in s}
    s = C.defaultdict(float); n = C.Counter()
    for b in fit:
        s[b['striker_id']] += b['rv_bat'] - ctx[b['ctx']] - bowl[b['bowler_id']]; n[b['striker_id']] += 1
    newbat = C.defaultdict(float, {k: s[k] / (n[k] + LAM) for k in s})
    s = C.defaultdict(float); n = C.Counter()
    for b in fit:
        s[b['bowler_id']] += b['rv_bat'] - ctx[b['ctx']] - newbat[b['striker_id']]; n[b['bowler_id']] += 1
    newbowl = C.defaultdict(float, {k: s[k] / (n[k] + LAM) for k in s})
    delta = max(max(abs(newbat[k] - bat[k]) for k in newbat), max(abs(newbowl[k] - bowl[k]) for k in newbowl))
    bat, bowl = newbat, newbowl
    if delta < 1e-7:
        break
log['backfit_iterations'] = it + 1
log['backfit_final_delta'] = delta
log['ridge_lambda'] = LAM
for b in live:
    # phase-neutral and opponent-adjusted (ctx = league mean for competition type / innings / phase)
    cx = ctx.get((b['ctype'], b['innings'], phase(b['over'])), 0.0)
    b['adj_bat'] = b['rv_bat'] - cx - bowl.get(b['bowler_id'], 0.0) if b['faced'] else 0.0
    b['adj_bowl'] = b['rv_bowl'] + cx + bat.get(b['striker_id'], 0.0)

# ------------------------------------------------------------ 2. per player / per match aggregates
def agg(role):
    """returns dict pid -> dict match -> [P_n, P_wpa, P_adj, P_adj2, B_n, B_adj, B_adj2, P_wpa_sum_for_consistency]"""
    D = C.defaultdict(lambda: C.defaultdict(lambda: [0.0] * 8))
    for b in live:
        if role == 'bat':
            if not b['faced']:
                continue
            pid, wpa, adj = b['striker_id'], b['wpa_bat'], b['adj_bat']
        else:
            pid, wpa, adj = b['bowler_id'], b['wpa_bowl'], b['adj_bowl']
        a = D[pid][b['match_id']]
        w = b['w']
        if b['P']:
            a[0] += w; a[1] += w * wpa; a[2] += w * adj; a[3] += w * adj * adj; a[7] += 1
        else:
            a[4] += w; a[5] += w * adj; a[6] += w * adj * adj
    return D

def eb_normal(stats):
    """stats: pid -> (mean, n, per-ball variance). Method-of-moments EB shrinkage toward weighted mean."""
    ids = list(stats)
    W = sum(stats[p][1] for p in ids)
    mu = sum(stats[p][0] * stats[p][1] for p in ids) / W
    s2 = sum(stats[p][2] * stats[p][1] for p in ids) / W
    v = sum((stats[p][0] - mu) ** 2 for p in ids) / len(ids)
    tau2 = max(v - sum(s2 / stats[p][1] for p in ids) / len(ids), 1e-9)
    out = {}
    for p in ids:
        Bp = tau2 / (tau2 + s2 / stats[p][1])
        out[p] = (mu + Bp * (stats[p][0] - mu), Bp)
    return out, {'mu': mu, 'tau2': tau2, 'sigma2': s2}

def eb_beta(k_n):
    ids = list(k_n)
    ps = [k_n[p][0] / k_n[p][1] for p in ids]
    m = sum(ps) / len(ps)
    v = sum((x - m) ** 2 for x in ps) / len(ps)
    nbar = sum(k_n[p][1] for p in ids) / len(ids)
    # method of moments for beta-binomial with average n
    v_true = max(v - m * (1 - m) / nbar, 1e-6)
    s = max(m * (1 - m) / v_true - 1, 1.0)
    a, bb = m * s, (1 - m) * s
    m_post = a / (a + bb)
    return ({p: (k_n[p][0] + a) / (k_n[p][1] + a + bb) for p in ids},
            {'alpha': a, 'beta': bb, 'mu': m_post, 'tau2': m_post * (1 - m_post) / (a + bb + 1)})

def rate(D, pids, weights=None):
    """compute raw component inputs from per-match aggregates; weights: match -> multiplicity (bootstrap).
    pos[0] = pressure innings with positive WPA, pos[1] = with positive adjusted run value."""
    res = {}
    for p in pids:
        t = [0.0] * 8; pos = [0, 0]; inn = 0
        for m, a in D[p].items():
            w = 1 if weights is None else weights.get(m, 0)
            if w == 0:
                continue
            for i in range(8):
                t[i] += w * a[i]
            if a[7] >= 3:
                inn += w
                pos[0] += w * (a[1] > 0)
                pos[1] += w * (a[2] > 0)
        res[p] = (t, pos, inn)
    return res

CONS = {}   # role -> 0 (WPA-positive) or 1 (RV-positive); chosen by between-player signal on full data

def score(role, D, eligible, weights=None, wpa_var=None):
    """Hierarchical EB:
         baseline  b_i  shrunk to league mean (many balls)
         clutch    d_i = pressure - baseline, shrunk to league mean
         C2 pressure RV = b_i + d_i  (pressure estimate shrunk toward the player's OWN baseline)
       Each component standardised by its true-score SD sqrt(tau2) so components without
       between-player signal carry ~no weight (classical test theory)."""
    raw = rate(D, eligible, weights)
    ids = [p for p in eligible if raw[p][0][0] > 0 and raw[p][0][4] > 0 and raw[p][2] > 0]
    s1, sb, sd, s4 = {}, {}, {}, {}
    for p in ids:
        t, pos, inn = raw[p]
        mP = t[2] / t[0]; vP = max(t[3] / t[0] - mP * mP, 1e-6)
        mB = t[5] / t[4]; vB = max(t[6] / t[4] - mB * mB, 1e-6)
        s1[p] = (100 * t[1] / t[0], t[0], wpa_var[role])
        sb[p] = (mB, t[4], vB)
        sd[p] = (mP - mB, 1 / (1 / t[0] + 1 / t[4]), (vP + vB) / 2)
        s4[p] = (pos[CONS[role]], inn)
    c1, h1 = eb_normal(s1); cb, hb = eb_normal(sb); cd, hd = eb_normal(sd); c4, h4 = eb_beta(s4)
    comp = {p: [c1[p][0], cb[p][0] + cd[p][0], cd[p][0], c4[p]] for p in ids}
    centre = [h1['mu'], hb['mu'] + hd['mu'], hd['mu'], h4['mu']]
    tsd = [math.sqrt(h1['tau2']), math.sqrt(hb['tau2'] + hd['tau2']), math.sqrt(hd['tau2']), math.sqrt(h4['tau2'])]
    z = {p: [(comp[p][k] - centre[k]) / tsd[k] for k in range(4)] for p in ids}
    total = {p: sum(z[p]) / 4 for p in ids}
    return ids, comp, z, total, raw, {'C1': h1, 'baseline': hb, 'clutch': hd, 'C4': h4, 'true_sd': tsd}

# per-ball variance of WPA*100 on pressure balls
wpa_var = {}
for role, key, cond in [('bat', 'wpa_bat', lambda b: b['faced']), ('bowl', 'wpa_bowl', lambda b: True)]:
    v = [100 * b[key] for b in live if b['P'] and cond(b)]
    m = sum(v) / len(v)
    wpa_var[role] = sum((x - m) ** 2 for x in v) / len(v)
log['wpa_per_ball_var'] = wpa_var

recent_ids = set()
for b in balls:
    if b['season'] >= 2025:
        recent_ids.add(b['striker_id']); recent_ids.add(b['bowler_id'])

MIN_P_BALLS = {'min40': 40, 'min100': 100}.get(MODE, 60)   # 10 overs of high-pressure exposure
MIN_P_INN = 6      # pressure innings (>=3 pressure balls) to judge consistency
results = {}
for role in ('bat', 'bowl'):
    D = agg(role)
    raw_all = rate(D, list(D))
    # eligibility always on UNWEIGHTED pressure balls (t[7]) so every variant ranks the same kind of pool
    elig = [p for p, (t, pos, inn) in raw_all.items() if t[7] >= MIN_P_BALLS and inn >= MIN_P_INN and p in recent_ids]
    log[f'{role}_eligible'] = len(elig)
    log[f'{role}_excluded_inactive'] = sum(1 for p, (t, pos, inn) in raw_all.items()
                                           if t[7] >= MIN_P_BALLS and inn >= MIN_P_INN and p not in recent_ids)
    # choose consistency definition with more between-player signal (smaller beta-binomial prior strength)
    cons_test = {}
    for c in (0, 1):
        _, h = eb_beta({p: (raw_all[p][1][c], raw_all[p][2]) for p in elig})
        cons_test[['WPA_positive', 'RV_positive'][c]] = {'prior_strength': round(h['alpha'] + h['beta'], 2),
                                                          'true_sd': round(math.sqrt(h['tau2']), 4)}
    CONS[role] = min((0, 1), key=lambda c: list(cons_test.values())[c]['prior_strength'])
    log[f'{role}_consistency_test'] = cons_test
    log[f'{role}_consistency_choice'] = ['WPA_positive', 'RV_positive'][CONS[role]]
    ids, comp, z, total, raw, hyper = score(role, D, elig, wpa_var=wpa_var)
    log[f'{role}_hyper'] = hyper
    order = sorted(ids, key=lambda p: -total[p])
    rank = {p: i + 1 for i, p in enumerate(order)}

    # Borda count across the 4 component rankings
    borda = C.Counter()
    for k in range(4):
        for i, p in enumerate(sorted(ids, key=lambda p: -comp[p][k])):
            borda[p] += len(ids) - i
    borda_rank = {p: i + 1 for i, p in enumerate(sorted(ids, key=lambda p: -borda[p]))}

    # SMAA: random weights from flat Dirichlet
    random.seed(11)
    top10 = C.Counter(); rsum = C.Counter()
    NS = 4000
    for _ in range(NS):
        g = [random.expovariate(1) for _ in range(4)]; s = sum(g); w = [x / s for x in g]
        sc = sorted(ids, key=lambda p: -sum(wi * zi for wi, zi in zip(w, z[p])))
        for i, p in enumerate(sc):
            rsum[p] += i + 1
            if i < 10:
                top10[p] += 1
    smaa_top10 = {p: top10[p] / NS for p in ids}
    smaa_exp_rank = {p: rsum[p] / NS for p in ids}

    # Poisson bootstrap over matches
    mids = sorted(set(b['match_id'] for b in live))
    random.seed(5)
    bt10 = C.Counter(); brank = C.defaultdict(list)
    NB = 300
    for _ in range(NB):
        wts = {}
        for m in mids:
            # Poisson(1) draw
            L, k, p_ = math.exp(-1), 0, 1.0
            while True:
                p_ *= random.random()
                if p_ < L:
                    break
                k += 1
            wts[m] = k
        bids, _, _, btot, _, _ = score(role, D, elig, weights=wts, wpa_var=wpa_var)
        bo = sorted(bids, key=lambda p: -btot[p])
        for i, p in enumerate(bo):
            brank[p].append(i + 1)
            if i < 10:
                bt10[p] += 1
    boot = {}
    for p in ids:
        r = sorted(brank[p]) or [999]
        boot[p] = {'p_top10': bt10[p] / NB, 'rank_p05': r[int(0.05 * len(r))], 'rank_p95': r[min(int(0.95 * len(r)), len(r) - 1)],
                   'rank_median': r[len(r) // 2]}

    # split-half reliability (odd vs even matches) of pressure run value C2 and clutch delta C3
    def half(par):
        wts = {m: 1 if (int(m) % 2 == par) else 0 for m in mids}
        r = rate(D, elig, wts)
        out = {}
        for p, (t, pos, inn) in r.items():
            if t[0] >= 20 and t[4] >= 20:
                out[p] = (t[2] / t[0], t[2] / t[0] - t[5] / t[4], 100 * t[1] / t[0], t[5] / t[4])
        return out
    h0, h1 = half(0), half(1)
    common = [p for p in h0 if p in h1]
    def corr(a, b):
        ma, mb = sum(a) / len(a), sum(b) / len(b)
        num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
        return num / math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))
    rel = {}
    for k, lab in enumerate(['pressure_RV', 'clutch_delta', 'pressure_WPA', 'baseline_RV']):
        r = corr([h0[p][k] for p in common], [h1[p][k] for p in common])
        rel[lab] = {'split_half_r': round(r, 3), 'spearman_brown': round(2 * r / (1 + r), 3) if r > -1 else None, 'n': len(common)}
    log[f'{role}_reliability'] = rel

    # descriptive stats for report
    desc = C.defaultdict(lambda: C.Counter())
    for b in live:
        if role == 'bat' and not b['faced']:
            continue
        pid = b['striker_id'] if role == 'bat' else b['bowler_id']
        if pid not in rank:
            continue
        d = desc[pid]; key = 'P' if b['P'] else 'B'
        d[key + 'balls'] += 1
        d[key + 'legal'] += b['legal']
        d['matches_' + key] += 0
        if role == 'bat':
            d[key + 'runs'] += b['bat_runs']
            d[key + 'outs'] += int(b['wicket'] and b['dismissed_id'] == b['striker_id'])
            d[key + 'bnd'] += int(b['bat_runs'] in (4, 6))
            d[key + 'dots'] += int(b['bat_runs'] == 0)
        else:
            d[key + 'runs'] += b['bowler_runs']
            d[key + 'outs'] += b['bowler_wkt']
            d[key + 'dots'] += int(b['legal'] and b['bowler_runs'] == 0)
        if b['P']:
            d['ipl_P'] += b['ctype'] == 'IPL'
    pm = C.defaultdict(set)
    for b in live:
        if b['P'] and (b['faced'] or role == 'bowl'):
            pm[b['striker_id'] if role == 'bat' else b['bowler_id']].add(b['match_id'])
    rows = []
    for p in order:
        d = desc[p]
        r = {'rank': rank[p], 'player_id': p, 'player': name[p], 'composite': round(total[p], 4),
             'C1_WPA_per100': round(comp[p][0], 3), 'C2_adjRV_per_ball': round(comp[p][1], 4),
             'C3_clutch_delta': round(comp[p][2], 4), 'C4_consistency': round(comp[p][3], 3),
             'z1': round(z[p][0], 3), 'z2': round(z[p][1], 3), 'z3': round(z[p][2], 3), 'z4': round(z[p][3], 3),
             'borda_rank': borda_rank[p], 'smaa_p_top10': round(smaa_top10[p], 3), 'smaa_exp_rank': round(smaa_exp_rank[p], 2),
             'boot_p_top10': round(boot[p]['p_top10'], 3), 'boot_rank_90ci': f"{boot[p]['rank_p05']}-{boot[p]['rank_p95']}",
             'P_balls': d['Pballs'], 'P_innings': raw[p][2], 'P_matches': len(pm[p]), 'B_balls': d['Bballs'],
             'IPL_share_P': round(d['ipl_P'] / max(d['Pballs'], 1), 3)}
        if role == 'bat':
            r.update({'P_runs': d['Pruns'], 'P_SR': round(100 * d['Pruns'] / max(d['Pballs'], 1), 1),
                      'P_outs': d['Pouts'], 'P_avg': round(d['Pruns'] / d['Pouts'], 1) if d['Pouts'] else None,
                      'P_boundary_pct': round(100 * d['Pbnd'] / max(d['Pballs'], 1), 1),
                      'B_SR': round(100 * d['Bruns'] / max(d['Bballs'], 1), 1),
                      'B_avg': round(d['Bruns'] / d['Bouts'], 1) if d['Bouts'] else None})
        else:
            r.update({'P_runs_conceded': d['Pruns'], 'P_econ': round(6 * d['Pruns'] / max(d['Plegal'], 1), 2),
                      'P_wkts': d['Pouts'], 'P_balls_per_wkt': round(d['Plegal'] / d['Pouts'], 1) if d['Pouts'] else None,
                      'P_dot_pct': round(100 * d['Pdots'] / max(d['Plegal'], 1), 1),
                      'B_econ': round(6 * d['Bruns'] / max(d['Blegal'], 1), 2),
                      'B_balls_per_wkt': round(d['Blegal'] / d['Bouts'], 1) if d['Bouts'] else None})
        rows.append(r)
    write_csv(os.path.join(OUT, f'rank_{role}_{MODE}.csv'), rows)
    results[role] = rows
    print(f'=== {role} ({MODE}) eligible={len(ids)}')
    for r in rows[:15]:
        print(r['rank'], r['player'], r['composite'], 'z', r['z1'], r['z2'], r['z3'], r['z4'], 'borda', r['borda_rank'],
              'smaa', r['smaa_p_top10'], 'boot', r['boot_p_top10'], r['boot_rank_90ci'], 'Pballs', r['P_balls'],
              'IPL', r['IPL_share_P'])

json.dump(log, open(os.path.join(OUT, f'step4_log_{MODE}.json'), 'w'), indent=1)
print(json.dumps({k: v for k, v in log.items() if 'hyper' not in k}, indent=1))
