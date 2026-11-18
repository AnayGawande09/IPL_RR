"""Build the short, plain-language summary for the judges (HTML -> PDF with Edge) from pipeline outputs.
Every number is read from the analysis outputs, so it always matches the full methodology report.
usage: python -I make_summary.py <analysis/out> <summary.html>"""
import sys, os, json, csv, html, re

OUT, DEST = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from holdout_text import holdout_text, pm_verdict

J = lambda f: json.load(open(os.path.join(OUT, f), encoding='utf-8'))
R = lambda f: list(csv.DictReader(open(os.path.join(OUT, f), encoding='utf-8')))
e = lambda s: html.escape(str(s))
s1, s3, s4 = J('step1_log.json'), J('step3_log.json'), J('step4_log_main.json')
au, rr, li2 = J('audit.json'), J('rr_fit.json'), J('sensitivity_li2.json')
FB, FW = R('FINAL_bat.csv'), R('FINAL_bowl.csv')
BL = {r['player']: r for r in J('rr_backlist.json')['rows']}
TIER = {t['player']: t['tier'] for r in au['E_tiers'].values() for t in r}
PMR = os.path.join(os.path.dirname(os.path.abspath(OUT)), '..', 'public_model', 'out', 'pm_results.json')
pm = json.load(open(PMR, encoding='utf-8')) if os.path.exists(PMR) else None
ct = s3['contrast']

def names(lst, conj='and'):
    lst = list(lst)
    return ', '.join(lst[:-1]) + (f' {conj} ' if len(lst) > 1 else '') + lst[-1] if lst else 'none'

def table(head, rows, cls=''):
    return (f'<table class="{cls}"><thead><tr>' + ''.join(f'<th>{h}</th>' for h in head) + '</tr></thead><tbody>' +
            ''.join('<tr>' + ''.join(f'<td>{c}</td>' for c in r) + '</tr>' for r in rows) + '</tbody></table>')

CALL_CLS = {'Retain': 'c-ret', 'Back - priority 1': 'c-p1', 'Back - priority 2': 'c-p2', 'Depth option': 'c-dep', 'Watch': 'c-wat'}
def call_chip(n):
    c = BL[n]['call']
    return f'<span class="chip {CALL_CLS[c]}">{e(c.replace(" - ", ": "))}</span>'

def flow():
    steps = [('Clean the data', f'{s1["raw_deliveries"]:,} balls, every rule checked'),
             ('Win chances', 'A model gives the batting side\'s chance of winning before every ball'),
             ('Find pressure', f'Balls that can swing the result most: {s3["pressure_share"]:.0%} of all balls'),
             ('Score players', 'Value of every pressure ball, fair to opponent and phase, small samples shrunk'),
             ('Check and fit RR', 'Stress tests, a time-split test, and RR\'s own gaps')]
    W, bw, gap, h = 900, 160, 25, 96
    body = ''
    for i, (t, s) in enumerate(steps):
        x = i * (bw + gap)
        body += f'<rect x="{x}" y="2" width="{bw}" height="{h}" rx="8" fill="#f2f6fc" stroke="#9db8e0"/>'
        body += f'<text x="{x + 12}" y="26" font-size="12" font-weight="700" fill="#1f5fbf">{i + 1}</text>'
        body += f'<text x="{x + 28}" y="26" font-size="12.5" font-weight="700" fill="#16181d">{e(t)}</text>'
        words, line, ly = s.split(), '', 46
        for w in words:
            if len(line + ' ' + w) > 24:
                body += f'<text x="{x + 12}" y="{ly}" font-size="10.5" fill="#4a5060">{e(line.strip())}</text>'; line, ly = w, ly + 14
            else:
                line += ' ' + w
        body += f'<text x="{x + 12}" y="{ly}" font-size="10.5" fill="#4a5060">{e(line.strip())}</text>'
        if i < len(steps) - 1:
            ax = x + bw + 3
            body += f'<path d="M{ax} {h / 2 + 2} L{ax + gap - 8} {h / 2 + 2}" stroke="#7f8796" stroke-width="1.6" fill="none"/>'
            body += f'<path d="M{ax + gap - 8} {h / 2 - 2} L{ax + gap - 3} {h / 2 + 2} L{ax + gap - 8} {h / 2 + 6} Z" fill="#7f8796"/>'
    return f'<svg viewBox="0 0 {W} {h + 4}" width="100%" role="img" aria-label="Five-step workflow">{body}</svg>'

