(() => {
  'use strict';
  const dialog = document.querySelector('[data-inventory-delete-dialog]');
  if (!dialog || typeof dialog.showModal !== 'function') return;

  const get = (selector) => dialog.querySelector(selector);
  const loading = get('[data-delete-loading]');
  const details = get('[data-delete-details]');
  const form = get('[data-delete-form]');
  const submit = get('[data-delete-submit]');
  const error = get('[data-delete-error]');
  const blocked = get('[data-delete-blocked]');
  const blockedActions = get('[data-delete-blocked-actions]');
  const notice = get('[data-delete-notice]');
  const headers = {
    'X-Requested-With': 'XMLHttpRequest',
    'Accept': 'application/json',
  };
  let controller = null;
  let opener = null;
  let busy = false;

  function showError(message) {
    error.textContent = message;
    error.hidden = false;
  }

  function makeList(container, items) {
    container.replaceChildren();
    items.forEach((text) => {
      const li = document.createElement('li');
      li.textContent = text;
      container.append(li);
    });
  }

  function applyPayload(payload) {
    get('[data-delete-title]').textContent = payload.title || 'Confirm deletion';
    get('[data-delete-subtitle]').textContent = payload.subtitle || '';
    get('[data-delete-type]').textContent = payload.record_type || 'Record';
    get('[data-delete-record]').textContent = payload.record_label || '';
    get('[data-delete-token]').textContent = payload.confirmation_token || '';
    get('[data-delete-retention]').textContent = `${payload.retention_days || 30} days`;
    makeList(get('[data-delete-effects]'), payload.effects || []);
    const reasons = (payload.blockers || []).map((item) =>
      item.count == null ? item.message : `${item.message} (${item.count})`
    );
    makeList(get('[data-delete-blockers]'), reasons);
    const canDelete = Boolean(payload.delete_allowed);
    notice.hidden = !canDelete;
    form.hidden = !canDelete;
    blocked.hidden = canDelete;
    blockedActions.hidden = canDelete;
    if (payload.error) showError(payload.error);
    loading.hidden = true;
    details.hidden = false;
  }

  async function fetchJson(url, options = {}) {
    const response = await fetch(url, {
      ...options,
      credentials: 'same-origin',
      headers,
      redirect: 'error',
    });
    const contentType = response.headers.get('Content-Type') || '';
    if (!contentType.includes('application/json')) throw new Error('The server did not return a deletion response. Please reload the page.');
    const payload = await response.json();
    return { response, payload };
  }

  async function openDialog(link) {
    if (dialog.open) return;
    opener = link;
    form.reset();
    form.action = link.href;
    error.hidden = true;
    loading.hidden = false;
    details.hidden = true;
    submit.disabled = false;
    busy = false;
    get('[data-delete-title]').textContent = 'Confirm deletion';
    get('[data-delete-subtitle]').textContent = '';
    controller = new AbortController();
    document.querySelectorAll('[data-row-actions][open]').forEach((menu) => menu.removeAttribute('open'));
    dialog.showModal();
    try {
      const { response, payload } = await fetchJson(link.href, { signal: controller.signal });
      if (!dialog.open || controller.signal.aborted) return;
      if (!response.ok && response.status !== 409) throw new Error(payload.error || 'Unable to load deletion details.');
      applyPayload(payload);
      if (payload.delete_allowed) form.elements.reason.focus();
      else get('[data-delete-close]').focus();
    } catch (exc) {
      if (exc.name === 'AbortError' || !dialog.open) return;
      loading.hidden = true;
      details.hidden = false;
      form.hidden = true;
      blocked.hidden = true;
      notice.hidden = true;
      blockedActions.hidden = false;
      showError(exc.message || 'Deletion details could not be loaded. Please try again.');
    }
  }

  document.addEventListener('click', (event) => {
    const link = event.target.closest?.('a[data-inventory-delete]');
    if (!link || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    openDialog(link);
  });

  dialog.querySelectorAll('[data-delete-close]').forEach((button) => {
    button.addEventListener('click', () => { if (!busy) dialog.close(); });
  });
  dialog.addEventListener('cancel', (event) => { if (busy) event.preventDefault(); });
  dialog.addEventListener('click', (event) => {
    if (event.target === dialog && !busy) dialog.close();
  });
  dialog.addEventListener('close', () => {
    controller?.abort();
    controller = null;
    form.reset();
    opener?.focus();
    opener = null;
  });

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (busy || !form.reportValidity()) return;
    busy = true;
    error.hidden = true;
    submit.disabled = true;
    submit.textContent = 'Moving to Trash…';
    try {
      const { response, payload } = await fetchJson(form.action, {
        method: 'POST',
        body: new FormData(form),
      });
      if (response.ok && payload.redirect_url) {
        window.location.assign(payload.redirect_url);
        return;
      }
      if (payload.blockers && !payload.delete_allowed) applyPayload(payload);
      showError(payload.error || 'Deletion was not completed. Check the confirmation and try again.');
    } catch (exc) {
      showError(exc.message || 'Deletion was not completed. Please try again.');
    } finally {
      busy = false;
      submit.disabled = false;
      submit.textContent = 'Move to Trash';
    }
  });
})();
