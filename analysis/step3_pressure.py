"""STEP 3 - Pressure definition and validation.

Pressure Index (PI) per delivery = Leverage Index (expected next-ball win-probability swing / average swing).
It responds jointly to required rate, wickets in hand, balls left, innings stage and closeness of the contest.
High-pressure = LI >= 1.5 (Tango tiers). A 2-component Gaussian mixture (EM) on log(LI) identifies 'dead'
balls (result effectively decided) which are excluded from both pressure and baseline samples.
We also test whether 'scoreboard-psychology' signals (dot-ball streak, wickets in last 12 balls) shift
outcomes beyond LI, and fold them in only if the data says they matter.
"""
import sys, os, math, json, collections as C
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *

OUT = sys.argv[1]
balls = read_csv(os.path.join(OUT, 'balls_model.csv'))
for b in balls:
    for k in ('innings', 'over', 'legal', 'faced', 'bat_runs', 'extras', 'bowler_runs', 'wicket', 'bowler_wkt',
              'wkts', 'balls_left', 'dots_streak', 'wkts_last12', 'season', 'knock_out'):
        b[k] = int(b[k])
    for k in ('LI', 'wp0', 'wpa_bat', 'wpa_bowl', 'rv_bat', 'rv_bowl'):
        b[k] = float(b[k])
log = {}

