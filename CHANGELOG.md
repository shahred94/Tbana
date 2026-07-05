# TBana Stream Change Record

## Unreleased - Pro price alignment

- Aligned the dashboard and ToyyibPay Pro subscription price to RM29.90.

## 1.0.9 - Feedback, account recovery and !spin flow

- Added local feedback submission with optional SMTP delivery.
- Added secure password reset codes and the Forgot Password interface.
- Sequenced `!spin` animation and linked actions through a single queue.
- Added cooldown notices with viewer status and remaining time.
- Unified current user-facing branding under TBana Stream.

## Unreleased - TBana Stream rebrand

- Unified the desktop app, dashboard, overlays, subscription screens, and
  Windows installer under the **TBana Stream** name.
- Renamed new build outputs to `TBana Stream.exe` and
  `TBana-Stream-Setup-<version>.exe`.
- Added `start-tbana-stream.bat`; the old `start-livetrigger.bat` remains as
  a compatibility launcher.
- Preserved legacy database, cookie, localStorage, and preset identifiers so
  existing user data and sessions continue to work.

## Unreleased - Dashboard QOL batch 11–15

- Reordered the dashboard workflow to TikTok Settings, TikTok Live Log,
  Configuration Presets, Action Library, Events Library, and Event Simulator,
  with Overlay, Spin Wheel, Queue, and Recent Activity grouped underneath.
- Standardized primary section headings and added a polished accent hover,
  focus outline, and directional movement to clickable panel headers.
- Moved panel hover emphasis to an outer blue focus ring and standardized
  card dimensions, padding, arrow alignment, icon width, and title position.
- Softened panel hover glow with a responsive 50ms transition, added a subtle
  silver-blue open state, and layered a restrained dark gradient into cards.
- Replaced neon-green panel titles with medium-weight Segoe UI Variable
  silver text and a soft-cyan hover state; status greens remain unchanged.
- Extended the same silver, medium-weight typography to TikTok Settings,
  TikTok Live Log, Configuration Presets, Action Library, and Events Library.
- Added aligned fixed-width icons to every primary dashboard heading,
  including Configuration Presets and Events Library.
- Standardized collapsible dashboard header typography across Spin Wheel,
  Live Queue Monitor, Recent Activity, Overlay, and Event Simulator panels.
- Placed Action/Event status badges and their Enable/Disable controls on one
  horizontal line to reduce library row height.
- Added inline Action and Event validation with highlighted invalid fields,
  replacing the main editor validation popups.
- Added a clear keyboard-target reminder beside the shared test countdown and
  an optional locally remembered countdown beep.
- Made Overlay, Spin, Queue, Recent Activity, and Event Simulator panels
  collapsible, with each open/closed state remembered locally.
- Replaced immediate Action/Event deletion with a six-second Undo Delete
  window and visible toast action.
- Added a four-step first-run setup guide for login, TikTok username, browser
  overlay, and Alt+Tab-friendly Action testing. The guide can be reopened from
  the top dashboard bar.

## Unreleased - Dashboard QOL batch 6–10

- Added persistent Compact and Comfortable dashboard density modes.
- Added a Recent Activity panel backed by a thread-safe event/queue activity
  feed, with refresh and clear controls.
- Improved simulator feedback to show Countdown, Executing, Completed, or
  Failed states instead of a single plain status message.
- Added backend queue Pause, Resume, Clear All, per-gift Clear Pending, pending
  counts, and estimated wait time based on Action duration plus queue delay.
- Added local gift favourites. Starred gifts are pinned above other gifts in
  the searchable suggestion list while retaining coin-value sorting.

## Unreleased - Dashboard QOL batch 1–5

- Persisted Action/Event search text, enabled-status filters, coin sorting, and
  expanded list state across dashboard refreshes.
- Added backend-enforced Clone controls for Actions and Event Triggers.
  Duplicated Actions retain all steps and settings with a unique `(Copy)` name.
- Added drag-and-drop ordering for Sound, Keyboard, TTS, and Webhook Action
  steps; the visual order is saved as the real execution order.
- Added unsaved-change warnings when closing Action/Event editors or leaving
  the dashboard with modified form values.
- Added quick Action enable/disable controls and retained the existing Event
  toggle. Disabled Actions are now skipped by the event engine, including
  Actions selected inside all/random groups.
- Added All/Enabled/Disabled status filters to both libraries.

