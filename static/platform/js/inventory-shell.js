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

  // Administration and Sourcing reuse the sidebar shell but own their page
  // navigation and register behavior. Keep this controller Inventory-only.
  const isInventoryWorkspace = !body.classList.contains('access-shell-v1')
    && !body.classList.contains('sourcing-shell-v1');
  if (!isInventoryWorkspace) return;

  const topbar = document.querySelector('[data-inventory-topbar]');
  const content = document.querySelector('.main > .content');
  if (!topbar || !content) return;

  const desktopStickyQuery = window.matchMedia('(min-width: 681px)');
  const tableStates = new Map();
  let filterCarriers = [];
  let topbarHidden = false;
  let lastScrollY = Math.max(0, window.scrollY || 0);
  let positionFrame = 0;
  let rebuildFrame = 0;

  const topbarHeight = () => Math.round(topbar.getBoundingClientRect().height || 56);
  const stickyTop = () => topbarHidden ? 0 : topbarHeight();

  const setTopbarHidden = (hidden) => {
    if (topbarHidden === hidden) return;
    topbarHidden = hidden;
    body.classList.toggle('inventory-topbar-hidden', hidden);
    topbar.dataset.scrollState = hidden ? 'hidden' : 'visible';
    schedulePosition();
  };

  const filterFormCandidate = (form) => {
    const method = (form.getAttribute('method') || 'get').toLowerCase();
    if (method !== 'get') return false;
    return form.matches('[data-filter-form], [data-live-filter-form], .archive-search, .history-filter')
      || Boolean(form.querySelector('.search-field, input[type="search"]'));
  };

  const discoverFilterCarriers = () => {
    content.querySelectorAll('[data-inventory-sticky-filter]').forEach((element) => {
      element.removeAttribute('data-inventory-sticky-filter');
      element.removeAttribute('data-inventory-stuck');
    });

    const carriers = [];
    [...content.querySelectorAll('form')].filter(filterFormCandidate).forEach((form) => {
      const card = form.closest('.card');
      const sameCardTable = card && [...card.querySelectorAll('.table-wrap > table')].some((table) => (
        Boolean(form.compareDocumentPosition(table) & Node.DOCUMENT_POSITION_FOLLOWING)
      ));
      const carrier = form.closest('.trash-toolbar')
        || (sameCardTable ? form : card)
        || form;
      if (!carriers.includes(carrier)) carriers.push(carrier);
    });
    carriers.forEach((carrier) => carrier.setAttribute('data-inventory-sticky-filter', ''));
    return carriers;
  };

  const nearestFilterCarrier = (table) => {
    let nearest = null;
    filterCarriers.forEach((carrier) => {
      if (carrier.compareDocumentPosition(table) & Node.DOCUMENT_POSITION_FOLLOWING) {
        nearest = carrier;
      }
    });
    return nearest;
  };

  const removeOverlay = (state) => {
    state.overlay?.remove();
    state.overlay = null;
    state.cloneTable = null;
  };

  const createOverlay = (state) => {
    if (state.overlay) return;
    const overlay = document.createElement('div');
    overlay.className = 'inventory-sticky-table-head';
    overlay.setAttribute('aria-hidden', 'true');
    overlay.hidden = true;
    const cloneTable = document.createElement('table');
    cloneTable.className = 'inventory-sticky-table-head__table';
    overlay.appendChild(cloneTable);
    document.body.appendChild(overlay);
    state.overlay = overlay;
    state.cloneTable = cloneTable;
  };

  const syncCloneColumns = (state) => {
    if (!state.overlay || !state.cloneTable || !state.head?.isConnected) return;
    const clonedHead = state.head.cloneNode(true);
    clonedHead.querySelectorAll('*').forEach((element) => {
      element.removeAttribute('id');
      element.removeAttribute('name');
      element.removeAttribute('for');
      element.removeAttribute('form');
      element.removeAttribute('data-description-resize-handle');
      element.removeAttribute('data-trash-select-all');
      if (element.matches('a, button, input, select, textarea, [tabindex]')) {
        element.setAttribute('tabindex', '-1');
      }
    });
    state.cloneTable.replaceChildren(clonedHead);

    const tableRect = state.table.getBoundingClientRect();
    const tableWidth = Math.max(tableRect.width, state.table.scrollWidth);
    state.cloneTable.style.width = `${Math.ceil(tableWidth)}px`;
    state.cloneTable.style.minWidth = `${Math.ceil(tableWidth)}px`;

    const sourceCells = [...state.head.querySelectorAll('th, td')];
    const clonedCells = [...clonedHead.querySelectorAll('th, td')];
    sourceCells.forEach((cell, index) => {
      const clone = clonedCells[index];
      if (!clone) return;
      const width = cell.getBoundingClientRect().width;
      clone.style.width = `${width}px`;
      clone.style.minWidth = `${width}px`;
      clone.style.maxWidth = `${width}px`;
    });
  };

  const destroyTableState = (state) => {
    state.wrapper.removeEventListener('scroll', state.onHorizontalScroll);
    state.wrapper.removeAttribute('data-inventory-native-sticky');
    state.wrapper.style.removeProperty('--inventory-table-sticky-top');
    removeOverlay(state);
  };

  const configureTableState = (state) => {
    const availableWidth = state.wrapper.clientWidth;
    const renderedWidth = Math.max(
      state.table.scrollWidth,
      state.table.getBoundingClientRect().width,
    );
    const useNativeSticky = renderedWidth <= availableWidth + 1;
    state.native = useNativeSticky;
    if (useNativeSticky) {
      state.wrapper.setAttribute('data-inventory-native-sticky', 'true');
      removeOverlay(state);
    } else {
      state.wrapper.removeAttribute('data-inventory-native-sticky');
      createOverlay(state);
      syncCloneColumns(state);
    }
  };

  const tableStickyTop = (state, shellTop) => {
    if (!desktopStickyQuery.matches || !state.filter?.isConnected) return shellTop;
    return shellTop + Math.ceil(state.filter.getBoundingClientRect().height);
  };

  const syncTablePosition = (state, shellTop) => {
    if (!state.table.isConnected || !state.head?.isConnected) return;
    const tableTop = tableStickyTop(state, shellTop);
    state.wrapper.style.setProperty('--inventory-table-sticky-top', `${tableTop}px`);
    if (state.native || !state.overlay || !state.cloneTable) return;

    const headRect = state.head.getBoundingClientRect();
    const tableRect = state.table.getBoundingClientRect();
    const wrapperRect = state.wrapper.getBoundingClientRect();
    const headHeight = Math.ceil(headRect.height);
    const visibleLeft = Math.max(0, wrapperRect.left);
    const visibleRight = Math.min(window.innerWidth, wrapperRect.right);
    const visibleWidth = Math.max(0, visibleRight - visibleLeft);
    const shouldShow = visibleWidth > 0
      && headHeight > 0
      && headRect.top <= tableTop
      && tableRect.bottom > tableTop + headHeight
      && wrapperRect.bottom > tableTop + headHeight;

    state.overlay.hidden = !shouldShow;
    if (!shouldShow) return;
    state.overlay.style.top = `${tableTop}px`;
    state.overlay.style.left = `${visibleLeft}px`;
    state.overlay.style.width = `${visibleWidth}px`;
    state.overlay.style.height = `${headHeight}px`;
    state.cloneTable.style.transform = `translateX(${Math.round(tableRect.left - visibleLeft)}px)`;
  };

  const syncPositions = () => {
    positionFrame = 0;
    const shellTop = stickyTop();
    body.style.setProperty('--inventory-shell-topbar-height', `${topbarHeight()}px`);
    body.style.setProperty('--inventory-sticky-top', `${shellTop}px`);

    filterCarriers.forEach((carrier) => {
      const rect = carrier.getBoundingClientRect();
      const stuck = desktopStickyQuery.matches
        && window.scrollY > 4
        && rect.top <= shellTop + 1
        && rect.bottom > shellTop;
      carrier.dataset.inventoryStuck = String(stuck);
    });
    tableStates.forEach((state) => syncTablePosition(state, shellTop));
  };

  function schedulePosition() {
    if (positionFrame) return;
    positionFrame = window.requestAnimationFrame(syncPositions);
  }

  const resizeObserver = typeof ResizeObserver === 'function'
    ? new ResizeObserver(() => scheduleRebuild())
    : null;

  const rebuildStickySurfaces = () => {
    rebuildFrame = 0;
    filterCarriers = discoverFilterCarriers();
    const tables = [...content.querySelectorAll('.table-wrap > table')].filter((table) => table.tHead);
    const liveTables = new Set(tables);

    tableStates.forEach((state, table) => {
      if (liveTables.has(table)) return;
      destroyTableState(state);
      tableStates.delete(table);
    });

    tables.forEach((table) => {
      const wrapper = table.parentElement;
      let state = tableStates.get(table);
      if (!state) {
        state = {
          table,
          wrapper,
          head: table.tHead,
          filter: null,
          native: false,
          overlay: null,
          cloneTable: null,
          onHorizontalScroll: schedulePosition,
        };
        wrapper.addEventListener('scroll', state.onHorizontalScroll, {passive: true});
        tableStates.set(table, state);
      } else {
        state.head = table.tHead;
      }
      state.filter = nearestFilterCarrier(table);
      configureTableState(state);
    });

    resizeObserver?.disconnect();
    resizeObserver?.observe(topbar);
    filterCarriers.forEach((carrier) => resizeObserver?.observe(carrier));
    tableStates.forEach((state) => {
      resizeObserver?.observe(state.wrapper);
      resizeObserver?.observe(state.table);
    });
    syncPositions();
  };

  function scheduleRebuild() {
    if (rebuildFrame) return;
    rebuildFrame = window.requestAnimationFrame(rebuildStickySurfaces);
  }

  const onWindowScroll = () => {
    const currentScrollY = Math.max(0, window.scrollY || 0);
    const delta = currentScrollY - lastScrollY;
    if (currentScrollY <= 8) {
      setTopbarHidden(false);
    } else if (delta > 1 && currentScrollY > topbarHeight() + 18) {
      setTopbarHidden(true);
    } else if (delta < -1) {
      setTopbarHidden(false);
    }
    lastScrollY = currentScrollY;
    schedulePosition();
  };

  window.addEventListener('scroll', onWindowScroll, {passive: true});
  window.addEventListener('resize', scheduleRebuild, {passive: true});
  desktopStickyQuery.addEventListener?.('change', scheduleRebuild);
  topbar.addEventListener('focusin', () => setTopbarHidden(false));

  const contentObserver = new MutationObserver(() => scheduleRebuild());
  contentObserver.observe(content, {childList: true, subtree: true});
  document.fonts?.ready.then(scheduleRebuild).catch(() => {});
  if (lastScrollY > topbarHeight() + 18) setTopbarHidden(true);
  rebuildStickySurfaces();
})();
