#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/tbanastream}"
APP_USER="${APP_USER:-tbanastream}"
DOMAIN="${DOMAIN:-api.tbanastream.com}"
ENV_DIR="${ENV_DIR:-/etc/tbanastream}"
ENV_FILE="${ENV_FILE:-${ENV_DIR}/tbanastream.env}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ "${EUID}" -ne 0 ]]; then
    echo "Run this script as root: sudo DOMAIN=${DOMAIN} bash scripts/deploy.sh"
    exit 1
fi

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
    python3 python3-venv python3-pip postgresql postgresql-client \
    nginx certbot python3-certbot-nginx curl git

if ! id "${APP_USER}" >/dev/null 2>&1; then
    useradd --system --home-dir "${APP_DIR}" --shell /usr/sbin/nologin "${APP_USER}"
fi

if [[ "${REPO_DIR}" != "${APP_DIR}" ]]; then
    echo "Clone or copy this repository to ${APP_DIR}, then run:"
    echo "  sudo APP_DIR=${APP_DIR} DOMAIN=${DOMAIN} bash ${APP_DIR}/scripts/deploy.sh"
    exit 1
fi

python3 -m venv "${APP_DIR}/.venv"
"${APP_DIR}/.venv/bin/python" -m pip install --upgrade pip
"${APP_DIR}/.venv/bin/pip" install -r "${APP_DIR}/requirements-production.txt"

install -d -m 0750 -o root -g "${APP_USER}" "${ENV_DIR}"
if [[ ! -f "${ENV_FILE}" ]]; then
    install -m 0640 -o root -g "${APP_USER}" \
        "${APP_DIR}/.env.example" "${ENV_FILE}"
    echo "Created ${ENV_FILE}. Replace every placeholder before starting the API."
fi

sed -e "s|__APP_DIR__|${APP_DIR}|g" \
    -e "s|__APP_USER__|${APP_USER}|g" \
    "${APP_DIR}/deploy/systemd/tbanastream-api.service" \
    > /etc/systemd/system/tbanastream-api.service
chmod 0644 /etc/systemd/system/tbanastream-api.service

sed "s/__DOMAIN__/${DOMAIN}/g" \
    "${APP_DIR}/deploy/nginx/tbanastream-api-bootstrap.conf" \
    > /etc/nginx/sites-available/tbanastream-api
ln -sfn /etc/nginx/sites-available/tbanastream-api \
    /etc/nginx/sites-enabled/tbanastream-api
rm -f /etc/nginx/sites-enabled/default

chown -R root:"${APP_USER}" "${APP_DIR}"
chmod -R g+rX "${APP_DIR}"
chmod 0755 "${APP_DIR}"/scripts/*.sh
systemctl daemon-reload
systemctl enable postgresql nginx tbanastream-api
nginx -t
systemctl restart nginx

echo
echo "Base installation complete."
echo "1. Edit ${ENV_FILE}"
echo "2. Start the API: sudo systemctl start tbanastream-api"
echo "3. Issue SSL: sudo certbot certonly --nginx -d ${DOMAIN}"
echo "4. Activate HTTPS as described in docs/SELF_HOST_DEPLOYMENT.md"
