import json,sys,itertools
from datetime import datetime
pools=[json.loads(l) for l in open('analysis/pumpswap_ohlcv.jsonl')]
def ts(s): return datetime.fromisoformat(s.replace('Z','+00:00')).timestamp()
def run(entry,exitp,cost,pools=pools,verbose=False):
    trades=[]
    for p in pools:
        c=sorted(p['ohlcv'],key=lambda x:x[0])
        if len(c)<20: continue
        created=ts(p['created']); i=6; n=len(c); last_exit=-1e18; cnt=0
        while i<n-1:
            t,o,h,l,cl,v=c[i]; age=(t+60-created)/60
            if age<entry['amin'] or age>entry['amax'] or t<last_exit+entry['cool']*60 or cnt>=2: i+=1; continue
            # need contiguous last 5 candles
            if c[i][0]-c[i-5][0]!=300: i+=1; continue
            r5=(cl/c[i-5][4]-1)*100; v5=sum(x[5] for x in c[i-4:i+1]); r1=(cl/o-1)*100
            if not(entry['r5lo']<=r5<=entry['r5hi'] and v5>=entry['v5'] and r1>0 and r1<entry['r1max']): i+=1; continue
            # enter at next open
            e=c[i+1][1]; j=i+1; rem=1.0; pnl=0.0; stop=e*(1+exitp['sl']/100); hit1=False; peak=e; t0=c[j][0]; mfe=0; mae=0
            def net(px): return ((px/e)*(1-cost)-1)*100
            done=False
            while j<n:
                t,o,h,l,cl,v=c[j]
                if c[j][0]-t0>exitp['tmax']*60 and (not hit1):
                    pnl+=rem*net(o); done=True; break
                if o<=stop: pnl+=rem*net(o*0.98); done=True; break      # gap through stop
                if l<=stop: pnl+=rem*net(stop*0.98); done=True; break   # conservative: stop before TP in same candle
                mfe=max(mfe,(h/e-1)*100)
                if exitp.get('tp1') and not hit1 and h>=e*(1+exitp['tp1']/100):
                    pnl+=exitp['frac']*net(e*(1+exitp['tp1']/100)); rem-=exitp['frac']; hit1=True; stop=max(stop,e*(1+exitp['be']/100))
                if h>=e*(1+exitp['tp2']/100): pnl+=rem*net(e*(1+exitp['tp2']/100)); done=True; break
                peak=max(peak,h)
                if exitp.get('trail') and hit1: stop=max(stop,peak*(1-exitp['trail']/100))
                if hit1 and c[j][0]-t0>exitp['tmax_runner']*60: pnl+=rem*net(cl); done=True; break
                j+=1
            if not done: pnl+=rem*net(c[-1][4]); j=n-1
            trades.append(dict(pool=p['name'],t=c[i+1][0],pnl=pnl,hold=(c[min(j,n-1)][0]-t0)/60,mfe=mfe))
            last_exit=c[min(j,n-1)][0]; cnt+=1; i=j+1
    return trades
def stats(tr):
    if not tr: return 'n=0'
    w=[x['pnl'] for x in tr if x['pnl']>0]; l=[x['pnl'] for x in tr if x['pnl']<=0]
    span=(max(x['t'] for x in tr)-min(x['t'] for x in tr))/3600 or 1
    eq=1.0
    for x in sorted(tr,key=lambda x:x['t']): eq*=1+0.12*x['pnl']/100   # 12% of equity per trade, sequential approx
    return (f"n={len(tr):3d} WR={len(w)/len(tr)*100:4.0f}% avgW={sum(w)/max(1,len(w)):+5.1f}% avgL={sum(l)/max(1,len(l)):+5.1f}% "
            f"exp/trade={sum(x['pnl'] for x in tr)/len(tr):+5.2f}% PF={sum(w)/max(1e-9,-sum(l)):.2f} worst={min(x['pnl'] for x in tr):+.0f}% "
            f"hold~{sum(x['hold'] for x in tr)/len(tr):.0f}m eq12%={eq:.2f}x")
ENTRIES={
 'fresh 3-20m, r5 8-30%':dict(amin=3,amax=20,r5lo=8,r5hi=30,v5=15000,r1max=15,cool=30),
 'fresh 3-30m, r5 5-25%':dict(amin=3,amax=30,r5lo=5,r5hi=25,v5=10000,r1max=12,cool=30),
 'mid 30-180m, r5 8-30%':dict(amin=30,amax=180,r5lo=8,r5hi=30,v5=15000,r1max=15,cool=30),
 'old 3-12h, r5 5-25%':dict(amin=180,amax=720,r5lo=5,r5hi=25,v5=10000,r1max=12,cool=30),
}
EXITS={
 'v1: TP25 SL-7 (all out)':dict(sl=-7,tp2=25,tmax=30,tmax_runner=30),
 'TP15 SL-5':dict(sl=-5,tp2=15,tmax=15,tmax_runner=15),
 'TP20 SL-5':dict(sl=-5,tp2=20,tmax=15,tmax_runner=15),
 'v2: 50%@+15,BE+3,run TP40/trail10, SL-5':dict(sl=-5,tp1=15,frac=0.5,be=3,tp2=40,trail=10,tmax=12,tmax_runner=30),
 'v2b: 50%@+12,BE+2,run TP30/trail8, SL-5':dict(sl=-5,tp1=12,frac=0.5,be=2,tp2=30,trail=8,tmax=12,tmax_runner=25),
}
if __name__=='__main__':
    print('pools with data:',sum(1 for p in pools if len(p['ohlcv'])>=20))
    for cost in (0.075,0.045):
        print(f'\n=== round-trip cost {cost*100:.1f}% ===')
        for en,ep in ENTRIES.items():
            print(f'-- entry: {en}')
            for xn,xp in EXITS.items():
                print(f'   {xn:42s} {stats(run(ep,xp,cost))}')
