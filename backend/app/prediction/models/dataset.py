"""Labeled feature windows and the splits used to evaluate models without leakage (TST-03/04).

A sample is one feature window of one component with a label from the simulator's ground truth.
``group`` is ``scenario/lifecycle``: windows of one installation are strongly correlated, so a group
is never split between training and test. The time split additionally holds out everything after a
cutoff, with an embargo gap, so no test window precedes or touches a training window of its group.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from app.monitoring.schemas import FeatureVector


@dataclass(frozen=True)
class Sample:
    vector: FeatureVector
    label: int  # 1 = degraded per the simulated ground truth
    scenario: str
    hours: float  # window start, hours since the scenario start

    @property
    def group(self) -> str:
        return f"{self.scenario}/{self.vector.lifecycle_id}"


class LeakageError(AssertionError):
    pass


def matrix(samples: Sequence[Sample], features: Sequence[str]) -> tuple[np.ndarray, np.ndarray]:
    x = np.array(
        [
            [s.vector.values.get(f) if s.vector.values.get(f) is not None else np.nan for f in features]
            for s in samples
        ],
        dtype=float,
    )
    return x, np.array([s.label for s in samples], dtype=int)


def feature_names(samples: Sequence[Sample]) -> list[str]:
    names = sorted({k for s in samples for k, v in s.vector.values.items() if v is not None})
    return names


def group_folds(samples: Sequence[Sample], k: int, seed: int = 0) -> list[tuple[list[int], list[int]]]:
    """k folds over whole groups (lifecycle-grouped cross-validation)."""
    groups = sorted({s.group for s in samples})
    rng = np.random.default_rng(seed)
    order = list(rng.permutation(groups))
    folds = [set(order[i::k]) for i in range(k)]
    out = []
    for f in folds:
        test = [i for i, s in enumerate(samples) if s.group in f]
        train = [i for i, s in enumerate(samples) if s.group not in f]
        if test and train:
            out.append((train, test))
    return out


def time_split(
    samples: Sequence[Sample], cutoff_h: float, embargo_h: float = 24.0
) -> tuple[list[int], list[int]]:
    train = [i for i, s in enumerate(samples) if s.hours < cutoff_h]
    test = [i for i, s in enumerate(samples) if s.hours >= cutoff_h + embargo_h]
    return train, test


def assert_no_leakage(
    samples: Sequence[Sample],
    train: Sequence[int],
    test: Sequence[int],
    by_group: bool = True,
    embargo_h: float = 0.0,
) -> None:
    """Refuse a split that shares a window, (optionally) a group, or lets test precede training."""
    tr, te = set(train), set(test)
    if tr & te:
        raise LeakageError("a window is in both training and test")
    keys = {(samples[i].group, samples[i].vector.window.start) for i in tr}
    if any((samples[i].group, samples[i].vector.window.start) in keys for i in te):
        raise LeakageError("the same window appears in both sets")
    if by_group:
        shared = {samples[i].group for i in tr} & {samples[i].group for i in te}
        if shared:
            raise LeakageError(f"groups in both training and test: {sorted(shared)[:3]}")
    else:
        latest: dict[str, float] = {}
        for i in tr:
            latest[samples[i].group] = max(latest.get(samples[i].group, -1e9), samples[i].hours)
        for i in te:
            g = samples[i].group
            if g in latest and samples[i].hours < latest[g] + embargo_h:
                raise LeakageError(f"test window of {g} at {samples[i].hours:.0f} h is not after training")
