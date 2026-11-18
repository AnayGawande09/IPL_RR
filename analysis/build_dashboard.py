"""Build the explainer dashboard (single self-contained HTML) from pipeline outputs.
usage: python -I build_dashboard.py <analysis/out> <dashboard.html>"""
import sys, os, json, csv, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from holdout_text import holdout_text, pm_verdict, pm_uses

OUT, DEST = sys.argv[1], sys.argv[2]
J = lambda f: json.load(open(os.path.join(OUT, f), encoding='utf-8'))
R = lambda f: list(csv.DictReader(open(os.path.join(OUT, f), encoding='utf-8')))
s1, s2, s3, s4 = J('step1_log.json'), J('step2_log.json'), J('step3_log.json'), J('step4_log_main.json')
rr, au, fit = J('rr_fit.json'), J('audit.json'), J('fit_text.json')
bl = J('rr_backlist.json')
call = {r['player']: r['call'] for r in bl['rows']}
sens, li2 = J('sensitivity.json'), J('sensitivity_li2.json')
tier = {t['player']: t for r in au['E_tiers'].values() for t in r}
prof = {p['player']: p for r in rr['profiles'].values() for p in r}

def players(role):
    out = []
    for r in R(f'FINAL_{role}.csv')[:10]:
        p = r['player']
        d = {'rank': int(r['final_rank']), 'name': p, 'balls': int(r['P_balls']), 'inn': int(r['P_innings']),
             'p10': float(r['ens_boot_p_top10']), 'ipl': float(r['IPL_share_P']),
             'tier': tier[p]['tier'], 'c2': tier[p]['C2_rank'], 'team': prof[p]['team_2026'], 'style': prof[p]['style'],
             'rr': prof[p]['in_rr_2026'], 'fit': fit[role][p], 'call': call[p],
             'ranks': [r['rank_main'], r['rank_ipl'] or '–', r['rank_recent']]}
        if role == 'bat':
            d.update(pv=r['P_SR'], uv=r['B_SR'], lab='SR')
        else:
            d.update(pv=r['P_econ'], uv=r['B_econ'], lab='Econ')
        out.append(d)
    return out

ct = s3['contrast']
oos = au['D_out_of_sample']
def oos_rows():
    rows = []
    for k, v in oos['bat'].items():
        if not isinstance(v, dict) or 'ci90' not in v:
            continue
        kw = k.replace('raw pressure strike rate', 'raw pressure economy (lower = better)')
        w = oos['bowl'][kw]
        short = {'Our composite (2022-24 only)': 'Our rating', 'Naive: raw pressure run value per ball': 'Raw pressure run value',
                 'Naive: raw pressure strike rate': 'Raw pressure SR / econ', 'Naive: overall run value (ignores pressure)': 'Overall run value'}
        rows.append({'label': short[k],
                     'ours': k.startswith('Our'),
                     'bat': [v['rho_vs_2025_26_pressure_RV']] + v['ci90'], 'bowl': [w['rho_vs_2025_26_pressure_RV']] + w['ci90']})
    return rows

