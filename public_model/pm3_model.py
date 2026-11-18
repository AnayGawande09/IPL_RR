"""PUBLIC MODEL 3 - a separate machine-learning model trained on all public IPL data (Cricsheet 2008-2026) plus
public auction history (2013-2025). It predicts each player's NEXT-season performance in pressure situations
(the model's own definition from pm1_parse.py). It never reads the SupeRR ratings except at the very end, where
its predictions are COMPARED with ours; nothing flows back into our lists.

Target (per player-season, pressure balls only):
  batting  value/ball = (runs - league avg) - c * (outs - league avg),  c = league runs per wicket on pressure balls
  bowling  value/ball = (league avg - runs conceded) + c * (wickets - league avg)
Features (all from seasons before the target season, recency-weighted, half-life 2 seasons) + auction features.
Models: ridge regression and gradient-boosted regression trees (pure Python), chosen by rolling-origin validation.
usage: python -I pm3_model.py <public_model/out> <auction_dir> <analysis/out>
"""
import sys, os, csv, math, json, random, collections as C

OUT, AUC, OURS = sys.argv[1], sys.argv[2], sys.argv[3]
rd = lambda p: list(csv.DictReader(open(p, encoding='utf-8')))
random.seed(3)

# ------------------------------------------------------------ per player-season aggregates
balls = rd(os.path.join(OUT, 'pm_balls.csv'))
S = C.defaultdict(lambda: C.Counter())       # (role, name, season) -> counts
L = C.defaultdict(lambda: C.Counter())       # (role, season, P) -> league counts
for b in balls:
    s, P = int(b['season']), int(b['pressure'])
    o = int(b['over'])
    if b['faced'] == '1':
        r, out = int(b['bat_runs']), int(b['batter_out'])
        for k in (('bat', b['batter'], s),):
            c = S[k]; c['n'] += 1; c['r'] += r; c['o'] += out; c['bnd'] += r in (4, 6); c['dot'] += r == 0; c['death'] += o >= 16
            if P:
                c['Pn'] += 1; c['Pr'] += r; c['Po'] += out
        for p_ in (0, P) if P else (0,):
            l = L[('bat', s, p_)]; l['n'] += 1; l['r'] += r; l['o'] += out
    r, wk = int(b['bowler_runs']), int(b['bowler_wkt'])
    c = S[('bowl', b['bowler'], s)]; c['n'] += 1; c['r'] += r; c['o'] += wk; c['dot'] += r == 0; c['death'] += o >= 16
    if P:
        c['Pn'] += 1; c['Pr'] += r; c['Po'] += wk
    for p_ in (0, P) if P else (0,):
        l = L[('bowl', s, p_)]; l['n'] += 1; l['r'] += r; l['o'] += wk

def value(role, s, n, r, o, P):
    """runs above league average per ball, wickets priced at league runs-per-wicket (pressure or all balls)."""
    if n == 0:
        return 0.0
    l = L[(role, s, P)]
    mr, mo, cst = l['r'] / l['n'], l['o'] / l['n'], l['r'] / max(l['o'], 1)
    v = (r / n - mr) - cst * (o / n - mo)
    return v if role == 'bat' else -v

# ------------------------------------------------------------ auction features
amap = {r['auction_name']: r['cricsheet_name'] for r in rd(os.path.join(AUC, 'player_id_map.csv'))}
auc = C.defaultdict(list)
yr_prices = C.defaultdict(list)
for r in rd(os.path.join(AUC, 'auction_history.csv')):
    y, pr = int(r['year']), float(r['price_paid_cr'] or 0)
    yr_prices[y].append(pr)
    if r['player_name'] in amap:
        auc[amap[r['player_name']]].append((y, pr))
def pct_rank(y, pr):
    v = yr_prices[y]
    return sum(x <= pr for x in v) / len(v)

FEATS = ['log_balls', 'val_all', 'val_P', 'log_Pballs', 'last_val_P', 'last_val_all', 'seasons', 'rate', 'bnd_or_dot',
         'out_or_wkt', 'played_last', 'death_share', 'log_price', 'price_pct', 'yrs_since_auction', 'has_auction']
