"""Build the methodology report (HTML with inline SVG charts) from pipeline outputs.
usage: python -I make_report.py <analysis/out> <report.html>"""
import sys, os, json, csv, html, collections as C
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from holdout_text import holdout_text, pm_verdict, pm_uses

OUT, DEST = sys.argv[1], sys.argv[2]
J = lambda f: json.load(open(os.path.join(OUT, f)))
R = lambda f: list(csv.DictReader(open(os.path.join(OUT, f), encoding='utf-8')))
s1, s2, s3 = J('step1_log.json'), J('step2_log.json'), J('step3_log.json')
s4 = J('step4_log_main.json')
rr = J('rr_fit.json')
au = J('audit.json')
ai_ = au['A_integrity']
TIER = {t['player']: t['tier'] for r in au['E_tiers'].values() for t in r}
CALL = {r['player']: r['call'] for r in J('rr_backlist.json')['rows']}
sens = J('sensitivity.json')
li2 = J('sensitivity_li2.json')
FB, FW = R('FINAL_bat.csv'), R('FINAL_bowl.csv')
BLR = J('rr_backlist.json')['rows']
def names(lst):
    lst = list(lst)
    return ', '.join(lst[:-1]) + (' and ' if len(lst) > 1 else '') + lst[-1] if lst else 'none'
names_or = lambda lst: names(lst).replace(' and ', ' or ')
STRONG = {r: [x['player'] for x in (FB if r == 'bat' else FW)[:10] if float(x['ens_boot_p_top10']) >= 0.7] for r in ('bat', 'bowl')}
RRP = [x for x in BLR if x['call'] == 'Retain']
THIN = [(x['player'], int(x['P_balls'])) for x in FB[:10] + FW[:10] if int(x['P_balls']) < 100]
UNTESTED = [x['player'] for x in BLR if 'IPL-untested' in x['flags']]
DEATH_B = [x['player'] for x in BLR if x['need'] == 'Death finisher' and x['call'].startswith('Back')]
PACE_B = [x['player'] for x in BLR if x['need'] == 'Pace' and x['call'].startswith('Back')]
SPIN_D = [x['player'] for x in BLR if x['need'] == 'Spin depth' and x['call'] == 'Depth option']
CLUTCH_B = [x['player'] for x in BLR if x['call'].startswith('Back') and 'clutch-dependent' in x['flags']]
RRP_TXT = names('%s (%s #%d)' % (x['player'], 'batting' if x['role'] == 'bat' else 'bowling', x['rank']) for x in RRP)
e = html.escape

BLUE, ORANGE, GREY, INK, INK2, MUTED, GRID = '#2a78d6', '#eb6834', '#9a9893', '#0b0b0b', '#52514e', '#7a7974', '#e4e3df'

# ---------- per-over pressure share (computed from the ball file)
share = {1: C.Counter(), 2: C.Counter()}; tot = {1: C.Counter(), 2: C.Counter()}
for b in csv.DictReader(open(os.path.join(OUT, 'balls_pressure.csv'), encoding='utf-8')):
    i, o = int(b['innings']), int(b['over'])
    tot[i][o] += 1
    share[i][o] += b['tier'] == 'high'
over_share = {i: [share[i][o] / tot[i][o] for o in range(1, 21)] for i in (1, 2)}
_li, _dead = [], [0, 0]
for b in csv.DictReader(open(os.path.join(OUT, 'balls_pressure.csv'), encoding='utf-8')):
    if b['dead'] == '1':
        _dead[1] += 1; _w = float(b['wp0']); _dead[0] += _w < 0.05 or _w > 0.95
    else:
        _li.append(float(b['PI']))
SHARE_LI2 = sum(x >= 2 for x in _li) / (len(_li) + _dead[1])
DEAD_DECIDED = _dead[0] / _dead[1]
CAL2 = max(abs(c['pred'] - c['obs']) for c in s2['calibration'] if c['innings'] == 'inn2')

# ---------- SVG helpers
def svg(w, h, body, label):
    return (f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="{e(label)}" '
            f'xmlns="http://www.w3.org/2000/svg" font-family="Inter, Segoe UI, Arial, sans-serif">{body}</svg>')

def t(x, y, s, size=11, fill=INK2, anchor='start', weight=400):
    return f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{fill}" text-anchor="{anchor}" font-weight="{weight}">{e(str(s))}</text>'

def hbar(rows, vmax, label, fmt=lambda v: f'{v:.0%}', color=BLUE, w=640):
    """horizontal bars: rows = [(name, value)]"""
    left, rh, top = 170, 24, 8
    h = top + rh * len(rows) + 22
    span = w - left - 60
    body = ''
    for k in range(0, 5):
        x = left + span * k / 4
        body += f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{h - 18}" stroke="{GRID}" stroke-width="1"/>'
        body += t(x, h - 4, fmt(vmax * k / 4), 10, MUTED, 'middle')
    for i, (n, v) in enumerate(rows):
        y = top + i * rh
        bw = max(span * v / vmax, 2)
        body += t(left - 8, y + 16, n, 11.5, INK, 'end')
        body += f'<rect x="{left}" y="{y + 5}" width="{bw:.1f}" height="14" rx="3" fill="{color}"/>'
        body += t(left + bw + 6, y + 16, fmt(v), 11, INK2)
    return svg(w, h, body, label)

def vbar(vals, labels, vmax, label, fmt, w=640, h=200, color=BLUE, ytitle=''):
    left, bot, top = 46, 30, 12
    n = len(vals); span = w - left - 10; bw = span / n
    body = ''
    for k in range(0, 5):
        y = h - bot - (h - bot - top) * k / 4
        body += f'<line x1="{left}" y1="{y:.1f}" x2="{w - 10}" y2="{y:.1f}" stroke="{GRID}"/>'
        body += t(left - 6, y + 4, fmt(vmax * k / 4), 10, MUTED, 'end')
    for i, v in enumerate(vals):
        x = left + i * bw + 2
        bh = (h - bot - top) * v / vmax
        body += f'<rect x="{x:.1f}" y="{h - bot - bh:.1f}" width="{bw - 4:.1f}" height="{max(bh, 0.5):.1f}" rx="3" fill="{color}"/>'
        body += t(x + (bw - 4) / 2, h - bot + 14, labels[i], 10, MUTED, 'middle')
    if ytitle:
        body += t(left, 9, ytitle, 10, MUTED)
    return svg(w, h, body, label)

def dumbbell(rows, lo, hi, label, unit, ticks, w=640):
    """rows = [(name, usual, pressure)]; grey = usual, blue = under pressure"""
    left, rh, top = 170, 26, 30
    h = top + rh * len(rows) + 38
    span = w - left - 70
    X = lambda v: left + span * (v - lo) / (hi - lo)
    body = (f'<circle cx="{left}" cy="12" r="5" fill="{GREY}"/>' + t(left + 9, 16, 'Usual (live, non-pressure balls)', 11, INK2) +
            f'<circle cx="{left + 230}" cy="12" r="5" fill="{BLUE}"/>' + t(left + 239, 16, 'Under pressure (LI ≥ 1.5)', 11, INK2))
    for v in ticks:
        body += f'<line x1="{X(v):.1f}" y1="{top - 4}" x2="{X(v):.1f}" y2="{h - 34}" stroke="{GRID}"/>'
        body += t(X(v), h - 20, f'{v:g}', 10, MUTED, 'middle')
    body += t(left + span / 2, h - 4, unit, 10, INK2, 'middle')
    for i, (n, a, b) in enumerate(rows):
        y = top + i * rh + 10
        body += t(left - 8, y + 4, n, 11.5, INK, 'end')
        body += f'<line x1="{X(a):.1f}" y1="{y}" x2="{X(b):.1f}" y2="{y}" stroke="{GREY}" stroke-width="2"/>'
        body += f'<circle cx="{X(a):.1f}" cy="{y}" r="5" fill="{GREY}" stroke="#fff" stroke-width="2"/>'
        body += f'<circle cx="{X(b):.1f}" cy="{y}" r="5.5" fill="{BLUE}" stroke="#fff" stroke-width="2"/>'
        body += t(max(X(a), X(b)) + 10, y + 4, f'{b:g} vs {a:g}', 10.5, INK2)
    return svg(w, h, body, label)

