#!/usr/bin/env bash
set -Eeuo pipefail

ENV_FILE="${ENV_FILE:-/etc/tbanastream/tbanastream.env}"
backup_file="${1:-}"
confirmation="${2:-}"

if [[ -z "${backup_file}" || "${confirmation}" != "--yes" ]]; then
    echo "Usage: sudo scripts/restore_db.sh /path/to/backup.dump --yes"
    echo "WARNING: this replaces the current database contents."
    exit 1
fi
if [[ ! -r "${backup_file}" || ! -r "${ENV_FILE}" ]]; then
    echo "Backup or environment file is not readable."
    exit 1
fi

set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a
: "${DATABASE_URL:?DATABASE_URL is missing from ${ENV_FILE}}"

systemctl stop tbanastream-api
trap 'systemctl start tbanastream-api' EXIT
pg_restore --clean --if-exists --no-owner --dbname="${DATABASE_URL}" \
    "${backup_file}"

echo "Database restored from ${backup_file}."
