"""Build the code-only upgrade package for an existing offline installation (no Python runtime inside).

    backend/.venv/bin/python deploy/build_upgrade.py [--out DIR]

Layout of pdm-<version>-upgrade-win64.zip (top folder pdm-upgrade/):
    upgrade.cmd + setup/upgrade.ps1  double-click upgrade of an installed system (database, .env untouched)
    install.cmd, uninstall.cmd, verify.cmd, setup/*.ps1, DEPLOY_GUIDE.md, RELEASE_NOTES.md
    pdm/                             backend, migrations, built browser client, deploy scripts, SIMULATED data
The browser client must be built first (cd frontend && npm run build).
"""

from __future__ import annotations

import argparse
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "deploy"))
sys.path.insert(0, str(ROOT / "backend"))
from build_package import INCLUDE, SKIP  # noqa: E402

from app import __version__  # noqa: E402

OFF = ROOT / "deploy" / "offline"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "dist")
    args = ap.parse_args()
    if not (ROOT / "frontend" / "dist" / "index.html").exists():
        sys.exit("frontend/dist is missing: run `npm run build` in frontend/ first")
    stage = args.out / "upgrade-stage"
    shutil.rmtree(stage, ignore_errors=True)
    for item in INCLUDE:
        p = ROOT / item
        for f in [p] if p.is_file() else sorted(x for x in p.rglob("*") if x.is_file()):
            rel = f.relative_to(ROOT).as_posix()
            if not SKIP.search(rel):
                dest = stage / "pdm" / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dest)
    (stage / "setup").mkdir()
    for n in ("upgrade.ps1", "offline_install.ps1", "offline_uninstall.ps1"):
        shutil.copy2(OFF / n, stage / "setup" / n)
    for n in ("upgrade.cmd", "install.cmd", "uninstall.cmd", "verify.cmd", "DEPLOY_GUIDE.md", "RELEASE_NOTES.md"):
        shutil.copy2(OFF / n, stage / n)
    out = args.out / f"pdm-{__version__}-upgrade-win64.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in sorted(x for x in stage.rglob("*") if x.is_file()):
            z.write(f, f"pdm-upgrade/{f.relative_to(stage).as_posix()}")
    shutil.rmtree(stage)
    print(out, out.stat().st_size)


if __name__ == "__main__":
    main()
