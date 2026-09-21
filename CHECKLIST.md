# KisanFlow — To-Do Checklist (tick box)

Tick items off as you demo / deploy. `[x]` = done in v13, `[ ]` = your action / future phase.

## 1. Farmer registration & login
- [x] Farmer can register (name + mobile + password, hashed)
- [x] Duplicate mobile number rejected
- [x] Weak password / bad mobile rejected
- [x] Valid farmer can log in, wrong password rejected
- [x] Farmer cannot open admin APIs (403), anonymous blocked (401)
- [x] Logout works
- [ ] Change demo data to real farmer accounts for pilot

## 2. Admin
- [x] Admin can log in (`admin@kisanflow.com` / `Admin@123`)
- [x] Admin can create slots (centre + date + start/end + capacity)
- [x] Past date / zero capacity / end-before-start rejected
- [x] Admin can view bookings with centre/date/status filters
- [x] Admin can CALL / SERVE / COMPLETE / CANCEL a farmer
- [ ] Change demo admin password before any real pilot

## 3. Booking & token
- [x] Farmer sees centres and slots for chosen date
- [x] Farmer can book an available slot
- [x] Token generated (unique per slot, e.g. Token #24)
- [x] Full slot shows FULL and rejects booking (409)
- [x] One active booking per farmer (double-tap safe)
- [x] Past-date booking rejected
- [x] Booking persisted in database

## 4. Queue / My Turn
- [x] Farmer sees token, centre, date, time, crop, status
- [x] Farmer sees queue position + farmers ahead + queue size
- [x] Queue scoped to centre + date + slot (no mixing)
- [x] Status flow Waiting → Called → Serving → Completed (+ Cancelled) enforced
- [x] Farmer can cancel own Waiting booking (frees capacity)

## 5. Call + notification
- [x] Admin CALL targets only that farmer
- [x] Called farmer sees YOU ARE BEING CALLED + vibration/sound page
- [x] Other farmers receive nothing (tested)
- [x] Notification history with read/unread
- [ ] SMS / WhatsApp / Web Push (Phase 3 — currently in-app polling only)

## 6. Multilingual
- [x] English works
- [x] Telugu (తెలుగు) works
- [x] Hindi (हिन्दी) works
- [x] Language choice remembered (localStorage `kf_lang`)
- [ ] Get Telugu/Hindi strings reviewed by native speaker before pilot

## 7. Mobile
- [x] Farmer UI works on phone browsers
- [x] Big touch targets (≥44px), large token, status badges
- [x] Loading / empty / error states, no silent fails
- [ ] Test on your own phones over LAN/Wi-Fi before SIH demo

## 8. Production deploy
- [x] `/health` reports `status + database: connected`
- [x] SQLite local, PostgreSQL via `DATABASE_URL`
- [x] `requirements.txt` + `gunicorn app:app` + `.env.example` ready
- [ ] Push to Git (never commit `.env` / `*.db`)
- [ ] Create managed PostgreSQL, set `DATABASE_URL`, `SECRET_KEY`, `COOKIE_SECURE=1`
- [ ] Open public `/health` → must say connected
- [ ] Open same public URL on all farmer phones + admin laptop

## 9. SIH demo rehearsal (do this order)
- [ ] Admin logs in on laptop
- [ ] Admin creates slot, capacity 2–3
- [ ] Farmer A on Phone 1 registers + books → Token A
- [ ] Farmer B on Phone 2 registers + books → Token B
- [ ] Admin dashboard shows both bookings
- [ ] Admin calls Farmer A → A sees YOU ARE BEING CALLED, B stays Waiting
- [ ] Switch language on one phone (EN/TE/HI)
- [ ] Show `/health` on projector (optional, proves prod-ready)

## 10. Known limits (not demo blockers)
- [ ] In-app notification only (closed browser can't be woken)
- [ ] No OTP for mobile numbers yet
- [ ] Admin UI English-only (PRD allows this)
- [ ] `_v12_backup/` can be deleted anytime

---
Last verified: `.\venv\Scripts\python.exe tests\test_workflows.py` → **118 passed, 0 failed**.
