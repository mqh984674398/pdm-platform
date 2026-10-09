# T010 security review notes

Reviewer: executing agent (self-review against L1-02, L1-05, L1-06, SEC-02, SEC-03). Date: 2026-10-09. An independent human review is still recommended before G4.

## Threats and controls

| Threat | Control | Test |
|---|---|---|
| Arbitrary SQL from users | Only stored, administrator-created templates run; users send a template id and parameter values | `test_api.py::test_sign_in_and_roles_are_required`, `test_run_returns_bound_rows_in_order` |
| Injection through parameter values | Values are bound (`sqlalchemy.text` bind parameters), never spliced; IDENTIFIER values must be a discovered device id or key name; types coerced; strings capped at 256 characters | `test_bad_parameters_are_rejected_before_execution`, `test_string_parameters_are_bound_not_spliced` |
| Write or DDL through a template | Guard accepts only one statement starting with SELECT/WITH; forbidden keywords (DML, DDL, INTO, SET, COPY, transaction control…); forbidden functions (pg_sleep, pg_read_file, dblink…); no row locking | `test_sql_guard.py::test_rejects_unsafe_templates` (30 cases) |
| Multi-statement and comment injection | `;`, `--`, `/* */`, `#`, backslashes, dollar quoting and NUL bytes are refused; string literals are parsed so `;` inside a literal is fine | same |
| Reading other tables | Every FROM-list item and JOIN target must be a table discovered in the source (or a CTE); table functions refused | `table not allowed` and `table functions` cases |
| Guard bypass | Defence in depth: the database session itself is read-only (`default_transaction_read_only=on` on PostgreSQL, `PRAGMA query_only` on SQLite), so a missed pattern still cannot write | T009 `test_writes_are_refused_by_the_database`, `test_postgres_session_is_read_only_with_timeout` |
| Resource exhaustion | Template must contain LIMIT; results fetched up to min(template, source) max_rows + 1 and flagged `truncated`; time range ≤ min(template, source) hours; statement timeout; concurrency limit (429) | `test_row_limit_truncates_and_says_so`, `limit_exceeded` case, `test_statement_timeout_returns_504_on_postgres`, `test_concurrency_limit_returns_busy` |
| Credential exposure | Configs carry `credential_ref` only; URLs resolved server-side from `PDM_SECRET_*`; error responses never include driver messages (they can echo SQL or hosts) | `test_no_endpoint_returns_credentials`, `test_database_errors_are_not_echoed`, `test_sources_file_resolves_secrets_server_side` |
| Unaudited template changes | Create, update and retire write an audit row in the same transaction: actor, role, version, changed fields, SQL hashes before and after. Changes create a new version; old versions are kept | `test_changes_are_versioned_and_audited` |
| Unauthorized template management | Admin role required for create/update/retire/history/audit and to see SQL text; schema inspection needs engineer | `test_sign_in_and_roles_are_required`, `test_sql_text_is_visible_to_administrators_only` |

## Residual risks

1. Authentication is the `dev` header provider (D-010). Anyone who can reach the API can claim any role. It must not be exposed on a shared network; real authentication is part of T028.
2. The guard is pattern-based, not a full SQL parser. It is deliberately strict (false rejections over false acceptances), and the read-only session is the backstop.
3. SQLite has no statement timeout; it is used only for tests and simulated demos.
4. Rejected template submissions are not audited (only accepted changes are). Revisit if attempted misuse needs tracking.
5. Query executions are not audited. They are reads; add an access log at deployment (T028) if required.
