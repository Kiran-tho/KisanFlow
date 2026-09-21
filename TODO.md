# KisanFlow — Delivery Checklist (tick box)

TIER RULE (tons): HIGH >= 5 · MID 1-5 · LOW < 1. Same quantity = same tier, strict seats.

Last verified run: `.\venv\Scripts\python.exe tests\test_workflows.py` → **134 passed, 0 failed**

---

## 0. Inspection phase

- [x] Repository structure inspected (app.py, templates/, static/, venv, procurement.db)
- [x] Backend identified: single-file Flask app, raw SQL through SQLAlchemy `text()`
- [x] Frontend identified: Jinja templates + `static/style.css` + inline vanilla JS
- [x] DB config identified: `DATABASE_URL` → SQLite local, PostgreSQL production, admin seed
- [x] Auth identified: session cookie + `login_required(role)` + werkzeug hashing
- [x] Existing APIs mapped (auth, farmer, admin, health)
- [x] Existing DB data checked — users/centres/slots/bookings/notifications **preserved**
- [x] Local venv verified: Python 3.14.2, Flask 3.1.3, SQLAlchemy 2.0.54

## Gaps found during inspection (all now closed)

- [x] Multilingual EN/TE/HI (FR-14) — was completely missing → implemented
- [x] Read-then-write capacity check → race window (FR-06 / §31) → single conditional INSERT
- [x] `POST /api/call/<id>` silently completed *another* farmer's Serving booking → fixed
- [x] Cancelled bookings still counted as slot capacity → fixed
- [x] No cancellation endpoint although `Cancelled` existed → added (farmer + admin)
- [x] `/api/stats` lacked Called / Cancelled / slot capacity → added (FR-16)
- [x] Farmer toast printed `Token #undefined` → fixed (localised text + real token)
- [x] Non-atomic `MAX(token)+1` → allocated inside the booking statement
- [x] No past-date validation → fixed (booking + slot creation)
- [x] No status-transition validation → validated state machine
- [x] No CSRF/origin guard, throttling, security headers, JSON 500 handler → added
- [x] `/health` reported the dialect name → now `database: connected|unavailable`
- [x] Docs: no PRD.md / design.md / tests → added

---

## 1. Backend — Flask API (`app.py`)

### Correctness & capacity
- [x] Race-safe booking: in-process write guard (SQLite) + `SELECT … FOR UPDATE` (PostgreSQL)
- [x] Capacity guard inside one conditional `INSERT … SELECT WHERE (SELECT COUNT(*) …) < capacity`
- [x] Cancelled/Completed bookings excluded from slot capacity
- [x] Atomic token generation in the same statement
- [x] Past-date booking rejected (400)
- [x] One active booking per farmer (duplicate taps blocked, 409)

### Queue (FR-11)
- [x] Queue scoped to centre + date + slot only (never global)
- [x] `ahead` = active bookings with a smaller token in the same slot
- [x] `position`, `queue_size`, `now_serving_token` returned to the farmer

### Status machine (§10)
- [x] `VALID_TRANSITIONS` table implemented and enforced
- [x] `POST /api/call/<bid>` → Called + targeted notification, no other-farmer side effect
- [x] `POST /api/serve/<bid>` → Serving + notification
- [x] `POST /api/complete/<bid>` → Completed (idempotent)
- [x] `POST /api/cancel/<bid>` (admin) and `POST /api/my-booking/cancel` (farmer, Waiting only)
- [x] `POST /api/advance` → completes current Serving, then calls next Waiting

### Notifications (FR-13)
- [x] Notification always scoped to the called farmer's `user_id`
- [x] `POST /api/notifications/<id>/read` + mark-all-read
- [x] Notification payload carries `booking_token` for localised rendering
- [x] Other farmers receive nothing (proved by test)

### Admin (FR-16)
- [x] `/api/stats` returns total, waiting, called, serving, completed, cancelled,
      slots_total, slots_available, slots_full
- [x] `/api/bookings` supports `?date=&centre_id=&status=` (defaults unchanged)
- [x] `/api/generate-slots` validates centre, date, capacity 1–200, interval, start < end,
      past dates

### Security / non-functional
- [x] Origin check on POST/PUT/PATCH/DELETE
- [x] Login + registration throttling (429)
- [x] Security headers + `Cache-Control: no-store` on API responses
- [x] JSON error envelope `{success:false,error}` with 400/401/403/404/409/429/500
- [x] Global error handlers (no traceback leaks), no hashes in any response
- [x] `/health` → `{status:"ok",database:"connected",engine:…}` / 503 when down
- [x] Additive-only schema change (`CREATE INDEX IF NOT EXISTS`), existing data untouched
- [x] SQLite WAL + busy timeout pragmas; no secrets or passwords logged

