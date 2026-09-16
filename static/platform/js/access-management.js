(() => {
  "use strict";

  const byId = (id) => document.getElementById(id);
  const accessScript = byId("administration-access-context");
  if (!accessScript) return;

  let accessContext = {};
  try { accessContext = JSON.parse(accessScript.textContent || "{}"); } catch (_) { accessContext = {}; }
  const permissionSet = new Set(accessContext?.effective_access?.permissions || []);
  const canManageUsers = permissionSet.has("access.users.manage");
  const canViewProfiles = permissionSet.has("access.profiles.view") || canManageUsers;
  const canManageProfiles = permissionSet.has("access.profiles.manage");
  const canViewAudit = permissionSet.has("access.audit.view");
  const actorMembershipId = String(accessContext.membership_id || "");
  const actorProfileKey = String(accessContext?.effective_access?.profile?.key || "");
  const actorProfileId = String(accessContext?.effective_access?.profile?.id || "");
  const actorIsOwner = actorProfileKey === "role-owner";
  const csrfToken = byId("administration-csrf-token")?.dataset?.token || "";

  const els = {
    search: byId("accessUserSearch"),
    searchState: byId("accessSearchState"),
    status: byId("accessUserStatus"),
    pageSize: byId("accessUserPageSize"),
    tbody: byId("accessUserRows"),
    tableWrap: byId("accessUserTableWrap"),
    meta: byId("accessRegisterMeta"),
    pageLabel: byId("accessPageLabel"),
    prev: byId("accessPrevPage"),
    next: byId("accessNextPage"),
    drawer: byId("accessDrawer"),
    scrim: byId("accessDrawerScrim"),
    drawerClose: byId("accessDrawerClose"),
    drawerEyebrow: byId("accessDrawerEyebrow"),
    drawerTitle: byId("accessDrawerTitle"),
    drawerSubtitle: byId("accessDrawerSubtitle"),
    drawerBody: byId("accessDrawerBody"),
    drawerFooter: byId("accessDrawerFooter"),
    toastStack: byId("toastStack"),
    profileRows: byId("accessProfileRows"),
    profileWrap: byId("accessProfileTableWrap"),
    profileMeta: byId("accessProfileMeta"),
    historySearch: byId("accessHistorySearch"),
    historySearchState: byId("accessHistorySearchState"),
    historyTarget: byId("accessHistoryTarget"),
    historyPageSize: byId("accessHistoryPageSize"),
    historyRows: byId("accessHistoryRows"),
    historyWrap: byId("accessHistoryTableWrap"),
    historyMeta: byId("accessHistoryMeta"),
    historyPageLabel: byId("accessHistoryPageLabel"),
    historyPrev: byId("accessHistoryPrevPage"),
    historyNext: byId("accessHistoryNextPage"),
  };

  const state = {
    page: 1,
    pageSize: 25,
    status: "all",
    query: "",
    users: [],
    hasNext: false,
    hasPrevious: false,
    profiles: [],
    permissionCatalog: [],
    profilesLoaded: false,
    usersAbort: null,
    usersRequest: 0,
    searchTimer: null,
    drawerUser: null,
    drawerMode: null,
    drawerLastFocus: null,
    scopeMaps: {
      projects: new Map(),
      branches: new Map(),
      inventoryLocations: new Map(),
    },
    scopeAbort: {},
    scopeTimer: {},
    historyPage: 1,
    historyPageSize: 25,
    historyTarget: "all",
    historyQuery: "",
    historyRows: [],
    historyHasNext: false,
    historyHasPrevious: false,
    historyAbort: null,
    historyRequest: 0,
    historySearchTimer: null,
  };

  const htmlEscape = (value) => String(value ?? "")
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;").replaceAll("'", "&#039;");

  function toast(message, tone = "success") {
    if (!els.toastStack) return;
    const node = document.createElement("div");
    node.className = `toast ${tone === "error" ? "toast-error" : "toast-success"}`;
    node.textContent = message;
    els.toastStack.appendChild(node);
    window.setTimeout(() => node.remove(), 3600);
  }

  class ApiError extends Error {
    constructor(message, payload, status) {
      super(message);
      this.payload = payload || {};
      this.status = status;
    }
  }

  async function api(url, options = {}) {
    const headers = new Headers(options.headers || {});
    headers.set("Accept", "application/json");
    if (options.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
    if (options.method && options.method !== "GET" && csrfToken) headers.set("X-CSRFToken", csrfToken);
    const response = await fetch(url, { credentials: "same-origin", ...options, headers });
    let payload = {};
    try { payload = await response.json(); } catch (_) { payload = {}; }
    if (!response.ok || payload.ok === false) {
      const errors = payload.errors || {};
      const first = Object.values(errors).flat().find(Boolean);
      throw new ApiError(String(first || `Request failed (${response.status})`), payload, response.status);
    }
    return payload;
  }

  function initials(user) {
    const parts = [user.firstName, user.lastName].filter(Boolean);
    if (parts.length) return parts.map((part) => part[0]).join("").slice(0, 2).toUpperCase();
    return String(user.username || "U").slice(0, 2).toUpperCase();
  }

  function formatDate(value, empty = "Never") {
    if (!value) return empty;
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return empty;
    return new Intl.DateTimeFormat(undefined, { year: "numeric", month: "short", day: "numeric" }).format(date);
  }

  function formatDateTime(value, empty = "—") {
    if (!value) return empty;
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return empty;
    return new Intl.DateTimeFormat(undefined, { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(date);
  }

  function auditActionLabel(value) {
    return String(value || "Access change")
      .replace(/^access\./, "")
      .replaceAll(".", " · ")
      .replaceAll("_", " ")
      .replace(/\b\w/g, (letter) => letter.toUpperCase());
  }

  function auditChangeSummary(event) {
    const changes = Array.isArray(event?.changes) ? event.changes : [];
    if (!changes.length) return "Recorded security event";
    const first = changes[0];
    const extra = changes.length > 1 ? ` +${changes.length - 1}` : "";
    return `${first.field}: ${first.before} → ${first.after}${extra}`;
  }

  function scopeLabel(scope, short) {
    if (!scope) return "—";
    if (scope.mode === "all") return short ? "All" : "All records";
    if (scope.mode === "none") return "None";
    const count = Number(scope.count ?? scope.rows?.length ?? 0);
    return `${count} selected`;
  }

  function renderUsers() {
    if (!els.tbody) return;
    els.tbody.replaceChildren();
    if (!state.users.length) {
      const tr = document.createElement("tr");
      const td = document.createElement("td"); td.colSpan = 6;
      const empty = document.createElement("div"); empty.className = "access-empty";
      empty.textContent = state.query ? "No users match this search." : "No company users are available.";
      td.appendChild(empty); tr.appendChild(td); els.tbody.appendChild(tr);
    } else {
      for (const user of state.users) {
        const tr = document.createElement("tr");
        tr.dataset.membershipId = user.membershipId;

        const userTd = document.createElement("td");
        const userCell = document.createElement("div"); userCell.className = "access-user-cell";
        const avatar = document.createElement("span"); avatar.className = "access-avatar"; avatar.textContent = initials(user);
        const copy = document.createElement("span"); copy.className = "access-user-copy";
        const name = document.createElement("strong"); name.textContent = user.displayName || user.username;
        const meta = document.createElement("small"); meta.textContent = `${user.username}${user.email ? ` · ${user.email}` : ""}`;
        copy.append(name, meta); userCell.append(avatar, copy); userTd.appendChild(userCell);

        const profileTd = document.createElement("td");
        const profileCopy = document.createElement("div"); profileCopy.className = "access-profile-copy";
        const profileName = document.createElement("strong"); profileName.textContent = user.profile?.name || "No access profile";
        const profileMeta = document.createElement("small");
        profileMeta.textContent = user.profile?.owner ? "Protected owner profile" : (user.profile?.system ? "Built-in Access Profile" : "Custom Access Profile");
        profileCopy.append(profileName, profileMeta); profileTd.appendChild(profileCopy);

        const scopeTd = document.createElement("td");
        const scopes = document.createElement("div"); scopes.className = "access-scope-summary";
        for (const [label, scope] of [["Projects", user.scopes?.projects], ["Branches", user.scopes?.branches], ["Locations", user.scopes?.inventoryLocations]]) {
          const pill = document.createElement("span"); pill.className = "access-scope-pill";
          const strong = document.createElement("strong"); strong.textContent = label;
          pill.append(strong, document.createTextNode(` ${scopeLabel(scope, true)}`)); scopes.appendChild(pill);
        }
        scopeTd.appendChild(scopes);

        const statusTd = document.createElement("td");
        const status = document.createElement("span"); status.className = `access-status ${user.active ? "is-active" : "is-inactive"}`; status.textContent = user.active ? "Active" : "Inactive";
        statusTd.appendChild(status);

        const loginTd = document.createElement("td");
        const login = document.createElement("div"); login.className = "access-date";
        const loginMain = document.createElement("span"); loginMain.textContent = formatDate(user.lastLogin);
        const loginMeta = document.createElement("small"); loginMeta.textContent = user.mustChangePassword ? "Password change required" : (user.lastLogin ? "Authenticated" : "Not signed in yet");
        login.append(loginMain, loginMeta); loginTd.appendChild(login);

        const actionTd = document.createElement("td"); actionTd.className = "access-actions-col";
        const action = document.createElement("button"); action.className = "access-row-action"; action.type = "button"; action.setAttribute("aria-label", `Open ${user.displayName || user.username}`); action.title = canManageUsers ? "Open user" : "View user";
        action.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 18l6-6-6-6"/></svg>';
        action.addEventListener("click", () => openUser(user.membershipId)); actionTd.appendChild(action);

        tr.append(userTd, profileTd, scopeTd, statusTd, loginTd, actionTd);
        tr.addEventListener("dblclick", () => openUser(user.membershipId));
        els.tbody.appendChild(tr);
      }
    }
    els.pageLabel.textContent = `Page ${state.page} · up to ${state.pageSize} users`;
    els.prev.disabled = !state.hasPrevious;
    els.next.disabled = !state.hasNext;
    els.meta.textContent = `${state.users.length} shown · server page ${state.page}`;
  }

  function renderUserError(message) {
    if (!els.tbody) return;
    els.tbody.innerHTML = `<tr><td colspan="6"><div class="access-error">${htmlEscape(message)}</div></td></tr>`;
    els.meta.textContent = "Unable to load";
  }

  async function loadUsers({ resetPage = false } = {}) {
    if (resetPage) state.page = 1;
    if (state.query && state.query.length < 2) {
      els.searchState.textContent = "Type 2+ characters";
      return;
    }
    els.searchState.textContent = state.query ? "Searching…" : "";
    els.tableWrap.setAttribute("aria-busy", "true");
    els.meta.textContent = state.users.length ? "Refreshing…" : "Loading…";
    if (state.usersAbort) state.usersAbort.abort();
    const controller = new AbortController(); state.usersAbort = controller;
    const requestId = ++state.usersRequest;
    const params = new URLSearchParams({ page: String(state.page), page_size: String(state.pageSize), status: state.status });
    if (state.query) params.set("q", state.query);
    try {
      const payload = await api(`/api/access/users/?${params.toString()}`, { signal: controller.signal });
      if (requestId !== state.usersRequest) return;
      const page = payload.users || {};
      state.users = page.rows || [];
      state.page = Number(page.page || state.page);
      state.pageSize = Number(page.pageSize || state.pageSize);
      state.hasNext = Boolean(page.hasNext);
      state.hasPrevious = Boolean(page.hasPrevious);
      renderUsers();
      els.searchState.textContent = "";
    } catch (error) {
      if (error?.name === "AbortError") return;
      renderUserError(error.message || "Could not load company users.");
      els.searchState.textContent = "";
    } finally {
      if (requestId === state.usersRequest) els.tableWrap.setAttribute("aria-busy", "false");
    }
  }

  function renderAccessHistory() {
    if (!els.historyRows) return;
    els.historyRows.replaceChildren();
    if (!state.historyRows.length) {
      els.historyRows.innerHTML = '<tr><td colspan="5"><div class="access-empty">No Access History matches this filter.</div></td></tr>';
    } else {
      for (const event of state.historyRows) {
        const tr = document.createElement("tr");
        const when = document.createElement("td"); when.innerHTML = `<div class="access-date"><span>${htmlEscape(formatDateTime(event.date))}</span><small>${htmlEscape(event.requestId || "No request ID")}</small></div>`;
        const actor = document.createElement("td"); actor.innerHTML = `<div class="access-profile-copy"><strong>${htmlEscape(event.actor || "System")}</strong><small>${htmlEscape(event.actorRole || event.actorUsername || "System")}</small></div>`;
        const action = document.createElement("td"); action.innerHTML = `<span class="access-history-action">${htmlEscape(auditActionLabel(event.action))}</span>`;
        const target = document.createElement("td"); target.innerHTML = `<div class="access-profile-copy"><strong>${htmlEscape(event.target || event.targetId || "—")}</strong><small>${htmlEscape(event.targetType || "")}</small></div>`;
        const change = document.createElement("td"); change.innerHTML = `<span class="access-history-change">${htmlEscape(auditChangeSummary(event))}</span>`;
        tr.append(when, actor, action, target, change);
        els.historyRows.appendChild(tr);
      }
    }
    if (els.historyPageLabel) els.historyPageLabel.textContent = `Page ${state.historyPage} · up to ${state.historyPageSize} events`;
    if (els.historyPrev) els.historyPrev.disabled = !state.historyHasPrevious;
    if (els.historyNext) els.historyNext.disabled = !state.historyHasNext;
    if (els.historyMeta) els.historyMeta.textContent = `${state.historyRows.length} shown · immutable ledger`;
  }

  async function loadAccessHistory({ resetPage = false } = {}) {
    if (!canViewAudit || !els.historyRows) return;
    if (resetPage) state.historyPage = 1;
    if (state.historyQuery && state.historyQuery.length < 2) {
      if (els.historySearchState) els.historySearchState.textContent = "Type 2+ characters";
      return;
    }
    if (els.historyWrap) els.historyWrap.setAttribute("aria-busy", "true");
    if (els.historyMeta) els.historyMeta.textContent = state.historyRows.length ? "Refreshing…" : "Loading…";
    if (els.historySearchState) els.historySearchState.textContent = state.historyQuery ? "Searching…" : "";
    if (state.historyAbort) state.historyAbort.abort();
    const controller = new AbortController(); state.historyAbort = controller;
    const requestId = ++state.historyRequest;
    const params = new URLSearchParams({ page: String(state.historyPage), page_size: String(state.historyPageSize), target: state.historyTarget });
    if (state.historyQuery) params.set("q", state.historyQuery);
    try {
      const payload = await api(`/api/access/audit/?${params.toString()}`, { signal: controller.signal });
      if (requestId !== state.historyRequest) return;
      const page = payload.audit || {};
      state.historyRows = page.rows || [];
      state.historyPage = Number(page.page || state.historyPage);
      state.historyPageSize = Number(page.pageSize || state.historyPageSize);
      state.historyHasNext = Boolean(page.hasNext);
      state.historyHasPrevious = Boolean(page.hasPrevious);
      renderAccessHistory();
      if (els.historySearchState) els.historySearchState.textContent = "";
    } catch (error) {
      if (error?.name === "AbortError") return;
      if (els.historyRows) els.historyRows.innerHTML = `<tr><td colspan="5"><div class="access-error">${htmlEscape(error.message || "Could not load Access History.")}</div></td></tr>`;
      if (els.historyMeta) els.historyMeta.textContent = "Unable to load";
      if (els.historySearchState) els.historySearchState.textContent = "";
    } finally {
      if (requestId === state.historyRequest && els.historyWrap) els.historyWrap.setAttribute("aria-busy", "false");
    }
  }

  async function loadProfiles({ force = false } = {}) {
    if (!canViewProfiles && !canManageProfiles) return [];
    if (state.profilesLoaded && !force) return state.profiles;
    if (els.profileWrap) els.profileWrap.setAttribute("aria-busy", "true");
    try {
      const payload = await api("/api/access/profiles/");
      state.profiles = payload.profiles || [];
      state.permissionCatalog = payload.permissionCatalog || [];
      state.profilesLoaded = true;
      renderProfiles();
      return state.profiles;
    } finally {
      if (els.profileWrap) els.profileWrap.setAttribute("aria-busy", "false");
    }
  }

  function openDrawer({ eyebrow, title, subtitle }) {
    if (els.drawer.hidden) state.drawerLastFocus = document.activeElement;
    els.drawerEyebrow.textContent = eyebrow;
    els.drawerTitle.textContent = title;
    els.drawerSubtitle.textContent = subtitle;
    els.scrim.hidden = false;
    els.drawer.hidden = false;
    els.drawer.setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";
    window.setTimeout(() => els.drawerClose?.focus(), 0);
  }

  function closeDrawer() {
    for (const controller of Object.values(state.scopeAbort)) controller?.abort?.();
    for (const timer of Object.values(state.scopeTimer)) window.clearTimeout(timer);
    state.scopeAbort = {}; state.scopeTimer = {};
    els.scrim.hidden = true;
    els.drawer.hidden = true;
    els.drawer.setAttribute("aria-hidden", "true");
    els.drawerBody.replaceChildren(); els.drawerFooter.replaceChildren();
    document.body.style.overflow = "";
    const focus = state.drawerLastFocus;
    state.drawerLastFocus = null; state.drawerUser = null; state.drawerMode = null;
    if (focus && document.contains(focus)) focus.focus();
  }

  function formField({ id, label, value = "", type = "text", required = false, disabled = false, wide = false, autocomplete = "off" }) {
    return `<label class="access-field${wide ? " is-wide" : ""}"><span>${htmlEscape(label)}${required ? ' <em class="required">*</em>' : ""}</span><input class="access-input" id="${id}" name="${id}" type="${type}" value="${htmlEscape(value)}" ${required ? "required" : ""} ${disabled ? "disabled" : ""} autocomplete="${autocomplete}"><small class="access-field-error" id="fieldError-${id}"></small></label>`;
  }

  function permissionGroups(profile) {
    const values = profile?.permissions || [];
    const groups = [];
    if (values.some((v) => v.startsWith("access.") || v.startsWith("settings."))) groups.push("Administration");
    if (values.some((v) => v.startsWith("inventory."))) groups.push("Inventory");
    if (values.some((v) => v.startsWith("internal."))) groups.push("Internal Payroll");
    if (values.some((v) => v.startsWith("rental."))) groups.push("Rental Manpower");
    if (values.some((v) => v.startsWith("sourcing."))) groups.push("Sourcing Directory");
    if (values.some((v) => v.startsWith("shared."))) groups.push("Shared records");
    return groups;
  }

  function renderProfileSummary(profile) {
    const card = byId("accessProfileSummary");
    if (!card) return;
    if (!profile) {
      card.innerHTML = '<div class="access-profile-card__head"><div><strong>No profile selected</strong><span>Choose an Access Profile to define page and action permissions.</span></div></div>';
      return;
    }
    const groups = permissionGroups(profile);
    card.innerHTML = `<div class="access-profile-card__head"><div><strong>${htmlEscape(profile.name)}</strong><span>${htmlEscape(profile.description || "Persisted company Access Profile.")}</span></div><span class="access-profile-tag">${profile.permissions.length} permissions</span></div><div class="access-profile-tags">${groups.map((g) => `<span class="access-profile-tag">${htmlEscape(g)}</span>`).join("") || '<span class="access-profile-tag">No operational pages</span>'}</div>`;
  }

  function profileCoverage(profile) {
    const groups = permissionGroups(profile);
    return groups.length ? groups.join(" · ") : "No operational pages";
  }

  function renderProfiles() {
    if (!els.profileRows) return;
    els.profileRows.replaceChildren();
    if (!state.profiles.length) {
      els.profileRows.innerHTML = '<tr><td colspan="6"><div class="access-empty">No Access Profiles are available.</div></td></tr>';
      if (els.profileMeta) els.profileMeta.textContent = "0 profiles";
      return;
    }
    for (const profile of state.profiles) {
      const tr = document.createElement("tr");
      const nameTd = document.createElement("td");
      nameTd.innerHTML = `<div class="access-profile-copy"><strong>${htmlEscape(profile.name)}</strong><small>${htmlEscape(profile.description || "No description")}</small></div>`;
      const coverageTd = document.createElement("td"); coverageTd.textContent = profileCoverage(profile);
      const permissionsTd = document.createElement("td"); permissionsTd.innerHTML = `<strong>${Number(profile.permissions?.length || 0)}</strong><small class="access-table-sub"> exact permissions</small>`;
      const usersTd = document.createElement("td"); usersTd.textContent = String(Number(profile.assignedUsers || 0));
      const typeTd = document.createElement("td"); typeTd.innerHTML = `<span class="access-status ${profile.active === false ? "is-inactive" : "is-active"}">${profile.system ? "Built-in" : (profile.active === false ? "Inactive custom" : "Custom")}</span>`;
      const actionTd = document.createElement("td"); actionTd.className = "access-actions-col";
      const action = document.createElement("button"); action.className = "access-row-action"; action.type = "button"; action.title = profile.system || !canManageProfiles ? "View profile" : "Edit profile"; action.setAttribute("aria-label", `${action.title} ${profile.name}`); action.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 18l6-6-6-6"/></svg>';
      action.addEventListener("click", () => renderProfileForm(profile)); actionTd.appendChild(action);
      tr.append(nameTd, coverageTd, permissionsTd, usersTd, typeTd, actionTd); els.profileRows.appendChild(tr);
    }
    if (els.profileMeta) els.profileMeta.textContent = `${state.profiles.length} profiles · ${state.profiles.filter((p) => !p.system).length} custom`;
  }

  function profilePermissionMarkup(profile, editable) {
    const selected = new Set(profile?.permissions || []);
    const groups = new Map();
    for (const permission of state.permissionCatalog) {
      const category = permission.category || "Platform";
      if (!groups.has(category)) groups.set(category, []);
      groups.get(category).push(permission);
    }
    return [...groups.entries()].map(([category, permissions]) => `<section class="access-permission-group"><header><strong>${htmlEscape(category)}</strong><span>${permissions.filter((item) => selected.has(item.code)).length}/${permissions.length} selected</span></header><div class="access-permission-grid">${permissions.map((permission) => `<label class="access-permission-item ${permission.kind === "view" ? "is-view" : "is-action"}"><input type="checkbox" data-profile-permission="${htmlEscape(permission.code)}" data-permission-kind="${htmlEscape(permission.kind || "action")}" ${selected.has(permission.code) ? "checked" : ""} ${editable ? "" : "disabled"}><span><strong>${htmlEscape(permission.label)}</strong><small>${permission.kind === "view" ? "Page / read authority" : "Action authority"}</small></span></label>`).join("")}</div></section>`).join("");
  }

  function profileSelectedPermissions() {
    return [...els.drawerBody.querySelectorAll("[data-profile-permission]:checked")].map((input) => input.dataset.profilePermission).filter(Boolean);
  }

  function applyViewOnlyMode(enabled) {
    els.drawerBody.querySelectorAll("[data-profile-permission]").forEach((input) => {
      const isView = input.dataset.permissionKind === "view";
      if (enabled && !isView) input.checked = false;
      if (!input.dataset.profileReadonly) input.disabled = enabled && !isView;
    });
    const counter = byId("accessProfilePermissionCount");
    if (counter) counter.textContent = `${profileSelectedPermissions().length} selected`;
  }

  function renderProfileForm(profile = null) {
    const creating = !profile;
    const isOwnProfile = Boolean(profile && String(profile.id) === actorProfileId);
    const editable = Boolean(canManageProfiles && (creating || (!profile.system && !isOwnProfile)));
    const title = creating ? "Create Access Profile" : profile.name;
    openDrawer({ eyebrow: creating ? "Access profile" : (profile.system ? "Built-in profile" : "Custom profile"), title, subtitle: creating ? "Choose exact pages and actions. Scope is assigned per user." : `${Number(profile.assignedUsers || 0)} active assigned user${Number(profile.assignedUsers || 0) === 1 ? "" : "s"}.` });
    const viewOnlyDefault = Boolean(profile && profile.permissions?.length && profile.permissions.every((code) => (state.permissionCatalog.find((item) => item.code === code)?.kind || "action") === "view"));
    els.drawerBody.innerHTML = `<form class="access-form" id="accessProfileForm" novalidate>
      <section class="access-form-section"><div class="access-section-head"><div><strong>Profile identity</strong><span>Custom profiles are company-scoped. Built-in profiles are immutable.</span></div>${profile ? `<span class="access-status ${profile.active === false ? "is-inactive" : "is-active"}">${profile.system ? "Built-in" : (profile.active === false ? "Inactive" : "Custom")}</span>` : ""}</div><div class="access-form-grid">${formField({ id:"accessProfileName", label:"Profile name", value:profile?.name, required:true, disabled:!editable, wide:true })}${formField({ id:"accessProfileDescription", label:"Description", value:profile?.description, disabled:!editable, wide:true })}</div>${isOwnProfile ? '<div class="access-form-note"><strong>Self-escalation protection:</strong> you cannot modify the profile currently granting your own authority. Another authorized administrator must make that change.</div>' : ""}</section>
      <section class="access-form-section"><div class="access-section-head"><div><strong>Pages & actions</strong><span>View-only profiles should contain only page/read permissions. Direct routes and APIs enforce the same permissions.</span></div><span class="access-profile-tag" id="accessProfilePermissionCount">${Number(profile?.permissions?.length || 0)} selected</span></div>${editable ? `<label class="access-view-only-switch"><input type="checkbox" id="accessProfileViewOnly" ${viewOnlyDefault ? "checked" : ""}><span><strong>View-only mode</strong><small>Remove and disable every mutation/approval/payment permission.</small></span></label>` : ""}<div class="access-permission-groups">${profilePermissionMarkup(profile, editable)}</div><small class="access-field-error" id="fieldError-permissions"></small></section>
      ${profile && !profile.system ? `<section class="access-form-section"><div class="access-section-head"><div><strong>Profile lifecycle</strong><span>Assigned profiles cannot be deleted or deactivated until every user is reassigned.</span></div></div><div class="access-detail-summary"><div class="access-detail-item"><span>Assigned users</span><strong>${Number(profile.assignedUsers || 0)}</strong></div><div class="access-detail-item"><span>Key</span><strong>${htmlEscape(profile.key)}</strong></div></div></section>` : ""}
    </form>`;
    const readonlyInputs = els.drawerBody.querySelectorAll("[data-profile-permission]");
    if (!editable) readonlyInputs.forEach((input) => input.dataset.profileReadonly = "1");
    const viewOnly = byId("accessProfileViewOnly");
    if (viewOnly) { viewOnly.addEventListener("change", () => applyViewOnlyMode(viewOnly.checked)); if (viewOnly.checked) applyViewOnlyMode(true); }
    const sourcingDependencies = {
      "sourcing.vendors.manage": "sourcing.vendors.view",
      "sourcing.manpower.manage": "sourcing.manpower.view",
      "sourcing.masters.manage": "sourcing.masters.view",
    };
    els.drawerBody.querySelectorAll("[data-profile-permission]").forEach((input) => input.addEventListener("change", () => {
      const code = input.dataset.profilePermission || "";
      if (input.checked && sourcingDependencies[code]) {
        const required = els.drawerBody.querySelector(`[data-profile-permission="${sourcingDependencies[code]}"]`);
        if (required) required.checked = true;
      }
      for (const [actionCode, viewCode] of Object.entries(sourcingDependencies)) {
        if (code === viewCode && !input.checked) {
          const action = els.drawerBody.querySelector(`[data-profile-permission="${actionCode}"]`);
          if (action) action.checked = false;
        }
      }
      const counter=byId("accessProfilePermissionCount"); if(counter) counter.textContent=`${profileSelectedPermissions().length} selected`;
    }));

    els.drawerFooter.replaceChildren();
    const close = document.createElement("button"); close.className="btn btn-ghost"; close.type="button"; close.textContent=editable ? "Cancel" : "Close"; close.addEventListener("click", closeDrawer); els.drawerFooter.appendChild(close);
    if (editable) {
      const spacer=document.createElement("span"); spacer.className="access-footer-spacer"; els.drawerFooter.appendChild(spacer);
      if (profile && !profile.system && Number(profile.assignedUsers || 0) === 0) { const del=document.createElement("button"); del.className="btn btn-danger"; del.type="button"; del.textContent="Delete Profile"; del.addEventListener("click",()=>renderProfileDelete(profile)); els.drawerFooter.appendChild(del); }
      const save=document.createElement("button"); save.className="btn btn-primary"; save.type="button"; save.textContent=creating?"Create Profile":"Save Profile"; save.addEventListener("click",()=>saveProfileForm(profile,save)); els.drawerFooter.appendChild(save);
    }
  }

  async function saveProfileForm(profile, button) {
    clearFormErrors();
    const payload={ name:byId("accessProfileName")?.value.trim()||"", description:byId("accessProfileDescription")?.value.trim()||"", permissions:profileSelectedPermissions() };
    button.disabled=true; const previous=button.textContent; button.textContent="Saving…";
    try {
      await api(profile ? `/api/access/profiles/${profile.id}/` : "/api/access/profiles/", { method:profile?"PATCH":"POST", body:JSON.stringify(payload) });
      toast(profile ? "Access Profile updated." : "Custom Access Profile created.");
      state.profilesLoaded=false; await loadProfiles({force:true}); await loadUsers(); closeDrawer();
    } catch(error) { showFormErrors(error); }
    finally { button.disabled=false; button.textContent=previous; }
  }

  function renderProfileDelete(profile) {
    els.drawerEyebrow.textContent="Access profile"; els.drawerTitle.textContent="Delete unused profile"; els.drawerSubtitle.textContent=profile.name;
    els.drawerBody.innerHTML=`<div class="access-confirm"><div class="access-form-alert"><strong>Only an unused custom profile can be deleted.</strong> Built-in profiles and profiles assigned to any membership are protected.</div><label class="access-field"><span>Type profile name <strong>${htmlEscape(profile.name)}</strong> to confirm</span><input class="access-input" id="accessProfileDeleteConfirmation" autocomplete="off"><small class="access-field-error" id="fieldError-confirmation"></small></label></div>`;
    els.drawerFooter.replaceChildren(); const back=document.createElement("button"); back.className="btn btn-ghost"; back.type="button"; back.textContent="Back"; back.addEventListener("click",()=>renderProfileForm(profile)); const spacer=document.createElement("span"); spacer.className="access-footer-spacer"; const del=document.createElement("button"); del.className="btn btn-danger"; del.type="button"; del.textContent="Delete Profile"; del.addEventListener("click",async()=>{ del.disabled=true; try { await api(`/api/access/profiles/${profile.id}/`,{method:"DELETE",body:JSON.stringify({confirmation:byId("accessProfileDeleteConfirmation")?.value||""})}); toast("Unused Access Profile deleted."); state.profilesLoaded=false; closeDrawer(); await loadProfiles({force:true}); } catch(error){ showFormErrors(error); del.disabled=false; } }); els.drawerFooter.append(back,spacer,del);
  }

  const scopeConfig = {
    projects: { api: "projects", modeField: "projectMode", idsField: "projectIds", title: "Projects", help: "Rental Manpower and project-scoped Inventory authority." },
    branches: { api: "branches", modeField: "branchMode", idsField: "branchIds", title: "Branches / Offices", help: "Internal Company records and branch-scoped operations." },
    inventoryLocations: { api: "inventory_locations", modeField: "inventoryLocationMode", idsField: "inventoryLocationIds", title: "Inventory Locations", help: "Stores, offices and controlled stock locations." },
  };

  function initializeScopeMaps(user) {
    for (const key of Object.keys(scopeConfig)) state.scopeMaps[key] = new Map();
    if (!user) return;
    for (const key of Object.keys(scopeConfig)) {
      const rows = user.scopes?.[key]?.rows || [];
      for (const row of rows) state.scopeMaps[key].set(String(row.id), row);
    }
  }

  function scopeMode(user, key) {
    return user?.scopes?.[key]?.mode || "all";
  }

  function scopeCardMarkup(user, key, disabled) {
    const cfg = scopeConfig[key];
    const mode = scopeMode(user, key);
    return `<div class="access-scope-card" data-scope-card="${key}">
      <div class="access-scope-card__head"><div class="access-scope-card__copy"><strong>${cfg.title}</strong><span>${cfg.help}</span></div>
      <select class="access-select" data-scope-mode="${key}" ${disabled ? "disabled" : ""}><option value="all" ${mode === "all" ? "selected" : ""}>All</option><option value="selected" ${mode === "selected" ? "selected" : ""}>Selected only</option><option value="none" ${mode === "none" ? "selected" : ""}>None</option></select></div>
      <div data-scope-selected="${key}"></div>
      <div class="access-scope-picker" data-scope-picker="${key}" ${mode === "selected" ? "" : "hidden"}><input type="search" data-scope-search="${key}" placeholder="Search ${cfg.title.toLowerCase()}…" autocomplete="off" ${disabled ? "disabled" : ""}><div class="access-scope-results" data-scope-results="${key}" hidden></div></div>
      <small class="access-field-error" id="fieldError-${cfg.idsField}"></small>
    </div>`;
  }

  function renderSelectedScope(key) {
    const host = els.drawerBody.querySelector(`[data-scope-selected="${key}"]`);
    if (!host) return;
    host.replaceChildren();
    const mode = els.drawerBody.querySelector(`[data-scope-mode="${key}"]`)?.value;
    if (mode !== "selected") return;
    const values = [...state.scopeMaps[key].values()];
    if (!values.length) {
      const note = document.createElement("div"); note.className = "access-form-note"; note.textContent = "No records selected yet."; host.appendChild(note); return;
    }
    const wrap = document.createElement("div"); wrap.className = "access-scope-selected";
    for (const row of values) {
      const chip = document.createElement("span"); chip.className = "access-scope-chip";
      const label = document.createElement("span"); label.textContent = `${row.code ? `${row.code} · ` : ""}${row.name}`;
      chip.appendChild(label);
      const editable = !els.drawerBody.querySelector(`[data-scope-mode="${key}"]`)?.disabled;
      if (editable) {
        const remove = document.createElement("button"); remove.type = "button"; remove.setAttribute("aria-label", `Remove ${row.name}`); remove.textContent = "×";
        remove.addEventListener("click", () => { state.scopeMaps[key].delete(String(row.id)); renderSelectedScope(key); renderScopeResults(key, state._scopeResults?.[key] || []); });
        chip.appendChild(remove);
      }
      wrap.appendChild(chip);
    }
    host.appendChild(wrap);
  }

  function renderScopeResults(key, rows) {
    const host = els.drawerBody.querySelector(`[data-scope-results="${key}"]`);
    if (!host) return;
    host.replaceChildren();
    if (!rows.length) {
      const empty = document.createElement("div"); empty.className = "access-scope-empty"; empty.textContent = "No matching records."; host.appendChild(empty); host.hidden = false; return;
    }
    for (const row of rows) {
      const selected = state.scopeMaps[key].has(String(row.id));
      const button = document.createElement("button"); button.type = "button"; button.className = `access-scope-result${selected ? " is-selected" : ""}`; button.disabled = selected;
      const copy = document.createElement("span");
      const name = document.createElement("strong"); name.textContent = `${row.code ? `${row.code} · ` : ""}${row.name}`;
      const meta = document.createElement("small"); meta.textContent = row.meta || "Company record";
      copy.append(name, meta);
      const status = document.createElement("small"); status.textContent = selected ? "Selected" : "Add";
      button.append(copy, status);
      button.addEventListener("click", () => { state.scopeMaps[key].set(String(row.id), row); renderSelectedScope(key); renderScopeResults(key, rows); });
      host.appendChild(button);
    }
    host.hidden = false;
  }

  async function loadScopeResults(key, query = "") {
    const host = els.drawerBody.querySelector(`[data-scope-results="${key}"]`);
    if (!host) return;
    if (query && query.length < 2) {
      host.innerHTML = '<div class="access-scope-empty">Enter at least 2 characters to search.</div>'; host.hidden = false; return;
    }
    state.scopeAbort[key]?.abort?.();
    const controller = new AbortController(); state.scopeAbort[key] = controller;
    host.innerHTML = '<div class="access-scope-empty">Loading…</div>'; host.hidden = false;
    const params = new URLSearchParams({ type: scopeConfig[key].api });
    if (query) params.set("q", query);
    try {
      const payload = await api(`/api/access/scopes/lookup/?${params.toString()}`, { signal: controller.signal });
      state._scopeResults ||= {}; state._scopeResults[key] = payload.rows || [];
      renderScopeResults(key, payload.rows || []);
    } catch (error) {
      if (error?.name === "AbortError") return;
      host.innerHTML = `<div class="access-scope-empty">${htmlEscape(error.message || "Lookup failed")}</div>`; host.hidden = false;
    }
  }

  function wireScopes(disabled) {
    for (const key of Object.keys(scopeConfig)) {
      const mode = els.drawerBody.querySelector(`[data-scope-mode="${key}"]`);
      const picker = els.drawerBody.querySelector(`[data-scope-picker="${key}"]`);
      const input = els.drawerBody.querySelector(`[data-scope-search="${key}"]`);
      renderSelectedScope(key);
      if (!mode || disabled) continue;
      mode.addEventListener("change", () => {
        picker.hidden = mode.value !== "selected";
        renderSelectedScope(key);
        if (mode.value === "selected") { input.focus(); loadScopeResults(key, input.value.trim()); }
      });
      input.addEventListener("focus", () => loadScopeResults(key, input.value.trim()));
      input.addEventListener("input", () => {
        window.clearTimeout(state.scopeTimer[key]);
        const q = input.value.trim();
        state.scopeTimer[key] = window.setTimeout(() => loadScopeResults(key, q), 280);
      });
    }
  }

  function collectScopes() {
    const payload = {};
    for (const [key, cfg] of Object.entries(scopeConfig)) {
      const mode = els.drawerBody.querySelector(`[data-scope-mode="${key}"]`)?.value || "all";
      payload[cfg.modeField] = mode;
      payload[cfg.idsField] = mode === "selected" ? [...state.scopeMaps[key].keys()] : [];
    }
    return payload;
  }

  function clearFormErrors() {
    els.drawerBody.querySelectorAll(".access-field-error").forEach((node) => { node.textContent = ""; });
    byId("accessFormGlobalError")?.remove();
  }

  function showFormErrors(error) {
    clearFormErrors();
    const errors = error?.payload?.errors || { __all__: [error?.message || "The request could not be completed."] };
    const map = { firstName: "accessFirstName", lastName: "accessLastName", username: "accessUsername", email: "accessEmail", temporaryPassword: "accessTemporaryPassword", accessProfileId: "accessProfileId", projectIds: "projectIds", branchIds: "branchIds", inventoryLocationIds: "inventoryLocationIds" };
    const globals = [];
    for (const [field, messages] of Object.entries(errors)) {
      const text = Array.isArray(messages) ? messages.join(" ") : String(messages);
      const id = map[field] || field;
      const target = byId(`fieldError-${id}`);
      if (target) target.textContent = text; else globals.push(text);
    }
    if (globals.length) {
      const alert = document.createElement("div"); alert.className = "access-form-alert"; alert.id = "accessFormGlobalError"; alert.textContent = globals.join(" ");
      els.drawerBody.prepend(alert);
    }
  }

  function generateTemporaryPassword() {
    const alpha = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789";
    const symbols = "!@#$%*+-_";
    const values = new Uint32Array(16); crypto.getRandomValues(values);
    let result = "";
    for (let index = 0; index < 14; index += 1) result += alpha[values[index] % alpha.length];
    result += symbols[values[14] % symbols.length];
    result += String(values[15] % 10);
    return result;
  }

  function profileOptions(selectedId, disabled) {
    return state.profiles
      .filter((profile) => (profile.active !== false || String(profile.id) === String(selectedId || "")) && (actorIsOwner || !profile.owner || profile.id === selectedId))
      .map((profile) => `<option value="${htmlEscape(profile.id)}" ${String(profile.id) === String(selectedId || "") ? "selected" : ""}>${htmlEscape(profile.name)}${profile.system ? " · Built-in" : " · Custom"}${profile.active === false ? " · Inactive" : ""}</option>`).join("");
  }

  function renderUserForm(user = null) {
    const creating = !user;
    if (user?.profile?.id && !state.profiles.some((profile) => String(profile.id) === String(user.profile.id))) {
      state.profiles.push({ ...user.profile, permissions: [], description: "Assigned Access Profile." });
    }
    const isSelf = Boolean(user && String(user.membershipId) === actorMembershipId);
    const protectedOwner = Boolean(user?.profile?.owner && !actorIsOwner);
    const canEditIdentity = canManageUsers && !protectedOwner;
    const canEditAccess = canEditIdentity && !isSelf;
    const canEdit = creating ? canManageUsers : canEditIdentity;
    initializeScopeMaps(user);
    state.drawerUser = user; state.drawerMode = creating ? "create" : "edit";
    const selectedProfileId = user?.profile?.id || "";

    openDrawer({
      eyebrow: creating ? "Add user" : "User access",
      title: creating ? "Create company user" : (user.displayName || user.username),
      subtitle: creating ? "Create a sign-in identity, assign an Access Profile and restrict operational scope." : `${user.username} · ${user.profile?.name || "No profile"}`,
    });

    els.drawerBody.innerHTML = `<form class="access-form" id="accessUserForm" novalidate>
      <section class="access-form-section">
        <div class="access-section-head"><div><strong>Identity</strong><span>Company sign-in identity. Usernames and emails are unique across SESCCO MS.</span></div>${user ? `<span class="access-status ${user.active ? "is-active" : "is-inactive"}">${user.active ? "Active" : "Inactive"}</span>` : ""}</div>
        <div class="access-form-grid">
          ${formField({ id: "accessFirstName", label: "First name", value: user?.firstName, disabled: !canEdit })}
          ${formField({ id: "accessLastName", label: "Last name", value: user?.lastName, disabled: !canEdit })}
          ${formField({ id: "accessUsername", label: "Username", value: user?.username, required: true, disabled: !canEdit })}
          ${formField({ id: "accessEmail", label: "Email", value: user?.email, type: "email", required: true, disabled: !canEdit })}
          ${creating ? `<label class="access-field is-wide"><span>Temporary password <em class="required">*</em></span><div class="access-password-wrap"><input class="access-input" id="accessTemporaryPassword" type="password" autocomplete="new-password" required><div class="access-password-tools"><button class="access-password-tool" type="button" id="accessPasswordShow">Show</button><button class="access-password-tool" type="button" id="accessPasswordGenerate">Generate</button></div></div><small class="access-field-error" id="fieldError-accessTemporaryPassword"></small></label>` : ""}
        </div>
        ${creating ? '<div class="access-form-note"><strong>Forced change:</strong> the new user must change this temporary password. The plaintext password is not stored in access audit records.</div>' : ""}
      </section>

      <section class="access-form-section">
        <div class="access-section-head"><div><strong>Access Profile</strong><span>The persisted profile defines pages and actions. Scope never adds a permission the profile does not have.</span></div></div>
        <label class="access-field"><span>Profile <em class="required">*</em></span><select class="access-select" id="accessProfileId" ${!canEditAccess && !creating ? "disabled" : ""}><option value="">Choose Access Profile</option>${profileOptions(selectedProfileId, !canEditAccess)}</select><small class="access-field-error" id="fieldError-accessProfileId"></small></label>
        <div class="access-profile-card" id="accessProfileSummary"></div>
        ${isSelf ? '<div class="access-form-note"><strong>Your own authority is protected.</strong> You can update your identity here, but another authorized administrator must change your Access Profile or scopes.</div>' : ""}
        ${protectedOwner ? '<div class="access-form-note"><strong>Owner protection.</strong> Only a Company Owner can modify another Owner account.</div>' : ""}
      </section>

      <section class="access-form-section">
        <div class="access-section-head"><div><strong>Operational scopes</strong><span>Use Selected only to limit otherwise-permitted operations to explicit company records.</span></div></div>
        <div class="access-scope-grid">
          ${scopeCardMarkup(user, "projects", !canEditAccess && !creating)}
          ${scopeCardMarkup(user, "branches", !canEditAccess && !creating)}
          ${scopeCardMarkup(user, "inventoryLocations", !canEditAccess && !creating)}
        </div>
      </section>

      ${user ? `<section class="access-form-section"><div class="access-section-head"><div><strong>Account state</strong><span>Security actions are audited. Established accounts are deactivated instead of hard-deleted.</span></div></div><div class="access-detail-summary"><div class="access-detail-item"><span>Joined</span><strong>${htmlEscape(formatDate(user.joinedAt, "—"))}</strong></div><div class="access-detail-item"><span>Last sign-in</span><strong>${htmlEscape(formatDate(user.lastLogin))}</strong></div><div class="access-detail-item"><span>Password state</span><strong>${user.mustChangePassword ? "Change required" : "Current"}</strong></div><div class="access-detail-item"><span>Identity</span><strong>${user.accountActive ? "Enabled" : "Disabled"}</strong></div></div>${canManageUsers ? `<div class="access-security-actions"><button class="access-drawer-action" type="button" data-security-action="password" ${isSelf || protectedOwner ? "disabled" : ""}><svg viewBox="0 0 24 24"><path d="M7 11V8a5 5 0 0 1 10 0v3M5 11h14v10H5z"/></svg><span><strong>Reset password</strong><small>Set a temporary password and require change.</small></span></button><button class="access-drawer-action ${user.active ? "is-danger" : ""}" type="button" data-security-action="status" ${isSelf || protectedOwner ? "disabled" : ""}><svg viewBox="0 0 24 24"><path d="M12 2v10m7.1-5.1a9 9 0 1 1-14.2 0"/></svg><span><strong>${user.active ? "Deactivate access" : "Reactivate access"}</strong><small>${user.active ? "Stops company access and may disable sign-in." : "Restores this company membership."}</small></span></button>${!user.profile?.owner ? `<button class="access-drawer-action is-danger" type="button" data-security-action="delete" ${isSelf || protectedOwner ? "disabled" : ""}><svg viewBox="0 0 24 24"><path d="M4 7h16M9 7V4h6v3M7 7l1 13h8l1-13"/></svg><span><strong>Delete unused account</strong><small>Allowed only before sign-in/history exists.</small></span></button>` : ""}</div>` : ""}</section>` : ""}
    </form>`;

    const profileSelect = byId("accessProfileId");
    const selectedProfile = state.profiles.find((profile) => String(profile.id) === String(profileSelect?.value));
    renderProfileSummary(selectedProfile);
    profileSelect?.addEventListener("change", () => renderProfileSummary(state.profiles.find((profile) => String(profile.id) === String(profileSelect.value))));
    wireScopes(!canEditAccess && !creating);

    if (creating) {
      const pw = byId("accessTemporaryPassword");
      byId("accessPasswordShow")?.addEventListener("click", (event) => { const show = pw.type === "password"; pw.type = show ? "text" : "password"; event.currentTarget.textContent = show ? "Hide" : "Show"; });
      byId("accessPasswordGenerate")?.addEventListener("click", () => { pw.value = generateTemporaryPassword(); pw.type = "text"; byId("accessPasswordShow").textContent = "Hide"; pw.focus(); pw.select(); });
    }

    els.drawerBody.querySelectorAll("[data-security-action]").forEach((button) => button.addEventListener("click", () => renderSecurityAction(button.dataset.securityAction, user)));
    if (user && canViewAudit) {
      const accountSection = Array.from(els.drawerBody.querySelectorAll(".access-form-section")).at(-1);
      if (accountSection) {
        const historyWrap = document.createElement("div"); historyWrap.className = "access-history-entry";
        const historyButton = document.createElement("button"); historyButton.className = "access-drawer-action"; historyButton.type = "button";
        historyButton.innerHTML = '<svg viewBox="0 0 24 24"><path d="M12 8v5l3 2M4.9 4.9A10 10 0 1 1 2 12m0-5v5h5"/></svg><span><strong>Access History</strong><small>Review immutable changes and guarded prior-access recovery.</small></span>';
        historyButton.addEventListener("click", () => renderUserHistory(user));
        historyWrap.appendChild(historyButton); accountSection.appendChild(historyWrap);
      }
    }

    els.drawerFooter.replaceChildren();
    const cancel = document.createElement("button"); cancel.className = "btn btn-ghost"; cancel.type = "button"; cancel.textContent = canEdit ? "Cancel" : "Close"; cancel.addEventListener("click", closeDrawer);
    els.drawerFooter.appendChild(cancel);
    if (canEdit) {
      const save = document.createElement("button"); save.className = "btn btn-primary"; save.type = "button"; save.textContent = creating ? "Create User" : "Save Changes";
      save.addEventListener("click", () => saveUserForm(user, save, { canEditAccess }));
      els.drawerFooter.appendChild(save);
    }
  }

  async function saveUserForm(user, button, { canEditAccess }) {
    clearFormErrors();
    button.disabled = true; const previous = button.textContent; button.textContent = user ? "Saving…" : "Creating…";
    const payload = {
      firstName: byId("accessFirstName")?.value.trim() || "",
      lastName: byId("accessLastName")?.value.trim() || "",
      username: byId("accessUsername")?.value.trim() || "",
      email: byId("accessEmail")?.value.trim() || "",
    };
    if (!user) payload.temporaryPassword = byId("accessTemporaryPassword")?.value || "";
    if (!user || canEditAccess) {
      payload.accessProfileId = byId("accessProfileId")?.value || "";
      payload.scopes = collectScopes();
    }
    try {
      const result = await api(user ? `/api/access/users/${user.membershipId}/` : "/api/access/users/", { method: user ? "PATCH" : "POST", body: JSON.stringify(payload) });
      toast(user ? "User access updated." : "Company user created.");
      closeDrawer(); await loadUsers();
      if (result.user?.membershipId && user) await openUser(result.user.membershipId);
    } catch (error) {
      showFormErrors(error);
    } finally {
      button.disabled = false; button.textContent = previous;
    }
  }

  function accessHistoryEventMarkup(event, user) {
    const changes = Array.isArray(event.changes) ? event.changes : [];
    const changeMarkup = changes.length
      ? `<div class="access-history-diff">${changes.map((change) => `<div><span>${htmlEscape(change.field)}</span><strong>${htmlEscape(change.before)}</strong><em>→</em><strong>${htmlEscape(change.after)}</strong></div>`).join("")}</div>`
      : '<div class="access-history-no-diff">Security event recorded without a recoverable configuration diff.</div>';
    const canRestore = Boolean(event.restorableBefore && canManageUsers && String(user.membershipId) !== actorMembershipId && (!user.profile?.owner || actorIsOwner));
    return `<article class="access-history-card" data-history-event="${htmlEscape(event.id)}">
      <header><div><strong>${htmlEscape(auditActionLabel(event.action))}</strong><span>${htmlEscape(formatDateTime(event.date))} · ${htmlEscape(event.actor || "System")}</span></div>${canRestore ? `<button class="btn btn-sm" type="button" data-restore-event="${htmlEscape(event.id)}">Restore prior access</button>` : ""}</header>
      ${changeMarkup}
      <footer><span>${htmlEscape(event.target || user.displayName || user.username)}</span><small>${htmlEscape(event.requestId || "No request ID")}</small></footer>
    </article>`;
  }

  async function renderUserHistory(user, page = 1) {
    if (!canViewAudit) return;
    state.drawerMode = "history";
    openDrawer({ eyebrow: "Access History", title: user.displayName || user.username, subtitle: `${user.username} · immutable access and credential events` });
    els.drawerBody.innerHTML = '<div class="access-loading">Loading user Access History…</div>';
    els.drawerFooter.replaceChildren();
    try {
      const payload = await api(`/api/access/users/${encodeURIComponent(user.membershipId)}/history/?page=${encodeURIComponent(page)}&page_size=25`);
      const history = payload.history || {};
      const rows = history.rows || [];
      els.drawerBody.innerHTML = rows.length
        ? `<div class="access-history-list">${rows.map((event) => accessHistoryEventMarkup(event, user)).join("")}</div>`
        : '<div class="access-empty">No access events are recorded for this user yet.</div>';
      els.drawerBody.querySelectorAll("[data-restore-event]").forEach((button) => {
        const event = rows.find((item) => String(item.id) === String(button.dataset.restoreEvent));
        if (event) button.addEventListener("click", () => renderAccessRestore(user, event));
      });

      const back = document.createElement("button"); back.className = "btn btn-ghost"; back.type = "button"; back.textContent = "Back to User"; back.addEventListener("click", () => renderUserForm(user));
      const spacer = document.createElement("span"); spacer.className = "access-footer-spacer";
      els.drawerFooter.append(back, spacer);
      if (history.hasPrevious) {
        const prev = document.createElement("button"); prev.className = "btn btn-sm"; prev.type = "button"; prev.textContent = "Previous"; prev.addEventListener("click", () => renderUserHistory(user, Math.max(1, Number(history.page || page) - 1))); els.drawerFooter.appendChild(prev);
      }
      if (history.hasNext) {
        const next = document.createElement("button"); next.className = "btn btn-sm"; next.type = "button"; next.textContent = "Next"; next.addEventListener("click", () => renderUserHistory(user, Number(history.page || page) + 1)); els.drawerFooter.appendChild(next);
      }
    } catch (error) {
      els.drawerBody.innerHTML = `<div class="access-error">${htmlEscape(error.message || "Could not load user Access History.")}</div>`;
      els.drawerFooter.innerHTML = '<button class="btn" type="button" id="accessHistoryBack">Back</button>';
      byId("accessHistoryBack")?.addEventListener("click", () => renderUserForm(user));
    }
  }

  function renderAccessRestore(user, event) {
    state.drawerMode = "restore-access";
    const before = event.before || {};
    const scopes = before.scopes || {};
    els.drawerEyebrow.textContent = "Guarded recovery";
    els.drawerTitle.textContent = "Restore prior access";
    els.drawerSubtitle.textContent = `${user.displayName || user.username} · from ${formatDateTime(event.date)}`;
    const profile = before.accessProfileKey || "historical profile";
    const scopeText = [
      `Projects: ${scopes.projectMode || "—"}`,
      `Branches: ${scopes.branchMode || "—"}`,
      `Locations: ${scopes.inventoryLocationMode || "—"}`,
    ].join(" · ");
    els.drawerBody.innerHTML = `<div class="access-confirm">
      <div class="access-form-alert"><strong>This creates a new recovery event; it never rewrites history.</strong> The backend revalidates the historical Access Profile, scope records, owner safeguards and company boundary before applying anything. Existing sessions for this user will be revoked again.</div>
      <div class="access-detail-summary"><div class="access-detail-item"><span>Prior profile</span><strong>${htmlEscape(profile)}</strong></div><div class="access-detail-item"><span>Prior access</span><strong>${before.accessActive === false ? "Inactive" : "Active"}</strong></div></div>
      <div class="access-form-note"><strong>Scope snapshot:</strong> ${htmlEscape(scopeText)}</div>
      <label class="access-field"><span>Type username <strong>${htmlEscape(user.username)}</strong> to confirm</span><input class="access-input" id="accessRestoreConfirmation" autocomplete="off"><small class="access-field-error" id="fieldError-confirmation"></small></label>
    </div>`;
    els.drawerFooter.replaceChildren();
    const back = document.createElement("button"); back.className = "btn btn-ghost"; back.type = "button"; back.textContent = "Back"; back.addEventListener("click", () => renderUserHistory(user));
    const spacer = document.createElement("span"); spacer.className = "access-footer-spacer";
    const restore = document.createElement("button"); restore.className = "btn btn-primary"; restore.type = "button"; restore.textContent = "Restore Prior Access";
    restore.addEventListener("click", async () => {
      clearFormErrors(); restore.disabled = true; const previous = restore.textContent; restore.textContent = "Restoring…";
      try {
        const result = await api(`/api/access/users/${encodeURIComponent(user.membershipId)}/restore-access/`, { method: "POST", body: JSON.stringify({ eventId: event.id, confirmation: byId("accessRestoreConfirmation")?.value || "" }) });
        toast("Prior access configuration restored and existing sessions revoked.");
        await loadUsers();
        if (canViewAudit) loadAccessHistory().catch(() => {});
        if (result?.user?.membershipId) await openUser(result.user.membershipId);
      } catch (error) {
        showFormErrors(error);
      } finally {
        restore.disabled = false; restore.textContent = previous;
      }
    });
    els.drawerFooter.append(back, spacer, restore);
  }

  function renderSecurityAction(action, user) {
    state.drawerMode = action;
    const titleMap = { password: "Reset temporary password", status: user.active ? "Deactivate user access" : "Reactivate user access", delete: "Delete unused account" };
    els.drawerEyebrow.textContent = "Security action";
    els.drawerTitle.textContent = titleMap[action] || "Security action";
    els.drawerSubtitle.textContent = `${user.displayName || user.username} · ${user.username}`;
    const identity = `<div class="access-confirm__identity"><span class="access-avatar">${htmlEscape(initials(user))}</span><span><strong>${htmlEscape(user.displayName || user.username)}</strong><small>${htmlEscape(user.profile?.name || "No profile")} · ${htmlEscape(user.email || user.username)}</small></span></div>`;
    if (action === "password") {
      els.drawerBody.innerHTML = `<div class="access-confirm">${identity}<div class="access-form-note"><strong>Existing sessions:</strong> changing the Django password hash invalidates authenticated sessions. The user will be required to change this temporary password.</div><label class="access-field"><span>Temporary password <em class="required">*</em></span><div class="access-password-wrap"><input class="access-input" id="accessTemporaryPassword" type="password" autocomplete="new-password"><div class="access-password-tools"><button class="access-password-tool" type="button" id="accessPasswordShow">Show</button><button class="access-password-tool" type="button" id="accessPasswordGenerate">Generate</button></div></div><small class="access-field-error" id="fieldError-accessTemporaryPassword"></small></label></div>`;
      const pw = byId("accessTemporaryPassword");
      byId("accessPasswordShow")?.addEventListener("click", (event) => { const show = pw.type === "password"; pw.type = show ? "text" : "password"; event.currentTarget.textContent = show ? "Hide" : "Show"; });
      byId("accessPasswordGenerate")?.addEventListener("click", () => { pw.value = generateTemporaryPassword(); pw.type = "text"; byId("accessPasswordShow").textContent = "Hide"; pw.focus(); pw.select(); });
    } else if (action === "status") {
      els.drawerBody.innerHTML = `<div class="access-confirm">${identity}<div class="access-form-note"><strong>${user.active ? "Deactivate" : "Reactivate"}:</strong> ${user.active ? "this removes company access immediately. If no other active company membership exists, sign-in is disabled too." : "this restores the company membership and enables the identity if its assigned Access Profile is active."}</div></div>`;
    } else if (action === "delete") {
      els.drawerBody.innerHTML = `<div class="access-confirm">${identity}<div class="access-form-alert"><strong>Permanent only for unused onboarding identities.</strong> If this account has signed in, acted on records, belongs to another company or is referenced by system history, the backend will reject deletion and you must deactivate it instead.</div><label class="access-field"><span>Type username <strong>${htmlEscape(user.username)}</strong> to confirm</span><input class="access-input" id="accessDeleteConfirmation" autocomplete="off"><small class="access-field-error" id="fieldError-confirmation"></small></label></div>`;
    }
    els.drawerFooter.replaceChildren();
    const back = document.createElement("button"); back.className = "btn btn-ghost"; back.type = "button"; back.textContent = "Back"; back.addEventListener("click", () => renderUserForm(user));
    const spacer = document.createElement("span"); spacer.className = "access-footer-spacer";
    const submit = document.createElement("button"); submit.className = action === "password" || (!user.active && action === "status") ? "btn btn-primary" : "btn btn-danger"; submit.type = "button";
    submit.textContent = action === "password" ? "Reset Password" : action === "status" ? (user.active ? "Deactivate" : "Reactivate") : "Delete Account";
    submit.addEventListener("click", () => submitSecurityAction(action, user, submit));
    els.drawerFooter.append(back, spacer, submit);
  }

  async function submitSecurityAction(action, user, button) {
    clearFormErrors();
    button.disabled = true; const previous = button.textContent; button.textContent = "Working…";
    try {
      let result;
      if (action === "password") {
        result = await api(`/api/access/users/${user.membershipId}/reset-password/`, { method: "POST", body: JSON.stringify({ temporaryPassword: byId("accessTemporaryPassword")?.value || "" }) });
        toast("Temporary password reset. The user must change it at next sign-in.");
      } else if (action === "status") {
        result = await api(`/api/access/users/${user.membershipId}/status/`, { method: "POST", body: JSON.stringify({ active: !user.active }) });
        toast(user.active ? "User access deactivated." : "User access reactivated.");
      } else {
        result = await api(`/api/access/users/${user.membershipId}/`, { method: "DELETE", body: JSON.stringify({ confirmation: byId("accessDeleteConfirmation")?.value || "" }) });
        toast("Unused account deleted.");
      }
      closeDrawer(); await loadUsers();
      if (action !== "delete" && result?.user?.membershipId) await openUser(result.user.membershipId);
    } catch (error) {
      showFormErrors(error);
    } finally {
      button.disabled = false; button.textContent = previous;
    }
  }

  async function openUser(membershipId) {
    try {
      if (canManageUsers || permissionSet.has("access.profiles.view")) await loadProfiles();
      openDrawer({ eyebrow: "User access", title: "Loading…", subtitle: "Loading company user authority." });
      els.drawerBody.innerHTML = '<div class="access-loading">Loading user access…</div>'; els.drawerFooter.replaceChildren();
      const payload = await api(`/api/access/users/${encodeURIComponent(membershipId)}/`);
      renderUserForm(payload.user);
    } catch (error) {
      els.drawerTitle.textContent = "Unable to open user";
      els.drawerSubtitle.textContent = "The requested user access record could not be loaded.";
      els.drawerBody.innerHTML = `<div class="access-error">${htmlEscape(error.message || "Could not load user")}</div>`;
      els.drawerFooter.innerHTML = '<button class="btn" type="button" id="accessDrawerErrorClose">Close</button>';
      byId("accessDrawerErrorClose")?.addEventListener("click", closeDrawer);
    }
  }

  async function openCreate() {
    if (!canManageUsers) return;
    try { await loadProfiles(); renderUserForm(null); }
    catch (error) { toast(error.message || "Could not load Access Profiles.", "error"); }
  }

  document.querySelectorAll("[data-access-add-user]").forEach((button) => button.addEventListener("click", openCreate));
  document.querySelectorAll("[data-access-add-profile]").forEach((button) => button.addEventListener("click", async () => { try { await loadProfiles(); renderProfileForm(null); } catch(error) { toast(error.message || "Could not load Access Profiles.", "error"); } }));
  els.drawerClose?.addEventListener("click", closeDrawer);
  els.scrim?.addEventListener("click", closeDrawer);
  document.addEventListener("keydown", (event) => { if (event.key === "Escape" && !els.drawer.hidden) closeDrawer(); });
  document.addEventListener("click", (event) => {
    if (!els.drawer || els.drawer.hidden) return;
    els.drawer.querySelectorAll("[data-scope-results]").forEach((menu) => {
      const picker = menu.closest(".access-scope-picker");
      if (picker && !picker.contains(event.target)) menu.hidden = true;
    });
  });

  els.search?.addEventListener("input", () => {
    state.query = els.search.value.trim();
    window.clearTimeout(state.searchTimer);
    if (state.query.length === 1) { els.searchState.textContent = "Type 2+ characters"; return; }
    state.searchTimer = window.setTimeout(() => loadUsers({ resetPage: true }), 320);
  });
  els.status?.addEventListener("change", () => { state.status = els.status.value; loadUsers({ resetPage: true }); });
  els.pageSize?.addEventListener("change", () => { state.pageSize = Number(els.pageSize.value) || 25; loadUsers({ resetPage: true }); });
  els.prev?.addEventListener("click", () => { if (!state.hasPrevious) return; state.page = Math.max(1, state.page - 1); loadUsers(); });
  els.next?.addEventListener("click", () => { if (!state.hasNext) return; state.page += 1; loadUsers(); });

  els.historySearch?.addEventListener("input", () => {
    state.historyQuery = els.historySearch.value.trim();
    window.clearTimeout(state.historySearchTimer);
    if (state.historyQuery.length === 1) { if (els.historySearchState) els.historySearchState.textContent = "Type 2+ characters"; return; }
    state.historySearchTimer = window.setTimeout(() => loadAccessHistory({ resetPage: true }), 320);
  });
  els.historyTarget?.addEventListener("change", () => { state.historyTarget = els.historyTarget.value; loadAccessHistory({ resetPage: true }); });
  els.historyPageSize?.addEventListener("change", () => { state.historyPageSize = Number(els.historyPageSize.value) || 25; loadAccessHistory({ resetPage: true }); });
  els.historyPrev?.addEventListener("click", () => { if (!state.historyHasPrevious) return; state.historyPage = Math.max(1, state.historyPage - 1); loadAccessHistory(); });
  els.historyNext?.addEventListener("click", () => { if (!state.historyHasNext) return; state.historyPage += 1; loadAccessHistory(); });

  loadUsers();
  if (canViewProfiles || canManageProfiles) loadProfiles().catch((error) => { if (els.profileRows) els.profileRows.innerHTML = `<tr><td colspan="6"><div class="access-error">${htmlEscape(error.message || "Could not load Access Profiles.")}</div></td></tr>`; });
  if (canViewAudit) loadAccessHistory();
})();
