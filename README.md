# KisanFlow v13 — farmer procurement slot booking and queue management (SIH26032)

KisanFlow lets farmers book a capacity-controlled procurement slot, receive a token,
follow their live queue position and get a private "you are being called" notification.
Centre staff create slots, watch the queue and call one specific farmer.

Phase 1 MVP, mobile-first web app — **HTML + CSS + vanilla JavaScript** frontend,
**Flask JSON API** backend, SQLAlchemy with **SQLite** locally and **PostgreSQL** in
production. No native app, no build step, no frontend framework.

## 1. What works today

* Farmer registration and login (mobile number + password, hashed with werkzeug).
* Separate admin login for centre staff (`role='admin'`).
* Admin creates hourly/half-hourly slots with a capacity; a full slot closes automatically.
* Farmer books a slot: capacity is enforced inside one SQL statement, so two farmers on
  two phones can never overbook the same slot.
* Every booking gets a unique token and a live queue position (farmers ahead, position).
* Farmer ticket page with a large token, centre, date, time, crop and status.
* **My Turn / Status** panel, notification history with read/unread state.
* Admin **CALL FARMER** → that farmer's status becomes `Called` and only that farmer is
  notified; other farmers receive nothing.
* Status flow `Waiting → Called → Serving → Completed` (plus `Cancelled`, validated).
* Farmer can cancel their own waiting booking; admin can cancel a no-show.
* Multilingual farmer UI: **English / తెలుగు / हिन्दी** with a remembered choice.
* Admin dashboard: Total, Waiting, Called, Serving, Completed, Cancelled counters,
  slot capacity summary, centre/date/status filters, per-status actions, "Next in queue".
* `/health` reports application + database status for cloud platforms.
* 118 automated end-to-end checks (see section 9).

## 2. Requirements

* Python 3.13 or 3.14 (tested on 3.14.2), pip
* Packages in `requirements.txt` (Flask, SQLAlchemy, Werkzeug, gunicorn, psycopg2-binary)
* Optional for production: a managed PostgreSQL database and any HTTPS host

## 3. Install (Windows / PowerShell)

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

Using `.\venv\Scripts\python.exe` directly avoids PowerShell execution-policy issues; if
you prefer activation, `.\venv\Scripts\Activate.ps1` works once scripts are allowed.

## 4. Database

Nothing to do locally — on first start the app creates `procurement.db`, seeds three
procurement centres and the demo admin, and adds any missing indexes.
`DATABASE_URL` switches the same code to PostgreSQL:

```powershell
$env:DATABASE_URL = "postgresql://USER:PASSWORD@HOST:5432/DATABASE"
```
Schema changes in v13 are additive only (`CREATE INDEX IF NOT EXISTS`), so an existing
`procurement.db` with real bookings keeps working — nothing is dropped or rewritten.

## 5. Run locally

```powershell
.\venv\Scripts\python.exe app.py
```
Open `http://127.0.0.1:5000` (farmer), `http://127.0.0.1:5000/admin` (admin),
or `http://127.0.0.1:5000/health` to check the database connection.

To test with two phones on the same Wi-Fi, start with `PORT=5000` and open
`http://<your-lan-ip>:5000` on both phones (`START_KISANFLOW_LAN.bat` helps on Windows).

Demo admin: `admin@kisanflow.com` / `Admin@123` — **change this before any real pilot.**

## 6. Admin usage

1. Open `/admin` and login.
2. Choose the centre, the date (today or later), the capacity per slot, the start/end
   working hours and the slot length, then press **Generate slots**.
3. The slot list under the form shows `booked/capacity` and a FULL/LEFT badge.
4. Open **Dashboard** for the live queue:
   * counters for Total / Waiting / Called / Serving / Completed / Cancelled;
   * slot capacity summary (available / full / total from today onwards);
   * filters by centre, date and status;
   * one action per row: `CALL FARMER` (Waiting), `START SERVING` (Called),
     `MARK COMPLETE` (Serving);
   * **Next in queue →** completes the farmer being served and calls the next waiting one.
5. Calling a farmer creates a notification for that farmer only.

## 7. Farmer usage

1. Open the app on a phone and press **Create account** (name, 10-digit mobile, password).
2. Choose the language (`EN | తెలుగు | हिन्दी`) — it is remembered on that device.
3. Pick the procurement centre, the date, the crop and one of the available slots
   (each button shows how many places are left; full slots are disabled).
4. Press **Confirm booking** → the token appears with centre, date, time, crop and a live
   queue position ("3 farmers ahead of you").
5. Press **My Turn / Status** at any time to re-check; the page also polls every 2.5 s.
6. When the centre calls the token, a large **🔔 YOU ARE BEING CALLED** alert appears
   (with vibration and, if permission was granted, a browser notification).
7. While the booking is still Waiting, **Cancel my booking** releases the place.
8. **Logout** ends the session.

## 8. API overview

`PRD.md` section 10 lists everything. Highlights:

