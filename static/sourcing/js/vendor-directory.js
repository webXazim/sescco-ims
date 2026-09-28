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

  const materialPicker = document.querySelector("[data-material-picker]");
  if (materialPicker) {
    const search = materialPicker.querySelector("[data-material-picker-search]");
    const count = materialPicker.querySelector("[data-material-selected-count]");
    const checkboxes = [...materialPicker.querySelectorAll('input[type="checkbox"]')];
    const optionRows = checkboxes.map((checkbox) => {
      const label = checkbox.closest("label") || materialPicker.querySelector(`label[for="${checkbox.id}"]`);
      return { checkbox, label, row: label?.parentElement || label };
    });
    const updateCount = () => {
      if (!count) return;
      const selected = checkboxes.filter((checkbox) => checkbox.checked).length;
      count.textContent = `${selected} selected`;
    };
    const filterOptions = () => {
      const term = String(search?.value || "").trim().toLocaleLowerCase();
      optionRows.forEach(({ label, row }) => {
        if (!row) return;
        const text = String(label?.textContent || "").toLocaleLowerCase();
        row.classList.toggle("sourcing-material-picker-option-hidden", !!term && !text.includes(term));
      });
    };
    checkboxes.forEach((checkbox) => checkbox.addEventListener("change", updateCount));
    search?.addEventListener("input", filterOptions);
    updateCount();
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
