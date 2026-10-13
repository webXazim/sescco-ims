/* Bounded, server-filtered sourcing catalog tables (one URL per sourcing directory).
   Progressive enhancement: every filter also works as a standard GET form. */
(() => {
  let activeController = null;
  let requestSerial = 0;
  let debounce = null;

  function getRoot() {
    return document.querySelector('[data-sourcing-finder-root]');
  }

  function updateExport(url) {
    const link = document.querySelector('[data-sourcing-export-current]');
    if (!link) return;
    const next = new URL(link.href, window.location.origin);
    const filters = new URL(url, window.location.origin);
    next.search = filters.search;
    next.searchParams.set('format', 'xlsx');
    link.href = `${next.pathname}${next.search}`;
  }

  function install(root) {
    const form = root.querySelector('form[data-sourcing-live-finder]');
    if (!form || form.dataset.scaleBound === '1') return;
    form.dataset.scaleBound = '1';

    function formUrl() {
      const url = new URL(form.action, location.origin);
      const data = new FormData(form);
      data.delete('page');
      for (const [key, value] of data.entries()) {
        if (String(value).trim()) url.searchParams.set(key, String(value));
      }
      url.searchParams.set('view', 'offers');
      return `${url.pathname}${url.search}`;
    }

    async function run(url, { push = true, expectFormState = false } = {}) {
      if (activeController) activeController.abort();
      const controller = new AbortController();
      activeController = controller;
      const serial = ++requestSerial;
      const active = document.activeElement;
      const field = form.contains(active) && active.name ? active.name : null;
      let caret = null;
      try {
        if (field && active instanceof HTMLInputElement && ['search', 'text'].includes(active.type)) {
          caret = [active.selectionStart, active.selectionEnd];
        }
      } catch (_) { /* Some input types do not expose a selection range. */ }
      root.dataset.loading = '1';
      root.setAttribute('aria-busy', 'true');
      try {
        const response = await fetch(url, {
          credentials: 'same-origin',
          headers: { 'X-Requested-With': 'sourcing-finder-scale' },
          signal: controller.signal,
        });
        if (!response.ok) throw new Error(`Directory search failed: ${response.status}`);
        const html = await response.text();
        if (serial !== requestSerial || !root.isConnected ||
            (expectFormState && formUrl() !== url)) return;
        const parsed = new DOMParser().parseFromString(html, 'text/html');
        const replacement = parsed.querySelector('[data-sourcing-finder-root]');
        if (!replacement) throw new Error('Search response did not contain results.');
        root.replaceWith(replacement);
        if (push) history.pushState({ sourcingCatalog: true }, '', url);
        else history.replaceState({ sourcingCatalog: true }, '', url);
        updateExport(url);
        install(replacement);
        if (field) {
          const replacementField = [...replacement.querySelectorAll('input,select')]
            .find((element) => element.name === field);
          if (replacementField) {
            replacementField.focus({ preventScroll: true });
            if (caret && typeof replacementField.setSelectionRange === 'function') {
              replacementField.setSelectionRange(caret[0], caret[1]);
            }
          }
        }
      } catch (error) {
        if (error.name !== 'AbortError' && serial === requestSerial) {
          // Fallback retains all filtering even when JavaScript/network parsing fails.
          location.assign(url);
        }
      } finally {
        if (root.isConnected) {
          delete root.dataset.loading;
          root.removeAttribute('aria-busy');
        }
      }
    }

    function queueSearch() {
      clearTimeout(debounce);
      debounce = setTimeout(() => run(formUrl(), { push: false, expectFormState: true }), 650);
    }

    form.addEventListener('submit', (event) => {
      event.preventDefault();
      clearTimeout(debounce);
      run(formUrl(), { push: true });
    });
    form.addEventListener('input', (event) => {
      const input = event.target;
      if (input instanceof HTMLInputElement && ['search', 'number', 'text'].includes(input.type)) {
        queueSearch();
      }
    });
    form.addEventListener('change', (event) => {
      if (event.target instanceof HTMLSelectElement) {
        clearTimeout(debounce);
        run(formUrl(), { push: true });
      }
    });
    root.addEventListener('click', (event) => {
      const link = event.target.closest('.sourcing-pagination a');
      if (!link) return;
      const url = new URL(link.href, location.origin);
      if (url.origin !== location.origin || url.pathname !== location.pathname) return;
      event.preventDefault();
      clearTimeout(debounce);
      run(`${url.pathname}${url.search}`, { push: true });
    });
  }

  const root = getRoot();
  if (root) install(root);
  window.addEventListener('popstate', () => location.reload());
})();
