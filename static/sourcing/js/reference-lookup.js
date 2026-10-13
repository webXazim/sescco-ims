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
    const description = document.createElement('p');
    description.textContent = 'Create a controlled sourcing reference without leaving your capability form.';
    heading.append(title, description);
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
    dialog.addEventListener('close', () => dialog.remove(), { once: true });
    cancel.addEventListener('click', () => dialog.close());
    dialog.addEventListener('click', (event) => {
      if (event.target === dialog) dialog.close();
    });
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
        dialog.close();
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
    }
    function listItems(items, query) {
      clearOptions();
      options.hidden = false;
      search.setAttribute('aria-expanded', 'true');
      if (!items.length) {
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
      help.textContent = query ? 'Search results. Choose the correct controlled item.' : 'Frequently used references shown first; search to find any other item.';
    }
    function highlight(index) {
      activeIndex = index;
      selectable.forEach(({ element }, i) => {
        element.classList.toggle('is-active', i === index);
        element.setAttribute('aria-selected', String(i === index));
      });
      if (index >= 0) selectable[index].element.scrollIntoView({ block: 'nearest' });
    }
    async function load(q = '', selectedId = '') {
      const token = ++requestId;
      if (controller) controller.abort();
      controller = new AbortController();
      options.hidden = false;
      clearOptions();
      message(options, 'Searching references…');
      const url = new URL(root.dataset.endpoint, window.location.href);
      if (selectedId) url.searchParams.set('selected', selectedId);
      else if (q) url.searchParams.set('q', q.slice(0, 80));
      try {
        const response = await fetch(url, { credentials: 'same-origin', signal: controller.signal, headers: { 'Accept': 'application/json' } });
        if (!response.ok) throw new Error('Search is currently unavailable.');
        const result = await response.json();
        if (token !== requestId) return;
        if (selectedId && result.results?.length) { choose(result.results[0]); return; }
        listItems(result.results || [], q);
      } catch (error) {
        if (error.name === 'AbortError' || token !== requestId) return;
        message(options, 'Unable to load references. Check your connection and retry.');
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
    root.querySelector('[data-reference-add]')?.addEventListener('click', () => dialogFor(root, choose));
    // Server-side errors restore the posted selection, including a reference not in the top twelve.
    if (hidden.value) load('', hidden.value);
    else load('');
  }
  document.querySelectorAll('[data-sourcing-reference-lookup]').forEach(initialize);
  document.addEventListener('sourcing:reference-lookup-mount', event => {
    (event.detail?.root || document).querySelectorAll('[data-sourcing-reference-lookup]').forEach(initialize);
  });
})();