def calib():
    w, h, left, bot, top = 640, 260, 56, 34, 14
    side = h - bot - top
    X = lambda v: left + side * 1.9 * v
    Y = lambda v: h - bot - side * v
    body = ''
    for k in range(0, 6):
        v = k / 5
        body += f'<line x1="{X(0)}" y1="{Y(v):.1f}" x2="{X(1):.1f}" y2="{Y(v):.1f}" stroke="{GRID}"/>'
        body += t(left - 6, Y(v) + 4, f'{v:.0%}', 10, MUTED, 'end')
        body += t(X(v), h - bot + 14, f'{v:.0%}', 10, MUTED, 'middle')
    body += f'<line x1="{X(0)}" y1="{Y(0)}" x2="{X(1):.1f}" y2="{Y(1):.1f}" stroke="{MUTED}" stroke-dasharray="4 4"/>'
    body += t(X(0.62), Y(0.45), 'dashed = perfect calibration', 10, MUTED, 'start')
    for inn, col, lab in (('inn1', ORANGE, 'Batting first'), ('inn2', BLUE, 'Chasing')):
        pts = [(c['pred'], c['obs']) for c in s2['calibration'] if c['innings'] == inn]
        body += '<polyline fill="none" stroke="%s" stroke-width="2" points="%s"/>' % (col, ' '.join(f'{X(p):.1f},{Y(o):.1f}' for p, o in pts))
        for p, o in pts:
            body += f'<circle cx="{X(p):.1f}" cy="{Y(o):.1f}" r="4.5" fill="{col}" stroke="#fff" stroke-width="2"/>'
    body += f'<circle cx="{X(0.05)}" cy="22" r="5" fill="{BLUE}"/>' + t(X(0.05) + 9, 26, 'Chasing (decile)', 11)
    body += f'<circle cx="{X(0.05)}" cy="42" r="5" fill="{ORANGE}"/>' + t(X(0.05) + 9, 46, 'Batting first (decile)', 11)
    body += t(X(0.5), h - 4, 'Predicted win probability', 10.5, INK2, 'middle')
    body += f'<text transform="translate(14 {Y(0.5):.1f}) rotate(-90)" font-size="10.5" fill="{INK2}" text-anchor="middle">Observed win rate</text>'
    return svg(w + 60, h, body, 'Win probability calibration by decile')

def flow():
    steps = [('1  Data preprocessing', '200,999 deliveries → legal-ball rules, extras rebuilt, super overs removed, match state reconstructed, scoring era normalised'),
             ('2  Win-probability engine', 'Duckworth–Lewis resource curve + isotonic (PAVA) fix → logistic WP model (IRLS), chosen by 5-fold match-grouped CV'),
             ('3  Pressure definition', 'Leverage Index = expected next-ball WP swing; LI ≥ 1.5 = pressure; Gaussian mixture (EM) removes dead balls'),
             ('4  Per-ball value', 'Win Probability Added + Run Value (runs − resources consumed); ridge backfitting removes opponent & phase effects'),
             ('5  Player ratings', 'Empirical-Bayes (James–Stein) hierarchical shrinkage; 4 components on true-score scale'),
             ('6  Robust ranking', 'Composite → Borda & SMAA cross-checks → Poisson bootstrap → model average of 3 specifications → top 10')]
    w, bh, gap = 700, 52, 18
    h = len(steps) * (bh + gap)
    body = '<defs><marker id="ar" markerWidth="10" markerHeight="10" refX="5" refY="5" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="%s"/></marker></defs>' % MUTED
    for i, (a, b) in enumerate(steps):
        y = i * (bh + gap)
        body += f'<rect x="1" y="{y + 1}" width="{w - 2}" height="{bh}" rx="8" fill="#f3f6fb" stroke="{BLUE}" stroke-width="1.2"/>'
        body += t(20, y + 21, a, 13, INK, 'start', 600)
        body += t(20, y + 40, b, 10.8, INK2)
        if i < len(steps) - 1:
            body += f'<line x1="{w / 2}" y1="{y + bh + 2}" x2="{w / 2}" y2="{y + bh + gap - 3}" stroke="{MUTED}" stroke-width="1.5" marker-end="url(#ar)"/>'
    return svg(w, h, body, 'Pipeline flow chart')

# ---------- tables
def table(headers, rows, cls=''):
    th = ''.join(f'<th>{e(h)}</th>' for h in headers)
    tr = ''.join('<tr>' + ''.join(f'<td>{c}</td>' for c in r) + '</tr>' for r in rows)
    return f'<table class="{cls}"><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table>'

def f(v, d=2):
    if v in ('', None):
        return '–'
    try:
        x = round(float(v), d)
        return f'{(0.0 if x == 0 else x):.{d}f}'
    except ValueError:
        return e(str(v))

def pct(v):
    return f'{float(v) * 100:.0f}%'

top_b, top_w = FB[:10], FW[:10]

def cover_list(rows, role):
    li = ''
    for r in rows:
        flag = ' <span class="flag">thin sample</span>' if int(r['P_balls']) < 100 else ''
        flag += ' <span class="flag cl">clutch-dependent</span>' if TIER[r['player']] != 'Core' else ''
        stat = (f"SR {r['P_SR']} under pressure (usual {r['B_SR']})" if role == 'bat'
                else f"Econ {r['P_econ']} under pressure (usual {r['B_econ']})")
        li += f'<li><span class="rk">{r["final_rank"]}</span><span class="nm">{e(r["player"])}{flag}</span><span class="st">{stat} · <b>RR: {e(CALL[r["player"]])}</b></span></li>'
    return f'<ol class="cover">{li}</ol>'

ct = s3['contrast']
tier_rows = [(k.capitalize(), ct[k]) for k in ('dead', 'low', 'medium', 'high')]
rc = s2['resource_curve']
cv = s2['wp_cv']
hyb = s4  # main log

# evidence tables
bat_ev = [[r['final_rank'], e(r['player']), r['P_balls'], r['P_innings'], r['P_SR'], r['B_SR'], f(r['P_avg'], 1), f(r['B_avg'], 1),
           pct(r['IPL_share_P']), r['rank_main'], r['rank_ipl'] or '–', r['rank_recent'], pct(r['ens_boot_p_top10'])] for r in top_b]
bowl_ev = [[r['final_rank'], e(r['player']), r['P_balls'], r['P_innings'], r['P_econ'], r['B_econ'], f(r['P_balls_per_wkt'], 1),
            f(r['B_balls_per_wkt'], 1), r['P_wkts'], pct(r['IPL_share_P']), r['rank_main'], r['rank_ipl'] or '–', r['rank_recent'],
            pct(r['ens_boot_p_top10'])] for r in top_w]
def comp_rows(rows):
    return [[r['final_rank'], e(r['player']), f(r['ens_score'], 3), f(r['z1']), f(r['z2']), f(r['z3']), f(r['z4']),
             r['borda_rank'], pct(r['smaa_p_top10']), r['boot_rank_90ci']] for r in rows]
def next_rows(rows):
    return [[r['final_rank'], e(r['player']), f(r['ens_score'], 3), r['P_balls'], r['rank_main'], r['rank_ipl'] or '–', r['rank_recent'],
             pct(r['ens_boot_p_top10'])] for r in rows[10:20]]

rel = lambda role: [[k.replace('_', ' '), f(v['split_half_r'], 3), f(v['spearman_brown'], 3), v['n']] for k, v in s4[f'{role}_reliability'].items()]

envrows = [[k.split('-')[0], k.split('-')[1], s1['env_n'][k], s1['env_par'][k]] for k in s1['env_par']]

css = """
@page { size: A4; margin: 16mm 15mm 16mm 15mm; }
:root { --ink:#0b0b0b; --ink2:#52514e; --muted:#7a7974; --line:#e4e3df; --accent:#2a78d6; --bg:#ffffff; --soft:#f3f6fb; }
* { box-sizing: border-box; }
body { background: var(--bg); color: var(--ink); font-family: Inter, 'Segoe UI', Arial, sans-serif; font-size: 10.5pt; line-height: 1.5; margin: 0; }
h1 { font-size: 24pt; margin: 0 0 4pt; letter-spacing: -0.5px; }
h2 { font-size: 15pt; margin: 22pt 0 6pt; padding-bottom: 4pt; border-bottom: 2px solid var(--accent); break-after: avoid; }
h3 { font-size: 11.5pt; margin: 14pt 0 4pt; break-after: avoid; }
p { margin: 4pt 0 8pt; }
.sub { color: var(--ink2); font-size: 11pt; margin-bottom: 14pt; }
.lists { display: grid; grid-template-columns: 1fr 1fr; gap: 14pt; }
.card { border: 1px solid var(--line); border-radius: 8px; padding: 10pt 12pt; break-inside: avoid; }
.card h3 { margin-top: 0; color: var(--accent); }
ol.cover { list-style: none; padding: 0; margin: 0; }
ol.cover li { display: grid; grid-template-columns: 22pt 1fr; padding: 4pt 0; border-bottom: 1px solid var(--line); }
ol.cover li:last-child { border-bottom: 0; }
.rk { grid-row: span 2; font-weight: 700; font-size: 13pt; color: var(--accent); }
.nm { font-weight: 600; }
.st { color: var(--ink2); font-size: 9pt; }
.flag { font-size: 7.5pt; font-weight: 600; color: #8a4b00; background: #fff1dc; border-radius: 4px; padding: 0 4pt; margin-left: 4pt; }
table { border-collapse: collapse; width: 100%; margin: 6pt 0 10pt; font-size: 8.6pt; break-inside: avoid; }
th { text-align: left; background: var(--soft); color: var(--ink); font-weight: 600; padding: 4pt 5pt; border-bottom: 1px solid #c9d6ea; }
td { padding: 3.5pt 5pt; border-bottom: 1px solid var(--line); vertical-align: top; }
.kv td:first-child { width: 30%; font-weight: 600; }
figure { margin: 8pt 0 12pt; break-inside: avoid; }
figcaption { color: var(--ink2); font-size: 9pt; margin-top: 3pt; }
.box { background: var(--soft); border: 1px solid #d6e0ef; padding: 7pt 10pt; border-radius: 6px; margin: 8pt 0; break-inside: avoid; }
.warn { background: #fff7ea; border-color: #f0d9ad; }
.sum3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10pt; margin: 10pt 0; }
.sum3 .box { margin: 0; font-size: 9.2pt; }
.sum3 h4 { margin: 0 0 3pt; font-size: 10pt; color: var(--accent); }
.flag.cl { color: #5a4a8a; background: #eeeaf8; }
.pb { break-before: page; }
code { font-family: Consolas, monospace; font-size: 9pt; background: #f1f0ec; padding: 0 3pt; border-radius: 3px; }
.formula { font-family: Consolas, monospace; font-size: 9pt; background: #f7f7f5; padding: 6pt 9pt; border-radius: 4px; white-space: pre-wrap; break-inside: avoid; }
.small { font-size: 8.8pt; color: var(--ink2); }
"""

