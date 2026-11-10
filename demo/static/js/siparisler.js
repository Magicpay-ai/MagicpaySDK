/* Orders: "Durumu sorgula" (retrieve_payment) and the inline refund confirmation (refund_payment). */
(function () {
  'use strict';

  function refreshLog() { if (window.SdkLog) window.SdkLog.refresh(); }

  function post(url) {
    return fetch(url, { method: 'POST', credentials: 'same-origin', headers: { Accept: 'application/json' } })
      .then(function (r) {
        return r.json().catch(function () { return {}; }).then(function (body) { return { ok: r.ok, body: body }; });
      }, function () {
        return { ok: false, body: { message: 'Sunucuya ulaşılamadı. Uygulamanın çalıştığını kontrol edip tekrar deneyin.' } };
      });
  }

  function show(node, text) {
    if (!node) return;
    node.textContent = text || '';
    node.hidden = !text;
  }

  Array.prototype.forEach.call(document.querySelectorAll('[data-siparis]'), function (group) {
    var id = group.dataset.siparis;
    var base = '/api/siparisler/' + encodeURIComponent(id);
    var label = group.querySelector('[data-durum]');
    var note = group.querySelector('[data-not]');
    var refundNote = group.querySelector('[data-iade-not]');
    var rowError = group.querySelector('[data-hata]');
    var queryButton = group.querySelector('[data-sorgula]');
    var refundButton = group.querySelector('[data-iade]');
    var confirmRow = group.querySelector('[data-iade-onay]');
    var confirmButton = group.querySelector('[data-iade-onayla]');
    var cancelButton = group.querySelector('[data-iade-vazgec]');
    var confirmError = group.querySelector('[data-iade-hata]');

    function closeConfirm(returnFocus) {
      if (!confirmRow || confirmRow.hidden) return;
      confirmRow.hidden = true;
      if (refundButton) {
        refundButton.setAttribute('aria-expanded', 'false');
        if (returnFocus) refundButton.focus();
      }
    }

    function applyRow(row) {
      label.className = 'durum durum--' + row.status.tone;
      label.textContent = row.status.label;
      show(note, row.note);
      show(refundNote, row.refundNote);
      if (!row.refundable && refundButton) {
        closeConfirm(false);
        refundButton.remove();
        refundButton = null;
        if (confirmRow) { confirmRow.remove(); confirmRow = null; }
      }
    }

    queryButton.addEventListener('click', function () {
      queryButton.disabled = true;
      queryButton.textContent = 'Sorgulanıyor…';
      show(rowError, '');
      post(base + '/sorgula').then(function (res) {
        if (res.ok) applyRow(res.body);
        else show(rowError, res.body.message);
        queryButton.disabled = false;
        queryButton.textContent = 'Durumu sorgula';
        refreshLog();
      });
    });

    if (!refundButton || !confirmRow) return;

    refundButton.addEventListener('click', function () {
      if (confirmRow.hidden) {
        confirmRow.hidden = false;
        refundButton.setAttribute('aria-expanded', 'true');
        show(confirmError, '');
        cancelButton.focus();
      } else {
        closeConfirm(true);
      }
    });
    cancelButton.addEventListener('click', function () { closeConfirm(true); });
    confirmRow.addEventListener('keydown', function (ev) {
      if (ev.key === 'Escape') { ev.preventDefault(); closeConfirm(true); }
    });

    confirmButton.addEventListener('click', function () {
      confirmButton.disabled = true;
      cancelButton.disabled = true;
      confirmButton.textContent = 'İade ediliyor…';
      show(confirmError, '');
      post(base + '/iade').then(function (res) {
        if (res.ok) {
          applyRow(res.body);
          queryButton.focus();
        } else {
          confirmButton.disabled = false;
          cancelButton.disabled = false;
          confirmButton.textContent = 'İadeyi onayla';
          show(confirmError, res.body.message);
        }
        refreshLog();
      });
    });
  });
})();
