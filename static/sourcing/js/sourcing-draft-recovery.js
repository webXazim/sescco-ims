/* Recover a Sourcing provider create draft after reload. Scoped to this tab and
 * signed-in identity; data is never sent to a draft API or made operational. */
(() => {
  'use strict';
  const form = document.querySelector('form[data-sourcing-draft-form]');
  if (!form) return;
  const root = form.querySelector('[data-supply-onboarding], [data-provider-onboarding]');
  const onboarding = window.SourcingOnboardingDraft;
  if (!root || !onboarding) return;
  const actor = document.querySelector('.platform-account__copy strong, .platform-account__identity strong')?.textContent?.trim() || 'unknown';
  const key = `sescco:sourcing:provider-draft:v1:${encodeURIComponent(actor)}:${location.pathname}`;
  const maxAge = 24 * 60 * 60 * 1000;
  const limit = 950000;
  let started = false;
  let submitting = false;
  let restoring = false;
  let baseline = '';
  let timer = null;
  let unavailable = false;
  let status;

  const controls = () => [...form.querySelectorAll('input[name],select[name],textarea[name]')]
    .filter(el => !el.closest('[data-onboarding-rows],template') &&
      !['csrfmiddlewaretoken', 'supply_items-TOTAL_FORMS', 'supply_items-INITIAL_FORMS',
        'supply_items-MIN_NUM_FORMS', 'supply_items-MAX_NUM_FORMS'].includes(el.name) &&
      !['password', 'file', 'submit', 'button'].includes(el.type));
  function snapshot() {
    return {
      fields: controls().map(el => ({
        name: el.name, value: el.value,
        checked: ['checkbox', 'radio'].includes(el.type) ? el.checked : null,
      })),
      tagText: form.querySelector('.sourcing-tag-editor__input')?.value || '',
      onboarding: onboarding.capture(),
    };
  }
  function serialized() { return JSON.stringify(snapshot()); }
  function dirty() { return serialized() !== baseline; }
  function renderStatus(message, showDiscard = false) {
    if (!status) return;
    status.hidden = false;
    status.querySelector('[data-draft-message]').textContent = message;
    status.querySelector('[data-draft-discard]').hidden = !showDiscard;
  }
  function save() {
    if (!started || restoring || unavailable || !dirty()) return;
    try {
      const state = { v: 1, path: location.pathname, actor, updated: Date.now(), submitted: submitting, content: snapshot() };
      const text = JSON.stringify(state);
      if (text.length > limit) throw new Error('Draft is too large for safe browser storage.');
      sessionStorage.setItem(key, text);
      if (status && !status.dataset.restored) renderStatus('Draft saved in this tab', true);
    } catch (error) {
      unavailable = true;
      renderStatus('Automatic draft recovery is unavailable. Keep this tab open.', false);
    }
  }
  function scheduleSave() {
    if (!started || restoring || submitting) return;
    clearTimeout(timer);
    timer = setTimeout(save, 260);
  }
  function restore(saved) {
    restoring = true;
    try {
      const byName = new Map(controls().map(el => [el.name, el]));
      for (const item of saved.fields || []) {
        const el = byName.get(item.name);
        if (!el) continue;
        el.value = item.value == null ? '' : String(item.value);
        if (item.checked !== null && item.checked !== undefined) el.checked = !!item.checked;
        if (el.matches('[data-provider-tag-field]')) el.dispatchEvent(new Event('sourcing:draft-restore'));
        if (el.name === 'name' || el.name === 'code') el.dispatchEvent(new Event('input', { bubbles: false }));
      }
      const tagInput = form.querySelector('.sourcing-tag-editor__input');
      if (tagInput && saved.tagText) tagInput.value = String(saved.tagText).slice(0, 80);
      onboarding.restore(saved.onboarding);
    } finally { restoring = false; }
  }
  function createNotice() {
    const banner = document.createElement('div');
    banner.className = 'sourcing-draft-notice';
    banner.setAttribute('role', 'status');
    banner.hidden = true;
    const label = document.createElement('span'); label.dataset.draftMessage = '';
    const discard = document.createElement('button');
    discard.className = 'sourcing-draft-notice__discard';
    discard.type = 'button'; discard.dataset.draftDiscard = '';
    discard.textContent = 'Discard draft';
    discard.addEventListener('click', () => {
      if (!window.confirm('Discard this provider draft and start again? This cannot be undone.')) return;
      submitting = true; // explicit discard is the one intentional no-warning reload
      try { sessionStorage.removeItem(key); } catch (error) { /* storage disabled */ }
      location.reload();
    });
    banner.append(label, discard);
    form.insertAdjacentElement('beforebegin', banner);
    status = banner;
  }
  createNotice();
  baseline = serialized();
  try {
    const raw = sessionStorage.getItem(key);
    if (raw) {
      const entry = JSON.parse(raw);
      if (entry.v === 1 && entry.actor === actor && entry.path === location.pathname &&
          Date.now() - entry.updated < maxAge && !entry.submitted && entry.content) {
        const serverErrors = !!form.querySelector('.has-error, .field-error, .sourcing-form-errors, [data-onboarding-invalid]');
        if (!serverErrors) {
          restore(entry.content);
          status.dataset.restored = '1';
          renderStatus('Draft restored after reload. Nothing has been submitted.', true);
        } else {
          // A failed POST has already re-rendered the authoritative bound forms.
          // Do not overwrite validation messages with an older browser snapshot.
          renderStatus('Please correct the highlighted fields; your submitted values are retained.', false);
        }
      } else if (entry.submitted || Date.now() - entry.updated >= maxAge) {
        sessionStorage.removeItem(key);
      }
    }
  } catch (error) {
    // Malformed/unavailable storage must never stop normal form submission.
    unavailable = true;
    renderStatus('Automatic draft recovery is unavailable. Keep this tab open.', false);
  }
  started = true;

  form.addEventListener('input', scheduleSave);
  form.addEventListener('change', scheduleSave);
  form.addEventListener('click', event => {
    // Stage, remove, discard, and chip buttons also mutate hidden form state.
    if (event.target.closest('button')) setTimeout(scheduleSave, 0);
  });
  form.addEventListener('sourcing:draft-change', scheduleSave);
  form.addEventListener('submit', event => {
    if (event.defaultPrevented) return;
    clearTimeout(timer);
    submitting = true;
    save(); // Mark the in-flight draft; if the POST fails Django keeps bound values.
  });
  window.addEventListener('beforeunload', event => {
    clearTimeout(timer);
    save();
    if (!submitting && dirty()) {
      event.preventDefault();
      event.returnValue = ''; // browser native confirmation (custom text is prohibited)
    }
  });
  window.addEventListener('pagehide', () => { clearTimeout(timer); save(); });
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') save();
  });
})();
