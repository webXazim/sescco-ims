/* Project Pulse U03 — optional, explicit confirmation for reversible archives. */
document.addEventListener('submit', function (event) {
  const form = event.target.closest('form[data-pulse-confirm]');
  if (form && !window.confirm(form.getAttribute('data-pulse-confirm'))) event.preventDefault();
});
