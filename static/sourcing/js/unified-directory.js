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
  let modalController = null;
  let activeProvider = null;
  let activeTrigger = null;

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
          <div>
            <span class="sourcing-unified-modal__eyebrow" id="sourcing-capability-modal-kind">Capabilities</span>
            <h2 class="sourcing-unified-modal__title" id="sourcing-capability-modal-title">Capability details</h2>
            <p class="sourcing-unified-modal__subtitle" id="sourcing-capability-modal-subtitle">Browse matching items with pagination.</p>
          </div>
          <button type="button" class="sourcing-unified-modal__close" aria-label="Close dialog" data-modal-close>&times;</button>
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
      if (event.key === 'Escape' && modal.classList.contains('is-open')) closeModal();
    });
    return modal;
  }
  function openModal(trigger) {
    const modal = ensureModal();
    activeProvider = trigger.dataset.providerExpand;
    activeTrigger = trigger;
    modal.querySelector('#sourcing-capability-modal-title').textContent = trigger.dataset.providerLabel || 'Capability details';
    modal.querySelector('#sourcing-capability-modal-kind').textContent = trigger.dataset.providerKind || 'Capabilities';
    modal.querySelector('#sourcing-capability-modal-subtitle').textContent = 'Scroll through paginated capability records without leaving the directory.';
    modal.querySelector('[data-modal-content]').innerHTML = '<div class="sourcing-unified-modal__loading">Loading matching capabilities…</div>';
    modal.classList.add('is-open');
    document.body.style.overflow = 'hidden';
    if (activeTrigger) activeTrigger.setAttribute('aria-expanded', 'true');
  }
  function closeModal() {
    const modal = document.getElementById('sourcing-capability-modal');
    if (!modal) return;
    if (modalController) modalController.abort();
    modal.classList.remove('is-open');
    document.body.style.overflow = '';
    if (activeTrigger) activeTrigger.setAttribute('aria-expanded', 'false');
    activeProvider = null;
    activeTrigger = null;
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
    const capPage = event.target.closest('[data-cap-page]');
    if (capPage && activeProvider) {
      event.preventDefault();
      await loadCapabilities(activeProvider, capPage.dataset.capPage || '1');
    }
  });
  // For back/forward use the browser's normal GET navigation to restore all form state.
  window.addEventListener('popstate', () => location.reload());
  applyColumns();
})();
