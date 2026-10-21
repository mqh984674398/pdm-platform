import sys
from pathlib import Path
BACKEND = Path("/home/claude/pdm-platform/backend"); DATA = BACKEND.parent/"Data"; sys.path.insert(0,str(BACKEND))
import numpy as np, warnings; warnings.filterwarnings("ignore")
import app.main  # noqa
from app.monitoring.features.definitions import FEATURE_SETS
from app.prediction.models.dataset import feature_names, group_folds, matrix
from app.prediction.models.labels import LABELS
from app.prediction.models.train import fit, degraded_probability, metrics
from app.simulation.training_data import scenario_samples
from app.equipment.schemas import ComponentType as C
scen = sorted(p.name.split("_")[0] for p in (DATA/"scenarios").glob("S*_*"))
pool = [s for sid in scen for s in scenario_samples(DATA, sid)]
K = 12  # first windows of each installation = its own reference (causal)
def add_norm(samples, feats):
    x, y = matrix(samples, feats)
    groups = np.array([s.group for s in samples]); order = np.array([s.vector.window.start.timestamp() for s in samples])
    z = np.full_like(x, np.nan); slope = np.full_like(x, np.nan)
    for g in set(groups):
        idx = np.where(groups == g)[0]; idx = idx[np.argsort(order[idx])]
        ref = x[idx[:K]]
        med = np.nanmedian(ref, 0); sc = np.nanstd(ref, 0); sc = np.maximum(sc, 0.01*np.abs(med)+1e-9)
        z[idx] = (x[idx]-med)/sc
        for j, i in enumerate(idx):  # trend over the last 8 windows (causal)
            w = idx[max(0, j-7):j+1]
            if len(w) >= 4:
                tt = order[w]/86400; tt = tt - tt[0]
                for c in range(x.shape[1]):
                    yy = z[w, c]; ok = ~np.isnan(yy)
                    if ok.sum() >= 4 and np.ptp(tt[ok]) > 0: slope[i, c] = np.polyfit(tt[ok], yy[ok], 1)[0]
    return x, y, z, slope
for ctype in (C.BALL_SCREW, C.PNEUMATIC_CYLINDER):
    fs = FEATURE_SETS[ctype]; ref = f"{fs.feature_set}@{fs.version}"
    samples = [s for s in pool if s.vector.feature_ref == ref]
    feats = feature_names(samples)
    x, y, z, slope = add_norm(samples, feats)
    folds = group_folds(samples, 5, 7)
    for name, X in (("current (absolute features)", x), ("+ per-installation z", np.hstack([x, z])), ("+ z + 2-day trend", np.hstack([x, z, slope]))):
        ys, ps = [], []
        for tr, te in folds:
            if len(set(y[tr])) < 2: continue
            m = fit("xgboost", X[tr], y[tr], 7); ys += y[te].tolist(); ps += degraded_probability(m, X[te]).tolist()
        mt = metrics(ys, ps)
        print(f"{ctype.value:20} {name:30} P={mt['precision']:.3f} R={mt['recall']:.3f} F1={mt['f1']:.3f} AUC={mt['roc_auc']:.3f} n={mt['n']}")
