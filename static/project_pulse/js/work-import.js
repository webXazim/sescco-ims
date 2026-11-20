/* One JSON field avoids Django's per-request 1,000-field default limit on large imports. */
(function () {
  "use strict";
  const form = document.querySelector("[data-pulse-import-form]");
  if (!form) return;
  form.addEventListener("submit", function () {
    const decisions = {};
    form.querySelectorAll("select[data-import-index]").forEach(function (select) {
      decisions[select.dataset.importIndex] = select.value;
    });
    form.querySelector('input[name="decisions_json"]').value = JSON.stringify(decisions);
  });
})();
