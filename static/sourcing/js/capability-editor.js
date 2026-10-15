/* Shared Sourcing capability modal: Vendor, Subcontractor and Manpower Supplier.
 * Both directory and profile routes use the same authorized Django form.
 * No iframe, duplicated business logic, or client-side privilege determination. */
(() => {
  'use strict';
  let activeEditor = null;
  // Reuse the existing audited Django capability form, regardless of entry point.
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
    const sections = document.createElement('div');
    sections.className = 'sourcing-capability-editor__scroll';
    const footer = formElement.querySelector('.sourcing-form-actions');
    const other = [...formElement.children].filter(node => node !== footer && node.tagName !== 'INPUT');
    // Move actual form sections (not cloned inputs) into the scroll container;
    // the action footer stays fixed while the entire form submits normally.
    other.forEach(node => sections.appendChild(node));
    if (footer) formElement.insertBefore(sections, footer);
    else formElement.appendChild(sections);
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
        if (typeof editor.onSaved === 'function') editor.onSaved();
        document.dispatchEvent(new CustomEvent('sourcing:capability-created', {detail: {url: sourceURL}}));
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
  async function openCapabilityEditor(link, options = {}) {
    if (activeEditor) return;
    const url = new URL(link.href, location.href);
    if (url.origin !== location.origin || !url.pathname.endsWith('/new/')) return;
    const editorElement = ensureEditor();
    const controller = new AbortController();
    const expectedDetail = url.pathname.replace(/(?:catalog|workforce|services)\/new\/$/, '');
    const draftKey = `sescco:sourcing:capability-modal:v1:${encodeURIComponent(actor)}:${url.pathname}`;
    activeEditor = {element:editorElement,controller,returnFocus:link,draftKey,expectedDetail,saving:false,initial:null,onSaved:options.onSaved};
    editorElement.querySelector('#sourcing-capability-editor-title').textContent = link.textContent.trim();
    editorElement.querySelector('[data-editor-confirm]').hidden = true;
    editorElement.querySelector('[data-editor-body]').innerHTML = '<div class="sourcing-unified-modal__loading">Loading capability editor…</div>';
    editorElement.classList.add('is-open');
    document.body.style.overflow = 'hidden';
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
    if (event.key === 'Tab' && activeEditor && !document.querySelector('.sourcing-reference-dialog[open]')) {
      const target = activeEditor.element.querySelector('[data-editor-confirm]:not([hidden])') || activeEditor.element.querySelector('.sourcing-capability-editor__panel');
      const controls = [...target.querySelectorAll('button:not([disabled]),a[href],input:not([type=hidden]):not([disabled]),select:not([disabled]),textarea:not([disabled])')].filter(el => el.getClientRects().length);
      if (controls.length && event.shiftKey && document.activeElement === controls[0]) {event.preventDefault(); controls.at(-1).focus();}
      else if (controls.length && !event.shiftKey && document.activeElement === controls.at(-1)) {event.preventDefault(); controls[0].focus();}
    }
    if (event.key !== 'Escape' || !activeEditor) return;
    // The quick-create reference dialog owns its own Escape/discard workflow.
    if (document.querySelector('.sourcing-reference-dialog[open]')) return;
    if (!activeEditor.element.querySelector('[data-editor-confirm]').hidden) activeEditor.element.querySelector('[data-editor-confirm]').hidden = true;
    else requestEditorClose();
    event.stopImmediatePropagation();event.preventDefault();
  }, true);
  // Only profile-level Add links use delegation. Directory modal buttons
  // supply a refresh callback directly through the same public API.
  document.addEventListener('click', event => {
    const trigger = event.target.closest('a[data-sourcing-capability-modal]');
    if (!trigger) return;
    event.preventDefault();
    openCapabilityEditor(trigger, {onSaved: () => {
      // A refreshed profile reflects the actual new active count and audit state.
      location.reload();
    }});
  });
  window.SourcingCapabilityEditor = { open: openCapabilityEditor, close: requestEditorClose };

})();
