import csv, sys, collections as C
DATA=sys.argv[1]
F={r:list(csv.DictReader(open(f'out/FINAL_{r}.csv'))) for r in ('bat','bowl')}
teams={r['team_id']:r['team_name'] for r in csv.DictReader(open(DATA+'/teams.csv'))}
B=[b for b in csv.DictReader(open('out/balls_pressure.csv')) if b['dead']=='0' and float(b['PI'])>=1.5]
for role in ('bat','bowl'):
    print('=====',role)
    for r in F[role][:10]:
        pid=r['player_id']
        if role=='bat':
            mine=[b for b in B if b['striker_id']==pid and b['faced']=='1']; opp=C.Counter(teams.get(b['bowl_team'],b['bowl_team']) for b in mine)
            print(r['final_rank'],r['player'],'P SR',r['P_SR'],'vs base',r['B_SR'],'| P avg',r['P_avg'],'vs',r['B_avg'],'| Pballs',r['P_balls'],'inn',r['P_innings'],'| C2',r['C2_adjRV_per_ball'],'C3',r['C3_clutch_delta'],'C4',r['C4_consistency'])
        else:
            mine=[b for b in B if b['bowler_id']==pid]; opp=C.Counter(teams.get(b['bat_team'],b['bat_team']) for b in mine)
            print(r['final_rank'],r['player'],'P econ',r['P_econ'],'vs base',r['B_econ'],'| P b/w',r['P_balls_per_wkt'],'vs',r['B_balls_per_wkt'],'| wkts',r['P_wkts'],'Pballs',r['P_balls'],'inn',r['P_innings'],'| C1',r['C1_WPA_per100'],'C3',r['C3_clutch_delta'],'C4',r['C4_consistency'])
        print('     opp:',opp.most_common(6), 'seasons',sorted(C.Counter(b['season'] for b in mine).items()))
