/* Shared, progressively enhanced company classification tags for all Sourcing providers.
 * The submitted Django field remains a comma-separated string; the server remains
 * the authority for validation, normalization, permissions and tenancy. */
(() => {
  'use strict';
  const controls = document.querySelectorAll('input[data-provider-tag-field]');
  if (!controls.length) return;

  const suggested = Array.from(document.querySelectorAll('#sourcing-provider-tags option'))
    .map((option) => (option.value || '').trim()).filter(Boolean);
  const canonical = (text) => text.trim().replace(/\s+/g, ' ');
  const norm = (text) => canonical(text).toLocaleLowerCase();
  const invalid = (text) => text.length > 40 || /^[=+\-@]/.test(text)
    || /["\\|<>\[\]{}\x00-\x1f]/.test(text);

  controls.forEach((field) => {
    if (field.dataset.providerTagReady === '1') return;
    field.dataset.providerTagReady = '1';
    const form = field.closest('form');
    const fieldHost = field.closest('.sourcing-field');
    if (!form || !fieldHost) return;

    const widget = document.createElement('div');
    widget.className = 'sourcing-tag-editor';
    widget.setAttribute('data-provider-tag-editor', '');
    const tokens = document.createElement('div');
    tokens.className = 'sourcing-tag-editor__tokens';
    tokens.setAttribute('aria-label', 'Selected company tags');
    const input = document.createElement('input');
    input.className = 'sourcing-tag-editor__input';
    input.type = 'text';
    input.placeholder = 'Type a tag and press Enter';
    input.autocomplete = 'off';
    input.maxLength = 80; // Server limit is 40; allow visibly reporting overflow.
    input.setAttribute('aria-label', 'Add a company tag');
    input.setAttribute('aria-autocomplete', 'list');
    input.setAttribute('aria-expanded', 'false');
    const options = document.createElement('div');
    options.className = 'sourcing-tag-editor__suggestions';
    options.setAttribute('role', 'listbox');
    options.id = `${field.id || 'tags'}-suggestions`;
    options.hidden = true;
    input.setAttribute('aria-controls', options.id);
    const message = document.createElement('div');
    message.className = 'sourcing-tag-editor__error';
    message.setAttribute('role', 'alert');
    message.hidden = true;
    const help = document.createElement('div');
    help.className = 'sourcing-tag-editor__hint';
    help.textContent = 'Enter or comma to add · Backspace to remove · Up to 10 tags';
    tokens.appendChild(input);
    // Keep the listbox outside clipping form cards/footers. A fixed-position
    // popup can flip above the input when the field is near the viewport edge.
    widget.append(tokens);
    document.body.appendChild(options);
    field.insertAdjacentElement('afterend', widget);
    widget.insertAdjacentElement('afterend', message);
    message.insertAdjacentElement('afterend', help);
    // Only hide the existing source input after the enhanced control is mounted.
    field.type = 'hidden';
    field.removeAttribute('list');

    let tags = [];
    let activeIndex = -1;
    let currentSuggestions = [];
    const feedback = (text = '') => {
      message.textContent = text;
      message.hidden = !text;
      widget.classList.toggle('has-error', !!text);
    };
    const matches = (text) => {
      const query = norm(text);
      return suggested.filter((tag) => !tags.some((selected) => norm(selected) === norm(tag))
        && (!query || norm(tag).includes(query))).slice(0, 8);
    };
    const sync = () => { field.value = tags.join(', '); render(); };
    const closeOptions = () => {
      options.hidden = true;
      options.replaceChildren();
      activeIndex = -1;
      currentSuggestions = [];
      input.setAttribute('aria-expanded', 'false');
      input.removeAttribute('aria-activedescendant');
    };
    const positionOptions = () => {
      if (options.hidden) return;
      const rect = widget.getBoundingClientRect();
      const edge = 8;
      const gap = 5;
      // Do not leave a detached popup visible if the containing form scrolls away.
      if (rect.bottom < edge || rect.top > window.innerHeight - edge) {
        closeOptions(); return;
      }
      const width = Math.min(rect.width, window.innerWidth - edge * 2);
      const left = Math.max(edge, Math.min(rect.left, window.innerWidth - width - edge));
      const below = Math.max(0, window.innerHeight - rect.bottom - gap - edge);
      const above = Math.max(0, rect.top - gap - edge);
      const naturalHeight = Math.min(options.scrollHeight, 240);
      const flipAbove = below < naturalHeight && above > below;
      const available = flipAbove ? above : below;
      const height = Math.min(naturalHeight, Math.max(0, available));
      if (height < 36) { closeOptions(); return; }
      options.style.left = `${left}px`;
      options.style.width = `${width}px`;
      options.style.maxHeight = `${height}px`;
      options.style.top = `${flipAbove ? rect.top - gap - height : rect.bottom + gap}px`;
    };
    const repositionOnScroll = () => { if (!options.hidden) positionOptions(); };
    // Capture also catches scrolls from nested form sections and the page itself.
    document.addEventListener('scroll', repositionOnScroll, { capture: true, passive: true });
    window.addEventListener('resize', repositionOnScroll, { passive: true });
    const renderOptions = () => {
      currentSuggestions = matches(input.value);
      activeIndex = -1;
      options.replaceChildren();
      if (!currentSuggestions.length || document.activeElement !== input) { closeOptions(); return; }
      currentSuggestions.forEach((name, index) => {
        const row = document.createElement('button');
        row.type = 'button';
        row.className = 'sourcing-tag-editor__option';
        row.textContent = name;
        row.id = `${options.id}-option-${index}`;
        row.setAttribute('role', 'option');
        row.setAttribute('aria-selected', 'false');
        row.addEventListener('pointerdown', (event) => event.preventDefault());
        row.addEventListener('click', () => { add(name); input.focus(); });
        options.appendChild(row);
      });
      options.hidden = false;
      input.setAttribute('aria-expanded', 'true');
      positionOptions();
    };
    const render = () => {
      tokens.querySelectorAll('[data-tag-token]').forEach((node) => node.remove());
      tags.forEach((tag) => {
        const chip = document.createElement('span');
        chip.className = 'sourcing-tag-editor__chip';
        chip.setAttribute('data-tag-token', '');
        const label = document.createElement('span');
        label.textContent = tag;
        const remove = document.createElement('button');
        remove.type = 'button';
        remove.textContent = '×';
        remove.title = `Remove ${tag}`;
        remove.setAttribute('aria-label', `Remove ${tag}`);
        remove.addEventListener('click', () => {
          tags = tags.filter((item) => norm(item) !== norm(tag));
          feedback(); sync(); input.focus(); renderOptions();
        });
        chip.append(label, remove);
        tokens.insertBefore(chip, input);
      });
      input.placeholder = tags.length ? 'Add another tag…' : 'Type a tag and press Enter';
      widget.classList.toggle('is-full', tags.length >= 10);
      renderOptions();
    };
    function add(raw) {
      const candidate = canonical(raw);
      if (!candidate) return true;
      if (invalid(candidate) || candidate.includes(',')) {
        feedback('Each tag must be 40 characters or fewer and cannot contain special delimiters.');
        return false;
      }
      if (tags.some((tag) => norm(tag) === norm(candidate))) {
        input.value = ''; feedback(); renderOptions(); return true;
      }
      if (tags.length >= 10) { feedback('A company can have no more than 10 tags.'); return false; }
      const name = suggested.find((tag) => norm(tag) === norm(candidate)) || candidate;
      tags.push(name);
      input.value = '';
      feedback(); sync();
      return true;
    }
    // A previously saved form or a server-returned validation error stays intact.
    field.value.split(',').forEach((part) => {
      const item = canonical(part);
      if (item && !tags.some((tag) => norm(tag) === norm(item))) tags.push(item);
    });
    sync();

    input.addEventListener('focus', renderOptions);
    input.addEventListener('input', () => { feedback(); renderOptions(); });
    input.addEventListener('blur', () => { window.setTimeout(closeOptions, 100); });
    input.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') { closeOptions(); return; }
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        if (options.hidden) renderOptions();
        if (!currentSuggestions.length) return;
        event.preventDefault();
        activeIndex = (activeIndex + (event.key === 'ArrowDown' ? 1 : -1) + currentSuggestions.length) % currentSuggestions.length;
        options.querySelectorAll('[role="option"]').forEach((item, index) => item.setAttribute('aria-selected', String(index === activeIndex)));
        input.setAttribute('aria-activedescendant', `${options.id}-option-${activeIndex}`);
        return;
      }
      if (event.key === 'Backspace' && !input.value && tags.length) {
        event.preventDefault(); tags.pop(); feedback(); sync(); return;
      }
      if (event.key === 'Enter' || event.key === ',') {
        event.preventDefault();
        const selected = activeIndex >= 0 && currentSuggestions[activeIndex];
        add(selected || input.value);
        return;
      }
    });
    form.addEventListener('submit', (event) => {
      if (input.value.trim() && !add(input.value)) {
        event.preventDefault(); input.focus(); return;
      }
      field.value = tags.join(', ');
      closeOptions();
    });
  });
})();
