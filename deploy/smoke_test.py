"""Production-mode smoke test of the deployment package (T028 deployment log).

Unpacks dist/pdm-<version>-windows.zip into a work folder, writes backend/.env for local sign-in with a
PostgreSQL database, creates an administrator through manage_users.py, starts serve.py with the labeled
SIMULATED fleet, and checks over HTTP what a LAN browser would do. Runs on Linux with the build
machine's Python environment; it stands in for, and does not replace, an install on Windows.

    backend/.venv/bin/python deploy/smoke_test.py --db-url postgresql+psycopg://pdm@127.0.0.1:5433/pdmsmoke \\
        --work /tmp/pdm-smoke --log contracts/evidence/T028/deployment_log.txt
"""

from __future__ import annotations

import argparse
import json
import secrets
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile
from datetime import UTC, datetime
from http.cookiejar import CookieJar
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PASSWORD = "smoke-" + secrets.token_hex(8)


class Run:
    def __init__(self, log: Path):
        self.log, self.lines, self.failed = log, [], 0

    def note(self, msg: str) -> None:
        line = f"[{datetime.now(UTC):%Y-%m-%dT%H:%M:%SZ}] {msg}"
        print(line)
        self.lines.append(line)

    def check(self, name: str, ok: bool, detail: str = "") -> None:
        self.failed += not ok
        self.note(f"{'PASS' if ok else 'FAIL'} {name}" + (f" ({detail})" if detail else ""))

    def save(self) -> None:
        self.log.parent.mkdir(parents=True, exist_ok=True)
        self.log.write_text("\n".join(self.lines) + "\n", encoding="utf-8")


