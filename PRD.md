# KisanFlow — Product Requirements Document (SIH26032)

Status legend: **DONE** = implemented and covered by tests · **PARTIAL** = works with a documented limit · **OUT** = out of MVP scope.

---

## 1. Overview

KisanFlow is a farmer procurement slot-booking and queue-management web application.
Farmers book a capacity-controlled procurement slot, receive a token, follow their queue
position and get a private notification when the centre calls them. Procurement-centre
staff create slots, watch the live queue and call individual farmers.

Delivered as a mobile-first web app (HTML + CSS + vanilla JS) on a Flask JSON API with
SQLAlchemy (SQLite locally, PostgreSQL in production) — no native app required.

## 2. Problem statement

Long waiting times · uncertain queue position · crowded centres · no visibility of free
slots · manual queue handling · no reliable "your turn now" signal · slot overbooking.

## 3. Goals

Primary: pre-booked slots, no overbooking, unique token, live queue position, admin slot
and queue control, targeted call to exactly one farmer, mobile-first UI, EN/TE/HI, and an
Internet-reachable production deployment.
Secondary: less physical waiting, better arrival visibility for centres, a digital record
of bookings, and a foundation for SMS/WhatsApp/analytics later.

## 4. Users

| Role | Needs |
|---|---|
| Farmer | Register/login, choose centre + date + slot, give crop, get token, track turn, be called. Minimal steps, minimal typing. |
| Admin (centre staff) | Login, create slots with capacity, monitor bookings/queue, call a farmer, track statuses. |

## 5. Roles and permissions (implemented)

| Capability | Farmer | Admin |
|---|---:|---:|
| Register | DONE | n/a |
| Login | DONE | DONE (separate `/admin/login`) |
| View centres/slots | DONE | DONE |
| Book a slot | DONE | Refused (403) |
| View own booking | DONE | Refused (403, farmer-only endpoint) |
| View other farmers' private data | Refused (404/403) | DONE (operational fields only) |
| Queue view | Own position | Whole centre, filterable |
| Create slots / set capacity | Refused (403) | DONE |
| Call farmer | Refused (403) | DONE |
| Notifications | Own only | Operational alerts (queue view) |
| Change language | DONE (EN/TE/HI) | Optional (English UI) |

## 6. Core journeys (implemented)

Farmer: open → register/login → choose centre → choose date → view slots with remaining
capacity → choose slot → choose crop → confirm → token → ticket with queue position →
My Turn / Status (2.5 s polling) → "YOU ARE BEING CALLED" → counter.

Admin: login → create slots + capacity → farmers book → dashboard counters and queue →
CALL FARMER → farmer status `Called` and only that farmer is notified → START SERVING →
MARK COMPLETE (or "Next in queue").

## 7. Functional requirements

| ID | Requirement | Status | Notes |
|---|---|---|---|
| FR-01 | Farmer registration | DONE | name + 10-digit mobile + password; duplicate mobile → 409; password hashed (werkzeug) |
| FR-02 | Farmer login | DONE | mobile number + password; wrong credentials → 401 |
| FR-03 | Admin login | DONE | separate `/admin/login` for `role='admin'` only |
| FR-04 | Procurement centre selection | DONE | `/api/centres`, three centres seeded |
| FR-05 | Slot creation | DONE | `/api/generate-slots`: centre, date, start, end, capacity, interval |
| FR-06 | Slot capacity | DONE | conditional INSERT + row lock; full slot disabled in the UI and 409 on the API |
| FR-07 | Slot booking | DONE | session → slot → date → capacity → one-active-booking → insert → token |
| FR-08 | Token generation | DONE | allocated inside the same booking statement, never collides |
| FR-09 | Farmer booking details | DONE | token, centre, date, time, crop, status, position, farmers ahead |
| FR-10 | My Turn / Status | DONE | Waiting / Called / Serving / Completed / Cancelled + notification history |
| FR-11 | Queue management | DONE | position computed only within centre + date + slot |
| FR-12 | Call farmer | DONE | admin-only, one booking, targeted notification, no side effects |
| FR-13 | Farmer notification | DONE | stored notification + alert, vibration and optional browser notification |
| FR-14 | Multilingual interface | DONE | EN / తెలుగు / हिन्दी switcher on index, login, register, farmer pages |
| FR-15 | Mobile responsiveness | DONE | responsive grid, 44 px touch targets, large token, focus rings |
| FR-16 | Admin dashboard | DONE | counters, slot capacity summary, filters, queue, per-status actions |
| FR-17 | Data persistence | DONE | SQLAlchemy; SQLite locally, PostgreSQL via `DATABASE_URL` |

Additional delivered behaviour: booking cancellation (farmer + admin), past-date
rejection, validated status transitions, login throttling, Origin check, security
headers, `/health` database probe, admin filters, history-aware notifications.

## 8. Non-functional requirements

| ID | Requirement | Status |
|---|---|---|
| NFR-01 | Security (hashing, RBAC, isolation, no secrets in code, HTTPS, secure cookies, validation) | DONE |
| NFR-02 | Availability over the Internet | DONE via cloud deployment (deployment checklist) |
| NFR-03 | Performance | DONE (indexed lookups, 2.5 s polling, single-statement booking) |
| NFR-04 | Scalability | DONE (PostgreSQL-ready, WAL locally) |
| NFR-05 | Usability | DONE (four-step booking, no technical jargon) |
| NFR-06 | Maintainability | DONE (routes/models/UI separated; one API layer) |
| NFR-07 | Localisation | DONE (`[en, te, hi]` rows; a new language is one column) |

## 9. Data model (as implemented)

