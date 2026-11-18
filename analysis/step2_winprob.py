"""STEP 2 - Run-resource curve (Duckworth-Lewis form), win-probability model, Leverage Index,
per-ball Win Probability Added (WPA) and Run Value (RV).

  R(u,w) = Z0(w) * (1 - exp(-b(w) * u))   expected further runs with u balls left, w wickets lost
           (fitted on first innings, runs normalised to a common scoring environment)
  WP (chasing side)  = logistic(features of R*scale - runs needed)   -> IRLS, chosen by 5-fold grouped CV
  WP (batting first) = logistic(features of projected total vs environment par)
  LI  = E_next-ball |dWP| / mean(E|dWP|)  (Tango's Leverage Index)
  RV  = runs + R(after) - R(before)   (run value: runs scored minus resource consumed, wickets priced in)
"""
import sys, os, math, json, random, collections as C
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *

OUT = sys.argv[1]
balls = read_csv(os.path.join(OUT, 'balls_clean.csv'))
INT = ['innings', 'over', 'legal', 'faced', 'bat_runs', 'extras', 'bowler_runs', 'wicket', 'bowler_wkt',
       'score', 'wkts', 'balls_bowled', 'balls_left', 'max_balls', 'dots_streak', 'wkts_last12', 'season']
for b in balls:
    for k in INT:
        b[k] = int(b[k])
    b['par'] = float(b['par'])
    b['target'] = int(b['target']) if b['target'] != '' else None
    b['y'] = float(b['y_bat_win']) if b['y_bat_win'] != '' else None
GLOB = 175.4
log = {}

# ------------------------------------------------------------------ 1. resource curve
final1 = {}
for b in balls:
    if b['innings'] == 1:
        final1[b['match_id']] = b['score'] + b['bat_runs'] + b['extras']
pts = C.defaultdict(list)
for b in balls:
    if b['innings'] == 1 and b['max_balls'] == 120 and b['wkts'] < 10:
        rem = (final1[b['match_id']] - b['score']) * GLOB / b['par']
        pts[b['wkts']].append((b['balls_left'], rem))
Z0, BB = {}, {}
for w in range(10):
    best = None
    for i in range(1, 400):
        bb = i * 0.00025
        g = [1 - math.exp(-bb * u) for u, _ in pts[w]]
        z = sum(gi * r for gi, (_, r) in zip(g, pts[w])) / sum(gi * gi for gi in g)
        sse = sum((r - z * gi) ** 2 for gi, (_, r) in zip(g, pts[w]))
        if best is None or sse < best[0]:
            best = (sse, z, bb)
    Z0[w], BB[w] = best[1], best[2]

def R_raw(u, w):
    if w >= 10 or u <= 0:
        return 0.0
    return Z0[w] * (1 - math.exp(-BB[w] * u))
# enforce monotonicity in wickets (more wickets lost can never mean more expected runs):
# weighted isotonic regression (Pool-Adjacent-Violators, Ayer et al. 1955) for every u
def pava_dec(vals, wts):
    blocks = [[v, wt, 1] for v, wt in zip(vals, wts)]
    i = 0
    while i < len(blocks) - 1:
        if blocks[i][0] < blocks[i + 1][0]:
            v1, w1, c1 = blocks[i]; v2, w2, c2 = blocks[i + 1]
            blocks[i] = [(v1 * w1 + v2 * w2) / (w1 + w2), w1 + w2, c1 + c2]
            del blocks[i + 1]
            i = max(i - 1, 0)
        else:
            i += 1
    out = []
    for v, _, c in blocks:
        out += [v] * c
    return out
RT = {}
for u in range(0, 121):
    iso = pava_dec([R_raw(u, w) for w in range(10)], [len(pts[w]) for w in range(10)])
    for w in range(10):
        RT[(u, w)] = iso[w]
def R(u, w):
    if w >= 10 or u <= 0:
        return 0.0
    return RT[(min(u, 120), w)]
log['resource_curve'] = {w: {'Z0': round(Z0[w], 1), 'b': BB[w], 'n': len(pts[w]), 'R(120)': round(R(120, w), 1),
                              'R(60)': round(R(60, w), 1), 'R(24)': round(R(24, w), 1)} for w in range(10)}