| Method | Path | Who | Purpose |
|---|---|---|---|
| POST | `/register`, `/api/register` | public | create a farmer account |
| POST | `/login`, `/api/login` | public | farmer/admin login |
| POST | `/logout`, `/api/logout` | any | end the session |
| GET | `/api/me` | any | current user (never returns a hash) |
| GET | `/api/centres` | any | procurement centres |
| GET | `/api/slots?centre_id=&date=` | any | slots with `booked` and `remaining` |
| POST | `/api/book` | farmer | capacity-checked booking + token |
| GET | `/api/my-booking` | farmer | own booking + queue position |
| GET | `/api/booking/<id>` | farmer | own booking (another farmer's id → 404) |
| POST | `/api/my-booking/cancel` | farmer | cancel while Waiting |
| GET | `/api/notifications` | farmer | own notification history |
| POST | `/api/notifications/read` | farmer | mark own notifications read |
| POST | `/api/generate-slots` | admin | create slots with capacity |
| GET | `/api/bookings?date=&centre_id=&status=` | admin | queue list |
| GET | `/api/stats` | admin | dashboard counters + slot capacity |
| POST | `/api/call/<id>` | admin | Waiting → Called + targeted notification |
| POST | `/api/serve/<id>` | admin | Called → Serving |
| POST | `/api/complete/<id>` | admin | Serving → Completed |
| POST | `/api/cancel/<id>` | admin | cancel a no-show |
| POST | `/api/advance` | admin | finish current, call next waiting |
| GET | `/health` | public | application + database status |

Failures always look like `{"success": false, "error": "..."}` with
400/401/403/404/409/429/500.

## 9. Tests

```powershell
.\venv\Scripts\python.exe tests\test_workflows.py
```
The suite uses a temporary SQLite database, so it is always safe to run. It prints one line
per check and ends with `passed: N failed: 0` (exit code 0 on success). Latest result:
**118 passed, 0 failed** — covering registration, login, slots, capacity, tokens, queue
isolation, targeted call notification, status transitions, authorisation, cancellation,
past dates, throttling, cross-origin blocking and a 5-thread overbooking race.

## 10. Deploy to a public HTTPS URL

1. Push this project to a Git repository (never commit `.env` or `procurement.db`).
2. Create a managed PostgreSQL database.
3. Create a Python web service from the repository.
4. Build command: `pip install -r requirements.txt`
5. Start command: `gunicorn app:app`
6. Environment variables:
   * `DATABASE_URL` = PostgreSQL connection string
   * `SECRET_KEY` = a long random secret
   * `COOKIE_SECURE=1`
   * `FLASK_DEBUG=0`
7. Open `/health` on the public URL — it must report `status: ok`, `database: connected`.
8. Open that same public URL on every farmer phone and on the admin laptop; one URL works
   for farmers in different towns because all bookings live in the shared database.

`DEPLOYMENT_CHECKLIST.txt` has the short version of the same steps.

## 11. Environment variables

| Variable | Purpose | Local default |
|---|---|---|
| `DATABASE_URL` | SQLAlchemy connection string | `sqlite:///procurement.db` |
| `SECRET_KEY` | session signing key | dev placeholder (change in production) |
| `COOKIE_SECURE` | send cookies only over HTTPS (`1` in production) | `0` |
| `FLASK_DEBUG` | Flask debug mode | `0` |
| `PORT` | local port | `5000` |
| `LOGIN_ATTEMPT_LIMIT` | failed logins per 5 minutes per IP | `12` |
| `REGISTER_ATTEMPT_LIMIT` | sign-ups per 5 minutes per IP | `20` |

## 12. Multilingual UI

* Dictionary: `static/i18n.strings.js` — every string as `[English, Telugu, Hindi]`.
* Engine: `static/i18n.js` — `KF.t()`, `KF.setLanguage()`, `data-i18n*` attributes.
* The switcher appears on `/`, `/login`, `/register` and `/farmer`; the choice is stored in
  `localStorage('kf_lang')` and survives reloads and logouts.
* The admin dashboard stays in English (the PRD makes admin language optional).

## 13. Security notes before real deployment

* Change the demo admin password (`admin@kisanflow.com` / `Admin@123`).
* Set a strong random `SECRET_KEY` and `COOKIE_SECURE=1`.
* Use managed PostgreSQL rather than SQLite for several towns, and enable backups.
* Serve only over HTTPS and keep `.env` out of version control (already in `.gitignore`).
* Consider admin account management and OTP verification for farmers as a next step.

## 14. Troubleshooting

| Symptom | Fix |
|---|---|
| `ModuleNotFoundError` | `.\venv\Scripts\python.exe -m pip install -r requirements.txt` |
| Activation blocked by execution policy | run `.\venv\Scripts\python.exe app.py` directly |
| Port already in use | `$env:PORT=5001; .\venv\Scripts\python.exe app.py` |
| `/health` returns 503 | database unreachable — check `DATABASE_URL` |
| "This slot is full" | the slot reached capacity; choose another slot |
| "Too many login attempts" | throttling is active; wait about five minutes |
| Slot list is empty | the admin has not created slots for that centre and date |
| Farmer page shows no ticket | that account has no booking yet — book from the booking form |

## 15. Notes about this version

* `V13_CHANGES.txt` — full change list for this upgrade.
* `PRD.md` — requirements with an implementation status per item.
* `design.md` — architecture, request flows, security and testing design.
* `TODO.md` — the tick-box checklist used while building v13.
* `_v12_backup/` — pre-upgrade templates and stylesheet, kept for reference only. The
  application never loads these files; the folder can be deleted safely.
* `V9_…V12_….txt`, `RUN_ON_MULTIPLE_MOBILES.txt` — older version notes kept for history.


