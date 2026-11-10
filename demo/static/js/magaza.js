/* Store page: demo amount, installment table, BIN line, card validation, pay button. */
(function () {
  'use strict';

  var form = document.querySelector('[data-odeme-formu]');
  if (!form) return;

  var demo = document.querySelector('[data-demo-ayar]');
  var amountInput = document.getElementById('demo-tutar');
  var amountError = document.querySelector('[data-tutar-hata]');
  var applyButton = document.querySelector('[data-tutar-uygula]');
  var priceText = document.querySelector('[data-fiyat]');
  var formAmount = form.querySelector('[data-form-tutar]');
  var formBank = form.querySelector('[data-form-banka]');

  var table = form.querySelector('[data-taksit]');
  var tbody = form.querySelector('[data-taksit-govde]');
  var tableError = form.querySelector('[data-taksit-hata]');
  var singleNote = form.querySelector('[data-taksit-tek]');
  var totalText = form.querySelector('[data-toplam]');
  var summaryText = form.querySelector('[data-ozet]');
  var payButton = form.querySelector('[data-ode]');

  var cardNumber = document.getElementById('kart-no');
  var binLine = form.querySelector('[data-bin]');
  var cardName = document.getElementById('kart-isim');
  var cardExp = document.getElementById('kart-skt');
  var cardCvc = document.getElementById('kart-cvc');

  var MIN = parseFloat(demo.dataset.min);
  var MAX = parseFloat(demo.dataset.max);
  var money = new Intl.NumberFormat('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  var options = [];
  var selected = parseInt(table.dataset.secili, 10) || 1;
  var payText = payButton.textContent;

  function refreshLog() { if (window.SdkLog) window.SdkLog.refresh(); }
  function tl(value) { return money.format(value) + ' TL'; }

  /* same rules as the server: 1250, 1250,5, 1.250,50 (and 1250.50) */
  function parseAmount(text) {
    var s = String(text || '').replace(/\s/g, '').replace(/TL$/i, '');
    if (/^\d{1,3}(\.\d{3})+(,\d{1,2})?$/.test(s)) s = s.replace(/\./g, '').replace(',', '.');
    else if (/^\d+(,\d{1,2})?$/.test(s)) s = s.replace(',', '.');
    else if (!/^\d+\.\d{1,2}$/.test(s)) return null;
    var value = Math.round(parseFloat(s) * 100) / 100;
    return value >= MIN && value <= MAX ? value : null;
  }

  /* ------------------------------------------------------------ field errors */

  function setError(input, errorId, message) {
    var error = document.getElementById(errorId);
    var described = (input.getAttribute('aria-describedby') || '').split(' ').filter(function (id) {
      return id && id !== errorId;
    });
    if (message) {
      error.textContent = message;
      error.hidden = false;
      input.setAttribute('aria-invalid', 'true');
      described.push(errorId);
    } else {
      error.textContent = '';
      error.hidden = true;
      input.removeAttribute('aria-invalid');
    }
    if (described.length) input.setAttribute('aria-describedby', described.join(' '));
    else input.removeAttribute('aria-describedby');
    return !message;
  }

  /* ------------------------------------------------------------ installments */

  function infoRow(text) {
    tbody.textContent = '';
    var tr = document.createElement('tr');
    tr.className = 'taksit-bilgi';
    var td = document.createElement('td');
    td.colSpan = 3;
    td.textContent = text;
    tr.appendChild(td);
    tbody.appendChild(tr);
  }

  function choose(n) {
    var opt = options.filter(function (o) { return o.n === n; })[0] || options[0];
    if (!opt) return;
    selected = opt.n;
    Array.prototype.forEach.call(tbody.querySelectorAll('tr'), function (tr) {
      var radio = tr.querySelector('input');
      var on = radio && parseInt(radio.value, 10) === selected;
      if (radio) radio.checked = on;
      tr.classList.toggle('secili', !!on);
    });
    totalText.textContent = opt.totalText;
    summaryText.textContent = opt.summary;
    payText = opt.payText;
    if (!payButton.disabled) payButton.textContent = payText;
  }

  function renderOptions(list) {
    options = list;
    tbody.textContent = '';
    list.forEach(function (opt) {
      var tr = document.createElement('tr');
      var first = document.createElement('td');
      var label = document.createElement('label');
      var radio = document.createElement('input');
      radio.type = 'radio';
      radio.name = 'taksit';
      radio.value = String(opt.n);
      radio.id = 'taksit-' + opt.n;
      label.htmlFor = radio.id;
      label.appendChild(radio);
      label.appendChild(document.createTextNode(opt.label));
      first.appendChild(label);
      var monthly = document.createElement('td');
      monthly.className = 'sayi';
      monthly.textContent = opt.monthlyText;
      var total = document.createElement('td');
      total.className = 'sayi';
      total.textContent = opt.totalText;
      tr.appendChild(first);
      tr.appendChild(monthly);
      tr.appendChild(total);
      tr.addEventListener('click', function (ev) {
        if (ev.target !== radio && ev.target !== label) radio.click();
      });
      radio.addEventListener('change', function () { choose(opt.n); });
      tbody.appendChild(tr);
    });
    singleNote.hidden = list.length !== 1;
    choose(selected);
  }

  function loadInstallments(amountText, trigger) {
    tableError.hidden = true;
    singleNote.hidden = true;
    infoRow('Taksit seçenekleri getiriliyor…');
    applyButton.disabled = true;
    var url = '/api/taksitler?tutar=' + encodeURIComponent(amountText) + '&tetikleyen=' + trigger;
    return fetch(url, { cache: 'no-store', credentials: 'same-origin' })
      .then(function (r) {
        return r.json().then(function (body) { return { ok: r.ok, body: body }; });
      })
      .then(function (res) {
        if (res.ok) {
          renderOptions(res.body.options);
        } else if (res.body && res.body.fallback) {
          tableError.hidden = false;
          renderOptions([res.body.fallback]);
          singleNote.hidden = true;
        } else {
          tableError.hidden = false;
          tableError.textContent = (res.body && res.body.message) || tableError.textContent;
          var value = parseAmount(amountText);
          renderOptions([{ n: 1, label: 'Tek çekim', monthlyText: tl(value), totalText: tl(value),
            summary: 'Tek çekim', payText: tl(value) + ' öde' }]);
          singleNote.hidden = true;
        }
      })
      .catch(function () {
        tableError.hidden = false;
        var value = parseAmount(amountText);
        renderOptions([{ n: 1, label: 'Tek çekim', monthlyText: tl(value), totalText: tl(value),
          summary: 'Tek çekim', payText: tl(value) + ' öde' }]);
        singleNote.hidden = true;
      })
      .then(function () {
        applyButton.disabled = false;
        refreshLog();
      });
  }

  applyButton.addEventListener('click', function () {
    var value = parseAmount(amountInput.value);
    if (value === null) {
      setError(amountInput, 'demo-tutar-hata', demo.dataset.hata);
      amountInput.focus();
      return;
    }
    setError(amountInput, 'demo-tutar-hata', '');
    var text = money.format(value);
    amountInput.value = text;
    formAmount.value = text;
    priceText.textContent = tl(value);
    loadInstallments(text, 'uygula');
  });
  amountInput.addEventListener('keydown', function (ev) {
    if (ev.key === 'Enter') { ev.preventDefault(); applyButton.click(); }
  });

  /* ------------------------------------------------------------ card number + BIN line */

  var lastBin = null;
  var CARD_TYPES = { kredi: 'kredi', banka: 'banka' };

  function digitsOf(value) { return value.replace(/\D/g, ''); }

  function formatCardNumber() {
    var caret = cardNumber.selectionStart;
    var before = digitsOf(cardNumber.value.slice(0, caret)).length;
    var digits = digitsOf(cardNumber.value).slice(0, 16);
    var formatted = digits.replace(/(\d{4})(?=\d)/g, '$1 ');
    if (formatted !== cardNumber.value) {
      cardNumber.value = formatted;
      var pos = 0;
      var seen = 0;
      while (pos < formatted.length && seen < before) {
        if (/\d/.test(formatted[pos])) seen++;
        pos++;
      }
      if (document.activeElement === cardNumber) cardNumber.setSelectionRange(pos, pos);
    }
    return digits;
  }

  function setBin(state, parts) {
    binLine.dataset.durum = state;
    binLine.textContent = '';
    if (state === 'bulundu') {
      var strong = document.createElement('strong');
      strong.textContent = parts.bank;
      binLine.appendChild(strong);
      var rest = '';
      if (parts.cardType) rest += ' ' + parts.cardType + ' kartı';
      else rest += ' kartı';
      if (parts.scheme) rest += ' (' + parts.scheme + ')';
      binLine.appendChild(document.createTextNode(rest));
      return;
    }
    binLine.textContent = {
      kisa: 'Kartın bankası ilk 6 haneden bulunur.',
      sorgu: 'Kart bilgisi sorgulanıyor…',
      yok: 'Bu kartın bankası bulunamadı. Numarayı kontrol edin; ödeme yine de denenebilir.',
      hata: 'Kart bilgisi alınamadı. Ödemeye devam edebilirsiniz.'
    }[state];
  }

  function lookupBin(digits) {
    if (digits.length < 6) {
      lastBin = null;
      formBank.value = '';
      setBin('kisa');
      return;
    }
    var bin = digits.slice(0, 6);
    if (bin === lastBin) return;
    lastBin = bin;
    setBin('sorgu');
    fetch('/api/bin?bin=' + bin, { cache: 'no-store', credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(); })
      .then(function (body) {
        if (bin !== lastBin) return;
        if (body.found) {
          formBank.value = body.bank;
          setBin('bulundu', { bank: body.bank, cardType: CARD_TYPES[body.cardType] || body.cardType, scheme: body.scheme });
        } else {
          formBank.value = '';
          setBin('yok');
        }
      })
      .catch(function () {
        if (bin === lastBin) { formBank.value = ''; setBin('hata'); }
      })
      .then(refreshLog);
  }

  cardNumber.addEventListener('input', function () { lookupBin(formatCardNumber()); });

  /* ------------------------------------------------------------ validation (blur + submit) */

  var checks = {
    'kart-no': function () {
      var ok = digitsOf(cardNumber.value).length === 16;
      return setError(cardNumber, 'kart-no-hata', ok ? '' : 'Kart numarası 16 hane olmalı. Eksik haneleri tamamlayın.');
    },
    'kart-isim': function () {
      return setError(cardName, 'kart-isim-hata', cardName.value.trim() ? '' : 'Kart üzerindeki ismi girin.');
    },
    'kart-skt': function () {
      var m = /^\s*(\d{2})\s*\/?\s*(\d{2})\s*$/.exec(cardExp.value);
      if (!m || +m[1] < 1 || +m[1] > 12) {
        return setError(cardExp, 'kart-skt-hata', 'Son kullanma tarihini AA/YY biçiminde girin, örneğin 12/30.');
      }
      cardExp.value = m[1] + '/' + m[2];
      var now = new Date();
      var year = 2000 + (+m[2]);
      if (year < now.getFullYear() || (year === now.getFullYear() && +m[1] < now.getMonth() + 1)) {
        return setError(cardExp, 'kart-skt-hata', 'Bu kartın süresi dolmuş. Kartın üzerindeki tarihi girin.');
      }
      return setError(cardExp, 'kart-skt-hata', '');
    },
    'kart-cvc': function () {
      return setError(cardCvc, 'kart-cvc-hata', /^\d{3}$/.test(cardCvc.value.trim()) ? '' : 'Güvenlik kodu kartın arkasındaki 3 hanedir.');
    }
  };
  [cardNumber, cardName, cardExp, cardCvc].forEach(function (input) {
    input.addEventListener('blur', function () { checks[input.id](); });
  });

  form.addEventListener('submit', function (ev) {
    var firstBad = null;
    [cardNumber, cardName, cardExp, cardCvc].forEach(function (input) {
      if (!checks[input.id]() && !firstBad) firstBad = input;
    });
    if (firstBad) {
      ev.preventDefault();
      firstBad.focus();
      return;
    }
    payButton.disabled = true;
    payButton.textContent = 'Ödeme başlatılıyor…';
  });

  /* back from the bank page (bfcache): the button must work again */
  window.addEventListener('pageshow', function (ev) {
    if (ev.persisted) {
      payButton.disabled = false;
      payButton.textContent = payText;
    }
  });

  /* ------------------------------------------------------------ start */

  var initialDigits = formatCardNumber();
  lookupBin(initialDigits);
  loadInstallments(formAmount.value, 'acilis');
})();