seasons_of = C.defaultdict(set)
for (role, n, s) in S:
    seasons_of[(role, n)].add(s)

def features(role, name, t):
    hist = sorted(s for s in seasons_of[(role, name)] if s < t)
    if not hist:
        return None
    W = C.Counter(); vals = []
    for s in hist:
        w = 0.5 ** ((t - 1 - s) / 2); c = S[(role, name, s)]
        for k in ('n', 'r', 'o', 'bnd', 'dot', 'death', 'Pn', 'Pr', 'Po'):
            W[k] += w * c[k]
        W['wv'] += w * c['n'] * value(role, s, c['n'], c['r'], c['o'], 0)
        W['wvP'] += w * c['Pn'] * value(role, s, c['Pn'], c['Pr'], c['Po'], 1)
    last = S[(role, name, hist[-1])]
    a = [x for x in auc.get(name, []) if x[0] <= t]
    ay, apr = max(a) if a else (None, 0.0)
    return [math.log1p(W['n']), W['wv'] / max(W['n'], 1e-9), W['wvP'] / max(W['Pn'], 1e-9), math.log1p(W['Pn']),
            value(role, hist[-1], last['Pn'], last['Pr'], last['Po'], 1), value(role, hist[-1], last['n'], last['r'], last['o'], 0),
            len(hist), (100 * W['r'] / max(W['n'], 1e-9)) if role == 'bat' else (6 * W['r'] / max(W['n'], 1e-9)),
            (W['bnd'] if role == 'bat' else W['dot']) / max(W['n'], 1e-9), W['o'] / max(W['n'], 1e-9),
            int(hist[-1] == t - 1), W['death'] / max(W['n'], 1e-9),
            math.log1p(apr), pct_rank(ay, apr) if a else 0.0, (t - ay) if a else 0.0, int(bool(a))]

MIN_TARGET = 30
def dataset(role, t_lo, t_hi):
    X, y, w, ids = [], [], [], []
    for (rl, name, t), c in S.items():
        if rl != role or not (t_lo <= t <= t_hi) or c['Pn'] < MIN_TARGET:
            continue
        f = features(role, name, t)
        if f is None:
            continue
        X.append(f); y.append(value(role, t, c['Pn'], c['Pr'], c['Po'], 1)); w.append(min(c['Pn'], 200)); ids.append((name, t))
    return X, y, w, ids

# ------------------------------------------------------------ models (pure Python)
def standardise(X, ref=None):
    ref = ref or [(sum(col) / len(col), (sum((v - sum(col) / len(col)) ** 2 for v in col) / len(col)) ** 0.5 or 1.0) for col in zip(*X)]
    return [[(v - m) / s for v, (m, s) in zip(row, ref)] for row in X], ref

def solve(A, b):
    n = len(A); M = [A[i][:] + [b[i]] for i in range(n)]
    for i in range(n):
        p = max(range(i, n), key=lambda r: abs(M[r][i])); M[i], M[p] = M[p], M[i]
        for r in range(n):
            if r != i and M[i][i]:
                f = M[r][i] / M[i][i]
                for c in range(i, n + 1):
                    M[r][c] -= f * M[i][c]
    return [M[i][n] / M[i][i] for i in range(n)]

class Ridge:
    def __init__(self, lam=10.0):
        self.lam = lam
    def fit(self, X, y, w):
        Z, self.ref = standardise(X); k = len(Z[0]) + 1
        Zb = [[1.0] + r for r in Z]
        A = [[sum(w[i] * Zb[i][a] * Zb[i][b] for i in range(len(Zb))) + (self.lam * sum(w) / len(w) if a == b and a > 0 else 0)
              for b in range(k)] for a in range(k)]
        bb = [sum(w[i] * Zb[i][a] * y[i] for i in range(len(Zb))) for a in range(k)]
        self.beta = solve(A, bb); return self
    def predict(self, X):
        Z, _ = standardise(X, self.ref)
        return [self.beta[0] + sum(b * z for b, z in zip(self.beta[1:], r)) for r in Z]

