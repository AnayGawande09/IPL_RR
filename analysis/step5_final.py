"""STEP 5 - Model-averaged final ranking.

Final score = mean composite across three specifications that differ only in evidence scope:
  main   : all IPL + T20I pressure balls, equal weight
  ipl    : IPL balls only (closest to the auction context)
  recent : all balls, recency-weighted (half-life 2 seasons)
A player missing from a specification (e.g. no IPL sample) is averaged over the specifications he has.
The rejected 'alt' definition (within-innings top decile) is reported only as a robustness check.
"""
import sys, os, json, csv, collections as C
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *

OUT = sys.argv[1]
SPECS = ['main', 'ipl', 'recent']
final = {}
for role in ('bat', 'bowl'):
    tabs = {m: {r['player_id']: r for r in read_csv(os.path.join(OUT, f'rank_{role}_{m}.csv'))} for m in SPECS + ['alt']}
    rows = []
    for pid, r in tabs['main'].items():
        scores = [float(tabs[m][pid]['composite']) for m in SPECS if pid in tabs[m]]
        ptop = [float(tabs[m][pid]['boot_p_top10']) for m in SPECS if pid in tabs[m]]
        out = dict(r)
        out['ens_score'] = round(sum(scores) / len(scores), 4)
        out['n_specs'] = len(scores)
        out['ens_boot_p_top10'] = round(sum(ptop) / len(ptop), 3)
        for m in SPECS + ['alt']:
            out[f'rank_{m}'] = tabs[m][pid]['rank'] if pid in tabs[m] else ''
        rows.append(out)
    rows.sort(key=lambda r: -r['ens_score'])
    for i, r in enumerate(rows):
        r['final_rank'] = i + 1
    first = ['final_rank', 'player', 'player_id', 'ens_score', 'n_specs', 'ens_boot_p_top10', 'rank_main', 'rank_ipl',
             'rank_recent', 'rank_alt']
    fields = first + [k for k in rows[0] if k not in first]
    write_csv(os.path.join(OUT, f'FINAL_{role}.csv'), rows, fields)
    final[role] = rows
    print(f'===== FINAL {role}')
    for r in rows[:15]:
        print(r['final_rank'], r['player'], r['ens_score'], 'specs', r['n_specs'], 'ranks m/i/r/alt', r['rank_main'],
              r['rank_ipl'], r['rank_recent'], r['rank_alt'], 'Ptop10', r['ens_boot_p_top10'], 'Pballs', r['P_balls'],
              'IPLshare', r['IPL_share_P'])
json.dump({role: [{k: r[k] for k in ('final_rank', 'player', 'player_id', 'ens_score')} for r in final[role][:10]]
           for role in final}, open(os.path.join(OUT, 'FINAL_top10.json'), 'w'), indent=1)
