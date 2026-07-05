#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

ENV_FILE="${ENV_FILE:-/etc/tbanastream/tbanastream.env}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/tbanastream}"
KEEP_DAYS="${KEEP_DAYS:-14}"

if [[ ! -r "${ENV_FILE}" ]]; then
    echo "Cannot read ${ENV_FILE}."
    exit 1
fi

set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a
: "${DATABASE_URL:?DATABASE_URL is missing from ${ENV_FILE}}"

mkdir -p "${BACKUP_DIR}"
backup_file="${BACKUP_DIR}/tbanastream_$(date -u +%Y%m%dT%H%M%SZ).dump"
pg_dump --format=custom --no-owner --file="${backup_file}" \
    --dbname="${DATABASE_URL}"
find "${BACKUP_DIR}" -type f -name 'tbanastream_*.dump' \
    -mtime "+${KEEP_DAYS}" -delete

echo "Backup created: ${backup_file}"
