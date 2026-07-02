#!/usr/bin/env bash
set -Eeuo pipefail

DOMAIN="${DOMAIN:-api.tbanastream.com}"

if [[ "${EUID}" -ne 0 ]]; then
    echo "Run with sudo."
    exit 1
fi

systemctl restart tbanastream-api
systemctl --no-pager --full status tbanastream-api

for attempt in {1..15}; do
    if curl --fail --silent --show-error \
        "https://${DOMAIN}/health" | grep -q '"status":"ok"'; then
        echo "Health check passed."
        exit 0
    fi
    sleep 2
done

echo "Health check failed. Inspect: journalctl -u tbanastream-api -n 100"
exit 1
