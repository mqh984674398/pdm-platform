"""Static checks on administrator-written template SQL (L1-05).

Defence in depth: the database session is read-only as well (L1-02), so these checks are about
rejecting anything that is not one bounded SELECT before it ever reaches the database.
"""

from __future__ import annotations

import re

FORBIDDEN_KEYWORDS = {
    "insert", "update", "delete", "merge", "upsert", "drop", "alter", "create", "truncate",
    "grant", "revoke", "copy", "call", "exec", "execute", "do", "set", "reset", "lock", "vacuum",
    "analyze", "cluster", "reindex", "refresh", "listen", "notify", "prepare", "deallocate", "into",
    "attach", "detach", "pragma", "begin", "commit", "rollback", "savepoint", "load", "import",
}  # fmt: skip
FORBIDDEN_FUNCTIONS = {
    "pg_sleep", "pg_sleep_for", "pg_sleep_until", "pg_read_file", "pg_read_binary_file", "pg_ls_dir",
    "pg_stat_file", "lo_import", "lo_export", "lo_get", "dblink", "dblink_exec", "pg_terminate_backend",
    "pg_cancel_backend", "set_config", "pg_reload_conf", "query_to_xml", "load_extension",
    "sleep", "benchmark", "load_file", "xp_cmdshell", "openrowset", "opendatasource",
}  # fmt: skip
PLACEHOLDER = re.compile(r"(?<![:\w]):([a-z_][a-z0-9_]*)\b")


class TemplateSqlError(ValueError):
    pass


def _strip_literals(sql: str) -> str:
    """Replace string literals with empty quotes; reject unterminated ones and dollar quoting."""
    if "$$" in sql or re.search(r"\$\w*\$", sql):
        raise TemplateSqlError("dollar-quoted strings are not allowed")
    out, i = [], 0
    while i < len(sql):
        ch = sql[i]
        if ch == "'":
            j = i + 1
            while True:
                k = sql.find("'", j)
                if k < 0:
                    raise TemplateSqlError("unterminated string literal")
                if k + 1 < len(sql) and sql[k + 1] == "'":
                    j = k + 2
                    continue
                break
            out.append("''")
            i = k + 1
        else:
            out.append(ch)
            i += 1
    return "".join(out)


FROM_FUNCTIONS = {"extract", "substring", "trim", "overlay", "position"}


def _inside_from_function(body: str, pos: int) -> bool:
    """True when ``pos`` sits directly inside a call whose syntax uses FROM, like EXTRACT(...)."""
    depth = 0
    for i in range(pos - 1, -1, -1):
        if body[i] == ")":
            depth += 1
        elif body[i] == "(":
            if depth == 0:
                name = re.search(r"([A-Za-z_]\w*)\s*$", body[:i])
                return bool(name and name.group(1).lower() in FROM_FUNCTIONS)
            depth -= 1
    return False


def check_template_sql(sql: str, declared_params: set[str], allowed_tables: set[str]) -> None:
    """Raise TemplateSqlError unless ``sql`` is a single bounded SELECT over allowed tables.

    ``allowed_tables`` holds lower-case ``table`` and ``schema.table`` names from discovery.
    """
    if "\x00" in sql:
        raise TemplateSqlError("NUL byte")
    if "\\" in sql:  # engines differ on backslash escapes inside literals; refuse them outright
        raise TemplateSqlError("backslash escapes are not allowed")
    body = _strip_literals(sql)
    if "--" in body or "/*" in body or "*/" in body or "#" in body:
        raise TemplateSqlError("comments are not allowed")
    if ";" in body:
        raise TemplateSqlError("only one statement is allowed; remove ';'")
    words = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", body)
    if not words or words[0].lower() not in {"select", "with"}:
        raise TemplateSqlError("template must start with SELECT or WITH")
    lowered = [w.lower() for w in words]
    bad = sorted(set(lowered) & FORBIDDEN_KEYWORDS)
    if bad:
        raise TemplateSqlError(f"keyword not allowed: {', '.join(bad)}")
    calls = {m.lower() for m in re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(", body)}
    bad = sorted(calls & FORBIDDEN_FUNCTIONS)
    if bad:
        raise TemplateSqlError(f"function not allowed: {', '.join(bad)}")
    if re.search(r"\bfor\s+(update|share|no\s+key\s+update|key\s+share)\b", body, re.I):
        raise TemplateSqlError("row locking is not allowed")
    if "limit" not in lowered:
        raise TemplateSqlError("template must include a LIMIT clause")
    used = set(PLACEHOLDER.findall(body))
    if used != declared_params:
        missing, extra = declared_params - used, used - declared_params
        raise TemplateSqlError(
            "placeholders must match parameters"
            + (f"; unused: {', '.join(sorted(missing))}" if missing else "")
            + (f"; undeclared: {', '.join(sorted(extra))}" if extra else "")
        )
    ctes = {m.lower() for m in re.findall(r"(\w+)\s+as\s*\(", body, re.I)}
    for name in _table_refs(body):
        if name not in allowed_tables and name not in ctes:
            raise TemplateSqlError(f"table not allowed: {name}")


CLAUSE_END = re.compile(
    r"\b(where|group|order|limit|having|union|intersect|except|window|offset|fetch|on|using|"
    r"join|inner|left|right|full|cross|natural|lateral)\b",
    re.I,
)
NAME = r'(?:"[^"]+"|[A-Za-z_]\w*)(?:\s*\.\s*(?:"[^"]+"|[A-Za-z_]\w*))?'


def _table_refs(body: str) -> list[str]:
    """Table names after FROM (every comma-separated item) and after JOIN, lower-cased."""
    names: list[str] = []
    for m in re.finditer(r"\b(from|join)\b", body, re.I):
        if _inside_from_function(body, m.start()):
            continue  # EXTRACT(x FROM col), SUBSTRING(s FROM n), TRIM(... FROM s)
        rest = body[m.end() :]
        # cut the FROM list at the first clause keyword or closing parenthesis at depth 0
        depth, end = 0, len(rest)
        for i, ch in enumerate(rest):
            if ch == "(":
                depth += 1
            elif ch == ")":
                if depth == 0:
                    end = i
                    break
                depth -= 1
            elif depth == 0 and CLAUSE_END.match(rest, i) and (i == 0 or not rest[i - 1].isalnum()):
                end = i
                break
        items, depth, cur = [], 0, ""
        for ch in rest[:end] if m.group(1).lower() == "from" else rest[:end].split(",")[0]:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            if ch == "," and depth == 0:
                items.append(cur)
                cur = ""
            else:
                cur += ch
        items.append(cur)
        for item in items:
            item = item.strip()
            if not item or item.startswith("("):
                continue  # subquery: its own FROM is checked separately
            tm = re.match(NAME, item)
            if not tm:
                raise TemplateSqlError(f"cannot read table reference: {item[:40]}")
            after = item[tm.end() :].lstrip()
            if after.startswith("("):
                raise TemplateSqlError("table functions are not allowed")
            names.append(re.sub(r"\s+", "", tm.group(0)).replace('"', "").lower())
    return names