H = []
A = H.append
A(f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
  f'<title>Reliable Under Pressure</title><style>{css}</style></head><body>')

# ---------------- cover
A('<h1>Reliable Under Pressure</h1>')
A('<div class="sub">SupeRR Selector Season 2 · Round 1 methodology report · Who Rajasthan Royals should back at the IPL 2027 auction<br>'
  'Built only from the supplied data pack (IPL 2022–2026 and T20Is 2022–2026, 200,999 deliveries).</div>')
A('<div class="lists"><div class="card"><h3>Top 10 batters under pressure</h3>' + cover_list(top_b, 'bat') +
  '</div><div class="card"><h3>Top 10 bowlers under pressure</h3>' + cover_list(top_w, 'bowl') + '</div></div>')
nxt = lambda rows: ', '.join(f"{r['final_rank']}. {e(r['player'])}" for r in rows[10:15])
A(f'<p class="small"><b>Next in line</b> (ranks 11–15, close behind the top 10): batting {nxt(FB)}; bowling {nxt(FW)}.</p>')
close_w = sum(v.get('close_won', 0) for v in rr['rr_results'].values())
close_l = sum(v.get('close_lost', 0) for v in rr['rr_results'].values())
dth = rr['bat_pressure_phase']['Death (16-20)']
A(f'''<div class="sum3">
<div class="box"><h4>Methodology</h4>Pressure = <b>Leverage Index</b>: how much the next ball can swing the match win probability, from a
win-probability model fitted to this data (Duckworth–Lewis-style resource curve + logistic regression). LI ≥ 1.5 marks {s3["pressure_share"]:.1%}
of balls as pressure; already-decided games are excluded. Each ball is valued by win probability added and run value, adjusted for opponent and phase,
then rated with empirical-Bayes (James–Stein) shrinkage, so a lucky few overs cannot top the list.</div>
<div class="box"><h4>Most reliable under pressure</h4>The final order averages three specifications (all data, IPL-only, recency-weighted)
and is stress-tested with Borda, SMAA and a bootstrap over matches. Strongest calls (top 10 in at least 70% of resamples): <b>{names(STRONG['bat'])}</b> (batting); <b>{names(STRONG['bowl'])}</b> (bowling). A 2022–24 → 2025–26 holdout test shows underlying pressure quality
carries forward better than "clutch" lifts, so players ranked mainly on clutch parts are tagged <i>clutch-dependent</i> (Section 9.3).</div>
<div class="box"><h4>How they strengthen RR</h4>RR's biggest measured gap in IPL 2025–26 is <b>death-overs batting in pressure chases</b>
(SR {dth["RR"]["SR"]} vs {dth["Rest of IPL"]["SR"]} for the rest of the IPL), and RR won {close_w} and lost {close_l} close matches.
Death finishers ({names_or(DEATH_B)}) and pace bowlers ({names_or(PACE_B)}) fit RR's gaps most directly. The auction board on the next page gives each player a call.</div>
</div>''')
A('<p class="small">"Usual" = the same player on live, non-pressure balls. Thin sample = fewer than 100 pressure balls. '
  'Clutch-dependent = outside the top 10 on pressure run value alone (C2), so the rank leans on the clutch and consistency components.</p>')

# ---------------- RR auction board
bl = J('rr_backlist.json')
A('<h2 class="pb">Who Rajasthan Royals should back at the IPL 2027 auction</h2>')
n_out = sum(r['status'].startswith('Auction') for r in bl['rows'])
A(f'''<p>All 20 names come from the supplied data pack: players are rated from <code>ball_by_ball.csv</code>, and each player's 2026 team comes from
<code>competition_team_player_mapping.csv</code> (IPL 2026). No player was added from outside the data. {n_out} of the 20 play for other teams, so they are
auction targets. The other {20 - n_out} ({names(x['player'] for x in RRP)}) {'was' if len(RRP) == 1 else 'were'} in RR's 2026 squad. Each player gets one call from fixed rules:
the RR gap they fill (Section 8) and how firm their rating is (Section 9.3).</p>''')
CALL_TXT = {'Retain': 'Already RR. Keep if retention allows.',
            'Back - priority 1': 'Fills a measured RR gap, and the rating is firm.',
            'Back - priority 2': 'Fills a measured RR gap, but the rating is less firm.',
            'Depth option': 'Reliable under pressure, but in an area where RR are not short.',
            'Watch': 'Less certain: no IPL record, or a less firm rating in an area RR do not need most.'}
for c in bl['order']:
    rows = [r for r in bl['rows'] if r['call'] == c]
    if not rows:
        continue
    A(f'<h3>{e(c)} <span class="small" style="font-weight:400">· {e(CALL_TXT[c])}</span></h3>')
    A(table(['Player', 'List', 'Status', '2026 team', 'RR need it addresses', 'Rating', 'Flags'],
            [[f"<b>{e(r['player'])}</b>", f"{'Bat' if r['role'] == 'bat' else 'Bowl'} #{r['rank']}", e(r['status']), e(r['team_2026']),
              e(r['need']) + (' <b>(RR gap)</b>' if r['fills_gap'] else ''), r['tier'], e(', '.join(r['flags'])) or '–'] for r in rows]))
A('''<p class="small"><b>Rules.</b> Death finisher: at least 25% of the player's pressure balls came in overs 16–20. RR's measured gaps (Section 8) are
death-overs batting in pressure chases, plus pace strike rate and death-over dot balls. RR's pressure spin is already above league level. Priority 1 =
fills a gap + Core + at least 100 pressure balls + an IPL record. Price, availability and the official 2027 retention and auction lists are outside the data
and should be checked before bidding.</p>''')

# ---------------- flow
A('<h2 class="pb">1. Workflow</h2>')
A('<p>Six stages, each feeding the next. Every stage is a separate, re-runnable script (Section 10).</p>')
A('<figure>' + flow() + '<figcaption>Figure 1 – End-to-end pipeline from raw deliveries to the two ranked lists.</figcaption></figure>')
A('<h3>Techniques used and why</h3>')
A(table(['Technique (origin)', 'Where', 'Why this one'], [
    ['Duckworth–Lewis exponential resource curve (1998)', 'Stage 2', 'Prices balls and wickets in runs; refitted to this data, normalised for scoring era'],
    ['Isotonic regression / Pool-Adjacent-Violators (1955)', 'Stage 2', 'Forces expected runs never to rise as wickets fall, without imposing a shape'],
    ['Logistic regression via IRLS / Newton–Raphson', 'Stage 2', 'Calibrated win probabilities; feature set chosen by cross-validated log-loss'],
    ['Match-grouped 5-fold cross-validation', 'Stage 2', 'Prevents leakage between balls of the same match'],
    ['Leverage Index (Tom Tango, baseball sabermetrics)', 'Stage 3', 'One number for "how much is at stake" that combines required rate, wickets, balls left and closeness'],
    ['Gaussian mixture via EM (1977)', 'Stage 3', 'Data-driven detection of dead balls (match already decided)'],
    ['Mantel–Haenszel pooled odds ratio (1959)', 'Stage 3', 'Tests psychological signals (dot streaks, recent wickets) within leverage strata'],
    ['Win Probability Added & Run Value (expected-runs framework)', 'Stage 4', 'Values every ball for batter and bowler in the match context'],
    ['Ridge regression by backfitting (Hastie–Tibshirani)', 'Stage 4', 'Separates batter skill from bowler skill, so weak oppositions are discounted'],
    ['Empirical Bayes / James–Stein / Efron–Morris (1961/1975)', 'Stage 5', '<b>The old technique at the core.</b> Optimal shrinkage for noisy small-sample rates'],
    ['Beta-binomial empirical Bayes', 'Stage 5', 'Shrinks the "delivered in this pressure innings" proportion'],
    ['Classical test theory (true-score standardisation, Spearman–Brown)', 'Stage 5/8', 'Weights components by real signal; measures repeatability'],
    ['Borda count (1770)', 'Stage 6', 'Rank-vote cross-check of the composite'],
    ['SMAA – Stochastic Multicriteria Acceptability Analysis (1998)', 'Stage 6', 'Rarely used in sport: tests every possible component weighting'],
    ['Poisson bootstrap over matches (Efron 1979; Poisson variant)', 'Stage 6', 'Rank confidence intervals and P(top 10)'],
    ['Model averaging across specifications', 'Stage 6', 'Makes the final order robust to the data-scope choice'],
]))

# ---------------- preprocessing
A('<h2 class="pb">2. Data and preprocessing</h2>')
A(f'<p>Six files: ball_by_ball (200,999 rows), matches (883), competitions (141), teams, playing XIs and competition–team–player mappings. '
  f'After cleaning, {s1["modelled_deliveries"]:,} deliveries in {s1["innings"]:,} innings were modelled; {s1["matches_with_result"]} matches have a result usable for the win model.</p>')
