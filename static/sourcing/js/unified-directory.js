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
  let activeEditor = null;

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
      if (event.key === 'Escape' && !activeEditor && !document.querySelector('.sourcing-reference-dialog[open]') && modal.classList.contains('is-open')) closeModal();
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
    if (activeEditor) { requestEditorClose(); return; }
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

  // Native modal: render the SAME Django capability form used at the normal URL.
  // Framing is intentionally avoided: SESCCO's gateway sets X-Frame-Options DENY.
  function ensureEditor() {
    let editor = document.getElementById('sourcing-capability-editor');
    if (editor) return editor;
    editor = document.createElement('div');
    editor.id = 'sourcing-capability-editor';
    editor.className = 'sourcing-capability-editor';
    editor.setAttribute('role', 'dialog');
    editor.setAttribute('aria-modal', 'true');
    editor.setAttribute('aria-labelledby', 'sourcing-capability-editor-title');
    editor.innerHTML = `
      <div class="sourcing-capability-editor__backdrop" data-editor-close></div>
      <div class="sourcing-capability-editor__panel">
        <header class="sourcing-capability-editor__head">
          <h2 id="sourcing-capability-editor-title">Add capability</h2>
          <button type="button" class="sourcing-unified-modal__close" data-editor-close aria-label="Close capability editor">&times;</button>
        </header>
        <div class="sourcing-capability-editor__body" data-editor-body role="document"></div>
      </div>
      <div class="sourcing-capability-editor__confirm" data-editor-confirm hidden role="alertdialog" aria-modal="true" aria-label="Discard capability changes">
        <div class="sourcing-capability-editor__confirm-card">
          <h3>Discard capability changes?</h3>
          <p>Your new capability has not been saved.</p>
          <div><button type="button" class="sourcing-btn" data-editor-keep>Keep editing</button><button type="button" class="sourcing-btn sourcing-capability-editor__discard" data-editor-discard>Discard changes</button></div>
        </div>
      </div>`;
    document.body.appendChild(editor);
    editor.addEventListener('click', (event) => {
      if (event.target.closest('[data-editor-close]')) requestEditorClose();
      if (event.target.closest('[data-editor-keep]')) {
        editor.querySelector('[data-editor-confirm]').hidden = true;
        editor.querySelector('[data-editor-body] input:not([type=hidden])')?.focus();
      }
      if (event.target.closest('[data-editor-discard]')) finishEditor(true);
    });
    return editor;
  }
  const actor = document.querySelector('.platform-account__copy strong, .platform-account__identity strong')?.textContent?.trim() || 'unknown';
  function editorState(form) {
    if (!form) return '';
    const fields = [...form.querySelectorAll('input[name],select[name],textarea[name]')]
      .filter(el => el.name !== 'csrfmiddlewaretoken' && !['file', 'password'].includes(el.type));
    return JSON.stringify(fields.map(el => ({ name:el.name, value:el.value,
      checked: ['checkbox','radio'].includes(el.type) ? el.checked : null })));
  }
  function editorDirty() {
    if (!activeEditor) return false;
    if (document.querySelector('.sourcing-reference-dialog[open]')) return true;
    const formElement = activeEditor.element.querySelector('form[data-sourcing-page-draft]');
    return !!formElement && editorState(formElement) !== activeEditor.initial;
  }
  function storeEditorDraft() {
    if (!activeEditor || !editorDirty()) return;
    const formElement = activeEditor.element.querySelector('form[data-sourcing-page-draft]');
    if (!formElement) return;
    try {
      sessionStorage.setItem(activeEditor.draftKey, JSON.stringify({at:Date.now(),state:editorState(formElement)}));
    } catch (_) { /* private browsing */ }
  }
  function clearEditorDraft(key) {try {sessionStorage.removeItem(key);} catch (_) {}}
  function requestEditorClose() {
    if (!activeEditor) return;
    // Do not abort an in-flight POST: the server may already have committed it.
    if (activeEditor.saving) return;
    if (editorDirty()) {
      storeEditorDraft();
      activeEditor.element.querySelector('[data-editor-confirm]').hidden = false;
      activeEditor.element.querySelector('[data-editor-keep]').focus();
    } else finishEditor(false);
  }
  function finishEditor(discard) {
    if (!activeEditor) return;
    const {element, returnFocus, draftKey, controller} = activeEditor;
    if (discard) {
      clearEditorDraft(draftKey);
      // Explicitly discarding a nested quick-create must not resurrect it on
      // the next opening of this capability form.
      const prefix = `sescco:sourcing:reference-modal:v1:${encodeURIComponent(actor)}:`;
      try {
        for (let i = sessionStorage.length - 1; i >= 0; i--) {
          const key = sessionStorage.key(i);
          if (key?.startsWith(prefix) && key.includes(`:${location.pathname}:`)) sessionStorage.removeItem(key);
        }
      } catch (_) { /* optional storage */ }
    }
    controller.abort();
    element.querySelector('[data-editor-confirm]').hidden = true;
    element.classList.remove('is-open');
    element.querySelector('[data-editor-body]').replaceChildren();
    activeEditor = null;
    if (!document.getElementById('sourcing-capability-modal')?.classList.contains('is-open')) document.body.style.overflow = '';
    returnFocus?.focus();
  }
  function renderEditorForm(markup, sourceURL, restoreDraft = false) {
    if (!activeEditor) return false;
    const doc = new DOMParser().parseFromString(markup, 'text/html');
    const sourceForm = doc.querySelector('form.sourcing-form-shell');
    if (!sourceForm) return false;
    const formElement = document.importNode(sourceForm, true);
    formElement.action = sourceURL;
    const body = activeEditor.element.querySelector('[data-editor-body]');
    body.replaceChildren(formElement);
    // HTML markup comes from the authenticated, same-origin Django form view.
    // The shared reference lookup mounts dynamically and keeps its paginated API.
    document.dispatchEvent(new CustomEvent('sourcing:reference-lookup-mount', {detail:{root:body}}));
    if (restoreDraft) {
      try {
        const draft = JSON.parse(sessionStorage.getItem(activeEditor.draftKey) || 'null');
        if (draft?.at && Date.now() - draft.at < 86400000 && Array.isArray(JSON.parse(draft.state))) {
          const values = new Map(JSON.parse(draft.state).map(item => [item.name,item]));
          formElement.querySelectorAll('input[name],select[name],textarea[name]').forEach(el => {
            const v = values.get(el.name);
            if (!v || el.name === 'csrfmiddlewaretoken') return;
            if (v.checked !== null) el.checked = !!v.checked;
            else if (el.tagName !== 'SELECT' || [...el.options].some(option => option.value === v.value)) el.value = v.value;
          });
          formElement.querySelectorAll('[data-sourcing-reference-lookup]').forEach(lookup => {
            const id = lookup.querySelector('input[type=hidden][name]')?.value;
            if (id) lookup.dispatchEvent(new CustomEvent('sourcing:reference-lookup-restore', {detail:{selectedId:id}}));
          });
          const notice = document.createElement('p');
          notice.className = 'sourcing-capability-editor__recovered';
          notice.textContent = 'Unsaved capability draft restored.';
          body.prepend(notice);
        }
      } catch (_) {clearEditorDraft(activeEditor.draftKey);}
    }
    if (!activeEditor.initial) activeEditor.initial = editorState(sourceForm);
    formElement.addEventListener('input', storeEditorDraft);
    formElement.addEventListener('change', storeEditorDraft);
    formElement.addEventListener('sourcing:reference-selected', storeEditorDraft);
    formElement.querySelector('.sourcing-form-actions a')?.addEventListener('click', event => {
      event.preventDefault(); requestEditorClose();
    });
    formElement.addEventListener('submit', event => {
      event.preventDefault();
      submitEditor(formElement, sourceURL);
    });
    return true;
  }
  async function submitEditor(formElement, sourceURL) {
    if (!activeEditor || activeEditor.saving) return;
    const editor = activeEditor;
    editor.saving = true;
    storeEditorDraft();
    const submit = formElement.querySelector('[type=submit]');
    if (submit) submit.disabled = true;
    try {
      const response = await fetch(sourceURL, {
        method:'POST',credentials:'same-origin', signal:editor.controller.signal,
        headers:{'X-CSRFToken':formElement.querySelector('[name=csrfmiddlewaretoken]')?.value || ''},
        body:new FormData(formElement),
      });
      if (response.ok && response.redirected && new URL(response.url).pathname === editor.expectedDetail) {
        clearEditorDraft(editor.draftKey);
        finishEditor(false);
        if (activeProvider) loadCapabilities(activeProvider,'1');
        search(makeURL());
        return;
      }
      const text = await response.text();
      if (response.status === 400 && renderEditorForm(text,sourceURL)) {
        editor.element.querySelector('.field-error,.has-error input,.sourcing-form-errors')?.scrollIntoView({block:'center'});
        return;
      }
      throw new Error(response.status === 403 ? 'You do not have permission to create this capability.' :
        'Unable to save this capability. Please check your connection or reload the form.');
    } catch (error) {
      if (error.name === 'AbortError' || !activeEditor) return;
      const alert = document.createElement('p'); alert.className = 'sourcing-capability-editor__error';
      alert.setAttribute('role','alert'); alert.textContent = error.message || 'Unable to save capability.';
      activeEditor.element.querySelector('[data-editor-body]').prepend(alert);
    } finally {
      if (activeEditor === editor) {editor.saving = false; if (submit?.isConnected) submit.disabled = false;}
    }
  }
  async function openCapabilityEditor(link) {
    if (!activeProvider) return;
    const url = new URL(link.href, location.href);
    if (url.origin !== location.origin || !url.pathname.endsWith('/new/')) return;
    const editorElement = ensureEditor();
    const controller = new AbortController();
    const expectedDetail = url.pathname.replace(/(?:catalog|workforce|services)\/new\/$/, '');
    const draftKey = `sescco:sourcing:capability-modal:v1:${encodeURIComponent(actor)}:${url.pathname}`;
    activeEditor = {element:editorElement,controller,returnFocus:link,draftKey,expectedDetail,saving:false,initial:null};
    editorElement.querySelector('#sourcing-capability-editor-title').textContent = link.textContent.trim();
    editorElement.querySelector('[data-editor-confirm]').hidden = true;
    editorElement.querySelector('[data-editor-body]').innerHTML = '<div class="sourcing-unified-modal__loading">Loading capability editor…</div>';
    editorElement.classList.add('is-open');
    try {
      const response = await fetch(url, {credentials:'same-origin',signal:controller.signal});
      if (!response.ok) throw new Error(response.status === 403 ? 'You do not have permission to add capabilities.' : 'Unable to load capability form.');
      if (!renderEditorForm(await response.text(),url.href,true)) throw new Error('The capability form was not available.');
      editorElement.querySelector('[data-editor-body] input:not([type=hidden])')?.focus();
    } catch (error) {
      if (error.name === 'AbortError') return;
      editorElement.querySelector('[data-editor-body]').textContent = error.message || 'Unable to load editor.';
    }
  }
  window.addEventListener('beforeunload', event => {
    storeEditorDraft();
    if (editorDirty()) {event.preventDefault();event.returnValue = '';}
  });
  document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape' || !activeEditor) return;
    // The quick-create reference dialog owns its own Escape/discard workflow.
    if (document.querySelector('.sourcing-reference-dialog[open]')) return;
    if (!activeEditor.element.querySelector('[data-editor-confirm]').hidden) activeEditor.element.querySelector('[data-editor-confirm]').hidden = true;
    else requestEditorClose();
    event.stopImmediatePropagation();event.preventDefault();
  }, true);
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
      openCapabilityEditor(createAction);
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
