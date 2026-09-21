/* KisanFlow i18n engine (PRD FR-14, NFR-07).

   Load order in every farmer-facing page:
     <script src="/static/i18n.strings.js"></script>   (dictionary)
     <script src="/static/i18n.js"></script>           (this engine)

   Markup is translated declaratively:
     <span data-i18n="farmer.title">Book your procurement visit</span>
     <input data-i18n-placeholder="login.passwordPh">
     <button data-i18n-aria="common.language">
   The English text already in the HTML is used as the fallback, so a missing
   key can never blank out the interface.

   The selected language is stored in localStorage (kf_lang) and survives a
   reload or a sign-out, and KF.onChange(fn) lets a page re-render its own
   dynamic text (tokens, queue messages) after a switch.
*/
(function (global) {
  'use strict';

  var STRINGS = global.KF_STRINGS || {};
  var LANGS = global.KF_LANGS || ['en', 'te', 'hi'];
  var ORDER = global.KF_ORDER || { en: 0, te: 1, hi: 2 };
  var LABELS = global.KF_LABELS || { en: 'EN', te: 'తెలుగు', hi: 'हिन्दी' };
  var STORE_KEY = global.KF_STORE_KEY || 'kf_lang';
  var listeners = [];
  var current = 'en';

  function each(list, fn) { for (var i = 0; i < list.length; i++) fn(list[i], i); }

  function t(key, fallback) {
    var row = STRINGS[key];
    if (!row) return fallback === undefined ? key : fallback;
    var value = row[ORDER[current]];
    if (value === undefined || value === null || value === '') value = row[0];
    if (value === undefined || value === null) value = fallback === undefined ? key : fallback;
    return value;
  }

  function storedLang() {
    try { return global.localStorage.getItem(STORE_KEY); } catch (e) { return null; }
  }

  function detect() {
    var saved = storedLang();
    if (saved && ORDER[saved] !== undefined) return saved;
    var nav = ((global.navigator && (global.navigator.language || global.navigator.userLanguage)) || '').toLowerCase();
    if (nav.indexOf('te') === 0) return 'te';
    if (nav.indexOf('hi') === 0) return 'hi';
    return 'en';
  }

  function apply(root) {
    var scope = root || global.document;
    each(scope.querySelectorAll('[data-i18n]'), function (el) {
      el.textContent = t(el.getAttribute('data-i18n'), el.textContent);
    });
    each(scope.querySelectorAll('[data-i18n-placeholder]'), function (el) {
      el.setAttribute('placeholder', t(el.getAttribute('data-i18n-placeholder'), el.getAttribute('placeholder') || ''));
    });
    each(scope.querySelectorAll('[data-i18n-title]'), function (el) {
      el.setAttribute('title', t(el.getAttribute('data-i18n-title'), el.getAttribute('title') || ''));
    });
    each(scope.querySelectorAll('[data-i18n-aria]'), function (el) {
      el.setAttribute('aria-label', t(el.getAttribute('data-i18n-aria'), el.getAttribute('aria-label') || ''));
    });
    global.document.documentElement.setAttribute('lang', current);
  }

  function renderSwitcher() {
    var box = global.document.getElementById('langSwitcher');
    if (!box) return;
    box.innerHTML = '';
    box.setAttribute('role', 'group');
    box.setAttribute('aria-label', t('common.language'));
    LANGS.forEach(function (code) {
      var btn = global.document.createElement('button');
      btn.type = 'button';
      btn.className = 'langBtn' + (code === current ? ' active' : '');
      btn.textContent = LABELS[code] || code.toUpperCase();
      btn.setAttribute('data-lang', code);
      btn.setAttribute('aria-pressed', code === current ? 'true' : 'false');
      btn.addEventListener('click', function () { setLanguage(code); });
      box.appendChild(btn);
    });
  }

  function setLanguage(code) {
    if (ORDER[code] === undefined) return;
    current = code;
    try { global.localStorage.setItem(STORE_KEY, code); } catch (e) { /* private mode */ }
    apply();
    renderSwitcher();
    each(listeners, function (fn) { try { fn(code); } catch (e) { /* keep the UI alive */ } });
  }

  function onChange(fn) { if (typeof fn === 'function') listeners.push(fn); }

  /* Localised text for a stored notification. The server keeps English text as
     the source of truth, but the farmer reads it in the chosen language. */
  function notificationText(note) {
    var token = (note && note.booking_token !== null && note.booking_token !== undefined) ? note.booking_token : '—';
    var kind = note ? note.kind : '';
    var message = (note && note.message) || '';
    var key = null;
    if (kind === 'call') key = 'farmer.notifCall';
    else if (kind === 'serve') key = 'farmer.notifServe';
    else if (/cancel/i.test(message)) key = 'farmer.notifCancel';
    else if (/complet|procured/i.test(message)) key = 'farmer.notifComplete';
    return key ? t(key).replace('{token}', token) : message;
  }

  function escape(text) {
    return String(text === null || text === undefined ? '' : text)
      .replace(/[&<>"']/g, function (c) {
        return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
      });
  }

  var api = {
    t: t,
    escape: escape,
    apply: apply,
    refresh: apply,
    setLanguage: setLanguage,
    getLanguage: function () { return current; },
    renderSwitcher: renderSwitcher,
    onChange: onChange,
    notificationText: notificationText
  };

  function init() { current = detect(); apply(); renderSwitcher(); }
  api.init = init;
  global.KF = api;

  if (global.document.readyState === 'loading') {
    global.document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})(window);
