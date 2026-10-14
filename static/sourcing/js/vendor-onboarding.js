/* Full Vendor supply offers are drafted locally and submitted atomically with Vendor. */
(() => {
  'use strict';
  const root = document.querySelector('[data-supply-onboarding]');
  if (!root) return;
  const stagedCategories = window.SourcingStagedCategories?.create(root, { categoryField: 'new_material_category', newCategoryField: 'new_material_new_category', nameField: 'new_material_name', stagedKey: 'onboardingNewMaterial' });
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
  let baseline = '';
  const confirm = root.querySelector('[data-onboarding-confirm]');
  const keepButton = root.querySelector('[data-onboarding-keep]');
  const discardButton = root.querySelector('[data-onboarding-discard]');
  function stateOf(row) {
    // Includes lookup search, chosen hidden material id and all draft fields.
    return JSON.stringify([...row.querySelectorAll('input, select, textarea')].map(item => [
      item.name || item.dataset.referenceSearch || item.outerHTML.slice(0, 100),
      item.type === 'checkbox' || item.type === 'radio' ? item.checked : item.value,
    ]));
  }
  function dirty() { return !!active && stateOf(active) !== baseline; }
  function hideWarning() {
    confirm.hidden = true;
    [dialog.querySelector('[data-onboarding-rows]'),
     dialog.querySelector('.sourcing-onboarding-dialog-head'),
     dialog.querySelector('.sourcing-onboarding-dialog-actions')].forEach(node => { if (node) node.inert = false; });
  }
  function showWarning() {
    confirm.hidden = false;
    [dialog.querySelector('[data-onboarding-rows]'),
     dialog.querySelector('.sourcing-onboarding-dialog-head'),
     dialog.querySelector('.sourcing-onboarding-dialog-actions')].forEach(node => { if (node) node.inert = true; });
    keepButton.focus();
  }
  function requestDismiss() {
    if (!dialog.open || !active) return;
    if (dirty()) { showWarning(); return; }
    dialog.close();
  }

  function field(row, suffix) {
    return [...row.querySelectorAll('input,textarea,select')].find(input => input.name.endsWith(`-${suffix}`));
  }
  function value(row, suffix) { return String(field(row, suffix)?.value || '').trim(); }
  function deleted(row) { return !!field(row, 'DELETE')?.checked; }
  function setDeleted(row, state) { const control = field(row, 'DELETE'); if (control) control.checked = state; }
  function masterControls(row) {
    const master = row.querySelector('[data-onboarding-master]');
    return master ? [...master.querySelectorAll('input,select,textarea')] : [];
  }
  function masterState(row) {
    return JSON.stringify(masterControls(row).map(input => [input.name, input.type === 'checkbox' ? input.checked : input.value]));
  }
  function masterSnapshot(row) {
    return masterControls(row).map(input => ({ name: input.name, value: input.value, checked: input.checked }));
  }
  function restoreMaster(row, snapshot) {
    for (const input of masterControls(row)) {
      const saved = snapshot.find(item => item.name === input.name);
      if (!saved) continue;
      input.value = saved.value;
      if (input.type === 'checkbox') input.checked = saved.checked;
    }
    row.querySelector('[data-material-category-select]')?.dispatchEvent(new Event('change'));
  }
  function stagedMaster(row, enabled) {
    const lookup = row.querySelector('[data-sourcing-reference-lookup]');
    const staged = row.querySelector('[data-onboarding-staged-material]');
    const button = row.querySelector('[data-onboarding-new-master]');
    if (!staged || !lookup || !button) return;
    row.dataset.onboardingNewMaterial = enabled ? '1' : '0';
    stagedCategories?.refresh();
    lookup.hidden = enabled;
    button.hidden = enabled;
    staged.hidden = !enabled;
    staged.querySelector('[data-onboarding-staged-name]').textContent =
      value(row, 'new_material_name') || 'New material';
    if (enabled) field(row, 'material').value = '';
  }
  function initMaster(row) {
    const dialogMaster = row.querySelector('[data-onboarding-master]');
    if (!dialogMaster) return;
    let before = null;
    let modeBefore = false;
    const warning = dialogMaster.querySelector('[data-material-confirm]');
    const errorMessage = dialogMaster.querySelector('[data-material-error]');
    const body = dialogMaster.querySelector('.sourcing-onboarding-material-body');
    const head = dialogMaster.querySelector('.sourcing-onboarding-material-head');
    const footer = dialogMaster.querySelector('.sourcing-onboarding-material-actions');
    const setWarning = state => {
      warning.hidden = !state;
      for (const item of [body, head, footer]) item.inert = state;
      if (state) dialogMaster.querySelector('[data-material-keep]').focus();
    };
    const dismiss = discard => {
      if (warning.hidden === false) { if (!discard) return; setWarning(false); }
      if (discard && before) restoreMaster(row, before);
      dialogMaster.close();
    };
    const requestClose = () => {
      if (!dialogMaster.open) return;
      if (JSON.stringify(before) !== JSON.stringify(masterSnapshot(row))) setWarning(true);
      else dismiss(false);
    };
    const show = () => {
      before = masterSnapshot(row);
      modeBefore = row.dataset.onboardingNewMaterial === '1';
      errorMessage.hidden = true;
      errorMessage.textContent = '';
      setWarning(false);
      dialogMaster.hidden = false;
      dialogMaster.showModal();
      field(row, 'new_material_name')?.focus();
    };
    row.querySelector('[data-onboarding-new-master]')?.addEventListener('click', show);
    row.querySelector('[data-onboarding-edit-master]')?.addEventListener('click', show);
    dialogMaster.querySelectorAll('[data-material-dismiss]').forEach(button => button.addEventListener('click', requestClose));
    dialogMaster.querySelector('[data-material-keep]').addEventListener('click', () => {
      setWarning(false);
      field(row, 'new_material_name')?.focus();
    });
    dialogMaster.querySelector('[data-material-discard]').addEventListener('click', () => dismiss(true));
    dialogMaster.querySelector('[data-material-save]').addEventListener('click', () => {
      const name = field(row, 'new_material_name');
      const category = field(row, 'new_material_category');
      const newCategory = field(row, 'new_material_new_category');
      errorMessage.hidden = true;
      errorMessage.textContent = '';
      if (!name.value.trim()) { errorMessage.textContent = 'Enter a material name.'; name.focus(); }
      else if (category?.value === '__new__' && !newCategory?.value.trim()) {
        errorMessage.textContent = 'Enter the new category / type.';
        newCategory.focus();
      } else {
        const invalid = masterControls(row).find(input => !input.closest('[hidden]') && !input.checkValidity());
        if (invalid) { invalid.reportValidity(); return; }
        // Commit a draft only; the existing server-side formset and atomic Vendor
        // creation remain the sole source of truth for validation and persistence.
        stagedMaster(row, true);
        dialogMaster.close();
        row.querySelector('[data-onboarding-edit-master]')?.focus({ preventScroll: true });
        return;
      }
      errorMessage.hidden = false;
    });
    row.querySelector('[data-onboarding-existing-master]')?.addEventListener('click', () => {
      if (value(row, 'new_material_name') &&
          !window.confirm('Discard this new material draft and choose an existing material?')) return;
      for (const input of masterControls(row)) {
        if (input.tagName === 'SELECT') input.selectedIndex = 0;
        else if (input.type === 'checkbox') input.checked = false;
        else input.value = '';
      }
      row.querySelector('[data-material-category-select]')?.dispatchEvent(new Event('change'));
      stagedMaster(row, false);
      row.querySelector('[data-reference-current] button')?.click();
      row.querySelector('[data-reference-search]')?.focus();
    });
    dialogMaster.addEventListener('cancel', event => {
      event.preventDefault();
      event.stopPropagation();
      if (!warning.hidden) { setWarning(false); return; }
      requestClose();
    });
    dialogMaster.addEventListener('click', event => {
      if (event.target === dialogMaster) requestClose();
    });
    dialogMaster.addEventListener('close', () => {
      dialogMaster.hidden = true;
      if (warning.hidden === false) setWarning(false);
      // Never leave a cancelled draft in the parent formset.
      if (!modeBefore && row.dataset.onboardingNewMaterial !== '1' && before) restoreMaster(row, before);
    });
    dialogMaster.addEventListener('keydown', event => {
      if (event.key === 'Enter' && event.target.matches('input:not([type="submit"]):not([type="button"])')) event.preventDefault();
    });
  }
  function initRow(row) {
    initMaster(row);
    const category = row.querySelector('[data-material-category-select]');
    const newCategory = row.querySelector('[data-new-material-category-field]');
    if (category && newCategory) {
      const sync = () => { newCategory.hidden = category.value !== '__new__'; };
      category.addEventListener('change', sync);
      sync();
    }
    if (value(row, 'new_material_name')) stagedMaster(row, true);
    stagedCategories?.mount(row);
    document.dispatchEvent(new CustomEvent('sourcing:reference-lookup-mount', { detail: { root: row } }));
  }
  function activeRows() { return [...rows.querySelectorAll('[data-onboarding-row]')].filter(row => !deleted(row)); }
  function renderSummary() {
    stagedCategories?.refresh();
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
    hideWarning();
    snapshot = fresh ? null : row.cloneNode(true);
    error.hidden = true; error.textContent = '';
    rows.querySelectorAll('[data-onboarding-row]').forEach(item => { item.hidden = item !== row; });
    dialog.querySelector('#sourcing-onboarding-dialog-title').textContent = fresh ? 'Add Supply Item' : 'Edit Supply Item';
    dialog.showModal();
    baseline = stateOf(row);
    if (fresh) row.querySelector('[data-reference-search]')?.focus();
    else if (row.querySelector('[data-onboarding-master] .has-error'))
      row.querySelector('[data-onboarding-edit-master]')?.click();
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
  function cancel() { requestDismiss(); }
  function close() {
    if (!active) return;
    const row = active;
    hideWarning();
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
    active = null; snapshot = null; baseline = '';
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
  dialog.addEventListener('click', event => { if (event.target === dialog) requestDismiss(); });
  dialog.addEventListener('cancel', event => {
    event.preventDefault(); // Escape also requires dirty-draft confirmation.
    if (confirm.hidden) requestDismiss(); else { hideWarning(); active.querySelector('input:not([type="hidden"]),textarea,select')?.focus(); }
  });
  keepButton.addEventListener('click', () => { hideWarning(); active?.querySelector('input:not([type="hidden"]), textarea, select')?.focus(); });
  discardButton.addEventListener('click', () => { hideWarning(); dialog.close(); });
  dialog.addEventListener('keydown', event => {
    if (event.key === 'Enter' && event.target.matches('input:not([type="button"]):not([type="submit"])') &&
        !event.target.matches('[data-reference-search]')) event.preventDefault();
  });
  rows.querySelectorAll('[data-onboarding-row]').forEach(initRow);
  renderSummary();
  const invalidRow = rows.querySelector('[data-onboarding-invalid]');
  if (invalidRow && !deleted(invalidRow)) open(invalidRow, false);
})();
