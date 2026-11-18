"""PUBLIC MODEL 2 - link Cricsheet names (e.g. 'SA Yadav') to data-pack player IDs, ONLY so the two methods can be
compared player by player. Uses IPL 2022-26 matches present in both sources: same date, and inside each team's XI the
names must agree on surname and first initial, or share a full-name token. A link is kept when it is the unique winner across >= 2 shared matches.
usage: python -I pm2_link.py <data_pack_dir> <out_dir>
"""
import sys, os, csv, re, collections as C

DATA, OUT = sys.argv[1], sys.argv[2]
rd = lambda p: list(csv.DictReader(open(p, encoding='utf-8')))
comps = {c['comp_id']: c for c in rd(os.path.join(DATA, 'competitions.csv'))}
pname = {}
for r in rd(os.path.join(DATA, 'competition_team_player_mapping.csv')):
    pname[r['player_id']] = r['player_name']
xi = C.defaultdict(set)
for r in rd(os.path.join(DATA, 'playing_eleven.csv')):
    xi[(r['match_id'], r['team_id'])].add(r['player_id'])
dp = C.defaultdict(list)   # date -> [(match_id, home_id, away_id)]
for m in rd(os.path.join(DATA, 'matches.csv')):
    if comps[m['comp_id']]['comp_name'].startswith('IPL'):
        dp[m['match_date']].append((m['match_id'], m['home_team_id'], m['away_team_id'], m['home_team'], m['away_team']))

def norm(s):
    return re.sub(r'[^a-z ]', '', s.lower().replace('bangalore', 'bengaluru').replace('kings xi punjab', 'punjab kings'))

def compatible(cs, full):
    """Cricsheet 'SA Yadav' / 'Shubman Gill' vs data pack 'Suryakumar Yadav': same surname and first initial."""
    a, b = norm(cs).split(), norm(full).split()
    if not a or not b:
        return 0
    if a[-1] != b[-1]:
        # e.g. 'CV Varun' vs 'Varun Chakravarthy', 'KL Rahul' vs 'Lokesh Rahul': a shared full-name token (3+ letters)
        return 1 if {t for t in a if len(t) >= 3} & set(b) else 0
    if a == b:
        return 2
    # same surname: any initial / given-name token in common ('KL Rahul' ~ 'Lokesh Rahul', 'Tilak Varma' ~ 'Namboori Tilak Varma')
    la = {ch for t in a[:-1] for ch in (t if len(t) <= 3 else t[0])}
    lb = {t[0] for t in b[:-1]}
    return 1 if (la & lb) or (set(a[:-1]) & set(b[:-1])) else 0

votes = C.defaultdict(C.Counter); shared = 0
for m in rd(os.path.join(OUT, 'pm_matches.csv')):
    if int(m['season']) < 2022:
        continue
    cand = [x for x in dp.get(m['date'], []) if {norm(x[3]), norm(x[4])} == {norm(m['team1']), norm(m['team2'])}]
    if len(cand) != 1:
        continue
    shared += 1
    mid, hid, aid, hn, an = cand[0]
    for tname, plist in ((m['team1'], m['players1']), (m['team2'], m['players2'])):
        tid = hid if norm(tname) == norm(hn) else aid
        ids = xi[(mid, tid)]
        for cs in plist.split('|'):
            sc = {pid: compatible(cs, pname.get(pid, '')) for pid in ids}
            best = max(sc.values(), default=0)
            top = [p for p, v in sc.items() if v == best and v > 0]
            if len(top) == 1:
                votes[cs][top[0]] += 1
link = {}
for cs, c in votes.items():
    (pid, n), *rest = c.most_common()
    if n >= 2 and (not rest or rest[0][1] * 3 < n):
        link[cs] = pid
with open(os.path.join(OUT, 'pm_link.csv'), 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f); w.writerow(['cricsheet_name', 'player_id', 'player_name'])
    for cs, pid in sorted(link.items()):
        w.writerow([cs, pid, pname[pid]])
dup = [p for p, n in C.Counter(link.values()).items() if n > 1]
print(f'shared matches {shared}, cricsheet names seen {len(votes)}, linked {len(link)}, ids linked twice {len(dup)}')
