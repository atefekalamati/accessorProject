#!/usr/bin/env bash
# PostgreSQL backup with retention (OPS-03). Run from BACKEND/, next to docker-compose.yml.
#
#   scripts/backup.sh [--service postgres] [--database NAME] [--out-dir backups]
#                     [--retention-days 14] [--allow-test]
#
# Writes <out-dir>/project_ak_<database>_<UTC timestamp>.dump (pg_dump custom format,
# mode 600), checks it with pg_restore --list, then deletes only dumps of the same naming
# pattern older than the retention. A database whose name ends in _test is refused unless
# --allow-test is given (the restore rehearsal uses the disposable postgres-test service).
set -euo pipefail

service="postgres"
database=""
out_dir="backups"
retention_days=14
allow_test=0

while [ $# -gt 0 ]; do
  case "$1" in
    --service) service="$2"; shift 2 ;;
    --database) database="$2"; shift 2 ;;
    --out-dir) out_dir="$2"; shift 2 ;;
    --retention-days) retention_days="$2"; shift 2 ;;
    --allow-test) allow_test=1; shift ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

case "$retention_days" in
  ''|*[!0-9]*) echo "--retention-days must be a whole number" >&2; exit 2 ;;
esac
case "$out_dir" in
  ''|-*) echo "--out-dir must be a path that does not start with '-'" >&2; exit 2 ;;
esac

compose=(docker compose)
if [ "$service" = "postgres-test" ]; then
  compose+=(--profile test)
fi

if [ -z "$database" ]; then
  database="$("${compose[@]}" exec -T "$service" sh -c 'printf %s "$POSTGRES_DB"')"
fi
case "$database" in
  *[!a-z0-9_]*|'') echo "invalid database name: '$database'" >&2; exit 2 ;;
esac
case "$database" in
  *_test)
    if [ "$allow_test" -ne 1 ]; then
      echo "refusing to back up test database '$database' without --allow-test" >&2
      exit 3
    fi
    ;;
esac

umask 077
mkdir -p "$out_dir"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
target="$out_dir/project_ak_${database}_${stamp}.dump"
partial="$target.partial"
trap 'rm -f "$partial"' EXIT

"${compose[@]}" exec -T -e DB="$database" "$service" \
  sh -c 'pg_dump --format=custom --no-owner -U "$POSTGRES_USER" -d "$DB"' > "$partial"

# A dump pg_restore cannot list (or one without table data) is not a backup.
if ! listing="$("${compose[@]}" exec -T "$service" pg_restore --list < "$partial")"; then
  echo "backup check failed: pg_restore cannot read $partial" >&2
  exit 4
fi
entries="$(printf '%s\n' "$listing" | grep -c ' TABLE DATA ' || true)"
if [ "${entries:-0}" -lt 1 ]; then
  echo "backup check failed: no table data in $partial" >&2
  exit 4
fi

chmod 600 "$partial"
mv "$partial" "$target"
trap - EXIT
echo "wrote $target ($entries tables with data)"

# Retention: only this script's own files for this database (the timestamp is anchored, so
# project_ak's retention never matches project_ak_staging's dumps), only in this directory.
find -- "$out_dir" -maxdepth 1 -type f -name "project_ak_${database}_????????T??????Z.dump" \
  -mtime +"$retention_days" -print -delete
