"""KisanFlow end-to-end workflow tests (offline, temporary SQLite database).

Run:
    .\\venv\\Scripts\\python.exe tests\\test_workflows.py

Covers the PRD section 29 checklist: registration/login, slot creation, capacity
enforcement, tokens, queue isolation, targeted call notification, status machine,
authorisation, cancellation, origin guard, throttling, filters and concurrent
overbooking. Nothing here touches the real procurement.db.
"""
import os
import shutil
import sys
import tempfile
import threading
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

TMP_DIR = tempfile.mkdtemp(prefix='kisanflow_test_')
os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.join(TMP_DIR, 'test.db').replace('\\', '/')
os.environ['SECRET_KEY'] = 'test-secret'
os.environ['COOKIE_SECURE'] = '0'
os.environ['LOGIN_ATTEMPT_LIMIT'] = '500'
os.environ['REGISTER_ATTEMPT_LIMIT'] = '500'

import app as kf  # noqa: E402  (imported after the test database is configured)

PASSED, FAILED = [], []
S = {}            # shared state between the test sections


def check(name, ok, detail=''):
    if ok:
        PASSED.append(name)
        print('PASS  ' + name)
    else:
        FAILED.append(name)
        print('FAIL  ' + name + (('  -> ' + str(detail)) if detail else ''))


def section(title):
    print('\n-- ' + title + ' ' + '-' * max(0, 58 - len(title)))


def client():
    return kf.app.test_client()


def admin_client():
    c = client()
    r = c.post('/admin/login', json={'identifier': 'admin@kisanflow.com', 'password': 'Admin@123'})
    check('admin login succeeds', r.status_code == 200, r.status_code)
    return c


def farmer_client(name, phone, password='Farmer@123'):
    """Register a farmer (registration logs them in) and return the session."""
    c = client()
    r = c.post('/register', json={'name': name, 'phone': phone, 'password': password})
    check('register ' + name, r.status_code == 201, r.status_code)
    return c


