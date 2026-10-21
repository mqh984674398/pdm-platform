#!/usr/bin/env python3
"""Walk one new component through the whole predictive-maintenance flow against a running server.

Plant structure -> signal mapping -> installation -> online pipeline -> verified healthy reference ->
recommended prediction configuration -> validate (data, compile, replay, simulation) -> publish ->
activate -> the component's health report uses the active version. Every step prints PASS or FAIL and
the process exits non-zero on the first failure. Uses only the Python standard library.

It acts on the SIMULATED demo fleet (device SIM-S03 of source sim-fleet) and re-homes that device's
screw signals to the new component, so run it on a throw-away demo server (tools/run_demo.*), not on a
production installation.

    python tools/verify_workflow.py --base http://127.0.0.1:8765                      # development headers
    python tools/verify_workflow.py --base http://127.0.0.1:8765 --password <pw>      # signed-in admin
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from http.cookiejar import CookieJar

SOURCE, DEVICE = "sim-fleet", "SIM-S03"
SCREW = "BS1"  # suffix of the screw's signal ids on the demo device (A03-BS1.speed, A03-BS1.torque)


class Failure(Exception):
    pass


class Api:
    def __init__(self, base: str, password: str | None):
        self.base = base.rstrip("/")
        self.cookies = urllib.request.HTTPCookieProcessor(CookieJar())
        self.opener = urllib.request.build_opener(self.cookies)
        self.headers = {"Content-Type": "application/json", "X-PDM-CSRF": "1"}
        if password is None:
            self.headers |= {"X-PDM-User": "verify-admin", "X-PDM-Role": "admin"}
        else:
            self("POST", "/api/auth/login", {"user_id": "admin", "password": password})

    def __call__(self, method: str, path: str, body=None, expect: tuple[int, ...] = (200, 201, 204)):
        req = urllib.request.Request(
            self.base + path,
            method=method,
            headers=self.headers,
            data=None if body is None else json.dumps(body).encode(),
        )
        try:
            with self.opener.open(req, timeout=300) as resp:
                raw, status = resp.read(), resp.status
        except urllib.error.HTTPError as e:
            raw, status = e.read(), e.code
        if status not in expect:
            raise Failure(f"{method} {path} -> {status}: {raw[:300].decode(errors='replace')}")
        return json.loads(raw) if raw else None


def step(name: str, fn):
    t0 = time.time()
    try:
        out = fn()
    except Failure as e:
        print(f"FAIL  {name}\n      {e}")
        sys.exit(1)
    print(f"PASS  {name}  ({time.time() - t0:.1f}s)")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="http://127.0.0.1:8765")
    ap.add_argument("--password", help="password of the 'admin' account (server in local auth mode)")
    args = ap.parse_args()
    api = Api(args.base, args.password)
    sfx = format(int(time.time()), "x")
    ws, pr, mc = f"VW-{sfx}", f"VP-{sfx}", f"VM-{sfx}"
    cid = f"{mc}-BS1"
    name = {"zh": "验证脚本创建", "en": "Created by verify_workflow"}

    def need(cond: bool, msg: str):
        if not cond:
            raise Failure(msg)

    step("server is up", lambda: need(api("GET", "/api/health")["status"] == "ok", "health is not ok"))

    def structure():
        api("PUT", f"/api/plant-nodes/{ws}", {"node_id": ws, "parent_id": None, "level": "WORKSHOP", "name": name, "sort": 0})
        api("PUT", f"/api/plant-nodes/{pr}", {"node_id": pr, "parent_id": ws, "level": "PROCESS", "name": name, "sort": 0})
        api("POST", "/api/plant-machines", {"machine_id": mc, "process_id": pr, "name": name, "device_id": DEVICE})
        api("PUT", f"/api/plant-machines/{mc}/components/{cid}", {"component_id": cid, "type": "BALL_SCREW", "name": name})

    step(f"1 plant structure: workshop > process > machine ({DEVICE}) > component {cid}", structure)

    def mapping():
        sug = api("GET", f"/api/datasources/{SOURCE}/devices/{DEVICE}/suggestions")
        state = api("GET", "/api/signal-config")
        cfg = state["content"]
        here = lambda m: (m["data_source_id"], m["device_id"]) == (SOURCE, DEVICE)  # noqa: E731
        picked = {x["signal_id"] for x in sug["signals"] if x["signal_id"].split("-")[-1].startswith(SCREW)}
        need(len(picked) == 2, f"expected 2 screw signals, found {sorted(picked)}")
        keep_m = [m for m in cfg["mappings"] if here(m) and m["signal_id"] not in picked]
        keep_ids = {m["signal_id"] for m in keep_m}
        api("PUT", f"/api/signal-config/sources/{SOURCE}/devices/{DEVICE}", {
            "comment": "verify_workflow",
            "base_version": state["version"]["version"] if state["version"] else 0,
            "signals": [s for s in cfg["signals"] if s["signal_id"] in keep_ids]
            + [s for s in sug["signals"] if s["signal_id"] in picked],
            "mappings": keep_m + [{**m, "component_id": cid} for m in sug["mappings"] if m["signal_id"] in picked],
            "groups": [], "visualizations": [],
        })  # fmt: skip

    step("2 map the screw's speed and torque signals to the component", mapping)
    step("3 register the installation date", lambda: api("POST", f"/api/components/{cid}/lifecycles", {"installed_at": "2026-04-01T00:00:00Z", "comment": "verify"}))

    def pipeline():
        total = 0
        for _ in range(4):  # one run covers up to 31 days of data
            r = api("POST", "/api/pipeline/run", {"machine_id": mc})
            need(r["catalog"] == "ready", f"operating-condition catalog is {r['catalog']}")
            total += r["windows_added"]
            if not r["windows_added"]:
                break
        need(total > 0, "the pipeline produced no feature windows")
        return total

    n = step("4 build feature windows from the data source (online pipeline)", pipeline)
    print(f"      {n} windows")

    def reference():
        cov = api("GET", f"/api/components/{cid}/feature-coverage")
        need(bool(cov), "no feature coverage")
        c = cov[0]
        start = time.mktime(time.strptime(c["start"], "%Y-%m-%dT%H:%M:%SZ"))
        end = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(start + 3 * 86400))
        api("POST", "/api/baselines/verified", {
            "component_id": cid, "lifecycle_id": c["lifecycle_id"], "feature_ref": c["feature_ref"],
            "regime_id": None, "window": {"start": c["start"], "end": end}, "comment": "verify_workflow: first 3 days",
        })  # fmt: skip

    step("5 confirm the healthy reference (first three days of the simulated data)", reference)

    def draft():
        rec = api("GET", f"/api/components/{cid}/recommended-config")
        need(rec["compile"]["ok"], f"recommended configuration does not compile: {rec['compile']['issues']}")
        return api("POST", f"/api/components/{cid}/prediction-configs", {"content": rec["content"]})

    cfg = step("6 draft the recommended prediction configuration", draft)
    cfg_id = cfg["config_id"]

    def validate():
        v = api("POST", f"/api/prediction-configs/{cfg_id}/validate", {})
        bad = [c["name"] for c in v["validation"] if not c["ok"]]
        need(v["status"] == "VALIDATED" and not bad, f"validation failed: {bad}")
        return [c["name"] for c in v["validation"]]

    names = step("7 validate: data, compile, replay, simulation", validate)
    print(f"      checks: {', '.join(names)}")
    step("8 publish (immutable)", lambda: need(api("POST", f"/api/prediction-configs/{cfg_id}/publish", {"comment": "verify_workflow"})["status"] == "PUBLISHED", "not published"))
    step("9 activate", lambda: need(api("POST", f"/api/prediction-configs/{cfg_id}/activate", {})["active"], "not active"))

    def health():
        rep = api("GET", f"/api/components/{cid}/health")
        need(rep.get("config_version") == cfg_id, f"health report uses {rep.get('config_version')!r}, not {cfg_id}")
        return rep["decision"]["health_state"]

    state = step("10 the component's health report uses the active configuration", health)
    print(f"      health state: {state}")
    print(f"\nALL STEPS PASSED  (component {cid}, configuration {cfg_id})")


if __name__ == "__main__":
    main()
