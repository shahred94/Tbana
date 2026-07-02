LiveTrigger - Windows Quick Start
=================================

LiveTrigger supports Windows 10 and Windows 11.


FIRST-TIME SETUP
----------------

Step 1: Double-click install.bat

If Python is missing, install.bat will automatically download the
official Python 3.13 installer from python.org, verify it, and install it.
The installer displays download progress; the file is about 28 MB.

Wait until the installer displays:
[SUCCESS] LiveTrigger is ready to use.


START LIVETRIGGER
-----------------

Step 2: Double-click start-livetrigger.bat

The dashboard opens automatically in your default browser when the
server is ready. Keep the command window open while LiveTrigger is running.


OPEN THE DASHBOARD
------------------

Step 3: Open this address in your web browser:

http://127.0.0.1:8000


ACCOUNT AND PLANS
-----------------

The dashboard can be opened as a Guest, but creating Actions and Event
Triggers requires an account.

Free account:
- Up to 6 Actions
- Up to 30 Event Triggers

Pro account:
- Unlimited Actions and Event Triggers
- Edge Text To Speech
- Premium and future features

Account passwords are hashed with bcrypt. Login sessions use an HttpOnly
local browser cookie, and only a hash of the session token is stored.


STOP LIVETRIGGER
----------------

Return to the LiveTrigger command window and press Ctrl+C.


SYSTEM CHECK
------------

If LiveTrigger does not start, double-click:

check-system.bat

It will check Python, the virtual environment, pip, Uvicorn, and the
LiveTrigger application.


PYTHON NOT FOUND OR UNSUPPORTED
-------------------------------

LiveTrigger supports Python 3.10 through Python 3.13.
Python 3.14 is not currently supported by pygame.

Install Python 3.13 from:

https://www.python.org/downloads/windows/

During Python installation, select:

Add Python to PATH

Then run install.bat again.

Manual installation is only needed if the automatic Python download
or installation fails.


NOTES
-----

- Dependencies are installed only inside the .venv folder.
- LiveTrigger does not use or modify global pip packages.
- You do not need to activate the virtual environment manually.
- Run install.bat again whenever requirements.txt changes.
- Edge Text To Speech requires an internet connection while speaking.


SUBSCRIPTION API
----------------

Production is self-hosted with app.production_main:app, PostgreSQL, systemd,
and Nginx. Configuration and ToyyibPay credentials are loaded from a private
environment file on the server.

To connect this Windows desktop app to the subscription API, set this
environment variable in a .env.local file beside requirements.txt:

SUBSCRIPTION_API_URL=https://api.tbanastream.com

The desktop then proxies login and subscription requests to the API while
Actions and Event Triggers remain on the local PC. See .env.example for
the complete variable list. Keep .env.local private; it is excluded by
.gitignore.

For Ubuntu 24.04 deployment, PostgreSQL migration, SSL, backup, restore, and
updates, see docs/SELF_HOST_DEPLOYMENT.md. Deprecated Railway files are kept
under legacy/railway for rollback only.
