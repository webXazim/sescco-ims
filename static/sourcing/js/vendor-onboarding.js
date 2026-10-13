/* Full Vendor supply offers are drafted locally and submitted atomically with Vendor. */
(() => {
  'use strict';
  const root = document.querySelector('[data-supply-onboarding]');
  if (!root) return;
  const dialog = root.querySelector('[data-onboarding-dialog]');
  const rows = root.querySelector('[data-onboarding-rows]');
  const summary = root.querySelector('[data-onboarding-summary]');
  const template = root.querySelector('[data-onboarding-template]');
  const total = root.querySelector('input[name="supply_items-TOTAL_FORMS"]');
  const maximum = Number(root.querySelector('input[name="supply_items-MAX_NUM_FORMS"]')?.value || 50);
  const error = root.querySelector('[data-onboarding-error]');
  const add = root.querySelector('[data-onboarding-add]');
  let active = null;
  let isNew = false;
  let snapshot = null;
  let committed = false;

  function field(row, suffix) {
    return [...row.querySelectorAll('input,textarea,select')].find(input => input.name.endsWith(`-${suffix}`));
  }
  function value(row, suffix) { return String(field(row, suffix)?.value || '').trim(); }
  function deleted(row) { return !!field(row, 'DELETE')?.checked; }
  function setDeleted(row, state) { const control = field(row, 'DELETE'); if (control) control.checked = state; }
  function useNewMaster(row, enabled) {
    const block = row.querySelector('[data-onboarding-master]');
    const lookup = row.querySelector('[data-sourcing-reference-lookup]');
    if (!block) return;
    block.hidden = !enabled;
    lookup.hidden = enabled;
    row.querySelector('[data-onboarding-new-master]').hidden = enabled;
    if (enabled) {
      const selected = field(row, 'material');
      if (selected) selected.value = '';
    }
  }
  function initRow(row) {
    row.querySelector('[data-onboarding-new-master]')?.addEventListener('click', () => {
      useNewMaster(row, true);
      field(row, 'new_material_name')?.focus();
    });
    row.querySelector('[data-onboarding-existing-master]')?.addEventListener('click', () => {
      row.querySelectorAll('[name*="-new_material_"]').forEach(input => {
        if (input.tagName === 'SELECT') input.selectedIndex = 0;
        else input.value = '';
      });
      useNewMaster(row, false);
      row.querySelector('[data-reference-current] button')?.click();
      row.querySelector('[data-reference-search]')?.focus();
    });
    const category = row.querySelector('[data-material-category-select]');
    const newCategory = row.querySelector('[data-new-material-category-field]');
    if (category && newCategory) {
      const sync = () => { newCategory.hidden = category.value !== '__new__'; };
      category.addEventListener('change', sync);
      sync();
    }
    if (value(row, 'new_material_name')) useNewMaster(row, true);
    document.dispatchEvent(new CustomEvent('sourcing:reference-lookup-mount', { detail: { root: row } }));
  }
  function activeRows() { return [...rows.querySelectorAll('[data-onboarding-row]')].filter(row => !deleted(row)); }
  function renderSummary() {
    summary.replaceChildren();
    const items = activeRows();
    if (!items.length) {
      const empty = document.createElement('p');
      empty.className = 'sourcing-onboarding-empty';
      empty.textContent = 'No supply items yet. Add a material capability with its specifications, availability and rates.';
      summary.append(empty);
    }
    items.forEach((row, index) => {
      const card = document.createElement('div'); card.className = 'sourcing-onboarding-card';
      const info = document.createElement('div');
      const name = document.createElement('strong');
      const selected = row.querySelector('[data-reference-current] .sourcing-reference-selected')?.textContent;
      name.textContent = value(row, 'new_material_name') || selected || 'Selected Sourcing Material';
      const details = document.createElement('small');
      details.textContent = [value(row, 'specification'), value(row, 'brand'), value(row, 'model'),
        value(row, 'availability') || 'Unknown availability',
        value(row, 'available_quantity') ? `Qty ${value(row, 'available_quantity')}` : '',
        value(row, 'rate') ? `${value(row, 'rate')} ${value(row, 'currency') || 'SAR'}` : ''].filter(Boolean).join(' · ');
      info.append(name, details);
      const actions = document.createElement('div'); actions.className = 'sourcing-onboarding-card-actions';
      const edit = document.createElement('button'); edit.type = 'button'; edit.className = 'sourcing-btn'; edit.textContent = 'Edit';
      edit.addEventListener('click', () => open(row, false));
      const remove = document.createElement('button'); remove.type = 'button'; remove.className = 'sourcing-btn sourcing-onboarding-remove'; remove.textContent = 'Remove';
      remove.addEventListener('click', () => { setDeleted(row, true); renderSummary(); });
      actions.append(edit, remove); card.append(info, actions); summary.append(card);
    });
    add.disabled = items.length >= maximum;
  }
  function open(row, fresh) {
    active = row;
    isNew = fresh;
    committed = false;
    snapshot = fresh ? null : row.cloneNode(true);
    error.hidden = true; error.textContent = '';
    rows.querySelectorAll('[data-onboarding-row]').forEach(item => { item.hidden = item !== row; });
    dialog.querySelector('#sourcing-onboarding-dialog-title').textContent = fresh ? 'Add Supply Item' : 'Edit Supply Item';
    dialog.showModal();
    if (fresh) row.querySelector('[data-reference-search]')?.focus();
    else row.querySelector('.has-error input,.has-error select,.has-error textarea')?.focus();
  }
  function addNew() {
    let index = Number(total.value);
    if (activeRows().length >= maximum || !Number.isSafeInteger(index)) return;
    let reusable = null;
    if (index >= maximum) {
      reusable = [...rows.querySelectorAll('[data-onboarding-row]')].find(deleted);
      if (!reusable) return;
      index = [...rows.querySelectorAll('[data-onboarding-row]')].indexOf(reusable);
    }
    const wrapper = document.createElement('div');
    wrapper.innerHTML = template.innerHTML.replaceAll('__prefix__', String(index)).trim();
    const row = wrapper.firstElementChild;
    if (!row) return;
    if (reusable) reusable.replaceWith(row);
    else {
      rows.append(row);
      total.value = String(index + 1);
    }
    initRow(row);
    open(row, true);
    renderSummary();
  }
  function cancel() { if (dialog.open) dialog.close(); }
  function close() {
    if (!active) return;
    const row = active;
    if (!committed) {
      if (isNew) setDeleted(row, true);
      else if (snapshot) {
        row.replaceWith(snapshot);
        snapshot.querySelectorAll('[data-sourcing-reference-lookup]').forEach(node => {
          node.removeAttribute('data-reference-initialized');
          node.querySelector('[data-reference-current]')?.replaceChildren();
          const search = node.querySelector('[data-reference-search]');
          if (search) search.hidden = false;
        });
        initRow(snapshot);
      }
    }
    rows.querySelectorAll('[data-onboarding-row]').forEach(item => { item.hidden = true; });
    active = null; snapshot = null;
    renderSummary();
  }
  function done() {
    if (!active) return;
    error.hidden = true; error.textContent = '';
    const hasNew = !!value(active, 'new_material_name');
    const material = value(active, 'material');
    if (!material && !hasNew) {
      error.textContent = 'Select an existing material or create a new material.';
    } else if (hasNew && material) {
      error.textContent = 'Choose an existing material OR create a new material.';
    } else if (active.querySelector('[data-onboarding-master]') && hasNew &&
               value(active, 'new_material_category') === '__new__' && !value(active, 'new_material_new_category')) {
      error.textContent = 'Enter the new material category / type.';
    }
    if (error.textContent) { error.hidden = false; return; }
    // Numeric/date constraints and missing required currency are checked by Django
    // on the final POST too; surface obvious invalid values before closing.
    const invalid = [...active.querySelectorAll('input, select, textarea')]
      .find(input => !input.hidden && input.closest('[hidden]') === null && !input.checkValidity());
    if (invalid) { invalid.reportValidity(); return; }
    setDeleted(active, false);
    committed = true;
    dialog.close();
  }
  add.addEventListener('click', addNew);
  dialog.querySelectorAll('[data-onboarding-cancel]').forEach(button => button.addEventListener('click', cancel));
  dialog.querySelector('[data-onboarding-done]').addEventListener('click', done);
  dialog.addEventListener('close', close);
  dialog.addEventListener('click', event => { if (event.target === dialog) cancel(); });
  dialog.addEventListener('keydown', event => {
    if (event.key === 'Enter' && event.target.matches('input:not([type="button"]):not([type="submit"])') &&
        !event.target.matches('[data-reference-search]')) event.preventDefault();
  });
  rows.querySelectorAll('[data-onboarding-row]').forEach(initRow);
  renderSummary();
  const invalidRow = rows.querySelector('[data-onboarding-invalid]');
  if (invalidRow && !deleted(invalidRow)) open(invalidRow, false);
})();