class GBM:
    """gradient-boosted regression trees, squared loss, histogram splits (16 quantile bins), depth 3."""
    def __init__(self, rounds=150, lr=0.05, depth=3, min_w=60.0, bins=16):
        self.rounds, self.lr, self.depth, self.min_w, self.bins = rounds, lr, depth, min_w, bins
    def fit(self, X, y, w):
        nf = len(X[0])
        self.cuts = []
        for j in range(nf):
            v = sorted(r[j] for r in X)
            self.cuts.append(sorted(set(v[int(q * (len(v) - 1) / self.bins)] for q in range(1, self.bins))))
        B = [[self._bin(j, r[j]) for j in range(nf)] for r in X]
        self.f0 = sum(wi * yi for wi, yi in zip(w, y)) / sum(w)
        pred = [self.f0] * len(y); self.trees = []
        for _ in range(self.rounds):
            g = [yi - pi for yi, pi in zip(y, pred)]
            tree = self._grow(B, g, w, list(range(len(y))), 0)
            self.trees.append(tree)
            for i in range(len(y)):
                pred[i] += self.lr * self._eval(tree, B[i])
        return self
    def _bin(self, j, v):
        c = self.cuts[j]; lo = 0
        while lo < len(c) and v > c[lo]:
            lo += 1
        return lo
    def _grow(self, B, g, w, idx, d):
        W = sum(w[i] for i in idx); G = sum(w[i] * g[i] for i in idx)
        leaf = ('leaf', G / W if W else 0.0)
        if d == self.depth or W < 2 * self.min_w:
            return leaf
        best = None
        for j in range(len(B[0])):
            hw = [0.0] * (self.bins + 1); hg = [0.0] * (self.bins + 1)
            for i in idx:
                hw[B[i][j]] += w[i]; hg[B[i][j]] += w[i] * g[i]
            lw = lg = 0.0
            for k in range(self.bins):
                lw += hw[k]; lg += hg[k]
                rw, rg = W - lw, G - lg
                if lw < self.min_w or rw < self.min_w:
                    continue
                gain = lg * lg / lw + rg * rg / rw - G * G / W
                if best is None or gain > best[0]:
                    best = (gain, j, k)
        if best is None or best[0] <= 1e-12:
            return leaf
        _, j, k = best
        L_ = [i for i in idx if B[i][j] <= k]; R_ = [i for i in idx if B[i][j] > k]
        return ('split', j, k, self._grow(B, g, w, L_, d + 1), self._grow(B, g, w, R_, d + 1))
    def _eval(self, t, b):
        while t[0] == 'split':
            t = t[3] if b[t[1]] <= t[2] else t[4]
        return t[1]
    def predict(self, X):
        out = []
        for r in X:
            b = [self._bin(j, r[j]) for j in range(len(r))]
            out.append(self.f0 + self.lr * sum(self._eval(t, b) for t in self.trees))
        return out

class Naive:
    def fit(self, X, y, w):
        return self
    def predict(self, X):
        return [r[FEATS.index('val_P')] for r in X]

def rank(v):
    o = sorted(range(len(v)), key=lambda i: v[i]); r = [0.0] * len(v); i = 0
    while i < len(o):
        j = i
        while j + 1 < len(o) and v[o[j + 1]] == v[o[i]]:
            j += 1
        for t in range(i, j + 1):
            r[o[t]] = (i + j) / 2
        i = j + 1
    return r
def spearman(a, b):
    x, y = rank(a), rank(b); n = len(x); mx, my = sum(x) / n, sum(y) / n
    d = math.sqrt(sum((p - mx) ** 2 for p in x) * sum((q - my) ** 2 for q in y))
    return sum((p - mx) * (q - my) for p, q in zip(x, y)) / d if d else 0.0