```
users(id, role, name, phone UNIQUE, username UNIQUE, password_hash, created_at)
centres(id, name, daily_capacity)
slots(id, centre_id, slot_date, start_time, end_time, capacity, UNIQUE(centre_id, slot_date, start_time))
bookings(id, user_id, slot_id, name, phone, crop, token, status, procurement_status,
         payment_status, created_at)
notifications(id, user_id, booking_id, message, kind, is_read, created_at)
```
Indexes: `bookings(user_id)`, `bookings(slot_id, status)`, `notifications(user_id, is_read)`,
`slots(centre_id, slot_date)`. All migrations are additive (`CREATE INDEX IF NOT EXISTS`),
so existing booking data is preserved.

`token` is a positive integer allocated inside the booking statement; the UI renders it as
`#24` and `KISAN-024` is available in a future release if the numeric token is replaced.

## 10. API surface

Auth: `POST /login` (+ `/api/login`), `POST /register` (+ `/api/register`),
`POST /logout` (+ `/api/logout`), `POST /admin/login`, `GET /api/me`.

Farmer: `GET /api/centres`, `GET /api/slots?centre_id=&date=`, `POST /api/book`,
`GET /api/my-booking`, `POST /api/my-booking/cancel`, `GET /api/booking/<id>`,
`GET /api/notifications` (+ `/api/my-notifications`), `POST /api/notifications/read`,
`POST /api/notifications/<id>/read`.

Admin: `POST /api/generate-slots`, `GET /api/bookings?date=&centre_id=&status=`,
`GET /api/stats`, `POST /api/call/<id>`, `POST /api/serve/<id>`, `POST /api/complete/<id>`,
`POST /api/cancel/<id>`, `POST /api/advance`, `POST /api/reset` (demo reset).

System: `GET /health` → `{status:"ok", database:"connected", engine:"sqlite"|"postgresql"}` or
503 when the database is unreachable.

Every error is `{"success": false, "error": "..."}` with 400/401/403/404/409/429/500.

## 11. Security

Implemented: password hashing, session cookies (`HttpOnly`, `SameSite=Lax`, `Secure` in
production), role-based route guards on every protected endpoint, farmer ownership checks
(another farmer's booking → 404), admin-only mutations, parameterised SQL everywhere,
input validation, login/registration throttling, Origin check on writes, security headers,
no tracebacks or hashes in responses, secrets only through environment variables.

Before public deployment: set a strong random `SECRET_KEY`, set `DATABASE_URL` to managed
PostgreSQL, set `COOKIE_SECURE=1`, keep `.env` out of git, use HTTPS, enable database
backups.

## 12. Prototype scope

Farmer/admin authentication · centre + slot management · capacity-controlled booking ·
token · queue tracking · My Turn / Status · targeted in-app notification · EN/TE/HI UI ·
mobile browser support · SQLite locally · PostgreSQL-ready.

## 13. Out of later-MVP features

Native apps, online payments, government identity verification, ERP integration,
predictive analytics, SMS billing, WhatsApp messaging, hardware/IoT.

## 14. Acceptance criteria (verified in `tests/test_workflows.py`)

Farmer registration: register works · duplicate handling works · password is never stored
in plain text — **verified**.
Farmer login: valid login works · invalid rejected · farmer blocked from admin features —
**verified**.
Admin: login works · creates slots · sets capacity · views bookings · calls a farmer —
**verified**.
Booking: available slots visible · slot bookable · token generated · full slot refuses the
next farmer · booking persisted — **verified**.
Queue: token visible · queue status visible · unrelated centres/slots isolated · status
changes reflected on the farmer page — **verified**.
Notification: admin calls exactly one farmer · that farmer sees the notification · other
farmers receive nothing — **verified**.
Multilingual: English / Telugu / Hindi render · selection is remembered in
`localStorage` — **verified for rendering and persistence wiring** (visual check on a real
phone is still recommended).
Mobile: mobile-first markup, responsive grid, 44 px targets — **verified in markup**
(device check recommended).
Production: HTTPS app, PostgreSQL connection, `/health` reporting a healthy database,
multiple concurrent users, farmer data isolated by account — **verified locally; requires
the operator's cloud deployment to confirm HTTPS + PostgreSQL**.

## 15. Demo scenario

1. Admin logs in at `/admin`.
2. Admin creates 09:00–11:00 hourly slots with capacity 2.
3. Farmer A registers on phone 1 and books 09:00.
4. Farmer B registers on phone 2 and books the same slot.
5. Each gets an individual token; B sees "1 farmer ahead".
6. Farmer C tries the same slot → "This slot is full."
7. Admin dashboard shows both bookings and the counters.
8. Admin presses CALL FARMER for A → A shows "YOU ARE BEING CALLED".
9. B stays Waiting and receives nothing from A.
10. Admin presses START SERVING then MARK COMPLETE for A; B stays Waiting.
11. A third phone switches to తెలుగు / हिन्दी while the others stay in English.

## 16. Success metrics for a pilot

Farmers using digital booking · slot fill rate · overbooking attempts prevented · average
waiting time · share of farmers receiving call notifications · completed bookings ·
cancellation rate · language usage.

## 17. Roadmap

Phase 1 (delivered): auth, slots, capacity, tokens, queue, admin dashboard, targeted
in-app notifications, multilingual UI, cancellation, tests.
Phase 2: cloud Flask + PostgreSQL + HTTPS hardening (checklist included).
Phase 3: Web Push, SMS, WhatsApp Business.
Phase 4: analytics (utilisation, waiting time, volume, crop-wise stats).
Phase 5: government integration, verification, payment tracking, queue prediction.

## 18. Product principle

> KisanFlow should make procurement-centre visits predictable for farmers and manageable
> for centre administrators.

Farmer path stays: login → book slot → get token → check my turn → get called → visit
counter. All complexity stays behind the API.

