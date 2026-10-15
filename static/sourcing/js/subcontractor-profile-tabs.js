/* Subcontractor profile sections: same one-panel-at-a-time behavior as Vendor/Manpower. */
(() => {
  "use strict";
  const bar = document.querySelector("[data-subcontractor-tabs]");
  if (!bar) return;
  const tabs = Array.from(bar.querySelectorAll('[role="tab"][data-sourcing-tab]'));
  const panels = Array.from(document.querySelectorAll('[role="tabpanel"][data-sourcing-panel]'));
  if (!tabs.length || !panels.length) return;
  const aliases = {
    overview: "company-information", company: "company-information",
    services: "service-catalog", "service-catalog": "service-catalog",
    "company-information": "company-information"
  };
  const available = new Set(tabs.map((tab) => tab.dataset.sourcingTab));
  const resolve = (fragment) => {
    let key = String(fragment || "").replace(/^#/, "");
    try { key = decodeURIComponent(key); } catch (_) { return "company-information"; }
    const normalized = aliases[key] || key;
    return available.has(normalized) ? normalized : "company-information";
  };
  const activate = (key, { focus = false } = {}) => {
    const selected = resolve(key);
    tabs.forEach((tab) => {
      const active = tab.dataset.sourcingTab === selected;
      tab.classList.toggle("active", active);
      tab.setAttribute("aria-selected", String(active));
      tab.tabIndex = active ? 0 : -1;
      if (active && focus) tab.focus();
    });
    panels.forEach((panel) => {
      panel.hidden = panel.dataset.sourcingPanel !== selected;
    });
    return selected;
  };
  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => {
      const selected = activate(tab.dataset.sourcingTab);
      if (window.location.hash !== `#${selected}`) {
        window.history.replaceState(null, "", `#${selected}`);
      }
    });
    tab.addEventListener("keydown", (event) => {
      let target;
      if (event.key === "ArrowRight") target = (index + 1) % tabs.length;
      else if (event.key === "ArrowLeft") target = (index - 1 + tabs.length) % tabs.length;
      else if (event.key === "Home") target = 0;
      else if (event.key === "End") target = tabs.length - 1;
      else return;
      event.preventDefault();
      const selected = activate(tabs[target].dataset.sourcingTab, { focus: true });
      if (window.location.hash !== `#${selected}`) {
        window.history.replaceState(null, "", `#${selected}`);
      }
    });
  });
  const activateFromLocation = () => {
    const selected = activate(window.location.hash);
    // Retain deep links and server-paginated catalog/document URLs.
    if (window.location.hash && resolve(window.location.hash) === selected) {
      window.requestAnimationFrame(() => bar.scrollIntoView({ block: "start" }));
    }
  };
  window.addEventListener("hashchange", activateFromLocation);
  window.addEventListener("popstate", activateFromLocation);
  activateFromLocation();
})();
