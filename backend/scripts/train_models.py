"""Trainer job (T022): fit decision-tree and XGBoost models on SIMULATED feature windows.

For each component type: lifecycle-grouped 5-fold cross-validation and a time split (train before
360 h, test from 384 h on), both checked by ``assert_no_leakage``; then a final model on all windows,
registered with its version and feature schema. Writes the evaluation report (JSON and Markdown,
marked SIMULATED PERFORMANCE) to OUT_DIR.

    python scripts/train_models.py --models var/models --report ../contracts/evidence/T022
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
DATA = BACKEND.parent / "Data"
sys.path.insert(0, str(BACKEND))

SEED = 7
CUTOFF_H, EMBARGO_H = 360.0, 24.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    ap.add_argument("--version", default="1.0.0")
    args = ap.parse_args()

    import numpy as np

    import app.main  # noqa: F401
    from app.monitoring.features.definitions import FEATURE_SETS
    from app.prediction.models.dataset import (
        assert_no_leakage,
        feature_names,
        group_folds,
        matrix,
        time_split,
    )
    from app.prediction.models.labels import LABELS, definition
    from app.prediction.models.registry import ModelRecord, ModelRegistry, stamp
    from app.prediction.models.train import KINDS, PARAMS, degraded_probability, fit, metrics
    from app.simulation.training_data import scenario_samples

    scenarios = sorted(p.name.split("_")[0] for p in (DATA / "scenarios").glob("S*_*"))
    pool = [s for sid in scenarios for s in scenario_samples(DATA, sid)]
    registry = ModelRegistry(args.models)
    report = {
        "is_simulated": True,
        "title": "SIMULATED PERFORMANCE — not evidence of real-world accuracy",
        "seed": SEED,
        "time_split": {"cutoff_h": CUTOFF_H, "embargo_h": EMBARGO_H},
        "types": [],
    }
    for ctype in LABELS:
        fs = FEATURE_SETS[ctype]
        ref = f"{fs.feature_set}@{fs.version}"
        samples = [s for s in pool if s.vector.feature_ref == ref]
        y_all = [s.label for s in samples]
        if len(set(y_all)) < 2:
            report["types"].append(
                {"component_type": ctype.value, "skipped": "only one class in the simulated data"}
            )
            continue
        positive_groups = {s.group for s in samples if s.label}
        if len(positive_groups) < 2:
            report["types"].append(
                {"component_type": ctype.value, "skipped": "fewer than 2 degraded installations"}
            )
            continue
        feats = feature_names(samples)
        x, y = matrix(samples, feats)
        entry = {
            "component_type": ctype.value,
            "feature_ref": ref,
            "features": feats,
            "windows": len(samples),
            "positives": int(y.sum()),
            "groups": len({s.group for s in samples}),
            "scenarios": sorted({s.scenario for s in samples}),
            "label": definition(ctype),
            "models": {},
        }
        folds = group_folds(samples, 5, SEED)
        tr_t, te_t = time_split(samples, CUTOFF_H, EMBARGO_H)
        for tr, te in folds:
            assert_no_leakage(samples, tr, te, by_group=True)
        assert_no_leakage(samples, tr_t, te_t, by_group=False, embargo_h=EMBARGO_H)
        for kind in KINDS:
            ys, ps, covered = [], [], set()
            for tr, te in folds:
                if len(set(y[tr])) < 2:
                    continue
                m = fit(kind, x[tr], y[tr], SEED)
                ys += y[te].tolist()
                ps += degraded_probability(m, x[te]).tolist()
                covered |= {samples[i].group for i in te}
            cv = metrics(ys, ps)
            if not positive_groups <= covered or cv["roc_auc"] is None:
                entry["models"][kind] = {
                    "not_registered": "grouped validation could not test every degraded installation "
                    "(a fold's training data had no degraded windows); the model is not validated"
                }
                continue
            m = fit(kind, x[tr_t], y[tr_t], SEED) if len(set(y[tr_t])) == 2 else None
            ts = metrics(y[te_t], degraded_probability(m, x[te_t])) if m is not None else None
            final = fit(kind, x, y, SEED)
            prefix = "dt" if kind == "decision_tree" else "xgb"
            rec = registry.save(
                final,
                ModelRecord(
                    model_id=f"{prefix}-{ctype.value.lower().replace('_', '-')}@{args.version}",
                    kind=kind,
                    component_type=ctype,
                    feature_ref=ref,
                    features=feats,
                    label_definition=definition(ctype),
                    training_scenarios=entry["scenarios"],
                    params=PARAMS[kind],
                    seed=SEED,
                    metrics={"grouped_cv": cv, "time_split": ts},
                    is_simulated=True,
                    created_at=stamp(),
                ),
            )
            entry["models"][kind] = {
                "model_id": rec.model_id,
                "sha256": rec.sha256,
                "grouped_cv": cv,
                "time_split": ts,
            }
        report["types"].append(entry)
        print(
            ctype.value,
            len(samples),
            {k: (v["grouped_cv"]["f1"], v["grouped_cv"]["roc_auc"]) for k, v in entry["models"].items()},
        )
    args.report.mkdir(parents=True, exist_ok=True)
    (args.report / "evaluation.json").write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    (args.report / "model_index.json").write_text(
        registry.index_path.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (args.report / "evaluation.md").write_text(markdown(report), encoding="utf-8")
    _ = np


def fmt(m: dict | None, k: str) -> str:
    if not m or m.get(k) is None:
        return "—"
    return f"{m[k]:.3f}" if isinstance(m[k], float) else str(m[k])


def markdown(r: dict) -> str:
    cut, emb = r["time_split"]["cutoff_h"], r["time_split"]["embargo_h"]
    lines = [
        "# 模型评估（模拟数据）/ Model evaluation (SIMULATED PERFORMANCE)",
        "",
        "以下数字全部来自模拟场景，标签取自模拟器的真值，不代表真实设备上的准确率。",
        "All numbers come from simulated scenarios with labels from the simulator's ground truth. "
        "They are not evidence of accuracy on real equipment.",
        "",
        f"Seed {r['seed']}. Lifecycle-grouped 5-fold CV (no installation in both sets); time split: train "
        f"< {cut:g} h, test ≥ {cut + emb:g} h. "
        "Both splits pass `assert_no_leakage`. Threshold 0.5 on uncalibrated scores. "
        "Grouped CV is the primary "
        "measure: the time split keeps the same installations on both sides, so it is optimistic.",
        "",
        "| Type | Model | Windows (degraded) | CV precision | CV recall | CV F1 | CV ROC AUC "
        "| Time-split F1 | Time-split ROC AUC |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for t in r["types"]:
        if "skipped" in t:
            lines.append(f"| {t['component_type']} | — | skipped: {t['skipped']} | | | | | | |")
            continue
        for kind, m in t["models"].items():
            if "not_registered" in m:
                lines.append(
                    f"| {t['component_type']} | {kind}: not registered | {t['windows']} ({t['positives']}) "
                    f"| {m['not_registered']} | | | | | |"
                )
                continue
            cv, ts = m["grouped_cv"], m["time_split"]
            lines.append(
                f"| {t['component_type']} | {m['model_id']} | {t['windows']} ({t['positives']}) | "
                f"{fmt(cv, 'precision')} | {fmt(cv, 'recall')} | {fmt(cv, 'f1')} | {fmt(cv, 'roc_auc')} | "
                f"{fmt(ts, 'f1')} | {fmt(ts, 'roc_auc')} |"
            )
    lines += ["", "Labels / 标签: " + "; ".join(t["label"] for t in r["types"] if "label" in t), ""]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
