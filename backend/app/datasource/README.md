# L1 data sources

All access to telemetry goes through `TimeSeriesAdapter` (`adapter.py`):

| Method | Purpose |
|---|---|
| `discover()` | Devices, their key names, earliest and latest timestamp (`SourceMetadata`) |
| `inspect_schema()` | Tables and columns (`SourceSchema`) |
| `query_range(device, key, window, limit)` | Rows with `start <= ts < end`, ascending, at most `limit` |
| `query_incremental(device, key, since, limit)` | Rows with `ts > since`, ascending, at most `limit` |

Implementations: `SimulatedAdapter` (simulator files) and `SqlAdapter` (SQL databases). Both pass `tests/datasource/test_adapter_contract.py`.

## Configuring a SQL source

Nothing is assumed from the example query `iotsharp.telemetrydata` (L1-08). Each source has a `SqlTableLayout`:

| Field | Meaning |
|---|---|
| `schema_name`, `table` | Where telemetry rows live |
| `device_column`, `key_column`, `time_column` | Device id, key name, and timestamp columns |
| `value_columns` | Value columns in order; the first non-null is used (e.g. `value_double`, `value_long`) |
| `naive_time_zone` | Zone of a timestamp column without time zone; results are always returned in UTC |
| `verified` | Stays `false` until the layout has been checked against the real database |

The adapter reflects the live table on start-up and refuses to run (`LayoutError`) if the table or a column is missing.

An IoTSharp-style layout, to be confirmed against the real database before use:

```python
SqlTableLayout(
    table="telemetrydata",
    device_column="deviceid",
    key_column="keyname",
    time_column="datetime",
    value_columns=["value_double", "value_long"],
)
```

## Safety

- Read-only twice over: read-only credentials (operations) and server-side session settings. PostgreSQL sessions start with `default_transaction_read_only=on`; SQLite runs with `PRAGMA query_only`. Other engines raise `UnsupportedEngineError` until verified.
- Bounded: `statement_timeout_s` and `max_rows` from `DataSourceConfig`, a maximum time range per query (`max_range_hours`, default 168), and a concurrency limit (`max_concurrency`, default 4).
- Queries are built with SQLAlchemy Core from reflected columns and bound parameters. Callers never pass SQL.
- Watermark reads use `ts > since`. If several rows share the boundary timestamp and a batch ends between them, the rest are skipped; callers that need every duplicate re-read the boundary timestamp.