A('<p>Every rule below was <b>checked against the data</b>, not assumed:</p>')
A(table(['Issue found', 'Evidence', 'Rule applied'], [
    ['Super-over innings (innings 3, 4)', '38 deliveries in 6 matches', 'Removed from modelling'],
    ['Abandoned matches', '16 matches with no deliveries', 'Nothing to remove; no-result matches excluded from win-model training'],
    ['Which deliveries are legal', 'With wide, Overstep and "other" excluded, 99.99% of completed overs (30,622 of 30,626, final over of each innings excluded) have exactly 6 legal balls', 'Illegal = wide, Overstep (no-ball), other'],
    ['<code>runs</code> holds bat runs only', 'Wides, byes and leg-byes always show runs = 0; "England won by 1 run" while raw sums differ by 5', 'Batter runs = <code>runs</code>; extras rebuilt separately'],
    ['Updated ball file (Nov 2026)', 'Same 200,999 deliveries; <code>extras1_runs</code> now holds real extras runs (the first file held a type code), and one name corrected (AHT Donald → Aneurin Donald)', 'Updated file used for every result in this report'],
    ['Extras runs', f'<code>extras1_runs</code> + <code>extras_2_runs</code> reproduces {ai_["won_by_runs_exact_pct"]}% of "won by N runs" margins exactly and every successful chase passes its target; the old 1-run-per-extra rule managed 32.6%', 'Extras = <code>extras1_runs</code> + <code>extras_2_runs</code>'],
    ['Rain-revised matches', 'Revised overs are stored in balls (e.g. 114 = 19 overs); DLS target in <code>revised_target</code>', 'Revised balls and target used for state'],
    ['Duplicate names', 'Abdul Samad, Basil Hameed and Haider Ali each map to 2 IDs; no ID has 2 names', 'All joins on player ID'],
    ['Ties', 'Tied / super-over results in <code>result</code> text', 'Outcome = 0.5 in win-model training'],
    ['Charging the bowler', 'Laws of cricket', 'Bowler charged bat runs + all wide runs + the no-ball penalty; not byes or leg-byes. Bowler wickets: caught, bowled, LBW, stumped, hit wicket'],
    ['Ball faced', 'Laws of cricket', 'Every delivery except wides'],
]))
A('<h3>Scoring-environment normalisation</h3>')
A('<p>Average first-innings totals differ sharply by competition and season (IPL rose 25 runs in four years), so a run is not the same everywhere. '
  'All run quantities are rescaled by <code>global par / environment par</code> (global par = ' + f'{s1["global_par"]}' + ').</p>')
A(table(['Competition', 'Season', 'Complete 1st innings', 'Par total'], envrows))
A('<p class="small">"OtherT20" = the Emerging Teams Asia Cup 2024 and Asia Cup Rising Stars 2025 (A-team tournaments).</p>')
A('<h3>Match state reconstructed before every ball</h3>')
A('<p>Score, wickets lost, legal balls bowled, balls remaining (from revised overs where relevant), target, dot-ball streak, wickets in the last 12 balls, '
  'and the environment par.</p>')

# ---------------- pressure
A('<h2 class="pb">3. Defining pressure</h2>')
A('<h3>3.1 Win-probability engine</h3>')
A('<p><b>Resource curve.</b> Expected further runs with <i>u</i> balls left and <i>w</i> wickets lost, in the Duckworth–Lewis form, fitted to first innings '
  'with runs normalised to the global par:</p>')
A('<div class="formula">R(u, w) = Z0(w) · (1 − exp(−b(w) · u))       then isotonic (PAVA) in w for each u, weighted by sample size</div>')
A(table(['Wickets lost', '0', '1', '2', '3', '4', '5', '6', '7', '8', '9'],
        [['R(120 balls)'] + [rc[str(w)]['R(120)'] for w in range(10)], ['R(60 balls)'] + [rc[str(w)]['R(60)'] for w in range(10)],
         ['R(24 balls)'] + [rc[str(w)]['R(24)'] for w in range(10)], ['States used'] + [f"{rc[str(w)]['n']:,}" for w in range(10)]]))
A('<p class="small">Why PAVA: a first fit using a running minimum flattened short-horizon values (identical R(24) for 0–3 wickets). '
  'Isotonic regression is the least-squares monotone fit, so it was adopted.</p>')
A('<p><b>Win probability.</b> Chasing side: logistic regression on (resources × scale − runs needed)/√(resources + 1), the raw gap, '
  'wickets in hand and required rate. Batting first: logistic on the projected total against par. Three nested feature sets were compared '
  'by match-grouped 5-fold cross-validation, and the best by log-loss was kept.</p>')
A(table(['Innings', 'Coin-flip log-loss', 'Set A', 'Set B', 'Set C', 'Chosen', 'Chosen Brier'], [
    ['Batting first', cv['inn1']['baseline_logloss'], cv['inn1']['A']['logloss'], cv['inn1']['B']['logloss'], cv['inn1']['C']['logloss'], s2['wp_choice']['inn1'], cv['inn1'][s2['wp_choice']['inn1']]['brier']],
    ['Chasing', cv['inn2']['baseline_logloss'], cv['inn2']['A']['logloss'], cv['inn2']['B']['logloss'], cv['inn2']['C']['logloss'], s2['wp_choice']['inn2'], cv['inn2'][s2['wp_choice']['inn2']]['brier']]]))
A('<figure>' + calib() + f'<figcaption>Figure 2 – Calibration: predicted vs observed win rate by decile. Chasing predictions are within {100 * CAL2:.1f} points in every decile.</figcaption></figure>')

A('<h3>3.2 Leverage Index = pressure</h3>')
A('<div class="formula">LI(state) = Σ_outcomes p(outcome | innings, phase) · |WP(next state) − WP(state)|  ÷  mean over all balls\n'
  'outcomes = 0,1,2,3,4,6 runs, wicket, wide/no-ball (empirical frequencies by innings and phase)\n'
  'Pressure ball: LI ≥ 1.5      (LI = 1 is an average ball)</div>')
A('<p>Why this definition: LI combines every factor named in the brief (required run rate, wickets in hand, balls remaining, stage, closeness) '
  'in one number, with no hand-set weights, because the weights come from a model fitted to real results. It is the same for batters and bowlers: '
  'one ball, one level of stakes.</p>')
A(f'<p><b>Why 1.5 and not 2.0.</b> The official FanGraphs tiers call LI above 2.0 "high" and below 0.85 "low"; 1.5 is a widely used, looser high-leverage benchmark. '
  f'We use 1.5 because sample size is the binding constraint (Section 9): it marks {s3["pressure_share"]:.1%} of balls as pressure against {SHARE_LI2:.1%} at 2.0, '
  f'and at 2.0 only {li2["bat"]["eligible"]} batters and {li2["bowl"]["eligible"]} bowlers reach 10 overs of pressure exposure. The 2.0 result is reported as a sensitivity check (Section 6).</p>')
A('<h3>3.3 Dead balls (Gaussian mixture by EM)</h3>')
A(f'<p>A two-component mixture on log(LI) converged in {s3["gmm"]["iterations"]} iterations. It does not split "pressure vs normal". '
  f'It splits <b>live</b> balls from <b>dead</b> balls: games already decided, LI centre ≈ {s3["gmm"]["dead_component_LI_centre"]}. '
  f'Dead balls ({s3["tier_share"]["dead"]:.1%}; {DEAD_DECIDED:.0%} have win probability below 5% or above 95%) are removed from both pressure and baseline samples, '
  f'so slogging in lost causes does not inflate anyone\'s "usual" level. A three-component fit gave overlapping middle components, '
  f'so the pressure cut-off uses a fixed leverage tier instead (3.2).</p>')

A('<h3>3.4 Does the definition separate different situations?</h3>')
A(table(['Tier', 'Balls faced', 'Strike rate', 'Dismissal % per ball', 'Dot %', 'Boundary %', 'Economy', 'Mean LI'],
        [[n, f"{v['balls']:,}", v['SR'], v['out_pct'], v['dot_pct'], v['boundary_pct'], v['econ'], v['mean_LI']] for n, v in tier_rows]))
A(f'<p>On high-pressure balls batters are dismissed <b>{ct["high"]["out_pct"] / ct["medium"]["out_pct"] - 1:.0%} more often</b> than on medium balls '
  f'({ct["high"]["out_pct"]}% vs {ct["medium"]["out_pct"]}%), with fewer dots ({ct["high"]["dot_pct"]}% vs {ct["medium"]["dot_pct"]}%): '
  f'more risk is forced. Knockout matches carry more pressure ({s3["knockout"]["pressure_share"]:.1%} of balls vs {s3["pressure_share"]:.1%} overall).</p>')
A('<figure>' + vbar(over_share[2], [str(o) for o in range(1, 21)], 0.6, 'Share of chase balls that are pressure balls, by over',
                    lambda v: f'{v:.0%}', ytitle='Share of balls with LI ≥ 1.5 (chasing innings), by over') +
  '<figcaption>Figure 3 – Pressure builds through a chase. No first-innings ball reaches LI ≥ 1.5 (Section 9).</figcaption></figure>')