## Unreleased - Clickable hover highlights

- Added consistent hover feedback to dashboard buttons and collapsible summary
  controls.
- Hovered controls become brighter, lift slightly, and receive a visible
  outline and shadow while preserving their original action colors.
- Added matching keyboard focus highlights for accessibility.
- Disabled controls remain muted and do not receive hover effects.
- Respects the operating system reduced-motion preference.

## 2026-07-01 - Collapsed Spin Wheel Settings v1.0.4

- Changed the complete Spin Wheel Settings panel to a collapsed section by
  default, reducing dashboard height.
- The collapsed row only shows the panel title and `Show settings` control.
- Clicking the row reveals wheel items, actions, test controls, and the nested
  Advanced !spin Settings section.

## 2026-07-01 - Dashboard test countdown v1.0.3

### Alt+Tab-friendly testing

- Added a shared adjustable test delay with `0`, `3`, `5`, and `10` second
  options; new installations default to 3 seconds.
- Applied the delay to Test Action, Events Library Test, and every Event
  Simulator option, including Simulate Gift.
- The delay is enforced by the local backend, so switching away from the
  browser does not cancel or shorten it.
- Added a visible countdown and Alt+Tab instruction before execution.
- Replaced blocking Action/Event test completion alerts with toast messages.
- Stored the selected test delay locally so it remains selected after restart.
- Live TikTok events and normal gift queue timing remain unchanged.

## 2026-07-01 - Windows installer v1.0.2

### Audit fixes

- Rebuilt the release path around version `1.0.2` so the installer includes
  all desktop, subscription, event, gift, and `!spin` changes from 30 June.
- Changed the build script to accept a version parameter and pass the matching
  distribution folder to Inno Setup instead of hardcoding `1.0.1`.
- Added Windows `SendInput` scan-code support for `Enable Game compatibility
  mode`, including configured modifiers, special keys, and function keys.
- Kept automatic PyAutoGUI fallback if Windows game input cannot be sent.
- Configured the packaged LiveTrigger executable to request Administrator
  access, preventing Windows UIPI from blocking input to elevated games.
- Expanded `.gitignore` to exclude runtime databases, caches, logs, build
  folders, distribution folders, and generated installer executables.
- Removed unused `EDOPC` and legacy event-engine backup source files.
- Added unit coverage for Windows keyboard key mapping and key-release order.

## 2026-06-30 - Latest audit on new PC

### Summary

LiveTrigger Desktop has been connected to the production Subscription API and packaged as a Windows installer. The newest distributable build is `LiveTrigger-Setup-1.0.1.exe`.

### Latest completed changes

- Improved specific gift event setup:
  - Replaced the large fixed gift dropdown with a compact searchable/custom gift input.
  - Added a custom gift suggestion list with smaller text and more visible results.
  - Gift suggestions now show catalogue icons when available and sort by coin value from lowest to highest.
  - Users can still pick gifts from the loaded catalogue, or type an exact gift name manually for overseas/region-specific gifts.
  - Gift matching still uses the saved trigger value exactly with existing case-insensitive matching.
- Simplified `Spin Wheel Settings` layout:
  - Moved access rules, cooldown controls, and spin overlay URL into a collapsed `Advanced !spin Settings` section.
  - Wheel item editing now takes less vertical space by default.
- Added adjustable `!spin` access and cooldown rules:
  - Non-followers are blocked by default through `Require follower to use !spin`.
  - Non-follower cooldown default: 30 minutes, used when follower requirement is turned off.
  - Follower cooldown default: 10 minutes.
  - Fan Club cooldown default: 8 minutes.
  - Subscriber cooldown default: 5 minutes.
  - Cooldown is enforced per TikTok user by the backend.
  - Dashboard `Spin Wheel Settings` now lets users adjust these cooldown values.
- Added dedicated `!spin` overlay URL:
  - New spin-only browser source page: `/overlay/spin.html?screen=1`.
  - Dashboard `Spin Wheel Settings` now shows Copy/Open controls for the dedicated spin overlay.
  - Spin-only overlay ignores normal gift alert UI, making TikTok Live Studio setup cleaner.
- Cleaned Events page labels:
  - Renamed `Events` to `Events Library`.
  - Removed the old `Create Event` section header above the simulator.
- Updated Event Simulator like test:
  - Changed `Simulate 15 Likes` to `Simulate 50 Likes`.
  - Simulator now sends `{ count: 50 }` for like events.
