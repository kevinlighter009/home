#!/usr/bin/env bash
# Nightly Postgres backup for Immich.
#
# Runs `pg_dumpall` inside the immich_postgres container, gzips the output,
# and stores under $BACKUP_DIR (default: $HOME/home_photo_repo_dev/immich/backups).
# Prunes dumps older than $RETENTION_DAYS (default: 14).
#
# Env:
#   BACKUP_DIR        target directory for .sql.gz files
#   RETENTION_DAYS    keep dumps newer than this many days (default 14)
#   BACKUP_DRY_RUN    if set to 1, print commands instead of running them
#   POSTGRES_USER     defaults to 'postgres'
#   CONTAINER_NAME    defaults to 'immich_postgres'

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-$HOME/home_photo_repo_dev/immich/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
POSTGRES_USER="${POSTGRES_USER:-postgres}"
CONTAINER_NAME="${CONTAINER_NAME:-immich_postgres}"
DRY_RUN="${BACKUP_DRY_RUN:-0}"

TIMESTAMP="$(date +%Y-%m-%d_%H%M%S)"
OUT_FILE="${BACKUP_DIR}/immich_${TIMESTAMP}.sql.gz"

# Run an array-form command, or print it in dry-run mode.
run_cmd() {
    if [[ "$DRY_RUN" == "1" ]]; then
        echo "DRY-RUN: $*"
    else
        "$@"
    fi
}

# Run a shell pipeline (used only where the pipe is structural — pg_dumpall | gzip).
# Inputs are operator-controlled env vars only; no user-supplied strings.
run_pipeline() {
    local cmd="$1"
    if [[ "$DRY_RUN" == "1" ]]; then
        echo "DRY-RUN: $cmd"
    else
        bash -c "$cmd"
    fi
}

# Ensure target dir exists.
run_cmd mkdir -p "$BACKUP_DIR"

# Run pg_dumpall and gzip in one stream. Pipe is the reason we need bash -c here;
# the arguments are env-var-only so this is safe.
run_pipeline "docker exec -t '$CONTAINER_NAME' pg_dumpall -U '$POSTGRES_USER' | gzip > '$OUT_FILE'"

# Rotate: delete .sql.gz files older than RETENTION_DAYS.
echo "retention: keeping dumps newer than ${RETENTION_DAYS} days in $BACKUP_DIR"
run_cmd find "$BACKUP_DIR" -maxdepth 1 -type f -name "immich_*.sql.gz" -mtime "+${RETENTION_DAYS}" -delete

echo "backup complete: $OUT_FILE"
