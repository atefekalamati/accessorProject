# Backup and restore runbook — PostgreSQL (OPS-03)

Written for: whoever operates the database (today the developer; later the production operator once D13 is decided).
All commands run from `BACKEND/`, next to `docker-compose.yml`. Production hosting is deferred (D13, ADR-058), so these steps target the Docker Compose stack. The same `pg_dump` and `pg_restore` flags apply to a managed PostgreSQL.

## Rules

- Never restore over the live database. Always restore into a new, empty database, check it, then switch.
- Never run `docker compose down -v` or delete the `postgres_data` volume. That removes every backup's source.
- Dumps contain personal data (mobiles, addresses, orders). Keep them in `backups/`, which is gitignored and created with mode 700 (files 600), and copy them off the host to encrypted storage. On Windows hosts the modes are advisory, so restrict the folder with NTFS permissions.
- `audit_logs` is append-only (SEC-04). The restore loads it with `COPY` before its triggers are created, so a restore into an empty database works. Do not use `--clean`: it would try to change existing rows and objects.

## Backup (daily)

```bash
scripts/backup.sh                       # postgres service, its POSTGRES_DB, into backups/
scripts/backup.sh --retention-days 30   # keep more
```

The script:

1. Runs `pg_dump --format=custom --no-owner` inside the `postgres` container.
2. Writes `backups/project_ak_<db>_<UTC>.dump` with mode 600.
3. Checks the dump with `pg_restore --list` and fails if it has no table data.
4. Deletes only its own dumps older than the retention (14 days by default).
5. Refuses a database whose name ends in `_test` unless `--allow-test` is given.

Schedule it once a day, for example with cron on the host:

```cron
15 2 * * * cd /srv/project-ak/BACKEND && scripts/backup.sh >> /var/log/project-ak-backup.log 2>&1
```

After each run, copy the new dump off the host. Off-host storage is part of D13.

## Restore

1. Pick the dump and check that it can be read:
   ```bash
   docker compose exec -T postgres pg_restore --list < backups/project_ak_<db>_<UTC>.dump | head
   ```
2. Create an empty target database. The live one stays untouched:
   ```bash
   docker compose exec -T postgres sh -c 'createdb -U "$POSTGRES_USER" -T template0 project_ak_restore'
   ```
3. Restore:
   ```bash
   docker compose exec -T postgres sh -c 'pg_restore --no-owner --exit-on-error -U "$POSTGRES_USER" -d project_ak_restore' \
     < backups/project_ak_<db>_<UTC>.dump
   ```
4. Check the restored database:
   ```bash
   docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d project_ak_restore -c "SELECT version_num FROM alembic_version"'
   docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d project_ak_restore -c "SELECT count(*) FROM orders"'
   ```
   The revision must equal the code's `alembic heads`. Compare row counts of `orders`, `payments` and `users` with the live database if it is still readable.
5. Switch over. Stop the API and every other client of the database first, such as cron jobs or DBeaver:
   ```bash
   docker compose stop api
   docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d postgres -c "ALTER DATABASE \"$POSTGRES_DB\" RENAME TO project_ak_broken"'
   docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d postgres -c "ALTER DATABASE project_ak_restore RENAME TO \"$POSTGRES_DB\""'
   docker compose up -d api
   ```
   Renaming keeps `.env` unchanged. If you change `POSTGRES_DB` in `.env` instead, compose recreates the `postgres` container. The `postgres_data` volume is kept, so this is safe. Run `alembic upgrade head` only if the code is newer than the dump.
6. Keep the old database until the restored one has served traffic for at least a day.

## Rehearsal

`scripts/restore_rehearsal.sh` runs the whole cycle on the disposable `postgres-test` service, never on `postgres`:

1. Migrate and seed a source database.
2. Back it up with `backup.sh`.
3. Restore it into an empty database.
4. Compare every table's row count, the alembic revision and the `audit_logs` triggers.
5. Drop both databases.

Run it after any migration that changes many tables, and before a release.