A('<h3>3.5 Psychological signals tested and left out</h3>')
A(f'<p>Within LI quartiles, Mantel–Haenszel pooled odds ratios for dismissal: <b>dot streak ≥ 3: OR {s3["MH_OR_dotstreak3"]}</b> '
  f'(no extra risk, so not added) and <b>2+ wickets in the last 12 balls: OR {s3["MH_OR_wk12_2"]}</b> (a small effect, reported but not added, '
  f'to keep the index model-based and free of hand-set weights).</p>')

# ---------------- performance measurement
A('<h2 class="pb">4. Measuring performance</h2>')
A('<h3>4.1 Per-ball value</h3>')
A('<div class="formula">WPA_batter = WP(after bat runs and own dismissal) − WP(before)\n'
  'WPA_bowler = −[WP(after runs charged to bowler and bowler wickets) − WP(before)]\n'
  'RV = runs/scale + R(u−1, w′) − R(u, w)        (runs minus resources consumed; a wicket costs its resource value)</div>')
A('<h3>4.2 Opponent and phase adjustment</h3>')
A(f'<p>Run value on all {s4["live_balls"]:,} live balls was decomposed as <code>RV = context(format, innings, phase) + batter + bowler + noise</code>, '
  f'a ridge regression (λ = {s4["ridge_lambda"]:.0f} balls) solved by backfitting, which converged in {s4["backfit_iterations"]} iterations '
  f'(final change {s4["backfit_final_delta"]:.1e}). A batter\'s adjusted value subtracts the context and the quality of each bowler faced; '
  f'a bowler\'s adds back the quality of each batter bowled to. That is how a spell against associate teams is discounted relative to a spell against an IPL top order.</p>')
A('<h3>4.3 Four components per player</h3>')
A(table(['Component', 'What it measures', 'Estimator'], [
    ['C1 Pressure impact', 'Win Probability Added per 100 pressure balls', 'Empirical Bayes (normal–normal) toward league mean'],
    ['C2 Pressure quality', 'Opponent and phase-adjusted run value per pressure ball', 'Hierarchical: shrunk own baseline + shrunk clutch delta'],
    ['C3 Clutch delta', 'Pressure RV − usual RV (rises or dips relative to own level)', 'Empirical Bayes toward league mean'],
    ['C4 Consistency', 'Share of pressure innings (≥ 3 pressure balls) with positive adjusted RV', 'Beta-binomial empirical Bayes'],
]))
A('<div class="formula">James–Stein / Efron–Morris shrinkage:   θ̂_i = μ + B_i (x̄_i − μ),   B_i = τ² / (τ² + σ²/n_i)\n'
  'τ² (true between-player variance) by method of moments;  σ² = pooled per-ball variance\n'
  'C2_i = b̂_i (baseline, shrunk) + d̂_i (clutch, shrunk)  →  a pressure estimate shrunk toward the player\'s OWN usual level\n'
  'z_k = (C_k − μ_k) / √τ²_k        (true-score standardisation, classical test theory)</div>')
A(f'''<div class="box"><b>Two design decisions the data forced.</b><br>
1. <b>True-score standardisation.</b> Ordinary z-scores after shrinkage re-inflate pure noise to full weight: on the first version of the ball file
the batter WPA component had τ² = 0 (differences indistinguishable from chance) yet was getting 25% of the weight. Dividing by √τ² gives every component weight
in proportion to its real signal, automatically. On the updated file the WPA component's true between-player SD is {s4["bat_hyper"]["true_sd"][0]:.3f} (batters)
and {s4["bowl_hyper"]["true_sd"][0]:.3f} (bowlers) per 100 pressure balls.<br>
2. <b>Consistency definition chosen by signal.</b> "Positive WPA per pressure innings" had beta-binomial prior strength
{s4["bat_consistency_test"]["WPA_positive"]["prior_strength"]:,.0f} for batters (no signal); "positive adjusted RV" had
{s4["bat_consistency_test"]["RV_positive"]["prior_strength"]:.0f} (batters) and {s4["bowl_consistency_test"]["RV_positive"]["prior_strength"]:.0f} (bowlers), so the RV version is used.</div>''')
A('<p>Composite = mean of the four z-scores. Equal weights are the neutral choice; SMAA (Section 6) shows how ranks behave under every other weighting.</p>')

# ---------------- fair comparisons
A('<h2>5. Fair comparisons</h2>')
A(table(['Concern', 'How it is handled'], [
    ['Small samples', f'Eligibility: ≥ 60 pressure balls (10 overs) and ≥ 6 pressure innings. Beyond that, shrinkage does the work: '
                      f'{s4["bat_eligible"]} batters and {s4["bowl_eligible"]} bowlers qualify.'],
    ['Auction relevance', f'Must appear in the 2025 or 2026 data (excluded as inactive: {s4["bat_excluded_inactive"]} batters, {s4["bowl_excluded_inactive"]} bowlers).'],
    ['IPL vs T20I', 'Both used, with no assumed exchange rate. Opposition strength is estimated from the data (ridge backfitting), and an IPL-only specification enters the model average.'],
    ['Scoring eras', 'Runs normalised by competition-season par (Section 2).'],
    ['Role and phase', 'Run value is phase-neutral (league context mean removed), so openers and finishers are compared fairly.'],
    ['Decided games', 'Dead balls are removed from both pressure and baseline samples.'],
    ['Recency', 'A recency-weighted specification (half-life 2 seasons) enters the model average. Eligibility is always counted on unweighted balls.'],
]))

# ---------------- ranking
A('<h2 class="pb">6. From ratings to a robust ranking</h2>')
A('<p><b>Borda count:</b> each component ranks the players and the ranks are summed. <b>SMAA:</b> 4,000 random weight vectors (flat Dirichlet) '
  'give each player\'s probability of being top 10 under any weighting. <b>Poisson bootstrap:</b> 300 resamples of matches give a 90% rank interval and P(top 10).</p>')
A('<p><b>Model averaging.</b> Rankings were computed under three specifications that change only the evidence scope, and the final score is their mean:</p>')
A(table(['Specification', 'Batter top-10 overlap with main', 'Kendall τ vs main, batters (or pool size)', 'Bowler top-10 overlap', 'Kendall τ vs main, bowlers (or pool size)'], [
    ['IPL only', sens['bat']['ipl']['overlap_top10'], sens['bat']['ipl']['kendall_tau_all'], sens['bowl']['ipl']['overlap_top10'], sens['bowl']['ipl']['kendall_tau_all']],
    ['Recency-weighted', sens['bat']['recent']['overlap_top10'], sens['bat']['recent']['kendall_tau_all'], sens['bowl']['recent']['overlap_top10'], sens['bowl']['recent']['kendall_tau_all']],
    ['Stricter threshold LI ≥ 2.0 (FanGraphs high tier)', f"{li2['bat']['overlap_final_top10']} (of final list)", f"{li2['bat']['eligible']} eligible", f"{li2['bowl']['overlap_final_top10']} (of final list)", f"{li2['bowl']['eligible']} eligible"],
    ['Rejected: within-innings top-decile pressure', sens['bat']['alt']['overlap_top10'], sens['bat']['alt']['kendall_tau_all'], sens['bowl']['alt']['overlap_top10'], sens['bowl']['alt']['kendall_tau_all']],
]))
_t = [sens[r][m]['kendall_tau_all'] for r in ('bat', 'bowl') for m in ('ipl', 'recent')]
A(f'<p class="small">The specifications agree only moderately (τ = {min(_t):.2f}–{max(_t):.2f}). That is the real level of signal in pressure data (Section 9), '
  'and it is why no single specification is trusted alone. The within-innings definition was rejected on evidence: its first-innings "pressure" balls are '
  'over-1 balls at 0 wickets (the resource curve prices early wickets highest), so it rewards new-ball bowling rather than pressure.</p>')
A(f'''<div class="box warn"><b>Threshold sensitivity.</b> At LI ≥ 2.0, {li2['bat']['overlap_final_top10']} of our 10 batters and {li2['bowl']['overlap_final_top10']} of our 10 bowlers stay in the top 10.
Part of the change is players falling below 10 overs of pressure exposure at 2.0 rather than being out-performed ({names(li2['bat']['not_eligible_at_2.0'] + li2['bowl']['not_eligible_at_2.0'])}).
The names in the top 10 at both thresholds ({names(p for p in [x['player'] for x in FB[:10]] if p in li2['bat']['top10_at_2.0'])}; {names(p for p in [x['player'] for x in FW[:10]] if p in li2['bowl']['top10_at_2.0'])}) are the most robust picks.
Top 10 at 2.0 &ndash; batters: {", ".join(li2['bat']['top10_at_2.0'])}. Bowlers: {", ".join(li2['bowl']['top10_at_2.0'])}.</div>''')

# ---------------- evidence
A('<h2 class="pb">7. Evidence for the top 10</h2>')
A('<h3>7.1 Batters</h3>')
A('<figure>' + dumbbell([(r['player'], float(r['B_SR']), float(r['P_SR'])) for r in top_b], 130, 210,
                        'Batter strike rate under pressure vs usual', 'Strike rate', [130, 150, 170, 190, 210]) +
  '<figcaption>Figure 4 – Strike rate on pressure balls (blue) vs the same player\'s live non-pressure balls (grey). Raw values; ranking uses adjusted run value.</figcaption></figure>')
