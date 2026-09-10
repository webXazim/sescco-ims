(() => {
  const switchers = [...document.querySelectorAll('[data-platform-switcher]')];
  if (!switchers.length) return;
  const closeExcept = (keep = null) => switchers.forEach((item) => { if (item !== keep) item.removeAttribute('open'); });
  switchers.forEach((item) => item.addEventListener('toggle', () => { if (item.open) closeExcept(item); }));
  document.addEventListener('click', (event) => { if (!event.target.closest('[data-platform-switcher]')) closeExcept(); });
  document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape') return;
    const open = switchers.find((item) => item.open);
    if (!open) return;
    open.removeAttribute('open');
    open.querySelector('summary')?.focus();
  });
})();