## 2. Frontend — farmer (mobile first)

- [x] `static/i18n.strings.js` + `static/i18n.js`: EN / తెలుగు / हिन्दी, `data-i18n` applier,
      localStorage persistence, `KF.onChange` re-render hook
- [x] Language switcher `EN | తెలుగు | हिन्दी` on index, login, register and farmer pages
- [x] Farmer page keeps every v12 behaviour (booking, ticket, My Turn menu, polling, browser notification)
- [x] `Token #undefined` toast bug fixed; the alert shows the real token in the chosen language
- [x] Notification history with read/unread styling; opening My Turn marks them read
- [x] Cancel-booking action (Waiting only) with a confirmation prompt
- [x] One `api()` fetch wrapper: network / HTTP / bad-JSON / session expiry + loading and disabled buttons
- [x] Slots disabled when full, "N left" label, correct chronological ordering
- [x] Large token, status text (not colour only), touch targets ≥ 44 px, focus-visible rings, aria-live regions

## 3. Frontend — admin

- [x] Dashboard counters: Total, Waiting, Called, Serving, Completed, Cancelled
- [x] Slot capacity summary: available / full / total (from today onwards)
- [x] Queue table with centre, date and status filters
- [x] Status-aware actions: CALL FARMER, START SERVING, MARK COMPLETE + "Next in queue"
- [x] Slot page: remaining capacity, FULL badge, client + server validation feedback
- [x] Loading / empty / error states, no silent failures, duplicate requests guarded

## 4. Tests (actually executed)

- [x] `tests/test_workflows.py` — offline end-to-end suite on a temp SQLite DB
- [x] Register, duplicate, invalid mobile, weak password, logout, wrong password
- [x] Admin login (good + bad credentials)
- [x] Slot creation + validation (past date, capacity 0, end < start, unknown centre, non-admin)
- [x] Farmer sees slots, books, receives token, booking persisted as Waiting
- [x] Full slot refuses the next farmer (409) and reports 0 remaining
- [x] Queue position correct and isolated per centre / date / slot
- [x] Farmer cannot read another booking (404) or admin APIs (403); anonymous → 401
- [x] Admin calls Farmer A → A notified, B untouched, statuses correct
- [x] Called → Serving → Completed; `advance` calls the next waiting farmer
- [x] Invalid transition refused (409); past-date booking refused (400)
- [x] Cross-origin POST blocked (403), same-origin allowed
- [x] Concurrency: 5 threads on a capacity-2 slot ⇒ exactly 2 succeed, unique tokens
- [x] Cancellation frees capacity; re-booking works; re-cancel is a no-op
- [x] Admin stats, date/status/centre filters, invalid filter 400
- [x] Login throttling returns 429
- [x] Rendered pages, i18n dictionary and static assets verified
- [x] Tier quotas: quantity mapping, tier-sum validation, per-tier 409s, 50/30/20 default split
- [x] Tier queue High->Mid->Low + tier filter + tier-ordered admin list + tier-ordered advance
- [x] 5-thread race on a 2-seat High quota → exactly 2 succeed, tokens unique
- [x] Result: **134 passed / 0 failed**

## 5. Docs

- [x] `README.md` rewritten (features, install, DB, admin + farmer usage, API, tests, deploy, env vars, troubleshooting)
- [x] `PRD.md` added with an implementation status per requirement
- [x] `design.md` added (architecture, booking flow, queue, state machine, i18n, security, tests)
- [x] `V13_CHANGES.txt` added (repo version-note convention)
- [x] `DEPLOYMENT_CHECKLIST.txt` updated with the `/health` expectation and migration note
- [x] `.gitignore` hardened (`*.db*`, `.venv/`, test output), `.env.example` extended

## 6. Definition of done

- [x] No existing working feature removed; existing SQLite data preserved
- [x] All automated checks pass
- [x] App starts and serves `/`, `/login`, `/register`, `/admin`, `/health` (smoke tested below)
- [x] Final report delivered (Changes / Files / Tests / Results / Run / Notes)

## 7. Known limits (honest list, not blockers for the demo)

- [ ] Notifications are in-app polling only; a fully closed browser cannot be woken
      (Web Push / SMS / WhatsApp = Phase 3)
- [ ] No OTP verification of the farmer's mobile number
- [ ] Admin UI is English-only (PRD marks admin language as optional)
- [ ] `POST /api/reset` is an admin-only demo reset that clears bookings/slots/notifications
- [ ] Telugu/Hindi strings were authored by the developer and should be reviewed by a native
      speaker before a public pilot
- [ ] Production HTTPS + PostgreSQL must be confirmed on the operator's own cloud account
- [ ] `_v12_backup/` is a reference snapshot only and can be deleted

