(() => {
  const CONTROL_SELECTOR = 'input:not([type="hidden"]), select, textarea';
  const REQUIRED_SELECTOR = '[required], [data-required="true"]';

  const wrapperFor = (control) => control?.closest?.('.field, .form-field, .login-field, [data-field]') || control?.closest?.('label') || null;

  const labelFor = (control) => {
    if (!control) return null;
    if (control.id) {
      try {
        const label = document.querySelector(`label[for="${CSS.escape(control.id)}"]`);
        if (label) return label;
      } catch (_) {}
    }
    const wrappingLabel = control.closest?.('label');
    if (wrappingLabel) {
      const span = Array.from(wrappingLabel.children).find((node) => node.tagName === 'SPAN');
      return span || wrappingLabel;
    }
    const wrapper = wrapperFor(control);
    return wrapper?.querySelector?.(':scope > label, :scope > .field-label, :scope > span:first-child') || null;
  };

  const syncConditionalRequired = (root = document) => {
    if (!root?.querySelectorAll) return;
    root.querySelectorAll('[data-required-when-name][data-required-when-value]').forEach((control) => {
      const form = control.form || control.closest?.('form') || document;
      const sourceName = control.dataset.requiredWhenName;
      const expected = control.dataset.requiredWhenValue;
      const source = form?.querySelector?.(`[name="${CSS.escape(sourceName)}"]`);
      const requiredNow = String(source?.value ?? '') === String(expected);
      control.required = requiredNow;
      if (requiredNow) {
        control.dataset.required = 'true';
        control.setAttribute('aria-required', 'true');
      } else {
        control.removeAttribute('data-required');
        control.removeAttribute('aria-required');
        clearInvalid(control);
        const label = labelFor(control);
        if (label?.dataset?.requiredLabel === 'true') {
          label.classList.remove('required');
          delete label.dataset.requiredLabel;
        }
      }
    });
  };

  const decorate = (root = document) => {
    if (!root?.querySelectorAll) return;
    root.querySelectorAll(REQUIRED_SELECTOR).forEach((control) => {
      if (!control.matches?.(CONTROL_SELECTOR)) return;
      control.setAttribute('aria-required', 'true');
      const label = labelFor(control);
      if (label && !label.classList.contains('required')) {
        label.classList.add('required');
        label.dataset.requiredLabel = 'true';
      }
    });
  };

  const valueMissing = (control) => {
    if (!control || control.disabled || control.type === 'hidden') return false;
    if (!(control.required || control.dataset.required === 'true')) return false;
    if (control.type === 'checkbox' || control.type === 'radio') return !control.checked;
    return String(control.value ?? '').trim() === '';
  };

  const clearInvalid = (control) => {
    if (!control) return;
    control.removeAttribute('aria-invalid');
    const wrapper = wrapperFor(control);
    wrapper?.classList.remove('is-invalid');
    wrapper?.querySelectorAll?.('.field-required-message[data-client-required="true"]').forEach((node) => node.remove());
  };

  const markInvalid = (control, message = 'Required') => {
    if (!control) return;
    control.setAttribute('aria-invalid', 'true');
    const wrapper = wrapperFor(control);
    wrapper?.classList.add('is-invalid');
    if (wrapper && !wrapper.querySelector('.field-required-message[data-client-required="true"]')) {
      const indicator = document.createElement('span');
      indicator.className = 'field-required-message';
      indicator.dataset.clientRequired = 'true';
      indicator.textContent = message;
      wrapper.appendChild(indicator);
    }
  };

  const validateRequired = (root, { focus = true } = {}) => {
    if (!root?.querySelectorAll) return true;
    decorate(root);
    let first = null;
    root.querySelectorAll(REQUIRED_SELECTOR).forEach((control) => {
      if (!control.matches?.(CONTROL_SELECTOR)) return;
      if (valueMissing(control)) {
        markInvalid(control, control.dataset.requiredMessage || 'Required');
        if (!first) first = control;
      } else {
        clearInvalid(control);
      }
    });
    if (first && focus) {
      first.focus?.({ preventScroll: true });
      first.scrollIntoView?.({ behavior: 'smooth', block: 'center' });
    }
    return !first;
  };

  document.addEventListener('invalid', (event) => {
    const control = event.target;
    if (!control?.matches?.(CONTROL_SELECTOR)) return;
    markInvalid(control, control.dataset.requiredMessage || (control.validity?.valueMissing ? 'Required' : 'Check this value'));
  }, true);

  document.addEventListener('input', (event) => {
    const control = event.target;
    if (!control?.matches?.(CONTROL_SELECTOR)) return;
    if (!valueMissing(control)) clearInvalid(control);
  }, true);

  document.addEventListener('change', (event) => {
    const control = event.target;
    if (!control?.matches?.(CONTROL_SELECTOR)) return;
    syncConditionalRequired(control.form || document);
    decorate(control.form || document);
    if (!valueMissing(control)) clearInvalid(control);
  }, true);

  document.addEventListener('submit', (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) return;
    if (!validateRequired(form)) {
      event.preventDefault();
      event.stopImmediatePropagation();
    }
  }, true);

  const observer = new MutationObserver((records) => {
    records.forEach((record) => record.addedNodes.forEach((node) => {
      if (node.nodeType !== Node.ELEMENT_NODE) return;
      syncConditionalRequired(node.parentElement || document);
      if (node.matches?.(REQUIRED_SELECTOR)) decorate(node.parentElement || document);
      else decorate(node);
    }));
  });

  document.addEventListener('DOMContentLoaded', () => {
    syncConditionalRequired(document);
    decorate(document);
    observer.observe(document.body, { childList: true, subtree: true });
  });

  window.PlatformFormValidation = { decorate, syncConditionalRequired, validateRequired, markInvalid, clearInvalid, valueMissing };
})();