# ---------------- EM for 2-component Gaussian mixture on log LI
x = [math.log(max(b['LI'], 1e-3)) for b in balls]
xs = sorted(x)
mu = [xs[len(xs) // 4], xs[3 * len(xs) // 4]]
sd = [0.5, 0.5]
pi = [0.5, 0.5]
for it in range(300):
    # E
    resp = []
    for v in x:
        p = [pi[k] / (sd[k] * math.sqrt(2 * math.pi)) * math.exp(-0.5 * ((v - mu[k]) / sd[k]) ** 2) for k in (0, 1)]
        s = sum(p) or 1e-300
        resp.append(p[1] / s)
    # M
    n1 = sum(resp); n0 = len(x) - n1
    mu_new = [sum((1 - r) * v for r, v in zip(resp, x)) / n0, sum(r * v for r, v in zip(resp, x)) / n1]
    sd = [math.sqrt(sum((1 - r) * (v - mu_new[0]) ** 2 for r, v in zip(resp, x)) / n0),
          math.sqrt(sum(r * (v - mu_new[1]) ** 2 for r, v in zip(resp, x)) / n1)]
    pi = [n0 / len(x), n1 / len(x)]
    if max(abs(a - c) for a, c in zip(mu, mu_new)) < 1e-7:
        mu = mu_new
        break
    mu = mu_new
hi = 1 if mu[1] > mu[0] else 0
post = [r if hi == 1 else 1 - r for r in resp]
# The EM split separates 'live' balls from 'dead' balls (result effectively decided, LI ~ 0),
# not pressure from normal (a 3-component fit gave overlapping middle components).
# Dead balls are therefore excluded from BOTH pressure and baseline samples.
log['gmm'] = {'mu_logLI': mu, 'sd': sd, 'pi': pi, 'iterations': it + 1,
              'dead_component_LI_centre': round(math.exp(min(mu)), 4)}

# Only the LOW side of the broad component is 'dead' (that component also spans the extreme-high tail).
live_centre = math.exp(max(mu))
mean_inn = {i: sum(b['LI'] for b in balls if b['innings'] == i) / sum(1 for b in balls if b['innings'] == i) for i in (1, 2)}
log['mean_raw_LI_by_innings'] = {i: round(v, 4) for i, v in mean_inn.items()}
# Single global LI scale. Innings-relative scaling was tested and rejected: within the first innings the
# highest-LI balls are over-1 balls at 0 wkts (wicket cost of the resource curve), not pressure situations.
# Within-innings top-decile is kept only as a sensitivity definition ('PI_alt').
HIGH, LOW = 1.5, 0.85   # Tango's leverage tiers: high >= 1.5, low < 0.85
inn_cut = {}
for i in (1, 2):
    s = sorted(b['LI'] for b in balls if b['innings'] == i)
    inn_cut[i] = s[int(0.9 * len(s))]
log['alt_top_decile_cut'] = inn_cut
for b, p in zip(balls, post):
    b['p_live'] = p
    b['dead'] = int(p < 0.5 and b['LI'] < live_centre)
    b['PI'] = b['LI']
    b['PI_alt'] = int(b['LI'] >= inn_cut[b['innings']] and not b['dead'])
    b['tier'] = 'dead' if b['dead'] else ('high' if b['PI'] >= HIGH else ('low' if b['PI'] < LOW else 'medium'))
    b['pressure'] = int(b['tier'] == 'high')
tiers = C.Counter(b['tier'] for b in balls)
log['tier_share'] = {k: round(v / len(balls), 4) for k, v in tiers.items()}
log['tier_share_by_innings'] = {i: {k: round(sum(1 for b in balls if b['innings'] == i and b['tier'] == k) /
                                    sum(1 for b in balls if b['innings'] == i), 4) for k in tiers} for i in (1, 2)}
dead_pi = sorted(b['LI'] for b in balls if b['dead'])
log['dead_LI_max'] = round(dead_pi[-1], 4)
log['pressure_share'] = round(sum(b['pressure'] for b in balls) / len(balls), 4)

# ---------------- does pressure change outcomes? league-wide contrast
def summ(rows):
    f = [r for r in rows if r['faced']]
    lg = [r for r in rows if r['legal']]
    n = len(f)
    return {'balls': n, 'SR': round(100 * sum(r['bat_runs'] for r in f) / n, 2),
            'out_pct': round(100 * sum(1 for r in f if r['wicket'] and r['dismissed_id'] == r['striker_id']) / n, 3),
            'dot_pct': round(100 * sum(1 for r in lg if r['bat_runs'] + r['extras'] == 0) / len(lg), 2),
            'boundary_pct': round(100 * sum(1 for r in f if r['bat_runs'] in (4, 6)) / n, 2),
            'econ': round(6 * sum(r['bowler_runs'] for r in rows) / len(lg), 3),
            'mean_LI': round(sum(r['LI'] for r in rows) / len(rows), 3)}
contrast = {t: summ([b for b in balls if b['tier'] == t]) for t in ('high', 'medium', 'low', 'dead')}
def phase(o):
    return 'PP' if o <= 6 else ('MID' if o <= 15 else 'DEATH')
by = {}
for inn in (1, 2):
    for ph in ('PP', 'MID', 'DEATH'):
        for p in (0, 1):
            rows = [b for b in balls if b['innings'] == inn and phase(b['over']) == ph and b['pressure'] == p and not b['dead']]
            if len(rows) > 200:
                by[f'inn{inn}-{ph}-{"P" if p else "N"}'] = summ(rows)
        # share of pressure balls by phase
        allr = [b for b in balls if b['innings'] == inn and phase(b['over']) == ph]
        by[f'inn{inn}-{ph}-share'] = round(sum(b['pressure'] for b in allr) / len(allr), 3)
log['contrast'] = contrast
log['by_phase'] = by

# ---------------- psychological signals: dismissal rate by dot-streak / recent wickets within LI strata
def rate(rows):
    f = [r for r in rows if r['faced']]
    return (sum(1 for r in f if r['wicket'] and r['dismissed_id'] == r['striker_id']) / len(f), len(f)) if f else (0, 0)
lq = sorted(b['PI'] for b in balls)
cuts = [lq[int(len(lq) * q)] for q in (0.25, 0.5, 0.75)]
def stratum(l):
    return sum(l > c for c in cuts)
psy = {}
for s in range(4):
    for name, cond in [('dots>=3', lambda b: b['dots_streak'] >= 3), ('dots<3', lambda b: b['dots_streak'] < 3),
                       ('wk12>=2', lambda b: b['wkts_last12'] >= 2), ('wk12<2', lambda b: b['wkts_last12'] < 2)]:
        r, n = rate([b for b in balls if stratum(b['PI']) == s and cond(b)])
        psy[f'LIq{s+1}-{name}'] = {'out_pct': round(100 * r, 3), 'n': n}
log['psychology'] = psy

# Mantel-Haenszel pooled odds ratio (1959) across LI strata: is a dot streak associated with dismissal?
def mh(cond):
    num = den = 0
    for s in range(4):
        rows = [b for b in balls if stratum(b['PI']) == s and b['faced']]
        a = sum(1 for b in rows if cond(b) and b['wicket'] and b['dismissed_id'] == b['striker_id'])
        bb = sum(1 for b in rows if cond(b)) - a
        c = sum(1 for b in rows if not cond(b) and b['wicket'] and b['dismissed_id'] == b['striker_id'])
        d = sum(1 for b in rows if not cond(b)) - c
        n = a + bb + c + d
        num += a * d / n; den += bb * c / n
    return num / den
log['MH_OR_dotstreak3'] = round(mh(lambda b: b['dots_streak'] >= 3), 3)
log['MH_OR_wk12_2'] = round(mh(lambda b: b['wkts_last12'] >= 2), 3)

# knockout matches
ko = [b for b in balls if b['knock_out'] == 1]
log['knockout'] = {'balls': len(ko), 'mean_LI': round(sum(b['LI'] for b in ko) / len(ko), 3),
                   'pressure_share': round(sum(b['pressure'] for b in ko) / len(ko), 3)}

for b in balls:
    b['p_live'] = round(b['p_live'], 5); b['PI'] = round(b['PI'], 5)
write_csv(os.path.join(OUT, 'balls_pressure.csv'), balls)
json.dump(log, open(os.path.join(OUT, 'step3_log.json'), 'w'), indent=1)
print(json.dumps(log, indent=1))
