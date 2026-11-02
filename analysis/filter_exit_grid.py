import runpy,io,contextlib,statistics as st,sys
sys.argv=['x']
buf=io.StringIO()
with contextlib.redirect_stdout(buf): g=runpy.run_path(__import__('os').path.join(__import__('os').path.dirname(__import__('os').path.abspath(__file__)),'trade_review.py'))
paths=g['paths'];sim=g['sim'];V=g['VARIANTS']
def stats(res):
    v=[x[0] for x in res]
    if not v: return 'n=0'
    W=[x for x in v if x>0];L=[x for x in v if x<=0]
    pf=sum(W)/-sum(L) if L and sum(L) else 99
    return f"n={len(v):2d} WR={100*len(W)/len(v):3.0f}% avgW={st.mean(W) if W else 0:+5.1f} avgL={st.mean(L) if L else 0:+6.1f} PF={pf:5.2f} exp={st.mean(v):+5.2f} pulls={sum(1 for x in res if x[2]=='PULL')}"
F={'none':lambda r:True,'bs5>=3':lambda r:r['bs5']>=3,'pc5<=20':lambda r:r['pc5']<=20,'bs5>=3&pc5<=20':lambda r:r['bs5']>=3 and r['pc5']<=20,
   'bs5>=3&pc5<=20&age<=8':lambda r:r['bs5']>=3 and r['pc5']<=20 and r['age']<=8,'bs5>=3.5&pc5 6-20&age<=6':lambda r:r['bs5']>=3.5 and 6<=r['pc5']<=20 and r['age']<=6}
X={'v3':V['v3 actual rules (50%@15, BE+3, runner 40/trail10, 30m)'],
 'all@15 max10':V['all-out @+15, SL-5, max 10m'],
 'all@15 SL-4 max8 ts5':dict(sl=-4,tp1=15,f1=1.0,tmax=8,tstop=5,tstop_gain=3),
 'all@18 SL-5 max10':dict(sl=-5,tp1=18,f1=1.0,tmax=10,tstop=6,tstop_gain=2),
 '80%@15 +20%->25 BE10 max10':dict(sl=-5,tp1=15,f1=0.8,be=10,tp2=25,trail=6,tmax=10,tstop=6,tstop_gain=2),
 '70%@15 +30%->25 BE10 max10':dict(sl=-5,tp1=15,f1=0.7,be=10,tp2=25,trail=6,tmax=10,tstop=6,tstop_gain=2),
 '50%@12 50%@20 BE5 max10':dict(sl=-5,tp1=12,f1=0.5,be=5,tp2=20,tmax=10,tstop=6,tstop_gain=2),
}
for cost in (6.0,7.5):
  print('cost',cost)
  for fn,ff in F.items():
    sel=[r for r in paths if ff(r)]
    for xn,xx in X.items(): print(f"  {fn:26s} {xn:28s} {stats([sim(r,xx,cost) for r in sel])}")
print([ (r['id'],r['sym'],round(r['bs5'],1),r['pc5'],round(r['age'],1),r['pull']) for r in paths if r['bs5']>=3 and r['pc5']<=20 and r['age']<=8])
