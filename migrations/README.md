# Migrations

Forward-only SQL migrations, applied in lexical filename order by
`home_photo_repo.db.apply_migrations`.

## Naming convention

`NNN_short_description.sql` — leading zero-padded number, snake_case
description.

## SQL constraint

The runner uses a naive statement splitter (`_split_sql_statements` in
`src/home_photo_repo/db.py`). It splits on `;` at the top level and does
**not** handle:

- Semicolons inside string literals (e.g., `DEFAULT 'a;b'`)
- Multi-statement triggers (`CREATE TRIGGER ... BEGIN ... END;`)
- Embedded comments containing `;`

If a future migration needs any of these, upgrade the splitter to a real
SQL parser. For all current and foreseeable migrations (simple
`CREATE TABLE` / `CREATE INDEX` / `ALTER TABLE ADD COLUMN`), the
splitter is fine.
