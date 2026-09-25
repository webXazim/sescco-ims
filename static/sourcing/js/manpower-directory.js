(() => {
  const storageKey = "sescco:sourcing:manpower-columns:v1";
  const table = document.querySelector("[data-manpower-table]");
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
    const hasTab = (key) => tabs.some((tab) => tab.dataset.sourcingTab === key);
    const activate = (key) => {
      if (!hasTab(key)) return false;
      tabs.forEach((tab) => tab.classList.toggle("active", tab.dataset.sourcingTab === key));
      panels.forEach((panel) => { panel.hidden = panel.dataset.sourcingPanel !== key; });
      return true;
    };
    const defaultTab = tabs.find((tab) => tab.classList.contains("active"))?.dataset.sourcingTab || tabs[0].dataset.sourcingTab;
    tabs.forEach((tab) => tab.addEventListener("click", () => {
      const key = tab.dataset.sourcingTab;
      if (activate(key) && location.hash !== `#${key}`) history.replaceState(null, "", `#${key}`);
    }));
    document.querySelectorAll("[data-sourcing-open-tab]").forEach((link) => {
      link.addEventListener("click", (event) => {
        const key = link.dataset.sourcingOpenTab;
        if (!activate(key)) return;
        event.preventDefault();
        if (location.hash !== `#${key}`) history.pushState(null, "", `#${key}`);
        document.querySelector(`[data-sourcing-panel="${key}"]`)?.scrollIntoView({ block: "start" });
      });
    });
    const activateHash = () => {
      const requested = location.hash.replace("#", "");
      activate(hasTab(requested) ? requested : defaultTab);
    };
    window.addEventListener("hashchange", activateHash);
    window.addEventListener("popstate", activateHash);
    activateHash();
  }
})();