def boot_ci(a, b, n=1000):
    rs = []
    for _ in range(n):
        s = [random.randrange(len(a)) for _ in a]
        rs.append(spearman([a[i] for i in s], [b[i] for i in s]))
    rs.sort(); return [round(rs[int(.05 * n)], 3), round(rs[int(.95 * n) - 1], 3)]

MODELS = {'naive (past pressure value)': lambda: Naive(), 'ridge': lambda: Ridge(10.0), 'gradient boosting': lambda: GBM()}
log = {'features': FEATS, 'min_target_pressure_balls': MIN_TARGET, 'roles': {}}

# ------------------------------------------------------------ rolling-origin validation (2016-2024)
choice = {}
for role in ('bat', 'bowl'):
    res = {m: [] for m in MODELS}
    for t in range(2016, 2025):
        Xtr, ytr, wtr, _ = dataset(role, 2009, t - 1); Xte, yte, wte, _ = dataset(role, t, t)
        for m, mk in MODELS.items():
            p = mk().fit(Xtr, ytr, wtr).predict(Xte)
            res[m].append(spearman(p, yte))
    summ = {m: round(sum(v) / len(v), 3) for m, v in res.items()}
    choice[role] = max(['ridge', 'gradient boosting'], key=lambda m: summ[m])
    log['roles'][role] = {'rolling_validation_mean_spearman_2016_2024': summ, 'per_season': {m: [round(x, 3) for x in v] for m, v in res.items()},
                          'chosen': choice[role], 'train_rows_all': len(dataset(role, 2009, 2026)[0])}
    print(role, summ, '->', choice[role])

