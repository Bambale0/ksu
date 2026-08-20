#!/bin/sh
set -eu

# Database archives contain the entire durable product state. Keep newly created
# files private even when the backing Docker volume is inspected from the host.
umask 077

BACKUP_DIR="${DB_BACKUP_DIR:-/backups}"
INTERVAL_SECONDS="${DB_BACKUP_INTERVAL_SECONDS:-10800}"
RETENTION_COUNT="${DB_BACKUP_RETENTION_COUNT:-16}"
BACKUP_ON_START="${DB_BACKUP_ON_START:-true}"
FAILURE_RETRY_SECONDS=60
CURRENT_DUMP_TMP=""
CURRENT_CHECKSUM_TMP=""

log() {
    printf '%s %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*"
}

positive_int() {
    case "$1" in
        ''|*[!0-9]*|0) return 1 ;;
        *) return 0 ;;
    esac
}

cleanup_temp() {
    if [ -n "$CURRENT_DUMP_TMP" ]; then
        rm -f "$CURRENT_DUMP_TMP"
    fi
    if [ -n "$CURRENT_CHECKSUM_TMP" ]; then
        rm -f "$CURRENT_CHECKSUM_TMP"
    fi
}

trap 'cleanup_temp; exit 130' INT
trap 'cleanup_temp; exit 143' TERM
trap 'cleanup_temp' EXIT

if ! positive_int "$INTERVAL_SECONDS"; then
    log "invalid DB_BACKUP_INTERVAL_SECONDS=$INTERVAL_SECONDS"
    exit 2
fi
if ! positive_int "$RETENTION_COUNT"; then
    log "invalid DB_BACKUP_RETENTION_COUNT=$RETENTION_COUNT"
    exit 2
fi
case "$BACKUP_ON_START" in
    true|1|false|0) ;;
    *)
        log "invalid DB_BACKUP_ON_START=$BACKUP_ON_START (expected true/false/1/0)"
        exit 2
        ;;
esac
if [ -z "${DATABASE_URL:-}" ]; then
    log "DATABASE_URL is required"
    exit 2
fi

# SQLAlchemy's asyncpg URL is not understood by libpq tools. Keep the same
# authority/credentials/query string and only normalize the scheme.
DB_URL="$(printf '%s' "$DATABASE_URL" | sed 's#^postgresql+asyncpg://#postgresql://#')"
case "$DB_URL" in
    postgresql://*|postgres://*) ;;
    *)
        log "DATABASE_URL must use PostgreSQL"
        exit 2
        ;;
esac

mkdir -p "$BACKUP_DIR"
# A killed container can leave unpublished temporary files. They are never
# considered backups, so remove them on the next worker start.
rm -f "$BACKUP_DIR"/.ksu-*.tmp.*

prune_old_backups() {
    keep="$RETENTION_COUNT"
    index=0
    find "$BACKUP_DIR" -maxdepth 1 -type f -name 'ksu-*.dump' -print \
        | sort -r \
        | while IFS= read -r file; do
            index=$((index + 1))
            if [ "$index" -gt "$keep" ]; then
                rm -f "$file" "$file.sha256"
            fi
        done
}

run_backup() {
    timestamp="$(date -u '+%Y%m%dT%H%M%SZ')"
    worker_id="$(printf '%s' "${HOSTNAME:-worker}" | tr -cd 'A-Za-z0-9._-' | cut -c1-32)"
    [ -n "$worker_id" ] || worker_id="worker"

    final="$BACKUP_DIR/ksu-$timestamp-$worker_id.dump"
    CURRENT_DUMP_TMP="$(mktemp "$BACKUP_DIR/.ksu-$timestamp.dump.tmp.XXXXXX")"
    CURRENT_CHECKSUM_TMP="$(mktemp "$BACKUP_DIR/.ksu-$timestamp.sha256.tmp.XXXXXX")"

    if ! pg_dump \
        --format=custom \
        --no-owner \
        --no-privileges \
        --file="$CURRENT_DUMP_TMP" \
        "$DB_URL"; then
        cleanup_temp
        CURRENT_DUMP_TMP=""
        CURRENT_CHECKSUM_TMP=""
        log "backup failed: pg_dump returned non-zero"
        return 1
    fi

    if [ ! -s "$CURRENT_DUMP_TMP" ]; then
        cleanup_temp
        CURRENT_DUMP_TMP=""
        CURRENT_CHECKSUM_TMP=""
        log "backup failed: pg_dump produced an empty archive"
        return 1
    fi

    # A custom-format file is not published merely because pg_dump exited zero.
    # Require pg_restore to parse its table of contents first.
    if ! pg_restore --list "$CURRENT_DUMP_TMP" >/dev/null 2>&1; then
        cleanup_temp
        CURRENT_DUMP_TMP=""
        CURRENT_CHECKSUM_TMP=""
        log "backup failed: pg_restore could not read the archive"
        return 1
    fi

    hash="$(sha256sum "$CURRENT_DUMP_TMP" | awk '{print $1}')"
    printf '%s  %s\n' "$hash" "$(basename "$final")" > "$CURRENT_CHECKSUM_TMP"

    # The named volume is one filesystem, so each rename is atomic. latest.* is
    # switched only after the verified archive and checksum are both published.
    mv "$CURRENT_DUMP_TMP" "$final"
    CURRENT_DUMP_TMP=""
    mv "$CURRENT_CHECKSUM_TMP" "$final.sha256"
    CURRENT_CHECKSUM_TMP=""
    ln -sfn "$(basename "$final")" "$BACKUP_DIR/latest.dump"
    ln -sfn "$(basename "$final.sha256")" "$BACKUP_DIR/latest.dump.sha256"

    prune_old_backups

    size="$(wc -c < "$final" | tr -d ' ')"
    log "backup completed file=$(basename "$final") bytes=$size sha256=$hash"
    return 0
}

run_until_success() {
    while ! run_backup; do
        log "backup retry scheduled in ${FAILURE_RETRY_SECONDS}s"
        sleep "$FAILURE_RETRY_SECONDS"
    done
}

if [ "$BACKUP_ON_START" = "true" ] || [ "$BACKUP_ON_START" = "1" ]; then
    run_until_success
fi

while :; do
    sleep "$INTERVAL_SECONDS"
    run_until_success
done
