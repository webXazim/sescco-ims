/* Advisory preview only: Django allocates the final tenant-unique code on save. */
(() => {
  'use strict';
  const form = document.querySelector('.sourcing-form-shell');
  const preview = form?.querySelector('[data-vendor-code-preview]');
  const code = form?.querySelector('[name="code"]');
  const legal = form?.querySelector('[name="name"]');
  const display = form?.querySelector('[name="display_name"]');
  if (!preview || !code || !legal || !display) return;
  function slug(source) {
    return String(source || '').normalize('NFKD').replace(/[\u0300-\u036f]/g, '')
      .toLocaleUpperCase().trim().replace(/[^\p{L}\p{N}]+/gu, '-').replace(/^-+|-+$/g, '').slice(0, 26).replace(/-+$/g, '');
  }
  function update() {
    if (code.value.trim()) { preview.textContent = 'Custom Vendor code will be used.'; return; }
    const value = slug(legal.value || display.value) || 'UNNAMED';
    const suggestion = `VND-${value}`;
    code.placeholder = suggestion;
    preview.textContent = `Generated on save: ${suggestion}${value === 'UNNAMED' ? '' : ' (a suffix may be added if taken)'}`;
  }
  [legal, display, code].forEach(el => el.addEventListener('input', update));
  update();
})();
