"""Sequential statistics on deviation series (L4-07): EWMA, one-sided CUSUM, running median."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

Z_CLIP = 6.0  # single windows cannot dominate EWMA and CUSUM


def ewma(z: Sequence[float], lam: float, start: float = 0.0) -> list[float]:
    out, m = [], start
    for x in z:
        m = lam * float(np.clip(x, -Z_CLIP, Z_CLIP)) + (1 - lam) * m
        out.append(m)
    return out


def cusum_upper(z: Sequence[float], k: float, start: float = 0.0) -> list[float]:
    """Upper CUSUM of clipped deviations: accumulates sustained shifts above ``k``. ``start``
    continues a series from its previous value."""
    out, s = [], start
    for x in z:
        s = max(0.0, s + float(np.clip(x, -Z_CLIP, Z_CLIP)) - k)
        out.append(s)
    return out


def running_median(z: Sequence[float], n: int) -> list[float | None]:
    """Median of the last ``n`` values; None until ``n`` values exist."""
    return [float(np.median(z[i - n + 1 : i + 1])) if i + 1 >= n else None for i in range(len(z))]
