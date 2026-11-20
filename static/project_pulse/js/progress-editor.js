/* Optional live slider. The normal numeric field and server-side validation
   remain authoritative when JavaScript is unavailable. */
(function () {
  "use strict";
  const form = document.querySelector('[data-pulse-progress-editor]');
  if (!form) return;
  const number = form.querySelector('input[name="progress_percent"]');
  const range = form.querySelector('[data-pulse-progress-range]');
  const output = form.querySelector('[data-pulse-progress-output]');
  if (!number || !range || !output) return;
  function updateFromNumber() {
    if (!number.value.trim()) return;
    const value = Number(number.value);
    if (!Number.isFinite(value) || value < 0 || value > 100 || !Number.isInteger(value)) return;
    range.value = String(value);
    output.textContent = value + "%";
  }
  range.addEventListener('input', function () {
    number.value = range.value;
    output.textContent = range.value + "%";
  });
  number.addEventListener('input', updateFromNumber);
  updateFromNumber();
})();