def future(days=5):
    return (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d')


def past(days=1):
    return (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')


def make_slot(centre_id, slot_date, start='09:00 AM', end='10:00 AM', capacity=2):
    """Insert a slot directly so capacity assertions are exact and isolated."""
    with kf.engine.begin() as c:
        new_id = c.execute(kf.text('''INSERT INTO slots(centre_id,slot_date,start_time,end_time,capacity)
            VALUES(:cid,:d,:s,:e,:cap) RETURNING id'''),
            {'cid': centre_id, 'd': slot_date, 's': start, 'e': end, 'cap': capacity}).scalar_one()
    return int(new_id)


def active_in_slot(slot_id):
    with kf.engine.connect() as c:
        return int(c.execute(kf.text("SELECT COUNT(*) FROM bookings WHERE slot_id=:sid AND status IN ('Waiting','Called','Serving')"),
                             {'sid': slot_id}).scalar())


def test_health_pages_and_auth():
    section('health, pages, anonymous access')
    r = client().get('/health')
    body = r.get_json() or {}
    check('/health reports a connected database',
          r.status_code == 200 and body.get('status') == 'ok' and body.get('database') == 'connected', body)
    for path in ('/', '/login', '/register', '/admin'):
        r = client().get(path)
        check('GET ' + path + ' renders', r.status_code == 200, r.status_code)
    check('anonymous /api/my-booking -> 401', client().get('/api/my-booking').status_code == 401)
    check('anonymous /api/bookings -> 401', client().get('/api/bookings').status_code == 401)
    check('anonymous /dashboard redirects to /admin', client().get('/dashboard').status_code == 302)
    r = client().get('/api/does-not-exist')
    check('unknown API path returns JSON 404', r.status_code == 404 and (r.get_json() or {}).get('error'), r.status_code)
    r = client().get('/health')
    check('security header X-Content-Type-Options present', r.headers.get('X-Content-Type-Options') == 'nosniff', dict(r.headers))

    section('registration and login validation')
    farmer_a = farmer_client('Queue Farmer A', '9000000001')
    S['farmer_a'] = farmer_a
    check('duplicate mobile rejected (409)',
          client().post('/register', json={'name': 'Dup', 'phone': '9000000001', 'password': 'Farmer@123'}).status_code == 409)
    check('invalid mobile rejected (400)',
          client().post('/register', json={'name': 'Bad', 'phone': '12345', 'password': 'Farmer@123'}).status_code == 400)
    check('weak password rejected (400)',
          client().post('/register', json={'name': 'Weak', 'phone': '9000000002', 'password': '123'}).status_code == 400)
    anon = client()
    check('wrong password rejected (401)',
          anon.post('/login', json={'identifier': '9000000001', 'password': 'nope'}).status_code == 401)
    r = anon.post('/login', json={'identifier': '9000000001', 'password': 'Farmer@123'})
    check('farmer login works', r.status_code == 200 and (r.get_json() or {}).get('role') == 'farmer', r.status_code)
    r = anon.get('/api/me')
    me = r.get_json() or {}
    check('/api/me never returns the password hash',
          r.status_code == 200 and 'password_hash' not in me and me.get('role') == 'farmer', me)
    check('/api/register alias works',
          client().post('/api/register', json={'name': 'Alias Farmer', 'phone': '9000000003', 'password': 'Farmer@123'}).status_code == 201)
    check('/api/login alias works',
          client().post('/api/login', json={'identifier': '9000000003', 'password': 'Farmer@123'}).status_code == 200)
    check('/api/logout alias works', client().post('/api/logout').status_code == 200)

    section('slot creation and validation')
    S['centre'] = kf.rows('SELECT id,name FROM centres ORDER BY id LIMIT 1')[0]
    S['second_centre'] = kf.rows('SELECT id,name FROM centres ORDER BY id')[1]
    centre = S['centre']
    admin = admin_client()
    S['admin'] = admin
    day5 = future(5)
    S['day5'] = day5
    payload = {'centre_id': centre['id'], 'date': day5, 'capacity': 3, 'start': '09:00', 'end': '11:00', 'interval': 60}
    r = admin.post('/api/generate-slots', json=payload)
    check('admin creates two hourly slots', r.status_code == 200 and (r.get_json() or {}).get('created') == 2, r.get_json())
    r = admin.post('/api/generate-slots', json=payload)
    check('re-running slot creation does not duplicate', (r.get_json() or {}).get('created') == 0, r.get_json())
    check('past date slot creation rejected (400)',
          admin.post('/api/generate-slots', json=dict(payload, date=past(2))).status_code == 400)
    check('capacity 0 rejected (400)', admin.post('/api/generate-slots', json=dict(payload, capacity=0)).status_code == 400)
    check('end before start rejected (400)', admin.post('/api/generate-slots', json=dict(payload, start='11:00', end='09:00')).status_code == 400)
    check('unknown centre rejected (404)', admin.post('/api/generate-slots', json=dict(payload, centre_id=99999)).status_code == 404)
    check('non-admin cannot create slots (403)', farmer_a.post('/api/generate-slots', json=payload).status_code == 403)
    r = farmer_a.get('/api/slots?centre_id=%s&date=%s' % (centre['id'], day5))
    slots = r.get_json() or []
    check('farmer sees slots with remaining capacity',
          r.status_code == 200 and len(slots) == 2 and slots[0]['remaining'] == 3 and slots[0]['booked'] == 0, slots)
    check('bad slot query rejected (400)', farmer_a.get('/api/slots?centre_id=abc&date=' + day5).status_code == 400)


def test_booking_capacity_and_queue():
    section('booking, token, capacity, queue isolation')
    centre, second = S['centre'], S['second_centre']
    day6 = future(6)
    S['day6'] = day6
    slot_cap2 = make_slot(centre['id'], day6, '09:00 AM', '10:00 AM', capacity=2)
    S['slot_cap2'] = slot_cap2
    farmer_a = S['farmer_a']

    r = farmer_a.post('/api/book', json={'crop': 'Rice', 'slot_id': slot_cap2})
    body = r.get_json() or {}
    S['booking_a'], S['token_a'] = body.get('booking_id'), body.get('token')
    check('farmer A books the slot and receives a token',
          r.status_code == 201 and body.get('token', 0) >= 1 and body.get('ahead') == 0 and body.get('position') == 1, body)
    with kf.engine.connect() as c:
        stored = c.execute(kf.text('SELECT id,token,status,crop,user_id FROM bookings WHERE id=:id'), {'id': S['booking_a']}).mappings().first()
    check('booking is persisted with Waiting status',
          stored is not None and stored['status'] == 'Waiting' and stored['crop'] == 'Rice' and stored['user_id'], dict(stored) if stored else None)
    check('duplicate active booking blocked (409)',
          farmer_a.post('/api/book', json={'crop': 'Rice', 'slot_id': slot_cap2}).status_code == 409)
    check('booking without a crop rejected (400)', farmer_a.post('/api/book', json={'slot_id': slot_cap2}).status_code == 400)
    check('booking an unknown slot rejected (404)',
          farmer_a.post('/api/book', json={'crop': 'Rice', 'slot_id': 999999}).status_code == 404)

    farmer_b = farmer_client('Queue Farmer B', '9000000011')
    r = farmer_b.post('/api/book', json={'crop': 'Maize', 'slot_id': slot_cap2})
    body = r.get_json() or {}
    S['farmer_b'], S['booking_b'], S['token_b'] = farmer_b, body.get('booking_id'), body.get('token')
    check('farmer B gets the next token and sees one farmer ahead',
          r.status_code == 201 and body.get('token') > S['token_a'] and body.get('ahead') == 1, body)

    farmer_c = farmer_client('Queue Farmer C', '9000000012')
    S['farmer_c'] = farmer_c
    check('full slot rejects the third farmer (409)',
          farmer_c.post('/api/book', json={'crop': 'Cotton', 'slot_id': slot_cap2}).status_code == 409)
    slots = (farmer_a.get('/api/slots?centre_id=%s&date=%s' % (centre['id'], day6)).get_json()) or []
    check('full slot reports zero remaining capacity',
          slots and slots[0]['remaining'] == 0 and slots[0]['booked'] == 2, slots)

    other_slot = make_slot(second['id'], day6, '09:00 AM', '10:00 AM', capacity=2)
    r = farmer_c.post('/api/book', json={'crop': 'Cotton', 'slot_id': other_slot})
    body = r.get_json() or {}
    S['booking_c'] = body.get('booking_id')
    check('another centre can still be booked', r.status_code == 201, body)
    check('queue isolation: other centre booking is not counted ahead of mine', body.get('ahead') == 0, body)

    mine = farmer_a.get('/api/my-booking').get_json() or {}
    check('farmer sees only their own booking plus queue position',
          mine.get('token') == S['token_a'] and mine.get('ahead') == 0 and mine.get('position') == 1 and mine.get('centre'), mine)
    mine_b = farmer_b.get('/api/my-booking').get_json() or {}
    check('farmer B sees exactly one farmer ahead', mine_b.get('ahead') == 1 and mine_b.get('position') == 2 and mine_b.get('queue_size') == 2, mine_b)
    mine_c = farmer_c.get('/api/my-booking').get_json() or {}
    check('farmer C is first in the other centre queue', mine_c.get('ahead') == 0 and mine_c.get('queue_size') == 1, mine_c)
    check("farmer cannot open another farmer's booking (404)",
          farmer_a.get('/api/booking/%s' % S['booking_b']).status_code == 404)
    r = farmer_b.get('/api/booking/%s' % S['booking_b'])
    check('farmer can open their own booking', r.status_code == 200 and (r.get_json() or {}).get('token') == S['token_b'], r.status_code)


def test_call_notification_and_status_machine():
    section('call farmer, targeted notification, status machine')
    admin, farmer_a, farmer_b = S['admin'], S['farmer_a'], S['farmer_b']

    r = admin.post('/api/call/%s' % S['booking_a'])
    check('admin can call farmer A', r.status_code == 200 and (r.get_json() or {}).get('status') == 'Called', r.get_json())
    a_state = farmer_a.get('/api/booking/%s' % S['booking_a']).get_json() or {}
    check('farmer A status becomes Called with nobody ahead',
          a_state.get('status') == 'Called' and a_state.get('ahead') == 0, a_state)
    notes_a = farmer_a.get('/api/notifications').get_json() or []
    check('farmer A receives the call notification',
          len(notes_a) == 1 and notes_a[0]['kind'] == 'call' and notes_a[0]['booking_token'] == S['token_a'] and notes_a[0]['is_read'] == 0, notes_a)
    notes_b = farmer_b.get('/api/notifications').get_json() or []
    check('farmer B never receives farmer A notification', notes_b == [], notes_b)
    check('farmer B is still Waiting', (farmer_b.get('/api/my-booking').get_json() or {}).get('status') == 'Waiting')
    r = admin.post('/api/call/%s' % S['booking_a'])
    notes_a = farmer_a.get('/api/notifications').get_json() or []
    check('calling an already-called farmer stays idempotent (no notification spam)',
          r.status_code == 200 and len(notes_a) == 1, (r.status_code, len(notes_a)))
    check('farmer can mark their own notification read',
          farmer_a.post('/api/notifications/%s/read' % notes_a[0]['id']).status_code == 200)
    check("a farmer cannot mark someone else's notification read (404)",
          farmer_a.post('/api/notifications/999999/read').status_code == 404)

    check('CALLED -> SERVING works', admin.post('/api/serve/%s' % S['booking_a']).status_code == 200)
    check('SERVING -> COMPLETED works', admin.post('/api/complete/%s' % S['booking_a']).status_code == 200)
    check('COMPLETED -> CALLED is refused (409)', admin.post('/api/call/%s' % S['booking_a']).status_code == 409)
    a_state = farmer_a.get('/api/booking/%s' % S['booking_a']).get_json() or {}
    check('completed booking has nobody ahead', a_state.get('status') == 'Completed' and a_state.get('ahead') == 0, a_state)

    r = admin.post('/api/advance')
    body = r.get_json() or {}
    check('advance calls the next waiting farmer', r.status_code == 200 and body.get('called') == S['booking_b'], body)
    check('farmer B is now Called', (farmer_b.get('/api/booking/%s' % S['booking_b']).get_json() or {}).get('status') == 'Called')
    notes_b = farmer_b.get('/api/notifications').get_json() or []
    check('farmer B receives their own call notification',
          len(notes_b) == 1 and notes_b[0]['booking_token'] == S['token_b'], notes_b)
    check('CALLED -> SERVING -> CANCELLED works for a no-show',
          admin.post('/api/serve/%s' % S['booking_b']).status_code == 200
          and admin.post('/api/cancel/%s' % S['booking_b']).status_code == 200)
    before = len(farmer_b.get('/api/notifications').get_json() or [])
    r = admin.post('/api/cancel/%s' % S['booking_b'])
    after = len(farmer_b.get('/api/notifications').get_json() or [])
    check('re-cancelling is a safe no-op that does not spam notifications',
          r.status_code == 200 and after == before
          and (farmer_b.get('/api/my-booking').get_json() or {}).get('status') == 'Cancelled', (r.status_code, before, after))


def test_cancellation_authorisation_and_past_dates():
    section('cancellation, freed capacity, authorisation')
    admin, farmer_a, centre = S['admin'], S['farmer_a'], S['centre']

    farmer_d = farmer_client('Queue Farmer D', '9000000021')
    r = farmer_d.post('/api/book', json={'crop': 'Wheat', 'slot_id': S['slot_cap2']})
    check('finished/cancelled bookings free the slot again', r.status_code == 201, r.get_json())
    r = farmer_d.post('/api/my-booking/cancel')
    check('farmer can cancel their own waiting booking',
          r.status_code == 200 and (r.get_json() or {}).get('status') == 'Cancelled', r.get_json())
    check('cancelling twice is refused (409)', farmer_d.post('/api/my-booking/cancel').status_code == 409)
    r = farmer_d.post('/api/book', json={'crop': 'Wheat', 'slot_id': S['slot_cap2']})
    check('a cancelled farmer can book a new slot', r.status_code == 201, r.get_json())
    check('re-booked farmer is Waiting again', (farmer_d.get('/api/my-booking').get_json() or {}).get('status') == 'Waiting')

    check('farmer cannot read the admin booking list (403)', farmer_a.get('/api/bookings').status_code == 403)
    check('farmer cannot read admin stats (403)', farmer_a.get('/api/stats').status_code == 403)
    check('farmer cannot call another farmer (403)', farmer_a.post('/api/call/%s' % S['booking_b']).status_code == 403)
    check('farmer cannot cancel another farmer booking (403)', farmer_a.post('/api/cancel/%s' % S['booking_b']).status_code == 403)
    check('admin cannot use farmer-only endpoints (403)', admin.get('/api/my-booking').status_code == 403)
    check('farmer is redirected away from the admin dashboard', farmer_a.get('/dashboard').status_code == 302)
    check('farmer can open the farmer page', farmer_a.get('/farmer').status_code == 200)

    past_slot = make_slot(centre['id'], past(1), '09:00 AM', '10:00 AM', capacity=2)
    farmer_e = farmer_client('Queue Farmer E', '9000000022')
    r = farmer_e.post('/api/book', json={'crop': 'Rice', 'slot_id': past_slot})
    check('booking a past date is rejected (400)', r.status_code == 400, r.status_code)


def test_security_and_concurrency():
    section('origin guard, session, concurrent booking')
    centre = S['centre']
    farmer_f = farmer_client('Queue Farmer F', '9000000031')
    slot_origin = make_slot(centre['id'], future(9), '10:00 AM', '11:00 AM', capacity=1)
    r = farmer_f.post('/api/book', json={'crop': 'Rice', 'slot_id': slot_origin}, headers={'Origin': 'https://evil.example'})
    check('cross-origin booking is blocked (403)', r.status_code == 403, r.status_code)
    r = farmer_f.post('/api/book', json={'crop': 'Rice', 'slot_id': slot_origin}, headers={'Origin': 'http://localhost'})
    check('same-origin booking is allowed', r.status_code == 201, (r.status_code, r.get_json()))
    check('logout ends the session',
          farmer_f.post('/logout').status_code == 200 and farmer_f.get('/api/my-booking').status_code == 401)

    concurrency_slot = make_slot(centre['id'], future(10), '09:00 AM', '10:00 AM', capacity=2)
    phones = ['9000000041', '9000000042', '9000000043', '9000000044', '9000000045']
    for i, phone in enumerate(phones):
        farmer_client('Concurrent Farmer %d' % i, phone)
    results, lock = {}, threading.Lock()

    def attempt(phone):
        c = client()
        c.post('/login', json={'identifier': phone, 'password': 'Farmer@123'})
        r = c.post('/api/book', json={'crop': 'Rice', 'slot_id': concurrency_slot})
        with lock:
            results[phone] = (r.status_code, (r.get_json() or {}).get('token'))

    threads = [threading.Thread(target=attempt, args=(p,)) for p in phones]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    winners = [p for p, (code, _) in results.items() if code == 201]
    tokens = [tok for code, tok in results.values() if code == 201]
    check('5 concurrent farmers on a capacity-2 slot -> exactly 2 succeed', len(winners) == 2, results)
    check('the losing threads receive a conflict (409)',
          all(code == 409 for code, _ in results.values() if code != 201), results)
    check('concurrent tokens are unique', len(set(tokens)) == len(tokens), tokens)
    check('database holds exactly the capacity (no overbooking)', active_in_slot(concurrency_slot) == 2, active_in_slot(concurrency_slot))


def test_admin_stats_filters_and_throttling():
    section('admin stats, filters, login throttling')
    admin, farmer_a = S['admin'], S['farmer_a']
    r = admin.get('/api/stats')
    stats = r.get_json() or {}
    needed = {'total', 'waiting', 'called', 'serving', 'completed', 'cancelled', 'slots_total', 'slots_available', 'slots_full'}
    check('stats expose every dashboard counter',
          r.status_code == 200 and needed.issubset(set(stats)) and stats['completed'] >= 1 and stats['cancelled'] >= 2, stats)
    check('slot capacity summary adds up',
          stats.get('slots_total', 0) >= 1 and stats.get('slots_available', 0) + stats.get('slots_full', 0) == stats.get('slots_total', -1), stats)

    rows = admin.get('/api/bookings').get_json() or []
    check('admin sees the queue list', len(rows) >= 5, len(rows))
    rows = admin.get('/api/bookings?date=' + S['day6']).get_json() or []
    check('date filter works', bool(rows) and all(x['slot_date'] == S['day6'] for x in rows), len(rows))
    rows = admin.get('/api/bookings?status=Cancelled').get_json() or []
    check('status filter works', bool(rows) and all(x['status'] == 'Cancelled' for x in rows), len(rows))
    rows = admin.get('/api/bookings?centre_id=%s' % S['second_centre']['id']).get_json() or []
    check('centre filter works', bool(rows) and all(x['centre'] == S['second_centre']['name'] for x in rows), len(rows))
    check('invalid status filter rejected (400)', admin.get('/api/bookings?status=Nonsense').status_code == 400)
    check('queue rows never expose password hashes', all('password_hash' not in x for x in rows), rows[:1])
    check('farmers still cannot read the queue (403)', farmer_a.get('/api/bookings').status_code == 403)

    original, kf.LOGIN_ATTEMPT_LIMIT = kf.LOGIN_ATTEMPT_LIMIT, 3
    kf._attempts.clear()
    codes = [client().post('/login', json={'identifier': '9000000001', 'password': 'bad'}).status_code for _ in range(4)]
    check('repeated failed logins are throttled (429)', codes == [401, 401, 401, 429], codes)
    kf.LOGIN_ATTEMPT_LIMIT = original
    kf._attempts.clear()


def test_rendered_pages_and_i18n_assets():
    section('rendered pages, i18n assets, mobile markup')
    farmer, admin = S['farmer_a'], S['admin']

    page = farmer.get('/farmer').get_data(as_text=True)
    check('farmer page renders the language switcher', 'id="langSwitcher"' in page)
    check('farmer page loads both i18n files', '/static/i18n.strings.js' in page and '/static/i18n.js' in page)
    check('farmer page keeps token, queue, My Turn, notification and cancel elements',
          all(x in page for x in ('id="token"', 'id="queueText"', 'id="menuStatus"', 'id="turnToast"',
                                  'id="notifications"', 'id="cancelBtn"', 'id="slots"')))
    check('farmer page uses translation keys instead of hard-coded text', 'data-i18n="farmer.book"' in page)
    check('no implicit DOM globals are used in the farmer script', 'name.value' not in page and 'centre.value' in page)

    login_page = client().get('/login').get_data(as_text=True)
    check('login page is translatable', 'data-i18n="login.title"' in login_page and 'id="langSwitcher"' in login_page)
    register_page = client().get('/register').get_data(as_text=True)
    check('register page is translatable', 'data-i18n="register.title"' in register_page)
    home_page = client().get('/').get_data(as_text=True)
    check('home page is translatable', 'data-i18n="home.title1"' in home_page)

    dash = admin.get('/dashboard').get_data(as_text=True)
    check('dashboard renders all counters, filters and the call action',
          all(x in dash for x in ('id="total"', 'id="waiting"', 'id="called"', 'id="serving"',
                                  'id="completed"', 'id="cancelled"', 'id="slotSummary"', 'CALL FARMER')))
    admin_page = admin.get('/admin').get_data(as_text=True)
    check('slot page renders the slot summary and generator',
          'id="slotRows"' in admin_page and 'Generate slots' in admin_page)

    css = client().get('/static/style.css')
    check('stylesheet still serves and contains the new components',
          css.status_code == 200 and b'.langBtn' in css.data and b'.pill-called' in css.data)
    for asset in ('/static/i18n.js', '/static/i18n.strings.js', '/static/sw.js'):
        check('static asset ' + asset + ' serves', client().get(asset).status_code == 200)
    strings = client().get('/static/i18n.strings.js').get_data(as_text=True)
    check('dictionary carries English, Telugu and Hindi text',
          'లాగిన్' in strings and 'लॉगिन' in strings and 'Login' in strings)
    check('dictionary covers the farmer booking, queue and call strings',
          all(k in strings for k in ("'farmer.book'", "'farmer.myTurn'", "'farmer.notifCall'", "'err.network'")))


def main():
    for test in (test_health_pages_and_auth, test_booking_capacity_and_queue,
                 test_call_notification_and_status_machine, test_cancellation_authorisation_and_past_dates,
                 test_security_and_concurrency, test_admin_stats_filters_and_throttling,
                 test_rendered_pages_and_i18n_assets):
        test()
    section('results')
    print('passed: %d   failed: %d' % (len(PASSED), len(FAILED)))
    for name in FAILED:
        print('  FAILED: ' + name)
    shutil.rmtree(TMP_DIR, ignore_errors=True)
    return 1 if FAILED else 0


if __name__ == '__main__':
    sys.exit(main())
