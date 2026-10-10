"""Static template checks, including injection attempts (T010 AC2)."""

import pytest

from app.datasource.query_service.sql_guard import TemplateSqlError, check_template_sql

TABLES = {"telemetrydata", "iot.raw_telemetry"}
OK = "SELECT deviceid, value_double FROM telemetrydata WHERE keyname = :k ORDER BY datetime LIMIT 100"


@pytest.mark.parametrize(
    "sql, params",
    [
        (OK, {"k"}),
        ("select * from telemetrydata where keyname <> 'a;b--c' and deviceid = :d limit 5", {"d"}),
        ("SELECT EXTRACT(EPOCH FROM datetime) AS t, value_double::float FROM telemetrydata LIMIT 10", set()),
        ("WITH w AS (SELECT * FROM telemetrydata WHERE keyname = :k) SELECT * FROM w LIMIT 10", {"k"}),
        ("SELECT ts, value FROM iot.raw_telemetry WHERE key_name = :k LIMIT 10", {"k"}),
        ("SELECT replace(keyname, '_', '-') FROM telemetrydata LIMIT 1", set()),
        ("SELECT 'it''s' AS s FROM telemetrydata LIMIT 1", set()),
        ("SELECT a.value_double FROM telemetrydata a, telemetrydata b WHERE a.id = b.id LIMIT 1", set()),
        ("SELECT * FROM telemetrydata t LEFT JOIN iot.raw_telemetry r ON r.ts = t.datetime LIMIT 1", set()),
        ("SELECT * FROM (SELECT * FROM telemetrydata) q LIMIT 1", set()),
    ],
)
def test_accepts_bounded_selects(sql, params):
    check_template_sql(sql, params, TABLES)


@pytest.mark.parametrize(
    "sql, reason",
    [
        ("DELETE FROM telemetrydata WHERE keyname = :k", "SELECT"),
        ("UPDATE telemetrydata SET value_double = 0 LIMIT 1", "SELECT"),
        ("INSERT INTO telemetrydata VALUES (1) LIMIT 1", "SELECT"),
        ("DROP TABLE telemetrydata", "SELECT"),
        ("SELECT * INTO copy_tbl FROM telemetrydata LIMIT 1", "into"),
        ("WITH d AS (DELETE FROM telemetrydata RETURNING *) SELECT * FROM d LIMIT 1", "delete"),
        ("SELECT 1 FROM telemetrydata LIMIT 1; DROP TABLE telemetrydata", "one statement"),
        ("SELECT 1 FROM telemetrydata LIMIT 1;", "one statement"),
        ("SELECT 1 FROM telemetrydata LIMIT 1 -- trailing", "comments"),
        ("SELECT 1 /* hidden */ FROM telemetrydata LIMIT 1", "comments"),
        ("SELECT 1 FROM telemetrydata LIMIT 1 # mysql comment", "comments"),
        ("SELECT pg_sleep(10) FROM telemetrydata LIMIT 1", "pg_sleep"),
        ("SELECT pg_read_file('/etc/passwd') FROM telemetrydata LIMIT 1", "pg_read_file"),
        ("SELECT * FROM dblink('host=x', 'select 1') AS t(a int) LIMIT 1", "dblink"),
        ("SELECT * FROM telemetrydata LIMIT 1 FOR UPDATE", "update"),
        ("SELECT * FROM telemetrydata", "LIMIT"),
        ("SELECT * FROM telemetrydata WHERE keyname = :k LIMIT 1", "undeclared"),
        ("SELECT * FROM telemetrydata LIMIT 1", "unused"),
        ("SELECT * FROM pg_shadow LIMIT 1", "table not allowed"),
        ("SELECT * FROM telemetrydata t JOIN users u ON true LIMIT 1", "table not allowed"),
        ("SELECT * FROM telemetrydata, pg_shadow LIMIT 1", "table not allowed"),
        ("SELECT * FROM telemetrydata a, (SELECT * FROM pg_authid) b LIMIT 1", "table not allowed"),
        ("SELECT * FROM generate_series(1, 10) LIMIT 1", "table functions"),
        (
            "SELECT * FROM telemetrydata WHERE deviceid IN (SELECT usename FROM pg_user) LIMIT 1",
            "table not allowed",
        ),
        ("SELECT $$x$$ FROM telemetrydata LIMIT 1", "dollar"),
        ("SELECT 'open FROM telemetrydata LIMIT 1", "unterminated"),
        ("SELECT 'a\\' FROM telemetrydata LIMIT 1", "backslash"),
        ("SELECT 1 FROM telemetrydata LIMIT 1\x00", "NUL"),
        ("SET statement_timeout = 0", "SELECT"),
        ("COPY telemetrydata TO '/tmp/x'", "SELECT"),
    ],
)
def test_rejects_unsafe_templates(sql, reason):
    params = {"k"} if "unused" in reason else set()
    with pytest.raises(TemplateSqlError, match=reason):
        check_template_sql(sql, params, TABLES)
