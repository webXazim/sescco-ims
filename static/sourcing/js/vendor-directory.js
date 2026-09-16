(() => {
  const storageKey = "sescco:sourcing:vendor-columns:v1";
  const table = document.querySelector("[data-vendor-table]");
  const toggles = [...document.querySelectorAll("[data-column-toggle]")];
  const apply = (state) => {
    if (!table) return;
    Object.entries(state).forEach(([name, visible]) => {
      table.querySelectorAll(`[data-column="${name}"]`).forEach((cell) => { cell.hidden = !visible; });
      const toggle = toggles.find((item) => item.dataset.columnToggle === name);
      if (toggle) toggle.checked = !!visible;
    });
  };
  if (table && toggles.length) {
    let state = Object.fromEntries(toggles.map((item) => [item.dataset.columnToggle, true]));
    try { state = { ...state, ...JSON.parse(localStorage.getItem(storageKey) || "{}") }; } catch (_) {}
    apply(state);
    toggles.forEach((toggle) => toggle.addEventListener("change", () => {
      state[toggle.dataset.columnToggle] = toggle.checked;
      try { localStorage.setItem(storageKey, JSON.stringify(state)); } catch (_) {}
      apply(state);
    }));
  }

  const tabs = [...document.querySelectorAll("[data-sourcing-tab]")];
  const panels = [...document.querySelectorAll("[data-sourcing-panel]")];
  if (tabs.length && panels.length) {
    const activate = (key) => {
      tabs.forEach((tab) => tab.classList.toggle("active", tab.dataset.sourcingTab === key));
      panels.forEach((panel) => { panel.hidden = panel.dataset.sourcingPanel !== key; });
    };
    tabs.forEach((tab) => tab.addEventListener("click", () => activate(tab.dataset.sourcingTab)));
    const requested = location.hash.replace("#", "");
    if (tabs.some((tab) => tab.dataset.sourcingTab === requested)) activate(requested);
  }
})();
