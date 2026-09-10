(() => {
  const shell = document.getElementById('inventoryAppShell');
  const sidebar = document.getElementById('inventorySidebar');
  if (!shell || !sidebar) return;

  const body = document.body;
  const collapseButton = document.querySelector('[data-inventory-sidebar-collapse]');
  const railToggle = document.querySelector('[data-inventory-sidebar-rail-toggle]');
  const resizeHandle = document.querySelector('[data-inventory-sidebar-resize]');
  const mobileQuery = window.matchMedia('(max-width: 920px)');
  const minWidth = 210;
  const maxWidth = 360;
  const defaultWidth = 236;

  const readStorage = (key, fallback = null) => {
    try { return window.localStorage.getItem(key) ?? fallback; } catch (_) { return fallback; }
  };
  const writeStorage = (key, value) => {
    try { window.localStorage.setItem(key, value); } catch (_) {}
  };
  const clamp = (value) => Math.min(maxWidth, Math.max(minWidth, Number(value) || defaultWidth));

  let sidebarWidth = clamp(readStorage('inventory-ui-sidebar-width', defaultWidth));
  let collapsed = readStorage('inventory-ui-sidebar', 'expanded') === 'collapsed';

  const applyWidth = (value, persist = false) => {
    sidebarWidth = clamp(value);
    shell.style.setProperty('--inventory-sidebar-runtime', `${Math.round(sidebarWidth)}px`);
    resizeHandle?.setAttribute('aria-valuenow', String(Math.round(sidebarWidth)));
    if (persist) writeStorage('inventory-ui-sidebar-width', String(Math.round(sidebarWidth)));
  };

  const syncCollapsed = (persist = false) => {
    shell.dataset.sidebarCollapsed = String(!mobileQuery.matches && collapsed);
    const isCollapsed = shell.dataset.sidebarCollapsed === 'true';
    collapseButton?.setAttribute('aria-label', isCollapsed ? 'Expand navigation' : 'Collapse navigation');
    collapseButton?.setAttribute('title', isCollapsed ? 'Expand navigation' : 'Collapse navigation');
    railToggle?.setAttribute('aria-label', isCollapsed ? 'Expand navigation' : 'Collapse navigation');
    railToggle?.setAttribute('title', isCollapsed ? 'Expand navigation' : 'Collapse navigation');
    if (persist) writeStorage('inventory-ui-sidebar', collapsed ? 'collapsed' : 'expanded');
  };

  const toggleCollapsed = () => {
    if (mobileQuery.matches) return;
    collapsed = !collapsed;
    syncCollapsed(true);
  };

  applyWidth(sidebarWidth, false);
  syncCollapsed(false);
  collapseButton?.addEventListener('click', toggleCollapsed);
  railToggle?.addEventListener('click', toggleCollapsed);

  mobileQuery.addEventListener?.('change', () => syncCollapsed(false));

  if (resizeHandle) {
    resizeHandle.addEventListener('pointerdown', (event) => {
      if (mobileQuery.matches || shell.dataset.sidebarCollapsed === 'true') return;
      event.preventDefault();
      const startX = event.clientX;
      const startWidth = sidebar.getBoundingClientRect().width;
      resizeHandle.setPointerCapture?.(event.pointerId);
      body.classList.add('is-inventory-sidebar-resizing');

      const move = (moveEvent) => applyWidth(startWidth + moveEvent.clientX - startX, false);
      const finish = (upEvent) => {
        move(upEvent);
        resizeHandle.releasePointerCapture?.(event.pointerId);
        resizeHandle.removeEventListener('pointermove', move);
        resizeHandle.removeEventListener('pointerup', finish);
        resizeHandle.removeEventListener('pointercancel', finish);
        body.classList.remove('is-inventory-sidebar-resizing');
        applyWidth(sidebar.getBoundingClientRect().width, true);
      };

      resizeHandle.addEventListener('pointermove', move);
      resizeHandle.addEventListener('pointerup', finish);
      resizeHandle.addEventListener('pointercancel', finish);
    });

    resizeHandle.addEventListener('dblclick', () => applyWidth(defaultWidth, true));
    resizeHandle.addEventListener('keydown', (event) => {
      if (!['ArrowLeft', 'ArrowRight', 'Home'].includes(event.key)) return;
      event.preventDefault();
      const next = event.key === 'Home' ? defaultWidth : sidebarWidth + (event.key === 'ArrowRight' ? 10 : -10);
      applyWidth(next, true);
    });
  }
})();
