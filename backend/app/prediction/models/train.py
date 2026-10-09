"""Fit and evaluate the two model families. Deterministic for a given seed."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
from sklearn.metrics import (
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.tree import DecisionTreeClassifier
from xgboost import XGBClassifier

KINDS = ("decision_tree", "xgboost")
PARAMS: dict[str, dict[str, Any]] = {
    "decision_tree": {"max_depth": 4, "min_samples_leaf": 10, "class_weight": "balanced"},
    "xgboost": {
        "n_estimators": 120,
        "max_depth": 3,
        "learning_rate": 0.1,
        "subsample": 0.9,
        "colsample_bytree": 0.9,
        "n_jobs": 1,
        "tree_method": "hist",
    },
}


def fit(kind: str, x: np.ndarray, y: np.ndarray, seed: int = 0):
    if kind == "decision_tree":
        return DecisionTreeClassifier(random_state=seed, **PARAMS[kind]).fit(x, y)
    if kind == "xgboost":
        pos = max(int(y.sum()), 1)
        return XGBClassifier(random_state=seed, scale_pos_weight=(len(y) - pos) / pos, **PARAMS[kind]).fit(
            x, y
        )
    raise ValueError(f"unknown model kind {kind}")


def degraded_probability(model, x: np.ndarray) -> np.ndarray:
    return model.predict_proba(x)[:, 1]


def metrics(y: Sequence[int], p: Sequence[float], threshold: float = 0.5) -> dict[str, float | int | None]:
    y, p = np.asarray(y), np.asarray(p)
    pred = (p >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    both = len(set(y.tolist())) == 2
    return {
        "n": int(len(y)),
        "positives": int(y.sum()),
        "tp": int(tp),
        "fp": int(fp),
        "tn": int(tn),
        "fn": int(fn),
        "precision": float(precision_score(y, pred, zero_division=0)),
        "recall": float(recall_score(y, pred, zero_division=0)),
        "f1": float(f1_score(y, pred, zero_division=0)),
        "roc_auc": float(roc_auc_score(y, p)) if both else None,
        "brier": float(brier_score_loss(y, p)) if len(y) else None,
    }