A(table(['#', 'Player', 'P balls', 'P inns', 'P SR', 'Usual SR', 'P avg', 'Usual avg', 'IPL share', 'Rank: all', 'IPL', 'Recent', 'P(top10)'], bat_ev))
A(table(['#', 'Player', 'Final score', 'z C1 impact', 'z C2 quality', 'z C3 clutch', 'z C4 consistency', 'Borda', 'SMAA P(top10)', 'Bootstrap 90% rank'], comp_rows(top_b)))
A('<p class="small">Final score = model average. z-scores, Borda rank, SMAA and bootstrap interval are from the main (all-data) specification.</p>')
A('<h3>7.2 Bowlers</h3>')
A('<figure>' + dumbbell([(r['player'], float(r['B_econ']), float(r['P_econ'])) for r in top_w], 3, 11,
                        'Bowler economy under pressure vs usual', 'Economy (runs per over, lower is better)', [3, 4, 5, 6, 7, 8, 9, 10]) +
  '<figcaption>Figure 5 – Economy on pressure balls (blue) vs usual (grey). Lower is better. Raw values; ranking uses adjusted run value and WPA.</figcaption></figure>')
A(table(['#', 'Player', 'P balls', 'P inns', 'P econ', 'Usual econ', 'P balls/wkt', 'Usual balls/wkt', 'P wkts', 'IPL share', 'Rank: all', 'IPL', 'Recent', 'P(top10)'], bowl_ev))
A(table(['#', 'Player', 'Final score', 'z C1 impact', 'z C2 quality', 'z C3 clutch', 'z C4 consistency', 'Borda', 'SMAA P(top10)', 'Bootstrap 90% rank'], comp_rows(top_w)))
A('<p class="small">As above: z-scores, Borda, SMAA and the bootstrap interval are from the main specification.</p>')
A('<h3>7.3 How certain is each place?</h3>')
A('<div class="lists"><figure>' + hbar([(r['player'], float(r['ens_boot_p_top10'])) for r in top_b], 1, 'Batters bootstrap probability of top 10', w=420) +
  '<figcaption>Figure 6a – Batters: share of bootstrap resamples in the top 10 (mean over specifications).</figcaption></figure><figure>' +
  hbar([(r['player'], float(r['ens_boot_p_top10'])) for r in top_w], 1, 'Bowlers bootstrap probability of top 10', color=BLUE, w=420) +
  '<figcaption>Figure 6b – Bowlers: the same measure.</figcaption></figure></div>')
A('<h3>7.4 Next ten (ranks 11–20)</h3>')
A('<div class="lists"><div>' + table(['#', 'Batter', 'Score', 'P balls', 'All', 'IPL', 'Recent', 'P(top10)'], next_rows(FB)) +
  '</div><div>' + table(['#', 'Bowler', 'Score', 'P balls', 'All', 'IPL', 'Recent', 'P(top10)'], next_rows(FW)) + '</div></div>')


# ---------------- RR fit
def rrrow(lbl, d):
    a, b = d['RR'], d['Rest of IPL']
    return [lbl, a['balls'], a['SR'], b['SR'], a['out_pct'], b['out_pct'], a['boundary_pct'], b['boundary_pct'], a['WPA_per100'], b['WPA_per100']]
def rrbowl(lbl, d):
    a, b = d['RR'], d['Rest of IPL']
    return [lbl, a['balls'], a['econ'], b['econ'], f(a['balls_per_wkt'], 1), f(b['balls_per_wkt'], 1), a['dot_pct'], b['dot_pct'], a['WPA_per100'], b['WPA_per100']]
bp = rr['bat_pressure_phase']; wp_ = rr['bowl_pressure_phase']; wt = rr['bowl_pressure_type']
PR = {p['player']: p for role in ('bat', 'bowl') for p in rr['profiles'][role]}
def ph(name, k):
    return f"{PR[name]['phase_share'].get(k, 0):.0%}"
def sp(name, k, m):
    v = PR[name]['split'].get(k)
    return v[m] if v and v[m] is not None else '–'
D, M, PP = 'Death (16-20)', 'Middle (7-15)', 'Powerplay (1-6)'
A('<h2 class="pb">8. How each player could strengthen Rajasthan Royals</h2>')
A("<p>To say how a player helps RR, we first measured RR's own record on pressure balls in IPL 2025 and 2026 against the rest of the IPL "
  "(same seasons, same pressure definition, dead balls excluded), then matched each top-10 player's pressure profile to the gaps. "
  "Everything here comes from the data pack.</p>")
A('<h3>8.1 RR batting on pressure balls, IPL 2025–26</h3>')
A(table(['Phase', 'RR balls', 'RR SR', 'Rest SR', 'RR out %', 'Rest out %', 'RR 4s/6s %', 'Rest 4s/6s %', 'RR WPA/100', 'Rest WPA/100'],
        [rrrow('All pressure balls', rr['bat_pressure'])] + [rrrow(k, bp[k]) for k in (PP, M, D)]))
A(f"""<div class="box warn"><b>The gap.</b> RR score quickly under pressure early in a chase, but at the death they strike at {bp[D]['RR']['SR']} against
{bp[D]['Rest of IPL']['SR']}, hit fewer boundaries ({bp[D]['RR']['boundary_pct']}% vs {bp[D]['Rest of IPL']['boundary_pct']}% of balls), lose wickets more often
({bp[D]['RR']['out_pct']}% vs {bp[D]['Rest of IPL']['out_pct']}% per ball) and give away win probability ({bp[D]['RR']['WPA_per100']} vs
{bp[D]['Rest of IPL']['WPA_per100']} per 100 balls). Overall, RR's pressure batting scores faster than the league but loses more win probability:
the extra dismissals cost more than the extra runs gain. Caution: {bp[D]['RR']['balls']} death-over pressure balls is a modest sample.</div>""")
A('<h3>8.2 RR bowling on pressure balls, IPL 2025–26</h3>')
A(table(['Split', 'RR balls', 'RR econ', 'Rest econ', 'RR balls/wkt', 'Rest balls/wkt', 'RR dot %', 'Rest dot %', 'RR WPA/100', 'Rest WPA/100'],
        [rrbowl('All pressure balls', rr['bowl_pressure'])] + [rrbowl(k, wp_[k]) for k in (PP, M, D)] + [rrbowl(k, wt[k]) for k in ('Pace', 'Spin')]))
A(f"""<p>RR's pressure bowling is at or slightly better than league level overall (economy {rr['bowl_pressure']['RR']['econ']} vs
{rr['bowl_pressure']['Rest of IPL']['econ']}). Spin is a strength (a wicket every {wt['Spin']['RR']['balls_per_wkt']} balls vs {wt['Spin']['Rest of IPL']['balls_per_wkt']}).
The softer spots: pace takes wickets slightly less often ({wt['Pace']['RR']['balls_per_wkt']} vs {wt['Pace']['Rest of IPL']['balls_per_wkt']} balls per wicket)
and death-over dot balls are rarer ({wp_[D]['RR']['dot_pct']}% vs {wp_[D]['Rest of IPL']['dot_pct']}%).</p>""")
res_rows = [[sea, v.get('won', 0), v.get('lost', 0), v.get('close_won', 0), v.get('close_lost', 0)] for sea, v in rr['rr_results'].items()]
A(table(['IPL season', 'Won', 'Lost', 'Close won', 'Close lost'], res_rows))
A('<p class="small">Close = decided by 10 runs or fewer, finished with 6 or fewer balls left, or tied.</p>')
A("<h3>8.3 RR's 2026 squad in our rankings</h3>")
sq = [r for r in rr['rr_squad_2026'] if r['bat_rank'] or r['bowl_rank']]
A(table(['Player', f"Batting rank (of {rr['pool_sizes']['bat']})", 'Pressure balls faced', f"Bowling rank (of {rr['pool_sizes']['bowl']})", 'Pressure balls bowled'],
        [[e(r['player']), r['bat_rank'] or '–', r['bat_P_balls'] or '–', r['bowl_rank'] or '–', r['bowl_P_balls'] or '–'] for r in sq]))
A(f"<p class='small'>{rr['rr_squad_size'] - len(sq)} of the {rr['rr_squad_size']} players in RR's IPL 2026 squad have too few pressure balls to be rated. "
  f"In our top 10: {RRP_TXT}.</p>")
A('<h3>8.4 Player-by-player fit</h3>')
A("<p>Phase shares show where each player's pressure balls came from (all competitions). Splits are raw pressure-ball figures.</p>")
BL = {r['player']: r for r in J('rr_backlist.json')['rows']}
FINR = {r['player']: r for r in FB + FW}
bpD, wtP, wtS, wpD = bp[D], wt['Pace'], wt['Spin'], wp_[D]