# ------------------------------------------------------------ head-to-head on 2025-26 with SuperRR method
link = {r['cricsheet_name']: r['player_id'] for r in rd(os.path.join(OUT, 'pm_link.csv'))}
ours_bp = rd(os.path.join(OURS, 'balls_pressure.csv'))
for role in ('bat', 'bowl'):
    Xtr, ytr, wtr, _ = dataset(role, 2009, 2024)
    model = MODELS[choice[role]]().fit(Xtr, ytr, wtr)
    # model prediction as of end of 2024 for every player with history
    names = [n for (rl, n) in seasons_of if rl == role]
    feats = {n: features(role, n, 2025) for n in names}
    pm = dict(zip([n for n in names if feats[n]], model.predict([feats[n] for n in names if feats[n]])))
    # truth A: model definition, IPL 2025-26 combined (Cricsheet)
    tA = {}
    for n in names:
        c = S[(role, n, 2025)] + S[(role, n, 2026)]
        if c['Pn'] >= MIN_TARGET:
            tA[n] = (c['Pn'] * value(role, 2025, S[(role, n, 2025)]['Pn'], S[(role, n, 2025)]['Pr'], S[(role, n, 2025)]['Po'], 1) +
                     S[(role, n, 2026)]['Pn'] * value(role, 2026, S[(role, n, 2026)]['Pn'], S[(role, n, 2026)]['Pr'], S[(role, n, 2026)]['Po'], 1)) / c['Pn']
    # truth B: SuperRR definition (Leverage Index >= 1.5, live), IPL 2025-26, run value per ball
    tB = C.defaultdict(lambda: [0, 0.0])
    for b in ours_bp:
        if b['ctype'] != 'IPL' or int(b['season']) < 2025 or b['dead'] == '1' or float(b['PI']) < 1.5:
            continue
        if role == 'bat' and b['faced'] == '1':
            x = tB[b['striker_id']]; x[0] += 1; x[1] += float(b['rv_bat'])
        elif role == 'bowl':
            x = tB[b['bowler_id']]; x[0] += 1; x[1] += float(b['rv_bowl'])
    pre = {r['player_id']: float(r['composite']) for r in rd(os.path.join(OURS, f'rank_{role}_pre25.csv'))}
    common = [n for n in pm if n in link and link[n] in pre]
    h2h = {}
    for lab, truth, key in (('truth A: model pressure rule (Cricsheet)', tA, lambda n: n),
                            ('truth B: SuperRR Leverage-Index pressure (data pack)', {k: v[1] / v[0] for k, v in tB.items() if v[0] >= MIN_TARGET}, lambda n: link[n])):
        ids = [n for n in common if key(n) in truth]
        y = [truth[key(n)] for n in ids]
        a = [pm[n] for n in ids]; b = [pre[link[n]] for n in ids]
        h2h[lab] = {'players': len(ids),
                    'public_model': {'rho': round(spearman(a, y), 3), 'ci90': boot_ci(a, y)},
                    'superrr_method': {'rho': round(spearman(b, y), 3), 'ci90': boot_ci(b, y)},
                    'rho_between_methods': round(spearman(a, b), 3)}
    log['roles'][role]['head_to_head_2025_26'] = h2h
    print(role, json.dumps(h2h))

    # ------------------------------------------------------------ forward: IPL 2027 predictions
    Xall, yall, wall, _ = dataset(role, 2009, 2026)
    model27 = MODELS[choice[role]]().fit(Xall, yall, wall)
    if isinstance(model27, Ridge):
        imp = {f: round(b, 4) for f, b in zip(FEATS, model27.beta[1:])}
        log['roles'][role]['what_the_model_uses'] = {'kind': 'ridge coefficient per 1 SD of the feature', 'values': imp}
    else:
        cnt = C.Counter()
        def walk(t):
            if t[0] == 'split':
                cnt[FEATS[t[1]]] += 1; walk(t[3]); walk(t[4])
        for t in model27.trees:
            walk(t)
        tot = sum(cnt.values()) or 1
        log['roles'][role]['what_the_model_uses'] = {'kind': 'share of tree splits', 'values': {f: round(cnt[f] / tot, 3) for f in FEATS}}
    act = [n for n in names if S[(role, n, 2026)]['n'] > 0]
    elig = [n for n in act if sum(S[(role, n, s)]['Pn'] for s in seasons_of[(role, n)]) >= 60]
    f27 = [features(role, n, 2027) for n in elig]
    p27 = sorted(zip(elig, model27.predict(f27)), key=lambda x: -x[1])
    fin = {r['player_id']: int(r['final_rank']) for r in rd(os.path.join(OURS, f'FINAL_{role}.csv'))}
    from_link = {v: k for k, v in link.items()}
    top = []
    for i, (n, v) in enumerate(p27[:10]):
        pid = link.get(n)
        top.append({'rank': i + 1, 'cricsheet_name': n, 'player': None, 'player_id': pid, 'pred_value_per_ball': round(v, 4),
                    'our_final_rank': fin.get(pid)})
    ours10 = [r for r in rd(os.path.join(OURS, f'FINAL_{role}.csv'))[:10]]
    mrank = {link.get(n): i + 1 for i, (n, v) in enumerate(p27)}
    ours_in_model = [{'player': r['player'], 'our_rank': int(r['final_rank']),
                      'model_rank': mrank.get(r['player_id']), 'cricsheet_name': from_link.get(r['player_id'])} for r in ours10]
    both = [pid for pid in fin if pid in mrank]
    log['roles'][role]['forecast_2027'] = {
        'model_pool': len(elig), 'model_top10': top, 'our_top10_in_model': ours_in_model,
        'overlap_top10': sum(1 for t in top if t['player_id'] and t['player_id'] in {r['player_id'] for r in ours10}),
        'rank_corr_common_players': round(spearman([fin[p] for p in both], [mrank[p] for p in both]), 3), 'common_players': len(both)}
    print(role, 'overlap', log['roles'][role]['forecast_2027']['overlap_top10'], [t['cricsheet_name'] for t in top])

# readable names for the model's top-10 from the data pack where linked
pn = {}
for r in rd(os.path.join(OUT, 'pm_link.csv')):
    pn[r['player_id']] = r['player_name']
for role in ('bat', 'bowl'):
    for t in log['roles'][role]['forecast_2027']['model_top10']:
        t['player'] = pn.get(t['player_id'], t['cricsheet_name'])
json.dump(log, open(os.path.join(OUT, 'pm_results.json'), 'w', encoding='utf-8'), indent=1)
print('wrote pm_results.json')
