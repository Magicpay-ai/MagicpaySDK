/* Connection check: every read-only call, V2 then V1, one after another so the roll fills slip by slip. */
(function () {
  'use strict';

  var start = document.querySelector('[data-kontrol-baslat]');
  var table = document.querySelector('[data-kontroller]');
  var summary = document.querySelector('[data-kontrol-ozet]');
  if (!start || !table) return;

  function refreshLog() { if (window.SdkLog) window.SdkLog.refresh(); }

  function cellContent(cell, className, text) {
    var label = cell.querySelector('.kontrol-etiket');
    cell.textContent = '';
    if (label) cell.appendChild(label);
    var span = document.createElement('span');
    span.className = className;
    span.textContent = text;
    cell.appendChild(span);
  }

  function setWaiting(cell) {
    cell.classList.remove('kontrol-sonuc--hata');
    cell.removeAttribute('aria-busy');
    cellContent(cell, 'sonuc-bekliyor', 'Bekliyor');
  }

  function setRunning(cell) {
    cell.setAttribute('aria-busy', 'true');
    cellContent(cell, 'sonuc-calisiyor', 'Çalışıyor…');
  }

  function setResult(cell, res) {
    cell.removeAttribute('aria-busy');
    if (res.ok) {
      cellContent(cell, 'sonuc-gecti', 'Geçti');
      var ms = document.createElement('span');
      ms.className = 'sonuc-sure';
      ms.textContent = ', ' + res.ms + ' ms';
      cell.appendChild(ms);
      return;
    }
    cell.classList.add('kontrol-sonuc--hata');
    cellContent(cell, 'sonuc-basarisiz', 'Başarısız');
    var detail = document.createElement('span');
    detail.className = 'sonuc-detay';
    detail.textContent = res.detail || 'Sunucu beklenmeyen bir yanıt verdi.';
    cell.appendChild(detail);
  }

  function runOne(check, version) {
    return fetch('/api/baglanti/kontrol', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ check: check, version: version })
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (body) {
        if (r.ok) return body;
        return { ok: false, detail: body.message || ('HTTP ' + r.status) };
      });
    }, function () {
      return { ok: false, detail: 'Sunucuya ulaşılamadı.' };
    });
  }

  start.addEventListener('click', function () {
    var cells = Array.prototype.slice.call(table.querySelectorAll('td[data-surum]'));
    cells.forEach(setWaiting);
    start.disabled = true;
    start.textContent = 'Kontroller çalışıyor…';
    var passed = 0;
    var failed = 0;

    cells.reduce(function (chain, cell) {
      return chain.then(function () {
        setRunning(cell);
        var check = cell.closest('tr').dataset.kontrol;
        return runOne(check, cell.dataset.surum).then(function (res) {
          setResult(cell, res);
          if (res.ok) passed++; else failed++;
          refreshLog();
        });
      });
    }, Promise.resolve()).then(function () {
      var total = passed + failed;
      var text = total + ' kontrol çalıştı: ' + passed + ' geçti, ' + failed + ' başarısız. ';
      text += failed
        ? 'Başarısız satırlardaki hata kodunu inceleyin; 401 ve 403 çoğunlukla API anahtarının yetkisinin eksik olduğunu gösterir.'
        : 'Entegrasyon test ortamında hazır.';
      summary.textContent = text;
      start.disabled = false;
      start.textContent = 'Kontrolleri yeniden çalıştır';
    });
  });
})();
