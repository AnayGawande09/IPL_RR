import csv, sys, json
def rows(role,mode): return list(csv.DictReader(open(f"out/rank_{role}_{mode}.csv", encoding="utf-8")))
def kendall(a,b):
    common=[p for p in a if p in b]; n=c=d=0
    for i in range(len(common)):
        for j in range(i+1,len(common)):
            s=(a[common[i]]-a[common[j]])*(b[common[i]]-b[common[j]]); c+=s>0; d+=s<0
    return (c-d)/max(c+d,1)
res={}
for role in ('bat','bowl'):
    M=rows(role,'main'); main=[r['player'] for r in M][:10]; RM={r['player']:int(r['rank']) for r in M}
    print('\n',role,'MAIN',main); res[role]={}
    for m in ('alt','ipl','recent'):
        R={r['player']:int(r['rank']) for r in rows(role,m)}
        t=[r['player'] for r in rows(role,m)][:10]
        res[role][m]={'overlap_top10':len(set(main)&set(t)),'kendall_tau_all':round(kendall(RM,R),3),'main_top10_ranks':[R.get(p,None) for p in main]}
        print(m,res[role][m]); print('   ',t)
json.dump(res,open('out/sensitivity.json','w'),indent=1)
# LI >= 2.0 sensitivity against the FINAL (model-averaged) top 10
li2 = {}
for role in ('bat', 'bowl'):
    fin = [r['player'] for r in csv.DictReader(open(f'out/FINAL_{role}.csv', encoding='utf-8'))][:10]
    L = rows(role, 'li2'); RL = {r['player']: int(r['rank']) for r in L}
    li2[role] = {'eligible': len(L), 'overlap_final_top10': len(set(fin) & {r['player'] for r in L[:10]}),
                 'final_top10_ranks_at_2.0': [RL.get(p) for p in fin], 'top10_at_2.0': [r['player'] for r in L[:10]],
                 'not_eligible_at_2.0': [p for p in fin if p not in RL]}
json.dump(li2, open('out/sensitivity_li2.json', 'w'), indent=1)
print('li2', {r: (li2[r]['overlap_final_top10'], li2[r]['eligible']) for r in li2})
