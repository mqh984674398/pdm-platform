import sys; sys.argv=['x','/tmp/claude-0/exp/ignore.json']
exec(open('exp.py').read().split('results = {}')[0])
from scipy.stats import theilslopes
from app.prediction.routing.builtin import PROFILES
for cid,h in sorted(svc.histories.items()):
    feats=PROFILES[h.component_type][1]
    for lc,ref in h.references.items():
        f=next((x for x in feats if x in ref.stats),None)
        if not f: continue
        vs=[v for v in h.vectors if v.lifecycle_id==lc and ref.window.start<=v.window.start and v.window.end<=ref.window.end and v.values.get(f) is not None]
        if len(vs)<5: continue
        t=[(v.window.start-vs[0].window.start).total_seconds()/86400 for v in vs]; y=[v.values[f] for v in vs]
        slope=theilslopes(y,t)[0]; span=t[-1]-t[0]
        drift=slope*span/max(ref.stats[f].std,1e-9)
        print(f"{cid:8} {lc:14} {f:24} n={len(vs):3} drift across reference = {drift:+.1f} spreads")
