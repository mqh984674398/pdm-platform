"""Hotelling T² (Mahalanobis distance) against the verified healthy reference windows (D-045).

Unsupervised: no fault labels are used. The reference is the set of feature windows inside the verified
healthy period; it is not evaluated when there are too few of them for the number of features. A window
counts as anomalous only when the statistic exceeds its F-based limit on two consecutive windows, so a
single noisy window does not flag. The finding can raise a component to WATCH at most (set by fusion).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from scipy import stats

from app.monitoring.schemas import FeatureVector

ALPHA = 0.001  # false-alarm rate of one window against a healthy reference
MIN_REFERENCE = 15
MIN_PER_FEATURE = 3  # reference windows per feature
SHRINK = 0.1  # pull the covariance towards its diagonal so it stays invertible


@dataclass(frozen=True)
class T2Finding:
    usable: bool
    flagged: bool = False
    value: float | None = None
    limit: float | None = None
    n_reference: int = 0
    features: tuple[str, ...] = ()
    reason: str = ""  # why it is not usable: TOO_FEW_REFERENCE | NO_FEATURES | MISSING_VALUES


def _matrix(vectors: Sequence[FeatureVector], features: Sequence[str]) -> np.ndarray | None:
    rows = [[v.values.get(f) for f in features] for v in vectors]
    if any(x is None for r in rows for x in r):
        return None
    return np.asarray(rows, dtype=float)


def limit(n: int, p: int, alpha: float = ALPHA) -> float:
    """Upper control limit of one new observation against n reference windows with p features."""
    return float(p * (n + 1) * (n - 1) / (n * (n - p)) * stats.f.ppf(1 - alpha, p, n - p))


def t2_values(reference: np.ndarray, x: np.ndarray) -> np.ndarray:
    mu = reference.mean(axis=0)
    cov = np.atleast_2d(np.cov(reference, rowvar=False, ddof=1))
    cov = (1 - SHRINK) * cov + SHRINK * np.diag(np.diag(cov))
    inv = np.linalg.pinv(cov)
    d = np.atleast_2d(x) - mu
    return np.einsum("ij,jk,ik->i", d, inv, d)


def assess(
    reference: Sequence[FeatureVector], recent: Sequence[FeatureVector], features: Sequence[str]
) -> T2Finding:
    """``recent``: the newest windows of the same lifecycle, oldest first (the last two decide)."""
    feats = tuple(features)
    if not feats:
        return T2Finding(usable=False, reason="NO_FEATURES")
    ref = _matrix(reference, feats)
    n = 0 if ref is None else len(ref)
    p = len(feats)
    if ref is None or n < max(MIN_REFERENCE, MIN_PER_FEATURE * p):
        return T2Finding(usable=False, n_reference=n, features=feats, reason="TOO_FEW_REFERENCE")
    last = recent[-2:]
    x = _matrix(last, feats)
    if x is None or len(x) < 1:
        return T2Finding(usable=False, n_reference=n, features=feats, reason="MISSING_VALUES")
    lim = limit(n, p)
    vals = t2_values(ref, x)
    flagged = len(vals) == 2 and bool((vals > lim).all())
    return T2Finding(True, flagged, float(vals[-1]), lim, n, feats)
