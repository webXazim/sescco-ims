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
  liveStatus.className = 'sourcing-unified-live-status sr-only';
  liveStatus.setAttribute('role', 'status');
  liveStatus.setAttribute('aria-live', 'polite');
  form.appendChild(liveStatus);
  let controller = null;
  let timer = null;
  let serial = 0;
  const debounceMs = 320;
  let modalController = null;
  let activeProvider = null;
  let activeTrigger = null;
  let refreshOnReturn = false;

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
      // Keep PDF exports on their own endpoint/format, but send the same
      // live company filters and sorting used by the directory.
      if (link.hasAttribute('data-unified-export-pdf')) {
        dest.searchParams.delete('format');
        dest.searchParams.delete('unified');
      } else {
        // Excel exports still use the unified, company-first filter contract.
        dest.searchParams.set('unified', '1');
        dest.searchParams.set('format', 'xlsx');
      }
      link.href = dest.pathname + dest.search;
    });
  }
  // A directory-specific preference, independent of company filters, backed only by
  // optional browser storage. Server-rendered rows retain the correct default if JS fails.
  const columnToggles = [...form.querySelectorAll('[data-column-toggle]')];
  const columnKeys = columnToggles.map((toggle) => toggle.dataset.columnToggle);
  const columnStorageKey = `sescco:sourcing:directory-columns:v2:${location.pathname}`;
  const compactKeys = new Set(['provider', 'tags', 'capabilities', 'status', 'actions']);
  const readColumns = () => {
    try {
      const saved = JSON.parse(localStorage.getItem(columnStorageKey) || '{}');
      if (!saved || typeof saved !== 'object' || Array.isArray(saved)) return;
      columnToggles.forEach((toggle) => {
        if (typeof saved[toggle.dataset.columnToggle] === 'boolean') {
          toggle.checked = saved[toggle.dataset.columnToggle];
        }
      });
      // Never strand the user with a completely blank table.
      if (!columnToggles.some((toggle) => toggle.checked)) {
        columnToggles.forEach((toggle) => { toggle.checked = true; });
      }
    } catch (_) { /* private browsing or unavailable local storage */ }
  };
  const saveColumns = () => {
    try {
      const state = Object.fromEntries(columnToggles.map((toggle) => [toggle.dataset.columnToggle, toggle.checked]));
      localStorage.setItem(columnStorageKey, JSON.stringify(state));
    } catch (_) { /* preference is still active in this page */ }
  };
  function applyColumns() {
    const table = results.querySelector('[data-vendor-table], [data-manpower-table], [data-subcontractor-table]');
    if (!table) return;
    columnToggles.forEach((toggle) => {
      table.querySelectorAll(`[data-column="${toggle.dataset.columnToggle}"]`)
        .forEach((cell) => { cell.hidden = !toggle.checked; });
    });
    const visible = columnToggles.filter((toggle) => toggle.checked).length;
    const count = form.querySelector('[data-column-count]');
    if (count) count.textContent = `${visible} of ${columnKeys.length}`;
    // Empty-result messages occupy all visible columns, never a fixed width.
    table.querySelectorAll('td[colspan]').forEach((cell) => { cell.colSpan = visible; });
  }
  function setColumnPreset(preset) {
    columnToggles.forEach((toggle) => {
      toggle.checked = preset === 'all' || compactKeys.has(toggle.dataset.columnToggle);
    });
    saveColumns();
    applyColumns();
  }
  readColumns();
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
      if (!columnToggles.some((toggle) => toggle.checked)) {
        event.target.checked = true;
        liveStatus.textContent = 'At least one column must remain visible';
      }
      saveColumns();
      applyColumns();
      return;
    }
    if (event.target.matches('select')) {
      clearTimeout(timer);
      search(makeURL(), {push: true});
    }
  });
  form.addEventListener('click', (event) => {
    if (event.target.closest('[data-columns-all]')) {
      event.preventDefault();
      setColumnPreset('all');
      return;
    }
    if (event.target.closest('[data-columns-compact]')) {
      event.preventDefault();
      setColumnPreset('compact');
      return;
    }
    const reset = event.target.closest('[data-unified-reset]');
    if (!reset) return;
    event.preventDefault();
    clearTimeout(timer);
    location.assign(new URL(reset.href, location.href).pathname);
  });

  function ensureModal() {
    let modal = document.getElementById('sourcing-capability-modal');
    if (modal) return modal;
    modal = document.createElement('div');
    modal.id = 'sourcing-capability-modal';
    modal.className = 'sourcing-unified-modal';
    modal.setAttribute('role', 'dialog');
    modal.setAttribute('aria-modal', 'true');
    modal.setAttribute('aria-labelledby', 'sourcing-capability-modal-title');
    modal.innerHTML = `
      <div class="sourcing-unified-modal__backdrop" data-modal-close></div>
      <div class="sourcing-unified-modal__dialog">
        <div class="sourcing-unified-modal__header">
          <div class="sourcing-unified-modal__identity">
            <span class="sourcing-unified-modal__eyebrow" id="sourcing-capability-modal-kind">Capabilities</span>
            <h2 class="sourcing-unified-modal__title" id="sourcing-capability-modal-title">Capability details</h2>
          </div>
          <div class="sourcing-unified-modal__header-controls">
            <div class="sourcing-unified-modal__header-tools" data-modal-header-tools></div>
            <button type="button" class="sourcing-unified-modal__close" aria-label="Close dialog" data-modal-close>&times;</button>
          </div>
        </div>
        <div class="sourcing-unified-modal__body">
          <div class="sourcing-unified-modal__content" data-modal-content>
            <div class="sourcing-unified-modal__loading">Loading matching capabilities…</div>
          </div>
        </div>
      </div>`;
    document.body.appendChild(modal);
    modal.addEventListener('click', (event) => {
      if (event.target.closest('[data-modal-close]')) closeModal();
    });
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && !document.querySelector('.sourcing-capability-editor.is-open') && !document.querySelector('.sourcing-reference-dialog[open]') && modal.classList.contains('is-open')) closeModal();
    });
    return modal;
  }
  function openModal(trigger) {
    const modal = ensureModal();
    activeProvider = trigger.dataset.providerExpand;
    activeTrigger = trigger;
    refreshOnReturn = false;
    modal.querySelector('#sourcing-capability-modal-title').textContent = trigger.dataset.providerLabel || 'Capability details';
    modal.querySelector('#sourcing-capability-modal-kind').textContent = trigger.dataset.providerKind || 'Capabilities';
    modal.querySelector('[data-modal-header-tools]').replaceChildren();
    modal.querySelector('[data-modal-content]').innerHTML = '<div class="sourcing-unified-modal__loading">Loading matching capabilities…</div>';
    modal.classList.add('is-open');
    document.body.style.overflow = 'hidden';
    if (activeTrigger) activeTrigger.setAttribute('aria-expanded', 'true');
  }
  function closeModal() {
    const modal = document.getElementById('sourcing-capability-modal');
    if (!modal) return;
    if (document.querySelector('.sourcing-capability-editor.is-open')) { window.SourcingCapabilityEditor?.close(); return; }
    if (modalController) modalController.abort();
    modal.classList.remove('is-open');
    document.body.style.overflow = '';
    if (activeTrigger) activeTrigger.setAttribute('aria-expanded', 'false');
    activeProvider = null;
    activeTrigger = null;
    refreshOnReturn = false;
  }
  async function loadCapabilities(provider, page = '1') {
    const modal = ensureModal();
    const target = modal.querySelector('[data-modal-content]');
    if (modalController) modalController.abort();
    modalController = new AbortController();
    target.innerHTML = '<div class="sourcing-unified-modal__loading">Loading matching capabilities…</div>';
    const url = makeURL();
    url.searchParams.set('fragment', 'capabilities');
    url.searchParams.set('provider', provider);
    url.searchParams.set('cap_page', page);
    try {
      const response = await fetch(url, {credentials: 'same-origin', signal: modalController.signal});
      if (!response.ok) throw new Error('Could not load company capabilities');
      target.innerHTML = await response.text();
      // Put server-authorized actions in the actual modal header; do not derive
      // permissions or create URLs on the client.
      const tools = target.querySelector('.sourcing-unified-cap-tools');
      const headerTools = modal.querySelector('[data-modal-header-tools]');
      headerTools.replaceChildren();
      if (tools) headerTools.append(...tools.children);
    } catch (error) {
      if (error.name === 'AbortError') return;
      target.innerHTML = '<div class="sourcing-unified-modal__empty">Could not load capabilities. Open the company profile to continue.</div>';
    }
  }

  document.addEventListener('click', async (event) => {
    if (!event.target.closest('[data-unified-results], #sourcing-capability-modal')) return;
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
    if (expand) {
      event.preventDefault();
      openModal(expand);
      await loadCapabilities(expand.dataset.providerExpand, '1');
      return;
    }
    // Reuse the complete audited create form inside a modal (ordinary href is
    // still a working fallback when JavaScript is disabled).
    const createAction = event.target.closest('[data-capability-create]');
    if (createAction && activeProvider) {
      event.preventDefault();
      window.SourcingCapabilityEditor?.open(createAction, {onSaved: () => {
        if (activeProvider) loadCapabilities(activeProvider,'1');
        search(makeURL());
      }});
      return;
    }
    if (event.target.closest('[data-capability-refresh]') && activeProvider) {
      event.preventDefault();
      refreshOnReturn = false;
      const currentPage = document.querySelector('#sourcing-capability-modal [data-capabilities-list]')
        ?.getAttribute('data-current-page') || '1';
      await loadCapabilities(activeProvider, currentPage);
      return;
    }
    const capPage = event.target.closest('[data-cap-page]');
    if (capPage && activeProvider) {
      event.preventDefault();
      await loadCapabilities(activeProvider, capPage.dataset.capPage || '1');
    }
  });
  // The user may have created a capability in the new tab. Refresh matching
  // results when they return; pagination/filter state remains server-authoritative.
  window.addEventListener('focus', () => {
    if (!refreshOnReturn || !activeProvider || !document.getElementById('sourcing-capability-modal')?.classList.contains('is-open')) return;
    refreshOnReturn = false;
    loadCapabilities(activeProvider, '1');
  });
  // For back/forward use the browser's normal GET navigation to restore all form state.
  window.addEventListener('popstate', () => location.reload());
  applyColumns();
})();