- Added dashboard editor for `!spin` wheel:
  - New `Spin Wheel Settings` panel lets users edit wheel results and link each result to an Action preset.
  - Wheel items are saved using local settings key `spin_wheel_segments`.
  - Legacy one-line text wheel items are still supported.
  - Added enable/disable setting using `spin_wheel_enabled`.
  - `!spin` now reads the saved wheel list dynamically, shows the winning result, and executes the linked Action preset if one is selected.
  - Added Save, Reset Default, and Test `!spin` controls.
- Reworked Event editing UI:
  - Event `Edit` now opens the friendly Event modal instead of browser prompt popups.
  - Edit modal pre-fills user scope, trigger type, trigger value, action preset, all-actions group, and random-actions group.
  - Save updates the event through `/api/actions/event-triggers/{id}`.
  - Event create and edit now share the same UI pattern, closer to Action edit.
- Prioritized and cleaned up New Event trigger list:
  - Main visible triggers are now `Sending a specific gift`, `Follow`, `Sending likes (taps)`, and `Commenting a command`.
  - Other less-ready/advanced triggers are hidden under `More triggers`.
  - New Event now defaults to `Sending a specific gift`.
  - Specific gift matching is now case-insensitive and trims spaces.
  - Command triggers starting with `!` now match the first comment command exactly, e.g. `!spin`.
- Marked unfinished media actions as coming soon:
  - `Show GIF / Image` and `Play Video` are now greyed out and disabled.
  - Added a `Coming soon` badge so users know these are planned updates, not broken features.
- Added built-in TikTok LIVE `!spin` widget:
  - Viewer comment `!spin` now triggers a TikFinity-style spin wheel on the overlay browser source.
  - Overlay receives a new WebSocket message type: `spin`.
  - Added wheel UI, animation, random result display, and auto-hide.
  - Added `Simulate !spin` button in Event Simulator for local testing.
  - Improved WebSocket dispatch so widget events can be sent from sync/background code after an overlay client has connected.
- Fixed TikTok like/tap trigger threshold:
  - Like triggers now accumulate taps per user and per trigger.
  - Example: minimum likes `15` now triggers after 15 separate tap events, not only when TikTok sends one event with `count >= 15`.
  - The counter keeps any remainder, so 20 taps on a 15-like trigger leaves 5 taps toward the next trigger.
  - Also improved action ID resolution for grouped action modes for compatibility.
- Made Action duration enforce maximum runtime:
  - `Maximum Duration (seconds)` now acts as a cap for the whole action preset.
  - Sound playback is stopped when the duration expires.
  - TTS playback is stopped when the duration expires.
  - Webhook timeout is capped by the remaining duration.
  - Keyboard hold duration is capped by the remaining duration.
  - Remaining steps are skipped once the duration window is reached.
  - Manual Test Action and live/queued event execution both use the same duration cap.
- Reduced Action execution delay:
  - Removed the hardcoded 1-second wait before keyboard actions.
  - Reason: sound actions start immediately, but keyboard/hotkey actions were intentionally sleeping for 1 second, making it feel like sound played first and the real action happened late.
  - Remaining intentional waits: gift queue delay if configured, keyboard hold duration in compatibility mode, and TTS playback wait.
- Removed blocking Action save popup:
  - Replaced browser `alert("Action saved successfully!")` with the app toast notification.
  - New notification auto-closes after 5 seconds and does not require clicking OK.
- Updated Event Simulator gift options:
  - Simulator gift dropdown now includes the full TikTok gift list used by Create Event.
  - Total simulator options: 30 including placeholder.
  - This replaces the older short list that only had a few gifts.
- Added desktop subscription/login integration in the dashboard:
  - Guest, Free, and Pro plan detection.
  - Top-right Login button and modern account dropdown.
  - Login/Register modal.
  - Profile modal.
  - Subscription page.
  - Upgrade to Pro flow.
  - Offline verified state.
- Added plan enforcement UI:
  - Guest can view dashboard but cannot create Actions or Event Triggers.
  - Free plan limit display: 6 Actions and 30 Event Triggers.
  - Pro plan display: unlimited Actions, unlimited Event Triggers, Edge TTS enabled.
- Updated Upgrade pricing display:
  - Original price: RM59.90.
  - Discounted price: RM29.90.