def bat_text(n):
    p, b, f = PR[n], BL[n], FINR[n]
    s = [f"{p['style']}; pressure balls: {ph(n, PP)} powerplay, {ph(n, M)} middle, {ph(n, D)} death."]
    parts = []
    for k, lab in (('Pace', 'pace'), ('Spin', 'spin')):
        v = p['split'].get(k)
        if v and v['balls'] >= 15:
            parts.append(f"SR {v['SR']} vs {lab} (out {v['out_pct']}% per ball, {v['balls']} balls)")
    if parts:
        s.append('Under pressure: ' + '; '.join(parts) + '.')
    if b['need'] == 'Death finisher':
        s.append(f"Targets RR's biggest measured gap, death-overs batting in pressure chases (RR SR {bpD['RR']['SR']} vs {bpD['Rest of IPL']['SR']} for the rest of the IPL).")
    elif b['need'] == 'Top order':
        s.append(f"Top-order option. RR's powerplay pressure batting is already above league level (SR {bp[PP]['RR']['SR']} vs {bp[PP]['Rest of IPL']['SR']}), so this adds depth rather than fixing a gap.")
    else:
        s.append(f"Middle-overs option. RR's middle-overs pressure batting is close to league level (SR {bp[M]['RR']['SR']} vs {bp[M]['Rest of IPL']['SR']}), so this adds depth rather than fixing a gap.")
    return ' '.join(s) + tail(n, b, f)

def bowl_text(n):
    p, b, f = PR[n], BL[n], FINR[n]
    s = [f"{p['style']}; pressure balls: {ph(n, PP)} powerplay, {ph(n, M)} middle, {ph(n, D)} death."]
    parts = []
    for k, lab in ((PP, 'powerplay'), (M, 'middle overs'), (D, 'death')):
        v = p['split'].get(k)
        if v and v['balls'] >= 18:
            w = f"a wicket every {v['balls_per_wkt']} balls" if v['balls_per_wkt'] else 'no wicket'
            parts.append(f"{lab}: economy {v['econ']}, {w}, {v['dot_pct']}% dots ({v['balls']} balls)")
    if parts:
        s.append('Under pressure, ' + '; '.join(parts) + '.')
    if b['need'] == 'Pace':
        s.append(f"Targets RR's pace gap (RR pace: a wicket every {wtP['RR']['balls_per_wkt']} pressure balls vs {wtP['Rest of IPL']['balls_per_wkt']} for the rest; "
                 f"death-over dots {wpD['RR']['dot_pct']}% vs {wpD['Rest of IPL']['dot_pct']}%).")
    else:
        s.append(f"Adds to an existing RR strength (RR spin: a wicket every {wtS['RR']['balls_per_wkt']} pressure balls vs {wtS['Rest of IPL']['balls_per_wkt']}), so depth and variety rather than a fix.")
    return ' '.join(s) + tail(n, b, f)

def tail(n, b, f):
    t = []
    if b['status'].startswith('RR'):
        t.append('Already in RR\'s 2026 squad: the data supports retaining this player, if possible.')
    if 'IPL-untested' in b['flags']:
        t.append('All pressure evidence is T20I, and the player is not in the IPL 2026 data, so IPL-untested.')
    if 'thin sample' in b['flags']:
        t.append(f"Thin sample ({f['P_balls']} pressure balls).")
    if 'clutch-dependent' in b['flags']:
        t.append('Rank leans on the less repeatable clutch components (Section 9.3).')
    return (' ' + ' '.join(t)) if t else ''

bat_fit = {p['player']: bat_text(p['player']) for p in rr['profiles']['bat']}
bowl_fit = {p['player']: bowl_text(p['player']) for p in rr['profiles']['bowl']}
json.dump({'bat': bat_fit, 'bowl': bowl_fit}, open(os.path.join(OUT, 'fit_text.json'), 'w', encoding='utf-8'), indent=1)
def fitrows(role, fits):
    return [[p['rank'], f"<b>{e(p['player'])}</b><br><span class='small'>{e(p['style'])} · 2026: {e(p['team_2026'])}</span>", fits[p['player']]]
            for p in rr['profiles'][role]]
A('<h3>Batters</h3>')
A(table(['#', 'Player', 'How this player could strengthen RR (from the data)'], fitrows('bat', bat_fit)))
A('<h3>Bowlers</h3>')
A(table(['#', 'Player', 'How this player could strengthen RR (from the data)'], fitrows('bowl', bowl_fit)))
A(f"""<div class="box"><b>Suggested auction priorities for RR, from the data.</b> (1) A death finisher for pressure chases: {names_or(DEATH_B)}.
(2) A pace bowler for RR's pace gap: {names_or(PACE_B)}. (3) Keep {names(x['player'] for x in RRP)} if retention allows.
Spin is already RR's pressure strength, so {names_or(SPIN_D)} would add depth and variety rather than fill a hole.
{('Among these, ' + names(CLUTCH_B) + (' leans' if len(CLUTCH_B) == 1 else ' lean') + ' more on the less repeatable clutch components (Section 9.3). ') if CLUTCH_B else ''}Availability, price and the official
auction list are outside this data and should be checked before bidding. The full call for every player is on the auction board after the cover.</div>""")

# ---------------- reliability
A('<h2 class="pb">9. Reliability and limitations</h2>')
A('<h3>9.1 Is pressure performance repeatable?</h3>')
A('<p>Each player\'s matches were split into odd and even match IDs and each metric was correlated across the halves (Spearman–Brown corrects to full length).</p>')
A('<div class="lists"><div><b>Batters</b>' + table(['Metric', 'Split-half r', 'Spearman–Brown', 'n'], rel('bat')) +
  '</div><div><b>Bowlers</b>' + table(['Metric', 'Split-half r', 'Spearman–Brown', 'n'], rel('bowl')) + '</div></div>')
A(f'''<div class="box warn"><b>Honest finding.</b> Pressure performance is only weakly repeatable at these sample sizes, as baseball's long-running
"clutch" research also found. A player's usual level is the most stable signal, and pure clutch delta is close to noise for batters.
That is why the model shrinks each pressure estimate toward the player's own baseline, weights components by true signal, and reports
bootstrap intervals. Players in the top 10 in at least 70% of bootstrap resamples ({names(STRONG['bat'])}; {names(STRONG['bowl'])})
are strong calls; the rest of each list is a tight group in which neighbouring places could swap.</div>''')
ai = au['A_integrity']; ro = au['C_robustness']; oo = au['D_out_of_sample']
A('<h3>9.3 Deeper audit (full re-run, 10 Nov 2026)</h3>')
A('<p>The whole pipeline was re-run from the raw files and reproduced every output byte for byte. Four further checks were then added (<code>step7_audit.py</code>).</p>')
A('<p><b>A. Raw-data integrity.</b></p>')
A(table(['Check', 'Result'], [
    ['Duplicate deliveries / innings with gaps in ball numbering', f"{ai['duplicate_delivery_keys']} / {ai['innings_with_ball_number_gaps']}"],
    ['Innings with more than 10 wickets', ai['innings_over_10_wickets']],
    ["Striker / non-striker / bowler listed in that match's XI", f"{ai['striker_in_XI_pct']}% / {ai['non_striker_in_XI_pct']}% / {ai['bowler_in_XI_pct']}%"],
    ['Dismissed player is the striker or non-striker', f"{ai['dismissed_is_on_strike_or_non_striker_pct']}%"],
    ['"Won by N wickets" reproduced exactly from ball data', ai['won_by_wickets_reproduced']],
    ['"Won by N runs" reproduced (exact / within 5 runs)', f"{ai['won_by_runs_exact_pct']}% / {ai['won_by_runs_within_5_pct']}% of {ai['won_by_runs_n']} (MAE {ai['won_by_runs_MAE']})"],
]))
A('<p class="small">With the updated ball file the extras runs are stored, so innings totals now match official results. '
  '<b>B. Recount:</b> the pressure balls, runs and wickets of all 20 listed players were re-counted directly from the ball file: '
  + ('no mismatches' if not au['B_recount']['mismatches'] else e(str(au['B_recount']['mismatches']))) + '.</p>')
A('<p><b>C. Robustness.</b> Players kept in the main top 10 when each component is dropped in turn, and when the 60-ball eligibility bar is moved:</p>')
lab = list(ro['bat']['leave_one_component_out_overlap_of_10'])
A(table(['Variant', 'Batters kept (of 10)', 'Bowlers kept (of 10)'],
        [[k, ro['bat']['leave_one_component_out_overlap_of_10'][k], ro['bowl']['leave_one_component_out_overlap_of_10'][k]] for k in lab] +
        [[f"Eligibility ≥40 balls ({ro['bat']['eligible_min40']} / {ro['bowl']['eligible_min40']} eligible)", ro['bat']['threshold_overlap_of_10']['min40'], ro['bowl']['threshold_overlap_of_10']['min40']],
         [f"Eligibility ≥100 balls ({ro['bat']['eligible_min100']} / {ro['bowl']['eligible_min100']} eligible)", ro['bat']['threshold_overlap_of_10']['min100'], ro['bowl']['threshold_overlap_of_10']['min100']]]))
A('<p class="small">Top 10 under every leave-one-out: ' + e(', '.join(ro['bat']['in_top10_under_every_leave_one_out'])) + ' (batting); ' +
  e(', '.join(ro['bowl']['in_top10_under_every_leave_one_out'])) + ' (bowling). A ≥40-ball bar admits many very small samples, which is why the batting list moves most there.</p>')
A('<p><b>D. Out-of-sample test.</b> The ratings were rebuilt from 2022–24 balls only and compared, by Spearman rank correlation, with what the same players did on pressure balls in 2025–26 '
  f"({oo['bat']['players_tested']} batters and {oo['bowl']['players_tested']} bowlers with at least 30 pressure balls in 2025–26).</p>")
