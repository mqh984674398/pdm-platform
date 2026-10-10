"""Validate contract files: task structure, registry consistency, dependencies, requirement IDs.

Usage: python tools/check_contracts.py   (exit 0 = OK)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQUIRED_DOCS = ["AGENTS.md", "REQUIREMENTS.md", "ARCHITECTURE.md", "TASKS.md", "ACCEPTANCE.md",
                 "DECISIONS.md", "contracts/CURRENT_TASK.md"]
REQUIRED_SECTIONS = ["Goal", "Dependencies", "Allowed Scope", "Related Requirements", "Acceptance Criteria",
                     "Required Verification", "Deliverables", "Failure Recovery"]
STATUSES = {"TODO", "IN_PROGRESS", "BLOCKED", "FAILED", "DONE"}
TASK_COUNT = 28


def main() -> int:
    errors: list[str] = []

    for doc in REQUIRED_DOCS:
        if not (ROOT / doc).is_file():
            errors.append(f"missing {doc}")

    req_text = (ROOT / "REQUIREMENTS.md").read_text(encoding="utf-8")
    req_ids = set(re.findall(r"^\| ([A-Z0-9]+-\d+) \|", req_text, re.M))

    task_files = sorted((ROOT / "contracts" / "tasks").glob("TASK-*.md"))
    if len(task_files) != TASK_COUNT:
        errors.append(f"expected {TASK_COUNT} task files, found {len(task_files)}")

    deps: dict[str, list[str]] = {}
    file_status: dict[str, str] = {}
    for f in task_files:
        text = f.read_text(encoding="utf-8")
        tid = "T" + f.stem.split("-")[1]
        for s in REQUIRED_SECTIONS:
            if not re.search(rf"^## {re.escape(s)}\s*$", text, re.M):
                errors.append(f"{f.name}: missing section '{s}'")
        m = re.search(r"\*\*Status:\*\* (\w+)", text)
        if not m or m.group(1) not in STATUSES:
            errors.append(f"{f.name}: invalid or missing status")
        else:
            file_status[tid] = m.group(1)
        dep_block = re.search(r"^## Dependencies\s*\n\n(.+?)\n", text, re.M)
        deps[tid] = re.findall(r"T\d{3}", dep_block.group(1)) if dep_block else []
        rel = re.search(r"^## Related Requirements\s*\n\n(.+?)\n", text, re.M)
        for rid in (rel.group(1).split(", ") if rel else []):
            if rid.strip() not in req_ids:
                errors.append(f"{f.name}: unknown requirement {rid.strip()}")

    for tid, ds in deps.items():
        for d in ds:
            if d not in deps:
                errors.append(f"{tid}: dependency {d} does not exist")
            elif int(d[1:]) >= int(tid[1:]):
                errors.append(f"{tid}: dependency {d} is not an earlier task")

    # Acyclic is implied by "dependencies point to earlier tasks"; check explicitly anyway.
    state: dict[str, int] = {}

    def visit(n: str) -> bool:
        if state.get(n) == 1:
            return False
        if state.get(n) == 2:
            return True
        state[n] = 1
        ok = all(visit(d) for d in deps.get(n, []) if d in deps)
        state[n] = 2
        return ok

    if not all(visit(n) for n in deps):
        errors.append("dependency graph has a cycle")

    registry = (ROOT / "TASKS.md").read_text(encoding="utf-8")
    reg_rows = dict(re.findall(r"^\| \[(T\d{3})\].*\| (\w+) \|$", registry, re.M))
    if set(reg_rows) != set(file_status):
        errors.append("TASKS.md rows do not match task files")
    for tid, st in file_status.items():
        if reg_rows.get(tid) != st:
            errors.append(f"{tid}: status mismatch (file {st}, TASKS.md {reg_rows.get(tid)})")

    current = (ROOT / "contracts" / "CURRENT_TASK.md").read_text(encoding="utf-8")
    m = re.search(r"\*\*Assigned task:\*\* (T\d{3})", current)
    if not m or m.group(1) not in file_status:
        errors.append("CURRENT_TASK.md does not name an existing task")

    for e in errors:
        print(f"ERROR: {e}")
    print(f"checked {len(task_files)} tasks, {len(req_ids)} requirement IDs: {'OK' if not errors else f'{len(errors)} error(s)'}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