D = {
    'bat': players('bat'), 'bowl': players('bowl'),
    'board': bl['rows'], 'board_order': bl['order'],
    'next': {r: [[int(x['final_rank']), x['player'], int(x['P_balls'])] for x in R(f'FINAL_{r}.csv')[10:15]] for r in ('bat', 'bowl')},
    'n': {'deliveries': s1['raw_deliveries'], 'innings': s1['innings'], 'superover': s1['super_over_deliveries_removed'],
          'par': s1['global_par'], 'pressure_share': s3['pressure_share'], 'dead_share': s3['tier_share']['dead'],
          'dead_cut': round(s3['dead_LI_max'], 2), 'out_hi': ct['high']['out_pct'], 'out_med': ct['medium']['out_pct'],
          'mh_dot': s3['MH_OR_dotstreak3'], 'mh_wk': s3['MH_OR_wk12_2'],
          'll1': s2['wp_cv']['inn1']['A']['logloss'], 'll1b': s2['wp_cv']['inn1']['baseline_logloss'],
          'll2': s2['wp_cv']['inn2']['C']['logloss'], 'll2b': s2['wp_cv']['inn2']['baseline_logloss'],
          'iters': s4['backfit_iterations'], 'lam': s4['ridge_lambda'],
          'pool_bat': s4['bat_eligible'], 'pool_bowl': s4['bowl_eligible'],
          'rel_bat': s4['bat_reliability']['pressure_RV']['split_half_r'], 'rel_bowl': s4['bowl_reliability']['pressure_RV']['split_half_r'],
          'base_bat': s4['bat_reliability']['baseline_RV']['split_half_r'], 'base_bowl': s4['bowl_reliability']['baseline_RV']['split_half_r']},
    'oos_text': holdout_text(au['D_out_of_sample']),
    'audit': au['A_integrity'], 'recount': len(au['B_recount']['mismatches']),
    'rob': au['C_robustness'], 'oos': oos_rows(), 'oos_n': [oos['bat']['players_tested'], oos['bowl']['players_tested']],
    'oos_q': [[oos[r]['top_quarter_by_composite_mean_2025_26_RV'], oos[r]['other_three_quarters_mean_2025_26_RV']] for r in ('bat', 'bowl')],
    'li2': {r: [li2[r]['overlap_final_top10'], li2[r]['eligible']] for r in ('bat', 'bowl')},
    'spec': {r: {k: sens[r][k]['overlap_top10'] for k in ('ipl', 'recent', 'alt')} for r in ('bat', 'bowl')},
    'rr_bat': rr['bat_pressure_phase'], 'rr_bowl': rr['bowl_pressure_phase'], 'rr_type': rr['bowl_pressure_type'],
    'rr_all': [rr['bat_pressure'], rr['bowl_pressure']], 'rr_res': rr['rr_results'], 'squad': rr['rr_squad_size'],
    'rated': sum(1 for r in rr['rr_squad_2026'] if r['bat_rank'] or r['bowl_rank']),
}
PMR = os.path.join(os.path.dirname(os.path.abspath(OUT)), '..', 'public_model', 'out', 'pm_results.json')
D['pm'] = json.load(open(PMR, encoding='utf-8')) if os.path.exists(PMR) else None
D['pm_call'] = pm_verdict(D['pm']) if D['pm'] else ''
D['pm_uses'] = pm_uses(D['pm']) if D['pm'] else ''
data = json.dumps(D, ensure_ascii=False).replace('</', '<\\/')
tpl = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dashboard_template.html'), encoding='utf-8').read()
assert tpl.count('/*DATA*/null') == 1
os.makedirs(os.path.dirname(os.path.abspath(DEST)), exist_ok=True)
page = tpl.replace('/*DATA*/null', data)
open(DEST, 'w', encoding='utf-8').write(page)
# full standalone document for local serving (serve_dashboard.py)
site = os.path.join(os.path.dirname(os.path.abspath(DEST)), 'site')
os.makedirs(site, exist_ok=True)
# the hosted site also serves the two PDFs (the Claude-hosted copy cannot serve files, so it gets no links)
links = []
for fn, lab in (('SupeRR_Judges_Summary.pdf', 'Summary (PDF)'), ('SupeRR_Pressure_Report.pdf', 'Full methodology report (PDF)')):
    src = os.path.join(os.path.dirname(os.path.abspath(DEST)), fn)
    if os.path.exists(src):
        shutil.copyfile(src, os.path.join(site, fn))
        links.append(f'<a href="{fn}" target="_blank" rel="noopener">{lab}</a>')
SITE_LINKS = '<div class="dl">' + ''.join(links) + '</div>' if links else ''
open(os.path.join(site, 'index.html'), 'w', encoding='utf-8').write(
    '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
    '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
    '<style>body{margin:0}</style></head><body>\n' + page.replace('<!--SITE_LINKS-->', SITE_LINKS) + '\n</body></html>\n')
print('wrote', DEST, 'and', os.path.join(site, 'index.html'), len(data), 'bytes of data')
