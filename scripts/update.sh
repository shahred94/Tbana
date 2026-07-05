#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/tbanastream}"
BRANCH="${BRANCH:-main}"

if [[ "${EUID}" -ne 0 ]]; then
    echo "Run with sudo."
    exit 1
fi
if [[ ! -d "${APP_DIR}/.git" ]]; then
    echo "${APP_DIR} is not a Git checkout."
    exit 1
fi

"${APP_DIR}/scripts/backup_db.sh"
git -C "${APP_DIR}" fetch --prune origin
git -C "${APP_DIR}" checkout "${BRANCH}"
git -C "${APP_DIR}" pull --ff-only origin "${BRANCH}"
"${APP_DIR}/.venv/bin/pip" install -r \
    "${APP_DIR}/requirements-production.txt"
systemctl restart tbanastream-api
systemctl --no-pager --full status tbanastream-api

echo "Updated ${APP_DIR} from origin/${BRANCH}."
