#!/usr/bin/env bash
# Backup/restore rehearsal on the disposable postgres-test service only (OPS-03).
# Run from BACKEND/ with the venv:  scripts/restore_rehearsal.sh
#
# 1. creates project_ak_rehearsal_src_test, migrates it to head and seeds it;
# 2. backs it up with scripts/backup.sh into a temporary directory;
# 3. restores the dump into an empty project_ak_rehearsal_dst_test (--no-owner,
#    --exit-on-error, no --clean);
# 4. compares the alembic revision and every table's row count, and checks that the
#    audit_logs triggers came back;
# 5. drops both databases. It never touches the postgres service or its volume.
set -euo pipefail

src="project_ak_rehearsal_src_test"
dst="project_ak_rehearsal_dst_test"
compose=(docker compose --profile test)
port="${TEST_DB_HOST_PORT:-55432}"
python="${PYTHON:-.venv/Scripts/python}"
work="$(mktemp -d)"

psql() {
  "${compose[@]}" exec -T postgres-test psql -v ON_ERROR_STOP=1 -U postgres -At "$@"
}

cleanup() {
  psql -d postgres -c "DROP DATABASE IF EXISTS $src" >/dev/null || true
  psql -d postgres -c "DROP DATABASE IF EXISTS $dst" >/dev/null || true
  rm -rf "$work"
}
trap cleanup EXIT

"${compose[@]}" up -d --wait postgres-test >/dev/null
# The host port must be the disposable service's, or the migration would hit another database.
published="$("${compose[@]}" port postgres-test 5432)"
if [ "${published##*:}" != "$port" ]; then
  echo "postgres-test publishes $published, not port $port; set TEST_DB_HOST_PORT" >&2
  exit 2
fi
for db in "$src" "$dst"; do
  psql -d postgres -c "DROP DATABASE IF EXISTS $db" >/dev/null
  psql -d postgres -c "CREATE DATABASE $db TEMPLATE template0" >/dev/null
done

export DATABASE_URL="postgresql+asyncpg://postgres:test@127.0.0.1:${port}/${src}"
"$python" -m alembic upgrade head >/dev/null
"$python" -m app.db.seed
psql -d "$src" -c "INSERT INTO audit_logs (id, action, entity_type, metadata) VALUES (gen_random_uuid(), 'rehearsal.backup', 'rehearsal', '{}')" >/dev/null

scripts/backup.sh --service postgres-test --database "$src" --out-dir "$work" --allow-test
dump="$(ls "$work"/project_ak_"$src"_*.dump)"

"${compose[@]}" exec -T postgres-test \
  pg_restore --no-owner --exit-on-error -U postgres -d "$dst" < "$dump"

counts() {
  psql -d "$1" -c "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE' ORDER BY 1" |
    while read -r table; do
      # </dev/null: docker exec would otherwise swallow the rest of the table list.
      printf '%s %s\n' "$table" "$(psql -d "$1" -c "SELECT count(*) FROM \"$table\"" </dev/null)"
    done
}

counts "$src" > "$work/src.txt"
counts "$dst" > "$work/dst.txt"
tables="$(wc -l < "$work/src.txt")"
if [ "$tables" -lt 10 ]; then
  echo "REHEARSAL FAILED: only $tables tables compared" >&2
  exit 1
fi
if ! diff -u "$work/src.txt" "$work/dst.txt"; then
  echo "REHEARSAL FAILED: row counts differ" >&2
  exit 1
fi
revision="$(psql -d "$dst" -c "SELECT version_num FROM alembic_version")"
if [ "$revision" != "$(psql -d "$src" -c "SELECT version_num FROM alembic_version")" ]; then
  echo "REHEARSAL FAILED: alembic revision differs after restore" >&2
  exit 1
fi
triggers="$(psql -d "$dst" -c "SELECT count(*) FROM pg_trigger WHERE tgrelid = 'audit_logs'::regclass AND NOT tgisinternal AND tgenabled = 'A'")"
if [ "$triggers" != "3" ]; then
  echo "REHEARSAL FAILED: audit_logs has $triggers always-enabled triggers, want 3" >&2
  exit 1
fi
echo "REHEARSAL OK: $tables tables, row counts equal, alembic $revision, audit triggers restored"
