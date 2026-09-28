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
    const categoryFilter = materialPicker.querySelector("[data-material-category-filter]");
    const count = materialPicker.querySelector("[data-material-selected-count]");
    const checkboxes = [...materialPicker.querySelectorAll('input[type="checkbox"]')];
    const knownCategories = categoryFilter
      ? [...categoryFilter.options]
        .map((option) => option.value)
        .filter((value) => value && value !== "__uncategorized__")
      : [];
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
      const category = String(categoryFilter?.value || "").trim();
      optionRows.forEach(({ label, row }) => {
        if (!row) return;
        const text = String(label?.textContent || "").toLocaleLowerCase();
        let categoryMatches = true;
        if (category === "__uncategorized__") {
          categoryMatches = !knownCategories.some((known) => text.startsWith(`${known.toLocaleLowerCase()} ·`));
        } else if (category) {
          categoryMatches = text.startsWith(`${category.toLocaleLowerCase()} ·`);
        }
        row.classList.toggle(
          "sourcing-material-picker-option-hidden",
          (!!term && !text.includes(term)) || !categoryMatches,
        );
      });
    };
    checkboxes.forEach((checkbox) => checkbox.addEventListener("change", updateCount));
    search?.addEventListener("input", filterOptions);
    categoryFilter?.addEventListener("change", filterOptions);
    updateCount();
  }

  const dynamicMaterialCategories = new Map();
  const addCategoryOption = (select, value) => {
    const cleanValue = String(value || "").trim();
    if (!select || !cleanValue) return;
    const key = cleanValue.toLocaleLowerCase();
    const exists = [...select.options].some((option) => option.value.toLocaleLowerCase() === key);
    if (exists) return;
    const sentinel = [...select.options].find((option) => option.value === "__new__");
    const option = new Option(cleanValue, cleanValue);
    if (sentinel) select.add(option, sentinel.index);
    else select.add(option);
  };
  const registerDynamicCategory = (value) => {
    const cleanValue = String(value || "").trim();
    if (!cleanValue) return;
    const key = cleanValue.toLocaleLowerCase();
    if (!dynamicMaterialCategories.has(key)) dynamicMaterialCategories.set(key, cleanValue);
    document.querySelectorAll("[data-material-category-select]").forEach((select) => {
      addCategoryOption(select, cleanValue);
    });
  };

  const initializeCategoryScope = (scope) => {
    if (!scope || scope.dataset.materialCategoryInitialized === "1") return;
    const select = scope.querySelector("[data-material-category-select]");
    const newCategoryField = scope.querySelector("[data-new-material-category-field]");
    if (!select || !newCategoryField) return;
    scope.dataset.materialCategoryInitialized = "1";
    dynamicMaterialCategories.forEach((value) => addCategoryOption(select, value));
    const newCategoryInput = newCategoryField.querySelector("[data-new-material-category-input]");
    const sync = () => { newCategoryField.hidden = select.value !== "__new__"; };
    select.addEventListener("change", sync);
    // Propagate only a committed text value. Using every input keystroke would create
    // partial category options (for example F, Fi, Fir, Fire) in sibling rows.
    newCategoryInput?.addEventListener("change", () => registerDynamicCategory(newCategoryInput.value));
    if (newCategoryInput?.value) registerDynamicCategory(newCategoryInput.value);
    sync();
  };
  document.querySelectorAll("[data-material-category-scope]").forEach(initializeCategoryScope);

  const inlineMaterialFormset = document.querySelector("[data-new-material-formset]");
  if (inlineMaterialFormset) {
    const rows = inlineMaterialFormset.querySelector("[data-new-material-rows]");
    const template = inlineMaterialFormset.querySelector("[data-new-material-template]");
    const addButton = inlineMaterialFormset.querySelector("[data-add-new-material]");
    const totalForms = inlineMaterialFormset.querySelector('input[name$="-TOTAL_FORMS"]');
    const maxForms = inlineMaterialFormset.querySelector('input[name$="-MAX_NUM_FORMS"]');

    const visibleRows = () => [...rows.querySelectorAll("[data-new-material-row]")].filter((row) => !row.hidden);
    const updateRowNumbers = () => {
      visibleRows().forEach((row, index) => {
        const number = row.querySelector("[data-new-material-row-number]");
        if (number) number.textContent = String(index + 1);
      });
      const total = Number.parseInt(totalForms?.value || "0", 10);
      const maximum = Number.parseInt(maxForms?.value || "0", 10);
      if (addButton && maximum > 0) addButton.disabled = total >= maximum;
    };

    const wireRow = (row) => {
      row.querySelectorAll("[data-material-category-scope]").forEach(initializeCategoryScope);
      const removeButton = row.querySelector("[data-remove-new-material]");
      removeButton?.addEventListener("click", () => {
        const deleteInput = row.querySelector('input[name$="-DELETE"]');
        if (deleteInput) deleteInput.checked = true;
        row.hidden = true;
        updateRowNumbers();
      });
    };

    rows?.querySelectorAll("[data-new-material-row]").forEach(wireRow);
    addButton?.addEventListener("click", () => {
      if (!rows || !template || !totalForms) return;
      const index = Number.parseInt(totalForms.value || "0", 10);
      const maximum = Number.parseInt(maxForms?.value || "0", 10);
      if (maximum > 0 && index >= maximum) return;
      const wrapper = document.createElement("div");
      wrapper.innerHTML = template.innerHTML.replaceAll("__prefix__", String(index)).trim();
      const row = wrapper.firstElementChild;
      if (!row) return;
      rows.appendChild(row);
      totalForms.value = String(index + 1);
      wireRow(row);
      updateRowNumbers();
      row.querySelector('input[name$="-name"]')?.focus();
    });
    updateRowNumbers();
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
