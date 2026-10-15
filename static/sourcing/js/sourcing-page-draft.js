/* Preserve standalone Sourcing capability/master forms on reload, including selected references.
 * Draft data stays in tab-local sessionStorage and is never submitted to a draft API. */
(() => {
  'use strict';
  const form = document.querySelector('form[data-sourcing-page-draft]');
  if (!form) return;
  const actor = document.querySelector('.platform-account__copy strong, .platform-account__identity strong')?.textContent?.trim() || 'unknown';
  const company = form.dataset.sourcingCompany || 'no-company';
  const key = `sescco:sourcing:page-draft:v1:${encodeURIComponent(actor)}:${encodeURIComponent(company)}:${location.pathname}`;
  const ttl = 24 * 60 * 60 * 1000;
  let submitting = false, restoring = false, disabled = false, timer;
  const elements = () => [...form.querySelectorAll('input[name],select[name],textarea[name]')]
    .filter(el => !['csrfmiddlewaretoken'].includes(el.name) && !['password', 'file', 'submit', 'button'].includes(el.type));
  function state() {
    return {
      fields: elements().map(el => ({ name: el.name, type: el.type, value: el.value,
        checked: ['checkbox', 'radio'].includes(el.type) ? el.checked : null })),
      queries: [...form.querySelectorAll('[data-sourcing-reference-lookup]')].map(el => ({
        kind: el.dataset.kind, value: el.querySelector('[data-reference-search]')?.value || ''
      })),
    };
  }
  const initial = JSON.stringify(state());
  const dirty = () => JSON.stringify(state()) !== initial;
  let notice;
  function showNotice(text, canDiscard) {
    if (!notice) {
      notice = document.createElement('div');
      notice.className = 'sourcing-page-draft-notice';
      notice.setAttribute('role', 'status');
      notice.innerHTML = '<span data-page-draft-message></span><button type="button" data-page-draft-discard>Discard draft</button>';
      notice.querySelector('[data-page-draft-discard]').addEventListener('click', () => {
        if (!window.confirm('Discard this unsaved Sourcing form and start again?')) return;
        submitting = true;
        try { sessionStorage.removeItem(key); } catch (_) { /* unavailable */ }
        location.reload();
      });
      form.parentElement.insertBefore(notice, form);
    }
    notice.querySelector('[data-page-draft-message]').textContent = text;
    notice.querySelector('[data-page-draft-discard]').hidden = !canDiscard;
  }
  function save(pending = false) {
    if (restoring || disabled || (!dirty() && !pending)) return;
    try {
      const entry = { v: 1, actor, company, path: location.pathname, updated: Date.now(), pending, content: state() };
      const payload = JSON.stringify(entry);
      if (payload.length > 500000) throw new Error('Draft too large');
      sessionStorage.setItem(key, payload);
    } catch (_) {
      disabled = true;
      showNotice('Automatic recovery is unavailable in this browser. Keep this page open.', false);
    }
  }
  function restore(entry) {
    restoring = true;
    try {
      const byName = new Map(elements().map(el => [el.name, el]));
      for (const field of entry.content.fields || []) {
        const el = byName.get(field.name);
        if (!el || el.type === 'file') continue;
        if (field.checked != null) el.checked = !!field.checked;
        else if (el.tagName === 'SELECT' && ![...el.options].some(opt => opt.value === field.value)) continue;
        else el.value = String(field.value ?? '');
      }
      form.querySelectorAll('[data-material-category-scope]').forEach(scope => {
        const select = scope.querySelector('[data-material-category-select]');
        if (select) select.dispatchEvent(new Event('change', { bubbles: true }));
      });
      form.querySelectorAll('[data-sourcing-reference-lookup]').forEach((lookup, i) => {
        const selected = lookup.querySelector('input[type=hidden][name]')?.value;
        if (selected) lookup.dispatchEvent(new CustomEvent('sourcing:reference-lookup-restore', {detail: {selectedId: selected}}));
        const q = entry.content.queries?.[i]?.value;
        const search = lookup.querySelector('[data-reference-search]');
        if (!selected && search && q) { search.value = q; search.dispatchEvent(new Event('input', {bubbles:true})); }
      });
    } finally { restoring = false; }
  }
  try {
    const raw = sessionStorage.getItem(key);
    if (raw) {
      const entry = JSON.parse(raw);
      if (entry?.v === 1 && entry.actor === actor && entry.company === company && entry.path === location.pathname &&
          Date.now() - entry.updated < ttl && entry.content) {
        const hasServerErrors = !!form.querySelector('.has-error, .field-error, .sourcing-form-errors');
        if (!hasServerErrors) {
          restore(entry);
          showNotice('Unsaved form recovered after reload.', true);
        } else showNotice('Correct the highlighted fields. Your submitted values are still here.', false);
      } else sessionStorage.removeItem(key);
    }
  } catch (_) { /* storage not accessible: form remains usable */ }
  function queueSave() { if (submitting || restoring) return; clearTimeout(timer); timer = setTimeout(() => save(false), 220); }
  form.addEventListener('input', queueSave);
  form.addEventListener('change', queueSave);
  form.addEventListener('sourcing:reference-selected', queueSave);
  form.addEventListener('submit', event => {
    if (event.defaultPrevented) return;
    clearTimeout(timer);
    save(true);
    submitting = true;
  });
  window.addEventListener('beforeunload', event => {
    clearTimeout(timer); if (!submitting) save(false);
    if (!submitting && dirty()) { event.preventDefault(); event.returnValue = ''; }
  });
  window.addEventListener('pagehide', () => { clearTimeout(timer); if (!submitting) save(false); });
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden' && !submitting) save(false); });
})();
