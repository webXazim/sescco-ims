/* Company-first sourcing directory. Progressive enhancement: GET forms, links and
 * profile pages remain usable without JS. Results alone are replaced after a
 * debounced, abortable server-side search. No client-side full catalog caching. */
(() => {
  'use strict';
  const form = document.querySelector('[data-unified-form]');
  if (!form) return;
  let results = document.querySelector('[data-unified-results]');
  if (!results) return;
  const liveStatus = document.createElement('span');
  liveStatus.className = 'sourcing-unified-live-status';
  liveStatus.setAttribute('role', 'status');
  liveStatus.setAttribute('aria-live', 'polite');
  form.appendChild(liveStatus);
  let controller = null;
  let timer = null;
  let serial = 0;
  const debounceMs = 320;

  function makeURL() {
    const url = new URL(form.action, location.href);
    const data = new FormData(form);
    data.delete('page');
    for (const [key, value] of data.entries()) {
      if (typeof value === 'string' && value.trim()) url.searchParams.set(key, value);
    }
    return url;
  }
  function updateExports(url) {
    document.querySelectorAll('[data-unified-export]').forEach((link) => {
      const dest = new URL(link.href, location.href);
      dest.search = url.search;
      // Export the same unified filter set as the screen, even after live typing.
      // Without this flag export_rows falls back to the legacy offer query.
      dest.searchParams.set('unified', '1');
      dest.searchParams.set('format', 'xlsx');
      link.href = dest.pathname + dest.search;
    });
  }
  function applyColumns() {
    const table = results.querySelector('[data-vendor-table], [data-manpower-table], [data-subcontractor-table]');
    if (!table) return;
    form.querySelectorAll('[data-column-toggle]').forEach((toggle) => {
      table.querySelectorAll(`[data-column="${toggle.dataset.columnToggle}"]`)
        .forEach((cell) => { cell.hidden = !toggle.checked; });
    });
  }
  function resetLoading() {
    results.removeAttribute('aria-busy');
    results.classList.remove('sourcing-unified-loading');
  }
  async function search(url, {push = false} = {}) {
    if (controller) controller.abort();
    controller = new AbortController();
    const local = controller;
    const id = ++serial;
    results.setAttribute('aria-busy', 'true');
    results.classList.add('sourcing-unified-loading');
    liveStatus.textContent = 'Searching…';
    try {
      const response = await fetch(url, {
        method: 'GET', credentials: 'same-origin',
        headers: {'X-Requested-With': 'sourcing-unified-directory'},
        signal: local.signal,
      });
      if (!response.ok) throw new Error('Directory search failed');
      const documentResponse = new DOMParser().parseFromString(await response.text(), 'text/html');
      const updated = documentResponse.querySelector('[data-unified-results]');
      if (!updated) throw new Error('Missing directory results');
      if (id !== serial) return;
      // Only replace the result surface. Keep keyboard focus and typed query intact.
      results.replaceWith(updated);
      results = updated;
      applyColumns();
      const cleanURL = `${url.pathname}${url.search}`;
      if (push) history.pushState({directory: true}, '', cleanURL);
      else history.replaceState({directory: true}, '', cleanURL);
      updateExports(url);
      liveStatus.textContent = 'Results updated';
    } catch (error) {
      if (error.name === 'AbortError' || id !== serial) return;
      // A standard GET is always a working fallback for browser/network edge cases.
      location.assign(`${url.pathname}${url.search}`);
    } finally {
      if (id === serial) resetLoading();
    }
  }
  function queue() {
    clearTimeout(timer);
    // Invalidate the previous request as soon as the user types, not only
    // when the next debounced request is sent. Old results must never flash.
    if (controller) controller.abort();
    serial += 1;
    resetLoading();
    if (!form.checkValidity()) {
      liveStatus.textContent = 'Correct the filter before searching';
      return;
    }
    liveStatus.textContent = 'Searching…';
    timer = setTimeout(() => search(makeURL()), debounceMs);
  }
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    clearTimeout(timer);
    if (form.checkValidity()) search(makeURL(), {push: true});
  });
  form.addEventListener('input', (event) => {
    if (event.target.matches('input[type="search"], input[type="text"], input[type="number"]')) queue();
  });
  form.addEventListener('change', (event) => {
    if (event.target.matches('[data-column-toggle]')) {
      applyColumns();
      return;
    }
    if (event.target.matches('select')) {
      clearTimeout(timer);
      search(makeURL(), {push: true});
    }
  });
  form.addEventListener('click', (event) => {
    const reset = event.target.closest('[data-unified-reset]');
    if (!reset) return;
    event.preventDefault();
    clearTimeout(timer);
    location.assign(new URL(reset.href, location.href).pathname);
  });
  document.addEventListener('click', async (event) => {
    if (!event.target.closest('[data-unified-results]')) return;
    const pageLink = event.target.closest('.sourcing-pagination a');
    const statusLink = event.target.closest('.sourcing-status-strip a');
    if (pageLink || statusLink) {
      event.preventDefault();
      clearTimeout(timer);
      const dest = new URL((pageLink || statusLink).href, location.href);
      const url = makeURL();
      if (pageLink) {
        const nums = dest.searchParams.getAll('page');
        url.searchParams.set('page', nums[nums.length - 1] || '1');
      } else {
        const status = dest.searchParams.getAll('status').pop() || 'active';
        const select = form.querySelector('[name="status"]');
        if (select) select.value = status;
        url.searchParams.set('status', status);
      }
      search(url, {push: true});
      return;
    }
    const expand = event.target.closest('[data-provider-expand]');
    const capPage = event.target.closest('[data-cap-page]');
    if (!expand && !capPage) return;
    const row = (expand || capPage).closest('tr[data-provider-row]') ||
      (capPage && capPage.closest('[data-provider-row]'));
    // Buttons inside nested capability tables live inside the expansion row.
    const sourceRow = row || (capPage && capPage.closest('tr.sourcing-unified-expansion'));
    const provider = expand ? expand.dataset.providerExpand : sourceRow?.dataset.providerRow;
    const hostRow = sourceRow || results.querySelector(`[data-provider-row="${provider}"]`);
    if (!provider || !hostRow) return;
    const trigger = expand || results.querySelector(`[data-provider-expand="${provider}"]`);
    if (expand && trigger.getAttribute('aria-expanded') === 'true') {
      hostRow.hidden = true;
      trigger.setAttribute('aria-expanded', 'false');
      return;
    }
    const target = hostRow.querySelector('[data-capabilities-slot]');
    hostRow.hidden = false;
    if (trigger) trigger.setAttribute('aria-expanded', 'true');
    const url = makeURL();
    url.searchParams.set('fragment', 'capabilities');
    url.searchParams.set('provider', provider);
    url.searchParams.set('cap_page', capPage ? capPage.dataset.capPage : '1');
    target.setAttribute('aria-busy', 'true');
    target.textContent = 'Loading matching capabilities…';
    try {
      const response = await fetch(url, {credentials: 'same-origin'});
      if (!response.ok) throw new Error('Could not load company capabilities');
      target.innerHTML = await response.text();
    } catch (_) {
      target.textContent = 'Could not load capabilities. Open the company profile to continue.';
    } finally {
      target.removeAttribute('aria-busy');
    }
  });
  // For back/forward use the browser's normal GET navigation to restore all form state.
  window.addEventListener('popstate', () => location.reload());
  applyColumns();
})();
