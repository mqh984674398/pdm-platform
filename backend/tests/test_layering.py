"""Enforce the layer import rule from ARCHITECTURE §3."""

import ast
from pathlib import Path

APP = Path(__file__).resolve().parent.parent / "app"

# Lower number = lower layer. A layer may import itself, lower layers, and core.
RANK = {
    "core": 0,
    "datasource": 1,
    "signals": 2,
    "equipment": 3,
    "monitoring": 4,
    "prediction": 5,
    "decision": 6,
    "llm": 7,
    "feedback": 7,
}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
    return {m.split(".")[1] for m in found if m.startswith("app.") and m.count(".") >= 1}


def test_layer_packages_exist():
    for pkg in RANK:
        assert (APP / pkg / "__init__.py").is_file(), pkg


def test_layer_import_direction():
    violations = []
    for pkg, rank in RANK.items():
        for f in (APP / pkg).rglob("*.py"):
            for target in _imports(f):
                if target not in RANK:
                    violations.append(f"{f.relative_to(APP)} imports app.{target} (not a layer)")
                elif target == pkg or target == "core":
                    continue
                elif target == "llm" or RANK[target] >= rank:
                    violations.append(f"{f.relative_to(APP)} imports app.{target}")
    assert not violations, violations


def test_checker_detects_violation(tmp_path):
    probe = tmp_path / "probe.py"
    probe.write_text("from app.decision import x\nimport app.llm.client\n", encoding="utf-8")
    assert _imports(probe) == {"decision", "llm"}