# ------------------------------------------------------------------ 2. win probability
def feats2(need, u, w, scale, fs):
    Rv = R(u, w) * scale
    d = Rv - need
    if fs == 'A':
        return [1.0, d / math.sqrt(Rv + 1)]
    if fs == 'B':
        return [1.0, d / math.sqrt(Rv + 1), d / scale / 10, (10 - w) / 10]
    return [1.0, d / math.sqrt(Rv + 1), d / scale / 10, (10 - w) / 10, need / max(u, 1) / 2]

def feats1(score, u, w, par, max_balls, fs):
    scale = par / GLOB
    Rv = R(u, w) * scale
    proj = score + Rv
    full = R(max_balls, 0) * scale
    d = (proj - par * full / (R(120, 0) * scale)) / 10
    frac = Rv / max(full, 1)
    if fs == 'A':
        return [1.0, d]
    if fs == 'B':
        return [1.0, d, d * frac]
    return [1.0, d, d * frac, (10 - w) / 10 * frac]

def mk2(b, fs):
    return feats2(b['target'] - b['score'], b['balls_left'], b['wkts'], b['par'] / GLOB, fs)

def mk1(b, fs):
    return feats1(b['score'], b['balls_left'], b['wkts'], b['par'], b['max_balls'], fs)

train1 = [b for b in balls if b['innings'] == 1 and b['y'] is not None and b['legal']]
train2 = [b for b in balls if b['innings'] == 2 and b['y'] is not None and b['legal']
          and b['target'] - b['score'] > 0 and b['balls_left'] > 0 and b['wkts'] < 10]
mids = sorted(set(b['match_id'] for b in train1 + train2))
random.seed(7)
random.shuffle(mids)
fold = {m: i % 5 for i, m in enumerate(mids)}

def cv(rows, mk, fs):
    ll = br = n = 0
    for k in range(5):
        tr = [r for r in rows if fold[r['match_id']] != k]
        te = [r for r in rows if fold[r['match_id']] == k]
        beta = logistic_irls([mk(r, fs) for r in tr], [r['y'] for r in tr])
        l, bb = logloss_brier([mk(r, fs) for r in te], [r['y'] for r in te], beta)
        ll += l * len(te); br += bb * len(te); n += len(te)
    return ll / n, br / n

cvres = {}
for name, rows, mk in [('inn1', train1, mk1), ('inn2', train2, mk2)]:
    base = sum(r['y'] for r in rows) / len(rows)
    bl = -sum(r['y'] * math.log(base) + (1 - r['y']) * math.log(1 - base) for r in rows) / len(rows)
    bb = sum((base - r['y']) ** 2 for r in rows) / len(rows)
    cvres[name] = {'baseline_logloss': round(bl, 4), 'baseline_brier': round(bb, 4)}
    for fs in 'ABC':
        l, b_ = cv(rows, mk, fs)
        cvres[name][fs] = {'logloss': round(l, 4), 'brier': round(b_, 4)}
        print(name, fs, l, b_, flush=True)
best1 = min('ABC', key=lambda f: cvres['inn1'][f]['logloss'])
best2 = min('ABC', key=lambda f: cvres['inn2'][f]['logloss'])
beta1 = logistic_irls([mk1(r, best1) for r in train1], [r['y'] for r in train1])
beta2 = logistic_irls([mk2(r, best2) for r in train2], [r['y'] for r in train2])
log['wp_cv'] = cvres
log['wp_choice'] = {'inn1': best1, 'inn2': best2, 'beta1': beta1, 'beta2': beta2}

def wp2(need, u, w, scale):
    if need <= 0:
        return 1.0
    if w >= 10 or u <= 0:
        return 0.5 if need == 1 else 0.0
    return sigmoid(sum(a * c for a, c in zip(beta2, feats2(need, u, w, scale, best2))))

def wp1(score, u, w, par, mb):
    return sigmoid(sum(a * c for a, c in zip(beta1, feats1(score, u, w, par, mb, best1))))

def wp_state(b, runs_add, wk_add, ball_add):
    """batting-side WP after adding runs/wickets/legal ball to the pre-delivery state of b."""
    s, w, u = b['score'] + runs_add, b['wkts'] + wk_add, b['balls_left'] - ball_add
    if b['innings'] == 1:
        if w >= 10:
            u = 0
        return wp1(s, max(u, 0), min(w, 10), b['par'], b['max_balls'])
    return wp2(b['target'] - s, u, w, b['par'] / GLOB)

