# TBana Stream merged-source report

Date: 2026-07-03

## Scope and method

- Folder A: `LiveTrigger-Windows(sub)/LiveTrigger`
- Folder B: `TBana`
- Output: `TBana Stream (Merged)`
- The repositories have unrelated Git histories, so there is no native common
  ancestor. Commit `dafec6a` from LiveTrigger was selected as the closest
  synthetic base after comparing every historical tree.
- Source was compared by content hash. Build outputs, virtual environments,
  caches, local databases, secrets, runtime feedback JSON, and release
  artifacts were excluded from the merged source folder.
- TBana Stream was used as the branding and packaging baseline. LiveTrigger
  patches were then merged at file, function, and conflict-hunk level.

## Files changed only in LiveTrigger

- `app/actions/executor-EDOPC.py`
- `app/actions/manager.py`
- `app/api/event_test-EDOPC.py`
- `assets/tibanakstream-dark.ico`
- `assets/tibanakstream-icon-dark.png`
- `tests/test_websocket_overlay_routing.py`

All six were retained in the merged folder. User-facing strings in the two
EDOPC fallback files were updated to TBana Stream branding.

## Files changed only in TBana

- `TBanaStream.spec`
- `app/api/feedback.py`
- `app/auth/email.py`
- `dashboard/index.html`
- `installer/TBanaStream.iss`
- `render.yaml`
- `start-tbana-stream.bat`
- `tests/test_feedback.py`
- `tests/test_spin.py`

All nine were retained. Three `feedback/*.json` files were classified as local
runtime submissions rather than source code and were intentionally excluded.

## Files modified in both

- `.env.example`
- `.gitignore`
- `CHANGELOG.md`
- `LiveTrigger.spec` / `TBanaStream.spec`
- `README.txt`
- `app/actions/executor.py`
- `app/api/actions_v2.py`
- `app/api/auth.py`
- `app/api/event_test.py`
- `app/api/events.py`
- `app/api/gift_catalog.py`
- `app/api/routes.py`
- `app/api/simulator.py`
- `app/api/subscription.py`
- `app/api/tiktok.py`
- `app/api/update.py`
- `app/api/websocket.py`
- `app/auth/__init__.py`
- `app/auth/remote_client.py`
- `app/auth/repository.py`
- `app/auth/service.py`
- `app/core/config.py`
- `app/core/paths.py`
- `app/core/websocket_manager.py`
- `app/desktop_launcher.py`
- `app/listeners/tiktok_listener.py`
- `app/main.py`
- `app/production_main.py`
- `app/queue/manager.py`
- `app/rules/engine.py`
- `app/rules/event_engine.py`
- `app/storage/sqlite_store.py`
- `app/subscription/__init__.py`
- `app/tiktok/connector.py`
- `app/widgets/__init__.py`
- `app/widgets/spin.py`
- `build-windows.ps1`
- `check-system.bat`
- `dashboard/events.html`
- `deploy/systemd/tbanastream-api.service`
- `docs/SELF_HOST_DEPLOYMENT.md`
- `install.bat`
- `installer/LiveTrigger.iss` / `installer/TBanaStream.iss`
- `start-livetrigger.bat`
- `tests/test_offline_cache.py`
- `tests/test_subscription_flow.py`
- `tests/test_update.py`
- `web/app.js`
- `web/index.html`
- `web/spin.html`
- `web/style.css`

## Merge conflicts

Three files merged cleanly with automatic three-way merge:

- `app/api/routes.py`
- `app/queue/manager.py`
- `app/rules/engine.py`

The remaining shared files required manual or function-level resolution. The
main conflict groups were:

- TBana branding, version 1.0.9, executable/installer names, and data migration
  versus legacy LiveTrigger names.
- TBana password recovery, feedback, SMTP, and queued `!spin` implementation
  versus LiveTrigger login enforcement, runtime entitlement checks, simulator
  behavior, and dedicated overlay routing.
- TBana's richer dashboard versus LiveTrigger's plan-lock UI and simulator
  diagnostics.
- TBana's configurable production price and Free trigger limit versus
  LiveTrigger's test-price and stricter trigger-limit changes.

## How conflicts were resolved

- Retained TBana Stream branding, version `1.0.9`, updater asset names,
  installer names, icons, paths, migration aliases, and documentation.
- Retained TBana password-reset tables/API, SMTP email support, feedback API,
  and the serialized `!spin` worker queue with cooldown notices.
- Added LiveTrigger authentication checks to action tests, event tests,
  simulator calls, TikTok reconnects, startup, event execution, action
  execution, and linked spin actions.
- Combined the spin implementations: real viewer spins use the TBana queue;
  dashboard simulations bypass disabled/cooldown state, report overlay
  connections, execute synchronously for diagnostics, and still enforce plan
  limits on linked actions.
- Routed both `spin` and `spin_notice` messages only to the dedicated spin
  overlay while preserving normal screen-overlay traffic.
- Used the TBana dashboard as the clean base, then applied only missing
  LiveTrigger hunks: plan-locked rows and controls, entitled initialization,
  overlay-aware spin test results, and locked spin-action options. Existing
  TBana update, account, feedback, and TikTok UI blocks were not duplicated.
- Kept TBana's default production price (`PRO_PRICE_CENTS=2990`) instead of the
  incompatible LiveTrigger test value (`200`).
- Used LiveTrigger's Free trigger limit of 10 instead of TBana's 30 because the
  merged runtime entitlement enforcement and its tests depend on that limit.
- Kept the TBana PyInstaller/Inno Setup names while adding LiveTrigger's
  Tkinter build preflight and hidden imports.
- Kept TBana's pip/install flow and added LiveTrigger's `ensurepip` recovery
  fallback.

## Verification

- Python syntax: 74 files parsed, 0 errors.
- JavaScript syntax: `web/app.js` and dashboard inline JavaScript passed.
- Conflict markers: 0.
- Reject files: 0.
- Tests: 37 passed, 5 subtests passed.
- Warnings: 3 third-party deprecation warnings from `websockets`/TikTokLive.
- No commit or push was performed.