def http(opener, method: str, url: str, body: dict | None = None, headers: dict | None = None):
    req = urllib.request.Request(url, method=method, headers={**(headers or {})})
    if body is not None:
        req.data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
    try:
        with opener.open(req, timeout=30) as r:
            return r.status, r.read().decode(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(), dict(e.headers)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db-url", required=True)
    ap.add_argument("--work", type=Path, required=True)
    ap.add_argument("--log", type=Path, required=True)
    ap.add_argument("--port", type=int, default=8090)
    args = ap.parse_args()
    run = Run(args.log)
    zips = sorted((ROOT / "dist").glob("pdm-*-windows.zip"))
    if not zips:
        sys.exit("build the package first: deploy/build_package.py")
    shutil.rmtree(args.work, ignore_errors=True)
    with zipfile.ZipFile(zips[-1]) as z:
        z.extractall(args.work)
    pkg = args.work / "pdm"
    backend = pkg / "backend"
    run.note(f"Unpacked {zips[-1].name} to {pkg} ({sum(1 for _ in pkg.rglob('*'))} entries)")
    for need in [
        "backend/app/main.py",
        "backend/requirements.lock",
        "frontend/dist/index.html",
        "deploy/windows/install.ps1",
        "deploy/serve.py",
        "deploy/datasources.simulated.json",
    ]:
        run.check(f"package contains {need}", (pkg / need).is_file())

    # Production source in the configuration must stay off until approval (SEC-06).
    sources = json.loads((pkg / "deploy/datasources.simulated.json").read_text(encoding="utf-8"))
    prod = json.loads(json.dumps(sources[0]))
    prod["config"].update(
        data_source_id="plant-iot",
        kind="SQL",
        is_simulated=False,
        engine="postgresql",
        host="iot.plant.lan",
        credential_ref="secret://pdm/plant-iot-readonly",
    )
    prod.pop("simulated_datasets", None)
    prod["layout"] = {}
    (pkg / "deploy/datasources.smoke.json").write_text(json.dumps([*sources, prod]), encoding="utf-8")

    env = "\n".join(
        [
            f"PDM_DATABASE_URL={args.db_url}",
            "PDM_AUTH_MODE=local",
            f"PDM_SECRET_KEY={secrets.token_urlsafe(48)}",
            "PDM_STATIC_DIR=../frontend/dist",
            "PDM_DATASOURCES_FILE=../deploy/datasources.smoke.json",
            "PDM_PRODUCTION_DATA_APPROVED=false",
        ]
    )
    (backend / ".env").write_text(env + "\n", encoding="utf-8")
    run.note("Wrote backend/.env: local sign-in, PostgreSQL, static client, production data not approved")

    py = sys.executable
    r = subprocess.run(
        [py, "-m", "alembic", "upgrade", "head"],
        cwd=backend,
        capture_output=True,
        check=False,
        text=True,
    )
    run.check(
        "alembic upgrade head on PostgreSQL",
        r.returncode == 0,
        r.stderr.strip().splitlines()[-1],
    )
    r = subprocess.run(
        [
            py,
            "../deploy/manage_users.py",
            "create-admin",
            "admin1",
            "--name",
            "Smoke admin",
        ],
        cwd=backend,
        input=f"{PASSWORD}\n{PASSWORD}\n",
        capture_output=True,
        check=False,
        text=True,
    )
    run.check(
        "manage_users.py create-admin",
        r.returncode == 0,
        r.stdout.strip() or r.stderr.strip()[-200:],
    )

    devenv = subprocess.run(
        [py, "../deploy/serve.py", "--port", str(args.port)],
        cwd=backend,
        capture_output=True,
        check=False,
        text=True,
        timeout=60,
        env={**__import__("os").environ, "PDM_AUTH_MODE": "dev"},
    )
    run.check(
        "serve.py refuses PDM_AUTH_MODE=dev",
        devenv.returncode != 0,
        devenv.stderr.strip()[-80:],
    )

    log = open(args.work / "server.log", "w")  # noqa: SIM115  (outlives the try block)
    t0 = time.time()
    srv = subprocess.Popen(
        [
            py,
            "../deploy/serve.py",
            "--host",
            "127.0.0.1",
            "--port",
            str(args.port),
            "--simulated-fleet",
        ],
        cwd=backend,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    base = f"http://127.0.0.1:{args.port}"
    anon = urllib.request.build_opener()
    try:
        for _ in range(600):
            try:
                if http(anon, "GET", base + "/api/health")[0] == 200:
                    break
            except OSError:
                pass
            if srv.poll() is not None:
                break
            time.sleep(1)
        st, body, _ = http(anon, "GET", base + "/api/health")
        run.check(
            "server up (migrations, SIMULATED fleet replay)",
            st == 200,
            f"{time.time() - t0:.0f}s, {body}",
        )
        server_log = (args.work / "server.log").read_text()
        run.check(
            "production source skipped until approval",
            "plant-iot" in server_log and "not enabled" in server_log,
        )

        st, body, h = http(anon, "GET", base + "/")
        run.check(
            "browser client served at /",
            st == 200 and '<div id="app"' in body,
            h.get("content-type", ""),
        )
        st, body, _ = http(anon, "GET", base + "/fleet")
        run.check(
            "client routes fall back to index.html",
            st == 200 and '<div id="app"' in body,
        )
        st, _, _ = http(anon, "GET", base + "/api/fleet")
        run.check("API needs sign-in", st == 401, str(st))
        st, _, _ = http(
            anon,
            "GET",
            base + "/api/fleet",
            headers={"X-PDM-User": "x", "X-PDM-Role": "admin"},
        )
        run.check("development headers ignored", st == 401, str(st))
        st, body, _ = http(
            anon,
            "POST",
            base + "/api/auth/login",
            {"user_id": "admin1", "password": "wrong-pass1"},
        )
        run.check("wrong password refused", st == 401, body)

        jar = CookieJar()
        browser = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        st, body, h = http(
            browser,
            "POST",
            base + "/api/auth/login",
            {"user_id": "admin1", "password": PASSWORD},
        )
        cookie = h.get("set-cookie", "").lower()
        run.check(
            "sign-in sets HttpOnly SameSite=Strict cookie",
            st == 200 and "httponly" in cookie and "samesite=strict" in cookie,
            body,
        )
        st, body, _ = http(browser, "GET", base + "/api/fleet")
        fleet = json.loads(body) if st == 200 else {}
        machines = fleet.get("machines", [])
        run.check(
            "fleet overview after sign-in",
            st == 200 and len(machines) > 0,
            f"{len(machines)} machines, simulated={fleet.get('is_simulated')}",
        )
        new = {
            "user_id": "tech1",
            "display_name": "Tech",
            "role": "maintenance",
            "password": "tech-pass-123",
        }
        st, _, _ = http(browser, "POST", base + "/api/auth/users", new)
        run.check("state change without X-PDM-CSRF refused", st == 403, str(st))
        st, _, _ = http(browser, "POST", base + "/api/auth/users", new, {"X-PDM-CSRF": "1"})
        run.check("admin creates maintenance account", st == 200, str(st))
        st, body, _ = http(browser, "GET", base + "/api/llm/health")
        llm = json.loads(body) if st == 200 else {}
        run.check(
            "platform runs without Ollama (LLM health reports unreachable)",
            st == 200 and llm.get("reachable") is False,
            llm.get("detail", "")[:80],
        )

        tech = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
        http(
            tech,
            "POST",
            base + "/api/auth/login",
            {"user_id": "tech1", "password": "tech-pass-123"},
        )
        st, _, _ = http(tech, "GET", base + "/api/llm/settings")
        run.check("non-admin cannot read LLM settings", st == 403, str(st))
        st, _, _ = http(tech, "GET", base + "/api/fleet")
        run.check("maintenance user reads fleet", st == 200, str(st))
        http(
            browser,
            "PUT",
            base + "/api/auth/users/tech1",
            {"active": False},
            {"X-PDM-CSRF": "1"},
        )
        st, _, _ = http(tech, "GET", base + "/api/fleet")
        run.check("deactivated account loses access at once", st == 401, str(st))
        st, _, _ = http(browser, "POST", base + "/api/auth/logout", None, {"X-PDM-CSRF": "1"})
        jar.clear()
        st, _, _ = http(browser, "GET", base + "/api/fleet")
        run.check("sign-out ends the session", st == 401, str(st))
    finally:
        srv.terminate()
        srv.wait(timeout=30)
        log.close()
    run.note(f"Result: {run.failed} failed checks")
    run.save()
    return 1 if run.failed else 0


if __name__ == "__main__":
    sys.exit(main())
