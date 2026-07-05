# TBana Stream self-host deployment

This guide deploys only the subscription API on Ubuntu Server 24.04 LTS.
The Windows desktop application and local development command remain
unchanged:

```bash
uvicorn app.main:app --reload
```

Production runs `app.production_main:app` on `127.0.0.1:8000`. Nginx is the
only public entry point.

## 1. Prepare DNS and the server

Point an `A` record for `api.tbanastream.com` to the server's public IPv4
address. If the domain changes, replace it in the commands below and set the
same host in `PUBLIC_BASE_URL`, `TRUSTED_HOSTS`, and the ToyyibPay URLs.

Open only SSH, HTTP, and HTTPS:

```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
```

PostgreSQL and Uvicorn must not be exposed publicly.

## 2. Clone the application

```bash
sudo git clone https://github.com/shahred94/Tbana.git /opt/tbanastream
cd /opt/tbanastream
sudo DOMAIN=api.tbanastream.com bash scripts/deploy.sh
```

The deployment script installs Python, PostgreSQL, Nginx, Certbot, Git, and
the production Python dependencies. It also creates the `tbanastream` system
user, virtual environment, systemd unit, bootstrap Nginx site, and private
environment file.

## 3. Create PostgreSQL user and database

Generate a strong database password, then run:

```bash
sudo -u postgres psql
```

In `psql`:

```sql
CREATE USER tbanastream WITH ENCRYPTED PASSWORD 'replace-with-strong-password';
CREATE DATABASE tbanastream OWNER tbanastream;
\q
```

Keep PostgreSQL listening on localhost. The application uses only
`DATABASE_URL`; there is no provider-specific database connection.

## 4. Configure the environment

The deploy script creates `/etc/tbanastream/tbanastream.env` from
`.env.example`. Generate a secret:

```bash
openssl rand -hex 32
sudo nano /etc/tbanastream/tbanastream.env
```

Set at least:

```dotenv
APP_ENV=production
DATABASE_URL=postgresql://tbanastream:URL_ENCODED_PASSWORD@127.0.0.1:5432/tbanastream
SECRET_KEY=PASTE_THE_GENERATED_SECRET
ACCESS_TOKEN_EXPIRE_MINUTES=43200
PUBLIC_BASE_URL=https://api.tbanastream.com
TRUSTED_HOSTS=api.tbanastream.com,127.0.0.1,localhost
ALLOWED_ORIGINS=http://127.0.0.1:8000,http://localhost:8000
LOG_LEVEL=info
TOYYIBPAY_BASE_URL=https://toyyibpay.com
TOYYIBPAY_SECRET_KEY=YOUR_TOYYIBPAY_SECRET
TOYYIBPAY_CATEGORY_CODE=YOUR_CATEGORY_CODE
TOYYIBPAY_CALLBACK_URL=https://api.tbanastream.com/api/payment/callback
TOYYIBPAY_RETURN_URL=https://api.tbanastream.com/api/payment/return
PRO_PRICE_CENTS=2990
PRO_DURATION_DAYS=30
```

Use percent-encoding for reserved characters in the database password.
Do not commit this file. It is readable only by root and the API service
group.

Do not put `SUBSCRIPTION_API_URL` in the server environment. That variable is
desktop-only and belongs in `desktop.env` or the Windows `.env.local` file.

`SECRET_KEY` and `ACCESS_TOKEN_EXPIRE_MINUTES` are production configuration
guards/reserved settings. Existing opaque database sessions and their
business rules remain unchanged.

## 5. Start and verify the API

```bash
sudo systemctl start tbanastream-api
sudo systemctl status tbanastream-api
sudo journalctl -u tbanastream-api -n 100 --no-pager
curl http://127.0.0.1:8000/health
curl http://api.tbanastream.com/health
```

Expected response:

```json
{"status":"ok"}
```

The service starts automatically after reboot and restarts after a crash.

## 6. Install HTTPS

Issue the certificate while the bootstrap HTTP site is active:

```bash
sudo certbot certonly --nginx -d api.tbanastream.com
```

Activate the final HTTPS template:

```bash
sudo sed 's/__DOMAIN__/api.tbanastream.com/g' \
  deploy/nginx/tbanastream-api.conf \
  | sudo tee /etc/nginx/sites-available/tbanastream-api >/dev/null
sudo nginx -t
sudo systemctl reload nginx
curl https://api.tbanastream.com/health
sudo certbot renew --dry-run
```

The Nginx configuration provides HTTP-to-HTTPS redirect, TLS, compression,
security headers, forwarded client details, and WebSocket upgrade headers
for future use.

## 7. Migrate the current production database

Do this during a maintenance window so no payment or account writes occur
between export and cutover. Keep the old provider available until all checks
pass.

On a secure machine with PostgreSQL client tools:

```bash
export OLD_DATABASE_URL='PASTE_OLD_PROVIDER_POSTGRES_URL'
pg_dump --format=custom --no-owner \
  --dbname="$OLD_DATABASE_URL" \
  --file=tbanastream-migration.dump
```

Copy the dump to the new server, stop the API, and restore it:

```bash
scp tbanastream-migration.dump user@server:/tmp/
sudo systemctl stop tbanastream-api
sudo ENV_FILE=/etc/tbanastream/tbanastream.env \
  bash scripts/restore_db.sh /tmp/tbanastream-migration.dump --yes
sudo bash scripts/restart.sh
```

Verify login, `/api/auth/me`, subscription status, and a ToyyibPay sandbox
payment before changing desktop clients to the new domain. Update the
ToyyibPay dashboard callback/return URLs to the HTTPS URLs in the ENV file.

## 8. Update the application

The update script takes a database backup before a fast-forward-only Git
update:

```bash
cd /opt/tbanastream
sudo BRANCH=main bash scripts/update.sh
```

To restart without updating:

```bash
sudo DOMAIN=api.tbanastream.com bash scripts/restart.sh
```

## 9. Backup and restore

Create an on-demand compressed PostgreSQL dump:

```bash
cd /opt/tbanastream
sudo bash scripts/backup_db.sh
```

Backups default to `/var/backups/tbanastream` and files older than 14 days
are removed. Override retention with `KEEP_DAYS=30`.

Restore is intentionally explicit and destructive:

```bash
sudo bash scripts/restore_db.sh \
  /var/backups/tbanastream/tbanastream_YYYYMMDDTHHMMSSZ.dump --yes
```

Schedule daily backups with root's crontab:

```cron
15 3 * * * cd /opt/tbanastream && /bin/bash scripts/backup_db.sh >> /var/log/tbanastream-backup.log 2>&1
```

Copy backups to a second encrypted location; a backup stored only on the API
server is not sufficient for disaster recovery.

## 10. Security and operations checklist

- Keep `/etc/tbanastream/tbanastream.env` out of Git and rotate any secret
  previously exposed.
- Allow only the exact hosts in `TRUSTED_HOSTS`; never use `*` in production.
- Keep CORS origins narrow. Desktop API traffic is server-to-server, so add
  browser origins only when actually needed.
- Monitor `journalctl -u tbanastream-api` and Nginx logs.
- Apply Ubuntu security updates regularly.
- Add edge/WAF rate limiting after measuring normal login and payment
  traffic. It is not enabled in this migration to avoid changing existing
  API behavior.
- Test restores periodically.

## 11. Rollback

Do not delete the old deployment until the migration is verified. Deprecated
Railway configuration is retained under `legacy/railway/`, and
`app.cloud_main:app` remains a compatibility import. The ignored local
`.tools/railway-*` CLI files are deprecated and are not required by local
development or production.
