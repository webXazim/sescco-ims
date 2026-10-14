/* Readable preview only. Backend allocates the authoritative tenant-unique code. */
(() => {
  'use strict';
  const preview = document.querySelector('[data-provider-code-preview]');
  if (!preview) return;
  const form = preview.closest('form');
  const name = form.querySelector('[name="name"]');
  const code = form.querySelector('[name="code"]');
  const prefix = location.pathname.includes('subcontractors') ? 'SUB' : 'MPS';
  if (!name || !code) return;
  function update() {
    if (code.value.trim()) { preview.textContent = 'Manual code: ' + code.value.trim(); return; }
    const slug = (name.value || '').trim().normalize('NFKC').replace(/[^\p{L}\p{N}]+/gu, '-').replace(/^-+|-+$/g, '').toUpperCase().slice(0, 26) || 'UNNAMED';
    preview.textContent = 'Suggested: ' + prefix + '-' + slug + ' · final uniqueness checked on save';
  }
  name.addEventListener('input', update);
  code.addEventListener('input', update);
  update();
})();
