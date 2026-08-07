(() => {
  const body = document.body;
  document.querySelectorAll("[data-sidebar-toggle]").forEach((button) => {
    button.addEventListener("click", () => body.classList.toggle("sidebar-open"));
  });
  document.addEventListener("click", (event) => {
    if (
      body.classList.contains("sidebar-open") &&
      !event.target.closest(".sidebar") &&
      !event.target.closest("[data-sidebar-toggle]")
    ) {
      body.classList.remove("sidebar-open");
    }
  });

  const setFilterPanelState = (button, panel, open) => {
    panel.classList.toggle("is-hidden", !open);
    button.textContent = open ? "Hide filters" : "More filters";
    button.setAttribute("aria-expanded", String(open));
  };

  document.querySelectorAll("[data-toggle-filter-panel]").forEach((button) => {
    const panel = button.closest("[data-filter-form]")?.querySelector("[data-filter-panel]");
    if (panel) setFilterPanelState(button, panel, !panel.classList.contains("is-hidden"));
  });

  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-toggle-filter-panel]");
    if (!button) return;
    const panel = button.closest("[data-filter-form]")?.querySelector("[data-filter-panel]");
    if (panel) setFilterPanelState(button, panel, panel.classList.contains("is-hidden"));
  });

  document.querySelectorAll("[data-filter-form]").forEach((form) => {
    const preset = form.querySelector('[name="date_preset"]');
    const from = form.querySelector('[name="date_from"]');
    const to = form.querySelector('[name="date_to"]');
    const markCustom = () => { if (preset && (from?.value || to?.value)) preset.value = "custom"; };
    from?.addEventListener("change", markCustom);
    to?.addEventListener("change", markCustom);
    preset?.addEventListener("change", () => {
      if (preset.value !== "custom") {
        if (from) from.value = "";
        if (to) to.value = "";
      }
    });
  });

  const liveFilterForm = document.querySelector("[data-live-filter-form]");
  if (liveFilterForm) {
    let liveFilterTimer = null;
    let liveFilterRequest = null;

    const cleanFilterUrl = () => {
      const params = new URLSearchParams();
      new FormData(liveFilterForm).forEach((value, key) => {
        const normalized = String(value).trim();
        if (normalized) params.append(key, normalized);
      });
      params.delete("page");
      if (params.get("status") === "active") params.delete("status");
      if (params.get("sort") === "project") params.delete("sort");
      if (params.get("date_field") === "latest_addition_date") params.delete("date_field");

      const defaults = (liveFilterForm.dataset.defaultColumns || "").split(",").filter(Boolean);
      const columns = params.getAll("columns");
      if (defaults.length === columns.length && defaults.every((value, index) => value === columns[index])) {
        params.delete("columns");
      }
      const query = params.toString();
      return `${window.location.pathname}${query ? `?${query}` : ""}`;
    };

    const refreshFilterResults = async () => {
      window.clearTimeout(liveFilterTimer);
      liveFilterRequest?.abort();
      liveFilterRequest = new AbortController();
      const url = cleanFilterUrl();
      const results = document.querySelector("[data-filter-results]");
      const status = liveFilterForm.querySelector("[data-filter-live-status]");
      if (results) results.setAttribute("aria-busy", "true");
      if (status) status.textContent = "Searching…";

      try {
        const response = await fetch(url, {
          headers: { "X-Requested-With": "XMLHttpRequest" },
          signal: liveFilterRequest.signal,
        });
        if (!response.ok) throw new Error("Search request failed");
        const nextPage = new DOMParser().parseFromString(await response.text(), "text/html");
        const nextResults = nextPage.querySelector("[data-filter-results]");
        const currentHead = document.querySelector(".page-head");
        const nextHead = nextPage.querySelector(".page-head");
        if (!results || !nextResults) throw new Error("Search results are unavailable");
        results.innerHTML = nextResults.innerHTML;
        if (currentHead && nextHead) currentHead.replaceWith(nextHead);
        const topSearch = document.querySelector('.top-search input[name="q"]');
        const search = liveFilterForm.querySelector("[data-live-filter-search]");
        if (topSearch && search) topSearch.value = search.value;
        window.history.replaceState({}, "", url);
        if (status) status.textContent = "Updated";
      } catch (error) {
        if (error.name !== "AbortError") window.location.assign(url);
      } finally {
        results?.removeAttribute("aria-busy");
      }
    };

    const search = liveFilterForm.querySelector("[data-live-filter-search]");
    const datePreset = liveFilterForm.querySelector('[name="date_preset"]');
    const dateFrom = liveFilterForm.querySelector('[name="date_from"]');
    const dateTo = liveFilterForm.querySelector('[name="date_to"]');
    const dateRange = liveFilterForm.querySelector("[data-quick-date-range]");
    const showDateRange = (show) => dateRange?.classList.toggle("is-hidden", !show);

    search?.addEventListener("input", () => {
      window.clearTimeout(liveFilterTimer);
      liveFilterRequest?.abort();
      const status = liveFilterForm.querySelector("[data-filter-live-status]");
      if (status) status.textContent = "Typing…";
      liveFilterTimer = window.setTimeout(refreshFilterResults, 300);
    });

    liveFilterForm.querySelectorAll(".quick-filters select").forEach((select) => {
      select.addEventListener("change", () => {
        if (select.name === "date_preset" && select.value === "custom") {
          showDateRange(true);
          const status = liveFilterForm.querySelector("[data-filter-live-status]");
          if (status) status.textContent = "Choose dates";
          dateFrom?.focus();
          return;
        }
        if (select.name === "date_preset") showDateRange(false);
        refreshFilterResults();
      });
    });

    [dateFrom, dateTo].forEach((input) => {
      input?.addEventListener("change", () => {
        const hasDate = Boolean(dateFrom?.value || dateTo?.value);
        if (datePreset) datePreset.value = hasDate ? "custom" : "";
        showDateRange(hasDate);
        refreshFilterResults();
      });
    });

    const closeDateRange = () => {
      showDateRange(false);
      if (datePreset?.value === "custom" && !dateFrom?.value && !dateTo?.value) {
        datePreset.value = "";
        refreshFilterResults();
      }
    };

    liveFilterForm.querySelectorAll("[data-close-date-range]").forEach((button) => {
      button.addEventListener("click", closeDateRange);
    });

    liveFilterForm.querySelector("[data-clear-date-range]")?.addEventListener("click", () => {
      if (dateFrom) dateFrom.value = "";
      if (dateTo) dateTo.value = "";
      if (datePreset) datePreset.value = "";
      showDateRange(false);
      refreshFilterResults();
    });

    document.addEventListener("click", (event) => {
      const control = liveFilterForm.querySelector("[data-date-filter-control]");
      if (dateRange && !dateRange.classList.contains("is-hidden") && !control?.contains(event.target)) {
        closeDateRange();
      }
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && dateRange && !dateRange.classList.contains("is-hidden")) {
        closeDateRange();
        datePreset?.focus();
      }
    });

    liveFilterForm.addEventListener("submit", (event) => {
      event.preventDefault();
      window.location.assign(cleanFilterUrl());
    });
  }

  document.querySelectorAll("form").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (form.dataset.confirm && !window.confirm(form.dataset.confirm)) {
        event.preventDefault();
        return;
      }
      form.querySelectorAll("[data-submit-once]").forEach((button) => {
        button.disabled = true;
        button.dataset.originalText = button.textContent;
        button.textContent = "Saving…";
      });
    });
  });

  const numberValue = (value) => {
    const parsed = Number.parseFloat(value || "0");
    return Number.isFinite(parsed) ? parsed : 0;
  };
  const formatQuantity = (value) => {
    if (!Number.isFinite(value)) return "—";
    return value.toLocaleString(undefined, { maximumFractionDigits: 3 });
  };
  const escapeHtml = (value) =>
    String(value ?? "").replace(/[&<>'"]/g, (character) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      "'": "&#39;",
      '"': "&quot;",
    })[character]);

  const additionForm = document.querySelector("[data-stock-addition-form]");
  if (additionForm) {
    const project = additionForm.querySelector("#id_project");
    const material = additionForm.querySelector("#id_material_name");
    const supplier = additionForm.querySelector("#id_supplier");
    const quantity = additionForm.querySelector("#id_quantity");
    const matchPanel = document.querySelector("#liveMatchPanel");
    const quantityPreview = document.querySelector("#additionQuantityPreview");
    const currentPreview = document.querySelector("#currentBalancePreview");
    const newPreview = document.querySelector("#newBalancePreview");
    let currentBalance = null;
    let debounceTimer = null;

    const updateAdditionBalance = () => {
      const added = numberValue(quantity?.value);
      if (quantityPreview) quantityPreview.textContent = formatQuantity(added);
      if (currentPreview) {
        currentPreview.textContent = currentBalance === null ? "New record" : formatQuantity(currentBalance);
      }
      if (newPreview) {
        newPreview.textContent = formatQuantity((currentBalance || 0) + added);
      }
    };

    const renderMatch = (data) => {
      currentBalance = data.exact ? numberValue(data.exact.current_quantity) : null;
      updateAdditionBalance();
      if (!matchPanel) return;
      if (data.exact) {
        const item = data.exact;
        matchPanel.innerHTML = `<div class="match-panel"><div class="match-head"><div><div class="match-title">Existing stock record found</div><div class="micro">This submission will increase its current balance.</div></div><a class="btn btn-sm" href="${escapeHtml(item.url)}">Open record</a></div><div class="match-data"><div><span>Project</span><strong>${escapeHtml(item.project_code)}</strong></div><div><span>Material</span><strong>${escapeHtml(item.material_name)}</strong></div><div><span>Current balance</span><strong>${escapeHtml(item.current_quantity)} ${escapeHtml(item.unit)}</strong></div><div><span>Supplier</span><strong>${escapeHtml(item.supplier_name)}</strong></div></div></div>`;
      } else if (data.similar?.length) {
        matchPanel.innerHTML = `<div class="alert alert-warning"><strong>Similar stock record found.</strong> The project, material and supplier match, but the phone differs. Review the warning before creating a separate record.</div>`;
      } else {
        matchPanel.innerHTML = `<div class="alert alert-success">No exact stock identity exists. A new stock record will be created with this addition.</div>`;
      }
    };

    const checkMatch = () => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(async () => {
        const supplierOption = supplier?.selectedOptions[0];
        const supplierName = supplierOption?.dataset.name || "";
        const supplierPhone = supplierOption?.dataset.phone || "";
        if (![project?.value, material?.value.trim(), supplierName, supplierPhone].every(Boolean)) {
          currentBalance = null;
          if (matchPanel) matchPanel.innerHTML = "";
          updateAdditionBalance();
          return;
        }
        const params = new URLSearchParams({
          project: project.value,
          material_name: material.value,
          supplier_name: supplierName,
          supplier_phone: supplierPhone,
        });
        try {
          const response = await fetch(`${additionForm.dataset.matchUrl}?${params}`, {
            headers: { "X-Requested-With": "XMLHttpRequest" },
          });
          if (!response.ok) return;
          renderMatch(await response.json());
        } catch (_) {
          // The server still performs the authoritative match on submit.
        }
      }, 280);
    };

    [project, material, supplier].forEach((field) => {
      field?.addEventListener(field.tagName === "SELECT" ? "change" : "input", checkMatch);
    });
    quantity?.addEventListener("input", updateAdditionBalance);
    updateAdditionBalance();
    checkMatch();
  }

  const usageForm = document.querySelector("[data-stock-usage-form]");
  if (usageForm) {
    const projectSelect = usageForm.querySelector("[data-stock-picker-project]");
    const stockSelect = usageForm.querySelector("[data-stock-picker-select]");
    const searchInput = usageForm.querySelector("[data-stock-picker-search]");
    const quantity = usageForm.querySelector("#id_quantity");
    const pickerState = document.querySelector("#stockPickerState");
    const selectedSummary = document.querySelector("#usageSelectedSummary");
    const availablePreview = document.querySelector("#usageAvailablePreview");
    const quantityPreview = document.querySelector("#usageQuantityPreview");
    const newPreview = document.querySelector("#usageNewBalancePreview");
    let debounceTimer = null;
    let activeRequest = null;

    const updateUsageBalance = () => {
      const option = stockSelect?.selectedOptions?.[0];
      const hasRecord = Boolean(option?.value);
      const available = hasRecord && option.dataset.balance
        ? numberValue(option.dataset.balance)
        : null;
      const used = numberValue(quantity?.value);
      if (availablePreview) availablePreview.textContent = available === null ? "—" : formatQuantity(available);
      if (quantityPreview) quantityPreview.textContent = formatQuantity(used);
      if (newPreview) {
        if (available === null) {
          newPreview.textContent = "—";
          newPreview.classList.remove("text-danger");
        } else {
          const remaining = available - used;
          newPreview.textContent = formatQuantity(remaining);
          newPreview.classList.toggle("text-danger", remaining < 0);
        }
      }
      if (selectedSummary) {
        if (!hasRecord) {
          selectedSummary.innerHTML = '<p class="micro">Choose a project, search, then select the stock record to use.</p>';
        } else {
          selectedSummary.innerHTML = `<span class="tag">${escapeHtml(option.dataset.project || "")}</span><h3 class="summary-heading">${escapeHtml(option.dataset.material || option.textContent)}</h3><div class="summary-list"><div class="summary-row"><span class="summary-key">Supplier</span><span class="summary-value">${escapeHtml(option.dataset.supplier || "—")}</span></div><div class="summary-row"><span class="summary-key">Available</span><span class="summary-value">${escapeHtml(formatQuantity(available))} ${escapeHtml(option.dataset.unit || "")}</span></div></div>`;
        }
      }
    };

    const renderPickerResults = (results, selectedValue) => {
      if (!stockSelect) return;
      const options = ['<option value="">Select stock record</option>'];
      results.forEach((item) => {
        const selected = String(item.id) === String(selectedValue) ? " selected" : "";
        options.push(`<option value="${escapeHtml(item.id)}" data-balance="${escapeHtml(item.quantity)}" data-unit="${escapeHtml(item.unit)}" data-project="${escapeHtml(item.project_code)}" data-material="${escapeHtml(item.material_name)}" data-supplier="${escapeHtml(item.supplier_name)}"${selected}>${escapeHtml(item.material_name)} · ${escapeHtml(item.supplier_name)} (${escapeHtml(item.quantity_display)})</option>`);
      });
      stockSelect.innerHTML = options.join("");
      stockSelect.disabled = false;
      if (pickerState) {
        pickerState.textContent = results.length
          ? `${results.length} matching stock record${results.length === 1 ? "" : "s"}`
          : "No available stock matched this project and search.";
      }
      updateUsageBalance();
    };

    const loadStockOptions = async ({ preserveSelection = false } = {}) => {
      if (!stockSelect || !projectSelect) return;
      const project = projectSelect.value;
      const selectedValue = preserveSelection ? stockSelect.value : "";
      if (!project) {
        stockSelect.innerHTML = '<option value="">Select a project first</option>';
        stockSelect.disabled = true;
        if (pickerState) pickerState.textContent = "Select a project to load its available stock.";
        updateUsageBalance();
        return;
      }
      activeRequest?.abort();
      activeRequest = new AbortController();
      stockSelect.disabled = true;
      if (pickerState) pickerState.textContent = "Loading available stock…";
      const params = new URLSearchParams({ project, q: searchInput?.value.trim() || "" });
      try {
        const response = await fetch(`${usageForm.dataset.pickerUrl}?${params}`, {
          headers: { "X-Requested-With": "XMLHttpRequest" },
          signal: activeRequest.signal,
        });
        if (!response.ok) throw new Error("Unable to load stock records");
        const data = await response.json();
        renderPickerResults(data.results || [], selectedValue);
      } catch (error) {
        if (error.name === "AbortError") return;
        stockSelect.disabled = false;
        if (pickerState) pickerState.textContent = "Could not refresh stock records. Submit validation remains active.";
      }
    };

    projectSelect?.addEventListener("change", () => {
      if (searchInput) searchInput.value = "";
      loadStockOptions();
    });
    searchInput?.addEventListener("input", () => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => loadStockOptions({ preserveSelection: true }), 260);
    });
    stockSelect?.addEventListener("change", updateUsageBalance);
    quantity?.addEventListener("input", updateUsageBalance);
    updateUsageBalance();
    loadStockOptions({ preserveSelection: true });
  }
})();
