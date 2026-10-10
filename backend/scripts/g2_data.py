"""G2 evidence data: what the T012-T014 services return on the simulated golden scenarios.

Writes contracts/evidence/G2/g2_data.json for the G2 review page. SIMULATED data only.
Usage: python scripts/g2_data.py ../contracts/evidence/G2/g2_data.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.equipment.operations import analyze_machine  # noqa: E402
from app.equipment.regimes import assign_regimes, learn_catalog  # noqa: E402
from tests.equipment.conftest import scenario, series  # noqa: E402
from tests.quality.conftest import scenario as qscenario  # noqa: E402


def _h(sc, ts) -> float:
    return round(sc.hours_of(ts), 3)


def regimes_s17() -> dict:
    sc, ser = scenario("S17"), series("S17")
    cat = learn_catalog(ser, sc.machine, sc.window(0, 96), "S17-ref")
    rows = []
    for a in assign_regimes(ser, sc.window(0, sc.hours), cat):
        f = {x.feature_id: x.value for x in a.features}
        rows.append(
            {
                "h": _h(sc, a.start),
                "state": a.state.value,
                "status": a.status.value,
                "regime": a.regime_id,
                "speed": f.get("M01-BS1.speed:cruise"),
            }
        )
    truth = [
        {"h": _h(sc, sc.t0.fromisoformat(w["window_start"].replace("Z", "+00:00"))), "recipe": w["recipe_id"]}
        for w in sc.truth
    ]
    regs = [
        {"id": r.regime.regime_id, "band": r.regime.speed_band, "windows": r.window_count}
        for r in cat.regimes
    ]
    return {"reference_h": [0, 96], "regimes": regs, "windows": rows, "truth": truth}


def regimes_s02() -> dict:
    sc, ser = scenario("S02"), series("S02")
    w = sc.window(0, sc.hours)
    cat = learn_catalog(ser, sc.machine, w, "S02-ref")
    rows = []
    for a in assign_regimes(ser, w, cat):
        f = {x.feature_id: x for x in a.features}
        t = f.get("M01-BS1.torque:cruise")
        if a.status.value == "KNOWN" and t is not None:
            rows.append({"h": _h(sc, a.start), "regime": a.regime_id, "torque": t.value, "z": t.normalized})
    regs = [
        {"id": r.regime.regime_id, "band": r.regime.speed_band, "load": r.regime.load_class}
        for r in cat.regimes
    ]
    return {"regimes": regs, "windows": rows}


def cycles_s18() -> dict:
    sc, ser = scenario("S18"), series("S18")
    ops = analyze_machine(sc.machine, ser, sc.window(0, sc.hours), sc.lifecycles())
    pts = [
        {
            "h": _h(sc, c.start),
            "signal": c.signal_id,
            "kind": c.kind.value,
            "complete": c.complete,
            "value": c.duration_s,
        }
        for c in ops.cycles
    ]
    raw = {}
    for s in ser:
        raw[s.signal.signal_id] = {round(float(t), 3): float(v) for t, v in zip(s.t, s.v, strict=True)}
    for p, c in zip(pts, ops.cycles, strict=True):
        if not c.complete:
            p["reported"] = raw[c.signal_id].get(round(c.start.timestamp(), 3))
    summaries = [s.model_dump(mode="json", exclude={"window"}) for s in ops.cycle_summaries]
    return {"cycles": pts, "summaries": summaries, "injected": len(sc.faults["incomplete_operations"])}


def quality() -> list[dict]:
    out = []
    for sid, sigs, a, b in [
        ("S13", ["M01-BS1.speed", "M01-BS1.torque", "M01-CY1.extend_time"], 48, 96),
        ("S14", ["M01-BS1.speed", "M01-BS1.torque", "M01-LM1.speed"], 48, 96),
        ("S15", ["M01-BS1.speed", "M01-BS1.torque"], 48, 96),
        ("S16", ["M01-BS1.speed", "M01-BS1.torque", "M01-VC1.release_time"], 72, 120),
        ("S16", ["M01-VC1.release_time"], 144, 192),
        ("S20", ["M01-BS1.speed", "M01-CY1.extend_time"], 96, 144),
        ("S01", ["M01-BS1.speed", "M01-BS1.torque", "M01-CY1.extend_time"], 48, 96),
    ]:
        resp = qscenario(sid).report(sigs, a, b)
        rows = [
            {
                "signal": r.signal_id,
                "flags": [f.value for f in r.flags],
                "samples": r.sample_count,
                "missing": r.missing_count,
                "duplicates": r.duplicate_count,
                "out_of_order": r.out_of_order_count,
                "gaps": r.gap_count,
                "median_interval_s": r.median_interval_s,
                "not_evaluated": [f.value for f in r.not_evaluated],
            }
            for r in resp.reports
        ]
        pairs = [
            {
                "pair": f"{p.speed_signal_id} / {p.torque_signal_id}",
                "flags": [f.value for f in p.flags],
                "agreement": p.agreement,
                "tolerance_s": p.tolerance_s,
                "misaligned_windows": len(p.misaligned_windows),
            }
            for p in resp.alignment
        ]
        out.append({"scenario": sid, "window_h": [a, b], "signals": rows, "pairs": pairs})
    return out


def lifecycle_s12() -> dict:
    sc = scenario("S12")
    return {
        "lifecycles": sc.topology["lifecycles"],
        "events": json.loads((sc.dir / "maintenance_events.json").read_text(encoding="utf-8")),
    }


def main(out: Path) -> None:
    data = {
        "note": "SIMULATED data only; produced by the T012-T014 services on the golden scenarios.",
        "quality": quality(),
        "regimes_s02": regimes_s02(),
        "regimes_s17": regimes_s17(),
        "cycles_s18": cycles_s18(),
        "lifecycle_s12": lifecycle_s12(),
    }
    out.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size // 1024} KiB)")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
