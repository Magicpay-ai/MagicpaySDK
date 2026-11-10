/* Result page: focus the heading; "Durumu sorgula" shows that it is working. */
(function () {
  'use strict';
  var heading = document.querySelector('[data-odak]');
  if (heading) heading.focus();

  var form = document.querySelector('[data-sorgu-formu]');
  if (!form) return;
  var button = form.querySelector('[data-sorgu-dugme]');
  form.addEventListener('submit', function () {
    button.disabled = true;
    button.textContent = 'Sorgulanıyor…';
  });
  window.addEventListener('pageshow', function (ev) {
    if (ev.persisted) {
      button.disabled = false;
      button.textContent = 'Durumu sorgula';
    }
  });
})();
