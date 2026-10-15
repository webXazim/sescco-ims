/* Shared progressive master-data lookup for Material, Workforce and Service capability forms.
 * Independent of jQuery/select plugins; never downloads the entire master list.
 */
(() => {
  'use strict';
  const titles = {
    material: 'Sourcing Material',
    trade: 'Worker Type / Trade',
    service: 'Sourcing Service',
  };
  function csrfToken(root) {
    return root.closest('form')?.querySelector('[name="csrfmiddlewaretoken"]')?.value || '';
  }
  function message(element, value) { element.textContent = value; }

  // The dialog receives the very same Django ModelForm sections used on the
  // standalone master-data creation/edit screens, instead of maintaining a
  // second, incomplete form definition in JavaScript.
  async function dialogFor(root, done) {
    const kind = root.dataset.kind;
    if (!Object.prototype.hasOwnProperty.call(titles, kind)) return;
    const dialog = document.createElement('dialog');
    dialog.className = 'sourcing-reference-dialog';
    const panel = document.createElement('form');
    panel.method = 'post';
    panel.className = 'sourcing-reference-dialog-form';
    const heading = document.createElement('div');
    heading.className = 'sourcing-reference-dialog-heading';
    const title = document.createElement('h2');
    title.id = 'sourcing-reference-modal-title';
    title.textContent = `Add ${titles[kind]}`;
    dialog.setAttribute('aria-labelledby', title.id);
    const closeButton = document.createElement('button');
    closeButton.type = 'button';
    closeButton.className = 'sourcing-reference-dialog-close';
    closeButton.setAttribute('aria-label', 'Close reference dialog');
    closeButton.textContent = '×';
    heading.append(title, closeButton);
    const content = document.createElement('div');
    content.className = 'sourcing-reference-dialog-content';
    content.textContent = 'Loading reference fields…';
    const errors = document.createElement('div');
    errors.className = 'sourcing-reference-modal-error';
    errors.setAttribute('role', 'alert');
    errors.setAttribute('aria-live', 'polite');
    const actions = document.createElement('div');
    actions.className = 'sourcing-reference-modal-actions';
    const cancel = document.createElement('button');
    cancel.type = 'button'; cancel.className = 'sourcing-btn'; cancel.textContent = 'Cancel';
    const save = document.createElement('button');
    save.type = 'submit'; save.className = 'sourcing-btn sourcing-btn--primary';
    save.textContent = `Create ${titles[kind]}`; save.disabled = true;
    actions.append(cancel, save);
    panel.append(heading, content, errors, actions);
    dialog.append(panel);
    document.body.append(dialog);
    const actor = document.querySelector('.platform-account__copy strong, .platform-account__identity strong')?.textContent?.trim() || 'unknown';
    const company = root.closest('form')?.dataset.sourcingCompany || 'no-company';
    const draftKey = `sescco:sourcing:reference-modal:v1:${encodeURIComponent(actor)}:${encodeURIComponent(company)}:${location.pathname}:${kind}`;
    let baseline = null, closing = false, savedDraft = null, debounce;
    const ttl = 24 * 60 * 60 * 1000;
    function formValues() {
      return [...panel.querySelectorAll('input[name],select[name],textarea[name]')].map(el => ({
        name: el.name, value: el.value,
        checked: ['checkbox', 'radio'].includes(el.type) ? el.checked : null,
      }));
    }
    function changed() { return baseline !== null && JSON.stringify(formValues()) !== baseline; }
    function preserve() {
      if (closing || !changed()) return;
      try {
        const state = { v: 1, actor, company, path: location.pathname, kind,
          updated: Date.now(), values: formValues() };
        const payload = JSON.stringify(state);
        if (payload.length < 30000) sessionStorage.setItem(draftKey, payload);
      } catch (_) { /* private browsing: the form remains editable */ }
    }
    function clearDraft() { try { sessionStorage.removeItem(draftKey); } catch (_) { /* unavailable */ } }
    try {
      const raw = sessionStorage.getItem(draftKey);
      if (raw) {
        const entry = JSON.parse(raw);
        if (entry.v === 1 && entry.actor === actor && entry.company === company && entry.kind === kind &&
            entry.path === location.pathname && Date.now() - entry.updated < ttl) savedDraft = entry;
        else clearDraft();
      }
    } catch (_) { /* optional restoration */ }
    const confirm = document.createElement('div');
    confirm.className = 'sourcing-reference-discard-confirm';
    confirm.hidden = true;
    confirm.setAttribute('role', 'alertdialog');
    confirm.setAttribute('aria-modal', 'true');
    confirm.setAttribute('aria-label', `Discard ${titles[kind]} changes`);
    confirm.innerHTML = `<div class="sourcing-reference-discard-card">
      <h3>Discard unsaved changes?</h3>
      <p>Your ${titles[kind].toLowerCase()} details have not been saved.</p>
      <div class="sourcing-reference-discard-actions">
        <button type="button" class="sourcing-btn sourcing-btn--primary" data-reference-keep>Keep editing</button>
        <button type="button" class="sourcing-btn sourcing-reference-discard" data-reference-discard>Discard changes</button>
      </div></div>`;
    panel.append(confirm);
    const finish = (discardDraft) => {
      closing = true;
      clearTimeout(debounce);
      if (discardDraft) clearDraft();
      dialog.close();
    };
    function requestClose() {
      if (!changed()) { finish(true); return; }
      preserve();
      confirm.hidden = false;
      confirm.querySelector('[data-reference-keep]').focus();
    }
    confirm.querySelector('[data-reference-keep]').addEventListener('click', () => {
      confirm.hidden = true;
      content.querySelector('[name="master-name"]')?.focus();
    });
    confirm.querySelector('[data-reference-discard]').addEventListener('click', () => finish(true));
    cancel.addEventListener('click', requestClose);
    dialog.addEventListener('click', event => { if (event.target === dialog) requestClose(); });
    dialog.addEventListener('cancel', event => {
      event.preventDefault();
      if (confirm.hidden) requestClose();
      else confirm.hidden = true;
    });
    content.addEventListener('input', () => { clearTimeout(debounce); debounce = setTimeout(preserve, 180); });
    content.addEventListener('change', () => { clearTimeout(debounce); preserve(); });
    const onUnload = event => {
      preserve();
      if (changed()) { event.preventDefault(); event.returnValue = ''; }
    };
    window.addEventListener('beforeunload', onUnload);
    window.addEventListener('pagehide', preserve);
    dialog.addEventListener('close', () => {
      window.removeEventListener('beforeunload', onUnload);
      window.removeEventListener('pagehide', preserve);
      dialog.remove();
    }, { once: true });
    dialog.showModal();

    const controller = new AbortController();
    dialog.addEventListener('close', () => controller.abort(), { once: true });
    function syncCategories() {
      content.querySelectorAll('[data-material-category-scope]').forEach(scope => {
        const select = scope.querySelector('[data-material-category-select]');
        const field = scope.querySelector('[data-new-material-category-field]');
        const input = field?.querySelector('[data-new-material-category-input]');
        if (!select || !field) return;
        const isNew = select.value === '__new__';
        field.hidden = !isNew;
        if (input) input.required = isNew;
      });
    }
    content.addEventListener('change', event => {
      if (event.target.matches('[data-material-category-select]')) syncCategories();
    });
    function clearErrors() {
      errors.textContent = '';
      content.querySelectorAll('[data-inline-error]').forEach(node => node.remove());
      content.querySelectorAll('[aria-invalid="true"]').forEach(node => node.removeAttribute('aria-invalid'));
    }
    function displayErrors(payload) {
      clearErrors();
      const errorData = payload.errors || {};
      let firstInvalid = null;
      for (const [fieldName, messages] of Object.entries(errorData)) {
        const details = (Array.isArray(messages) ? messages : [messages])
          .map(entry => typeof entry === 'string' ? entry : (entry?.message || 'Invalid value.'));
        // Restrict lookup to a real form control name; never construct HTML
        // from a server error message.
        const input = [...panel.elements].find(element => element.name === `master-${fieldName}`);
        if (input) {
          input.setAttribute('aria-invalid', 'true');
          const field = input.closest('.sourcing-field');
          if (field) {
            const error = document.createElement('div');
            error.className = 'field-error';
            error.dataset.inlineError = '';
            error.textContent = details.join(' ');
            field.append(error);
            firstInvalid ||= input;
            continue;
          }
        }
        errors.textContent += `${fieldName === '__all__' ? 'Error' : fieldName}: ${details.join(' ')}\n`;
      }
      if (!Object.keys(errorData).length) errors.textContent = payload.error || 'Unable to save the reference.';
      firstInvalid?.focus();
    }
    try {
      const url = new URL(root.dataset.endpoint, window.location.href);
      url.searchParams.set('form', '1');
      const response = await fetch(url, {
        credentials: 'same-origin', cache: 'no-store', signal: controller.signal,
        headers: { 'Accept': 'text/html' },
      });
      if (!response.ok) throw new Error(response.status === 403
        ? 'You do not have permission to create reference records.'
        : 'Unable to load the reference form. Please try again.');
      const markup = await response.text();
      if (!dialog.isConnected) return;
      const scratch = document.createElement('div');
      scratch.innerHTML = markup;
      const fields = scratch.querySelector('[data-reference-master-fields]');
      if (!fields || fields.dataset.referenceMasterFields !== kind) {
        throw new Error('The reference form could not be loaded. Please refresh and try again.');
      }
      content.replaceChildren(fields);
      syncCategories();
      baseline = JSON.stringify(formValues());
      if (savedDraft?.values?.length) {
        const inputMap = new Map(formValues().map(v => [v.name, panel.elements.namedItem(v.name)]));
        savedDraft.values.forEach(saved => {
          const element = inputMap.get(saved.name);
          if (!element) return;
          if (saved.checked !== null && saved.checked !== undefined) element.checked = !!saved.checked;
          else if (element.tagName === 'SELECT' && ![...element.options].some(opt => opt.value === saved.value)) return;
          else element.value = String(saved.value ?? '');
        });
        syncCategories();
        const restored = document.createElement('div');
        restored.className = 'sourcing-reference-restored';
        restored.setAttribute('role', 'status');
        restored.textContent = 'Unsaved reference draft restored after reload.';
        content.prepend(restored);
      }
      save.disabled = false;
      content.querySelector('[name="master-name"]')?.focus();
    } catch (exc) {
      if (exc.name === 'AbortError' || !dialog.isConnected) return;
      content.textContent = '';
      errors.textContent = exc.message || 'Unable to open the reference form.';
      return;
    }
    panel.addEventListener('submit', async event => {
      event.preventDefault();
      if (!panel.reportValidity()) return;
      clearErrors();
      save.disabled = true;
      try {
        const response = await fetch(root.dataset.endpoint, {
          method: 'POST', credentials: 'same-origin',
          headers: { 'X-CSRFToken': csrfToken(root), 'Accept': 'application/json' },
          body: new FormData(panel),
        });
        const data = await response.json();
        if (!response.ok) {
          displayErrors(data);
          return;
        }
        if (!data.item?.id) throw new Error('Invalid server response.');
        finish(true);
        done(data.item);
      } catch (exc) {
        errors.textContent = exc.message || 'Unable to save the reference. Please try again.';
      } finally {
        if (dialog.isConnected) save.disabled = false;
      }
    });
  }
  function initialize(root) {
    if (root.dataset.referenceInitialized === '1') return;
    const hidden = root.querySelector('input[type="hidden"]');
    const search = root.querySelector('[data-reference-search]');
    const current = root.querySelector('[data-reference-current]');
    const options = root.querySelector('[data-reference-options]');
    const help = root.querySelector('[data-reference-help]');
    if (!hidden || !search || !options) return;
    root.dataset.referenceInitialized = '1';
    let requestId = 0;
    let controller;
    let timeout;
    let activeIndex = -1;
    let selectable = [];
    let selected = null;
    const clearOptions = () => { options.replaceChildren(); selectable = []; activeIndex = -1; };
    const selectedLabel = item => `${item.name} · ${item.code}`;
    function choose(item) {
      selected = item;
      hidden.value = item.id;
      search.value = '';
      current.replaceChildren();
      const chip = document.createElement('span'); chip.className = 'sourcing-reference-selected';
      chip.textContent = selectedLabel(item);
      const clear = document.createElement('button'); clear.type = 'button';
      clear.className = 'sourcing-reference-clear'; clear.textContent = 'Change';
      clear.setAttribute('aria-label', `Change ${item.name}`);
      clear.addEventListener('click', () => {
        selected = null; hidden.value = ''; current.replaceChildren(); search.hidden = false;
        help.textContent = 'Commonly used items appear first. Type to search the entire company reference list.';
        search.setAttribute('aria-expanded', 'true'); search.focus(); load('');
      });
      current.append(chip, clear);
      help.textContent = 'Selected reference. Select Change to choose another item.';
      options.hidden = true; search.hidden = true;
      hidden.dispatchEvent(new Event('change', { bubbles: true }));
      hidden.dispatchEvent(new Event('sourcing:reference-selected', { bubbles: true }));
    }
    function listItems(items, query, {append = false, hasMore = false, page = 1} = {}) {
      if (!append) clearOptions();
      else options.querySelector('[data-reference-more]')?.remove();
      options.hidden = false;
      search.setAttribute('aria-expanded', 'true');
      if (!items.length && !append) {
        const info = document.createElement('div');
        info.className = 'sourcing-reference-status';
        info.textContent = query ? 'No matching reference. Try another term or add a new one.' : 'No references available. Add the first item if permitted.';
        options.append(info); return;
      }
      for (const item of items) {
        const option = document.createElement('button');
        option.type = 'button'; option.setAttribute('role', 'option');
        option.className = 'sourcing-reference-option';
        option.setAttribute('aria-selected', 'false');
        option.textContent = item.name;
        const meta = document.createElement('span'); meta.textContent = [item.code, item.category].filter(Boolean).join(' · ');
        option.append(meta);
        option.addEventListener('click', () => choose(item));
        options.append(option); selectable.push({ element: option, item });
      }
      if (hasMore && query) {
        const more = document.createElement('button');
        more.type = 'button'; more.dataset.referenceMore = '';
        more.className = 'sourcing-reference-more';
        more.textContent = 'Load more results';
        more.addEventListener('click', () => load(query, '', true, page + 1));
        options.append(more);
      }
      help.textContent = query ? 'Matching references · refine your search to narrow results.' : 'Commonly used references · type to search the complete catalog.';
    }
    function highlight(index) {
      activeIndex = index;
      selectable.forEach(({ element }, i) => {
        element.classList.toggle('is-active', i === index);
        element.setAttribute('aria-selected', String(i === index));
      });
      if (index >= 0) selectable[index].element.scrollIntoView({ block: 'nearest' });
    }
    async function load(q = '', selectedId = '', append = false, page = 1) {
      const token = ++requestId;
      if (controller) controller.abort();
      controller = new AbortController();
      options.hidden = false;
      if (!append) { clearOptions(); message(options, 'Searching references…'); }
      else options.querySelector('[data-reference-more]')?.remove();
      const url = new URL(root.dataset.endpoint, window.location.href);
      if (selectedId) url.searchParams.set('selected', selectedId);
      else if (q) {
        url.searchParams.set('q', q.slice(0, 80));
        if (page > 1) url.searchParams.set('page', String(page));
      }
      try {
        const response = await fetch(url, { credentials: 'same-origin', signal: controller.signal, headers: { 'Accept': 'application/json' } });
        if (!response.ok) throw new Error('Search is currently unavailable.');
        const result = await response.json();
        if (token !== requestId) return;
        if (selectedId && result.results?.length) { choose(result.results[0]); return; }
        listItems(result.results || [], q, {append, hasMore: !!result.has_more, page: result.page || page});
      } catch (error) {
        if (error.name === 'AbortError' || token !== requestId) return;
        if (append) {
          const retry = document.createElement('button');
          retry.type = 'button'; retry.className = 'sourcing-reference-more';
          retry.textContent = 'Could not load results · Retry';
          retry.addEventListener('click', () => load(q, '', true, page));
          options.append(retry);
        } else message(options, 'Unable to load references. Check your connection and retry.');
      }
    }
    search.addEventListener('input', () => {
      window.clearTimeout(timeout);
      if (controller) controller.abort();
      timeout = window.setTimeout(() => load(search.value.trim()), 250);
    });
    search.addEventListener('keydown', event => {
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        if (!selectable.length) return;
        event.preventDefault();
        highlight(event.key === 'ArrowDown' ? Math.min(activeIndex + 1, selectable.length - 1) : Math.max(activeIndex - 1, 0));
      } else if (event.key === 'Enter') {
        event.preventDefault();
        if (activeIndex >= 0 && selectable[activeIndex]) choose(selectable[activeIndex].item);
        else if (selectable.length === 1) choose(selectable[0].item);
      } else if (event.key === 'Escape') {
        search.blur(); options.hidden = true; search.setAttribute('aria-expanded', 'false');
      }
    });
    search.addEventListener('focus', () => {
      if (!hidden.value) { options.hidden = false; search.setAttribute('aria-expanded', 'true'); }
    });
    root.addEventListener('sourcing:reference-lookup-restore', event => {
      const selectedId = String(event.detail?.selectedId || '');
      if (selectedId) load('', selectedId);
    });
    root.querySelector('[data-reference-add]')?.addEventListener('click', () => dialogFor(root, choose));
    if (root.closest('form[data-sourcing-page-draft]')) {
      const actor = document.querySelector('.platform-account__copy strong, .platform-account__identity strong')?.textContent?.trim() || 'unknown';
      const company = root.closest('form')?.dataset.sourcingCompany || 'no-company';
      const key = `sescco:sourcing:reference-modal:v1:${encodeURIComponent(actor)}:${encodeURIComponent(company)}:${location.pathname}:${root.dataset.kind}`;
      try {
        const entry = JSON.parse(sessionStorage.getItem(key) || 'null');
        if (entry?.v === 1 && entry.actor === actor && Date.now() - entry.updated < 86400000 &&
            entry.path === location.pathname && entry.values?.length) {
          setTimeout(() => dialogFor(root, choose), 80);
        }
      } catch (_) { /* session storage unavailable */ }
    }
    // Server-side errors restore the posted selection, including a reference not in the top twelve.
    if (hidden.value) load('', hidden.value);
    else load('');
  }
  document.querySelectorAll('[data-sourcing-reference-lookup]').forEach(initialize);
  document.addEventListener('sourcing:reference-lookup-mount', event => {
    (event.detail?.root || document).querySelectorAll('[data-sourcing-reference-lookup]').forEach(initialize);
  });
})();
