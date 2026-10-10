"""Update a task's status in its task file and TASKS.md, optionally assigning it as current.

Usage: python tools/set_task_status.py T003 DONE
       python tools/set_task_status.py T004 IN_PROGRESS --assign
"""

import argparse
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATUSES = ["TODO", "IN_PROGRESS", "BLOCKED", "FAILED", "DONE"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("task", help="e.g. T004")
    ap.add_argument("status", choices=STATUSES)
    ap.add_argument("--assign", action="store_true", help="also make this the current task")
    a = ap.parse_args()
    num = int(a.task.lstrip("T"))
    tid = f"T{num:03d}"

    tf = ROOT / "contracts" / "tasks" / f"TASK-{num:03d}.md"
    text = tf.read_text(encoding="utf-8")
    title = re.search(r"^# TASK-\d+ — (.+)$", text, re.M).group(1)
    tf.write_text(re.sub(r"\*\*Status:\*\* \w+", f"**Status:** {a.status}", text, count=1), encoding="utf-8")

    reg = ROOT / "TASKS.md"
    rtext = reg.read_text(encoding="utf-8")
    rtext = re.sub(rf"^(\| \[{tid}\].*\| )\w+( \|)$", rf"\g<1>{a.status}\2", rtext, count=1, flags=re.M)
    reg.write_text(rtext, encoding="utf-8")

    if a.assign:
        cur = ROOT / "contracts" / "CURRENT_TASK.md"
        prev = re.search(r"\*\*Assigned task:\*\* (T\d{3})", cur.read_text(encoding="utf-8")).group(1)
        prev_status = re.search(r"\*\*Status:\*\* (\w+)", (ROOT / "contracts" / "tasks" / f"TASK-{prev[1:]}.md").read_text(encoding="utf-8")).group(1)
        cur.write_text(
            f"""# CURRENT_TASK

- **Assigned task:** {tid} — {title}
- **Task file:** `contracts/tasks/TASK-{num:03d}.md`
- **Status:** {a.status}
- **Assigned by:** Principal Agent
- **Previous task:** {prev} {prev_status} ({date.today().isoformat()})

Update this file only when the Principal Agent assigns a new task.
""",
            encoding="utf-8",
        )
    print(f"{tid} -> {a.status}{' (assigned)' if a.assign else ''}")


if __name__ == "__main__":
    main()
