# KisanFlow — Design Document (v13)

## 1. Architecture

```
Farmer phones (HTML + CSS + vanilla JS)          Admin laptop / tablet
        |  fetch() JSON over HTTPS                      |
        +---------------> Flask app (app.py) <----------+
                              |  SQLAlchemy Core (parameterised SQL)
                              v
                   SQLite (local)  /  PostgreSQL (production)
```
One deployable Python web service (Gunicorn `app:app`), one shared database, stateless
sessions on a signed cookie - the same public URL works for every town.

## 2. File map

```
app.py                      Flask app: config, schema bootstrap, auth, farmer API, admin API
templates/index.html        landing page (EN/TE/HI)
templates/login.html        shared login for farmers and admins (EN/TE/HI)
templates/register.html     farmer self-registration (EN/TE/HI)
templates/farmer.html       booking + ticket + My Turn + notifications (EN/TE/HI)
templates/admin_login.html  admin-only login form
templates/admin.html        slot creation and slot list (admin, English)
templates/dashboard.html    live queue control (admin, English)
static/style.css            all styling (mobile-first; v13 components appended)
static/i18n.strings.js      [English, Telugu, Hindi] dictionary rows
static/i18n.js              KF.t / KF.setLanguage / markup applier / notification text
static/sw.js                minimal service worker used for browser notifications
tests/test_workflows.py     offline end-to-end suite (temporary SQLite database)
_v12_backup/                pre-upgrade templates + stylesheet kept for reference
```

## 3. Request flow: booking (race-safe)

```
POST /api/book  {crop, slot_id}
  session + role check (farmer)
  booking_write_guard()          SQLite: one in-process lock
  engine.begin()
    SELECT slot ... FOR UPDATE   PostgreSQL: row lock on the slot
    validate: exists, valid date, not in the past
    reject if the farmer already has an active booking          -> 409
    reject if active bookings >= capacity                       -> 409
    INSERT ... SELECT ..., COALESCE(MAX(token),0)+1, ...
      WHERE (SELECT COUNT(*) ... active) < capacity
      RETURNING id, token        <- capacity check + token in ONE statement
    if no row was returned                                   -> 409 "just filled"
  COMMIT -> 201 {booking_id, token, slot, centre, ahead, position}
```
The database is the final authority: even with ten simultaneous taps the slot can never
exceed its capacity (proved by the 5-thread test in `tests/test_workflows.py`).

## 4. Queue position

```
ahead = COUNT(bookings WHERE slot_id = my slot
                AND status IN ('Waiting','Called','Serving')
                AND token < my token)
position = ahead + 1        (0 ahead while my status is Called/Serving/Completed)
```
Scoped strictly to the farmer's own centre + date + slot, so unrelated queues can never
leak into a position. Ordering is deterministic through the token sequence.

## 5. Booking status machine

```
Waiting --> Called --> Serving --> Completed (terminal)
   |           |           |
   +-----------+-----------+----> Cancelled --> Waiting (admin re-open)
```
Transitions are validated in one helper (`transition_booking`) that also writes the
targeted notification inside the same transaction. Repeating the same action is an
idempotent no-op, so double taps cannot spam a farmer.

## 6. Notification targeting

`transition_booking` inserts `notifications(user_id = that booking's farmer, booking_id,
message, kind)`. The farmer page polls `/api/notifications` (4 s) and `/api/booking/<id>`
(2.5 s); both are scoped by `session['user_id']` in the WHERE clause, and a farmer can only
read their own rows (another id → 404). That isolation is what makes the SIH demo work with
two phones showing different states at the same time.

## 7. Localisation design

`static/i18n.strings.js` keeps every string as `[English, Telugu, Hindi]`:

```js
'farmer.notifCall': ['Token #{token} is being called. Please proceed to the procurement counter.',
                     'టోకెన్ #{token} పిలుస్తున్నారు. దయచేసి కొనుగోలు కౌంటర్‌కు వెళ్లండి.',
                     'टोकन #{token} बुलाया जा रहा है। कृपया खरीद काउंटर पर जाएँ।']
```

`static/i18n.js` resolves the active column, applies `data-i18n*` attributes, renders the
`EN | తెలుగు | हिन्दी` switcher, stores the choice in `localStorage('kf_lang')` and fires
`KF.onChange` so dynamic text (token, queue, notification history) re-renders immediately.
Server-side notification text stays English as the fallback while the client renders the
localised version from the notification `kind` + `booking_token`.

Adding a language = one more column plus one entry in `KF_LANGS` (NFR-07).

## 8. Security model

* Session cookie: `HttpOnly`, `SameSite=Lax`, `Secure` when `COOKIE_SECURE=1`.
* `login_required(role)` on every page and API route; wrong role → 403, no session → 401
  (JSON) or a redirect (HTML pages).
* Farmer ownership enforced in SQL (`WHERE user_id = :uid`), never trusted from the client.
* Extra write protection: Origin/Host comparison on POST/PUT/PATCH/DELETE so a foreign site
  cannot drive the API with a farmer's cookie (SameSite=Lax remains the primary defence).
* Login/registration throttling (in-memory; `LOGIN_ATTEMPT_LIMIT`, `REGISTER_ATTEMPT_LIMIT`).
* Uniform JSON error envelope; unhandled exceptions are logged and answered safely.
* `PRAGMA journal_mode=WAL` + `busy_timeout` locally; `pool_pre_ping` for PostgreSQL.
* Secrets only from the environment (`SECRET_KEY`, `DATABASE_URL`, `COOKIE_SECURE`).

## 9. Testing strategy

`tests/test_workflows.py` runs the real Flask app through its test client against a
throwaway SQLite database in the system temp folder — it never touches `procurement.db`:

* registration / login / authorisation matrix;
* slot creation validation (past date, capacity bounds, start < end, unknown centre);
* booking, token, persistence, duplicate-active booking, past-date booking;
* capacity exhaustion plus a 5-thread concurrency race on a capacity-2 slot;
* queue isolation across centres, dates and slots;
* call-farmer targeting (farmer A notified, farmer B untouched);
* the whole status machine including invalid transitions (409) and cancellation paths;
* admin stats, filters, login throttling and cross-origin blocking;
* rendered pages, i18n dictionary and static assets.

Latest run: **118 passed, 0 failed** (`.\venv\Scripts\python.exe tests\test_workflows.py`).

## 10. Deployment

```
Procfile:          web: gunicorn app:app
Environment:       DATABASE_URL (postgresql://...), SECRET_KEY, COOKIE_SECURE=1, FLASK_DEBUG=0
Optional tuning:   LOGIN_ATTEMPT_LIMIT, REGISTER_ATTEMPT_LIMIT, PORT
Health probe:      GET /health -> {"status":"ok","database":"connected"}
Schema bootstrap:  automatic on start (CREATE TABLE/INDEX IF NOT EXISTS + admin seed)
```
The reverse proxy must forward `X-Forwarded-For/Proto/Host` (ProxyFix is already configured).

## 11. Known limits (prototype)

* Notifications are in-app polling based; a fully closed app cannot be woken (Web Push /
  SMS / WhatsApp are Phase 3).
* The mobile number is the farmer identifier; there is no OTP verification yet.
* The admin account is seeded with a demo password — change it before a real pilot.
* Local SQLite suits a single-machine demo; use managed PostgreSQL for several towns.
* `POST /api/reset` (admin-only) clears bookings/notifications/slots for a fresh demo run.
* The service worker only supports browser notifications; the app works without it.
* Slot times are stored as `hh:mm AM/PM` strings, so both UIs sort them by parsed time.

