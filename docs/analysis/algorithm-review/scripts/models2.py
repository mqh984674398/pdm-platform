exec(open('models.py').read().split('for ctype in')[0])
from collections import defaultdict
fs = FEATURE_SETS[C.PNEUMATIC_CYLINDER]; ref=f"{fs.feature_set}@{fs.version}"
samples=[s for s in pool if s.vector.feature_ref==ref]; feats=feature_names(samples); x,y=matrix(samples,feats)
folds=group_folds(samples,5,7); pred=np.full(len(y),np.nan)
for tr,te in folds:
    if len(set(y[tr]))<2: continue
    m=fit("xgboost",x[tr],y[tr],7); pred[te]=degraded_probability(m,x[te])
by=defaultdict(lambda:[0,0,0])
for i,s in enumerate(samples):
    if np.isnan(pred[i]): continue
    b=by[s.group]; b[0]+=y[i]; b[1]+= int(y[i] and pred[i]>=.5); b[2]+=int((not y[i]) and pred[i]>=.5)
for g,(p,tp,fp) in sorted(by.items()): print(f"{g:40} positives={p:3} caught={tp:3} false_pos={fp}")
print(feats)
