# Deprecated Railway deployment

These files are retained only for emergency rollback. Production now uses the
self-hosted configuration in `deploy/` and `app.production_main:app`.

Railway CLI files under the ignored `.tools/` directory are also deprecated
and are not required for local development or self-hosted deployment.

To build the legacy container from the repository root:

```bash
docker build -f legacy/railway/Dockerfile .
```
