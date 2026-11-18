"""STEP 8 - Which of the 20 reliable-under-pressure players RR should back at the IPL 2027 auction.

Fixed rules (no judgement calls per player):
  Status   RR 2026 squad (comp 3298 mapping)            -> Retain;  otherwise auction target.
  Need     batters: >= 25% of pressure balls at the death (16-20) -> Death finisher (RR's biggest measured gap);
                    >= 50% in the powerplay -> Top order;  else Middle overs.
           bowlers: pace -> Pace (RR's pace strike rate and death-over dots trail the league);
                    spin -> Spin depth (RR's pressure spin is already above league level).
  Fills an RR gap = Death finisher or Pace.
  Confidence flags: Clutch-dependent (step7 tier), thin sample (< 100 pressure balls),
                    IPL-untested (no IPL pressure balls / not in the IPL 2026 data).
  Call     Retain                    already RR
           Back - priority 1         auction target, fills a gap, Core, not thin, IPL-tested
           Back - priority 2         auction target, fills a gap, but clutch-dependent or thin
           Depth option              auction target, no gap filled, Core, not thin, IPL-tested
           Watch                     everything else (IPL-untested, or no gap and a confidence flag)
"""
import sys, os, json, csv

OUT = sys.argv[1]
J = lambda f: json.load(open(os.path.join(OUT, f), encoding='utf-8'))
R = lambda f: list(csv.DictReader(open(os.path.join(OUT, f), encoding='utf-8')))
rr, au = J('rr_fit.json'), J('audit.json')
tier = {t['player']: t for r in au['E_tiers'].values() for t in r}
ORDER = ['Retain', 'Back - priority 1', 'Back - priority 2', 'Depth option', 'Watch']
PACE = ('fast', 'medium')

rows = []
for role in ('bat', 'bowl'):
    fin = {r['player']: r for r in R(f'FINAL_{role}.csv')}
    for p in rr['profiles'][role]:
        n = p['player']; f = fin[n]; ph = p['phase_share']
        if role == 'bat':
            death, pp = ph.get('Death (16-20)', 0), ph.get('Powerplay (1-6)', 0)
            need = 'Death finisher' if death >= 0.25 else ('Top order' if pp >= 0.5 else 'Middle overs')
            gap = need == 'Death finisher'
        else:
            pace = any(k in p['style'].lower() for k in PACE)
            need = 'Pace' if pace else 'Spin depth'
            gap = pace
        clutch = tier[n]['tier'] != 'Core'
        thin = int(f['P_balls']) < 100
        untested = float(f['IPL_share_P']) == 0 or p['team_2026'] == 'not in IPL 2026 data'
        flags = [x for x, on in (('clutch-dependent', clutch), ('thin sample', thin), ('IPL-untested', untested)) if on]
        if p['in_rr_2026']:
            call = 'Retain'
        elif untested:
            call = 'Watch'
        elif gap and not clutch and not thin:
            call = 'Back - priority 1'
        elif gap:
            call = 'Back - priority 2'
        elif not clutch and not thin:
            call = 'Depth option'
        else:
            call = 'Watch'
        rows.append({'role': role, 'rank': int(f['final_rank']), 'player': n, 'style': p['style'], 'team_2026': p['team_2026'],
                     'status': 'RR player (2026 squad)' if p['in_rr_2026'] else 'Auction target (outside RR)',
                     'need': need, 'fills_gap': gap, 'tier': tier[n]['tier'], 'P_balls': int(f['P_balls']),
                     'boot_p_top10': float(f['ens_boot_p_top10']), 'flags': flags, 'call': call,
                     'death_share': round(ph.get('Death (16-20)', 0), 3)})
rows.sort(key=lambda r: (ORDER.index(r['call']), r['role'] != 'bat', r['rank']))
json.dump({'rules': __doc__, 'order': ORDER, 'rows': rows}, open(os.path.join(OUT, 'rr_backlist.json'), 'w', encoding='utf-8'), indent=1)
for r in rows:
    print(f"{r['call']:<18} {r['role']:<4} #{r['rank']:<2} {r['player']:<20} {r['need']:<15} {r['status']:<28} {r['tier']:<16} {', '.join(r['flags'])}")
