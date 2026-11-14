/* Stop wheel-induced changes of focused numeric/date/select controls on every page.
   Keyboard, pointer increment buttons, and scrolling elsewhere remain available. */
(() => {
  if (window.__sesccoWheelValueGuardInstalled) return;
  window.__sesccoWheelValueGuardInstalled = true;
  document.addEventListener("wheel", (event) => {
    const target = event.target;
    if (!(target instanceof Element)) return;
    const control = target.closest('input[type="number"], input[type="date"], input[type="time"], input[type="datetime-local"], select, [role="spinbutton"]');
    if (!control || document.activeElement !== control) return;
    event.preventDefault();
    // Blur as an additional safeguard for browsers that increment before default.
    if (typeof control.blur === "function") control.blur();
  }, { capture: true, passive: false });
})();