def plist(rows, role):
    out = []
    for r in rows[:10]:
        n = r['player']
        st = (f"SR {r['P_SR']} <span class='mut'>(usual {r['B_SR']})</span>" if role == 'bat'
              else f"Econ {r['P_econ']} <span class='mut'>(usual {r['B_econ']})</span>")
        flags = []
        if int(r['P_balls']) < 100:
            flags.append('small sample')
        if TIER[n] != 'Core':
            flags.append('clutch-dependent')
        if 'IPL-untested' in BL[n]['flags']:
            flags.append('no IPL record')
        out.append([r['final_rank'], f"<b>{e(n)}</b>" + (f"<div class='mut sm'>{e(', '.join(flags))}</div>" if flags else ''),
                    e(BL[n]['team_2026']), st, f"{float(r['ens_boot_p_top10']):.0%}", call_chip(n)])
    return table(['#', 'Player', '2026 team', 'Under pressure', 'Stays top 10*', 'For RR'], out, 'lst')

css = """
@page { size: A4; margin: 15mm 14mm; }
:root { --ink: #16181d; --mut: #5a606c; --line: #e2e5eb; --accent: #1f5fbf; --soft: #f4f7fb; --pink: #b5175a; }
* { box-sizing: border-box; }
body { font: 10.4pt/1.5 "Segoe UI", system-ui, sans-serif; color: var(--ink); margin: 0; background: #fff; }
h1 { font-size: 24pt; margin: 0 0 4pt; letter-spacing: -.01em; }
h2 { font-size: 15pt; margin: 18pt 0 6pt; color: var(--ink); border-bottom: 2px solid var(--accent); padding-bottom: 3pt; }
h3 { font-size: 11.5pt; margin: 12pt 0 4pt; }
p { margin: 4pt 0 7pt; }
.eyebrow { font-size: 8.5pt; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; color: var(--pink); }
.lead { font-size: 11.5pt; color: var(--mut); margin-bottom: 10pt; }
.answer { border: 1.5px solid var(--accent); border-radius: 8px; padding: 9pt 12pt; background: var(--soft); margin: 8pt 0 10pt; }
.answer b { color: var(--accent); }
table { border-collapse: collapse; width: 100%; margin: 5pt 0 9pt; font-size: 9.3pt; break-inside: avoid; }
th { text-align: left; font-weight: 600; color: var(--mut); font-size: 8.4pt; padding: 4pt 5pt; border-bottom: 1.5px solid #c9d3e3; }
td { padding: 4pt 5pt; border-bottom: 1px solid var(--line); vertical-align: top; }
table.lst td:first-child { font-weight: 700; color: var(--accent); width: 18pt; }
.mut { color: var(--mut); } .sm { font-size: 8pt; }
.chip { display: inline-block; font-size: 8pt; font-weight: 700; padding: 1pt 6pt; border-radius: 9pt; white-space: nowrap; }
.c-ret { background: #fbe9f0; color: #9a1350; } .c-p1 { background: #dff3ea; color: #136347; } .c-p2 { background: #e8f1e0; color: #3f6a12; }
.c-dep { background: #e8eef9; color: #1f4f9a; } .c-wat { background: #f1f1f1; color: #55595f; }
.box { border: 1px solid var(--line); border-radius: 8px; padding: 8pt 11pt; margin: 7pt 0; background: #fafbfc; break-inside: avoid; }
.warn { background: #fff8ec; border-color: #f0d9ad; }
.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12pt; }
.kpis { display: flex; gap: 8pt; margin: 6pt 0 8pt; }
.kpi { flex: 1; border: 1px solid var(--line); border-radius: 8px; padding: 6pt 9pt; }
.kpi b { display: block; font-size: 15pt; color: var(--accent); }
.kpi span { font-size: 8.4pt; color: var(--mut); }
.pb { break-before: page; }
ol, ul { margin: 3pt 0 7pt 16pt; padding: 0; } li { margin: 2pt 0; }
.foot { font-size: 8.2pt; color: var(--mut); }
"""

