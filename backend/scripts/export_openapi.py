"""Write the OpenAPI contract document to contracts/schemas/openapi.json."""

import json
import sys
from pathlib import Path

from app.api.contracts import build_openapi
from app.main import create_app

OUT = Path(__file__).resolve().parents[2] / "contracts" / "schemas" / "openapi.json"

if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(build_openapi(create_app()), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"wrote {out}")
