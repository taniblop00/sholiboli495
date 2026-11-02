import re,json,sqlite3
from datetime import datetime,timedelta
c=sqlite3.connect('state.db');c.row_factory=sqlite3.Row
pos=[dict(r) for r in c.execute("select * from positions where strategy='scalp' and status='closed' order by id")]
ticks=[]
for line in open('cycle.log'):
    m=re.match(r'\[(\S+ \S+)\] \[scalp\] tick: (.*)',line)
    if not m: continue
    ts=datetime.strptime(m.group(1),'%Y-%m-%d %H:%M:%S')
    parts=[]
    for part in m.group(2).split(' | '):
        mm=re.match(r'(.+?) ([+-]\d+\.\d)% \(pk',part.strip())
        if mm: parts.append((mm.group(1),float(mm.group(2))))
    ticks.append((ts,parts))
def local(s): return datetime.fromisoformat(s).replace(tzinfo=None)+timedelta(hours=2)
paths={}
for p in pos:
    o,cl=local(p['opened_at']),local(p['closed_at'])
    same=[q for q in pos if q['symbol']==p['symbol'] and local(q['opened_at'])<=cl and local(q['closed_at'])>=o]
    same.sort(key=lambda q:q['opened_at']); idx=same.index(p)
    path=[]
    for ts,parts in ticks:
        if o<=ts<=cl+timedelta(seconds=5):
            occ=[g for s,g in parts if s==p['symbol']]
            if len(occ)>idx: path.append(((ts-o).total_seconds()/60,occ[idx]))
    # add actual exit mark
    fl=c.execute("select mark from fills where pos_id=? and side='SELL'",(p['id'],)).fetchall()
    ex=(fl[-1][0]/p['entry_mark']-1)*100 if fl else None
    rug = p['exit_reason']=='scalp_liquidity_drop' and p['pnl_pct']<=-99
    path.append(((cl-o).total_seconds()/60, -100.0 if rug else ex))
    paths[p['id']]=dict(sym=p['symbol'],dex=p['dex'],path=path,actual=p['pnl_pct'],rug=rug)
COST=0.075  # multiplicative round-trip cost observed (~7-8%)
def net(g): return ((1+g/100)*(1-COST)-1)*100
def sim(path,tp1=12,frac=0.5,sl=-6,be=1.0,tp2=25,trail=None,tmax=15,tmin_gain=4):
    rem=1.0;real=0.0;stop=sl;hit1=False;peak=-999
    for t,g in path:
        if g<=-99: real+=rem*-100; return real
        peak=max(peak,g)
        if g<=stop: real+=rem*net(g); return real   # fills at observed (gapped) price
        if not hit1 and tp1 and g>=tp1:
            real+=frac*net(g); rem-=frac; hit1=True; stop=max(stop,be)
        if g>=tp2: real+=rem*net(g); return real
        if trail and hit1 and g<=peak-trail: real+=rem*net(g); return real
        if t>=tmax and g<tmin_gain and not hit1: real+=rem*net(g); return real
    t,g=path[-1]; real+=rem*net(g); return real
variants={
 'actual(v1)':None,
 'v2: 50%@+12, BE+1, rest TP+25':dict(),
 'v2b: 50%@+10, BE+2, rest TP+22':dict(tp1=10,be=2,tp2=22),
 'all-out TP+15, SL-6':dict(tp1=None,tp2=15),
 'all-out TP+12, SL-6':dict(tp1=None,tp2=12),
}
for name,kw in variants.items():
    res=[]
    for i,d in paths.items():
        r=d['actual'] if kw is None else sim(d['path'],**kw)
        res.append((i,d['sym'],d['dex'],r))
    def stats(rs):
        w=[x for x in rs if x>0];l=[x for x in rs if x<=0]
        return f"n={len(rs)} WR={len(w)/len(rs)*100:.0f}% avgW={sum(w)/max(1,len(w)):+.1f}% avgL={sum(l)/max(1,len(l)):+.1f}% sum={sum(rs):+.1f}% PF={sum(w)/max(1e-9,-sum(l)):.2f}"
    print(name);print('  all scalps   ',stats([r for *_,r in res]))
    print('  ex-meteora   ',stats([r for _,_,dx,r in res if dx!='meteora']))
    print('  ',' '.join(f"{s[:6]}:{r:+.0f}" for _,s,_,r in res))
