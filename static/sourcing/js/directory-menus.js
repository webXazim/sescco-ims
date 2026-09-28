(() => {
  const selector = ".sourcing-row-menu";
  const viewportEdge = 8;
  const gap = 6;
  let active = null;
  let frame = 0;

  const directPanel = (menu) => [...menu.children].find((node) => node instanceof HTMLElement && node.tagName === "DIV");
  const directSummary = (menu) => [...menu.children].find((node) => node instanceof HTMLElement && node.tagName === "SUMMARY");

  const clearFloatingStyles = (panel) => {
    for (const property of ["left", "right", "top", "bottom", "maxHeight"]) panel.style[property] = "";
  };

  const restore = (state = active) => {
    if (!state) return;
    if (active === state) active = null;
    if (frame) {
      cancelAnimationFrame(frame);
      frame = 0;
    }

    const { menu, panel, marker, summary } = state;
    if (marker.isConnected && menu.isConnected) marker.replaceWith(panel);
    else if (panel.isConnected) panel.remove();

    panel.classList.remove("sourcing-row-menu__floating-panel");
    panel.removeAttribute("data-sourcing-floating-menu");
    clearFloatingStyles(panel);
    menu.classList.remove("is-floating-open");
    summary?.setAttribute("aria-expanded", menu.open ? "true" : "false");
  };

  const closeActive = ({ focusSummary = false } = {}) => {
    const state = active;
    if (!state) return;
    if (state.menu.open) state.menu.open = false;
    restore(state);
    if (focusSummary) state.summary?.focus({ preventScroll: true });
  };

  const position = () => {
    frame = 0;
    if (!active) return;
    const { menu, panel, summary } = active;
    if (!menu.isConnected || !summary.isConnected || !panel.isConnected) {
      restore(active);
      return;
    }

    const trigger = summary.getBoundingClientRect();
    if (trigger.bottom < 0 || trigger.top > window.innerHeight || trigger.right < 0 || trigger.left > window.innerWidth) {
      closeActive();
      return;
    }

    panel.style.maxHeight = "";
    const initialPanel = panel.getBoundingClientRect();
    const availableBelow = Math.max(0, window.innerHeight - trigger.bottom - gap - viewportEdge);
    const availableAbove = Math.max(0, trigger.top - gap - viewportEdge);
    const placeAbove = initialPanel.height > availableBelow && availableAbove > availableBelow;
    const availableVertical = placeAbove ? availableAbove : availableBelow;
    const maxUsableHeight = Math.max(72, Math.min(window.innerHeight - viewportEdge * 2, availableVertical || window.innerHeight - viewportEdge * 2));
    panel.style.maxHeight = `${Math.floor(maxUsableHeight)}px`;

    const panelRect = panel.getBoundingClientRect();
    let left = trigger.right - panelRect.width;
    left = Math.max(viewportEdge, Math.min(left, window.innerWidth - panelRect.width - viewportEdge));

    let top;
    if (placeAbove) top = trigger.top - gap - panelRect.height;
    else top = trigger.bottom + gap;
    top = Math.max(viewportEdge, Math.min(top, window.innerHeight - panelRect.height - viewportEdge));

    panel.style.left = `${Math.round(left)}px`;
    panel.style.top = `${Math.round(top)}px`;
  };

  const schedulePosition = () => {
    if (!active || frame) return;
    frame = requestAnimationFrame(position);
  };

  const floatMenu = (menu) => {
    if (!(menu instanceof HTMLDetailsElement) || !menu.open) return;
    if (active?.menu === menu) {
      schedulePosition();
      return;
    }
    closeActive();

    const panel = directPanel(menu);
    const summary = directSummary(menu);
    if (!panel || !summary) return;

    const marker = document.createComment("sourcing-row-menu-panel");
    panel.before(marker);
    document.body.appendChild(panel);
    panel.classList.add("sourcing-row-menu__floating-panel");
    panel.setAttribute("data-sourcing-floating-menu", "");
    menu.classList.add("is-floating-open");
    summary.setAttribute("aria-expanded", "true");
    active = { menu, panel, marker, summary };
    schedulePosition();
  };

  document.addEventListener("toggle", (event) => {
    const menu = event.target;
    if (!(menu instanceof HTMLDetailsElement) || !menu.matches(selector)) return;
    if (menu.open) floatMenu(menu);
    else if (active?.menu === menu) restore(active);
  }, true);

  document.addEventListener("click", (event) => {
    if (!active) return;
    const target = event.target;
    if (!(target instanceof Node)) return;
    if (active.menu.contains(target) || active.panel.contains(target)) return;
    closeActive();
  }, true);

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || !active) return;
    event.preventDefault();
    closeActive({ focusSummary: true });
  });

  document.addEventListener("scroll", schedulePosition, true);
  window.addEventListener("resize", schedulePosition, { passive: true });

  const observer = new MutationObserver(() => {
    if (active && !active.menu.isConnected) restore(active);
  });
  observer.observe(document.body, { childList: true, subtree: true });

  document.querySelectorAll(selector).forEach((menu) => {
    const summary = directSummary(menu);
    summary?.setAttribute("aria-expanded", menu.open ? "true" : "false");
    if (menu.open) floatMenu(menu);
  });
})();
