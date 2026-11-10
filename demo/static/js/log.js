/* SDK log ("fiş rulosu"): renders the server's masked request log and keeps it live by polling. */
(function () {
  'use strict';

  var root = document.querySelector('[data-rulo]');
  if (!root) return;

  var list = root.querySelector('[data-rulo-liste]');
  var scroller = root.querySelector('[data-rulo-govde]');
  var emptyText = root.querySelector('[data-rulo-bos]');
  var newButton = root.querySelector('[data-rulo-yeni]');
  var live = root.querySelector('[data-rulo-duyuru]');
  var counter = root.querySelector('[data-rulo-sayac]');
  var counterShort = root.querySelector('[data-rulo-sayi]');
  var lastLine = root.querySelector('[data-rulo-son]');
  var toggle = root.querySelector('[data-rulo-ac]');
  var toggleText = root.querySelector('[data-rulo-ac-metin]');
  var clearButton = root.querySelector('[data-rulo-temizle]');
  var title = document.getElementById('rulo-baslik');

  var SEEN_KEY = 'mpdemo.sonGorulen';
  var OPEN_KEY = 'mpdemo.ruloAcik';
  var POLL_MS = 1500;
  var narrow = window.matchMedia('(max-width: 899px)');
  var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

  var boot = JSON.parse(document.getElementById('sdk-log-data').textContent);
  var state = {
    generation: boot.generation,
    lastSeq: boot.lastSeq,
    count: boot.count,
    cleared: boot.cleared,
    unseen: 0,
    arrivals: [],
    busy: false,
    again: false
  };

  /* ------------------------------------------------------------ small DOM helpers */

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  var SVG_NS = 'http://www.w3.org/2000/svg';
  function icon(pathData, className) {
    var svg = document.createElementNS(SVG_NS, 'svg');
    svg.setAttribute('viewBox', '0 0 16 16');
    svg.setAttribute('width', '16');
    svg.setAttribute('height', '16');
    svg.setAttribute('fill', 'none');
    svg.setAttribute('stroke', 'currentColor');
    svg.setAttribute('stroke-width', '1.75');
    svg.setAttribute('stroke-linecap', 'round');
    svg.setAttribute('stroke-linejoin', 'round');
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('focusable', 'false');
    if (className) svg.setAttribute('class', className);
    pathData.forEach(function (d) {
      var path = document.createElementNS(SVG_NS, 'path');
      path.setAttribute('d', d);
      svg.appendChild(path);
    });
    return svg;
  }
  var CHEVRON = ['M4 6l4 4 4-4'];
  var COPY = ['M5.5 5.5V3.25c0-.41.34-.75.75-.75h6.5c.41 0 .75.34.75.75v6.5c0 .41-.34.75-.75.75H10.5',
    'M3.25 5.5h6.5c.41 0 .75.34.75.75v6.5c0 .41-.34.75-.75.75h-6.5a.75.75 0 0 1-.75-.75v-6.5c0-.41.34-.75.75-.75z'];

  /* ------------------------------------------------------------ JSON block (no syntax colours) */

  function pointerPart(key) {
    return String(key).replace(/~/g, '~0').replace(/\//g, '~1');
  }

  function renderJson(value, maskedPaths) {
    var pre = el('pre', 'json');
    var masked = {};
    (maskedPaths || []).forEach(function (p) { masked[p] = true; });
    function text(t) { pre.appendChild(document.createTextNode(t)); }
    function pad(n) { return new Array(n + 1).join('  '); }
    function walk(v, path, depth) {
      if (masked[path] && (v === null || typeof v !== 'object')) {
        var m = el('span', 'm', JSON.stringify(v));
        m.title = 'Gizlendi';
        pre.appendChild(m);
        return;
      }
      if (Array.isArray(v)) {
        if (!v.length) { text('[]'); return; }
        text('[\n');
        v.forEach(function (item, i) {
          text(pad(depth + 1));
          walk(item, path + '/' + i, depth + 1);
          text(i < v.length - 1 ? ',\n' : '\n');
        });
        text(pad(depth) + ']');
      } else if (v !== null && typeof v === 'object') {
        var keys = Object.keys(v);
        if (!keys.length) { text('{}'); return; }
        text('{\n');
        keys.forEach(function (k, i) {
          text(pad(depth + 1));
          pre.appendChild(el('span', 'k', JSON.stringify(k)));
          text(': ');
          walk(v[k], path + '/' + pointerPart(k), depth + 1);
          text(i < keys.length - 1 ? ',\n' : '\n');
        });
        text(pad(depth) + '}');
      } else {
        text(JSON.stringify(v));
      }
    }
    walk(value, '', 0);
    return pre;
  }

  function copyText(value, button, label) {
    var payload = JSON.stringify(value, null, 2);
    function done() {
      button.lastChild.textContent = 'Kopyalandı';
      setTimeout(function () { button.lastChild.textContent = label; }, 2000);
    }
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(payload).then(done, function () {});
      return;
    }
    var area = el('textarea');
    area.value = payload;
    area.setAttribute('readonly', '');
    area.className = 'gorunmez';
    document.body.appendChild(area);
    area.select();
    try { document.execCommand('copy'); done(); } catch (e) { /* ignore */ }
    document.body.removeChild(area);
  }

  function block(titleText, value, maskedPaths, copyLabel) {
    var wrap = el('div', 'blok');
    var head = el('div', 'blok-ust');
    head.appendChild(el('span', 'blok-baslik', titleText));
    var hasBody = value !== null && value !== undefined && !(typeof value === 'object' && !Object.keys(value).length && !Array.isArray(value));
    if (hasBody && copyLabel) {
      var btn = el('button', 'kopyala');
      btn.type = 'button';
      btn.appendChild(icon(COPY));
      btn.appendChild(el('span', null, copyLabel));
      btn.addEventListener('click', function () { copyText(value, btn, copyLabel); });
      head.appendChild(btn);
    }
    wrap.appendChild(head);
    wrap.appendChild(hasBody ? renderJson(value, maskedPaths) : el('p', 'json-bos', 'Gövde yok.'));
    return wrap;
  }

  /* ------------------------------------------------------------ one slip */

  function authLabel(auth) {
    if (auth === 'V2') return 'İmza V2';
    if (auth === 'V1') return 'İmza V1';
    return 'İmzasız';
  }

  function buildDetail(entry, container) {
    container.appendChild(block('Başlıklar', entry.headers, entry.headersMasked, null));
    container.appendChild(block('İstek', entry.request, entry.requestMasked, 'İsteği kopyala'));
    container.appendChild(block(entry.kind === 'error' ? 'Yanıt (hata)' : 'Yanıt', entry.response,
      entry.responseMasked, 'Yanıtı kopyala'));
    container.appendChild(el('p', 'maske-notu', 'Kart numarası, son kullanma tarihi, CVC ve gizli anahtarlar gizlendi.'));
  }

  function buildEntry(entry) {
    var li = el('li', 'kayit' + (entry.kind === 'error' ? ' kayit--hata' : '') + (entry.bankReject ? ' kayit--red' : ''));
    li.dataset.seq = entry.seq;
    var detailId = 'kayit-' + entry.seq + '-detay';

    var button = el('button', 'kayit-ozet');
    button.type = 'button';
    button.setAttribute('aria-expanded', 'false');
    button.setAttribute('aria-controls', detailId);

    var s1 = el('span', 'kayit-s1');
    var methodName = el('span', 'kayit-metot');
    String(entry.method).split('.').forEach(function (part, i) {
      if (i) { methodName.appendChild(document.createTextNode('.')); methodName.appendChild(document.createElement('wbr')); }
      methodName.appendChild(document.createTextNode(part));
    });
    s1.appendChild(methodName);
    var meta = el('span', 'kayit-meta');
    meta.appendChild(el('span', null, authLabel(entry.auth)));
    meta.appendChild(el('span', 'kayit-http', entry.status === null ? 'Yanıt yok' : 'HTTP ' + entry.status));
    meta.appendChild(el('span', null, entry.ms + ' ms'));
    s1.appendChild(meta);
    button.appendChild(s1);

    var s2 = el('span', 'kayit-s2');
    s2.appendChild(el('b', null, entry.httpMethod));
    s2.appendChild(document.createTextNode(' ' + entry.path + (entry.query ? '?' + entry.query : '')));
    button.appendChild(s2);

    var s3 = el('span', 'kayit-s3');
    s3.appendChild(el('span', null, '#' + entry.seq));
    s3.appendChild(el('span', null, entry.time));
    if (entry.trigger) s3.appendChild(el('span', null, 'Tetikleyen: ' + entry.trigger));
    button.appendChild(s3);

    if (entry.errorLine) button.appendChild(el('span', 'kayit-s4', entry.errorLine));
    button.appendChild(icon(CHEVRON, 'kayit-ok'));
    var sr = el('span', 'gorunmez', 'Ayrıntıları göster');
    button.appendChild(sr);

    var detail = el('div', 'kayit-detay');
    detail.id = detailId;
    detail.hidden = true;

    button.addEventListener('click', function () {
      var open = button.getAttribute('aria-expanded') !== 'true';
      if (open && !detail.firstChild) buildDetail(entry, detail);
      detail.hidden = !open;
      button.setAttribute('aria-expanded', open ? 'true' : 'false');
      sr.textContent = open ? 'Ayrıntıları gizle' : 'Ayrıntıları göster';
    });

    li.appendChild(button);
    li.appendChild(detail);
    li.addEventListener('animationend', function (ev) {
      if (ev.animationName.indexOf('fosfor') === 0) li.classList.remove('kayit--yeni', 'kayit--besle');
    });
    return li;
  }

  /* ------------------------------------------------------------ header, counters, empty state */

  function isOpen() { return root.classList.contains('rulo--acik'); }

  function updateHead(latest) {
    counter.textContent = state.count + ' çağrı';
    counterShort.textContent = state.count;
    if (latest) {
      var status = latest.status === null ? 'yanıt yok' : 'HTTP ' + latest.status;
      lastLine.textContent = 'Son çağrı: ' + latest.method + ', ' + status + (latest.kind === 'error' ? ', hata' : '');
    } else if (!state.count) {
      lastLine.textContent = '';
    }
    var hasRows = !!list.firstChild;
    emptyText.hidden = hasRows;
    if (!hasRows) {
      emptyText.textContent = state.cleared
        ? 'Günlük temizlendi. Bir sonraki SDK çağrısı burada görünecek.'
        : 'Henüz SDK çağrısı yok. Kart numarasını değiştirin ya da ödeme yapın; sunucunun yaptığı her çağrı burada görünür.';
    }
  }

  function updateNewButton() {
    if (state.unseen > 0) {
      newButton.textContent = state.unseen + ' yeni çağrı, en üste git';
      newButton.hidden = false;
    } else {
      newButton.hidden = true;
    }
  }

  function remember() {
    try { sessionStorage.setItem(SEEN_KEY, String(state.lastSeq)); } catch (e) { /* ignore */ }
  }

  /* ------------------------------------------------------------ adding slips (the planned moment) */

  function addEntries(entries) {
    if (!entries.length) return;
    var now = Date.now();
    state.arrivals = state.arrivals.filter(function (t) { return now - t < 1000; });
    var burst = state.arrivals.length + entries.length > 3;
    entries.forEach(function () { state.arrivals.push(now); });

    var collapsed = narrow.matches && !isOpen();
    var scrolled = !narrow.matches && scroller.scrollTop > 0;
    var feed = !reduceMotion.matches && !burst && !scrolled && !collapsed;

    var siblings = Array.prototype.slice.call(list.children, 0, 25);
    var added = [];
    entries.forEach(function (entry) {
      var li = buildEntry(entry);
      list.insertBefore(li, list.firstChild);
      added.push(li);
    });
    var height = added.reduce(function (sum, li) { return sum + li.offsetHeight; }, 0);

    if (!collapsed) {
      added.forEach(function (li) { li.classList.add(feed ? 'kayit--besle' : 'kayit--yeni'); });
    }
    if (feed && siblings.length) {
      siblings.forEach(function (li) {
        li.style.transition = 'none';
        li.style.transform = 'translateY(' + (-height) + 'px)';
      });
      void list.offsetHeight;
      siblings.forEach(function (li) {
        li.style.transition = 'transform var(--sure-besleme) var(--egri-besleme)';
        li.style.transform = '';
        li.addEventListener('transitionend', function clear() {
          li.style.transition = '';
          li.removeEventListener('transitionend', clear);
        });
      });
    }
    if (scrolled) {
      scroller.scrollTop += height;
      state.unseen += entries.length;
      updateNewButton();
    }
    var latest = entries[entries.length - 1];
    live.textContent = latest.announce;
    updateHead(latest);
  }

  function renderAll(snapshot, markAfter) {
    list.textContent = '';
    var entries = snapshot.entries.slice();
    entries.forEach(function (entry) {
      var li = buildEntry(entry);
      if (markAfter !== null && entry.seq > markAfter) li.classList.add('kayit--yeni');
      list.insertBefore(li, list.firstChild);
    });
    updateHead(entries[entries.length - 1] || null);
  }

  /* ------------------------------------------------------------ polling */

  function isReset(snapshot) {
    // cleared in another tab, or the server restarted (sequence numbers start again)
    return snapshot.generation !== state.generation || snapshot.lastSeq < state.lastSeq;
  }

  function apply(snapshot) {
    if (isReset(snapshot)) {
      state.generation = snapshot.generation;
      state.lastSeq = snapshot.lastSeq;
      state.count = snapshot.count;
      state.cleared = snapshot.cleared;
      renderAll(snapshot, null);
    } else {
      var fresh = snapshot.entries.filter(function (e) { return e.seq > state.lastSeq; });
      state.count = snapshot.count;
      state.lastSeq = Math.max(state.lastSeq, snapshot.lastSeq);
      addEntries(fresh);
      updateHead(null);
    }
    remember();
  }

  function refresh() {
    if (state.busy) { state.again = true; return; }
    state.busy = true;
    fetch('/api/log?after=' + encodeURIComponent(state.lastSeq), { cache: 'no-store', credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (snapshot) {
        if (!snapshot) return;
        if (isReset(snapshot) && snapshot.entries.length < snapshot.count) {
          return fetch('/api/log?after=0', { cache: 'no-store', credentials: 'same-origin' })
            .then(function (r) { return r.ok ? r.json() : null; })
            .then(function (full) { if (full) apply(full); });
        }
        apply(snapshot);
      })
      .catch(function () { /* server restarting; try again on the next tick */ })
      .then(function () {
        state.busy = false;
        if (state.again) { state.again = false; refresh(); }
      });
  }

  setInterval(function () { if (!document.hidden) refresh(); }, POLL_MS);
  document.addEventListener('visibilitychange', function () { if (!document.hidden) refresh(); });

  /* ------------------------------------------------------------ controls */

  newButton.addEventListener('click', function () {
    scroller.scrollTo({ top: 0, behavior: reduceMotion.matches ? 'auto' : 'smooth' });
    state.unseen = 0;
    updateNewButton();
  });
  scroller.addEventListener('scroll', function () {
    if (scroller.scrollTop <= 0 && state.unseen) {
      state.unseen = 0;
      updateNewButton();
    }
  }, { passive: true });

  clearButton.addEventListener('click', function () {
    clearButton.disabled = true;
    fetch('/api/log/temizle', { method: 'POST', credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (snapshot) {
        if (!snapshot) return;
        state.generation = snapshot.generation;
        state.count = snapshot.count;
        state.cleared = true;
        state.unseen = 0;
        list.textContent = '';
        updateNewButton();
        updateHead(null);
        (narrow.matches ? toggle : title).focus();
      })
      .catch(function () { /* keep the list */ })
      .then(function () { clearButton.disabled = false; });
  });

  function setOpen(open) {
    root.classList.toggle('rulo--acik', open);
    toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    toggleText.textContent = open ? 'Gizle' : 'Göster';
    try { sessionStorage.setItem(OPEN_KEY, open ? '1' : '0'); } catch (e) { /* ignore */ }
  }
  toggle.addEventListener('click', function () { setOpen(!isOpen()); });

  /* ------------------------------------------------------------ start */

  var seen = null;
  try {
    var stored = sessionStorage.getItem(SEEN_KEY);
    seen = stored === null ? null : parseInt(stored, 10);
    setOpen(sessionStorage.getItem(OPEN_KEY) === '1');
  } catch (e) { setOpen(false); }
  renderAll(boot, seen);
  remember();

  window.SdkLog = { refresh: refresh };
})();
