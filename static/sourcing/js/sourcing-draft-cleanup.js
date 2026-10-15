/* Clear an in-flight create draft once the server has navigated to a new URL.
 * A failed POST stays on its original form URL and retains bound form values. */
(() => {
  'use strict';
  try {
    for (let i = sessionStorage.length - 1; i >= 0; i--) {
      const key = sessionStorage.key(i);
      if (!key || !(key.startsWith('sescco:sourcing:provider-draft:v1:') || key.startsWith('sescco:sourcing:page-draft:v1:'))) continue;
      let entry;
      try { entry = JSON.parse(sessionStorage.getItem(key)); } catch (error) { continue; }
      if ((entry?.submitted || entry?.pending) && entry.path !== location.pathname) sessionStorage.removeItem(key);
    }
  } catch (error) { /* private browsing or restricted storage: normal navigation works */ }
  // Session-only drafts must not survive an explicit sign-out in the same tab.
  document.addEventListener('submit', event => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) return;
    let pathname = '';
    try { pathname = new URL(form.action, location.href).pathname; } catch (error) { return; }
    if (!/\/logout\/?$/.test(pathname)) return;
    try {
      for (let i = sessionStorage.length - 1; i >= 0; i--) {
        const key = sessionStorage.key(i);
        if (key?.startsWith('sescco:sourcing:provider-draft:v1:') || key?.startsWith('sescco:sourcing:page-draft:v1:') || key?.startsWith('sescco:sourcing:reference-modal:v1:')) sessionStorage.removeItem(key);
      }
    } catch (error) { /* do not interfere with logout */ }
  });
})();
