/* Shared progressive master-data lookup for Material, Workforce and Service capability forms.
 * Independent of jQuery/select plugins; never downloads the entire master list.
 */
(() => {
  'use strict';
  const configurations = {
    material: { title: 'Sourcing Material', extra: [['default_unit', 'Default unit', 'e.g. pcs, box, kg']] },
    trade: { title: 'Worker Type / Trade', extra: [] },
    service: { title: 'Sourcing Service', extra: [['description', 'Service description', 'Optional scope definition']] },
  };
  function csrfToken(root) {
    return root.closest('form')?.querySelector('[name="csrfmiddlewaretoken"]')?.value || '';
  }
  function message(element, value) { element.textContent = value; }
  function dialogFor(root, done) {
    const kind = root.dataset.kind;
    const config = configurations[kind];
    const dialog = document.createElement('dialog');
    dialog.className = 'sourcing-reference-dialog';
    const panel = document.createElement('form');
    panel.method = 'post';
    panel.className = 'sourcing-reference-dialog-form';
    const title = document.createElement('h2');
    title.textContent = `Add ${config.title}`;
    panel.append(title);
    const description = document.createElement('p');
    description.textContent = 'Create a company-wide sourcing reference item without leaving this capability form.';
    panel.append(description);
    const controls = [];
    function field(name, label, placeholder, required = false) {
      const wrapper = document.createElement('label');
      wrapper.className = 'sourcing-reference-modal-field';
      const text = document.createElement('span'); text.textContent = label;
      const input = document.createElement('input');
      input.type = 'text'; input.name = name; input.className = 'sourcing-input';
      input.placeholder = placeholder; input.maxLength = name === 'name' ? 200 : 120;
      input.required = required;
      wrapper.append(text, input);
      panel.append(wrapper); controls.push(input);
      return input;
    }
    const nameInput = field('name', `${config.title} name`, 'Enter a clear controlled name', true);
    field('category', 'Category / type (optional)', 'e.g. Electrical, HVAC, Civil');
    for (const [key, label, placeholder] of config.extra) field(key, label, placeholder);
    const aliasLabel = document.createElement('label');
    aliasLabel.className = 'sourcing-reference-modal-field';
    const aliasTitle = document.createElement('span'); aliasTitle.textContent = 'Search aliases (optional)';
    const aliases = document.createElement('textarea');
    aliases.name = 'aliases'; aliases.className = 'sourcing-input';
    aliases.rows = 2; aliases.maxLength = 500;
    aliases.placeholder = 'Alternative names, one per line';
    aliasLabel.append(aliasTitle, aliases); panel.append(aliasLabel); controls.push(aliases);
    if (kind === 'service') {
      const basisLabel = document.createElement('label');
      basisLabel.className = 'sourcing-reference-modal-field';
      const basisTitle = document.createElement('span'); basisTitle.textContent = 'Default quotation basis (optional)';
      const select = document.createElement('select');
      select.className = 'sourcing-input'; select.name = 'default_rate_basis';
      const basisOptions = [['', 'Not specified'], ['hour', 'Hour'], ['day', 'Day'],
        ['visit', 'Visit'], ['job', 'Job'], ['m2', 'Square metre'], ['m3', 'Cubic metre'],
        ['month', 'Month'], ['quotation', 'Quotation']];
      for (const [value, label] of basisOptions) {
        const option = document.createElement('option'); option.value = value;
        option.textContent = label; select.append(option);
      }
      basisLabel.append(basisTitle, select); panel.append(basisLabel); controls.push(select);
    }
    const error = document.createElement('div');
    error.className = 'sourcing-reference-modal-error'; error.setAttribute('role', 'alert');
    panel.append(error);
    const actions = document.createElement('div');
    actions.className = 'sourcing-reference-modal-actions';
    const cancel = document.createElement('button');
    cancel.className = 'sourcing-btn'; cancel.type = 'button'; cancel.textContent = 'Cancel';
    const save = document.createElement('button');
    save.className = 'sourcing-btn sourcing-btn--primary'; save.type = 'submit';
    save.textContent = `Create ${config.title}`;
    actions.append(cancel, save); panel.append(actions); dialog.append(panel);
    document.body.append(dialog);
    const close = () => { dialog.close(); dialog.remove(); };
    cancel.addEventListener('click', close);
    dialog.addEventListener('cancel', () => { dialog.remove(); });
    dialog.addEventListener('click', event => { if (event.target === dialog) close(); });
    panel.addEventListener('submit', async event => {
      event.preventDefault();
      if (!panel.reportValidity()) return;
      save.disabled = true; error.textContent = '';
      const body = new FormData();
      for (const input of controls) body.set(input.name, input.value.trim());
      try {
        const response = await fetch(root.dataset.endpoint, {
          method: 'POST', credentials: 'same-origin',
          headers: { 'X-CSRFToken': csrfToken(root), 'Accept': 'application/json' },
          body,
        });
        const data = await response.json();
        if (!response.ok) {
          const details = data.errors && Object.entries(data.errors).flatMap(([key, entries]) => {
            return entries.map(entry => `${key === '__all__' ? 'Error' : key}: ${typeof entry === 'string' ? entry : entry.message}`);
          });
          throw new Error(details?.join(' · ') || data.error || `Could not create reference (${response.status}).`);
        }
        if (!data.item || !data.item.id) throw new Error('Invalid server response.');
        close(); done(data.item);
      } catch (exc) { error.textContent = exc.message || 'Unable to create this reference. Try again.'; }
      finally { save.disabled = false; }
    });
    dialog.showModal(); nameInput.focus();
  }
  function initialize(root) {
    const hidden = root.querySelector('input[type="hidden"]');
    const search = root.querySelector('[data-reference-search]');
    const current = root.querySelector('[data-reference-current]');
    const options = root.querySelector('[data-reference-options]');
    const help = root.querySelector('[data-reference-help]');
    if (!hidden || !search || !options) return;
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
})();