# calibration table (deciles) on full data
cal = []
for name, rows, f in [('inn1', train1, lambda r: wp_state(r, 0, 0, 0)), ('inn2', train2, lambda r: wp_state(r, 0, 0, 0))]:
    pr = sorted((f(r), r['y']) for r in rows)
    n = len(pr)
    for d in range(10):
        seg = pr[d * n // 10:(d + 1) * n // 10]
        cal.append({'innings': name, 'decile': d + 1, 'pred': round(sum(p for p, _ in seg) / len(seg), 3),
                    'obs': round(sum(t for _, t in seg) / len(seg), 3)})
log['calibration'] = cal

# ------------------------------------------------------------------ 3. next-ball outcome distribution (by phase & innings)
def phase(o):
    return 'PP' if o <= 6 else ('MID' if o <= 15 else 'DEATH')
dist = C.defaultdict(C.Counter)
for b in balls:
    key = (b['innings'], phase(b['over']))
    if not b['legal']:
        o = ('X', b['bat_runs'] + b['extras'], b['wicket'])  # illegal delivery
    else:
        o = ('L', b['bat_runs'] + b['extras'], b['wicket'])
    dist[key][o] += 1
distp = {k: [(o, c / sum(v.values())) for o, c in v.items()] for k, v in dist.items()}

# ------------------------------------------------------------------ 4. per-ball WP, LI, WPA, RV
el = []
for b in balls:
    wp0 = wp_state(b, 0, 0, 0)
    e = 0.0
    for (t, r, wk), p in distp[(b['innings'], phase(b['over']))]:
        e += p * abs(wp_state(b, r, wk, 1 if t == 'L' else 0) - wp0)
    b['wp0'] = wp0
    b['exp_swing'] = e
    el.append(e)
mean_swing = sum(el) / len(el)
for b in balls:
    b['LI'] = b['exp_swing'] / mean_swing
    lb = b['legal']
    # batter attribution: bat runs + striker's own dismissal
    bwk = 1 if (b['wicket'] and b['dismissed_id'] == b['striker_id']) else 0
    b['wpa_bat'] = wp_state(b, b['bat_runs'], bwk, lb) - b['wp0'] if b['faced'] else 0.0
    # bowler attribution: runs charged to bowler + bowler's wickets (credited to bowling side)
    b['wpa_bowl'] = -(wp_state(b, b['bowler_runs'], b['bowler_wkt'], lb) - b['wp0'])
    scale = b['par'] / GLOB
    u, w = b['balls_left'], b['wkts']
    # run value in normalised runs
    rv_b = (b['bat_runs'] / scale) + R(u - lb, w + bwk) - R(u, w) if b['faced'] else 0.0
    rv_w = (b['bowler_runs'] / scale) + R(u - lb, w + b['bowler_wkt']) - R(u, w)
    b['rv_bat'] = rv_b
    b['rv_bowl'] = -rv_w   # positive = good for bowler
log['mean_expected_swing'] = mean_swing

# LI distribution
lis = sorted(b['LI'] for b in balls)
log['LI_quantiles'] = {q: round(lis[int(q / 100 * (len(lis) - 1))], 3) for q in (5, 25, 50, 75, 80, 90, 95, 99)}

keep = ['match_id', 'innings', 'ctype', 'season', 'knock_out', 'bat_team', 'bowl_team', 'striker_id', 'striker_name',
        'bowler_id', 'bowler_name', 'dismissed_id', 'over', 'legal', 'faced', 'bat_runs', 'extras', 'bowler_runs',
        'wicket', 'bowler_wkt', 'score', 'wkts', 'balls_left', 'target', 'dots_streak', 'wkts_last12', 'par',
        'pace_spin', 'wp0', 'LI', 'wpa_bat', 'wpa_bowl', 'rv_bat', 'rv_bowl']
for b in balls:
    for k in ('wp0', 'LI', 'wpa_bat', 'wpa_bowl', 'rv_bat', 'rv_bowl'):
        b[k] = round(b[k], 6)
write_csv(os.path.join(OUT, 'balls_model.csv'), [{k: b[k] for k in keep} for b in balls], keep)
json.dump(log, open(os.path.join(OUT, 'step2_log.json'), 'w'), indent=1)
print(json.dumps({k: v for k, v in log.items() if k != 'calibration'}, indent=1))
for c in cal:
    print(c)