rows = []
for k in oo['bat']:
    if isinstance(oo['bat'][k], dict) and 'ci90' in oo['bat'][k]:
        kw = k.replace('raw pressure strike rate', 'raw pressure economy (lower = better)')
        cb, cw = oo['bat'][k], oo['bowl'][kw]
        rows.append([e(k.replace('raw pressure strike rate', 'raw pressure SR / economy')),
                     f"{cb['rho_vs_2025_26_pressure_RV']:+.2f} ({cb['ci90'][0]:+.2f} to {cb['ci90'][1]:+.2f})",
                     f"{cw['rho_vs_2025_26_pressure_RV']:+.2f} ({cw['ci90'][0]:+.2f} to {cw['ci90'][1]:+.2f})"])
A(table(['Predictor built on 2022–24', 'Batters ρ (90% CI)', 'Bowlers ρ (90% CI)'], rows))
A(f'''<div class="box warn"><b>What the holdout shows.</b> {holdout_text(oo)} Every interval is wide at these sample sizes, so the published order was <b>not</b>
re-tuned on this one split, because that would be fitting to the test. Instead each player is tagged: <b>Core</b> = also top 10 on C2 alone; <b>clutch-dependent</b> = ranked mainly on the
less repeatable parts. Top-quarter players by the 2022–24 composite did go on to produce more run value under pressure in 2025–26 than the rest
(batters {oo['bat']['top_quarter_by_composite_mean_2025_26_RV']:+.3f} vs {oo['bat']['other_three_quarters_mean_2025_26_RV']:+.3f} runs per ball; bowlers
{oo['bowl']['top_quarter_by_composite_mean_2025_26_RV']:+.3f} vs {oo['bowl']['other_three_quarters_mean_2025_26_RV']:+.3f}).</div>''')
A(table(['#', 'Batter', 'C2 rank', 'Tier', '#', 'Bowler', 'C2 rank', 'Tier'],
        [[a['rank'], e(a['player']), a['C2_rank'], a['tier'], b['rank'], e(b['player']), b['C2_rank'], b['tier']]
         for a, b in zip(au['E_tiers']['bat'], au['E_tiers']['bowl'])]))

A('<h3>9.2 Where the model is less certain</h3>')
A(table(['Limitation', 'Effect', 'Mitigation'], [
    ['First-innings pressure not captured', 'A single first-innings ball never reaches LI ≥ 1.5, so collapses and defending a total are not counted', 'Alternative definition tested and shown (Section 6)'],
    ['Thin samples', names(f'{n} ({b} pressure balls)' for n, b in THIN), 'Shrinkage, bootstrap intervals, flagged on the cover'],
    ['T20I-only evidence', names(UNTESTED) + ' have no IPL pressure sample', 'Opponent adjustment; averaged over the specifications available to them'],
    ['Attribution', 'Run-outs and byes are not charged to bowlers; partnership effects are ignored', 'Standard convention'],
    ['Availability', 'The data cannot show 2027 retentions or auction entries (' + names(x['player'] for x in RRP) + ' played for RR in 2026). A public search on 10 Nov 2026 found only predicted lists; official retentions are due 15–17 Nov 2026', 'Check against the official retention and auction lists'],
]))

# ---------------- repro
A('<h2>10. Reproducing this work</h2>')
A('<p>Pure Python 3 standard library, no third-party packages. Runtime about 4 minutes.</p>')
A('<div class="formula">sh analysis/run_all.sh "path/to/SupeRR_Selector_Season_2_Data_Pack_Extracted"\n\n'
  'step1_preprocess.py  cleaning, extras rule, state reconstruction, era par        → out/balls_clean.csv\n'
  'step2_winprob.py     resource curve, PAVA, WP model (CV), LI, WPA, RV            → out/balls_model.csv\n'
  'step3_pressure.py    EM dead-ball detection, tiers, validation, MH tests         → out/balls_pressure.csv\n'
  'step4_ratings.py     backfitting, EB components, Borda, SMAA, bootstrap (×5 specs) → out/rank_*.csv\n'
  'step5_final.py       model-averaged final ranking                                → out/FINAL_*.csv\n'
  'step6_rr_fit.py      RR pressure record, 2026 squad, player profiles             → out/rr_fit.json\n'
  'step7_audit.py       raw-data integrity, recount, robustness, holdout test       → out/audit.json\n'
  'make_report.py       this report</div>')
A('<p class="small">Random seeds are fixed (CV folds 7, SMAA 11, bootstrap 5), so results are identical on every run.</p>')

# ---------------- appendix: separate public-data model
PMR = os.path.join(os.path.dirname(os.path.abspath(OUT)), '..', 'public_model', 'out', 'pm_results.json')
if os.path.exists(PMR):
    pmr = json.load(open(PMR, encoding='utf-8'))
    A('<h2 class="pb">Appendix. A separate check: machine-learning model on public data</h2>')
    A('''<div class="box warn"><b>Kept separate.</b> This model is a cross-check only. It is trained on different data with its own definition of pressure,
and none of its output feeds into the two top-10 lists or the RR auction board above.</div>''')
    A('''<p><b>Data.</b> Every IPL match 2008–2026 from Cricsheet (open ball-by-ball data, 1,243 matches, 295,557 deliveries) and public IPL auction
history 2013–2025 (1,279 sold players, prices in crores; no 2024 mini-auction file was available). <b>Pressure rule (the model's own):</b> overs 16–20,
or a chase needing 9 or more an over, excluding chases already decided. <b>Target:</b> the player's run value per pressure ball in the <i>next</i> season
(runs above league average, with wickets priced at league runs per wicket). <b>Features</b> (all from earlier seasons, recency-weighted):
overall and pressure run value, last-season values, balls faced or bowled, strike rate or economy, boundary or dot rate, dismissal or wicket rate,
death-over share, seasons played, and the auction features: last price, its rank within that auction, and years since it.
<b>Models:</b> ridge regression and gradient-boosted trees (both written in pure Python), compared each season 2016–2024 by training on earlier seasons only.</p>''')
    rows = []
    for role, lab in (('bat', 'Batters'), ('bowl', 'Bowlers')):
        v = pmr['roles'][role]['rolling_validation_mean_spearman_2016_2024']
        rows.append([lab] + [f"{v[m]:+.3f}" for m in ('naive (past pressure value)', 'ridge', 'gradient boosting')] + [e(pmr['roles'][role]['chosen'])])
    A(table(['', 'Naive: past pressure value', 'Ridge', 'Gradient boosting', 'Chosen'], rows))
    A('<p class="small">Mean Spearman correlation between predicted and actual next-season pressure value, 2016–2024, each season predicted from earlier seasons only.</p>')
    A('<p>' + e(pm_uses(pmr)) + '</p>')
    A('<h3>Head to head on IPL 2025–26</h3>')
    A('<p>Both methods were frozen at the end of 2024 and asked to rank the same IPL players. The ranking was then compared with what the players actually did '
      'under pressure in 2025–26, judged two ways: by the model\'s own pressure rule and by ours.</p>')
    rows = []
    for role, lab in (('bat', 'Batters'), ('bowl', 'Bowlers')):
        for truth, h in pmr['roles'][role]['head_to_head_2025_26'].items():
            rows.append([lab, e(truth.split(': ', 1)[1]), h['players'],
                         f"{h['public_model']['rho']:+.2f} ({h['public_model']['ci90'][0]:+.2f} to {h['public_model']['ci90'][1]:+.2f})",
                         f"{h['superrr_method']['rho']:+.2f} ({h['superrr_method']['ci90'][0]:+.2f} to {h['superrr_method']['ci90'][1]:+.2f})"])
    A(table(['', 'Actual 2025–26 pressure performance judged by', 'Players', 'Public model ρ (90% CI)', 'Our method ρ (90% CI)'], rows))
    A('<div class="box warn">' + pm_verdict(pmr) + '</div>')
    A('<h3>The model\'s IPL 2027 lists beside ours</h3>')
    for role, lab in (('bat', 'Batters'), ('bowl', 'Bowlers')):
        fc = pmr['roles'][role]['forecast_2027']
        ours = fc['our_top10_in_model']
        A(f"<p><b>{lab}</b>: {fc['overlap_top10']} of 10 names shared; rank correlation over the {fc['common_players']} players both methods rate: {fc['rank_corr_common_players']:+.2f}.</p>")
        A(table(['#', 'Public model top 10', 'Our rank', 'Our top 10', 'Model rank'],
                [[i + 1, e(m['player']), m['our_final_rank'] or '–', e(o['player']), o['model_rank'] or 'not rated (no IPL 2026 record)']
                 for i, (m, o) in enumerate(zip(fc['model_top10'], ours))]))
    A('<p class="small">The public model only sees IPL matches, so T20I-only players (here ' + names(UNTESTED) + ') and players without an IPL 2026 '
      'appearance cannot be rated by it. Scripts: <code>public_model/pm1_parse.py</code>, <code>pm2_link.py</code> (name linking for comparison only), '
      '<code>pm3_model.py</code>. Data: Cricsheet (Open Data Commons Attribution License); auction history from the public GitHub repository psai09599-stack/IPL-Auction-Intelligence.</p>')

A('</body></html>')

os.makedirs(os.path.dirname(DEST), exist_ok=True)
open(DEST, 'w', encoding='utf-8').write(''.join(H))
print('wrote', DEST)