- Added production API configuration for desktop:
  - `SUBSCRIPTION_API_URL=<legacy-production-api-url>`
  - Stored in `desktop.env`.
- Added packaged app path handling:
  - Runtime resources load from bundled installer folder.
  - User data stores under `%LOCALAPPDATA%\LiveTrigger`.
  - SQLite database no longer needs to live inside the installed app folder.
  - Bundled sounds are copied into user data on startup.
- Added desktop launcher:
  - Starts the local FastAPI/Uvicorn server.
  - Opens dashboard automatically.
  - Shows a small LiveTrigger control window.
  - Provides Open Dashboard and Exit buttons.
  - Writes launcher errors to `%LOCALAPPDATA%\LiveTrigger\launcher-error.log`.
- Fixed cache issue for dashboard:
  - Dashboard route now uses no-cache headers.
  - Startup redirect uses `/dashboard/events.html?v=1.0.1`.
  - This helps prevent old UI from hiding the login button after update.
- Created Windows installer build:
  - Installer version: `1.0.1`.
  - Install path: `%LOCALAPPDATA%\Programs\LiveTrigger`.
  - No admin required.

### Important files changed

- `dashboard/events.html`
- `app/auth/remote_client.py`
- `app/auth/service.py`
- `app/core/config.py`
- `app/core/paths.py`
- `app/desktop_launcher.py`
- `app/main.py`
- `app/storage/sqlite_store.py`
- `app/subscription/service.py`
- `desktop.env`
- `LiveTrigger.spec`
- `installer/LiveTrigger.iss`
- `build-windows.ps1`
- `build-windows.bat`
- `.env.example`
- `.gitignore`
- `tests/test_offline_cache.py`

### Installer artifacts

- Latest installer:
  - `release/LiveTrigger-Setup-1.0.1.exe`
  - Size: about 33.3 MB
  - SHA256: `3AE5896ACA7E52FBFF3DA631014C96EFFF8A58B7B462F0F0DFB50E80DA262534`
- Old installer still present:
  - `release/LiveTrigger-Setup-1.0.0.exe`
  - Do not use for testing on another PC because it may show the old dashboard without the new login button.

### Backend status

- Subscription API production URL:
  - Legacy hosted URL retired; active URL is configured through ENV.
- Backend features completed:
  - Register/Login/Logout/session.
  - `/api/auth/me`.
  - Subscription status.
  - ToyyibPay Sandbox payment flow.
  - Payment callback updates subscription to Pro.
  - PostgreSQL on the legacy hosted deployment.
  - Guest/Free/Pro limits.
- Legacy production price variable was updated to RM29.90:
  - `PRO_PRICE_CENTS=2990`

### Validation status

- Syntax check:
  - `py -3.13 -m compileall -q app` passed on 2026-06-30.
- Unit tests:
  - Currently blocked on this new PC because Python dependencies are not installed in the active environment:
    - Missing `httpx`.
    - Missing `fastapi`.
  - Existing `.venv` is not usable on this PC because it points to old path:
    - `C:\Users\Plus\AppData\Local\Programs\Python\Python313\python.exe`
- Previous package smoke test status:
  - Installed app opened dashboard.
  - Dashboard contained `id="top-login-button"`.
  - Dashboard returned no-cache headers.
  - Local database created in `%LOCALAPPDATA%\LiveTrigger`.

### Known notes / issues

- `git` is not available in PATH on this PC, so this audit used file timestamps and code inspection instead of Git history.
- There are two installer versions in `release`. For another PC, use only `LiveTrigger-Setup-1.0.1.exe`.
- If another PC still shows no Login button:
  1. Uninstall old LiveTrigger.
  2. Install `LiveTrigger-Setup-1.0.1.exe`.
  3. Open `http://127.0.0.1:8000/dashboard/events.html?v=1.0.1`.
  4. Press `Ctrl + F5`.
  5. Check `%LOCALAPPDATA%\LiveTrigger\launcher-error.log`.

### Recommended next action

1. Recreate the virtual environment on this PC.
2. Install dependencies from `requirements.txt`.
3. Run unit tests again.
4. Test installer `LiveTrigger-Setup-1.0.1.exe` on the other PC.
5. Confirm:
   - Login button appears.
   - Login works.
   - Free plan limits show 6/30.
   - Upgrade shows RM29.90.
   - Pro account unlocks unlimited limits and Edge TTS.
