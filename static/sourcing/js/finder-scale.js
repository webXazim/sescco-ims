(() => {
  let controller = null;
  let timer = null;
  let requestSerial = 0;

  const roots = () => [...document.querySelectorAll("[data-sourcing-finder-root]")];

  const install = (root) => {
    const form = root.querySelector("form[data-sourcing-live-finder]");
    if (!form || form.dataset.scaleBound === "1") return;
    form.dataset.scaleBound = "1";

    const run = async (url, { push = true } = {}) => {
      if (controller) controller.abort();
      controller = new AbortController();
      const serial = ++requestSerial;
      root.dataset.loading = "1";
      try {
        const response = await fetch(url, {
          method: "GET",
          credentials: "same-origin",
          headers: { "X-Requested-With": "sourcing-finder-scale" },
          signal: controller.signal,
        });
        if (!response.ok) throw new Error(`Finder request failed: ${response.status}`);
        const html = await response.text();
        if (serial !== requestSerial) return;
        const parsed = new DOMParser().parseFromString(html, "text/html");
        const replacement = parsed.querySelector("[data-sourcing-finder-root]");
        if (!replacement) throw new Error("Finder response did not include bounded results root.");
        root.replaceWith(replacement);
        if (push) history.pushState({ sourcingFinder: true }, "", url);
        else history.replaceState({ sourcingFinder: true }, "", url);
        install(replacement);
      } catch (error) {
        if (error && error.name === "AbortError") return;
        window.location.assign(url);
      } finally {
        const current = document.querySelector("[data-sourcing-finder-root]");
        if (current) delete current.dataset.loading;
      }
    };

    const submitUrl = () => {
      const url = new URL(form.action, window.location.origin);
      const data = new FormData(form);
      data.delete("page");
      for (const [key, value] of data.entries()) {
        if (String(value).trim() !== "") url.searchParams.set(key, String(value));
      }
      return `${url.pathname}${url.search}`;
    };

    form.addEventListener("submit", (event) => {
      event.preventDefault();
      clearTimeout(timer);
      run(submitUrl());
    });

    form.addEventListener("input", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLInputElement)) return;
      if (!["search", "number"].includes(target.type)) return;
      clearTimeout(timer);
      timer = setTimeout(() => run(submitUrl(), { push: false }), 350);
    });

    form.addEventListener("change", (event) => {
      if (!(event.target instanceof HTMLSelectElement)) return;
      clearTimeout(timer);
      run(submitUrl(), { push: false });
    });

    root.addEventListener("click", (event) => {
      const link = event.target.closest(".sourcing-pagination a");
      if (!link || !link.href) return;
      const url = new URL(link.href, window.location.origin);
      if (url.origin !== window.location.origin) return;
      event.preventDefault();
      run(`${url.pathname}${url.search}`);
    });
  };

  roots().forEach(install);
  window.addEventListener("popstate", () => window.location.reload());
})();