H = []; A = H.append
A(f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Reliable Under Pressure: Summary</title><style>{css}</style></head><body>')

# ---------------- page 1: the answer
A('<div class="eyebrow">SupeRR Selector Season 2 · Rajasthan Royals · IPL 2027 auction</div>')
A('<h1>Reliable Under Pressure</h1>')
A('<div class="lead">Which players hold their nerve when a match is on the line, and which of them Rajasthan Royals should back at the IPL 2027 auction. '
  'A short summary for the judges; the full methodology report is attached separately.</div>')
p1 = [x['player'] for x in BL.values() if x['call'] == 'Back - priority 1']
ret = [x['player'] for x in BL.values() if x['call'] == 'Retain']
A(f'''<div class="answer"><b>Our answer in one line.</b> Back {names(p1)} first: they are reliable under pressure <i>and</i> fill RR's two measured gaps
(death-overs batting in chases, and pace bowling). Keep {names(ret)}, RR's only player in our top 10.</div>''')
A('<div class="kpis">' + ''.join(f'<div class="kpi"><b>{v}</b><span>{k}</span></div>' for v, k in [
    (f'{s1["raw_deliveries"]:,}', 'balls analysed (IPL and T20Is, 2022–26)'), (f'{s3["pressure_share"]:.0%}', 'of balls are high pressure'),
    (f'{s4["bat_eligible"]} / {s4["bowl_eligible"]}', 'batters / bowlers compared'), ('20', 'players in the two lists')]) + '</div>')
A('<h3>Top 10 batters under pressure</h3>')
A(plist(FB, 'bat'))
A('<h3>Top 10 bowlers under pressure</h3>')
A(plist(FW, 'bowl'))
A('<p class="foot">*Stays top 10 = share of 300 re-runs (each with matches randomly re-sampled) in which the player is still in the top 10: a measure of how firm the place is. '
  'Usual = the same player on ordinary balls. Small sample = under 100 pressure balls. Clutch-dependent = the rank leans on the "rises to the occasion" part of the score, '
  'which our time-split test found less repeatable. All names come from the supplied data pack.</p>')

# ---------------- page 2: who RR should back
A('<h2 class="pb">Who Rajasthan Royals should back</h2>')
bp, wt, wp_ = rr['bat_pressure_phase'], rr['bowl_pressure_type'], rr['bowl_pressure_phase']
D = 'Death (16-20)'
A(f'''<p>We first measured RR's own pressure record in IPL 2025–26 against the rest of the league, to see where RR are short:</p>
<ul><li><b>Biggest gap: finishing chases.</b> In overs 16–20 of pressure chases RR strike at {bp[D]['RR']['SR']} against {bp[D]['Rest of IPL']['SR']} for other teams,
hit fewer boundaries ({bp[D]['RR']['boundary_pct']}% vs {bp[D]['Rest of IPL']['boundary_pct']}% of balls) and lose far more win probability.</li>
<li><b>Second gap: pace bowling.</b> RR's pace bowlers take a wicket every {wt['Pace']['RR']['balls_per_wkt']} pressure balls (league {wt['Pace']['Rest of IPL']['balls_per_wkt']}),
and RR bowl fewer dot balls at the death ({wp_[D]['RR']['dot_pct']}% vs {wp_[D]['Rest of IPL']['dot_pct']}%).</li>
<li><b>Strength: spin.</b> RR's spinners take a pressure wicket every {wt['Spin']['RR']['balls_per_wkt']} balls (league {wt['Spin']['Rest of IPL']['balls_per_wkt']}), so more spin adds depth, not a fix.</li></ul>''')
A('<p>Each of the 20 players then gets one call from fixed rules, combining the gap they fill with how firm their rating is:</p>')
order = ['Retain', 'Back - priority 1', 'Back - priority 2', 'Depth option', 'Watch']
what = {'Retain': 'Already at RR; keep if retention allows', 'Back - priority 1': 'Fills an RR gap and the rating is firm',
        'Back - priority 2': 'Fills an RR gap; rating less firm', 'Depth option': 'Reliable, but where RR are not short',
        'Watch': 'Less certain (no IPL record, small sample, or less firm rating)'}
rows = []
for c in order:
    ps = [x for x in BL.values() if x['call'] == c]
    if ps:
        rows.append([call_chip(ps[0]['player']), e(what[c]),
                     '<br>'.join(f"{e(x['player'])} <span class='mut sm'>({'bat' if x['role'] == 'bat' else 'bowl'} #{x['rank']} · {e(x['need'].lower())})</span>" for x in ps)])
A(table(['Call', 'Meaning', 'Players'], rows))
A('<p class="foot">Death finisher = at least 25% of the player\'s pressure balls came in overs 16–20. Price, availability and the official 2027 retention and auction lists '
  'are not in the data and should be checked before bidding.</p>')

# ---------------- page 3: how we did it
A('<h2 class="pb">How we found them</h2>')
A(flow())
A(f'''<h3>1. What "pressure" means</h3>
<p>Pressure is not "the last five overs". We built a win-probability model from the data (the same idea broadcasters use for win predictors), then asked of every
ball: <b>how much could this one ball change who wins?</b> That number is the <b>Leverage Index</b>, borrowed from baseball analytics. An average ball scores 1;
we call a ball high pressure when it scores 1.5 or more. Games already decided are removed so nobody gains from slogging in a lost cause.</p>
<p>It behaves the way pressure should: on these balls batters are dismissed <b>{ct['high']['out_pct'] / ct['medium']['out_pct'] - 1:.0%} more often</b>
({ct['high']['out_pct']}% vs {ct['medium']['out_pct']}% per ball), and pressure builds through a run chase.</p>
<h3>2. How performance is measured fairly</h3>
<ul><li>Every ball is worth what it did to the team's chance of winning, and to its expected runs.</li>
<li>Results are adjusted for <b>who you faced</b> (a spell against a top IPL batting line-up counts for more than one against a weak team) and for the stage of the innings.</li>
<li>Small samples are pulled toward the player's normal level (a long-established statistical technique, James–Stein shrinkage), so a lucky few overs cannot top the list.</li>
<li>Four measures are combined: impact on winning, run value, how much better than usual the player is under pressure, and how often they deliver.</li>
<li>To qualify, a player needs at least 60 pressure balls (10 overs), at least 6 innings with pressure balls, and a match in 2025 or 2026.</li></ul>
<h3>3. How the final order was set</h3>
<p>The rating was computed three ways (all data, IPL only, recent seasons weighted more) and averaged, then stress-tested by re-running it 300 times on re-sampled
matches and 4,000 times with random weightings. A player's "stays top 10" figure comes from these re-runs.</p>''')

# ---------------- page 4: checks
A('<h2 class="pb">How we checked our work</h2>')
ai, ro = au['A_integrity'], au['C_robustness']
A(table(['Check', 'Result'], [
    ['Data rebuilt correctly', f'Official "won by N wickets" results reproduced {ai["won_by_wickets_reproduced"]}; "won by N runs" {ai["won_by_runs_exact_pct"]}% exactly'],
    ['Numbers in the lists recounted from raw balls', 'All 20 players match' if not au['B_recount']['mismatches'] else f"{len(au['B_recount']['mismatches'])} mismatches"],
    ['Same result every run', 'Random seeds fixed, so the pipeline reproduces identical outputs'],
    ['Drop any one of the four measures', f"Batters kept: {', '.join(str(v) for v in ro['bat']['leave_one_component_out_overlap_of_10'].values())} of 10; "
                                          f"bowlers kept: {', '.join(str(v) for v in ro['bowl']['leave_one_component_out_overlap_of_10'].values())} of 10"],
    ['Stricter pressure threshold (LI ≥ 2.0 instead of 1.5)', f"{li2['bat']['overlap_final_top10']} batters and {li2['bowl']['overlap_final_top10']} bowlers stay in the top 10"],
]))
both_b = [p for p in [x['player'] for x in FB[:10]] if p in li2['bat']['top10_at_2.0']]
both_w = [p for p in [x['player'] for x in FW[:10]] if p in li2['bowl']['top10_at_2.0']]
A(f'<p><b>Most robust names</b> (top 10 at both pressure thresholds): {e(names(both_b))} (batting); {e(names(both_w))} (bowling).</p>')
A('<h3>Does it predict the future?</h3>')
A(f'<p>We rebuilt every rating using only 2022–24 and compared it with what players actually did under pressure in 2025–26. {e(holdout_text(au["D_out_of_sample"]))}</p>')
A('<div class="box warn"><b>What this means.</b> Pressure performance is only partly a stable skill; a player\'s underlying quality is the most reliable signal. '
  'That is why our method pulls every pressure number toward the player\'s own normal level, and why we flag players whose rank depends on the less repeatable '
  '"clutch" part of the score. We did not tune the lists to this one test, because that would be fitting to the answer.</div>')
if pm:
    A('<h3>A separate check: a machine-learning model on public data</h3>')
    A('<p>As an independent comparison we trained a separate model on every IPL match 2008–2026 (open data from Cricsheet, 1,243 matches) plus public IPL auction '
      'prices 2013–2025, with its own simple definition of pressure (death overs, or chases needing 9+ an over). It is kept completely apart from our lists. '
      'Both were frozen at the end of 2024 and scored against 2025–26 (1 = perfect ordering, 0 = no better than chance):</p>')
    rows = []
    for role, lab in (('bat', 'Batters'), ('bowl', 'Bowlers')):
        for k, h in pm['roles'][role]['head_to_head_2025_26'].items():
            rows.append([lab, "the model's rule" if 'model pressure rule' in k else 'our Leverage-Index rule', f"{h['public_model']['rho']:+.2f}", f"{h['superrr_method']['rho']:+.2f}"])
    A(table(['', 'Pressure judged by', 'Public model', 'Our method'], rows))
    v = re.sub('<[^>]+>', '', pm_verdict(pm)).replace('Which is closer? ', '')
    A(f'<p class="foot">{e(v)}</p>')
    fb, fw = pm['roles']['bat']['forecast_2027'], pm['roles']['bowl']['forecast_2027']
    A(f'''<p><b>Where the two agree.</b> The public model's own 2027 lists share {fb['overlap_top10']} batters and {fw['overlap_top10']} bowlers with ours
({e(names(t['player'] for t in fb['model_top10'] if t['our_final_rank'] and t['our_final_rank'] <= 10))}; {e(names(t['player'] for t in fw['model_top10'] if t['our_final_rank'] and t['our_final_rank'] <= 10))}).
Its batting list leans toward expensive top-order batters, and its bowling model found almost no repeatable signal, so we keep our lists, which also use T20I
evidence and are matched to RR's needs.</p>''')

# ---------------- page 5: limits + glossary
A('<h2 class="pb">What the data cannot tell us</h2>')
thin = [f"{x['player']} ({x['P_balls']})" for x in FB[:10] + FW[:10] if int(x['P_balls']) < 100]
unt = [x['player'] for x in BL.values() if 'IPL-untested' in x['flags']]
A(f'''<ul>
<li><b>Small samples.</b> Even the busiest players face only a few hundred pressure balls. Under 100: {e(names(thin))}.</li>
<li><b>No IPL record.</b> {e(names(unt))} {'is' if len(unt) == 1 else 'are'} rated on T20I evidence only.</li>
<li><b>First-innings pressure.</b> By this measure no single first-innings ball reaches high pressure; big swings there build up over many balls.</li>
<li><b>Price and availability.</b> The data has no auction prices, injuries or 2027 retention decisions. These must be checked before bidding.</li>
<li><b>Data correction.</b> An updated ball file (November 2026) added the real extras runs; every result here uses it.</li></ul>''')
A('<h2>Glossary</h2>')
A(table(['Term', 'Plain meaning'], [
    ['Win probability', 'The batting side\'s chance of winning before a ball, from a model fitted to these matches'],
    ['Leverage Index (LI)', 'How much one ball can change the win probability, relative to an average ball (1 = average)'],
    ['Pressure ball', 'A ball with LI of 1.5 or more, in a game not already decided'],
    ['Run value', 'Runs scored minus the batting resources used up (a wicket uses a lot)'],
    ['Shrinkage', 'Pulling a small-sample number toward a sensible centre, so luck counts for less'],
    ['Stays top 10', 'Share of 300 re-sampled re-runs in which the player is still top 10'],
    ['Core / clutch-dependent', 'Core = top 10 on underlying pressure quality alone; clutch-dependent = rank relies more on "better than usual under pressure"'],
]))
A('<p class="foot">Full methodology, every rule and all tables: SupeRR_Pressure_Report.pdf. Code: Python standard library only, fully reproducible '
  '(analysis/run_all.sh). Public-model data: Cricsheet (Open Data Commons Attribution License) and a public IPL auction-history dataset.</p>')
A('</body></html>')
os.makedirs(os.path.dirname(os.path.abspath(DEST)), exist_ok=True)
open(DEST, 'w', encoding='utf-8').write(''.join(H))
print('wrote', DEST)
