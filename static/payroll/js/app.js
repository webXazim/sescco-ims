(() => {
  const APP_ROUTES = {
    overview:{title:'Overview'}, 'management-cost':{title:'Workforce Cost'}, 'management-approvals':{title:'Approval Center'}, 'management-audit':{title:'Audit Trail'}, 'access-roles':{title:'Access & Roles'},
    'internal-employees':{title:'Internal Employees'}, branches:{title:'Branches & Offices'}, departments:{title:'Departments'}, 'bank-export':{title:'Bank & WPS Export'}, 'salary-setup':{title:'Salary Setup'},
    'rental-workforce':{title:'Rental Workforce'}, 'rental-onboarding':{title:'Rental Worker Onboarding'}, 'rental-assignments':{title:'Rental Assignments'}, projects:{title:'Projects'}, suppliers:{title:'Manpower Suppliers'},
    timesheets:{title:'Timesheets'}, 'payroll-runs':{title:'Payroll Runs'}, 'rental-settlements':{title:'Rental Settlements'}, adjustments:{title:'Advances & Adjustments'}, payments:{title:'Payments'}, wps:{title:'WPS'}, documents:{title:'Documents'}, archive:{title:'Archive'}, trash:{title:'Delete'}, reports:{title:'Reports'}, settings:{title:'Settings'}
  };
  const PAGE_SEARCH_ITEMS = [
    {type:'Page',code:'OV',name:'Overview',meta:'Workspace overview and operational status',route:'overview'},
    {type:'Page',code:'IE',name:'Internal Employees',meta:'Internal company employee master',route:'internal-employees'},
    {type:'Page',code:'BR',name:'Branches & Offices',meta:'Internal organization master',route:'branches'},
    {type:'Page',code:'DP',name:'Departments',meta:'Internal department master',route:'departments'},
    {type:'Page',code:'SS',name:'Salary Setup',meta:'Salary components, structures and overtime policy',route:'salary-setup'},
    {type:'Page',code:'TS',name:'Timesheets',meta:'Attendance and project timesheets',route:'timesheets'},
    {type:'Page',code:'PR',name:'Payroll Runs',meta:'Internal payroll calculation and review',route:'payroll-runs'},
    {type:'Page',code:'BW',name:'Bank & WPS Export',meta:'Salary payment readiness and export',route:'bank-export'},
    {type:'Page',code:'WP',name:'WPS',meta:'WPS readiness and salary payment batches',route:'wps'},
    {type:'Page',code:'RW',name:'Rental Workforce',meta:'Rental worker master',route:'rental-workforce'},
    {type:'Page',code:'RA',name:'Rental Assignments',meta:'Project, trade and rate assignment history',route:'rental-assignments'},
    {type:'Page',code:'PJ',name:'Projects',meta:'Rental manpower project master',route:'projects'},
    {type:'Page',code:'SP',name:'Manpower Suppliers',meta:'Rental manpower supplier master',route:'suppliers'},
    {type:'Page',code:'RS',name:'Rental Settlements',meta:'Supplier settlement calculation and approval',route:'rental-settlements'},
    {type:'Page',code:'AD',name:'Advances & Adjustments',meta:'Internal and rental adjustment ledgers',route:'adjustments'},
    {type:'Page',code:'PY',name:'Payments',meta:'Internal salary and supplier payments',route:'payments'},
    {type:'Page',code:'DC',name:'Documents',meta:'Finalized payroll and workforce documents',route:'documents'},
    {type:'Page',code:'AR',name:'Archive',meta:'Archived master records retained for history',route:'archive'},
    {type:'Page',code:'DL',name:'Delete',meta:'Deleted master records recoverable for 30 days',route:'trash'},
    {type:'Page',code:'RP',name:'Reports',meta:'Controlled payroll and workforce reports',route:'reports'},
    {type:'Page',code:'SE',name:'Settings',meta:'Company and domain configuration',route:'settings'}
  ];
  const accessContextNode = document.getElementById('payroll-access-context');
  if (!accessContextNode) throw new Error('Missing server access context.');
  const serverAccess = JSON.parse(accessContextNode.textContent || '{}');
  if (!serverAccess.role || !serverAccess.role_matrix) throw new Error('Invalid server access context.');
  const internalMasterNode = document.getElementById('payroll-internal-master-context');
  if (!internalMasterNode) throw new Error('Missing internal payroll master context.');
  const internalMaster = JSON.parse(internalMasterNode.textContent || '{}');
  const rentalMasterNode = document.getElementById('payroll-rental-master-context');
  if (!rentalMasterNode) throw new Error('Missing rental manpower master context.');
  const rentalMaster = JSON.parse(rentalMasterNode.textContent || '{}');
  const salarySetupNode = document.getElementById('payroll-salary-setup-context');
  if (!salarySetupNode) throw new Error('Missing salary setup context.');
  const salarySetup = JSON.parse(salarySetupNode.textContent || '{}');
  const attendanceContextNode = document.getElementById('payroll-attendance-context');
  if (!attendanceContextNode) throw new Error('Missing attendance context.');
  const attendanceBootstrap = JSON.parse(attendanceContextNode.textContent || '{}');
  const payrollContextNode = document.getElementById('payroll-run-context');
  if (!payrollContextNode) throw new Error('Missing internal payroll context.');
  const payrollBootstrap = JSON.parse(payrollContextNode.textContent || '{}');
  const paymentContextNode = document.getElementById('payroll-payment-context');
  if (!paymentContextNode) throw new Error('Missing salary payment context.');
  const paymentBootstrap = JSON.parse(paymentContextNode.textContent || '{}');
  const documentsContextNode = document.getElementById('payroll-documents-context');
  if (!documentsContextNode) throw new Error('Missing business documents context.');
  const documentsBootstrap = JSON.parse(documentsContextNode.textContent || '{}');
  const managementContextNode = document.getElementById('payroll-management-context');
  if (!managementContextNode) throw new Error('Missing management context.');
  const managementBootstrap = JSON.parse(managementContextNode.textContent || '{}');
  const settingsContextNode = document.getElementById('payroll-settings-context');
  if (!settingsContextNode) throw new Error('Missing company settings context.');
  const settingsBootstrap = JSON.parse(settingsContextNode.textContent || '{}');
  const recordManagementNode = document.getElementById('payroll-record-management-context');
  if (!recordManagementNode) throw new Error('Missing record management context.');
  const recordManagementBootstrap = JSON.parse(recordManagementNode.textContent || '{}');
  const companyTodayIso = String(settingsBootstrap.today || '');
  if (!/^\d{4}-\d{2}-\d{2}$/.test(companyTodayIso)) throw new Error('Invalid company date context.');
  const periodMonths = ['January','February','March','April','May','June','July','August','September','October','November','December'];
  const [companyTodayYear, companyTodayMonth, companyTodayDay] = companyTodayIso.split('-').map(Number);
  if (!Number.isInteger(companyTodayYear) || companyTodayMonth < 1 || companyTodayMonth > 12 || !Number.isInteger(companyTodayDay) || companyTodayDay < 1 || companyTodayDay > 31) throw new Error('Invalid company date context.');
  const companyCurrentPeriod = `${periodMonths[companyTodayMonth - 1]} ${companyTodayYear}`;
  const defaultInternalPeriod = attendanceBootstrap.period?.label || payrollBootstrap.run?.label || companyCurrentPeriod;

  function defaultTimesheetDay(periodLabel) {
    const [monthName, yearText] = String(periodLabel || '').trim().split(/\s+/);
    const monthIndex = periodMonths.indexOf(monthName);
    const year = Number(yearText);
    if (monthIndex === companyTodayMonth - 1 && year === companyTodayYear) return companyTodayDay;
    return 1;
  }

  function isCompanyToday(day, periodLabel) {
    return Number(day) === companyTodayDay && String(periodLabel || '') === companyCurrentPeriod;
  }
  const csrfToken = document.getElementById('payroll-csrf-token')?.dataset.token || '';

  async function appApi(url, { method = 'GET', body = null } = {}) {
    const options = { method, credentials: 'same-origin', headers: { 'Accept': 'application/json' } };
    if (body !== null) {
      options.headers['Content-Type'] = 'application/json';
      options.headers['X-CSRFToken'] = csrfToken;
      options.body = JSON.stringify(body);
    }
    const response = await fetch(url, options);
    let payload = {};
    try { payload = await response.json(); }
    catch { throw new Error('The server returned an invalid response.'); }
    if (response.status === 401) {
      throw new Error('Your sign-in session is no longer active. Sign in again to continue.');
    }
    if (!response.ok || payload.ok === false) {
      const errors = payload.errors || {};
      const first = Object.values(errors).flat().find(Boolean);
      throw new Error(first || `Request failed (${response.status}).`);
    }
    return payload;
  }

  async function appMultipartApi(url, { method = 'POST', formData = null } = {}) {
    const options = { method, credentials: 'same-origin', headers: { 'Accept': 'application/json', 'X-CSRFToken': csrfToken } };
    if (formData !== null) options.body = formData;
    const response = await fetch(url, options);
    let payload = {};
    try { payload = await response.json(); }
    catch { throw new Error('The server returned an invalid response.'); }
    if (response.status === 401) throw new Error('Your sign-in session is no longer active. Sign in again to continue.');
    if (!response.ok || payload.ok === false) {
      const errors = payload.errors || {};
      const first = Object.values(errors).flat().find(Boolean);
      throw new Error(first || `Request failed (${response.status}).`);
    }
    return payload;
  }

  function replaceStateRecord(collection, record) {
    const index = collection.findIndex(item => item.id === record.id);
    if (index >= 0) collection.splice(index, 1, record);
    else collection.push(record);
  }

  const payrollTableSortPrefs = (() => {
    try { return JSON.parse(localStorage.getItem('payroll-ui-table-sort') || '{}') || {}; }
    catch { return {}; }
  })();
  function persistPayrollTableSortPrefs() {
    try { localStorage.setItem('payroll-ui-table-sort', JSON.stringify(payrollTableSortPrefs)); }
    catch { /* Storage may be unavailable in hardened/private browser modes. */ }
  }

  function bindPayrollSearch(input, setter, { delay = 180, beforeRender = null } = {}) {
    if (!input) return;
    let renderTimer = null;
    const commit = () => {
      setter(input.value);
      if (beforeRender) beforeRender();
      const cursor = input.selectionStart;
      clearTimeout(renderTimer);
      renderTimer = setTimeout(() => {
        renderRoute();
        const next = input.id ? document.getElementById(input.id) : null;
        if (next) {
          next.focus({ preventScroll:true });
          if (typeof cursor === 'number') next.setSelectionRange(cursor, cursor);
        }
      }, delay);
    };
    input.addEventListener('input', commit);
    input.addEventListener('search', commit);
  }

  function payrollSortValue(cell) {
    const explicit = cell?.dataset?.sortValue;
    const raw = String(explicit ?? cell?.innerText ?? cell?.textContent ?? '').replace(/\s+/g, ' ').trim();
    if (!raw || raw === '—' || raw === '-') return { type:'empty', value:'' };

    const compact = raw.replace(/SAR\s*/gi, '').replace(/,/g, '').replace(/%/g, '').trim();
    if (/^[+-]?\d+(?:\.\d+)?$/.test(compact)) return { type:'number', value:Number(compact) };

    if (/^(?:\d{4}-\d{2}-\d{2}|\d{1,2}\s+[A-Za-z]{3}\s+\d{4}|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4})$/.test(raw)) {
      const timestamp = Date.parse(raw);
      if (Number.isFinite(timestamp)) return { type:'number', value:timestamp };
    }
    const leadingNumber = raw.match(/^(?:SAR\s*)?([+-]?\d[\d,]*(?:\.\d+)?)(?:%|\s|$)/i);
    if (leadingNumber) return { type:'number', value:Number(leadingNumber[1].replace(/,/g, '')) };
    return { type:'text', value:raw };
  }

  function comparePayrollSortValues(left, right) {
    if (left.type === 'empty' && right.type === 'empty') return 0;
    if (left.type === 'empty') return 1;
    if (right.type === 'empty') return -1;
    if (left.type === 'number' && right.type === 'number') return left.value - right.value;
    return String(left.value).localeCompare(String(right.value), undefined, { numeric:true, sensitivity:'base' });
  }

  function applyPayrollTableSort(table, tableKey, columnIndex, direction) {
    const body = table.tBodies?.[0];
    if (!body) return;
    const rows = Array.from(body.rows).filter(row => row.cells.length > columnIndex && !row.querySelector('.table-empty'));
    if (rows.length < 2) return;
    rows.forEach((row, index) => { row.dataset.sortStableIndex = String(index); });
    rows.sort((a,b) => {
      const compared = comparePayrollSortValues(payrollSortValue(a.cells[columnIndex]), payrollSortValue(b.cells[columnIndex]));
      if (compared) return direction === 'desc' ? -compared : compared;
      return Number(a.dataset.sortStableIndex || 0) - Number(b.dataset.sortStableIndex || 0);
    });
    rows.forEach(row => body.appendChild(row));
    table.querySelectorAll('thead th').forEach((th, index) => {
      th.setAttribute('aria-sort', index === columnIndex ? (direction === 'desc' ? 'descending' : 'ascending') : 'none');
      th.classList.toggle('is-sorted', index === columnIndex);
      th.classList.toggle('is-desc', index === columnIndex && direction === 'desc');
    });
    payrollTableSortPrefs[tableKey] = { columnIndex, direction };
    persistPayrollTableSortPrefs();
  }

  function enhancePayrollSortableTables(root = pageRoot) {
    if (!root?.querySelectorAll) return;
    const routeKey = currentRoute();
    root.querySelectorAll('table.data-table').forEach((table, tableIndex) => {
      if (table.closest('.ui-v2-payroll-timesheet-workspace, .rental-timesheet-workspace, .timesheet-sheet')) return;
      const tableKey = `${state.workspace}:${routeKey}:${table.dataset.tableKey || tableIndex}`;
      const headers = Array.from(table.querySelectorAll('thead th'));
      headers.forEach((th, columnIndex) => {
        const label = String(th.textContent || '').trim();
        const ariaLabel = String(th.getAttribute('aria-label') || '').toLowerCase();
        if (!label || /action|open/.test(ariaLabel) || th.dataset.noSort === 'true') return;
        th.classList.add('ui-v2-payroll-sortable');
        th.tabIndex = 0;
        th.setAttribute('role', 'button');
        th.setAttribute('aria-sort', 'none');
        th.title = `Sort by ${label}`;
        const trigger = () => {
          const current = payrollTableSortPrefs[tableKey];
          const direction = current?.columnIndex === columnIndex && current.direction === 'asc' ? 'desc' : 'asc';
          applyPayrollTableSort(table, tableKey, columnIndex, direction);
        };
        th.addEventListener('click', trigger);
        th.addEventListener('keydown', event => {
          if (event.key !== 'Enter' && event.key !== ' ') return;
          event.preventDefault();
          trigger();
        });
      });
      const saved = payrollTableSortPrefs[tableKey];
      if (saved && Number.isInteger(saved.columnIndex) && saved.columnIndex >= 0 && saved.columnIndex < headers.length) {
        applyPayrollTableSort(table, tableKey, saved.columnIndex, saved.direction === 'desc' ? 'desc' : 'asc');
      }
    });
  }
  const appShell = document.getElementById('app');
  const sidebar = document.getElementById('sidebar');
  const shell = document.querySelector('.ui-v2-app-shell__workspace');
  const pageRoot = document.getElementById('pageRoot');
  const breadcrumbs = document.getElementById('breadcrumbs');
  const periodLabel = document.getElementById('periodLabel');
  const mobileScrim = document.getElementById('mobileScrim');
  const searchDialog = document.getElementById('searchDialog');
  const searchInput = document.getElementById('globalSearchInput');
  const commandResults = document.getElementById('commandResults');
  const drawer = document.getElementById('quickDrawer');
  const drawerScrim = document.getElementById('drawerScrim');
  const drawerTitle = document.getElementById('drawerTitle');
  const drawerBody = document.getElementById('drawerBody');
  const drawerSave = document.getElementById('drawerSave');
  const toastStack = document.getElementById('toastStack');


  /* Upgrade 3: semantic V2 primitive bridge.
     Legacy classes remain intact because they are also behavioral/production hooks in
     several screens. These additional classes make each shared primitive explicitly
     identifiable to the DocGen V2 design system while page migration proceeds. */
  function applyV2PrimitiveClasses(root = pageRoot) {
    if (!root || !root.querySelectorAll) return;
    const add = (selector, ...classes) => root.querySelectorAll(selector).forEach(el => el.classList.add(...classes));
    add('.page', 'ui-v2-payroll-page');
    add('.page-head', 'ui-v2-page-header', 'ui-v2-payroll-page-head');
    add('.page-head__copy', 'ui-v2-page-header__copy');
    add('.page-head__actions', 'ui-v2-page-header__actions');
    add('.eyebrow', 'ui-v2-eyebrow');
    add('.btn', 'ui-v2-button');
    add('.btn--primary', 'ui-v2-button--primary');
    add('.btn--secondary', 'ui-v2-button--secondary');
    add('.btn--ghost', 'ui-v2-button--quiet');
    add('.btn--danger', 'ui-v2-button--danger');
    add('.btn--sm', 'ui-v2-button--sm');
    add('.icon-btn', 'ui-v2-icon-button');
    add('.input', 'ui-v2-input');
    add('.select, .compact-select', 'ui-v2-select');
    add('.textarea', 'ui-v2-textarea');
    add('.summary-strip', 'ui-v2-payroll-summary-strip');
    add('.summary-item', 'ui-v2-payroll-metric');
    add('.panel, .data-panel', 'ui-v2-payroll-panel');
    add('.data-table', 'ui-v2-table', 'ui-v2-payroll-table');
    add('.table-primary', 'ui-v2-table__primary');
    add('.status', 'ui-v2-status');
    add('.status--success', 'ui-v2-status--success');
    add('.status--warning', 'ui-v2-status--warning');
    add('.status--danger', 'ui-v2-status--danger');
    add('.status--neutral', 'ui-v2-status--neutral');
    add('.table-empty', 'ui-v2-empty');
    add('.search-field, .table-toolbar__search', 'ui-v2-filter-bar__search');
    add('.profile-tabs, .tabs', 'ui-v2-tabs');
    add('.profile-crumb', 'ui-v2-payroll-profile-crumb');
    add('.entity-header', 'ui-v2-payroll-entity-header');
    add('.entity-header__identity', 'ui-v2-payroll-entity-header__identity');
    add('.entity-title-row', 'ui-v2-payroll-entity-title');
    add('.entity-avatar', 'ui-v2-payroll-entity-avatar');
    add('.entity-header__actions', 'ui-v2-payroll-entity-header__actions');
    add('.profile-facts', 'ui-v2-payroll-profile-facts');
    add('.profile-content', 'ui-v2-payroll-profile-content');
    add('.profile-grid', 'ui-v2-payroll-profile-grid');
    add('.profile-main-stack', 'ui-v2-payroll-profile-main');
    add('.profile-side-stack', 'ui-v2-payroll-profile-side');
    add('.attendance-kpis', 'ui-v2-payroll-attendance-kpis');
    add('.employee-document-list', 'ui-v2-payroll-employee-document-list');
    add('.employee-document-icon', 'ui-v2-payroll-employee-document-icon');
    root.querySelectorAll('.profile-tabs button, .tabs > button').forEach(el => {
      el.classList.add('ui-v2-tab');
      el.setAttribute('aria-selected', String(el.classList.contains('is-active')));
    });
  }

  /* Upgrade 6: Internal payroll execution surfaces.
     The production PRS workflows stay authoritative; this enhancer only binds the
     existing DOM to the canonical DocGen/Notes payroll V2 contracts. */
  function applyInternalExecutionV2Classes(root = pageRoot) {
    if (!root || !root.querySelectorAll) return;
    const add = (selector, ...classes) => root.querySelectorAll(selector).forEach(el => el.classList.add(...classes));

    const salaryPage = root.querySelector('.salary-setup-page');
    if (salaryPage) {
      salaryPage.classList.add('ui-v2-prs-internal-page','ui-v2-prs-internal-execution-page','ui-v2-payroll-salary-page');
      add('.salary-setup-summary','ui-v2-payroll-salary-summary-strip');
      add('.salary-setup-tabs','ui-v2-payroll-salary-tabs');
      add('.salary-config-panel','ui-v2-payroll-salary-config-panel');
      add('.table-toolbar--salary','ui-v2-payroll-salary-toolbar');
      add('.salary-type-filter','ui-v2-payroll-segmented');
      add('.component-kind','ui-v2-payroll-component-kind');
      add('.component-kind--earning','is-earning');
      add('.component-kind--deduction','is-deduction');
      add('.mapping-chip','ui-v2-payroll-mapping-chip');
      add('.salary-components-table','ui-v2-payroll-salary-components-table');
      add('.salary-config-footnote','ui-v2-payroll-salary-footnote');
      add('.structure-coverage','ui-v2-payroll-structure-coverage');
      add('.structure-progress','ui-v2-payroll-structure-progress');
      salaryPage.querySelectorAll('.table-toolbar--inner').forEach(el => el.classList.add('ui-v2-payroll-salary-structure-toolbar'));
      add('.setup-state','ui-v2-payroll-setup-state');
      add('.setup-state--ready','is-ready');
      add('.setup-state--needed','is-needed');
      add('.salary-structures-table','ui-v2-payroll-salary-structures-table');
      add('.salary-overtime-layout','ui-v2-payroll-salary-overtime-layout');
      add('.ot-policy-card','ui-v2-payroll-ot-policy-card');
      add('.ot-policy-card__head','ui-v2-payroll-ot-policy-card__head');
      add('.ot-formula','ui-v2-payroll-ot-formula');
      add('.ot-policy-card__meta','ui-v2-payroll-ot-policy-card__meta');
      add('.ot-policy-card__foot','ui-v2-payroll-ot-policy-card__foot');
      add('.salary-preview-stack','ui-v2-payroll-salary-preview-stack');
      add('.ot-preview-card','ui-v2-payroll-ot-preview-card');
      add('.ot-preview-form','ui-v2-payroll-ot-preview-form');
      add('.ot-preview-result','ui-v2-payroll-ot-preview-result');
      add('.money-input','ui-v2-payroll-money-input');
    }

    const payrollPage = root.querySelector('.payroll-run-page');
    if (payrollPage) {
      payrollPage.classList.add('ui-v2-prs-internal-page','ui-v2-prs-internal-execution-page','ui-v2-payroll-run-page');
      add('.payroll-title-line','ui-v2-payroll-run-title-status');
      add('.payroll-run-status','ui-v2-status');
      add('.payroll-run-status--success','ui-v2-status--success');
      add('.payroll-run-status--warning','ui-v2-status--warning');
      add('.payroll-run-status--neutral','ui-v2-status--neutral');
      add('.payroll-summary-strip','ui-v2-payroll-run-summary');
      add('.payroll-summary-strip .summary-item--strong','is-strong');
      add('.payroll-workflow-panel','ui-v2-payroll-run-lifecycle');
      add('.payroll-workflow','ui-v2-payroll-run-workflow');
      add('.payroll-view-switch','ui-v2-payroll-run-view-switch');
      add('.payroll-run-layout','ui-v2-payroll-run-layout');
      add('.payroll-register','ui-v2-payroll-run-register');
      add('.payroll-register .payroll-toolbar','ui-v2-payroll-run-toolbar');
      add('.payroll-register .table-meta','ui-v2-payroll-run-table-meta');
      add('.payroll-table-scroll','ui-v2-payroll-run-table-wrap');
      add('.payroll-table','ui-v2-payroll-run-table');
      payrollPage.querySelectorAll('.payroll-table th.num,.payroll-table td.num').forEach(el => el.classList.add('is-num'));
      payrollPage.querySelectorAll('.payroll-table tr.payroll-row--blocked').forEach(el => el.classList.add('is-blocked'));
      add('.payroll-gross','is-gross');
      add('.payroll-net','is-net');
      add('.payroll-mobile-detail','ui-v2-payroll-run-mobile-detail');
      add('.payroll-table-footer','ui-v2-payroll-run-table-foot');
      add('.payroll-side-stack','ui-v2-payroll-run-side');
      add('.payroll-input-list','ui-v2-payroll-run-inputs');
      add('.payroll-formula-stack','ui-v2-payroll-run-formulas');
      add('.payroll-run-meta','ui-v2-payroll-run-meta');
      add('.payroll-blocker-banner','ui-v2-payroll-run-alert','is-danger');
      add('.payroll-input-warning','ui-v2-payroll-run-alert');
      add('.entity-link','ui-v2-payroll-entity-link');
      add('.entity-link--stack','is-stack');
      add('.review-layout','ui-v2-payroll-review-layout');
      add('.review-main-stack','ui-v2-payroll-review-main');
      add('.review-side-stack','ui-v2-payroll-review-side');
      add('.review-status-panel','ui-v2-payroll-review-status');
      add('.review-exceptions-panel','ui-v2-payroll-review-exceptions');
      add('.review-filterbar','ui-v2-payroll-review-filters');
      add('.review-issue-list','ui-v2-payroll-review-issues');
      payrollPage.querySelectorAll('.review-issue').forEach(el => {
        el.tagName === 'ARTICLE' || el.setAttribute('data-ui-v2-review-item','true');
        if (el.classList.contains('review-issue--critical')) el.classList.add('is-critical');
        if (el.classList.contains('review-issue--warning')) el.classList.add('is-warning');
      });
      add('.review-clear-state','ui-v2-payroll-review-clear');
      add('.review-table','ui-v2-payroll-review-table');
      payrollPage.querySelectorAll('.review-table th.num,.review-table td.num').forEach(el => el.classList.add('is-num'));
      add('.review-clear-badge','ui-v2-payroll-review-clear-badge');
      add('.review-comparison-metrics','ui-v2-payroll-review-comparison');
      add('.review-comparison-empty','ui-v2-payroll-review-no-comparison');
      add('.review-checklist','ui-v2-payroll-review-checklist');
      add('.review-check-foot','ui-v2-payroll-review-check-foot');
      add('.review-history','ui-v2-payroll-run-history');
      add('.review-note-panel','ui-v2-payroll-review-note');
      add('.review-decision-panel','ui-v2-payroll-review-decision');
    }

    if (state.workspace === 'internal') {
      const adjustmentPage = root.querySelector('.adjustments-page');
      if (adjustmentPage) {
        adjustmentPage.classList.add('ui-v2-prs-internal-page','ui-v2-prs-internal-execution-page','ui-v2-payroll-adjustments-page');
        add('.adjustment-summary-strip','ui-v2-payroll-adjustment-summary');
        add('.adjustment-tabs','ui-v2-payroll-adjustment-tabs');
        add('.adjustment-ledger-panel','ui-v2-payroll-adjustment-register');
        add('.adjustment-filterbar','ui-v2-payroll-register__toolbar','ui-v2-prs-adjustment-toolbar');
        add('.adjustment-ledger-table','ui-v2-payroll-adjustment-table');
        add('.adjustment-impact','ui-v2-payroll-adjustment-impact');
        add('.adjustment-impact--earning','is-earning');
        add('.adjustment-impact--deduction','is-deduction');
        add('.adjustment-balance-layout','ui-v2-payroll-adjustment-balance-layout');
        add('.adjustment-balance-table','ui-v2-payroll-advance-balance-table');
        add('.adjustment-balance-side','ui-v2-payroll-adjustment-balance-side');
        add('.entity-link','ui-v2-payroll-adjustment-entity');
      }

      const paymentsPage = root.querySelector('.payments-page');
      if (paymentsPage) {
        paymentsPage.classList.add('ui-v2-prs-internal-page','ui-v2-prs-internal-execution-page','ui-v2-payroll-payments-page');
        add('.payment-workspace-switch','ui-v2-payroll-payment-tabs');
        add('.payment-summary-strip','ui-v2-payroll-payment-summary');
        add('.payment-empty-hero','ui-v2-payroll-payment-empty');
        add('.payment-empty-hero__icon','ui-v2-payroll-payment-empty__icon');
        paymentsPage.querySelectorAll('.panel--flush').forEach(el => el.classList.add('ui-v2-payroll-payment-register'));
        add('.payment-head-actions','ui-v2-payroll-payment-head-actions');
        add('.payment-batch-select','ui-v2-payroll-payment-batch-select');
        paymentsPage.querySelectorAll('.toolbar--table').forEach(el => el.classList.add('ui-v2-payroll-payment-toolbar'));
        add('.payment-table','ui-v2-payroll-payment-table');
        add('.bank-cell','ui-v2-payroll-payment-bank');
        add('.mono-cell','ui-v2-payroll-payment-reference');
        add('.table-secondary--attention','ui-v2-payroll-payment-failure');
        add('.table-row-actions','ui-v2-payroll-payment-row-actions');
      }
    }

    const bankPage = root.querySelector('.bank-export-page');
    if (bankPage) {
      bankPage.classList.add('ui-v2-prs-internal-page','ui-v2-prs-internal-execution-page','ui-v2-payroll-bank-export-page');
      add('.bank-export-tabs','ui-v2-payroll-bank-channel-tabs','ui-v2-prs-bank-channel-tabs');
      add('.bank-workflow-tabs','ui-v2-payroll-bank-subnav');
      add('.bank-transfer-toolbar','ui-v2-payroll-bank-toolbar');
      add('.bank-template-picker select','ui-v2-payroll-bank-template-select');
      add('.bank-payment-register','ui-v2-payroll-bank-table');
      add('.bank-cell','ui-v2-payroll-bank-account');
      add('.mono-cell','ui-v2-payroll-bank-mono');
      add('.payment-head-actions','ui-v2-payroll-bank-head-actions');
      add('.readiness','ui-v2-status');
      add('.readiness--ready','ui-v2-status--success');
      add('.readiness--danger','ui-v2-status--danger');
      bankPage.querySelectorAll('.data-panel').forEach(el => el.classList.add('ui-v2-payroll-bank-register'));
      add('.payment-summary-strip','ui-v2-payroll-bank-summary');
    }

    const wpsPage = root.querySelector('.wps-page');
    if (wpsPage) {
      wpsPage.classList.add('ui-v2-prs-internal-page','ui-v2-prs-internal-execution-page','ui-v2-payroll-bank-export-page');
      add('.wps-tabs','ui-v2-payroll-bank-subnav');
      add('.wps-summary-strip','ui-v2-payroll-bank-summary');
      add('.toolbar--table','ui-v2-payroll-bank-toolbar');
      add('.wps-table','ui-v2-payroll-bank-table','is-wps');
      add('.bank-cell','ui-v2-payroll-bank-account');
      add('.mono-cell','ui-v2-payroll-bank-mono');
      add('.payment-head-actions','ui-v2-payroll-bank-head-actions');
      add('.readiness','ui-v2-status');
      add('.readiness--ready','ui-v2-status--success');
      add('.readiness--danger','ui-v2-status--danger');
      wpsPage.querySelectorAll('.panel--flush').forEach(el => el.classList.add('ui-v2-payroll-bank-register'));
    }

    /* Shared execution drawer content. The outer quick drawer remains the PRS shell
       so existing save/cancel behavior and focus management stay untouched. */
    add('.salary-structure-editor','ui-v2-payroll-salary-structure-editor');
    add('.salary-editor-row','ui-v2-payroll-salary-editor-row');
    add('.drawer-calculation-preview','ui-v2-payroll-drawer-preview');
    add('.payroll-detail-hero','ui-v2-payroll-run-detail-hero');
    add('.payroll-detail-alert','ui-v2-payroll-run-detail-alert');
    add('.payroll-detail-alert--danger','is-danger');
    add('.payroll-detail-lines','ui-v2-payroll-run-detail-section');
    add('.payroll-detail-total','ui-v2-payroll-run-detail-total');
    add('.adjustment-detail-hero','ui-v2-payroll-adjustment-detail-hero');
    add('.adjustment-detail-grid','ui-v2-payroll-adjustment-detail-grid');
    add('.adjustment-drawer-intro','ui-v2-payroll-adjustment-drawer-intro');
    add('.bank-detail-grid','ui-v2-payroll-bank-detail-grid');
    add('.bank-issue-list','ui-v2-payroll-bank-issue-list');
  }

  /* 1.0.25: canonical Payroll control normalization.
     Every operational select is tagged once after render and legacy compact
     classes are removed from business filters. Only day/page-size/table editors
     remain dense. Standalone labelled pickers are normalized as selects without
     being converted into row toolbars, so flex-basis can never inflate control height. */
  function applyPayrollControlClasses(root = pageRoot) {
    if (!root || !root.querySelectorAll) return;

    const denseSelector = [
      '.ui-v2-payroll-timesheet-command-strip select',
      '.ui-v2-prs-timesheet-day-select select',
      '.ui-v2-payroll-timesheet-pagination__size select',
      'select.table-select'
    ].join(',');

    root.querySelectorAll(denseSelector).forEach(select => {
      select.classList.remove('ui-v2-payroll-operational-select');
      select.classList.add('ui-v2-select', 'ui-v2-payroll-dense-select');
    });

    const toolbarSelector = [
      '.ui-v2-payroll-register__toolbar',
      '.table-toolbar',
      '.toolbar--table',
      '.ui-v2-filter-bar',
      '.ui-v2-payroll-rental-filterbar',
      '.rental-filterbar',
      '.assignment-filterbar',
      '.adjustment-filterbar',
      '.payment-supplier-toolbar',
      '.payment-register-toolbar',
      '.bank-transfer-toolbar',
      '.wps-toolbar',
      '.document-toolbar',
      '.report-filterbar',
      '.review-filterbar',
      '.employee-filter-row',
      '.ui-v2-payroll-management-audit-toolbar',
      '.ui-v2-payroll-advanced-filters',
      '[data-advanced-filter-panel]',
      '.payment-head-actions',
      '.ui-v2-payroll-timesheet-toolbar',
      '.payroll-toolbar'
    ].join(',');

    const markOperationalSelect = (select) => {
      if (!select || select.matches(denseSelector) || select.closest('table, .ui-v2-compact-select')) return;
      select.classList.remove('compact-select', 'ui-v2-payroll-compact-select', 'ui-v2-payroll-dense-select');
      select.classList.add('ui-v2-select', 'ui-v2-payroll-operational-select');
    };

    root.querySelectorAll(toolbarSelector).forEach(container => {
      if (container.closest('.document-preview-toolbar, .receipt-preview-toolbar, .onboarding-stage-toolbar')) return;
      container.classList.add('ui-v2-payroll-control-toolbar');
      container.querySelectorAll('select:not([multiple]):not([size])').forEach(select => {
        markOperationalSelect(select);
        const labelled = select.closest('.timesheet-filter, .timesheet-filter--compact');
        if (labelled && container.contains(labelled)) labelled.classList.add('ui-v2-payroll-operational-filter');
      });
    });

    /* Standalone labelled selectors are controls, not toolbars. Keeping the
       parent out of ui-v2-payroll-control-toolbar prevents row flex sizing from
       becoming vertical flex sizing on column layouts (the Bank/WPS template
       picker regression that produced a ~220px-tall select). */
    root.querySelectorAll('.bank-template-picker select:not([multiple]):not([size])').forEach(markOperationalSelect);
  }


  /* Upgrade 7: Rental manpower operations surfaces.
     This enhancer is presentation-only. Permanent worker masters, supplier/project
     records, effective-dated assignments and all API actions keep their PRS hooks. */
  function applyRentalOperationsV2Classes(root = pageRoot) {
    if (!root || !root.querySelectorAll) return;
    const add = (selector, ...classes) => root.querySelectorAll(selector).forEach(el => el.classList.add(...classes));
    const markPage = (selector, ...classes) => {
      const page = root.querySelector(selector);
      if (page) page.classList.add('ui-v2-prs-rental-page', ...classes);
      return page;
    };

    const overview = markPage('.rental-control-overview', 'ui-v2-prs-rental-overview');
    if (overview) {
      add('.rental-flow-strip','ui-v2-prs-rental-flow');
      add('.rental-control-projects','ui-v2-prs-rental-control-projects');
      add('.rental-control-table','ui-v2-prs-rental-control-table');
      add('.entity-link--stack','ui-v2-payroll-table-entity');
      add('.table-empty','ui-v2-payroll-table-empty');
    }

    const workforce = markPage('.rental-workforce-page', 'ui-v2-payroll-rental-workforce');
    if (workforce) {
      add('.rental-summary-strip','ui-v2-prs-rental-summary','ui-v2-payroll-assignment-summary');
      add('.rental-directory-panel','ui-v2-prs-rental-directory','ui-v2-payroll-register');
      add('.rental-filterbar','ui-v2-payroll-rental-filterbar');
      add('.rental-status-tabs','ui-v2-prs-rental-status-tabs');
      add('.rental-table-wrap','ui-v2-payroll-table-wrap');
      add('.rental-worker-table','ui-v2-payroll-rental-worker-table');
      add('.entity-link--stack','ui-v2-payroll-table-entity');
      add('.table-empty','ui-v2-payroll-table-empty');
      add('.rental-workforce-footer-grid','ui-v2-prs-rental-footer-grid');
      add('.rental-rule-list','ui-v2-payroll-rental-rules');
    }

    const assignments = markPage('.rental-assignments-page', 'ui-v2-payroll-rental-assignments');
    if (assignments) {
      add('.assignment-summary-strip','ui-v2-payroll-assignment-summary');
      add('.assignment-workspace-tabs','ui-v2-payroll-assignment-tabs');
      add('.assignment-activity-panel','ui-v2-prs-rental-directory');
      add('.assignment-filterbar','ui-v2-prs-assignment-filterbar');
      add('.assignment-filterbar--compact','is-compact');
      add('.assignment-activity-table-wrap','ui-v2-payroll-table-wrap');
      add('.assignment-activity-table,.assignment-deployment-table','ui-v2-payroll-rental-worker-table');
      add('.entity-link--stack','ui-v2-payroll-table-entity');
      add('.table-empty','ui-v2-payroll-table-empty');
      add('.assignment-footer-grid','ui-v2-prs-rental-footer-grid');
      add('.assignment-integrity-list','ui-v2-payroll-rental-integrity');
      add('.rental-rule-list','ui-v2-payroll-rental-rules');
    }

    const projects = markPage('.projects-page', 'ui-v2-prs-rental-directory-page');
    if (projects) {
      add('.data-panel','ui-v2-prs-rental-directory-register','ui-v2-payroll-register');
      add('.table-toolbar','ui-v2-prs-rental-directory-toolbar');
      add('.project-table','ui-v2-prs-rental-directory-table');
      add('.entity-link--stack','ui-v2-payroll-table-entity');
      add('.table-empty','ui-v2-payroll-table-empty');
    }

    const suppliers = markPage('.supplier-directory', 'ui-v2-prs-rental-directory-page');
    if (suppliers) {
      add('.data-panel','ui-v2-prs-rental-directory-register','ui-v2-payroll-register');
      add('.table-toolbar','ui-v2-prs-rental-directory-toolbar');
      add('.supplier-table','ui-v2-prs-rental-directory-table');
      add('.entity-link--stack','ui-v2-payroll-table-entity');
      add('.table-empty','ui-v2-payroll-table-empty');
    }

    const projectProfile = markPage('.project-profile', 'ui-v2-prs-rental-profile','ui-v2-prs-project-profile');
    if (projectProfile) {
      add('.entity-link--stack','ui-v2-payroll-table-entity');
      add('.rental-worker-actions-list','ui-v2-payroll-info-stack');
      add('.table-empty','ui-v2-payroll-table-empty');
    }

    const supplierProfile = markPage('.supplier-profile', 'ui-v2-prs-rental-profile','ui-v2-prs-supplier-profile');
    if (supplierProfile) {
      add('.entity-link--stack','ui-v2-payroll-table-entity');
      add('.table-empty','ui-v2-payroll-table-empty');
    }

    const workerProfile = markPage('.rental-worker-profile-page', 'ui-v2-prs-rental-profile','ui-v2-prs-worker-profile');
    if (workerProfile) {
      add('.rental-assignment-timeline','ui-v2-payroll-rental-timeline');
      add('.rental-assignment-event__rail','ui-v2-payroll-rental-timeline__rail');
      add('.rental-assignment-event__top','ui-v2-payroll-rental-timeline__head');
      add('.mini-entity','ui-v2-payroll-rental-link-card');
      add('.entity-link--stack','ui-v2-payroll-table-entity');
      add('.table-empty','ui-v2-payroll-table-empty');
    }

    const onboarding = markPage('.rental-onboarding-page', 'ui-v2-prs-rental-onboarding');
    if (onboarding) {
      add('.onboarding-table-wrap','ui-v2-payroll-table-wrap');
      add('.onboarding-table','ui-v2-payroll-rental-worker-table');
      add('.table-empty','ui-v2-payroll-table-empty');
    }

    /* Rental create/edit/assignment drawers are dynamic; bind them whenever the
       observer sees drawer content without altering existing save/cancel hooks. */
    const rentalDrawer = root.querySelector('[data-rental-assignment-form], .rental-assignment-form, .rental-worker-form, .supplier-form, .project-form, .assignment-preview');
    if (rentalDrawer) {
      const host = root === drawerBody ? root : rentalDrawer.closest('.drawer-body') || root;
      host.classList?.add('ui-v2-prs-rental-assignment-editor');
    }
  }

  /* Upgrade 9: Rental settlement, supplier payable and payment evidence surfaces. */
  function applyRentalFinancialV2Classes(root = pageRoot) {
    if (!root || !root.querySelectorAll) return;
    const add = (selector, ...classes) => root.querySelectorAll(selector).forEach(el => el.classList.add(...classes));
    const settlementPage=root.querySelector('.rental-settlement-page');
    if (settlementPage) {
      settlementPage.classList.add('ui-v2-prs-rental-page','ui-v2-prs-rental-finance-page','ui-v2-payroll-rental-settlements');
      add('.settlement-nav-row','ui-v2-payroll-rental-settlement-nav');
      add('.settlement-tabs','ui-v2-payroll-view-tabs');
      add('.settlement-view-toggle','ui-v2-payroll-view-tabs','is-compact');
      add('.settlement-control-grid','ui-v2-payroll-rental-settlement-control-grid');
      add('.settlement-lifecycle-card','ui-v2-payroll-panel');
      add('.settlement-workflow','ui-v2-payroll-rental-settlement-workflow');
      add('.settlement-readiness','ui-v2-payroll-rental-settlement-readiness');
      add('.settlement-actions','ui-v2-payroll-rental-settlement-actions');
      add('.settlement-summary-grid','ui-v2-payroll-rental-settlement-summary-grid');
      add('.settlement-register','ui-v2-payroll-register');
      add('.settlement-table,.settlement-project-table','ui-v2-payroll-rental-settlement-table');
      add('.settlement-supplier-grid','ui-v2-payroll-rental-settlement-supplier-grid');
      add('.settlement-supplier-card','ui-v2-payroll-rental-settlement-supplier-card');
      add('.supplier-settlement-hero','ui-v2-payroll-rental-supplier-settlement-hero');
      add('.source-banner,.source-note','ui-v2-payroll-source-note');
    }
    const paymentsPage=root.querySelector('.payments-page');
    if (paymentsPage && state.workspace==='rental') {
      paymentsPage.classList.add('ui-v2-prs-rental-page','ui-v2-prs-rental-finance-page','ui-v2-payroll-rental-supplier-payments-page');
      add('.supplier-payment-summary','ui-v2-payroll-rental-payment-summary');
      add('.payment-workspace-switch','ui-v2-payroll-adjustment-tabs','ui-v2-payroll-rental-payment-tabs');
      add('.supplier-payable-table,.supplier-payment-table','ui-v2-payroll-rental-payment-table');
      add('.table-row-actions','ui-v2-payroll-rental-payment-row-actions');
      add('.mono-cell','ui-v2-payroll-rental-payment-reference');
      add('.receipt-workspace','ui-v2-prs-rental-receipt-workspace');
      add('.source-note','ui-v2-payroll-source-note');
    }
    add('.settlement-drawer-summary','ui-v2-payroll-rental-settlement-drawer-summary');
    add('.supplier-payment-scope','ui-v2-payroll-rental-payment-mini-summary');
    add('.settlement-segment-list','ui-v2-prs-settlement-segment-list');
    add('.settlement-segment','ui-v2-prs-settlement-segment');
    if (root === drawerBody) {
      const isSettlement=!!root.querySelector('.ui-v2-payroll-rental-settlement-drawer-summary');
      const isSupplierPayment=state.drawerType==='supplier-payment' || state.drawerType==='supplier-payment-result' || state.drawerType==='supplier-payment-readonly';
      drawer.classList.toggle('ui-v2-prs-rental-settlement-drawer',isSettlement);
      drawer.classList.toggle('ui-v2-prs-rental-payment-drawer',isSupplierPayment);
    }
  }

  /* Upgrade 10: Documents, Reports, Management/Admin and Settings.
     These bindings connect PRS's existing Django-backed markup to the canonical
     DocGen/Notes payroll V2 contracts. No backend workflow or permission logic
     is duplicated in the browser. */
  function applyRecordsManagementV2Classes(root = pageRoot) {
    if (!root || !root.querySelectorAll) return;
    const add = (selector, ...classes) => root.querySelectorAll(selector).forEach(el => el.classList.add(...classes));

    const documentsPage = root.querySelector('.documents-page');
    if (documentsPage) {
      documentsPage.classList.add('ui-v2-prs-records-page','ui-v2-payroll-documents-page');
      if (state.workspace === 'internal') documentsPage.classList.add('ui-v2-prs-internal-page');
      if (state.workspace === 'rental') documentsPage.classList.add('ui-v2-payroll-rental-documents-page');
      add('.document-kpis','ui-v2-payroll-document-kpis');
      add('.document-tabs','ui-v2-payroll-document-tabs');
      add('.document-toolbar','ui-v2-payroll-document-toolbar');
      add('.document-workspace','ui-v2-payroll-document-workspace');
      add('.document-list-panel','ui-v2-payroll-document-list-panel');
      add('.document-list-head','ui-v2-prs-document-list-head');
      add('.document-list','ui-v2-payroll-document-list');
      add('.document-list-item__icon','ui-v2-payroll-document-type-code');
      add('.document-list-item__body','ui-v2-payroll-document-list-copy');
      add('.document-preview-panel','ui-v2-payroll-document-preview-panel');
      add('.document-preview-toolbar','ui-v2-payroll-document-preview-toolbar');
      add('.document-preview-stage','ui-v2-payroll-document-preview-stage');
      add('.document-info-strip','ui-v2-payroll-document-info-strip');
      add('.document-empty-preview','ui-v2-payroll-document-preview-empty');
      add('.document-paper','ui-v2-payroll-document-paper');
      add('.document-brand-header','ui-v2-payroll-paper-brand');
      add('.document-brand-mark','ui-v2-payroll-paper-brandmark');
      add('.document-title-block','ui-v2-payroll-paper-title');
      add('.document-meta-grid','ui-v2-payroll-paper-meta');
      add('.document-summary-grid','ui-v2-prs-document-summary-grid');
      add('.document-source-note','ui-v2-payroll-report-source-note');
      add('.table-empty','ui-v2-payroll-document-empty');
    }

    const reportPage = root.querySelector('.report-page');
    if (reportPage) {
      reportPage.classList.add('ui-v2-prs-records-page','ui-v2-payroll-reports-page');
      if (state.workspace === 'internal') reportPage.classList.add('ui-v2-prs-internal-page');
      if (state.workspace === 'management') reportPage.classList.add('ui-v2-payroll-management-reports-page');
      add('.report-layout','ui-v2-payroll-report-layout');
      add('.report-catalog','ui-v2-payroll-report-catalog');
      add('.report-catalog__head','ui-v2-prs-report-catalog-head');
      add('.report-catalog__item > span:first-child','ui-v2-payroll-report-code');
      add('.report-viewer','ui-v2-payroll-report-viewer');
      add('.report-viewer__head','ui-v2-payroll-report-viewer-head');
      add('.report-live-chip','ui-v2-payroll-report-source-chip');
      add('.report-filterbar','ui-v2-payroll-report-filterbar');
      add('.report-kpis','ui-v2-payroll-report-kpis');
      add('.report-table-wrap','ui-v2-payroll-report-table-wrap');
      add('.report-table','ui-v2-payroll-report-table');
      reportPage.querySelectorAll('.report-table .num').forEach(el => el.classList.add('is-number'));
      add('.report-source-note','ui-v2-payroll-report-source-note');
      add('.table-empty','ui-v2-payroll-report-empty');
    }

    const managementOverview = root.querySelector('.management-overview');
    if (managementOverview) {
      managementOverview.classList.add('ui-v2-payroll-management-page');
      add('.management-boundary-banner','ui-v2-payroll-management-boundary');
      add('.management-workforce-cards','ui-v2-payroll-management-workforces');
      add('.management-workforce-card','ui-v2-payroll-management-workforce-card');
      add('.management-comparison-card','ui-v2-payroll-management-comparison');
      add('.management-control-grid','ui-v2-payroll-management-control-grid');
      add('.management-approval-mini','ui-v2-payroll-management-approval-mini');
      add('.management-access-summary','ui-v2-payroll-management-access-summary');
      add('.management-access-badges','ui-v2-payroll-management-access-badges');
      add('.text-link','ui-v2-payroll-text-link');
      add('.empty-inline','ui-v2-payroll-management-empty');
    }

    const managementCost = root.querySelector('.management-cost-page');
    if (managementCost) {
      managementCost.classList.add('ui-v2-payroll-management-cost-page');
      add('.data-panel','ui-v2-payroll-management-cost-table-panel');
      add('.table-scroll','ui-v2-payroll-table-scroll');
      add('.data-table','ui-v2-payroll-management-table');
      managementCost.querySelectorAll('.data-table .num').forEach(el => el.classList.add('is-number'));
      add('.management-cost-rules','ui-v2-payroll-management-rules');
      add('.management-not-comparable','ui-v2-payroll-management-not-comparable');
    }

    const managementApprovals = root.querySelector('.management-approval-page');
    if (managementApprovals) {
      managementApprovals.classList.add('ui-v2-payroll-management-approval-page');
      add('.summary-strip','ui-v2-payroll-management-approval-summary');
      managementApprovals.querySelectorAll('.summary-item--attention').forEach(el => el.classList.add('is-attention'));
      add('.management-approval-filters','ui-v2-payroll-management-approval-filters');
      add('.management-approval-list','ui-v2-payroll-management-approval-list');
      add('.management-approval-item','ui-v2-payroll-management-approval-item');
      add('.table-empty','ui-v2-payroll-management-empty');
    }

    const managementAudit = root.querySelector('.management-audit-page');
    if (managementAudit) {
      managementAudit.classList.add('ui-v2-payroll-management-audit-page');
      add('.table-toolbar','ui-v2-payroll-management-audit-toolbar');
      add('.management-audit-list','ui-v2-payroll-management-audit-list');
      add('.table-empty','ui-v2-payroll-management-empty');
    }

    const accessPage = root.querySelector('.access-roles-page');
    if (accessPage) {
      accessPage.classList.add('ui-v2-payroll-management-access-page');
      add('.management-boundary-banner','ui-v2-payroll-management-boundary');
      add('.table-scroll','ui-v2-payroll-table-scroll');
      add('.role-matrix-table','ui-v2-payroll-management-role-table','ui-v2-payroll-management-table');
      add('.management-cost-rules','ui-v2-payroll-management-rules');
      add('.source-note','ui-v2-payroll-management-note');
    }

    const settingsPage = root.querySelector('.settings-page');
    if (settingsPage) {
      settingsPage.classList.add('ui-v2-settings-page','ui-v2-prs-settings-page');
      add('.settings-layout','ui-v2-prs-settings-layout');
      add('.settings-nav','ui-v2-prs-settings-nav');
      add('.settings-main','ui-v2-prs-settings-main');
      add('.settings-panel','ui-v2-prs-settings-panel');
      add('.settings-panel__head','ui-v2-prs-settings-panel-head');
      add('.settings-list','ui-v2-setting-list','ui-v2-prs-setting-list');
      add('.settings-summary-row','ui-v2-setting-row','ui-v2-prs-setting-row');
      add('.settings-field','ui-v2-setting-row','ui-v2-prs-setting-field');
      add('.settings-policy-note','ui-v2-admin-note','ui-v2-prs-settings-note');
    }

    if (root === drawerBody && state.drawerType === 'document-generate') {
      drawer.classList.add('ui-v2-payroll-document-drawer');
      root.classList.add('ui-v2-payroll-document-form');
    } else if (root === drawerBody) {
      drawer.classList.remove('ui-v2-payroll-document-drawer');
      root.classList.remove('ui-v2-payroll-document-form');
    }
  }

  const primitiveObserver = new MutationObserver(() => {
    applyV2PrimitiveClasses(drawerBody);
    applyInternalExecutionV2Classes(drawerBody);
    applyRentalOperationsV2Classes(drawerBody);
    applyRentalFinancialV2Classes(drawerBody);
    applyRecordsManagementV2Classes(drawerBody);
    applyPayrollControlClasses(drawerBody);
    applyPayrollRequiredFields(drawerBody, state.drawerType);
  });
  if (drawerBody) {
    primitiveObserver.observe(drawerBody, { childList: true, subtree: true });
    drawerBody.addEventListener('change', () => applyPayrollRequiredFields(drawerBody, state.drawerType));
  }

  const rentalTimesheetCache = {};
  const rentalTimesheetStatusCache = {};
  const rentalOvertimeCache = {};



  const systemSettings = {
    general: {
      companyName: settingsBootstrap.companyName || serverAccess.company_name || '',
      legalName: settingsBootstrap.legalName || '',
      currency: settingsBootstrap.currency || 'SAR',
      timezone: settingsBootstrap.timezone || 'Asia/Riyadh',
      country: settingsBootstrap.country || 'SA',
      commercialRegistration: settingsBootstrap.commercialRegistration || '',
      vatNumber: settingsBootstrap.vatNumber || '',
      documentAddress: settingsBootstrap.documentAddress || '',
      documentEmail: settingsBootstrap.documentEmail || '',
      documentPhone: settingsBootstrap.documentPhone || '',
      website: settingsBootstrap.website || '',
      documentBrandingMode: settingsBootstrap.documentBrandingMode || settingsBootstrap.branding?.mode || 'standard',
      branding: settingsBootstrap.branding || {mode:'standard',logo:{configured:false,url:''},letterhead:{configured:false,url:''},watermark:{configured:false,url:''}},
      today: companyTodayIso
    },
    canManage: Boolean(settingsBootstrap.canManage)
  };

  const storedWorkspace = localStorage.getItem('payroll-ui-workspace') || 'internal';
  const storedInternalWorkspacePeriod = localStorage.getItem('payroll-ui-internal-period') || defaultInternalPeriod;
  const storedRentalWorkspacePeriod = localStorage.getItem('payroll-ui-rental-period') || defaultInternalPeriod;
  const storedManagementWorkspacePeriod = localStorage.getItem('payroll-ui-management-period') || defaultInternalPeriod;
  const accessRoles = serverAccess.role_matrix;
  const serverWorkspaces = Array.isArray(serverAccess.workspaces) ? serverAccess.workspaces : [];
  const urlWorkspace = new URLSearchParams(location.search).get('workspace');
  const serverInitialWorkspace = typeof serverAccess.initial_workspace === 'string' ? serverAccess.initial_workspace : '';
  const requestedWorkspace = serverWorkspaces.includes(serverInitialWorkspace)
    ? serverInitialWorkspace
    : (serverWorkspaces.includes(urlWorkspace) ? urlWorkspace : '');
  const initialWorkspace = requestedWorkspace
    || (serverWorkspaces.includes(storedWorkspace) ? storedWorkspace : '')
    || (serverWorkspaces.includes('internal') ? 'internal' : (serverWorkspaces[0] || 'management'));
  const initialPeriod = initialWorkspace === 'rental' ? storedRentalWorkspacePeriod : initialWorkspace === 'management' ? storedManagementWorkspacePeriod : storedInternalWorkspacePeriod;

  const rentalProjectCandidates = Array.isArray(rentalMaster.projects) ? rentalMaster.projects : [];
  function preferredRentalProjectId(projects = rentalProjectCandidates, storedProjectId = '') {
    const stored = projects.find(item => item?.id === storedProjectId && !item.deleted && !item.archived && item.status !== 'Completed');
    if (stored) return stored.id;
    const eligible = projects.filter(item => item && !item.deleted && !item.archived && item.status !== 'Completed');
    const pool = eligible.length ? eligible : projects.filter(item => item && !item.deleted);
    return [...pool].sort((left,right) => {
      const workers = Number(right.rentalWorkers || 0) - Number(left.rentalWorkers || 0);
      if (workers) return workers;
      return String(left.code || left.name || '').localeCompare(String(right.code || right.name || ''));
    })[0]?.id || '';
  }
  const storedRentalTimesheetProject = localStorage.getItem('payroll-ui-rental-timesheet-project') || '';
  const storedRentalSettlementProject = localStorage.getItem('payroll-ui-rental-settlement-project') || '';
  const initialRentalTimesheetProject = preferredRentalProjectId(rentalProjectCandidates, storedRentalTimesheetProject);
  const initialRentalSettlementProject = preferredRentalProjectId(rentalProjectCandidates, storedRentalSettlementProject || storedRentalTimesheetProject);

  const state = {
    workspace: initialWorkspace,
    period: initialPeriod,
    accessRole: serverAccess.role,
    managementCostMode: localStorage.getItem('payroll-ui-management-cost-mode') || 'latest',
    managementApprovalFilter: 'All',
    managementAuditSearch: '',
    managementAuditType: 'All activity',
    sidebarCollapsed: localStorage.getItem('payroll-ui-sidebar') === 'collapsed',
    projectSearch: '',
    projectStatus: 'All',
    projectFiltersOpen: false,
    projectClient: 'All clients',
    projectManager: 'All managers',
    projectSupplier: 'All suppliers',
    projectWorkerSearch: '',
    projectWorkerStatus: 'All statuses',
    projectWorkerSupplier: 'All suppliers',
    projectWorkerTrade: 'All trades',
    projectWorkerFiltersOpen: false,
    projectTab: 'overview',
    branchSearch: '',
    branchStatus: 'Active',
    branchSort: localStorage.getItem('payroll-ui-branch-sort') || 'code-asc',
    branchTab: 'overview',
    branchSelectedId: '',
    departmentSearch: '',
    departmentStatus: 'Active',
    departmentSort: localStorage.getItem('payroll-ui-department-sort') || 'code-asc',
    departmentTab: 'overview',
    departmentSelectedId: '',
    supplierSearch: '',
    supplierStatus: 'All',
    supplierFiltersOpen: false,
    supplierProject: 'All projects',
    supplierPaymentTerm: 'All payment terms',
    supplierWorkforce: 'Any workforce',
    supplierOutstanding: 'Any balance',
    supplierWorkerSearch: '',
    supplierWorkerStatus: 'All statuses',
    supplierWorkerProject: 'All projects',
    supplierWorkerTrade: 'All trades',
    supplierWorkerFiltersOpen: false,
    supplierTab: 'overview',
    employeeSearch: '',
    employeeStatus: 'All',
    employeeBranch: 'All branches',
    employeeDepartment: 'All departments',
    employeeProject: 'All projects',
    employeeWps: 'All',
    employeeTab: 'overview',
    rentalSearch: '',
    rentalStatus: 'All',
    rentalSupplier: 'All suppliers',
    rentalProject: 'All projects',
    rentalTrade: 'All trades',
    rentalRateType: 'All rate types',
    rentalView: 'directory',
    rentalWorkerTab: 'overview',
    rentalAssignmentTab: 'activity',
    rentalAssignmentSearch: '',
    rentalAssignmentSupplier: 'All suppliers',
    rentalAssignmentProject: 'All projects',
    rentalAssignmentType: 'All activity',
    rentalOnboarding: { sourceText:'', rows:[], defaultSupplierId:'', lastImport:null },
    inlineRentalDraft: null,
    inlineInternalDraft: null,
    rentalAssignments: { ...(rentalMaster.assignmentsByWorker || {}) },
    rentalAdjustments: {},
    internalAdjustments: payrollBootstrap.adjustmentsByEmployee || {},
    adjustmentView: 'register',
    adjustmentSearch: '',
    adjustmentWorkforce: 'All',
    adjustmentType: 'All',
    adjustmentStatus: 'All',
    adjustmentProject: 'All projects',
    adjustmentSupplier: 'All suppliers',
    salarySetupTab: 'components',
    salaryComponentSearch: '',
    salaryComponentType: 'All',
    salaryComponentStatus: 'Active',
    overtimePolicyStatus: 'Active',
    salaryStructureSearch: '',
    timesheetWorkspace: localStorage.getItem('payroll-ui-timesheet-workspace') || 'internal',
    timesheetFullscreen: false,
    internalTimesheetPeriod: localStorage.getItem('payroll-ui-internal-timesheet-period') || defaultInternalPeriod,
    rentalTimesheetPeriod: localStorage.getItem('payroll-ui-rental-timesheet-period') || defaultInternalPeriod,
    timesheetTab: 'attendance',
    rentalTimesheetTab: 'daily',
    rentalTimesheetProject: initialRentalTimesheetProject,
    rentalTimesheetSupplier: 'All suppliers',
    rentalTimesheetSearch: '',
    rentalTimesheetSelected: new Set(),
    rentalTimesheetBulkDay: defaultTimesheetDay(localStorage.getItem('payroll-ui-rental-timesheet-period') || defaultInternalPeriod),
    rentalTimesheetPage: 1,
    rentalTimesheetPageSize: Number(localStorage.getItem('payroll-ui-rental-timesheet-page-size') || 50),
    rentalTimesheetMobileWeek: 1,
    rentalTimesheets: rentalTimesheetCache,
    rentalTimesheetStatuses: rentalTimesheetStatusCache,
    rentalOvertime: rentalOvertimeCache,
    rentalSettlementView: 'project',
    rentalSettlementTab: 'current',
    rentalSettlementProject: initialRentalSettlementProject,
    rentalSettlementSupplier: localStorage.getItem('payroll-ui-rental-settlement-supplier') || 'All suppliers',
    rentalSettlementSearch: '',
    rentalSettlementStatus: 'All',
    rentalSettlements: {},
    rentalSettlementContexts: {},
    rentalSettlementLoadedPeriods: new Set(),
    rentalSettlementLoadingPeriod: null,
    rentalTimesheetScopes: [],
    rentalTimesheetMeta: {},
    timesheetSearch: '',
    timesheetProject: 'All projects',
    timesheetBranch: 'All branches',
    timesheetDepartment: 'All departments',
    timesheetSelected: new Set(),
    timesheetBulkDay: defaultTimesheetDay(localStorage.getItem('payroll-ui-internal-timesheet-period') || defaultInternalPeriod),
    timesheetPage: 1,
    timesheetPageSize: Number(localStorage.getItem('payroll-ui-internal-timesheet-page-size') || 50),
    timesheetMobileWeek: 1,
    timesheets: attendanceBootstrap.period?.label ? { [attendanceBootstrap.period.label]: attendanceBootstrap.records || {} } : {},
    overtimeEntries: attendanceBootstrap.period?.label ? { [attendanceBootstrap.period.label]: Object.fromEntries(Object.entries(attendanceBootstrap.overtime || {}).map(([employeeId,row]) => [employeeId, Number(row.hours || 0)])) } : {},
    timesheetStatuses: attendanceBootstrap.period?.label ? { [attendanceBootstrap.period.label]: attendanceBootstrap.period.status || 'Draft' } : {},
    attendancePeriodMeta: attendanceBootstrap.period?.label ? { [attendanceBootstrap.period.label]: attendanceBootstrap.period } : {},
    attendanceRoster: attendanceBootstrap.period?.label ? { [attendanceBootstrap.period.label]: attendanceBootstrap.roster || [] } : {},
    attendanceOvertimeMeta: attendanceBootstrap.period?.label ? { [attendanceBootstrap.period.label]: attendanceBootstrap.overtime || {} } : {},
    attendanceSummary: attendanceBootstrap.period?.label ? { [attendanceBootstrap.period.label]: attendanceBootstrap.summary || {} } : {},
    attendanceLoadedPeriods: new Set(attendanceBootstrap.period?.label ? [attendanceBootstrap.period.label] : []),
    attendanceLoadingPeriod: null,
    payrollSearch: '',
    payrollBranch: 'All branches',
    payrollDepartment: 'All departments',
    payrollProject: 'All projects',
    payrollReadiness: 'All',
    payrollView: 'register',
    payrollReviewSeverity: 'All',
    payrollContexts: payrollBootstrap.run?.label ? { [payrollBootstrap.run.label]: payrollBootstrap } : {},
    payrollLoadedPeriods: new Set(payrollBootstrap.run?.label ? [payrollBootstrap.run.label] : []),
    payrollLoadingPeriod: null,
    payrollRuns: {},
    bankExportTab: localStorage.getItem('payroll-ui-bank-export-tab') || 'bank',
    bankExportView: localStorage.getItem('payroll-ui-bank-export-view') || 'register',
    bankExportSearch: '',
    bankExportStatus: 'All',
    bankExportBranch: 'All branches',
    bankTemplateId: localStorage.getItem('payroll-ui-bank-template-id') || (paymentBootstrap.templates || []).find(item => item.channel === 'bank_csv' && item.active && !item.archived)?.id || null,
    exportTemplateDetailId: null,
    bankTemplates: [...(paymentBootstrap.templates || [])],
    bankBatches: (paymentBootstrap.batches || []).filter(item => item.channelValue === 'bank_csv'),
    bankReconciliation: {},
    wpsTab: 'validation',
    wpsTemplateId: localStorage.getItem('payroll-ui-wps-template-id') || (paymentBootstrap.templates || []).find(item => item.channel === 'wps' && item.active && !item.archived)?.id || null,
    wpsStatusFilter: 'All',
    wpsSearch: '',
    wpsBatches: (paymentBootstrap.batches || []).filter(item => item.channelValue === 'wps'),
    wpsValidation: {},
    paymentTab: 'internal',
    selectedInternalPaymentBatchId: localStorage.getItem('payroll-ui-selected-internal-payment-batch') || null,
    paymentStatusFilter: 'All',
    paymentSearch: '',
    paymentSupplierFilter: 'All suppliers',
    paymentMethodFilter: 'All methods',
    paymentPayableFilter: 'Open',
    selectedReceiptId: null,
    paymentBatches: [...(paymentBootstrap.batches || [])],
    paymentContext: paymentBootstrap,
    paymentContexts: paymentBootstrap.period ? { [paymentBootstrap.period]: paymentBootstrap } : {},
    paymentLoadedPeriods: new Set(paymentBootstrap.period ? [paymentBootstrap.period] : []),
    paymentLoadingPeriod: null,
    supplierPayments: {},
    documentTab: localStorage.getItem('payroll-ui-document-tab') || 'all',
    documentSearch: '',
    documentPeriodFilter: localStorage.getItem('payroll-ui-document-period') || 'All periods',
    documentStatusFilter: 'All statuses',
    selectedDocumentId: localStorage.getItem('payroll-ui-selected-document') || null,
    businessDocuments: [...(documentsBootstrap.documents || [])],
    documentDetails: {},
    documentLoadingId: null,
    managementContexts: managementBootstrap.periodLabel ? { [managementBootstrap.periodLabel]: managementBootstrap } : {},
    managementLoadingPeriod: null,
    reportContexts: {},
    reportLoadingKey: null,
    reportType: localStorage.getItem('payroll-ui-report-type') || 'workforce-cost',
    reportPeriod: localStorage.getItem('payroll-ui-report-period') || localStorage.getItem('payroll-ui-period') || defaultInternalPeriod,
    reportSearch: '',
    settingsTab: localStorage.getItem('payroll-ui-settings-tab') || 'general',
    systemSettings,
    recordManagement: { archive:[...(recordManagementBootstrap.archive || [])], trash:[...(recordManagementBootstrap.trash || [])], retentionDays:Number(recordManagementBootstrap.retentionDays || 30) },
    drawerType: null,
    drawerContext: null,
    branches: [...(internalMaster.branches || [])],
    departments: [...(internalMaster.departments || [])],
    employeeOrganizationHistory: { ...(internalMaster.employeeOrganizationHistory || {}) },
    projects: [...(rentalMaster.projects || [])],
    suppliers: [...(rentalMaster.suppliers || [])],
    employees: [...(internalMaster.employees || [])],
    rentalWorkers: [...(rentalMaster.workers || [])],
    salaryComponents: [...(salarySetup.salaryComponents || [])],
    overtimePolicies: [...(salarySetup.overtimePolicies || [])],
    salaryStructures: { ...(salarySetup.salaryStructures || {}) },
    salaryStructureHistory: { ...(salarySetup.salaryStructureHistory || {}) }
  };
  if (!state.projects.some(item => item.id === state.rentalTimesheetProject)) state.rentalTimesheetProject = preferredRentalProjectId(state.projects);
  if (!/^\w+ \d{4}$/.test(state.rentalTimesheetPeriod || '')) state.rentalTimesheetPeriod = defaultInternalPeriod;

  const icon = (name) => {
    const icons = {
      users: '<svg viewBox="0 0 24 24"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zm8-1a4 4 0 0 0-1-7.87M22 21v-2a4 4 0 0 0-3-3.87"/></svg>',
      briefcase: '<svg viewBox="0 0 24 24"><path d="M4 7h16v13H4zM9 7V4h6v3M4 12h16"/></svg>',
      calculator: '<svg viewBox="0 0 24 24"><path d="M5 2h14v20H5zM8 6h8M8 11h.01M12 11h.01M16 11h.01M8 15h.01M12 15h.01M16 15h.01M8 19h.01M12 19h4"/></svg>',
      timesheet: '<svg viewBox="0 0 24 24"><path d="M8 2v4m8-4v4M3 10h18M5 4h14a2 2 0 0 1 2 2v15H3V6a2 2 0 0 1 2-2zm3 10h3v3H8z"/></svg>',
      bank: '<svg viewBox="0 0 24 24"><path d="M3 10h18M5 10v8m4-8v8m6-8v8m4-8v8M2 21h20M12 3 2 8h20z"/></svg>',
      info: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 11v5m0-8h.01"/></svg>',
      plus: '<svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg>',
      arrow: '<svg viewBox="0 0 24 24"><path d="M5 12h14m-5-5 5 5-5 5"/></svg>',
      search: '<svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>',
      filter: '<svg viewBox="0 0 24 24"><path d="M4 6h16M7 12h10M10 18h4"/></svg>',
      project: '<svg viewBox="0 0 24 24"><path d="M3 21h18M5 21V7l7-4 7 4v14M9 21v-5h6v5M9 10h.01M15 10h.01"/></svg>',
      location: '<svg viewBox="0 0 24 24"><path d="M20 10c0 5-8 11-8 11S4 15 4 10a8 8 0 1 1 16 0z"/><circle cx="12" cy="10" r="2.5"/></svg>',
      calendar: '<svg viewBox="0 0 24 24"><path d="M8 2v4m8-4v4M3 10h18M5 4h14a2 2 0 0 1 2 2v15H3V6a2 2 0 0 1 2-2z"/></svg>',
      edit: '<svg viewBox="0 0 24 24"><path d="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L8 18l-4 1 1-4z"/></svg>',
      more: '<svg viewBox="0 0 24 24"><circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/></svg>',
      chevron: '<svg viewBox="0 0 24 24"><path d="m9 18 6-6-6-6"/></svg>',
      supplier: '<svg viewBox="0 0 24 24"><path d="M3 7h18M5 7V5h14v2m-1 0v12H6V7m3 4h6m-6 4h4"/></svg>',
      document: '<svg viewBox="0 0 24 24"><path d="M6 2h9l4 4v16H6zM14 2v5h5M9 12h6m-6 4h6"/></svg>',
      archive: '<svg viewBox="0 0 24 24"><path d="M4 7h16v14H4zM3 3h18v4H3zM9 11h6"/></svg>',
      trash: '<svg viewBox="0 0 24 24"><path d="M4 7h16M9 7V4h6v3m-9 0 1 14h10l1-14M10 11v6m4-6v6"/></svg>',
      clock: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>',
      person: '<svg viewBox="0 0 24 24"><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></svg>',
      wallet: '<svg viewBox="0 0 24 24"><path d="M3 6h16v14H3z"/><path d="M3 8V5h13v3m1 4h4v5h-4a2.5 2.5 0 0 1 0-5z"/></svg>',
      branch: '<svg viewBox="0 0 24 24"><path d="M3 21h18M5 21V8h14v13M8 5h8v3M9 12h2m2 0h2M9 16h2m2 0h2"/></svg>',
      department: '<svg viewBox="0 0 24 24"><path d="M4 4h16v16H4zM8 4v16m8-16v16M4 10h16M4 15h16"/></svg>',
      expand: '<svg viewBox="0 0 24 24"><path d="M8 3H3v5m13-5h5v5M8 21H3v-5m13 5h5v-5"/></svg>',
      collapse: '<svg viewBox="0 0 24 24"><path d="M3 8h5V3m13 5h-5V3M3 16h5v5m13-5h-5v5"/></svg>'
    };
    return icons[name] || icons.info;
  };

  function currencyCode() {
    return state.systemSettings?.general?.currency || settingsBootstrap.currency || 'SAR';
  }

  function formatCurrency(value) {
    return new Intl.NumberFormat('en-SA', { style: 'currency', currency: currencyCode(), currencyDisplay: 'code', minimumFractionDigits: 2 }).format(Number(value || 0));
  }

  function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>'"]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#039;','"':'&quot;'}[ch]));
  }

  function statusBadge(status) {
    const success = ['Active','Assigned','Paid','Approved','Ready','Applied','Recorded'];
    const neutral = ['Completed','Released','Inactive','Terminated','Archived','Available','Closed','Transferred'];
    const tone = success.includes(status) ? 'success' : neutral.includes(status) ? 'neutral' : 'warning';
    return `<span class="status status--${tone}"><span></span>${escapeHtml(status)}</span>`;
  }

  function supplierRouteByName(name) {
    const supplier = state.suppliers.find(item => item.name === name);
    return supplier ? `suppliers/${supplier.id}` : 'suppliers';
  }

  function roleDefinition(role = state.accessRole) {
    const definition = accessRoles[role];
    if (!definition) throw new Error(`Unknown server access role: ${role}`);
    return definition;
  }

  function roleCanWorkspace(workspace) {
    // The request-specific workspace list is authoritative.  The role matrix is useful
    // for labels/capabilities, but it must not be able to disagree with the membership
    // context that the server authorized for this request.
    return serverWorkspaces.includes(workspace);
  }

  function roleCanEdit(workspace = state.workspace) {
    return roleDefinition().edit.includes(workspace);
  }

  function roleCanApprove() { return !!roleDefinition().approve; }
  function roleCanPay() { return !!roleDefinition().pay; }
  function roleCanSettings() { return !!roleDefinition().settings; }

  function workspaceLabel() {
    if (state.workspace === 'rental') return 'Rental Manpower';
    if (state.workspace === 'management') return 'Management';
    return 'Internal Company';
  }

  function internalRouteSet() {
    return new Set(['overview','internal-employees','branches','departments','salary-setup','timesheets','payroll-runs','adjustments','payments','bank-export','wps','documents','archive','trash','reports','settings']);
  }

  function rentalRouteSet() {
    return new Set(['overview','rental-workforce','rental-onboarding','rental-assignments','projects','suppliers','timesheets','rental-settlements','adjustments','payments','documents','archive','trash','reports','settings']);
  }

  function managementRouteSet() {
    return new Set(['overview','management-cost','management-approvals','management-audit','reports','access-roles','settings']);
  }

  function workspaceAllowsRoute(route) {
    if (!roleCanWorkspace(state.workspace)) return false;
    if (route === 'settings' && !roleCanSettings()) return false;
    if (route === 'access-roles' && !roleDefinition().view_access) return false;
    const set = state.workspace === 'rental' ? rentalRouteSet() : state.workspace === 'management' ? managementRouteSet() : internalRouteSet();
    return set.has(route);
  }

  function workspaceNavSections() {
    if (state.workspace === 'management') return [
      ['Company Control', [['overview','Company Overview','briefcase'],['management-cost','Workforce Cost','calculator'],['management-approvals','Approval Center','document'],['management-audit','Audit Trail','clock']]],
      ['Intelligence', [['reports','Management Reports','calculator']]],
      ['Governance', [['access-roles','Access & Roles','person']]]
    ].map(([label,items]) => [label, items.filter(([route]) => workspaceAllowsRoute(route))]);
    if (state.workspace === 'rental') return [
      ['Workspace', [['overview','Overview','briefcase']]],
      ['Workforce', [['rental-workforce','Rental Workers','users'],['suppliers','Manpower Suppliers','supplier']]],
      ['Operations', [['rental-assignments','Assignment Lifecycle','arrow'],['projects','Projects','project'],['timesheets','Project Timesheets','timesheet']]],
      ['Cost & Settlement', [['rental-settlements','Supplier Settlements','calculator'],['adjustments','Worker Adjustments','wallet'],['payments','Supplier Payments','bank']]],
      ['Records', [['documents','Rental Documents','document'],['archive','Archive','archive'],['trash','Delete','trash'],['reports','Rental Reports','calculator']]]
    ];
    return [
      ['Workspace', [['overview','Overview','users']]],
      ['Organization', [['internal-employees','Employees','users'],['branches','Branches & Offices','branch'],['departments','Departments','department']]],
      ['Time', [['timesheets','Attendance & Overtime','timesheet']]],
      ['Payroll', [['salary-setup','Salary Setup','wallet'],['payroll-runs','Payroll Runs','calculator'],['adjustments','Advances & Adjustments','wallet'],['payments','Salary Payments','bank'],['bank-export','Bank & WPS Export','bank']]],
      ['Records', [['documents','Salary Slips & Documents','document'],['archive','Archive','archive'],['trash','Delete','trash'],['reports','Reports','calculator']]]
    ];
  }

  function workspaceNavItem(route, label, iconName) {
    return `<a class="ui-v2-nav-item" href="#/${route}" data-route="${route}" data-active="false">${icon(iconName)}<span>${escapeHtml(label)}</span></a>`;
  }

  function renderWorkspaceShell() {
    if (appShell) appShell.dataset.payrollWorkspace = state.workspace;
    document.body.dataset.accessRole = state.accessRole;
    const nav = document.getElementById('primaryNav');
    if (nav) nav.innerHTML = workspaceNavSections().filter(([,items])=>items.length).map(([label, items]) => `<div class="ui-v2-nav-group"><div class="ui-v2-nav-group__label">${escapeHtml(label)}</div><div class="ui-v2-nav-group__items">${items.map(([route,title,iconName])=>workspaceNavItem(route,title,iconName)).join('')}</div></div>`).join('');

    const workspaceMeta = state.workspace === 'rental'
      ? { icon:'RM', title:'Rental Manpower', subtitle:'Supplier workers' }
      : state.workspace === 'management'
      ? { icon:'MG', title:'Management', subtitle:'Company control' }
      : { icon:'IC', title:'Internal Company', subtitle:'Own employees' };
    const workspaceTriggerIcon = document.getElementById('workspaceTriggerIcon');
    const workspaceTriggerTitle = document.getElementById('workspaceTriggerTitle');
    const workspaceTriggerSubtitle = document.getElementById('workspaceTriggerSubtitle');
    if (workspaceTriggerIcon) workspaceTriggerIcon.textContent = workspaceMeta.icon;
    if (workspaceTriggerTitle) workspaceTriggerTitle.textContent = workspaceMeta.title;
    if (workspaceTriggerSubtitle) workspaceTriggerSubtitle.textContent = workspaceMeta.subtitle;

    document.querySelectorAll('[data-workspace-switch]').forEach(control => {
      const target = control.dataset.workspaceSwitch;
      const active = target === state.workspace;
      const allowed = roleCanWorkspace(target);
      control.classList.toggle('is-active', active);
      control.classList.toggle('is-disabled', !allowed);
      control.dataset.active = String(active);
      control.setAttribute('aria-current', active ? 'page' : 'false');
      control.setAttribute('aria-disabled', String(!allowed));
      if ('disabled' in control) control.disabled = !allowed;
      if (!allowed) control.tabIndex = -1;
      else control.removeAttribute('tabindex');
      control.title = allowed ? `Open ${target === 'internal' ? 'Internal Company' : target === 'rental' ? 'Rental Manpower' : 'Management'}` : `${roleDefinition().label} does not have access to this workspace`;
    });
    const accountLabel = document.getElementById('workspaceAccountLabel');
    if (accountLabel) accountLabel.textContent = workspaceLabel();
    const accountMenuWorkspaceLabel = document.getElementById('accountMenuWorkspaceLabel');
    if (accountMenuWorkspaceLabel) accountMenuWorkspaceLabel.textContent = workspaceLabel();
    const accountRoleLabel = document.getElementById('accountRoleLabel');
    if (accountRoleLabel) accountRoleLabel.textContent = roleDefinition().label;
    const accountMenuRoleLabel = document.getElementById('accountMenuRoleLabel');
    if (accountMenuRoleLabel) accountMenuRoleLabel.textContent = roleDefinition().label;
    const settingsLink = document.querySelector('[data-account-settings]');
    if (settingsLink) settingsLink.hidden = !roleCanSettings();

    const quickAddMenu = document.getElementById('quickAddMenu');
    if (quickAddMenu) {
      quickAddMenu.innerHTML = state.workspace === 'management'
        ? `<div class="ui-v2-prs-menu-header"><strong>Management workspace</strong><span>Read-only aggregate</span></div><div class="ui-v2-prs-menu-note">Create and edit operational records inside Internal Company or Rental Manpower. Management intentionally does not create cross-workspace records.</div>`
        : state.workspace === 'rental'
        ? `<button class="ui-v2-menu__item ui-v2-prs-menu-rich" data-quick-add="rental-worker"><span class="ui-v2-command__icon">RW</span><span><strong>Rental Worker</strong><small>Create permanent supplier worker</small></span></button><button class="ui-v2-menu__item ui-v2-prs-menu-rich" data-route-link="rental-onboarding"><span class="ui-v2-command__icon">BI</span><span><strong>Bulk Onboard Workers</strong><small>Paste / import a supplier roster</small></span></button><div class="ui-v2-menu__separator"></div><button class="ui-v2-menu__item ui-v2-prs-menu-rich" data-quick-add="project"><span class="ui-v2-command__icon">PR</span><span><strong>Project</strong><small>Create rental project master</small></span></button><button class="ui-v2-menu__item ui-v2-prs-menu-rich" data-quick-add="supplier"><span class="ui-v2-command__icon">SP</span><span><strong>Manpower Supplier</strong><small>Create supplier company</small></span></button><div class="ui-v2-menu__separator"></div><button class="ui-v2-menu__item ui-v2-prs-menu-rich" data-quick-add="advance"><span class="ui-v2-command__icon">AD</span><span><strong>Worker Adjustment</strong><small>Advance / deduction / earning</small></span></button>`
        : `<button class="ui-v2-menu__item ui-v2-prs-menu-rich" data-quick-add="internal-employee"><span class="ui-v2-command__icon">IE</span><span><strong>Internal Employee</strong><small>Add company employee</small></span></button><button class="ui-v2-menu__item ui-v2-prs-menu-rich" data-quick-add="branch"><span class="ui-v2-command__icon">BR</span><span><strong>Branch / Office</strong><small>Create company office master</small></span></button><button class="ui-v2-menu__item ui-v2-prs-menu-rich" data-quick-add="department"><span class="ui-v2-command__icon">DP</span><span><strong>Department</strong><small>Create department master</small></span></button><div class="ui-v2-menu__separator"></div><button class="ui-v2-menu__item ui-v2-prs-menu-rich" data-quick-add="advance"><span class="ui-v2-command__icon">AD</span><span><strong>Employee Adjustment</strong><small>Advance / deduction / earning</small></span></button>`;
    }

    const notificationMenu = document.getElementById('notificationMenu');
    if (notificationMenu) {
      if (state.workspace === 'management') {
        const approvals = managementApprovalItems();
        const critical = approvals.filter(item=>item.severity==='Critical').length;
        notificationMenu.innerHTML = `<div class="ui-v2-prs-menu-header"><strong>Company control attention</strong><span>${approvals.length} items</span></div><a href="#/management-approvals" class="notice-row"><span class="notice-icon ${critical?'notice-icon--warn':''}">${critical?'!':'A'}</span><span><strong>${critical ? `${critical} critical control item${critical===1?'':'s'}` : 'Approval center'}</strong><small>Internal payroll and rental settlement reviews stay separately attributable.</small></span></a><a href="#/management-cost" class="notice-row"><span class="notice-icon">C</span><span><strong>Workforce cost visibility</strong><small>Compare finalized Internal and Rental costs without merging operational records.</small></span></a><a href="#/management-audit" class="notice-row"><span class="notice-icon">AU</span><span><strong>Audit trail</strong><small>Review payroll, settlement, assignment and payment lifecycle events.</small></span></a>`;
      } else if (state.workspace === 'rental') {
        notificationMenu.innerHTML = `<div class="ui-v2-prs-menu-header"><strong>Rental manpower controls</strong><span>Current workspace</span></div><a href="#/timesheets" class="notice-row"><span class="notice-icon">T</span><span><strong>Project timesheets</strong><small>Review supplier manpower hours before settlement.</small></span></a><a href="#/rental-assignments" class="notice-row"><span class="notice-icon notice-icon--warn">!</span><span><strong>Assignment changes</strong><small>Transfers, trade and rate changes remain effective-dated.</small></span></a><a href="#/rental-settlements" class="notice-row"><span class="notice-icon">S</span><span><strong>Supplier settlements</strong><small>Approved timesheets feed supplier payable calculations.</small></span></a><a href="#/suppliers" class="notice-row"><span class="notice-icon">SP</span><span><strong>Supplier deployment</strong><small>Review active and available workers by company.</small></span></a>`;
      } else {
        notificationMenu.innerHTML = `<div class="ui-v2-prs-menu-header"><strong>Internal payroll controls</strong><span>Current workspace</span></div><a href="#/bank-export" class="notice-row"><span class="notice-icon">BK</span><span><strong>Bank / WPS readiness</strong><small>Review current employee and company payment readiness.</small></span></a><a href="#/timesheets" class="notice-row"><span class="notice-icon">T</span><span><strong>Attendance & overtime</strong><small>Approve the monthly input before payroll review.</small></span></a><a href="#/payroll-runs" class="notice-row"><span class="notice-icon">P</span><span><strong>Payroll run</strong><small>Company payroll stays isolated from rental settlements.</small></span></a><a href="#/branches" class="notice-row"><span class="notice-icon">BR</span><span><strong>Organization setup</strong><small>Employees are organized by branch and department, not project.</small></span></a>`;
      }
    }

    searchInput.placeholder = state.workspace === 'rental'
      ? 'Search rental workers, projects, suppliers…'
      : state.workspace === 'management'
      ? 'Search both workspaces, approvals, reports…'
      : 'Search employees, branches, departments, payroll…';
  }

  function syncWorkspaceUrl(workspace) {
    const url = new URL(window.location.href);
    url.searchParams.set('workspace', workspace);
    history.replaceState(history.state, '', `${url.pathname}${url.search}${url.hash}`);
  }

  function switchWorkspace(nextWorkspace) {
    const next = ['internal','rental','management'].includes(nextWorkspace) ? nextWorkspace : 'internal';
    if (!roleCanWorkspace(next)) { showToast('Workspace access restricted', `${roleDefinition().label} cannot open ${next === 'internal' ? 'Internal Company' : next === 'rental' ? 'Rental Manpower' : 'Management'}.`); return; }
    if (next === state.workspace) { syncWorkspaceUrl(next); navigate('overview'); return; }
    if (state.workspace === 'internal') localStorage.setItem('payroll-ui-internal-period', state.period);
    else if (state.workspace === 'rental') localStorage.setItem('payroll-ui-rental-period', state.period);
    else localStorage.setItem('payroll-ui-management-period', state.period);

    state.workspace = next;
    localStorage.setItem('payroll-ui-workspace', next);
    syncWorkspaceUrl(next);
    state.period = next === 'rental'
      ? (localStorage.getItem('payroll-ui-rental-period') || defaultInternalPeriod)
      : next === 'management'
      ? (localStorage.getItem('payroll-ui-management-period') || defaultInternalPeriod)
      : (localStorage.getItem('payroll-ui-internal-period') || defaultInternalPeriod);
    localStorage.setItem('payroll-ui-period', state.period);
    periodLabel.textContent = state.period;
    document.querySelectorAll('[data-period]').forEach(btn => btn.classList.toggle('is-selected', btn.dataset.period === state.period));

    if (next !== 'management') {
      state.timesheetWorkspace = next === 'rental' ? 'rental' : 'internal';
      state.adjustmentWorkforce = next === 'rental' ? 'Rental' : 'Internal';
      state.paymentTab = next === 'rental' ? 'supplier' : 'internal';
      state.reportType = next === 'rental' ? 'rental-project-cost' : 'internal-payroll';
      state.documentTab = 'all';
    } else {
      state.reportType = 'workforce-cost';
    }

    renderWorkspaceShell();
    navigate('overview');
    const message = next === 'rental' ? 'Projects, manpower suppliers, rental workers and settlements are isolated from internal payroll.' : next === 'internal' ? 'Branches, departments, employees, salary payments and bank/WPS exports are isolated from rental manpower.' : 'Management compares finalized company costs and control statuses without merging operational records.';
    showToast(`${workspaceLabel()} workspace`, message);
  }

  function internalOverviewTemplate() {
    const activeEmployees = state.employees.filter(item => item.status === 'Active');
    const branchCount = state.branches.filter(item => item.status === 'Active').length;
    const departmentCount = state.departments.filter(item => item.status === 'Active').length;
    const wpsReady = activeEmployees.filter(item => item.wps === 'Ready').length;
    const salaryConfigured = activeEmployees.filter(item => !!employeeProfileData(item).salary).length;
    const payrollRows = payrollRowsForDisplay();
    const totals = payrollTotals(payrollRows);
    const runStatus = payrollRunStatus();
    return `<section class="page ui-v2-payroll-page ui-v2-payroll-overview ui-v2-prs-internal-page">
      <div class="page-head ui-v2-page-header ui-v2-payroll-page-head">
        <div class="page-head__copy ui-v2-page-header__copy"><span class="eyebrow ui-v2-eyebrow">Internal Company</span><h1 class="ui-v2-title-lg">Internal Company Payroll</h1><p class="ui-v2-body">Internal employees, organization, attendance, salary setup and salary-payment readiness for the active payroll period.</p></div>
        <div class="page-head__actions ui-v2-page-header__actions"><div class="ui-v2-payroll-period"><span>Payroll period</span><strong>${escapeHtml(state.period)}</strong></div><button class="btn btn--secondary" data-route-link="bank-export">${icon('bank')} Bank / WPS</button><button class="btn btn--primary" data-route-link="payroll-runs">Open Payroll Run</button></div>
      </div>
      <div class="summary-strip ui-v2-payroll-summary-strip">
        <div class="summary-item ui-v2-payroll-metric"><span>Active employees</span><strong>${activeEmployees.length}</strong><small>${branchCount} active branch${branchCount === 1 ? '' : 'es'}</small></div>
        <div class="summary-item ui-v2-payroll-metric"><span>Departments</span><strong>${departmentCount}</strong><small>Organization masters</small></div>
        <div class="summary-item ui-v2-payroll-metric"><span>Salary configured</span><strong>${salaryConfigured}/${activeEmployees.length}</strong><small>Current numeric structures</small></div>
        <div class="summary-item ui-v2-payroll-metric"><span>WPS ready</span><strong>${wpsReady}/${activeEmployees.length}</strong><small>Bank / identity source records</small></div>
      </div>
      <section class="ui-v2-payroll-financial-shortcut ui-v2-prs-financial-shortcut">
        <span>${icon('bank')}</span><div><strong>Payroll & payment control</strong><small>${escapeHtml(runStatus)} · ${formatCurrency(totals.net || 0)} current net payable. Review the controlled payroll calculation before bank/WPS export.</small></div><button type="button" data-route-link="payroll-runs">Open payroll ${icon('chevron')}</button>
      </section>
      <div class="ui-v2-payroll-overview-grid">
        <section class="panel ui-v2-payroll-panel">
          <header><div><span>Organization</span><h2>Internal workforce</h2></div>${statusBadge('Active')}</header>
          <div class="ui-v2-payroll-org-grid">
            <button type="button" data-route-link="internal-employees"><span>${icon('person')}</span><div><strong>${activeEmployees.length} employees</strong><small>Open internal employee register</small></div>${icon('chevron')}</button>
            <button type="button" data-route-link="branches"><span>${icon('branch')}</span><div><strong>${branchCount} active branches</strong><small>Company office masters</small></div>${icon('chevron')}</button>
            <button type="button" data-route-link="departments"><span>${icon('department')}</span><div><strong>${departmentCount} departments</strong><small>Published organization masters</small></div>${icon('chevron')}</button>
            <button type="button" data-route-link="timesheets"><span>${icon('timesheet')}</span><div><strong>Attendance & overtime</strong><small>${escapeHtml(state.period)} company timesheet</small></div>${icon('chevron')}</button>
          </div>
        </section>
        <section class="panel ui-v2-payroll-panel">
          <header><div><span>Payroll readiness</span><h2>Items needing configuration</h2></div></header>
          <div class="ui-v2-payroll-attention">
            <article><span>!</span><div><strong>${Math.max(0, activeEmployees.length - salaryConfigured)} salary record${activeEmployees.length - salaryConfigured === 1 ? '' : 's'} incomplete</strong><small>Configure a numeric salary structure before calculation.</small></div></article>
            <article><span>BK</span><div><strong>${Math.max(0, activeEmployees.length - wpsReady)} employee${activeEmployees.length - wpsReady === 1 ? '' : 's'} not WPS-ready</strong><small>Bank and identity setup remains separate from salary calculation.</small></div></article>
          </div>
        </section>
      </div>
      <div class="source-banner ui-v2-payroll-source-note">${icon('info')}<span>Internal employees are organized through company-controlled branches and departments. Rental projects and manpower suppliers remain outside this workspace.</span></div>
    </section>`;
  }

  function rentalProjectControlRows() {
    const projects = state.projects.filter(project => project.status === 'Active' && !project.legacyInternal);
    const projectMetrics = new Map(projects.map(project => [project.id, { workers:0, suppliers:new Set() }]));
    state.rentalWorkers.forEach(worker => {
      if (worker.status !== 'Assigned') return;
      const projectId = rentalWorkerCurrentSnapshot(worker).project?.id;
      const metric = projectMetrics.get(projectId);
      if (!metric) return;
      metric.workers += 1;
      if (worker.supplierId) metric.suppliers.add(worker.supplierId);
    });
    const payablesByProject = new Map();
    supplierPayables(state.period).forEach(row => {
      const metric = payablesByProject.get(row.projectId) || { payable:0, paid:0, outstanding:0 };
      metric.payable += Number(row.amount || 0);
      metric.paid += Number(row.paid || 0);
      metric.outstanding += Number(row.outstanding || 0);
      payablesByProject.set(row.projectId, metric);
    });
    const settlementByProject = new Map();
    Object.values(state.rentalSettlements || {}).forEach(row => {
      if (row.period !== state.period) return;
      const current = settlementByProject.get(row.projectId);
      if (!current || rentalSettlementStage(row.status) > rentalSettlementStage(current.status)) settlementByProject.set(row.projectId, row);
    });
    return projects.map(project => {
      const workforce = projectMetrics.get(project.id) || { workers:0, suppliers:new Set() };
      const payable = payablesByProject.get(project.id) || { payable:0, paid:0, outstanding:0 };
      return {
        project,
        workers: workforce.workers,
        suppliers: workforce.suppliers.size,
        timesheet: rentalTimesheetStatus(state.period, project.id),
        settlement: settlementByProject.get(project.id)?.status || 'Not started',
        payable: payable.payable,
        paid: payable.paid,
        outstanding: payable.outstanding,
        cost: payable.payable
      };
    });
  }

  function rentalSupplierControlRows() {
    const supplierMetrics = new Map(state.suppliers.map(supplier => [supplier.id, { assigned:0, available:0, projects:new Set() }]));
    state.rentalWorkers.forEach(worker => {
      const metric = supplierMetrics.get(worker.supplierId);
      if (!metric) return;
      if (worker.status === 'Assigned') {
        metric.assigned += 1;
        const projectId = rentalWorkerCurrentSnapshot(worker).project?.id;
        if (projectId) metric.projects.add(projectId);
      } else if (worker.status === 'Available') {
        metric.available += 1;
      }
    });
    const payableBySupplier = new Map();
    supplierPayables(state.period).forEach(row => {
      const metric = payableBySupplier.get(row.supplierId) || { payable:0, paid:0, outstanding:0 };
      metric.payable += Number(row.amount || 0);
      metric.paid += Number(row.paid || 0);
      metric.outstanding += Number(row.outstanding || 0);
      payableBySupplier.set(row.supplierId, metric);
    });
    return state.suppliers.filter(supplier => supplier.status === 'Active').map(supplier => {
      const workforce = supplierMetrics.get(supplier.id) || { assigned:0, available:0, projects:new Set() };
      const payable = payableBySupplier.get(supplier.id) || { payable:0, paid:0, outstanding:0 };
      return {
        supplier,
        assigned: workforce.assigned,
        available: workforce.available,
        projects: workforce.projects.size,
        payable: payable.payable,
        paid: payable.paid,
        outstanding: payable.outstanding
      };
    });
  }

  function rentalOverviewTemplate() {
    if (!state.rentalSettlementLoadedPeriods.has(state.period) && state.rentalSettlementLoadingPeriod !== state.period) loadRentalSettlementContext(state.period, { render:true });
    const assigned = state.rentalWorkers.filter(worker => worker.status === 'Assigned').length;
    const available = state.rentalWorkers.filter(worker => worker.status === 'Available').length;
    const activeProjects = state.projects.filter(project => project.status === 'Active' && !project.legacyInternal);
    const activeSuppliers = state.suppliers.filter(supplier => supplier.status === 'Active');
    const projectRows = rentalProjectControlRows();
    const supplierRows = rentalSupplierControlRows();
    const payables = supplierPayables(state.period);
    const payableSummary = supplierPaymentSummary(payables);
    const activity = rentalAssignmentActivityRows().slice(0,5);
    const periodHours = Object.values(state.rentalSettlements || {}).filter(row=>row.period===state.period).reduce((sum,row)=>sum+Number(row.totals?.regularHours||0),0);
    const periodNet = payableSummary.payable;
    const timesheetAttention = projectRows.filter(row=>!['Approved','Locked'].includes(row.timesheet)).length;
    const settlementAttention = projectRows.filter(row=>row.settlement === 'Not started' || row.settlement === 'Draft').length;
    return `<section class="page workspace-overview workspace-overview--rental rental-control-overview">
      <div class="page-head"><div class="page-head__copy"><span class="eyebrow">Rental Manpower · ${escapeHtml(state.period)}</span><h1>Rental Manpower Control</h1><p>A separate supplier-workforce operation for project deployment, project hours, manpower cost, supplier settlement and supplier payment.</p></div><div class="page-head__actions"><button class="btn btn--secondary" data-route-link="rental-assignments">Assignment Lifecycle</button><button class="btn btn--primary" data-route-link="timesheets">Project Timesheets</button></div></div>
      <div class="workspace-context-banner workspace-context-banner--rental"><span class="workspace-context-banner__icon">RM</span><div><strong>Independent rental operation</strong><span>Manpower Supplier → Permanent Worker → Effective Assignment → Project → Approved Timesheet → Supplier Settlement → Supplier Payment.</span></div><button class="text-link" data-workspace-jump="internal">Switch to Internal Company →</button></div>
      <div class="rental-flow-strip" aria-label="Rental manpower workflow"><button data-route-link="suppliers"><span>1</span><strong>Suppliers</strong><small>${activeSuppliers.length} active</small></button><button data-route-link="rental-workforce"><span>2</span><strong>Workers</strong><small>${assigned} assigned · ${available} available</small></button><button data-route-link="rental-assignments"><span>3</span><strong>Assignments</strong><small>Effective-dated</small></button><button data-route-link="projects"><span>4</span><strong>Projects</strong><small>${activeProjects.length} active</small></button><button data-route-link="timesheets"><span>5</span><strong>Timesheets</strong><small>${timesheetAttention} need attention</small></button><button data-route-link="rental-settlements"><span>6</span><strong>Settlements</strong><small>${settlementAttention} pending</small></button><button data-route-link="payments"><span>7</span><strong>Payments</strong><small>${formatCurrency(payableSummary.outstanding)} open</small></button></div>
      <div class="summary-strip summary-strip--6 rental-control-summary"><div class="summary-item"><span>Assigned workers</span><strong>${assigned}</strong><small>${available} available with suppliers</small></div><div class="summary-item"><span>Active suppliers</span><strong>${activeSuppliers.length}</strong><small>Manpower company masters</small></div><div class="summary-item"><span>Active projects</span><strong>${activeProjects.length}</strong><small>Rental manpower projects</small></div><div class="summary-item"><span>Recorded hours</span><strong>${periodHours.toLocaleString('en-SA',{maximumFractionDigits:2})}</strong><small>${escapeHtml(state.period)}</small></div><div class="summary-item"><span>Manpower cost</span><strong>${formatCurrency(periodNet)}</strong><small>Controlled settlement period cost</small></div><div class="summary-item ${payableSummary.outstanding>.005?'summary-item--attention':''}"><span>Supplier outstanding</span><strong>${formatCurrency(payableSummary.outstanding)}</strong><small>${payableSummary.open} open · ${payableSummary.partial} part paid</small></div></div>

      <div class="rental-control-grid">
        <section class="panel panel--flush rental-control-projects"><div class="panel__head panel__head--padded"><div><h2>Project control</h2><p>Deployment, timesheet, settlement and payable status in one view.</p></div><button class="text-link" data-route-link="projects">All projects →</button></div><div class="table-scroll"><table class="data-table rental-control-table"><thead><tr><th>Project</th><th>Workers</th><th>Suppliers</th><th>Timesheet</th><th>Settlement</th><th class="num">Cost / Payable</th><th class="num">Outstanding</th><th></th></tr></thead><tbody>${projectRows.length?projectRows.map(row=>`<tr><td><button class="entity-link entity-link--stack" data-open-project="${escapeHtml(row.project.id)}"><strong>${escapeHtml(row.project.name)}</strong><span>${escapeHtml(row.project.code)} · ${escapeHtml(row.project.location)}</span></button></td><td><strong>${row.workers}</strong></td><td>${row.suppliers}</td><td>${timesheetStatusBadge(row.timesheet)}</td><td>${row.settlement==='Not started'?'<span class="status status--neutral"><span></span>Not started</span>':rentalSettlementStatusBadge(row.settlement)}</td><td class="num table-money"><strong>${formatCurrency(row.cost)}</strong></td><td class="num table-money">${row.outstanding>.005?`<strong class="text-alert">${formatCurrency(row.outstanding)}</strong>`:formatCurrency(0)}</td><td><button class="icon-btn icon-btn--sm" data-open-project="${escapeHtml(row.project.id)}">${icon('chevron')}</button></td></tr>`).join(''):`<tr><td colspan="8"><div class="table-empty"><strong>No active rental projects.</strong><span>Create a project before assigning supplier workers.</span></div></td></tr>`}</tbody></table></div></section>

        <aside class="rental-control-side">
          <section class="panel panel--flush"><div class="panel__head panel__head--padded"><div><h2>Supplier exposure</h2><p>Current deployment and unpaid settlement balance.</p></div><button class="text-link" data-route-link="suppliers">All suppliers →</button></div><div class="rental-supplier-control-list">${supplierRows.slice(0,5).map(row=>`<button data-open-supplier="${escapeHtml(row.supplier.id)}"><span class="rental-supplier-control-list__icon">SP</span><span><strong>${escapeHtml(row.supplier.name)}</strong><small>${row.assigned} assigned · ${row.available} available · ${row.projects} projects</small></span><em>${row.outstanding>.005?formatCurrency(row.outstanding):'No open payable'}</em>${icon('chevron')}</button>`).join('') || '<div class="empty-inline">No active suppliers.</div>'}</div></section>
          <section class="panel panel--flush"><div class="panel__head panel__head--padded"><div><h2>Recent manpower changes</h2><p>Latest assignment lifecycle events.</p></div><button class="text-link" data-route-link="rental-assignments">Activity log →</button></div><div class="rental-recent-events">${activity.map(row=>`<button data-open-rental-worker="${escapeHtml(row.worker.id)}"><div class="rental-recent-events__badge">${rentalAssignmentBadge(row.type)}</div><div class="rental-recent-events__copy"><strong>${escapeHtml(row.worker.name)}</strong><small>${escapeHtml(row.from)} → ${escapeHtml(row.to)} · ${escapeHtml(row.effective ? rentalDisplayDate(row.effective) : 'Date not supplied')}</small></div></button>`).join('') || '<div class="empty-inline">No assignment activity yet.</div>'}</div></section>
        </aside>
      </div>

      <div class="grid-2"><section class="panel"><div class="panel__head"><div><h2>Needs attention</h2><p>Only rental-manpower operational blockers.</p></div></div><div class="attention-list"><a href="#/timesheets" class="attention-row"><span class="attention-row__icon">TS</span><span class="attention-row__copy"><strong>${timesheetAttention} project timesheet${timesheetAttention===1?'':'s'} need approval/locking</strong><span>Settlements use only approved or locked project manpower inputs.</span></span><span class="attention-row__action">Review</span></a><a href="#/rental-settlements" class="attention-row"><span class="attention-row__icon">ST</span><span class="attention-row__copy"><strong>${settlementAttention} project settlement${settlementAttention===1?'':'s'} not finalized</strong><span>Supplier payable is created only from controlled settlement status.</span></span><span class="attention-row__action">Open</span></a><a href="#/payments" class="attention-row"><span class="attention-row__icon attention-row__icon--warn">SP</span><span class="attention-row__copy"><strong>${formatCurrency(payableSummary.outstanding)} supplier payable outstanding</strong><span>Partial payments and reversals remain linked to their settlement.</span></span><span class="attention-row__action">Pay</span></a></div></section><section class="panel"><div class="panel__head"><div><h2>Quick actions</h2><p>Rental-manpower actions only.</p></div></div><div class="quick-actions"><button class="action-tile" data-quick-add="rental-worker"><span class="action-tile__icon">${icon('plus')}</span><span class="action-tile__copy"><strong>Add worker</strong><span>Supplier + assignment</span></span></button><button class="action-tile" data-route-link="rental-onboarding"><span class="action-tile__icon">${icon('users')}</span><span class="action-tile__copy"><strong>Bulk onboard</strong><span>Paste/import supplier roster</span></span></button><button class="action-tile" data-quick-add="project"><span class="action-tile__icon">${icon('project')}</span><span class="action-tile__copy"><strong>Add project</strong><span>Rental project master</span></span></button><button class="action-tile" data-quick-add="supplier"><span class="action-tile__icon">${icon('supplier')}</span><span class="action-tile__copy"><strong>Add supplier</strong><span>Manpower company</span></span></button></div></section></div>
      <div class="source-banner">${icon('info')}<span>Rental manpower financials are derived from controlled project assignments, locked project timesheets, approved supplier settlements and recorded supplier payments. Internal employee payroll and WPS remain isolated in Internal Company.</span></div>
    </section>`;
  }


  function managementPeriodSort(a,b) {
    return String(b || '').localeCompare(String(a || ''));
  }

  function managementCurrentContext() {
    return state.managementContexts[state.period] || null;
  }

  async function loadManagementContext(period = state.period, { render = true, force = false } = {}) {
    if (state.managementLoadingPeriod === period) return;
    if (!force && state.managementContexts[period]) return;
    state.managementLoadingPeriod = period;
    try {
      const payload = await appApi(`/api/management/?period=${encodeURIComponent(periodKeyFromLabel(period))}`);
      const context = payload.management || {};
      if (context.periodLabel) state.managementContexts[context.periodLabel] = context;
      if (render && state.workspace === 'management') renderRoute();
    } catch (error) {
      showToast('Management data unavailable', error.message);
    } finally {
      state.managementLoadingPeriod = null;
    }
  }

  function managementApprovalItems() {
    return managementCurrentContext()?.approvals || [];
  }

  function managementAuditEvents() {
    return managementCurrentContext()?.audit || [];
  }

  function managementWorkspaceLink(workspace, route, label) {
    return `<button class="text-link" data-management-open="${escapeHtml(workspace)}|${escapeHtml(route)}">${escapeHtml(label)} →</button>`;
  }

  function managementLoadingTemplate(title) {
    if (!state.managementLoadingPeriod) queueMicrotask(() => loadManagementContext(state.period));
    return `<section class="page"><div class="table-empty table-empty--card"><strong>${escapeHtml(title)}</strong><span>Loading controlled company records for ${escapeHtml(state.period)}.</span></div></section>`;
  }

  function managementOverviewTemplate() {
    const ctx = managementCurrentContext();
    if (!ctx) return managementLoadingTemplate('Loading company workforce control…');
    const internal = ctx.internal || {}, rental = ctx.rental || {}, payments = ctx.payments || {};
    const approvals = ctx.approvals || [], critical = approvals.filter(item => item.severity === 'Critical').length;
    return `<section class="page management-overview">
      <div class="page-head"><div class="page-head__copy"><span class="eyebrow">Management · Company Control · ${escapeHtml(ctx.periodLabel || state.period)}</span><h1>Company Workforce Control</h1><p>Compare controlled Internal Company payroll and Rental Manpower settlement records without merging their operational ledgers.</p></div><div class="page-head__actions"><button class="btn btn--secondary" data-route-link="management-audit">Audit Trail</button><button class="btn btn--primary" data-route-link="management-approvals">Approval Center${approvals.length?` · ${approvals.length}`:''}</button></div></div>
      <div class="management-boundary-banner"><span class="management-boundary-banner__icon">MG</span><div><strong>Read-only aggregate</strong><span>Financial values come from controlled payroll and supplier-settlement snapshots. Management does not calculate or mutate operational records.</span></div><span class="management-role-chip">${escapeHtml(roleDefinition().label)}</span></div>
      <div class="management-workforce-cards">
        <article class="management-workforce-card management-workforce-card--internal"><div class="management-workforce-card__head"><span>IC</span><div><strong>Internal Company</strong><small>Branches · Departments · Employees</small></div>${managementWorkspaceLink('internal','overview','Open workspace')}</div><div class="management-workforce-card__metrics"><div><span>Current employees</span><strong>${Number(ctx.headcount?.internal||0)}</strong></div><div><span>Selected payroll</span><strong>${internal.finalized?formatCurrency(internal.net):'Not finalized'}</strong><small>${escapeHtml(internal.status||'Not calculated')}</small></div><div><span>Salary payment outstanding</span><strong>${formatCurrency(payments.internal?.pending||0)}</strong><small>${Number(payments.internal?.failed||0)} failed/reversed</small></div></div></article>
        <article class="management-workforce-card management-workforce-card--rental"><div class="management-workforce-card__head"><span>RM</span><div><strong>Rental Manpower</strong><small>Suppliers · Workers · Projects</small></div>${managementWorkspaceLink('rental','overview','Open workspace')}</div><div class="management-workforce-card__metrics"><div><span>Currently assigned workers</span><strong>${Number(ctx.headcount?.rental||0)}</strong></div><div><span>Approved settlement cost</span><strong>${rental.finalized?formatCurrency(rental.net):'Not finalized'}</strong><small>${Number(rental.records||0)} settlement${Number(rental.records||0)===1?'':'s'}</small></div><div><span>Supplier outstanding</span><strong>${formatCurrency(payments.rental?.outstanding||0)}</strong><small>${Number(payments.rental?.failed||0)} failed/reversed</small></div></div></article>
      </div>
      <section class="panel panel--flush management-comparison-card"><div class="panel__head panel__head--padded"><div><h2>${escapeHtml(ctx.periodLabel || state.period)} cost comparability</h2><p>Combined cost is shown only when both domains have finalized records for the same period.</p></div><button class="text-link" data-route-link="management-cost">Full cost view →</button></div><div class="management-comparison-grid"><div><span>Internal finalized payroll</span><strong>${internal.finalized?formatCurrency(internal.net):'Not finalized'}</strong><small>${escapeHtml(internal.status||'—')}</small></div><div><span>Rental approved settlements</span><strong>${rental.finalized?formatCurrency(rental.net):'Not finalized'}</strong><small>${Number(rental.records||0)} finalized settlement${Number(rental.records||0)===1?'':'s'}</small></div><div class="${ctx.comparable?'is-comparable':'is-incomplete'}"><span>Comparable workforce cost</span><strong>${ctx.comparable?formatCurrency(ctx.combined):'Not comparable yet'}</strong><small>${ctx.comparable?'Both controlled sources are finalized.':'No estimated or draft values are added.'}</small></div></div></section>
      <div class="grid-2 management-control-grid"><section class="panel"><div class="panel__head"><div><h2>Approval & exception center</h2><p>Cross-workspace attention while record ownership remains unchanged.</p></div><span class="placeholder__stage ${critical?'placeholder__stage--warn':''}">${critical?`${critical} critical`:`${approvals.length} open`}</span></div><div class="management-approval-mini">${approvals.slice(0,5).map(item=>`<button data-management-open="${escapeHtml(item.workspace)}|${escapeHtml(item.route)}"><span class="management-approval-dot management-approval-dot--${String(item.severity||'Review').toLowerCase()}"></span><div><strong>${escapeHtml(item.title)}</strong><small>${escapeHtml(item.detail)}</small></div><em>${escapeHtml(item.workspace==='internal'?'Internal':'Rental')}</em>${icon('chevron')}</button>`).join('')||'<div class="empty-inline">No review or payment exceptions are currently recorded.</div>'}</div></section><section class="panel"><div class="panel__head"><div><h2>Access boundary</h2><p>Server-enforced access for the authenticated company membership.</p></div>${roleDefinition().view_access?'<button class="text-link" data-route-link="access-roles">View roles →</button>':''}</div><div class="management-access-summary"><div><span>Current role</span><strong>${escapeHtml(roleDefinition().label)}</strong><small>${escapeHtml(roleDefinition().description)}</small></div><div class="management-access-badges">${roleDefinition().workspaces.map(workspace=>`<span>${workspace==='internal'?'IC':workspace==='rental'?'RM':'MG'} · ${workspace}</span>`).join('')}</div></div></section></div>
    </section>`;
  }

  function managementCostTemplate() {
    const ctx = managementCurrentContext();
    if (!ctx) return managementLoadingTemplate('Loading workforce cost…');
    const internal=ctx.internal||{}, rental=ctx.rental||{};
    return `<section class="page management-cost-page"><div class="page-head"><div class="page-head__copy"><span class="eyebrow">Management · Cost Control</span><h1>Workforce Cost</h1><p>Finalized company-employee payroll and supplier manpower settlement cost for the selected period.</p></div><div class="page-head__actions"><button class="btn btn--primary" data-open-report="workforce-cost" data-report-period="${escapeHtml(ctx.periodLabel||state.period)}">Open Report</button></div></div><section class="data-panel"><div class="table-scroll"><table class="data-table"><thead><tr><th>Workforce</th><th>Status</th><th>Headcount</th><th>Gross</th><th>Deductions / Adjustments</th><th>Net Cost</th></tr></thead><tbody><tr><td><strong>Internal Company</strong></td><td>${documentStatusBadge(internal.status||'Not calculated')}</td><td>${Number(internal.employees||0)}</td><td class="num">${formatCurrency(internal.gross||0)}</td><td class="num">${formatCurrency(internal.deductions||0)}</td><td class="num table-money"><strong>${internal.finalized?formatCurrency(internal.net):'—'}</strong></td></tr><tr><td><strong>Rental Manpower</strong></td><td>${rental.finalized?documentStatusBadge('Finalized'):documentStatusBadge('Not finalized')}</td><td>${Number(rental.workers||0)}</td><td class="num">${formatCurrency(rental.gross||0)}</td><td class="num">${formatCurrency(Number(rental.adjustmentDeductions||0)-Number(rental.adjustmentEarnings||0))}</td><td class="num table-money"><strong>${rental.finalized?formatCurrency(rental.net):'—'}</strong></td></tr></tbody></table></div></section><div class="management-cost-rules"><section class="detail-card"><div class="detail-card__head"><h3>Comparison rule</h3></div><p>Combined workforce cost is ${ctx.comparable?`<strong>${formatCurrency(ctx.combined)}</strong>`:'not shown'} because only same-period finalized snapshots may be combined.</p></section><section class="detail-card"><div class="detail-card__head"><h3>Source boundary</h3></div><p>Internal values come from approved payroll snapshots. Rental values come from approved supplier-settlement snapshots.</p></section></div></section>`;
  }

  function managementApprovalsTemplate() {
    const ctx=managementCurrentContext(); if(!ctx)return managementLoadingTemplate('Loading approval center…');
    const all=ctx.approvals||[]; const types=['All','Critical','Review','Payment','Internal Payroll','Rental Settlement','Adjustment'];
    const rows=state.managementApprovalFilter==='All'?all:state.managementApprovalFilter==='Critical'||state.managementApprovalFilter==='Review'?all.filter(item=>item.severity===state.managementApprovalFilter):all.filter(item=>item.type===state.managementApprovalFilter);
    const counts={critical:all.filter(i=>i.severity==='Critical').length,review:all.filter(i=>i.severity==='Review').length,internal:all.filter(i=>i.workspace==='internal').length,rental:all.filter(i=>i.workspace==='rental').length};
    return `<section class="page management-approval-page"><div class="page-head"><div class="page-head__copy"><span class="eyebrow">Management · Controls</span><h1>Approval Center</h1><p>A read-only consolidated queue of real workflow decisions and payment exceptions. Actions remain in each owning workspace.</p></div></div><div class="summary-strip summary-strip--4"><div class="summary-item ${counts.critical?'summary-item--attention':''}"><span>Critical</span><strong>${counts.critical}</strong><small>Payment exceptions</small></div><div class="summary-item"><span>Review queue</span><strong>${counts.review}</strong><small>Controlled next actions</small></div><div class="summary-item"><span>Internal Company</span><strong>${counts.internal}</strong></div><div class="summary-item"><span>Rental Manpower</span><strong>${counts.rental}</strong></div></div><section class="data-panel"><div class="management-approval-filters">${types.map(type=>`<button class="${state.managementApprovalFilter===type?'is-active':''}" data-management-approval-filter="${escapeHtml(type)}">${escapeHtml(type)}<span>${type==='All'?all.length:type==='Critical'?counts.critical:type==='Review'?counts.review:all.filter(item=>item.type===type).length}</span></button>`).join('')}</div><div class="management-approval-list">${rows.length?rows.map(item=>`<article class="management-approval-item management-approval-item--${String(item.severity||'Review').toLowerCase()}"><span class="management-approval-item__mark">${item.severity==='Critical'?'!':'R'}</span><div><div class="management-approval-item__meta"><span>${escapeHtml(item.workspace==='internal'?'Internal Company':'Rental Manpower')}</span><span>${escapeHtml(item.type)}</span><span>${escapeHtml(item.period||'')}</span></div><strong>${escapeHtml(item.title)}</strong><p>${escapeHtml(item.detail)}</p></div><button class="btn btn--secondary btn--sm" data-management-open="${escapeHtml(item.workspace)}|${escapeHtml(item.route)}">Open owning record</button></article>`).join(''):'<div class="table-empty table-empty--card"><strong>No items in this filter.</strong><span>No matching controlled review/payment exceptions are currently recorded.</span></div>'}</div></section></section>`;
  }

  function managementAuditTemplate() {
    const ctx=managementCurrentContext(); if(!ctx)return managementLoadingTemplate('Loading audit trail…');
    const q=state.managementAuditSearch.trim().toLowerCase(); const all=ctx.audit||[];
    const types=['All activity',...new Set(all.map(item=>item.type).filter(Boolean))];
    const rows=all.filter(item=>{const typeMatch=state.managementAuditType==='All activity'||item.type===state.managementAuditType; const text=`${item.workspace} ${item.area||''} ${item.type||''} ${item.period||''} ${item.actor||''} ${item.action||''} ${item.detail||''}`.toLowerCase(); return typeMatch&&(!q||text.includes(q));});
    return `<section class="page management-audit-page"><div class="page-head"><div class="page-head__copy"><span class="eyebrow">Management · Governance</span><h1>Cross-workspace Audit Trail</h1><p>Append-only audit events captured by Django services across Internal Company, Rental Manpower, access, documents and core infrastructure.</p></div></div><section class="data-panel"><div class="table-toolbar"><div class="table-toolbar__search">${icon('search')}<input id="managementAuditSearch" type="search" value="${escapeHtml(state.managementAuditSearch)}" placeholder="Search actor, action, reference…"></div><select class="select" id="managementAuditType">${types.map(type=>`<option ${state.managementAuditType===type?'selected':''}>${escapeHtml(type)}</option>`).join('')}</select><span class="inline-stat"><strong>${rows.length}</strong> events</span></div><div class="management-audit-list">${rows.length?rows.map(item=>`<article class="management-audit-row"><span class="management-audit-row__workspace management-audit-row__workspace--${escapeHtml(item.workspace)}">${item.workspace==='internal'?'IC':item.workspace==='rental'?'RM':'MG'}</span><div class="management-audit-row__copy"><div><strong>${escapeHtml(item.action)}</strong><span>${escapeHtml(item.type||item.area||'Audit')}${item.period?` · ${escapeHtml(item.period)}`:''}</span></div><p>${escapeHtml(item.detail||'No additional record label.')}</p><small>${escapeHtml(item.actor||'System')} · ${escapeHtml(payrollTimestamp(item.date))}</small></div></article>`).join(''):'<div class="table-empty table-empty--card"><strong>No matching audit events.</strong><span>Change the filter to inspect other recorded events.</span></div>'}</div></section></section>`;
  }

  function accessRolesTemplate() {
    const current=roleDefinition();
    const rows=Object.entries(accessRoles);
    return `<section class="page access-roles-page"><div class="page-head"><div class="page-head__copy"><span class="eyebrow">Management · Access Control</span><h1>Workspace Roles & Boundaries</h1><p>Server-enforced company roles separate internal payroll preparation, rental-manpower operations, financial review, payments and read-only oversight.</p></div></div><div class="management-boundary-banner"><span class="management-boundary-banner__icon">${state.accessRole==='owner'?'OW':'AC'}</span><div><strong>Current role: ${escapeHtml(current.label)}</strong><span>${escapeHtml(current.description)}</span></div></div><section class="data-panel"><div class="table-scroll"><table class="data-table role-matrix-table"><thead><tr><th>Role</th><th>Management</th><th>Internal</th><th>Rental</th><th>Edit</th><th>Approve</th><th>Pay</th><th>Settings</th><th>Status</th></tr></thead><tbody>${rows.map(([id,role])=>`<tr class="${state.accessRole===id?'is-current-role':''}"><td><strong>${escapeHtml(role.label)}</strong><small class="table-secondary">${escapeHtml(role.description)}</small></td><td>${role.workspaces.includes('management')?'✓':'—'}</td><td>${role.workspaces.includes('internal')?'✓':'—'}</td><td>${role.workspaces.includes('rental')?'✓':'—'}</td><td>${role.edit.length?escapeHtml(role.edit.map(v=>v==='internal'?'Internal':'Rental').join(' + ')):'Read only'}</td><td>${role.approve?'✓':'—'}</td><td>${role.pay?'✓':'—'}</td><td>${role.settings?'✓':'—'}</td><td>${state.accessRole===id?'<span class="readiness readiness--ready"><span></span>Current</span>':'—'}</td></tr>`).join('')}</tbody></table></div></section><div class="management-cost-rules"><section class="detail-card"><div class="detail-card__head"><h3>Operational separation</h3></div><p>Internal Payroll Officer cannot access rental suppliers/projects. Rental Manpower Officer cannot access internal salary, bank or WPS data.</p></section><section class="detail-card"><div class="detail-card__head"><h3>Review separation</h3></div><p>Finance Reviewer can inspect both workspaces and make controlled approval decisions without operational master-data editing.</p></section><section class="detail-card"><div class="detail-card__head"><h3>Audit separation</h3></div><p>Read-only Auditor is restricted to management, reports and audit history.</p></section></div><div class="source-note">${icon('info')}<span><strong>Authorization boundary.</strong> The visible controls reflect the authenticated company membership. Django permission checks remain authoritative for every backend read and write.</span></div></section>`;
  }

  function overviewTemplate() {
    return state.workspace === 'management' ? managementOverviewTemplate() : state.workspace === 'rental' ? rentalOverviewTemplate() : internalOverviewTemplate();
  }



  function branchEmployeesByDepartment(departmentName) {
    return state.employees.filter(employee => !employee.deleted && !employee.archived && employee.status === 'Active' && employee.department === departmentName);
  }

  function branchEmployees(branchId) {
    return state.employees.filter(employee => !employee.deleted && !employee.archived && employee.branchId === branchId);
  }

  function branchPayrollTotals(branchId) {
    const rows = payrollRowsForDisplay().filter(row => row.branchId === branchId || state.employees.find(employee => employee.id === row.employeeId)?.branchId === branchId);
    return payrollTotals(rows);
  }


  function departmentByName(name) {
    return state.departments.find(item => item.name === name) || null;
  }

  function departmentEmployees(departmentIdOrName) {
    const department = state.departments.find(item => item.id === departmentIdOrName) || departmentByName(departmentIdOrName);
    if (!department) return [];
    return state.employees.filter(employee => !employee.deleted && !employee.archived && (employee.departmentId === department.id || employee.department === department.name));
  }

  function departmentPayrollTotals(departmentIdOrName) {
    const department = state.departments.find(item => item.id === departmentIdOrName) || departmentByName(departmentIdOrName);
    if (!department) return payrollTotals([]);
    const currentIds = new Set(departmentEmployees(department.id).map(employee => employee.id));
    return payrollTotals(payrollRowsForDisplay().filter(row => row.department ? row.department === department.name : currentIds.has(row.employeeId)));
  }

  function employeeOrganizationHistory(employee) {
    const saved = Array.isArray(state.employeeOrganizationHistory?.[employee.id]) ? state.employeeOrganizationHistory[employee.id] : [];
    if (saved.length) return [...saved].sort((a,b) => String(b.effective || '').localeCompare(String(a.effective || '')));
    const branch = state.branches.find(item => item.id === employee.branchId);
    const department = state.departments.find(item => item.id === employee.departmentId) || departmentByName(employee.department);
    if (!employee.joining || !/^\d{4}-\d{2}-\d{2}$/.test(employee.joining)) return [];
    return [{
      id:`${employee.id}-org-initial`, effective: employee.joining,
      branchId:branch?.id || null, branch:branch?.name || employee.branch || 'Branch not set',
      departmentId:department?.id || null, department:department?.name || employee.department || 'Department not set',
      position:employee.position || '—', reason:'Initial organization assignment'
    }];
  }

  function branchDepartmentCount(branchId) {
    return new Set(branchEmployees(branchId).map(employee => employee.departmentId || employee.department).filter(Boolean)).size;
  }

  function branchesTemplate() {
    const q = state.branchSearch.trim().toLowerCase();
    const branchActiveCounts = new Map();
    state.employees.forEach(employee => {
      if (employee.deleted || employee.archived || employee.status !== 'Active' || !employee.branchId) return;
      branchActiveCounts.set(employee.branchId, (branchActiveCounts.get(employee.branchId) || 0) + 1);
    });
    const branches = state.branches.filter(branch => {
      const statusMatch = state.branchStatus === 'All' || branch.status === state.branchStatus;
      const text = `${branch.name} ${branch.code} ${branch.location} ${branch.address} ${branch.manager || ''}`.toLowerCase();
      return statusMatch && (!q || text.includes(q));
    });
    const [branchSortKey, branchSortDirection] = String(state.branchSort || 'code-asc').split('-');
    branches.sort((left, right) => {
      const values = branchSortKey === 'employees'
        ? [branchActiveCounts.get(left.id) || 0, branchActiveCounts.get(right.id) || 0]
        : [String(left[branchSortKey] || '').toLowerCase(), String(right[branchSortKey] || '').toLowerCase()];
      const cmp = typeof values[0] === 'number' ? values[0] - values[1] : values[0].localeCompare(values[1], undefined, { numeric:true, sensitivity:'base' });
      return branchSortDirection === 'desc' ? -cmp : cmp;
    });
    if (!branches.some(item => item.id === state.branchSelectedId)) state.branchSelectedId = branches[0]?.id || '';
    const selected = branches.find(item => item.id === state.branchSelectedId) || branches[0] || null;
    const active = state.branches.filter(branch => branch.status === 'Active').length;
    const activeEmployees = state.employees.filter(employee => employee.status === 'Active');
    const unassigned = state.employees.filter(employee => !employee.branchId).length;
    const selectedEmployees = selected ? branchEmployees(selected.id) : [];
    const selectedTotals = selected ? branchPayrollTotals(selected.id) : payrollTotals([]);
    const selectedReady = selectedEmployees.filter(employee => employee.wps === 'Ready').length;
    return `<section class="page ui-v2-payroll-page ui-v2-prs-internal-page ui-v2-prs-organization-master">
      <div class="page-head ui-v2-page-header ui-v2-payroll-page-head"><div class="page-head__copy ui-v2-page-header__copy"><span class="eyebrow ui-v2-eyebrow">Internal Company · Organization</span><h1 class="ui-v2-title-lg">Branches & Offices</h1><p class="ui-v2-body">Company offices are organization masters for internal employees. Inactive values remain in history but are unavailable for new assignments.</p></div><div class="page-head__actions ui-v2-page-header__actions"><button class="btn btn--secondary" data-route-link="departments">Departments</button><button class="btn btn--primary" data-quick-add="branch">${icon('plus')} Add Branch / Office</button></div></div>
      <div class="summary-strip ui-v2-payroll-summary-strip"><div class="summary-item ui-v2-payroll-metric"><span>Branches / offices</span><strong>${state.branches.length}</strong><small>${active} active</small></div><div class="summary-item ui-v2-payroll-metric"><span>Employees assigned</span><strong>${state.employees.filter(employee=>!employee.deleted).length - unassigned}</strong><small>${unassigned ? `${unassigned} need branch assignment` : 'All current employee masters assigned'}</small></div><div class="summary-item ui-v2-payroll-metric"><span>Largest branch</span><strong>${Math.max(0, ...branchActiveCounts.values())}</strong><small>Active employees</small></div><div class="summary-item ui-v2-payroll-metric"><span>Master policy</span><strong>Reversible cascade</strong><small>Archive or 30-day Delete</small></div></div>
      <section class="ui-v2-payroll-panel ui-v2-prs-master-filter"><div class="ui-v2-payroll-register__toolbar"><div class="table-toolbar__search ui-v2-filter-bar__search">${icon('search')}<input id="branchSearch" class="ui-v2-input" type="search" value="${escapeHtml(state.branchSearch)}" placeholder="Search branch, code, city, manager or address"></div><select id="branchStatusFilter" class="ui-v2-select ui-v2-payroll-operational-select" aria-label="Filter branch status">${['All','Active','Inactive','Archived'].map(status => `<option value="${status}" ${state.branchStatus === status ? 'selected' : ''}>${status === 'All' ? 'All statuses' : status}</option>`).join('')}</select><select id="branchSortFilter" class="ui-v2-select ui-v2-payroll-operational-select" aria-label="Sort branches"><option value="code-asc" ${state.branchSort==='code-asc'?'selected':''}>Code A–Z</option><option value="name-asc" ${state.branchSort==='name-asc'?'selected':''}>Name A–Z</option><option value="name-desc" ${state.branchSort==='name-desc'?'selected':''}>Name Z–A</option><option value="employees-desc" ${state.branchSort==='employees-desc'?'selected':''}>Most employees</option></select>${state.branchSearch || state.branchStatus !== 'Active' || state.branchSort !== 'code-asc' ? '<button class="btn btn--secondary btn--sm" type="button" data-branch-reset>Reset</button>' : ''}</div></section>
      ${branches.length ? `<div class="ui-v2-payroll-master-grid">
        <section class="ui-v2-payroll-panel ui-v2-payroll-master-list"><header><div><span>Organization</span><h2>Branch / office directory</h2></div><button class="btn btn--ghost btn--sm" data-quick-add="branch">${icon('plus')} Add</button></header><div class="ui-v2-payroll-list">${branches.map(branch => { const activeCount=branchActiveCounts.get(branch.id)||0; return `<button type="button" data-select-branch="${escapeHtml(branch.id)}" class="${selected?.id === branch.id ? 'is-selected' : ''}"><span class="ui-v2-payroll-list__icon">${icon('branch')}</span><span class="ui-v2-payroll-list__copy"><strong>${escapeHtml(branch.name)}</strong><small>${escapeHtml(branch.code)} · ${escapeHtml(branch.type || 'Branch')} · ${escapeHtml(branch.location || 'Location not set')}${branch.status !== 'Active' ? ` · ${escapeHtml(branch.status)}` : ''}</small></span><span class="ui-v2-payroll-list__value"><strong>${activeCount}</strong><small>employees</small></span>${icon('chevron')}</button>`; }).join('')}</div></section>
        <section class="ui-v2-payroll-panel ui-v2-payroll-master-detail"><header><div><span>${escapeHtml(selected.code)}</span><h2>${escapeHtml(selected.name)}</h2></div>${statusBadge(selected.status)}</header><div class="ui-v2-payroll-master-detail__hero"><span>${icon('branch')}</span><div><strong>${escapeHtml(selected.name)}</strong><small>${escapeHtml(selected.location || 'Location not set')}</small></div></div><div class="ui-v2-payroll-master-detail__stats"><div><span>Active employees</span><strong>${selectedEmployees.filter(employee=>employee.status==='Active').length}</strong></div><div><span>Departments represented</span><strong>${branchDepartmentCount(selected.id)}</strong></div><div><span>WPS ready</span><strong>${selectedReady}/${selectedEmployees.length}</strong></div><div><span>${escapeHtml(state.period)} net</span><strong>${formatCurrency(selectedTotals.net || 0)}</strong></div></div><div class="ui-v2-payroll-master-detail__actions"><button class="btn btn--primary btn--sm" data-open-branch="${escapeHtml(selected.id)}">Open branch</button><button class="btn btn--secondary btn--sm" data-branch-employees-filter="${escapeHtml(selected.id)}">View employees</button>${lifecycleActionsMenu([{label:'Edit branch / office',hint:'Update current master details',iconName:'edit',attrs:`data-edit-branch="${escapeHtml(selected.id)}"`},'separator',{label:selected.archived?'Restore from archive':'Archive branch / office',hint:selected.archived?'Restore previous state':'Archive branch / office and current employee scope',iconName:'info',attrs:`data-organization-lifecycle="branch|${escapeHtml(selected.id)}|${selected.archived?'restore':'archive'}"`},{label:'Delete',hint:'Delete with 30-day recovery; current employee scope follows automatically',iconName:'trash',danger:true,attrs:`data-organization-lifecycle="branch|${escapeHtml(selected.id)}|delete"`}],{compact:true})}</div></section>
      </div>` : `<section class="ui-v2-payroll-panel"><div class="table-empty table-empty--card"><strong>No branches match these filters.</strong><span>Change the search/status filter or add a new office master.</span><button class="btn btn--primary btn--sm" data-quick-add="branch">Add Branch / Office</button></div></section>`}
      <div class="source-banner ui-v2-payroll-source-note">${icon('info')}<span>Branches and offices are company-controlled masters. Moving an employee creates effective-dated organization history rather than rewriting prior payroll context.</span></div>
    </section>`;
  }

  function branchProfileTemplate(branch) {
    if (!branch) return `<section class="page"><div class="placeholder"><div class="placeholder__inner"><h2>Branch not found</h2><button class="btn btn--secondary" data-route-link="branches">Back to Branches</button></div></div></section>`;
    const employees = branchEmployees(branch.id);
    const departmentRows = state.departments.map(department=>({department,employees:employees.filter(item=>item.departmentId===department.id || item.department===department.name)})).filter(row=>row.employees.length);
    const totals = branchPayrollTotals(branch.id);
    const wpsReady = employees.filter(item=>item.wps==='Ready').length;
    const activeEmployees = employees.filter(item=>item.status==='Active');
    const timesheetRecord = state.timesheets?.[state.internalTimesheetPeriod || state.period] || {};
    const attendanceEntered = employees.filter(employee=>timesheetRecord[employee.id]).length;
    const tab = state.branchTab;
    let content = '';
    if (tab === 'employees') {
      content = `<section class="data-panel"><div class="section-headline"><div><h2>Employees in ${escapeHtml(branch.name)}</h2><p>Branch membership is organizational—not a project assignment.</p></div><button class="btn btn--primary btn--sm" data-quick-add="internal-employee" data-employee-branch-context="${escapeHtml(branch.id)}">${icon('plus')} Add Employee</button></div><div class="table-scroll"><table class="data-table"><thead><tr><th>Employee</th><th>Position</th><th>Department</th><th>Salary Setup</th><th>WPS</th><th>Status</th><th></th></tr></thead><tbody>${employees.length?employees.map(employee=>`<tr><td><button class="entity-link entity-link--stack" data-open-employee="${escapeHtml(employee.id)}"><strong>${escapeHtml(employee.name)}</strong><span>EMP ${escapeHtml(employee.employeeId)}</span></button></td><td>${escapeHtml(employee.position)}</td><td>${departmentByName(employee.department)?`<button class="entity-link" data-open-department="${escapeHtml(employee.departmentId || departmentByName(employee.department)?.id)}">${escapeHtml(employee.department)}</button>`:escapeHtml(employee.department)}</td><td>${employeeProfileData(employee).salary?'<span class="readiness readiness--ready"><span></span>Configured</span>':'<span class="readiness readiness--warn"><span></span>Needs setup</span>'}</td><td>${employeeWpsBadge(employee.wps)}</td><td>${statusBadge(employee.status)}</td><td><button class="icon-btn icon-btn--sm" data-change-employee-organization="${escapeHtml(employee.id)}" title="Change branch / department">${icon('edit')}</button></td></tr>`).join(''):`<tr><td colspan="7"><div class="table-empty"><strong>No employees in this branch.</strong><span>Add or transfer an internal employee here.</span></div></td></tr>`}</tbody></table></div></section>`;
    } else if (tab === 'departments') {
      content = `<section class="data-panel"><div class="section-headline"><div><h2>Departments represented</h2><p>Department masters are reusable across multiple offices.</p></div><button class="btn btn--secondary btn--sm" data-quick-add="department">${icon('plus')} Add Department</button></div><div class="department-card-grid">${departmentRows.length?departmentRows.map(({department,employees:rows})=>{const deptTotals=departmentPayrollTotals(department.id);return `<button class="department-card organization-department-card" data-open-department="${escapeHtml(department.id)}"><span>${icon('department')}</span><div><strong>${escapeHtml(department.name)}</strong><small>${rows.length} employee${rows.length===1?'':'s'} in this branch · ${formatCurrency(deptTotals.net||0)} total dept net</small></div>${icon('chevron')}</button>`}).join(''):`<div class="table-empty table-empty--card"><strong>No represented departments</strong><span>Add employees or change their organization assignment.</span></div>`}</div></section>`;
    } else if (tab === 'attendance') {
      content = `<div class="profile-grid profile-grid--wide-side"><section class="panel panel--flush"><div class="section-headline"><div><h2>${escapeHtml(state.internalTimesheetPeriod || state.period)} attendance</h2><p>Branch-scoped view of internal attendance readiness.</p></div><button class="btn btn--primary btn--sm" data-open-branch-timesheet="${escapeHtml(branch.id)}">Open Attendance</button></div><div class="project-kpis internal-kpis"><div><span>Employees</span><strong>${employees.length}</strong><small>${activeEmployees.length} active</small></div><div><span>Attendance entered</span><strong>${attendanceEntered}/${employees.length}</strong><small>Current internal timesheet</small></div><div><span>Timesheet status</span><strong>${escapeHtml(timesheetStatus())}</strong><small>Company-wide period status</small></div><div><span>Branch WPS ready</span><strong>${wpsReady}/${employees.length}</strong><small>Bank/identity setup</small></div></div></section><aside class="detail-card"><div class="detail-card__head"><h3>Branch payroll control</h3></div><p>Attendance is filtered by branch, but approval remains part of the controlled internal-company timesheet and payroll period.</p></aside></div>`;
    } else if (tab === 'payroll') {
      content = `<section class="panel panel--flush"><div class="panel__head panel__head--padded"><div><h2>${escapeHtml(state.period)} branch payroll</h2><p>Internal salary totals grouped by company branch.</p></div><button class="btn btn--secondary btn--sm" data-open-branch-payroll="${escapeHtml(branch.id)}">Open Payroll Run</button></div><div class="project-kpis internal-kpis"><div><span>Employees</span><strong>${employees.length}</strong></div><div><span>Gross payroll</span><strong>${formatCurrency(totals.gross||0)}</strong></div><div><span>Deductions</span><strong>${formatCurrency((totals.advances||0)+(totals.deductions||0))}</strong></div><div><span>Net payable</span><strong>${formatCurrency(totals.net||0)}</strong></div></div></section>`;
    } else if (tab === 'documents') {
      content = `<section class="data-panel"><div class="section-headline"><div><h2>Branch payroll documents</h2><p>Salary slips and internal-company documents remain employee/payroll records but can be reviewed by branch.</p></div><button class="btn btn--secondary btn--sm" data-route-link="documents">Open Document Center</button></div><div class="document-grid"><button class="document-tile" data-route-link="documents"><span>SL</span><div><strong>Salary Slips</strong><small>${employees.length} branch employees</small></div><em>Internal</em>${icon('chevron')}</button><button class="document-tile" data-route-link="bank-export"><span>BK</span><div><strong>Bank / WPS Export</strong><small>${wpsReady}/${employees.length} WPS-ready employees</small></div><em>Payment</em>${icon('chevron')}</button></div></section>`;
    } else {
      content = `<div class="profile-grid profile-grid--overview"><div class="profile-main-stack"><section class="panel panel--flush"><div class="panel__head panel__head--padded"><div><h2>Organization snapshot</h2><p>Employees and departments attached to this company office.</p></div></div><div class="project-kpis internal-kpis"><div><span>Employees</span><strong>${employees.length}</strong><small>${activeEmployees.length} active</small></div><div><span>Departments</span><strong>${departmentRows.length}</strong><small>Represented in this branch</small></div><div><span>WPS ready</span><strong>${wpsReady}/${employees.length}</strong><small>Bank / identity readiness</small></div><div><span>Net payroll</span><strong>${formatCurrency(totals.net||0)}</strong><small>${escapeHtml(state.period)}</small></div></div></section><section class="panel panel--flush"><div class="panel__head panel__head--padded"><div><h2>Department mix</h2><p>Current employee-master assignments.</p></div></div><div class="composition-block">${departmentRows.length?departmentRows.map(({department,employees:rows})=>{const pct=employees.length?Math.round(rows.length/employees.length*100):0;return `<div class="composition-row"><button class="text-link" data-open-department="${escapeHtml(department.id)}">${escapeHtml(department.name)}</button><div><i style="width:${pct}%"></i></div><strong>${rows.length}</strong></div>`}).join(''):'<div class="empty-inline">No employees assigned yet.</div>'}</div></section></div><aside class="profile-side-stack"><section class="detail-card"><div class="detail-card__head"><h3>Branch details</h3><button class="text-link" data-edit-branch="${escapeHtml(branch.id)}">Edit</button></div><dl class="detail-list"><div><dt>Code</dt><dd>${escapeHtml(branch.code)}</dd></div><div><dt>Type</dt><dd>${escapeHtml(branch.type||'Branch')}</dd></div><div><dt>Location</dt><dd>${escapeHtml(branch.location)}</dd></div><div><dt>Address</dt><dd>${escapeHtml(branch.address||'—')}</dd></div><div><dt>Manager</dt><dd>${escapeHtml(branch.manager||'—')}</dd></div><div><dt>Status</dt><dd>${escapeHtml(branch.status)}</dd></div>${branch.archivedReason?`<div><dt>Archive reason</dt><dd>${escapeHtml(branch.archivedReason)}</dd></div>`:''}</dl></section><section class="detail-card"><div class="detail-card__head"><h3>Quick actions</h3></div><div class="stack-actions"><button data-open-branch-timesheet="${escapeHtml(branch.id)}">Attendance & OT ${icon('chevron')}</button><button data-open-branch-payroll="${escapeHtml(branch.id)}">Branch Payroll ${icon('chevron')}</button><button data-route-link="bank-export">Bank / WPS ${icon('chevron')}</button></div></section></aside></div>`;
    }
    return `<section class="page branch-profile-page ui-v2-payroll-page ui-v2-payroll-employee-profile ui-v2-prs-internal-page"><div class="profile-crumb ui-v2-payroll-profile-crumb"><button class="text-link text-link--muted" data-route-link="branches">Branches & Offices</button><span>›</span><span>${escapeHtml(branch.code)}</span></div><header class="entity-header"><div class="entity-header__identity"><span class="entity-avatar entity-avatar--project">${icon('branch')}</span><div><div class="entity-title-row ui-v2-payroll-entity-title"><h1>${escapeHtml(branch.name)}</h1>${statusBadge(branch.status)}</div><div class="entity-subline"><span>${escapeHtml(branch.code)}</span><span>·</span><span>${escapeHtml(branch.location)}</span><span>·</span><span>${employees.length} employees</span></div></div></div><div class="entity-header__actions ui-v2-payroll-entity-header__actions">${branch.status==='Active'?`<button class="btn btn--primary" data-quick-add="internal-employee" data-employee-branch-context="${escapeHtml(branch.id)}">${icon('plus')} Add Employee</button>`:''}${lifecycleActionsMenu([{label:'Edit branch / office',hint:'Update the current organization master',iconName:'edit',attrs:`data-edit-branch="${escapeHtml(branch.id)}"`},'separator',{label:branch.archived?'Restore from archive':'Archive branch / office',hint:branch.archived?'Restore previous state':'Archive branch and current employee scope',iconName:'info',attrs:`data-organization-lifecycle="branch|${escapeHtml(branch.id)}|${branch.archived?'restore':'archive'}"`},{label:'Delete',hint:'Delete with 30-day recovery; current employee scope follows automatically',iconName:'trash',danger:true,attrs:`data-organization-lifecycle="branch|${escapeHtml(branch.id)}|delete"`}])}</div></header><nav class="tabs profile-tabs">${[['overview','Overview'],['employees','Employees'],['departments','Departments'],['attendance','Attendance & OT'],['payroll','Payroll'],['documents','Documents']].map(([id,label])=>`<button data-branch-tab="${id}" class="${tab===id?'is-active':''}">${label}</button>`).join('')}</nav><div class="profile-content ui-v2-payroll-profile-content">${content}</div><div class="source-banner ui-v2-payroll-source-note">${icon('info')}<span>Branch assignments are effective-dated internal organization records and remain separate from rental project assignments.</span></div></section>`;
  }

  function departmentsTemplate() {
    const q = state.departmentSearch.trim().toLowerCase();
    const departmentActiveCounts = new Map();
    state.employees.forEach(employee => {
      if (employee.deleted || employee.archived || employee.status !== 'Active') return;
      const key = employee.departmentId || departmentByName(employee.department)?.id;
      if (key) departmentActiveCounts.set(key, (departmentActiveCounts.get(key) || 0) + 1);
    });
    const departments = state.departments.filter(item => {
      const statusMatch = state.departmentStatus === 'All' || item.status === state.departmentStatus;
      return statusMatch && (!q || `${item.name} ${item.code} ${item.notes || ''}`.toLowerCase().includes(q));
    });
    const [departmentSortKey, departmentSortDirection] = String(state.departmentSort || 'code-asc').split('-');
    departments.sort((left, right) => {
      const values = departmentSortKey === 'employees'
        ? [departmentActiveCounts.get(left.id) || 0, departmentActiveCounts.get(right.id) || 0]
        : [String(left[departmentSortKey] || '').toLowerCase(), String(right[departmentSortKey] || '').toLowerCase()];
      const cmp = typeof values[0] === 'number' ? values[0] - values[1] : values[0].localeCompare(values[1], undefined, { numeric:true, sensitivity:'base' });
      return departmentSortDirection === 'desc' ? -cmp : cmp;
    });
    if (!departments.some(item => item.id === state.departmentSelectedId)) state.departmentSelectedId = departments[0]?.id || '';
    const selected = departments.find(item => item.id === state.departmentSelectedId) || departments[0] || null;
    const active = state.departments.filter(item=>item.status==='Active').length;
    const assigned = state.employees.filter(item=>item.department).length;
    const counts = [...departmentActiveCounts.values()];
    const selectedEmployees = selected ? departmentEmployees(selected.id) : [];
    const selectedBranches = new Set(selectedEmployees.map(employee=>employee.branchId).filter(Boolean)).size;
    const selectedTotals = selected ? departmentPayrollTotals(selected.id) : payrollTotals([]);
    return `<section class="page ui-v2-payroll-page ui-v2-prs-internal-page ui-v2-prs-organization-master">
      <div class="page-head ui-v2-page-header ui-v2-payroll-page-head"><div class="page-head__copy ui-v2-page-header__copy"><span class="eyebrow ui-v2-eyebrow">Internal Company · Organization</span><h1 class="ui-v2-title-lg">Departments</h1><p class="ui-v2-body">Departments are published organization masters used across employee assignment, filtering and reporting. Inactive values remain available to historical records.</p></div><div class="page-head__actions ui-v2-page-header__actions"><button class="btn btn--secondary" data-route-link="branches">Branches & Offices</button><button class="btn btn--primary" data-quick-add="department">${icon('plus')} Add Department</button></div></div>
      <div class="summary-strip ui-v2-payroll-summary-strip"><div class="summary-item ui-v2-payroll-metric"><span>Departments</span><strong>${state.departments.length}</strong><small>${active} active</small></div><div class="summary-item ui-v2-payroll-metric"><span>Employees assigned</span><strong>${assigned}</strong><small>Internal company records</small></div><div class="summary-item ui-v2-payroll-metric"><span>Largest department</span><strong>${Math.max(0,...counts)}</strong><small>Active employees</small></div><div class="summary-item ui-v2-payroll-metric"><span>Master policy</span><strong>Deactivate</strong><small>No destructive delete of referenced values</small></div></div>
      <section class="ui-v2-payroll-panel ui-v2-prs-master-filter"><div class="ui-v2-payroll-register__toolbar"><div class="table-toolbar__search ui-v2-filter-bar__search">${icon('search')}<input id="departmentSearch" class="ui-v2-input" type="search" value="${escapeHtml(state.departmentSearch)}" placeholder="Search department, code or notes"></div><select id="departmentStatusFilter" class="ui-v2-select ui-v2-payroll-operational-select" aria-label="Filter department status">${['All','Active','Inactive','Archived'].map(status => `<option value="${status}" ${state.departmentStatus === status ? 'selected' : ''}>${status === 'All' ? 'All statuses' : status}</option>`).join('')}</select><select id="departmentSortFilter" class="ui-v2-select ui-v2-payroll-operational-select" aria-label="Sort departments"><option value="code-asc" ${state.departmentSort==='code-asc'?'selected':''}>Code A–Z</option><option value="name-asc" ${state.departmentSort==='name-asc'?'selected':''}>Name A–Z</option><option value="name-desc" ${state.departmentSort==='name-desc'?'selected':''}>Name Z–A</option><option value="employees-desc" ${state.departmentSort==='employees-desc'?'selected':''}>Most employees</option></select>${state.departmentSearch || state.departmentStatus !== 'Active' || state.departmentSort !== 'code-asc' ? '<button class="btn btn--secondary btn--sm" type="button" data-department-reset>Reset</button>' : ''}</div></section>
      ${departments.length ? `<div class="ui-v2-payroll-master-grid"><section class="ui-v2-payroll-panel ui-v2-payroll-master-list"><header><div><span>Organization</span><h2>Department directory</h2></div><button class="btn btn--ghost btn--sm" data-quick-add="department">${icon('plus')} Add</button></header><div class="ui-v2-payroll-list">${departments.map(department => { const count=departmentActiveCounts.get(department.id)||0; return `<button type="button" data-select-department="${escapeHtml(department.id)}" class="${selected?.id === department.id ? 'is-selected' : ''}"><span class="ui-v2-payroll-list__icon">${icon('department')}</span><span class="ui-v2-payroll-list__copy"><strong>${escapeHtml(department.name)}</strong><small>${escapeHtml(department.code)} · Internal Company${department.status !== 'Active' ? ` · ${escapeHtml(department.status)}` : ''}</small></span><span class="ui-v2-payroll-list__value"><strong>${count}</strong><small>employees</small></span>${icon('chevron')}</button>`; }).join('')}</div></section><section class="ui-v2-payroll-panel ui-v2-payroll-master-detail"><header><div><span>${escapeHtml(selected.code)}</span><h2>${escapeHtml(selected.name)}</h2></div>${statusBadge(selected.status)}</header><div class="ui-v2-payroll-master-detail__hero"><span>${icon('department')}</span><div><strong>${escapeHtml(selected.name)}</strong><small>Internal Company organization department</small></div></div><div class="ui-v2-payroll-master-detail__stats"><div><span>Active employees</span><strong>${selectedEmployees.filter(employee=>employee.status==='Active').length}</strong></div><div><span>Branches represented</span><strong>${selectedBranches}</strong></div><div><span>Total records</span><strong>${selectedEmployees.length}</strong></div><div><span>${escapeHtml(state.period)} net</span><strong>${formatCurrency(selectedTotals.net || 0)}</strong></div></div><div class="ui-v2-payroll-master-detail__actions"><button class="btn btn--primary btn--sm" data-open-department="${escapeHtml(selected.id)}">Open department</button><button class="btn btn--secondary btn--sm" data-department-employees-filter="${escapeHtml(selected.id)}">Open employees</button>${lifecycleActionsMenu([{label:'Edit department',hint:'Update the current department master',iconName:'edit',attrs:`data-edit-department="${escapeHtml(selected.id)}"`},'separator',{label:selected.archived?'Restore from archive':'Archive department',hint:selected.archived?'Restore previous state':'Archive department and current employee scope',iconName:'info',attrs:`data-organization-lifecycle="department|${escapeHtml(selected.id)}|${selected.archived?'restore':'archive'}"`},{label:'Delete',hint:'Delete with 30-day recovery; current employee scope follows automatically',iconName:'trash',danger:true,attrs:`data-organization-lifecycle="department|${escapeHtml(selected.id)}|delete"`}],{compact:true})}</div></section></div>` : `<section class="ui-v2-payroll-panel"><div class="table-empty table-empty--card"><strong>No departments match these filters.</strong><span>Change the search/status filter or add a department master.</span><button class="btn btn--primary btn--sm" data-quick-add="department">Add Department</button></div></section>`}
      <div class="source-banner ui-v2-payroll-source-note">${icon('info')}<span>Department edits affect the current master only; employee organization history and closed payroll snapshots remain attributable to their original effective records.</span></div>
    </section>`;
  }

  function departmentProfileTemplate(department) {
    if (!department) return `<section class="page"><div class="placeholder"><div class="placeholder__inner"><h2>Department not found</h2><button class="btn btn--secondary" data-route-link="departments">Back to Departments</button></div></div></section>`;
    const employees = departmentEmployees(department.id);
    const branchRows = state.branches.map(branch=>({branch,employees:employees.filter(employee=>employee.branchId===branch.id)})).filter(row=>row.employees.length);
    const totals = departmentPayrollTotals(department.id);
    const ready = employees.filter(employee=>employee.wps==='Ready').length;
    const salaryReady = employees.filter(employee=>!!employeeProfileData(employee).salary).length;
    const tab = state.departmentTab;
    let content='';
    if (tab==='employees') {
      content=`<section class="data-panel"><div class="section-headline"><div><h2>${escapeHtml(department.name)} employees</h2><p>Employees across every branch using this department master.</p></div><button class="btn btn--primary btn--sm" data-quick-add="internal-employee" data-employee-department-context="${escapeHtml(department.id)}">${icon('plus')} Add Employee</button></div><div class="table-scroll"><table class="data-table"><thead><tr><th>Employee</th><th>Position</th><th>Branch / Office</th><th>Salary Setup</th><th>WPS</th><th>Status</th><th></th></tr></thead><tbody>${employees.length?employees.map(employee=>`<tr><td><button class="entity-link entity-link--stack" data-open-employee="${escapeHtml(employee.id)}"><strong>${escapeHtml(employee.name)}</strong><span>EMP ${escapeHtml(employee.employeeId)}</span></button></td><td>${escapeHtml(employee.position)}</td><td>${employee.branchId?`<button class="entity-link" data-open-branch="${escapeHtml(employee.branchId)}">${escapeHtml(employee.branch)}</button>`:'—'}</td><td>${employeeProfileData(employee).salary?'<span class="readiness readiness--ready"><span></span>Configured</span>':'<span class="readiness readiness--warn"><span></span>Needs setup</span>'}</td><td>${employeeWpsBadge(employee.wps)}</td><td>${statusBadge(employee.status)}</td><td><button class="icon-btn icon-btn--sm" data-change-employee-organization="${escapeHtml(employee.id)}">${icon('edit')}</button></td></tr>`).join(''):`<tr><td colspan="7"><div class="table-empty"><strong>No employees in this department.</strong><span>Add a company employee or change an existing employee's department.</span></div></td></tr>`}</tbody></table></div></section>`;
    } else if (tab==='branches') {
      content=`<section class="data-panel"><div class="section-headline"><div><h2>Branch representation</h2><p>Where this department currently has employees.</p></div></div><div class="department-card-grid">${branchRows.length?branchRows.map(({branch,employees:rows})=>`<button class="department-card" data-open-branch="${escapeHtml(branch.id)}"><span>${icon('branch')}</span><div><strong>${escapeHtml(branch.name)}</strong><small>${rows.length} ${escapeHtml(department.name)} employee${rows.length===1?'':'s'}</small></div>${icon('chevron')}</button>`).join(''):`<div class="table-empty table-empty--card"><strong>Not represented in any branch</strong><span>This master remains available for future employees.</span></div>`}</div></section>`;
    } else if (tab==='payroll') {
      content=`<section class="panel panel--flush"><div class="panel__head panel__head--padded"><div><h2>${escapeHtml(state.period)} department payroll</h2><p>Company payroll aggregated across every branch for this department.</p></div><button class="btn btn--secondary btn--sm" data-open-department-payroll="${escapeHtml(department.id)}">Open Payroll Run</button></div><div class="project-kpis internal-kpis"><div><span>Employees</span><strong>${employees.length}</strong></div><div><span>Gross payroll</span><strong>${formatCurrency(totals.gross||0)}</strong></div><div><span>Deductions</span><strong>${formatCurrency((totals.advances||0)+(totals.deductions||0))}</strong></div><div><span>Net payable</span><strong>${formatCurrency(totals.net||0)}</strong></div></div></section>`;
    } else {
      content=`<div class="profile-grid profile-grid--overview"><div class="profile-main-stack"><section class="panel panel--flush"><div class="panel__head panel__head--padded"><div><h2>Department snapshot</h2><p>Cross-branch internal-company organization view.</p></div></div><div class="project-kpis internal-kpis"><div><span>Employees</span><strong>${employees.length}</strong><small>${employees.filter(item=>item.status==='Active').length} active</small></div><div><span>Branches</span><strong>${branchRows.length}</strong><small>Currently represented</small></div><div><span>Salary setup</span><strong>${salaryReady}/${employees.length}</strong><small>Configured structures</small></div><div><span>WPS ready</span><strong>${ready}/${employees.length}</strong><small>Payment-data readiness</small></div></div></section><section class="panel panel--flush"><div class="panel__head panel__head--padded"><div><h2>Branch distribution</h2><p>Employees grouped by office.</p></div></div><div class="composition-block">${branchRows.length?branchRows.map(({branch,employees:rows})=>{const pct=employees.length?Math.round(rows.length/employees.length*100):0;return `<div class="composition-row"><button class="text-link" data-open-branch="${escapeHtml(branch.id)}">${escapeHtml(branch.name)}</button><div><i style="width:${pct}%"></i></div><strong>${rows.length}</strong></div>`}).join(''):'<div class="empty-inline">No employee assignments yet.</div>'}</div></section></div><aside class="profile-side-stack"><section class="detail-card"><div class="detail-card__head"><h3>Department details</h3><button class="text-link" data-edit-department="${escapeHtml(department.id)}">Edit</button></div><dl class="detail-list"><div><dt>Code</dt><dd>${escapeHtml(department.code)}</dd></div><div><dt>Status</dt><dd>${escapeHtml(department.status)}</dd></div>${department.archivedReason?`<div><dt>Archive reason</dt><dd>${escapeHtml(department.archivedReason)}</dd></div>`:''}<div><dt>Employees</dt><dd>${employees.length}</dd></div><div><dt>Current net payroll</dt><dd>${formatCurrency(totals.net||0)}</dd></div></dl>${department.notes?`<p class="organization-notes">${escapeHtml(department.notes)}</p>`:''}</section></aside></div>`;
    }
    return `<section class="page department-profile-page ui-v2-payroll-page ui-v2-payroll-employee-profile ui-v2-prs-internal-page"><div class="profile-crumb ui-v2-payroll-profile-crumb"><button class="text-link text-link--muted" data-route-link="departments">Departments</button><span>›</span><span>${escapeHtml(department.code)}</span></div><header class="entity-header"><div class="entity-header__identity"><span class="entity-avatar entity-avatar--supplier">${icon('department')}</span><div><div class="entity-title-row ui-v2-payroll-entity-title"><h1>${escapeHtml(department.name)}</h1>${statusBadge(department.status)}</div><div class="entity-subline"><span>${escapeHtml(department.code)}</span><span>·</span><span>${employees.length} employees</span><span>·</span><span>${branchRows.length} branches</span></div></div></div><div class="entity-header__actions ui-v2-payroll-entity-header__actions">${department.status==='Active'?`<button class="btn btn--primary" data-quick-add="internal-employee" data-employee-department-context="${escapeHtml(department.id)}">${icon('plus')} Add Employee</button>`:''}${lifecycleActionsMenu([{label:'Edit department',hint:'Update the current organization master',iconName:'edit',attrs:`data-edit-department="${escapeHtml(department.id)}"`},'separator',{label:department.archived?'Restore from archive':'Archive department',hint:department.archived?'Restore previous state':'Archive department and current employee scope',iconName:'info',attrs:`data-organization-lifecycle="department|${escapeHtml(department.id)}|${department.archived?'restore':'archive'}"`},{label:'Delete',hint:'Delete with 30-day recovery; current employee scope follows automatically',iconName:'trash',danger:true,attrs:`data-organization-lifecycle="department|${escapeHtml(department.id)}|delete"`}])}</div></header><nav class="tabs profile-tabs">${[['overview','Overview'],['employees','Employees'],['branches','Branches'],['payroll','Payroll']].map(([id,label])=>`<button data-department-tab="${id}" class="${tab===id?'is-active':''}">${label}</button>`).join('')}</nav><div class="profile-content ui-v2-payroll-profile-content">${content}</div><div class="source-banner ui-v2-payroll-source-note">${icon('info')}<span>Department changes do not rewrite historical payroll snapshots or organization audit events.</span></div></section>`;
  }

  function employeeWpsBadge(value) {
    if (value === 'Ready') return `<span class="readiness readiness--ready"><span></span>WPS ready</span>`;
    if (value === 'Needs setup') return `<span class="readiness readiness--warn"><span></span>Needs setup</span>`;
    return `<span class="readiness readiness--neutral"><span></span>No supplied record</span>`;
  }

  function employeeLifecycleActions(employee) {
    if (!employee || employee.archived) return [];
    if (employee.status === 'Active') return [
      { value:'leave', label:'Put employee on leave' },
      { value:'deactivate', label:'Stop activity (temporary)' },
      { value:'terminate', label:'Terminate employment' }
    ];
    if (employee.status === 'On Leave') return [
      { value:'activate', label:'Return employee to Active' },
      { value:'deactivate', label:'Stop activity (temporary)' },
      { value:'terminate', label:'Terminate employment' }
    ];
    if (employee.status === 'Inactive') return [
      { value:'activate', label:'Reactivate employee' },
      { value:'terminate', label:'Terminate employment' }
    ];
    return [];
  }

  function employeeLifecycleBanner(employee) {
    if (!employee) return '';
    if (employee.archived) return `<div class="employee-lifecycle-banner is-archived">${icon('info')}<span><strong>Archived employee record</strong>${escapeHtml(employee.archivedReason || 'Removed from current employee registers while payroll history remains available.')} ${employee.archivedAt ? `Archived ${escapeHtml(payrollTimestamp(employee.archivedAt))}.` : ''}</span><button class="text-link" data-employee-record-action="restore">Restore from archive</button></div>`;
    if (employee.status === 'Terminated') return `<div class="employee-lifecycle-banner is-stopped">${icon('info')}<span><strong>Employment ended${employee.employmentEnd ? ` · ${escapeHtml(employee.employmentEnd)}` : ''}</strong>This master remains available for payroll, payment and document history. Use Actions to archive it or delete it with a 30-day recovery window.</span></div>`;
    if (employee.status === 'Inactive') return `<div class="employee-lifecycle-banner is-stopped">${icon('info')}<span><strong>Employee inactive</strong>Inactive employees are excluded from new attendance/payroll eligibility. Use Employment to reactivate or terminate; use Actions for Archive or Delete.</span><button class="text-link" data-employee-lifecycle>Manage employment</button></div>`;
    if (employee.status === 'On Leave') return `<div class="employee-lifecycle-banner">${icon('info')}<span><strong>Employee on leave</strong>The employee remains employed. Attendance can record leave while the employee is outside normal active work.</span><button class="text-link" data-employee-lifecycle>Manage employment</button></div>`;
    return '';
  }

  function getFilteredEmployees() {
    const q = state.employeeSearch.trim().toLowerCase();
    return state.employees.filter(employee => {
      if (employee.deleted) return false;
      const archiveMatch = state.employeeStatus === 'Archived' ? !!employee.archived : !employee.archived;
      const statusMatch = state.employeeStatus === 'All' || state.employeeStatus === 'Archived' || employee.status === state.employeeStatus;
      const branchMatch = state.employeeBranch === 'All branches' || employee.branch === state.employeeBranch;
      const departmentMatch = state.employeeDepartment === 'All departments' || employee.department === state.employeeDepartment;
      const wpsMatch = state.employeeWps === 'All' || (state.employeeWps === 'WPS ready' ? employee.wps === 'Ready' : employee.wps !== 'Ready');
      const text = `${employee.employeeId} ${employee.name} ${employee.position} ${employee.department} ${employee.branch} ${employee.status} ${employee.archivedReason || ''}`.toLowerCase();
      return archiveMatch && statusMatch && branchMatch && departmentMatch && wpsMatch && (!q || text.includes(q));
    });
  }

  function salaryBasicComponent(salary) {
    return salary?.components?.find(component => component.wpsMap === 'Basic Salary' || component.name === 'Basic Salary') || null;
  }

  function salaryBasicForEmployee(employee) {
    const salary = employeeProfileData(employee).salary;
    const amount = salaryBasicComponent(salary)?.amount;
    return Number.isFinite(Number(amount)) ? Number(amount) : null;
  }

  state.employees.forEach(employee => { employee.basicSalary = salaryBasicForEmployee(employee); });

  function internalEmployeesTemplate() {
    const employees = getFilteredEmployees();
    const currentEmployees = state.employees.filter(e => !e.deleted && !e.archived);
    const archivedCount = state.employees.filter(e => !e.deleted && e.archived).length;
    const active = currentEmployees.filter(e => e.status === 'Active').length;
    const wpsReady = currentEmployees.filter(e => e.wps === 'Ready').length;
    const configuredSalary = currentEmployees.filter(e => !!employeeProfileData(e).salary).length;
    const dimensions = [
      state.branches.filter(b => b.status === 'Active').length,
      state.departments.filter(d => d.status === 'Active').length
    ].filter(Boolean).length;
    const branchOptions = ['All branches', ...state.branches.filter(b => b.status === 'Active').map(b => b.name)];
    const departmentOptions = ['All departments', ...state.departments.filter(d => d.status === 'Active').map(d => d.name)];

    return `<section class="page ui-v2-payroll-page ui-v2-prs-internal-page ui-v2-prs-internal-employees">
      <div class="page-head ui-v2-page-header ui-v2-payroll-page-head">
        <div class="page-head__copy ui-v2-page-header__copy"><span class="eyebrow ui-v2-eyebrow">Internal Company · ${escapeHtml(state.period)}</span><h1 class="ui-v2-title-lg">Internal Employees</h1><p class="ui-v2-body">Internal employee masters use company branch and department organization, with salary, attendance and WPS readiness connected from one controlled register.</p></div>
        <div class="page-head__actions ui-v2-page-header__actions"><button class="btn btn--secondary" data-route-link="salary-setup">Salary Setup</button><button class="btn btn--secondary" data-employee-export>Export</button><button class="btn btn--primary" data-quick-add="internal-employee">${icon('plus')} Add Employee</button></div>
      </div>
      <div class="summary-strip ui-v2-payroll-summary-strip">
        <div class="summary-item ui-v2-payroll-metric"><span>Current employee records</span><strong>${currentEmployees.length}</strong><small>${active} active · ${archivedCount} archived retained</small></div>
        <div class="summary-item ui-v2-payroll-metric"><span>Organization dimensions</span><strong>${dimensions}</strong><small>Branch + department in current preset</small></div>
        <div class="summary-item ui-v2-payroll-metric"><span>Salary configured</span><strong>${configuredSalary}/${currentEmployees.length || 0}</strong><small>Current employee structures available</small></div>
        <div class="summary-item ui-v2-payroll-metric"><span>WPS ready</span><strong>${wpsReady}/${currentEmployees.length || 0}</strong><small>Current employee payment records</small></div>
      </div>
      <section class="data-panel ui-v2-payroll-panel ui-v2-payroll-register">
        <div class="table-toolbar ui-v2-payroll-register__toolbar ui-v2-payroll-register__toolbar--dimensions">
          <div class="table-toolbar__search ui-v2-filter-bar__search">${icon('search')}<input id="employeeSearch" class="ui-v2-input" type="search" placeholder="Search employee, ID, position or organization…" value="${escapeHtml(state.employeeSearch)}"></div>
          <select id="employeeBranchFilter" class="ui-v2-select ui-v2-payroll-operational-select" aria-label="Filter by branch">${branchOptions.map(option => `<option ${state.employeeBranch === option ? 'selected' : ''}>${escapeHtml(option)}</option>`).join('')}</select>
          <select id="employeeDepartmentFilter" class="ui-v2-select ui-v2-payroll-operational-select" aria-label="Filter by department">${departmentOptions.map(option => `<option ${state.employeeDepartment === option ? 'selected' : ''}>${escapeHtml(option)}</option>`).join('')}</select>
          <select id="employeeStatusFilter" class="ui-v2-select ui-v2-payroll-operational-select" aria-label="Filter by employee status">${['All','Active','On Leave','Inactive','Terminated','Archived'].map(option => `<option value="${option}" ${state.employeeStatus === option ? 'selected' : ''}>${option === 'All' ? 'All statuses' : option}</option>`).join('')}</select>
          <select id="employeeWpsFilter" class="ui-v2-select ui-v2-payroll-operational-select" aria-label="Filter by WPS readiness"><option ${state.employeeWps === 'All' ? 'selected' : ''}>All</option><option ${state.employeeWps === 'WPS ready' ? 'selected' : ''}>WPS ready</option><option ${state.employeeWps === 'Needs setup' ? 'selected' : ''}>Needs setup</option></select>
          <button class="btn btn--secondary btn--sm" type="button" data-employee-filter-reset>Reset</button>
        </div>
        <div class="table-meta ui-v2-payroll-table-meta"><span><strong>${employees.length}</strong> employee${employees.length === 1 ? '' : 's'}</span><span>Organization filters use the employee's current effective branch and department assignment.</span></div>
        <div class="table-scroll ui-v2-table-wrap ui-v2-payroll-table-wrap">
          <table class="data-table ui-v2-table ui-v2-payroll-table employee-table"><thead><tr><th>Employee</th><th>Organization</th><th>Position</th><th>Salary base</th><th>WPS</th><th>Status</th><th aria-label="Open"></th></tr></thead>
          <tbody>${employees.length ? employees.map(employee => `<tr class="ui-v2-payroll-clickable-row" data-ui-v2-row-action="true" data-open-employee="${escapeHtml(employee.id)}" tabindex="0" aria-label="Open ${escapeHtml(employee.name)} profile"><td><div class="table-primary ui-v2-table__primary"><strong>${escapeHtml(employee.name)}</strong><span>EMP ${escapeHtml(employee.employeeId)}${employee.email ? ` · ${escapeHtml(employee.email)}` : ''}</span></div></td><td><div class="table-primary ui-v2-table__primary"><strong>${escapeHtml(employee.branch || 'Branch not set')}</strong><span>${escapeHtml(employee.department || 'Department not set')}</span></div></td><td>${escapeHtml(employee.position || '—')}</td><td class="table-money ui-v2-table__numeric">${salaryBasicForEmployee(employee) != null ? formatCurrency(salaryBasicForEmployee(employee)) : '—'}</td><td>${employeeWpsBadge(employee.wps)}</td><td>${employee.archived ? statusBadge('Archived') : statusBadge(employee.status)}</td><td class="ui-v2-prs-row-arrow">${icon('chevron')}</td></tr>`).join('') : `<tr><td colspan="7"><div class="table-empty"><strong>No employees match these filters.</strong><span>Change the search or organization filters, or add a new internal employee.</span></div></td></tr>`}</tbody></table>
        </div>
      </section>
      <div class="source-banner ui-v2-payroll-source-note">${icon('info')}<span>Employee master records are company-scoped and organization changes are preserved as effective-dated history.</span></div>
    </section>`;
  }

  function employeeProfileData(employee) {
    const salary = state.salaryStructures[employee?.id] || null;
    const timesheetRecord = state.timesheets?.[state.period]?.[employee?.id];
    const timesheetSummary = timesheetRecord ? summarizeAttendanceRecord(timesheetRecord, state.period) : null;
    return {
      salary,
      attendance: timesheetSummary ? {
        present: timesheetSummary.present, absent: timesheetSummary.absent,
        leave: timesheetSummary.leave + timesheetSummary.sick, off: timesheetSummary.off + timesheetSummary.holiday,
        regularHours: timesheetSummary.regularHours, otHours: 0, available: true
      } : { present:0, absent:0, leave:0, off:0, regularHours:0, otHours:0, available:false },
      adjustments: (state.internalAdjustments?.[employee?.id] || []),
      payrollHistory: [],
      documents: [],
      activity: []
    };
  }

  function employeeProfileOverview(employee, profile, branch) {
    const payrollReady = !!profile.salary && employee.wps === 'Ready';
    return `
      <div class="profile-grid profile-grid--overview employee-profile-grid">
        <div class="profile-main-stack">
          <section class="panel panel--flush">
            <div class="panel__head panel__head--padded"><div><h2>Employee information</h2><p>Permanent master data used across company payroll, branches, WPS and employee documents.</p></div><button class="text-link" data-employee-profile-action="edit">Edit details</button></div>
            <div class="employee-info-grid">
              <div><span>Employee ID</span><strong>${escapeHtml(employee.employeeId)}</strong></div>
              <div><span>Position</span><strong>${escapeHtml(employee.position)}</strong></div>
              <div><span>Department</span><strong>${escapeHtml(employee.department)}</strong></div>
              <div><span>Joining date</span><strong>${escapeHtml(employee.joining || 'Not supplied')}</strong></div><div><span>Employment end</span><strong>${escapeHtml(employee.employmentEnd || '—')}</strong></div>
              <div><span>National ID / Iqama</span><strong>${escapeHtml(employee.nationalId || 'Not supplied')}</strong></div>
              <div><span>Phone</span><strong>${escapeHtml(employee.phone || 'Not supplied')}</strong></div>
              <div><span>Address</span><strong>${escapeHtml(employee.address || 'Not supplied')}</strong></div>
              <div><span>Payment method</span><strong>${escapeHtml(employee.paymentMethod || 'Not set')}</strong></div>
            </div>
          </section>

          ${branch ? (()=>{const department=state.departments.find(item=>item.id===employee.departmentId)||departmentByName(employee.department);const history=employeeOrganizationHistory(employee);return `<section class="panel panel--flush"><div class="section-headline"><div><h2>Organization assignment</h2><p>Branch and department define the employee's internal-company organization. They are not construction-project assignments.</p></div><button class="btn btn--secondary btn--sm" data-change-employee-organization="${escapeHtml(employee.id)}">Change Organization</button></div><div class="employee-organization-current"><button class="employee-project-card" data-open-branch="${branch.id}"><span class="employee-assignment-card__icon">${icon('branch')}</span><span><strong>${escapeHtml(branch.name)}</strong><small>${escapeHtml(branch.code)} · ${escapeHtml(branch.location)}</small></span><span class="project-deployment-tag">Branch / Office</span>${icon('chevron')}</button>${department?`<button class="employee-project-card employee-department-assignment" data-open-department="${escapeHtml(department.id)}"><span class="employee-assignment-card__icon">${icon('department')}</span><span><strong>${escapeHtml(department.name)}</strong><small>${escapeHtml(department.code)} · ${escapeHtml(employee.position)}</small></span><span class="project-deployment-tag">Department</span>${icon('chevron')}</button>`:''}</div><div class="organization-history"><div class="organization-history__head"><strong>Assignment history</strong><span>Effective-dated organization changes</span></div>${history.slice(0,4).map((item,index)=>`<div class="organization-history__row ${index===0?'is-current':''}"><span class="organization-history__dot"></span><div><strong>${escapeHtml(item.branch)} · ${escapeHtml(item.department)}</strong><small>${escapeHtml(item.position||employee.position)} · effective ${escapeHtml(item.effective||'Not set')}</small>${item.reason?`<em>${escapeHtml(item.reason)}</em>`:''}</div><span>${item.effectiveTo ? 'Ended' : (index===0 ? 'Current' : 'History')}</span></div>`).join('')}</div></section>`})() : `<section class="panel panel--flush"><div class="section-headline"><div><h2>Organization assignment</h2><p>No branch has been assigned to this employee.</p></div><button class="btn btn--primary btn--sm" data-change-employee-organization="${escapeHtml(employee.id)}">Assign Organization</button></div><div class="employee-empty-compact"><strong>Branch not set</strong><span>Select a managed Branch / Office and Department record; do not use a construction project as the employee's master location.</span></div></section>`}

          <section class="panel panel--flush">
            <div class="section-headline"><div><h2>Payroll snapshot</h2><p>${escapeHtml(state.period)} · current employee readiness and payroll inputs.</p></div><button class="text-link" data-employee-tab-jump="payroll">Payroll history →</button></div>
            <div class="employee-snapshot-grid">
              <div><span>Salary structure</span><strong>${profile.salary ? 'Configured' : 'Needs setup'}</strong><small>${profile.salary ? escapeHtml(profile.salary.effective || 'Current') : 'No numeric salary structure supplied'}</small></div>
              <div><span>Basic salary</span><strong>${profile.salary ? formatCurrency(salaryBasicComponent(profile.salary)?.amount || 0) : '—'}</strong><small>${profile.salary ? `Effective ${escapeHtml(profile.salary.effective || 'current')}` : 'Not configured'}</small></div>
              <div><span>WPS</span><strong>${employee.wps === 'Ready' ? 'Ready' : 'Needs setup'}</strong><small>${employee.bank ? `${escapeHtml(employee.bank)} · ${escapeHtml(employee.account?.slice(-6) || '')}` : 'Banking data missing'}</small></div>
              <div><span>Attendance</span><strong>${profile.attendance.present} present</strong><small>${profile.attendance.available ? `${profile.attendance.otHours} OT hours` : 'Attendance not recorded for this period'}</small></div>
            </div>
          </section>
        </div>

        <div class="profile-side-stack">
          <section class="panel panel--flush">
            <div class="panel__head panel__head--padded"><div><h2>Payroll readiness</h2><p>Checks needed before payroll can be cleanly approved.</p></div>${payrollReady ? '<span class="readiness readiness--ready"><span></span>Ready</span>' : '<span class="readiness readiness--warn"><span></span>Action needed</span>'}</div>
            <div class="readiness-list readiness-list--profile">
              <div class="${profile.salary ? 'is-done' : ''}"><span>${profile.salary ? '✓' : '1'}</span><p><strong>Salary structure</strong><small>${profile.salary ? 'Effective salary components available' : 'Configure earnings and deductions'}</small></p></div>
              <div class="${employee.wps === 'Ready' ? 'is-done' : ''}"><span>${employee.wps === 'Ready' ? '✓' : '2'}</span><p><strong>Bank & WPS</strong><small>${employee.wps === 'Ready' ? 'Bank, account and ID record available' : 'Complete WPS banking fields'}</small></p></div>
              <div class="is-done"><span>✓</span><p><strong>Employee identity</strong><small>Employee ID and employment master are present</small></p></div>
              <div><span>4</span><p><strong>Attendance approval</strong><small>Monthly attendance will be approved from Timesheets</small></p></div>
            </div>
          </section>

          <section class="panel panel--flush">
            <div class="panel__head panel__head--padded"><div><h2>Quick actions</h2><p>Common payroll actions without leaving the employee context.</p></div></div>
            <div class="stack-actions employee-quick-actions"><button data-change-employee-organization="${escapeHtml(employee.id)}">Branch / Department ${icon('chevron')}</button><button data-employee-tab-jump="salary">Salary structure ${icon('chevron')}</button><button data-employee-tab-jump="bank">Bank & WPS ${icon('chevron')}</button><button data-employee-profile-action="adjustment">Add advance / adjustment ${icon('chevron')}</button><button data-employee-tab-jump="documents">Employee documents ${icon('chevron')}</button></div>
          </section>

          <section class="panel panel--flush">
            <div class="panel__head panel__head--padded"><div><h2>Recent activity</h2><p>Employee-specific audit trail preview.</p></div></div>
            <div class="employee-activity-list">
              ${(profile.activity.length ? profile.activity : [
                { title: 'Employee record available', meta: 'Employee master record' },
                { title: branch ? 'Branch assignment linked' : 'Branch assignment pending', meta: branch ? branch.name : 'No branch' },
                { title: employee.wps === 'Ready' ? 'WPS profile ready' : 'WPS setup pending', meta: employee.wps === 'Ready' ? 'Required payment profile fields are available' : 'Complete the payment profile before export' }
              ]).map(item => `<div><span></span><p><strong>${escapeHtml(item.title)}</strong><small>${escapeHtml(item.meta)}</small></p></div>`).join('')}
            </div>
          </section>
        </div>
      </div>`;
  }

  function employeeProfileSalary(employee, profile) {
    if (!profile.salary) return `
      <div class="profile-grid profile-grid--wide-side">
        <section class="panel panel--flush">
          <div class="section-headline"><div><h2>Salary structure</h2><p>Effective-dated salary components keep future changes from rewriting historical payroll.</p></div><button class="btn btn--primary btn--sm" data-employee-profile-action="create-salary">Create Salary Structure</button></div>
          <div class="salary-empty-state"><span>${icon('wallet')}</span><div><strong>No numeric salary structure configured</strong><p>Create an effective salary structure before this employee can be included in a calculated payroll run.</p></div></div>
          <div class="component-reference"><span>Available recurring components</span><div>${state.salaryComponents.filter(c => c.status === 'Active' && c.recurrence === 'Recurring').map(c => `<em>${escapeHtml(c.name)}</em>`).join('') || '<em>No recurring components configured</em>'}</div></div>
        </section>
        <div class="profile-side-stack">
          <section class="panel panel--flush"><div class="panel__head panel__head--padded"><div><h2>Overtime policy</h2><p>Payroll rule configuration</p></div></div><div class="employee-rule-card"><span>Available policies</span><strong>${state.overtimePolicies.filter(p => p.status === 'Active').length}</strong><small>Select an overtime policy when creating the salary structure, or leave overtime unassigned.</small></div></section>
          <section class="source-note">${icon('info')}<span><strong>Salary not configured</strong>No salary amount is assumed until an effective salary structure is saved.</span></section>
        </div>
      </div>`;

    const earnings = profile.salary.components.filter(c => c.type === 'earning');
    const deductions = profile.salary.components.filter(c => c.type === 'deduction');
    const salaryHistory = state.salaryStructureHistory[employee.id] || [profile.salary];
    const gross = earnings.reduce((sum,c) => sum + Number(c.amount || 0),0);
    const fixedDeductions = deductions.reduce((sum,c) => sum + Number(c.amount || 0),0);
    return `
      <div class="profile-grid profile-grid--wide-side">
        <div class="profile-main-stack">
          <section class="panel panel--flush">
            <div class="section-headline"><div><h2>Current salary structure</h2><p>Effective ${escapeHtml(profile.salary.effective || 'Current')} · effective until ${escapeHtml(profile.salary.effectiveTo || 'current')}</p></div><button class="btn btn--secondary btn--sm" data-employee-profile-action="edit-salary">Edit Structure</button></div>
            <div class="salary-structure-summary"><div><span>Fixed earnings</span><strong>${formatCurrency(gross)}</strong></div><div><span>Fixed deductions</span><strong>${formatCurrency(fixedDeductions)}</strong></div><div><span>Fixed net before OT/adjustments</span><strong>${formatCurrency(gross-fixedDeductions)}</strong></div></div>
            <div class="salary-component-columns"><div><div class="salary-component-head"><strong>Earnings</strong><span>${earnings.length} components</span></div>${earnings.map(c => `<div class="salary-component-row"><span>${escapeHtml(c.name)}</span><strong>${formatCurrency(c.amount)}</strong></div>`).join('')}</div><div><div class="salary-component-head"><strong>Deductions</strong><span>${deductions.length} components</span></div>${deductions.length ? deductions.map(c => `<div class="salary-component-row"><span>${escapeHtml(c.name)}</span><strong>${formatCurrency(c.amount)}</strong></div>`).join('') : '<div class="salary-component-row salary-component-row--muted"><span>No recurring deductions</span><strong>—</strong></div>'}</div></div>
          </section>
          <section class="panel panel--flush"><div class="section-headline"><div><h2>Salary structure history</h2><p>Changes are effective-dated; old payroll keeps the structure used at that time.</p></div></div>${salaryHistory.map(item => { const itemEarnings=(item.components||[]).filter(c=>c.type==='earning').reduce((sum,c)=>sum+Number(c.amount||0),0); const itemDeductions=(item.components||[]).filter(c=>c.type==='deduction').reduce((sum,c)=>sum+Number(c.amount||0),0); const current=item.id===profile.salary.id; return `<div class="salary-history-row"><span class="salary-history-dot ${current?'is-current':''}"></span><div><strong>${escapeHtml(item.effective || 'Current')}</strong><small>${item.effectiveTo ? `Until ${escapeHtml(item.effectiveTo)}` : 'Open-ended'}</small></div><span>${current?'Current':'History'}</span><strong>${formatCurrency(itemEarnings-itemDeductions)}</strong></div>`; }).join('')}</section>
        </div>
        <div class="profile-side-stack">
          <section class="panel panel--flush"><div class="panel__head panel__head--padded"><div><h2>Overtime policy</h2><p>Separate from fixed salary</p></div></div><div class="employee-rule-card"><span>Policy</span><strong>${escapeHtml(profile.salary.otPolicy || 'Not configured')}</strong><small>Overtime is calculated from approved attendance rather than stored as a fixed recurring earning.</small></div></section>
          <section class="source-note">${icon('info')}<span><strong>Effective-dated configuration</strong>Salary component values and the assigned overtime formula are snapshotted with this structure. Future master-data changes do not rewrite this assignment.</span></section>
        </div>
      </div>`;
  }

  function employeeProfileBank(employee) {
    const context = paymentContextForPeriod();
    const profile = context.profiles?.[employee.id] || null;
    const readiness = (context.wpsReadiness?.employees || []).find(row => row.employeeId === employee.id) || null;
    const blockers = readiness?.blockers || [];
    const ready = readiness?.status === 'Ready';
    const destination = profile?.destinationMasked || 'Not configured';
    return `
      <div class="profile-grid profile-grid--wide-side">
        <div class="profile-main-stack">
          <section class="panel panel--flush">
            <div class="section-headline"><div><h2>Salary Payment Profile</h2><p>Current payment destination used when a new Bank/WPS batch is prepared.</p></div><button class="btn btn--secondary btn--sm" data-employee-profile-action="edit-bank">${profile ? 'Edit Payment Profile' : 'Add Payment Profile'}</button></div>
            <div class="bank-card ${profile?.active ? '' : 'bank-card--empty'}">
              <div class="bank-card__brand">${icon('bank')}<span><small>Bank / issuer</small><strong>${escapeHtml(profile?.bankName || 'Not configured')}</strong></span>${employeeWpsBadge(ready ? 'Ready' : 'Not configured')}</div>
              <div class="bank-detail-grid"><div><span>Destination</span><strong class="mono-cell">${escapeHtml(destination)}</strong></div><div><span>Destination type</span><strong>${escapeHtml(profile?.destinationLabel || 'Not configured')}</strong></div><div><span>Account holder</span><strong>${escapeHtml(profile?.accountHolderName || 'Not configured')}</strong></div><div><span>National ID / Iqama</span><strong>${escapeHtml(employee.nationalId || 'Not supplied')}</strong></div><div><span>WPS enabled</span><strong>${profile?.wpsEnabled ? 'Yes' : 'No'}</strong></div><div><span>Verified</span><strong>${profile?.verifiedAt ? 'Yes' : 'No'}</strong></div></div>
            </div>
          </section>
          <section class="panel panel--flush"><div class="section-headline"><div><h2>WPS Readiness</h2><p>Server validation against the current approved payroll and company WPS setup.</p></div><button class="text-link" data-route-link="wps">Open WPS workspace →</button></div>${readiness ? `<div class="validation-list">${blockers.length ? blockers.map(text => `<div class="validation-list__item is-danger"><span>!</span><p>${escapeHtml(text)}</p></div>`).join('') : '<div class="validation-list__item is-ok"><span>✓</span><p>This employee is ready for the currently selected WPS configuration.</p></div>'}</div>` : '<div class="table-empty table-empty--card"><strong>No WPS payroll row for this period.</strong><span>Readiness becomes available when the employee is part of an approved payroll run.</span></div>'}</section>
        </div>
        <div class="profile-side-stack">
          <section class="panel panel--flush"><div class="panel__head panel__head--padded"><div><h2>Payment security</h2><p>Current master-data state</p></div></div><div class="wps-check-list">${[['Active profile',!!profile?.active],['Payment destination',!!profile?.destinationMasked],['National ID / Iqama',!!employee.nationalId],['WPS enabled',!!profile?.wpsEnabled]].map(([label,ok]) => `<div class="${ok?'is-ok':''}"><span>${ok?'✓':'!'}</span><strong>${label}</strong><small>${ok?'Available':'Required when applicable'}</small></div>`).join('')}</div></section>
          <section class="source-note">${icon('info')}<span><strong>Protected bank data</strong>The interface only receives masked payment destinations. Full values are decrypted server-side only for authorized payment/export operations.</span></section>
        </div>
      </div>`;
  }

  function employeeProfileAttendance(employee, profile) {
    const a = profile.attendance;
    if (!a.available) return `
      <section class="panel panel--flush">
        <div class="section-headline"><div><h2>Attendance & overtime</h2><p>${escapeHtml(state.period)} · employee attendance has not been recorded for this period.</p></div><button class="btn btn--secondary btn--sm" data-route-link="timesheets">Open Timesheets</button></div>
        <div class="table-empty table-empty--card"><strong>No attendance record</strong><span>Daily attendance and overtime will appear here after the monthly attendance module stores an approved employee record.</span></div>
      </section>`;
    return `
      <section class="panel panel--flush">
        <div class="section-headline"><div><h2>Attendance & overtime</h2><p>${escapeHtml(state.period)} · employee-level attendance summary.</p></div><button class="btn btn--secondary btn--sm" data-route-link="timesheets">Open Timesheets</button></div>
        <div class="attendance-kpis"><div><span>Present</span><strong>${a.present}</strong><small>days</small></div><div><span>Absent</span><strong>${a.absent}</strong><small>days</small></div><div><span>Leave</span><strong>${a.leave}</strong><small>days</small></div><div><span>Regular hours</span><strong>${a.regularHours}</strong><small>hours</small></div><div><span>OT</span><strong>${a.otHours}</strong><small>hours</small></div></div>
      </section>`;
  }

  function employeeProfileAdjustments(employee, profile) {
    const adjustments = profile.adjustments || [];
    return `
      <section class="panel panel--flush">
        <div class="section-headline"><div><h2>Advances & adjustments</h2><p>One-time payroll transactions remain separate from the permanent salary structure.</p></div><button class="btn btn--primary btn--sm" data-employee-profile-action="adjustment">${icon('plus')} Add Adjustment</button></div>
        ${adjustments.length ? `<div class="table-scroll"><table class="data-table employee-adjustment-table"><thead><tr><th>Date</th><th>Type</th><th>Payroll period</th><th>Reason</th><th>Amount</th><th>Balance</th><th>Status</th><th></th></tr></thead><tbody>${adjustments.map(x=>`<tr><td>${escapeHtml(x.date)}</td><td><strong>${escapeHtml(x.type)}</strong></td><td>${escapeHtml(x.period)}</td><td>${escapeHtml(x.reason)}</td><td class="table-money">${formatCurrency(x.amount)}</td><td class="table-money">${Number.isFinite(x.balance)?formatCurrency(x.balance):'—'}</td><td>${statusBadge(x.status)}</td><td><button class="icon-btn icon-btn--sm" data-route-link="adjustments">${icon('more')}</button></td></tr>`).join('')}</tbody></table></div>` : `<div class="table-empty table-empty--card"><strong>No advances or adjustments</strong><span>Create salary advances, bonuses, reimbursements, fines or other one-time payroll transactions here. They will never alter the employee's permanent salary structure.</span><button class="btn btn--secondary btn--sm" data-employee-profile-action="adjustment">Add first adjustment</button></div>`}
      </section>`;
  }

  function employeeProfilePayroll(employee, profile) {
    const rows = profile.payrollHistory || [];
    return `
      <section class="panel panel--flush">
        <div class="section-headline"><div><h2>Payroll history</h2><p>Historical payroll remains immutable after closing; corrections use explicit revision workflows.</p></div><button class="btn btn--secondary btn--sm" data-route-link="payroll-runs">Open Payroll Runs</button></div>
        ${rows.length ? `<div class="table-scroll"><table class="data-table payroll-history-table"><thead><tr><th>Period</th><th>Basic</th><th>Allowances / OT</th><th>Gross</th><th>Deductions</th><th>Net</th><th>Payment</th><th>Status</th></tr></thead><tbody>${rows.map(r=>`<tr><td><strong>${escapeHtml(r.period)}</strong><small class="table-secondary">${escapeHtml(r.reference || '')}</small></td><td class="table-money">${formatCurrency(r.basic)}</td><td class="table-money">${formatCurrency(r.extras||0)}</td><td class="table-money">${formatCurrency(r.gross)}</td><td class="table-money">${formatCurrency(r.deductions||0)}</td><td class="table-money"><strong>${formatCurrency(r.net)}</strong></td><td>${escapeHtml(r.payment||'—')}</td><td>${statusBadge(r.status)}</td></tr>`).join('')}</tbody></table></div>` : `<div class="table-empty table-empty--card"><strong>No structured payroll runs yet</strong><span>Payroll history will populate when calculated monthly runs are approved and closed.</span></div>`}
      </section>`;
  }

  function employeeProfileDocuments(employee) {
    const docs=(state.businessDocuments||[]).filter(doc=>doc.workspace==='internal' && doc.type==='salary_slip' && doc.entityReference===employee.employeeId).sort((a,b)=>String(b.finalizedAt||'').localeCompare(String(a.finalizedAt||'')));
    return `
      <section class="panel panel--flush">
        <div class="section-headline"><div><h2>Employee documents</h2><p>Final salary slips are immutable records generated from approved payroll snapshots.</p></div><button class="btn btn--secondary btn--sm" data-employee-profile-action="generate-slip">Finalize Salary Slip</button></div>
        ${docs.length ? `<div class="employee-document-list">${docs.map(d=>`<button class="employee-document-row" data-employee-document="${escapeHtml(d.id)}"><span class="employee-document-icon">${icon('document')}</span><span><strong>${escapeHtml(d.title)}</strong><small>${escapeHtml(d.number)} · ${escapeHtml(d.period||'')}</small></span><em>${escapeHtml(d.status||'Final')}</em>${icon('chevron')}</button>`).join('')}</div>` : `<div class="table-empty table-empty--card"><strong>No finalized salary slips</strong><span>Finalize a salary slip after the employee has an Approved-or-later payroll line.</span><button class="btn btn--secondary btn--sm" data-employee-profile-action="generate-slip">Open eligible payroll sources</button></div>`}
      </section>`;
  }

  function employeeRecordPreviewTemplate(employee) {
    if (!employee) return `<section class="page"><div class="placeholder"><div class="placeholder__inner"><div class="placeholder__icon">${icon('person')}</div><h2>Employee not found</h2><p>This internal employee record is not available for the active company.</p><button class="btn btn--secondary" data-route-link="internal-employees">Back to Employees</button></div></div></section>`;
    const branch = employee.branchId ? state.branches.find(item => item.id === employee.branchId) : null;
    const profile = employeeProfileData(employee);
    const fixedGross = profile.salary ? profile.salary.components.filter(c=>c.type==='earning').reduce((s,c)=>s+Number(c.amount||0),0) : null;
    const tab = state.employeeTab;
    const organizationLocked = !!employee.archived || ['Inactive','Terminated'].includes(employee.status);
    const tabs = [
      ['overview','Overview'],['salary','Salary Structure'],['bank','Bank & WPS'],['attendance','Attendance'],['adjustments','Advances & Adjustments'],['payroll','Payroll History'],['documents','Documents']
    ];
    let content = employeeProfileOverview(employee, profile, branch);
    if (tab === 'salary') content = employeeProfileSalary(employee, profile);
    else if (tab === 'bank') content = employeeProfileBank(employee);
    else if (tab === 'attendance') content = employeeProfileAttendance(employee, profile);
    else if (tab === 'adjustments') content = employeeProfileAdjustments(employee, profile);
    else if (tab === 'payroll') content = employeeProfilePayroll(employee, profile);
    else if (tab === 'documents') content = employeeProfileDocuments(employee, profile);

    return `
      <section class="page employee-profile-page ui-v2-prs-internal-page ui-v2-payroll-employee-profile">
        <div class="profile-crumb ui-v2-payroll-profile-crumb"><button type="button" class="text-link text-link--muted" data-route-link="internal-employees">Internal Employees</button><span>›</span><span>EMP ${escapeHtml(employee.employeeId)}</span></div>
        <header class="entity-header employee-profile-header ui-v2-payroll-entity-header">
          <div class="entity-header__identity ui-v2-payroll-entity-header__identity"><span class="entity-avatar entity-avatar--employee ui-v2-payroll-entity-avatar">${icon('person')}</span><div><div class="entity-title-row ui-v2-payroll-entity-title"><h1>${escapeHtml(employee.name)}</h1>${statusBadge(employee.status)}${employee.archived ? statusBadge('Archived') : ''}</div><div class="entity-subline"><span>EMP ${escapeHtml(employee.employeeId)}</span><span>·</span><span>${escapeHtml(employee.position)}</span><span>·</span><span>${escapeHtml(employee.department)}</span></div></div></div>
          <div class="entity-header__actions ui-v2-payroll-entity-header__actions">${employeeLifecycleActions(employee).length?`<button class="btn btn--primary employee-employment-btn" data-employee-lifecycle>${icon('person')} Employment</button>`:''}${lifecycleActionsMenu([{label:'Edit employee master',hint:'Identity and contact details only',iconName:'edit',attrs:'data-employee-profile-action="edit"'},{label:'Change organization',hint:organizationLocked?'Restore/reactivate before changing organization':'Effective-dated branch and department assignment',iconName:'branch',attrs:`data-change-employee-organization="${escapeHtml(employee.id)}"`,disabled:organizationLocked},{label:'Add adjustment',hint:'Advance, deduction, bonus or reimbursement',iconName:'plus',attrs:'data-employee-profile-action="adjustment"'},'separator',{label:employee.archived?'Restore from archive':'Archive employee',hint:employee.archived?'Restore the retained master to its previous operational state':'Retain all history and remove from current registers',iconName:'archive',attrs:`data-employee-record-action="${employee.archived?'restore':'archive'}"`},{label:'Delete',hint:'Delete with 30-day recovery; protected history is never erased',iconName:'trash',danger:true,attrs:'data-employee-record-action="delete"'}])}</div>
        </header>
        ${employeeLifecycleBanner(employee)}
        <div class="profile-facts employee-profile-facts ui-v2-payroll-profile-facts">
          <div><span>Branch / Office</span><strong>${escapeHtml(employee.branch || 'Branch not set')}</strong></div>
          <div><span>Department</span><strong>${escapeHtml(employee.department || 'Department not set')}</strong></div>
          <div><span>Fixed salary</span><strong>${fixedGross !== null ? formatCurrency(fixedGross) : 'Needs setup'}</strong></div>
          <div><span>WPS readiness</span><strong>${employee.wps === 'Ready' ? 'Ready' : 'Needs setup'}</strong></div>
        </div>
        <div class="tabs profile-tabs employee-profile-tabs ui-v2-payroll-profile-tabs" role="tablist">${tabs.map(([id,label])=>`<button type="button" role="tab" data-employee-tab="${id}" class="${tab===id?'is-active':''}" aria-selected="${tab===id}">${label}${id==='adjustments'&&profile.adjustments.length?`<span class="tab-count">${profile.adjustments.length}</span>`:''}${id==='documents'&&profile.documents.length?`<span class="tab-count">${profile.documents.length}</span>`:''}</button>`).join('')}</div>
        <div class="profile-content ui-v2-payroll-profile-content">${content}</div>
        <div class="source-banner">${icon('info')}<span>Employee identity and organization changes are stored as company-scoped records with effective-dated organization history.</span></div>
      </section>`;
  }


  function getFilteredProjects() {
    const q = state.projectSearch.trim().toLowerCase();
    const supplierProjectIds = new Set();
    if (state.projectSupplier !== 'All suppliers') {
      state.rentalWorkers.forEach(worker => {
        if (worker.supplierId !== state.projectSupplier || worker.status !== 'Assigned') return;
        const projectId = rentalWorkerCurrentSnapshot(worker).project?.id || worker.projectId;
        if (projectId) supplierProjectIds.add(projectId);
      });
    }
    return state.projects.filter(project => {
      if (project.legacyInternal) return false;
      const statusMatch = state.projectStatus === 'All' || project.status === state.projectStatus;
      const clientMatch = state.projectClient === 'All clients' || (state.projectClient === 'Client not set' ? !project.client : project.client === state.projectClient);
      const managerMatch = state.projectManager === 'All managers' || (state.projectManager === 'Manager not set' ? !project.manager : project.manager === state.projectManager);
      const supplierMatch = state.projectSupplier === 'All suppliers' || supplierProjectIds.has(project.id);
      const text = `${project.name} ${project.code} ${project.client || ''} ${project.location || ''} ${project.manager || ''}`.toLowerCase();
      return statusMatch && clientMatch && managerMatch && supplierMatch && (!q || text.includes(q));
    });
  }

  function projectsTemplate() {
    const projects = getFilteredProjects();
    const rentalProjects = state.projects.filter(p => !p.legacyInternal);
    const active = rentalProjects.filter(p => p.status === 'Active').length;
    const rental = rentalProjects.reduce((sum, p) => sum + Number(p.rentalWorkers || 0), 0);
    const supplierCount = state.suppliers.filter(s=>s.status==='Active').length;
    const knownCost = rentalProjects.reduce((sum, p) => sum + Number(p.netCost || 0), 0);
    const clientOptions = [...new Set(rentalProjects.map(project => project.client).filter(Boolean))].sort((a,b)=>a.localeCompare(b));
    const managerOptions = [...new Set(rentalProjects.map(project => project.manager).filter(Boolean))].sort((a,b)=>a.localeCompare(b));
    const projectAdvancedCount = [
      state.projectClient !== 'All clients',
      state.projectManager !== 'All managers',
      state.projectSupplier !== 'All suppliers'
    ].filter(Boolean).length;
    const projectHasFilters = !!state.projectSearch || state.projectStatus !== 'All' || projectAdvancedCount > 0;

    return `
      <section class="page projects-page">
        <div class="page-head">
          <div class="page-head__copy">
            <div class="eyebrow">Operations</div>
            <h1>Projects</h1>
            <p>Manage rental-manpower projects used for supplier-worker assignments, timesheets and settlement costing. Internal company employees belong to branches/offices instead.</p>
          </div>
          <div class="page-head__actions">
            <button class="btn btn--secondary" data-project-export>Export</button>
            <button class="btn btn--primary" data-quick-add="project">${icon('plus')} Add Project</button>
          </div>
        </div>

        <div class="summary-strip summary-strip--4">
          <div class="summary-item"><span>Active projects</span><strong>${active}</strong><small>${rentalProjects.length} rental project records</small></div>
          <div class="summary-item"><span>Manpower suppliers</span><strong>${supplierCount}</strong><small>Managed supplier companies</small></div>
          <div class="summary-item"><span>Rental manpower</span><strong>${rental}</strong><small>Active project assignments</small></div>
          <div class="summary-item"><span>Known manpower cost</span><strong>${formatCurrency(knownCost)}</strong><small>Controlled rental records</small></div>
        </div>

        <section class="data-panel">
          <div class="table-toolbar">
            <div class="table-toolbar__search">${icon('search')}<input id="projectSearch" type="search" placeholder="Search project, code, client or location" value="${escapeHtml(state.projectSearch)}"></div>
            <div class="segmented segmented--compact" aria-label="Project status filter">
              ${['All','Active','On Hold','Completed'].map(status => `<button type="button" data-project-status="${status}" class="${state.projectStatus === status ? 'is-active' : ''}">${status}</button>`).join('')}
            </div>
            <button class="btn btn--ghost ${projectAdvancedCount ? 'is-active-filter' : ''}" data-project-filter aria-expanded="${state.projectFiltersOpen}">${icon('more')} More filters${projectAdvancedCount ? ` (${projectAdvancedCount})` : ''}</button>
            ${projectHasFilters ? '<button class="btn btn--ghost" data-project-reset>Reset</button>' : ''}
          </div>
          ${state.projectFiltersOpen ? `<div class="ui-v2-payroll-advanced-filters" data-advanced-filter-panel>
            <label><span>Client</span><select id="projectClientFilter" class="ui-v2-select"><option>All clients</option><option ${state.projectClient==='Client not set'?'selected':''}>Client not set</option>${clientOptions.map(value=>`<option ${state.projectClient===value?'selected':''}>${escapeHtml(value)}</option>`).join('')}</select></label>
            <label><span>Manager</span><select id="projectManagerFilter" class="ui-v2-select"><option>All managers</option><option ${state.projectManager==='Manager not set'?'selected':''}>Manager not set</option>${managerOptions.map(value=>`<option ${state.projectManager===value?'selected':''}>${escapeHtml(value)}</option>`).join('')}</select></label>
            <label><span>Supplier</span><select id="projectSupplierFilter" class="ui-v2-select"><option value="All suppliers">All suppliers</option>${state.suppliers.filter(s=>s.status==='Active').map(s=>`<option value="${escapeHtml(s.id)}" ${state.projectSupplier===s.id?'selected':''}>${escapeHtml(s.name)}</option>`).join('')}</select></label>
            <button class="btn btn--secondary" type="button" data-project-advanced-reset>Clear advanced</button>
          </div>` : ''}

          <div class="table-meta"><span><strong>${projects.length}</strong> project${projects.length === 1 ? '' : 's'}</span><span>Names are clickable; project profiles preserve workforce and cost context.</span></div>

          <div class="table-scroll">
            <table class="data-table project-table">
              <thead><tr><th>Project</th><th>Client / Location</th><th>Rental Workers</th><th>Suppliers</th><th>Current Cost</th><th>Status</th><th aria-label="Actions"></th></tr></thead>
              <tbody>
                ${projects.length ? projects.map(project => `
                  <tr>
                    <td>
                      <button class="entity-link entity-link--stack" data-open-project="${project.id}">
                        <strong>${escapeHtml(project.name)}</strong><span>${escapeHtml(project.code)} · Started ${escapeHtml(project.start)}</span>
                      </button>
                    </td>
                    <td><div class="table-primary">${escapeHtml(project.client)}</div><div class="table-secondary">${escapeHtml(project.location)}</div></td>
                    <td><span class="table-number">${project.rentalWorkers}</span></td>
                    <td><span class="table-number">${project.suppliers}</span></td>
                    <td><div class="table-primary">${project.netCost ? formatCurrency(project.netCost) : '—'}</div><div class="table-secondary">${project.netCost ? 'Current known period' : 'No cost posted'}</div></td>
                    <td>${statusBadge(project.status)}</td>
                    <td class="table-actions">${lifecycleActionsMenu([{label:'Open project',hint:'Open the full project profile',iconName:'project',attrs:`data-route-link="projects/${escapeHtml(project.id)}"`},{label:'Edit project',hint:'Update project master data',iconName:'edit',attrs:`data-project-edit-id="${escapeHtml(project.id)}"`},'separator',{label:project.archived?'Restore from archive':'Archive project',hint:'Archive preserves all project history',iconName:'archive',attrs:`data-project-lifecycle="${project.archived?'restore':'archive'}" data-project-lifecycle-id="${escapeHtml(project.id)}"`},{label:'Delete',hint:'Delete with 30-day recovery',iconName:'trash',danger:true,attrs:`data-project-lifecycle="delete" data-project-lifecycle-id="${escapeHtml(project.id)}"`}],{compact:true,label:'Actions'})}</td>
                  </tr>`).join('') : `<tr><td colspan="8"><div class="table-empty"><strong>No projects match these filters.</strong><span>Change the search/status filter or add a new project.</span></div></td></tr>`}
              </tbody>
            </table>
          </div>
        </section>

        <div class="source-banner">${icon('info')}<span>Projects are company-controlled rental-manpower masters. Worker deployment, trade and commercial rates are maintained separately as effective-dated assignments.</span></div>
      </section>`;
  }


  function projectRentalWorkersForProfile(project) {
    if (!project) return [];
    return state.rentalWorkers.flatMap(worker => {
      const history = rentalAssignmentsFor(worker).filter(item => item.kind === 'assignment' && item.projectId === project.id);
      if (!history.length) return [];
      const snapshot = rentalWorkerCurrentSnapshot(worker);
      const current = worker.status === 'Assigned' && snapshot.project?.id === project.id;
      const record = current ? (rentalCurrentAssignment(worker) || history[history.length-1]) : [...history].sort((a,b)=>String(b.start||'').localeCompare(String(a.start||'')))[0];
      const supplier = rentalWorkerSupplier(worker);
      const assignments = rentalAssignmentsFor(worker).filter(item => item.kind === 'assignment');
      return [{
        id:worker.id, name:worker.name, type:'Rental', supplier:supplier?.name || worker.supplier || 'Supplier not linked',
        supplierId:worker.supplierId || null, trade:record.trade || worker.trade || 'Worker',
        rate:rentalRateLabelFromParts(record.rateType,record.rateValue,record.rateLabel),
        since:record.start ? rentalDisplayDate(record.start) : worker.since || '—',
        status:current ? 'Assigned' : (record.status === 'Released' || worker.status === 'Released' ? 'Released' : 'Transferred'),
        changed:assignments.length > 1, current
      }];
    }).sort((a,b) => Number(b.current)-Number(a.current) || a.name.localeCompare(b.name));
  }

  function projectSuppliersForProfile(project) {
    if (!project) return [];
    const groups = new Map();
    state.rentalWorkers.filter(worker => worker.status === 'Assigned' && rentalWorkerCurrentSnapshot(worker).project?.id === project.id).forEach(worker => {
      const supplier = rentalWorkerSupplier(worker); if (!supplier) return;
      if (!groups.has(supplier.id)) groups.set(supplier.id,{ id:supplier.id,name:supplier.name,workers:0,hours:0,currentCost:0,status:'Active',note:'Current deployment from rental worker assignment master.' });
      groups.get(supplier.id).workers += 1;
    });
    return [...groups.values()];
  }

  function supplierProjectsForProfile(supplierId) {
    const groups = new Map();
    state.rentalWorkers.filter(worker => worker.supplierId === supplierId && worker.status === 'Assigned').forEach(worker => {
      const snapshot = rentalWorkerCurrentSnapshot(worker); const project=snapshot.project; if(!project) return;
      if(!groups.has(project.id)) groups.set(project.id,{projectId:project.id,project:project.name,workers:0,hours:0,otHours:0,cost:0,status:project.status || 'Active'});
      groups.get(project.id).workers += 1;
    });
    return [...groups.values()].sort((a,b)=>b.workers-a.workers || a.project.localeCompare(b.project));
  }

  function projectProfileTemplate(project) {
    if (!project) return missingProjectTemplate();
    const workers = projectRentalWorkersForProfile(project);
    const suppliers = projectSuppliersForProfile(project);
    const activeWorkers = workers.filter(w => w.status === 'Assigned').length;
    const releasedWorkers = workers.filter(w => ['Released','Transferred'].includes(w.status)).length;
    const control = rentalProjectControlRows().find(row => row.project.id === project.id) || null;
    const tab = state.projectTab;

    return `
      <section class="page project-profile">
        <div class="profile-crumb ui-v2-payroll-profile-crumb"><button type="button" class="text-link text-link--muted" data-route-link="projects">Projects</button><span>›</span><span>${escapeHtml(project.code)}</span></div>

        <header class="entity-header">
          <div class="entity-header__identity">
            <span class="entity-avatar entity-avatar--project">${icon('project')}</span>
            <div>
              <div class="entity-title-row ui-v2-payroll-entity-title"><h1>${escapeHtml(project.name)}</h1>${statusBadge(project.status)}</div>
              <div class="entity-subline"><span>${escapeHtml(project.code)}</span><span>·</span><span>${escapeHtml(project.client)}</span><span>·</span><span>${icon('location')} ${escapeHtml(project.location)}</span></div>
            </div>
          </div>
          <div class="entity-header__actions ui-v2-payroll-entity-header__actions">
            <button class="btn btn--secondary" data-project-assignment-activity="${escapeHtml(project.id)}">Assignment Activity</button>
            <button class="btn btn--secondary" data-project-add-worker="${escapeHtml(project.id)}">${icon('plus')} Add Worker</button>
            ${lifecycleActionsMenu([{label:'Edit project',hint:'Update the project master',iconName:'edit',attrs:'data-project-action="edit"'},'separator',{label:project.archived?'Restore from archive':'Archive project',hint:project.archived?'Return the retained project master':'Retain history and stop new operational use',iconName:'archive',attrs:`data-project-lifecycle="${project.archived?'restore':'archive'}"`},{label:'Delete',hint:'Delete with 30-day recovery; project inventory and assignments follow automatically',iconName:'trash',danger:true,attrs:'data-project-lifecycle="delete"'}])}
          </div>
        </header>

        <div class="profile-facts profile-facts--rental-project">
          <div><span>Start date</span><strong>${escapeHtml(project.start)}</strong></div>
          <div><span>Rental workforce</span><strong>${activeWorkers} active</strong></div>
          <div><span>Suppliers</span><strong>${suppliers.length}</strong></div>
          <div><span>${escapeHtml(state.period)} timesheet</span><strong>${escapeHtml(control?.timesheet || 'Draft')}</strong></div>
          <div><span>Settlement</span><strong>${escapeHtml(control?.settlement || 'Not started')}</strong></div>
          <div><span>Outstanding payable</span><strong>${formatCurrency(control?.outstanding || 0)}</strong></div>
        </div>

        <nav class="tabs profile-tabs" aria-label="Project profile sections">
          ${[
            ['overview','Overview'],['workforce','Workforce'],['suppliers','Suppliers'],['timesheets','Timesheets'],['cost','Manpower Cost'],['documents','Documents']
          ].map(([key,label]) => `<button type="button" data-project-tab="${key}" class="${tab === key ? 'is-active' : ''}">${label}${key === 'workforce' && workers.length ? `<span class="tab-count">${workers.length}</span>` : ''}</button>`).join('')}
        </nav>

        <div class="profile-content">
          ${projectProfileTab(project, tab, workers, suppliers, activeWorkers, releasedWorkers)}
        </div>
      </section>`;
  }

  function projectProfileTab(project, tab, workers, suppliers, activeWorkers, releasedWorkers) {
    if (tab === 'workforce') return projectWorkforceTab(project, workers, activeWorkers, releasedWorkers);
    if (tab === 'suppliers') return projectSuppliersTab(project, suppliers);
    if (tab === 'timesheets') return projectTimesheetsTab(project);
    if (tab === 'cost') return projectCostTab(project);
    if (tab === 'documents') return projectDocumentsTab(project);
    return projectOverviewTab(project, workers, suppliers, activeWorkers, releasedWorkers);
  }

  function projectOverviewTab(project, workers, suppliers, activeWorkers, releasedWorkers) {
    const currentWorkers = workers.filter(w => w.status === 'Assigned');
    const masonCount = currentWorkers.filter(w => String(w.trade || '').includes('Mason')).length;
    const helperCount = currentWorkers.filter(w => String(w.trade || '').includes('Helper')).length;
    const control = rentalProjectControlRows().find(row => row.project.id === project.id) || null;
    const settlements = Object.values(state.rentalSettlements || {}).filter(item => item.period === state.period && item.projectId === project.id);
    const periodHours = settlements.reduce((sum,item)=>sum+Number(item.totals?.regularHours||0),0);
    const gross = settlements.reduce((sum,item)=>sum+Number(item.totals?.gross||0),0);
    const deductions = settlements.reduce((sum,item)=>sum+Number(item.totals?.adjustmentDeductions||0),0);
    const net = settlements.reduce((sum,item)=>sum+Number(item.totals?.net||0),0);
    return `
      <div class="profile-grid profile-grid--overview">
        <div class="profile-main-stack">
          <section class="panel panel--flush">
            <div class="panel__head panel__head--padded"><div><h2>Current manpower</h2><p>Supplier-worker deployment for this rental project.</p></div><button class="text-link" data-project-tab-jump="workforce">View workforce →</button></div>
            <div class="project-kpis">
              <div><span>Active workers</span><strong>${activeWorkers}</strong><small>${releasedWorkers ? `${releasedWorkers} historical / released` : 'Current assignments'}</small></div>
              <div><span>Manpower suppliers</span><strong>${suppliers.length}</strong><small>Current assignment suppliers</small></div>
              <div><span>Recorded hours</span><strong>${settlements.length ? periodHours.toLocaleString('en-SA',{maximumFractionDigits:2}) : '—'}</strong><small>${settlements.length ? `${state.period} settlement snapshots` : 'No settlement calculated for this period'}</small></div>
            </div>
            ${workers.length ? `<div class="composition-block"><div class="composition-block__head"><strong>Rental trade mix</strong><span>Current assignment roster</span></div><div class="composition-row"><span>Mason</span><div><i style="width:${Math.min(100, masonCount / Math.max(1,currentWorkers.length) * 100)}%"></i></div><strong>${masonCount}</strong></div><div class="composition-row"><span>Helper</span><div><i style="width:${Math.min(100, helperCount / Math.max(1,currentWorkers.length) * 100)}%"></i></div><strong>${helperCount}</strong></div><div class="composition-row"><span>Other roles</span><div><i style="width:${Math.min(100, (currentWorkers.length-masonCount-helperCount) / Math.max(1,currentWorkers.length) * 100)}%"></i></div><strong>${Math.max(0,currentWorkers.length-masonCount-helperCount)}</strong></div></div>` : `<div class="empty-inline">No workforce assignments have been added yet.</div>`}
          </section>
          <section class="panel panel--flush"><div class="panel__head panel__head--padded"><div><h2>${escapeHtml(state.period)} manpower cost</h2><p>Financial values are read from controlled supplier-settlement snapshots.</p></div><button class="text-link" data-project-tab-jump="cost">Open cost →</button></div><div class="cost-ledger"><div><span>Gross rental amount</span><strong>${settlements.length ? formatCurrency(gross) : '—'}</strong></div><div><span>Adjustment deductions</span><strong>${settlements.length ? formatCurrency(deductions) : '—'}</strong></div><div class="cost-ledger__total"><span>Net manpower cost</span><strong>${settlements.length ? formatCurrency(net) : '—'}</strong></div></div></section>
        </div>
        <aside class="profile-side-stack"><section class="detail-card"><div class="detail-card__head"><h3>Project details</h3><button class="text-link" data-project-action="edit">Edit</button></div><dl class="detail-list"><div><dt>Project code</dt><dd>${escapeHtml(project.code)}</dd></div><div><dt>Client</dt><dd>${escapeHtml(project.client)}</dd></div><div><dt>Location</dt><dd>${escapeHtml(project.location)}</dd></div><div><dt>Started</dt><dd>${escapeHtml(project.start)}</dd></div><div><dt>Expected end</dt><dd>${escapeHtml(project.end)}</dd></div><div><dt>Manager</dt><dd>${escapeHtml(project.manager)}</dd></div></dl></section><section class="detail-card"><div class="detail-card__head"><h3>Supplier deployment</h3><button class="text-link" data-project-tab-jump="suppliers">View all</button></div>${suppliers.length ? suppliers.map(row => `<button class="mini-entity" data-route-link="suppliers/${row.id}"><span class="mini-entity__icon">${icon('supplier')}</span><span><strong>${escapeHtml(row.name)}</strong><small>${row.workers} active worker${row.workers===1?'':'s'}</small></span>${icon('chevron')}</button>`).join('') : `<div class="empty-inline">No supplier linked yet.</div>`}</section><div class="source-note">${icon('info')}<span>Project master details are maintained independently from assignment, timesheet and settlement history.</span></div></aside>
      </div>`;
  }
  function projectWorkforceTab(project, workers, activeWorkers, releasedWorkers) {
    const q = state.projectWorkerSearch.trim().toLowerCase();
    const supplierOptions = [...new Set(workers.map(worker=>worker.supplier).filter(Boolean))].sort((a,b)=>a.localeCompare(b));
    const tradeOptions = [...new Set(workers.map(worker=>worker.trade).filter(Boolean))].sort((a,b)=>a.localeCompare(b));
    if (state.projectWorkerSupplier !== 'All suppliers' && !supplierOptions.includes(state.projectWorkerSupplier)) state.projectWorkerSupplier = 'All suppliers';
    if (state.projectWorkerTrade !== 'All trades' && !tradeOptions.includes(state.projectWorkerTrade)) state.projectWorkerTrade = 'All trades';
    const filteredWorkers = workers.filter(worker => {
      const statusMatch = state.projectWorkerStatus === 'All statuses' || worker.status === state.projectWorkerStatus;
      const supplierMatch = state.projectWorkerSupplier === 'All suppliers' || worker.supplier === state.projectWorkerSupplier;
      const tradeMatch = state.projectWorkerTrade === 'All trades' || worker.trade === state.projectWorkerTrade;
      const haystack = `${worker.name} ${worker.id || ''} ${worker.trade || ''} ${worker.supplier || ''} ${worker.rate || ''} ${worker.status || ''}`.toLowerCase();
      return statusMatch && supplierMatch && tradeMatch && (!q || haystack.includes(q));
    });
    const advancedCount = [state.projectWorkerSupplier !== 'All suppliers', state.projectWorkerTrade !== 'All trades'].filter(Boolean).length;
    const hasFilters = !!state.projectWorkerSearch || state.projectWorkerStatus !== 'All statuses' || advancedCount > 0;
    return `
      <section class="data-panel">
        <div class="section-headline">
          <div><h2>Project manpower</h2><p>Supplier workers currently or historically assigned to ${escapeHtml(project.name)}.</p></div>
          <div class="section-headline__actions"><span class="inline-stat"><strong>${activeWorkers || project.rentalWorkers}</strong> active rental</span>${releasedWorkers ? `<span class="inline-stat"><strong>${releasedWorkers}</strong> historical</span>` : ''}<button class="btn btn--secondary" data-project-bulk-onboard="${escapeHtml(project.id)}">Bulk Assign</button><button class="btn btn--primary" data-project-add-worker="${escapeHtml(project.id)}">${icon('plus')} Assign Worker</button></div>
        </div>
        <div class="table-toolbar table-toolbar--inside">
          <div class="table-toolbar__search">${icon('search')}<input id="projectWorkerSearch" type="search" placeholder="Search worker, trade or supplier" value="${escapeHtml(state.projectWorkerSearch)}"></div>
          <select id="projectWorkerStatusFilter" class="ui-v2-select ui-v2-payroll-operational-select" aria-label="Filter project workers by status">${['All statuses','Assigned','Released','Transferred'].map(value=>`<option ${state.projectWorkerStatus===value?'selected':''}>${value}</option>`).join('')}</select>
          <button class="btn btn--ghost ${advancedCount ? 'is-active-filter' : ''}" data-project-workforce-filter aria-expanded="${state.projectWorkerFiltersOpen}">${icon('more')} Filters${advancedCount ? ` (${advancedCount})` : ''}</button>
          ${hasFilters ? '<button class="btn btn--ghost" data-project-workforce-reset>Reset</button>' : ''}
        </div>
        ${state.projectWorkerFiltersOpen ? `<div class="ui-v2-payroll-advanced-filters ui-v2-payroll-advanced-filters--compact" data-advanced-filter-panel>
          <label><span>Supplier</span><select id="projectWorkerSupplierFilter" class="ui-v2-select"><option>All suppliers</option>${supplierOptions.map(value=>`<option ${state.projectWorkerSupplier===value?'selected':''}>${escapeHtml(value)}</option>`).join('')}</select></label>
          <label><span>Trade</span><select id="projectWorkerTradeFilter" class="ui-v2-select"><option>All trades</option>${tradeOptions.map(value=>`<option ${state.projectWorkerTrade===value?'selected':''}>${escapeHtml(value)}</option>`).join('')}</select></label>
          <button class="btn btn--secondary" type="button" data-project-workforce-advanced-reset>Clear advanced</button>
        </div>` : ''}
        <div class="table-meta"><span><strong>${filteredWorkers.length}</strong> worker${filteredWorkers.length===1?'':'s'} in this view</span><span>Search and filters apply to the current project assignment roster.</span></div>
        <div class="table-scroll">
          <table class="data-table workforce-table">
            <thead><tr><th>Worker</th><th>Type</th><th>Supplier</th><th>Trade</th><th>Rate</th><th>Assigned Since</th><th>Status</th><th></th></tr></thead>
            <tbody data-worker-body>
              ${filteredWorkers.length ? filteredWorkers.map(worker => workerRow(worker)).join('') : `<tr><td colspan="8"><div class="table-empty"><strong>No project workers match these filters.</strong><span>Reset the search/filter controls or assign a worker to this project.</span></div></td></tr>`}
            </tbody>
          </table>
        </div>
      </section>`;
  }

  function workerRow(worker) {
    return `<tr data-worker-search-row="${escapeHtml(`${worker.name} ${worker.trade} ${worker.supplier}`.toLowerCase())}">
      <td><button class="entity-link entity-link--stack" data-worker-profile="${escapeHtml(worker.name)}"><strong>${escapeHtml(worker.name)}</strong><span>${worker.changed ? 'Assignment history available' : 'Rental worker profile'}</span></button></td>
      <td><span class="type-pill">${escapeHtml(worker.type)}</span></td>
      <td><button class="entity-link" data-route-link="${worker.supplierId ? `suppliers/${worker.supplierId}` : supplierRouteByName(worker.supplier)}">${escapeHtml(worker.supplier)}</button></td>
      <td><div class="table-primary">${escapeHtml(worker.trade)}</div>${worker.changed ? '<div class="table-secondary table-secondary--attention">Effective-dated history</div>' : ''}</td>
      <td><div class="table-primary">${escapeHtml(worker.rate)}</div></td>
      <td><div class="table-primary">${escapeHtml(worker.since)}</div></td>
      <td>${statusBadge(worker.status)}</td>
      <td class="table-actions"><button class="icon-btn icon-btn--sm" type="button" data-worker-menu="${escapeHtml(worker.name)}" aria-label="Worker actions">${icon('more')}</button></td>
    </tr>`;
  }

  function projectSuppliersTab(project, suppliers) {
    return `
      <div class="profile-grid profile-grid--wide-side">
        <section class="data-panel">
          <div class="section-headline">
            <div><h2>Manpower suppliers on this project</h2><p>Supplier records are linked once and reused when assigning workers.</p></div>
            <button class="btn btn--primary" data-quick-add="supplier">${icon('plus')} Add Supplier</button>
          </div>
          <div class="supplier-project-list">
            ${suppliers.length ? suppliers.map(s => `
              <article class="supplier-project-card">
                <div class="supplier-project-card__main">
                  <span class="entity-avatar entity-avatar--supplier">${icon('supplier')}</span>
                  <div><button class="entity-link entity-link--title" data-route-link="suppliers/${s.id}">${escapeHtml(s.name)}</button><p>${escapeHtml(s.note || 'Active manpower supplier')}</p></div>
                </div>
                <div class="supplier-project-card__stats">
                  <div><span>Active workers</span><strong>${s.workers}</strong></div>
                  <div><span>Hours</span><strong>${s.hours.toLocaleString()}</strong></div>
                  <div><span>Current cost</span><strong>${formatCurrency(s.currentCost)}</strong></div>
                  <div><span>Status</span>${statusBadge(s.status)}</div>
                </div>
                <div class="supplier-project-card__footer"><button class="text-link" data-route-link="suppliers/${s.id}">Open supplier profile →</button><button class="btn btn--ghost" data-project-action="supplier-workers">View ${s.workers} workers</button></div>
              </article>`).join('') : `<div class="table-empty table-empty--card"><strong>No manpower suppliers linked.</strong><span>Create a supplier master, then assign workers from that supplier to this project.</span><button class="btn btn--secondary" data-quick-add="supplier">Add supplier</button></div>`}
          </div>
        </section>
        <aside class="detail-card assignment-rule-card">
          <div class="detail-card__head"><h3>Assignment rule</h3></div>
          <p>A worker must select an existing supplier and project master. Transfers close the old assignment and create a new effective-dated assignment instead of overwriting history.</p>
          <div class="rule-flow"><span>Supplier</span><b>→</b><span>Worker</span><b>→</b><span>Assignment</span><b>→</b><span>Project</span></div>
        </aside>
      </div>`;
  }

  function projectTimesheetsTab(project) {
    return `
      <section class="data-panel"><div class="section-headline"><div><h2>Project timesheets</h2><p>Monthly worker hours are stored by project and resolved against effective assignment history.</p></div><button class="btn btn--primary" data-open-rental-timesheet-project="${escapeHtml(project.id)}" data-timesheet-period="${escapeHtml(state.period)}">${icon('timesheet')} Open ${escapeHtml(state.period)}</button></div><div class="table-empty table-empty--card"><strong>Open the project timesheet workspace</strong><span>The selected project/period view loads its authoritative Django timesheet, workflow status and daily records.</span></div></section>`;
  }
  function projectCostTab(project) {
    const rows = Object.values(state.rentalSettlements || {}).filter(item => item.period === state.period && item.projectId === project.id);
    const totals = rows.reduce((acc,item)=>{acc.hours+=Number(item.totals?.regularHours||0);acc.ot+=Number(item.totals?.overtimeHours||0);acc.gross+=Number(item.totals?.gross||0);acc.adjustments+=Number(item.totals?.adjustments||0);acc.net+=Number(item.totals?.net||0);acc.outstanding+=Number(item.totals?.outstanding||0);return acc;},{hours:0,ot:0,gross:0,adjustments:0,net:0,outstanding:0});
    return `<div class="profile-grid profile-grid--cost"><section class="panel panel--flush"><div class="panel__head panel__head--padded"><div><h2>Rental manpower cost</h2><p>Controlled supplier-settlement snapshots for this project and period.</p></div><span class="period-chip">${escapeHtml(state.period)}</span></div>${rows.length?`<div class="cost-detail-grid"><div><span>Regular hours</span><strong>${totals.hours.toLocaleString('en-SA',{maximumFractionDigits:2})}</strong></div><div><span>OT hours</span><strong>${totals.ot.toLocaleString('en-SA',{maximumFractionDigits:2})}</strong></div><div><span>Gross amount</span><strong>${formatCurrency(totals.gross)}</strong></div><div><span>Adjustments</span><strong>${formatCurrency(totals.adjustments)}</strong></div></div><div class="cost-total-banner"><span>Net rental manpower cost</span><strong>${formatCurrency(totals.net)}</strong></div>`:`<div class="table-empty table-empty--card"><strong>No settlement snapshot for ${escapeHtml(state.period)}.</strong><span>Lock the project timesheet, then calculate the supplier settlement.</span></div>`}</section><aside class="profile-side-stack"><section class="detail-card"><div class="detail-card__head"><h3>Cost controls</h3></div><div class="rental-worker-actions-list"><button data-open-rental-settlement-project="${escapeHtml(project.id)}" data-settlement-period="${escapeHtml(state.period)}">Open rental settlement ${icon('chevron')}</button><button data-open-rental-timesheet-project="${escapeHtml(project.id)}" data-timesheet-period="${escapeHtml(state.period)}">Review project timesheet ${icon('chevron')}</button><button data-open-report="rental-project-cost" data-report-project="${escapeHtml(project.id)}" data-report-period="${escapeHtml(state.period)}">Open project cost report ${icon('chevron')}</button></div></section><section class="detail-card"><div class="detail-card__head"><h3>Outstanding</h3></div><div class="cost-total-banner"><span>Supplier payable</span><strong>${rows.length?formatCurrency(totals.outstanding):'—'}</strong></div></section></aside></div>`;
  }
  function projectDocumentsTab(project) {
    const docs = [
      ['TS','Project Timesheet','Attendance / hours document','Timesheets'],
      ['RS','Rental Settlement','Supplier/project monthly cost','Settlement'],
      ['IN','Manpower Invoice','Letterhead invoice output','Invoice'],
      ['RC','Payment Receipt','Linked payment acknowledgement','Receipt']
    ];
    return `
      <section class="data-panel">
        <div class="section-headline"><div><h2>Project documents</h2><p>Documents remain linked to the project, payroll period and underlying records.</p></div><button class="btn btn--secondary" data-route-link="documents">Open Document Center</button></div>
        <div class="document-grid">
          ${docs.map(([code,name,meta,type]) => `<button class="document-tile" data-route-link="documents"><span>${code}</span><div><strong>${name}</strong><small>${meta}</small></div><em>${type}</em>${icon('chevron')}</button>`).join('')}
        </div>
      </section>`;
  }


  function suppliersTemplate() {
    if (!state.rentalSettlementLoadedPeriods.has(state.period) && state.rentalSettlementLoadingPeriod !== state.period) loadRentalSettlementContext(state.period, { render:true });
    const controlRows = rentalSupplierControlRows();
    const controlBySupplier = new Map(controlRows.map(row => [row.supplier.id, row]));
    const workforceBySupplier = new Map(state.suppliers.map(supplier => [supplier.id, { total:0, assigned:0, available:0, released:0, projects:new Set() }]));
    state.rentalWorkers.forEach(worker => {
      const metric = workforceBySupplier.get(worker.supplierId);
      if (!metric) return;
      metric.total += 1;
      if (worker.status === 'Assigned') { metric.assigned += 1; if (worker.projectId) metric.projects.add(worker.projectId); }
      else if (worker.status === 'Available') metric.available += 1;
      else if (worker.status === 'Released') metric.released += 1;
    });
    const supplierStats = supplierId => { const metric=workforceBySupplier.get(supplierId)||{total:0,assigned:0,available:0,released:0,projects:new Set()}; return { ...metric, activeProjects:metric.projects.size }; };
    const supplierProjectIds = new Map();
    state.rentalWorkers.forEach(worker => {
      if (worker.status !== 'Assigned' || !worker.supplierId) return;
      const projectId = rentalWorkerCurrentSnapshot(worker).project?.id || worker.projectId;
      if (!projectId) return;
      if (!supplierProjectIds.has(worker.supplierId)) supplierProjectIds.set(worker.supplierId, new Set());
      supplierProjectIds.get(worker.supplierId).add(projectId);
    });
    const q = state.supplierSearch.trim().toLowerCase();
    const suppliers = state.suppliers.filter(supplier => {
      const matchesStatus = state.supplierStatus === 'All' || supplier.status === state.supplierStatus;
      const stats = supplierStats(supplier.id);
      const control = controlBySupplier.get(supplier.id);
      const projectMatch = state.supplierProject === 'All projects' || supplierProjectIds.get(supplier.id)?.has(state.supplierProject);
      const paymentTerm = supplier.paymentTerms || 'Payment terms not set';
      const paymentTermMatch = state.supplierPaymentTerm === 'All payment terms' || paymentTerm === state.supplierPaymentTerm;
      const workforceMatch = state.supplierWorkforce === 'Any workforce'
        || (state.supplierWorkforce === 'Assigned workers' && stats.assigned > 0)
        || (state.supplierWorkforce === 'Available workers' && stats.available > 0)
        || (state.supplierWorkforce === 'No active workers' && stats.assigned + stats.available === 0);
      const outstanding = Number(control?.outstanding || 0);
      const outstandingMatch = state.supplierOutstanding === 'Any balance'
        || (state.supplierOutstanding === 'Open payable' && outstanding > .005)
        || (state.supplierOutstanding === 'Cleared / none' && outstanding <= .005);
      const haystack = `${supplier.name} ${supplier.code} ${supplier.contact || ''} ${supplier.phone || ''} ${supplier.address || ''} ${supplier.email || ''} ${supplier.cr || ''} ${supplier.vat || ''}`.toLowerCase();
      return matchesStatus && projectMatch && paymentTermMatch && workforceMatch && outstandingMatch && (!q || haystack.includes(q));
    });
    const active = state.suppliers.filter(s => s.status === 'Active').length;
    const assigned = state.rentalWorkers.filter(worker => worker.status === 'Assigned').length;
    const available = state.rentalWorkers.filter(worker => worker.status === 'Available').length;
    const currentCost = controlRows.reduce((sum, row) => sum + Number(row.payable || 0), 0);
    const paymentTermOptions = [...new Set(state.suppliers.map(s => s.paymentTerms || 'Payment terms not set'))].sort((a,b)=>a.localeCompare(b));
    const supplierAdvancedCount = [
      state.supplierProject !== 'All projects',
      state.supplierPaymentTerm !== 'All payment terms',
      state.supplierWorkforce !== 'Any workforce',
      state.supplierOutstanding !== 'Any balance'
    ].filter(Boolean).length;
    const supplierHasFilters = !!state.supplierSearch || state.supplierStatus !== 'All' || supplierAdvancedCount > 0;

    return `
      <section class="page supplier-directory">
        <div class="page-head">
          <div class="page-head__copy">
            <div class="eyebrow">Operations</div>
            <h1>Manpower Suppliers</h1>
            <p>Maintain one supplier company record, see every deployed worker and project, and keep settlement/payment history connected.</p>
          </div>
          <div class="page-head__actions">
            <button class="btn btn--secondary" data-supplier-export>Export</button>
            <button class="btn btn--primary" data-quick-add="supplier">${icon('plus')} Add Supplier</button>
          </div>
        </div>

        <div class="summary-strip summary-strip--4">
          <div class="summary-item"><span>Active suppliers</span><strong>${active}</strong><small>${state.suppliers.length} total master records</small></div>
          <div class="summary-item"><span>Assigned workers</span><strong>${assigned}</strong><small>Current project assignments</small></div>
          <div class="summary-item"><span>Available workers</span><strong>${available}</strong><small>Ready for a new assignment</small></div>
          <div class="summary-item"><span>Known current cost</span><strong>${formatCurrency(currentCost)}</strong><small>Controlled rental records</small></div>
        </div>

        <section class="data-panel">
          <div class="table-toolbar">
            <div class="table-toolbar__search">${icon('search')}<input id="supplierSearch" type="search" placeholder="Search supplier, code, contact or location" value="${escapeHtml(state.supplierSearch)}"></div>
            <div class="segmented segmented--compact" aria-label="Supplier status filter">
              ${['All','Active','Inactive','Terminated','Archived'].map(status => `<button type="button" data-supplier-status="${status}" class="${state.supplierStatus === status ? 'is-active' : ''}">${status}</button>`).join('')}
            </div>
            <button class="btn btn--ghost ${supplierAdvancedCount ? 'is-active-filter' : ''}" data-supplier-filter aria-expanded="${state.supplierFiltersOpen}">${icon('more')} More filters${supplierAdvancedCount ? ` (${supplierAdvancedCount})` : ''}</button>
            ${supplierHasFilters ? '<button class="btn btn--ghost" data-supplier-reset>Reset</button>' : ''}
          </div>
          ${state.supplierFiltersOpen ? `<div class="ui-v2-payroll-advanced-filters" data-advanced-filter-panel>
            <label><span>Project</span><select id="supplierProjectFilter" class="ui-v2-select"><option value="All projects">All projects</option>${state.projects.filter(p=>!p.legacyInternal && p.status==='Active').map(p=>`<option value="${escapeHtml(p.id)}" ${state.supplierProject===p.id?'selected':''}>${escapeHtml(p.name)}</option>`).join('')}</select></label>
            <label><span>Payment terms</span><select id="supplierPaymentTermFilter" class="ui-v2-select"><option>All payment terms</option>${paymentTermOptions.map(value=>`<option ${state.supplierPaymentTerm===value?'selected':''}>${escapeHtml(value)}</option>`).join('')}</select></label>
            <label><span>Workforce</span><select id="supplierWorkforceFilter" class="ui-v2-select">${['Any workforce','Assigned workers','Available workers','No active workers'].map(value=>`<option ${state.supplierWorkforce===value?'selected':''}>${value}</option>`).join('')}</select></label>
            <label><span>Payable</span><select id="supplierOutstandingFilter" class="ui-v2-select">${['Any balance','Open payable','Cleared / none'].map(value=>`<option ${state.supplierOutstanding===value?'selected':''}>${value}</option>`).join('')}</select></label>
            <button class="btn btn--secondary" type="button" data-supplier-advanced-reset>Clear advanced</button>
          </div>` : ''}
          <div class="table-meta"><span><strong>${suppliers.length}</strong> supplier${suppliers.length === 1 ? '' : 's'}</span><span>Open a supplier to see workers, projects, settlements and payments.</span></div>
          <div class="table-scroll">
            <table class="data-table supplier-table">
              <thead><tr><th>Supplier</th><th>Contact</th><th>Assigned</th><th>Available</th><th>Projects</th><th>Current Cost</th><th>Outstanding</th><th>Status</th><th></th></tr></thead>
              <tbody>
                ${suppliers.length ? suppliers.map(supplier => { const stats = supplierStats(supplier.id); const control=controlBySupplier.get(supplier.id); return `
                  <tr>
                    <td><button class="entity-link entity-link--stack" data-open-supplier="${supplier.id}"><strong>${escapeHtml(supplier.name)}</strong><span>${escapeHtml(supplier.code)} · ${escapeHtml(supplier.paymentTerms || 'Payment terms not set')}</span></button></td>
                    <td><div class="table-primary">${escapeHtml(supplier.contact || '—')}</div><div class="table-secondary">${escapeHtml(supplier.phone || '—')}</div></td>
                    <td><span class="table-number">${stats.assigned}</span></td>
                    <td><span class="table-number">${stats.available}</span></td>
                    <td><span class="table-number">${stats.activeProjects}</span></td>
                    <td><div class="table-primary">${control?.payable ? formatCurrency(control.payable) : '—'}</div><div class="table-secondary">${escapeHtml(state.period)}</div></td>
                    <td><div class="table-primary">${formatCurrency(control?.outstanding || 0)}</div><div class="table-secondary">${control?.outstanding > .005 ? 'Open payable' : 'Cleared / none'}</div></td>
                    <td>${statusBadge(supplier.status)}</td>
                    <td class="table-actions"><button class="icon-btn icon-btn--sm" type="button" data-supplier-row-menu="${supplier.id}" aria-label="Supplier actions">${icon('more')}</button></td>
                  </tr>`; }).join('') : `<tr><td colspan="9"><div class="table-empty"><strong>No suppliers match these filters.</strong><span>Change the search/status filter or add a manpower supplier.</span></div></td></tr>`}
              </tbody>
            </table>
          </div>
        </section>

        <div class="source-banner">${icon('info')}<span>Supplier companies are managed masters. Stop activity is temporary; Terminate ends the relationship; Archive and 30-day Delete preserve worker, assignment, settlement and payment history.</span></div>
      </section>`;
  }

  function supplierProfileTemplate(supplier) {
    if (!state.rentalSettlementLoadedPeriods.has(state.period) && state.rentalSettlementLoadingPeriod !== state.period) loadRentalSettlementContext(state.period, { render:true });
    if (!supplier) return missingSupplierTemplate();
    const workers = state.rentalWorkers.filter(worker => worker.supplierId === supplier.id);
    const projects = supplierProjectsForProfile(supplier.id);
    const settlements = Object.values(state.rentalSettlements || {}).filter(item => item.period === state.period && item.supplierId === supplier.id);
    const payments = state.supplierPayments?.[supplier.id] || [];
    const workforceStats = supplierWorkforceStats(supplier.id);
    const control = rentalSupplierControlRows().find(row => row.supplier.id === supplier.id) || null;
    const tab = state.supplierTab;
    return `
      <section class="page supplier-profile">
        <div class="profile-crumb ui-v2-payroll-profile-crumb"><button type="button" class="text-link text-link--muted" data-route-link="suppliers">Manpower Suppliers</button><span>›</span><span>${escapeHtml(supplier.code)}</span></div>
        <header class="entity-header">
          <div class="entity-header__identity">
            <span class="entity-avatar entity-avatar--supplier">${icon('supplier')}</span>
            <div>
              <div class="entity-title-row ui-v2-payroll-entity-title"><h1>${escapeHtml(supplier.name)}</h1>${statusBadge(supplier.status)}</div>
              <div class="entity-subline"><span>${escapeHtml(supplier.code)}</span><span>·</span><span>${escapeHtml(supplier.contact || 'No contact')}</span><span>·</span><span>${escapeHtml(supplier.phone || 'No phone')}</span></div>
            </div>
          </div>
          <div class="entity-header__actions ui-v2-payroll-entity-header__actions">
            <button class="btn btn--secondary" data-supplier-assignment-activity="${escapeHtml(supplier.id)}">Assignment Activity</button>
            ${!supplier.archived && supplier.status === 'Active' ? `<button class="btn btn--secondary" data-supplier-bulk-onboard="${escapeHtml(supplier.id)}">Bulk Add</button><button class="btn btn--primary" data-supplier-add-worker="${escapeHtml(supplier.id)}">${icon('plus')} Add Worker</button>` : ''}
            ${lifecycleActionsMenu([
              ...(!supplier.archived ? [{label:'Edit supplier',hint:'Update supplier master details',iconName:'edit',attrs:'data-supplier-action="edit"'}] : []),
              {label:supplier.status==='Terminated'?'Supplier terminated':'Manage supplier status',hint:supplier.status==='Terminated'?'Termination is final for this supplier relationship':'Activate, deactivate, or terminate supplier activity',iconName:'info',disabled:supplier.archived || supplier.status==='Terminated',attrs:`data-rental-master-lifecycle="supplier|${escapeHtml(supplier.id)}|manage"`},
              'separator',
              {label:supplier.archived?'Restore from archive':'Archive supplier',hint:supplier.archived?'Restore previous state':'Archive supplier and its worker scope while preserving history',iconName:'info',attrs:`data-rental-master-lifecycle="supplier|${escapeHtml(supplier.id)}|${supplier.archived?'restore':'archive'}"`},
              {label:'Delete',hint:'Delete with 30-day recovery; worker operational scope follows automatically',iconName:'trash',danger:true,attrs:`data-rental-master-lifecycle="supplier|${escapeHtml(supplier.id)}|delete"`}
            ])}
          </div>
        </header>

        <div class="profile-facts profile-facts--supplier profile-facts--rental-supplier">
          <div><span>Assigned workers</span><strong>${workforceStats.assigned}</strong></div>
          <div><span>Available workers</span><strong>${workforceStats.available}</strong></div>
          <div><span>Active projects</span><strong>${workforceStats.activeProjects}</strong></div>
          <div><span>Settlement payable</span><strong>${formatCurrency(control?.payable || 0)}</strong></div>
          <div><span>Paid</span><strong>${formatCurrency(control?.paid || 0)}</strong></div>
          <div><span>Outstanding</span><strong>${formatCurrency(control?.outstanding || 0)}</strong></div>
        </div>

        <nav class="tabs profile-tabs" aria-label="Supplier profile sections">
          ${[['overview','Overview'],['workers','Workers'],['projects','Projects'],['timesheets','Timesheets'],['settlements','Settlements'],['payments','Payments'],['documents','Documents']].map(([key,label]) => `<button type="button" data-supplier-tab="${key}" class="${tab === key ? 'is-active' : ''}">${label}${key === 'workers' && workers.length ? `<span class="tab-count">${workers.length}</span>` : ''}</button>`).join('')}
        </nav>
        <div class="profile-content">${supplierProfileTab(supplier, tab, workers, projects, settlements, payments)}</div>
      </section>`;
  }

  function supplierProfileTab(supplier, tab, workers, projects, settlements, payments) {
    if (tab === 'workers') return supplierWorkersTab(supplier, workers);
    if (tab === 'projects') return supplierProjectsTab(supplier, projects);
    if (tab === 'timesheets') return supplierTimesheetsTab(supplier, projects);
    if (tab === 'settlements') return supplierSettlementsTab(supplier, settlements);
    if (tab === 'payments') return supplierPaymentsTab(supplier, payments);
    if (tab === 'documents') return supplierDocumentsTab(supplier);
    return supplierOverviewTab(supplier, workers, projects, settlements, rentalSupplierControlRows().find(row => row.supplier.id === supplier.id) || null);
  }

  function supplierOverviewTab(supplier, workers, projects, settlements, control=null) {
    const assigned = workers.filter(w => w.status === 'Assigned').length || supplier.activeWorkers || 0;
    const available = workers.filter(w => w.status === 'Available').length || supplier.availableWorkers || 0;
    const trades = [...new Set(workers.filter(w => w.status === 'Assigned').map(w => w.trade.replace('Helper → ','').replace('New ','')).filter(Boolean))];
    return `
      <div class="profile-grid profile-grid--overview supplier-overview-grid">
        <div class="profile-main-stack">
          <section class="panel panel--flush">
            <div class="panel__head panel__head--padded"><div><h2>Current deployment</h2><p>Where this supplier's workforce is currently assigned.</p></div><button class="text-link" data-supplier-tab-jump="workers">View all workers →</button></div>
            <div class="project-kpis supplier-kpis">
              <div><span>Assigned</span><strong>${assigned}</strong><small>Working on projects</small></div>
              <div><span>Available</span><strong>${available}</strong><small>Ready to assign</small></div>
              <div><span>Hours</span><strong>${supplier.hours ? supplier.hours.toLocaleString() : '—'}</strong><small>Current known period</small></div>
              <div><span>OT hours</span><strong>${supplier.otHours || '—'}</strong><small>Approved / known</small></div>
            </div>
            <div class="supplier-project-list">
              ${projects.length ? projects.map(project => `<button class="supplier-deployment-row" data-route-link="projects/${project.projectId}"><span class="supplier-deployment-row__icon">${icon('project')}</span><span><strong>${escapeHtml(project.project)}</strong><small>${project.workers} workers · ${project.hours.toLocaleString()} hrs</small></span><span class="supplier-deployment-row__amount">${formatCurrency(project.cost)}</span>${icon('chevron')}</button>`).join('') : `<div class="empty-inline">No active project deployment.</div>`}
            </div>
          </section>

          <section class="panel panel--flush">
            <div class="panel__head panel__head--padded"><div><h2>Commercial snapshot</h2><p>Settlement context without mixing supplier cost into internal payroll.</p></div><button class="text-link" data-supplier-tab-jump="settlements">Open settlements →</button></div>
            <div class="cost-detail-grid supplier-commercial-grid">
              <div><span>Current manpower cost</span><strong>${control?.payable ? formatCurrency(control.payable) : '—'}</strong></div>
              <div><span>Outstanding payable</span><strong>${formatCurrency(control?.outstanding || 0)}</strong></div>
              <div><span>Payment terms</span><strong>${escapeHtml(supplier.paymentTerms || '—')}</strong></div>
              <div><span>Latest settlement</span><strong>${settlements[0]?.period || '—'}</strong></div>
            </div>
          </section>
        </div>

        <aside class="detail-stack">
          <section class="detail-card">
            <div class="detail-card__head"><h3>Supplier details</h3><button class="text-link" data-supplier-action="edit">Edit</button></div>
            <dl class="detail-list">
              <div><dt>Contact</dt><dd>${escapeHtml(supplier.contact || '—')}</dd></div>
              <div><dt>Phone</dt><dd>${escapeHtml(supplier.phone || '—')}</dd></div>
              <div><dt>Email</dt><dd>${escapeHtml(supplier.email || '—')}</dd></div>
              <div><dt>CR</dt><dd>${escapeHtml(supplier.cr || '—')}</dd></div>
              <div><dt>VAT</dt><dd>${escapeHtml(supplier.vat || '—')}</dd></div>
              <div><dt>Address</dt><dd>${escapeHtml(supplier.address || '—')}</dd></div>${supplier.inactiveOn?`<div><dt>Activity stopped</dt><dd>${escapeHtml(rentalDisplayDate(supplier.inactiveOn))}</dd></div>`:''}${supplier.inactiveReason?`<div><dt>Stop reason</dt><dd>${escapeHtml(supplier.inactiveReason)}</dd></div>`:''}${supplier.terminatedOn?`<div><dt>Terminated</dt><dd>${escapeHtml(rentalDisplayDate(supplier.terminatedOn))}</dd></div>`:''}${supplier.terminationReason?`<div><dt>Termination reason</dt><dd>${escapeHtml(supplier.terminationReason)}</dd></div>`:''}
            </dl>
          </section>
          <section class="detail-card">
            <div class="detail-card__head"><h3>Workforce mix</h3></div>
            <div class="supplier-trade-pills">${trades.length ? trades.slice(0,6).map(trade => `<span>${escapeHtml(trade)}</span>`).join('') : '<span>No active trades</span>'}</div>
            <p class="detail-note">Worker identity stays permanent while project, trade and rate are effective-dated assignments.</p>
          </section>
        </aside>
      </div>`;
  }

  function supplierWorkersTab(supplier, workers) {
    const q = state.supplierWorkerSearch.trim().toLowerCase();
    const projectOptions = [...new Set(workers.map(worker=>worker.project).filter(value=>value && !String(value).toLowerCase().startsWith('available') && value !== 'Inactive'))].sort((a,b)=>a.localeCompare(b));
    const tradeOptions = [...new Set(workers.map(worker=>worker.trade).filter(Boolean))].sort((a,b)=>a.localeCompare(b));
    if (state.supplierWorkerProject !== 'All projects' && !projectOptions.includes(state.supplierWorkerProject)) state.supplierWorkerProject = 'All projects';
    if (state.supplierWorkerTrade !== 'All trades' && !tradeOptions.includes(state.supplierWorkerTrade)) state.supplierWorkerTrade = 'All trades';
    const filteredWorkers = workers.filter(worker => {
      const statusMatch = state.supplierWorkerStatus === 'All statuses' || worker.status === state.supplierWorkerStatus;
      const projectMatch = state.supplierWorkerProject === 'All projects' || worker.project === state.supplierWorkerProject;
      const tradeMatch = state.supplierWorkerTrade === 'All trades' || worker.trade === state.supplierWorkerTrade;
      const haystack = `${worker.name} ${worker.id || ''} ${worker.trade || ''} ${worker.project || ''} ${worker.rate || ''} ${worker.status || ''}`.toLowerCase();
      return statusMatch && projectMatch && tradeMatch && (!q || haystack.includes(q));
    });
    const advancedCount = [state.supplierWorkerProject !== 'All projects', state.supplierWorkerTrade !== 'All trades'].filter(Boolean).length;
    const hasFilters = !!state.supplierWorkerSearch || state.supplierWorkerStatus !== 'All statuses' || advancedCount > 0;
    return `
      <section class="data-panel">
        <div class="section-headline"><div><h2>Supplier workers</h2><p>See exactly who is assigned, where they are working and which workers are currently available.</p></div><div class="section-headline__actions"><button class="btn btn--secondary ${advancedCount ? 'is-active-filter' : ''}" data-supplier-worker-filter aria-expanded="${state.supplierWorkerFiltersOpen}">${icon('more')} Filters${advancedCount ? ` (${advancedCount})` : ''}</button><button class="btn btn--primary" data-quick-add="rental-worker">${icon('plus')} Add Worker</button></div></div>
        <div class="table-toolbar table-toolbar--inner"><div class="table-toolbar__search">${icon('search')}<input id="supplierWorkerSearch" type="search" placeholder="Search worker, trade or project" value="${escapeHtml(state.supplierWorkerSearch)}"></div><div class="segmented segmented--compact" aria-label="Supplier worker status filter">${[['All statuses','All'],['Assigned','Assigned'],['Scheduled','Scheduled'],['Available','Available'],['Inactive','Inactive'],['Terminated','Terminated'],['Archived','Archived']].map(([value,label])=>`<button type="button" data-supplier-worker-status="${value}" class="${state.supplierWorkerStatus===value?'is-active':''}">${label}</button>`).join('')}</div>${hasFilters ? '<button class="btn btn--ghost" data-supplier-worker-reset>Reset</button>' : ''}</div>
        ${state.supplierWorkerFiltersOpen ? `<div class="ui-v2-payroll-advanced-filters ui-v2-payroll-advanced-filters--compact" data-advanced-filter-panel>
          <label><span>Project</span><select id="supplierWorkerProjectFilter" class="ui-v2-select"><option>All projects</option>${projectOptions.map(value=>`<option ${state.supplierWorkerProject===value?'selected':''}>${escapeHtml(value)}</option>`).join('')}</select></label>
          <label><span>Trade</span><select id="supplierWorkerTradeFilter" class="ui-v2-select"><option>All trades</option>${tradeOptions.map(value=>`<option ${state.supplierWorkerTrade===value?'selected':''}>${escapeHtml(value)}</option>`).join('')}</select></label>
          <button class="btn btn--secondary" type="button" data-supplier-worker-advanced-reset>Clear advanced</button>
        </div>` : ''}
        <div class="table-meta"><span><strong>${filteredWorkers.length}</strong> worker${filteredWorkers.length===1?'':'s'} in this view</span><span>Filters use the current effective supplier/project assignment snapshot.</span></div>
        <div class="table-scroll"><table class="data-table"><thead><tr><th>Worker</th><th>Trade</th><th>Current Project</th><th>Rate</th><th>Assigned Since</th><th>Status</th><th></th></tr></thead><tbody>
          ${filteredWorkers.length ? filteredWorkers.map(worker => `<tr><td><button class="entity-link entity-link--stack" data-worker-profile="${escapeHtml(worker.name)}"><strong>${escapeHtml(worker.name)}</strong><span>${escapeHtml(worker.id.toUpperCase())}</span></button></td><td><div class="table-primary">${escapeHtml(worker.trade)}</div>${worker.changed ? '<div class="table-secondary">Effective-dated change</div>' : ''}</td><td>${worker.projectId ? `<button class="entity-link" data-route-link="projects/${worker.projectId}">${escapeHtml(worker.project)}</button>` : `<span class="table-secondary">${escapeHtml(worker.project)}</span>`}</td><td>${escapeHtml(worker.rate)}</td><td>${escapeHtml(worker.since)}</td><td>${statusBadge(worker.status)}</td><td class="table-actions"><button class="icon-btn icon-btn--sm" data-worker-menu="${escapeHtml(worker.name)}">${icon('more')}</button></td></tr>`).join('') : `<tr><td colspan="7"><div class="table-empty"><strong>No supplier workers match these filters.</strong><span>Reset the search/filter controls or add a worker to this supplier.</span></div></td></tr>`}
        </tbody></table></div>
      </section>`;
  }

  function supplierProjectsTab(supplier, projects) {
    return `
      <section class="data-panel">
        <div class="section-headline"><div><h2>Project deployment</h2><p>Project-by-project view of this supplier's manpower and current cost.</p></div><button class="btn btn--secondary" data-route-link="projects">All Projects</button></div>
        <div class="supplier-project-grid">
          ${projects.length ? projects.map(project => `<article class="supplier-project-card"><div class="supplier-project-card__head"><span class="supplier-project-card__icon">${icon('project')}</span><div><button class="entity-link entity-link--title" data-route-link="projects/${project.projectId}">${escapeHtml(project.project)}</button><p>${project.workers} currently assigned workers</p></div>${statusBadge(project.status)}</div><div class="supplier-project-card__metrics"><div><span>Workers</span><strong>${project.workers}</strong></div><div><span>Hours</span><strong>${project.hours.toLocaleString()}</strong></div><div><span>OT</span><strong>${project.otHours || '—'}</strong></div><div><span>Current cost</span><strong>${formatCurrency(project.cost)}</strong></div></div><div class="supplier-project-card__footer"><button class="text-link" data-route-link="projects/${project.projectId}">Open project profile →</button><button class="btn btn--ghost" data-supplier-tab-jump="workers">View workers</button></div></article>`).join('') : `<div class="table-empty table-empty--card"><strong>No active project deployment.</strong><span>Available supplier workers can be assigned from their worker profile or Add Worker flow.</span></div>`}
        </div>
      </section>`;
  }

  function supplierTimesheetsTab(supplier, projects) {
    return `<section class="data-panel"><div class="section-headline"><div><h2>Supplier timesheets</h2><p>Timesheets remain project-based. Open a deployed project to review the selected period.</p></div><button class="btn btn--primary" data-open-rental-timesheet-supplier="${escapeHtml(supplier.id)}">${icon('timesheet')} Open Rental Timesheets</button></div><div class="table-scroll"><table class="data-table"><thead><tr><th>Project</th><th>Period</th><th>Assigned workers</th><th>Status</th><th></th></tr></thead><tbody>${projects.length ? projects.map(project => `<tr><td><button class="entity-link" data-route-link="projects/${project.projectId}">${escapeHtml(project.project)}</button></td><td>${escapeHtml(state.period)}</td><td>${project.workers}</td><td><span class="table-secondary">Load in timesheet workspace</span></td><td class="table-actions"><button class="btn btn--ghost" data-open-rental-timesheet-project="${escapeHtml(project.projectId)}" data-timesheet-period="${escapeHtml(state.period)}">Open</button></td></tr>`).join('') : `<tr><td colspan="5"><div class="table-empty"><strong>No supplier project deployment.</strong><span>Assign workers before creating project timesheets.</span></div></td></tr>`}</tbody></table></div></section>`;
  }
  function supplierSettlementsTab(supplier, settlements) {
    const total = settlements.reduce((sum, item) => sum + Number(item.totals?.net || 0), 0);
    const outstanding = settlements.reduce((sum, item) => sum + Number(item.totals?.outstanding || 0), 0);
    return `
      <section class="data-panel">
        <div class="section-headline"><div><h2>Supplier settlements</h2><p>Approved financial snapshots remain linked to their project timesheet and payment ledger.</p></div><button class="btn btn--primary" data-open-rental-settlement-supplier="${escapeHtml(supplier.id)}">${icon('plus')} Open Settlement Workspace</button></div>
        <div class="settlement-summary"><div><span>Settlement records</span><strong>${settlements.length}</strong></div><div><span>Net payable</span><strong>${settlements.length ? formatCurrency(total) : '—'}</strong></div><div><span>Outstanding</span><strong>${formatCurrency(outstanding)}</strong></div></div>
        <div class="table-scroll"><table class="data-table"><thead><tr><th>Settlement</th><th>Project</th><th>Workers</th><th>Gross</th><th>Adjustments</th><th>Net</th><th>Status</th><th></th></tr></thead><tbody>
          ${settlements.length ? settlements.map(item => `<tr><td><button class="entity-link entity-link--stack" data-open-rental-settlement-project="${escapeHtml(item.projectId)}" data-settlement-supplier="${escapeHtml(supplier.id)}" data-settlement-period="${escapeHtml(item.period)}"><strong>${escapeHtml(item.number || item.period)}</strong><span>${escapeHtml(item.period)} · Timesheet rev ${Number(item.sourceTimesheetRevision||0)}</span></button></td><td>${escapeHtml(item.project)}</td><td>${Number(item.totals?.workers||0)}</td><td>${formatCurrency(Number(item.totals?.gross||0))}</td><td>${formatCurrency(Number(item.totals?.adjustments||0))}</td><td><strong>${formatCurrency(Number(item.totals?.net||0))}</strong></td><td>${rentalSettlementStatusBadge(item.status)}</td><td class="table-actions"><button class="btn btn--ghost" data-open-rental-settlement-project="${escapeHtml(item.projectId)}" data-settlement-supplier="${escapeHtml(supplier.id)}" data-settlement-period="${escapeHtml(item.period)}">Open</button></td></tr>`).join('') : `<tr><td colspan="8"><div class="table-empty"><strong>No settlements yet.</strong><span>Locked project timesheets can be calculated in the Supplier Settlements workspace.</span></div></td></tr>`}
        </tbody></table></div>
      </section>`;
  }

  function supplierPaymentsTab(supplier, payments) {
    return `
      <section class="data-panel">
        <div class="section-headline"><div><h2>Supplier payments</h2><p>Payments link back to a settlement and retain bank/cash/cheque references.</p></div><button class="btn btn--secondary" data-route-link="payments">Open Payments</button></div>
        <div class="table-scroll"><table class="data-table"><thead><tr><th>Reference</th><th>Date</th><th>Method</th><th>Amount</th><th>Status</th><th></th></tr></thead><tbody>
          ${payments.length ? payments.map(item => `<tr><td><button class="entity-link" data-route-link="payments">${escapeHtml(item.ref)}</button></td><td>${escapeHtml(item.date)}</td><td>${escapeHtml(item.method)}</td><td><strong>${formatCurrency(item.amount)}</strong></td><td>${statusBadge(item.status)}</td><td class="table-actions"><button class="btn btn--ghost" data-route-link="payments">View</button></td></tr>`).join('') : `<tr><td colspan="6"><div class="table-empty"><strong>No supplier payments posted.</strong><span>Once a settlement is approved, payments and receipts will appear here.</span></div></td></tr>`}
        </tbody></table></div>
      </section>`;
  }

  function supplierDocumentsTab(supplier) {
    const docs = [['ST','Supplier Statement','Settlements + payment history','Statement'],['RS','Rental Settlement','Monthly manpower calculation','Settlement'],['IN','Manpower Invoice','Letterhead document output','Invoice'],['RC','Payment Receipt','Payment acknowledgement','Receipt']];
    return `<section class="data-panel"><div class="section-headline"><div><h2>Supplier documents</h2><p>Every generated document stays linked to this supplier and its source settlement/payment.</p></div><button class="btn btn--secondary" data-route-link="documents">Document Center</button></div><div class="document-grid">${docs.map(([code,name,meta,type]) => `<button class="document-tile" data-route-link="documents"><span>${code}</span><div><strong>${name}</strong><small>${meta}</small></div><em>${type}</em>${icon('chevron')}</button>`).join('')}</div></section>`;
  }

  function salarySetupTemplate() {
    const activeComponents = state.salaryComponents.filter(item => item.status === 'Active');
    const earningCount = activeComponents.filter(item => item.category === 'Earning').length;
    const deductionCount = activeComponents.filter(item => item.category === 'Deduction').length;
    const configuredEmployees = state.employees.filter(employee => !!employeeProfileData(employee).salary).length;
    const activeOt = state.overtimePolicies.filter(item => item.status === 'Active').length;
    const tabs = [
      ['components','Components'],
      ['structures','Employee Structures'],
      ['overtime','Overtime Policies']
    ];
    let content = salaryComponentsTab();
    if (state.salarySetupTab === 'structures') content = salaryStructuresTab();
    if (state.salarySetupTab === 'overtime') content = salaryOvertimeTab();
    return `
      <section class="page salary-setup-page ui-v2-prs-internal-page ui-v2-prs-internal-execution-page">
        <div class="page-head">
          <div class="page-head__copy">
            <h1>Salary Setup</h1>
            <p>Define reusable earning and deduction components, assign effective-dated employee salary structures, and keep overtime rules configurable.</p>
          </div>
          <div class="page-head__actions">
            <button class="btn btn--secondary" data-salary-structure-new>${icon('users')} Assign Structure</button>
            <button class="btn btn--primary" data-salary-component-add>${icon('plus')} Add Component</button>
          </div>
        </div>

        <div class="salary-setup-summary">
          <div><span>Active components</span><strong>${activeComponents.length}</strong><small>${earningCount} earnings · ${deductionCount} deductions</small></div>
          <div><span>Employee coverage</span><strong>${configuredEmployees}/${state.employees.length}</strong><small>${state.employees.length - configuredEmployees} need salary setup</small></div>
          <div><span>OT policies</span><strong>${activeOt}</strong><small>${activeOt ? 'Configurable formula available' : 'No active overtime policy'}</small></div>
          <div><span>WPS mapping</span><strong>${activeComponents.filter(item => item.wpsMap && item.wpsMap !== 'Not mapped').length}</strong><small>Components mapped to export fields</small></div>
        </div>

        <div class="profile-tabs salary-setup-tabs" role="tablist">
          ${tabs.map(([id,label]) => `<button class="${state.salarySetupTab === id ? 'is-active' : ''}" data-salary-tab="${id}" type="button">${label}</button>`).join('')}
        </div>
        ${content}
      </section>`;
  }

  function salaryComponentsTab() {
    const q = state.salaryComponentSearch.trim().toLowerCase();
    const rows = state.salaryComponents.filter(item => {
      const typeMatch = state.salaryComponentType === 'All' || item.category === state.salaryComponentType;
      const statusMatch = state.salaryComponentStatus === 'All' || item.status === state.salaryComponentStatus;
      const searchMatch = !q || `${item.name} ${item.code} ${item.category} ${item.calculation} ${item.wpsMap}`.toLowerCase().includes(q);
      return typeMatch && statusMatch && searchMatch;
    });
    return `
      <section class="data-panel salary-config-panel">
        <div class="table-toolbar table-toolbar--salary">
          <div class="table-toolbar__search">${icon('search')}<input id="salaryComponentSearch" type="search" value="${escapeHtml(state.salaryComponentSearch)}" placeholder="Search component or code"></div>
          <div class="segmented segmented--compact salary-type-filter">
            ${['All','Earning','Deduction'].map(type => `<button class="${state.salaryComponentType === type ? 'is-active' : ''}" data-salary-component-type="${type}">${type === 'All' ? 'All' : `${type}s`}</button>`).join('')}
          </div>
          <select class="select salary-status-select" id="salaryComponentStatus"><option ${state.salaryComponentStatus === 'Active' ? 'selected' : ''}>Active</option><option ${state.salaryComponentStatus === 'Inactive' ? 'selected' : ''}>Inactive</option><option ${state.salaryComponentStatus === 'Archived' ? 'selected' : ''}>Archived</option><option ${state.salaryComponentStatus === 'All' ? 'selected' : ''}>All</option></select>
          <button class="btn btn--primary" data-salary-component-add>${icon('plus')} Add Component</button>
        </div>
        <div class="table-scroll">
          <table class="data-table salary-components-table">
            <thead><tr><th>Component</th><th>Type</th><th>Usage</th><th>Calculation</th><th>WPS Mapping</th><th>Status</th><th></th></tr></thead>
            <tbody>
              ${rows.length ? rows.map(item => `<tr>
                <td>${item.archived?`<span class="entity-link entity-link--stack"><strong>${escapeHtml(item.name)}</strong><span>${escapeHtml(item.code)}</span></span>`:`<button class="entity-link entity-link--stack" data-salary-component-edit="${item.id}"><strong>${escapeHtml(item.name)}</strong><span>${escapeHtml(item.code)}</span></button>`}</td>
                <td><span class="component-kind component-kind--${item.category.toLowerCase()}">${escapeHtml(item.category)}</span></td>
                <td><div class="table-primary">${escapeHtml(item.recurrence)}</div><div class="table-secondary">${item.recurrence === 'Recurring' ? 'Part of permanent salary structure' : 'Calculated / entered per payroll period'}</div></td>
                <td><div class="table-primary">${escapeHtml(item.calculation)}</div><div class="table-secondary">${item.calculation === 'Manual Amount' ? 'Entered when assigned or processed' : 'Stored recurring component amount'}</div></td>
                <td><span class="mapping-chip ${item.wpsMap === 'Not mapped' ? 'is-muted' : ''}">${escapeHtml(item.wpsMap || 'Not mapped')}</span></td>
                <td>${statusBadge(item.status)}</td>
                <td class="table-actions">${lifecycleActionsMenu([
                  ...(!item.archived ? [{label:'Edit component',hint:'Update future salary setup behaviour',iconName:'edit',attrs:`data-salary-component-edit="${item.id}"`}] : []),
                  'separator',
                  {label:item.archived?'Restore component':'Archive component',hint:item.archived?'Restore as Inactive':'Keep payroll history; remove from new salary setup',iconName:'info',attrs:`data-config-lifecycle="component|${item.id}|${item.archived?'restore':'archive'}"`},
                  {label:'Delete unused component',hint:'Only before salary or overtime references exist',iconName:'more',danger:true,attrs:`data-config-lifecycle="component|${item.id}|delete"`}
                ],{compact:true})}</td>
              </tr>`).join('') : `<tr><td colspan="7"><div class="table-empty"><strong>No salary components match this view.</strong><span>Change the type/status filters or create a new reusable component.</span></div></td></tr>`}
            </tbody>
          </table>
        </div>
        <div class="salary-config-footnote"><span>Component changes affect future salary structures and payroll calculations only.</span><strong>Historical approved payroll snapshots remain unchanged.</strong></div>
      </section>`;
  }

  function salaryStructuresTab() {
    const q = state.salaryStructureSearch.trim().toLowerCase();
    const employees = state.employees.filter(employee => !q || `${employee.name} ${employee.employeeId} ${employee.position} ${employee.department}`.toLowerCase().includes(q));
    const configured = state.employees.filter(employee => !!employeeProfileData(employee).salary).length;
    return `
      <section class="data-panel salary-config-panel">
        <div class="section-headline salary-structure-head"><div><h2>Employee salary structures</h2><p>Each employee keeps an effective-dated structure. Effective-dated history is retained; changes create the next effective record and never rewrite a closed payroll period.</p></div><button class="btn btn--primary" data-salary-structure-new>${icon('plus')} Assign Structure</button></div>
        <div class="structure-coverage">
          <div class="structure-coverage__copy"><span>Configuration coverage</span><strong>${configured} of ${state.employees.length} employees</strong><small>${state.employees.length - configured} records still need a numeric salary structure.</small></div>
          <div class="structure-progress"><span style="width:${state.employees.length ? Math.round(configured/state.employees.length*100) : 0}%"></span></div>
          <em>${state.employees.length ? Math.round(configured/state.employees.length*100) : 0}%</em>
        </div>
        <div class="table-toolbar table-toolbar--inner">
          <div class="table-toolbar__search">${icon('search')}<input id="salaryStructureSearch" type="search" value="${escapeHtml(state.salaryStructureSearch)}" placeholder="Search employee, ID or position"></div>
          <button class="btn btn--secondary" data-route-link="internal-employees">Employee Directory</button>
        </div>
        <div class="table-scroll">
          <table class="data-table salary-structures-table">
            <thead><tr><th>Employee</th><th>Current Structure</th><th>Basic Salary</th><th>Fixed Earnings</th><th>Fixed Deductions</th><th>Overtime</th><th>Effective Until</th><th></th></tr></thead>
            <tbody>${employees.map(employee => {
              const profile = employeeProfileData(employee);
              const salary = profile.salary;
              if (!salary) return `<tr><td><button class="entity-link entity-link--stack" data-open-employee="${employee.id}"><strong>${escapeHtml(employee.name)}</strong><span>EMP ${escapeHtml(employee.employeeId)} · ${escapeHtml(employee.position)}</span></button></td><td><span class="setup-state setup-state--needed">Needs setup</span></td><td>—</td><td>—</td><td>—</td><td>Company policy</td><td><span class="table-secondary">—</span></td><td class="table-actions"><button class="btn btn--ghost btn--sm" data-salary-structure-edit="${employee.id}">Configure</button></td></tr>`;
              const earnings = salary.components.filter(c => c.type === 'earning').reduce((sum,c)=>sum+(Number(c.amount)||0),0);
              const deductions = salary.components.filter(c => c.type === 'deduction').reduce((sum,c)=>sum+(Number(c.amount)||0),0);
              const basic = salaryBasicComponent(salary)?.amount;
              return `<tr><td><button class="entity-link entity-link--stack" data-open-employee="${employee.id}"><strong>${escapeHtml(employee.name)}</strong><span>EMP ${escapeHtml(employee.employeeId)} · ${escapeHtml(employee.position)}</span></button></td><td><span class="setup-state setup-state--ready">Configured</span><div class="table-secondary">Effective ${escapeHtml(salary.effective || 'Current')}</div></td><td class="table-money"><strong>${Number.isFinite(Number(basic)) ? formatCurrency(Number(basic)) : '—'}</strong></td><td class="table-money">${formatCurrency(earnings)}</td><td class="table-money">${formatCurrency(deductions)}</td><td><div class="table-primary">${escapeHtml(salary.otPolicy || 'Not assigned')}</div></td><td><div class="table-primary">${escapeHtml(salary.effectiveTo || 'Current')}</div></td><td class="table-actions"><button class="btn btn--ghost btn--sm" data-salary-structure-edit="${employee.id}">Create effective change</button></td></tr>`;
            }).join('')}</tbody>
          </table>
        </div>
      </section>`;
  }

  function salaryOvertimeTab() {
    const visiblePolicies = state.overtimePolicies.filter(item => state.overtimePolicyStatus === 'All' || item.status === state.overtimePolicyStatus);
    const active = state.overtimePolicies.find(item => item.status === 'Active') || null;
    const formula = active ? `${active.baseComponent} ÷ ${active.divisor} × OT hours × ${active.multiplier}` : 'No active policy';
    return `
      <div class="salary-overtime-layout">
        <section class="data-panel salary-config-panel">
          <div class="section-headline"><div><h2>Overtime policies</h2><p>Keep the company formula configurable and assign it to employee salary structures instead of hard-coding it into payroll.</p></div><div class="payment-head-actions"><select class="select" id="overtimePolicyStatus">${['Active','Inactive','Archived','All'].map(status=>`<option ${state.overtimePolicyStatus===status?'selected':''}>${status}</option>`).join('')}</select><button class="btn btn--primary" data-overtime-policy-add>${icon('plus')} Add Policy</button></div></div>
          <div class="ot-policy-list">
            ${visiblePolicies.length ? visiblePolicies.map(policy => `<article class="ot-policy-card ${policy.status === 'Active' ? 'is-active' : ''}">
              <div class="ot-policy-card__head"><div><span class="ot-policy-icon">OT</span><div><strong>${escapeHtml(policy.name)}</strong><small>${escapeHtml(policy.code || 'Overtime policy')}</small></div></div>${statusBadge(policy.status)}</div>
              <div class="ot-formula">${escapeHtml(policy.baseComponent)} <span>÷</span> ${escapeHtml(policy.divisor)} <span>×</span> OT hours <span>×</span> ${escapeHtml(policy.multiplier)}</div>
              <div class="ot-policy-card__meta"><span>Base <strong>${escapeHtml(policy.baseComponent)}</strong></span><span>Divisor <strong>${escapeHtml(policy.divisor)}</strong></span><span>Multiplier <strong>${escapeHtml(policy.multiplier)}</strong></span></div>
              <div class="ot-policy-card__foot"><span>${escapeHtml(policy.archivedReason || policy.notes || 'Managed overtime policy')}</span><div class="payment-head-actions">${lifecycleActionsMenu([
                ...(!policy.archived ? [{label:'Edit overtime policy',hint:'Update future overtime calculation setup',iconName:'edit',attrs:`data-overtime-policy-edit="${policy.id}"`}] : []),
                'separator',
                {label:policy.archived?'Restore policy':'Archive policy',hint:policy.archived?'Restore as Inactive':'Preserve salary history and remove from new structures',iconName:'info',attrs:`data-config-lifecycle="overtime|${policy.id}|${policy.archived?'restore':'archive'}"`},
                {label:'Delete unused policy',hint:'Only before salary structures reference this policy',iconName:'more',danger:true,attrs:`data-config-lifecycle="overtime|${policy.id}|delete"`}
              ],{compact:true})}</div></div>
            </article>`).join('') : `<div class="table-empty table-empty--card"><strong>No overtime policies in this view.</strong><span>Change the status filter or create a policy before assigning overtime calculation to employee salary structures.</span></div>`}
          </div>
        </section>

        <aside class="profile-side-stack salary-preview-stack">
          <section class="panel panel--flush ot-preview-card">
            <div class="panel__head panel__head--padded"><div><h2>Calculation preview</h2><p>Test the active formula before payroll.</p></div></div>
            <div class="ot-preview-form">
              <label><span>Base amount</span><div class="money-input"><em>${escapeHtml(currencyCode())}</em><input id="otPreviewBasic" type="number" value="" placeholder="0.00" min="0" step="0.01"></div></label>
              <label><span>OT hours</span><input class="input" id="otPreviewHours" type="number" value="" placeholder="0" min="0" step="0.5"></label>
            </div>
            <div class="ot-preview-result"><span>Calculated overtime</span><strong id="otPreviewResult">—</strong><small id="otPreviewFormula">${escapeHtml(formula)}</small></div>
          </section>
          <section class="source-note">${icon('info')}<span><strong>Historical formula integrity</strong>When a policy is assigned to an employee salary structure, its formula is snapshotted so later policy changes affect future assignments only.</span></section>
        </aside>
      </div>`;
  }

  function periodInfo(period = state.period) {
    const parts = String(period || '').trim().split(/\s+/);
    const months = ['January','February','March','April','May','June','July','August','September','October','November','December'];
    const monthIndex = months.indexOf(parts[0]);
    const year = Number(parts[1]);
    if (monthIndex < 0 || !Number.isInteger(year) || year < 2000 || year > 2200) {
      const [fallbackYear, fallbackMonth] = String(state.systemSettings.general.today || companyTodayIso).split('-').map(Number);
      const month = Math.max(1, Math.min(12, Number(fallbackMonth) || 1));
      const fallbackDays = new Date(Number(fallbackYear), month, 0).getDate();
      return { monthName: months[month - 1], monthIndex: month - 1, year: Number(fallbackYear), days: fallbackDays };
    }
    const days = new Date(year, monthIndex + 1, 0).getDate();
    return { monthName: months[monthIndex], monthIndex, year, days };
  }

  function periodKeyFromLabel(period = state.period) {
    const info = periodInfo(period);
    return `${info.year}-${String(info.monthIndex + 1).padStart(2, '0')}`;
  }

  function attendanceDateForDay(day, period = state.period) {
    const info = periodInfo(period);
    return `${info.year}-${String(info.monthIndex + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
  }

  function isWeekendDay(day, period = state.period) {
    const info = periodInfo(period);
    const weekday = new Date(info.year, info.monthIndex, day).getDay();
    return weekday === 5 || weekday === 6;
  }

  function weekdayShort(day, period = state.period) {
    const info = periodInfo(period);
    return new Intl.DateTimeFormat('en', { weekday: 'short' }).format(new Date(info.year, info.monthIndex, day)).slice(0, 2);
  }


  function attendanceDayClasses(day, period = state.period) {
    const info = periodInfo(period);
    const date = new Date(info.year, info.monthIndex, day);
    const dateIso = attendanceDateForDay(day, period);
    const todayIso = state.systemSettings?.general?.today || companyTodayIso;
    return [isWeekendDay(day, period) ? 'is-weekend' : '', date.getDay() === 6 ? 'is-week-boundary' : '', dateIso === todayIso ? 'is-today' : ''].filter(Boolean).join(' ');
  }

  function applyAttendancePayload(payload, period = state.period) {
    const label = payload.period?.label || period;
    state.timesheets[label] = payload.records || {};
    state.timesheetStatuses[label] = payload.period?.status || 'Draft';
    state.attendancePeriodMeta[label] = payload.period || {};
    state.attendanceRoster[label] = payload.roster || [];
    state.attendanceOvertimeMeta[label] = payload.overtime || {};
    state.attendanceSummary[label] = payload.summary || {};
    state.overtimeEntries[label] = Object.fromEntries(Object.entries(payload.overtime || {}).map(([employeeId,row]) => [employeeId, Number(row.hours || 0)]));
    state.attendanceLoadedPeriods.add(label);
  }

  async function loadInternalAttendancePeriod(period = state.period, { force = false } = {}) {
    if (!force && state.attendanceLoadedPeriods.has(period)) return;
    if (state.attendanceLoadingPeriod === period) return;
    state.attendanceLoadingPeriod = period;
    try {
      const payload = await appApi(`/api/internal/attendance/?period=${encodeURIComponent(periodKeyFromLabel(period))}`);
      applyAttendancePayload(payload, period);
    } catch (error) {
      showToast('Attendance not loaded', error.message);
    } finally {
      if (state.attendanceLoadingPeriod === period) state.attendanceLoadingPeriod = null;
      if (currentRoute() === 'timesheets' && state.timesheetWorkspace === 'internal' && state.period === period) renderRoute();
    }
  }

  async function saveAttendanceApiEntries(entries, period = state.period) {
    if (!entries.length) return null;
    const payload = await appApi(`/api/internal/attendance/?period=${encodeURIComponent(periodKeyFromLabel(period))}`, {
      method: 'PATCH',
      body: { entries }
    });
    applyAttendancePayload(payload, period);
    return payload;
  }

  async function saveAttendanceOvertimeApi(employeeId, hours, period = state.period) {
    const payload = await appApi('/api/internal/attendance/overtime/', {
      method: 'PATCH',
      body: { period: periodKeyFromLabel(period), entries: [{ employee_id: employeeId, hours }] }
    });
    applyAttendancePayload(payload, period);
    return payload;
  }

  async function runAttendanceWorkflow(action, { reason = '', period = state.period } = {}) {
    const payload = await appApi('/api/internal/attendance/workflow/', {
      method: 'POST',
      body: { period: periodKeyFromLabel(period), action, reason }
    });
    applyAttendancePayload(payload, period);
    return payload;
  }

  function parseAttendanceImportText(text, period = state.period) {
    const rawLines = String(text || '').split(/\r?\n/).map(line => line.trim()).filter(Boolean);
    if (rawLines.length < 2) throw new Error('Paste a header row and at least one employee row.');
    const delimiter = rawLines[0].includes('\t') ? '\t' : ',';
    const parseLine = line => line.split(delimiter).map(value => value.trim());
    const headers = parseLine(rawLines[0]);
    if (!headers.length || !/employee/i.test(headers[0])) throw new Error('The first column header must be Employee ID or Employee Number.');
    const info = periodInfo(period);
    const dayColumns = headers.slice(1).map((value, index) => {
      const day = Number(String(value).replace(/[^0-9]/g, ''));
      if (!Number.isInteger(day) || day < 1 || day > info.days) throw new Error(`Invalid day column: ${value || index + 2}.`);
      return day;
    });
    if (new Set(dayColumns).size !== dayColumns.length) throw new Error('Day columns must be unique.');
    return rawLines.slice(1).map((line, rowIndex) => {
      const cells = parseLine(line);
      const employeeNumber = cells[0] || '';
      if (!employeeNumber) throw new Error(`Row ${rowIndex + 2} is missing an employee number.`);
      const days = {};
      dayColumns.forEach((day, index) => {
        if (index + 1 < cells.length && cells[index + 1] !== '') days[String(day)] = cells[index + 1];
      });
      return { employee_number: employeeNumber, days };
    });
  }

  function ensureTimesheetPeriod(period = state.period) {
    if (!state.timesheets[period] || typeof state.timesheets[period] !== 'object') state.timesheets[period] = {};
    if (!state.overtimeEntries[period] || typeof state.overtimeEntries[period] !== 'object') state.overtimeEntries[period] = {};
    if (!state.timesheetStatuses[period]) state.timesheetStatuses[period] = 'Draft';
    return state.timesheets[period];
  }

  function attendanceMeta(period = state.period) {
    return state.attendancePeriodMeta[period] || { status:'Draft', canEdit:roleCanEdit('internal'), canApprove:roleCanApprove(), nextAction:roleCanEdit('internal') ? 'submit' : null };
  }

  function attendanceRosterForPeriod(period = state.period) {
    return state.attendanceRoster[period] || [];
  }

  function normalizeAttendanceValue(value) {
    const raw = String(value ?? '').trim().toUpperCase();
    if (!raw) return '';
    const aliases = { P: '8', PRESENT: '8', ABSENT: 'A', LEAVE: 'L', SICK: 'S', HOLIDAY: 'H', OFFDAY: 'OFF', 'OFF DAY': 'OFF' };
    if (aliases[raw]) return aliases[raw];
    if (['A','L','S','H','OFF'].includes(raw)) return raw;
    const n = Number(raw);
    if (Number.isFinite(n) && n >= 0 && n <= 24) return String(Math.round(n * 100) / 100);
    return null;
  }

  function attendanceHours(value) {
    const n = Number(value);
    return Number.isFinite(n) && n >= 0 ? n : 0;
  }

  function attendanceTone(value) {
    const normalized = String(value || '').toUpperCase();
    if (normalized === 'A') return 'absent';
    if (normalized === 'L') return 'leave';
    if (normalized === 'S') return 'sick';
    if (normalized === 'H') return 'holiday';
    if (normalized === 'OFF') return 'off';
    if (attendanceHours(normalized) > 0) return 'worked';
    return 'empty';
  }

  function employeeEmployedOnDay(employee, day, period = state.period) {
    const dateKey = attendanceDateForDay(day, period);
    return (!employee.joining || dateKey >= employee.joining) && (!employee.employmentEnd || dateKey <= employee.employmentEnd);
  }

  function summarizeAttendanceRecord(record = {}, period = state.period, employee = null) {
    const info = periodInfo(period);
    let regularHours = 0;
    let present = 0;
    let absent = 0;
    let leave = 0;
    let sick = 0;
    let holiday = 0;
    let off = 0;
    let missing = 0;
    for (let day = 1; day <= info.days; day += 1) {
      if (employee && !employeeEmployedOnDay(employee, day, period)) continue;
      const value = record[day] ?? record[String(day)] ?? '';
      const hours = attendanceHours(value);
      regularHours += hours;
      if (hours > 0) present += 1;
      else if (value === 'A') absent += 1;
      else if (value === 'L') leave += 1;
      else if (value === 'S') sick += 1;
      else if (value === 'H') holiday += 1;
      else if (value === 'OFF') off += 1;
      else missing += 1;
    }
    return { regularHours, present, absent, leave, sick, holiday, off, missing };
  }

  function timesheetStatus(period = state.period) {
    return attendanceMeta(period).status || state.timesheetStatuses[period] || 'Draft';
  }

  function timesheetCanEdit(period = state.period) {
    const meta = attendanceMeta(period);
    return meta.status === 'Draft' && meta.canEdit === true;
  }

  function timesheetStatusBadge(status) {
    const tone = status === 'Locked' || status === 'Approved' ? 'success' : status === 'Submitted' ? 'warning' : 'neutral';
    return `<span class="timesheet-status timesheet-status--${tone}"><span></span>${escapeHtml(status)}</span>`;
  }


  function v2TimesheetStatusBadge(status) {
    const tone = status === 'Locked' || status === 'Approved' ? 'success' : status === 'Submitted' ? 'warning' : 'neutral';
    return `<span class="ui-v2-status ui-v2-status--${tone}">${escapeHtml(status)}</span>`;
  }

  function timesheetNextAction(status = timesheetStatus()) {
    const action = attendanceMeta().nextAction;
    if (action === 'submit') return { label: 'Submit for Review', next: 'Submitted', action:'submit' };
    if (action === 'approve') return { label: 'Approve Timesheet', next: 'Approved', action:'approve' };
    if (action === 'lock') return { label: 'Lock Period', next: 'Locked', action:'lock' };
    if (status === 'Submitted') return { label: 'Awaiting Approval', next: null, action:null };
    if (status === 'Approved') return { label: 'Approved', next: null, action:null };
    if (status === 'Locked') return { label: 'Period Locked', next: null, action:null };
    return { label: 'Read only', next: null, action:null };
  }

  function filteredTimesheetEmployees() {
    const q = state.timesheetSearch.trim().toLowerCase();
    return attendanceRosterForPeriod().filter(employee => {
      const branchMatch = state.timesheetBranch === 'All branches' || employee.branch === state.timesheetBranch;
      const departmentMatch = state.timesheetDepartment === 'All departments' || employee.department === state.timesheetDepartment;
      const text = `${employee.employeeId} ${employee.name} ${employee.position} ${employee.department} ${employee.branch}`.toLowerCase();
      return branchMatch && departmentMatch && (!q || text.includes(q));
    });
  }

  function overtimeHoursFor(item, period = state.period) {
    const employeeId = typeof item === 'string' ? item : item?.id;
    return Number(state.overtimeEntries[period]?.[employeeId] || 0);
  }

  function overtimeAmountFor(item, period = state.period) {
    const employeeId = typeof item === 'string' ? item : item?.id;
    const meta = state.attendanceOvertimeMeta[period]?.[employeeId] || {};
    if (meta.saved) return Number(meta.amount || 0);
    return Number(meta.rate || 0) * overtimeHoursFor(employeeId, period);
  }

  function timesheetWorkflow() {
    const status = timesheetStatus();
    const steps = ['Draft','Submitted','Approved','Locked'];
    const currentIndex = Math.max(0, steps.indexOf(status));
    return `<div class="ui-v2-payroll-workflow-steps" aria-label="Timesheet approval status">${steps.map((step,index) => `<div class="${index < currentIndex ? 'is-done' : ''} ${index === currentIndex ? 'is-current' : ''}"><span>${index < currentIndex ? '✓' : index + 1}</span><strong>${step}</strong></div>`).join('')}</div>`;
  }

  function internalTimesheetPageData() {
    const all = filteredTimesheetEmployees();
    const allowedSizes = [25, 50, 100];
    if (!allowedSizes.includes(Number(state.timesheetPageSize))) state.timesheetPageSize = 50;
    const pageSize = Number(state.timesheetPageSize);
    const totalPages = Math.max(1, Math.ceil(all.length / pageSize));
    state.timesheetPage = Math.min(Math.max(1, Number(state.timesheetPage) || 1), totalPages);
    const startIndex = (state.timesheetPage - 1) * pageSize;
    const rows = all.slice(startIndex, startIndex + pageSize);
    return {
      all,
      rows,
      pageSize,
      totalPages,
      page: state.timesheetPage,
      rangeStart: all.length ? startIndex + 1 : 0,
      rangeEnd: Math.min(startIndex + pageSize, all.length)
    };
  }

  function attendanceStatusDescription(status = timesheetStatus()) {
    if (status === 'Draft') return 'Attendance remains editable until it is submitted for review.';
    if (status === 'Submitted') return 'Operational editing is frozen while an authorized reviewer checks the period.';
    if (status === 'Approved') return 'The reviewed attendance snapshot is approved and ready to lock for payroll.';
    if (status === 'Locked') return 'The attendance period is immutable and ready as a controlled payroll input.';
    return 'This attendance period is under controlled payroll review.';
  }

  function exportInternalAttendanceCsv() {
    const roster = filteredTimesheetEmployees();
    const info = periodInfo();
    const records = ensureTimesheetPeriod();
    const header = ['Employee ID','Employee','Department','Branch', ...Array.from({length:info.days},(_,i)=>String(i+1)), 'Hours','Days','Exceptions'];
    const quote = value => `"${String(value ?? '').replace(/"/g, '""')}"`;
    const rows = roster.map(employee => {
      const record = records[employee.id] || {};
      const summary = summarizeAttendanceRecord(record, state.period, employee);
      return [employee.employeeId, employee.name, employee.department || '', employee.branch || '', ...Array.from({length:info.days},(_,i)=>record[i+1] ?? record[String(i+1)] ?? ''), summary.regularHours, summary.present, summary.absent + summary.leave + summary.sick];
    });
    const csv = [header, ...rows].map(row => row.map(quote).join(',')).join('\r\n');
    const blob = new Blob([`\uFEFF${csv}`], {type:'text/csv;charset=utf-8'});
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `internal-attendance-${state.period.replace(/\s+/g,'-').toLowerCase()}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    showToast('Attendance exported', `${roster.length} employee row${roster.length === 1 ? '' : 's'} exported for ${state.period}.`);
  }

  function timesheetAttendanceGrid(employees) {
    const records = ensureTimesheetPeriod();
    const info = periodInfo();
    const editable = timesheetCanEdit();
    const days = Array.from({ length: info.days }, (_, i) => i + 1);
    return `
      <div class="ui-v2-payroll-timesheet-scroll" tabindex="0" role="region" aria-label="${escapeHtml(state.period)} internal attendance grid">
        <table class="ui-v2-payroll-timesheet-grid" aria-label="Internal employee monthly attendance grid">
          <caption class="ui-v2-sr-only">${escapeHtml(state.period)} internal employee attendance by day</caption>
          <thead><tr>
            <th class="is-select" aria-label="Employee selection"></th>
            <th class="is-employee">Employee</th>
            ${days.map(day => `<th class="${attendanceDayClasses(day)}" title="${escapeHtml(attendanceDateForDay(day))}"><span>${weekdayShort(day)}</span><strong>${day}</strong></th>`).join('')}
            <th class="is-total is-hours">Hours</th><th class="is-total is-days">Days</th><th class="is-total is-exceptions">Exceptions</th>
          </tr></thead>
          <tbody>${employees.map(employee => {
            const record = records[employee.id] || {};
            const summary = summarizeAttendanceRecord(record, state.period, employee);
            const exceptions = summary.absent + summary.leave + summary.sick + summary.missing;
            return `<tr>
              <td class="is-select"><input type="checkbox" data-timesheet-select="${employee.id}" ${state.timesheetSelected.has(employee.id) ? 'checked' : ''} ${editable ? '' : 'disabled'} aria-label="Select ${escapeHtml(employee.name)}"></td>
              <td class="is-employee"><button type="button" data-open-employee="${employee.id}"><strong>${escapeHtml(employee.name)}</strong><span>EMP ${escapeHtml(employee.employeeId)} · ${escapeHtml(employee.department || employee.position || 'Department not set')} · ${escapeHtml(employee.branch || 'Branch not set')}</span></button></td>
              ${days.map(day => {
                const employed = employeeEmployedOnDay(employee, day);
                const value = record[day] ?? record[String(day)] ?? '';
                const tone = attendanceTone(value);
                const numericHours = Number(value);
                const overtime = Number.isFinite(numericHours) && numericHours > 8;
                const dayClasses = [attendanceDayClasses(day), !employed ? 'is-disabled-day' : '', overtime ? 'has-overtime' : ''].filter(Boolean).join(' ');
                if (!employed) return `<td class="${dayClasses}"><span class="ui-v2-payroll-timesheet-not-assigned" aria-label="Not employed on day ${day}">—</span></td>`;
                return `<td class="${dayClasses}"><input class="ui-v2-payroll-ts-input is-${tone}${overtime ? ' is-overtime' : ''}${String(value).length > 1 ? ' is-multi-digit' : ''}" data-attendance-input="${employee.id}" data-day="${day}" value="${escapeHtml(value)}" ${editable ? '' : 'disabled'} aria-label="${escapeHtml(employee.name)}, day ${day}" maxlength="4" autocomplete="off"></td>`;
              }).join('')}
              <td class="is-total is-hours"><strong>${summary.regularHours.toLocaleString()}</strong></td>
              <td class="is-total is-days ${summary.missing ? 'has-missing' : ''}"><strong>${summary.present}</strong></td>
              <td class="is-total is-exceptions ${exceptions ? 'has-exceptions' : ''}"><strong>${exceptions}</strong></td>
            </tr>`;
          }).join('')}</tbody>
        </table>
      </div>`;
  }

  function timesheetMobileList(employees) {
    const records = ensureTimesheetPeriod();
    const info = periodInfo();
    const maxWeek = Math.ceil(info.days / 7);
    state.timesheetMobileWeek = Math.min(Math.max(1, state.timesheetMobileWeek), maxWeek);
    const start = (state.timesheetMobileWeek - 1) * 7 + 1;
    const end = Math.min(info.days, start + 6);
    const days = Array.from({ length: end - start + 1 }, (_, i) => start + i);
    const editable = timesheetCanEdit();
    return `<div class="timesheet-mobile"><div class="timesheet-mobile__weekbar"><button class="btn btn--ghost btn--sm" data-mobile-week="${state.timesheetMobileWeek - 1}" ${state.timesheetMobileWeek <= 1 ? 'disabled' : ''}>← Previous</button><strong>Week ${state.timesheetMobileWeek} · ${start}–${end} ${escapeHtml(info.monthName)}</strong><button class="btn btn--ghost btn--sm" data-mobile-week="${state.timesheetMobileWeek + 1}" ${state.timesheetMobileWeek >= maxWeek ? 'disabled' : ''}>Next →</button></div>${employees.map(employee => {
      const record = records[employee.id] || {};
      const summary = summarizeAttendanceRecord(record, state.period, employee);
      return `<article class="timesheet-mobile-card"><div class="timesheet-mobile-card__head"><button class="entity-link entity-link--stack" data-open-employee="${employee.id}"><strong>${escapeHtml(employee.name)}</strong><span>${escapeHtml(employee.position || '—')} · ${escapeHtml(employee.branch || 'Branch not set')}</span></button><strong>${summary.regularHours}h</strong></div><div class="timesheet-mobile-days">${days.map(day => {
        const employed = employeeEmployedOnDay(employee, day);
        const value = record[day] ?? record[String(day)] ?? '';
        return `<label class="timesheet-mobile-day ${isWeekendDay(day) ? 'is-weekend' : ''} ${employed ? '' : 'is-disabled'}"><span>${weekdayShort(day)} ${day}</span><input class="ts-cell-input ts-cell-input--${attendanceTone(value)}" data-attendance-input="${employee.id}" data-day="${day}" value="${employed ? escapeHtml(value) : '—'}" ${editable && employed ? '' : 'disabled'} maxlength="4"></label>`;
      }).join('')}</div></article>`;
    }).join('')}</div>`;
  }

  function internalAttendanceTemplate() {
    const page = internalTimesheetPageData();
    const employees = page.rows;
    const filteredEmployees = page.all;
    const records = ensureTimesheetPeriod();
    const totals = filteredEmployees.reduce((acc, employee) => {
      const rowSummary = summarizeAttendanceRecord(records[employee.id] || {}, state.period, employee);
      acc.hours += rowSummary.regularHours;
      acc.absent += rowSummary.absent;
      acc.leave += rowSummary.leave + rowSummary.sick;
      acc.missing += rowSummary.missing;
      return acc;
    }, { hours:0, absent:0, leave:0, missing:0 });
    const roster = attendanceRosterForPeriod();
    const branchOptions = ['All branches', ...new Set(roster.map(employee => employee.branch).filter(Boolean))];
    const departments = ['All departments', ...new Set(roster.map(employee => employee.department).filter(Boolean))];
    const status = timesheetStatus();
    const next = timesheetNextAction(status);
    const selectedCount = state.timesheetSelected.size;
    const info = periodInfo();
    const missingCount = Number(totals.missing || 0);
    const editable = timesheetCanEdit();
    const allPageSelected = employees.length > 0 && employees.every(employee => state.timesheetSelected.has(employee.id));
    const somePageSelected = employees.some(employee => state.timesheetSelected.has(employee.id)) && !allPageSelected;
    return `
      <div class="ui-v2-payroll-summary-strip">
        <div class="ui-v2-payroll-metric"><span>Employee roster</span><strong>${roster.length}</strong><small>${filteredEmployees.length} in current filter · assigned scope</small></div>
        <div class="ui-v2-payroll-metric"><span>Regular hours</span><strong>${totals.hours.toLocaleString()}</strong><small>${escapeHtml(state.period)} saved attendance</small></div>
        <div class="ui-v2-payroll-metric"><span>Exceptions</span><strong>${(totals.absent + totals.leave + missingCount).toLocaleString()}</strong><small>${missingCount.toLocaleString()} missing · ${totals.absent} absent · ${totals.leave} leave/sick</small></div>
        <div class="ui-v2-payroll-metric"><span>Approval state</span><strong>${escapeHtml(status)}</strong><small>Revision ${Number(attendanceMeta().revision || 0)} · ${editable ? 'operational input open' : 'controlled review state'}</small></div>
      </div>
      <section class="ui-v2-payroll-panel ui-v2-payroll-timesheet-lifecycle"><header><div><span>Period control</span><h2>Monthly attendance lifecycle</h2></div>${v2TimesheetStatusBadge(status)}</header>${timesheetWorkflow()}</section>
      <section class="ui-v2-payroll-attendance-control-strip">
        <div class="ui-v2-payroll-attendance-control-strip__state"><span class="ui-v2-payroll-attendance-control-icon is-${escapeHtml(status.toLowerCase().replace(/\s+/g,'-'))}">${status === 'Approved' || status === 'Locked' ? '✓' : icon('timesheet')}</span><div><strong>${escapeHtml(status)}</strong><span>${escapeHtml(attendanceStatusDescription(status))}</span></div></div>
        <div class="ui-v2-payroll-attendance-control-strip__actions">${missingCount ? `<span class="ui-v2-payroll-attendance-exception-link">${missingCount.toLocaleString()} missing entr${missingCount === 1 ? 'y' : 'ies'}</span>` : '<span class="ui-v2-payroll-attendance-clear">✓ No missing entries</span>'}${attendanceMeta().canApprove && ['Submitted','Approved'].includes(status) ? '<button class="ui-v2-button ui-v2-button--secondary ui-v2-button--sm" data-timesheet-return>Return to Draft</button>' : ''}<button class="ui-v2-button ui-v2-button--primary ui-v2-button--sm" data-timesheet-workflow ${next.next ? '' : 'disabled'}>${escapeHtml(next.label)}</button></div>
      </section>
      <section class="ui-v2-payroll-panel ui-v2-payroll-register ui-v2-payroll-timesheet-workspace ${state.timesheetFullscreen ? 'is-fullscreen' : ''}" aria-label="Internal company attendance workspace">
        <div class="ui-v2-payroll-register__toolbar ui-v2-payroll-timesheet-toolbar">
          <div class="ui-v2-filter-bar__search">${icon('search')}<input id="timesheetSearch" class="ui-v2-input" type="search" placeholder="Search employee, ID, position or branch" value="${escapeHtml(state.timesheetSearch)}" autocomplete="off" aria-label="Search internal attendance employees"></div>
          <select id="timesheetBranchFilter" class="ui-v2-select ui-v2-payroll-operational-select" aria-label="Branch / Office">${branchOptions.map(option => `<option ${state.timesheetBranch === option ? 'selected' : ''}>${escapeHtml(option)}</option>`).join('')}</select>
          <select id="timesheetDepartmentFilter" class="ui-v2-select ui-v2-payroll-operational-select" aria-label="Department">${departments.map(option => `<option ${state.timesheetDepartment === option ? 'selected' : ''}>${escapeHtml(option)}</option>`).join('')}</select>
          <button class="ui-v2-button ui-v2-button--secondary ui-v2-button--sm" data-timesheet-filter-reset>${icon('filter')}<span>Reset</span></button>
          <div class="ui-v2-payroll-timesheet-file-actions">${editable ? '<button class="ui-v2-button ui-v2-button--secondary ui-v2-button--sm" data-timesheet-import>Import</button>' : ''}<button class="ui-v2-button ui-v2-button--secondary ui-v2-button--sm" data-timesheet-export>Export</button></div>
          <button class="ui-v2-button ui-v2-button--secondary ui-v2-button--sm ui-v2-payroll-timesheet-fullscreen" data-timesheet-fullscreen aria-pressed="${state.timesheetFullscreen ? 'true' : 'false'}"><span>${icon(state.timesheetFullscreen ? 'collapse' : 'expand')}</span>${state.timesheetFullscreen ? 'Exit Full Screen' : 'Full Screen'}</button>
        </div>
        <div class="ui-v2-payroll-timesheet-subtoolbar"><div class="ui-v2-payroll-timesheet-legend"><span><i class="is-worked"></i>Hours</span><span><i class="is-absent"></i>A · Absent</span><span><i class="is-leave"></i>L · Leave</span><span><i class="is-sick"></i>S · Sick</span><span><i class="is-holiday"></i>H · Holiday</span><span><i class="is-off"></i>OFF</span><span><i class="is-weekend"></i>Weekend</span></div><span>A / L / S / H / OFF are valid explicit statuses; only blank required days block submission. Enter 0–24 hours for worked days.</span></div>
        <div class="ui-v2-payroll-timesheet-bulkbar ${selectedCount ? 'is-active' : 'is-idle'}">
          <div class="ui-v2-payroll-timesheet-master-select"><input type="checkbox" data-timesheet-select-all aria-label="${allPageSelected ? 'Unselect' : 'Select'} this page of employees" ${allPageSelected ? 'checked' : ''} ${editable ? '' : 'disabled'} data-indeterminate="${somePageSelected ? 'true' : 'false'}"></div>
          <div class="ui-v2-payroll-timesheet-selection-summary"><strong>${selectedCount ? `${selectedCount.toLocaleString()} selected` : `${employees.length} employees`}</strong><div class="ui-v2-payroll-timesheet-selection-meta"><small>${selectedCount ? `${employees.filter(employee=>state.timesheetSelected.has(employee.id)).length} on this page · ${selectedCount.toLocaleString()} selected` : `${page.rangeStart}–${page.rangeEnd} of ${filteredEmployees.length.toLocaleString()} matching`}</small>${selectedCount ? '<div class="ui-v2-payroll-timesheet-selection-actions"><button type="button" data-timesheet-clear-selection>Clear</button></div>' : ''}</div></div>
          <div class="ui-v2-payroll-timesheet-command-strip"><label class="ui-v2-prs-timesheet-day-select"><span>Day</span><select id="timesheetBulkDay" class="ui-v2-select ui-v2-payroll-dense-select" ${selectedCount && editable ? '' : 'disabled'}>${Array.from({length:info.days},(_,i)=>i+1).map(day => `<option value="${day}" ${Number(state.timesheetBulkDay) === day ? 'selected' : ''}>${day} · ${weekdayShort(day)}${isCompanyToday(day,state.period) ? ' · Today' : ''}</option>`).join('')}</select></label><button class="ui-v2-button ui-v2-button--secondary ui-v2-button--sm" data-timesheet-bulk-action="8" ${selectedCount && editable ? '' : 'disabled'}>Fill 8h</button><button class="ui-v2-button ui-v2-button--secondary ui-v2-button--sm" data-timesheet-bulk-action="A" ${selectedCount && editable ? '' : 'disabled'}>Absent</button><button class="ui-v2-button ui-v2-button--secondary ui-v2-button--sm" data-timesheet-bulk-action="L" ${selectedCount && editable ? '' : 'disabled'}>Leave</button><button class="ui-v2-button ui-v2-button--secondary ui-v2-button--sm" data-timesheet-bulk-action="OFF" ${selectedCount && editable ? '' : 'disabled'}>Off</button><button class="ui-v2-button ui-v2-button--secondary ui-v2-button--sm" data-timesheet-bulk-action="copy" ${selectedCount && editable && Number(state.timesheetBulkDay) > 1 ? '' : 'disabled'}>Copy previous</button><button class="ui-v2-button ui-v2-button--secondary ui-v2-button--sm" data-timesheet-bulk-action="workdays" ${selectedCount && editable ? '' : 'disabled'}>Fill workdays</button><button class="ui-v2-button ui-v2-button--quiet ui-v2-button--sm" data-timesheet-bulk-action="clear" ${selectedCount && editable ? '' : 'disabled'}>Clear day</button></div>
        </div>
        ${employees.length ? timesheetAttendanceGrid(employees) : `<div class="ui-v2-payroll-table-empty"><strong>No employees match this attendance view.</strong><span>Change the search, branch or department filters.</span></div>`}
        <div class="ui-v2-payroll-timesheet-footer"><span class="ui-v2-payroll-timesheet-footer-status"><strong>${page.rangeStart}–${page.rangeEnd}</strong> of <strong>${filteredEmployees.length.toLocaleString()}</strong> employees <i></i> <strong>${(totals.absent + totals.leave + missingCount).toLocaleString()}</strong> controlled exceptions <i></i> <strong>${escapeHtml(status)}</strong>${editable ? ' · editable' : ' · read-only'}</span>${page.totalPages > 1 ? `<div class="ui-v2-payroll-timesheet-pagination"><div class="ui-v2-payroll-timesheet-pagination__pages"><button type="button" data-timesheet-page="${page.page - 1}" ${page.page <= 1 ? 'disabled' : ''} aria-label="Previous page">‹</button><span>Page <strong>${page.page}</strong> / ${page.totalPages}</span><button type="button" data-timesheet-page="${page.page + 1}" ${page.page >= page.totalPages ? 'disabled' : ''} aria-label="Next page">›</button></div><label class="ui-v2-payroll-timesheet-pagination__size">Rows <select id="timesheetPageSize" class="ui-v2-select ui-v2-payroll-dense-select"><option value="25" ${page.pageSize===25?'selected':''}>25</option><option value="50" ${page.pageSize===50?'selected':''}>50</option><option value="100" ${page.pageSize===100?'selected':''}>100</option></select></label></div>` : ''}<div class="ui-v2-payroll-timesheet-footer-actions">${editable ? '<button class="ui-v2-button ui-v2-button--secondary ui-v2-button--sm" data-timesheet-save>Save draft</button>' : ''}</div></div>
      </section>`;
  }

  function internalOvertimeTemplate() {
    const roster = attendanceRosterForPeriod();
    const overtimeMeta = state.attendanceOvertimeMeta[state.period] || {};
    const configured = roster.filter(employee => overtimeMeta[employee.id]?.configured);
    const totalOtHours = roster.reduce((sum, employee) => sum + overtimeHoursFor(employee), 0);
    const totalAmount = roster.reduce((sum, employee) => sum + overtimeAmountFor(employee), 0);
    const policyNames = [...new Set(configured.map(employee => overtimeMeta[employee.id]?.policyName).filter(Boolean))];
    const editable = timesheetCanEdit();
    return `
      <div class="timesheet-summary summary-strip summary-strip--4">
        <div class="summary-item"><span>Employees in period</span><strong>${roster.length}</strong><small>${configured.length} OT-ready salary structures</small></div>
        <div class="summary-item"><span>OT configured</span><strong>${configured.length}</strong><small>${roster.length - configured.length} require salary/OT setup</small></div>
        <div class="summary-item"><span>OT hours</span><strong>${totalOtHours.toLocaleString()}</strong><small>Saved monthly overtime</small></div>
        <div class="summary-item"><span>Calculated OT</span><strong>${formatCurrency(totalAmount)}</strong><small>Salary-structure snapshot calculation</small></div>
      </div>
      <div class="overtime-workspace-layout">
        <section class="data-panel overtime-register"><div class="section-headline"><div><h2>${escapeHtml(state.period)} overtime register</h2><p>OT is calculated from each employee's salary structure and snapshotted policy effective at the period end.</p></div><button class="btn btn--secondary btn--sm" data-route-link="salary-setup">Manage Salary & OT Policy</button></div><div class="table-scroll"><table class="data-table overtime-table"><thead><tr><th>Employee</th><th>Base Amount</th><th>Divisor</th><th>OT Hours</th><th>Multiplier</th><th>OT Amount</th><th>Readiness</th></tr></thead><tbody>
          ${roster.map(employee => {
            const meta = overtimeMeta[employee.id] || { configured:false, reason:'Salary/OT setup unavailable.' };
            const hours = overtimeHoursFor(employee);
            const amount = overtimeAmountFor(employee);
            return `<tr><td><button class="entity-link entity-link--stack" data-open-employee="${employee.id}"><strong>${escapeHtml(employee.name)}</strong><span>EMP ${escapeHtml(employee.employeeId)} · ${escapeHtml(employee.position || '—')}</span></button></td><td><strong>${meta.configured ? formatCurrency(Number(meta.baseAmount || 0)) : '—'}</strong><div class="table-secondary">${escapeHtml(meta.baseComponent || '')}</div></td><td>${meta.configured ? Number(meta.divisor || 0).toLocaleString() : '—'}</td><td><input class="input ot-inline-input" type="number" min="0" max="744" step="0.5" value="${hours}" data-ot-hours="${employee.id}" ${editable && meta.configured ? '' : 'disabled'} aria-label="Overtime hours for ${escapeHtml(employee.name)}"></td><td>${meta.configured ? `× ${Number(meta.multiplier || 0).toLocaleString('en-SA',{maximumFractionDigits:4})}` : '—'}</td><td><strong>${meta.configured ? formatCurrency(amount) : '—'}</strong></td><td>${meta.configured ? `<span class="readiness readiness--ready"><span></span>${escapeHtml(meta.policyName || 'Configured')}</span>` : `<span class="readiness readiness--warn"><span></span>Needs setup</span><div class="table-secondary">${escapeHtml(meta.reason || '')}</div>`}</td></tr>`;
          }).join('')}
        </tbody><tfoot><tr><td><strong>Total</strong></td><td colspan="2">—</td><td><strong>${totalOtHours.toLocaleString()}</strong></td><td>—</td><td><strong>${formatCurrency(totalAmount)}</strong></td><td></td></tr></tfoot></table></div></section>
        <aside class="data-panel overtime-policy-panel"><div class="panel__head panel__head--padded"><div><h2>Period calculation basis</h2><p>Effective employee salary structures</p></div>${timesheetStatusBadge(timesheetStatus())}</div><div class="overtime-policy-formula"><span>Base component</span><strong>÷ Salary divisor</strong><strong>× OT hours</strong><strong>× Multiplier</strong></div><div class="overtime-policy-foot"><span>Policies represented</span><strong>${escapeHtml(policyNames.length ? policyNames.join(' · ') : 'No configured OT policy')}</strong><button class="text-link" data-route-link="salary-setup">Review Salary Setup →</button></div></aside>
      </div>`;
  }

  /* Rental project timesheets */

  function rentalTimesheetPeriodRange(period = state.period) {
    const info = periodInfo(period);
    const start = `${info.year}-${String(info.monthIndex + 1).padStart(2,'0')}-01`;
    const end = `${info.year}-${String(info.monthIndex + 1).padStart(2,'0')}-${String(info.days).padStart(2,'0')}`;
    return { ...info, start, end };
  }

  function rentalTimesheetDate(day, period = state.period) {
    const info = periodInfo(period);
    return `${info.year}-${String(info.monthIndex + 1).padStart(2,'0')}-${String(day).padStart(2,'0')}`;
  }

  function rentalAssignmentsInProjectPeriod(worker, projectId, period = state.period) {
    const range = rentalTimesheetPeriodRange(period);
    return rentalAssignmentsFor(worker).filter(item => {
      if (item.kind !== 'assignment' || item.projectId !== projectId) return false;
      const start = item.start || range.start;
      const end = item.end || range.end;
      return start <= range.end && end >= range.start;
    });
  }

  function rentalAssignmentForDate(worker, projectId, day, period = state.period) {
    const date = rentalTimesheetDate(day, period);
    const matches = rentalAssignmentsFor(worker).filter(item => {
      if (item.kind !== 'assignment' || item.projectId !== projectId) return false;
      const start = item.start || '0000-01-01';
      const end = item.end || '9999-12-31';
      return start <= date && end >= date;
    });
    return matches[matches.length - 1] || null;
  }

  function rentalWorkersForTimesheet(projectId = state.rentalTimesheetProject, period = state.period) {
    if (!projectId) return [];
    const q = state.rentalTimesheetSearch.trim().toLowerCase();
    return state.rentalWorkers.filter(worker => {
      const assignments = rentalAssignmentsInProjectPeriod(worker, projectId, period);
      if (!assignments.length) return false;
      if (state.rentalTimesheetSupplier !== 'All suppliers' && worker.supplierId !== state.rentalTimesheetSupplier) return false;
      const supplier = rentalWorkerSupplier(worker);
      const text = `${rentalWorkerCode(worker)} ${worker.name} ${worker.trade || ''} ${supplier?.name || ''}`.toLowerCase();
      return !q || text.includes(q);
    });
  }


  function rentalTimesheetRecordKey(period = state.period, projectId = state.rentalTimesheetProject) {
    return `${period}::${projectId}`;
  }

  function rentalTimesheetApiPeriod(period = state.period) {
    return rentalTimesheetPeriodRange(period).start;
  }

  function applyRentalTimesheetPayload(payload) {
    const periodLabel = payload.period?.label || state.period;
    const projectId = payload.period?.projectId || state.rentalTimesheetProject;
    if (!projectId) return;
    state.rentalTimesheets[periodLabel] ||= {};
    state.rentalTimesheets[periodLabel][projectId] = payload.records || {};
    const key = rentalTimesheetRecordKey(periodLabel, projectId);
    state.rentalTimesheetStatuses[key] = payload.period?.status || 'Draft';
    state.rentalTimesheetMeta[key] = payload.period || {};
    state.rentalOvertime[key] = Object.fromEntries(Object.entries(payload.overtime || {}).map(([workerId,row]) => [workerId,{hours:Number(row.hours||0),rate:Number(row.rate||0)}]));
    state.rentalTimesheetLoaded ||= new Set();
    state.rentalTimesheetLoaded.add(key);
  }

  async function loadRentalTimesheet({ render = true } = {}) {
    if (!state.rentalTimesheetProject) return;
    try {
      const payload = await appApi(`/api/rental/timesheets/?project_id=${encodeURIComponent(state.rentalTimesheetProject)}&period=${encodeURIComponent(rentalTimesheetApiPeriod())}`);
      applyRentalTimesheetPayload(payload);
      if (render) renderRoute();
    } catch (error) { showToast('Could not load project timesheet', error.message); }
  }

  async function saveRentalTimesheetEntries(entries, { render = true } = {}) {
    const payload = await appApi('/api/rental/timesheets/', { method:'PATCH', body:{ project_id:state.rentalTimesheetProject, period:rentalTimesheetApiPeriod(), entries } });
    applyRentalTimesheetPayload(payload);
    if (render) renderRoute();
    return payload;
  }

  function persistRentalTimesheets() {}
  function persistRentalTimesheetStatuses() {}
  function persistRentalOvertime() {}

  function ensureRentalTimesheet(period = state.period, projectId = state.rentalTimesheetProject) {
    if (!projectId) return {};
    if (!state.rentalTimesheets[period] || typeof state.rentalTimesheets[period] !== 'object') state.rentalTimesheets[period] = {};
    if (!state.rentalTimesheets[period][projectId] || typeof state.rentalTimesheets[period][projectId] !== 'object') state.rentalTimesheets[period][projectId] = {};
    const bucket = state.rentalTimesheets[period][projectId];
    rentalWorkersForTimesheet(projectId, period).forEach(worker => {
      if (!bucket[worker.id]) bucket[worker.id] = {};
    });
    const key = rentalTimesheetRecordKey(period, projectId);
    if (!state.rentalTimesheetStatuses[key]) state.rentalTimesheetStatuses[key] = 'Draft';
    if (!state.rentalOvertime[key] || typeof state.rentalOvertime[key] !== 'object') state.rentalOvertime[key] = {};
    return bucket;
  }

  function rentalTimesheetStatus(period = state.period, projectId = state.rentalTimesheetProject) {
    ensureRentalTimesheet(period, projectId);
    return state.rentalTimesheetStatuses[rentalTimesheetRecordKey(period, projectId)] || 'Draft';
  }

  function rentalTimesheetNextAction(status) {
    if (status === 'Draft') return { label:'Submit Timesheet', next:'Submitted' };
    if (status === 'Submitted') return { label:'Approve Timesheet', next:'Approved' };
    if (status === 'Approved') return { label:'Lock Timesheet', next:'Locked' };
    return { label:'Timesheet Locked', next:null };
  }

  function rentalTimesheetWorkflow(status = rentalTimesheetStatus()) {
    const steps = ['Draft','Submitted','Approved','Locked'];
    const currentIndex = Math.max(0, steps.indexOf(status));
    return `<div class="ui-v2-payroll-workflow-steps" aria-label="Rental timesheet approval status">${steps.map((step,index) => `<div class="${index < currentIndex ? 'is-done' : ''} ${index === currentIndex ? 'is-current' : ''}"><span>${index < currentIndex ? '✓' : index + 1}</span><strong>${step}</strong></div>`).join('')}</div>`;
  }

  function normalizeRentalTimesheetValue(value) {
    const raw = String(value ?? '').trim().toUpperCase();
    if (!raw) return '';
    const aliases = { ABSENT:'A', SICK:'A', LEAVE:'L', 'NO SCOPE':'N', NOSCOPE:'N', 'NO WORK':'N', OFFDAY:'OFF', 'OFF DAY':'OFF' };
    if (aliases[raw]) return aliases[raw];
    if (['A','N','L','OFF'].includes(raw)) return raw;
    const n = Number(raw);
    if (Number.isFinite(n) && n >= 0 && n <= 24) return String(Math.round(n * 100) / 100);
    return null;
  }

  function rentalTimesheetTone(value) {
    const raw = String(value ?? '').trim().toUpperCase();
    if (raw === 'A') return 'absent';
    if (raw === 'N') return 'noscope';
    if (raw === 'L') return 'leave';
    if (raw === 'OFF') return 'off';
    if (raw === '0') return 'unexcused';
    if (Number(raw) > 0) return 'worked';
    return 'empty';
  }

  function rentalTimesheetHours(value) {
    const n = Number(value);
    return Number.isFinite(n) && n > 0 ? n : 0;
  }

  function rentalTimesheetSummary(worker, period = state.period, projectId = state.rentalTimesheetProject) {
    ensureRentalTimesheet(period, projectId);
    const record = state.rentalTimesheets?.[period]?.[projectId]?.[worker.id] || {};
    const info = periodInfo(period);
    let hours = 0, workDays = 0, absent = 0, noScope = 0, leave = 0, off = 0, missing = 0;
    for (let day = 1; day <= info.days; day += 1) {
      const assignment = rentalAssignmentForDate(worker, projectId, day, period);
      if (!assignment) continue;
      const value = record[day] ?? record[String(day)] ?? '';
      const h = rentalTimesheetHours(value);
      hours += h;
      if (h > 0) workDays += 1;
      else if (String(value) === 'A') absent += 1;
      else if (String(value) === 'N') noScope += 1;
      else if (String(value) === 'L') leave += 1;
      else if (String(value) === 'OFF') off += 1;
      else if (String(value) === '0') absent += 1;
      else missing += 1;
    }
    return { hours, workDays, absent, noScope, leave, off, missing };
  }

  function rentalOvertimeFor(worker, period = state.period, projectId = state.rentalTimesheetProject) {
    ensureRentalTimesheet(period, projectId);
    const key = rentalTimesheetRecordKey(period, projectId);
    const entry = state.rentalOvertime?.[key]?.[worker.id] || {};
    return { hours:Number(entry.hours || 0), rate:Number(entry.rate || 0) };
  }

  function rentalPeriodAssignmentsLabel(worker, projectId = state.rentalTimesheetProject, period = state.period, field = 'trade') {
    const rows = rentalAssignmentsInProjectPeriod(worker, projectId, period);
    const values = [];
    rows.forEach(row => {
      const value = field === 'rate'
        ? rentalRateLabelFromParts(row.rateType, row.rateValue, row.rateLabel)
        : (row.trade || worker.trade || 'Worker');
      if (value && !values.includes(value)) values.push(value);
    });
    return values.length > 1 ? values.join(' → ') : (values[0] || '—');
  }

  function rentalWorkerTimesheetMetrics(worker, period = state.period, projectId = state.rentalTimesheetProject) {
    const summary = rentalTimesheetSummary(worker, period, projectId);
    const overtime = rentalOvertimeFor(worker, period, projectId);
    return { ...summary, otHours:overtime.hours, otRate:overtime.rate };
  }

  function rentalTimesheetProjectTotals(workers) {
    return workers.reduce((totals,worker) => {
      const metrics = rentalWorkerTimesheetMetrics(worker);
      totals.hours += metrics.hours;
      totals.otHours += metrics.otHours;
      totals.workDays += metrics.workDays;
      totals.missing += metrics.missing;
      return totals;
    }, { hours:0, otHours:0, workDays:0, missing:0 });
  }

  function rentalTimesheetDayHeaders(info) {
    return Array.from({length:info.days},(_,index)=>{
      const day = index + 1;
      return `<th class="${attendanceDayClasses(day,state.period)}" title="${escapeHtml(rentalTimesheetDate(day))}"><span>${weekdayShort(day,state.period)}</span><strong>${day}</strong></th>`;
    }).join('');
  }

  function rentalTimesheetCanEdit() {
    return rentalTimesheetStatus() === 'Draft' && !rentalProjectHasSettlementSnapshot(state.period,state.rentalTimesheetProject) && roleCanEdit('rental');
  }

  function rentalTimesheetPageData() {
    const all = rentalWorkersForTimesheet();
    const allowedSizes = [25, 50, 100];
    if (!allowedSizes.includes(Number(state.rentalTimesheetPageSize))) state.rentalTimesheetPageSize = 50;
    const pageSize = Number(state.rentalTimesheetPageSize);
    const totalPages = Math.max(1, Math.ceil(all.length / pageSize));
    state.rentalTimesheetPage = Math.min(Math.max(1, Number(state.rentalTimesheetPage) || 1), totalPages);
    const startIndex = (state.rentalTimesheetPage - 1) * pageSize;
    const rows = all.slice(startIndex, startIndex + pageSize);
    return {
      all,
      rows,
      pageSize,
      totalPages,
      page: state.rentalTimesheetPage,
      rangeStart: all.length ? startIndex + 1 : 0,
      rangeEnd: Math.min(startIndex + pageSize, all.length)
    };
  }

  function rentalTimesheetStatusDescription(status = rentalTimesheetStatus()) {
    if (status === 'Draft') return 'Project manpower input is open while effective assignments remain the edit boundary.';
    if (status === 'Submitted') return 'Worker-day entries are frozen while the project timesheet is under operational review.';
    if (status === 'Approved') return 'The reviewed project snapshot is approved and ready to lock for supplier settlement.';
    if (status === 'Locked') return 'The project timesheet is immutable and available as a controlled supplier-settlement input.';
    return 'This project timesheet is under controlled rental-manpower review.';
  }

  function exportRentalTimesheetCsv() {
    const workers = rentalWorkersForTimesheet();
    const info = periodInfo();
    const project = state.projects.find(item => item.id === state.rentalTimesheetProject);
    const bucket = state.rentalTimesheets?.[state.period]?.[state.rentalTimesheetProject] || {};
    const header = ['Worker ID','Worker','Supplier','Trade / Rate', ...Array.from({length:info.days},(_,i)=>String(i+1)), 'Regular Hours','OT Hours','Missing'];
    const quote = value => `"${String(value ?? '').replace(/"/g, '""')}"`;
    const rows = workers.map(worker => {
      const supplier = rentalWorkerSupplier(worker);
      const record = bucket[worker.id] || {};
      const metrics = rentalWorkerTimesheetMetrics(worker);
      return [
        rentalWorkerCode(worker), worker.name, supplier?.name || '', rentalPeriodAssignmentsLabel(worker),
        ...Array.from({length:info.days},(_,i)=>record[i+1] ?? record[String(i+1)] ?? ''),
        metrics.hours, metrics.otHours, metrics.missing
      ];
    });
    const csv = [header, ...rows].map(row => row.map(quote).join(',')).join('\r\n');
    const blob = new Blob([`\uFEFF${csv}`], {type:'text/csv;charset=utf-8'});
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `rental-timesheet-${(project?.code || state.rentalTimesheetProject || 'project').replace(/[^a-z0-9_-]+/gi,'-').toLowerCase()}-${state.period.replace(/\s+/g,'-').toLowerCase()}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    showToast('Project timesheet exported', `${workers.length} worker row${workers.length === 1 ? '' : 's'} exported for ${project?.name || 'the selected project'} · ${state.period}.`);
  }

  function rentalTimesheetGrid(workers) {
    ensureRentalTimesheet();
    const info = periodInfo();
    const editable = rentalTimesheetCanEdit();
    const bucket = state.rentalTimesheets?.[state.period]?.[state.rentalTimesheetProject] || {};
    const days = Array.from({length:info.days},(_,i)=>i+1);
    return `<div class="ui-v2-payroll-timesheet-scroll ui-v2-prs-rental-timesheet-scroll" tabindex="0" role="region" aria-label="${escapeHtml(state.period)} rental project manpower timesheet grid">
      <table class="ui-v2-payroll-timesheet-grid ui-v2-prs-rental-timesheet-grid" aria-label="Rental worker project timesheet by day">
        <caption class="ui-v2-sr-only">${escapeHtml(state.period)} rental worker project timesheet by day</caption>
        <thead><tr>
          <th class="is-select" aria-label="Worker selection"></th>
          <th class="is-employee">Worker</th>
          ${rentalTimesheetDayHeaders(info)}
          <th class="is-total is-hours">Reg hrs</th><th class="is-total is-days">OT</th><th class="is-total is-exceptions">Missing</th>
        </tr></thead>
        <tbody>${workers.map(worker => {
          const record = bucket[worker.id] || {};
          const supplier = rentalWorkerSupplier(worker);
          const metrics = rentalWorkerTimesheetMetrics(worker);
          const trade = rentalPeriodAssignmentsLabel(worker,undefined,undefined,'trade');
          const rate = rentalPeriodAssignmentsLabel(worker,undefined,undefined,'rate');
          const cells = days.map(day => {
            const assignment = rentalAssignmentForDate(worker,state.rentalTimesheetProject,day,state.period);
            const dayClasses = attendanceDayClasses(day,state.period);
            if (!assignment) return `<td class="${dayClasses} is-disabled-day"><span class="ui-v2-payroll-timesheet-not-assigned" title="Not assigned to this project on ${day} ${escapeHtml(info.monthName)}" aria-label="Not assigned on day ${day}">—</span></td>`;
            const value = record[day] ?? record[String(day)] ?? '';
            const tone = rentalTimesheetTone(value);
            const uiTone = tone === 'unexcused' ? 'zero' : tone;
            const numericHours = Number(value);
            const overtime = Number.isFinite(numericHours) && numericHours > 8;
            const title = `${assignment.trade || worker.trade || 'Worker'} · ${rentalRateLabelFromParts(assignment.rateType,assignment.rateValue,assignment.rateLabel)}`;
            return `<td class="${dayClasses}${overtime ? ' has-overtime' : ''}" title="${escapeHtml(title)}"><input class="ui-v2-payroll-ts-input is-${uiTone}${overtime ? ' is-overtime' : ''}${String(value).length > 1 ? ' is-multi-digit' : ''}" value="${escapeHtml(value)}" data-rental-ts-input="${escapeHtml(worker.id)}" data-day="${day}" ${editable ? '' : 'disabled'} aria-label="${escapeHtml(worker.name)}, day ${day}" maxlength="4" autocomplete="off"></td>`;
          }).join('');
          return `<tr data-rental-ts-row="${escapeHtml(worker.id)}">
            <td class="is-select"><input type="checkbox" data-rental-ts-select="${escapeHtml(worker.id)}" ${state.rentalTimesheetSelected.has(worker.id) ? 'checked' : ''} ${editable ? '' : 'disabled'} aria-label="Select ${escapeHtml(worker.name)}"></td>
            <td class="is-employee"><button type="button" data-open-rental-worker="${escapeHtml(worker.id)}"><strong>${escapeHtml(worker.name)}</strong><span>${escapeHtml(rentalWorkerCode(worker))} · ${escapeHtml(trade)} · ${escapeHtml(supplier?.name || 'Supplier not linked')} · ${escapeHtml(rate)}</span></button></td>
            ${cells}
            <td class="is-total is-hours"><strong>${metrics.hours.toLocaleString('en-SA',{maximumFractionDigits:2})}</strong></td>
            <td class="is-total is-days"><strong>${metrics.otHours ? metrics.otHours.toLocaleString('en-SA',{maximumFractionDigits:2}) : '—'}</strong></td>
            <td class="is-total is-exceptions ${metrics.missing ? 'has-exceptions' : ''}"><strong>${metrics.missing || '—'}</strong></td>
          </tr>`;
        }).join('')}</tbody>
      </table>
    </div>`;
  }


  function rentalTimesheetDailyTemplate() {
    ensureRentalTimesheet();
    const page = rentalTimesheetPageData();
    const workers = page.rows;
    const filteredWorkers = page.all;
    const totals = rentalTimesheetProjectTotals(filteredWorkers);
    const status = rentalTimesheetStatus();
    const next = rentalTimesheetNextAction(status);
    const project = state.projects.find(item => item.id === state.rentalTimesheetProject);
    const projectWorkers = state.rentalWorkers.filter(worker => rentalAssignmentsInProjectPeriod(worker,state.rentalTimesheetProject,state.period).length);
    const supplierOptions = [...new Set(projectWorkers.map(worker => worker.supplierId).filter(Boolean))].map(id=>state.suppliers.find(s=>s.id===id)).filter(Boolean);
    const selectedCount = state.rentalTimesheetSelected.size;
    const selectedOnPage = workers.filter(worker=>state.rentalTimesheetSelected.has(worker.id)).length;
    const info = periodInfo();
    const editable = rentalTimesheetCanEdit();
    const settlementProtected = rentalProjectHasSettlementSnapshot(state.period,state.rentalTimesheetProject);
    const meta = state.rentalTimesheetMeta[rentalTimesheetRecordKey()] || {};
    const allPageSelected = workers.length > 0 && workers.every(worker => state.rentalTimesheetSelected.has(worker.id));
    const somePageSelected = workers.some(worker => state.rentalTimesheetSelected.has(worker.id)) && !allPageSelected;
    const supplierCount = new Set(filteredWorkers.map(worker=>worker.supplierId).filter(Boolean)).size;

    return `
      <div class="ui-v2-payroll-summary-strip ui-v2-prs-rental-timesheet-summary">
        <div class="ui-v2-payroll-metric"><span>Worker roster</span><strong>${projectWorkers.length.toLocaleString()}</strong><small>${filteredWorkers.length.toLocaleString()} in current filter · ${supplierCount.toLocaleString()} supplier${supplierCount===1?'':'s'}</small></div>
        <div class="ui-v2-payroll-metric"><span>Regular hours</span><strong>${totals.hours.toLocaleString('en-SA',{maximumFractionDigits:2})}</strong><small>${escapeHtml(state.period)} saved project hours</small></div>
        <div class="ui-v2-payroll-metric"><span>Overtime</span><strong>${totals.otHours.toLocaleString('en-SA',{maximumFractionDigits:2})}</strong><small>Explicit worker OT register</small></div>
        <div class="ui-v2-payroll-metric"><span>Approval state</span><strong>${escapeHtml(status)}</strong><small>${totals.missing.toLocaleString()} missing · revision ${Number(meta.revision || 0)}</small></div>
      </div>
      <section class="ui-v2-payroll-panel ui-v2-payroll-timesheet-lifecycle"><header><div><span>Project period control</span><h2>${escapeHtml(project?.name || 'Project')} timesheet lifecycle</h2></div>${v2TimesheetStatusBadge(status)}</header>${rentalTimesheetWorkflow(status)}</section>
      <section class="ui-v2-payroll-attendance-control-strip ui-v2-prs-rental-control-strip">
        <div class="ui-v2-payroll-attendance-control-strip__state"><span class="ui-v2-payroll-attendance-control-icon is-${escapeHtml(status.toLowerCase().replace(/\s+/g,'-'))}">${status === 'Approved' || status === 'Locked' ? '✓' : icon('timesheet')}</span><div><strong>${escapeHtml(status)}</strong><span>${escapeHtml(settlementProtected && status === 'Draft' ? 'A calculated supplier settlement protects this project-period snapshot. Return the settlement before editing or resubmitting.' : rentalTimesheetStatusDescription(status))}</span></div></div>
        <div class="ui-v2-payroll-attendance-control-strip__actions">${totals.missing ? `<span class="ui-v2-payroll-attendance-exception-link">${totals.missing.toLocaleString()} missing entr${totals.missing===1?'y':'ies'}</span>` : '<span class="ui-v2-payroll-attendance-clear">✓ No missing entries</span>'}${['Submitted','Approved'].includes(status) && roleCanApprove() ? '<button class="ui-v2-button ui-v2-button--secondary ui-v2-button--sm" data-rental-timesheet-return>Return to Draft</button>' : ''}${['Approved','Locked'].includes(status) ? `<button class="ui-v2-button ui-v2-button--secondary ui-v2-button--sm" data-open-rental-settlement-project="${escapeHtml(state.rentalTimesheetProject)}" data-settlement-period="${escapeHtml(state.period)}">Open Settlement</button>` : ''}<button class="ui-v2-button ui-v2-button--primary ui-v2-button--sm" data-rental-timesheet-workflow ${next.next && !(settlementProtected && status === 'Draft') ? '' : 'disabled'}>${escapeHtml(settlementProtected && status === 'Draft' ? 'Settlement Protected' : next.label)}</button></div>
      </section>
      <section class="ui-v2-payroll-panel ui-v2-payroll-register ui-v2-payroll-timesheet-workspace ui-v2-prs-rental-timesheet-workspace ${state.timesheetFullscreen ? 'is-fullscreen' : ''}" aria-label="Rental project manpower timesheet workspace">
        <div class="ui-v2-payroll-register__toolbar ui-v2-payroll-timesheet-toolbar">
          <div class="ui-v2-filter-bar__search">${icon('search')}<input id="rentalTimesheetSearch" class="ui-v2-input" type="search" value="${escapeHtml(state.rentalTimesheetSearch)}" placeholder="Search worker, ID, trade or supplier" autocomplete="off" aria-label="Search rental project timesheet workers"></div>
          <select class="ui-v2-select ui-v2-payroll-operational-select" id="rentalTimesheetProjectFilter" aria-label="Project">${state.projects.filter(project=>project.status !== 'Completed').map(item=>`<option value="${escapeHtml(item.id)}" ${item.id===state.rentalTimesheetProject?'selected':''}>${escapeHtml(item.name)}</option>`).join('')}</select>
          <select class="ui-v2-select ui-v2-payroll-operational-select" id="rentalTimesheetSupplierFilter" aria-label="Supplier"><option>All suppliers</option>${supplierOptions.map(item=>`<option value="${escapeHtml(item.id)}" ${item.id===state.rentalTimesheetSupplier?'selected':''}>${escapeHtml(item.name)}</option>`).join('')}</select>
          <button class="ui-v2-button ui-v2-button--secondary ui-v2-button--sm" data-rental-timesheet-reset>${icon('filter')}<span>Reset</span></button>
          <div class="ui-v2-payroll-timesheet-file-actions">${editable ? '<button class="ui-v2-button ui-v2-button--secondary ui-v2-button--sm" data-rental-timesheet-import>Import</button>' : ''}<button class="ui-v2-button ui-v2-button--secondary ui-v2-button--sm" data-rental-timesheet-export>Export</button></div>
          <button class="ui-v2-button ui-v2-button--secondary ui-v2-button--sm ui-v2-payroll-timesheet-fullscreen" data-timesheet-fullscreen aria-pressed="${state.timesheetFullscreen ? 'true' : 'false'}"><span>${icon(state.timesheetFullscreen ? 'collapse' : 'expand')}</span>${state.timesheetFullscreen ? 'Exit Full Screen' : 'Full Screen'}</button>
        </div>
        <div class="ui-v2-payroll-timesheet-subtoolbar"><div class="ui-v2-payroll-timesheet-legend"><span><i class="is-worked"></i>Hours</span><span><i class="is-zero"></i>0 · Zero hours</span><span><i class="is-absent"></i>A · Absent</span><span><i class="is-noscope"></i>N · No scope</span><span><i class="is-leave"></i>L · Leave</span><span><i class="is-off"></i>OFF</span><span><i class="is-weekend"></i>Weekend</span><span><i class="is-disabled"></i>Not assigned</span></div><span>A / N / L / OFF are valid explicit statuses; only blank assigned worker-days block submission. Enter 0–24 hours for worked days.</span></div>
        <div class="ui-v2-payroll-timesheet-bulkbar ${selectedCount ? 'is-active' : 'is-idle'}">
          <div class="ui-v2-payroll-timesheet-master-select"><input type="checkbox" data-rental-ts-select-all aria-label="${allPageSelected ? 'Unselect' : 'Select'} this page of workers" ${allPageSelected ? 'checked' : ''} ${editable ? '' : 'disabled'} data-rental-indeterminate="${somePageSelected ? 'true' : 'false'}"></div>
          <div class="ui-v2-payroll-timesheet-selection-summary"><strong>${selectedCount ? `${selectedCount.toLocaleString()} selected` : `${workers.length.toLocaleString()} workers`}</strong><div class="ui-v2-payroll-timesheet-selection-meta"><small>${selectedCount ? `${selectedOnPage.toLocaleString()} on this page · ${selectedCount.toLocaleString()} selected` : `${page.rangeStart}–${page.rangeEnd} of ${filteredWorkers.length.toLocaleString()} matching`}</small>${selectedCount ? '<div class="ui-v2-payroll-timesheet-selection-actions"><button type="button" data-rental-timesheet-clear-selection>Clear</button></div>' : ''}</div></div>
          <div class="ui-v2-payroll-timesheet-command-strip"><label class="ui-v2-prs-timesheet-day-select"><span>Day</span><select id="rentalTimesheetBulkDay" class="ui-v2-select ui-v2-payroll-dense-select" ${selectedCount && editable ? '' : 'disabled'}>${Array.from({length:info.days},(_,i)=>i+1).map(day=>`<option value="${day}" ${Number(state.rentalTimesheetBulkDay)===day?'selected':''}>${day} · ${weekdayShort(day,state.period)}${isCompanyToday(day,state.period) ? ' · Today' : ''}</option>`).join('')}</select></label><button class="ui-v2-button ui-v2-button--secondary ui-v2-button--sm" data-rental-ts-bulk="8" ${selectedCount && editable ? '' : 'disabled'}>Fill 8h</button><button class="ui-v2-button ui-v2-button--secondary ui-v2-button--sm" data-rental-ts-bulk="A" ${selectedCount && editable ? '' : 'disabled'}>Sick absent</button><button class="ui-v2-button ui-v2-button--secondary ui-v2-button--sm" data-rental-ts-bulk="0" ${selectedCount && editable ? '' : 'disabled'}>Absent</button><button class="ui-v2-button ui-v2-button--secondary ui-v2-button--sm" data-rental-ts-bulk="N" ${selectedCount && editable ? '' : 'disabled'}>No scope</button><button class="ui-v2-button ui-v2-button--secondary ui-v2-button--sm" data-rental-ts-bulk="copy" ${selectedCount && editable && Number(state.rentalTimesheetBulkDay) > 1 ? '' : 'disabled'}>Copy previous</button><button class="ui-v2-button ui-v2-button--quiet ui-v2-button--sm" data-rental-ts-bulk="clear" ${selectedCount && editable ? '' : 'disabled'}>Clear day</button></div>
        </div>
        ${workers.length ? rentalTimesheetGrid(workers) : `<div class="ui-v2-payroll-table-empty"><strong>No rental workers overlap this project period.</strong><span>Assign workers to this project, change the supplier filter, or choose another project.</span></div>`}
        <div class="ui-v2-payroll-timesheet-footer"><span class="ui-v2-payroll-timesheet-footer-status"><strong>${page.rangeStart}–${page.rangeEnd}</strong> of <strong>${filteredWorkers.length.toLocaleString()}</strong> workers <i></i> <strong>${supplierCount.toLocaleString()}</strong> supplier${supplierCount===1?'':'s'} <i></i> <strong>${totals.missing.toLocaleString()}</strong> missing <i></i> <strong>${escapeHtml(status)}</strong>${editable ? ' · editable' : ' · read-only'}</span>${page.totalPages > 1 ? `<div class="ui-v2-payroll-timesheet-pagination"><div class="ui-v2-payroll-timesheet-pagination__pages"><button type="button" data-rental-timesheet-page="${page.page - 1}" ${page.page <= 1 ? 'disabled' : ''} aria-label="Previous page">‹</button><span>Page <strong>${page.page}</strong> / ${page.totalPages}</span><button type="button" data-rental-timesheet-page="${page.page + 1}" ${page.page >= page.totalPages ? 'disabled' : ''} aria-label="Next page">›</button></div><label class="ui-v2-payroll-timesheet-pagination__size">Rows <select id="rentalTimesheetPageSize" class="ui-v2-select ui-v2-payroll-dense-select"><option value="25" ${page.pageSize===25?'selected':''}>25</option><option value="50" ${page.pageSize===50?'selected':''}>50</option><option value="100" ${page.pageSize===100?'selected':''}>100</option></select></label></div>` : ''}<div class="ui-v2-payroll-timesheet-footer-actions">${editable ? '<button class="ui-v2-button ui-v2-button--secondary ui-v2-button--sm" data-rental-timesheet-save>Save draft</button>' : ''}</div></div>
      </section>`;
  }

  function rentalOvertimeRegisterTemplate() {
    ensureRentalTimesheet();
    const page = rentalTimesheetPageData();
    const workers = page.rows;
    const filteredWorkers = page.all;
    const totals = rentalTimesheetProjectTotals(filteredWorkers);
    const editable = rentalTimesheetCanEdit();
    const project = state.projects.find(item => item.id === state.rentalTimesheetProject);
    return `
      <div class="ui-v2-payroll-summary-strip ui-v2-prs-rental-timesheet-summary">
        <div class="ui-v2-payroll-metric"><span>Workers</span><strong>${filteredWorkers.length.toLocaleString()}</strong><small>${escapeHtml(project?.name || 'Selected project')} · ${escapeHtml(state.period)}</small></div>
        <div class="ui-v2-payroll-metric"><span>Regular hours</span><strong>${totals.hours.toLocaleString('en-SA',{maximumFractionDigits:2})}</strong><small>Daily project timesheet</small></div>
        <div class="ui-v2-payroll-metric"><span>OT hours</span><strong>${totals.otHours.toLocaleString('en-SA',{maximumFractionDigits:2})}</strong><small>Explicit rental overtime</small></div>
        <div class="ui-v2-payroll-metric"><span>Incomplete cells</span><strong>${totals.missing.toLocaleString('en-SA')}</strong><small>Daily sheet must be complete before submission</small></div>
      </div>
      <section class="ui-v2-payroll-panel ui-v2-payroll-register ui-v2-prs-rental-ot-panel">
        <div class="ui-v2-payroll-register__toolbar ui-v2-prs-rental-ot-toolbar"><div><strong>Worker overtime register</strong><span>OT inputs stay separate from supplier settlement calculation.</span></div><button class="ui-v2-button ui-v2-button--secondary ui-v2-button--sm" data-rental-timesheet-tab-jump="daily">Daily Timesheet</button></div>
        <div class="ui-v2-table-wrap"><table class="ui-v2-table ui-v2-prs-rental-ot-table"><thead><tr><th>Worker</th><th>Trade / commercial rate</th><th class="is-numeric">Regular</th><th>OT hours</th><th>OT hourly rate</th><th>Settlement</th></tr></thead><tbody>${workers.length ? workers.map(worker=>{
          const metrics=rentalWorkerTimesheetMetrics(worker);
          return `<tr><td><button class="ui-v2-prs-rental-ot-worker" data-open-rental-worker="${escapeHtml(worker.id)}"><strong>${escapeHtml(worker.name)}</strong><span>${escapeHtml(rentalWorkerCode(worker))} · ${escapeHtml(rentalWorkerSupplier(worker)?.name || 'Supplier not linked')}</span></button></td><td><strong>${escapeHtml(rentalPeriodAssignmentsLabel(worker))}</strong><span class="ui-v2-prs-rental-ot-rate-label">${escapeHtml(rentalPeriodAssignmentsLabel(worker,undefined,undefined,'rate'))}</span></td><td class="is-numeric">${metrics.hours.toLocaleString('en-SA',{maximumFractionDigits:2})} h</td><td><input class="ui-v2-input ui-v2-prs-rental-ot-input" type="number" min="0" step="0.25" value="${metrics.otHours || ''}" data-rental-ot-hours="${escapeHtml(worker.id)}" ${editable?'':'disabled'} aria-label="Overtime hours for ${escapeHtml(worker.name)}"></td><td><div class="ui-v2-prs-money-input"><span>${escapeHtml(currencyCode())}</span><input class="ui-v2-input" type="number" min="0" step="0.01" value="${metrics.otRate || ''}" data-rental-ot-rate="${escapeHtml(worker.id)}" ${editable?'':'disabled'} aria-label="Overtime hourly rate for ${escapeHtml(worker.name)}"></div></td><td><span class="ui-v2-muted">Calculated after lock</span></td></tr>`;
        }).join('') : '<tr><td colspan="6"><div class="ui-v2-payroll-table-empty"><strong>No workers match this overtime view.</strong><span>Change the project, supplier or search filter on the Daily Timesheet tab.</span></div></td></tr>'}</tbody>${workers.length ? `<tfoot><tr><td colspan="2"><strong>Page total</strong></td><td class="is-numeric"><strong>${rentalTimesheetProjectTotals(workers).hours.toLocaleString('en-SA',{maximumFractionDigits:2})} h</strong></td><td><strong>${rentalTimesheetProjectTotals(workers).otHours.toLocaleString('en-SA',{maximumFractionDigits:2})} h</strong></td><td></td><td></td></tr></tfoot>` : ''}</table></div>
        <div class="ui-v2-payroll-timesheet-footer"><span class="ui-v2-payroll-timesheet-footer-status"><strong>${page.rangeStart}–${page.rangeEnd}</strong> of <strong>${filteredWorkers.length.toLocaleString()}</strong> workers <i></i> Settlement values remain server-calculated after lock</span>${page.totalPages > 1 ? `<div class="ui-v2-payroll-timesheet-pagination"><div class="ui-v2-payroll-timesheet-pagination__pages"><button type="button" data-rental-timesheet-page="${page.page - 1}" ${page.page <= 1 ? 'disabled' : ''}>‹</button><span>Page <strong>${page.page}</strong> / ${page.totalPages}</span><button type="button" data-rental-timesheet-page="${page.page + 1}" ${page.page >= page.totalPages ? 'disabled' : ''}>›</button></div><label class="ui-v2-payroll-timesheet-pagination__size">Rows <select id="rentalTimesheetPageSize" class="ui-v2-select ui-v2-payroll-dense-select"><option value="25" ${page.pageSize===25?'selected':''}>25</option><option value="50" ${page.pageSize===50?'selected':''}>50</option><option value="100" ${page.pageSize===100?'selected':''}>100</option></select></label></div>` : ''}</div>
      </section>
      <section class="ui-v2-payroll-panel ui-v2-prs-rental-settlement-boundary"><header><div><span>Financial boundary</span><h2>Timesheet → Lock → Settlement → Payment</h2></div>${v2TimesheetStatusBadge(rentalTimesheetStatus())}</header><div class="ui-v2-prs-rental-boundary-grid"><div><strong>Timesheet</strong><span>Records worker-day hours/status and assignment-specific OT inputs.</span></div><div><strong>Lock</strong><span>Freezes this project-period as a controlled financial source.</span></div><div><strong>Settlement</strong><span>Applies supplier commercial rules and approved adjustments server-side.</span></div><div><strong>Payment</strong><span>Remains a separate supplier-payable lifecycle after settlement approval.</span></div></div></section>`;
  }

  function rentalTimesheetsTemplate() {
    let project = state.projects.find(item => item.id === state.rentalTimesheetProject);
    if (!project) {
      state.rentalTimesheetProject = preferredRentalProjectId(state.projects);
      project = state.projects.find(item => item.id === state.rentalTimesheetProject);
    }
    ensureRentalTimesheet();
    const status = rentalTimesheetStatus();
    const overtimeCount = rentalWorkersForTimesheet().filter(worker => rentalOvertimeFor(worker).hours > 0).length;
    return `<section class="ui-v2-page ui-v2-payroll-page ui-v2-prs-rental-page ui-v2-prs-rental-timesheets-page timesheets-page">
      <div class="ui-v2-page-header"><div class="ui-v2-page-header__copy"><span class="ui-v2-eyebrow">Operations · Rental Workforce</span><h1 class="ui-v2-title-lg">Project Manpower Timesheets</h1><p class="ui-v2-body">Daily supplier-workforce input tied to permanent worker masters and effective-dated project assignments.</p><span class="ui-v2-prs-period-note">Working period: <strong>${escapeHtml(state.period)}</strong>${project ? ` · <strong>${escapeHtml(project.name)}</strong>` : ''} · ${v2TimesheetStatusBadge(status)}</span></div><div class="ui-v2-page-header__actions">${state.rentalTimesheetTab === 'ot' ? '<button class="ui-v2-button ui-v2-button--primary" data-rental-timesheet-tab-jump="daily">Daily Timesheet</button>' : ''}</div></div>
      <nav class="ui-v2-tabs ui-v2-prs-timesheet-tabs" aria-label="Rental project timesheet views"><button class="${state.rentalTimesheetTab==='daily'?'is-active':''}" data-rental-timesheet-tab="daily">Daily Timesheet</button><button class="${state.rentalTimesheetTab==='ot'?'is-active':''}" data-rental-timesheet-tab="ot">Overtime <span class="ui-v2-prs-tab-count">${overtimeCount}</span></button></nav>
      ${state.rentalTimesheetTab === 'ot' ? rentalOvertimeRegisterTemplate() : rentalTimesheetDailyTemplate()}
    </section>`;
  }

  function timesheetsTemplate() {
    if (state.timesheetWorkspace === 'rental') return rentalTimesheetsTemplate();
    if (!state.attendanceLoadedPeriods.has(state.period)) {
      loadInternalAttendancePeriod(state.period);
      return `<section class="ui-v2-page ui-v2-payroll-page ui-v2-prs-internal-page timesheets-page"><div class="ui-v2-page-header"><div class="ui-v2-page-header__copy"><span class="ui-v2-eyebrow">Operations · Attendance</span><h1 class="ui-v2-title-lg">Timesheets & Overtime</h1><p class="ui-v2-body">Loading the company attendance period and employee roster for ${escapeHtml(state.period)}.</p></div></div><div class="ui-v2-payroll-table-empty"><strong>Loading attendance…</strong><span>Fetching the company-scoped monthly snapshot from the server.</span></div></section>`;
    }
    ensureTimesheetPeriod();
    const status = timesheetStatus();
    const overtimeCount = Object.values(state.attendanceOvertimeMeta[state.period] || {}).filter(item => Number(item.hours || 0) > 0).length;
    return `<section class="ui-v2-page ui-v2-payroll-page ui-v2-prs-internal-page timesheets-page">
      <div class="ui-v2-page-header"><div class="ui-v2-page-header__copy"><span class="ui-v2-eyebrow">Operations · Attendance</span><h1 class="ui-v2-title-lg">Timesheets & Overtime</h1><p class="ui-v2-body">Monthly internal-company attendance and overtime with server-enforced review, approval and locking.</p><span class="ui-v2-prs-period-note">Working period: <strong>${escapeHtml(state.period)}</strong> · ${v2TimesheetStatusBadge(status)}</span></div><div class="ui-v2-page-header__actions">${state.timesheetTab === 'overtime' ? '<button class="ui-v2-button ui-v2-button--primary" data-route-link="salary-setup">OT Policy</button>' : ''}</div></div>
      <nav class="ui-v2-tabs ui-v2-prs-timesheet-tabs" aria-label="Internal timesheet views"><button class="${state.timesheetTab === 'attendance' ? 'is-active' : ''}" data-timesheet-tab="attendance">Attendance</button><button class="${state.timesheetTab === 'overtime' ? 'is-active' : ''}" data-timesheet-tab="overtime">Overtime <span class="ui-v2-prs-tab-count">${overtimeCount}</span></button></nav>
      ${state.timesheetTab === 'overtime' ? internalOvertimeTemplate() : internalAttendanceTemplate()}
    </section>`;
  }

  function emptyPayrollContext(period = state.period) {
    return {
      run: { id:null, exists:false, label:period, statusValue:'draft', status:'Draft', revision:0, calculatedAt:null, submittedAt:null, approvedAt:null, reviewerNote:'', canEdit:false, canApprove:false, totals:{} },
      rows: [], sourceErrors: [], policy: { prorationMethod:'not_configured', prorationLabel:'Not configured', configured:false },
      adjustments: [], adjustmentsByEmployee: {}, reviewHistory: [], attendanceStatus:'Not created', attendanceLocked:false,
      previous: { label:payrollPreviousPeriod(period), run:null, rows:[] }
    };
  }

  function normalizedPayrollRun(context = emptyPayrollContext()) {
    const source = context.run || {};
    const run = {
      ...source,
      status: source.status || 'Draft',
      calculatedAt: source.calculatedAt || null,
      submittedAt: source.submittedAt || null,
      approvedAt: source.approvedAt || null,
      reviewerNote: source.reviewerNote || '',
      reviewHistory: Array.isArray(context.reviewHistory) ? context.reviewHistory : []
    };
    run.snapshot = run.status === 'Draft' ? null : {
      period: run.label || state.period,
      timesheetStatus: context.attendanceStatus || 'Not created',
      rows: Array.isArray(context.rows) ? context.rows : [],
      totals: run.totals || {},
      calculatedAt: run.calculatedAt
    };
    return run;
  }

  function applyPayrollPayload(payload, fallbackPeriod = state.period) {
    const label = payload?.run?.label || fallbackPeriod;
    state.payrollContexts[label] = payload;
    state.payrollLoadedPeriods.add(label);
    state.payrollRuns[label] = normalizedPayrollRun(payload);
    if (label === state.period) state.internalAdjustments = payload.adjustmentsByEmployee || {};
    const previous = payload?.previous;
    if (previous?.label) {
      const previousContext = {
        run: previous.run || { label:previous.label, status:'Draft', statusValue:'draft' },
        rows: Array.isArray(previous.rows) ? previous.rows : [],
        sourceErrors: [], policy: payload.policy || {}, adjustments: [], adjustmentsByEmployee: {}, reviewHistory: [],
        attendanceStatus: previous.run?.status ? 'Historical snapshot' : 'Not loaded', attendanceLocked:false,
        previous: null
      };
      state.payrollContexts[previous.label] = previousContext;
      state.payrollRuns[previous.label] = normalizedPayrollRun(previousContext);
    }
    return payload;
  }

  if (payrollBootstrap.run?.label) applyPayrollPayload(payrollBootstrap, payrollBootstrap.run.label);

  async function loadInternalPayrollPeriod(period = state.period, { force = false } = {}) {
    if (!force && state.payrollLoadedPeriods.has(period)) return state.payrollContexts[period];
    if (state.payrollLoadingPeriod === period) return null;
    state.payrollLoadingPeriod = period;
    try {
      const payload = await appApi(`/api/internal/payroll/?period=${encodeURIComponent(periodKeyFromLabel(period))}`);
      applyPayrollPayload(payload, period);
      if (state.workspace === 'internal' && state.period === period && ['payroll-runs','adjustments'].includes(currentRoute())) renderRoute();
      return payload;
    } catch (error) {
      showToast('Payroll could not be loaded', error.message);
      return null;
    } finally {
      if (state.payrollLoadingPeriod === period) state.payrollLoadingPeriod = null;
    }
  }

  function payrollContextForPeriod(period = state.period) {
    return state.payrollContexts[period] || emptyPayrollContext(period);
  }

  function payrollRunRecord(period = state.period) {
    const context = payrollContextForPeriod(period);
    const run = normalizedPayrollRun(context);
    state.payrollRuns[period] = run; // Transitional read cache for payment/report modules until their server endpoints are wired.
    return run;
  }

  function payrollRunStatus(period = state.period) {
    return payrollRunRecord(period).status || 'Draft';
  }

  function payrollRunStatusBadge(status) {
    const tone = ['Closed','Paid','Approved'].includes(status) ? 'success' : ['Review','Calculated','Payment Processing'].includes(status) ? 'warning' : 'neutral';
    return `<span class="payroll-run-status payroll-run-status--${tone}"><span></span>${escapeHtml(status)}</span>`;
  }

  function payrollWorkflow(status = payrollRunStatus()) {
    const steps = ['Draft','Calculated','Review','Approved','Payment Processing','Paid','Closed'];
    const currentIndex = Math.max(0, steps.indexOf(status));
    return `<div class="payroll-workflow" aria-label="Payroll run status">${steps.map((step,index) => `<div class="payroll-workflow__step ${index <= currentIndex ? 'is-complete' : ''} ${index === currentIndex ? 'is-current' : ''}"><span>${index + 1}</span><strong>${step}</strong></div>`).join('')}</div>`;
  }

  function payrollRowForEmployee(employee) {
    const row = payrollRowsForDisplay().find(item => item.employeeId === employee.id);
    if (row) return row;
    return {
      employeeId:employee.id, employeeCode:employee.employeeId, name:employee.name, position:employee.position || '', department:employee.department || '',
      branchId:employee.branchId || null, branch:employee.branch || '', basic:0, allowances:0, overtime:0, otHours:0, otPolicy:'', otherEarnings:0,
      gross:0, advances:0, deductions:0, net:0, salaryComponents:[], adjustmentLines:[], pendingAdjustments:[],
      blockers:['Payroll data is not available from the server for this period.'], warnings:[], readiness:'Blocked'
    };
  }

  function livePayrollRows() {
    return [...(payrollContextForPeriod().rows || [])];
  }

  function payrollRowsForDisplay(period = state.period) {
    return [...(payrollContextForPeriod(period).rows || [])];
  }

  async function requestPayrollCalculation() {
    const payload = await appApi('/api/internal/payroll/calculate/', { method:'POST', body:{ period:periodKeyFromLabel() } });
    return applyPayrollPayload(payload);
  }

  async function requestPayrollWorkflow(action, { note = '', confirmed = false } = {}) {
    const payload = await appApi('/api/internal/payroll/workflow/', { method:'POST', body:{ period:periodKeyFromLabel(), action, note, confirmed } });
    return applyPayrollPayload(payload);
  }

  async function requestPayrollPolicy(prorationMethod) {
    const result = await appApi('/api/internal/payroll/policy/', { method:'PATCH', body:{ proration_method:prorationMethod } });
    const current = payrollContextForPeriod();
    current.policy = result.policy;
    await loadInternalPayrollPeriod(state.period, { force:true });
    return result.policy;
  }

  function payrollTotals(rows = []) {
    return rows.reduce((totals,row) => {
      totals.basic += Number(row.basic || 0);
      totals.allowances += Number(row.allowances || 0);
      totals.overtime += Number(row.overtime || 0);
      totals.otherEarnings += Number(row.otherEarnings || 0);
      totals.gross += Number(row.gross || 0);
      totals.advances += Number(row.advances || 0);
      totals.deductions += Number(row.deductions || 0);
      totals.net += Number(row.net || 0);
      if (row.blockers?.length) totals.blocked += 1; else totals.ready += 1;
      if (row.warnings?.length) totals.warning += 1;
      return totals;
    }, { basic:0, allowances:0, overtime:0, otherEarnings:0, gross:0, advances:0, deductions:0, net:0, ready:0, blocked:0, warning:0 });
  }

  function payrollFilteredRows(rows) {
    const q = state.payrollSearch.trim().toLowerCase();
    return rows.filter(row => {
      const branchMatch = state.payrollBranch === 'All branches' || row.branch === state.payrollBranch;
      const departmentMatch = state.payrollDepartment === 'All departments' || row.department === state.payrollDepartment;
      const readinessMatch = state.payrollReadiness === 'All' || (state.payrollReadiness === 'Blocked' ? row.blockers?.length : !row.blockers?.length);
      const text = `${row.employeeCode} ${row.name} ${row.position} ${row.department} ${row.branch}`.toLowerCase();
      return branchMatch && departmentMatch && readinessMatch && (!q || text.includes(q));
    });
  }

  function payrollMoney(value, blocked = false) {
    if (blocked && !(Number(value) > 0)) return '<span class="payroll-empty-amount">—</span>';
    return formatCurrency(Number(value || 0));
  }

  function payrollReadinessBadge(row) {
    if (row.blockers?.length) return `<span class="readiness readiness--danger"><span></span>Blocked</span>`;
    if (row.warnings?.length) return `<span class="readiness readiness--warn"><span></span>Ready · warning</span>`;
    return `<span class="readiness readiness--ready"><span></span>Ready</span>`;
  }

  function payrollTimestamp(value) {
    if (!value) return 'Not calculated yet';
    try {
      return new Intl.DateTimeFormat('en-SA', { dateStyle:'medium', timeStyle:'short', timeZone: state.systemSettings.general.timezone || 'Asia/Riyadh' }).format(new Date(value));
    } catch { return value; }
  }


  function payrollPeriodDate(label) {
    const match = String(label || '').match(/^([A-Za-z]+)\s+(\d{4})$/);
    if (!match) return null;
    const month = ['January','February','March','April','May','June','July','August','September','October','November','December'].indexOf(match[1]);
    if (month < 0) return null;
    return new Date(Number(match[2]), month, 1);
  }

  function payrollPreviousPeriod(label = state.period) {
    const date = payrollPeriodDate(label);
    if (!date) return null;
    date.setMonth(date.getMonth() - 1);
    return `${date.toLocaleString('en', { month:'long' })} ${date.getFullYear()}`;
  }

  function payrollComparisonData(rows = payrollRowsForDisplay()) {
    const previousPeriod = payrollPreviousPeriod();
    const previousRun = previousPeriod ? state.payrollRuns[previousPeriod] : null;
    const previousRows = previousRun?.snapshot?.rows || [];
    const previousByEmployee = new Map(previousRows.map(row => [row.employeeId, row]));
    const available = previousRows.length > 0;
    const comparedRows = rows.map(row => {
      const previous = previousByEmployee.get(row.employeeId) || null;
      const currentNet = Number(row.net || 0);
      const previousNet = previous ? Number(previous.net || 0) : null;
      const delta = previousNet === null ? null : currentNet - previousNet;
      const deltaPct = previousNet && previousNet !== 0 ? delta / previousNet * 100 : null;
      return { ...row, previous, previousNet, delta, deltaPct };
    });
    return {
      previousPeriod,
      previousRun,
      available,
      rows: comparedRows,
      currentTotals: payrollTotals(rows),
      previousTotals: available ? payrollTotals(previousRows) : null
    };
  }

  function payrollReviewIssues(rows = payrollRowsForDisplay()) {
    const context = payrollContextForPeriod();
    const comparison = payrollComparisonData(rows);
    const issues = [];
    const push = issue => issues.push({ id: `${issue.type || 'issue'}-${issues.length + 1}`, employeeId: null, severity:'Info', type:'Review', ...issue });

    (context.sourceErrors || []).forEach(detail => push({ severity:'Critical', type:'Payroll input', title:'Payroll source input requires correction', detail, action:'Review payroll inputs' }));
    if (!context.attendanceLocked) {
      push({ severity:'Critical', type:'Attendance', title:`Attendance & overtime is ${context.attendanceStatus || 'not locked'}`, detail:'Finance Review and approval require the attendance/overtime period to be Locked.', action:'Open Timesheets', route:'timesheets' });
    }

    rows.forEach(row => {
      (row.blockers || []).forEach((detail, index) => push({ employeeId:row.employeeId, severity:'Critical', type:'Payroll setup', title:`${row.name}: calculation blocked`, detail, action:'Open employee', route:`internal-employees/${row.employeeId}`, key:`blocker-${index}` }));
      (row.warnings || []).forEach((detail, index) => push({ employeeId:row.employeeId, severity:'Warning', type:'Adjustment', title:`${row.name}: attention required`, detail, action:'View calculation', route:`internal-employees/${row.employeeId}`, key:`warning-${index}` }));
      if (Number(row.otHours || 0) >= 40 || (row.basic > 0 && Number(row.overtime || 0) / Number(row.basic) >= 0.2)) {
        push({ employeeId:row.employeeId, severity:'Warning', type:'Overtime', title:`${row.name}: high overtime`, detail:`${Number(row.otHours || 0)} OT hours · ${formatCurrency(row.overtime)}. Review against attendance and the assigned OT policy.`, action:'View calculation' });
      }
      const compared = comparison.rows.find(item => item.employeeId === row.employeeId);
      if (compared?.deltaPct !== null && Math.abs(compared.deltaPct) >= 10) {
        const severity = Math.abs(compared.deltaPct) >= 25 ? 'Critical' : 'Warning';
        push({ employeeId:row.employeeId, severity, type:'Variance', title:`${row.name}: net pay changed ${compared.deltaPct > 0 ? '+' : ''}${compared.deltaPct.toFixed(1)}%`, detail:`${comparison.previousPeriod}: ${formatCurrency(compared.previousNet)} → ${state.period}: ${formatCurrency(row.net)}.`, action:'View comparison' });
      }
    });

    if (!comparison.available) {
      push({ severity:'Info', type:'Comparison', title:`No ${comparison.previousPeriod || 'previous-period'} payroll snapshot available`, detail:'Variance checks become automatic after the previous period has a calculated payroll snapshot. No comparison amount is fabricated.', action:comparison.previousPeriod ? `Open ${comparison.previousPeriod}` : '' });
    }

    return { issues, comparison };
  }

  function payrollReviewSeverityBadge(severity) {
    const tone = severity === 'Critical' ? 'danger' : severity === 'Warning' ? 'warn' : 'info';
    return `<span class="review-severity review-severity--${tone}"><span></span>${escapeHtml(severity)}</span>`;
  }

  function payrollReviewCounts(issues) {
    return issues.reduce((out, issue) => { out[issue.severity] = (out[issue.severity] || 0) + 1; return out; }, { Critical:0, Warning:0, Info:0 });
  }

  function payrollReviewHistory(run) {
    const history = Array.isArray(run.reviewHistory) ? run.reviewHistory : [];
    if (!history.length) return `<div class="review-history-empty"><strong>No reviewer decisions yet</strong><span>Calculation and review decisions will be recorded here for this period.</span></div>`;
    return `<div class="review-history">${[...history].reverse().map(item => `<div class="review-history__item"><span class="review-history__dot"></span><div><strong>${escapeHtml(item.action)}</strong><span>${escapeHtml(item.actor || 'Payroll user')} · ${escapeHtml(payrollTimestamp(item.at))}</span>${item.note ? `<p>${escapeHtml(item.note)}</p>` : ''}</div></div>`).join('')}</div>`;
  }

  function payrollReviewTemplate(run, allRows) {
    const review = payrollReviewIssues(allRows);
    const counts = payrollReviewCounts(review.issues);
    const filteredIssues = state.payrollReviewSeverity === 'All' ? review.issues : review.issues.filter(issue => issue.severity === state.payrollReviewSeverity);
    const critical = counts.Critical || 0;
    const comparison = review.comparison;
    const canApprove = run.status === 'Review' && critical === 0;
    const previousNet = comparison.previousTotals?.net ?? null;
    const currentNet = comparison.currentTotals.net;
    const netDelta = previousNet === null ? null : currentNet - previousNet;
    const netDeltaPct = previousNet ? netDelta / previousNet * 100 : null;
    const checklist = [
      { label:'Salary structures and payroll calculations', ok:!allRows.some(row => row.blockers?.length), meta:allRows.some(row => row.blockers?.length) ? `${allRows.filter(row => row.blockers?.length).length} blocked` : 'No calculation blockers' },
      { label:'Attendance & overtime snapshot', ok:payrollContextForPeriod().attendanceLocked, meta:payrollContextForPeriod().attendanceStatus || 'Not locked' },
      { label:'Critical review exceptions', ok:critical === 0, meta:critical ? `${critical} unresolved` : 'None' }
    ];

    return `
      <div class="review-layout">
        <div class="review-main-stack">
          <section class="data-panel review-status-panel">
            <div class="review-status-copy"><span class="review-status-icon">${run.status === 'Review' ? 'R' : 'V'}</span><div><strong>${run.status === 'Review' ? 'Submitted for finance review' : 'Pre-review validation'}</strong><p>${run.status === 'Review' ? `Submitted ${payrollTimestamp(run.submittedAt)}. Review exceptions and comparison before approving.` : 'Validate the saved payroll snapshot before submission. Critical items will block approval.'}</p></div></div>
            <div class="review-status-meta"><span>Snapshot</span><strong>${escapeHtml(run.snapshot?.timesheetStatus || timesheetStatus())}</strong></div>
          </section>

          <section class="data-panel review-exceptions-panel">
            <div class="panel__head panel__head--padded review-panel-head"><div><h2>Exception center</h2><p>Issues are generated from payroll inputs, attendance integrity, approved adjustments and period variance checks.</p></div><span class="review-total-count">${review.issues.length} issue${review.issues.length === 1 ? '' : 's'}</span></div>
            <div class="review-filterbar">
              ${['All','Critical','Warning','Info'].map(level => `<button class="review-filter ${state.payrollReviewSeverity === level ? 'is-active' : ''}" data-review-severity="${level}"><span>${level}</span><em>${level === 'All' ? review.issues.length : counts[level] || 0}</em></button>`).join('')}
            </div>
            <div class="review-issue-list">
              ${filteredIssues.length ? filteredIssues.map(issue => `<div class="review-issue review-issue--${issue.severity.toLowerCase()}">
                <div class="review-issue__mark">${issue.severity === 'Critical' ? '!' : issue.severity === 'Warning' ? '△' : 'i'}</div>
                <div class="review-issue__copy"><div>${payrollReviewSeverityBadge(issue.severity)}<span class="review-issue-type">${escapeHtml(issue.type)}</span></div><strong>${escapeHtml(issue.title)}</strong><p>${escapeHtml(issue.detail)}</p></div>
                <div class="review-issue__action">${issue.employeeId ? `<button class="btn btn--ghost btn--sm" data-review-open-row="${issue.employeeId}">${escapeHtml(issue.action || 'Review')}</button>` : issue.route ? `<button class="btn btn--ghost btn--sm" data-review-route="${escapeHtml(issue.route)}">${escapeHtml(issue.action || 'Open')}</button>` : issue.action && issue.action.startsWith('Open ') && comparison.previousPeriod ? `<button class="btn btn--ghost btn--sm" data-review-previous-period>${escapeHtml(issue.action)}</button>` : ''}</div>
              </div>`).join('') : `<div class="review-clear-state"><span>✓</span><strong>No ${state.payrollReviewSeverity === 'All' ? '' : state.payrollReviewSeverity.toLowerCase() + ' '}exceptions</strong><p>This filter has no unresolved items in the current payroll snapshot.</p></div>`}
            </div>
          </section>

          <section class="data-panel review-employee-panel">
            <div class="panel__head panel__head--padded"><div><h2>Employee review register</h2><p>Current payroll with previous-period variance when an earlier snapshot exists.</p></div>${comparison.available ? `<span class="comparison-source">vs ${escapeHtml(comparison.previousPeriod)}</span>` : `<span class="comparison-source comparison-source--muted">No prior snapshot</span>`}</div>
            <div class="table-scroll review-table-scroll"><table class="data-table review-table"><thead><tr><th>Employee</th><th>Branch / Office</th><th class="num">Current Net</th><th class="num">Previous Net</th><th class="num">Variance</th><th class="num">OT</th><th>Review</th><th></th></tr></thead><tbody>
              ${comparison.rows.map(row => {
                const rowIssues = review.issues.filter(issue => issue.employeeId === row.employeeId);
                const highest = rowIssues.some(issue => issue.severity === 'Critical') ? 'Critical' : rowIssues.some(issue => issue.severity === 'Warning') ? 'Warning' : 'Clear';
                const deltaText = row.delta === null ? '—' : `${row.delta >= 0 ? '+' : '−'} ${formatCurrency(Math.abs(row.delta))}`;
                const pctText = row.deltaPct === null ? '' : `${row.deltaPct >= 0 ? '+' : ''}${row.deltaPct.toFixed(1)}%`;
                return `<tr><td><button class="entity-link entity-link--stack" data-open-employee="${row.employeeId}"><strong>${escapeHtml(row.name)}</strong><span>EMP ${escapeHtml(row.employeeCode)} · ${escapeHtml(row.position)}</span></button></td><td>${row.branchId ? `<button class="entity-link" data-open-branch="${row.branchId}">${escapeHtml(row.branch)}</button>` : '—'}</td><td class="num table-money"><strong>${formatCurrency(row.net)}</strong></td><td class="num table-money">${row.previousNet === null ? '<span class="table-secondary">—</span>' : formatCurrency(row.previousNet)}</td><td class="num table-money"><span class="variance-value ${row.deltaPct !== null && Math.abs(row.deltaPct) >= 10 ? 'is-alert' : ''}">${deltaText}</span>${pctText ? `<small>${pctText}</small>` : ''}</td><td class="num table-money">${row.otHours ? `${row.otHours}h<small>${formatCurrency(row.overtime)}</small>` : '—'}</td><td>${highest === 'Critical' ? payrollReviewSeverityBadge('Critical') : highest === 'Warning' ? payrollReviewSeverityBadge('Warning') : `<span class="review-clear-badge">✓ Clear</span>`}</td><td><button class="icon-btn icon-btn--sm" data-review-open-row="${row.employeeId}" aria-label="Review employee calculation">${icon('chevron')}</button></td></tr>`;
              }).join('')}
            </tbody></table></div>
          </section>
        </div>

        <aside class="review-side-stack">
          <section class="data-panel review-comparison-card">
            <div class="panel__head panel__head--padded"><div><h2>Previous-period comparison</h2><p>${comparison.available ? `Snapshot: ${escapeHtml(comparison.previousPeriod)}` : `Expected baseline: ${escapeHtml(comparison.previousPeriod || 'previous period')}`}</p></div></div>
            ${comparison.available ? `<div class="review-comparison-metrics"><div><span>Previous net</span><strong>${formatCurrency(previousNet)}</strong></div><div><span>Current net</span><strong>${formatCurrency(currentNet)}</strong></div><div class="is-delta"><span>Change</span><strong>${netDelta >= 0 ? '+' : '−'} ${formatCurrency(Math.abs(netDelta))}</strong><small>${netDeltaPct === null ? '' : `${netDeltaPct >= 0 ? '+' : ''}${netDeltaPct.toFixed(1)}%`}</small></div></div>` : `<div class="review-comparison-empty"><span>${icon('calculator')}</span><strong>No prior payroll snapshot</strong><p>The system will compare automatically after ${escapeHtml(comparison.previousPeriod || 'the previous period')} has a calculated snapshot. No historical amount is fabricated.</p>${comparison.previousPeriod ? `<button class="btn btn--secondary btn--sm" data-review-previous-period>Open ${escapeHtml(comparison.previousPeriod)}</button>` : ''}</div>`}
          </section>

          <section class="data-panel review-checklist-card">
            <div class="panel__head panel__head--padded"><div><h2>Approval checklist</h2><p>Critical controls before final approval.</p></div></div>
            <div class="review-checklist">${checklist.map(item => `<div class="review-check ${item.ok ? 'is-ok' : item.soft ? 'is-soft' : 'is-fail'}"><span>${item.ok ? '✓' : item.soft ? '•' : '!'}</span><div><strong>${escapeHtml(item.label)}</strong><small>${escapeHtml(item.meta)}</small></div></div>`).join('')}</div>
            <div class="review-checklist-foot"><strong>${critical ? `${critical} critical issue${critical === 1 ? '' : 's'} block approval` : 'Critical approval controls are clear'}</strong><span>Bank/WPS readiness is handled after payroll approval in the payment lifecycle.</span></div>
          </section>

          <section class="data-panel review-history-card">
            <div class="panel__head panel__head--padded"><div><h2>Approval history</h2><p>Immutable audit trail for this payroll period.</p></div></div>
            ${payrollReviewHistory(run)}
          </section>

          ${run.reviewerNote ? `<section class="data-panel review-note-card"><div class="panel__head panel__head--padded"><div><h2>Latest reviewer note</h2></div></div><p>${escapeHtml(run.reviewerNote)}</p></section>` : ''}

          <section class="data-panel review-decision-card">
            <div class="panel__head panel__head--padded"><div><h2>Reviewer decision</h2><p>${run.status === 'Review' ? 'Decisions are recorded in the run audit trail.' : 'Submit the calculated run to Review before a final decision.'}</p></div></div>
            <div class="review-decision-actions"><button class="btn btn--secondary" data-review-return ${run.status === 'Review' ? '' : 'disabled'}>Return for Changes</button><button class="btn btn--primary" data-review-approve ${canApprove ? '' : 'disabled'}>Approve Payroll</button></div>
            ${critical ? `<span class="review-decision-help">Resolve all critical exceptions before approval.</span>` : run.status !== 'Review' ? `<span class="review-decision-help">Approval becomes available after submission to Review.</span>` : ''}
          </section>
        </aside>
      </div>`;
  }

  function payrollRunsTemplate() {
    if (!state.payrollLoadedPeriods.has(state.period)) {
      loadInternalPayrollPeriod(state.period);
      return `<section class="page payroll-run-page ui-v2-prs-internal-page ui-v2-prs-internal-execution-page"><div class="page-head"><div class="page-head__copy"><div class="eyebrow">Payroll · Internal Employees</div><h1>${escapeHtml(state.period)} Payroll</h1><p>Loading the company payroll period.</p></div></div><div class="table-empty table-empty--card"><strong>Loading payroll…</strong><span>Fetching the server-authoritative payroll inputs and saved snapshot.</span></div></section>`;
    }
    const context = payrollContextForPeriod();
    const run = payrollRunRecord();
    const allRows = payrollRowsForDisplay();
    const rows = payrollFilteredRows(allRows);
    const totals = payrollTotals(allRows);
    const branchOptions = ['All branches', ...Array.from(new Set(allRows.map(row => row.branch).filter(Boolean))).sort()];
    const departmentOptions = ['All departments', ...Array.from(new Set(allRows.map(row => row.department).filter(Boolean))).sort()];
    const tsStatus = context.attendanceStatus || 'Not created';
    const calculationInputReady = ['Approved','Locked'].includes(tsStatus);
    const inputReady = !!context.attendanceLocked;
    const canReview = run.status === 'Calculated' && totals.blocked === 0 && inputReady;
    const calculated = run.status !== 'Draft' && !!run.snapshot;
    const sourceErrors = Array.isArray(context.sourceErrors) ? context.sourceErrors : [];
    const policy = context.policy || { configured:false, prorationLabel:'Not configured' };
    const statusSub = run.status === 'Draft' ? 'Live input preview · not yet snapshotted' : `Snapshot calculated ${payrollTimestamp(run.calculatedAt)}`;
    if (run.status === 'Review' && state.payrollView !== 'review') state.payrollView = 'review';

    return `
      <section class="page payroll-run-page ui-v2-prs-internal-page ui-v2-prs-internal-execution-page">
        <div class="page-head payroll-run-head">
          <div class="page-head__copy">
            <div class="eyebrow">Payroll · Internal Employees</div>
            <div class="payroll-title-line"><h1>${escapeHtml(state.period)} Payroll</h1>${payrollRunStatusBadge(run.status)}</div>
            <p>Calculate internal employee payroll from effective salary structures, overtime and approved period adjustments. Rental manpower stays in its separate project settlement workflow.</p>
          </div>
          <div class="page-head__actions payroll-head-actions">
            <button class="btn btn--secondary" data-route-link="timesheets">Open Timesheets</button>
            <button class="btn btn--secondary" data-route-link="salary-setup">Salary Setup</button>
            ${run.status === 'Draft' ? `<button class="btn btn--primary" data-payroll-calculate>${icon('calculator')} Calculate Payroll</button>` : run.status === 'Calculated' ? `<button class="btn btn--secondary" data-payroll-calculate>Recalculate</button><button class="btn btn--primary" data-payroll-submit-review ${canReview ? '' : 'disabled'}>Submit for Review</button>` : run.status === 'Review' ? `<button class="btn btn--secondary" data-review-return>Return for Changes</button><button class="btn btn--primary" data-review-approve ${payrollReviewCounts(payrollReviewIssues(allRows).issues).Critical ? 'disabled' : ''}>Approve Payroll</button>` : run.status === 'Approved' ? `<button class="btn btn--secondary" data-payroll-view-review>View Approval</button><button class="btn btn--primary" data-route-link="bank-export">Continue to Bank / WPS</button>` : run.status === 'Paid' ? `<button class="btn btn--secondary" data-payroll-view-review>View Approval</button><button class="btn btn--primary" data-route-link="payments">View Payments</button>` : `<button class="btn btn--secondary" disabled>${escapeHtml(run.status)}</button>`}
          </div>
        </div>

        <div class="summary-strip payroll-summary-strip">
          <div class="summary-item"><span>Active employees</span><strong>${allRows.length}</strong><small>${statusSub}</small></div>
          <div class="summary-item"><span>Ready to calculate</span><strong>${totals.ready}</strong><small>${totals.blocked} blocked by setup</small></div>
          <div class="summary-item"><span>Gross payroll</span><strong>${formatCurrency(totals.gross)}</strong><small>${formatCurrency(totals.overtime)} overtime</small></div>
          <div class="summary-item"><span>Total deductions</span><strong>${formatCurrency(totals.advances + totals.deductions)}</strong><small>${formatCurrency(totals.advances)} advance recovery</small></div>
          <div class="summary-item summary-item--strong"><span>Net payable</span><strong>${formatCurrency(totals.net)}</strong><small>${calculated ? 'Saved run snapshot' : 'Current-input preview'}</small></div>
        </div>

        <section class="data-panel payroll-workflow-panel">
          <div class="panel__head panel__head--padded"><div><h2>Payroll lifecycle</h2><p>Calculation creates a period snapshot. Approval, payment and closing build on that immutable snapshot.</p></div>${payrollRunStatusBadge(run.status)}</div>
          ${payrollWorkflow(run.status)}
        </section>

        <div class="source-banner source-banner--compact payroll-source-banner">${icon('info')}<span><strong>Server-authoritative calculation:</strong> payroll is derived from the approved attendance period, effective salary structures, saved overtime snapshots and approved adjustments. Calculation is all-or-nothing; unresolved source issues never become zero-value payroll rows.</span></div>

        <div class="payroll-view-switch"><button class="${state.payrollView === 'register' ? 'is-active' : ''}" data-payroll-view="register"><span>Payroll Register</span><small>Calculation rows & inputs</small></button><button class="${state.payrollView === 'review' ? 'is-active' : ''}" data-payroll-view="review"><span>Review & Validation</span><small>Exceptions · variance · approval</small></button></div>

        ${state.payrollView === 'review' ? payrollReviewTemplate(run, allRows) : `<div class="payroll-run-layout">
          <section class="data-panel payroll-register">
            <div class="table-toolbar payroll-toolbar">
              <div class="table-toolbar__search">${icon('search')}<input id="payrollSearch" type="search" placeholder="Search employee, ID, position or branch" value="${escapeHtml(state.payrollSearch)}"></div>
              <label class="timesheet-filter"><span>Branch / Office</span><select id="payrollBranchFilter" class="ui-v2-select ui-v2-payroll-operational-select">${branchOptions.map(option => `<option ${state.payrollBranch === option ? 'selected' : ''}>${escapeHtml(option)}</option>`).join('')}</select></label>
              <label class="timesheet-filter"><span>Department</span><select id="payrollDepartmentFilter" class="ui-v2-select ui-v2-payroll-operational-select">${departmentOptions.map(option => `<option ${state.payrollDepartment === option ? 'selected' : ''}>${escapeHtml(option)}</option>`).join('')}</select></label>
              <label class="timesheet-filter"><span>Readiness</span><select id="payrollReadinessFilter" class="ui-v2-select ui-v2-payroll-operational-select"><option ${state.payrollReadiness === 'All' ? 'selected' : ''}>All</option><option ${state.payrollReadiness === 'Ready' ? 'selected' : ''}>Ready</option><option ${state.payrollReadiness === 'Blocked' ? 'selected' : ''}>Blocked</option></select></label>
              <button class="btn btn--ghost" data-payroll-reset-filter>Reset</button>
            </div>

            ${sourceErrors.length ? `<div class="payroll-blocker-banner"><span class="payroll-blocker-icon">!</span><span><strong>Payroll input requires attention</strong><small>${escapeHtml(sourceErrors.slice(0,3).join(' · '))}${sourceErrors.length>3?` · +${sourceErrors.length-3} more`:''}</small></span></div>` : ''}
            ${totals.blocked ? `<div class="payroll-blocker-banner"><span class="payroll-blocker-icon">!</span><span><strong>${totals.blocked} employee${totals.blocked === 1 ? '' : 's'} cannot be finalized yet</strong><small>Invalid salary inputs block calculation instead of being treated as zero salary.</small></span><button class="text-link" data-route-link="salary-setup">Fix salary setup →</button></div>` : ''}
            ${!calculationInputReady ? `<div class="payroll-input-warning"><span>${icon('timesheet')}</span><span><strong>Attendance & overtime is ${escapeHtml(tsStatus)}</strong><small>Payroll calculation requires an Approved or Locked attendance period.</small></span><button class="text-link" data-route-link="timesheets">Open Timesheets →</button></div>` : !inputReady ? `<div class="payroll-input-warning"><span>${icon('timesheet')}</span><span><strong>Attendance is Approved but not Locked</strong><small>Calculation is allowed, but Finance Review requires the attendance period to be Locked.</small></span><button class="text-link" data-route-link="timesheets">Lock Timesheet →</button></div>` : ''}

            <div class="table-meta"><span><strong>${rows.length}</strong> of ${allRows.length} employees</span><span>${run.status === 'Draft' ? 'Preview uses current inputs; Calculate Payroll creates the run snapshot.' : 'Amounts below are read from the saved calculation snapshot until Recalculate is used.'}</span></div>
            <div class="table-scroll payroll-table-scroll">
              <table class="data-table payroll-table">
                <thead><tr><th>Employee</th><th>Branch / Office</th><th class="num">Basic</th><th class="num">Allowances</th><th class="num">OT</th><th class="num">Other Earnings</th><th class="num">Gross</th><th class="num">Advances</th><th class="num">Deductions</th><th class="num">Net Payable</th><th>Readiness</th><th></th></tr></thead>
                <tbody>
                  ${rows.length ? rows.map(row => `<tr class="${row.blockers?.length ? 'payroll-row--blocked' : ''}">
                    <td><button class="entity-link entity-link--stack" data-open-employee="${row.employeeId}"><strong>${escapeHtml(row.name)}</strong><span>EMP ${escapeHtml(row.employeeCode)} · ${escapeHtml(row.position)}</span></button><button class="payroll-mobile-detail" type="button" data-payroll-row="${row.employeeId}">View calculation</button></td>
                    <td>${row.branchId ? `<button class="entity-link" data-open-branch="${row.branchId}">${escapeHtml(row.branch)}</button>` : `<span class="table-secondary">Branch not set</span>`}</td>
                    <td class="num table-money">${payrollMoney(row.basic, row.blockers?.length)}</td>
                    <td class="num table-money">${payrollMoney(row.allowances, row.blockers?.length)}</td>
                    <td class="num table-money"><span>${payrollMoney(row.overtime, row.blockers?.length)}</span>${row.otHours ? `<small>${row.otHours}h</small>` : ''}</td>
                    <td class="num table-money">${payrollMoney(row.otherEarnings, row.blockers?.length)}</td>
                    <td class="num table-money payroll-gross">${payrollMoney(row.gross, row.blockers?.length)}</td>
                    <td class="num table-money">${payrollMoney(row.advances, row.blockers?.length)}</td>
                    <td class="num table-money">${payrollMoney(row.deductions, row.blockers?.length)}</td>
                    <td class="num table-money payroll-net">${payrollMoney(row.net, row.blockers?.length)}</td>
                    <td>${payrollReadinessBadge(row)}</td>
                    <td><button class="icon-btn icon-btn--sm" data-payroll-row="${row.employeeId}" aria-label="Open calculation details">${icon('chevron')}</button></td>
                  </tr>`).join('') : `<tr><td colspan="12"><div class="table-empty"><strong>No payroll rows match these filters.</strong><span>Reset the filters or search for another employee.</span></div></td></tr>`}
                </tbody>
                ${rows.length ? `<tfoot><tr><td colspan="2"><strong>Visible rows</strong><small>${rows.length} employee${rows.length === 1 ? '' : 's'}</small></td><td class="num table-money">${formatCurrency(payrollTotals(rows).basic)}</td><td class="num table-money">${formatCurrency(payrollTotals(rows).allowances)}</td><td class="num table-money">${formatCurrency(payrollTotals(rows).overtime)}</td><td class="num table-money">${formatCurrency(payrollTotals(rows).otherEarnings)}</td><td class="num table-money"><strong>${formatCurrency(payrollTotals(rows).gross)}</strong></td><td class="num table-money">${formatCurrency(payrollTotals(rows).advances)}</td><td class="num table-money">${formatCurrency(payrollTotals(rows).deductions)}</td><td class="num table-money"><strong>${formatCurrency(payrollTotals(rows).net)}</strong></td><td colspan="2"></td></tr></tfoot>` : ''}
              </table>
            </div>
            <div class="payroll-table-footer"><span>Amounts are shown in ${escapeHtml(currencyCode())}. Blocked rows never silently become zero-pay employees.</span>${run.status === 'Calculated' ? `<button class="text-link" data-payroll-reset-run>Reset run to Draft</button>` : ''}</div>
          </section>

          <aside class="payroll-side-stack">
            <section class="data-panel payroll-control-panel">
              <div class="panel__head panel__head--padded"><div><h2>Input readiness</h2><p>What this run is currently connected to.</p></div></div>
              <div class="payroll-input-list">
                <button data-route-link="salary-setup"><span class="payroll-input-icon">S</span><div><strong>Salary structures</strong><small>${totals.ready} ready · ${totals.blocked} blocked</small></div><em>${totals.blocked ? 'Fix' : 'Ready'}</em></button>
                <button data-route-link="timesheets"><span class="payroll-input-icon">T</span><div><strong>Attendance & overtime</strong><small>${escapeHtml(tsStatus)}</small></div><em>${inputReady ? 'Locked' : calculationInputReady ? 'Approved' : 'Open'}</em></button>
                <button data-route-link="adjustments"><span class="payroll-input-icon">A</span><div><strong>Period adjustments</strong><small>${allRows.reduce((n,row)=>n+(row.pendingAdjustments?.length||0),0)} pending · approved items calculate automatically</small></div><em>Review</em></button>
              </div>
            </section>

            <section class="data-panel payroll-basis-panel">
              <div class="panel__head panel__head--padded"><div><h2>Calculation basis</h2><p>Transparent rather than hidden spreadsheet formulas.</p></div></div>
              <div class="payroll-formula-stack">
                <div><span>Gross earnings</span><strong>Basic + allowances + OT + other earnings</strong></div>
                <div><span>Total deductions</span><strong>Advance recovery + recurring + approved deductions</strong></div>
                <div class="is-total"><span>Net payable</span><strong>Gross earnings − total deductions</strong></div>
              </div>
              <div class="payroll-basis-foot"><span>Overtime</span><strong>Uses the OT policy snapshotted with each employee salary structure.</strong><button class="text-link" data-route-link="salary-setup">Review OT policies →</button></div>
              <div class="payroll-basis-foot"><span>Monthly proration</span><strong>${escapeHtml(policy.prorationLabel || 'Not configured')}</strong><button class="text-link" data-payroll-policy>Configure →</button></div>
            </section>

            <section class="data-panel payroll-run-meta">
              <div class="panel__head panel__head--padded"><div><h2>Run record</h2><p>Period-level processing state.</p></div></div>
              <dl>
                <div><dt>Period</dt><dd>${escapeHtml(state.period)}</dd></div>
                <div><dt>Status</dt><dd>${escapeHtml(run.status)}</dd></div>
                <div><dt>Calculated</dt><dd>${escapeHtml(payrollTimestamp(run.calculatedAt))}</dd></div>
                <div><dt>Input snapshot</dt><dd>${escapeHtml(run.snapshot?.timesheetStatus || tsStatus)}</dd></div>
              </dl>
            </section>
          </aside>
        </div>`}
      </section>`;
  }

  function openPayrollDetailDrawer(employeeId) {
    const row = payrollRowsForDisplay().find(item => item.employeeId === employeeId) || livePayrollRows().find(item => item.employeeId === employeeId);
    if (!row) return;
    state.drawerType = 'payroll-detail';
    state.drawerContext = employeeId;
    drawerTitle.textContent = `${row.name} · Payroll calculation`;
    drawerSave.hidden = true;
    const components = row.salaryComponents || [];
    const earningComponents = components.filter(item => item.type === 'earning');
    const deductionComponents = components.filter(item => item.type === 'deduction');
    drawerBody.innerHTML = `
      <section class="payroll-detail-hero">
        <div><span>EMP ${escapeHtml(row.employeeCode)}</span><strong>${escapeHtml(row.name)}</strong><small>${escapeHtml(row.position)} · ${escapeHtml(row.branch || 'Branch not set')}</small></div>
        ${payrollReadinessBadge(row)}
      </section>
      ${row.blockers?.length ? `<section class="payroll-detail-alert payroll-detail-alert--danger"><strong>Calculation blocked</strong>${row.blockers.map(issue => `<span>• ${escapeHtml(issue)}</span>`).join('')}</section>` : ''}
      ${row.warnings?.length ? `<section class="payroll-detail-alert"><strong>Attention</strong>${row.warnings.map(issue => `<span>• ${escapeHtml(issue)}</span>`).join('')}</section>` : ''}
      <section class="form-section"><div class="form-section__head"><strong>Effective salary snapshot</strong><span>Stored calculation basis</span></div>
        <div class="payroll-detail-lines">
          ${earningComponents.length ? earningComponents.map(item => `<div><span>${escapeHtml(item.name)}</span><strong>${formatCurrency(item.amount)}</strong></div>`).join('') : '<div><span>Recurring earnings</span><strong>Not configured</strong></div>'}
          ${deductionComponents.map(item => `<div class="is-deduction"><span>${escapeHtml(item.name)}</span><strong>− ${formatCurrency(item.amount)}</strong></div>`).join('')}
        </div>
      </section>
      <section class="form-section"><div class="form-section__head"><strong>Period variables</strong><span>${escapeHtml(state.period)}</span></div>
        <div class="payroll-detail-lines">
          <div><span>Overtime</span><strong>${row.otHours ? `${row.otHours}h · ${formatCurrency(row.overtime)}` : formatCurrency(0)}</strong></div>
          <div><span>OT policy</span><strong>${escapeHtml(row.otPolicy)}</strong></div>
          <div><span>Other earnings</span><strong>${formatCurrency(row.otherEarnings)}</strong></div>
          <div class="is-deduction"><span>Advance recovery</span><strong>− ${formatCurrency(row.advances)}</strong></div>
          <div class="is-deduction"><span>Other deductions</span><strong>− ${formatCurrency(row.deductions)}</strong></div>
        </div>
        ${row.pendingAdjustments?.length ? `<div class="payroll-pending-note"><strong>Pending adjustments are excluded</strong><span>${row.pendingAdjustments.map(item => `${escapeHtml(item.type)} · ${formatCurrency(Math.abs(item.amount))} · ${escapeHtml(item.status)}`).join('<br>')}</span></div>` : ''}
      </section>
      <section class="payroll-detail-total">
        <div><span>Gross earnings</span><strong>${formatCurrency(row.gross)}</strong></div>
        <div><span>Total deductions</span><strong>− ${formatCurrency(row.advances + row.deductions)}</strong></div>
        <div class="is-net"><span>Net payable</span><strong>${formatCurrency(row.net)}</strong></div>
      </section>
      <section class="payroll-detail-actions"><button class="btn btn--secondary" data-payroll-open-employee>Open Employee Profile</button><button class="btn btn--secondary" data-route-link="salary-setup">Salary Setup</button></section>`;
    drawer.classList.add('is-open');
    drawerScrim.classList.add('is-open');
    drawer.setAttribute('aria-hidden', 'false');
    drawerBody.querySelector('[data-payroll-open-employee]')?.addEventListener('click', () => { closeDrawer(); navigate(`internal-employees/${employeeId}`); });
    drawerBody.querySelectorAll('[data-route-link]').forEach(btn => btn.addEventListener('click', () => { const route = btn.dataset.routeLink; closeDrawer(); navigate(route); }));
  }

  function maskAccount(value) {
    const text = String(value || '');
    return text || '—';
  }

  function paymentPeriodKey(period = state.period) {
    return periodKeyFromLabel(period);
  }

  function paymentContextForPeriod(period = state.period) {
    const key = paymentPeriodKey(period);
    return state.paymentContexts[key] || (state.paymentContext?.period === key ? state.paymentContext : {
      period:key, payrollStatus:null, payrollStatusLabel:'Not calculated', profiles:{}, templates:[], batches:[],
      bankReadiness:{ready:false,companyBlockers:['Salary payment data has not been loaded.'],readyCount:0,blockedCount:0,employees:[]},
      wpsReadiness:{ready:false,companyBlockers:['Salary payment data has not been loaded.'],readyCount:0,blockedCount:0,employees:[]},
      settings:{}, canEditSetup:false, canPay:false
    });
  }

  function syncEmployeePaymentProfiles(context = paymentContextForPeriod()) {
    const profiles = context.profiles || {};
    const wpsRows = new Map((context.wpsReadiness?.employees || []).map(row => [row.employeeId, row]));
    state.employees.forEach(employee => {
      const profile = profiles[employee.id] || null;
      employee.paymentProfile = profile;
      employee.bank = profile?.bankName || '';
      employee.account = profile?.destinationMasked || '';
      employee.paymentMethod = profile?.destinationLabel || '';
      const readiness = wpsRows.get(employee.id);
      employee.wps = readiness ? readiness.status : (profile?.active && profile?.wpsEnabled ? 'Pending' : 'Not configured');
    });
  }

  function applyPaymentPayload(payload) {
    if (!payload?.period) return;
    state.paymentContext = payload;
    state.paymentContexts[payload.period] = payload;
    state.paymentLoadedPeriods.add(payload.period);
    state.bankTemplates = [...(payload.templates || [])];
    state.paymentBatches = [...(payload.batches || [])];
    state.bankBatches = state.paymentBatches.filter(item => item.channelValue === 'bank_csv');
    state.wpsBatches = state.paymentBatches.filter(item => item.channelValue === 'wps');
    const bankTemplates = state.bankTemplates.filter(item => item.channel === 'bank_csv' && item.active && !item.archived);
    if (!bankTemplates.some(item => item.id === state.bankTemplateId)) state.bankTemplateId = bankTemplates[0]?.id || null;
    const wpsTemplates = state.bankTemplates.filter(item => item.channel === 'wps' && item.active && !item.archived);
    if (!wpsTemplates.some(item => item.id === state.wpsTemplateId)) state.wpsTemplateId = wpsTemplates[0]?.id || null;
    syncEmployeePaymentProfiles(payload);
  }

  async function loadSalaryPayments(period = state.period, { force = false } = {}) {
    const key = paymentPeriodKey(period);
    if (!force && state.paymentLoadedPeriods.has(key)) return paymentContextForPeriod(period);
    if (state.paymentLoadingPeriod === key) return null;
    state.paymentLoadingPeriod = key;
    try {
      const params=new URLSearchParams({period:key}); if(state.bankTemplateId)params.set('bank_template_id',state.bankTemplateId); if(state.wpsTemplateId)params.set('wps_template_id',state.wpsTemplateId); const payload = await appApi(`/api/internal/salary-payments/?${params.toString()}`);
      applyPaymentPayload(payload);
      if (state.period === period) renderRoute();
      return payload;
    } catch (error) {
      showToast('Salary payment data unavailable', error.message);
      return null;
    } finally {
      state.paymentLoadingPeriod = null;
    }
  }

  function paymentReadinessRows(channel) {
    const context = paymentContextForPeriod();
    const readiness = channel === 'wps' ? context.wpsReadiness : context.bankReadiness;
    return (readiness?.employees || []).map(row => {
      const employee = state.employees.find(item => item.id === row.employeeId) || {};
      const blockers = Array.isArray(row.blockers) ? row.blockers : [];
      return {
        ...row,
        employee,
        branchId: employee.branchId || null,
        nationalId: employee.nationalId || '',
        address: employee.address || '',
        totalSalary: Number(row.netSalary || 0),
        basicSalary: Number(row.basicSalary || 0),
        housingAllowance: Number(row.housingAllowance || 0),
        otherEarnings: Number(row.otherEarnings || 0),
        deductions: Number(row.deductions || 0),
        account: row.account || '',
        wpsBlockers: blockers,
        wpsWarnings: [],
        wpsStatus: blockers.length ? 'Blocked' : 'Ready',
        bankStatus: blockers.length ? 'Blocked' : 'Ready',
        bankBlockers: blockers,
        reference: `SAL-${paymentPeriodKey()}-${row.employeeCode}`,
      };
    });
  }

  function wpsValidationRows() {
    const q = state.wpsSearch.trim().toLowerCase();
    return paymentReadinessRows('wps').filter(row => {
      const statusMatch = state.wpsStatusFilter === 'All' || row.wpsStatus === state.wpsStatusFilter;
      const text = `${row.employeeCode} ${row.name} ${row.position} ${row.bank} ${row.account} ${row.nationalId}`.toLowerCase();
      return statusMatch && (!q || text.includes(q));
    });
  }

  function wpsAllRows() { return paymentReadinessRows('wps'); }
  function wpsSummary(rows = wpsAllRows()) {
    return rows.reduce((out,row) => {
      out.total += 1; out.amount += Number(row.totalSalary || 0);
      if (row.wpsStatus === 'Ready') { out.ready += 1; out.readyAmount += Number(row.totalSalary || 0); }
      else out.blocked += 1;
      return out;
    }, { total:0, ready:0, warning:0, blocked:0, amount:0, readyAmount:0 });
  }
  function wpsStatusBadge(status) {
    return status === 'Ready' ? '<span class="readiness readiness--ready"><span></span>Ready</span>' : '<span class="readiness readiness--danger"><span></span>Blocked</span>';
  }
  function wpsBatchStatusBadge(status) {
    const tone = status === 'Paid' || status === 'Closed' ? 'success' : status === 'Needs Attention' || status === 'Failed' || status === 'Reversed' ? 'danger' : ['Prepared','Exported','Processing','Partially Paid'].includes(status) ? 'warning' : 'neutral';
    return `<span class="status status--${tone}"><span></span>${escapeHtml(status || 'Prepared')}</span>`;
  }
  function bankBatchStatusBadge(status) { return wpsBatchStatusBadge(status); }

  function wpsBatchesForPeriod(period = state.period) { return state.wpsBatches.filter(batch => batch.period === period); }
  function paymentBatchesForPeriod(period = state.period) { return state.paymentBatches.filter(batch => batch.period === period); }
  function wpsLatestBatch(period = state.period) { return [...wpsBatchesForPeriod(period)].sort((a,b) => String(b.createdAt || '').localeCompare(String(a.createdAt || '')))[0] || null; }
  function bankBatchesForPeriod(period = state.period) { return state.bankBatches.filter(batch => batch.period === period); }
  function latestBankBatch(period = state.period) { return [...bankBatchesForPeriod(period)].sort((a,b) => String(b.createdAt || '').localeCompare(String(a.createdAt || '')))[0] || null; }

  const bankColumnCatalog = {
    employee_number:'Employee ID', employee_name:'Employee name', national_id:'National ID / Iqama', employee_address:'Employee address', bank_name:'Bank name', bank_code:'Bank code',
    iban:'IBAN', salary_card_number:'Salary card number', account_holder_name:'Account holder', basic_salary:'Basic salary', housing_allowance:'Housing allowance',
    other_earnings:'Other earnings', deductions:'Deductions', net_salary:'Net salary', transaction_reference:'Transaction reference', period_start:'Period start',
    period_end:'Period end', employer_identifier:'Employer identifier', employer_bank_name:'Employer bank name', employer_bank_code:'Employer bank code', employer_iban:'Employer IBAN', bank_customer_reference:'Bank customer reference'
  };

  function bankTemplatesAll(channel = null) {
    return (state.bankTemplates || []).filter(item => !channel || item.channel === channel);
  }
  function bankTemplateById(id = state.bankTemplateId) {
    return bankTemplatesAll().find(item => item.id === id) || null;
  }
  function activePaymentTemplate(channel) {
    const preferred = channel === 'bank_csv' ? bankTemplateById() : bankTemplatesAll('wps').find(item => item.id === state.wpsTemplateId);
    return preferred?.active && !preferred.archived && preferred.channel === channel ? preferred : bankTemplatesAll(channel).find(item => item.active && !item.archived) || null;
  }

  function bankPaymentRows({ all = false } = {}) {
    const q = state.bankExportSearch.trim().toLowerCase();
    return paymentReadinessRows('bank_csv').filter(row => {
      if (all) return true;
      const statusMatch = state.bankExportStatus === 'All' || row.bankStatus === state.bankExportStatus;
      const branchMatch = state.bankExportBranch === 'All branches' || row.branchId === state.bankExportBranch;
      const text = `${row.employeeCode} ${row.name} ${row.branch} ${row.department} ${row.bank} ${row.account} ${row.reference}`.toLowerCase();
      return statusMatch && branchMatch && (!q || text.includes(q));
    });
  }

  async function preparePaymentChannel(channel) {
    const template = activePaymentTemplate(channel);
    if (!template) {
      state.bankExportView = 'templates';
      renderRoute();
      showToast('Export template required', `Create and activate a ${channel === 'wps' ? 'WPS' : 'bank'} export template before preparing a salary payment batch.`);
      return;
    }
    try {
      const payload = await appApi('/api/internal/salary-payments/batches/', {
        method:'POST', body:{ period:paymentPeriodKey(), channel, template_id:template.id }
      });
      state.selectedInternalPaymentBatchId = payload.batchId || state.selectedInternalPaymentBatchId;
      if (state.selectedInternalPaymentBatchId) localStorage.setItem('payroll-ui-selected-internal-payment-batch', state.selectedInternalPaymentBatchId);
      await loadSalaryPayments(state.period, { force:true });
      const batch = state.paymentBatches.find(item => item.id === state.selectedInternalPaymentBatchId);
      renderRoute();
      showToast('Salary payment batch prepared', batch ? `${batch.reference} · ${batch.employeeCount} employees · ${formatCurrency(Number(batch.total || 0))}.` : 'The salary payment batch is ready.');
    } catch (error) { showToast('Batch preparation blocked', error.message); }
  }

  async function exportPaymentBatch(batchId) {
    try {
      const response = await fetch(`/api/internal/salary-payments/batches/${encodeURIComponent(batchId)}/export/`, {
        method:'POST', credentials:'same-origin', headers:{'Accept':'text/csv,application/json','Content-Type':'application/json','X-CSRFToken':csrfToken}, body:'{}'
      });
      if (!response.ok) {
        let payload = {}; try { payload = await response.json(); } catch {}
        const first = Object.values(payload.errors || {}).flat().find(Boolean);
        throw new Error(first || `Export failed (${response.status}).`);
      }
      const blob = await response.blob();
      const disposition = response.headers.get('Content-Disposition') || '';
      const filename = (disposition.match(/filename="?([^";]+)"?/i) || [])[1] || 'salary-payment-export.csv';
      const url = URL.createObjectURL(blob); const anchor = document.createElement('a'); anchor.href=url; anchor.download=filename; document.body.appendChild(anchor); anchor.click(); anchor.remove(); setTimeout(()=>URL.revokeObjectURL(url),800);
      await loadSalaryPayments(state.period, { force:true });
      showToast('Salary file exported', `${filename} was generated from the immutable payment batch snapshot.`);
    } catch (error) { showToast('Export blocked', error.message); }
  }

  async function runPaymentBatchWorkflow(batchId, action, extra = {}) {
    try {
      await appApi(`/api/internal/salary-payments/batches/${encodeURIComponent(batchId)}/workflow/`, {method:'POST', body:{action,...extra}});
      await loadSalaryPayments(state.period, { force:true });
      renderRoute();
      return true;
    } catch (error) { showToast('Payment action blocked', error.message); return false; }
  }

  async function importPaymentResults(batchId, file) {
    try {
      const content = await file.text();
      const payload = await appApi(`/api/internal/salary-payments/batches/${encodeURIComponent(batchId)}/results/`, {method:'POST', body:{file_name:file.name,content}});
      await loadSalaryPayments(state.period, { force:true });
      renderRoute();
      const errors = payload.errors || [];
      showToast('Bank results imported', `${payload.import.updatedRows} row${payload.import.updatedRows === 1 ? '' : 's'} updated${errors.length ? ` · ${errors.length} issue${errors.length === 1 ? '' : 's'}` : ''}.`);
    } catch (error) { showToast('Result import rejected', error.message); }
  }

  function paymentSetupAction() {
    return `<button class="btn btn--secondary" data-payment-settings>Edit Payment Settings</button>`;
  }

  function wpsWorkflowGate() {
    const context = paymentContextForPeriod(); const rows = wpsAllRows(); const summary = wpsSummary(rows);
    return { rows, summary, payrollApproved: context.payrollStatus === 'approved', canPrepare: !!context.wpsReadiness?.ready && context.payrollStatus === 'approved', allPayrollEmployeesReady: summary.blocked === 0 && !(context.wpsReadiness?.companyBlockers || []).length };
  }

  function wpsValidationTemplate() {
    const context = paymentContextForPeriod(); const rows = wpsValidationRows(); const allRows = wpsAllRows(); const summary = wpsSummary(allRows); const readiness = context.wpsReadiness || {};
    const blockers = readiness.companyBlockers || [];
    return `<div class="wps-summary-strip"><div><span>Payroll status</span><strong>${escapeHtml(context.payrollStatusLabel || 'Not calculated')}</strong><small>Approved payroll required</small></div><div><span>WPS ready</span><strong>${summary.ready} / ${summary.total}</strong><small>Employee payment profiles</small></div><div><span>Ready amount</span><strong>${formatCurrency(summary.readyAmount)}</strong><small>Approved net salaries</small></div><div class="${summary.blocked || blockers.length ? 'is-alert' : ''}"><span>Blocked</span><strong>${summary.blocked + blockers.length}</strong><small>${blockers.length ? 'Company setup required' : summary.blocked ? 'Employee setup required' : 'No blockers'}</small></div></div>
      ${blockers.length ? `<section class="source-note">${icon('info')}<span><strong>WPS company setup</strong>${escapeHtml(blockers.join(' · '))}</span></section>` : ''}
      <section class="panel panel--flush"><div class="panel__head panel__head--padded"><div><h2>WPS validation register</h2><p>Server validation against the approved payroll snapshot, WPS component mapping and employee payment profiles.</p></div><div class="payment-head-actions">${paymentSetupAction()}<button class="btn btn--primary" data-wps-prepare ${!wpsWorkflowGate().canPrepare ? 'disabled' : ''}>Prepare WPS Batch</button></div></div><div class="toolbar toolbar--table"><div class="search-field">${icon('search')}<input id="wpsSearch" type="search" value="${escapeHtml(state.wpsSearch)}" placeholder="Search employee, bank, account or ID…"></div>${bankTemplatesAll('wps').filter(item=>item.active && !item.archived).length>1?`<select class="select" id="wpsTemplateSelect">${bankTemplatesAll('wps').filter(item=>item.active && !item.archived).map(item=>`<option value="${escapeHtml(item.id)}" ${item.id===state.wpsTemplateId?'selected':''}>${escapeHtml(item.name)}</option>`).join('')}</select>`:''}<div class="segmented compact-segmented">${['All','Ready','Blocked'].map(status=>`<button type="button" class="${state.wpsStatusFilter===status?'is-active':''}" data-wps-status="${status}">${status}</button>`).join('')}</div><button class="btn btn--ghost" data-wps-reset>Reset</button></div><div class="table-wrap"><table class="data-table wps-table"><thead><tr><th>Employee</th><th>Bank / Account</th><th>National ID / Iqama</th><th class="num">Basic</th><th class="num">Housing</th><th class="num">Other Earnings</th><th class="num">Deductions</th><th class="num">Net Salary</th><th>Validation</th><th></th></tr></thead><tbody>${rows.length ? rows.map(row=>`<tr><td><button class="entity-link entity-link--stack" data-open-employee="${escapeHtml(row.employeeId)}"><strong>${escapeHtml(row.name)}</strong><span>EMP ${escapeHtml(row.employeeCode)} · ${escapeHtml(row.position || '—')}</span></button></td><td><div class="bank-cell"><strong>${escapeHtml(row.bank || 'Not configured')}</strong><span>${escapeHtml(row.account || '—')}</span></div></td><td><span class="mono-cell">${escapeHtml(row.nationalId || '—')}</span></td><td class="num">${formatCurrency(row.basicSalary)}</td><td class="num">${formatCurrency(row.housingAllowance)}</td><td class="num">${formatCurrency(row.otherEarnings)}</td><td class="num">${formatCurrency(row.deductions)}</td><td class="num table-money"><strong>${formatCurrency(row.totalSalary)}</strong></td><td>${wpsStatusBadge(row.wpsStatus)}${row.wpsBlockers.length?`<small class="validation-issue-count">${row.wpsBlockers.length} issue${row.wpsBlockers.length===1?'':'s'}</small>`:''}</td><td><button class="icon-btn icon-btn--sm" data-wps-inspect="${escapeHtml(row.employeeId)}">${icon('chevron')}</button></td></tr>`).join('') : `<tr><td colspan="10"><div class="table-empty"><strong>No WPS rows match this view.</strong><span>Complete payroll and employee payment setup or reset filters.</span></div></td></tr>`}</tbody></table></div></section>`;
  }

  function wpsBatchesTemplate() {
    const batches = wpsBatchesForPeriod();
    return `<section class="panel panel--flush"><div class="panel__head panel__head--padded"><div><h2>WPS batches & export history</h2><p>Every batch is an immutable snapshot of an approved payroll and its payment destinations.</p></div><button class="btn btn--primary" data-wps-prepare ${!wpsWorkflowGate().canPrepare?'disabled':''}>Prepare Batch</button></div><div class="table-wrap"><table class="data-table"><thead><tr><th>Batch</th><th>Period</th><th>Prepared</th><th>Employees</th><th class="num">Amount</th><th>Status</th><th></th></tr></thead><tbody>${batches.length ? batches.map(batch=>`<tr><td><button class="entity-link" data-wps-batch-open="${escapeHtml(batch.id)}">${escapeHtml(batch.reference)}</button></td><td>${escapeHtml(batch.period)}</td><td>${escapeHtml(payrollTimestamp(batch.createdAt))}</td><td>${batch.employeeCount}</td><td class="num table-money"><strong>${formatCurrency(Number(batch.total||0))}</strong></td><td>${wpsBatchStatusBadge(batch.status)}</td><td><button class="icon-btn icon-btn--sm" data-wps-batch-open="${escapeHtml(batch.id)}">${icon('chevron')}</button></td></tr>`).join('') : `<tr><td colspan="7"><div class="table-empty"><strong>No WPS batches for ${escapeHtml(state.period)}.</strong><span>Configure an active WPS template and resolve all readiness blockers first.</span></div></td></tr>`}</tbody></table></div></section>`;
  }

  function wpsTemplate() {
    const key = paymentPeriodKey(); if (!state.paymentLoadedPeriods.has(key)) { loadSalaryPayments(state.period); return `<section class="page"><div class="table-empty table-empty--card"><strong>Loading WPS…</strong><span>Fetching server-authoritative salary payment readiness.</span></div></section>`; }
    return `<section class="page wps-page ui-v2-prs-internal-page ui-v2-prs-internal-execution-page"><div class="page-head"><div class="page-head__copy"><span class="eyebrow">Internal Payroll · ${escapeHtml(state.period)}</span><h1>WPS Salary Payments</h1><p>Validate WPS data, create immutable batches and reconcile payment results without changing the approved payroll.</p></div><div class="page-head__actions"><button class="btn btn--secondary" data-route-link="payroll-runs">Open Payroll</button>${paymentSetupAction()}</div></div><nav class="profile-tabs wps-tabs"><button class="${state.wpsTab==='validation'?'is-active':''}" data-wps-tab="validation">Validation Register</button><button class="${state.wpsTab==='batches'?'is-active':''}" data-wps-tab="batches">Batches & Export${wpsBatchesForPeriod().length?`<span class="tab-count">${wpsBatchesForPeriod().length}</span>`:''}</button></nav>${state.wpsTab==='batches'?wpsBatchesTemplate():wpsValidationTemplate()}</section>`;
  }

  function bankExportRegisterTemplate() {
    const context = paymentContextForPeriod(); const readiness = context.bankReadiness || {}; const rows = bankPaymentRows(); const allRows = bankPaymentRows({all:true}); const ready = allRows.filter(row=>row.bankStatus==='Ready'); const blockers = readiness.companyBlockers || []; const template=activePaymentTemplate('bank_csv');
    return `<div class="bank-export-subhead"><div><span class="eyebrow">Bank salary file</span><h2>Salary Transfer Register</h2><p>Validate payment profiles and generate only the configured bank layout from an approved payroll snapshot.</p></div><div class="bank-template-picker"><label>Export template</label><select class="select" id="bankTemplateSelect" ${!bankTemplatesAll('bank_csv').some(item=>item.active && !item.archived)?'disabled':''}>${bankTemplatesAll('bank_csv').filter(item=>item.active && !item.archived).map(item=>`<option value="${escapeHtml(item.id)}" ${item.id===state.bankTemplateId?'selected':''}>${escapeHtml(item.name)}${item.active?'':' · inactive'}</option>`).join('') || '<option>No bank template configured</option>'}</select></div></div>${blockers.length?`<section class="source-note">${icon('info')}<span><strong>Payment setup</strong>${escapeHtml(blockers.join(' · '))}</span></section>`:''}<section class="data-panel"><div class="panel__head panel__head--padded"><div><h2>Bank-payment validation</h2><p>${template?`Using ${escapeHtml(template.name)}.`:'Create an export template before preparing a payment batch.'}</p></div><div class="payment-head-actions">${paymentSetupAction()}<button class="btn btn--primary" data-bank-batch-prepare ${!(context.payrollStatus==='approved' && readiness.ready && template)?'disabled':''}>Prepare Payment Batch</button></div></div><div class="table-toolbar bank-transfer-toolbar"><div class="table-toolbar__search">${icon('search')}<input id="bankExportSearch" type="search" value="${escapeHtml(state.bankExportSearch)}" placeholder="Search employee, branch, bank or account"></div><select class="select" id="bankExportBranch"><option value="All branches">All branches</option>${state.branches.filter(item=>item.status==='Active').map(item=>`<option value="${escapeHtml(item.id)}" ${state.bankExportBranch===item.id?'selected':''}>${escapeHtml(item.name)}</option>`).join('')}</select><div class="segmented segmented--compact">${['All','Ready','Blocked'].map(status=>`<button data-bank-export-status="${status}" class="${state.bankExportStatus===status?'is-active':''}">${status}</button>`).join('')}</div></div><div class="table-scroll"><table class="data-table bank-payment-register"><thead><tr><th>Employee</th><th>Branch / Department</th><th>Bank / Account</th><th class="num">Net Salary</th><th>Status</th><th></th></tr></thead><tbody>${rows.length?rows.map(row=>`<tr><td><button class="entity-link entity-link--stack" data-open-employee="${escapeHtml(row.employeeId)}"><strong>${escapeHtml(row.name)}</strong><span>EMP ${escapeHtml(row.employeeCode)} · ${escapeHtml(row.position||'—')}</span></button></td><td>${escapeHtml(row.branch||'—')}<small class="table-secondary">${escapeHtml(row.department||'—')}</small></td><td><div class="bank-cell"><strong>${escapeHtml(row.bank||'Not configured')}</strong><span>${escapeHtml(row.account||'—')}</span></div></td><td class="num table-money"><strong>${formatCurrency(row.totalSalary)}</strong></td><td>${wpsStatusBadge(row.bankStatus)}${row.bankBlockers.length?`<small class="validation-issue-count">${row.bankBlockers.length} issue${row.bankBlockers.length===1?'':'s'}</small>`:''}</td><td><button class="icon-btn icon-btn--sm" data-bank-inspect="${escapeHtml(row.employeeId)}">${icon('chevron')}</button></td></tr>`).join(''):`<tr><td colspan="6"><div class="table-empty"><strong>No salary rows match this view.</strong><span>Reset filters or complete employee payment profiles.</span></div></td></tr>`}</tbody></table></div><div class="table-meta"><span><strong>${ready.length}</strong> ready · ${allRows.length-ready.length} blocked</span><span>Batch creation is all-or-nothing for the approved payroll.</span></div></section>`;
  }

  function bankTemplatesTemplate() {
    const templates=bankTemplatesAll(); const selected=templates.find(item=>item.id===state.exportTemplateDetailId) || bankTemplateById() || templates[0] || null;
    if(selected && !state.exportTemplateDetailId) state.exportTemplateDetailId=selected.id;
    return `<section class="panel panel--flush"><div class="panel__head panel__head--padded"><div><h2>Salary export templates</h2><p>Company-owned bank/WPS file layouts. Archived templates remain visible for payment history but cannot be used for new batches.</p></div><button class="btn btn--primary" data-bank-template-new>${icon('plus')} New Template</button></div>${templates.length?`<div class="bank-template-layout"><div class="bank-template-list">${templates.map(item=>`<button class="bank-template-card ${item.id===selected?.id?'is-active':''}" data-bank-template-pick="${escapeHtml(item.id)}"><span class="bank-template-card__icon">${item.channel==='wps'?'WPS':'CSV'}</span><span><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml(item.code)} · ${escapeHtml(item.channelLabel)}</small><em>${item.columns.length} columns · ${escapeHtml(item.status || (item.active?'Active':'Inactive'))}</em></span></button>`).join('')}</div>${selected?`<aside class="detail-card bank-template-detail"><div class="detail-card__head"><h3>${escapeHtml(selected.name)}</h3>${selected.archived?'':`<button class="text-link" data-bank-template-edit>Edit</button>`}</div><p>${escapeHtml(selected.channelLabel)} · ${escapeHtml(selected.code)} · ${escapeHtml(selected.status || '')}</p>${selected.archivedReason?`<div class="source-note"><span><strong>Archive reason</strong>${escapeHtml(selected.archivedReason)}</span></div>`:''}<div class="mapping-flow">${selected.columns.map((key,index)=>`<div><span>${index+1}</span><strong>${escapeHtml((selected.headers||[])[index]||bankColumnCatalog[key]||key)}</strong><small>${escapeHtml(key)}</small></div>`).join('')}</div><div class="bank-template-detail__actions">${!selected.archived?`<button class="btn btn--secondary" data-bank-template-use ${selected.active?'':'disabled'}>Use for Export</button>`:''}<button class="btn btn--ghost" data-bank-template-preview>Preview Header</button>${lifecycleActionsMenu([
          ...(!selected.archived ? [{label:'Edit export template',hint:'Change the future bank/WPS file layout',iconName:'edit',attrs:'data-bank-template-edit'}] : []),
          'separator',
          {label:selected.archived?'Restore template':'Archive template',hint:selected.archived?'Restore as Inactive':'Keep payment history and stop new batch use',iconName:'info',attrs:`data-config-lifecycle="template|${selected.id}|${selected.archived?'restore':'archive'}"`},
          {label:'Delete unused template',hint:'Only before payment batches reference it',iconName:'more',danger:true,attrs:`data-config-lifecycle="template|${selected.id}|delete"`}
        ])}</div></aside>`:''}</div>`:`<div class="table-empty table-empty--card"><strong>No salary export template configured.</strong><span>Create the exact layout required by the company bank or WPS submission channel.</span></div>`}</section>`;
  }

  function bankBatchesTemplate() {
    const batches=bankBatchesForPeriod();
    return `<section class="panel panel--flush"><div class="panel__head panel__head--padded"><div><h2>Bank payment batches</h2><p>Immutable approved-payroll snapshots and export history.</p></div><button class="btn btn--primary" data-bank-batch-prepare>Prepare Batch</button></div><div class="table-wrap"><table class="data-table"><thead><tr><th>Batch</th><th>Template</th><th>Prepared</th><th>Employees</th><th class="num">Amount</th><th>Status</th><th></th></tr></thead><tbody>${batches.length?batches.map(batch=>`<tr><td><button class="entity-link" data-bank-batch-open="${escapeHtml(batch.id)}">${escapeHtml(batch.reference)}</button></td><td>${escapeHtml(batch.templateName)}</td><td>${escapeHtml(payrollTimestamp(batch.createdAt))}</td><td>${batch.employeeCount}</td><td class="num table-money"><strong>${formatCurrency(Number(batch.total||0))}</strong></td><td>${bankBatchStatusBadge(batch.status)}</td><td><button class="icon-btn icon-btn--sm" data-bank-batch-open="${escapeHtml(batch.id)}">${icon('chevron')}</button></td></tr>`).join(''):`<tr><td colspan="7"><div class="table-empty"><strong>No bank payment batches for ${escapeHtml(state.period)}.</strong><span>Prepare one from an approved payroll after configuring employee payment profiles and an export template.</span></div></td></tr>`}</tbody></table></div></section>`;
  }

  function bankReconciliationTemplate() {
    const batches=[...bankBatchesForPeriod()].filter(batch=>!['Cancelled'].includes(batch.status)); const latest=batches[0]||null; const summary=paymentBatchSummary(latest);
    return `${latest?`<div class="payment-summary-strip"><div><span>Tracking batch</span><strong>${escapeHtml(latest.reference)}</strong><small>${escapeHtml(latest.status)}</small></div><div><span>Total</span><strong>${formatCurrency(summary.total)}</strong><small>${latest.rows.length} employees</small></div><div><span>Paid</span><strong>${formatCurrency(summary.paid)}</strong><small>${summary.paidCount} completed</small></div><div class="${summary.failedCount||summary.reversedCount?'is-alert':''}"><span>Needs action</span><strong>${summary.failedCount+summary.reversedCount}</strong><small>Failed / reversed</small></div></div>`:''}<section class="panel panel--flush"><div class="panel__head panel__head--padded"><div><h2>Bank result reconciliation</h2><p>Import bank-return results. Paid/failed/reversed states are recorded against the existing payment attempt; failed rows can be retried without creating another payroll.</p></div>${latest?`<div class="payment-head-actions">${bankBatchStatusBadge(latest.status)}${['Processing','Partially Paid','Needs Attention'].includes(latest.status)?`<label class="btn btn--secondary bank-result-import">Import Result CSV<input id="bankResultFile" type="file" accept=".csv,.txt,text/csv,text/plain"></label>`:''}</div>`:''}</div>${latest?paymentRowsTable(latest):`<div class="table-empty table-empty--card"><strong>No bank batch available for reconciliation.</strong><span>Prepare and start a payment batch first.</span></div>`}</section><section class="source-note">${icon('info')}<span><strong>Result import fields</strong>Employee ID and Status are required. Paid rows require a transaction reference; Failed/Reversed rows require a reason. Raw result files are not retained after reconciliation—only their SHA-256 and import metadata are stored.</span></section>`;
  }

  function bankExportTemplate() {
    const key=paymentPeriodKey(); if(!state.paymentLoadedPeriods.has(key)){loadSalaryPayments(state.period);return `<section class="page"><div class="table-empty table-empty--card"><strong>Loading salary payments…</strong><span>Fetching payment profiles, templates and batch history.</span></div></section>`;}
    if(state.bankExportTab==='wps') return `<section class="page bank-export-page ui-v2-prs-internal-page ui-v2-prs-internal-execution-page"><div class="page-head"><div class="page-head__copy"><span class="eyebrow">Internal Company · Salary Payments</span><h1>Bank & WPS Export</h1><p>Bank salary files and WPS are separate configured channels over the same approved payroll snapshot.</p></div><div class="page-head__actions"><button class="btn btn--secondary" data-route-link="payments">Salary Payments</button><button class="btn btn--primary" data-route-link="wps">Open WPS</button></div></div><div class="bank-export-tabs"><button data-bank-export-tab="bank"><span>Bank Payment</span><small>Templates · batches · reconciliation</small></button><button class="is-active" data-bank-export-tab="wps"><span>WPS Export</span><small>WPS validation & batches</small></button></div>${wpsValidationTemplate()}</section>`;
    let content=bankExportRegisterTemplate(); if(state.bankExportView==='templates')content=bankTemplatesTemplate(); else if(state.bankExportView==='batches')content=bankBatchesTemplate(); else if(state.bankExportView==='reconciliation')content=bankReconciliationTemplate();
    return `<section class="page bank-export-page ui-v2-prs-internal-page ui-v2-prs-internal-execution-page"><div class="page-head"><div class="page-head__copy"><span class="eyebrow">Internal Company · Salary Payments · ${escapeHtml(state.period)}</span><h1>Bank Payment & WPS</h1><p>Prepare salary files, preserve payment snapshots and reconcile outcomes without altering approved payroll.</p></div><div class="page-head__actions"><button class="btn btn--secondary" data-route-link="payments">Salary Payments</button>${paymentSetupAction()}</div></div><div class="bank-export-tabs"><button class="is-active" data-bank-export-tab="bank"><span>Bank Payment</span><small>Configured salary-transfer workflow</small></button><button data-bank-export-tab="wps"><span>WPS Export</span><small>WPS validation & batches</small></button></div><div class="bank-workflow-tabs"><button class="${state.bankExportView==='register'?'is-active':''}" data-bank-export-view="register"><span>Validation Register</span></button><button class="${state.bankExportView==='templates'?'is-active':''}" data-bank-export-view="templates"><span>Export Templates</span></button><button class="${state.bankExportView==='batches'?'is-active':''}" data-bank-export-view="batches"><span>Payment Batches</span></button><button class="${state.bankExportView==='reconciliation'?'is-active':''}" data-bank-export-view="reconciliation"><span>Reconciliation</span></button></div>${content}</section>`;
  }

  function openBankTemplateDrawer(templateId = null) {
    const source = templateId ? bankTemplatesAll().find(item=>item.id===templateId) : null;
    if (source?.archived) { openConfigurationLifecycleDrawer('template', source.id, 'restore'); return; }
    const columns = source?.columns || ['employee_number','employee_name','iban','net_salary','transaction_reference'];
    state.drawerType='bank-template'; state.drawerContext=templateId; drawerSave.hidden=false; drawerSave.textContent=source?'Save Template':'Create Template'; drawerTitle.textContent=source?`Edit ${source.name}`:'New Salary Export Template';
    const headers = source?.headers?.length === columns.length ? source.headers : columns.map(key=>bankColumnCatalog[key]||key);
    const resultColumns = source?.resultColumns || {};
    drawerBody.innerHTML=`<section class="form-section"><div class="form-section__head"><strong>Template definition</strong><span>Company-owned file layout</span></div><div class="form-grid">${namedField('Code','bank-template-code',source?.code||'')} ${namedField('Template name','bank-template-name',source?.name||'')} ${namedSelectFieldValue('Channel','bank-template-channel',['Bank CSV','WPS'],source?.channel==='wps'?'WPS':'Bank CSV')} ${namedSelectFieldValue('Delimiter','bank-template-delimiter',['Comma','Tab','Semicolon'],source?.delimiter==='tab'?'Tab':source?.delimiter==='semicolon'?'Semicolon':'Comma')} ${namedSelectFieldValue('Encoding','bank-template-encoding',['UTF-8','UTF-8 with BOM'],source?.encoding==='utf-8-sig'?'UTF-8 with BOM':'UTF-8')} ${namedSelectFieldValue('Include header','bank-template-header',['Yes','No'],source?.includeHeader===false?'No':'Yes')} ${namedSelectFieldValue('Status','bank-template-status',['Active','Inactive'],source?.active===false?'Inactive':'Active')}<div class="form-field form-field--full"><label>Column keys in export order</label><textarea class="textarea mono-cell" name="bank-template-columns" rows="5">${escapeHtml(columns.join(', '))}</textarea><span class="field-hint">Required: net_salary. Employee ID is optional when the bank layout identifies rows another way. Allowed: ${escapeHtml(Object.keys(bankColumnCatalog).join(', '))}</span></div><div class="form-field form-field--full"><label>Exact header labels</label><textarea class="textarea" name="bank-template-headers" rows="5">${escapeHtml(headers.join('\n'))}</textarea><span class="field-hint">One label per line, in the same order as the column keys. Use the exact labels required by the bank/WPS channel.</span></div></div></section><section class="form-section"><div class="form-section__head"><strong>Reconciliation result headers</strong><span>Optional exact mapping</span></div><div class="form-grid">${namedField('Employee ID header','bank-result-employee',resultColumns.employee||'')}${namedField('Status header','bank-result-status',resultColumns.status||'')}${namedField('Transaction reference header','bank-result-reference',resultColumns.reference||'')}${namedField('Failure reason header','bank-result-reason',resultColumns.reason||'')}</div><span class="field-hint">Leave all four blank to accept the built-in common aliases. If configured, Employee ID and Status are required.</span></section><section class="source-note">${icon('info')}<span>Configure the exact file and reconciliation layout supplied by the company bank/WPS channel. The system does not seed or claim a universal bank format.</span></section>`;
    drawer.classList.add('is-open'); drawerScrim.classList.add('is-open'); drawer.setAttribute('aria-hidden','false');
  }

  function openEmployeePaymentProfileDrawer(employeeId) {
    const employee = state.employees.find(item => item.id === employeeId);
    if (!employee) return;
    const profile = paymentContextForPeriod().profiles?.[employeeId] || null;
    state.drawerType='employee-payment-profile'; state.drawerContext={employeeId}; drawerSave.hidden=false; drawerSave.disabled=false; drawerSave.textContent=profile?'Save Payment Profile':'Create Payment Profile'; drawerTitle.textContent=`${employee.name} · Salary Payment`;
    const destinationType = profile?.destinationType === 'salary_card' ? 'Salary card' : 'Bank account / IBAN';
    drawerBody.innerHTML=`<section class="form-section"><div class="form-section__head"><strong>Payment destination</strong><span>Encrypted at rest</span></div><div class="form-grid">${namedSelectFieldValue('Destination type','payment-profile-destination',['Bank account / IBAN','Salary card'],destinationType)}${namedField('Account holder name','payment-profile-holder',profile?.accountHolderName||employee.name||'')}${namedField('Bank / issuer name','payment-profile-bank-name',profile?.bankName||'')}${namedField('Bank code','payment-profile-bank-code',profile?.bankCode||'')}<div class="form-field"><label>IBAN</label><input class="input mono-cell" name="payment-profile-iban" autocomplete="off" value="" placeholder="${escapeHtml(profile?.ibanMasked ? `Leave blank to keep ${profile.ibanMasked}` : 'Enter full IBAN')}"><span class="field-hint">The full value is never sent back to the browser after it is saved.</span></div><div class="form-field"><label>Salary card number</label><input class="input mono-cell" name="payment-profile-card" autocomplete="off" value="" placeholder="${escapeHtml(profile?.salaryCardMasked ? `Leave blank to keep ${profile.salaryCardMasked}` : 'Enter salary card number')}"></div>${namedSelectFieldValue('WPS enabled','payment-profile-wps',['Yes','No'],profile?.wpsEnabled?'Yes':'No')}${namedSelectFieldValue('Profile status','payment-profile-active',['Active','Inactive'],profile?.active===false?'Inactive':'Active')}${namedSelectFieldValue('Mark verified','payment-profile-verified',['No','Yes'],'No')}</div></section><section class="source-note">${icon('info')}<span><strong>Historical payment protection</strong>Updating this profile affects only future payment batches. Existing batches keep their encrypted destination snapshot.</span></section>${profile?`<section class="payroll-detail-actions"><button type="button" class="btn btn--ghost" data-config-lifecycle="payment-profile|${escapeHtml(employeeId)}|delete">Delete unused payment profile</button></section>`:''}`;
    drawer.classList.add('is-open'); drawerScrim.classList.add('is-open'); drawer.setAttribute('aria-hidden','false');
    drawerBody.querySelector('[data-config-lifecycle]')?.addEventListener('click',()=>{const [kind,id,action]=drawerBody.querySelector('[data-config-lifecycle]').dataset.configLifecycle.split('|');openConfigurationLifecycleDrawer(kind,id,action);});
  }

  function openCompanyPaymentSettingsDrawer() {
    const settings = paymentContextForPeriod().settings || {};
    state.drawerType='salary-payment-settings'; state.drawerContext=null; drawerSave.hidden=false; drawerSave.disabled=false; drawerSave.textContent='Save Payment Settings'; drawerTitle.textContent='Company Salary Payment Settings';
    drawerBody.innerHTML=`<section class="form-section"><div class="form-section__head"><strong>Employer payment identity</strong><span>Required when used by the selected export/WPS channel</span></div><div class="form-grid">${namedField('Employer identifier','payment-settings-employer-id',settings.employerIdentifier||'')}${namedField('Employer bank name','payment-settings-bank-name',settings.employerBankName||'')}${namedField('Employer bank code','payment-settings-bank-code',settings.employerBankCode||'')}<div class="form-field"><label>Employer IBAN</label><input class="input mono-cell" name="payment-settings-iban" autocomplete="off" value="" placeholder="${escapeHtml(settings.hasEmployerIban ? `Leave blank to keep ${settings.employerIbanMasked}` : 'Enter employer IBAN')}"><span class="field-hint">Stored encrypted. Leave blank to preserve the current value.</span></div>${namedField('Bank customer reference','payment-settings-customer-reference',settings.bankCustomerReference||'')}</div></section><section class="source-note">${icon('info')}<span><strong>Company-specific configuration</strong>No bank or WPS file format is seeded. Pair these details with the exact export template provided by the company bank/payment channel.</span></section>`;
    drawer.classList.add('is-open'); drawerScrim.classList.add('is-open'); drawer.setAttribute('aria-hidden','false');
  }

  function openBankRowDrawer(employeeId) {
    const row=bankPaymentRows({all:true}).find(item=>item.employeeId===employeeId); if(!row)return; const profile=paymentContextForPeriod().profiles?.[employeeId];
    state.drawerType='bank-row'; state.drawerContext=employeeId; drawerSave.hidden=true; drawerTitle.textContent=`${row.name} · Payment Profile`;
    drawerBody.innerHTML=`<section class="form-section"><div class="form-section__head"><strong>Salary payment destination</strong>${wpsStatusBadge(row.bankStatus)}</div><div class="detail-grid"><div><span>Bank / issuer</span><strong>${escapeHtml(row.bank||'Not configured')}</strong></div><div><span>Destination</span><strong class="mono-cell">${escapeHtml(row.account||'—')}</strong></div><div><span>Type</span><strong>${escapeHtml(profile?.destinationLabel||'—')}</strong></div><div><span>Verified</span><strong>${profile?.verifiedAt?'Yes':'No'}</strong></div></div></section>${row.bankBlockers.length?`<section class="form-section"><div class="validation-list">${row.bankBlockers.map(text=>`<div class="validation-list__item is-danger"><span>!</span><p>${escapeHtml(text)}</p></div>`).join('')}</div></section>`:''}<section class="payroll-detail-actions"><button class="btn btn--secondary" data-payment-profile-edit="${escapeHtml(employeeId)}">Edit Payment Profile</button></section>`;
    drawer.classList.add('is-open'); drawerScrim.classList.add('is-open'); drawer.setAttribute('aria-hidden','false');
    drawerBody.querySelector('[data-payment-profile-edit]')?.addEventListener('click',()=>openEmployeePaymentProfileDrawer(employeeId));
  }

  function openBankBatchDrawer(batchId) {
    const batch=state.paymentBatches.find(item=>item.id===batchId); if(!batch)return; state.drawerType='bank-batch'; state.drawerContext=batchId; drawerSave.hidden=true; drawerTitle.textContent=batch.reference;
    drawerBody.innerHTML=`<section class="form-section"><div class="form-section__head"><strong>Salary payment batch</strong>${bankBatchStatusBadge(batch.status)}</div><div class="detail-grid"><div><span>Period</span><strong>${escapeHtml(batch.period)}</strong></div><div><span>Channel</span><strong>${escapeHtml(batch.channel)}</strong></div><div><span>Template</span><strong>${escapeHtml(batch.templateName)}</strong></div><div><span>Employees</span><strong>${batch.employeeCount}</strong></div><div><span>Total</span><strong>${formatCurrency(Number(batch.total||0))}</strong></div><div><span>Paid</span><strong>${formatCurrency(Number(batch.paidAmount||0))}</strong></div></div></section><section class="payroll-detail-actions">${!['Cancelled','Closed'].includes(batch.status)?`<button class="btn btn--secondary" data-payment-export="${escapeHtml(batch.id)}">Export File</button>`:''}${['Prepared','Exported'].includes(batch.status)?`<button class="btn btn--primary" data-payment-start-batch="${escapeHtml(batch.id)}">Start Processing</button>`:''}${batch.status==='Paid'?`<button class="btn btn--primary" data-payment-close-batch="${escapeHtml(batch.id)}">Close Payroll</button>`:''}</section>`;
    drawer.classList.add('is-open'); drawerScrim.classList.add('is-open'); drawer.setAttribute('aria-hidden','false');
    drawerBody.querySelector('[data-payment-export]')?.addEventListener('click',()=>exportPaymentBatch(batch.id));
    drawerBody.querySelector('[data-payment-start-batch]')?.addEventListener('click',()=>runPaymentBatchWorkflow(batch.id,'start'));
    drawerBody.querySelector('[data-payment-close-batch]')?.addEventListener('click',()=>runPaymentBatchWorkflow(batch.id,'close'));
  }

  function paymentBatchSummary(batch) {
    const rows=Array.isArray(batch?.rows)?batch.rows:[]; const out={total:0,paid:0,failed:0,reversed:0,paidCount:0,failedCount:0,reversedCount:0,processingCount:0,pendingCount:0};
    rows.forEach(row=>{out.total+=Number(row.amount||0); if(row.status==='Paid'){out.paid+=Number(row.amount||0);out.paidCount++;}else if(row.status==='Failed')out.failedCount++;else if(row.status==='Reversed')out.reversedCount++;else if(row.status==='Processing')out.processingCount++;else out.pendingCount++;}); out.remaining=Math.max(0,out.total-out.paid); return out;
  }

  function paymentRowsTable(batch) {
    const q=state.paymentSearch.trim().toLowerCase(); const rows=(batch?.rows||[]).filter(row=>{const statusMatch=state.paymentStatusFilter==='All'||row.status===state.paymentStatusFilter;return statusMatch&&(!q||`${row.employeeCode} ${row.name} ${row.bank} ${row.reference||''}`.toLowerCase().includes(q));});
    return `<div class="table-wrap"><table class="data-table payment-table"><thead><tr><th>Employee</th><th>Bank / Destination</th><th class="num">Amount</th><th>Status</th><th>Transaction Reference</th><th>Attempts</th><th></th></tr></thead><tbody>${rows.length?rows.map(row=>`<tr><td><button class="entity-link entity-link--stack" data-open-employee="${escapeHtml(row.employeeId)}"><strong>${escapeHtml(row.name)}</strong><span>EMP ${escapeHtml(row.employeeCode)}</span></button></td><td><div class="bank-cell"><strong>${escapeHtml(row.bank||'—')}</strong><span>${escapeHtml(row.account||'—')}</span></div></td><td class="num table-money"><strong>${formatCurrency(Number(row.amount||0))}</strong></td><td>${wpsBatchStatusBadge(row.status)}</td><td><span class="mono-cell">${escapeHtml(row.reference||'—')}</span>${row.failureReason?`<small class="table-secondary table-secondary--attention">${escapeHtml(row.failureReason)}</small>`:''}</td><td>${Number(row.attempts||0)}</td><td><div class="table-row-actions">${['Failed','Reversed'].includes(row.status)?`<button class="btn btn--ghost btn--sm" data-payment-retry="${escapeHtml(row.id)}" data-payment-batch="${escapeHtml(batch.id)}">Retry</button>`:''}<button class="icon-btn icon-btn--sm" data-payment-row="${escapeHtml(row.id)}" data-payment-batch="${escapeHtml(batch.id)}">${icon('chevron')}</button></div></td></tr>`).join(''):`<tr><td colspan="7"><div class="table-empty"><strong>No payment rows match this filter.</strong><span>Reset filters to see the batch.</span></div></td></tr>`}</tbody></table></div>`;
  }

  function paymentsInternalTemplate() {
    const key=paymentPeriodKey(); if(!state.paymentLoadedPeriods.has(key)){loadSalaryPayments(state.period);return `<div class="table-empty table-empty--card"><strong>Loading salary payments…</strong><span>Fetching payment batches and reconciliation state.</span></div>`;}
    const batches=[...paymentBatchesForPeriod()].sort((a,b)=>String(b.createdAt||'').localeCompare(String(a.createdAt||''))); if(!state.selectedInternalPaymentBatchId||!batches.some(item=>item.id===state.selectedInternalPaymentBatchId))state.selectedInternalPaymentBatchId=batches[0]?.id||null; const batch=batches.find(item=>item.id===state.selectedInternalPaymentBatchId)||batches[0]||null; const summary=paymentBatchSummary(batch);
    return `${batch?`<div class="payment-summary-strip"><div><span>Payment batch</span><strong>${escapeHtml(batch.reference)}</strong><small>${escapeHtml(batch.channel)} · ${escapeHtml(batch.templateName)}</small></div><div><span>Total</span><strong>${formatCurrency(summary.total)}</strong><small>${batch.rows.length} employee payments</small></div><div><span>Paid</span><strong>${formatCurrency(summary.paid)}</strong><small>${summary.paidCount} completed</small></div><div class="${summary.failedCount||summary.reversedCount?'is-alert':''}"><span>Remaining</span><strong>${formatCurrency(summary.remaining)}</strong><small>${summary.failedCount||summary.reversedCount?`${summary.failedCount} failed · ${summary.reversedCount} reversed`:`${summary.pendingCount+summary.processingCount} pending / processing`}</small></div></div>`:`<div class="payment-empty-hero"><div class="payment-empty-hero__icon">${icon('wallet')}</div><div><span class="eyebrow">Internal salary payments</span><h2>No payment batch for ${escapeHtml(state.period)}</h2><p>Prepare a controlled Bank or WPS batch from the approved payroll.</p></div><button class="btn btn--primary" data-route-link="bank-export">Open Bank / WPS</button></div>`}${batch?`<section class="panel panel--flush"><div class="panel__head panel__head--padded"><div><h2>Salary payment register</h2><p>Bank-return outcomes and retry attempts are server controlled.</p></div><div class="payment-head-actions">${batches.length>1?`<select class="select payment-batch-select" id="internalPaymentBatchSelect">${batches.map(item=>`<option value="${escapeHtml(item.id)}" ${item.id===batch.id?'selected':''}>${escapeHtml(item.reference)} · ${escapeHtml(item.channel)}</option>`).join('')}</select>`:''}${wpsBatchStatusBadge(batch.status)}${['Prepared','Exported'].includes(batch.status)?`<button class="btn btn--primary" data-payment-start data-payment-batch="${escapeHtml(batch.id)}">Start Processing</button>`:''}${['Processing','Partially Paid','Needs Attention'].includes(batch.status)?`<label class="btn btn--secondary bank-result-import">Import Results<input class="payment-result-file" data-result-batch="${escapeHtml(batch.id)}" type="file" accept=".csv,.txt,text/csv,text/plain"></label>`:''}${batch.status==='Paid'?`<button class="btn btn--secondary" data-payment-close-payroll data-payment-batch="${escapeHtml(batch.id)}">Close Payroll</button>`:''}</div></div><div class="toolbar toolbar--table"><div class="search-field">${icon('search')}<input id="paymentSearch" type="search" value="${escapeHtml(state.paymentSearch)}" placeholder="Search employee, bank or reference…"></div><select class="select" id="paymentStatusFilter"><option>All</option>${['Pending','Processing','Paid','Failed','Reversed','Cancelled'].map(x=>`<option ${state.paymentStatusFilter===x?'selected':''}>${x}</option>`).join('')}</select><button class="btn btn--ghost" data-payment-reset>Reset</button></div>${paymentRowsTable(batch)}</section>`:''}`;
  }

  function persistSupplierPayments() {}
  function supplierPaymentRecords() {
    return Object.entries(state.supplierPayments || {}).flatMap(([supplierId, payments]) => (payments || []).map((payment, index) => {
      const allocation=(payment.allocations||[])[0];
      return {
        id: payment.id || `${supplierId}-${payment.ref || index}`,
        ...payment,
        supplierId,
        supplier: payment.supplier || state.suppliers.find(item => item.id === supplierId)?.name || supplierId,
        period: allocation?.period || payment.period || state.period,
        projectId: allocation?.projectId || null,
        settlementId: allocation?.settlementId || null,
        settlementKey: allocation?.settlementId || null
      };
    }));
  }
  function supplierPaymentById(id) {
    for (const [supplierId, payments] of Object.entries(state.supplierPayments || {})) {
      const payment = (payments || []).find((item,index)=>(item.id || `${supplierId}-${item.ref || index}`) === id);
      if (payment) return { payment, supplierId };
    }
    return null;
  }

  function supplierPaymentStatusBadge(status) {
    const tone = status === 'Paid' ? 'success' : status === 'Failed' || status === 'Reversed' ? 'danger' : status === 'Processing' ? 'warning' : 'neutral';
    return `<span class="status status--${tone}"><span></span>${escapeHtml(status || 'Processing')}</span>`;
  }

  function supplierPaidAmount(settlementId) {
    const settlement=Object.values(state.rentalSettlements||{}).find(item=>item.id===settlementId);
    return Number(settlement?.totals?.paid||0);
  }
  function supplierPayables(period = state.period) {
    return Object.values(state.rentalSettlements || {})
      .filter(record => record.period === period && ['Approved','Payment Processing','Partially Paid','Paid','Closed'].includes(record.status))
      .map(record => {
        const totals = record.totals || {};
        const amount = Number(totals.net || 0);
        const paid = Number(totals.paid || 0);
        const processing = Number(totals.processing || 0);
        const outstanding = Number(totals.outstanding ?? Math.max(0, amount - paid));
        const available = Number(totals.available ?? Math.max(0, amount - paid - processing));
        return {
          key: record.id,
          settlementId: record.id,
          settlementNumber: record.number,
          period: record.period,
          projectId: record.projectId,
          supplierId: record.supplierId,
          supplier: record.supplier,
          project: record.project,
          amount,
          paid,
          processing,
          outstanding,
          available,
          settlementStatus: record.status,
          paymentStatus: record.status === 'Paid' || record.status === 'Closed' ? 'Paid' : paid > .005 ? 'Part paid' : processing > .005 ? 'Processing' : 'Open'
        };
      });
  }
  function supplierPaymentSummary(rows) {
    return rows.reduce((o,row)=>{o.payable+=row.amount;o.paid+=row.paid;o.outstanding+=row.outstanding;if(row.paymentStatus==='Open')o.open++;if(row.paymentStatus==='Part paid')o.partial++;return o;},{payable:0,paid:0,outstanding:0,open:0,partial:0});
  }

  function paymentDateDisplay(value) {
    if (!value) return '—';
    if (/^\d{4}-\d{2}-\d{2}$/.test(value)) { const [y,m,d]=value.split('-').map(Number); return new Date(y,m-1,d).toLocaleDateString('en-SA',{day:'2-digit',month:'short',year:'numeric'}); }
    return value;
  }

  function amountIntegerWords(value) {
    const ones=['','One','Two','Three','Four','Five','Six','Seven','Eight','Nine','Ten','Eleven','Twelve','Thirteen','Fourteen','Fifteen','Sixteen','Seventeen','Eighteen','Nineteen'];
    const tens=['','','Twenty','Thirty','Forty','Fifty','Sixty','Seventy','Eighty','Ninety'];
    const u=n=>{const out=[];if(n>=100){out.push(`${ones[Math.floor(n/100)]} Hundred`);n%=100;}if(n>=20){out.push(tens[Math.floor(n/10)]);if(n%10)out.push(ones[n%10]);}else if(n>0)out.push(ones[n]);return out.join(' ');};
    let n=Math.max(0,Math.floor(Number(value)||0));if(!n)return 'Zero';const out=[];[['Million',1e6],['Thousand',1e3],['',1]].forEach(([label,size])=>{const c=Math.floor(n/size);if(c){out.push(`${u(c)}${label?` ${label}`:''}`);n%=size;}});return out.join(' ');
  }

  function amountInWords(value) {
    const amount=Math.max(0,Number(value)||0), r=Math.floor(amount+1e-8), h=Math.round((amount-r)*100);
    return `${amountIntegerWords(r)} Saudi Riyal${r===1?'':'s'}${h?` and ${amountIntegerWords(h)} Halala${h===1?'':'s'}`:''} Only`;
  }

  function paymentReceiptsForPeriod() {
    const type = state.workspace === 'rental' ? 'supplier_payment_receipt' : 'salary_payment_receipt';
    return (state.businessDocuments || []).filter(doc => doc.workspace === state.workspace && doc.type === type && doc.period === state.period);
  }

  function receiptPaperTemplate(receipt) {
    if (!receipt) return `<div class="receipt-empty"><div>${icon('document')}</div><strong>Select a receipt</strong><span>A finalized payment receipt preview will appear here.</span></div>`;
    return documentSnapshotSummary(receipt);
  }

  function paymentsSupplierTemplate() {
    if (!state.rentalSettlementLoadedPeriods.has(state.period)) {
      loadRentalSettlementContext(state.period);
      return `<div class="table-empty table-empty--card ui-v2-payroll-table-empty"><strong>Loading supplier payments…</strong><span>Fetching approved settlement payables and payment history from the server.</span></div>`;
    }
    let payables=supplierPayables(state.period);
    if(state.paymentSupplierFilter!=='All suppliers') payables=payables.filter(row=>row.supplierId===state.paymentSupplierFilter);
    const allFiltered=[...payables];
    if(state.paymentPayableFilter==='Open') payables=payables.filter(row=>row.available>.005 && row.paid<=.005);
    else if(state.paymentPayableFilter==='Part paid') payables=payables.filter(row=>row.paymentStatus==='Part paid');
    else if(state.paymentPayableFilter==='Paid') payables=payables.filter(row=>row.paymentStatus==='Paid');
    const summary=supplierPaymentSummary(allFiltered);
    let payments=supplierPaymentRecords().filter(row=>row.period===state.period);
    if(state.paymentSupplierFilter!=='All suppliers') payments=payments.filter(row=>row.supplierId===state.paymentSupplierFilter);
    if(state.paymentMethodFilter!=='All methods') payments=payments.filter(row=>row.method===state.paymentMethodFilter);
    if(state.paymentStatusFilter!=='All') payments=payments.filter(row=>row.status===state.paymentStatusFilter);
    const q=state.paymentSearch.trim().toLowerCase();
    if(q) payments=payments.filter(row=>`${row.ref||''} ${row.supplier||''} ${row.transactionReference||''} ${row.resultReason||''}`.toLowerCase().includes(q));
    const open=allFiltered.filter(row=>row.available>.005);
    const processingCount=payments.filter(row=>row.status==='Processing').length;
    const attentionCount=payments.filter(row=>['Failed','Reversed'].includes(row.status)).length;
    return `<section class="payment-summary-strip supplier-payment-summary ui-v2-payroll-rental-payment-summary"><article><span>Approved payables</span><strong>${formatCurrency(summary.payable)}</strong><small>${allFiltered.length} settlement payable${allFiltered.length===1?'':'s'}</small></article><article><span>Paid</span><strong>${formatCurrency(summary.paid)}</strong><small>Confirmed supplier payments</small></article><article class="is-emphasis"><span>Outstanding</span><strong>${formatCurrency(summary.outstanding)}</strong><small>${summary.open} open · ${summary.partial} part paid</small></article><article><span>In processing</span><strong>${processingCount}</strong><small>Reserved payment records</small></article><article class="${attentionCount?'is-attention':''}"><span>Needs attention</span><strong>${attentionCount}</strong><small>Failed / reversed records</small></article></section>
      <section class="panel panel--flush ui-v2-payroll-panel ui-v2-payroll-register ui-v2-prs-supplier-payables"><div class="panel__head panel__head--padded"><div><span class="ui-v2-prs-panel-kicker">Supplier reconciliation</span><h2>Supplier payables</h2><p>Approved rental settlements become controlled payables. Processing allocations reserve only the available balance; failed/reversed results release it without changing the approved settlement snapshot.</p></div><button class="btn btn--primary" data-supplier-payment-new ${open.length?'':'disabled'}>${icon('plus')} Record Supplier Payment</button></div><div class="toolbar toolbar--table payment-supplier-toolbar ui-v2-payroll-register__toolbar"><select class="ui-v2-select ui-v2-payroll-operational-select" id="paymentSupplierFilter"><option value="All suppliers">All suppliers</option>${state.suppliers.map(s=>`<option value="${escapeHtml(s.id)}" ${state.paymentSupplierFilter===s.id?'selected':''}>${escapeHtml(s.name)}</option>`).join('')}</select><div class="segmented compact-segmented ui-v2-payroll-view-tabs is-compact">${['Open','Part paid','Paid','All'].map(x=>`<button data-payment-payable="${x}" class="${state.paymentPayableFilter===x?'is-active':''}">${x}</button>`).join('')}</div></div><div class="table-meta ui-v2-payroll-table-meta"><span><strong>${payables.length}</strong> payable${payables.length===1?'':'s'} in this view</span><span>Available excludes money already reserved by Processing payments.</span></div><div class="table-wrap ui-v2-payroll-table-wrap"><table class="data-table supplier-payable-table ui-v2-payroll-rental-payment-table"><thead><tr><th>Supplier</th><th>Project</th><th>Settlement</th><th class="num">Net Payable</th><th class="num">Paid</th><th class="num">Processing</th><th class="num">Available</th><th>Status</th><th></th></tr></thead><tbody>${payables.length?payables.map(row=>`<tr><td><button class="entity-link" data-open-supplier="${escapeHtml(row.supplierId)}">${escapeHtml(row.supplier)}</button></td><td><button class="entity-link" data-route-link="projects/${escapeHtml(row.projectId)}">${escapeHtml(row.project)}</button></td><td><div class="table-primary">${escapeHtml(row.settlementNumber||row.period)}</div><div class="table-secondary ui-v2-payroll-muted">${escapeHtml(row.settlementStatus)}</div></td><td class="num table-money">${formatCurrency(row.amount)}</td><td class="num table-money">${formatCurrency(row.paid)}</td><td class="num table-money">${formatCurrency(row.processing)}</td><td class="num table-money"><strong>${formatCurrency(row.available)}</strong></td><td>${row.paymentStatus==='Paid'?supplierPaymentStatusBadge('Paid'):row.paymentStatus==='Part paid'?'<span class="status status--warning"><span></span>Part paid</span>':row.paymentStatus==='Processing'?'<span class="status status--warning"><span></span>Processing</span>':'<span class="status status--neutral"><span></span>Open</span>'}</td><td>${row.available>.005?`<button class="btn btn--ghost btn--sm" data-pay-supplier-settlement="${escapeHtml(row.settlementId)}">Pay</button>`:'—'}</td></tr>`).join(''):`<tr><td colspan="9"><div class="table-empty ui-v2-payroll-table-empty"><strong>No supplier payables match this view.</strong><span>Only approved settlement snapshots enter the payment ledger.</span></div></td></tr>`}</tbody></table></div></section>
      <section class="panel panel--flush ui-v2-payroll-panel ui-v2-payroll-register ui-v2-prs-supplier-payment-register"><div class="panel__head panel__head--padded"><div><span class="ui-v2-prs-panel-kicker">Payment evidence</span><h2>Supplier payment register</h2><p>Payment outcomes remain immutable history. Failed or reversed payments are retried as new payment records.</p></div><button class="btn btn--secondary" data-route-link="rental-settlements">Open Settlements</button></div><div class="toolbar toolbar--table payment-register-toolbar ui-v2-payroll-register__toolbar"><div class="search-field ui-v2-filter-bar__search">${icon('search')}<input id="paymentSearch" type="search" value="${escapeHtml(state.paymentSearch)}" placeholder="Search payment, supplier or transaction reference…"></div><select class="ui-v2-select ui-v2-payroll-operational-select" id="paymentMethodFilter"><option>All methods</option>${['Bank','Cash','Cheque'].map(x=>`<option ${state.paymentMethodFilter===x?'selected':''}>${x}</option>`).join('')}</select><select class="ui-v2-select ui-v2-payroll-operational-select" id="paymentStatusFilter"><option>All</option>${['Processing','Paid','Failed','Reversed','Cancelled'].map(x=>`<option ${state.paymentStatusFilter===x?'selected':''}>${x}</option>`).join('')}</select><button class="btn btn--ghost" data-payment-reset>Reset</button></div><div class="table-meta ui-v2-payroll-table-meta"><span><strong>${payments.length}</strong> matching payment record${payments.length===1?'':'s'}</span><span>Failed/reversed records remain retained evidence.</span></div><div class="table-wrap ui-v2-payroll-table-wrap"><table class="data-table supplier-payment-table ui-v2-payroll-rental-payment-table"><thead><tr><th>Payment</th><th>Supplier</th><th>Project / Settlement</th><th>Date</th><th>Method</th><th class="num">Amount</th><th>Status</th><th>Reference / Result</th><th></th></tr></thead><tbody>${payments.length?payments.map(row=>{const allocation=(row.allocations||[])[0];return `<tr><td><button class="entity-link" data-supplier-payment-open="${escapeHtml(row.id)}">${escapeHtml(row.ref||row.id)}</button>${row.retryOf?'<span class="source-mini">Retry</span>':''}</td><td><button class="entity-link" data-open-supplier="${escapeHtml(row.supplierId)}">${escapeHtml(row.supplier)}</button></td><td>${allocation?`<button class="entity-link entity-link--stack ui-v2-payroll-table-entity" data-route-link="projects/${escapeHtml(allocation.projectId)}"><strong>${escapeHtml(allocation.project)}</strong><span>${escapeHtml(allocation.settlementNumber)}</span></button>`:'—'}</td><td>${escapeHtml(paymentDateDisplay(row.date))}</td><td>${escapeHtml(row.method||'—')}</td><td class="num table-money"><strong>${formatCurrency(row.amount)}</strong></td><td>${supplierPaymentStatusBadge(row.status)}</td><td><span class="mono-cell ui-v2-payroll-rental-payment-reference">${escapeHtml(row.transactionReference||'—')}</span>${row.resultReason?`<small class="table-secondary table-secondary--attention">${escapeHtml(row.resultReason)}</small>`:''}</td><td><div class="table-row-actions ui-v2-payroll-rental-payment-row-actions">${['Failed','Reversed'].includes(row.status)?`<button class="btn btn--ghost btn--sm" data-supplier-payment-retry="${escapeHtml(row.id)}">Retry</button>`:''}<button class="icon-btn icon-btn--sm" data-supplier-payment-open="${escapeHtml(row.id)}">${icon('chevron')}</button></div></td></tr>`}).join(''):`<tr><td colspan="9"><div class="table-empty ui-v2-payroll-table-empty"><strong>No supplier payments recorded for ${escapeHtml(state.period)}.</strong><span>Choose an approved settlement above to create the first controlled payment.</span></div></td></tr>`}</tbody></table></div></section>`;
  }
  function paymentsReceiptsTemplate() {
    const receipts=paymentReceiptsForPeriod();
    if(!state.selectedReceiptId || !receipts.some(item=>item.id===state.selectedReceiptId)) state.selectedReceiptId=receipts[0]?.id||null;
    const selected=receipts.find(item=>item.id===state.selectedReceiptId)||null;
    const label=state.workspace==='rental'?'Supplier payment receipts':'Salary payment receipts';
    return `<div class="receipt-workspace ${state.workspace==='rental'?'ui-v2-prs-rental-receipt-workspace':''}"><section class="receipt-list-panel ui-v2-payroll-panel"><div class="receipt-list-head"><div><span class="eyebrow">Receipts · ${escapeHtml(state.period)}</span><h2>${escapeHtml(label)}</h2><p>Immutable receipts finalized from confirmed paid ledger records.</p></div><span class="tab-count">${receipts.length}</span></div><div class="receipt-list">${receipts.length?receipts.map(item=>`<button class="receipt-list-item ${item.id===state.selectedReceiptId?'is-active':''}" data-receipt-select="${escapeHtml(item.id)}"><span class="receipt-list-item__icon">${escapeHtml(documentTypeCode(item.type))}</span><span><strong>${escapeHtml(item.number)}</strong><small>${escapeHtml(item.entityName||item.entityReference||'Payment record')}</small></span><span>${escapeHtml(item.period||'—')}</span></button>`).join(''):`<div class="table-empty table-empty--card ui-v2-payroll-table-empty"><strong>No finalized payment receipts for ${escapeHtml(state.period)}.</strong><span>Finalize a confirmed Paid payment from the Documents workspace.</span><button class="btn btn--secondary btn--sm" data-route-link="documents">Open Documents</button></div>`}</div></section><section class="receipt-preview-panel ui-v2-payroll-panel"><div class="receipt-preview-toolbar"><div><strong>${selected?escapeHtml(selected.number):'Receipt preview'}</strong><span>${selected?escapeHtml(documentTypeLabel(selected.type)):'No record selected'}</span></div><button class="btn btn--secondary" data-receipt-print ${selected?'':'disabled'}>${icon('document')} Print / Save PDF</button></div>${receiptPaperTemplate(selected)}</section></div>`;
  }
  function paymentsTemplate() {
    if (state.workspace === 'rental') {
      if (!state.rentalSettlementLoadedPeriods.has(state.period)) {
        loadRentalSettlementContext(state.period);
        return `<section class="page payments-page ui-v2-payroll-page ui-v2-prs-rental-page ui-v2-prs-rental-finance-page ui-v2-payroll-rental-supplier-payments-page"><div class="table-empty table-empty--card ui-v2-payroll-table-empty"><strong>Loading supplier payment ledger…</strong><span>Fetching approved settlements and payment history.</span></div></section>`;
      }
      if (!['supplier','receipts'].includes(state.paymentTab)) state.paymentTab='supplier';
      return `<section class="page payments-page ui-v2-payroll-page ui-v2-prs-rental-page ui-v2-prs-rental-finance-page ui-v2-payroll-rental-supplier-payments-page"><div class="page-head"><div class="page-head__copy"><span class="eyebrow">Rental Manpower · Supplier Reconciliation</span><h1>Supplier Payments</h1><p>Allocate controlled payments against Approved manpower-supplier settlement snapshots. Failed and reversed payment outcomes remain evidence and never rewrite settlement calculation.</p><span class="period-note">Payment period: <strong>${escapeHtml(state.period)}</strong></span></div><div class="page-head__actions"><button class="btn btn--secondary" data-route-link="rental-settlements">Supplier Settlements</button><button class="btn btn--secondary" data-route-link="documents">Supplier Documents</button></div></div><div class="source-note ui-v2-payroll-source-note ui-v2-prs-rental-payment-boundary">${icon('info')}<span><strong>Payment boundary.</strong> Only Approved supplier settlement payables are eligible. Processing payments reserve available balance; only Paid outcomes reduce the payable. Failed/Reversed outcomes release or restore the balance while preserving evidence.</span></div><div class="payment-workspace-switch ui-v2-payroll-adjustment-tabs ui-v2-payroll-rental-payment-tabs"><button class="${state.paymentTab==='supplier'?'is-active':''}" data-payment-tab="supplier"><span class="payment-switch-icon">SP</span><span><strong>Supplier Payments</strong><small>Payables + payment register</small></span></button><button class="${state.paymentTab==='receipts'?'is-active':''}" data-payment-tab="receipts"><span class="payment-switch-icon">RC</span><span><strong>Receipts</strong><small>Final paid evidence</small></span></button></div>${state.paymentTab==='receipts'?paymentsReceiptsTemplate():paymentsSupplierTemplate()}</section>`;
    }
    if (!['internal','receipts'].includes(state.paymentTab)) state.paymentTab='internal';
    return `<section class="page payments-page ui-v2-prs-internal-page ui-v2-prs-internal-execution-page"><div class="page-head"><div class="page-head__copy"><span class="eyebrow">Internal Payroll · Payments · ${escapeHtml(state.period)}</span><h1>Salary Payments</h1><p>Process company-employee salary batches and reconciliation without mixing supplier payments into the internal payroll ledger.</p></div><div class="page-head__actions"><button class="btn btn--secondary" data-route-link="bank-export">Bank / WPS</button></div></div><div class="payment-workspace-switch"><button class="${state.paymentTab==='internal'?'is-active':''}" data-payment-tab="internal"><span class="payment-switch-icon">IE</span><span><strong>Internal Salary Payments</strong><small>Bank / WPS batches</small></span></button><button class="${state.paymentTab==='receipts'?'is-active':''}" data-payment-tab="receipts"><span class="payment-switch-icon">RC</span><span><strong>Receipts</strong><small>Paid salary documents</small></span></button></div>${state.paymentTab==='receipts'?paymentsReceiptsTemplate():paymentsInternalTemplate()}</section>`;
  }
  function prepareWpsBatch() {
    return preparePaymentChannel('wps');
  }

  function openWpsRowDrawer(employeeId) {
    const row = wpsAllRows().find(item => item.employeeId === employeeId);
    if (!row) return;
    const profile = paymentContextForPeriod().profiles?.[employeeId] || null;
    state.drawerType = 'wps-inspect'; state.drawerContext = employeeId; drawerSave.hidden = true; drawerTitle.textContent = `${row.name} · WPS readiness`;
    drawerBody.innerHTML = `<section class="form-section"><div class="form-section__head"><strong>Current payment profile</strong>${wpsStatusBadge(row.wpsStatus)}</div><div class="detail-grid"><div><span>Bank / issuer</span><strong>${escapeHtml(row.bank || 'Not configured')}</strong></div><div><span>Destination</span><strong class="mono-cell">${escapeHtml(row.account || '—')}</strong></div><div><span>Destination type</span><strong>${escapeHtml(profile?.destinationLabel || '—')}</strong></div><div><span>National ID / Iqama</span><strong>${escapeHtml(row.nationalId || '—')}</strong></div><div><span>WPS enabled</span><strong>${profile?.wpsEnabled ? 'Yes' : 'No'}</strong></div><div><span>Verified</span><strong>${profile?.verifiedAt ? 'Yes' : 'No'}</strong></div></div></section><section class="form-section"><div class="form-section__head"><strong>Validation</strong><span>${row.wpsBlockers.length} blocker${row.wpsBlockers.length===1?'':'s'}</span></div><div class="validation-list">${row.wpsBlockers.length ? row.wpsBlockers.map(text => `<div class="validation-list__item is-danger"><span>!</span><p>${escapeHtml(text)}</p></div>`).join('') : '<div class="validation-list__item is-ok"><span>✓</span><p>All required WPS fields are valid for the current payroll and selected WPS template.</p></div>'}</div></section><section class="payroll-detail-actions"><button class="btn btn--secondary" data-payment-profile-edit="${escapeHtml(employeeId)}">Edit Payment Profile</button><button class="btn btn--secondary" data-wps-open-profile>Open Employee Profile</button></section>`;
    drawer.classList.add('is-open'); drawerScrim.classList.add('is-open'); drawer.setAttribute('aria-hidden','false');
    drawerBody.querySelector('[data-payment-profile-edit]')?.addEventListener('click',()=>openEmployeePaymentProfileDrawer(employeeId));
    drawerBody.querySelector('[data-wps-open-profile]')?.addEventListener('click', () => { closeDrawer(); state.employeeTab='bank'; navigate(`internal-employees/${employeeId}`); });
  }

  function openWpsBatchDrawer(batchId) {
    openBankBatchDrawer(batchId);
  }

  function latestPaymentBatch() {
    const batches = [...paymentBatchesForPeriod()].sort((a,b) => String(b.createdAt || '').localeCompare(String(a.createdAt || '')));
    return batches.find(item => item.id === state.selectedInternalPaymentBatchId) || batches[0] || null;
  }

  function salaryPaymentCoverage(period=state.period){
    const run=payrollRunRecord(period);
    const sourceRows=Array.isArray(run.snapshot?.rows)?run.snapshot.rows:[];
    let expected=sourceRows.filter(row=>Number(row.net||0)>0).map(row=>row.employeeId).filter(id=>{const employee=state.employees.find(item=>item.id===id);return /bank|wps/i.test(employee?.paymentMethod||'');});
    if(!expected.length){
      expected=[...new Set((state.paymentBatches||[]).filter(batch=>batch.period===period&&batch.status!=='Cancelled').flatMap(batch=>(batch.rows||[]).map(row=>row.employeeId)))];
    }
    const paid=new Set((state.paymentBatches||[]).filter(batch=>batch.period===period&&batch.status!=='Cancelled').flatMap(batch=>(batch.rows||[]).filter(row=>row.status==='Paid').map(row=>row.employeeId)));
    return {expected,paid,complete:expected.length>0&&expected.every(id=>paid.has(id))};
  }

  function refreshPaymentBatchStatus() {
    // Salary payment state is server-authoritative.
  }

  function openPaymentRowDrawer(rowId, batchId = null) {
    const batch = batchId ? state.paymentBatches.find(item => item.id === batchId) : latestPaymentBatch();
    if (!batch) return;
    const row = batch.rows.find(item => item.id === rowId);
    if (!row) return;
    state.drawerType='payment-row'; state.drawerContext={ batchId:batch.id, rowId }; drawerSave.hidden=true; drawerTitle.textContent=`${row.name} · Payment`;
    drawerBody.innerHTML = `<section class="form-section"><div class="form-section__head"><strong>Payment snapshot</strong>${wpsBatchStatusBadge(row.status)}</div><div class="detail-grid"><div><span>Batch</span><strong>${escapeHtml(batch.reference)}</strong></div><div><span>Amount</span><strong>${formatCurrency(Number(row.amount||0))}</strong></div><div><span>Bank / issuer</span><strong>${escapeHtml(row.bank||'—')}</strong></div><div><span>Destination</span><strong class="mono-cell">${escapeHtml(row.account||'—')}</strong></div><div><span>Transaction reference</span><strong class="mono-cell">${escapeHtml(row.reference||'—')}</strong></div><div><span>Attempts</span><strong>${Number(row.attempts||0)}</strong></div></div></section>${row.failureReason?`<section class="payroll-detail-alert payroll-detail-alert--danger"><strong>Bank result</strong><span>${escapeHtml(row.failureReason)}</span></section>`:''}<section class="payroll-detail-actions">${['Failed','Reversed'].includes(row.status)?`<button class="btn btn--primary" data-payment-retry="${escapeHtml(row.id)}" data-payment-batch="${escapeHtml(batch.id)}">Retry Payment</button>`:''}</section><section class="source-note">${icon('info')}<span><strong>Controlled reconciliation</strong>Payment results are changed only by an imported bank/WPS result file. Failed or reversed rows create a new retry attempt against this same approved payroll line.</span></section>`;
    drawer.classList.add('is-open'); drawerScrim.classList.add('is-open'); drawer.setAttribute('aria-hidden','false');
    drawerBody.querySelector('[data-payment-retry]')?.addEventListener('click',async()=>{try{const payload=await appApi(`/api/internal/salary-payments/rows/${encodeURIComponent(row.id)}/retry/`,{method:'POST',body:{}});applyPaymentPayload(payload);closeDrawer();renderRoute();showToast('Payment retry started','A new controlled payment attempt is now Processing.');}catch(error){showToast('Retry blocked',error.message);}});
  }

  function supplierPaymentScopeUpdate(select) {
    const payable=supplierPayables(state.period).find(item=>item.settlementId===select?.value);
    const box=drawerBody.querySelector('[data-supplier-payment-scope]');
    const amount=drawerBody.querySelector('[name="supplier-payment-amount"]');
    if(!payable){if(box)box.innerHTML='<span>Select an approved settlement.</span>';return;}
    if(box)box.innerHTML=`<div><span>Supplier</span><strong>${escapeHtml(payable.supplier)}</strong></div><div><span>Project</span><strong>${escapeHtml(payable.project)}</strong></div><div><span>Settlement</span><strong>${escapeHtml(payable.settlementNumber||'—')}</strong></div><div><span>Net</span><strong>${formatCurrency(payable.amount)}</strong></div><div><span>Paid</span><strong>${formatCurrency(payable.paid)}</strong></div><div><span>Processing</span><strong>${formatCurrency(payable.processing)}</strong></div><div class="is-emphasis"><span>Available</span><strong>${formatCurrency(payable.available)}</strong></div>`;
    if(amount){amount.max=String(payable.available);if(!amount.value||Number(amount.value)>payable.available)amount.value=payable.available.toFixed(2);}
  }
  function openSupplierPaymentDrawer(settlementId=null) {
    const payables=supplierPayables(state.period).filter(item=>item.available>.005);
    if(!payables.length){showToast('No available supplier payable',`There is no approved rental settlement with an unreserved balance in ${state.period}.`);return;}
    const selected=payables.find(item=>item.settlementId===settlementId)||payables[0];
    state.drawerType='supplier-payment';state.drawerContext=selected.settlementId;drawerSave.hidden=false;drawerSave.textContent='Record Payment';drawerTitle.textContent='Record supplier payment';
    drawerBody.innerHTML=`<section class="form-section"><div class="form-section__head"><strong>Settlement allocation</strong><span>Partial payment supported</span></div><div class="form-grid"><label class="form-field form-field--full"><span>Approved settlement</span><select name="supplier-payment-settlement">${payables.map(item=>`<option value="${escapeHtml(item.settlementId)}" ${item.settlementId===selected.settlementId?'selected':''}>${escapeHtml(item.supplier)} · ${escapeHtml(item.project)} · ${escapeHtml(item.settlementNumber||'Settlement')} · ${formatCurrency(item.available)} available</option>`).join('')}</select></label></div><div class="supplier-payment-scope ui-v2-payroll-rental-payment-mini-summary" data-supplier-payment-scope></div></section><section class="form-section"><div class="form-section__head"><strong>Payment details</strong><span>Bank · Cash · Cheque</span></div><div class="form-grid"><label class="form-field"><span>Amount</span><input name="supplier-payment-amount" type="number" min="0.01" step="0.01" value="${selected.available.toFixed(2)}"></label><label class="form-field"><span>Payment date</span><input name="supplier-payment-date" type="date" value="${rentalTodayIso()}"></label><label class="form-field"><span>Method</span><select name="supplier-payment-method"><option>Bank</option><option>Cash</option><option>Cheque</option></select></label><label class="form-field"><span>Initial status</span><select name="supplier-payment-status"><option>Processing</option><option>Paid</option></select></label><label class="form-field form-field--full"><span>Transaction / cheque reference</span><input name="supplier-payment-reference" placeholder="Required when Bank/Cheque is immediately marked Paid"></label><label class="form-field form-field--full"><span>Remarks</span><textarea name="supplier-payment-note" placeholder="Optional payment note"></textarea></label></div></section><section class="source-note">${icon('info')}<span><strong>Approved settlement remains immutable.</strong>The payment reserves or consumes only its available balance. Failed/reversed outcomes are retained and retried as separate records.</span></section>`;
    drawer.classList.add('is-open');drawerScrim.classList.add('is-open');drawer.setAttribute('aria-hidden','false');
    const select=drawerBody.querySelector('[name="supplier-payment-settlement"]');supplierPaymentScopeUpdate(select);select?.addEventListener('change',()=>supplierPaymentScopeUpdate(select));
  }
  function openSupplierPaymentDetailDrawer(paymentId) {
    const found=supplierPaymentById(paymentId); if(!found) return; const {payment,supplierId}=found;
    const allocation=(payment.allocations||[])[0];
    state.drawerType=payment.status==='Processing'||payment.status==='Paid'?'supplier-payment-result':'supplier-payment-readonly';
    state.drawerContext={paymentId,supplierId};
    drawerSave.hidden=state.drawerType==='supplier-payment-readonly';
    drawerSave.textContent='Save Payment Result';
    drawerTitle.textContent=payment.ref||'Supplier payment';
    const allowed=payment.status==='Processing'?['Processing','Paid','Failed','Cancelled']:payment.status==='Paid'?['Paid','Reversed']:[payment.status];
    drawerBody.innerHTML=`<section class="form-section"><div class="form-section__head"><strong>Supplier payment</strong><span>${supplierPaymentStatusBadge(payment.status)}</span></div><div class="detail-grid"><div><span>Supplier</span><strong>${escapeHtml(payment.supplier||supplierId)}</strong></div><div><span>Settlement</span><strong>${escapeHtml(allocation?.settlementNumber||'—')}</strong></div><div><span>Project</span><strong>${escapeHtml(allocation?.project||'—')}</strong></div><div><span>Amount</span><strong>${formatCurrency(payment.amount)}</strong></div><div><span>Method</span><strong>${escapeHtml(payment.method||'—')}</strong></div><div><span>Payment date</span><strong>${escapeHtml(paymentDateDisplay(payment.date))}</strong></div></div></section>${state.drawerType==='supplier-payment-readonly'?`<section class="source-note">${icon('info')}<span><strong>Immutable payment outcome.</strong>${escapeHtml(payment.resultReason||'Create a retry for failed/reversed payments instead of rewriting this record.')}</span></section>`:`<section class="form-section"><div class="form-section__head"><strong>Payment result</strong><span>Controlled state transition</span></div><div class="form-grid"><label class="form-field"><span>Status</span><select name="supplier-payment-result-status">${allowed.map(status=>`<option ${payment.status===status?'selected':''}>${escapeHtml(status)}</option>`).join('')}</select></label><label class="form-field"><span>Transaction / cheque reference</span><input name="supplier-payment-result-reference" value="${escapeHtml(payment.transactionReference||'')}"></label><label class="form-field form-field--full"><span>Failure / reversal reason</span><textarea name="supplier-payment-result-note" placeholder="Required for Failed or Reversed">${escapeHtml(payment.resultReason||'')}</textarea></label></div></section>`}<section class="payroll-detail-actions">${['Failed','Reversed'].includes(payment.status)?`<button class="btn btn--secondary" data-supplier-payment-retry="${escapeHtml(paymentId)}">Create Retry</button>`:''}</section>`;
    drawer.classList.add('is-open');drawerScrim.classList.add('is-open');drawer.setAttribute('aria-hidden','false');
  }
  function printPaymentReceipt(receipt) {
    printDocumentRecord(receipt);
  }
  function rentalTodayIso() {
    return state.systemSettings.general.today || companyTodayIso;
  }

  function openRentalWorkerActionDrawer(workerId, action) {
    const worker = rentalWorkerById(workerId);
    if (!worker) return;
    const snapshot = rentalWorkerCurrentSnapshot(worker);
    const currentProject = snapshot.project;
    const projectOptions = state.projects.filter(project => project.status === 'Active').map(project => ({ value:project.id, label:`${project.name} · ${project.code}` }));
    const targetProjectOptions = projectOptions.filter(item => item.value !== currentProject?.id);
    const today = rentalTodayIso();
    state.drawerType = 'rental-assignment-action';
    state.drawerContext = { workerId, action };
    drawerSave.hidden = false;
    const currentSummary = `<div class="assignment-action-current"><span class="assignment-action-current__icon">${currentProject ? 'PR' : 'RW'}</span><div><span class="eyebrow">Current state</span><strong>${escapeHtml(currentProject?.name || (worker.status === 'Scheduled' ? `Scheduled · ${worker.nextProject || 'project assignment'}` : worker.status === 'Inactive' ? 'Inactive worker' : 'Available with supplier'))}</strong><small>${escapeHtml(snapshot.trade)} · ${escapeHtml(snapshot.rate)}${snapshot.since ? ` · from ${escapeHtml(rentalDisplayDate(snapshot.since))}` : ''}</small></div></div>`;

    if (action === 'transfer') {
      drawerTitle.textContent = `${worker.name} · Transfer project`;
      drawerSave.textContent = 'Confirm Transfer';
      drawerBody.innerHTML = `${currentSummary}<section class="form-section"><div class="form-section__head"><strong>New project assignment</strong><span>The current assignment closes the day before this effective date. Worker identity and supplier remain unchanged.</span></div><div class="form-grid">${namedSelectOptions('Transfer to project','rental-action-project',targetProjectOptions,targetProjectOptions[0]?.value || '')}${namedField('Effective date','rental-action-date',today,'date')}${namedField('Trade','rental-action-trade',snapshot.trade || '')}${namedSelectFieldValue('Rate type','rental-action-rate-type',['Hourly','Daily','Monthly'],snapshot.rateType || 'Hourly')}${namedField(`Rate (${currencyCode()})`,'rental-action-rate',snapshot.rateValue == null ? '' : String(snapshot.rateValue),'number')}${namedField('Reason','rental-action-reason','Project manpower transfer')}</div></section><section class="source-note">${icon('info')}<span><strong>Preview:</strong> the old project stays in assignment history and future timesheet/cost rows are attributed to the new project from the effective date.</span></section>`;
    } else if (action === 'trade') {
      drawerTitle.textContent = `${worker.name} · Change trade`;
      drawerSave.textContent = 'Save Trade Change';
      drawerBody.innerHTML = `${currentSummary}<section class="form-section"><div class="form-section__head"><strong>Effective trade change</strong><span>Use this when the worker stays on the same project but changes role/trade.</span></div><div class="form-grid">${namedField('New trade','rental-action-trade',snapshot.trade === 'Helper → Mason' ? 'Mason' : snapshot.trade)}${namedField('Effective date','rental-action-date',today,'date')}${namedField('New rate (optional)','rental-action-rate','', 'number')}${namedSelectFieldValue('Rate type','rental-action-rate-type',['Hourly','Daily','Monthly'],snapshot.rateType || 'Hourly')}${namedField('Reason','rental-action-reason','Trade / role change')}</div></section>`;
    } else if (action === 'rate') {
      drawerTitle.textContent = `${worker.name} · Change rate`;
      drawerSave.textContent = 'Save Rate Change';
      drawerBody.innerHTML = `${currentSummary}<section class="form-section"><div class="form-section__head"><strong>Effective rate change</strong><span>The previous rate remains attached to earlier dates and settlement history.</span></div><div class="form-grid">${namedSelectFieldValue('Rate type','rental-action-rate-type',['Hourly','Daily','Monthly'],snapshot.rateType || 'Hourly')}${namedField(`New rate (${currencyCode()})`,'rental-action-rate',snapshot.rateValue == null ? '' : String(snapshot.rateValue),'number')}${namedField('Effective date','rental-action-date',today,'date')}${namedField('Reason','rental-action-reason','Rate revision')}</div></section>`;
    } else if (action === 'release') {
      drawerTitle.textContent = `${worker.name} · Release worker`;
      drawerSave.textContent = 'Release Worker';
      drawerBody.innerHTML = `${currentSummary}<section class="form-section"><div class="form-section__head"><strong>Release from current project</strong><span>The project assignment closes on the last working date. Do not delete the worker master.</span></div><div class="form-grid">${namedField('Last working date','rental-action-date',today,'date')}${namedSelectFieldValue('After release','rental-action-disposition',['Available','Inactive'],'Available')}${namedField('Reason','rental-action-reason','Work completed')}${namedTextareaField('Notes','rental-action-note','Optional release / return-to-supplier note')}</div></section>`;
    } else if (action === 'assign') {
      drawerTitle.textContent = `${worker.name} · Assign to project`;
      drawerSave.textContent = 'Create Assignment';
      drawerBody.innerHTML = `${currentSummary}<section class="form-section"><div class="form-section__head"><strong>Project assignment</strong><span>Select from the managed project master. This creates a new dated assignment without duplicating the worker.</span></div><div class="form-grid">${namedSelectOptions('Project','rental-action-project',projectOptions,projectOptions[0]?.value || '')}${namedField('Start date','rental-action-date',today,'date')}${namedField('Trade','rental-action-trade',snapshot.trade && !['—','Not assigned'].includes(snapshot.trade) ? snapshot.trade : '')}${namedSelectFieldValue('Rate type','rental-action-rate-type',['Hourly','Daily','Monthly'],snapshot.rateType || 'Hourly')}${namedField(`Rate (${currencyCode()})`,'rental-action-rate',snapshot.rateValue == null ? '' : String(snapshot.rateValue),'number')}${namedField('Reason','rental-action-reason','Project assignment')}</div></section>`;
    } else if (action === 'cancel') {
      drawerTitle.textContent = `${worker.name} · Cancel scheduled change`;
      drawerSave.textContent = 'Cancel Scheduled Change';
      drawerBody.innerHTML = `${currentSummary}<section class="form-section"><div class="form-section__head"><strong>Cancel latest future assignment change</strong><span>The cancelled schedule remains in audit history. If it came from a future transfer, trade or rate revision, the preceding assignment is restored automatically.</span></div><div class="form-grid">${namedTextareaField('Cancellation reason','rental-action-reason','Required reason for cancelling this scheduled change')}</div></section>`;
    } else if (action === 'edit') {
      drawerTitle.textContent = `${worker.name} · Edit worker`;
      drawerSave.textContent = 'Save Worker';
      drawerBody.innerHTML = `<section class="form-section"><div class="form-section__head"><strong>Permanent worker identity</strong><span>Editing master details does not create or rewrite an assignment.</span></div><div class="form-grid">${namedField('Worker ID','rental-action-worker-code',rentalWorkerCode(worker))}${namedField('Full name','rental-action-name',worker.name || '')}${namedField('Iqama / National ID','rental-action-national-id',worker.nationalId || '')}${namedField('Phone','rental-action-phone',worker.phone || '')}${namedTextareaField('Notes','rental-action-notes',worker.notes || '')}</div></section><section class="source-note">${icon('info')}<span>Supplier ownership is preserved here. Project/trade/rate changes are separate effective-dated assignment events.</span></section>`;
    } else if (action === 'advance') {
      drawerTitle.textContent = `${worker.name} · Record advance`;
      drawerSave.textContent = 'Record Advance';
      const adjustmentProjectOptions = projectOptions;
      drawerBody.innerHTML = `<section class="form-section"><div class="form-section__head"><strong>Worker advance</strong><span>Keep advances as separate transactions; do not change the worker's permanent rate.</span></div><div class="form-grid">${namedField('Date','rental-action-date',today,'date')}${namedSelectOptions('Project','rental-action-project',adjustmentProjectOptions,currentProject?.id || adjustmentProjectOptions[0]?.value || '')}${namedField(`Amount (${currencyCode()})`,'rental-action-amount','0','number')}${namedField('Reason','rental-action-reason','Salary / worker advance')}</div></section>`;
    } else return;
    drawer.classList.add('is-open'); drawerScrim.classList.add('is-open'); drawer.setAttribute('aria-hidden','false');
  }

  function rentalWorkerById(id) {
    return state.rentalWorkers.find(worker => worker.id === id) || null;
  }

  function rentalWorkerCode(worker) {
    return worker?.workerCode || String(worker?.id || '').replace(/^rw-/, 'RW-').toUpperCase() || 'RW';
  }

  function rentalWorkerRate(worker) {
    if (worker?.rate) return worker.rate;
    if (worker?.rateValue != null) return `${worker.rateType === 'Monthly' ? 'Monthly ' : ''}${currencyCode()} ${Number(worker.rateValue).toLocaleString('en-SA', { maximumFractionDigits:2 })}${worker.rateType === 'Hourly' ? '/hr' : worker.rateType === 'Daily' ? '/day' : ''}`;
    return 'Not set';
  }

  function rentalWorkerCurrentProject(worker) {
    if (!worker?.projectId || worker.status !== 'Assigned') return null;
    return state.projects.find(project => project.id === worker.projectId) || null;
  }

  function rentalWorkerSupplier(worker) {
    return state.suppliers.find(supplier => supplier.id === worker?.supplierId) || null;
  }

  function rentalSourceMonth(worker) {
    return null;
  }

  function rentalFriendlyToIso(value) {
    const raw = String(value || '').trim();
    if (!raw || raw === '—') return '';
    if (/^\d{4}-\d{2}-\d{2}$/.test(raw)) return raw;
    const match = raw.match(/^(\d{1,2})\s+([A-Za-z]{3,9})\s+(\d{4})$/);
    if (!match) return '';
    const months = { jan:1,january:1,feb:2,february:2,mar:3,march:3,apr:4,april:4,may:5,jun:6,june:6,jul:7,july:7,aug:8,august:8,sep:9,september:9,oct:10,october:10,nov:11,november:11,dec:12,december:12 };
    const month = months[match[2].toLowerCase()];
    if (!month) return '';
    return `${match[3]}-${String(month).padStart(2,'0')}-${String(match[1]).padStart(2,'0')}`;
  }

  function rentalDisplayDate(value) {
    if (!value) return 'Current';
    if (!/^\d{4}-\d{2}-\d{2}$/.test(String(value))) return String(value);
    try { return new Intl.DateTimeFormat('en-GB', { day:'2-digit', month:'short', year:'numeric' }).format(new Date(`${value}T00:00:00`)); }
    catch { return String(value); }
  }

  function rentalShiftDate(value, deltaDays) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(String(value || ''))) return '';
    const date = new Date(`${value}T00:00:00`);
    date.setDate(date.getDate() + deltaDays);
    return `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`;
  }

  function rentalRateLabelFromParts(rateType, rateValue, fallback = '') {
    if (fallback) return fallback;
    const value = Number(rateValue);
    if (!Number.isFinite(value)) return 'Rate not recorded';
    if (rateType === 'Monthly') return `Monthly ${currencyCode()} ${value.toLocaleString('en-SA', { maximumFractionDigits:2 })}`;
    if (rateType === 'Daily') return `${currencyCode()} ${value.toLocaleString('en-SA', { maximumFractionDigits:2 })}/day`;
    return `${currencyCode()} ${value.toLocaleString('en-SA', { maximumFractionDigits:2 })}/hr`;
  }

  function rentalAssignmentsFor(worker) {
    const rows = state.rentalAssignments?.[worker?.id];
    return Array.isArray(rows) ? rows : [];
  }

  function rentalCurrentAssignment(worker) {
    const rows = rentalAssignmentsFor(worker).filter(item => item.kind === 'assignment' && item.status !== 'Cancelled');
    if (worker?.currentAssignmentId) {
      const exact = rows.find(item => item.id === worker.currentAssignmentId);
      if (exact) return exact;
    }
    const today = rentalTodayIso();
    return rows.find(item => item.start && item.start <= today && (!item.end || item.end >= today)) || null;
  }

  function rentalWorkerCurrentSnapshot(worker) {
    const current = rentalCurrentAssignment(worker);
    if (!current) return {
      project:null,
      trade:worker?.trade || '—',
      rate:rentalWorkerRate(worker),
      rateType:worker?.rateType || 'Hourly',
      rateValue:worker?.rateValue,
      since:worker?.since || '',
      status:worker?.status || 'Available'
    };
    return {
      project:state.projects.find(item => item.id === current.projectId) || null,
      trade:current.trade || '—',
      rate:rentalRateLabelFromParts(current.rateType, current.rateValue, current.rateLabel),
      rateType:current.rateType || 'Hourly',
      rateValue:current.rateValue,
      since:current.start || '',
      status:'Assigned'
    };
  }

  function persistRentalWorkerState() {}
  function refreshRentalMasterCounts() {
    state.suppliers.forEach(supplier => {
      const rows = state.rentalWorkers.filter(worker => worker.supplierId === supplier.id);
      supplier.totalWorkers = rows.length;
      supplier.activeWorkers = rows.filter(worker => worker.status === 'Assigned').length;
      supplier.availableWorkers = rows.filter(worker => worker.status === 'Available').length;
      supplier.activeProjects = new Set(rows.filter(worker => worker.status === 'Assigned' && worker.projectId).map(worker => worker.projectId)).size;
    });
    state.projects.forEach(project => {
      const rows = state.rentalWorkers.filter(worker => worker.status === 'Assigned' && worker.projectId === project.id);
      project.rentalWorkers = rows.length;
      project.suppliers = new Set(rows.map(worker => worker.supplierId).filter(Boolean)).size;
    });
  }

  function applyRentalAssignmentPayload(payload) {
    if (payload.worker) replaceStateRecord(state.rentalWorkers, payload.worker);
    if (payload.worker?.id && Array.isArray(payload.assignments)) state.rentalAssignments[payload.worker.id] = payload.assignments;
    refreshRentalMasterCounts();
  }

  function rentalAssignmentHistoryHtml(worker) {
    const rows = [...rentalAssignmentsFor(worker)].sort((a,b) => String(b.start || '').localeCompare(String(a.start || '')));
    return `<div class="rental-assignment-timeline">${rows.map((item,index) => {
      const project = item.projectId ? state.projects.find(p => p.id === item.projectId) : null;
      const dateRange = item.endLabel || `${item.start ? rentalDisplayDate(item.start) : 'Date not supplied'} → ${item.end ? rentalDisplayDate(item.end) : item.status === 'Active' ? 'Current' : item.status}`;
      const auditTag = '<span class="source-mini">Audited history</span>';
      return `<article class="rental-assignment-event ${item.status === 'Active' ? 'is-current' : ''}"><div class="rental-assignment-event__rail"><span></span></div><div class="rental-assignment-event__body"><div class="rental-assignment-event__top"><div><span class="eyebrow">${escapeHtml(item.changeType || 'Assignment')}</span><h3>${escapeHtml(project?.name || item.projectName || 'Supplier worker pool')}</h3></div>${statusBadge(item.status || 'Closed')}</div><div class="rental-assignment-event__chips"><span>${escapeHtml(item.trade || 'Trade not set')}</span><span>${escapeHtml(rentalRateLabelFromParts(item.rateType, item.rateValue, item.rateLabel))}</span><span>${escapeHtml(dateRange)}</span></div>${item.note ? `<p>${escapeHtml(item.note)}</p>` : ''}<div class="rental-assignment-event__foot">${auditTag}<span>${escapeHtml(item.reason || 'Assignment lifecycle')}</span></div></div></article>`;
    }).join('')}</div>`;
  }

  function rentalWorkerSettlementMetrics(worker) {
    const rows = Object.values(state.rentalSettlements || {}).filter(group => group.period === state.period).flatMap(group => (group.rows || []).filter(row => row.workerId === worker?.id));
    if (!rows.length) return { hours:null, gross:null, advance:null, net:null, period:null };
    return {
      hours: rows.reduce((sum,row)=>sum+Number(row.hours||0),0),
      gross: rows.reduce((sum,row)=>sum+Number(row.gross||0),0),
      advance: rows.reduce((sum,row)=>sum+Number(row.adjustmentDeductions||0),0),
      net: rows.reduce((sum,row)=>sum+Number(row.net||0),0),
      period: state.period
    };
  }

  function rentalWorkerOverviewTab(worker, supplier, snapshot) {
    const history = rentalAssignmentsFor(worker);
    const changes = Math.max(0, history.filter(item => item.kind === 'assignment').length - 1);
    return `<div class="rental-profile-grid">
      <div class="profile-main-stack">
        <section class="panel panel--flush"><div class="section-headline"><div><h2>Worker overview</h2><p>Permanent worker identity stays separate from changing project, trade and rate assignments.</p></div><button class="btn btn--secondary btn--sm" data-rental-worker-action="edit" data-worker-id="${escapeHtml(worker.id)}">Edit worker</button></div><div class="worker-overview-grid"><div><span>Worker ID</span><strong>${escapeHtml(rentalWorkerCode(worker))}</strong></div><div><span>Iqama / National ID</span><strong>${escapeHtml(worker.nationalId || 'Not recorded')}</strong></div><div><span>Phone</span><strong>${escapeHtml(worker.phone || 'Not recorded')}</strong></div><div><span>Supplier</span><strong>${escapeHtml(supplier?.name || 'Not linked')}</strong></div><div><span>Master status</span><strong>${escapeHtml(worker.masterStatus || 'Active')}</strong>${worker.terminatedOn?`<small>Terminated ${escapeHtml(rentalDisplayDate(worker.terminatedOn))}</small>`:worker.inactiveOn?`<small>Stopped ${escapeHtml(rentalDisplayDate(worker.inactiveOn))}</small>`:''}</div><div><span>Assignment changes</span><strong>${changes}</strong></div></div></section>
        <section class="panel panel--flush"><div class="section-headline"><div><h2>Current assignment</h2><p>Current state is resolved from effective-dated assignment history.</p></div>${snapshot.project ? `<button class="text-link" data-open-project="${escapeHtml(snapshot.project.id)}">Open project →</button>` : ''}</div><div class="current-assignment-card ${snapshot.project ? '' : 'is-pool'}"><div class="current-assignment-card__icon">${snapshot.project ? 'PR' : 'AV'}</div><div><span class="eyebrow">${snapshot.project ? 'Active project assignment' : 'Supplier worker pool'}</span><h3>${escapeHtml(snapshot.project?.name || (worker.status === 'Inactive' ? 'Inactive / not available' : worker.status === 'Scheduled' ? `Scheduled for ${worker.nextProject || 'project assignment'}` : 'Available for assignment'))}</h3><div class="assignment-preview__meta"><span>${escapeHtml(snapshot.trade)}</span><span>${escapeHtml(snapshot.rate)}</span>${snapshot.since ? `<span>From ${escapeHtml(rentalDisplayDate(snapshot.since))}</span>` : ''}</div></div><div class="current-assignment-card__action">${snapshot.project && !worker.nextAssignmentId ? `<button class="btn btn--secondary btn--sm" data-rental-worker-action="transfer" data-worker-id="${escapeHtml(worker.id)}">Transfer</button>` : worker.status === 'Available' ? `<button class="btn btn--primary btn--sm" data-rental-worker-action="assign" data-worker-id="${escapeHtml(worker.id)}">Assign to project</button>` : ''}</div></div></section>
      </div>
      <aside class="profile-side-stack"><section class="detail-card"><div class="detail-card__head"><h3>Master links</h3></div><div class="rental-master-links">${supplier ? `<button class="mini-entity" data-open-supplier="${escapeHtml(supplier.id)}"><span class="mini-entity__icon">SP</span><span><strong>${escapeHtml(supplier.name)}</strong><small>Manpower supplier</small></span>${icon('chevron')}</button>` : ''}${snapshot.project ? `<button class="mini-entity" data-open-project="${escapeHtml(snapshot.project.id)}"><span class="mini-entity__icon">PR</span><span><strong>${escapeHtml(snapshot.project.name)}</strong><small>Current project</small></span>${icon('chevron')}</button>` : ''}</div></section><section class="detail-card"><div class="detail-card__head"><h3>Worker controls</h3></div><div class="rental-worker-actions-list">${snapshot.project && !worker.nextAssignmentId ? `<button data-rental-worker-action="transfer" data-worker-id="${escapeHtml(worker.id)}">Transfer project <span>→</span></button><button data-rental-worker-action="trade" data-worker-id="${escapeHtml(worker.id)}">Change trade <span>→</span></button><button data-rental-worker-action="rate" data-worker-id="${escapeHtml(worker.id)}">Change rate <span>→</span></button><button data-rental-worker-action="release" data-worker-id="${escapeHtml(worker.id)}">Release worker <span>→</span></button>` : worker.status === 'Available' ? `<button data-rental-worker-action="assign" data-worker-id="${escapeHtml(worker.id)}">Assign to project <span>→</span></button>` : ''}${worker.nextAssignmentId ? `<button class="is-danger" data-rental-worker-action="cancel" data-worker-id="${escapeHtml(worker.id)}">Cancel latest scheduled change <span>→</span></button>` : ''}<button data-rental-worker-action="advance" data-worker-id="${escapeHtml(worker.id)}">Record advance <span>→</span></button></div></section></aside>
    </div>`;
  }

  function rentalWorkerAssignmentsTab(worker) {
    return `<section class="panel panel--flush"><div class="section-headline"><div><h2>Assignment history</h2><p>Project, trade and rate changes are effective-dated. Previous records are closed, never overwritten.</p></div><div class="section-headline__actions"><button class="btn btn--ghost btn--sm" data-route-link="rental-assignments">All assignment activity</button>${worker.status === 'Assigned' && !worker.nextAssignmentId ? `<button class="btn btn--secondary btn--sm" data-rental-worker-action="transfer" data-worker-id="${escapeHtml(worker.id)}">Transfer</button>` : worker.status === 'Available' ? `<button class="btn btn--primary btn--sm" data-rental-worker-action="assign" data-worker-id="${escapeHtml(worker.id)}">Assign</button>` : ''}${worker.nextAssignmentId ? `<button class="btn btn--ghost btn--sm" data-rental-worker-action="cancel" data-worker-id="${escapeHtml(worker.id)}">Cancel scheduled</button>` : ''}</div></div>${rentalAssignmentHistoryHtml(worker)}<div class="assignment-integrity-note">${icon('info')}<span><strong>Historical integrity:</strong> a transfer, trade change or rate change closes the previous assignment on the day before the new effective date. The permanent worker and supplier relationship remain unchanged.</span></div></section>`;
  }

  function rentalWorkerTimesheetsTab(worker) {
    if (!state.rentalSettlementLoadedPeriods.has(state.period)) loadRentalSettlementContext(state.period,{render:false});
    const rows=Object.values(state.rentalSettlements||{}).filter(group=>group.period===state.period).flatMap(group=>(group.rows||[]).filter(row=>row.workerId===worker.id).map(row=>({group,row})));
    return `<section class="panel panel--flush"><div class="section-headline"><div><h2>Timesheet / settlement history</h2><p>Locked rental timesheet data stays tied to the commercial assignment effective on each work date.</p></div><button class="btn btn--secondary btn--sm" data-route-link="timesheets">Open Timesheets</button></div>${rows.length?`<div class="table-scroll"><table class="data-table rental-profile-table"><thead><tr><th>Period</th><th>Project</th><th>Supplier</th><th>Regular Hours</th><th>OT Hours</th><th>Settlement</th><th>Status</th></tr></thead><tbody>${rows.map(({group,row})=>`<tr><td><strong>${escapeHtml(group.period)}</strong></td><td><button class="entity-link" data-open-project="${escapeHtml(group.projectId)}">${escapeHtml(group.project)}</button></td><td>${escapeHtml(group.supplier)}</td><td class="table-money">${Number(row.hours||0).toLocaleString('en-SA',{maximumFractionDigits:2})}</td><td class="table-money">${Number(row.otHours||0).toLocaleString('en-SA',{maximumFractionDigits:2})}</td><td>${escapeHtml(group.number||'Calculated snapshot')}</td><td>${rentalSettlementStatusBadge(group.status)}</td></tr>`).join('')}</tbody></table></div>`:`<div class="table-empty table-empty--card"><strong>No calculated snapshot for ${escapeHtml(state.period)}.</strong><span>Approved/locked project timesheets remain available in the Timesheets workspace; calculated settlement snapshots appear here once settlement is prepared.</span></div>`}</section>`;
  }
  function rentalWorkerCostTab(worker) {
    if (!state.rentalSettlementLoadedPeriods.has(state.period)) loadRentalSettlementContext(state.period,{render:false});
    const matches=Object.values(state.rentalSettlements||{}).filter(group=>group.period===state.period).flatMap(group=>(group.rows||[]).filter(row=>row.workerId===worker.id).map(row=>({group,row})));
    if(!matches.length) return `<section class="panel panel--flush"><div class="section-headline"><div><h2>Cost / settlement history</h2><p>Worker cost is taken only from calculated supplier-settlement snapshots.</p></div></div><div class="table-empty table-empty--card"><strong>No calculated worker cost for ${escapeHtml(state.period)}.</strong><span>Lock the relevant project timesheet and calculate its supplier settlement.</span></div></section>`;
    return `<div class="profile-main-stack">${matches.map(({group,row})=>`<section class="panel panel--flush"><div class="section-headline"><div><h2>${escapeHtml(group.period)} worker cost</h2><p>${escapeHtml(group.project)} · ${escapeHtml(group.supplier)}</p></div>${rentalSettlementStatusBadge(group.status)}</div><div class="cost-detail-grid rental-worker-cost-grid"><div><span>Regular hours</span><strong>${Number(row.hours||0).toLocaleString('en-SA',{maximumFractionDigits:2})}</strong></div><div><span>OT hours</span><strong>${Number(row.otHours||0).toLocaleString('en-SA',{maximumFractionDigits:2})}</strong></div><div><span>Base cost</span><strong>${formatCurrency(row.base||0)}</strong></div><div><span>OT cost</span><strong>${formatCurrency(row.otAmount||0)}</strong></div><div><span>Adjustment earnings</span><strong>${formatCurrency(row.adjustmentEarnings||0)}</strong></div><div><span>Adjustment deductions</span><strong>${formatCurrency(row.adjustments||0)}</strong></div></div><div class="worker-net-banner"><span>Net worker cost</span><strong>${formatCurrency(row.net||0)}</strong></div><div class="payroll-detail-actions"><button class="btn btn--ghost btn--sm" data-settlement-worker="${escapeHtml(worker.id)}" data-project-id="${escapeHtml(group.projectId)}">Open calculation breakdown</button></div></section>`).join('')}<section class="source-note">${icon('info')}<span><strong>Immutable calculation snapshots.</strong>These amounts come from supplier settlement lines, including locked timesheet rate snapshots and Approved rental adjustments.</span></section></div>`;
  }
  function rentalWorkerAdvancesTab(worker) {
    if (!state.rentalSettlementLoadedPeriods.has(state.period)) loadRentalSettlementContext(state.period,{render:false});
    const rows = state.rentalAdjustments[worker.id] || [];
    return `<section class="panel panel--flush"><div class="section-headline"><div><h2>Advances & adjustments</h2><p>Project-attributed transactions remain separate from the permanent worker rate and flow into settlement only after approval.</p></div><button class="btn btn--primary btn--sm" data-rental-worker-action="advance" data-worker-id="${escapeHtml(worker.id)}">${icon('plus')} Record Advance</button></div>${rows.length ? `<div class="table-scroll"><table class="data-table rental-profile-table"><thead><tr><th>Date</th><th>Type</th><th>Project</th><th>Reason</th><th>Amount</th><th>Effect</th><th>Status</th></tr></thead><tbody>${rows.map(row => `<tr><td>${escapeHtml(row.date || '—')}</td><td><strong>${escapeHtml(row.type || 'Adjustment')}</strong></td><td>${escapeHtml(row.project || '—')}</td><td>${escapeHtml(row.reason || '—')}</td><td class="table-money">${formatCurrency(Number(row.amount || 0))}</td><td>${escapeHtml(row.impact||adjustmentImpactText(row))}</td><td>${statusBadge(row.status || 'Draft')}</td></tr>`).join('')}</tbody></table></div>` : `<div class="table-empty table-empty--card"><strong>No worker adjustments for ${escapeHtml(state.period)}.</strong><span>Create a Draft transaction and send it through the audited Review/Approval workflow before settlement calculation.</span></div>`}</section>`;
  }
  function rentalWorkerDocumentsTab(worker) {
    return `<section class="panel panel--flush"><div class="section-headline"><div><h2>Worker document references</h2><p>Rental final documents are controlled at the project timesheet, supplier settlement, supplier invoice and supplier-payment levels.</p></div><button class="btn btn--secondary btn--sm" data-route-link="documents">Open Documents</button></div><div class="table-empty table-empty--card"><strong>No separate worker-statement document type</strong><span>Use the worker assignment history for placement records and the finalized Rental Documents workspace for financial/timesheet records.</span></div></section>`;
  }

  function supplierWorkforceStats(supplierId) {
    const workers = state.rentalWorkers.filter(worker => worker.supplierId === supplierId);
    return {
      total: workers.length,
      assigned: workers.filter(worker => worker.status === 'Assigned').length,
      available: workers.filter(worker => worker.status === 'Available').length,
      released: workers.filter(worker => worker.status === 'Released').length,
      activeProjects: new Set(workers.filter(worker => worker.status === 'Assigned' && worker.projectId).map(worker => worker.projectId)).size
    };
  }

  function rentalWorkforceRows() {
    const q = state.rentalSearch.trim().toLowerCase();
    return state.rentalWorkers.filter(worker => {
      const supplier = rentalWorkerSupplier(worker);
      const project = rentalWorkerCurrentProject(worker);
      const statusMatch = state.rentalStatus === 'All' || worker.status === state.rentalStatus;
      const supplierMatch = state.rentalSupplier === 'All suppliers' || worker.supplierId === state.rentalSupplier;
      const projectMatch = state.rentalProject === 'All projects' || (state.rentalProject === 'Unassigned / available' ? !worker.projectId : worker.projectId === state.rentalProject);
      const tradeMatch = state.rentalTrade === 'All trades' || worker.trade === state.rentalTrade;
      const rateMatch = state.rentalRateType === 'All rate types' || worker.rateType === state.rentalRateType;
      const searchMatch = !q || `${worker.name} ${rentalWorkerCode(worker)} ${worker.trade} ${supplier?.name || worker.supplier || ''} ${project?.name || worker.project || ''} ${rentalWorkerRate(worker)}`.toLowerCase().includes(q);
      return statusMatch && supplierMatch && projectMatch && tradeMatch && rateMatch && searchMatch;
    });
  }


  function rentalAssignmentTypeLabel(item) {
    const type = String(item?.changeType || '').toLowerCase();
    if (type.includes('transfer')) return 'Project transfer';
    if (type.includes('trade')) return 'Trade change';
    if (type.includes('rate')) return 'Rate change';
    if (type.includes('released')) return 'Release';
    if (type.includes('assignment')) return 'Project assignment';
    if (type.includes('pool')) return 'Supplier pool';
    return item?.changeType || 'Assignment update';
  }

  function rentalAssignmentBadge(type) {
    const key = String(type || '').toLowerCase();
    const cls = key.includes('transfer') ? 'assignment-event-badge--transfer' : key.includes('trade') ? 'assignment-event-badge--trade' : key.includes('rate') ? 'assignment-event-badge--rate' : key.includes('release') ? 'assignment-event-badge--release' : 'assignment-event-badge--assign';
    return `<span class="assignment-event-badge ${cls}">${escapeHtml(type)}</span>`;
  }

  function rentalAssignmentActivityRows() {
    const activity = [];
    state.rentalWorkers.forEach(worker => {
      const supplier = rentalWorkerSupplier(worker);
      const history = [...rentalAssignmentsFor(worker)].sort((a,b) => String(a.start || '').localeCompare(String(b.start || '')));
      history.forEach((item,index) => {
        const previous = history.slice(0,index).reverse().find(row => row.kind === 'assignment') || null;
        const type = rentalAssignmentTypeLabel(item);
        if (item.kind === 'pool' && type === 'Supplier pool' && history.length === 1) return;
        const project = item.projectId ? state.projects.find(project => project.id === item.projectId) : null;
        const previousProject = previous?.projectId ? state.projects.find(project => project.id === previous.projectId) : null;
        let effective = item.start || '';
        let from = 'Supplier pool';
        let to = project?.name || item.projectName || 'Supplier pool';
        let detail = `${item.trade || 'Trade not set'} · ${rentalRateLabelFromParts(item.rateType,item.rateValue,item.rateLabel)}`;
        if (type === 'Project transfer') {
          from = previousProject?.name || previous?.projectName || 'Previous project';
          to = project?.name || item.projectName || 'New project';
        } else if (type === 'Trade change') {
          from = previous?.trade || 'Previous trade';
          to = item.trade || 'New trade';
          detail = project?.name || item.projectName || 'Project';
        } else if (type === 'Rate change') {
          from = previous ? rentalRateLabelFromParts(previous.rateType,previous.rateValue,previous.rateLabel) : 'Previous rate';
          to = rentalRateLabelFromParts(item.rateType,item.rateValue,item.rateLabel);
          detail = `${project?.name || item.projectName || 'Project'} · ${item.trade || 'Trade not set'}`;
        } else if (type === 'Release') {
          effective = item.endLabel && !previous ? '' : (previous?.end || rentalShiftDate(item.start,-1) || item.start || '');
          from = previousProject?.name || previous?.projectName || project?.name || item.projectName || 'Project';
          to = item.status === 'Inactive' ? 'Inactive' : 'Available with supplier';
          detail = `${item.trade || previous?.trade || 'Trade not set'} · ${rentalRateLabelFromParts(item.rateType,item.rateValue,item.rateLabel)}`;
        } else if (type === 'Project assignment') {
          from = previous?.end ? 'Previous assignment' : 'Supplier pool';
          to = project?.name || item.projectName || 'Project';
        }
        activity.push({
          id:item.id, worker, supplier, item, previous, project, previousProject, type, effective,
          from, to, detail,
          reason:item.reason || item.note || item.source || 'Assignment update',
          audit:item.actor || 'Audit trail',
          recordedAt:item.createdAt || null
        });
      });
    });
    return activity.sort((a,b) => String(b.effective || '').localeCompare(String(a.effective || '')) || a.worker.name.localeCompare(b.worker.name));
  }

  function rentalAssignmentIntegrity() {
    const issues = [];
    state.rentalWorkers.forEach(worker => {
      const rows = rentalAssignmentsFor(worker).filter(row => row.kind === 'assignment');
      const active = rows.filter(row => row.status === 'Active' && !row.end);
      if (active.length > 1) issues.push({ worker, message:'More than one open project assignment.' });
      rows.forEach(row => { if (!row.start) issues.push({ worker, message:'Assignment is missing an effective start date.' }); });
      const sorted = [...rows].filter(row => row.start).sort((a,b) => String(a.start).localeCompare(String(b.start)));
      for (let i=1;i<sorted.length;i++) {
        const previous = sorted[i-1], current = sorted[i];
        if (previous.end && String(previous.end) >= String(current.start)) issues.push({ worker, message:`Assignment dates overlap around ${rentalDisplayDate(current.start)}.` });
      }
    });
    return issues;
  }

  function rentalAssignmentFilteredActivity() {
    const q = state.rentalAssignmentSearch.trim().toLowerCase();
    return rentalAssignmentActivityRows().filter(row => {
      const supplierMatch = state.rentalAssignmentSupplier === 'All suppliers' || row.worker.supplierId === state.rentalAssignmentSupplier;
      const projectIds = [row.item.projectId,row.previous?.projectId].filter(Boolean);
      const projectMatch = state.rentalAssignmentProject === 'All projects' || projectIds.includes(state.rentalAssignmentProject);
      const typeMatch = state.rentalAssignmentType === 'All activity' || (state.rentalAssignmentType === 'Trade / rate changes' ? ['Trade change','Rate change'].includes(row.type) : row.type === state.rentalAssignmentType);
      const searchText = `${row.worker.name} ${rentalWorkerCode(row.worker)} ${row.supplier?.name || ''} ${row.from} ${row.to} ${row.detail} ${row.reason}`.toLowerCase();
      return supplierMatch && projectMatch && typeMatch && (!q || searchText.includes(q));
    });
  }

  function rentalAssignmentActivityTemplate() {
    const rows = rentalAssignmentFilteredActivity();
    const all = rentalAssignmentActivityRows();
    const eventTypes = ['All activity','Project assignment','Project transfer','Trade / rate changes','Trade change','Rate change','Release'];
    return `<section class="panel panel--flush assignment-activity-panel">
      <div class="panel__head panel__head--padded assignment-panel-head"><div><h2>Assignment activity</h2><p>One audit view for project transfers, role changes, rate revisions, releases and reassignments across every manpower supplier.</p></div><div class="assignment-panel-count"><strong>${rows.length}</strong><span>matching events</span></div></div>
      <div class="assignment-filterbar">
        <div class="search-field assignment-search">${icon('search')}<input id="rentalAssignmentSearch" type="search" value="${escapeHtml(state.rentalAssignmentSearch)}" placeholder="Search worker, supplier, project, trade or reason…"></div>
        <select class="select" id="rentalAssignmentSupplier"><option value="All suppliers">All suppliers</option>${state.suppliers.filter(s=>s.status==='Active').map(s=>`<option value="${escapeHtml(s.id)}" ${state.rentalAssignmentSupplier===s.id?'selected':''}>${escapeHtml(s.name)}</option>`).join('')}</select>
        <select class="select" id="rentalAssignmentProject"><option value="All projects">All projects</option>${state.projects.map(p=>`<option value="${escapeHtml(p.id)}" ${state.rentalAssignmentProject===p.id?'selected':''}>${escapeHtml(p.name)}</option>`).join('')}</select>
        <select class="select" id="rentalAssignmentType">${eventTypes.map(type=>`<option ${state.rentalAssignmentType===type?'selected':''}>${escapeHtml(type)}</option>`).join('')}</select>
        <button class="btn btn--ghost" data-assignment-reset>Reset</button>
      </div>
      <div class="table-wrap assignment-activity-table-wrap"><table class="data-table assignment-activity-table"><thead><tr><th>Effective</th><th>Worker</th><th>Event</th><th>Change</th><th>Context</th><th>Reason</th><th>Audit</th><th></th></tr></thead><tbody>${rows.length ? rows.map(row=>`<tr><td><strong>${escapeHtml(row.effective ? rentalDisplayDate(row.effective) : 'Date not supplied')}</strong>${row.recordedAt?`<small class="table-secondary">Recorded ${escapeHtml(payrollTimestamp(row.recordedAt))}</small>`:''}</td><td><button class="entity-link entity-link--stack" data-open-rental-worker="${escapeHtml(row.worker.id)}"><strong>${escapeHtml(row.worker.name)}</strong><span>${escapeHtml(rentalWorkerCode(row.worker))}</span></button>${row.supplier?`<button class="table-sub-link" data-open-supplier="${escapeHtml(row.supplier.id)}">${escapeHtml(row.supplier.name)}</button>`:''}</td><td>${rentalAssignmentBadge(row.type)}</td><td><div class="assignment-change-cell"><span>${escapeHtml(row.from)}</span><b>→</b><strong>${escapeHtml(row.to)}</strong></div></td><td><div class="table-primary">${escapeHtml(row.detail)}</div>${row.project?`<button class="table-sub-link" data-open-project="${escapeHtml(row.project.id)}">${escapeHtml(row.project.code)}</button>`:''}</td><td><span class="assignment-reason">${escapeHtml(row.reason)}</span></td><td><span class="source-mini">Audited</span><small class="assignment-audit-actor">${escapeHtml(row.audit)}</small></td><td><button class="icon-btn icon-btn--sm" data-assignment-worker="${escapeHtml(row.worker.id)}" title="Open assignment history">${icon('chevron')}</button></td></tr>`).join(''):`<tr><td colspan="8"><div class="table-empty"><strong>No assignment events match these filters.</strong><span>Reset the filters to review the full effective-dated history.</span></div></td></tr>`}</tbody></table></div>
      <div class="table-meta"><span><strong>${all.length}</strong> lifecycle events in the current worker master</span><span>Every lifecycle event is backed by the server assignment history and audit trail.</span></div>
    </section>`;
  }

  function rentalAssignmentDeploymentTemplate() {
    const q = state.rentalAssignmentSearch.trim().toLowerCase();
    const rows = state.rentalWorkers.filter(worker => worker.status === 'Assigned').map(worker => ({ worker, supplier:rentalWorkerSupplier(worker), snapshot:rentalWorkerCurrentSnapshot(worker) })).filter(row => {
      const supplierMatch = state.rentalAssignmentSupplier === 'All suppliers' || row.worker.supplierId === state.rentalAssignmentSupplier;
      const projectMatch = state.rentalAssignmentProject === 'All projects' || row.snapshot.project?.id === state.rentalAssignmentProject;
      const text = `${row.worker.name} ${rentalWorkerCode(row.worker)} ${row.supplier?.name || ''} ${row.snapshot.project?.name || ''} ${row.snapshot.trade} ${row.snapshot.rate}`.toLowerCase();
      return supplierMatch && projectMatch && (!q || text.includes(q));
    });
    return `<section class="panel panel--flush"><div class="panel__head panel__head--padded assignment-panel-head"><div><h2>Current deployment</h2><p>The latest open assignment for each worker, resolved from effective-dated history.</p></div><div class="assignment-panel-count"><strong>${rows.length}</strong><span>deployed workers</span></div></div><div class="assignment-filterbar assignment-filterbar--compact"><div class="search-field assignment-search">${icon('search')}<input id="rentalAssignmentSearch" type="search" value="${escapeHtml(state.rentalAssignmentSearch)}" placeholder="Search current deployment…"></div><select class="select" id="rentalAssignmentSupplier"><option value="All suppliers">All suppliers</option>${state.suppliers.filter(s=>s.status==='Active').map(s=>`<option value="${escapeHtml(s.id)}" ${state.rentalAssignmentSupplier===s.id?'selected':''}>${escapeHtml(s.name)}</option>`).join('')}</select><select class="select" id="rentalAssignmentProject"><option value="All projects">All projects</option>${state.projects.filter(p=>p.status==='Active').map(p=>`<option value="${escapeHtml(p.id)}" ${state.rentalAssignmentProject===p.id?'selected':''}>${escapeHtml(p.name)}</option>`).join('')}</select><button class="btn btn--ghost" data-assignment-reset>Reset</button></div><div class="table-wrap"><table class="data-table assignment-deployment-table"><thead><tr><th>Worker</th><th>Supplier</th><th>Project</th><th>Trade</th><th>Rate</th><th>Effective Since</th><th>Actions</th></tr></thead><tbody>${rows.length?rows.map(({worker,supplier,snapshot})=>`<tr><td><button class="entity-link entity-link--stack" data-open-rental-worker="${escapeHtml(worker.id)}"><strong>${escapeHtml(worker.name)}</strong><span>${escapeHtml(rentalWorkerCode(worker))}</span></button></td><td>${supplier?`<button class="entity-link" data-open-supplier="${escapeHtml(supplier.id)}">${escapeHtml(supplier.name)}</button>`:'—'}</td><td>${snapshot.project?`<button class="entity-link entity-link--stack" data-open-project="${escapeHtml(snapshot.project.id)}"><strong>${escapeHtml(snapshot.project.name)}</strong><span>${escapeHtml(snapshot.project.code)}</span></button>`:'—'}</td><td><strong>${escapeHtml(snapshot.trade)}</strong></td><td>${escapeHtml(snapshot.rate)}</td><td>${escapeHtml(snapshot.since?rentalDisplayDate(snapshot.since):'—')}</td><td><div class="assignment-inline-actions">${worker.nextAssignmentId ? `<button class="is-danger" data-rental-worker-action="cancel" data-worker-id="${escapeHtml(worker.id)}">Cancel scheduled</button>` : `<button data-rental-worker-action="transfer" data-worker-id="${escapeHtml(worker.id)}">Transfer</button><button data-rental-worker-action="trade" data-worker-id="${escapeHtml(worker.id)}">Trade</button><button data-rental-worker-action="rate" data-worker-id="${escapeHtml(worker.id)}">Rate</button><button class="is-danger" data-rental-worker-action="release" data-worker-id="${escapeHtml(worker.id)}">Release</button>`}</div></td></tr>`).join(''):`<tr><td colspan="7"><div class="table-empty"><strong>No active assignments match these filters.</strong><span>Reset filters or assign an available supplier worker.</span></div></td></tr>`}</tbody></table></div></section>`;
  }

  function rentalAssignmentPoolTemplate() {
    const q = state.rentalAssignmentSearch.trim().toLowerCase();
    const rows = state.rentalWorkers.filter(worker => ['Available','Inactive'].includes(worker.status)).map(worker => {
      const history = rentalAssignmentsFor(worker);
      const last = [...history].reverse().find(item => item.kind === 'assignment');
      return { worker, supplier:rentalWorkerSupplier(worker), last };
    }).filter(row => {
      const supplierMatch = state.rentalAssignmentSupplier === 'All suppliers' || row.worker.supplierId === state.rentalAssignmentSupplier;
      const text = `${row.worker.name} ${rentalWorkerCode(row.worker)} ${row.supplier?.name || ''} ${row.worker.trade} ${row.worker.status} ${row.last?.projectName || ''}`.toLowerCase();
      return supplierMatch && (!q || text.includes(q));
    });
    return `<section class="panel panel--flush"><div class="panel__head panel__head--padded assignment-panel-head"><div><h2>Supplier worker pool</h2><p>Released and available workers remain permanent master records and can be assigned again without duplication.</p></div><div class="assignment-panel-count"><strong>${rows.filter(r=>r.worker.status==='Available').length}</strong><span>available now</span></div></div><div class="assignment-filterbar assignment-filterbar--pool"><div class="search-field assignment-search">${icon('search')}<input id="rentalAssignmentSearch" type="search" value="${escapeHtml(state.rentalAssignmentSearch)}" placeholder="Search available or inactive workers…"></div><select class="select" id="rentalAssignmentSupplier"><option value="All suppliers">All suppliers</option>${state.suppliers.filter(s=>s.status==='Active').map(s=>`<option value="${escapeHtml(s.id)}" ${state.rentalAssignmentSupplier===s.id?'selected':''}>${escapeHtml(s.name)}</option>`).join('')}</select><button class="btn btn--ghost" data-assignment-reset>Reset</button></div><div class="table-wrap"><table class="data-table"><thead><tr><th>Worker</th><th>Supplier</th><th>Trade</th><th>Current Rate</th><th>Last Project</th><th>Status</th><th>Available Since</th><th></th></tr></thead><tbody>${rows.length?rows.map(({worker,supplier,last})=>`<tr><td><button class="entity-link entity-link--stack" data-open-rental-worker="${escapeHtml(worker.id)}"><strong>${escapeHtml(worker.name)}</strong><span>${escapeHtml(rentalWorkerCode(worker))}</span></button></td><td>${supplier?`<button class="entity-link" data-open-supplier="${escapeHtml(supplier.id)}">${escapeHtml(supplier.name)}</button>`:'—'}</td><td>${escapeHtml(worker.trade || '—')}</td><td>${escapeHtml(rentalWorkerRate(worker))}</td><td>${last?.projectId?`<button class="entity-link" data-open-project="${escapeHtml(last.projectId)}">${escapeHtml(last.projectName || 'Project')}</button>`:'—'}</td><td>${statusBadge(worker.status || 'Available')}</td><td>${escapeHtml(worker.since?rentalDisplayDate(rentalFriendlyToIso(worker.since)||worker.since):'—')}</td><td>${worker.status==='Available'||worker.status==='Released'?`<button class="btn btn--secondary btn--sm" data-rental-worker-action="assign" data-worker-id="${escapeHtml(worker.id)}">Assign</button>`:`<button class="text-link" data-open-rental-worker="${escapeHtml(worker.id)}">View profile</button>`}</td></tr>`).join(''):`<tr><td colspan="8"><div class="table-empty"><strong>No supplier-pool workers match this filter.</strong><span>Released workers appear here when returned to the supplier pool.</span></div></td></tr>`}</tbody></table></div></section>`;
  }

  function rentalAssignmentsTemplate() {
    const all = rentalAssignmentActivityRows();
    const integrity = rentalAssignmentIntegrity();
    const assigned = state.rentalWorkers.filter(worker=>worker.status==='Assigned').length;
    const available = state.rentalWorkers.filter(worker=>worker.status==='Available').length;
    const transfers = all.filter(row=>row.type==='Project transfer').length;
    const changes = all.filter(row=>['Trade change','Rate change'].includes(row.type)).length;
    const releases = all.filter(row=>row.type==='Release').length;
    let content = rentalAssignmentActivityTemplate();
    if (state.rentalAssignmentTab === 'deployment') content = rentalAssignmentDeploymentTemplate();
    else if (state.rentalAssignmentTab === 'pool') content = rentalAssignmentPoolTemplate();
    return `<section class="page rental-assignments-page">
      <div class="page-head rental-assignment-head"><div class="page-head__copy"><span class="eyebrow">Rental Workforce · Assignment Control</span><h1>Assignment Lifecycle</h1><p>Control project deployment without duplicating workers: assign, transfer, change trade/rate, release back to the supplier pool and preserve every effective-dated record.</p></div><div class="page-head__actions"><button class="btn btn--secondary" data-route-link="rental-workforce">Worker Master</button><button class="btn btn--secondary" data-route-link="rental-onboarding">Bulk Onboard</button><button class="btn btn--primary" data-rental-available-jump>${icon('plus')} Assign Available Worker</button></div></div>
      <div class="assignment-summary-strip"><div><span>Deployed now</span><strong>${assigned}</strong><small>Open project assignments</small></div><button data-assignment-tab-jump="pool"><span>Available pool</span><strong>${available}</strong><small>Ready to reassign</small></button><button data-assignment-type-jump="Project transfer"><span>Transfers</span><strong>${transfers}</strong><small>Preserved project moves</small></button><button data-assignment-type-jump="Trade / rate changes"><span>Trade / rate changes</span><strong>${changes}</strong><small>Effective revisions</small></button><button data-assignment-type-jump="Release"><span>Releases</span><strong>${releases}</strong><small>Returned / inactive</small></button></div>
      <div class="assignment-workspace-tabs"><button class="${state.rentalAssignmentTab==='activity'?'is-active':''}" data-assignment-tab="activity"><span>Activity Log</span><small>All lifecycle events</small></button><button class="${state.rentalAssignmentTab==='deployment'?'is-active':''}" data-assignment-tab="deployment"><span>Current Deployment</span><small>Who is working where</small></button><button class="${state.rentalAssignmentTab==='pool'?'is-active':''}" data-assignment-tab="pool"><span>Supplier Pool</span><small>Available & released</small></button></div>
      ${content}
      <div class="assignment-footer-grid"><section class="detail-card"><div class="detail-card__head"><h3>History integrity</h3>${integrity.length?'<span class="status status--danger"><span></span>Needs review</span>':'<span class="status status--success"><span></span>Healthy</span>'}</div>${integrity.length?`<div class="assignment-integrity-list">${integrity.slice(0,4).map(issue=>`<button data-open-rental-worker="${escapeHtml(issue.worker.id)}"><strong>${escapeHtml(issue.worker.name)}</strong><span>${escapeHtml(issue.message)}</span></button>`).join('')}</div>`:`<p>Each worker has at most one open project assignment, effective dates are present, and closed records do not overlap the next assignment.</p>`}</section><section class="detail-card"><div class="detail-card__head"><h3>Lifecycle rule</h3></div><div class="rental-rule-list"><div><strong>Transfer</strong><span>Close old project the day before the new assignment starts.</span></div><div><strong>Trade / Rate</strong><span>Same project, new effective record; do not rewrite prior payroll.</span></div><div><strong>Release</strong><span>Close project assignment and return the worker to supplier pool or mark inactive.</span></div></div></section><section class="detail-card"><div class="detail-card__head"><h3>Audit scope</h3></div><p>Every assignment lifecycle action is persisted server-side and written to the append-only company audit trail with actor and request context.</p></section></div>
    </section>`;
  }

  function rentalWorkforceTemplate() {
    const rows = rentalWorkforceRows();
    const assigned = state.rentalWorkers.filter(worker => worker.status === 'Assigned').length;
    const available = state.rentalWorkers.filter(worker => worker.status === 'Available').length;
    const scheduled = state.rentalWorkers.filter(worker => worker.status === 'Scheduled').length;
    const activeSupplierIds = new Set(state.rentalWorkers.filter(worker => ['Assigned','Available'].includes(worker.status)).map(worker => worker.supplierId).filter(Boolean));
    const activeProjectIds = new Set(state.rentalWorkers.filter(worker => worker.status === 'Assigned' && worker.projectId).map(worker => worker.projectId));
    const trades = [...new Set(state.rentalWorkers.map(worker => worker.trade).filter(Boolean))].sort((a,b) => a.localeCompare(b));
    const activeMasters = state.rentalWorkers.filter(worker => worker.masterStatus === 'Active').length;
    const filtered = rows.length !== state.rentalWorkers.length;

    return `<section class="page rental-workforce-page">
      <div class="page-head rental-workforce-head">
        <div class="page-head__copy">
          <span class="eyebrow">Rental Workforce · ${escapeHtml(state.period)}</span>
          <h1>Rental Workforce</h1>
          <p>One permanent worker master per person, connected to a manpower supplier and an effective project assignment instead of repeating names in monthly spreadsheets.</p>
        </div>
        <div class="page-head__actions">
          <button class="btn btn--secondary" data-route-link="suppliers">Manpower Suppliers</button>
          <button class="btn btn--secondary" data-route-link="projects">Projects</button>
          <button class="btn btn--secondary" data-route-link="rental-assignments">Assignment Activity</button>
          <button class="btn btn--secondary" data-route-link="rental-onboarding">Bulk Onboard</button>
          <button class="btn btn--primary" data-quick-add="rental-worker">${icon('plus')} Add Worker</button>
        </div>
      </div>

      <div class="rental-summary-strip">
        <button type="button" class="rental-summary-item ${state.rentalStatus === 'All' ? 'is-selected' : ''}" data-rental-summary="All"><span>Total workers</span><strong>${state.rentalWorkers.length}</strong><small>${activeMasters} active worker masters</small></button>
        <button type="button" class="rental-summary-item ${state.rentalStatus === 'Assigned' ? 'is-selected' : ''}" data-rental-summary="Assigned"><span>Assigned now</span><strong>${assigned}</strong><small>Working on active projects</small></button>
        <button type="button" class="rental-summary-item ${state.rentalStatus === 'Available' ? 'is-selected' : ''}" data-rental-summary="Available"><span>Available</span><strong>${available}</strong><small>Supplier worker pool</small></button>
        <div class="rental-summary-item"><span>Active suppliers</span><strong>${activeSupplierIds.size}</strong><small>Linked manpower companies</small></div>
        <div class="rental-summary-item"><span>Active projects</span><strong>${activeProjectIds.size}</strong><small>Current deployments</small></div>
      </div>

      <section class="panel panel--flush rental-directory-panel">
        <div class="panel__head panel__head--padded rental-directory-head">
          <div><h2>Worker master</h2><p>Filter the complete rental roster by assignment, supplier, project, trade or rate type.</p></div>
          <div class="rental-directory-meta"><strong>${rows.length}</strong><span>${filtered ? 'matching workers' : 'workers in master'}</span></div>
        </div>

        <div class="rental-filterbar">
          <div class="search-field rental-search">${icon('search')}<input id="rentalSearch" type="search" value="${escapeHtml(state.rentalSearch)}" placeholder="Search worker, ID, supplier, project or trade…"></div>
          <select class="select" id="rentalSupplierFilter"><option value="All suppliers">All suppliers</option>${state.suppliers.filter(s => !s.deleted).map(s => `<option value="${escapeHtml(s.id)}" ${state.rentalSupplier === s.id ? 'selected' : ''}>${escapeHtml(s.name)}${s.status !== 'Active' ? ` · ${escapeHtml(s.status)}` : ''}</option>`).join('')}</select>
          <select class="select" id="rentalProjectFilter"><option value="All projects">All projects</option><option value="Unassigned / available" ${state.rentalProject === 'Unassigned / available' ? 'selected' : ''}>Unassigned / available</option>${state.projects.filter(p => p.status === 'Active').map(p => `<option value="${escapeHtml(p.id)}" ${state.rentalProject === p.id ? 'selected' : ''}>${escapeHtml(p.name)}</option>`).join('')}</select>
          <select class="select" id="rentalTradeFilter"><option>All trades</option>${trades.map(trade => `<option ${state.rentalTrade === trade ? 'selected' : ''}>${escapeHtml(trade)}</option>`).join('')}</select>
          <select class="select" id="rentalRateFilter"><option>All rate types</option>${['Hourly','Daily','Monthly'].map(rate => `<option ${state.rentalRateType === rate ? 'selected' : ''}>${rate}</option>`).join('')}</select>
          <button class="btn btn--ghost" data-rental-reset>Reset</button>
        </div>

        <div class="rental-status-tabs" role="tablist" aria-label="Rental worker assignment status">
          ${['All','Assigned','Scheduled','Available','Inactive','Terminated','Archived'].map(status => {
            const count = status === 'All' ? state.rentalWorkers.length : state.rentalWorkers.filter(worker => worker.status === status).length;
            return `<button type="button" class="${state.rentalStatus === status ? 'is-active' : ''}" data-rental-status="${status}"><span>${status}</span><em>${count}</em></button>`;
          }).join('')}
        </div>

        <div class="table-wrap rental-table-wrap"><table class="data-table rental-worker-table"><thead><tr><th>Worker</th><th>Manpower Supplier</th><th>Current Project</th><th>Trade</th><th>Rate</th><th>Since</th><th>Status</th><th></th></tr></thead><tbody>
          ${rows.length ? rows.map(worker => {
            const supplier = rentalWorkerSupplier(worker);
            const project = rentalWorkerCurrentProject(worker);
            return `<tr>
              <td><button class="entity-link entity-link--stack" data-open-rental-worker="${escapeHtml(worker.id)}"><strong>${escapeHtml(worker.name)}</strong><span>${escapeHtml(rentalWorkerCode(worker))}</span></button></td>
              <td>${supplier ? `<button class="entity-link entity-link--stack" data-open-supplier="${escapeHtml(supplier.id)}"><strong>${escapeHtml(supplier.name)}</strong><span>${escapeHtml(supplier.code)}</span></button>` : `<span class="table-secondary">Supplier not linked</span>`}</td>
              <td>${project ? `<button class="entity-link entity-link--stack" data-open-project="${escapeHtml(project.id)}"><strong>${escapeHtml(project.name)}</strong><span>${escapeHtml(project.code)}</span></button>` : `<div class="table-primary">${worker.archived ? 'Archived' : worker.status === 'Terminated' ? 'Terminated' : worker.status === 'Inactive' ? 'Inactive / unassigned' : 'Available / unassigned'}</div><div class="table-secondary">No active project</div>`}</td>
              <td><div class="table-primary">${escapeHtml(worker.trade || '—')}</div>${worker.changed ? '<div class="table-secondary">Role changed in source period</div>' : ''}</td>
              <td><div class="rate-cell"><strong>${escapeHtml(rentalWorkerRate(worker))}</strong><span>${escapeHtml(worker.rateType || 'Rate')}</span></div></td>
              <td>${escapeHtml(worker.since || '—')}</td>
              <td>${statusBadge(worker.status || 'Available')}</td>
              <td class="table-actions"><button class="icon-btn icon-btn--sm" data-rental-worker-menu="${escapeHtml(worker.id)}" aria-label="Worker actions">${icon('more')}</button></td>
            </tr>`;
          }).join('') : `<tr><td colspan="8"><div class="table-empty"><strong>No workers match these filters.</strong><span>Reset the filters or add a new rental worker from a managed manpower supplier.</span></div></td></tr>`}
        </tbody></table></div>
      </section>

      <div class="rental-workforce-footer-grid">
        <section class="detail-card"><div class="detail-card__head"><h3>Master-data rule</h3><span class="status status--success"><span></span>Controlled</span></div><div class="rental-rule-list"><div><strong>Supplier</strong><span>Selected from Manpower Suppliers; never repeated free text.</span></div><div><strong>Project</strong><span>Selected from Projects; transfer creates history instead of overwriting.</span></div><div><strong>Worker</strong><span>Created once and reused across every project assignment.</span></div></div></section>
        <section class="detail-card"><div class="detail-card__head"><h3>Current availability</h3><button class="text-link" data-rental-status-jump="Available">View available</button></div><div class="rental-availability"><strong>${available}</strong><span>workers currently available for assignment</span>${scheduled ? `<small>${scheduled} future assignment${scheduled === 1 ? '' : 's'} scheduled</small>` : '<small>No future assignments currently scheduled.</small>'}</div></section>
        <section class="detail-card"><div class="detail-card__head"><h3>Master-data boundary</h3></div><p class="rental-source-copy">Worker identity and supplier ownership are maintained here. Project, trade and commercial-rate history are effective-dated assignment records and are managed separately.</p></section>
      </div>
    </section>`;
  }

  function rentalNormalize(value) {
    return String(value || '').trim().toLowerCase().replace(/\s+/g, ' ');
  }

  function rentalOnboardingDefaults() {
    const onboarding = state.rentalOnboarding;
    if (!onboarding.defaultSupplierId) onboarding.defaultSupplierId = state.suppliers.find(item => item.status === 'Active')?.id || '';
    if (onboarding.defaultSupplierId && !state.suppliers.some(item => item.id === onboarding.defaultSupplierId && item.status === 'Active')) onboarding.defaultSupplierId = '';
    return onboarding;
  }

  function rentalOnboardingNewRow(seed = {}) {
    const defaults = rentalOnboardingDefaults();
    return {
      rowId: seed.rowId || `stage-${crypto.randomUUID()}`,
      workerCode: String(seed.workerCode || '').trim(),
      name: String(seed.name || '').trim(),
      nationalId: String(seed.nationalId || '').trim(),
      phone: String(seed.phone || '').trim(),
      supplierId: seed.supplierId === undefined ? defaults.defaultSupplierId : seed.supplierId,
      status: seed.status === 'Inactive' ? 'Inactive' : 'Active',
      notes: String(seed.notes || '').trim(),
      ignored: Boolean(seed.ignored)
    };
  }

  function rentalOnboardingHeaderIndex(headers, aliases) {
    const normalized = headers.map(item => rentalNormalize(item).replace(/[^a-z0-9]+/g,' '));
    return normalized.findIndex(header => aliases.some(alias => header === alias || header.includes(alias)));
  }

  function rentalOnboardingParse(text) {
    const clean = String(text || '').replace(/\r/g,'').trim();
    if (!clean) return [];
    const lines = clean.split('\n').map(line => line.trimEnd()).filter(Boolean);
    const delimiter = lines.some(line => line.includes('\t')) ? '\t' : ',';
    const parseLine = line => {
      if (delimiter === '\t') return line.split('\t').map(cell => cell.trim());
      const cells=[]; let cur=''; let quoted=false;
      for (let i=0;i<line.length;i++) {
        const ch=line[i];
        if (ch==='"') { if (quoted && line[i+1]==='"') { cur+='"'; i++; } else quoted=!quoted; }
        else if (ch===',' && !quoted) { cells.push(cur.trim()); cur=''; }
        else cur+=ch;
      }
      cells.push(cur.trim()); return cells;
    };
    const matrix = lines.map(parseLine);
    const first = matrix[0].map(item => rentalNormalize(item));
    const looksHeader = first.some(item => /name|worker|iqama|national|phone|mobile|supplier|status|note/.test(item));
    let idx={code:0,name:1,nationalId:2,phone:3,supplier:4,status:5,notes:6}, start=0;
    if (looksHeader) {
      const headers=matrix[0], find=(aliases,fallback=-1)=>{ const i=rentalOnboardingHeaderIndex(headers,aliases); return i>=0?i:fallback; };
      idx={
        code:find(['worker id','worker code','worker number','id','code']),
        name:find(['full name','worker name','name']),
        nationalId:find(['iqama','national id','national','identity']),
        phone:find(['phone','mobile','contact']),
        supplier:find(['supplier code','supplier','manpower supplier']),
        status:find(['status']),
        notes:find(['notes','note','remarks','remark'])
      };
      start=1;
    }
    return matrix.slice(start).filter(c=>c.some(v=>String(v||'').trim())).map(cells=>{
      const get=i=>i>=0?String(cells[i]||'').trim():'';
      const supplierText=get(idx.supplier);
      const supplier=state.suppliers.find(item=>rentalNormalize(item.code)===rentalNormalize(supplierText) || rentalNormalize(item.name)===rentalNormalize(supplierText));
      return rentalOnboardingNewRow({
        workerCode:get(idx.code), name:get(idx.name), nationalId:get(idx.nationalId), phone:get(idx.phone),
        supplierId:supplier?.id || (supplierText ? '' : state.rentalOnboarding.defaultSupplierId),
        status:/inactive/i.test(get(idx.status))?'Inactive':'Active', notes:get(idx.notes)
      });
    });
  }

  function rentalOnboardingValidateRow(row, allRows = state.rentalOnboarding.rows) {
    const blockers=[], warnings=[];
    const supplier=state.suppliers.find(item=>item.id===row.supplierId && item.status==='Active');
    const code=rentalNormalize(row.workerCode), name=rentalNormalize(row.name), nationalId=rentalNormalize(row.nationalId);
    if (!name) blockers.push('Worker name is required.');
    if (!supplier) blockers.push('Select an active manpower supplier.');
    if (!['Active','Inactive'].includes(row.status)) blockers.push('Choose a valid worker status.');
    const existingCode=code&&state.rentalWorkers.find(w=>rentalNormalize(rentalWorkerCode(w))===code);
    const existingNational=nationalId&&state.rentalWorkers.find(w=>rentalNormalize(w.nationalId)===nationalId);
    if (existingCode) blockers.push(`Worker ID already exists: ${rentalWorkerCode(existingCode)}.`);
    if (existingNational) blockers.push(`Iqama/National ID already belongs to ${existingNational.name}.`);
    const stagedDuplicate=allRows.find(other=>other.rowId!==row.rowId&&!other.ignored&&((code&&rentalNormalize(other.workerCode)===code)||(nationalId&&rentalNormalize(other.nationalId)===nationalId)));
    if (stagedDuplicate) blockers.push('Duplicate Worker ID or National ID within staged rows.');
    if (!row.nationalId) warnings.push('Iqama/National ID is blank; duplicate detection is limited.');
    if (!row.workerCode) warnings.push('Worker ID will be generated by the server.');
    return { blockers,warnings,status:blockers.length?'Blocked':warnings.length?'Warning':'Ready' };
  }

  function rentalOnboardingStatusBadge(v) {
    if (v.status==='Blocked') return `<span class="readiness readiness--danger"><span></span>Blocked</span>`;
    if (v.status==='Warning') return `<span class="readiness readiness--warn"><span></span>Ready · warning</span>`;
    return `<span class="readiness readiness--ready"><span></span>Ready</span>`;
  }

  function rentalOnboardingTemplate() {
    const o=rentalOnboardingDefaults(), suppliers=state.suppliers.filter(i=>i.status==='Active'), rows=o.rows.filter(r=>!r.ignored), validations=rows.map(r=>rentalOnboardingValidateRow(r,rows));
    const ready=validations.filter(v=>v.status==='Ready').length, warning=validations.filter(v=>v.status==='Warning').length, blocked=validations.filter(v=>v.status==='Blocked').length;
    return `<section class="page rental-onboarding-page">
      <div class="page-head rental-onboarding-head"><div class="page-head__copy"><span class="eyebrow">Rental Workforce · Onboarding</span><h1>Add & onboard rental workers</h1><p>Create permanent rental-worker masters under managed manpower suppliers. Project, trade and rate assignments are handled separately so assignment history remains effective-dated.</p></div><div class="page-head__actions"><button class="btn btn--secondary" data-route-link="rental-workforce">Back to Workforce</button><button class="btn btn--primary" data-quick-add="rental-worker">${icon('plus')} Add Single Worker</button></div></div>
      <div class="onboarding-mode-grid"><section class="onboarding-mode-card"><span class="onboarding-mode-card__icon">1</span><div><strong>Single worker</strong><p>Create one permanent worker and link the controlled supplier master.</p></div><button class="btn btn--secondary btn--sm" data-quick-add="rental-worker">Open form</button></section><section class="onboarding-mode-card is-active"><span class="onboarding-mode-card__icon">N</span><div><strong>Bulk onboarding</strong><p>Paste rows from Excel/CSV, validate duplicates and create worker masters in one transaction.</p></div><span class="status status--success"><span></span>Active</span></section></div>
      <section class="panel panel--flush onboarding-defaults-panel"><div class="section-headline"><div><h2>1. Supplier default</h2><p>The selected supplier is applied to staged rows that do not identify another managed supplier.</p></div><span class="source-chip">Controlled master</span></div><div class="onboarding-defaults-grid">
        <div class="form-field"><label>Manpower supplier</label><div class="inline-select-action"><select class="select" id="onboardingDefaultSupplier"><option value="">Select supplier…</option>${suppliers.map(s=>`<option value="${escapeHtml(s.id)}" ${o.defaultSupplierId===s.id?'selected':''}>${escapeHtml(s.name)} · ${escapeHtml(s.code)}</option>`).join('')}</select><button class="btn btn--secondary btn--sm" data-onboarding-create-master="supplier">+ New</button></div></div>
      </div></section>
      <section class="panel panel--flush onboarding-source-panel"><div class="section-headline"><div><h2>2. Bring workers from Excel</h2><p>Copy rows directly from Excel or import a CSV file. Data is staged locally only until the server validates and creates the records.</p></div><div class="section-headline__actions"><label class="btn btn--secondary btn--sm file-button">Import CSV<input id="onboardingCsvFile" type="file" accept=".csv,text/csv" hidden></label></div></div><div class="onboarding-source-grid"><div class="onboarding-paste"><textarea class="textarea" id="onboardingPaste" placeholder="Worker ID\tFull Name\tIqama / National ID\tPhone\tSupplier Code\tStatus\tNotes">${escapeHtml(o.sourceText)}</textarea><div class="paste-help"><span>Headers: Worker ID, Full Name, Iqama/National ID, Phone, Supplier Code, Status, Notes.</span><button class="btn btn--primary btn--sm" data-onboarding-stage>Stage pasted rows</button></div></div><div class="onboarding-format"><strong>Import boundary</strong><ol><li>Worker ID (optional)</li><li>Full Name</li><li>Iqama / National ID</li><li>Phone</li><li>Supplier Code</li><li>Status</li><li>Notes</li></ol><p>Worker IDs may be blank and will be allocated transaction-safely by the server. Assignments, trades and rates are not imported here.</p></div></div></section>
      <section class="panel panel--flush onboarding-stage-panel"><div class="section-headline"><div><h2>3. Validate staged workers</h2><p>The server performs the authoritative validation again before creating any row. The import is all-or-nothing.</p></div><div class="onboarding-validation-summary"><span class="is-ready"><strong>${ready}</strong> ready</span><span class="is-warning"><strong>${warning}</strong> warnings</span><span class="is-blocked"><strong>${blocked}</strong> blocked</span></div></div><div class="onboarding-stage-toolbar"><button class="btn btn--secondary btn--sm" data-onboarding-add-row>${icon('plus')} Add blank row</button><button class="btn btn--ghost btn--sm" data-onboarding-apply-defaults>Apply supplier default</button><span>${rows.length} active staged row${rows.length===1?'':'s'}</span></div>
      ${rows.length?`<div class="table-wrap onboarding-table-wrap"><table class="data-table onboarding-table"><thead><tr><th>Worker</th><th>Iqama / Phone</th><th>Supplier</th><th>Status</th><th>Notes</th><th>Validation</th><th></th></tr></thead><tbody>${rows.map(row=>{const v=rentalOnboardingValidateRow(row,rows);return `<tr data-onboarding-row="${escapeHtml(row.rowId)}" class="${v.status==='Blocked'?'has-error':''}"><td><input class="table-input" data-onboarding-field="workerCode" value="${escapeHtml(row.workerCode)}" placeholder="Auto ID"><input class="table-input table-input--primary" data-onboarding-field="name" value="${escapeHtml(row.name)}" placeholder="Full name"></td><td><input class="table-input" data-onboarding-field="nationalId" value="${escapeHtml(row.nationalId)}" placeholder="Iqama / ID"><input class="table-input" data-onboarding-field="phone" value="${escapeHtml(row.phone)}" placeholder="Phone"></td><td><select class="table-select" data-onboarding-field="supplierId"><option value="">Select…</option>${suppliers.map(s=>`<option value="${escapeHtml(s.id)}" ${row.supplierId===s.id?'selected':''}>${escapeHtml(s.name)}</option>`).join('')}</select></td><td><select class="table-select" data-onboarding-field="status">${['Active','Inactive'].map(value=>`<option ${row.status===value?'selected':''}>${value}</option>`).join('')}</select></td><td><input class="table-input" data-onboarding-field="notes" value="${escapeHtml(row.notes)}" placeholder="Optional"></td><td><div class="validation-cell">${rentalOnboardingStatusBadge(v)}${[...v.blockers,...v.warnings].slice(0,2).map(x=>`<small>${escapeHtml(x)}</small>`).join('')}${v.blockers.length+v.warnings.length>2?`<small>+${v.blockers.length+v.warnings.length-2} more</small>`:''}</div></td><td><button class="icon-btn icon-btn--sm" data-onboarding-remove-row="${escapeHtml(row.rowId)}" title="Remove row">×</button></td></tr>`;}).join('')}</tbody></table></div>`:`<div class="table-empty table-empty--card"><strong>No staged workers yet.</strong><span>Paste rows from Excel/CSV or add a blank row to start.</span><button class="btn btn--secondary btn--sm" data-onboarding-add-row>${icon('plus')} Add first row</button></div>`}
      <div class="onboarding-importbar"><div><strong>${blocked?`${blocked} row${blocked===1?'':'s'} blocked`:'Ready for server validation'}</strong><span>${blocked?'Resolve blocked rows or remove them before importing.':`${ready+warning} worker${ready+warning===1?'':'s'} will be validated and created transactionally.`}</span></div><button class="btn btn--primary" data-onboarding-import ${!rows.length||blocked?'disabled':''}>Create ${ready+warning} Worker${ready+warning===1?'':'s'}</button></div></section>
      ${o.lastImport?`<section class="source-note onboarding-complete-note">${icon('info')}<span><strong>Last import</strong>${o.lastImport.count} worker${o.lastImport.count===1?'':'s'} created · ${escapeHtml(o.lastImport.at)}.</span></section>`:''}
    </section>`;
  }

  function rentalWorkerPreviewTemplate(worker) {
    if (!worker) return `<section class="page"><div class="placeholder"><div class="placeholder__inner"><div class="placeholder__icon">RW</div><h2>Rental worker not found</h2><p>This worker master record is not available.</p><button class="btn btn--secondary" data-route-link="rental-workforce">Back to Rental Workforce</button></div></div></section>`;
    const supplier = rentalWorkerSupplier(worker);
    const snapshot = rentalWorkerCurrentSnapshot(worker);
    const sourceMetrics = rentalWorkerSettlementMetrics(worker);
    const assignmentCount = rentalAssignmentsFor(worker).filter(item => item.kind === 'assignment').length;
    const tabs = [
      ['overview','Overview'],['assignments','Assignments'],['timesheets','Timesheets'],['cost','Manpower Cost'],['advances','Advances'],['documents','Documents']
    ];
    let content = rentalWorkerOverviewTab(worker, supplier, snapshot);
    if (state.rentalWorkerTab === 'assignments') content = rentalWorkerAssignmentsTab(worker);
    else if (state.rentalWorkerTab === 'timesheets') content = rentalWorkerTimesheetsTab(worker);
    else if (state.rentalWorkerTab === 'cost') content = rentalWorkerCostTab(worker);
    else if (state.rentalWorkerTab === 'advances') content = rentalWorkerAdvancesTab(worker);
    else if (state.rentalWorkerTab === 'documents') content = rentalWorkerDocumentsTab(worker);

    return `<section class="page rental-worker-profile-page">
      <div class="profile-crumb ui-v2-payroll-profile-crumb"><button type="button" class="text-link text-link--muted" data-route-link="rental-workforce">Rental Workforce</button><span>›</span><span>${escapeHtml(rentalWorkerCode(worker))}</span></div>
      <header class="entity-header rental-worker-header">
        <div class="entity-header__identity"><span class="entity-avatar rental-worker-avatar">RW</span><div><div class="entity-title-row ui-v2-payroll-entity-title"><h1>${escapeHtml(worker.name)}</h1>${statusBadge(worker.status || 'Available')}</div><div class="entity-subline"><span>${escapeHtml(rentalWorkerCode(worker))}</span><span>·</span><span>Rental worker</span>${supplier ? `<span>·</span><button class="text-link" data-open-supplier="${escapeHtml(supplier.id)}">${escapeHtml(supplier.name)}</button>` : ''}</div></div></div>
        <div class="entity-header__actions ui-v2-payroll-entity-header__actions">${!worker.archived && snapshot.project && !worker.nextAssignmentId ? `<button class="btn btn--primary" data-rental-worker-action="transfer" data-worker-id="${escapeHtml(worker.id)}">Transfer Project</button>` : !worker.archived && worker.status === 'Available' ? `<button class="btn btn--primary" data-rental-worker-action="assign" data-worker-id="${escapeHtml(worker.id)}">Assign to Project</button>` : ''}${lifecycleActionsMenu([
          ...(!worker.archived ? [{label:'Edit worker',hint:'Update current worker master details',iconName:'edit',attrs:`data-rental-worker-action="edit" data-worker-id="${escapeHtml(worker.id)}"`}] : []),
          {label:worker.masterStatus==='Terminated'?'Worker terminated':'Manage worker status',hint:worker.masterStatus==='Terminated'?'Termination is final for this worker record':'Deactivate, reactivate, or terminate worker activity',iconName:'info',disabled:worker.archived || worker.masterStatus==='Terminated',attrs:`data-rental-master-lifecycle="worker|${escapeHtml(worker.id)}|manage"`},
          'separator',
          {label:worker.archived?'Restore from archive':'Archive worker',hint:worker.archived?'Restore previous state':'Archive immediately while retaining assignments and history',iconName:'info',attrs:`data-rental-master-lifecycle="worker|${escapeHtml(worker.id)}|${worker.archived?'restore':'archive'}"`},
          {label:'Delete',hint:'Delete with 30-day recovery; assignments and history are retained for restore',iconName:'trash',danger:true,attrs:`data-rental-master-lifecycle="worker|${escapeHtml(worker.id)}|delete"`}
        ])}</div>
      </header>
      <div class="profile-facts rental-worker-facts"><div><span>Supplier</span><strong>${escapeHtml(supplier?.name || worker.supplier || 'Not linked')}</strong></div><div><span>Current project</span><strong>${escapeHtml(snapshot.project?.name || (worker.status === 'Terminated' ? 'Terminated' : worker.status === 'Inactive' ? 'Inactive' : worker.status === 'Archived' ? 'Archived' : worker.status === 'Released' ? 'Released / unassigned' : 'Available / unassigned'))}</strong></div><div><span>Current trade</span><strong>${escapeHtml(snapshot.trade)}</strong></div><div><span>Current rate</span><strong>${escapeHtml(snapshot.rate)}</strong></div></div>
      <div class="rental-profile-kpis"><div><span>Assignments</span><strong>${assignmentCount}</strong><small>effective-dated record${assignmentCount === 1 ? '' : 's'}</small></div><div><span>Current period hours</span><strong>${sourceMetrics.hours == null ? '—' : Number(sourceMetrics.hours).toLocaleString('en-SA',{maximumFractionDigits:2})}</strong><small>${sourceMetrics.period || 'No source timesheet'}</small></div><div><span>Current period net</span><strong>${sourceMetrics.net == null ? '—' : formatCurrency(sourceMetrics.net)}</strong><small>${sourceMetrics.period || 'No settlement source'}</small></div><div><span>Worker status</span><strong class="text-value">${escapeHtml(worker.status || 'Available')}</strong><small>${snapshot.since ? `Since ${escapeHtml(rentalDisplayDate(snapshot.since))}` : 'Permanent worker master'}</small></div></div>
      <div class="tabs profile-tabs rental-worker-tabs">${tabs.map(([id,label]) => `<button type="button" class="${state.rentalWorkerTab === id ? 'is-active' : ''}" data-rental-worker-tab="${id}">${escapeHtml(label)}${id === 'assignments' ? `<span class="tab-count">${assignmentCount}</span>` : id === 'advances' && Number(rentalSourceMonth(worker)?.advance || 0) > 0 ? '<span class="tab-count">1</span>' : ''}</button>`).join('')}</div>
      ${content}
    </section>`;
  }

  function missingSupplierTemplate() {
    return `<section class="page"><div class="placeholder"><div class="placeholder__inner"><div class="placeholder__icon">${icon('supplier')}</div><h2>Supplier not found</h2><p>This manpower supplier record is not available.</p><button class="btn btn--secondary" data-route-link="suppliers">Back to Suppliers</button></div></div></section>`;
  }

  function missingProjectTemplate() {
    return `<section class="page"><div class="placeholder"><div class="placeholder__inner"><div class="placeholder__icon">${icon('project')}</div><h2>Project not found</h2><p>This project record is not available.</p><button class="btn btn--secondary" data-route-link="projects">Back to Projects</button></div></div></section>`;
  }


  function persistRentalSettlements() {}

  function rentalSettlementKey(period, projectId, supplierId) {
    return `${period}::${projectId}::${supplierId}`;
  }

  function applyRentalSettlementPayload(payload) {
    const label = payload.label || state.period;
    state.rentalSettlementContexts[label] = payload;
    state.rentalTimesheetScopes = payload.timesheetScopes || [];
    Object.keys(state.rentalSettlements).forEach(key => {
      if (state.rentalSettlements[key]?.period === label) delete state.rentalSettlements[key];
    });
    (payload.settlements || []).forEach(record => {
      state.rentalSettlements[rentalSettlementKey(record.period, record.projectId, record.supplierId)] = record;
    });
    state.rentalAdjustments = payload.adjustmentsByWorker || {};
    state.supplierPayments = {};
    (payload.payments || []).forEach(payment => {
      state.supplierPayments[payment.supplierId] ||= [];
      state.supplierPayments[payment.supplierId].push(payment);
    });
    state.rentalSettlementLoadedPeriods.add(label);
  }

  async function loadRentalSettlementContext(period = state.period, { render = true } = {}) {
    if (state.rentalSettlementLoadingPeriod === period) return;
    state.rentalSettlementLoadingPeriod = period;
    try {
      const payload = await appApi(`/api/rental/settlements/?period=${encodeURIComponent(periodKeyFromLabel(period))}`);
      applyRentalSettlementPayload(payload);
      if (render) renderRoute();
    } catch (error) {
      showToast('Could not load rental settlements', error.message);
    } finally {
      if (state.rentalSettlementLoadingPeriod === period) state.rentalSettlementLoadingPeriod = null;
    }
  }

  function rentalSettlementStage(status) {
    return { Draft:0, Calculated:1, Review:2, Approved:3, 'Payment Processing':4, 'Partially Paid':5, Paid:6, Closed:7 }[status] ?? 0;
  }

  function rentalSettlementStatusBadge(status) {
    const tone = ['Approved','Paid','Closed'].includes(status) ? 'success' : ['Review','Calculated','Payment Processing','Partially Paid'].includes(status) ? 'warning' : 'neutral';
    return `<span class="status status--${tone}"><span></span>${escapeHtml(status || 'Draft')}</span>`;
  }

  function rentalTimesheetScope(projectId, period = state.period) {
    const context = state.rentalSettlementContexts[period];
    return (context?.timesheetScopes || []).find(item => item.projectId === projectId) || null;
  }

  function rentalSettlementRelevantWorkers(projectId, supplierId = 'All suppliers', period = state.period) {
    const groups = Object.values(state.rentalSettlements || {}).filter(row => row.period === period && row.projectId === projectId && (supplierId === 'All suppliers' || row.supplierId === supplierId));
    const workerIds = new Set(groups.flatMap(group => (group.rows || []).map(row => row.workerId)));
    return state.rentalWorkers.filter(worker => workerIds.has(worker.id));
  }

  function rentalSettlementSuppliers(projectId, period = state.period) {
    const scope = rentalTimesheetScope(projectId, period);
    const ids = new Set((scope?.suppliers || []).map(item => item.id));
    Object.values(state.rentalSettlements || {}).filter(row => row.period === period && row.projectId === projectId).forEach(row => ids.add(row.supplierId));
    return state.suppliers.filter(supplier => ids.has(supplier.id));
  }

  function rentalSettlementLiveRows(projectId, supplierId = 'All suppliers', period = state.period) {
    const groups = Object.values(state.rentalSettlements || {}).filter(row => row.period === period && row.projectId === projectId && (supplierId === 'All suppliers' || row.supplierId === supplierId));
    return groups.flatMap(group => (group.rows || []).map(row => ({ ...row, supplierId:group.supplierId, supplier:group.supplier })));
  }
  function groupByWorkerSupplier(workerId) {
    return state.rentalWorkers.find(worker => worker.id === workerId)?.supplierId || '';
  }

  function groupSupplierName(workerId) {
    const supplierId = groupByWorkerSupplier(workerId);
    return state.suppliers.find(item => item.id === supplierId)?.name || '';
  }

  function rentalSettlementTotals(rows) {
    return rows.reduce((a,row) => {
      a.workers += 1;
      a.hours += Number(row.hours || 0);
      a.otHours += Number(row.otHours || 0);
      a.base += Number(row.base || 0);
      a.otAmount += Number(row.otAmount || 0);
      a.gross += Number(row.gross || 0);
      a.adjustmentEarnings += Number(row.adjustmentEarnings || 0);
      a.adjustments += Number(row.adjustments || 0);
      a.net += Number(row.net || 0);
      return a;
    }, { workers:0, hours:0, otHours:0, base:0, otAmount:0, gross:0, adjustmentEarnings:0, adjustments:0, net:0, missing:0 });
  }

  function rentalSettlementRecord(period, projectId, supplierId) {
    return state.rentalSettlements[rentalSettlementKey(period, projectId, supplierId)] || null;
  }

  function rentalSettlementRecordOrDraft(period, projectId, supplierId) {
    const existing = rentalSettlementRecord(period, projectId, supplierId);
    if (existing) return existing;
    const supplier = state.suppliers.find(item => item.id === supplierId);
    return {
      id:null, number:null, period, projectId, supplierId, supplier:supplier?.name || '', status:'Draft', statusValue:'draft', rows:[],
      totals:{workers:0,hours:0,workDays:0,otHours:0,base:0,otAmount:0,gross:0,adjustmentEarnings:0,adjustments:0,net:0,paid:0,processing:0,outstanding:0,available:0},
      sourceTimesheetStatus:rentalTimesheetScope(projectId, period)?.status || 'Not started', preview:true
    };
  }

  function rentalSettlementCurrentGroups() {
    const projectId = state.rentalSettlementProject;
    if (!projectId) return [];
    const suppliers = state.rentalSettlementSupplier === 'All suppliers'
      ? rentalSettlementSuppliers(projectId, state.period)
      : state.suppliers.filter(item => item.id === state.rentalSettlementSupplier);
    return suppliers.map(supplier => rentalSettlementRecordOrDraft(state.period, projectId, supplier.id));
  }

  function rentalSettlementHistoryRows() {
    return Object.values(state.rentalSettlements || {}).sort((a,b) => String(b.period).localeCompare(String(a.period)) || String(a.number || '').localeCompare(String(b.number || '')));
  }

  function rentalSettlementGroupStatus(groups) {
    if (!groups.length) return 'Draft';
    return groups.reduce((status,group) => rentalSettlementStage(group.status) < rentalSettlementStage(status) ? group.status : status, groups[0].status || 'Draft');
  }

  function rentalProjectHasSettlementSnapshot(period, projectId) {
    return Object.values(state.rentalSettlements || {}).some(record => record.period === period && record.projectId === projectId && rentalSettlementStage(record.status) >= rentalSettlementStage('Calculated'));
  }

  function rentalSettlementHasDrift() { return false; }

  function rentalSettlementReadiness(groups) {
    const projectIds = [...new Set(groups.map(group => group.projectId))];
    const statuses = projectIds.map(projectId => ({ projectId, status:rentalTimesheetScope(projectId, state.period)?.status || rentalTimesheetStatus(state.period, projectId) || 'Not started' }));
    return { ready: statuses.length > 0 && statuses.every(item => item.status === 'Locked'), statuses };
  }

  async function progressRentalSettlement(nextStatus) {
    const groups = rentalSettlementCurrentGroups();
    if (!groups.length) { showToast('No settlement scope','Choose a project with a locked rental timesheet and supplier workers.'); return; }
    try {
      let payload;
      if (nextStatus === 'Calculated') {
        const readiness = rentalSettlementReadiness(groups);
        if (!readiness.ready) {
          const pending = readiness.statuses.map(item => `${state.projects.find(p=>p.id===item.projectId)?.name || 'Project'} (${item.status})`).join(', ');
          showToast('Locked timesheet required', `Settlement calculation requires the locked project timesheet. ${pending}`);
          return;
        }
        payload = await appApi('/api/rental/settlements/calculate/', { method:'POST', body:{ period:periodKeyFromLabel(), project_id:state.rentalSettlementProject } });
      } else if (nextStatus === 'Review') {
        payload = await appApi('/api/rental/settlements/workflow/', { method:'POST', body:{ period:periodKeyFromLabel(), project_id:state.rentalSettlementProject, action:'submit' } });
      } else if (nextStatus === 'Approved') {
        if (!window.confirm('Approve these supplier settlement snapshots? Approved settlements cannot be recalculated or edited.')) return;
        payload = await appApi('/api/rental/settlements/workflow/', { method:'POST', body:{ period:periodKeyFromLabel(), project_id:state.rentalSettlementProject, action:'approve', confirmed:true } });
      } else return;
      applyRentalSettlementPayload(payload); renderRoute();
      showToast(`Settlement ${nextStatus.toLowerCase()}`, `${state.period} supplier settlement state was updated by the server.`);
    } catch (error) { showToast('Settlement action blocked', error.message); }
  }

  async function returnRentalSettlementForChanges() {
    const reason = window.prompt('Enter the finance correction reason for returning this settlement:');
    if (!reason?.trim()) return;
    try {
      const payload = await appApi('/api/rental/settlements/workflow/', { method:'POST', body:{ period:periodKeyFromLabel(), project_id:state.rentalSettlementProject, action:'return', reason:reason.trim() } });
      applyRentalSettlementPayload(payload); renderRoute();
      showToast('Settlement returned', 'The Review settlement is Calculated again and must be recalculated after source changes.');
    } catch (error) { showToast('Settlement return blocked', error.message); }
  }

  async function closeRentalSettlementPeriod() {
    if (!window.confirm('Close this fully paid project settlement period? Closed settlements remain immutable unless a paid supplier payment is later reversed.')) return;
    try {
      const payload = await appApi('/api/rental/settlements/workflow/', { method:'POST', body:{ period:periodKeyFromLabel(), project_id:state.rentalSettlementProject, action:'close' } });
      applyRentalSettlementPayload(payload); renderRoute();
      showToast('Settlement period closed', `${state.period} supplier settlements for this project are closed.`);
    } catch (error) { showToast('Settlement close blocked', error.message); }
  }

  function rentalSettlementWorkerSegments(worker, period = state.period, projectId = state.rentalSettlementProject) {
    const group = rentalSettlementRecord(period, projectId, worker?.supplierId);
    const row = (group?.rows || []).find(item => item.workerId === worker?.id);
    return row?.rateLines || [];
  }

  function openRentalSettlementWorkerDrawer(workerId, projectId) {
    const worker = rentalWorkerById(workerId);
    if (!worker) return;
    const group = rentalSettlementRecord(state.period, projectId, worker.supplierId);
    const row = (group?.rows || []).find(item => item.workerId === workerId);
    if (!row) { showToast('Settlement snapshot required','Calculate the locked project timesheet before opening a financial breakdown.'); return; }
    const segments = row.rateLines || [];
    const adjustments = row.adjustmentLines || [];
    state.drawerType='rental-settlement-worker'; state.drawerContext={workerId,projectId};
    drawerSave.hidden=true; drawerTitle.textContent=`${worker.name} · Settlement breakdown`;
    drawerBody.innerHTML=`
      <section class="form-section"><div class="form-section__head"><strong>Server settlement snapshot</strong><span>${escapeHtml(state.period)} · ${escapeHtml(state.projects.find(p=>p.id===projectId)?.name || 'Project')}</span></div>
        <div class="settlement-drawer-summary ui-v2-payroll-rental-settlement-drawer-summary"><div><span>Regular hours</span><strong>${Number(row.hours||0).toLocaleString('en-SA',{maximumFractionDigits:2})}</strong></div><div><span>Base</span><strong>${formatCurrency(row.base||0)}</strong></div><div><span>OT</span><strong>${formatCurrency(row.otAmount||0)}</strong></div><div><span>Adjustment earnings</span><strong>${formatCurrency(row.adjustmentEarnings||0)}</strong></div><div><span>Deductions</span><strong>− ${formatCurrency(row.adjustments||0)}</strong></div><div class="is-total"><span>Net</span><strong>${formatCurrency(row.net||0)}</strong></div></div>
      </section>
      <section class="form-section"><div class="form-section__head"><strong>Effective commercial segments</strong><span>Copied from the locked rental timesheet snapshot.</span></div>
        <div class="settlement-segment-list ui-v2-prs-settlement-segment-list">${segments.map(segment => `<div class="settlement-segment ui-v2-prs-settlement-segment"><div><strong>${escapeHtml(segment.trade)}</strong><span>${escapeHtml(paymentDateDisplay(segment.effectiveFrom))} → ${escapeHtml(paymentDateDisplay(segment.effectiveTo))} · ${escapeHtml(segment.rateType)} ${formatCurrency(segment.rate)}</span></div><div><span>${segment.rateType==='Hourly'?`${Number(segment.regularHours||0).toLocaleString()} h`:segment.rateType==='Daily'?`${segment.billableDays} billable days`:`${segment.calendarDays} calendar days`}</span><strong>${formatCurrency(segment.base)}</strong></div></div>`).join('') || '<div class="empty-inline">No commercial segments in this snapshot.</div>'}</div>
      </section>
      <section class="form-section"><div class="form-section__head"><strong>Approved adjustment snapshot</strong><span>Only approved rental adjustments are consumed.</span></div>${adjustments.length?`<div class="settlement-segment-list ui-v2-prs-settlement-segment-list">${adjustments.map(item=>`<div class="settlement-segment ui-v2-prs-settlement-segment"><div><strong>${escapeHtml(item.type)}</strong><span>${escapeHtml(item.reason)}${item.reference?` · ${escapeHtml(item.reference)}`:''}</span></div><div><span>${item.effect==='earning'?'Adds':'Deducts'}</span><strong>${formatCurrency(item.amount)}</strong></div></div>`).join('')}</div>`:'<div class="empty-inline">No approved adjustments were included.</div>'}</section>
      <section class="source-note">${icon('info')}<span><strong>Calculation trace</strong>Hourly rows use recorded hours × effective rate; Daily rows use positive-work days × daily rate; Monthly rows prorate the monthly rate by assignment calendar days in the month; OT uses the locked rental-timesheet OT snapshot.</span></section>`;
    drawer.classList.add('is-open'); drawerScrim.classList.add('is-open'); drawer.setAttribute('aria-hidden','false');
  }

  function rentalSettlementWorkflow(status) {
    const steps=['Draft','Calculated','Review','Approved'];
    const current=Math.max(0,steps.indexOf(status));
    return `<div class="settlement-workflow ui-v2-payroll-rental-settlement-workflow">${steps.map((step,index)=>`<div class="settlement-workflow__step ${index<=current?'is-complete':''} ${index===current?'is-current':''}"><span>${index<current?'✓':index+1}</span><strong>${step}</strong></div>`).join('')}</div>`;
  }
  function rentalSettlementProjectView() {
    const project = state.projects.find(item => item.id === state.rentalSettlementProject);
    if (!project) return `<div class="table-empty table-empty--card ui-v2-payroll-table-empty"><strong>Select a project</strong><span>Choose a managed project with a rental timesheet for the selected month.</span></div>`;
    const suppliers = rentalSettlementSuppliers(project.id,state.period);
    if (state.rentalSettlementSupplier !== 'All suppliers' && !suppliers.some(item=>item.id===state.rentalSettlementSupplier)) state.rentalSettlementSupplier='All suppliers';
    const groups = rentalSettlementCurrentGroups();
    const rows = groups.flatMap(group => (group.rows || []).map(row=>({...row,supplierId:group.supplierId,supplier:group.supplier}))).filter(row => {
      const q=state.rentalSettlementSearch.trim().toLowerCase();
      return !q || `${row.workerCode} ${row.name} ${row.supplier} ${row.trade}`.toLowerCase().includes(q);
    });
    const totals=rentalSettlementTotals(rows);
    const groupStatus=rentalSettlementGroupStatus(groups);
    const readiness=rentalSettlementReadiness(groups);
    const approvedCount=groups.filter(group=>rentalSettlementStage(group.status)>=rentalSettlementStage('Approved')).length;
    const next = groupStatus==='Draft' ? 'Calculated' : groupStatus==='Calculated' ? 'Review' : groupStatus==='Review' ? 'Approved' : null;
    const actionLabel = next==='Calculated' ? 'Calculate Settlement' : next==='Review' ? 'Submit for Review' : next==='Approved' ? 'Approve Settlement' : ['Paid','Closed'].includes(groupStatus)?'Settlement Complete':'Settlement Approved';
    return `
      <div class="settlement-control-grid ui-v2-payroll-rental-settlement-control-grid">
        <section class="panel panel--flush settlement-lifecycle-card ui-v2-payroll-panel"><div class="panel__head panel__head--padded"><div><span class="ui-v2-prs-panel-kicker">Settlement control</span><h2>${escapeHtml(project.name)}</h2><p>${escapeHtml(state.period)} · ${groups.length} supplier snapshot${groups.length===1?'':'s'}</p></div>${rentalSettlementStatusBadge(groupStatus)}</div>
          ${rentalSettlementWorkflow(groupStatus)}
          <div class="settlement-readiness ui-v2-payroll-rental-settlement-readiness ${readiness.ready?'is-ready':'is-blocked'}">${icon(readiness.ready?'info':'clock')}<div><strong>${readiness.ready?'Locked timesheet snapshot ready':'Locked timesheet required'}</strong><span>${readiness.statuses.map(item=>`${escapeHtml(state.projects.find(p=>p.id===item.projectId)?.name || 'Project')}: ${escapeHtml(item.status)}`).join(' · ')}</span></div>${!readiness.ready?`<button class="btn btn--secondary btn--sm" data-open-rental-timesheet-project="${escapeHtml(project.id)}" data-timesheet-period="${escapeHtml(state.period)}">Open Timesheet</button>`:''}</div>
          <div class="settlement-actions ui-v2-payroll-rental-settlement-actions">${groupStatus==='Review'?`<button class="btn btn--ghost" data-settlement-return>Return for Changes</button>`:''}${groupStatus==='Paid'?`<button class="btn btn--primary" data-settlement-close>Close Project Period</button>`:`<button class="btn btn--primary" data-settlement-progress="${next||''}" ${!next || (next==='Calculated' && !readiness.ready) ? 'disabled':''}>${escapeHtml(actionLabel)}</button>`}</div>
        </section>
        <div class="ui-v2-payroll-rental-settlement-overview-stack">
          <section class="settlement-summary-grid ui-v2-payroll-rental-settlement-summary-grid"><div><span>Workers</span><strong>${totals.workers}</strong><small>${groups.length} supplier settlement${groups.length===1?'':'s'}</small></div><div><span>Regular / OT hours</span><strong>${totals.hours.toLocaleString('en-SA',{maximumFractionDigits:2})} / ${totals.otHours.toLocaleString('en-SA',{maximumFractionDigits:2})}</strong><small>Locked project snapshot</small></div><div><span>Gross manpower</span><strong>${formatCurrency(totals.gross)}</strong><small>Base + overtime</small></div><div><span>Additions / deductions</span><strong>+ ${formatCurrency(totals.adjustmentEarnings)} / − ${formatCurrency(totals.adjustments)}</strong><small>Approved rental adjustments</small></div><div class="is-total"><span>Net payable</span><strong>${formatCurrency(totals.net)}</strong><small>${approvedCount}/${groups.length} supplier snapshots approved or later</small></div></section>
          <div class="table-toolbar ui-v2-payroll-register__toolbar ui-v2-payroll-rental-settlement-filter-dock"><div class="table-toolbar__search ui-v2-filter-bar__search">${icon('search')}<input id="rentalSettlementSearch" type="search" value="${escapeHtml(state.rentalSettlementSearch)}" placeholder="Search worker, trade or supplier…"></div><div class="timesheet-filter timesheet-filter--compact"><select id="rentalSettlementProject" class="ui-v2-select ui-v2-payroll-operational-select" aria-label="Project">${state.projects.map(p=>`<option value="${escapeHtml(p.id)}" ${p.id===project.id?'selected':''}>${escapeHtml(p.name)}</option>`).join('')}</select></div><div class="timesheet-filter timesheet-filter--compact"><select id="rentalSettlementSupplier" class="ui-v2-select ui-v2-payroll-operational-select" aria-label="Supplier"><option value="All suppliers">All suppliers</option>${suppliers.map(s=>`<option value="${escapeHtml(s.id)}" ${s.id===state.rentalSettlementSupplier?'selected':''}>${escapeHtml(s.name)}</option>`).join('')}</select></div><button class="btn btn--ghost" data-settlement-reset>Reset</button></div>
          <div class="table-meta ui-v2-payroll-table-meta ui-v2-payroll-rental-settlement-filter-meta"><span><strong>${rows.length}</strong> worker snapshot${rows.length===1?'':'s'}</span><span>Locked timesheet + effective commercial snapshot + Approved rental adjustments</span></div>
        </div>
      </div>
      <section class="data-panel settlement-register ui-v2-payroll-panel ui-v2-payroll-register ui-v2-payroll-rental-settlement-register--table-only">
        <div class="table-scroll ui-v2-payroll-table-wrap"><table class="data-table settlement-table ui-v2-payroll-rental-settlement-table"><thead><tr><th>Worker</th><th>Supplier</th><th>Trade / effective rate</th><th>Reg hrs</th><th>OT</th><th>Base</th><th>Gross</th><th>Earnings</th><th>Deductions</th><th>Net</th><th></th></tr></thead><tbody>${rows.length?rows.map(row=>`<tr><td><button class="entity-link entity-link--stack ui-v2-payroll-table-entity" data-open-rental-worker="${escapeHtml(row.workerId)}"><strong>${escapeHtml(row.name)}</strong><span>${escapeHtml(row.workerCode)}</span></button></td><td><button class="entity-link" data-route-link="suppliers/${escapeHtml(row.supplierId)}">${escapeHtml(row.supplier)}</button></td><td><div class="table-primary">${escapeHtml(row.trade)}</div><div class="table-secondary ui-v2-payroll-muted">${escapeHtml(row.rate)}${row.assignmentCount>1?' · split commercial segments':''}</div></td><td>${Number(row.hours||0).toLocaleString('en-SA',{maximumFractionDigits:2})}</td><td>${Number(row.otHours||0).toLocaleString('en-SA',{maximumFractionDigits:2})}</td><td class="table-money">${formatCurrency(row.base||0)}</td><td class="table-money">${formatCurrency(row.gross||0)}</td><td class="table-money">${formatCurrency(row.adjustmentEarnings||0)}</td><td class="table-money">${row.adjustments?`− ${formatCurrency(row.adjustments)}`:formatCurrency(0)}</td><td class="table-money"><strong>${formatCurrency(row.net||0)}</strong></td><td class="table-actions"><button class="btn btn--ghost btn--sm" data-settlement-worker="${escapeHtml(row.workerId)}" data-project-id="${escapeHtml(project.id)}">Breakdown</button></td></tr>`).join(''):`<tr><td colspan="11"><div class="table-empty ui-v2-payroll-table-empty"><strong>No calculated worker snapshots yet.</strong><span>Lock the project timesheet, approve adjustments, then calculate the settlement.</span></div></td></tr>`}</tbody><tfoot><tr><td colspan="3"><strong>Settlement totals</strong></td><td><strong>${totals.hours.toLocaleString('en-SA',{maximumFractionDigits:2})}</strong></td><td><strong>${totals.otHours.toLocaleString('en-SA',{maximumFractionDigits:2})}</strong></td><td class="table-money"><strong>${formatCurrency(totals.base)}</strong></td><td class="table-money"><strong>${formatCurrency(totals.gross)}</strong></td><td class="table-money"><strong>${formatCurrency(totals.adjustmentEarnings)}</strong></td><td class="table-money"><strong>${formatCurrency(totals.adjustments)}</strong></td><td class="table-money"><strong>${formatCurrency(totals.net)}</strong></td><td></td></tr></tfoot></table></div>
      </section>
      <section class="settlement-supplier-cards"><div class="section-headline"><div><h2>Supplier settlement split</h2><p>Each supplier remains a separate immutable payable snapshot even when several suppliers work on the same project.</p></div></div><div class="settlement-supplier-grid ui-v2-payroll-rental-settlement-supplier-grid">${groups.map(group=>{const totals=group.totals||rentalSettlementTotals(group.rows||[]);return `<article class="settlement-supplier-card ui-v2-payroll-rental-settlement-supplier-card"><header><button class="entity-link entity-link--title" data-route-link="suppliers/${escapeHtml(group.supplierId)}">${escapeHtml(group.supplier||group.supplierId)}</button>${rentalSettlementStatusBadge(group.status)}</header><div><span>Workers</span><strong>${totals.workers}</strong></div><div><span>Gross</span><strong>${formatCurrency(totals.gross)}</strong></div><div><span>Additions / deductions</span><strong>+ ${formatCurrency(totals.adjustmentEarnings||0)} / − ${formatCurrency(totals.adjustments)}</strong></div><div><span>Net payable</span><strong>${formatCurrency(totals.net)}</strong></div><footer><button class="text-link" data-open-rental-settlement-supplier="${escapeHtml(group.supplierId)}">Open supplier view →</button></footer></article>`}).join('')||'<div class="table-empty table-empty--card ui-v2-payroll-table-empty"><strong>No manpower suppliers in scope</strong><span>The locked timesheet has no supplier worker entries for this project.</span></div>'}</div></section>`;
  }
  function rentalSettlementSupplierView() {
    const context = state.rentalSettlementContexts[state.period];
    const availableSupplierIds = new Set((context?.timesheetScopes||[]).flatMap(scope=>(scope.suppliers||[]).map(item=>item.id)));
    Object.values(state.rentalSettlements||{}).filter(row=>row.period===state.period).forEach(row=>availableSupplierIds.add(row.supplierId));
    const candidateSuppliers=state.suppliers.filter(item=>availableSupplierIds.has(item.id));
    const supplierId = state.rentalSettlementSupplier !== 'All suppliers' ? state.rentalSettlementSupplier : (candidateSuppliers[0]?.id || '');
    const supplier = state.suppliers.find(item=>item.id===supplierId);
    if (!supplier) return `<div class="table-empty table-empty--card ui-v2-payroll-table-empty"><strong>No supplier settlement scope</strong><span>No supplier workers appear in rental timesheets for ${escapeHtml(state.period)}.</span></div>`;
    const projectIds=new Set();
    (context?.timesheetScopes||[]).forEach(scope=>{if((scope.suppliers||[]).some(item=>item.id===supplier.id)) projectIds.add(scope.projectId);});
    Object.values(state.rentalSettlements||{}).filter(row=>row.period===state.period&&row.supplierId===supplier.id).forEach(row=>projectIds.add(row.projectId));
    const projects=state.projects.filter(project=>projectIds.has(project.id));
    const groups = projects.map(project=>rentalSettlementRecordOrDraft(state.period,project.id,supplier.id));
    const totals = rentalSettlementTotals(groups.flatMap(group=>group.rows||[]));
    return `<section class="supplier-settlement-hero ui-v2-payroll-rental-supplier-settlement-hero"><div><span>Supplier settlement</span><button class="entity-link entity-link--stack ui-v2-payroll-table-entity" data-route-link="suppliers/${escapeHtml(supplier.id)}"><strong>${escapeHtml(supplier.name)}</strong><span>${escapeHtml(state.period)} · project-by-project manpower payable</span></button></div><div class="supplier-settlement-total"><span>Calculated net</span><strong>${formatCurrency(totals.net)}</strong><small>${projects.length} project${projects.length===1?'':'s'} · ${totals.workers} worker snapshots</small></div></section>
      <section class="data-panel ui-v2-payroll-panel ui-v2-payroll-register"><div class="table-toolbar ui-v2-payroll-register__toolbar"><div class="timesheet-filter timesheet-filter--compact"><select id="rentalSettlementSupplierMaster" class="ui-v2-select ui-v2-payroll-operational-select" aria-label="Supplier">${candidateSuppliers.map(s=>`<option value="${escapeHtml(s.id)}" ${s.id===supplier.id?'selected':''}>${escapeHtml(s.name)}</option>`).join('')}</select></div><button class="btn btn--secondary" data-supplier-assignment-activity="${escapeHtml(supplier.id)}">Assignment Activity</button></div><div class="table-scroll ui-v2-payroll-table-wrap"><table class="data-table settlement-project-table ui-v2-payroll-rental-settlement-table"><thead><tr><th>Project</th><th>Timesheet</th><th>Workers</th><th>Hours</th><th>Gross</th><th>Additions</th><th>Deductions</th><th>Net</th><th>Settlement</th><th></th></tr></thead><tbody>${groups.length?groups.map(group=>{const project=state.projects.find(p=>p.id===group.projectId);const totals=group.totals||rentalSettlementTotals(group.rows||[]);const ts=rentalTimesheetScope(group.projectId,state.period)?.status||'Not started';return `<tr><td><button class="entity-link entity-link--stack ui-v2-payroll-table-entity" data-route-link="projects/${escapeHtml(group.projectId)}"><strong>${escapeHtml(project?.name||group.projectId)}</strong><span>${escapeHtml(project?.code||'Project')}</span></button></td><td>${rentalSettlementStatusBadge(ts)}</td><td>${totals.workers}</td><td>${Number(totals.hours||0).toLocaleString('en-SA',{maximumFractionDigits:2})}</td><td class="table-money">${formatCurrency(totals.gross)}</td><td class="table-money">${formatCurrency(totals.adjustmentEarnings||0)}</td><td class="table-money">${formatCurrency(totals.adjustments)}</td><td class="table-money"><strong>${formatCurrency(totals.net)}</strong></td><td>${rentalSettlementStatusBadge(group.status)}</td><td><button class="btn btn--ghost btn--sm" data-open-rental-settlement-project="${escapeHtml(group.projectId)}" data-settlement-supplier="${escapeHtml(supplier.id)}">Open</button></td></tr>`}).join(''):`<tr><td colspan="10"><div class="table-empty ui-v2-payroll-table-empty"><strong>No project deployment in ${escapeHtml(state.period)}.</strong><span>This supplier does not appear in a rental timesheet for the selected month.</span></div></td></tr>`}</tbody></table></div></section>
      <section class="source-note ui-v2-payroll-source-note">${icon('info')}<span><strong>Commercial ledger separation.</strong> Each project remains independently auditable while this view aggregates the supplier's calculated snapshots across projects.</span></section>`;
  }
  function rentalSettlementHistoryTemplate() {
    let rows = rentalSettlementHistoryRows();
    if (state.rentalSettlementStatus !== 'All') rows=rows.filter(row=>row.status===state.rentalSettlementStatus);
    const q=state.rentalSettlementSearch.trim().toLowerCase();
    if (q) rows=rows.filter(row=>`${row.period} ${row.project||''} ${row.supplier||''} ${row.number||''} ${row.status}`.toLowerCase().includes(q));
    return `<section class="data-panel ui-v2-payroll-panel ui-v2-payroll-register"><div class="table-toolbar ui-v2-payroll-register__toolbar"><div class="table-toolbar__search ui-v2-filter-bar__search">${icon('search')}<input id="rentalSettlementSearch" type="search" value="${escapeHtml(state.rentalSettlementSearch)}" placeholder="Search settlement, period, project or supplier…"></div><select id="rentalSettlementStatus" class="ui-v2-select ui-v2-payroll-operational-select"><option>All</option>${['Draft','Calculated','Review','Approved','Payment Processing','Partially Paid','Paid','Closed'].map(status=>`<option ${state.rentalSettlementStatus===status?'selected':''}>${status}</option>`).join('')}</select><button class="btn btn--ghost" data-settlement-reset>Reset</button></div><div class="table-meta ui-v2-payroll-table-meta"><span><strong>${rows.length}</strong> matching settlement snapshot${rows.length===1?'':'s'}</span><span>Historical calculated snapshots remain immutable evidence.</span></div><div class="table-scroll ui-v2-payroll-table-wrap"><table class="data-table ui-v2-payroll-rental-settlement-table"><thead><tr><th>Settlement</th><th>Period</th><th>Supplier</th><th>Project</th><th>Workers</th><th>Gross</th><th>Additions</th><th>Deductions</th><th>Net</th><th>Status</th><th>Lifecycle</th><th></th></tr></thead><tbody>${rows.length?rows.map(row=>{const totals=row.totals||{};const stamp=row.closedAt||row.approvedAt||row.submittedAt||row.calculatedAt;return `<tr><td><strong>${escapeHtml(row.number||'—')}</strong></td><td>${escapeHtml(row.period)}</td><td><button class="entity-link" data-route-link="suppliers/${escapeHtml(row.supplierId)}">${escapeHtml(row.supplier||row.supplierId)}</button></td><td><button class="entity-link" data-route-link="projects/${escapeHtml(row.projectId)}">${escapeHtml(row.project||row.projectId)}</button></td><td>${totals.workers||0}</td><td class="table-money">${formatCurrency(totals.gross||0)}</td><td class="table-money">${formatCurrency(totals.adjustmentEarnings||0)}</td><td class="table-money">${formatCurrency(totals.adjustments||0)}</td><td class="table-money"><strong>${formatCurrency(totals.net||0)}</strong></td><td>${rentalSettlementStatusBadge(row.status)}</td><td><div class="table-primary">${stamp?escapeHtml(payrollTimestamp(stamp)):'Calculated snapshot'}</div><div class="table-secondary ui-v2-payroll-muted">Timesheet rev ${escapeHtml(String(row.sourceTimesheetRevision??'—'))}</div></td><td><button class="btn btn--ghost btn--sm" data-open-rental-settlement-project="${escapeHtml(row.projectId)}" data-settlement-supplier="${escapeHtml(row.supplierId)}" data-settlement-period="${escapeHtml(row.period)}">Open</button></td></tr>`}).join(''):`<tr><td colspan="12"><div class="table-empty ui-v2-payroll-table-empty"><strong>No settlement history matches the filters.</strong><span>Calculated supplier settlement snapshots will appear here.</span></div></td></tr>`}</tbody></table></div></section>`;
  }
  function rentalSettlementsTemplate() {
    if (!state.rentalSettlementLoadedPeriods.has(state.period)) {
      loadRentalSettlementContext(state.period);
      return `<section class="page rental-settlement-page ui-v2-payroll-page ui-v2-prs-rental-page ui-v2-prs-rental-finance-page ui-v2-payroll-rental-settlements"><div class="table-empty table-empty--card ui-v2-payroll-table-empty"><strong>Loading supplier settlements…</strong><span>Fetching the locked-timesheet settlement context from the server.</span></div></section>`;
    }
    const scopes=state.rentalSettlementContexts[state.period]?.timesheetScopes||[];
    const scopedProjectIds=new Set(scopes.map(item=>item.projectId));
    Object.values(state.rentalSettlements||{}).filter(item=>item.period===state.period).forEach(item=>scopedProjectIds.add(item.projectId));
    const currentProject = state.projects.find(item=>item.id===state.rentalSettlementProject&&scopedProjectIds.has(item.id)) || state.projects.find(item=>scopedProjectIds.has(item.id));
    if (currentProject) state.rentalSettlementProject=currentProject.id;
    return `<section class="page rental-settlement-page ui-v2-payroll-page ui-v2-prs-rental-page ui-v2-prs-rental-finance-page ui-v2-payroll-rental-settlements">
      <div class="page-head"><div class="page-head__copy"><span class="eyebrow">Rental Manpower · Cost & Settlement</span><h1>Supplier Settlements</h1><p>Convert locked project-timesheet snapshots into immutable supplier payables without mixing rental manpower with internal employee payroll.</p><span class="period-note">Settlement period: <strong>${escapeHtml(state.period)}</strong></span></div><div class="page-head__actions"><button class="btn btn--secondary" data-route-link="timesheets">Project Timesheets</button><button class="btn btn--secondary" data-route-link="adjustments">Worker Adjustments</button><button class="btn btn--secondary" data-route-link="payments">Supplier Payments</button></div></div>
      <div class="source-banner source-banner--compact ui-v2-payroll-source-note ui-v2-payroll-rental-settlement-boundary">${icon('info')}<span><strong>Controlled settlement boundary.</strong> Locked project timesheets supply the frozen hours and OT snapshot; effective assignment rates and Approved rental adjustments are calculated on the server and snapshotted before Finance Review. Approval creates the supplier payable; payment remains separate.</span></div>
      <div class="settlement-nav-row ui-v2-payroll-rental-settlement-nav"><div class="profile-tabs settlement-tabs ui-v2-payroll-view-tabs"><button class="${state.rentalSettlementTab==='current'?'is-active':''}" data-settlement-tab="current">Current Settlement</button><button class="${state.rentalSettlementTab==='history'?'is-active':''}" data-settlement-tab="history">Settlement History</button></div>${state.rentalSettlementTab==='current'?`<div class="segmented settlement-view-toggle ui-v2-payroll-view-tabs is-compact"><button class="${state.rentalSettlementView==='project'?'is-active':''}" data-settlement-view="project">By Project</button><button class="${state.rentalSettlementView==='supplier'?'is-active':''}" data-settlement-view="supplier">By Supplier</button></div>`:''}</div>
      ${state.rentalSettlementTab==='history' ? rentalSettlementHistoryTemplate() : (state.rentalSettlementView==='supplier' ? rentalSettlementSupplierView() : rentalSettlementProjectView())}
    </section>`;
  }
  function adjustmentNormalizeType(type) {
    const value = String(type || '').trim();
    if (!value) return 'Other Deduction';
    if (value === 'Advance') return 'Legacy Advance Deduction';
    return value;
  }

  function internalAdjustmentTypeCode(type) {
    const map = {
      'Salary Advance':'salary_advance', 'Advance Recovery':'advance_recovery', 'Bonus':'bonus', 'Reimbursement':'reimbursement',
      'Fine':'fine', 'Other Earning':'other_earning', 'Other Deduction':'other_deduction'
    };
    return map[adjustmentNormalizeType(type)] || 'other_deduction';
  }

  function rentalAdjustmentTypeCode(type) {
    const map = {
      'Worker Advance':'advance', 'Bonus':'bonus', 'Reimbursement':'reimbursement',
      'Fine / Penalty':'fine', 'Fine':'fine', 'Other Earning':'other_earning', 'Other Deduction':'other_deduction'
    };
    return map[adjustmentNormalizeType(type)] || 'other_deduction';
  }

  function adjustmentKind(type) {
    const value = adjustmentNormalizeType(type).toLowerCase();
    if (value.includes('salary advance') && !value.includes('recovery')) return 'advance-issue';
    if (value.includes('advance recovery') || value.includes('legacy advance')) return 'deduction';
    if (value.includes('fine') || value.includes('deduction') || value.includes('loan') || value.includes('installment')) return 'deduction';
    if (value.includes('bonus') || value.includes('reimbursement') || value.includes('allowance') || value.includes('earning')) return 'earning';
    return 'deduction';
  }

  function adjustmentIsApplied(status) {
    return ['Approved','Applied','Paid','Recorded'].includes(String(status || ''));
  }

  function adjustmentImpactText(row) {
    const kind = adjustmentKind(row.type);
    if (kind === 'advance-issue') return 'Advance balance';
    if (kind === 'earning') return 'Adds to payable';
    return 'Deducts from payable';
  }

  function adjustmentCustomRows() {
    const rows = [];
    Object.entries(state.internalAdjustments || {}).forEach(([employeeId, items]) => {
      const employee = state.employees.find(item => item.id === employeeId);
      if (!employee) return;
      (items || []).forEach(item => rows.push({
        ...item, type:adjustmentNormalizeType(item.type), workforce:'Internal Employee', workforceKey:'Internal', personId:employee.id,
        personName:employee.name, personCode:`EMP ${employee.employeeId}`, supplierId:null, supplier:'—',
        projectId:null, project:'Employee-level',
        source:item.source || 'Company database', immutable:!!item.immutable
      }));
    });
    Object.entries(state.rentalAdjustments || {}).forEach(([workerId, items]) => {
      const worker = rentalWorkerById(workerId);
      if (!worker) return;
      const supplier = rentalWorkerSupplier(worker);
      (items || []).forEach(item => rows.push({
        ...item, type:adjustmentNormalizeType(item.type), workforce:'Rental Worker', workforceKey:'Rental', personId:worker.id,
        personName:item.personName || worker.name, personCode:item.personCode || rentalWorkerCode(worker),
        supplierId:item.supplierId || worker.supplierId || null, supplier:item.supplier || supplier?.name || 'Supplier not linked',
        projectId:item.projectId || null, project:item.project || (item.projectId ? state.projects.find(p=>p.id===item.projectId)?.name : 'Project') || 'Project',
        source:item.source || 'Company database', immutable:!!item.immutable
      }));
    });
    return rows;
  }
  function allAdjustmentRows() {
    return adjustmentCustomRows().sort((a,b) => {
      const ad = /^\d{4}-\d{2}-\d{2}$/.test(String(a.date||'')) ? a.date : '0000-00-00';
      const bd = /^\d{4}-\d{2}-\d{2}$/.test(String(b.date||'')) ? b.date : '0000-00-00';
      return bd.localeCompare(ad) || String(b.id).localeCompare(String(a.id));
    });
  }

  function adjustmentFilteredRows() {
    const q = state.adjustmentSearch.trim().toLowerCase();
    return allAdjustmentRows().filter(row => {
      if (state.workspace === 'rental' && row.workforceKey !== 'Rental') return false;
      if (state.workspace === 'internal' && row.workforceKey !== 'Internal') return false;
      if (state.adjustmentWorkforce !== 'All' && row.workforceKey !== state.adjustmentWorkforce) return false;
      if (state.adjustmentType !== 'All' && adjustmentNormalizeType(row.type) !== state.adjustmentType) return false;
      if (state.adjustmentStatus !== 'All' && row.status !== state.adjustmentStatus) return false;
      if (state.adjustmentProject !== 'All projects' && row.projectId !== state.adjustmentProject) return false;
      if (state.adjustmentSupplier !== 'All suppliers' && row.supplierId !== state.adjustmentSupplier) return false;
      if (q && !`${row.personName} ${row.personCode} ${row.type} ${row.reason} ${row.project} ${row.supplier} ${row.reference}`.toLowerCase().includes(q)) return false;
      return true;
    });
  }

  function adjustmentPeriodSummary(rows = allAdjustmentRows()) {
    const periodRows = rows.filter(row => row.period === state.period);
    return periodRows.reduce((out,row) => {
      const amount = Number(row.amount || 0);
      const kind = adjustmentKind(row.type);
      if (!adjustmentIsApplied(row.status)) out.pending += 1;
      else if (kind === 'earning') out.earnings += amount;
      else if (kind === 'deduction') out.deductions += amount;
      else if (kind === 'advance-issue') out.advanceIssues += amount;
      out.count += 1;
      return out;
    }, {count:0,earnings:0,deductions:0,advanceIssues:0,pending:0});
  }

  function adjustmentAdvanceBalances() {
    const groups = new Map();
    const customRows = adjustmentCustomRows().filter(row => state.workspace === 'rental' ? row.workforceKey === 'Rental' : row.workforceKey === 'Internal');
    customRows.forEach(row => {
      const type = adjustmentNormalizeType(row.type);
      if (!['Salary Advance','Advance Recovery'].includes(type)) return;
      const key = `${row.workforceKey}:${row.personId}`;
      if (!groups.has(key)) groups.set(key,{key,workforce:row.workforce,workforceKey:row.workforceKey,personId:row.personId,personName:row.personName,personCode:row.personCode,supplier:row.supplier,issued:0,recovered:0,pending:0,lastDate:'',plans:[]});
      const group=groups.get(key), amount=Number(row.amount||0);
      if (!adjustmentIsApplied(row.status)) { group.pending += amount; return; }
      if (type === 'Salary Advance') { group.issued += amount; if(row.recoveryPlan && row.recoveryPlan !== 'No automatic schedule') group.plans.push({plan:row.recoveryPlan,installment:Number(row.installmentAmount||0),start:row.recoveryStart||''}); }
      else group.recovered += amount;
      if (/^\d{4}-\d{2}-\d{2}$/.test(String(row.date||'')) && row.date > group.lastDate) group.lastDate=row.date;
    });
    return [...groups.values()].map(group=>({...group,balance:Math.max(0,group.issued-group.recovered)})).sort((a,b)=>b.balance-a.balance || a.personName.localeCompare(b.personName));
  }

  function adjustmentSummaryStrip(summary, balances) {
    if (state.workspace === 'rental') {
      return `<div class="adjustment-summary-strip">
        <div><span>Transactions · ${escapeHtml(state.period)}</span><strong>${summary.count}</strong><small>Rental worker settlement ledger</small></div>
        <div><span>Approved earnings</span><strong>${formatCurrency(summary.earnings)}</strong><small>Added to supplier payable</small></div>
        <div><span>Approved deductions</span><strong>${formatCurrency(summary.deductions)}</strong><small>Advances, fines & deductions</small></div>
        <div><span>Awaiting approval</span><strong>${summary.pending}</strong><small>Excluded from settlement calculation</small></div>
      </div>`;
    }
    const openBalance = balances.reduce((sum,row)=>sum+Number(row.balance||0),0);
    return `<div class="adjustment-summary-strip">
      <div><span>Transactions · ${escapeHtml(state.period)}</span><strong>${summary.count}</strong><small>Internal employee ledger</small></div>
      <div><span>Approved earnings</span><strong>${formatCurrency(summary.earnings)}</strong><small>Add to period payable</small></div>
      <div><span>Approved deductions</span><strong>${formatCurrency(summary.deductions)}</strong><small>Recoveries, fines & deductions</small></div>
      <button data-adjustment-view="balances"><span>Open advance balance</span><strong>${formatCurrency(openBalance)}</strong><small>${balances.filter(row=>row.balance>0).length} active balance${balances.filter(row=>row.balance>0).length===1?'':'s'}</small></button>
      <div><span>Awaiting approval</span><strong>${summary.pending}</strong><small>Excluded from payroll</small></div>
    </div>`;
  }
  function adjustmentRegisterTemplate() {
    const rows = adjustmentFilteredRows();
    const workspaceRows = allAdjustmentRows().filter(row=>state.workspace==='rental'?row.workforceKey==='Rental':row.workforceKey==='Internal');
    const types = [...new Set(workspaceRows.map(row=>adjustmentNormalizeType(row.type)))].sort();
    const statuses = [...new Set(workspaceRows.map(row=>row.status).filter(Boolean))].sort();
    return `<section class="panel panel--flush adjustment-ledger-panel">
      <div class="adjustment-filterbar">
        <div class="search-field adjustment-search">${icon('search')}<input id="adjustmentSearch" type="search" value="${escapeHtml(state.adjustmentSearch)}" placeholder="Search person, type, project, supplier, reference…"></div>
        
        <select class="select" id="adjustmentType"><option>All</option>${types.map(type=>`<option ${state.adjustmentType===type?'selected':''}>${escapeHtml(type)}</option>`).join('')}</select>
        <select class="select" id="adjustmentStatus"><option>All</option>${statuses.map(status=>`<option ${state.adjustmentStatus===status?'selected':''}>${escapeHtml(status)}</option>`).join('')}</select>
        ${state.workspace==='rental'?`<select class="select" id="adjustmentProject"><option>All projects</option>${state.projects.filter(project=>!project.legacyInternal).map(project=>`<option value="${escapeHtml(project.id)}" ${state.adjustmentProject===project.id?'selected':''}>${escapeHtml(project.name)}</option>`).join('')}</select><select class="select" id="adjustmentSupplier"><option>All suppliers</option>${state.suppliers.filter(s=>s.status==='Active').map(supplier=>`<option value="${escapeHtml(supplier.id)}" ${state.adjustmentSupplier===supplier.id?'selected':''}>${escapeHtml(supplier.name)}</option>`).join('')}</select>`:''}
        <button class="btn btn--ghost" data-adjustment-reset>Reset</button>
      </div>
      <div class="table-meta"><span><strong>${rows.length}</strong> matching transaction${rows.length===1?'':'s'}</span><span>Draft/Review items are visible but do not change payroll or rental settlement.</span></div>
      <div class="table-scroll"><table class="data-table adjustment-ledger-table"><thead><tr><th>Date / Period</th><th>Person</th><th>Transaction</th><th>Project / Supplier</th><th>Amount</th><th>${state.workspace==='rental'?'Settlement effect':'Payroll effect'}</th><th>Status</th><th>Source</th><th></th></tr></thead><tbody>${rows.length?rows.map(row=>{
        const kind=adjustmentKind(row.type), amount=Number(row.amount||0);
        const entityButton=row.workforceKey==='Internal'?`<button class="entity-link entity-link--stack" data-open-employee="${escapeHtml(row.personId)}"><strong>${escapeHtml(row.personName)}</strong><span>${escapeHtml(row.personCode)} · Internal</span></button>`:`<button class="entity-link entity-link--stack" data-open-rental-worker="${escapeHtml(row.personId)}"><strong>${escapeHtml(row.personName)}</strong><span>${escapeHtml(row.personCode)} · Rental</span></button>`;
        const action=!row.immutable?(row.status==='Draft'?`<button class="btn btn--ghost btn--sm" data-adjustment-action="submit" data-adjustment-id="${escapeHtml(row.id)}">Submit</button>`:row.status==='Review'?`<button class="btn btn--secondary btn--sm" data-adjustment-action="approve" data-adjustment-id="${escapeHtml(row.id)}">Approve</button>`:`<button class="icon-btn icon-btn--sm" data-adjustment-detail="${escapeHtml(row.id)}">${icon('more')}</button>`):`<button class="icon-btn icon-btn--sm" data-adjustment-detail="${escapeHtml(row.id)}">${icon('more')}</button>`;
        return `<tr><td><div class="table-primary">${escapeHtml(row.date||'—')}</div><div class="table-secondary">${escapeHtml(row.period||'—')}</div></td><td>${entityButton}</td><td><div class="adjustment-type-cell"><strong>${escapeHtml(adjustmentNormalizeType(row.type))}</strong><span>${escapeHtml(row.reason||'No reason recorded')}</span></div></td><td><div class="table-primary">${row.projectId?`<button class="entity-link" data-open-project="${escapeHtml(row.projectId)}">${escapeHtml(row.project)}</button>`:escapeHtml(row.project||'Employee-level')}</div>${row.workforceKey==='Rental'?`<div class="table-secondary">${row.supplierId?`<button class="entity-link entity-link--inline" data-open-supplier="${escapeHtml(row.supplierId)}">${escapeHtml(row.supplier)}</button>`:escapeHtml(row.supplier||'—')}</div>`:''}</td><td class="table-money"><strong>${formatCurrency(amount)}</strong></td><td><span class="adjustment-impact adjustment-impact--${kind}">${kind==='earning'?'+':kind==='deduction'?'−':'↔'} ${escapeHtml(adjustmentImpactText(row))}</span></td><td>${statusBadge(row.status||'Draft')}</td><td><span class="source-mini">Database</span></td><td class="table-actions">${action}</td></tr>`;
      }).join(''):`<tr><td colspan="9"><div class="table-empty"><strong>No matching transactions.</strong><span>Change the filters or record an advance/adjustment from the controlled transaction drawer.</span></div></td></tr>`}</tbody></table></div>
    </section>`;
  }

  function adjustmentBalancesTemplate() {
    const balances=adjustmentAdvanceBalances();
    return `<div class="adjustment-balance-layout">
      <section class="panel panel--flush"><div class="section-headline"><div><h2>Advance balances</h2><p>Approved Salary Advance issues build the balance; approved Advance Recovery transactions reduce it without deleting prior history.</p></div><button class="btn btn--primary btn--sm" data-quick-add="advance">${icon('plus')} New Advance / Recovery</button></div>
      <div class="table-scroll"><table class="data-table adjustment-balance-table"><thead><tr><th>Person</th><th>Workforce</th><th>Issued</th><th>Recovered</th><th>Outstanding</th><th>Recovery plan</th><th>Last activity</th><th></th></tr></thead><tbody>${balances.length?balances.map(row=>`<tr><td>${row.workforceKey==='Internal'?`<button class="entity-link entity-link--stack" data-open-employee="${escapeHtml(row.personId)}"><strong>${escapeHtml(row.personName)}</strong><span>${escapeHtml(row.personCode)}</span></button>`:`<button class="entity-link entity-link--stack" data-open-rental-worker="${escapeHtml(row.personId)}"><strong>${escapeHtml(row.personName)}</strong><span>${escapeHtml(row.personCode)}</span></button>`}</td><td>${escapeHtml(row.workforce)}</td><td class="table-money">${formatCurrency(row.issued)}</td><td class="table-money">${formatCurrency(row.recovered)}</td><td class="table-money"><strong>${formatCurrency(row.balance)}</strong>${row.pending?`<small class="balance-pending">${formatCurrency(row.pending)} pending</small>`:''}</td><td>${row.plans.length?`<div class="table-primary">${escapeHtml(row.plans[0].plan)}</div><div class="table-secondary">${row.plans[0].installment?`${formatCurrency(row.plans[0].installment)} / period`:''}${row.plans[0].start?` · from ${escapeHtml(row.plans[0].start)}`:''}</div>`:'<span class="table-secondary">Manual recovery</span>'}</td><td>${row.lastDate?escapeHtml(rentalDisplayDate(row.lastDate)):'—'}</td><td class="table-actions"><button class="btn btn--ghost btn--sm" data-quick-add="advance" data-adjustment-person-context="${escapeHtml(row.personId)}" data-adjustment-workforce-context="${escapeHtml(row.workforce)}" data-adjustment-type-context="Advance Recovery">Recover</button></td></tr>`).join(''):`<tr><td colspan="8"><div class="table-empty"><strong>No approved advance balances yet.</strong><span>Create a Salary Advance, approve it, then record recoveries as separate transactions.</span></div></td></tr>`}</tbody></table></div></section>
      <aside class="adjustment-balance-side"><section class="detail-card"><div class="detail-card__head"><h3>Balance rule</h3><span class="status status--success"><span></span>Audit safe</span></div><div class="rental-rule-list"><div><strong>Salary Advance</strong><span>Creates an outstanding balance; it does not rewrite salary or worker rate.</span></div><div><strong>Advance Recovery</strong><span>Deducts from approved payroll/settlement and reduces the open balance.</span></div><div><strong>Never overwrite</strong><span>Corrections use reversal/new transactions so the history stays traceable.</span></div></div></section></aside>
    </div>`;
  }

  function adjustmentsTemplate() {
    if (state.workspace === 'internal' && !state.payrollLoadedPeriods.has(state.period)) {
      loadInternalPayrollPeriod(state.period);
      return `<section class="page adjustments-page"><div class="table-empty table-empty--card"><strong>Loading adjustments…</strong><span>Fetching the period ledger from the server.</span></div></section>`;
    }
    if (state.workspace === 'rental' && !state.rentalSettlementLoadedPeriods.has(state.period)) {
      loadRentalSettlementContext(state.period);
      return `<section class="page adjustments-page"><div class="table-empty table-empty--card"><strong>Loading rental adjustments…</strong><span>Fetching company-scoped settlement transactions from the server.</span></div></section>`;
    }
    if (state.workspace === 'rental' && state.adjustmentView === 'balances') state.adjustmentView='register';
    const rows=allAdjustmentRows().filter(row=>state.workspace==='rental'?row.workforceKey==='Rental':row.workforceKey==='Internal');
    const summary=adjustmentPeriodSummary(rows), balances=adjustmentAdvanceBalances();
    const content=state.workspace==='rental' ? adjustmentRegisterTemplate() : (state.adjustmentView==='balances'?adjustmentBalancesTemplate():adjustmentRegisterTemplate());
    return `<section class="page adjustments-page ${state.workspace==='internal'?'ui-v2-prs-internal-page ui-v2-prs-internal-execution-page':''}">
      <div class="page-head"><div class="page-head__copy"><span class="eyebrow">${escapeHtml(workspaceLabel())} · Controlled Transactions</span><h1>${state.workspace==='rental'?'Worker Adjustments':'Advances & Adjustments'}</h1><p>${state.workspace==='rental'?'Project-attributed rental-worker advances, fines, bonuses, reimbursements and other settlement adjustments.':'Company-employee advances, recoveries, fines, bonuses, reimbursements and other payroll adjustments.'}</p><span class="period-note">Working period: <strong>${escapeHtml(state.period)}</strong></span></div><div class="page-head__actions">${state.workspace==='rental'?'<button class="btn btn--secondary" data-route-link="rental-settlements">Supplier Settlements</button>':'<button class="btn btn--secondary" data-route-link="payroll-runs">Internal Payroll</button>'}<button class="btn btn--primary" data-quick-add="advance">${icon('plus')} New Transaction</button></div></div>
      ${adjustmentSummaryStrip(summary,balances)}
      ${state.workspace==='rental'?'':`<div class="adjustment-tabs"><button class="${state.adjustmentView==='register'?'is-active':''}" data-adjustment-view="register"><span>Transaction Register</span><small>${rows.length} total records</small></button><button class="${state.adjustmentView==='balances'?'is-active':''}" data-adjustment-view="balances"><span>Advance Balances</span><small>${balances.filter(row=>row.balance>0).length} open</small></button></div>`}
      ${content}
      <div class="source-note adjustment-source-note">${icon('info')}<span><strong>Calculation boundary:</strong> ${state.workspace==='rental'?'Only Approved database adjustments are snapshotted into the matching supplier/project settlement. Worker Advance is a direct settlement deduction; it is not an internal employee salary-advance balance.':'Internal transactions are company-scoped database records. Draft and Review items remain excluded from payroll until approved.'}</span></div>
    </section>`;
  }
  function adjustmentFindRow(id) {
    return allAdjustmentRows().find(row=>row.id===id) || null;
  }

  function adjustmentFindMutable(id) {
    for (const [employeeId,items] of Object.entries(state.internalAdjustments||{})) {
      const item=(items||[]).find(row=>row.id===id); if(item) return {item,kind:'internal',personId:employeeId};
    }
    for (const [workerId,items] of Object.entries(state.rentalAdjustments||{})) {
      const item=(items||[]).find(row=>row.id===id); if(item) return {item,kind:'rental',personId:workerId};
    }
    return null;
  }

  function openAdjustmentDetailDrawer(id) {
    const row=adjustmentFindRow(id); if(!row) return;
    state.drawerType='adjustment-detail'; state.drawerContext={id}; drawerSave.hidden=true;
    drawerTitle.textContent=`${adjustmentNormalizeType(row.type)} · ${row.personName}`;
    drawerBody.innerHTML=`<section class="adjustment-detail-hero"><div><span class="eyebrow">${escapeHtml(row.workforce)}</span><h3>${escapeHtml(row.personName)}</h3><p>${escapeHtml(row.personCode)} · ${escapeHtml(row.period)}</p></div><strong>${formatCurrency(row.amount)}</strong></section><section class="detail-card"><div class="detail-card__head"><h3>Transaction detail</h3>${statusBadge(row.status)}</div><div class="adjustment-detail-grid"><div><span>Type</span><strong>${escapeHtml(adjustmentNormalizeType(row.type))}</strong></div><div><span>Effective date</span><strong>${escapeHtml(row.date||'—')}</strong></div><div><span>${row.workforceKey==='Rental'?'Settlement effect':'Payroll effect'}</span><strong>${escapeHtml(adjustmentImpactText(row))}</strong></div><div><span>Project</span><strong>${escapeHtml(row.project||'Employee-level')}</strong></div>${row.workforceKey==='Rental'?`<div><span>Supplier</span><strong>${escapeHtml(row.supplier||'—')}</strong></div>`:''}<div><span>Reference</span><strong>${escapeHtml(row.reference||'Not recorded')}</strong></div></div></section><section class="detail-card"><div class="detail-card__head"><h3>Reason / notes</h3></div><p>${escapeHtml(row.reason||'No reason recorded.')}</p></section><section class="source-note source-note--compact">${icon('info')}<span><strong>Company database record.</strong> ${row.immutable?'This Approved transaction is immutable through normal editing and is eligible for settlement/payroll snapshotting.':'Status changes use the audited transaction workflow; Draft/Review items are excluded from financial calculations.'}</span></section>`;
    drawer.classList.add('is-open');drawerScrim.classList.add('is-open');drawer.setAttribute('aria-hidden','false');
  }
  function setupAdjustmentDrawer() {
    const workforceSelect=drawerBody.querySelector('[name="adjustment-workforce"]');
    const personSelect=drawerBody.querySelector('[name="adjustment-person"]');
    if(!workforceSelect||!personSelect)return;
    const preferred=state.drawerContext?.personId || '';
    const fill=()=>{
      const isRental=workforceSelect.value==='Rental Worker';
      const options=isRental?state.rentalWorkers.map(worker=>({value:worker.id,label:`${rentalWorkerCode(worker)} · ${worker.name}`})):state.employees.map(employee=>({value:employee.id,label:`EMP ${employee.employeeId} · ${employee.name}`}));
      personSelect.innerHTML=options.map(item=>`<option value="${escapeHtml(item.value)}" ${item.value===preferred?'selected':''}>${escapeHtml(item.label)}</option>`).join('');
      if(preferred && options.some(item=>item.value===preferred)) personSelect.value=preferred;
    };
    fill(); workforceSelect.addEventListener('change',()=>{state.drawerContext={...(state.drawerContext||{}),personId:''};fill();});
  }


  function documentTone(status) {
    const value = String(status || '').toLowerCase();
    if (value.includes('final') || value.includes('paid') || value.includes('approved') || value.includes('locked')) return 'success';
    if (value.includes('failed') || value.includes('invalid')) return 'danger';
    return 'neutral';
  }

  function documentStatusBadge(status) {
    return `<span class="status status--${documentTone(status)}"><span></span>${escapeHtml(status || 'Final')}</span>`;
  }

  const documentTypeMeta = {
    salary_slip:{label:'Salary Slip',code:'SL'},
    internal_timesheet:{label:'Internal Timesheet',code:'IT'},
    salary_payment_receipt:{label:'Salary Payment Receipt',code:'SR'},
    rental_timesheet:{label:'Rental Timesheet',code:'RT'},
    supplier_settlement:{label:'Supplier Settlement',code:'SS'},
    supplier_invoice:{label:'Supplier Invoice',code:'SI'},
    supplier_payment_receipt:{label:'Supplier Payment Receipt',code:'PR'}
  };

  function documentTypeLabel(type) { return documentTypeMeta[type]?.label || type || 'Document'; }
  function documentTypeCode(type) { return documentTypeMeta[type]?.code || 'DC'; }
  function documentAllRecords() { return (state.businessDocuments||[]).filter(item=>item.workspace===state.workspace); }

  async function loadDocumentList({render=true}={}) {
    try {
      const payload=await appApi(`/api/documents/?workspace=${encodeURIComponent(state.workspace)}`);
      state.businessDocuments=(state.businessDocuments||[]).filter(item=>item.workspace!==state.workspace).concat(payload.documents||[]);
      if(render && currentRoute()==='documents')renderRoute();
    } catch(error){showToast('Documents unavailable',error.message);}
  }

  async function loadDocumentDetail(id,{render=true}={}) {
    if(!id||state.documentLoadingId===id)return;
    if(state.documentDetails[id])return;
    state.documentLoadingId=id;
    try{const payload=await appApi(`/api/documents/${encodeURIComponent(id)}/`);state.documentDetails[id]=payload.document;if(render&&currentRoute()==='documents')renderRoute();}
    catch(error){showToast('Document unavailable',error.message);}
    finally{state.documentLoadingId=null;}
  }

  function documentSnapshotSummary(doc) {
    const full=state.documentDetails[doc?.id]||doc;
    const snapshot=full?.snapshot;
    if(!doc)return '<div class="table-empty table-empty--card"><strong>Select a document</strong><span>Choose a finalized document from the list.</span></div>';
    if(!snapshot){if(state.documentLoadingId!==doc.id)queueMicrotask(()=>loadDocumentDetail(doc.id));return '<div class="table-empty table-empty--card"><strong>Loading document snapshot…</strong><span>Fetching the immutable server snapshot.</span></div>';}
    const kind=documentTypeLabel(doc.type);
    const totals=snapshot.totals||snapshot.earnings||snapshot.payment||{};
    const important=Object.entries(totals).filter(([,value])=>['string','number'].includes(typeof value)).slice(0,8);
    const entity=snapshot.employee?.name||snapshot.supplier?.name||snapshot.project?.name||doc.entityName||'Company';
    return `<article class="document-paper"><header class="document-brand-header"><div class="document-brand-mark">${escapeHtml(documentTypeCode(doc.type))}</div><div><strong>${escapeHtml(snapshot.issuer?.legal_name||snapshot.issuer?.name||serverAccess.company_name||'Company')}</strong><span>Final business document</span></div><div class="document-brand-vat"><span>Integrity</span><strong>${doc.integrityOk?'Verified':'Check failed'}</strong></div></header><div class="document-title-block"><span>${escapeHtml(kind.toUpperCase())}</span><h2>${escapeHtml(doc.number)}</h2></div><div class="document-meta-grid"><div><span>Entity</span><strong>${escapeHtml(entity)}</strong></div><div><span>Period</span><strong>${escapeHtml(doc.period||'—')}</strong></div><div><span>Finalized</span><strong>${escapeHtml(payrollTimestamp(doc.finalizedAt))}</strong></div><div><span>Finalized by</span><strong>${escapeHtml(doc.finalizedBy||'System')}</strong></div></div>${important.length?`<div class="document-summary-grid">${important.map(([key,value])=>`<div><span>${escapeHtml(String(key).replaceAll('_',' '))}</span><strong>${/amount|gross|net|deduction|base|overtime|total/i.test(key)?formatCurrency(value):escapeHtml(value)}</strong></div>`).join('')}</div>`:''}<div class="source-note document-source-note">${icon('info')}<span><strong>Immutable snapshot.</strong> This preview is backed by the finalized Django document record. Use Print / Save PDF for the full formatted document.</span></div></article>`;
  }

  function recordKindLabel(kind) {
    return ({branch:'Branch / Office',department:'Department',employee:'Employee',supplier:'Supplier',worker:'Rental Worker',project:'Project'})[kind] || 'Record';
  }

  function recordManagementTemplate(bucket) {
    const isTrash = bucket === 'trash';
    const rows = (state.recordManagement?.[bucket] || []).filter(item => item.workspace === state.workspace);
    const title = isTrash ? 'Delete' : 'Archive';
    const copy = isTrash
      ? `Deleted master records remain recoverable for ${state.recordManagement.retentionDays || 30} days. Restore them here before the purge date.`
      : 'Archived master records remain part of company history and can be restored here without rewriting historical activity.';
    return `<section class="page records-bin-page ui-v2-payroll-page">
      <div class="page-head"><div class="page-head__copy"><span class="eyebrow">Records · Lifecycle control</span><h1>${title}</h1><p>${escapeHtml(copy)}</p></div></div>
      <section class="panel panel--flush">
        <div class="panel__head panel__head--padded"><div><h2>${title}</h2><p>${isTrash ? 'Deleted records remain separate from Archive. Protected historical references stay preserved even after the 30-day recovery window expires.' : 'Archive is persistent until a user deliberately restores the record.'}</p></div><span class="status-badge">${rows.length} record${rows.length===1?'':'s'}</span></div>
        ${rows.length ? `<div class="table-scroll"><table class="data-table"><thead><tr><th>Type</th><th>Record</th><th>${isTrash?'Deleted':'Archived'}</th>${isTrash?'<th>Purge after</th>':''}<th>Reason</th><th></th></tr></thead><tbody>${rows.map(row=>`<tr><td>${escapeHtml(recordKindLabel(row.kind))}</td><td><strong>${escapeHtml(row.label)}</strong><small class="table-secondary">${escapeHtml(row.code || '')}${row.detail?` · ${escapeHtml(row.detail)}`:''}</small></td><td>${escapeHtml(payrollTimestamp(isTrash?row.deletedAt:row.archivedAt) || '—')}</td>${isTrash?`<td><strong>${escapeHtml(payrollTimestamp(row.purgeAfter) || '—')}</strong><small class="table-secondary">30-day recovery window</small></td>`:''}<td>${escapeHtml((isTrash?row.deletionReason:row.archiveReason) || '—')}</td><td><button class="btn btn--secondary btn--sm" data-record-bin-restore="${bucket}|${escapeHtml(row.kind)}|${escapeHtml(row.id)}">Restore</button></td></tr>`).join('')}</tbody></table></div>` : `<div class="table-empty table-empty--card"><strong>${isTrash?'No deleted records':'Archive is empty'}</strong><span>${isTrash?'Deleted records that are still inside the 30-day recovery window will appear here.':'Archived records for this workspace will appear here.'}</span></div>`}
      </section>
      <section class="source-note">${icon('info')}<span><strong>${isTrash?'30-day delete recovery':'Archive is not deletion'}.</strong>${isTrash?' Deleting a record starts a 30-day recovery window and never erases protected payroll, assignment, inventory, settlement or audit history.':' Archived records are retained until restored and remain resolvable from historical records.'}</span></section>
    </section>`;
  }

  function documentsTemplate() {
    const all=documentAllRecords();
    const allowedTypes=state.workspace==='rental'?['rental_timesheet','supplier_settlement','supplier_invoice','supplier_payment_receipt']:['salary_slip','internal_timesheet','salary_payment_receipt'];
    if(state.documentTab!=='all'&&!allowedTypes.includes(state.documentTab))state.documentTab='all';
    const q=state.documentSearch.trim().toLowerCase();
    const filtered=all.filter(doc=>{
      if(state.documentTab!=='all'&&doc.type!==state.documentTab)return false;
      if(state.documentPeriodFilter!=='All periods'&&doc.period!==state.documentPeriodFilter)return false;
      if(state.documentStatusFilter!=='All statuses'&&doc.status!==state.documentStatusFilter)return false;
      if(!q)return true;
      return `${doc.number} ${doc.title} ${doc.entityReference} ${doc.entityName} ${doc.sourceReference} ${doc.externalReference}`.toLowerCase().includes(q);
    });
    const periods=[...new Set(all.map(item=>item.period).filter(Boolean))].sort(managementPeriodSort);
    const statuses=[...new Set(all.map(item=>item.status).filter(Boolean))].sort();
    const counts=Object.fromEntries(allowedTypes.map(type=>[type,all.filter(item=>item.type===type).length]));
    let selected=filtered.find(item=>item.id===state.selectedDocumentId)||filtered[0]||null;
    if(selected&&state.selectedDocumentId!==selected.id)state.selectedDocumentId=selected.id;
    return `<section class="page documents-page"><div class="page-head"><div class="page-head__copy"><span class="eyebrow">${escapeHtml(workspaceLabel())} · Final Records</span><h1>Documents</h1><p>${state.workspace==='rental'?'Final project timesheets, supplier settlements, supplier invoices and supplier-payment receipts.':'Final salary slips, internal timesheets and salary-payment receipts.'}</p></div><div class="page-head__actions"><button class="btn btn--primary" data-document-generate>${icon('plus')} Finalize Document</button></div></div><div class="document-kpis">${allowedTypes.map(type=>`<div><span>${escapeHtml(documentTypeLabel(type))}</span><strong>${counts[type]||0}</strong><small>Immutable final records</small></div>`).join('')}</div><div class="document-tabs"><button class="${state.documentTab==='all'?'is-active':''}" data-document-tab="all"><span>All Documents</span><em>${all.length}</em></button>${allowedTypes.map(type=>`<button class="${state.documentTab===type?'is-active':''}" data-document-tab="${type}"><span>${escapeHtml(documentTypeLabel(type))}</span><em>${counts[type]||0}</em></button>`).join('')}</div><div class="document-toolbar"><div class="search-field">${icon('search')}<input id="documentSearch" type="search" value="${escapeHtml(state.documentSearch)}" placeholder="Search number, employee, project, supplier…"></div><select class="select" id="documentPeriodFilter"><option>All periods</option>${periods.map(period=>`<option ${state.documentPeriodFilter===period?'selected':''}>${escapeHtml(period)}</option>`).join('')}</select><select class="select" id="documentStatusFilter"><option>All statuses</option>${statuses.map(status=>`<option ${state.documentStatusFilter===status?'selected':''}>${escapeHtml(status)}</option>`).join('')}</select><button class="btn btn--ghost" data-document-reset>Reset</button></div><div class="document-workspace"><aside class="document-list-panel"><div class="document-list-head"><div><strong>${filtered.length} document${filtered.length===1?'':'s'}</strong><span>${state.documentPeriodFilter}</span></div><button class="icon-btn icon-btn--sm" data-document-generate aria-label="Finalize document">${icon('plus')}</button></div><div class="document-list">${filtered.length?filtered.map(doc=>`<button class="document-list-item ${doc.id===selected?.id?'is-active':''}" data-document-select="${escapeHtml(doc.id)}"><span class="document-list-item__icon">${escapeHtml(documentTypeCode(doc.type))}</span><span class="document-list-item__body"><strong>${escapeHtml(doc.title)}</strong><small>${escapeHtml(doc.number)} · ${escapeHtml(doc.entityName||doc.entityReference||'Company')}</small><em>${escapeHtml(doc.period||'No period')} · ${escapeHtml(doc.sourceReference||'Controlled source')}</em></span><span class="document-list-item__status">${documentStatusBadge(doc.status)}</span></button>`).join(''):'<div class="table-empty table-empty--card"><strong>No finalized documents match these filters.</strong><span>Finalize an eligible controlled source record for this workspace.</span></div>'}</div></aside><section class="document-preview-panel"><div class="document-preview-toolbar"><div class="document-preview-toolbar__meta"><strong>${selected?escapeHtml(selected.number):'Document preview'}</strong><span>${selected?`${escapeHtml(documentTypeLabel(selected.type))} · ${escapeHtml(selected.period||'')}`:'Select a document from the list'}</span></div><div class="document-preview-toolbar__actions"><button class="btn btn--secondary btn--sm" data-document-print ${selected?'':'disabled'}>${icon('document')} Print / Save PDF</button></div></div><div class="document-preview-stage">${documentSnapshotSummary(selected)}</div>${selected?`<div class="document-info-strip"><div><span>Document</span><strong>${escapeHtml(selected.number)}</strong></div><div><span>Source</span><strong>${escapeHtml(selected.sourceReference||'Controlled record')}</strong></div><div><span>Status</span><strong>${escapeHtml(selected.status)}</strong></div><div><span>Integrity</span><strong>${selected.integrityOk?'Verified':'Failed'}</strong></div></div>`:''}</section></div></section>`;
  }

  async function openDocumentGenerateDrawer() {
    state.drawerType='document-generate';state.drawerContext=null;drawerSave.hidden=false;drawerSave.disabled=true;drawerSave.textContent='Finalize Document';drawerTitle.textContent='Finalize business document';
    drawerBody.innerHTML='<section class="form-section"><div class="table-empty"><strong>Loading eligible source records…</strong><span>Only controlled final/locked/paid records can be finalized.</span></div></section>';
    drawer.classList.add('is-open');drawerScrim.classList.add('is-open');drawer.setAttribute('aria-hidden','false');
    try{
      const payload=await appApi(`/api/documents/sources/?workspace=${encodeURIComponent(state.workspace)}&period=${encodeURIComponent(periodKeyFromLabel(state.period))}`);
      const sources=(payload.sources||[]).filter(item=>!item.finalized);
      state.drawerContext={sources};
      if(!sources.length){drawerBody.innerHTML=`<section class="form-section"><div class="table-empty"><strong>No eligible sources for ${escapeHtml(state.period)}.</strong><span>Complete and lock/approve/pay the owning business record first, or the document may already be finalized.</span></div></section>`;return;}
      drawerSave.disabled=false;
      drawerBody.innerHTML=`<section class="form-section"><div class="form-section__head"><strong>Controlled source</strong><span>Final documents are immutable and can be created only once for each source/type.</span></div><div class="form-grid"><label class="form-field form-field--full"><span>Source record</span><select name="document-source">${sources.map((item,index)=>`<option value="${index}">${escapeHtml(documentTypeLabel(item.type))} · ${escapeHtml(item.label)}${item.amount!==null&&item.amount!==undefined?` · ${escapeHtml(formatCurrency(item.amount))}`:''}</option>`).join('')}</select></label><div class="form-field form-field--full"><span>Working period</span><strong>${escapeHtml(state.period)}</strong></div></div></section><section class="form-section" data-document-invoice-fields hidden><div class="form-section__head"><strong>Supplier invoice details</strong><span>Enter the supplier-issued invoice identity and explicit VAT amount. The backend does not infer tax treatment.</span></div><div class="form-grid"><label class="form-field"><span>Supplier invoice number</span><input name="document-invoice-number" autocomplete="off"></label><label class="form-field"><span>Issue date</span><input name="document-issue-date" type="date" value="${rentalTodayIso()}"></label><label class="form-field"><span>VAT amount (${escapeHtml(currencyCode())})</span><input name="document-vat-amount" type="number" min="0" step="0.01" value="0"></label></div></section>`;
      const sourceSelect=drawerBody.querySelector('[name="document-source"]');
      const sync=()=>{const item=sources[Number(sourceSelect.value)||0];drawerBody.querySelector('[data-document-invoice-fields]').hidden=item?.type!=='supplier_invoice';};
      sourceSelect.addEventListener('change',sync);sync();
    }catch(error){drawerBody.innerHTML=`<section class="form-section"><div class="table-empty"><strong>Eligible sources could not be loaded.</strong><span>${escapeHtml(error.message)}</span></div></section>`;showToast('Document sources unavailable',error.message);}
  }

  async function generateDocumentFromDrawer(get) {
    const sources=state.drawerContext?.sources||[];const index=Number(get('document-source')||0);const source=sources[index];
    if(!source){showToast('Source required','Choose an eligible controlled record.');return false;}
    const body={document_type:source.type,source_id:source.sourceId};
    if(source.type==='supplier_invoice'){
      const invoiceNumber=get('document-invoice-number').trim(),issueDate=get('document-issue-date'),vat=Number(get('document-vat-amount')||0),subtotal=Number(source.amount||0);
      if(!invoiceNumber||!issueDate||vat<0){showToast('Invoice details required','Enter the supplier invoice number, issue date and a non-negative VAT amount.');return false;}
      body.invoice_number=invoiceNumber;body.issue_date=issueDate;body.subtotal=subtotal.toFixed(2);body.vat_amount=vat.toFixed(2);body.total=(subtotal+vat).toFixed(2);
    }
    drawerSave.disabled=true;
    try{const payload=await appApi('/api/documents/',{method:'POST',body});const doc=payload.document;replaceStateRecord(state.businessDocuments,doc);state.documentDetails[doc.id]=doc;state.selectedDocumentId=doc.id;state.documentTab='all';state.documentPeriodFilter='All periods';closeDrawer();if(currentRoute()!=='documents')navigate('documents');else renderRoute();showToast('Document finalized',`${doc.number} is stored as an immutable final snapshot.`);return true;}
    catch(error){drawerSave.disabled=false;showToast('Document could not be finalized',error.message);return false;}
  }

  function printDocumentRecord(doc) {
    if(!doc)return;
    window.open(`/documents/${encodeURIComponent(doc.id)}/print/`,'_blank','noopener');
  }

  /* Reports and company settings */
  function reportPeriodIsoPrefix(period = state.reportPeriod) {
    return periodKeyFromLabel(period);
  }

  const reportCatalog = [
    { id:'workforce-cost', code:'WC', title:'Workforce Cost', meta:'Finalized internal + rental cost' },
    { id:'internal-payroll', code:'IP', title:'Internal Payroll', meta:'Payroll snapshot summary' },
    { id:'rental-project-cost', code:'PC', title:'Project Manpower Cost', meta:'Approved cost by project' },
    { id:'supplier-cost', code:'SC', title:'Supplier Cost', meta:'Approved cost by supplier' },
    { id:'overtime', code:'OT', title:'Overtime', meta:'Controlled overtime records' },
    { id:'advances', code:'AD', title:'Advances & Adjustments', meta:'Approved financial adjustments' },
    { id:'transfers', code:'TR', title:'Worker Transfers', meta:'Effective-dated assignment history' },
    { id:'payments', code:'PY', title:'Payments', meta:'Salary or supplier payment ledger' },
    { id:'wps', code:'WP', title:'WPS', meta:'Salary-payment configuration visibility' }
  ];

  function reportAllowedTypes(){return state.workspace==='management'?['workforce-cost']:state.workspace==='rental'?['rental-project-cost','supplier-cost','overtime','advances','transfers','payments']:['internal-payroll','overtime','advances','payments','wps'];}
  function reportCacheKey(type=state.reportType,period=state.reportPeriod,workspace=state.workspace){return `${workspace}|${type}|${period}`;}

  async function loadReportContext({render=true,force=false}={}){
    const key=reportCacheKey();if(state.reportLoadingKey===key)return;if(!force&&state.reportContexts[key])return;
    state.reportLoadingKey=key;
    try{const payload=await appApi(`/api/reports/?workspace=${encodeURIComponent(state.workspace)}&type=${encodeURIComponent(state.reportType)}&period=${encodeURIComponent(periodKeyFromLabel(state.reportPeriod))}`);state.reportContexts[key]={report:payload.report,periods:payload.periods||[]};if(render&&currentRoute()==='reports')renderRoute();}
    catch(error){showToast('Report unavailable',error.message);state.reportContexts[key]={error:error.message,report:null,periods:[]};if(render&&currentRoute()==='reports')renderRoute();}
    finally{state.reportLoadingKey=null;}
  }

  function reportModel(){const key=reportCacheKey();const cached=state.reportContexts[key];if(!cached&&!state.reportLoadingKey)queueMicrotask(()=>loadReportContext());return cached||null;}
  function reportFilteredRows(report){const q=state.reportSearch.trim().toLowerCase();return (report?.rows||[]).filter(row=>!q||row.map(value=>String(value??'')).join(' ').toLowerCase().includes(q));}
  function reportNumericColumn(column){return /amount|gross|net|cost|salary|deduction|adjustment|hours|paid|base|overtime/i.test(String(column));}

  function reportsTemplate() {
    const allowed=reportAllowedTypes();if(!allowed.includes(state.reportType))state.reportType=allowed[0];
    const catalog=reportCatalog.filter(item=>allowed.includes(item.id));const cached=reportModel();const report=cached?.report;const rows=reportFilteredRows(report);
    const periodOptions=(cached?.periods?.length?cached.periods:[{key:periodKeyFromLabel(state.reportPeriod),label:state.reportPeriod}]);
    if(!report)return `<section class="page report-page"><div class="page-head"><div class="page-head__copy"><span class="eyebrow">${escapeHtml(workspaceLabel())} · Reporting</span><h1>Reports</h1><p>Server-generated reporting from controlled payroll, settlement, payment and assignment records.</p></div></div><div class="table-empty table-empty--card"><strong>${cached?.error?'Report could not be loaded':'Loading report…'}</strong><span>${escapeHtml(cached?.error||`Fetching ${state.reportPeriod} from the company database.`)}</span></div></section>`;
    return `<section class="page report-page"><div class="page-head"><div class="page-head__copy"><span class="eyebrow">${escapeHtml(workspaceLabel())} · Reporting</span><h1>Reports</h1><p>${state.workspace==='management'?'Compare finalized workforce cost without merging operational ledgers.':state.workspace==='rental'?'Analyze approved supplier manpower, assignments, adjustments and payments.':'Analyze payroll snapshots, employee overtime, adjustments, salary payments and WPS configuration.'}</p></div><div class="page-head__actions"><button class="btn btn--secondary" data-report-print>${icon('document')} Print</button><button class="btn btn--primary" data-report-export>Export CSV</button></div></div><div class="report-layout"><aside class="report-catalog"><div class="report-catalog__head"><strong>Report library</strong><span>${catalog.length} reports</span></div>${catalog.map(item=>`<button class="report-catalog__item ${state.reportType===item.id?'is-active':''}" data-report-type="${item.id}"><span>${item.code}</span><span><strong>${item.title}</strong><small>${item.meta}</small></span>${icon('chevron')}</button>`).join('')}</aside><div class="report-main"><section class="panel panel--flush report-viewer"><div class="report-viewer__head"><div><span class="eyebrow">${escapeHtml(state.reportPeriod)}</span><h2>${escapeHtml(report.title)}</h2><p>${escapeHtml(report.description)}</p></div><span class="report-live-chip"><span></span>Company database</span></div><div class="report-filterbar"><div class="search-field">${icon('search')}<input id="reportSearch" type="search" value="${escapeHtml(state.reportSearch)}" placeholder="Search this report…"></div><select class="select" id="reportPeriod">${periodOptions.map(item=>`<option ${state.reportPeriod===item.label?'selected':''} value="${escapeHtml(item.label)}">${escapeHtml(item.label)}</option>`).join('')}</select><button class="btn btn--ghost" data-report-reset>Reset</button></div><div class="report-kpis">${(report.kpis||[]).map(([label,value])=>`<div><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`).join('')}</div><div class="table-wrap report-table-wrap"><table class="data-table report-table"><thead><tr>${(report.columns||[]).map(column=>`<th class="${reportNumericColumn(column)?'num':''}">${escapeHtml(column)}</th>`).join('')}</tr></thead><tbody>${rows.length?rows.map(row=>`<tr>${row.map((value,index)=>`<td class="${reportNumericColumn(report.columns[index])?'num':''}">${escapeHtml(value)}</td>`).join('')}</tr>`).join(''):`<tr><td colspan="${Math.max(1,(report.columns||[]).length)}"><div class="table-empty"><strong>No records for this report.</strong><span>Change the period or search. No estimated rows are generated.</span></div></td></tr>`}</tbody></table></div><div class="report-source-note"><span>${icon('info')}</span><p><strong>Data note.</strong> ${escapeHtml(report.sourceNote||'This report reads controlled company records.')}</p></div></section></div></div></section>`;
  }

  function exportCurrentReport() {
    const url=`/api/reports/export.csv?workspace=${encodeURIComponent(state.workspace)}&type=${encodeURIComponent(state.reportType)}&period=${encodeURIComponent(periodKeyFromLabel(state.reportPeriod))}`;
    const a=document.createElement('a');a.href=url;a.rel='noopener';document.body.appendChild(a);a.click();a.remove();
  }

  function printCurrentReport() {
    const cached=reportModel();const report=cached?.report;if(!report){showToast('Report not ready','Load the report before printing.');return;}
    const rows=reportFilteredRows(report);const win=window.open('','_blank','width=1150,height=900');if(!win){showToast('Print window blocked','Allow pop-ups to print this report.');return;}
    const head=(report.columns||[]).map(value=>`<th>${escapeHtml(value)}</th>`).join('');const body=rows.map(row=>`<tr>${row.map(value=>`<td>${escapeHtml(value)}</td>`).join('')}</tr>`).join('');
    win.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>${escapeHtml(report.title)} — ${escapeHtml(state.reportPeriod)}</title><style>body{font-family:Arial,sans-serif;color:#111;margin:32px}.head{display:flex;justify-content:space-between;align-items:flex-end;border-bottom:2px solid #111;padding-bottom:14px;margin-bottom:22px}.head h1{font-size:20px;margin:0 0 4px}.head p{margin:0;color:#666;font-size:11px}.meta{text-align:right;font-size:11px}table{border-collapse:collapse;width:100%;font-size:10px}th,td{padding:7px 6px;border-bottom:1px solid #ddd;text-align:left;vertical-align:top}th{background:#f6f6f6;font-size:9px;text-transform:uppercase}.note{margin-top:18px;padding-top:10px;border-top:1px solid #ddd;font-size:9px;color:#666}@media print{body{margin:12mm}}</style></head><body><div class="head"><div><h1>${escapeHtml(report.title)}</h1><p>${escapeHtml(report.description)}</p></div><div class="meta"><strong>${escapeHtml(state.reportPeriod)}</strong><br>${escapeHtml(serverAccess.company_name||'Company')}</div></div><table><thead><tr>${head}</tr></thead><tbody>${body||`<tr><td colspan="${Math.max(1,(report.columns||[]).length)}">No records.</td></tr>`}</tbody></table><div class="note">${escapeHtml(report.sourceNote||'')}</div><script>window.onload=()=>setTimeout(()=>window.print(),200)<\/script></body></html>`);win.document.close();
  }

  function settingsInputRow(name, label, value, hint='', attrs='') {
    const disabled = state.systemSettings.canManage ? '' : 'disabled';
    return `<label class="settings-field"><span><strong>${escapeHtml(label)}</strong><small>${escapeHtml(hint)}</small></span><input class="input" data-company-setting="${escapeHtml(name)}" value="${escapeHtml(value ?? '')}" ${attrs} ${disabled}></label>`;
  }

  function brandingAssetTemplate(kind, label, hint) {
    const general=state.systemSettings.general || {};
    const asset=general.branding?.[kind] || {configured:false,url:''};
    const canManage=state.systemSettings.canManage;
    return `<div class="branding-asset-card" data-brand-card="${kind}"><div class="branding-asset-preview">${asset.configured&&asset.url?`<img src="${escapeHtml(asset.url)}" alt="${escapeHtml(label)} preview">`:`<span>${icon('document')}<small>Not configured</small></span>`}</div><div class="branding-asset-copy"><strong>${escapeHtml(label)}</strong><span>${escapeHtml(hint)}</span><small>${asset.configured?'Configured · historical documents keep the version they were finalized with.':'PNG, JPEG or WebP.'}</small></div>${canManage?`<div class="branding-asset-actions"><input type="file" hidden accept="image/png,image/jpeg,image/webp" data-brand-file="${kind}"><button class="btn btn--secondary" type="button" data-brand-upload="${kind}">${asset.configured?'Replace':'Upload'}</button>${asset.configured?`<button class="btn btn--ghost" type="button" data-brand-clear="${kind}">Clear current</button>`:''}</div>`:''}</div>`;
  }

  function settingsPanelTemplate() {
    const general=state.systemSettings.general || {};
    if(state.settingsTab==='internal') {
      const policy=payrollContextForPeriod().policy || {};
      return `<section class="settings-panel"><div class="settings-panel__head"><div><span class="eyebrow">Internal payroll</span><h2>Payroll policy</h2><p>Salary components and overtime policies are maintained in Salary Setup. Payroll proration is a controlled server-side company rule.</p></div><div class="payment-head-actions"><button class="btn btn--secondary" data-route-link="salary-setup">Salary Setup</button><button class="btn btn--secondary" data-payroll-policy>Proration Policy</button></div></div><div class="settings-list"><div class="settings-summary-row"><span><strong>Attendance boundary</strong><small>Finance Review requires the selected attendance period to be locked.</small></span><strong>Enforced</strong></div><div class="settings-summary-row"><span><strong>Payroll proration</strong><small>Used for partial employment months or mid-month salary changes.</small></span><strong>${escapeHtml(policy.prorationLabel || 'Not configured')}</strong></div><div class="settings-summary-row"><span><strong>Approved payroll</strong><small>Financial snapshots cannot be recalculated after approval.</small></span><strong>Immutable</strong></div></div></section>`;
    }
    if(state.settingsTab==='rental') return `<section class="settings-panel"><div class="settings-panel__head"><div><span class="eyebrow">Rental workforce</span><h2>Rental lifecycle controls</h2><p>Rental rules are enforced by assignment, timesheet and settlement services rather than browser defaults.</p></div><button class="btn btn--secondary" data-route-link="rental-assignments">Open Assignments</button></div><div class="settings-list"><div class="settings-summary-row"><span><strong>Assignment history</strong><small>Transfers, trade changes and rate changes close the previous effective segment.</small></span><strong>Preserved</strong></div><div class="settings-summary-row"><span><strong>Timesheet completeness</strong><small>Every assigned worker-day requires hours or an explicit status before submission.</small></span><strong>Required</strong></div><div class="settings-summary-row"><span><strong>Settlement boundary</strong><small>Only locked project timesheets can feed supplier settlements.</small></span><strong>Enforced</strong></div></div></section>`;
    if(state.settingsTab==='wps') {
      const paymentSettings=paymentContextForPeriod().settings||{};
      const activeWpsTemplates=bankTemplatesAll('wps').filter(item=>item.active && !item.archived);
      return `<section class="settings-panel"><div class="settings-panel__head"><div><span class="eyebrow">WPS & salary payments</span><h2>Employer payment configuration</h2><p>Company payment identity and configured WPS export layouts used by the server-side salary payment workflow.</p></div><div class="payment-head-actions"><button class="btn btn--secondary" data-payment-settings>Edit Payment Settings</button><button class="btn btn--secondary" data-route-link="wps">Open WPS Workspace</button></div></div><div class="settings-list settings-list--two"><div class="settings-summary-row"><span><strong>Employer identifier</strong><small>Used only by templates that require it.</small></span><strong>${escapeHtml(paymentSettings.employerIdentifier||'Not configured')}</strong></div><div class="settings-summary-row"><span><strong>Employer bank</strong><small>${escapeHtml(paymentSettings.employerBankCode||'No bank code')}</small></span><strong>${escapeHtml(paymentSettings.employerBankName||'Not configured')}</strong></div><div class="settings-summary-row"><span><strong>Employer IBAN</strong><small>Encrypted at rest.</small></span><strong class="mono-cell">${escapeHtml(paymentSettings.employerIbanMasked||'Not configured')}</strong></div><div class="settings-summary-row"><span><strong>Bank customer reference</strong><small>Optional bank-specific identifier.</small></span><strong>${escapeHtml(paymentSettings.bankCustomerReference||'Not configured')}</strong></div><div class="settings-summary-row"><span><strong>Active WPS templates</strong><small>Export layouts are company-defined.</small></span><strong>${activeWpsTemplates.length}</strong></div></div></section>`;
    }
    if(state.settingsTab==='access') return `<section class="settings-panel"><div class="settings-panel__head"><div><span class="eyebrow">Access</span><h2>Workspace authorization</h2><p>Company-scoped Django memberships enforce workspace and action permissions on the server.</p></div><button class="btn btn--secondary" data-route-link="access-roles">Open Access & Roles</button></div><div class="settings-list"><div class="settings-summary-row"><span><strong>Current role</strong><small>Resolved from the active company membership.</small></span><strong>${escapeHtml(serverAccess.role_label||serverAccess.role||'—')}</strong></div><div class="settings-summary-row"><span><strong>Operational separation</strong><small>Internal Company and Rental Manpower keep separate masters, calculations and payment workflows.</small></span><strong>Enforced</strong></div><div class="settings-summary-row"><span><strong>Management workspace</strong><small>Aggregates controlled records without owning operational writes.</small></span><strong>Read-only</strong></div></div><div class="settings-policy-note"><span>${icon('info')}</span><p>Access changes are applied through company membership controls and audited server-side. Browser state never grants permissions.</p></div></section>`;
    if(state.settingsTab==='documents') {
      const branding=general.branding || {};
      const mode=general.documentBrandingMode || branding.mode || 'standard';
      return `<section class="settings-panel"><div class="settings-panel__head"><div><span class="eyebrow">Documents</span><h2>Final document controls</h2><p>Document identity, branding and finalization are server-controlled and snapshotted at finalization.</p></div><button class="btn btn--secondary" data-route-link="documents">Open Documents</button></div><div class="settings-list"><div class="settings-field"><span><strong>Print branding mode</strong><small>Use the normal issuer header, or reserve the page for a full-page letterhead image.</small></span><select class="select" data-company-setting="documentBrandingMode" ${state.systemSettings.canManage?'':'disabled'}><option value="standard" ${mode==='standard'?'selected':''}>Standard header</option><option value="letterhead" ${mode==='letterhead'?'selected':''}>Full-page letterhead</option></select></div><div class="settings-summary-row"><span><strong>Number allocation</strong><small>Company-scoped server sequence.</small></span><strong>Server controlled</strong></div><div class="settings-summary-row"><span><strong>Final records</strong><small>Source, payment evidence, issuer identity and branding versions are snapshotted at finalization.</small></span><strong>Immutable</strong></div><div class="settings-summary-row"><span><strong>Integrity</strong><small>Final JSON snapshots and historical branding assets are SHA-256 verified before printing.</small></span><strong>Verified</strong></div></div><div class="branding-asset-grid">${brandingAssetTemplate('logo','Company logo','Displayed beside the standard document header.')}${brandingAssetTemplate('letterhead','A4 letterhead','Full-page background used when Letterhead mode is selected.')}${brandingAssetTemplate('watermark','Watermark','Centered, faint background mark used on finalized documents.')}</div><div class="settings-policy-note"><span>${icon('info')}</span><p>Replacing or clearing current branding never rewrites previously finalized documents. Historical documents keep their original image hash and storage version.</p></div></section>`;
    }
    if(state.settingsTab==='workflow') return `<section class="settings-panel"><div class="settings-panel__head"><div><span class="eyebrow">Workflow</span><h2>Approval & audit controls</h2><p>Financial lifecycle rules are enforced by the owning Django services and database constraints.</p></div></div><div class="settings-list"><div class="settings-summary-row"><span><strong>Internal payroll</strong><small>Calculation, Finance Review, approval and payment are separate controlled states.</small></span><strong>Enforced</strong></div><div class="settings-summary-row"><span><strong>Rental settlement</strong><small>Locked timesheets feed reviewed/approved immutable settlement snapshots.</small></span><strong>Enforced</strong></div><div class="settings-summary-row"><span><strong>Payments</strong><small>Payment results, retries and reversals never rewrite approved financial snapshots.</small></span><strong>Audited</strong></div><div class="settings-summary-row"><span><strong>Audit trail</strong><small>Security and financial lifecycle events are append-only through the application layer.</small></span><strong>Enabled</strong></div></div></section>`;
    return `<section class="settings-panel"><div class="settings-panel__head"><div><span class="eyebrow">General</span><h2>Company settings</h2><p>Company identity, legal print details and locale values are stored in Django and audited when changed.</p></div></div><div class="settings-list">${settingsInputRow('companyName','Company name',general.companyName,'Operational display name.','maxlength="200" autocomplete="organization"')}${settingsInputRow('legalName','Legal name',general.legalName,'Legal entity name used on finalized payroll documents.','maxlength="250" autocomplete="organization"')}${settingsInputRow('commercialRegistration','Commercial registration',general.commercialRegistration,'Printed on finalized payroll and manpower documents.','maxlength="60" autocomplete="off"')}${settingsInputRow('vatNumber','VAT number',general.vatNumber,'Company VAT identity for branded documents.','maxlength="60" autocomplete="off"')}${settingsInputRow('documentAddress','Document address',general.documentAddress,'Registered/company address shown on final documents.','maxlength="400" autocomplete="street-address"')}${settingsInputRow('documentEmail','Document email',general.documentEmail,'Contact email shown on final documents.','maxlength="254" type="email" autocomplete="email"')}${settingsInputRow('documentPhone','Document phone',general.documentPhone,'Contact number shown on final documents.','maxlength="40" autocomplete="tel"')}${settingsInputRow('website','Website',general.website,'Website shown on final documents.','maxlength="300" type="url" autocomplete="url"')}<div class="settings-summary-row"><span><strong>Current role</strong><small>Only authorized company roles may change these settings.</small></span><strong>${escapeHtml(serverAccess.role_label||serverAccess.role||'—')}</strong></div>${settingsInputRow('timezone','Timezone',general.timezone,'IANA timezone, for example Asia/Riyadh.','autocomplete="off"')}${settingsInputRow('currency','Currency',general.currency,'ISO 4217 currency code.','maxlength="3" autocomplete="off"')}${settingsInputRow('country','Country',general.country,'ISO 3166-1 alpha-2 country code.','maxlength="2" autocomplete="off"')}</div>${state.systemSettings.canManage?'':'<div class="settings-policy-note"><span>'+icon('info')+'</span><p>Your company role has read-only access to these settings.</p></div>'}</section>`;
  }

  function settingsTemplate() {
    const tabs = state.workspace === 'management' ? [['general','General'],['documents','Documents'],['workflow','Workflow'],['access','Access']] : state.workspace === 'rental' ? [['general','General'],['rental','Rental Workforce'],['documents','Documents'],['workflow','Workflow']] : [['general','General'],['internal','Internal Payroll'],['wps','WPS'],['documents','Documents'],['workflow','Workflow']];
    if (!tabs.some(([id])=>id===state.settingsTab)) state.settingsTab = state.workspace === 'rental' ? 'rental' : 'general';
    const canSave=['general','documents'].includes(state.settingsTab) && state.systemSettings.canManage;
    return `<section class="page settings-page"><div class="page-head"><div class="page-head__copy"><span class="eyebrow">Payroll administration</span><h1>Settings</h1><p>Review server-enforced company, payroll, rental, document and workflow controls.</p></div><div class="page-head__actions">${canSave?'<button class="btn btn--primary" data-settings-save>Save Company Settings</button>':''}</div></div><div class="settings-layout"><nav class="settings-nav" aria-label="Settings sections">${tabs.map(([id,label])=>`<button class="${state.settingsTab===id?'is-active':''}" data-settings-tab="${id}"><span>${label}</span>${icon('chevron')}</button>`).join('')}</nav><div class="settings-main">${settingsPanelTemplate()}</div></div></section>`;
  }

  async function saveSettingsFromPage() {
    if(!state.systemSettings.canManage) return;
    const current=state.systemSettings.general || {};
    const field=(name,fallback='')=>{const control=document.querySelector(`[data-company-setting="${name}"]`);return control?String(control.value||'').trim():String(fallback||'').trim();};
    try {
      const payload=await appApi('/api/settings/',{method:'PATCH',body:{companyName:field('companyName',current.companyName),legalName:field('legalName',current.legalName),commercialRegistration:field('commercialRegistration',current.commercialRegistration),vatNumber:field('vatNumber',current.vatNumber),documentAddress:field('documentAddress',current.documentAddress),documentEmail:field('documentEmail',current.documentEmail),documentPhone:field('documentPhone',current.documentPhone),website:field('website',current.website),documentBrandingMode:field('documentBrandingMode',current.documentBrandingMode||'standard'),timezone:field('timezone',current.timezone),currency:field('currency',current.currency).toUpperCase(),country:field('country',current.country).toUpperCase()}});
      const updated=payload.settings || {};
      state.systemSettings.general={companyName:updated.companyName||current.companyName,legalName:updated.legalName||'',commercialRegistration:updated.commercialRegistration||'',vatNumber:updated.vatNumber||'',documentAddress:updated.documentAddress||'',documentEmail:updated.documentEmail||'',documentPhone:updated.documentPhone||'',website:updated.website||'',documentBrandingMode:updated.documentBrandingMode||'standard',branding:updated.branding||current.branding||{},timezone:updated.timezone||'',currency:updated.currency||'',country:updated.country||'',today:updated.today||current.today};
      serverAccess.company_name=state.systemSettings.general.companyName;
      renderWorkspaceShell();
      renderRoute();
      showToast('Company settings saved','Company identity, document branding mode and locale settings were updated and audited.');
    } catch(error) { showToast('Settings not saved',error.message); }
  }

  async function uploadBrandAsset(kind, file) {
    if(!state.systemSettings.canManage || !file) return;
    const formData=new FormData();formData.append('asset',file);
    try {
      const payload=await appMultipartApi(`/api/settings/branding/${encodeURIComponent(kind)}/`,{method:'POST',formData});
      state.systemSettings.general.branding=payload.branding||state.systemSettings.general.branding;
      state.systemSettings.general.documentBrandingMode=state.systemSettings.general.branding?.mode||state.systemSettings.general.documentBrandingMode;
      renderRoute();showToast('Branding image saved',`${kind[0].toUpperCase()+kind.slice(1)} is ready for newly finalized documents.`);
    } catch(error) { showToast('Branding image not saved',error.message); }
  }

  async function clearBrandAsset(kind) {
    if(!state.systemSettings.canManage) return;
    try {
      const payload=await appMultipartApi(`/api/settings/branding/${encodeURIComponent(kind)}/`,{method:'DELETE'});
      state.systemSettings.general.branding=payload.branding||state.systemSettings.general.branding;
      renderRoute();showToast('Current branding cleared',`New documents will no longer use the current ${kind}. Historical finalized documents are unchanged.`);
    } catch(error) { showToast('Branding image not cleared',error.message); }
  }

  function placeholderTemplate(route) {
    const info = APP_ROUTES[route] || { title: 'Page' };
    return `<section class="page"><div class="page-head"><div class="page-head__copy"><h1>${escapeHtml(info.title)}</h1><p>This route is not available in the current workspace or application version.</p></div></div><div class="placeholder"><div class="placeholder__inner"><div class="placeholder__icon">${icon('info')}</div><h2>${escapeHtml(info.title)}</h2><p>Return to the workspace overview or use the navigation to open an available function.</p><button class="btn btn--secondary" data-route-link="overview">Back to overview</button></div></div></section>`;
  }

  function currentPath() {
    return location.hash.replace(/^#\//, '').split('?')[0] || 'overview';
  }

  function currentRoute() {
    return currentPath().split('/')[0] || 'overview';
  }

  function currentProjectId() {
    const parts = currentPath().split('/');
    return parts[0] === 'projects' && parts[1] ? parts[1] : null;
  }

  function currentBranchId() {
    const parts = currentPath().split('/');
    return parts[0] === 'branches' && parts[1] ? parts[1] : null;
  }


  function currentDepartmentId() {
    const parts = currentPath().split('/');
    return parts[0] === 'departments' && parts[1] ? parts[1] : null;
  }

  function currentSupplierId() {
    const parts = currentPath().split('/');
    return parts[0] === 'suppliers' && parts[1] ? parts[1] : null;
  }

  function currentEmployeeId() {
    const parts = currentPath().split('/');
    return parts[0] === 'internal-employees' && parts[1] ? parts[1] : null;
  }

  function currentRentalWorkerId() {
    const parts = currentPath().split('/');
    return parts[0] === 'rental-workforce' && parts[1] ? parts[1] : null;
  }

  function navigate(route) {
    const target = `#/${route}`;
    if (location.hash === target) {
      renderRoute();
      return;
    }
    location.hash = target;
  }

  function reloadIntoRoute(route) {
    history.replaceState(null, '', `${location.pathname}${location.search}#/${route}`);
    location.reload();
  }

  async function restoreRecordFromBin(bucket, kind, id) {
    const endpoints = {
      branch:`/api/internal/branches/${encodeURIComponent(id)}/lifecycle/`,
      department:`/api/internal/departments/${encodeURIComponent(id)}/lifecycle/`,
      employee:`/api/internal/employees/${encodeURIComponent(id)}/lifecycle/`,
      supplier:`/api/rental/suppliers/${encodeURIComponent(id)}/lifecycle/`,
      worker:`/api/rental/workers/${encodeURIComponent(id)}/lifecycle/`,
      project:`/api/rental/projects/${encodeURIComponent(id)}/lifecycle/`
    };
    const endpoint = endpoints[kind];
    if (!endpoint) throw new Error('Unsupported record type.');
    const action = bucket === 'trash' ? 'restore_trash' : 'restore_archive';
    await appApi(endpoint, { method:'POST', body:{ action, reason:`${bucket === 'trash' ? 'Restored deleted record' : 'Restored from Archive'}` } });
    reloadIntoRoute(bucket);
  }

  function applyTimesheetFullscreenState() {
    const active = currentRoute() === 'timesheets' && !!state.timesheetFullscreen;
    document.documentElement.classList.toggle('timesheet-focus-mode', active);
    document.body.classList.toggle('timesheet-focus-mode', active);
    return active;
  }

  function leaveTimesheetFullscreen({ exitBrowser = true, rerender = true } = {}) {
    if (!state.timesheetFullscreen && !document.fullscreenElement) return;
    state.timesheetFullscreen = false;
    applyTimesheetFullscreenState();
    if (exitBrowser && document.fullscreenElement && document.exitFullscreen) document.exitFullscreen().catch(() => {});
    if (rerender && currentRoute() === 'timesheets') renderRoute();
  }

  function toggleTimesheetFullscreen() {
    const entering = !state.timesheetFullscreen;
    state.timesheetFullscreen = entering;
    applyTimesheetFullscreenState();
    if (entering && !document.fullscreenElement && document.documentElement.requestFullscreen) {
      document.documentElement.requestFullscreen().catch(() => {});
    } else if (!entering && document.fullscreenElement && document.exitFullscreen) {
      document.exitFullscreen().catch(() => {});
    }
    renderRoute();
  }

  function renderRoute() {
    const route = currentRoute();
    if (appShell) appShell.dataset.activeNav = route;
    if (route !== 'timesheets' && state.timesheetFullscreen) {
      state.timesheetFullscreen = false;
      if (document.fullscreenElement && document.exitFullscreen) document.exitFullscreen().catch(() => {});
    }
    applyTimesheetFullscreenState();
    if (!workspaceAllowsRoute(route)) { navigate('overview'); return; }
    const projectId = currentProjectId();
    const supplierId = currentSupplierId();
    const branchId = currentBranchId();
    const departmentId = currentDepartmentId();
    const employeeId = currentEmployeeId();
    const rentalWorkerId = currentRentalWorkerId();
    let title = APP_ROUTES[route]?.title || 'Overview';
    if (route === 'timesheets') state.timesheetWorkspace = state.workspace === 'rental' ? 'rental' : 'internal';
    if (route === 'payments') state.paymentTab = state.workspace === 'rental' ? 'supplier' : 'internal';
    if (route === 'adjustments') state.adjustmentWorkforce = state.workspace === 'rental' ? 'Rental' : 'Internal';
    if (route === 'documents') state.documentTab = state.workspace === 'rental' ? (state.documentTab === 'salary-slips' ? 'timesheets' : state.documentTab) : (['timesheets','settlements','invoices'].includes(state.documentTab) ? 'salary-slips' : state.documentTab);
    renderWorkspaceShell();

    if (route === 'overview') pageRoot.innerHTML = overviewTemplate();
    else if (route === 'management-cost') { pageRoot.innerHTML = managementCostTemplate(); title = 'Workforce Cost'; }
    else if (route === 'management-approvals') { pageRoot.innerHTML = managementApprovalsTemplate(); title = 'Approval Center'; }
    else if (route === 'management-audit') { pageRoot.innerHTML = managementAuditTemplate(); title = 'Audit Trail'; }
    else if (route === 'access-roles') { pageRoot.innerHTML = accessRolesTemplate(); title = 'Access & Roles'; }
    else if (route === 'projects' && projectId) {
      const project = state.projects.find(p => p.id === projectId);
      pageRoot.innerHTML = projectProfileTemplate(project);
      title = project?.name || 'Project';
    } else if (route === 'projects') pageRoot.innerHTML = projectsTemplate();
    else if (route === 'suppliers' && supplierId) {
      const supplier = state.suppliers.find(item => item.id === supplierId);
      pageRoot.innerHTML = supplierProfileTemplate(supplier);
      title = supplier?.name || 'Supplier';
    } else if (route === 'suppliers') pageRoot.innerHTML = suppliersTemplate();
    else if (route === 'branches' && branchId) {
      const branch = state.branches.find(item => item.id === branchId);
      pageRoot.innerHTML = branchProfileTemplate(branch);
      title = branch?.name || 'Branch / Office';
    } else if (route === 'branches') pageRoot.innerHTML = branchesTemplate();
    else if (route === 'departments' && departmentId) {
      const department = state.departments.find(item => item.id === departmentId);
      pageRoot.innerHTML = departmentProfileTemplate(department);
      title = department?.name || 'Department';
    } else if (route === 'departments') pageRoot.innerHTML = departmentsTemplate();
    else if (route === 'internal-employees' && employeeId) {
      const employee = state.employees.find(item => item.id === employeeId);
      pageRoot.innerHTML = employeeRecordPreviewTemplate(employee);
      title = employee?.name || 'Employee';
    } else if (route === 'internal-employees') pageRoot.innerHTML = internalEmployeesTemplate();
    else if (route === 'rental-onboarding') { pageRoot.innerHTML = rentalOnboardingTemplate(); title = 'Rental Worker Onboarding'; }
    else if (route === 'rental-assignments') { pageRoot.innerHTML = rentalAssignmentsTemplate(); title = 'Rental Assignments'; }
    else if (route === 'rental-workforce' && rentalWorkerId) {
      const worker = rentalWorkerById(rentalWorkerId);
      pageRoot.innerHTML = rentalWorkerPreviewTemplate(worker);
      title = worker?.name || 'Rental Worker';
    } else if (route === 'rental-workforce') pageRoot.innerHTML = rentalWorkforceTemplate();
    else if (route === 'salary-setup') pageRoot.innerHTML = salarySetupTemplate();
    else if (route === 'timesheets') pageRoot.innerHTML = timesheetsTemplate();
    else if (route === 'payroll-runs') pageRoot.innerHTML = payrollRunsTemplate();
    else if (route === 'rental-settlements') pageRoot.innerHTML = rentalSettlementsTemplate();
    else if (route === 'adjustments') pageRoot.innerHTML = adjustmentsTemplate();
    else if (route === 'bank-export') pageRoot.innerHTML = bankExportTemplate();
    else if (route === 'wps') pageRoot.innerHTML = wpsTemplate();
    else if (route === 'payments') pageRoot.innerHTML = paymentsTemplate();
    else if (route === 'documents') pageRoot.innerHTML = documentsTemplate();
    else if (route === 'archive') pageRoot.innerHTML = recordManagementTemplate('archive');
    else if (route === 'trash') pageRoot.innerHTML = recordManagementTemplate('trash');
    else if (route === 'reports') pageRoot.innerHTML = reportsTemplate();
    else if (route === 'settings') pageRoot.innerHTML = settingsTemplate();
    else pageRoot.innerHTML = placeholderTemplate(route);

    applyV2PrimitiveClasses(pageRoot);
    applyInternalExecutionV2Classes(pageRoot);
    applyRentalOperationsV2Classes(pageRoot);
    applyRentalFinancialV2Classes(pageRoot);
    applyRecordsManagementV2Classes(pageRoot);
    applyPayrollControlClasses(pageRoot);
    enhancePayrollSortableTables(pageRoot);

    const rootCrumb = workspaceLabel();
    const breadcrumbChevron = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9 18 6-6-6-6"/></svg>';
    const breadcrumbItem = (label, href = '', current = false) => `<span class="ui-v2-topbar__breadcrumb-item">${href ? `${breadcrumbChevron}<a href="${href}" title="${escapeHtml(label)}">${escapeHtml(label)}</a>` : `${current ? breadcrumbChevron : ''}<strong${current ? ' aria-current="page"' : ''} title="${escapeHtml(label)}">${escapeHtml(label)}</strong>`}</span>`;
    let breadcrumbHtml = breadcrumbItem(rootCrumb);
    if (route === 'projects' && projectId) breadcrumbHtml += breadcrumbItem('Projects', '#/projects') + breadcrumbItem(title, '', true);
    else if (route === 'suppliers' && supplierId) breadcrumbHtml += breadcrumbItem('Manpower Suppliers', '#/suppliers') + breadcrumbItem(title, '', true);
    else if (route === 'branches' && branchId) breadcrumbHtml += breadcrumbItem('Branches & Offices', '#/branches') + breadcrumbItem(title, '', true);
    else if (route === 'departments' && departmentId) breadcrumbHtml += breadcrumbItem('Departments', '#/departments') + breadcrumbItem(title, '', true);
    else if (route === 'internal-employees' && employeeId) breadcrumbHtml += breadcrumbItem('Internal Employees', '#/internal-employees') + breadcrumbItem(title, '', true);
    else if (route === 'rental-onboarding') breadcrumbHtml += breadcrumbItem('Rental Workforce', '#/rental-workforce') + breadcrumbItem('Onboarding', '', true);
    else if (route === 'rental-assignments') breadcrumbHtml += breadcrumbItem('Rental Workforce', '#/rental-workforce') + breadcrumbItem('Assignments', '', true);
    else if (route === 'rental-workforce' && rentalWorkerId) breadcrumbHtml += breadcrumbItem('Rental Workforce', '#/rental-workforce') + breadcrumbItem(title, '', true);
    else breadcrumbHtml += breadcrumbItem(title, '', true);
    breadcrumbs.innerHTML = breadcrumbHtml;

    document.title = `${title} — SESCCO MS`;
    document.querySelectorAll('[data-route]').forEach(el => {
      const active = el.dataset.route === route;
      el.classList.toggle('is-active', active);
      if (el.classList.contains('ui-v2-nav-item')) {
        el.dataset.active = String(active);
        if (active) el.setAttribute('aria-current', 'page'); else el.removeAttribute('aria-current');
      }
    });
    if (route === 'rental-onboarding') { const el = document.querySelector('[data-route="rental-workforce"]'); el?.classList.add('is-active'); if (el?.classList.contains('ui-v2-nav-item')) { el.dataset.active='true'; el.setAttribute('aria-current','page'); } }
    if (route === 'rental-assignments') { const el = document.querySelector('[data-route="rental-assignments"]'); el?.classList.add('is-active'); if (el?.classList.contains('ui-v2-nav-item')) { el.dataset.active='true'; el.setAttribute('aria-current','page'); } }
    wireDynamicActions();
    if (route === 'timesheets' && state.workspace === 'rental' && state.rentalTimesheetProject) {
      const key=rentalTimesheetRecordKey(); state.rentalTimesheetLoaded ||= new Set();
      if (!state.rentalTimesheetLoaded.has(key)) { state.rentalTimesheetLoaded.add(key); queueMicrotask(()=>loadRentalTimesheet()); }
    }
    pageRoot.focus({ preventScroll: true });
    closeMobileNav();
  }

  function wireDynamicActions() {
    document.querySelectorAll('[data-timesheet-fullscreen]').forEach(btn => btn.addEventListener('click', toggleTimesheetFullscreen));
    document.querySelectorAll('[data-route-link]').forEach(btn => btn.addEventListener('click', () => navigate(btn.dataset.routeLink)));
    document.querySelectorAll('[data-record-bin-restore]').forEach(btn => btn.addEventListener('click', async () => {
      const [bucket,kind,id] = String(btn.dataset.recordBinRestore || '').split('|');
      if (!bucket || !kind || !id) return;
      btn.disabled = true;
      try { await restoreRecordFromBin(bucket, kind, id); }
      catch (error) { btn.disabled = false; showToast('Restore not completed', error.message); }
    }));
    document.querySelectorAll('[data-workspace-jump]').forEach(btn => btn.addEventListener('click', () => switchWorkspace(btn.dataset.workspaceJump)));
    document.querySelectorAll('[data-management-open]').forEach(btn => btn.addEventListener('click', () => {
      const [workspace, route] = String(btn.dataset.managementOpen || '').split('|');
      if (!workspace || !route) return;
      if (!roleCanWorkspace(workspace)) { showToast('Access restricted', `${roleDefinition().label} cannot open this owning workspace.`); return; }
      const afterSwitch = () => navigate(route);
      if (state.workspace !== workspace) {
        if (state.workspace === 'internal') localStorage.setItem('payroll-ui-internal-period', state.period);
        else if (state.workspace === 'rental') localStorage.setItem('payroll-ui-rental-period', state.period);
        else localStorage.setItem('payroll-ui-management-period', state.period);
        state.workspace = workspace;
        localStorage.setItem('payroll-ui-workspace', workspace);
        syncWorkspaceUrl(workspace);
        state.period = workspace === 'rental'
          ? (localStorage.getItem('payroll-ui-rental-period') || defaultInternalPeriod)
          : workspace === 'management'
          ? (localStorage.getItem('payroll-ui-management-period') || defaultInternalPeriod)
          : (localStorage.getItem('payroll-ui-internal-period') || defaultInternalPeriod);
        localStorage.setItem('payroll-ui-period', state.period); periodLabel.textContent = state.period;
        document.querySelectorAll('[data-period]').forEach(x => x.classList.toggle('is-selected', x.dataset.period === state.period));
        renderWorkspaceShell();
      }
      afterSwitch();
    }));
    document.querySelectorAll('[data-management-approval-filter]').forEach(btn => btn.addEventListener('click', () => { state.managementApprovalFilter=btn.dataset.managementApprovalFilter; renderRoute(); }));
    const managementAuditSearch=document.getElementById('managementAuditSearch'); bindPayrollSearch(managementAuditSearch,value=>{state.managementAuditSearch=value;});
    const managementAuditType=document.getElementById('managementAuditType'); if(managementAuditType) managementAuditType.addEventListener('change',()=>{state.managementAuditType=managementAuditType.value;renderRoute();});
    document.querySelectorAll('[data-select-branch]').forEach(btn => btn.addEventListener('click', () => { state.branchSelectedId=btn.dataset.selectBranch; renderRoute(); }));
    document.querySelectorAll('[data-select-department]').forEach(btn => btn.addEventListener('click', () => { state.departmentSelectedId=btn.dataset.selectDepartment; renderRoute(); }));
    document.querySelectorAll('[data-branch-employees-filter]').forEach(btn => btn.addEventListener('click', () => { const branch=state.branches.find(item=>item.id===btn.dataset.branchEmployeesFilter); state.employeeBranch=branch?.name||'All branches'; state.employeeDepartment='All departments'; state.employeeSearch=''; navigate('internal-employees'); }));
    document.querySelectorAll('[data-department-employees-filter]').forEach(btn => btn.addEventListener('click', () => { const department=state.departments.find(item=>item.id===btn.dataset.departmentEmployeesFilter); state.employeeDepartment=department?.name||'All departments'; state.employeeBranch='All branches'; state.employeeSearch=''; navigate('internal-employees'); }));
    document.querySelectorAll('[data-open-branch]').forEach(btn => btn.addEventListener('click', () => navigate(`branches/${btn.dataset.openBranch}`)));
    document.querySelectorAll('[data-open-department]').forEach(btn => btn.addEventListener('click', () => navigate(`departments/${btn.dataset.openDepartment}`)));
    document.querySelectorAll('[data-branch-tab]').forEach(btn => btn.addEventListener('click', () => { state.branchTab=btn.dataset.branchTab; renderRoute(); }));
    document.querySelectorAll('[data-department-tab]').forEach(btn => btn.addEventListener('click', () => { state.departmentTab=btn.dataset.departmentTab; renderRoute(); }));
    const branchSearch=document.getElementById('branchSearch'); bindPayrollSearch(branchSearch,value=>{state.branchSearch=value;});
    document.querySelectorAll('[data-branch-status]').forEach(btn=>btn.addEventListener('click',()=>{state.branchStatus=btn.dataset.branchStatus;renderRoute();}));
    const branchStatusFilter=document.getElementById('branchStatusFilter'); if(branchStatusFilter) branchStatusFilter.addEventListener('change',()=>{state.branchStatus=branchStatusFilter.value;renderRoute();});
    const branchSortFilter=document.getElementById('branchSortFilter'); if(branchSortFilter) branchSortFilter.addEventListener('change',()=>{state.branchSort=branchSortFilter.value;localStorage.setItem('payroll-ui-branch-sort',state.branchSort);renderRoute();});
    document.querySelectorAll('[data-branch-reset]').forEach(btn=>btn.addEventListener('click',()=>{state.branchSearch='';state.branchStatus='Active';state.branchSort='code-asc';localStorage.setItem('payroll-ui-branch-sort',state.branchSort);renderRoute();}));
    const departmentSearch=document.getElementById('departmentSearch'); bindPayrollSearch(departmentSearch,value=>{state.departmentSearch=value;});
    document.querySelectorAll('[data-department-status]').forEach(btn=>btn.addEventListener('click',()=>{state.departmentStatus=btn.dataset.departmentStatus;renderRoute();}));
    const departmentStatusFilter=document.getElementById('departmentStatusFilter'); if(departmentStatusFilter) departmentStatusFilter.addEventListener('change',()=>{state.departmentStatus=departmentStatusFilter.value;renderRoute();});
    const departmentSortFilter=document.getElementById('departmentSortFilter'); if(departmentSortFilter) departmentSortFilter.addEventListener('change',()=>{state.departmentSort=departmentSortFilter.value;localStorage.setItem('payroll-ui-department-sort',state.departmentSort);renderRoute();});
    document.querySelectorAll('[data-department-reset]').forEach(btn=>btn.addEventListener('click',()=>{state.departmentSearch='';state.departmentStatus='Active';state.departmentSort='code-asc';localStorage.setItem('payroll-ui-department-sort',state.departmentSort);renderRoute();}));
    document.querySelectorAll('[data-edit-branch]').forEach(btn=>btn.addEventListener('click',()=>openBranchEditDrawer(btn.dataset.editBranch)));
    document.querySelectorAll('[data-edit-department]').forEach(btn=>btn.addEventListener('click',()=>openDepartmentEditDrawer(btn.dataset.editDepartment)));
    document.querySelectorAll('[data-organization-lifecycle]').forEach(btn=>btn.addEventListener('click',()=>{const [kind,id,action]=btn.dataset.organizationLifecycle.split('|');openOrganizationLifecycleDrawer(kind,id,action);}));
    document.querySelectorAll('[data-rental-master-lifecycle]').forEach(btn=>btn.addEventListener('click',()=>{const [kind,id,action]=btn.dataset.rentalMasterLifecycle.split('|');openRentalMasterLifecycleDrawer(kind,id,action);}));
    document.querySelectorAll('[data-config-lifecycle]').forEach(btn=>btn.addEventListener('click',()=>{const [kind,id,action]=btn.dataset.configLifecycle.split('|');openConfigurationLifecycleDrawer(kind,id,action);}));
    document.querySelectorAll('[data-change-employee-organization]').forEach(btn=>btn.addEventListener('click',()=>openEmployeeOrganizationDrawer(btn.dataset.changeEmployeeOrganization)));
    document.querySelectorAll('[data-open-branch-timesheet]').forEach(btn=>btn.addEventListener('click',()=>{const branch=state.branches.find(item=>item.id===btn.dataset.openBranchTimesheet);state.timesheetBranch=branch?.name||'All branches';state.timesheetDepartment='All departments';navigate('timesheets');}));
    document.querySelectorAll('[data-open-branch-payroll]').forEach(btn=>btn.addEventListener('click',()=>{const branch=state.branches.find(item=>item.id===btn.dataset.openBranchPayroll);state.payrollBranch=branch?.name||'All branches';state.payrollDepartment='All departments';navigate('payroll-runs');}));
    document.querySelectorAll('[data-open-department-payroll]').forEach(btn=>btn.addEventListener('click',()=>{const department=state.departments.find(item=>item.id===btn.dataset.openDepartmentPayroll);state.payrollDepartment=department?.name||'All departments';state.payrollBranch='All branches';navigate('payroll-runs');}));
    document.querySelectorAll('[data-filter-employee-department]').forEach(btn=>btn.addEventListener('click',()=>{state.employeeSearch='';state.employeeDepartment=btn.dataset.filterEmployeeDepartment;state.employeeBranch='All branches';navigate('internal-employees');}));
    document.querySelectorAll('[data-bank-export-tab]').forEach(btn=>btn.addEventListener('click',()=>{state.bankExportTab=btn.dataset.bankExportTab;localStorage.setItem('payroll-ui-bank-export-tab',state.bankExportTab);renderRoute();}));
    document.querySelectorAll('[data-bank-export-view]').forEach(btn=>btn.addEventListener('click',()=>{state.bankExportView=btn.dataset.bankExportView;localStorage.setItem('payroll-ui-bank-export-view',state.bankExportView);renderRoute();}));
    document.querySelectorAll('[data-bank-export-status]').forEach(btn=>btn.addEventListener('click',()=>{state.bankExportStatus=btn.dataset.bankExportStatus;renderRoute();}));
    const bankExportSearch=document.getElementById('bankExportSearch'); bindPayrollSearch(bankExportSearch,value=>{state.bankExportSearch=value;});
    const bankExportBranch=document.getElementById('bankExportBranch'); if(bankExportBranch) bankExportBranch.addEventListener('change',()=>{state.bankExportBranch=bankExportBranch.value;renderRoute();});
    const bankTemplateSelect=document.getElementById('bankTemplateSelect'); if(bankTemplateSelect) bankTemplateSelect.addEventListener('change',async()=>{state.bankTemplateId=bankTemplateSelect.value;localStorage.setItem('payroll-ui-bank-template-id',state.bankTemplateId);await loadSalaryPayments(state.period,{force:true});renderRoute();});
    document.querySelectorAll('[data-bank-batch-prepare]').forEach(btn=>btn.addEventListener('click',()=>preparePaymentChannel('bank_csv')));
    document.querySelectorAll('[data-bank-batch-open]').forEach(btn=>btn.addEventListener('click',()=>openBankBatchDrawer(btn.dataset.bankBatchOpen)));
    document.querySelectorAll('[data-bank-inspect]').forEach(btn=>btn.addEventListener('click',()=>openBankRowDrawer(btn.dataset.bankInspect)));
    document.querySelectorAll('[data-bank-template-pick]').forEach(btn=>btn.addEventListener('click',async()=>{const picked=bankTemplatesAll().find(item=>item.id===btn.dataset.bankTemplatePick);if(!picked)return;state.exportTemplateDetailId=picked.id;if(picked.channel==='wps'){state.wpsTemplateId=picked.id;localStorage.setItem('payroll-ui-wps-template-id',picked.id);}else{state.bankTemplateId=picked.id;localStorage.setItem('payroll-ui-bank-template-id',picked.id);}await loadSalaryPayments(state.period,{force:true});renderRoute();}));
    document.querySelectorAll('[data-bank-template-use]').forEach(btn=>btn.addEventListener('click',()=>{const template=bankTemplatesAll().find(item=>item.id===state.exportTemplateDetailId);if(!template)return;if(template.channel==='wps'){state.wpsTemplateId=template.id;localStorage.setItem('payroll-ui-wps-template-id',template.id);state.bankExportTab='wps';}else{state.bankTemplateId=template.id;localStorage.setItem('payroll-ui-bank-template-id',template.id);state.bankExportTab='bank';state.bankExportView='register';localStorage.setItem('payroll-ui-bank-export-view','register');}renderRoute();showToast('Export template selected',`${template.name} is now selected for ${template.channel==='wps'?'WPS':'bank'} validation and future batches.`);}));
    document.querySelectorAll('[data-bank-template-new]').forEach(btn=>btn.addEventListener('click',()=>openBankTemplateDrawer()));
    document.querySelectorAll('[data-bank-template-edit]').forEach(btn=>btn.addEventListener('click',()=>openBankTemplateDrawer(state.exportTemplateDetailId||state.bankTemplateId)));
    document.querySelectorAll('[data-bank-template-preview]').forEach(btn=>btn.addEventListener('click',()=>{const template=bankTemplatesAll().find(item=>item.id===state.exportTemplateDetailId)||bankTemplateById();if(template)showToast('Export headers',(template.headers||template.columns.map(key=>bankColumnCatalog[key]||key)).join(' · '));}));
    const bankResultFile=document.getElementById('bankResultFile'); if(bankResultFile) bankResultFile.addEventListener('change',async()=>{const file=bankResultFile.files?.[0];if(!file)return;const batch=[...paymentBatchesForPeriod()].filter(item=>item.channelValue==='bank_csv').sort((a,b)=>String(b.createdAt||'').localeCompare(String(a.createdAt||'')))[0];if(!batch){showToast('No bank batch','Prepare and start a bank salary-payment batch first.');return;}await importPaymentResults(batch.id,file);});
    document.querySelectorAll('[data-report-type]').forEach(btn=>btn.addEventListener('click',()=>{state.reportType=btn.dataset.reportType;state.reportSearch='';localStorage.setItem('payroll-ui-report-type',state.reportType);renderRoute();}));
    document.querySelectorAll('[data-open-report]').forEach(btn=>btn.addEventListener('click',()=>{state.reportType=btn.dataset.openReport||'workforce-cost';state.reportPeriod=btn.dataset.reportPeriod||state.period;state.reportSearch='';localStorage.setItem('payroll-ui-report-type',state.reportType);localStorage.setItem('payroll-ui-report-period',state.reportPeriod);if(currentRoute()==='reports')renderRoute();else navigate('reports');}));
    const reportSearch=document.getElementById('reportSearch'); bindPayrollSearch(reportSearch,value=>{state.reportSearch=value;});
    const reportPeriod=document.getElementById('reportPeriod'); if(reportPeriod) reportPeriod.addEventListener('change',()=>{state.reportPeriod=reportPeriod.value;localStorage.setItem('payroll-ui-report-period',state.reportPeriod);renderRoute();});
    document.querySelectorAll('[data-report-reset]').forEach(btn=>btn.addEventListener('click',()=>{state.reportSearch='';renderRoute();}));
    document.querySelectorAll('[data-report-export]').forEach(btn=>btn.addEventListener('click',exportCurrentReport));
    document.querySelectorAll('[data-report-print]').forEach(btn=>btn.addEventListener('click',printCurrentReport));
    document.querySelectorAll('[data-settings-tab]').forEach(btn=>btn.addEventListener('click',()=>{state.settingsTab=btn.dataset.settingsTab;localStorage.setItem('payroll-ui-settings-tab',state.settingsTab);renderRoute();}));
    document.querySelectorAll('[data-settings-save]').forEach(btn=>btn.addEventListener('click',saveSettingsFromPage));
    document.querySelectorAll('[data-brand-upload]').forEach(btn=>btn.addEventListener('click',()=>document.querySelector(`[data-brand-file="${btn.dataset.brandUpload}"]`)?.click()));
    document.querySelectorAll('[data-brand-file]').forEach(input=>input.addEventListener('change',()=>uploadBrandAsset(input.dataset.brandFile,input.files?.[0]||null)));
    document.querySelectorAll('[data-brand-clear]').forEach(btn=>btn.addEventListener('click',()=>clearBrandAsset(btn.dataset.brandClear)));
    document.querySelectorAll('[data-document-tab]').forEach(btn => btn.addEventListener('click', () => { state.documentTab=btn.dataset.documentTab; localStorage.setItem('payroll-ui-document-tab',state.documentTab); renderRoute(); }));
    const documentSearch=document.getElementById('documentSearch'); bindPayrollSearch(documentSearch,value=>{state.documentSearch=value;});
    const documentPeriod=document.getElementById('documentPeriodFilter'); if(documentPeriod) documentPeriod.addEventListener('change',()=>{state.documentPeriodFilter=documentPeriod.value;localStorage.setItem('payroll-ui-document-period',state.documentPeriodFilter);renderRoute();});
    const documentStatus=document.getElementById('documentStatusFilter'); if(documentStatus) documentStatus.addEventListener('change',()=>{state.documentStatusFilter=documentStatus.value;renderRoute();});
    document.querySelectorAll('[data-document-reset]').forEach(btn=>btn.addEventListener('click',()=>{state.documentSearch='';state.documentPeriodFilter='All periods';state.documentStatusFilter='All statuses';localStorage.setItem('payroll-ui-document-period',state.documentPeriodFilter);renderRoute();}));
    document.querySelectorAll('[data-document-select]').forEach(btn=>btn.addEventListener('click',()=>{state.selectedDocumentId=btn.dataset.documentSelect;localStorage.setItem('payroll-ui-selected-document',state.selectedDocumentId);renderRoute();}));
    document.querySelectorAll('[data-document-generate]').forEach(btn=>btn.addEventListener('click',()=>openDocumentGenerateDrawer()));
    document.querySelectorAll('[data-document-print]').forEach(btn=>btn.addEventListener('click',()=>{const doc=documentAllRecords().find(item=>item.id===state.selectedDocumentId);printDocumentRecord(doc);}));
    document.querySelectorAll('[data-adjustment-view]').forEach(btn => btn.addEventListener('click', () => { state.adjustmentView=btn.dataset.adjustmentView; renderRoute(); }));
    const adjustmentSearch=document.getElementById('adjustmentSearch');
    bindPayrollSearch(adjustmentSearch,value=>{state.adjustmentSearch=value;});
    const adjustmentWorkforce=document.getElementById('adjustmentWorkforce'); if(adjustmentWorkforce) adjustmentWorkforce.addEventListener('change',()=>{state.adjustmentWorkforce=adjustmentWorkforce.value;renderRoute();});
    const adjustmentType=document.getElementById('adjustmentType'); if(adjustmentType) adjustmentType.addEventListener('change',()=>{state.adjustmentType=adjustmentType.value;renderRoute();});
    const adjustmentStatus=document.getElementById('adjustmentStatus'); if(adjustmentStatus) adjustmentStatus.addEventListener('change',()=>{state.adjustmentStatus=adjustmentStatus.value;renderRoute();});
    const adjustmentProject=document.getElementById('adjustmentProject'); if(adjustmentProject) adjustmentProject.addEventListener('change',()=>{state.adjustmentProject=adjustmentProject.value;renderRoute();});
    const adjustmentSupplier=document.getElementById('adjustmentSupplier'); if(adjustmentSupplier) adjustmentSupplier.addEventListener('change',()=>{state.adjustmentSupplier=adjustmentSupplier.value;renderRoute();});
    document.querySelectorAll('[data-adjustment-reset]').forEach(btn=>btn.addEventListener('click',()=>{state.adjustmentSearch='';state.adjustmentWorkforce='All';state.adjustmentType='All';state.adjustmentStatus='All';state.adjustmentProject='All projects';state.adjustmentSupplier='All suppliers';renderRoute();}));
    document.querySelectorAll('[data-adjustment-detail]').forEach(btn=>btn.addEventListener('click',()=>openAdjustmentDetailDrawer(btn.dataset.adjustmentDetail)));
    document.querySelectorAll('[data-adjustment-action]').forEach(btn=>btn.addEventListener('click',async()=>{
      const found=adjustmentFindMutable(btn.dataset.adjustmentId); if(!found){showToast('Read-only transaction','This transaction cannot be changed from the current workflow state.');return;}
      const action=btn.dataset.adjustmentAction;
      if (found.kind === 'internal') {
        btn.disabled = true;
        try {
          const payload = await appApi(`/api/internal/adjustments/${encodeURIComponent(found.item.id)}/workflow/`, { method:'POST', body:{ action } });
          applyPayrollPayload(payload);
          renderRoute();
          showToast(action==='approve'?'Transaction approved':'Transaction submitted', action==='approve' ? `${adjustmentNormalizeType(found.item.type)} is now eligible for payroll calculation.` : 'The transaction is awaiting approval and remains excluded from payroll.');
        } catch (error) {
          showToast('Transaction workflow failed', error.message);
          btn.disabled = false;
        }
        return;
      }
      btn.disabled = true;
      try {
        const payload = await appApi(`/api/rental/adjustments/${encodeURIComponent(found.item.id)}/workflow/`, { method:'POST', body:{ action } });
        applyRentalSettlementPayload(payload);
        renderRoute();
        showToast(action==='approve'?'Transaction approved':'Transaction submitted', action==='approve' ? `${adjustmentNormalizeType(found.item.type)} is now eligible for the matching rental settlement calculation.` : 'The transaction is awaiting approval and remains excluded from settlement calculation.');
      } catch (error) {
        showToast('Transaction workflow failed', error.message);
        btn.disabled = false;
      }
    }));
    document.querySelectorAll('[data-settlement-tab]').forEach(btn => btn.addEventListener('click', () => { state.rentalSettlementTab=btn.dataset.settlementTab; renderRoute(); }));
    document.querySelectorAll('[data-settlement-tab-jump]').forEach(btn => btn.addEventListener('click', () => { state.rentalSettlementTab=btn.dataset.settlementTabJump; renderRoute(); }));
    document.querySelectorAll('[data-settlement-view]').forEach(btn => btn.addEventListener('click', () => { state.rentalSettlementView=btn.dataset.settlementView; if(state.rentalSettlementView==='supplier' && state.rentalSettlementSupplier==='All suppliers') state.rentalSettlementSupplier=rentalSettlementSuppliers(state.rentalSettlementProject,state.period)[0]?.id || state.suppliers[0]?.id || 'All suppliers'; renderRoute(); }));
    document.querySelectorAll('[data-open-rental-settlement-project]').forEach(btn => btn.addEventListener('click', () => {
      state.rentalSettlementProject=btn.dataset.openRentalSettlementProject;
      state.rentalSettlementSupplier=btn.dataset.settlementSupplier || 'All suppliers';
      state.rentalSettlementView='project'; state.rentalSettlementTab='current';
      if(btn.dataset.settlementPeriod){ state.period=btn.dataset.settlementPeriod; localStorage.setItem('payroll-ui-period',state.period); periodLabel.textContent=state.period; }
      localStorage.setItem('payroll-ui-rental-settlement-project',state.rentalSettlementProject);
      localStorage.setItem('payroll-ui-rental-settlement-supplier',state.rentalSettlementSupplier);
      navigate('rental-settlements');
    }));
    document.querySelectorAll('[data-open-rental-settlement-supplier]').forEach(btn => btn.addEventListener('click', () => {
      state.rentalSettlementSupplier=btn.dataset.openRentalSettlementSupplier;
      state.rentalSettlementView='supplier'; state.rentalSettlementTab='current';
      localStorage.setItem('payroll-ui-rental-settlement-supplier',state.rentalSettlementSupplier);
      if(currentRoute()==='rental-settlements') renderRoute(); else navigate('rental-settlements');
    }));
    const rentalSettlementSearch=document.getElementById('rentalSettlementSearch');
    bindPayrollSearch(rentalSettlementSearch,value=>{state.rentalSettlementSearch=value;});
    const rentalSettlementProject=document.getElementById('rentalSettlementProject');
    if(rentalSettlementProject) rentalSettlementProject.addEventListener('change',()=>{state.rentalSettlementProject=rentalSettlementProject.value;state.rentalSettlementSupplier='All suppliers';localStorage.setItem('payroll-ui-rental-settlement-project',state.rentalSettlementProject);renderRoute();});
    const rentalSettlementSupplier=document.getElementById('rentalSettlementSupplier');
    if(rentalSettlementSupplier) rentalSettlementSupplier.addEventListener('change',()=>{state.rentalSettlementSupplier=rentalSettlementSupplier.value;localStorage.setItem('payroll-ui-rental-settlement-supplier',state.rentalSettlementSupplier);renderRoute();});
    const rentalSettlementSupplierMaster=document.getElementById('rentalSettlementSupplierMaster');
    if(rentalSettlementSupplierMaster) rentalSettlementSupplierMaster.addEventListener('change',()=>{state.rentalSettlementSupplier=rentalSettlementSupplierMaster.value;localStorage.setItem('payroll-ui-rental-settlement-supplier',state.rentalSettlementSupplier);renderRoute();});
    const rentalSettlementStatus=document.getElementById('rentalSettlementStatus');
    if(rentalSettlementStatus) rentalSettlementStatus.addEventListener('change',()=>{state.rentalSettlementStatus=rentalSettlementStatus.value;renderRoute();});
    document.querySelectorAll('[data-settlement-reset]').forEach(btn=>btn.addEventListener('click',()=>{state.rentalSettlementSearch='';state.rentalSettlementStatus='All';if(state.rentalSettlementView==='project')state.rentalSettlementSupplier='All suppliers';renderRoute();}));
    document.querySelectorAll('[data-settlement-worker]').forEach(btn=>btn.addEventListener('click',()=>openRentalSettlementWorkerDrawer(btn.dataset.settlementWorker,btn.dataset.projectId)));
    document.querySelectorAll('[data-settlement-progress]').forEach(btn=>btn.addEventListener('click',()=>{if(btn.dataset.settlementProgress)progressRentalSettlement(btn.dataset.settlementProgress);}));
    document.querySelectorAll('[data-settlement-return]').forEach(btn=>btn.addEventListener('click',returnRentalSettlementForChanges));
    document.querySelectorAll('[data-settlement-close]').forEach(btn=>btn.addEventListener('click',closeRentalSettlementPeriod));
    document.querySelectorAll('[data-quick-add]').forEach(btn => btn.addEventListener('click', () => openQuickDrawer(btn.dataset.quickAdd, btn.dataset.adjustmentPersonContext ? { workforce:btn.dataset.adjustmentWorkforceContext || (state.workspace==='rental'?'Rental Worker':'Internal Employee'), personId:btn.dataset.adjustmentPersonContext, type:btn.dataset.adjustmentTypeContext || 'Salary Advance' } : (btn.dataset.employeeBranchContext || btn.dataset.employeeDepartmentContext) ? { branchId:btn.dataset.employeeBranchContext || null, departmentId:btn.dataset.employeeDepartmentContext || null } : null)));
    document.querySelectorAll('[data-open-project]').forEach(btn => btn.addEventListener('click', () => navigate(`projects/${btn.dataset.openProject}`)));
    document.querySelectorAll('[data-open-supplier]').forEach(btn => btn.addEventListener('click', () => navigate(`suppliers/${btn.dataset.openSupplier}`)));
    document.querySelectorAll('[data-open-employee]').forEach(btn => btn.addEventListener('click', () => navigate(`internal-employees/${btn.dataset.openEmployee}`)));
    document.querySelectorAll('tr[data-open-employee]').forEach(row => row.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); navigate(`internal-employees/${row.dataset.openEmployee}`); } }));
    document.querySelectorAll('[data-open-rental-worker]').forEach(btn => btn.addEventListener('click', () => { state.rentalWorkerTab='overview'; navigate(`rental-workforce/${btn.dataset.openRentalWorker}`); }));
    document.querySelectorAll('[data-open-rental-timesheet-project]').forEach(btn => btn.addEventListener('click', () => {
      state.timesheetWorkspace='rental';
      localStorage.setItem('payroll-ui-timesheet-workspace','rental');
      state.rentalTimesheetProject=btn.dataset.openRentalTimesheetProject;
      const nextRentalTimesheetPeriod=btn.dataset.timesheetPeriod || state.rentalTimesheetPeriod || defaultInternalPeriod;
      if (nextRentalTimesheetPeriod !== state.rentalTimesheetPeriod) state.rentalTimesheetBulkDay=defaultTimesheetDay(nextRentalTimesheetPeriod);
      state.rentalTimesheetPeriod=nextRentalTimesheetPeriod;
      state.period=state.rentalTimesheetPeriod;
      localStorage.setItem('payroll-ui-rental-timesheet-project',state.rentalTimesheetProject);
      localStorage.setItem('payroll-ui-rental-timesheet-period',state.rentalTimesheetPeriod);
      localStorage.setItem('payroll-ui-period',state.period);
      periodLabel.textContent=state.period;
      navigate('timesheets');
    }));
    document.querySelectorAll('[data-open-rental-timesheet-supplier]').forEach(btn => btn.addEventListener('click', () => {
      const supplierId=btn.dataset.openRentalTimesheetSupplier;
      const deployed=state.rentalWorkers.find(worker=>worker.supplierId===supplierId && rentalAssignmentsFor(worker).some(item=>item.kind==='assignment'));
      const projectId=deployed ? rentalAssignmentsFor(deployed).find(item=>item.kind==='assignment')?.projectId : null;
      state.timesheetWorkspace='rental';
      localStorage.setItem('payroll-ui-timesheet-workspace','rental');
      state.rentalTimesheetSupplier=supplierId;
      if(projectId) state.rentalTimesheetProject=projectId;
      state.rentalTimesheetPeriod=state.rentalTimesheetPeriod || defaultInternalPeriod;
      state.period=state.rentalTimesheetPeriod;
      localStorage.setItem('payroll-ui-rental-timesheet-project',state.rentalTimesheetProject);
      localStorage.setItem('payroll-ui-rental-timesheet-period',state.rentalTimesheetPeriod);
      localStorage.setItem('payroll-ui-period',state.period);
      periodLabel.textContent=state.period;
      navigate('timesheets');
    }));
    document.querySelectorAll('[data-assignment-tab]').forEach(btn => btn.addEventListener('click', () => { state.rentalAssignmentTab = btn.dataset.assignmentTab; renderRoute(); }));
    document.querySelectorAll('[data-assignment-tab-jump]').forEach(btn => btn.addEventListener('click', () => { state.rentalAssignmentTab = btn.dataset.assignmentTabJump; renderRoute(); }));
    document.querySelectorAll('[data-assignment-type-jump]').forEach(btn => btn.addEventListener('click', () => { state.rentalAssignmentTab='activity'; state.rentalAssignmentType=btn.dataset.assignmentTypeJump; renderRoute(); }));
    document.querySelectorAll('[data-assignment-worker]').forEach(btn => btn.addEventListener('click', () => { state.rentalWorkerTab='assignments'; navigate(`rental-workforce/${btn.dataset.assignmentWorker}`); }));
    document.querySelectorAll('[data-rental-available-jump]').forEach(btn => btn.addEventListener('click', () => { state.rentalAssignmentTab='pool'; renderRoute(); }));
    document.querySelectorAll('[data-assignment-reset]').forEach(btn => btn.addEventListener('click', () => { state.rentalAssignmentSearch=''; state.rentalAssignmentSupplier='All suppliers'; state.rentalAssignmentProject='All projects'; state.rentalAssignmentType='All activity'; renderRoute(); }));
    document.querySelectorAll('[data-project-assignment-activity]').forEach(btn => btn.addEventListener('click', () => { state.rentalAssignmentTab='activity'; state.rentalAssignmentProject=btn.dataset.projectAssignmentActivity; state.rentalAssignmentSupplier='All suppliers'; state.rentalAssignmentType='All activity'; state.rentalAssignmentSearch=''; navigate('rental-assignments'); }));
    document.querySelectorAll('[data-supplier-assignment-activity]').forEach(btn => btn.addEventListener('click', () => { state.rentalAssignmentTab='activity'; state.rentalAssignmentSupplier=btn.dataset.supplierAssignmentActivity; state.rentalAssignmentProject='All projects'; state.rentalAssignmentType='All activity'; state.rentalAssignmentSearch=''; navigate('rental-assignments'); }));
    const rentalAssignmentSearch = document.getElementById('rentalAssignmentSearch');
    bindPayrollSearch(rentalAssignmentSearch,value=>{state.rentalAssignmentSearch=value;});
    const rentalAssignmentSupplier = document.getElementById('rentalAssignmentSupplier'); if (rentalAssignmentSupplier) rentalAssignmentSupplier.addEventListener('change', () => { state.rentalAssignmentSupplier=rentalAssignmentSupplier.value; renderRoute(); });
    const rentalAssignmentProject = document.getElementById('rentalAssignmentProject'); if (rentalAssignmentProject) rentalAssignmentProject.addEventListener('change', () => { state.rentalAssignmentProject=rentalAssignmentProject.value; renderRoute(); });
    const rentalAssignmentType = document.getElementById('rentalAssignmentType'); if (rentalAssignmentType) rentalAssignmentType.addEventListener('change', () => { state.rentalAssignmentType=rentalAssignmentType.value; renderRoute(); });

    const rentalSearch = document.getElementById('rentalSearch');
    bindPayrollSearch(rentalSearch,value=>{state.rentalSearch=value;});
    const rentalSupplierFilter = document.getElementById('rentalSupplierFilter');
    if (rentalSupplierFilter) rentalSupplierFilter.addEventListener('change', () => { state.rentalSupplier = rentalSupplierFilter.value; renderRoute(); });
    const rentalProjectFilter = document.getElementById('rentalProjectFilter');
    if (rentalProjectFilter) rentalProjectFilter.addEventListener('change', () => { state.rentalProject = rentalProjectFilter.value; renderRoute(); });
    const rentalTradeFilter = document.getElementById('rentalTradeFilter');
    if (rentalTradeFilter) rentalTradeFilter.addEventListener('change', () => { state.rentalTrade = rentalTradeFilter.value; renderRoute(); });
    const rentalRateFilter = document.getElementById('rentalRateFilter');
    if (rentalRateFilter) rentalRateFilter.addEventListener('change', () => { state.rentalRateType = rentalRateFilter.value; renderRoute(); });
    document.querySelectorAll('[data-rental-status]').forEach(btn => btn.addEventListener('click', () => { state.rentalStatus = btn.dataset.rentalStatus; renderRoute(); }));
    document.querySelectorAll('[data-rental-summary]').forEach(btn => btn.addEventListener('click', () => { state.rentalStatus = btn.dataset.rentalSummary; renderRoute(); }));
    document.querySelectorAll('[data-rental-status-jump]').forEach(btn => btn.addEventListener('click', () => { state.rentalStatus = btn.dataset.rentalStatusJump; navigate('rental-workforce'); if (currentRoute() === 'rental-workforce' && !currentRentalWorkerId()) renderRoute(); }));
    document.querySelectorAll('[data-rental-reset]').forEach(btn => btn.addEventListener('click', () => { state.rentalSearch=''; state.rentalStatus='All'; state.rentalSupplier='All suppliers'; state.rentalProject='All projects'; state.rentalTrade='All trades'; state.rentalRateType='All rate types'; renderRoute(); }));
    document.querySelectorAll('[data-rental-worker-tab]').forEach(btn => btn.addEventListener('click', () => { state.rentalWorkerTab = btn.dataset.rentalWorkerTab; renderRoute(); }));
    document.querySelectorAll('[data-rental-worker-menu]').forEach(btn => btn.addEventListener('click', () => {
      const worker = rentalWorkerById(btn.dataset.rentalWorkerMenu);
      if (!worker) return;
      state.rentalWorkerTab = 'assignments';
      if (currentRentalWorkerId() === worker.id) renderRoute(); else navigate(`rental-workforce/${worker.id}`);
      showToast('Assignment history opened', `${worker.name} keeps transfers, trade changes, rate changes and releases as dated history.`);
    }));
    document.querySelectorAll('[data-rental-worker-action]').forEach(btn => btn.addEventListener('click', () => {
      if (btn.dataset.rentalWorkerAction === 'advance') openQuickDrawer('advance',{ workforce:'Rental Worker', personId:btn.dataset.workerId, type:'Salary Advance' });
      else openRentalWorkerActionDrawer(btn.dataset.workerId, btn.dataset.rentalWorkerAction);
    }));

    document.querySelectorAll('[data-onboarding-create-master]').forEach(btn => btn.addEventListener('click', () => openQuickDrawer(btn.dataset.onboardingCreateMaster, { returnTo:'rental-onboarding', selectTarget:btn.dataset.onboardingCreateMaster })));
    document.querySelectorAll('[data-supplier-bulk-onboard]').forEach(btn => btn.addEventListener('click', () => { state.rentalOnboarding.defaultSupplierId=btn.dataset.supplierBulkOnboard; navigate('rental-onboarding'); }));
    document.querySelectorAll('[data-project-bulk-onboard]').forEach(btn => btn.addEventListener('click', () => { navigate('rental-onboarding'); showToast('Worker master onboarding','Create supplier-owned worker masters first. Project assignment is managed separately.'); }));
    document.querySelectorAll('[data-supplier-add-worker]').forEach(btn => btn.addEventListener('click', () => { state.inlineRentalDraft={'rental-worker-supplier':btn.dataset.supplierAddWorker}; openQuickDrawer('rental-worker',{resumeInline:true}); }));
    document.querySelectorAll('[data-project-add-worker]').forEach(btn => btn.addEventListener('click', () => { openQuickDrawer('rental-worker'); showToast('Worker master first','Create the permanent supplier worker first; project assignment is a separate controlled step.'); }));
    const onboardingSupplier=document.getElementById('onboardingDefaultSupplier'); if (onboardingSupplier) onboardingSupplier.addEventListener('change',()=>{state.rentalOnboarding.defaultSupplierId=onboardingSupplier.value;});
    const onboardingPaste=document.getElementById('onboardingPaste'); if (onboardingPaste) onboardingPaste.addEventListener('input',()=>{state.rentalOnboarding.sourceText=onboardingPaste.value;});
    document.querySelectorAll('[data-onboarding-stage]').forEach(btn=>btn.addEventListener('click',()=>{const parsed=rentalOnboardingParse(state.rentalOnboarding.sourceText); if(!parsed.length){showToast('Nothing to stage','Paste Excel/CSV rows first.');return;} state.rentalOnboarding.rows=[...state.rentalOnboarding.rows,...parsed]; renderRoute(); showToast('Rows staged',`${parsed.length} worker row${parsed.length===1?'':'s'} added to validation.`);}));
    document.querySelectorAll('[data-onboarding-add-row]').forEach(btn=>btn.addEventListener('click',()=>{state.rentalOnboarding.rows.push(rentalOnboardingNewRow({}));renderRoute();}));
    document.querySelectorAll('[data-onboarding-apply-defaults]').forEach(btn=>btn.addEventListener('click',()=>{state.rentalOnboarding.rows.forEach(row=>{if(!row.ignored)row.supplierId=state.rentalOnboarding.defaultSupplierId;});renderRoute();showToast('Supplier default applied','The selected managed supplier was applied to staged rows.');}));
    document.querySelectorAll('[data-onboarding-remove-row]').forEach(btn=>btn.addEventListener('click',()=>{const row=state.rentalOnboarding.rows.find(r=>r.rowId===btn.dataset.onboardingRemoveRow);if(row)row.ignored=true;renderRoute();}));
    document.querySelectorAll('[data-onboarding-row]').forEach(tr=>{const row=state.rentalOnboarding.rows.find(r=>r.rowId===tr.dataset.onboardingRow);if(!row)return;tr.querySelectorAll('[data-onboarding-field]').forEach(control=>{const update=()=>{row[control.dataset.onboardingField]=control.value;};control.addEventListener('change',()=>{update();renderRoute();});if(control.tagName==='INPUT')control.addEventListener('blur',()=>{update();renderRoute();});});});
    const csvInput=document.getElementById('onboardingCsvFile'); if(csvInput)csvInput.addEventListener('change',()=>{const file=csvInput.files?.[0];if(!file)return;const reader=new FileReader();reader.onload=()=>{state.rentalOnboarding.sourceText=String(reader.result||'');const parsed=rentalOnboardingParse(state.rentalOnboarding.sourceText);state.rentalOnboarding.rows=[...state.rentalOnboarding.rows,...parsed];renderRoute();showToast('CSV staged',`${parsed.length} row${parsed.length===1?'':'s'} loaded from ${file.name}.`);};reader.readAsText(file);});
    document.querySelectorAll('[data-onboarding-import]').forEach(btn=>btn.addEventListener('click',async()=>{
      const rows=state.rentalOnboarding.rows.filter(r=>!r.ignored);
      const blocked=rows.filter(r=>rentalOnboardingValidateRow(r,rows).blockers.length);
      if(blocked.length){showToast('Resolve blocked rows',`${blocked.length} staged row${blocked.length===1?'':'s'} cannot be created yet.`);return;}
      if(!rows.length){showToast('No workers staged','Add at least one worker row.');return;}
      try {
        btn.disabled=true;
        const body={rows:rows.map(row=>({worker_number:row.workerCode,full_name:row.name,national_id:row.nationalId,phone:row.phone,supplier_id:row.supplierId,status:row.status,notes:row.notes}))};
        await appApi('/api/rental/workers/import/',{method:'POST',body:{...body,dry_run:true}});
        const payload=await appApi('/api/rental/workers/import/',{method:'POST',body});
        (payload.workers||[]).forEach(worker=>replaceStateRecord(state.rentalWorkers,worker));
        state.rentalOnboarding.lastImport={count:Number(payload.created||0),at:payrollTimestamp(new Date().toISOString())};
        state.rentalOnboarding.rows=[];state.rentalOnboarding.sourceText='';renderRoute();
        showToast('Workers created',`${payload.created||0} permanent rental worker master${Number(payload.created||0)===1?'':'s'} created.`);
      } catch(error) { showToast('Worker import blocked',error.message); }
      finally { btn.disabled=false; }
    }));

    const payrollSearch = document.getElementById('payrollSearch');
    bindPayrollSearch(payrollSearch,value=>{state.payrollSearch=value;});
    const payrollBranchFilter = document.getElementById('payrollBranchFilter');
    if (payrollBranchFilter) payrollBranchFilter.addEventListener('change', () => { state.payrollBranch = payrollBranchFilter.value; renderRoute(); });
    const payrollDepartmentFilter = document.getElementById('payrollDepartmentFilter');
    if (payrollDepartmentFilter) payrollDepartmentFilter.addEventListener('change', () => { state.payrollDepartment = payrollDepartmentFilter.value; renderRoute(); });
    const payrollReadinessFilter = document.getElementById('payrollReadinessFilter');
    if (payrollReadinessFilter) payrollReadinessFilter.addEventListener('change', () => { state.payrollReadiness = payrollReadinessFilter.value; renderRoute(); });
    document.querySelectorAll('[data-payroll-reset-filter]').forEach(btn => btn.addEventListener('click', () => { state.payrollSearch=''; state.payrollBranch='All branches'; state.payrollDepartment='All departments'; state.payrollReadiness='All'; renderRoute(); }));
    document.querySelectorAll('[data-payroll-policy]').forEach(btn => btn.addEventListener('click', openPayrollPolicyDrawer));
    document.querySelectorAll('[data-payroll-row]').forEach(btn => btn.addEventListener('click', () => openPayrollDetailDrawer(btn.dataset.payrollRow)));
    document.querySelectorAll('[data-payroll-calculate]').forEach(btn => btn.addEventListener('click', async () => {
      btn.disabled = true;
      try {
        const payload = await requestPayrollCalculation();
        const totals = payrollTotals(payload.rows || []);
        state.payrollView = 'register';
        renderRoute();
        showToast('Payroll calculated', `${(payload.rows || []).length} employee${(payload.rows || []).length === 1 ? '' : 's'} · ${formatCurrency(totals.net)} net payable.`);
      } catch (error) {
        showToast('Payroll calculation blocked', error.message);
        btn.disabled = false;
      }
    }));
    document.querySelectorAll('[data-payroll-submit-review]').forEach(btn => btn.addEventListener('click', async () => {
      btn.disabled = true;
      try {
        await requestPayrollWorkflow('submit_review');
        state.payrollView = 'review';
        renderRoute();
        showToast('Payroll submitted for review', `${state.period} is now in Finance Review.`);
      } catch (error) {
        showToast('Payroll could not be submitted', error.message);
        btn.disabled = false;
      }
    }));
    document.querySelectorAll('[data-payroll-reset-run]').forEach(btn => btn.addEventListener('click', async () => {
      btn.disabled = true;
      try {
        await requestPayrollWorkflow('reset');
        state.payrollView='register';
        renderRoute();
        showToast('Payroll reset to Draft', 'The calculated financial snapshot was cleared. Audit history remains retained.');
      } catch (error) {
        showToast('Payroll could not be reset', error.message);
        btn.disabled = false;
      }
    }));

    document.querySelectorAll('[data-payroll-view]').forEach(btn => btn.addEventListener('click', () => { state.payrollView = btn.dataset.payrollView; renderRoute(); }));
    document.querySelectorAll('[data-payroll-view-review]').forEach(btn => btn.addEventListener('click', () => { state.payrollView='review'; renderRoute(); }));
    document.querySelectorAll('[data-review-severity]').forEach(btn => btn.addEventListener('click', () => { state.payrollReviewSeverity = btn.dataset.reviewSeverity; renderRoute(); }));
    document.querySelectorAll('[data-review-open-row]').forEach(btn => btn.addEventListener('click', () => openPayrollDetailDrawer(btn.dataset.reviewOpenRow)));
    document.querySelectorAll('[data-review-route]').forEach(btn => btn.addEventListener('click', () => navigate(btn.dataset.reviewRoute)));
    document.querySelectorAll('[data-review-previous-period]').forEach(btn => btn.addEventListener('click', () => {
      const previous = payrollPreviousPeriod();
      if (!previous) return;
      const currentPeriod = state.period;
      state.period = previous;
      localStorage.setItem('payroll-ui-period', previous);
      periodLabel.textContent = previous;
      state.payrollView = 'register';
      document.querySelectorAll('[data-period]').forEach(x => x.classList.toggle('is-selected', x.dataset.period === previous));
      renderRoute();
      showToast('Previous period opened', `${previous} is ready for payroll calculation. Once it has a snapshot, switch back to ${currentPeriod} for automatic variance comparison.`);
    }));
    document.querySelectorAll('[data-review-return]').forEach(btn => btn.addEventListener('click', () => openPayrollReviewDecisionDrawer('return')));
    document.querySelectorAll('[data-review-approve]').forEach(btn => btn.addEventListener('click', () => {
      const issues = payrollReviewIssues(payrollRowsForDisplay()).issues;
      const critical = payrollReviewCounts(issues).Critical;
      if (critical) { showToast('Approval blocked', `${critical} critical review issue${critical === 1 ? '' : 's'} must be resolved first.`); return; }
      if (payrollRunStatus() !== 'Review') { showToast('Submit for review first', 'Final approval is available only while the payroll run is in Review.'); return; }
      openPayrollReviewDecisionDrawer('approve');
    }));

    document.querySelectorAll('[data-timesheet-tab]').forEach(btn => btn.addEventListener('click', () => {
      state.timesheetTab = btn.dataset.timesheetTab;
      state.timesheetPage = 1;
      state.timesheetSelected.clear();
      renderRoute();
    }));

    document.querySelectorAll('[data-timesheet-workspace]').forEach(btn => btn.addEventListener('click', () => {
      const workspace = btn.dataset.timesheetWorkspace;
      if (!['internal','rental'].includes(workspace) || workspace === state.timesheetWorkspace) return;
      if (state.timesheetWorkspace === 'internal') {
        state.internalTimesheetPeriod = state.period;
        localStorage.setItem('payroll-ui-internal-timesheet-period', state.internalTimesheetPeriod);
      } else {
        state.rentalTimesheetPeriod = state.period;
        localStorage.setItem('payroll-ui-rental-timesheet-period', state.rentalTimesheetPeriod);
      }
      state.timesheetWorkspace = workspace;
      localStorage.setItem('payroll-ui-timesheet-workspace', workspace);
      state.period = workspace === 'rental' ? state.rentalTimesheetPeriod : state.internalTimesheetPeriod;
      localStorage.setItem('payroll-ui-period', state.period);
      periodLabel.textContent = state.period;
      document.querySelectorAll('[data-period]').forEach(x => x.classList.toggle('is-selected', x.dataset.period === state.period));
      state.timesheetSelected.clear();
      state.rentalTimesheetPage = 1;
      state.rentalTimesheetSelected.clear();
      renderRoute();
      showToast(workspace === 'rental' ? 'Rental project timesheets' : 'Internal attendance', workspace === 'rental' ? `Project manpower workspace opened for ${state.period}.` : `Internal employee workspace opened for ${state.period}.`);
    }));

    document.querySelectorAll('[data-rental-timesheet-tab]').forEach(btn => btn.addEventListener('click', () => {
      state.rentalTimesheetTab = btn.dataset.rentalTimesheetTab;
      state.rentalTimesheetPage = 1;
      state.rentalTimesheetSelected.clear();
      renderRoute();
    }));
    document.querySelectorAll('[data-rental-timesheet-tab-jump]').forEach(btn => btn.addEventListener('click', () => {
      state.rentalTimesheetTab = btn.dataset.rentalTimesheetTabJump;
      renderRoute();
    }));

    const rentalTimesheetSearch = document.getElementById('rentalTimesheetSearch');
    bindPayrollSearch(rentalTimesheetSearch,value=>{state.rentalTimesheetSearch=value;},{beforeRender:()=>{state.rentalTimesheetPage=1;state.rentalTimesheetSelected.clear();}});
    const rentalTimesheetProjectFilter = document.getElementById('rentalTimesheetProjectFilter');
    if (rentalTimesheetProjectFilter) rentalTimesheetProjectFilter.addEventListener('change', () => {
      state.rentalTimesheetProject = rentalTimesheetProjectFilter.value;
      state.rentalTimesheetSupplier = 'All suppliers';
      state.rentalTimesheetPage = 1;
      state.rentalTimesheetSelected.clear();
      localStorage.setItem('payroll-ui-rental-timesheet-project', state.rentalTimesheetProject);
      state.rentalTimesheetLoaded?.delete(rentalTimesheetRecordKey());
      renderRoute();
    });
    const rentalTimesheetSupplierFilter = document.getElementById('rentalTimesheetSupplierFilter');
    if (rentalTimesheetSupplierFilter) rentalTimesheetSupplierFilter.addEventListener('change', () => {
      state.rentalTimesheetSupplier = rentalTimesheetSupplierFilter.value;
      state.rentalTimesheetPage = 1;
      state.rentalTimesheetSelected.clear();
      renderRoute();
    });
    document.querySelectorAll('[data-rental-timesheet-reset]').forEach(btn => btn.addEventListener('click', () => {
      state.rentalTimesheetSearch='';
      state.rentalTimesheetSupplier='All suppliers';
      state.rentalTimesheetPage=1;
      state.rentalTimesheetSelected.clear();
      renderRoute();
    }));

    document.querySelectorAll('[data-rental-ts-input]').forEach(input => {
      input.addEventListener('change', () => {
        if (rentalTimesheetStatus() !== 'Draft' || rentalProjectHasSettlementSnapshot(state.period,state.rentalTimesheetProject)) { showToast('Timesheet protected', rentalTimesheetStatus() !== 'Draft' ? 'Submitted, Approved and Locked rental attendance cannot be edited. Return it to Draft through the controlled workflow first.' : 'A calculated rental settlement already uses this project-period snapshot. Return the settlement for changes before editing hours.'); renderRoute(); return; }
        const normalized = normalizeRentalTimesheetValue(input.value);
        if (normalized == null) { showToast('Invalid timesheet value','Enter 0–24 hours or A, N, L or OFF.'); renderRoute(); return; }
        const workerId=input.dataset.rentalTsInput; const day=Number(input.dataset.day);
        input.disabled=true;
        saveRentalTimesheetEntries([{worker_id:workerId,work_date:rentalTimesheetDate(day),value:normalized}]).catch(error=>{ showToast('Timesheet update failed',error.message); loadRentalTimesheet(); });
      });
      input.addEventListener('keydown', event => {
        if (!['Enter','ArrowRight','ArrowLeft','ArrowDown','ArrowUp'].includes(event.key)) return;
        const workerId = input.dataset.rentalTsInput;
        const day = Number(input.dataset.day);
        const rows = rentalTimesheetPageData().rows;
        const rowIndex = rows.findIndex(worker => worker.id === workerId);
        let targetWorker = workerId, targetDay = day;
        if (event.key === 'Enter' || event.key === 'ArrowDown') targetWorker = rows[Math.min(rows.length - 1,rowIndex + 1)]?.id || workerId;
        else if (event.key === 'ArrowUp') targetWorker = rows[Math.max(0,rowIndex - 1)]?.id || workerId;
        else if (event.key === 'ArrowRight') targetDay = Math.min(periodInfo().days,day + 1);
        else if (event.key === 'ArrowLeft') targetDay = Math.max(1,day - 1);
        const selector = `[data-rental-ts-input="${CSS.escape(targetWorker)}"][data-day="${targetDay}"]`;
        const target = document.querySelector(selector);
        if (target && !target.disabled) { event.preventDefault(); target.focus(); target.select(); }
      });
    });

    document.querySelectorAll('[data-rental-ts-select]').forEach(input => input.addEventListener('change', () => {
      if (input.checked) state.rentalTimesheetSelected.add(input.dataset.rentalTsSelect);
      else state.rentalTimesheetSelected.delete(input.dataset.rentalTsSelect);
      renderRoute();
    }));
    document.querySelectorAll('[data-rental-ts-select-all]').forEach(input => input.addEventListener('change', () => {
      const visible = rentalTimesheetPageData().rows;
      if (input.checked) visible.forEach(worker => state.rentalTimesheetSelected.add(worker.id));
      else visible.forEach(worker => state.rentalTimesheetSelected.delete(worker.id));
      renderRoute();
    }));
    document.querySelectorAll('[data-rental-timesheet-page]').forEach(btn => btn.addEventListener('click', () => {
      const nextPage = Number(btn.dataset.rentalTimesheetPage);
      if (Number.isFinite(nextPage) && nextPage > 0) { state.rentalTimesheetPage = nextPage; state.rentalTimesheetSelected.clear(); renderRoute(); }
    }));
    const rentalTimesheetPageSize = document.getElementById('rentalTimesheetPageSize');
    if (rentalTimesheetPageSize) rentalTimesheetPageSize.addEventListener('change', () => {
      state.rentalTimesheetPageSize = Number(rentalTimesheetPageSize.value) || 50;
      state.rentalTimesheetPage = 1;
      localStorage.setItem('payroll-ui-rental-timesheet-page-size', String(state.rentalTimesheetPageSize));
      state.rentalTimesheetSelected.clear();
      renderRoute();
    });
    document.querySelectorAll('[data-rental-timesheet-clear-selection]').forEach(btn => btn.addEventListener('click', () => { state.rentalTimesheetSelected.clear(); renderRoute(); }));
    document.querySelectorAll('[data-rental-timesheet-export]').forEach(btn => btn.addEventListener('click', exportRentalTimesheetCsv));
    document.querySelectorAll('[data-rental-indeterminate="true"]').forEach(input => { input.indeterminate = true; });

    const rentalTimesheetBulkDay = document.getElementById('rentalTimesheetBulkDay');
    if (rentalTimesheetBulkDay) rentalTimesheetBulkDay.addEventListener('change', () => { state.rentalTimesheetBulkDay = Number(rentalTimesheetBulkDay.value) || 1; });
    document.querySelectorAll('[data-rental-ts-bulk]').forEach(btn => btn.addEventListener('click', () => {
      if (rentalTimesheetStatus() !== 'Draft' || rentalProjectHasSettlementSnapshot(state.period,state.rentalTimesheetProject)) { showToast('Timesheet protected', rentalTimesheetStatus() !== 'Draft' ? 'Only Draft rental timesheets can be edited.' : 'A calculated settlement protects this timesheet snapshot. Return the settlement for changes before bulk editing.'); return; }
      if (!state.rentalTimesheetSelected.size) return;
      ensureRentalTimesheet();
      const action = btn.dataset.rentalTsBulk;
      const day = Number(state.rentalTimesheetBulkDay) || 1;
      if (action === 'copy' && day <= 1) { showToast('No previous day','Choose day 2 or later before using Copy previous.'); return; }
      let updated = 0, skipped = 0;
      state.rentalTimesheetSelected.forEach(workerId => {
        const worker = state.rentalWorkers.find(item => item.id === workerId);
        if (!worker || !rentalAssignmentForDate(worker,state.rentalTimesheetProject,day,state.period)) { skipped += 1; return; }
        const record = state.rentalTimesheets[state.period][state.rentalTimesheetProject][workerId] || (state.rentalTimesheets[state.period][state.rentalTimesheetProject][workerId]={});
        if (action === 'copy') record[day] = record[day-1] ?? record[String(day-1)] ?? '';
        else if (action === 'clear') record[day] = '';
        else record[day] = action;
        updated += 1;
      });
      const entries=[];
      state.rentalTimesheetSelected.forEach(workerId=>{ const worker=state.rentalWorkers.find(item=>item.id===workerId); if(!worker||!rentalAssignmentForDate(worker,state.rentalTimesheetProject,day,state.period)) return; const record=state.rentalTimesheets[state.period][state.rentalTimesheetProject][workerId]||{}; entries.push({worker_id:workerId,work_date:rentalTimesheetDate(day),value:record[day]??''}); });
      if (entries.length) saveRentalTimesheetEntries(entries).then(()=>showToast('Project timesheet updated', `${entries.length} worker${entries.length===1?'':'s'} updated for day ${day}.`)).catch(error=>showToast('Bulk update failed',error.message));
    }));

    document.querySelectorAll('[data-rental-mobile-week]').forEach(btn => btn.addEventListener('click', () => {
      state.rentalTimesheetMobileWeek = Number(btn.dataset.rentalMobileWeek) || 1;
      renderRoute();
    }));

    document.querySelectorAll('[data-rental-ot-hours]').forEach(input => input.addEventListener('change', () => {
      if (rentalTimesheetStatus() !== 'Draft' || rentalProjectHasSettlementSnapshot(state.period,state.rentalTimesheetProject)) { showToast('OT protected', rentalTimesheetStatus() !== 'Draft' ? 'Only Draft rental timesheet overtime can be edited.' : 'A calculated settlement already uses these OT values. Return the settlement for changes before editing OT.'); renderRoute(); return; }
      const hours = Number(input.value || 0);
      if (!Number.isFinite(hours) || hours < 0 || hours > 500) { showToast('Invalid OT hours','Enter a non-negative overtime-hour value.'); renderRoute(); return; }
      const workerId=input.dataset.rentalOtHours; const key=rentalTimesheetRecordKey(); const current=state.rentalOvertime[key]?.[workerId]||{};
      appApi('/api/rental/timesheets/overtime/',{method:'PATCH',body:{project_id:state.rentalTimesheetProject,period:rentalTimesheetApiPeriod(),worker_id:workerId,hours,rate:current.rate||null}}).then(payload=>{applyRentalTimesheetPayload(payload);renderRoute();}).catch(error=>{showToast('OT update failed',error.message);loadRentalTimesheet();});
    }));
    document.querySelectorAll('[data-rental-ot-rate]').forEach(input => input.addEventListener('change', () => {
      if (rentalTimesheetStatus() !== 'Draft' || rentalProjectHasSettlementSnapshot(state.period,state.rentalTimesheetProject)) { showToast('OT protected', rentalTimesheetStatus() !== 'Draft' ? 'Only Draft rental timesheet overtime can be edited.' : 'A calculated settlement already uses these OT values. Return the settlement for changes before editing OT.'); renderRoute(); return; }
      const rate = Number(input.value || 0);
      if (!Number.isFinite(rate) || rate < 0 || rate > 10000) { showToast('Invalid OT rate','Enter a non-negative OT rate.'); renderRoute(); return; }
      const workerId=input.dataset.rentalOtRate; const key=rentalTimesheetRecordKey(); const current=state.rentalOvertime[key]?.[workerId]||{};
      appApi('/api/rental/timesheets/overtime/',{method:'PATCH',body:{project_id:state.rentalTimesheetProject,period:rentalTimesheetApiPeriod(),worker_id:workerId,hours:current.hours||0,rate}}).then(payload=>{applyRentalTimesheetPayload(payload);renderRoute();}).catch(error=>{showToast('OT update failed',error.message);loadRentalTimesheet();});
    }));

    document.querySelectorAll('[data-rental-timesheet-save]').forEach(btn => btn.addEventListener('click', () => {
      showToast('Rental timesheet saved', 'Changes are stored in the company database as you edit.');
    }));
    document.querySelectorAll('[data-rental-timesheet-workflow]').forEach(btn => btn.addEventListener('click', () => {
      const current = rentalTimesheetStatus();
      const action = rentalTimesheetNextAction(current);
      if (!action.next) return;
      const actionName=current==='Draft'?'submit':current==='Submitted'?'approve':current==='Approved'?'lock':null; if(!actionName)return;
      appApi('/api/rental/timesheets/workflow/',{method:'POST',body:{project_id:state.rentalTimesheetProject,period:rentalTimesheetApiPeriod(),action:actionName}}).then(payload=>{applyRentalTimesheetPayload(payload);if(actionName==='lock')state.rentalTimesheetSelected.clear();showToast('Rental timesheet updated',`Timesheet moved to ${payload.period.status}.`);renderRoute();}).catch(error=>showToast('Workflow update failed',error.message));
    }));
    document.querySelectorAll('[data-rental-timesheet-return]').forEach(btn => btn.addEventListener('click', () => {
      const reason=window.prompt('Reason for returning this timesheet to Draft:','')?.trim(); if(!reason)return;
      appApi('/api/rental/timesheets/workflow/',{method:'POST',body:{project_id:state.rentalTimesheetProject,period:rentalTimesheetApiPeriod(),action:'return',reason}}).then(payload=>{applyRentalTimesheetPayload(payload);showToast('Timesheet returned','The period is Draft again and the correction reason is audited.');renderRoute();}).catch(error=>showToast('Return failed',error.message));
    }));

    document.querySelectorAll('[data-rental-timesheet-import]').forEach(btn => btn.addEventListener('click', () => {
      showToast('Rental import / paste', 'The import mapping is ready for Worker ID/Name + day columns + OT. Rows will be matched to the worker master and effective project assignment before staging.');
    }));

    const timesheetSearch = document.getElementById('timesheetSearch');
    bindPayrollSearch(timesheetSearch,value=>{state.timesheetSearch=value;},{beforeRender:()=>{state.timesheetPage=1;}});
    const timesheetBranchFilter = document.getElementById('timesheetBranchFilter');
    if (timesheetBranchFilter) timesheetBranchFilter.addEventListener('change', () => { state.timesheetBranch = timesheetBranchFilter.value; state.timesheetPage = 1; state.timesheetSelected.clear(); renderRoute(); });
    const timesheetDepartmentFilter = document.getElementById('timesheetDepartmentFilter');
    if (timesheetDepartmentFilter) timesheetDepartmentFilter.addEventListener('change', () => { state.timesheetDepartment = timesheetDepartmentFilter.value; state.timesheetPage = 1; state.timesheetSelected.clear(); renderRoute(); });
    document.querySelectorAll('[data-timesheet-filter-reset]').forEach(btn => btn.addEventListener('click', () => { state.timesheetSearch = ''; state.timesheetBranch = 'All branches'; state.timesheetDepartment = 'All departments'; state.timesheetPage = 1; state.timesheetSelected.clear(); renderRoute(); }));

    document.querySelectorAll('[data-timesheet-page]').forEach(btn => btn.addEventListener('click', () => {
      const nextPage = Number(btn.dataset.timesheetPage);
      if (Number.isFinite(nextPage) && nextPage > 0) { state.timesheetPage = nextPage; renderRoute(); }
    }));
    const timesheetPageSize = document.getElementById('timesheetPageSize');
    if (timesheetPageSize) timesheetPageSize.addEventListener('change', () => {
      state.timesheetPageSize = Number(timesheetPageSize.value) || 50;
      state.timesheetPage = 1;
      localStorage.setItem('payroll-ui-internal-timesheet-page-size', String(state.timesheetPageSize));
      state.timesheetSelected.clear();
      renderRoute();
    });
    document.querySelectorAll('[data-timesheet-clear-selection]').forEach(btn => btn.addEventListener('click', () => { state.timesheetSelected.clear(); renderRoute(); }));
    document.querySelectorAll('[data-timesheet-export]').forEach(btn => btn.addEventListener('click', exportInternalAttendanceCsv));
    document.querySelectorAll('[data-indeterminate="true"]').forEach(input => { input.indeterminate = true; });

    document.querySelectorAll('[data-attendance-input]').forEach(input => input.addEventListener('change', async () => {
      if (!timesheetCanEdit()) { showToast('Attendance is read only', 'Only Draft attendance periods can be edited.'); renderRoute(); return; }
      const normalized = normalizeAttendanceValue(input.value);
      if (normalized == null) {
        showToast('Invalid attendance value', 'Enter 0–24 hours or one of A, L, S, H or OFF.');
        renderRoute();
        return;
      }
      input.disabled = true;
      try {
        await saveAttendanceApiEntries([{
          employee_id: input.dataset.attendanceInput,
          date: attendanceDateForDay(Number(input.dataset.day)),
          value: normalized
        }]);
      } catch (error) {
        showToast('Attendance not saved', error.message);
        await loadInternalAttendancePeriod(state.period, { force:true });
      }
      renderRoute();
    }));

    document.querySelectorAll('[data-timesheet-select]').forEach(input => input.addEventListener('change', () => {
      if (input.checked) state.timesheetSelected.add(input.dataset.timesheetSelect);
      else state.timesheetSelected.delete(input.dataset.timesheetSelect);
      renderRoute();
    }));
    document.querySelectorAll('[data-timesheet-select-all]').forEach(input => input.addEventListener('change', () => {
      const visible = internalTimesheetPageData().rows;
      if (input.checked) visible.forEach(employee => state.timesheetSelected.add(employee.id));
      else visible.forEach(employee => state.timesheetSelected.delete(employee.id));
      renderRoute();
    }));

    const timesheetBulkDay = document.getElementById('timesheetBulkDay');
    if (timesheetBulkDay) timesheetBulkDay.addEventListener('change', () => { state.timesheetBulkDay = Number(timesheetBulkDay.value) || 1; });
    document.querySelectorAll('[data-timesheet-bulk-action]').forEach(btn => btn.addEventListener('click', async () => {
      if (!timesheetCanEdit()) { showToast('Attendance is read only', 'Only Draft attendance periods can be bulk edited.'); return; }
      if (!state.timesheetSelected.size) { showToast('Select employees', 'Choose at least one employee before applying a bulk attendance action.'); return; }
      const action = btn.dataset.timesheetBulkAction;
      const day = Number(state.timesheetBulkDay) || 1;
      if (action === 'copy' && day <= 1) { showToast('No previous day', 'Choose day 2 or later before using Copy previous.'); return; }
      const info = periodInfo();
      const roster = attendanceRosterForPeriod();
      const entries = [];
      state.timesheetSelected.forEach(employeeId => {
        const employee = roster.find(item => item.id === employeeId);
        if (!employee) return;
        const record = state.timesheets[state.period]?.[employeeId] || {};
        if (action === 'workdays') {
          for (let d = 1; d <= info.days; d += 1) {
            if (!employeeEmployedOnDay(employee, d)) continue;
            entries.push({ employee_id:employeeId, date:attendanceDateForDay(d), value:isWeekendDay(d) ? 'OFF' : '8' });
          }
          return;
        }
        if (!employeeEmployedOnDay(employee, day)) return;
        let value = action;
        if (action === 'copy') value = record[day - 1] ?? record[String(day - 1)] ?? '';
        else if (action === 'clear') value = '';
        entries.push({ employee_id:employeeId, date:attendanceDateForDay(day), value });
      });
      if (!entries.length) { showToast('Nothing to update', 'No selected employee is employed on the chosen date.'); return; }
      btn.disabled = true;
      try {
        await saveAttendanceApiEntries(entries);
        showToast('Attendance updated', action === 'workdays' ? `Filled explicit workday/off-day values for ${state.timesheetSelected.size} selected employee${state.timesheetSelected.size === 1 ? '' : 's'}.` : `Updated day ${day} for the selected employees.`);
      } catch (error) {
        showToast('Bulk update failed', error.message);
      }
      renderRoute();
    }));

    document.querySelectorAll('[data-mobile-week]').forEach(btn => btn.addEventListener('click', () => {
      const week = Number(btn.dataset.mobileWeek);
      if (week > 0) { state.timesheetMobileWeek = week; renderRoute(); }
    }));

    document.querySelectorAll('[data-timesheet-import]').forEach(btn => btn.addEventListener('click', () => {
      if (!timesheetCanEdit()) { showToast('Attendance is read only', 'Imports are accepted only while the period is Draft.'); return; }
      openQuickDrawer('attendance-import', { period:state.period });
    }));
    document.querySelectorAll('[data-timesheet-save]').forEach(btn => btn.addEventListener('click', async () => {
      try {
        await loadInternalAttendancePeriod(state.period, { force:true });
        showToast('Draft synchronized', `${state.period} attendance and overtime match the saved company records.`);
      } catch (error) { showToast('Draft refresh failed', error.message); }
    }));
    document.querySelectorAll('[data-timesheet-workflow]').forEach(btn => btn.addEventListener('click', async () => {
      const action = timesheetNextAction();
      if (!action.action) return;
      btn.disabled = true;
      try {
        await runAttendanceWorkflow(action.action);
        if (action.action === 'lock') state.timesheetSelected.clear();
        showToast(`Timesheet ${action.next.toLowerCase()}`, action.action === 'submit' ? 'Attendance and overtime are frozen for reviewer approval.' : action.action === 'approve' ? 'The reviewed attendance snapshot is approved and ready to lock.' : 'The approved attendance period is locked against ordinary changes.');
      } catch (error) {
        showToast('Workflow action blocked', error.message);
      }
      renderRoute();
    }));
    document.querySelectorAll('[data-timesheet-return]').forEach(btn => btn.addEventListener('click', () => {
      if (!attendanceMeta().canApprove || !['Submitted','Approved'].includes(timesheetStatus())) return;
      openQuickDrawer('attendance-return', { period:state.period });
    }));

    document.querySelectorAll('[data-ot-hours]').forEach(input => input.addEventListener('change', async () => {
      if (!timesheetCanEdit()) { showToast('Overtime is read only', 'Only Draft attendance periods can be edited.'); renderRoute(); return; }
      const hours = Number(input.value || 0);
      if (!Number.isFinite(hours) || hours < 0 || hours > 744) { showToast('Invalid overtime hours', 'Enter overtime hours between 0 and 744.'); renderRoute(); return; }
      input.disabled = true;
      try {
        await saveAttendanceOvertimeApi(input.dataset.otHours, Math.round(hours * 100) / 100);
      } catch (error) {
        showToast('Overtime not saved', error.message);
        await loadInternalAttendancePeriod(state.period, { force:true });
      }
      renderRoute();
    }));

    document.querySelectorAll('[data-employee-status]').forEach(btn => btn.addEventListener('click', () => {
      state.employeeStatus = btn.dataset.employeeStatus;
      renderRoute();
    }));
    const employeeSearch = document.getElementById('employeeSearch');
    bindPayrollSearch(employeeSearch,value=>{state.employeeSearch=value;});
    const employeeStatusFilter = document.getElementById('employeeStatusFilter'); if(employeeStatusFilter) employeeStatusFilter.addEventListener('change',()=>{state.employeeStatus=employeeStatusFilter.value;renderRoute();});
    const employeeBranchFilter = document.getElementById('employeeBranchFilter');
    if (employeeBranchFilter) employeeBranchFilter.addEventListener('change', () => { state.employeeBranch = employeeBranchFilter.value; renderRoute(); });
    const employeeDepartmentFilter = document.getElementById('employeeDepartmentFilter');
    if (employeeDepartmentFilter) employeeDepartmentFilter.addEventListener('change', () => { state.employeeDepartment = employeeDepartmentFilter.value; renderRoute(); });
    const employeeWpsFilter = document.getElementById('employeeWpsFilter');
    if (employeeWpsFilter) employeeWpsFilter.addEventListener('change', () => { state.employeeWps = employeeWpsFilter.value; renderRoute(); });
    document.querySelectorAll('[data-employee-filter-reset]').forEach(btn => btn.addEventListener('click', () => { state.employeeSearch=''; state.employeeStatus='All'; state.employeeBranch='All branches'; state.employeeDepartment='All departments'; state.employeeWps='All'; renderRoute(); }));
    document.querySelectorAll('[data-employee-row-menu]').forEach(btn => btn.addEventListener('click', () => {
      const employee = state.employees.find(item => item.id === btn.dataset.employeeRowMenu);
      showToast('Employee actions', `${employee?.name || 'Employee'}: view, edit, salary structure, advance, attendance and payroll history actions are mapped.`);
    }));
    document.querySelectorAll('[data-employee-tab]').forEach(btn => btn.addEventListener('click', () => {
      state.employeeTab = btn.dataset.employeeTab;
      renderRoute();
    }));
    document.querySelectorAll('[data-employee-tab-jump]').forEach(btn => btn.addEventListener('click', () => {
      state.employeeTab = btn.dataset.employeeTabJump;
      renderRoute();
    }));
    document.querySelectorAll('[data-employee-lifecycle]').forEach(btn => btn.addEventListener('click', () => openEmployeeLifecycleDrawer(currentEmployeeId())));
    document.querySelectorAll('[data-employee-record-action]').forEach(btn => btn.addEventListener('click', () => openEmployeeRecordLifecycleDrawer(currentEmployeeId(), btn.dataset.employeeRecordAction)));
    document.querySelectorAll('[data-employee-profile-action]').forEach(btn => btn.addEventListener('click', () => {
      const action = btn.dataset.employeeProfileAction;
      const employeeId = currentEmployeeId();
      const employee = state.employees.find(item => item.id === employeeId);
      if (action === 'adjustment') { state.employeeTab = 'adjustments'; openQuickDrawer('advance',{ workforce:'Internal Employee', personId:employee?.id || '' }); }
      else if (action === 'adjustment-detail') { state.employeeTab = 'adjustments'; renderRoute(); }
      else if (action === 'create-salary' || action === 'edit-salary') openSalaryStructureDrawer(employee?.id);
      else if (action === 'edit-bank') { openEmployeePaymentProfileDrawer(employeeId); }
      else if (action === 'generate-slip') { openDocumentGenerateDrawer('Salary Slip',{ employeeId:currentEmployeeId(), period:state.period }); }
      else if (action === 'edit') openEmployeeEditDrawer(employee?.id);
      else showToast('Employee actions', 'Lifecycle, deactivate and audit actions will live here without deleting historical payroll records.');
    }));
    document.querySelectorAll('[data-employee-document]').forEach(btn => btn.addEventListener('click', () => {
      const employeeId=currentEmployeeId(); const employee=state.employees.find(item=>item.id===employeeId); const id=btn.dataset.employeeDocument; const target=documentAllRecords().find(doc=>doc.type==='salary_slip' && doc.entityReference===employee?.employeeId && (doc.number===id || doc.id===id)) || documentAllRecords().find(doc=>doc.type==='salary_slip' && doc.entityReference===employee?.employeeId); if(target){state.selectedDocumentId=target.id;navigate('documents');} else {showToast('No finalized salary slip','Finalize an eligible approved payroll line from the Documents workspace first.');}
    }));
    document.querySelectorAll('[data-employee-export]').forEach(btn => btn.addEventListener('click', () => showToast('Employee export ready', 'The current filtered employee register is ready for CSV/XLSX export wiring.')));
    document.querySelectorAll('[data-employee-more-filter]').forEach(btn => btn.addEventListener('click', () => showToast('Employee filters', 'Department, position, joining period, payment method and payroll-readiness filters are mapped for production data.')));

    document.querySelectorAll('[data-salary-tab]').forEach(btn => btn.addEventListener('click', () => {
      state.salarySetupTab = btn.dataset.salaryTab;
      renderRoute();
    }));
    document.querySelectorAll('[data-salary-component-type]').forEach(btn => btn.addEventListener('click', () => {
      state.salaryComponentType = btn.dataset.salaryComponentType;
      renderRoute();
    }));
    const salaryComponentSearch = document.getElementById('salaryComponentSearch');
    bindPayrollSearch(salaryComponentSearch,value=>{state.salaryComponentSearch=value;});
    const salaryComponentStatus = document.getElementById('salaryComponentStatus');
    if (salaryComponentStatus) salaryComponentStatus.addEventListener('change', () => {
      state.salaryComponentStatus = salaryComponentStatus.value;
      renderRoute();
    });
    document.querySelectorAll('[data-salary-component-add]').forEach(btn => btn.addEventListener('click', () => openSalaryComponentDrawer()));
    document.querySelectorAll('[data-salary-component-edit]').forEach(btn => btn.addEventListener('click', () => openSalaryComponentDrawer(btn.dataset.salaryComponentEdit)));
    document.querySelectorAll('[data-salary-structure-new]').forEach(btn => btn.addEventListener('click', () => openSalaryStructureDrawer()));
    document.querySelectorAll('[data-salary-structure-edit]').forEach(btn => btn.addEventListener('click', () => openSalaryStructureDrawer(btn.dataset.salaryStructureEdit)));
    const salaryStructureSearch = document.getElementById('salaryStructureSearch');
    bindPayrollSearch(salaryStructureSearch,value=>{state.salaryStructureSearch=value;});
    document.querySelectorAll('[data-overtime-policy-add]').forEach(btn => btn.addEventListener('click', () => openOvertimePolicyDrawer()));
    document.querySelectorAll('[data-overtime-policy-edit]').forEach(btn => btn.addEventListener('click', () => openOvertimePolicyDrawer(btn.dataset.overtimePolicyEdit)));
    const overtimePolicyStatus=document.getElementById('overtimePolicyStatus'); if(overtimePolicyStatus)overtimePolicyStatus.addEventListener('change',()=>{state.overtimePolicyStatus=overtimePolicyStatus.value;renderRoute();});
    const otBasic = document.getElementById('otPreviewBasic');
    const otHours = document.getElementById('otPreviewHours');
    const updateOtPreview = () => {
      const active = state.overtimePolicies.find(item => item.status === 'Active') || state.overtimePolicies[0];
      const result = document.getElementById('otPreviewResult');
      if (!result || !active) return;
      const basic = Number(otBasic?.value || 0);
      const hours = Number(otHours?.value || 0);
      result.textContent = formatCurrency(basic / Number(active.divisor || 1) * hours * Number(active.multiplier || 0));
    };
    otBasic?.addEventListener('input', updateOtPreview);
    otHours?.addEventListener('input', updateOtPreview);

    document.querySelectorAll('[data-supplier-status]').forEach(btn => btn.addEventListener('click', () => {
      state.supplierStatus = btn.dataset.supplierStatus;
      renderRoute();
    }));

    const supplierSearch = document.getElementById('supplierSearch');
    bindPayrollSearch(supplierSearch, value => { state.supplierSearch = value; });

    document.querySelectorAll('[data-supplier-tab]').forEach(btn => btn.addEventListener('click', () => {
      state.supplierTab = btn.dataset.supplierTab;
      renderRoute();
    }));
    document.querySelectorAll('[data-supplier-tab-jump]').forEach(btn => btn.addEventListener('click', () => {
      state.supplierTab = btn.dataset.supplierTabJump;
      renderRoute();
    }));

    const supplierWorkerSearch = document.getElementById('supplierWorkerSearch');
    bindPayrollSearch(supplierWorkerSearch, value => { state.supplierWorkerSearch = value; });
    document.querySelectorAll('[data-supplier-worker-status]').forEach(btn=>btn.addEventListener('click',()=>{state.supplierWorkerStatus=btn.dataset.supplierWorkerStatus;renderRoute();}));
    document.querySelectorAll('[data-supplier-worker-filter]').forEach(btn=>btn.addEventListener('click',()=>{state.supplierWorkerFiltersOpen=!state.supplierWorkerFiltersOpen;renderRoute();}));
    const supplierWorkerProjectFilter=document.getElementById('supplierWorkerProjectFilter'); if(supplierWorkerProjectFilter) supplierWorkerProjectFilter.addEventListener('change',()=>{state.supplierWorkerProject=supplierWorkerProjectFilter.value;renderRoute();});
    const supplierWorkerTradeFilter=document.getElementById('supplierWorkerTradeFilter'); if(supplierWorkerTradeFilter) supplierWorkerTradeFilter.addEventListener('change',()=>{state.supplierWorkerTrade=supplierWorkerTradeFilter.value;renderRoute();});
    document.querySelectorAll('[data-supplier-worker-advanced-reset]').forEach(btn=>btn.addEventListener('click',()=>{state.supplierWorkerProject='All projects';state.supplierWorkerTrade='All trades';renderRoute();}));
    document.querySelectorAll('[data-supplier-worker-reset]').forEach(btn=>btn.addEventListener('click',()=>{state.supplierWorkerSearch='';state.supplierWorkerStatus='All statuses';state.supplierWorkerProject='All projects';state.supplierWorkerTrade='All trades';renderRoute();}));

    document.querySelectorAll('[data-supplier-row-menu]').forEach(btn => btn.addEventListener('click', () => {
      const supplier = state.suppliers.find(item => item.id === btn.dataset.supplierRowMenu);
      if (supplier) { state.supplierTab='overview'; navigate(`suppliers/${supplier.id}`); }
    }));

    document.querySelectorAll('[data-supplier-action]').forEach(btn => btn.addEventListener('click', () => {
      const action = btn.dataset.supplierAction;
      if (action === 'edit') { const supplierId=String(currentRoute()).split('/')[1]; openSupplierEditDrawer(supplierId); }
      else if (action === 'new-settlement') showToast('New settlement', 'Open Supplier Settlements to calculate from a locked project timesheet.');
      else showToast('Supplier actions', 'Deactivate, statement and supplier lifecycle actions preserve worker and payment history.');
    }));
    document.querySelectorAll('[data-supplier-settlement]').forEach(btn => btn.addEventListener('click', () => showToast('Settlement detail', `${btn.dataset.supplierSettlement} settlement detail will be fully interactive with rental settlement processing.`)));
    document.querySelectorAll('[data-supplier-export]').forEach(btn => btn.addEventListener('click', () => { state.reportType='supplier-cost';state.reportPeriod=state.period;localStorage.setItem('payroll-ui-report-type',state.reportType);localStorage.setItem('payroll-ui-report-period',state.reportPeriod);navigate('reports'); }));
    document.querySelectorAll('[data-supplier-filter]').forEach(btn => btn.addEventListener('click', () => { state.supplierFiltersOpen = !state.supplierFiltersOpen; renderRoute(); }));
    const supplierProjectFilter=document.getElementById('supplierProjectFilter'); if(supplierProjectFilter) supplierProjectFilter.addEventListener('change',()=>{state.supplierProject=supplierProjectFilter.value;renderRoute();});
    const supplierPaymentTermFilter=document.getElementById('supplierPaymentTermFilter'); if(supplierPaymentTermFilter) supplierPaymentTermFilter.addEventListener('change',()=>{state.supplierPaymentTerm=supplierPaymentTermFilter.value;renderRoute();});
    const supplierWorkforceFilter=document.getElementById('supplierWorkforceFilter'); if(supplierWorkforceFilter) supplierWorkforceFilter.addEventListener('change',()=>{state.supplierWorkforce=supplierWorkforceFilter.value;renderRoute();});
    const supplierOutstandingFilter=document.getElementById('supplierOutstandingFilter'); if(supplierOutstandingFilter) supplierOutstandingFilter.addEventListener('change',()=>{state.supplierOutstanding=supplierOutstandingFilter.value;renderRoute();});
    document.querySelectorAll('[data-supplier-advanced-reset]').forEach(btn=>btn.addEventListener('click',()=>{state.supplierProject='All projects';state.supplierPaymentTerm='All payment terms';state.supplierWorkforce='Any workforce';state.supplierOutstanding='Any balance';renderRoute();}));
    document.querySelectorAll('[data-supplier-reset]').forEach(btn=>btn.addEventListener('click',()=>{state.supplierSearch='';state.supplierStatus='All';state.supplierProject='All projects';state.supplierPaymentTerm='All payment terms';state.supplierWorkforce='Any workforce';state.supplierOutstanding='Any balance';renderRoute();}));
    document.querySelectorAll('[data-project-status]').forEach(btn => btn.addEventListener('click', () => {
      state.projectStatus = btn.dataset.projectStatus;
      renderRoute();
    }));

    const projectSearch = document.getElementById('projectSearch');
    bindPayrollSearch(projectSearch, value => { state.projectSearch = value; });

    document.querySelectorAll('[data-project-tab]').forEach(btn => btn.addEventListener('click', () => {
      state.projectTab = btn.dataset.projectTab;
      renderRoute();
    }));
    document.querySelectorAll('[data-project-tab-jump]').forEach(btn => btn.addEventListener('click', () => {
      state.projectTab = btn.dataset.projectTabJump;
      renderRoute();
    }));

    const workerSearch = document.getElementById('projectWorkerSearch');
    bindPayrollSearch(workerSearch, value => { state.projectWorkerSearch = value; });
    const projectWorkerStatusFilter=document.getElementById('projectWorkerStatusFilter'); if(projectWorkerStatusFilter) projectWorkerStatusFilter.addEventListener('change',()=>{state.projectWorkerStatus=projectWorkerStatusFilter.value;renderRoute();});
    document.querySelectorAll('[data-project-workforce-filter]').forEach(btn=>btn.addEventListener('click',()=>{state.projectWorkerFiltersOpen=!state.projectWorkerFiltersOpen;renderRoute();}));
    const projectWorkerSupplierFilter=document.getElementById('projectWorkerSupplierFilter'); if(projectWorkerSupplierFilter) projectWorkerSupplierFilter.addEventListener('change',()=>{state.projectWorkerSupplier=projectWorkerSupplierFilter.value;renderRoute();});
    const projectWorkerTradeFilter=document.getElementById('projectWorkerTradeFilter'); if(projectWorkerTradeFilter) projectWorkerTradeFilter.addEventListener('change',()=>{state.projectWorkerTrade=projectWorkerTradeFilter.value;renderRoute();});
    document.querySelectorAll('[data-project-workforce-advanced-reset]').forEach(btn=>btn.addEventListener('click',()=>{state.projectWorkerSupplier='All suppliers';state.projectWorkerTrade='All trades';renderRoute();}));
    document.querySelectorAll('[data-project-workforce-reset]').forEach(btn=>btn.addEventListener('click',()=>{state.projectWorkerSearch='';state.projectWorkerStatus='All statuses';state.projectWorkerSupplier='All suppliers';state.projectWorkerTrade='All trades';renderRoute();}));

    document.querySelectorAll('[data-worker-profile]').forEach(btn => btn.addEventListener('click', () => {
      const worker = state.rentalWorkers.find(item => item.name === btn.dataset.workerProfile);
      if (worker) { state.rentalWorkerTab='overview'; navigate(`rental-workforce/${worker.id}`); }
      else showToast('Worker master not matched', `${btn.dataset.workerProfile} needs a rental-worker master link before opening a profile.`);
    }));

    document.querySelectorAll('[data-worker-menu]').forEach(btn => btn.addEventListener('click', () => {
      const worker = state.rentalWorkers.find(item => item.name === btn.dataset.workerMenu);
      showToast('Assignment actions', `${worker?.name || btn.dataset.workerMenu}: Transfer, change trade/rate, advance and release will use the effective-dated worker assignment lifecycle.`);
    }));

    document.querySelectorAll('[data-project-action]').forEach(btn => btn.addEventListener('click', () => {
      const action = btn.dataset.projectAction;
      if (action === 'edit') { const projectId=String(currentRoute()).split('/')[1]; openProjectEditDrawer(projectId); }
      else if (action === 'supplier-workers') { state.projectTab = 'workforce'; renderRoute(); }
      else showToast('Project actions', 'Project lifecycle actions are reserved without deleting payroll/workforce history.');
    }));
    document.querySelectorAll('[data-project-edit-id]').forEach(btn => btn.addEventListener('click', () => openProjectEditDrawer(btn.dataset.projectEditId)));
    document.querySelectorAll('[data-project-lifecycle]').forEach(btn => btn.addEventListener('click', () => {
      const projectId=btn.dataset.projectLifecycleId || String(currentPath()).split('/')[1];
      openProjectLifecycleDrawer(projectId, btn.dataset.projectLifecycle);
    }));

    document.querySelectorAll('[data-project-export]').forEach(btn => btn.addEventListener('click', () => { state.reportType='rental-project-cost';state.reportPeriod=state.period;localStorage.setItem('payroll-ui-report-type',state.reportType);localStorage.setItem('payroll-ui-report-period',state.reportPeriod);navigate('reports'); }));
    document.querySelectorAll('[data-project-filter]').forEach(btn => btn.addEventListener('click', () => { state.projectFiltersOpen = !state.projectFiltersOpen; renderRoute(); }));
    const projectClientFilter=document.getElementById('projectClientFilter'); if(projectClientFilter) projectClientFilter.addEventListener('change',()=>{state.projectClient=projectClientFilter.value;renderRoute();});
    const projectManagerFilter=document.getElementById('projectManagerFilter'); if(projectManagerFilter) projectManagerFilter.addEventListener('change',()=>{state.projectManager=projectManagerFilter.value;renderRoute();});
    const projectSupplierFilter=document.getElementById('projectSupplierFilter'); if(projectSupplierFilter) projectSupplierFilter.addEventListener('change',()=>{state.projectSupplier=projectSupplierFilter.value;renderRoute();});
    document.querySelectorAll('[data-project-advanced-reset]').forEach(btn=>btn.addEventListener('click',()=>{state.projectClient='All clients';state.projectManager='All managers';state.projectSupplier='All suppliers';renderRoute();}));
    document.querySelectorAll('[data-project-reset]').forEach(btn=>btn.addEventListener('click',()=>{state.projectSearch='';state.projectStatus='All';state.projectClient='All clients';state.projectManager='All managers';state.projectSupplier='All suppliers';renderRoute();}));

    document.querySelectorAll('[data-wps-tab]').forEach(btn => btn.addEventListener('click', () => { state.wpsTab = btn.dataset.wpsTab; renderRoute(); }));
    document.querySelectorAll('[data-wps-status]').forEach(btn => btn.addEventListener('click', () => { state.wpsStatusFilter = btn.dataset.wpsStatus; renderRoute(); }));
    const wpsSearch = document.getElementById('wpsSearch');
    bindPayrollSearch(wpsSearch,value=>{state.wpsSearch=value;});
    const wpsTemplateSelect=document.getElementById('wpsTemplateSelect');
    if(wpsTemplateSelect) wpsTemplateSelect.addEventListener('change',async()=>{state.wpsTemplateId=wpsTemplateSelect.value;localStorage.setItem('payroll-ui-wps-template-id',state.wpsTemplateId);await loadSalaryPayments(state.period,{force:true});renderRoute();});
    document.querySelectorAll('[data-wps-reset]').forEach(btn => btn.addEventListener('click', () => { state.wpsSearch=''; state.wpsStatusFilter='All'; renderRoute(); }));
    document.querySelectorAll('[data-wps-validate]').forEach(btn => btn.addEventListener('click', async () => { await loadSalaryPayments(state.period,{force:true}); const summary=wpsSummary(); showToast('WPS validation refreshed', `${summary.ready} ready · ${summary.blocked} blocked · ${formatCurrency(summary.readyAmount)} ready amount.`); }));
    document.querySelectorAll('[data-wps-prepare]').forEach(btn => btn.addEventListener('click', prepareWpsBatch));
    document.querySelectorAll('[data-wps-inspect]').forEach(btn => btn.addEventListener('click', () => openWpsRowDrawer(btn.dataset.wpsInspect)));
    document.querySelectorAll('[data-wps-batch-open]').forEach(btn => btn.addEventListener('click', () => openWpsBatchDrawer(btn.dataset.wpsBatchOpen)));

    document.querySelectorAll('[data-payment-tab]').forEach(btn => btn.addEventListener('click', () => { state.paymentTab = btn.dataset.paymentTab; state.paymentSearch=''; state.paymentStatusFilter='All'; renderRoute(); }));
    const paymentSearch = document.getElementById('paymentSearch');
    bindPayrollSearch(paymentSearch,value=>{state.paymentSearch=value;});
    const paymentStatusFilter=document.getElementById('paymentStatusFilter');
    if(paymentStatusFilter) paymentStatusFilter.addEventListener('change',()=>{state.paymentStatusFilter=paymentStatusFilter.value;renderRoute();});
    const internalPaymentBatchSelect=document.getElementById('internalPaymentBatchSelect');
    if(internalPaymentBatchSelect) internalPaymentBatchSelect.addEventListener('change',()=>{state.selectedInternalPaymentBatchId=internalPaymentBatchSelect.value;localStorage.setItem('payroll-ui-selected-internal-payment-batch',state.selectedInternalPaymentBatchId);state.paymentStatusFilter='All';state.paymentSearch='';renderRoute();});
    const paymentSupplierFilter=document.getElementById('paymentSupplierFilter');
    if(paymentSupplierFilter) paymentSupplierFilter.addEventListener('change',()=>{state.paymentSupplierFilter=paymentSupplierFilter.value;renderRoute();});
    const paymentMethodFilter=document.getElementById('paymentMethodFilter');
    if(paymentMethodFilter) paymentMethodFilter.addEventListener('change',()=>{state.paymentMethodFilter=paymentMethodFilter.value;renderRoute();});
    document.querySelectorAll('[data-payment-payable]').forEach(btn=>btn.addEventListener('click',()=>{state.paymentPayableFilter=btn.dataset.paymentPayable;renderRoute();}));
    document.querySelectorAll('[data-payment-reset]').forEach(btn=>btn.addEventListener('click',()=>{state.paymentSearch='';state.paymentStatusFilter='All';state.paymentMethodFilter='All methods';renderRoute();}));
    document.querySelectorAll('[data-payment-start]').forEach(btn=>btn.addEventListener('click',()=>runPaymentBatchWorkflow(btn.dataset.paymentBatch||latestPaymentBatch()?.id,'start')));
    document.querySelectorAll('[data-payment-row]').forEach(btn=>btn.addEventListener('click',()=>openPaymentRowDrawer(btn.dataset.paymentRow, btn.dataset.paymentBatch || null)));
    document.querySelectorAll('[data-payment-profile-edit]').forEach(btn=>btn.addEventListener('click',()=>openEmployeePaymentProfileDrawer(btn.dataset.paymentProfileEdit)));
    document.querySelectorAll('[data-payment-settings]').forEach(btn=>btn.addEventListener('click',openCompanyPaymentSettingsDrawer));
    document.querySelectorAll('[data-payment-export]').forEach(btn=>btn.addEventListener('click',()=>exportPaymentBatch(btn.dataset.paymentExport)));
    document.querySelectorAll('[data-payment-start-batch]').forEach(btn=>btn.addEventListener('click',()=>runPaymentBatchWorkflow(btn.dataset.paymentStartBatch,'start')));
    document.querySelectorAll('[data-payment-close-batch]').forEach(btn=>btn.addEventListener('click',()=>runPaymentBatchWorkflow(btn.dataset.paymentCloseBatch,'close')));
    document.querySelectorAll('.payment-result-file').forEach(input=>input.addEventListener('change',async()=>{const file=input.files?.[0];if(file)await importPaymentResults(input.dataset.resultBatch,file);}));
    document.querySelectorAll('[data-payment-retry]').forEach(btn=>btn.addEventListener('click',async()=>{try{const payload=await appApi(`/api/internal/salary-payments/rows/${encodeURIComponent(btn.dataset.paymentRetry)}/retry/`,{method:'POST',body:{}});applyPaymentPayload(payload);renderRoute();showToast('Payment retry started','A new controlled payment attempt is now Processing.');}catch(error){showToast('Retry blocked',error.message);}}));
    document.querySelectorAll('[data-payment-close-payroll]').forEach(btn=>btn.addEventListener('click',()=>runPaymentBatchWorkflow(btn.dataset.paymentBatch||latestPaymentBatch()?.id,'close')));
    document.querySelectorAll('[data-supplier-payment-new]').forEach(btn=>btn.addEventListener('click',()=>openSupplierPaymentDrawer()));
    document.querySelectorAll('[data-pay-supplier-settlement]').forEach(btn=>btn.addEventListener('click',()=>openSupplierPaymentDrawer(btn.dataset.paySupplierSettlement)));
    document.querySelectorAll('[data-supplier-payment-open]').forEach(btn=>btn.addEventListener('click',()=>openSupplierPaymentDetailDrawer(btn.dataset.supplierPaymentOpen)));
    document.querySelectorAll('[data-supplier-payment-retry]').forEach(btn=>btn.addEventListener('click',async()=>{
      btn.disabled=true;
      try {
        const payload=await appApi(`/api/rental/supplier-payments/${encodeURIComponent(btn.dataset.supplierPaymentRetry)}/retry/`,{method:'POST',body:{payment_date:rentalTodayIso()}});
        applyRentalSettlementPayload(payload);
        closeDrawer();state.paymentTab='supplier';renderRoute();
        showToast('Supplier payment retry created','A new Processing payment record was created; the failed/reversed payment remains immutable history.');
      } catch(error){btn.disabled=false;showToast('Supplier payment retry blocked',error.message);}
    }));
    document.querySelectorAll('[data-receipt-select]').forEach(btn=>btn.addEventListener('click',()=>{state.selectedReceiptId=btn.dataset.receiptSelect;renderRoute();}));
    document.querySelectorAll('[data-receipt-print]').forEach(btn=>btn.addEventListener('click',()=>{const receipt=paymentReceiptsForPeriod().find(item=>item.id===state.selectedReceiptId);if(receipt)printPaymentReceipt(receipt);}));
  }


  function openPayrollPolicyDrawer() {
    const policy = payrollContextForPeriod().policy || {};
    state.drawerType = 'payroll-policy';
    state.drawerContext = null;
    drawerTitle.textContent = 'Payroll proration policy';
    drawerSave.hidden = false;
    drawerSave.disabled = false;
    drawerSave.textContent = 'Save Policy';
    drawerBody.innerHTML = `<section class="form-section"><div class="form-section__head"><strong>Monthly salary proration</strong><span>This company-level rule is used only when employment or salary structure changes make a month partial.</span></div><label class="form-field form-field--full"><span>Proration method</span><select class="select" name="payroll-proration-method"><option value="calendar_days" ${policy.prorationMethod==='calendar_days'?'selected':''}>Calendar-day proration</option><option value="no_proration" ${policy.prorationMethod==='no_proration'?'selected':''}>No proration — use full monthly salary</option></select><span class="field-hint">Full-month employees with one salary structure calculate normally even before a proration policy is needed. Partial months are blocked until this rule is explicitly configured.</span></label></section><section class="source-note">${icon('info')}<span><strong>Company policy is retained.</strong> This is singleton company configuration, not a deletable master record. Changing it affects future calculations only; existing calculated/reviewed payroll snapshots are not rewritten.</span></section>`;
    drawer.classList.add('is-open');
    drawerScrim.classList.add('is-open');
    drawer.setAttribute('aria-hidden','false');
  }

  function openPayrollReviewDecisionDrawer(decision) {
    const run = payrollRunRecord();
    state.drawerType = 'payroll-review-decision';
    state.drawerContext = decision;
    drawerTitle.textContent = decision === 'approve' ? `Approve ${state.period} payroll` : `Return ${state.period} for changes`;
    drawerSave.hidden = false;
    drawerSave.textContent = decision === 'approve' ? 'Approve Payroll' : 'Return for Changes';
    const review = payrollReviewIssues(payrollRowsForDisplay());
    const counts = payrollReviewCounts(review.issues);
    drawerBody.innerHTML = decision === 'approve' ? `
      <section class="form-section"><div class="form-section__head"><strong>Final reviewer confirmation</strong><span>This decision changes the run from Review to Approved and writes an audit-trail event. Payment/WPS remains a later lifecycle step.</span></div><div class="review-decision-summary"><div><span>Period</span><strong>${escapeHtml(state.period)}</strong></div><div><span>Net payable</span><strong>${formatCurrency(payrollTotals(payrollRowsForDisplay()).net)}</strong></div><div><span>Critical exceptions</span><strong>${counts.Critical}</strong></div><div><span>Warnings</span><strong>${counts.Warning}</strong></div></div></section>
      <section class="form-section"><div class="form-section__head"><strong>Reviewer note</strong><span>Optional note is retained with the approval record.</span></div><div class="form-grid"><div class="form-field form-field--full"><label>Approval note</label><textarea class="textarea" name="payroll-review-note" placeholder="Reviewed payroll calculation, attendance snapshot and exceptions…"></textarea></div><label class="review-confirm"><input type="checkbox" name="payroll-review-confirm"><span><strong>I reviewed the payroll exceptions and calculation snapshot.</strong><small>This confirmation is required before the server accepts final approval.</small></span></label></div></section>` : `
      <section class="form-section"><div class="form-section__head"><strong>Return to Payroll</strong><span>The run returns to Calculated so Payroll can correct salary setup, attendance, overtime or adjustments and recalculate before resubmitting.</span></div><div class="form-grid">${namedSelectField('Reason category', 'payroll-return-category', ['Payroll setup','Attendance / overtime','Adjustment / deduction','Bank / WPS data','Other'])}<div class="form-field form-field--full"><label>Reviewer note</label><textarea class="textarea" name="payroll-review-note" placeholder="Describe what needs to be corrected…"></textarea></div></div></section>
      <section class="source-note">${icon('info')}<span><strong>History is preserved</strong>Returning a run does not delete its prior calculation or submission events from the audit trail.</span></section>`;
    drawer.classList.add('is-open');
    drawerScrim.classList.add('is-open');
    drawer.setAttribute('aria-hidden','false');
  }

  function initDropdowns() {
    if (document.documentElement.dataset.payrollDropdownDelegation === 'ready') return;
    document.documentElement.dataset.payrollDropdownDelegation = 'ready';
    document.addEventListener('click', (event) => {
      const trigger = event.target.closest('[data-dropdown-trigger]');
      if (trigger) {
        const dropdown = trigger.closest('[data-dropdown]');
        if (!dropdown) return;
        event.preventDefault();
        event.stopPropagation();
        document.querySelectorAll('[data-dropdown].is-open').forEach(other => {
          if (other !== dropdown) {
            other.classList.remove('is-open');
            other.querySelector('[data-dropdown-trigger]')?.setAttribute('aria-expanded','false');
          }
        });
        const open = dropdown.classList.toggle('is-open');
        trigger.setAttribute('aria-expanded', String(open));
        return;
      }
      const menuAction = event.target.closest('[data-lifecycle-menu-action]');
      if (menuAction) {
        const host = menuAction.closest('[data-dropdown]');
        host?.classList.remove('is-open');
        host?.querySelector('[data-dropdown-trigger]')?.setAttribute('aria-expanded','false');
        return;
      }
      if (!event.target.closest('[data-dropdown]')) {
        document.querySelectorAll('[data-dropdown].is-open').forEach(dropdown => {
          dropdown.classList.remove('is-open');
          dropdown.querySelector('[data-dropdown-trigger]')?.setAttribute('aria-expanded','false');
        });
      }
    });
  }

  function initWorkspaceSwitcher() {
    document.querySelectorAll('[data-workspace-switch]').forEach(control => {
      control.addEventListener('click', event => {
        const target = control.dataset.workspaceSwitch;
        if (!roleCanWorkspace(target)) {
          event.preventDefault();
          showToast('Workspace access restricted', `${roleDefinition().label} cannot open this workspace.`);
          return;
        }
        // Keep the anchor as a real fallback if JavaScript never initializes, but once
        // initialized switch in-place and make the resulting URL reload/copy safe.
        event.preventDefault();
        const dropdown = control.closest('[data-dropdown]');
        switchWorkspace(target);
        dropdown?.classList.remove('is-open');
        dropdown?.querySelector('[data-dropdown-trigger]')?.setAttribute('aria-expanded','false');
        closeMobileNav();
      });
    });
  }

  function initPeriod() {
    periodLabel.textContent = state.period;
    document.querySelectorAll('[data-period]').forEach(btn => {
      btn.classList.toggle('is-selected', btn.dataset.period === state.period);
      btn.addEventListener('click', () => {
        state.period = btn.dataset.period;
        state.payrollView = 'register';
        state.payrollReviewSeverity = 'All';
        localStorage.setItem('payroll-ui-period', state.period);
        localStorage.setItem(state.workspace === 'rental' ? 'payroll-ui-rental-period' : state.workspace === 'management' ? 'payroll-ui-management-period' : 'payroll-ui-internal-period', state.period);
        if (currentRoute() === 'timesheets') {
          state.timesheetPage = 1;
          state.timesheetSelected.clear();
          if (state.timesheetWorkspace === 'rental') {
            state.rentalTimesheetPage = 1;
            state.rentalTimesheetSelected.clear();
            state.rentalTimesheetPeriod = state.period;
            state.rentalTimesheetBulkDay = defaultTimesheetDay(state.period);
            localStorage.setItem('payroll-ui-rental-timesheet-period', state.period);
          } else {
            state.internalTimesheetPeriod = state.period;
            state.timesheetBulkDay = defaultTimesheetDay(state.period);
            localStorage.setItem('payroll-ui-internal-timesheet-period', state.period);
          }
        }
        periodLabel.textContent = state.period;
        document.querySelectorAll('[data-period]').forEach(x => x.classList.toggle('is-selected', x.dataset.period === state.period));
        btn.closest('[data-dropdown]')?.classList.remove('is-open');
        renderRoute();
        showToast(state.workspace==='management'?'Management period changed':'Payroll period changed', `${workspaceLabel()} switched to ${state.period}.`);
      });
    });
  }

  function initSidebar() {
    const DEFAULT_WIDTH = 236;
    const MIN_WIDTH = 210;
    const MAX_WIDTH = 360;
    const resizeHandle = document.getElementById('sidebarResizeHandle');
    const railToggle = document.getElementById('sidebarRailToggle');
    const mobileClose = document.getElementById('sidebarMobileClose');
    const savedWidth = Number(localStorage.getItem('payroll-ui-sidebar-width'));
    let sidebarWidth = Number.isFinite(savedWidth) && savedWidth >= MIN_WIDTH && savedWidth <= MAX_WIDTH ? savedWidth : DEFAULT_WIDTH;

    const applySidebarWidth = (value, persist = true) => {
      sidebarWidth = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, Number(value) || DEFAULT_WIDTH));
      appShell?.style.setProperty('--ui-v2-sidebar-runtime', `${sidebarWidth}px`);
      resizeHandle?.setAttribute('aria-valuenow', String(Math.round(sidebarWidth)));
      if (persist) localStorage.setItem('payroll-ui-sidebar-width', String(Math.round(sidebarWidth)));
    };
    const setCollapsed = (collapsed, persist = true) => {
      state.sidebarCollapsed = Boolean(collapsed);
      appShell?.setAttribute('data-collapsed', collapsed ? 'true' : 'false');
      sidebar.classList.toggle('is-collapsed', collapsed);
      shell?.classList.toggle('is-expanded', collapsed);
      if (persist) localStorage.setItem('payroll-ui-sidebar', collapsed ? 'collapsed' : 'expanded');
      const label = collapsed ? 'Expand navigation' : 'Collapse navigation';
      document.getElementById('sidebarCollapse')?.setAttribute('aria-label', label);
      railToggle?.setAttribute('aria-label', label);
      const railPath = railToggle?.querySelector('path');
      if (railPath) railPath.setAttribute('d', collapsed ? 'M9 18l6-6-6-6' : 'M15 18l-6-6 6-6');
    };

    applySidebarWidth(sidebarWidth, false);
    setCollapsed(state.sidebarCollapsed && innerWidth > 920, false);

    const toggleCollapsed = () => setCollapsed(appShell?.dataset.collapsed !== 'true');
    document.getElementById('sidebarCollapse')?.addEventListener('click', toggleCollapsed);
    railToggle?.addEventListener('click', toggleCollapsed);

    document.getElementById('mobileNavToggle')?.addEventListener('click', () => {
      sidebar.classList.add('is-mobile-open');
      appShell?.setAttribute('data-mobile-open', 'true');
      mobileScrim.hidden = false;
    });
    mobileClose?.addEventListener('click', closeMobileNav);
    mobileScrim.addEventListener('click', closeMobileNav);

    if (resizeHandle) {
      const startResize = (event) => {
        if (innerWidth <= 1120 || appShell?.dataset.collapsed === 'true') return;
        event.preventDefault();
        const startX = event.clientX;
        const startWidth = sidebarWidth;
        document.body.classList.add('ui-v2-sidebar-resizing');
        const move = (moveEvent) => applySidebarWidth(startWidth + moveEvent.clientX - startX);
        const stop = () => {
          window.removeEventListener('pointermove', move);
          window.removeEventListener('pointerup', stop);
          document.body.classList.remove('ui-v2-sidebar-resizing');
        };
        window.addEventListener('pointermove', move);
        window.addEventListener('pointerup', stop, { once:true });
      };
      resizeHandle.addEventListener('pointerdown', startResize);
      resizeHandle.addEventListener('dblclick', () => applySidebarWidth(DEFAULT_WIDTH));
      resizeHandle.addEventListener('keydown', event => {
        if (!['ArrowLeft','ArrowRight','Home'].includes(event.key) || appShell?.dataset.collapsed === 'true') return;
        event.preventDefault();
        if (event.key === 'Home') applySidebarWidth(DEFAULT_WIDTH);
        else applySidebarWidth(sidebarWidth + (event.key === 'ArrowRight' ? 10 : -10));
      });
    }

    document.querySelectorAll('[data-account-settings]').forEach(link => link.addEventListener('click', () => {
      const dropdown = link.closest('[data-dropdown]');
      dropdown?.classList.remove('is-open');
      dropdown?.querySelector('[data-dropdown-trigger]')?.setAttribute('aria-expanded','false');
      closeMobileNav();
    }));
  }

  function closeMobileNav() {
    sidebar.classList.remove('is-mobile-open');
    appShell?.setAttribute('data-mobile-open', 'false');
    mobileScrim.hidden = true;
  }

  function openSearch() {
    searchDialog.hidden = false;
    searchDialog.classList.add('is-open');
    searchDialog.setAttribute('aria-hidden', 'false');
    searchInput.value = '';
    renderSearch('');
    setTimeout(() => searchInput.focus(), 20);
  }

  function closeSearch() {
    searchDialog.classList.remove('is-open');
    searchDialog.setAttribute('aria-hidden', 'true');
    searchDialog.hidden = true;
  }

  function renderSearch(query) {
    const q = query.trim().toLowerCase();
    let pageResults = PAGE_SEARCH_ITEMS.filter(item => workspaceAllowsRoute(String(item.route || '').split('/')[0])).map(item => ({...item, workspace:state.workspace}));
    let all = [];
    if (state.workspace === 'management') {
      pageResults = [
        {type:'Page',code:'MG',name:'Company Overview',meta:'Cross-workspace company control',route:'overview',workspace:'management'},
        {type:'Page',code:'WC',name:'Workforce Cost',meta:'Internal vs rental controlled cost',route:'management-cost',workspace:'management'},
        {type:'Page',code:'AP',name:'Approval Center',meta:'Payroll · settlement · payment exceptions',route:'management-approvals',workspace:'management'},
        {type:'Page',code:'AU',name:'Audit Trail',meta:'Cross-workspace lifecycle events',route:'management-audit',workspace:'management'},
        {type:'Page',code:'RP',name:'Management Reports',meta:'Controlled workforce cost reporting',route:'reports',workspace:'management'}
      ];
      if (['owner','finance'].includes(state.accessRole)) pageResults.push({type:'Page',code:'AC',name:'Access & Roles',meta:'Workspace permission matrix',route:'access-roles',workspace:'management'});
      const employeeResults = state.employees.map(employee => ({ type:'Internal Employee', code:'IE', name:employee.name, meta:`EMP ${employee.employeeId} · ${employee.branch || 'Branch not set'} · ${employee.department}`, route:`internal-employees/${employee.id}`, workspace:'internal' }));
      const branchResults = state.branches.map(branch => ({ type:'Branch', code:'BR', name:branch.name, meta:`${branch.code} · ${branch.location}`, route:`branches/${branch.id}`, workspace:'internal' }));
      const rentalResults = state.rentalWorkers.map(worker => ({ type:'Rental Worker', code:'RW', name:worker.name, meta:`${rentalWorkerCode(worker)} · ${worker.trade || 'Rental worker'} · ${rentalWorkerSupplier(worker)?.name || 'Supplier not linked'}`, route:`rental-workforce/${worker.id}`, workspace:'rental' }));
      const projectResults = state.projects.filter(project=>!project.legacyInternal).map(project => ({ type:'Project', code:'PR', name:project.name, meta:`${project.code} · ${project.location}`, route:`projects/${project.id}`, workspace:'rental' }));
      const supplierResults = state.suppliers.map(supplier => ({ type:'Supplier', code:'SP', name:supplier.name, meta:`${supplier.code} · ${supplier.activeWorkers || 0} assigned · ${supplier.activeProjects || 0} projects`, route:`suppliers/${supplier.id}`, workspace:'rental' }));
      all = [...pageResults, ...employeeResults, ...branchResults, ...rentalResults, ...projectResults, ...supplierResults];
    } else if (state.workspace === 'internal') {
      const employeeResults = state.employees.map(employee => ({ type:'Employee', code:'IE', name:employee.name, meta:`EMP ${employee.employeeId} · ${employee.branch || 'Branch not set'} · ${employee.department}`, route:`internal-employees/${employee.id}`, workspace:'internal' }));
      const branchResults = state.branches.map(branch => ({ type:'Branch', code:'BR', name:branch.name, meta:`${branch.code} · ${branch.location}`, route:`branches/${branch.id}`, workspace:'internal' }));
      const departmentResults = state.departments.map(dept => ({ type:'Department', code:'DP', name:dept.name, meta:`${dept.code} · ${branchEmployeesByDepartment(dept.name).length} employees`, route:`departments/${dept.id}`, workspace:'internal' }));
      all = [...pageResults.filter(x=>!['Employee','Branch','Department'].includes(x.type)), ...employeeResults, ...branchResults, ...departmentResults];
    } else {
      const projectResults = state.projects.filter(project=>!project.legacyInternal).map(project => ({ type:'Project', code:'PR', name:project.name, meta:`${project.code} · ${project.location}`, route:`projects/${project.id}`, workspace:'rental' }));
      const supplierResults = state.suppliers.map(supplier => ({ type:'Supplier', code:'SP', name:supplier.name, meta:`${supplier.code} · ${supplier.activeWorkers || 0} assigned · ${supplier.activeProjects || 0} projects`, route:`suppliers/${supplier.id}`, workspace:'rental' }));
      const rentalResults = state.rentalWorkers.map(worker => ({ type:'Worker', code:'RW', name:worker.name, meta:`${rentalWorkerCode(worker)} · ${worker.trade || 'Rental worker'} · ${rentalWorkerSupplier(worker)?.name || 'Supplier not linked'}`, route:`rental-workforce/${worker.id}`, workspace:'rental' }));
      all = [...pageResults.filter(x=>!['Project','Supplier','Worker'].includes(x.type)), ...rentalResults, ...projectResults, ...supplierResults];
    }
    const rows = all.filter(item => !q || `${item.type} ${item.name} ${item.meta}`.toLowerCase().includes(q));
    if (!rows.length) { commandResults.innerHTML = `<div class="ui-v2-command__empty">${icon('search')}<strong>No matching destination</strong><span>No matching records in ${escapeHtml(workspaceLabel())}.</span></div>`; return; }
    const groups = rows.reduce((acc,item)=>{(acc[item.type] ||= []).push(item);return acc;},{});
    commandResults.innerHTML = Object.entries(groups).map(([type,items]) => `<div class="ui-v2-prs-command-group">${type}${items.length>1?'s':''}</div>${items.map(item=>`<button data-search-route="${item.route}" data-search-workspace="${escapeHtml(item.workspace||state.workspace)}"><span class="ui-v2-command__icon">${item.code}</span><span class="ui-v2-command__copy"><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml(item.meta)}</small></span>${icon('arrow')}</button>`).join('')}`).join('');
    commandResults.querySelectorAll('[data-search-route]').forEach(btn=>btn.addEventListener('click',()=>{closeSearch(); const targetWorkspace=btn.dataset.searchWorkspace||state.workspace; if(targetWorkspace!==state.workspace){ if(!roleCanWorkspace(targetWorkspace)){showToast('Access restricted',`${roleDefinition().label} cannot open this result.`);return;} state.workspace=targetWorkspace; localStorage.setItem('payroll-ui-workspace',targetWorkspace); syncWorkspaceUrl(targetWorkspace); state.period=targetWorkspace==='rental'?(localStorage.getItem('payroll-ui-rental-period')||defaultInternalPeriod):targetWorkspace==='management'?(localStorage.getItem('payroll-ui-management-period')||defaultInternalPeriod):(localStorage.getItem('payroll-ui-internal-period')||defaultInternalPeriod); localStorage.setItem('payroll-ui-period',state.period); periodLabel.textContent=state.period; renderWorkspaceShell(); } navigate(btn.dataset.searchRoute);}));
  }

  function initSearch() {
    document.getElementById('globalSearchButton').addEventListener('click', openSearch);
    searchInput.addEventListener('input', () => renderSearch(searchInput.value));
    searchDialog.addEventListener('click', e => { if (e.target === searchDialog) closeSearch(); });
    document.addEventListener('keydown', e => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); openSearch(); }
      if (e.key === 'Escape') { closeSearch(); closeDrawer(); closeMobileNav(); }
    });
  }

  const drawerTemplates = {
    'internal-employee': {
      title: 'Add internal employee',
      saveLabel: 'Create employee',
      html: () => {
        const draft = state.inlineInternalDraft || {};
        const contextDepartment = state.departments.find(item=>item.id===state.drawerContext?.departmentId);
        const branchOptions = state.branches.filter(item=>item.status==='Active').map(item=>({value:item.id,label:`${item.name} · ${item.code}`}));
        const departmentOptions = state.departments.filter(item=>item.status==='Active').map(item=>({value:item.id,label:`${item.name} · ${item.code}`}));
        return formSections([
          ['Employee identity', 'Create one permanent company-employee record. Payroll history will reference this master instead of duplicating the person each month.', [
            namedField('Employee ID (auto if blank)', 'employee-id', draft['employee-id'] || ''), namedField('Full name', 'employee-name', draft['employee-name'] || ''), namedField('Position', 'employee-position', draft['employee-position'] || ''), namedSelectOptions('Department', 'employee-department', departmentOptions, draft['employee-department'] || contextDepartment?.id || departmentOptions[0]?.value || ''), `<div class="form-field"><label>&nbsp;</label><button class="btn btn--secondary btn--form" type="button" data-inline-internal-create="department">+ New department</button><span class="field-hint">Create a reusable department master without leaving employee onboarding.</span></div>`
          ]],
          ['Employment & organization', 'Internal employees belong to a company branch/office and department. Construction projects are not used as the employee master location.', [
            namedField('Joining date', 'employee-joining', draft['employee-joining'] || '', 'date'), namedSelectOptions('Branch / Office', 'employee-branch', branchOptions, draft['employee-branch'] || state.drawerContext?.branchId || branchOptions[0]?.value || ''), `<div class="form-field"><label>&nbsp;</label><button class="btn btn--secondary btn--form" type="button" data-inline-internal-create="branch">+ New branch / office</button><span class="field-hint">Newly created office returns selected in this employee form.</span></div>`, namedSelectFieldValue('Status', 'employee-status', ['Active','On Leave','Inactive'], draft['employee-status'] || 'Active'), namedField('National ID / Iqama', 'employee-national-id', draft['employee-national-id'] || ''), namedField('Phone', 'employee-phone', draft['employee-phone'] || ''), namedField('Address', 'employee-address', draft['employee-address'] || '')
          ]]
        ]);
      }
    },
    'branch': {
      title: 'Add branch / office',
      saveLabel: 'Create branch',
      html: () => formSections([
        ['Branch / office master', 'Internal employees are organized by company office or branch. This is separate from construction projects used by rental manpower.', [
          namedField('Branch / office name', 'branch-name', ''), namedField('Branch code (auto if blank)', 'branch-code', ''), namedSelectFieldValue('Type', 'branch-kind', ['Branch','Office'], 'Branch'), namedField('Location / city', 'branch-location', ''), namedField('Address', 'branch-address', ''), namedField('Branch manager', 'branch-manager', ''), namedSelectField('Status', 'branch-status', ['Active','Inactive'])
        ]]
      ])
    },
    'department': {
      title: 'Add department',
      saveLabel: 'Create department',
      html: () => formSections([
        ['Department master', 'Departments are reusable organization records across internal company branches.', [
          namedField('Department name', 'department-name', ''), namedField('Department code (auto if blank)', 'department-code', ''), namedSelectField('Status', 'department-status', ['Active','Inactive']), namedTextareaField('Notes', 'department-notes', 'Optional organization notes')
        ]]
      ])
    },
    'rental-worker': {
      title: 'Add rental worker',
      saveLabel: 'Create worker',
      html: () => {
        const draft = state.inlineRentalDraft || {};
        const supplierOptions = state.suppliers.filter(s => s.status === 'Active').map(s => ({ value:s.id, label:`${s.name} · ${s.code}` }));
        return formSections([
          ['Worker identity', 'Create the permanent worker once. Project, trade and rate are effective-dated assignment data and are managed separately.', [
            namedField('Worker ID (auto if blank)', 'rental-worker-code', draft['rental-worker-code'] || ''),
            namedField('Full name', 'rental-worker-name', draft['rental-worker-name'] || ''),
            namedField('Iqama / National ID', 'rental-worker-national-id', draft['rental-worker-national-id'] || ''),
            namedField('Phone', 'rental-worker-phone', draft['rental-worker-phone'] || '')
          ]],
          ['Supplier relationship', 'Every rental worker belongs to one managed manpower supplier. Assignment history will reference this permanent worker master.', [
            namedSelectOptions('Manpower supplier', 'rental-worker-supplier', supplierOptions, draft['rental-worker-supplier'] || supplierOptions[0]?.value || ''),
            namedSelectFieldValue('Master status', 'rental-worker-status', ['Active','Inactive'], draft['rental-worker-status'] || 'Active'),
            `<div class="form-field"><label>&nbsp;</label><button class="btn btn--secondary btn--form" type="button" data-inline-create="supplier">+ New supplier</button><span class="field-hint">Create a supplier master without leaving worker onboarding.</span></div>`,
            namedTextareaFieldValue('Notes', 'rental-worker-notes', draft['rental-worker-notes'] || '', 'Optional worker-master notes')
          ]]
        ]);
      }
    },
    'project': {
      title: 'Add project',
      saveLabel: 'Create project',
      html: () => formSections([['Project master', 'Create one controlled project record for rental assignments, timesheets and supplier costing.', [
        namedField('Project name', 'project-name', ''),
        namedField('Project code (auto if blank)', 'project-code', ''),
        namedField('Client / principal', 'project-client', ''),
        namedField('Location / site', 'project-location', ''),
        namedField('Start date', 'project-start', '', 'date'),
        namedField('Expected / actual end', 'project-end', '', 'date'),
        namedField('Project manager', 'project-manager', ''),
        namedSelectFieldValue('Status', 'project-status', ['Active','On Hold','Completed'], 'Active'),
        namedTextareaFieldValue('Notes', 'project-notes', '', 'Optional project notes')
      ]]])
    },
    'supplier': {
      title: 'Add manpower supplier',
      saveLabel: 'Create supplier',
      html: () => formSections([
        ['Supplier master', 'Keep one formal supplier record and reuse it across rental workers, assignments, settlements and payments.', [
          namedField('Company name', 'supplier-name', ''),
          namedField('Supplier code (auto if blank)', 'supplier-code', ''),
          namedSelectFieldValue('Status', 'supplier-status', ['Active','Inactive'], 'Active'),
          namedField('Contact person', 'supplier-contact', ''),
          namedField('Phone', 'supplier-phone', ''),
          namedField('Email', 'supplier-email', '', 'email')
        ]],
        ['Commercial & payment', 'Store verified commercial details on the managed supplier record.', [
          namedField('CR', 'supplier-cr', ''),
          namedField('VAT number', 'supplier-vat', ''),
          namedField('Payment terms', 'supplier-payment-terms', ''),
          namedField('Address', 'supplier-address', ''),
          namedTextareaFieldValue('Notes', 'supplier-notes', '', 'Optional supplier notes')
        ]]
      ])
    },
    'advance': {
      title: 'Record advance / adjustment',
      saveLabel: 'Save Transaction',
      html: () => {
        const context = state.drawerContext || {};
        const isRental = state.workspace === 'rental';
        const workforce = isRental ? 'Rental Worker' : 'Internal Employee';
        const internalOptions = state.employees.map(employee => ({ value:employee.id, label:`EMP ${employee.employeeId} · ${employee.name}` }));
        const rentalOptions = state.rentalWorkers.map(worker => ({ value:worker.id, label:`${rentalWorkerCode(worker)} · ${worker.name}` }));
        const selectedPerson = context.personId || (isRental ? rentalOptions[0]?.value : internalOptions[0]?.value) || '';
        const projectOptions = isRental ? state.projects.map(project => ({value:project.id,label:`${project.name} · ${project.code}`})) : [{value:'',label:'Internal employee-level'}];
        const types = isRental ? ['Worker Advance','Fine / Penalty','Bonus','Reimbursement','Other Earning','Other Deduction'] : ['Salary Advance','Advance Recovery','Fine','Bonus','Reimbursement','Other Earning','Other Deduction'];
        const ownerFields = [
          namedSelectFieldValue('Workforce type','adjustment-workforce',[workforce],workforce),
          `<div class="form-field form-field--wide"><label for="adjustment-person">Person</label><select class="select" id="adjustment-person" name="adjustment-person"></select><span class="field-hint">Managed employee/worker master only.</span></div>`,
          namedSelectOptions(isRental?'Project':'Project','adjustment-project',projectOptions,context.projectId || projectOptions[0]?.value || ''),
          namedSelectFieldValue('Transaction type','adjustment-type',types,context.type || (isRental?'Worker Advance':'Salary Advance'))
        ];
        const amountFields = [
          namedField(`Amount (${currencyCode()})`,'adjustment-amount',context.amount || '0','number'),
          namedField('Effective date','adjustment-date',context.date || rentalTodayIso(),'date'),
          namedField(isRental?'Settlement period':'Payroll period','adjustment-period',context.period || state.period),
          `<div class="form-field"><label>Status</label><strong class="field-static">Draft</strong><span class="field-hint">Submit and approval are separate audited actions.</span></div>`,
          namedField('Reference','adjustment-reference',context.reference || ''),
          namedTextareaField('Reason / notes','adjustment-reason',context.reason || '')
        ];
        if (!isRental) {
          amountFields.push(
            namedSelectFieldValue('Recovery plan','adjustment-recovery-plan',['No automatic schedule','Fixed installment'],context.recoveryPlan || 'No automatic schedule'),
            namedField(`Installment amount (${currencyCode()})`,'adjustment-installment',context.installmentAmount || '','number'),
            namedField('Recovery starts','adjustment-recovery-start',context.recoveryStart || `${periodKeyFromLabel()}-01`,'date')
          );
        }
        return `<section class="adjustment-drawer-intro"><span class="eyebrow">Controlled financial transaction</span><p>${isRental?'Rental adjustments are attributed to the worker, supplier, project and effective assignment. Approved transactions are snapshotted into supplier settlement calculation.':'One-time earnings and deductions stay outside the permanent salary master and flow into payroll only after approval.'}</p></section>${formSections([
          ['Transaction owner', isRental?'A rental adjustment must belong to a managed project and an assignment effective on the transaction date.':'Choose the managed internal employee.', ownerFields],
          ['Amount & financial application', 'Draft/Review transactions are visible but excluded from calculation until Approved.', amountFields]
        ])}`;
      }
    },
    'attendance-import': {
      title: 'Import attendance',
      saveLabel: 'Validate & Import',
      html: () => `<section class="form-section"><div class="form-section__head"><strong>${escapeHtml(state.period)} attendance import</strong><span>Paste tab-separated Excel data or comma-separated CSV. Employee numbers are matched only against the active company.</span></div><label class="form-field form-field--full"><span>Attendance rows</span><textarea name="attendance-import-text" rows="14" placeholder="Employee ID\t1\t2\t3\t4\n0001\t8\t8\t8\t8"></textarea><span class="field-hint">First column: Employee ID / Employee Number. Remaining headers must be day numbers 1–${periodInfo().days}. Blank cells are ignored.</span></label></section><section class="source-note">${icon('info')}<span><strong>Validation before write.</strong> Invalid employee numbers, dates, attendance codes or duplicate employee rows reject the import before any attendance entry is changed.</span></section>`
    },
    'attendance-return': {
      title: 'Return attendance to Draft',
      saveLabel: 'Return to Draft',
      html: () => `<section class="form-section"><div class="form-section__head"><strong>${escapeHtml(state.period)} · ${escapeHtml(timesheetStatus())}</strong><span>Returning the reviewed period re-enables attendance and overtime editing. The reason is written to the company audit trail.</span></div><label class="form-field form-field--full"><span>Return reason</span><textarea name="attendance-return-reason" rows="6" maxlength="1000" placeholder="Describe what must be corrected before resubmission."></textarea></label></section>`
    },
    'salary-component': {
      title: 'Salary component',
      saveLabel: 'Save component',
      html: () => {
        const item = state.salaryComponents.find(component => component.id === state.drawerContext) || {};
        return formSections([
          ['Component identity', 'Reusable payroll components prevent every employee and payroll month from defining its own arbitrary columns.', [
            namedField('Component name', 'salary-component-name', item.name || ''),
            namedField('Code', 'salary-component-code', item.code || ''),
            namedSelectFieldValue('Type', 'salary-component-category', ['Earning','Deduction'], item.category || 'Earning'),
            namedSelectFieldValue('Status', 'salary-component-status', ['Active','Inactive'], item.status || 'Active')
          ]],
          ['Payroll behavior', 'Define where the component belongs and how payroll should source its value.', [
            namedSelectFieldValue('Usage', 'salary-component-recurrence', ['Recurring','Variable'], item.recurrence || 'Recurring'),
            namedSelectFieldValue('Calculation', 'salary-component-calculation', ['Fixed Amount','Manual Amount'], item.calculation || 'Fixed Amount'),
            namedSelectFieldValue('WPS mapping', 'salary-component-wps', ['Basic Salary','Housing Allowance','Other Earnings','Deductions','Not mapped'], item.wpsMap || 'Not mapped'),
            namedTextareaFieldValue('Notes', 'salary-component-notes', item.notes || '', 'Optional administrative notes')
          ]]
        ]);
      }
    },
    'salary-structure': {
      title: 'Employee salary structure',
      saveLabel: 'Save structure',
      html: () => {
        const employeeId = state.drawerContext || '';
        const employee = state.employees.find(item => item.id === employeeId);
        const salary = employee ? employeeProfileData(employee).salary : null;
        const currentAmounts = Object.fromEntries((salary?.components || []).map(component => [component.id, Number(component.amount) || 0]));
        const recurring = state.salaryComponents.filter(component => component.status === 'Active' && component.recurrence === 'Recurring');
        const employeeOptions = state.employees.map(item => ({ value: item.id, label: `${item.employeeId} · ${item.name}` }));
        const policyOptions = [{ value: '', label: 'No overtime policy' }, ...state.overtimePolicies.filter(item => item.status === 'Active').map(item => ({ value: item.id, label: item.name }))];
        const currentPolicy = salary?.otPolicyId || '';
        return `
          <section class="form-section"><div class="form-section__head"><strong>Structure assignment</strong><span>Salary changes require an effective date. Historical payroll keeps the structure that was valid in that period.</span></div><div class="form-grid">
            ${namedSelectOptions('Employee', 'salary-structure-employee', employeeOptions, employeeId)}
            ${namedField('Effective from', 'salary-structure-effective', '', 'date')}
            ${namedSelectOptions('Overtime policy', 'salary-structure-ot-policy', policyOptions, currentPolicy)}
            <div class="form-field"><label>Current effective date</label><div class="readonly-field">${escapeHtml(salary?.effective || 'Not configured')}</div></div>
          </div></section>
          <section class="form-section"><div class="form-section__head"><strong>Recurring components</strong><span>Only permanent earnings/deductions belong here. Overtime, advances and other period adjustments remain outside the structure.</span></div><div class="salary-structure-editor">
            ${recurring.map(component => `<label class="salary-editor-row"><span><strong>${escapeHtml(component.name)}</strong><small>${escapeHtml(component.category)} · ${escapeHtml(component.code)}</small></span><div class="money-input"><em>${escapeHtml(currencyCode())}</em><input type="number" min="0" step="0.01" name="salary-amount-${component.id}" value="${currentAmounts[component.id] || ''}" placeholder="0.00"></div></label>`).join('')}
          </div></section>
          <section class="drawer-calculation-preview"><span>Structure rule</span><strong>Recurring earnings − recurring deductions</strong><small>Overtime and one-time adjustments are calculated separately during the payroll run.</small></section>`;
      }
    },
    'overtime-policy': {
      title: 'Overtime policy',
      saveLabel: 'Save policy',
      html: () => {
        const item = state.overtimePolicies.find(policy => policy.id === state.drawerContext) || {};
        const bases = state.salaryComponents.filter(component => component.category === 'Earning' && component.recurrence === 'Recurring' && component.status === 'Active').map(component => ({ value: component.id, label: `${component.code} · ${component.name}` }));
        return formSections([
          ['Policy identity', 'Create a named rule that can be assigned to employee salary structures.', [
            namedField('Policy name', 'ot-policy-name', item.name || ''),
            namedField('Code', 'ot-policy-code', item.code || ''),
            namedSelectFieldValue('Status', 'ot-policy-status', ['Active','Inactive'], item.status || 'Active')
          ]],
          ['Formula', 'Define the earning component and formula used to calculate overtime.', [
            namedSelectOptions('Base component', 'ot-policy-base', bases, item.baseComponentId || ''),
            namedField('Divisor', 'ot-policy-divisor', item.divisor ?? '', 'number'),
            namedField('Multiplier', 'ot-policy-multiplier', item.multiplier ?? '', 'number'),
            namedTextareaFieldValue('Notes', 'ot-policy-notes', item.notes || '', 'Optional policy notes')
          ]]
        ]);
      }
    }
  };

  function payrollRequiredFieldNames(type = state.drawerType) {
    const fixed = {
      'internal-employee': ['employee-name','employee-position','employee-department','employee-joining','employee-branch'],
      'internal-employee-edit': ['employee-id','employee-name','employee-joining'],
      'branch': ['branch-name'],
      'branch-edit': ['branch-name','branch-code'],
      'department': ['department-name'],
      'department-edit': ['department-name','department-code'],
      'employee-organization': ['organization-branch','organization-department','organization-position','organization-effective'],
      'rental-worker': ['rental-worker-name','rental-worker-supplier'],
      'supplier': ['supplier-name'],
      'supplier-edit': ['supplier-name','supplier-code'],
      'project': ['project-name','project-start'],
      'project-edit': ['project-name','project-code','project-start'],
      'attendance-import': ['attendance-import-text'],
      'attendance-return': ['attendance-return-reason'],
      'salary-component': ['salary-component-name'],
      'salary-structure': ['salary-structure-employee','salary-structure-effective'],
      'overtime-policy': ['ot-policy-name','ot-policy-base','ot-policy-divisor','ot-policy-multiplier'],
      'advance': ['adjustment-person','adjustment-amount','adjustment-date'],
      'bank-template': ['bank-template-code','bank-template-name','bank-template-columns','bank-template-headers'],
      'supplier-payment': ['supplier-payment-settlement','supplier-payment-amount','supplier-payment-date'],
      'payroll-policy': ['payroll-proration-method'],
      'document-generate': ['document-source'],
    };
    const names = [...(fixed[type] || [])];

    if (type === 'advance' && state.workspace === 'rental') names.push('adjustment-project');
    if (type === 'salary-component' && state.drawerContext) names.push('salary-component-code');
    if (type === 'overtime-policy' && state.drawerContext) names.push('ot-policy-code');

    if (type === 'document-generate') {
      const sources = state.drawerContext?.sources || [];
      const index = Number(drawerBody?.querySelector('[name="document-source"]')?.value || 0);
      if (sources[index]?.type === 'supplier_invoice') {
        names.push('document-invoice-number','document-issue-date','document-vat-amount');
      }
    }

    if (['internal-employee','internal-employee-edit'].includes(type)) {
      const status = drawerBody?.querySelector('[name="employee-status"]')?.value || '';
    }

    if (['project','project-edit'].includes(type)) {
      const status = drawerBody?.querySelector('[name="project-status"]')?.value || '';
      if (status === 'Completed') names.push('project-end');
    }

    if (type === 'bank-template') {
      const resultNames = ['bank-result-employee','bank-result-status','bank-result-reference','bank-result-reason'];
      if (resultNames.some(name => String(drawerBody?.querySelector(`[name="${name}"]`)?.value || '').trim())) {
        names.push('bank-result-employee','bank-result-status');
      }
    }

    if (type === 'employee-payment-profile') {
      names.push('payment-profile-holder','payment-profile-bank-name');
      const employeeId = state.drawerContext?.employeeId;
      const profile = employeeId ? paymentContextForPeriod().profiles?.[employeeId] : null;
      const destination = drawerBody?.querySelector('[name="payment-profile-destination"]')?.value || 'Bank account / IBAN';
      if (destination === 'Salary card') {
        if (!(profile?.destinationType === 'salary_card' && profile?.salaryCardMasked)) names.push('payment-profile-card');
      } else if (!(profile?.destinationType === 'iban' && profile?.ibanMasked)) {
        names.push('payment-profile-iban');
      }
    }

    if (type === 'salary-structure') {
      const basic = state.salaryComponents.find(component => component.status === 'Active' && component.recurrence === 'Recurring' && component.wpsMap === 'Basic Salary');
      if (basic?.id) names.push(`salary-amount-${basic.id}`);
    }

    if (type === 'supplier-payment') {
      const status = drawerBody?.querySelector('[name="supplier-payment-status"]')?.value || '';
      const method = drawerBody?.querySelector('[name="supplier-payment-method"]')?.value || '';
      if (status === 'Paid' && method !== 'Cash') names.push('supplier-payment-reference');
    }

    if (type === 'supplier-payment-result') {
      const status = drawerBody?.querySelector('[name="supplier-payment-result-status"]')?.value || '';
      const found = supplierPaymentById(state.drawerContext?.paymentId);
      const method = found?.payment?.method || '';
      if (status === 'Paid' && method !== 'Cash') names.push('supplier-payment-result-reference');
      if (['Failed','Reversed'].includes(status)) names.push('supplier-payment-result-note');
    }

    if (type === 'payroll-review-decision') {
      if (state.drawerContext === 'approve') names.push('payroll-review-confirm');
      else names.push('payroll-review-note');
    }

    if (type === 'rental-assignment-action') {
      const action = state.drawerContext?.action;
      if (action === 'edit') names.push('rental-action-worker-code','rental-action-name');
      else if (action === 'advance') names.push('rental-action-date','rental-action-project','rental-action-amount');
      else if (action === 'cancel') names.push('rental-action-reason');
      else {
        names.push('rental-action-date');
        if (['assign','transfer'].includes(action)) names.push('rental-action-project','rental-action-trade','rental-action-rate');
        if (action === 'trade') names.push('rental-action-trade');
        if (action === 'rate') names.push('rental-action-rate');
      }
    }

    return [...new Set(names.filter(Boolean))];
  }

  function applyPayrollRequiredFields(root = drawerBody, type = state.drawerType) {
    if (!root?.querySelectorAll || !type) return;
    const requiredNames = new Set(payrollRequiredFieldNames(type));

    root.querySelectorAll('[data-required-label="true"]').forEach(label => {
      label.classList.remove('required');
      delete label.dataset.requiredLabel;
    });

    root.querySelectorAll('[data-payroll-required="true"]').forEach(control => {
      if (requiredNames.has(control.name)) return;
      control.required = false;
      control.removeAttribute('data-required');
      control.removeAttribute('data-payroll-required');
      control.removeAttribute('aria-required');
      window.PlatformFormValidation?.clearInvalid?.(control);
    });

    requiredNames.forEach(name => {
      const control = root.querySelector(`[name="${CSS.escape(name)}"]`);
      if (!control || control.disabled) return;
      control.required = true;
      control.dataset.required = 'true';
      control.dataset.payrollRequired = 'true';
      control.setAttribute('aria-required', 'true');
    });
    window.PlatformFormValidation?.decorate?.(root);
  }

  function validatePayrollRequiredFields() {
    applyPayrollRequiredFields(drawerBody, state.drawerType);
    const valid = window.PlatformFormValidation?.validateRequired?.(drawerBody);
    if (valid === false) {
      showToast('Required fields missing', 'Complete the highlighted fields marked with * before saving.');
      return false;
    }
    return true;
  }

  function markPayrollFieldInvalid(name, message = 'Required') {
    const control = drawerBody?.querySelector(`[name="${CSS.escape(name)}"]`);
    if (!control) return;
    window.PlatformFormValidation?.markInvalid?.(control, message);
    control.focus?.({ preventScroll:true });
    control.scrollIntoView?.({ behavior:'smooth', block:'center' });
  }

  function field(label, placeholder, type='text') { return `<div class="form-field"><label>${label}</label><input class="input" type="${type}" placeholder="${escapeHtml(placeholder)}"></div>`; }
  function namedField(label, name, value, type='text') { return `<div class="form-field"><label>${label}</label><input class="input" name="${name}" type="${type}" value="${escapeHtml(value)}" placeholder="${escapeHtml(value || label)}"></div>`; }
  function textareaField(label, placeholder) { return `<div class="form-field form-field--full"><label>${label}</label><textarea class="textarea" placeholder="${escapeHtml(placeholder)}"></textarea></div>`; }
  function namedTextareaField(label, name, placeholder) { return `<div class="form-field form-field--full"><label>${label}</label><textarea class="textarea" name="${name}" placeholder="${escapeHtml(placeholder)}"></textarea></div>`; }
  function namedTextareaFieldValue(label, name, value, placeholder='') { return `<div class="form-field form-field--full"><label>${label}</label><textarea class="textarea" name="${name}" placeholder="${escapeHtml(placeholder)}">${escapeHtml(value)}</textarea></div>`; }
  function selectField(label, options) { return `<div class="form-field"><label>${label}</label><select class="select">${options.map(x=>`<option>${escapeHtml(x)}</option>`).join('')}</select></div>`; }
  function namedSelectField(label, name, options) { return `<div class="form-field"><label>${label}</label><select class="select" name="${name}">${options.map(x=>`<option>${escapeHtml(x)}</option>`).join('')}</select></div>`; }
  function namedSelectFieldValue(label, name, options, current) { return `<div class="form-field"><label>${label}</label><select class="select" name="${name}">${options.map(x=>`<option ${String(x) === String(current) ? 'selected' : ''}>${escapeHtml(x)}</option>`).join('')}</select></div>`; }
  function namedSelectOptions(label, name, options, current) { return `<div class="form-field"><label>${label}</label><select class="select" name="${name}">${options.map(x=>`<option value="${escapeHtml(x.value)}" ${String(x.value) === String(current) ? 'selected' : ''}>${escapeHtml(x.label)}</option>`).join('')}</select></div>`; }
  function selectWithCreate(label, options, type) { return `<div class="form-field form-field--full"><label>${label}</label><div class="inline-create"><select class="select">${options.map(x=>`<option>${escapeHtml(x)}</option>`).join('')}</select><button class="btn btn--secondary" type="button" data-inline-create="${type}">+ New</button></div><span class="field-hint">Existing records appear here; creating a new one returns to this form.</span></div>`; }
  function formSections(sections) { return sections.map(([title, subtitle, fields]) => `<section class="form-section"><div class="form-section__head"><strong>${title}</strong><span>${subtitle}</span></div><div class="form-grid">${fields.join('')}</div></section>`).join(''); }

  function lifecycleMenuItem({label, hint='', iconName='info', attrs='', danger=false, disabled=false}) {
    return `<button type="button" class="ui-v2-menu__item${danger ? ' ui-v2-menu__item--danger' : ''}" ${attrs} data-lifecycle-menu-action ${disabled ? 'disabled aria-disabled="true"' : ''}>${icon(iconName)}<span class="ui-v2-menu__copy"><strong>${escapeHtml(label)}</strong>${hint ? `<small>${escapeHtml(hint)}</small>` : ''}</span></button>`;
  }

  function lifecycleActionsMenu(items, {label='Actions', compact=false} = {}) {
    const rendered = items.map(item => item === 'separator' ? '<div class="ui-v2-menu__separator" role="separator"></div>' : lifecycleMenuItem(item)).join('');
    return `<div class="ui-v2-prs-dropdown ui-v2-lifecycle-menu" data-dropdown><button type="button" class="btn btn--secondary${compact ? ' btn--sm' : ''} ui-v2-lifecycle-menu__trigger" data-dropdown-trigger aria-haspopup="menu" aria-expanded="false">${escapeHtml(label)} ${icon('more')}</button><div class="ui-v2-menu ui-v2-prs-dropdown-menu ui-v2-lifecycle-menu__menu" data-dropdown-menu role="menu"><div class="ui-v2-menu__label">Record actions</div>${rendered}</div></div>`;
  }

  function lifecycleDrawerIntro(title, copy, danger=false) {
    return `<section class="ui-v2-lifecycle-panel${danger ? ' ui-v2-lifecycle-panel--danger' : ''}"><strong>${escapeHtml(title)}</strong><span>${escapeHtml(copy)}</span></section>`;
  }

  function clearLifecycleDrawerError() {
    drawerBody?.querySelector('.ui-v2-lifecycle-error')?.remove();
  }

  function showLifecycleDrawerError(error, fallback='This lifecycle action could not be completed.') {
    clearLifecycleDrawerError();
    const raw = String(error?.message || fallback);
    drawerBody?.insertAdjacentHTML('afterbegin', `<div class="ui-v2-lifecycle-error" role="alert"><strong>Action blocked</strong><span>${escapeHtml(raw)}</span></div>`);
  }

  function openSalaryComponentDrawer(componentId = null) {
    openQuickDrawer('salary-component', componentId);
    drawerTitle.textContent = componentId ? 'Edit salary component' : 'Add salary component';
    drawerSave.textContent = componentId ? 'Save changes' : 'Create component';
  }

  function openSalaryStructureDrawer(employeeId = null) {
    openQuickDrawer('salary-structure', employeeId);
    const employee = state.employees.find(item => item.id === employeeId);
    drawerTitle.textContent = employee ? `${employee.name} · Salary structure` : 'Assign salary structure';
    drawerSave.textContent = employeeProfileData(employee || {}).salary ? 'Create effective change' : 'Save structure';
  }

  function openOvertimePolicyDrawer(policyId = null) {
    openQuickDrawer('overtime-policy', policyId);
    drawerTitle.textContent = policyId ? 'Edit overtime policy' : 'Add overtime policy';
    drawerSave.textContent = policyId ? 'Save policy' : 'Create policy';
  }

  function openBranchEditDrawer(branchId) {
    const branch = state.branches.find(item=>item.id===branchId);
    if (!branch) return;
    state.drawerType='branch-edit'; state.drawerContext={branchId};
    drawerTitle.textContent='Edit branch / office'; drawerSave.hidden=false; drawerSave.textContent='Save Changes';
    drawerBody.innerHTML=formSections([[`Branch / office master`, 'Changes affect future organization selections while existing employee history stays intact.', [
      namedField('Branch / office name','branch-name',branch.name||''), namedField('Branch code','branch-code',branch.code||''), namedSelectFieldValue('Type','branch-kind',['Branch','Office'],branch.type||'Branch'), namedField('Location / city','branch-location',branch.location||''), namedField('Address','branch-address',branch.address||''), namedField('Branch manager','branch-manager',branch.manager||''), namedSelectFieldValue('Status','branch-status',['Active','Inactive'],branch.archived?'Inactive':(branch.status||'Active'))
    ]]]);
    drawer.classList.add('is-open'); drawerScrim.classList.add('is-open'); drawer.setAttribute('aria-hidden','false');
  }

  function openDepartmentEditDrawer(departmentId) {
    const department = state.departments.find(item=>item.id===departmentId);
    if (!department) return;
    state.drawerType='department-edit'; state.drawerContext={departmentId};
    drawerTitle.textContent='Edit department'; drawerSave.hidden=false; drawerSave.textContent='Save Changes';
    drawerBody.innerHTML=formSections([[`Department master`, 'Renaming the master updates current employee organization labels without deleting historical assignment events.', [
      namedField('Department name','department-name',department.name||''), namedField('Department code','department-code',department.code||''), namedSelectFieldValue('Status','department-status',['Active','Inactive'],department.status||'Active'), namedTextareaField('Notes','department-notes',department.notes||'')
    ]]]);
    drawer.classList.add('is-open'); drawerScrim.classList.add('is-open'); drawer.setAttribute('aria-hidden','false');
  }

  function openConfigurationLifecycleDrawer(kind, id, action) {
    let record=null, label='configuration record', token='';
    if(kind==='component'){record=state.salaryComponents.find(item=>item.id===id);label='salary component';token=record?.code||'';}
    else if(kind==='overtime'){record=state.overtimePolicies.find(item=>item.id===id);label='overtime policy';token=record?.code||'';}
    else if(kind==='template'){record=bankTemplatesAll().find(item=>item.id===id);label='bank / WPS export template';token=record?.code||'';}
    else if(kind==='payment-profile'){const employee=state.employees.find(item=>item.id===id);const profile=paymentContextForPeriod().profiles?.[id];if(!employee||!profile)return;record={name:employee.name};label='employee payment profile';token=employee.employeeId||'';}
    if(!record)return;
    state.drawerType='configuration-lifecycle'; state.drawerContext={kind,id,action,token}; drawerSave.hidden=false; drawerSave.disabled=false; drawerSave.classList.toggle('is-lifecycle-danger', action==='delete');
    if(action==='archive'){
      drawerTitle.textContent=`Archive ${label}`; drawerSave.textContent='Archive record';
      drawerBody.innerHTML=lifecycleDrawerIntro('Archive preserves history','This record will stop appearing in new Payroll selections, but every historical salary, payment and export reference remains intact.')+formSections([[`Archive ${record.name}`,'A reason is required for the lifecycle audit trail.',[namedTextareaField('Archive reason','configuration-lifecycle-reason','')]]]);
    }else if(action==='restore'){
      drawerTitle.textContent=`Restore ${label}`; drawerSave.textContent='Restore record';
      drawerBody.innerHTML=lifecycleDrawerIntro('Restore safely','Restored configuration returns as Inactive. Review it before activating it for new Payroll work.')+formSections([[`Restore ${record.name}`,'Historical records are not rewritten.',[namedTextareaField('Restore note','configuration-lifecycle-reason','')]]]);
    }else{
      drawerTitle.textContent=`Delete unused ${label}`; drawerSave.textContent='Delete unused record';
      drawerBody.innerHTML=lifecycleDrawerIntro('Delete only mistaken, unused setup','The server will reject this action if any protected salary, payment or export history exists. Real historical records must be archived instead.',true)+formSections([[`Permanent delete`,'Type the exact code to confirm this destructive action.',[namedField(`Type ${token} to confirm delete`,'configuration-lifecycle-confirmation',''),namedTextareaField('Reason / note','configuration-lifecycle-reason','Duplicate or mistaken setup')]]]);
    }
    drawer.classList.add('is-open'); drawerScrim.classList.add('is-open'); drawer.setAttribute('aria-hidden','false');
  }

  function openOrganizationLifecycleDrawer(kind, id, action) {
    const collection = kind === 'branch' ? state.branches : state.departments;
    const record = collection.find(item => item.id === id);
    if (!record) return;
    const label = kind === 'branch' ? 'branch / office' : 'department';
    state.drawerType = 'organization-lifecycle';
    state.drawerContext = { kind, id, action };
    drawerSave.hidden = false;
    drawerSave.classList.toggle('is-lifecycle-danger', action === 'delete');
    if (action === 'archive') {
      drawerTitle.textContent = `Archive ${label}`; drawerSave.textContent = 'Archive record';
      drawerBody.innerHTML = lifecycleDrawerIntro('Archive preserves organization history','The master is removed from new employee assignments while existing organization and payroll history continues to resolve normally.') + formSections([[`Archive ${record.name}`, 'A reason is required for the audit trail.', [namedTextareaField('Archive reason','organization-lifecycle-reason','')]]]);
    } else if (action === 'restore') {
      drawerTitle.textContent = `Restore ${label}`; drawerSave.textContent = 'Restore record';
      drawerBody.innerHTML = lifecycleDrawerIntro('Restore safely','The master returns to its exact previous active/inactive state. Employee scope hidden by this parent lifecycle becomes available again automatically.') + formSections([[`Restore ${record.name}`, 'Historical employee/payroll context is unchanged.', [namedTextareaField('Restore note','organization-lifecycle-reason','')]]]);
    } else {
      drawerTitle.textContent = `Delete ${label}`; drawerSave.textContent = 'Delete';
      drawerBody.innerHTML = lifecycleDrawerIntro('Delete with 30-day recovery','The record and its current employee scope are removed from operational registers together and can be restored for 30 days. Payroll and organization history is preserved.',true) + formSections([[`Delete record`, 'Type the exact master code to confirm and provide a reason.', [namedField(`Type ${record.code} to confirm`,'organization-lifecycle-confirmation',''), namedTextareaField('Deletion reason','organization-lifecycle-reason','')]]]);
    }
    drawer.classList.add('is-open'); drawerScrim.classList.add('is-open'); drawer.setAttribute('aria-hidden','false');
  }

  function openRentalMasterLifecycleDrawer(kind, id, action='manage') {
    const record = kind === 'supplier' ? state.suppliers.find(item=>item.id===id) : state.rentalWorkers.find(item=>item.id===id);
    if (!record) return;
    state.drawerType='rental-master-lifecycle'; state.drawerContext={kind,id,action}; drawerSave.hidden=false; drawerSave.disabled=false; drawerSave.classList.toggle('is-lifecycle-danger', action === 'delete');
    const code=kind==='supplier'?record.code:rentalWorkerCode(record); const label=kind==='supplier'?'manpower supplier':'rental worker';
    if (action === 'archive') {
      drawerTitle.textContent=`Archive ${label}`; drawerSave.textContent='Archive record';
      drawerBody.innerHTML=lifecycleDrawerIntro('Archive preserves manpower history','Assignments, timesheets, settlements and payments remain intact while the master is removed from new operational selections.')+formSections([[`Archive ${record.name}`,'A reason is required for the audit trail.',[namedTextareaField('Archive reason','rental-lifecycle-reason','')]]]);
    } else if (action === 'restore') {
      drawerTitle.textContent=`Restore ${label}`; drawerSave.textContent='Restore record';
      drawerBody.innerHTML=lifecycleDrawerIntro('Restore safely','The master returns to its exact previous status. Any worker scope hidden only by this parent lifecycle becomes available again automatically.')+formSections([[`Restore ${record.name}`,'Historical manpower records are unchanged.',[namedTextareaField('Restore note','rental-lifecycle-reason','')]]]);
    } else if (action === 'delete') {
      drawerTitle.textContent=`Delete ${label}`; drawerSave.textContent='Delete';
      drawerBody.innerHTML=lifecycleDrawerIntro('Delete with 30-day recovery','The master is recoverable from the Delete page for 30 days. Dependent operational scope follows the lifecycle automatically while historical assignments, timesheets, settlements and payments remain intact.',true)+formSections([[`Delete record`,'Type the exact worker/supplier code to confirm and provide a reason.',[namedField(`Type ${code} to confirm`,'rental-lifecycle-confirmation',''),namedTextareaField('Deletion reason','rental-lifecycle-reason','')]]]);
    } else if (kind === 'worker') {
      if (record.archived) { showToast('Worker is archived','Use the separate Restore from archive action.'); return; }
      if (record.masterStatusValue==='terminated') { showToast('Worker already terminated','This worker cannot be reactivated. Create a new onboarding record if the worker returns.'); return; }
      const actions=record.masterStatusValue==='inactive'?[{value:'activate',label:'Reactivate worker'},{value:'terminate',label:'Terminate worker'}]:[{value:'deactivate',label:'Stop worker activity (temporary)'},{value:'terminate',label:'Terminate worker'}];
      drawerTitle.textContent=`${record.name} · Worker status`; drawerSave.textContent='Apply Action';
      drawerBody.innerHTML=lifecycleDrawerIntro('Worker activity lifecycle','Stop activity is temporary and keeps the current assignment relationship ready for later reactivation. Terminate stops new assignments/timesheets immediately and retains all historical assignments, timesheets, settlements and payments.')+formSections([[`Choose lifecycle action`,'Termination is final for this worker record. A reason is retained in the audit trail.',[namedSelectOptions('Action','rental-lifecycle-action',actions,actions[0]?.value||''),namedField('Effective stop / termination date','rental-lifecycle-effective',rentalTodayIso(),'date'),namedTextareaField('Reason','rental-lifecycle-reason',record.inactiveReason||record.terminationReason||record.archivedReason||'')]]]);
    } else if (kind === 'supplier') {
      if (record.archived) { showToast('Supplier is archived','Use the separate Restore from archive action.'); return; }
      if (record.statusValue==='terminated') { showToast('Supplier already terminated','This supplier relationship cannot be reactivated. Create a new supplier relationship if business resumes.'); return; }
      const actions=record.statusValue==='inactive'?[{value:'activate',label:'Reactivate supplier'},{value:'terminate',label:'Terminate supplier relationship'}]:[{value:'deactivate',label:'Stop supplier activity (temporary)'},{value:'terminate',label:'Terminate supplier relationship'}];
      drawerTitle.textContent=`${record.name} · Supplier status`; drawerSave.textContent='Apply Action';
      drawerBody.innerHTML=lifecycleDrawerIntro('Supplier activity lifecycle','Stop activity is temporary and inherited by supplier workers without rewriting their master or assignment history. Terminate immediately stops supplier activity and cascades termination to its current worker scope while preserving assignment, timesheet, settlement and payment history.')+formSections([[`Choose lifecycle action`,'Termination is final for this supplier relationship. Archive and Delete remain separate.',[namedSelectOptions('Action','rental-lifecycle-action',actions,actions[0]?.value||''),namedField('Effective stop / termination date','rental-lifecycle-effective',rentalTodayIso(),'date'),namedTextareaField('Reason','rental-lifecycle-reason',record.inactiveReason||record.terminationReason||record.archivedReason||'')]]]);
    } else { return; }
    drawer.classList.add('is-open');drawerScrim.classList.add('is-open');drawer.setAttribute('aria-hidden','false');
  }

  function openEmployeeOrganizationDrawer(employeeId) {
    const employee=state.employees.find(item=>item.id===employeeId);
    if (!employee) return;
    state.drawerType='employee-organization'; state.drawerContext={employeeId};
    const branchOptions=state.branches.filter(item=>item.status==='Active' || item.id===employee.branchId).map(item=>({value:item.id,label:`${item.name} · ${item.code}`}));
    const departmentOptions=state.departments.filter(item=>item.status==='Active' || item.id===employee.departmentId).map(item=>({value:item.id,label:`${item.name} · ${item.code}`}));
    drawerTitle.textContent='Change organization assignment'; drawerSave.hidden=false; drawerSave.textContent='Apply Change';
    drawerBody.innerHTML=`<section class="organization-change-summary"><span class="eyebrow">Internal company movement</span><h3>${escapeHtml(employee.name)}</h3><p>Current: <strong>${escapeHtml(employee.branch||'Branch not set')}</strong> · ${escapeHtml(employee.department||'Department not set')} · ${escapeHtml(employee.position||'—')}</p></section>${formSections([
      ['New organization assignment','Use an effective date. Previous branch/department context remains in organization history.',[
        namedSelectOptions('Branch / Office','organization-branch',branchOptions,employee.branchId||branchOptions[0]?.value||''), namedSelectOptions('Department','organization-department',departmentOptions,employee.departmentId||departmentByName(employee.department)?.id||departmentOptions[0]?.value||''), namedField('Position / designation','organization-position',employee.position||''), namedField('Effective date','organization-effective',rentalTodayIso(),'date'), namedTextareaField('Reason / notes','organization-reason','Transfer, department change, promotion, office move…')
      ]]
    ])}<section class="source-note">${icon('info')}<span><strong>History-safe change</strong>This updates the employee's current organization master only. Earlier payroll records and organization history are not rewritten.</span></section>`;
    drawer.classList.add('is-open'); drawerScrim.classList.add('is-open'); drawer.setAttribute('aria-hidden','false');
  }

  function openEmployeeEditDrawer(employeeId) {
    const employee = state.employees.find(item => item.id === employeeId);
    if (!employee) return;
    state.drawerType = 'internal-employee-edit';
    state.drawerContext = { employeeId };
    drawerTitle.textContent = 'Edit employee';
    drawerSave.hidden = false;
    drawerSave.textContent = 'Save Changes';
    drawerBody.innerHTML = formSections([
      ['Employee master', 'Edit identity/contact data here. Employment status is controlled from Employment; Archive and Delete are separate Actions-menu commands.', [
        namedField('Employee ID','employee-id',employee.employeeNumber || employee.employeeId || ''),
        namedField('Full name','employee-name',employee.name || ''),
        namedField('Joining date','employee-joining',employee.joining || '','date'),
        namedField('National ID / Iqama','employee-national-id',employee.nationalId || ''),
        namedField('Phone','employee-phone',employee.phone || ''),
        namedField('Address','employee-address',employee.address || '')
      ]]
    ]) + `<section class="source-note">${icon('info')}<span><strong>Employment lifecycle is protected.</strong>Use Employment for leave, reactivation, deactivation and termination. Use the separate Actions menu for Archive and Delete; deleted masters remain recoverable for 30 days.</span></section>`;
    drawer.classList.add('is-open'); drawerScrim.classList.add('is-open'); drawer.setAttribute('aria-hidden','false');
  }

  function openEmployeeLifecycleDrawer(employeeId) {
    const employee = state.employees.find(item => item.id === employeeId);
    if (!employee) return;
    const actions = employeeLifecycleActions(employee);
    if (!actions.length) {
      showToast('No employment-state action available', 'Use the Actions menu for Archive, Restore or Delete.');
      return;
    }
    state.drawerType = 'employee-lifecycle';
    state.drawerContext = { employeeId };
    drawerTitle.textContent = `${employee.name} · Employment`;
    drawerSave.hidden = false;
    drawerSave.disabled = false;
    drawerSave.textContent = 'Apply Action';
    drawerSave.classList.remove('is-lifecycle-danger');
    const statusCopy = `${employee.status}${employee.employmentEnd ? ` · ended ${employee.employmentEnd}` : ''}`;
    drawerBody.innerHTML = lifecycleDrawerIntro('Employment lifecycle','Use employment states to stop work cleanly without erasing attendance, payroll, payment or document history.') + `<section class="employee-lifecycle-summary"><span class="eyebrow">Employment lifecycle</span><h3>${escapeHtml(employee.name)}</h3><p>EMP ${escapeHtml(employee.employeeId)} · <strong>${escapeHtml(statusCopy)}</strong></p></section>${formSections([
      ['Lifecycle action','Employment changes are audited and historical payroll remains immutable.',[
        namedSelectOptions('Action','employee-lifecycle-action',actions,actions[0]?.value || ''),
        namedField('Employment end date (termination only)','employee-lifecycle-effective',rentalTodayIso(),'date'),
        namedTextareaField('Reason / notes','employee-lifecycle-reason','')
      ]]
    ])}<section class="source-note">${icon('info')}<span><strong>Archive and Delete are separate.</strong>Use this Employment drawer only for employment-state changes. Archive and Delete live in the profile Actions menu.</span></section>`;
    drawer.classList.add('is-open');
    drawerScrim.classList.add('is-open');
    drawer.setAttribute('aria-hidden','false');
  }

  function openEmployeeRecordLifecycleDrawer(employeeId, action) {
    const employee = state.employees.find(item => item.id === employeeId);
    if (!employee) return;
    state.drawerType = 'employee-record-lifecycle';
    state.drawerContext = { employeeId, action };
    drawerSave.hidden = false;
    drawerSave.disabled = false;
    drawerSave.classList.toggle('is-lifecycle-danger', action === 'delete');
    if (action === 'archive') {
      drawerTitle.textContent = 'Archive employee';
      drawerSave.textContent = 'Archive Employee';
      drawerBody.innerHTML = lifecycleDrawerIntro('Archive keeps the employee permanently available in history','The employee is removed from current registers, but payroll, attendance, payment, document and organization history remains intact.') + formSections([['Archive employee','Archive removes the employee from current operations while retaining payroll, attendance, payment and organization history. A reason is required.',[namedTextareaField('Archive reason','employee-record-reason','')]]]);
    } else if (action === 'restore') {
      drawerTitle.textContent = 'Restore employee from archive';
      drawerSave.textContent = 'Restore Employee';
      drawerBody.innerHTML = lifecycleDrawerIntro('Restore from Archive','The employee returns as an inactive/current master. Historical records are unchanged.') + formSections([['Restore employee','Add an optional audit note.',[namedTextareaField('Restore note','employee-record-reason','')]]]);
    } else if (action === 'delete') {
      drawerTitle.textContent = 'Delete employee';
      drawerSave.textContent = 'Delete';
      drawerBody.innerHTML = lifecycleDrawerIntro('Delete with 30-day recovery','This does not erase payroll or other protected history. The employee master is recoverable from the Delete page for 30 days. Active employment does not block this recoverable delete; payroll and organization history remain protected.',true) + formSections([['Delete employee',`Type employee ID ${employee.employeeId} to confirm and provide a reason.`,[namedField(`Type ${employee.employeeId} to confirm`,'employee-record-confirmation',''),namedTextareaField('Deletion reason','employee-record-reason','')]]]);
    } else return;
    drawer.classList.add('is-open');
    drawerScrim.classList.add('is-open');
    drawer.setAttribute('aria-hidden','false');
  }

  function openSupplierEditDrawer(supplierId) {
    const supplier = state.suppliers.find(item => item.id === supplierId);
    if (!supplier) return;
    state.drawerType = 'supplier-edit';
    state.drawerContext = { supplierId };
    drawerTitle.textContent = `${supplier.name} · Edit supplier`;
    drawerSave.hidden = false;
    drawerSave.disabled = false;
    drawerSave.textContent = 'Save Supplier';
    drawerBody.innerHTML = formSections([
      ['Supplier master', 'Update the managed supplier record. Existing worker and financial history remains linked to the same supplier ID.', [
        namedField('Company name', 'supplier-name', supplier.name || ''),
        namedField('Supplier code', 'supplier-code', supplier.code || ''),
        namedField('Contact person', 'supplier-contact', supplier.contact || ''),
        namedField('Phone', 'supplier-phone', supplier.phone || ''),
        namedField('Email', 'supplier-email', supplier.email || '', 'email')
      ]],
      ['Commercial & payment', 'Keep verified supplier commercial details current without rewriting historical settlements.', [
        namedField('CR', 'supplier-cr', supplier.cr || ''),
        namedField('VAT number', 'supplier-vat', supplier.vat || ''),
        namedField('Payment terms', 'supplier-payment-terms', supplier.paymentTerms || ''),
        namedField('Address', 'supplier-address', supplier.address || ''),
        namedTextareaFieldValue('Notes', 'supplier-notes', supplier.notes || '', 'Optional supplier notes')
      ]]
    ]);
    drawer.classList.add('is-open');
    drawerScrim.classList.add('is-open');
    drawer.setAttribute('aria-hidden', 'false');
  }

  function openProjectEditDrawer(projectId) {
    const project = state.projects.find(item => item.id === projectId);
    if (!project) return;
    state.drawerType = 'project-edit';
    state.drawerContext = { projectId };
    drawerTitle.textContent = `${project.name} · Edit project`;
    drawerSave.hidden = false;
    drawerSave.disabled = false;
    drawerSave.textContent = 'Save Project';
    drawerBody.innerHTML = formSections([['Project master', 'Update project master data without replacing the project identity used by assignments and financial history.', [
      namedField('Project name', 'project-name', project.name || ''),
      namedField('Project code', 'project-code', project.code || ''),
      namedField('Client / principal', 'project-client', project.client || ''),
      namedField('Location / site', 'project-location', project.location || ''),
      namedField('Start date', 'project-start', project.startDate || '', 'date'),
      namedField('Expected / actual end', 'project-end', project.endDate || '', 'date'),
      namedField('Project manager', 'project-manager', project.manager || ''),
      namedSelectFieldValue('Status', 'project-status', ['Active','On Hold','Completed'], project.status || 'Active'),
      namedTextareaFieldValue('Notes', 'project-notes', project.notes || '', 'Optional project notes')
    ]]]);
    drawer.classList.add('is-open');
    drawerScrim.classList.add('is-open');
    drawer.setAttribute('aria-hidden', 'false');
  }

  function openProjectLifecycleDrawer(projectId, action) {
    const project = state.projects.find(item => item.id === projectId);
    if (!project) return;
    state.drawerType='project-lifecycle';
    state.drawerContext={projectId,action};
    drawerSave.hidden=false;
    drawerSave.disabled=false;
    drawerSave.classList.toggle('is-lifecycle-danger', action === 'delete');
    if (action === 'archive') {
      drawerTitle.textContent='Archive project';
      drawerSave.textContent='Archive Project';
      drawerBody.innerHTML=lifecycleDrawerIntro('Archive preserves project history','Archive immediately suspends project operations. Inventory, rental assignments, timesheets, settlements and audit history remain intact and return with the project on restore.')+formSections([['Archive project','A reason is required for the audit trail.',[namedTextareaField('Archive reason','project-lifecycle-reason','')]]]);
    } else if (action === 'restore') {
      drawerTitle.textContent='Restore project from archive';
      drawerSave.textContent='Restore Project';
      drawerBody.innerHTML=lifecycleDrawerIntro('Restore from Archive','The retained project master becomes available again without rewriting historical project records.')+formSections([['Restore project','Add an optional audit note.',[namedTextareaField('Restore note','project-lifecycle-reason','')]]]);
    } else if (action === 'delete') {
      drawerTitle.textContent='Delete project';
      drawerSave.textContent='Delete';
      drawerBody.innerHTML=lifecycleDrawerIntro('Delete with 30-day recovery','The project and its operational inventory/assignment scope are hidden together and recoverable for 30 days. Historical records remain protected and restore with the project.',true)+formSections([['Delete project',`Type project code ${project.code} to confirm and provide a reason.`,[namedField(`Type ${project.code} to confirm`,'project-lifecycle-confirmation',''),namedTextareaField('Deletion reason','project-lifecycle-reason','')]]]);
    } else return;
    drawer.classList.add('is-open');
    drawerScrim.classList.add('is-open');
    drawer.setAttribute('aria-hidden','false');
  }

  function openQuickDrawer(type, context = null) {
    document.querySelectorAll('[data-dropdown].is-open').forEach(d => d.classList.remove('is-open'));
    if (type === 'rental-worker' && !context?.resumeInline) state.inlineRentalDraft = null;
    if (type === 'internal-employee' && !context?.resumeInline) state.inlineInternalDraft = null;
    state.drawerType = type;
    state.drawerContext = context;
    const spec = drawerTemplates[type] || drawerTemplates.project;
    drawerTitle.textContent = spec.title;
    drawerSave.hidden = false;
    drawerSave.disabled = false;
    drawerSave.textContent = spec.saveLabel || 'Save draft';
    drawerBody.innerHTML = spec.html();
    applyPayrollRequiredFields(drawerBody, type);
    drawer.classList.add('is-open');
    drawerScrim.classList.add('is-open');
    drawer.setAttribute('aria-hidden', 'false');
    drawerBody.querySelectorAll('[data-inline-create]').forEach(btn => btn.addEventListener('click', () => {
      if (state.drawerType !== 'rental-worker') return;
      const values={}; drawerBody.querySelectorAll('[name]').forEach(input => { values[input.name]=input.value; });
      state.inlineRentalDraft=values;
      openQuickDrawer(btn.dataset.inlineCreate,{returnTo:'rental-worker',selectTarget:btn.dataset.inlineCreate,resumeInline:true});
    }));
    drawerBody.querySelectorAll('[data-inline-internal-create]').forEach(btn => btn.addEventListener('click', () => {
      if (state.drawerType !== 'internal-employee') return;
      const values={}; drawerBody.querySelectorAll('[name]').forEach(input => { values[input.name]=input.value; });
      state.inlineInternalDraft=values;
      openQuickDrawer(btn.dataset.inlineInternalCreate,{returnTo:'internal-employee',selectTarget:btn.dataset.inlineInternalCreate,resumeInline:true});
    }));
    if (type === 'advance') setupAdjustmentDrawer();
  }

  function closeDrawer() {
    drawer.classList.remove('is-open');
    drawerScrim.classList.remove('is-open');
    drawer.setAttribute('aria-hidden', 'true');
    state.drawerType = null;
    state.drawerContext = null;
    drawerSave.hidden = false;
    drawerSave.disabled = false;
    drawerSave.classList.remove('is-lifecycle-danger');
  }

  async function saveDrawer() {
    const approvalDrawer = ['payroll-review-decision','attendance-return'].includes(state.drawerType);
    const paymentDrawer = ['supplier-payment','supplier-payment-result'].includes(state.drawerType);
    if (approvalDrawer && !roleCanApprove()) { showToast('Approval permission required', `${roleDefinition().label} cannot make final review decisions.`); return; }
    if (paymentDrawer && !roleCanPay()) { showToast('Payment permission required', `${roleDefinition().label} cannot post or reconcile payments.`); return; }
    if (!approvalDrawer && !paymentDrawer && !roleCanEdit(state.workspace)) { showToast('Read-only workspace access', `${roleDefinition().label} can view this workspace but cannot change operational records.`); return; }
    if (!validatePayrollRequiredFields()) return;
    if (!['project','project-edit','supplier','supplier-edit','branch','branch-edit','department','department-edit','employee-organization','internal-employee','internal-employee-edit','employee-lifecycle','employee-record-lifecycle','project-lifecycle','organization-lifecycle','rental-master-lifecycle','configuration-lifecycle','rental-worker','rental-assignment-action','salary-component','salary-structure','overtime-policy','attendance-import','attendance-return','payroll-review-decision','payroll-policy','supplier-payment','supplier-payment-result','advance','document-generate','bank-template','employee-payment-profile','salary-payment-settings'].includes(state.drawerType)) {
      const type = state.drawerType;
      closeDrawer();
      showToast('Action unavailable', 'This function is not enabled in the current backend module.');
      return;
    }

    const get = name => drawerBody.querySelector(`[name="${name}"]`)?.value.trim() || '';

    if (state.drawerType === 'attendance-import') {
      const text = get('attendance-import-text');
      if (!text) { drawerBody.querySelector('[name="attendance-import-text"]')?.focus(); showToast('Attendance data required', 'Paste attendance rows before importing.'); return; }
      let rows;
      try { rows = parseAttendanceImportText(text); }
      catch (error) { showToast('Import format error', error.message); return; }
      drawerSave.disabled = true;
      try {
        const payload = await appApi('/api/internal/attendance/import/', {
          method:'POST',
          body:{ period:periodKeyFromLabel(), rows, dry_run:false }
        });
        applyAttendancePayload(payload, state.period);
        const imported = payload.import || {};
        closeDrawer();
        renderRoute();
        showToast('Attendance imported', `${Number(imported.employee_count || 0)} employee row${Number(imported.employee_count || 0) === 1 ? '' : 's'} · ${Number(imported.entry_count || 0)} attendance entr${Number(imported.entry_count || 0) === 1 ? 'y' : 'ies'} saved.`);
      } catch (error) {
        drawerSave.disabled = false;
        showToast('Import rejected', error.message);
      }
      return;
    }

    if (state.drawerType === 'attendance-return') {
      const reason = get('attendance-return-reason');
      if (!reason) { drawerBody.querySelector('[name="attendance-return-reason"]')?.focus(); showToast('Return reason required', 'Explain what must be corrected before the attendance period is reopened.'); return; }
      drawerSave.disabled = true;
      try {
        await runAttendanceWorkflow('return_to_draft', { reason });
        closeDrawer();
        renderRoute();
        showToast('Attendance returned to Draft', `${state.period} is editable again. The return reason was recorded in the audit trail.`);
      } catch (error) {
        drawerSave.disabled = false;
        showToast('Return blocked', error.message);
      }
      return;
    }

    if (state.drawerType === 'bank-template') {
      const code=get('bank-template-code');
      const name=get('bank-template-name');
      const rawColumns=get('bank-template-columns');
      const columns=rawColumns.split(',').map(item=>item.trim()).filter(Boolean);
      const headers=get('bank-template-headers').split(/\r?\n/).map(item=>item.trim()).filter(Boolean);
      const resultColumns={
        employee:get('bank-result-employee'), status:get('bank-result-status'),
        reference:get('bank-result-reference'), reason:get('bank-result-reason')
      };
      Object.keys(resultColumns).forEach(key=>{if(!resultColumns[key])delete resultColumns[key];});
      const invalid=columns.filter(key=>!bankColumnCatalog[key]);
      if(!code){drawerBody.querySelector('[name="bank-template-code"]')?.focus();showToast('Template code required','Use a short stable code for this export definition.');return;}
      if(!name){drawerBody.querySelector('[name="bank-template-name"]')?.focus();showToast('Template name required','Give this salary export mapping a clear name.');return;}
      if(!columns.length||invalid.length){drawerBody.querySelector('[name="bank-template-columns"]')?.focus();showToast('Check template columns',invalid.length?`Unknown keys: ${invalid.join(', ')}`:'Add at least one export column.');return;}
      if(!columns.includes('net_salary')){drawerBody.querySelector('[name="bank-template-columns"]')?.focus();showToast('Required column missing','Every salary export template must contain net_salary.');return;}
      if(headers.length!==columns.length){drawerBody.querySelector('[name="bank-template-headers"]')?.focus();showToast('Header count does not match',`Add exactly ${columns.length} header label${columns.length===1?'':'s'}, one per line.`);return;}
      if(Object.keys(resultColumns).length && (!resultColumns.employee||!resultColumns.status)){showToast('Result mapping incomplete','When result headers are configured, Employee ID and Status headers are required.');return;}
      const payload={
        code, name,
        channel:get('bank-template-channel')==='WPS'?'wps':'bank_csv',
        delimiter:get('bank-template-delimiter')==='Tab'?'tab':get('bank-template-delimiter')==='Semicolon'?'semicolon':'comma',
        encoding:get('bank-template-encoding')==='UTF-8 with BOM'?'utf-8-sig':'utf-8',
        include_header:get('bank-template-header')!=='No',
        is_active:get('bank-template-status')!=='Inactive',
        columns, headers, result_columns:resultColumns
      };
      const existingId=state.drawerContext;
      drawerSave.disabled=true;
      try {
        const response=await appApi(existingId?`/api/internal/salary-payments/templates/${encodeURIComponent(existingId)}/`:'/api/internal/salary-payments/templates/', {method:existingId?'PATCH':'POST',body:payload});
        const item=response.template;
        state.exportTemplateDetailId=item.id;
        await loadSalaryPayments(state.period,{force:true});
        if(item.channel==='wps'){state.wpsTemplateId=item.id;localStorage.setItem('payroll-ui-wps-template-id',item.id);}else{state.bankTemplateId=item.id;localStorage.setItem('payroll-ui-bank-template-id',item.id);}
        closeDrawer();state.bankExportView='templates';renderRoute();showToast(existingId?'Export template updated':'Export template created',`${item.name} is available for future salary payment batches.`);
      } catch(error){drawerSave.disabled=false;showToast('Template could not be saved',error.message);}
      return;
    }

    if (state.drawerType === 'employee-payment-profile') {
      const employeeId=(state.drawerContext||{}).employeeId;
      const payload={
        destination_type:get('payment-profile-destination')==='Salary card'?'salary_card':'iban',
        account_holder_name:get('payment-profile-holder'),
        bank_name:get('payment-profile-bank-name'),
        bank_code:get('payment-profile-bank-code'),
        wps_enabled:get('payment-profile-wps')==='Yes',
        is_active:get('payment-profile-active')!=='Inactive',
        mark_verified:get('payment-profile-verified')==='Yes'
      };
      const iban=get('payment-profile-iban'); const card=get('payment-profile-card');
      if(iban)payload.iban=iban; if(card)payload.salary_card_number=card;
      drawerSave.disabled=true;
      try {
        await appApi(`/api/internal/salary-payments/profiles/${encodeURIComponent(employeeId)}/`,{method:'PATCH',body:payload});
        await loadSalaryPayments(state.period,{force:true});
        closeDrawer();renderRoute();showToast('Payment profile saved','Future salary payment batches will use the updated encrypted destination.');
      } catch(error){drawerSave.disabled=false;showToast('Payment profile could not be saved',error.message);}
      return;
    }

    if (state.drawerType === 'salary-payment-settings') {
      const payload={
        employer_identifier:get('payment-settings-employer-id'),
        employer_bank_name:get('payment-settings-bank-name'),
        employer_bank_code:get('payment-settings-bank-code'),
        bank_customer_reference:get('payment-settings-customer-reference')
      };
      const iban=get('payment-settings-iban'); if(iban)payload.employer_iban=iban;
      drawerSave.disabled=true;
      try {
        await appApi('/api/internal/salary-payments/settings/',{method:'PATCH',body:payload});
        await loadSalaryPayments(state.period,{force:true});
        closeDrawer();renderRoute();showToast('Payment settings saved','Company salary payment configuration has been updated.');
      } catch(error){drawerSave.disabled=false;showToast('Payment settings could not be saved',error.message);}
      return;
    }

    if (state.drawerType === 'document-generate') {
      generateDocumentFromDrawer(get);
      return;
    }

    if (state.drawerType === 'advance') {
      const workforce = get('adjustment-workforce') || 'Internal Employee';
      const personId = get('adjustment-person');
      const type = adjustmentNormalizeType(get('adjustment-type'));
      const amount = Number(get('adjustment-amount') || 0);
      const date = get('adjustment-date') || rentalTodayIso();
      const period = get('adjustment-period') || state.period;
      const status = get('adjustment-status') || 'Draft';
      const projectId = get('adjustment-project') || null;
      const project = projectId ? state.projects.find(item=>item.id===projectId) : null;
      const reference = get('adjustment-reference');
      const reason = get('adjustment-reason');
      const recoveryPlan = get('adjustment-recovery-plan') || 'No automatic schedule';
      const installmentAmount = Number(get('adjustment-installment') || 0);
      const recoveryStart = get('adjustment-recovery-start');
      if (!personId) { showToast('Person required','Select an employee or rental worker from the managed master.'); return; }
      if (!(amount > 0)) { markPayrollFieldInvalid('adjustment-amount', 'Enter an amount greater than zero'); showToast('Amount required','Enter an amount greater than zero.'); return; }
      if (!date) { showToast('Effective date required','Choose the transaction effective date.'); return; }
      if (workforce === 'Internal Employee') {
        const employee=state.employees.find(item=>item.id===personId); if(!employee){showToast('Employee not found','Choose a valid internal employee.');return;}
        drawerSave.disabled = true;
        try {
          const payload = await appApi('/api/internal/adjustments/', {
            method:'POST',
            body:{
              employee_id:personId,
              transaction_date:date,
              period:periodKeyFromLabel(period),
              adjustment_type:internalAdjustmentTypeCode(type),
              amount,
              reason:reason || type,
              reference,
              recovery_plan:recoveryPlan === 'No automatic schedule' ? '' : recoveryPlan,
              installment_amount:installmentAmount > 0 ? installmentAmount : null,
              recovery_start:recoveryStart || null
            }
          });
          applyPayrollPayload(payload, period);
          closeDrawer();
          if (currentRoute()==='adjustments') renderRoute();
          else if (currentRoute()==='internal-employees') { state.employeeTab='adjustments'; renderRoute(); }
          showToast('Transaction saved', `${type} · ${formatCurrency(amount)} · Draft. Submit and approval are separate audited actions.`);
        } catch (error) {
          showToast('Transaction could not be saved', error.message);
          drawerSave.disabled = false;
        }
        return;
      }
      const worker=rentalWorkerById(personId); if(!worker){showToast('Worker not found','Choose a valid rental worker.');return;}
      if (!projectId || !project) { drawerBody.querySelector('[name="adjustment-project"]')?.focus(); showToast('Project required','Rental adjustments must be attributed to a managed project.'); return; }
      drawerSave.disabled = true;
      try {
        const payload = await appApi('/api/rental/adjustments/', {
          method:'POST',
          body:{
            worker_id:personId,
            project_id:projectId,
            transaction_date:date,
            period:periodKeyFromLabel(period),
            adjustment_type:rentalAdjustmentTypeCode(type),
            amount,
            reason:reason || type,
            reference
          }
        });
        applyRentalSettlementPayload(payload);
        closeDrawer();
        if (currentRoute()==='adjustments') renderRoute();
        else { state.rentalWorkerTab='advances'; renderRoute(); }
        showToast('Transaction saved', `${type} · ${formatCurrency(amount)} · Draft. Submit and approval are separate audited actions.`);
      } catch (error) {
        showToast('Transaction could not be saved', error.message);
        drawerSave.disabled = false;
      }
      return;
    }

    if (state.drawerType === 'rental-assignment-action') {
      const context = state.drawerContext || {};
      const worker = rentalWorkerById(context.workerId);
      const action = context.action;
      if (!worker) { closeDrawer(); return; }
      const snapshot = rentalWorkerCurrentSnapshot(worker);
      const effective = get('rental-action-date');
      const reason = get('rental-action-reason');

      if (action === 'edit') {
        const name = get('rental-action-name');
        if (!name) { drawerBody.querySelector('[name="rental-action-name"]')?.focus(); showToast('Worker name required','Enter the permanent worker name.'); return; }
        try {
          drawerSave.disabled = true;
          const payload = await appApi(`/api/rental/workers/${encodeURIComponent(worker.id)}/`, {
            method:'PATCH', body:{
              worker_number:get('rental-action-worker-code'), full_name:name,
              national_id:get('rental-action-national-id'), phone:get('rental-action-phone'),
              supplier_id:worker.supplierId, status:worker.masterStatusValue || (worker.masterStatus === 'Inactive' ? 'inactive' : worker.masterStatus === 'Terminated' ? 'terminated' : 'active'),
              notes:get('rental-action-notes')
            }
          });
          replaceStateRecord(state.rentalWorkers,payload.worker);
          closeDrawer(); renderRoute();
          showToast('Worker updated', `${payload.worker.name}'s permanent master details were saved.`);
        } catch(error) { showToast('Worker not updated', error.message); }
        finally { drawerSave.disabled = false; }
        return;
      }

      if (action === 'advance') {
        const amount = Number(get('rental-action-amount') || 0);
        const projectId = get('rental-action-project');
        const project = state.projects.find(item => item.id === projectId);
        const txDate = effective || rentalTodayIso();
        if (!(amount > 0)) { markPayrollFieldInvalid('rental-action-amount', 'Enter an amount greater than zero'); showToast('Advance amount required','Enter an amount greater than zero.'); return; }
        if (!project) { drawerBody.querySelector('[name="rental-action-project"]')?.focus(); showToast('Project required','Worker Advance must be attributed to the effective project assignment.'); return; }
        drawerSave.disabled = true;
        try {
          const payload = await appApi('/api/rental/adjustments/', { method:'POST', body:{
            worker_id:worker.id, project_id:projectId, transaction_date:txDate,
            period:periodKeyFromLabel(state.period), adjustment_type:'advance',
            amount, reason:reason || 'Worker advance', reference:''
          }});
          applyRentalSettlementPayload(payload);
          closeDrawer(); state.rentalWorkerTab='advances'; renderRoute();
          showToast('Worker advance saved', `${formatCurrency(amount)} was recorded as a Draft settlement deduction for ${worker.name}.`);
        } catch (error) { drawerSave.disabled=false; showToast('Advance could not be saved', error.message); }
        return;
      }

      if (action !== 'cancel' && !effective) { drawerBody.querySelector('[name="rental-action-date"]')?.focus(); showToast('Effective date required','Choose the date this assignment change takes effect.'); return; }
      if (action === 'cancel' && !reason) { drawerBody.querySelector('[name="rental-action-reason"]')?.focus(); showToast('Cancellation reason required','Enter why the scheduled assignment change is being cancelled.'); return; }

      const requestBody = {
        action,
        worker_id:worker.id,
        effective_date:effective,
        reason
      };
      if (action === 'transfer' || action === 'assign') {
        const projectId = get('rental-action-project');
        const project = state.projects.find(item => item.id === projectId);
        if (!project) { showToast('Project required','Select an active managed project.'); return; }
        requestBody.project_id = projectId;
        requestBody.trade = get('rental-action-trade');
        requestBody.rate_type = get('rental-action-rate-type');
        requestBody.rate = get('rental-action-rate');
      } else if (action === 'trade') {
        requestBody.trade = get('rental-action-trade');
        requestBody.rate_type = get('rental-action-rate-type') || null;
        requestBody.rate = get('rental-action-rate') === '' ? null : get('rental-action-rate');
      } else if (action === 'rate') {
        requestBody.rate_type = get('rental-action-rate-type');
        requestBody.rate = get('rental-action-rate');
      } else if (action === 'release') {
        requestBody.disposition = get('rental-action-disposition') || 'Available';
        requestBody.note = get('rental-action-note');
      } else if (action === 'cancel') {
        delete requestBody.effective_date;
      } else {
        closeDrawer();
        return;
      }

      try {
        drawerSave.disabled = true;
        const payload = await appApi('/api/rental/assignments/', { method:'POST', body:requestBody });
        applyRentalAssignmentPayload(payload);
        const updated = payload.worker || worker;
        closeDrawer();
        state.rentalWorkerTab = 'assignments';
        renderRoute();
        const messages = {
          assign:`${updated.name} was assigned from ${rentalDisplayDate(effective)}.`,
          transfer:`${updated.name}'s project transfer is effective ${rentalDisplayDate(effective)} and prior history remains preserved.`,
          trade:`${updated.name}'s trade change is effective ${rentalDisplayDate(effective)}.`,
          rate:`${updated.name}'s rate revision is effective ${rentalDisplayDate(effective)}.`,
          release:`${updated.name}'s release was recorded through ${rentalDisplayDate(effective)}.`,
          cancel:`${updated.name}'s latest scheduled assignment change was cancelled and retained in audit history.`
        };
        showToast(action === 'assign' ? 'Worker assigned' : action === 'transfer' ? 'Worker transferred' : action === 'trade' ? 'Trade changed' : action === 'rate' ? 'Rate changed' : action === 'cancel' ? 'Scheduled change cancelled' : 'Worker released', messages[action]);
      } catch (error) {
        showToast('Assignment change failed', error.message);
        drawerSave.disabled = false;
      }
      return;
    }

    if (state.drawerType === 'supplier-payment') {
      const settlementId=get('supplier-payment-settlement');
      const payable=supplierPayables(state.period).find(item=>item.settlementId===settlementId);
      const amount=Number(get('supplier-payment-amount')||0), date=get('supplier-payment-date')||rentalTodayIso();
      const method=get('supplier-payment-method')||'Bank', status=get('supplier-payment-status')||'Processing';
      const reference=get('supplier-payment-reference'), note=get('supplier-payment-note');
      if(!payable){showToast('Settlement required','Select an approved rental settlement.');return;}
      if(!(amount>0)){markPayrollFieldInvalid('supplier-payment-amount','Enter an amount greater than zero');showToast('Amount required','Enter a supplier payment amount greater than zero.');return;}
      if(amount>payable.available+.005){drawerBody.querySelector('[name="supplier-payment-amount"]')?.focus();showToast('Amount exceeds available payable',`${formatCurrency(payable.available)} is currently unreserved on this settlement.`);return;}
      if(status==='Paid' && method!=='Cash' && !reference){drawerBody.querySelector('[name="supplier-payment-reference"]')?.focus();showToast('Reference required',`Record the ${method==='Cheque'?'cheque':'bank transaction'} reference before posting this payment as Paid.`);return;}
      drawerSave.disabled=true;
      try {
        const payload=await appApi('/api/rental/supplier-payments/',{method:'POST',body:{
          settlement_id:settlementId,payment_date:date,method:method.toLowerCase(),amount,
          status:status.toLowerCase(),transaction_reference:reference,note
        }});
        applyRentalSettlementPayload(payload);
        closeDrawer();state.paymentTab='supplier';renderRoute();
        showToast(status==='Paid'?'Supplier payment posted':'Supplier payment recorded',`${payable.supplier} · ${formatCurrency(amount)} · ${status}.`);
      } catch(error){drawerSave.disabled=false;showToast('Supplier payment could not be recorded',error.message);}
      return;
    }

    if (state.drawerType === 'supplier-payment-result') {
      const found=supplierPaymentById((state.drawerContext||{}).paymentId);if(!found){closeDrawer();return;}
      const payment=found.payment, status=get('supplier-payment-result-status')||payment.status, reference=get('supplier-payment-result-reference'), note=get('supplier-payment-result-note');
      if(status===payment.status){closeDrawer();return;}
      if(status==='Paid' && payment.method!=='Cash' && !reference){drawerBody.querySelector('[name="supplier-payment-result-reference"]')?.focus();showToast('Reference required','Record the bank/cheque reference before marking this payment Paid.');return;}
      if((status==='Failed'||status==='Reversed')&&!note){drawerBody.querySelector('[name="supplier-payment-result-note"]')?.focus();showToast(`${status} reason required`,'Add a clear reason so the audit trail explains the outcome.');return;}
      drawerSave.disabled=true;
      try {
        const payload=await appApi(`/api/rental/supplier-payments/${encodeURIComponent(payment.id)}/result/`,{method:'POST',body:{
          status:status.toLowerCase(),transaction_reference:reference,reason:note
        }});
        applyRentalSettlementPayload(payload);
        closeDrawer();state.paymentTab='supplier';renderRoute();
        showToast(`Supplier payment ${status.toLowerCase()}`,`${payment.ref} · ${formatCurrency(payment.amount)}.`);
      } catch(error){drawerSave.disabled=false;showToast('Payment result could not be saved',error.message);}
      return;
    }

    if (state.drawerType === 'payroll-policy') {
      const method = get('payroll-proration-method');
      drawerSave.disabled = true;
      try {
        await requestPayrollPolicy(method);
        closeDrawer();
        renderRoute();
        showToast('Payroll policy updated', 'The proration policy is now active for future payroll calculations.');
      } catch (error) {
        showToast('Payroll policy could not be updated', error.message);
        drawerSave.disabled = false;
      }
      return;
    }

    if (state.drawerType === 'payroll-review-decision') {
      const decision = state.drawerContext;
      const note = get('payroll-review-note');
      if (decision === 'approve') {
        const confirmed = !!drawerBody.querySelector('[name="payroll-review-confirm"]')?.checked;
        const counts = payrollReviewCounts(payrollReviewIssues(payrollRowsForDisplay()).issues);
        if (counts.Critical) { showToast('Approval blocked', `${counts.Critical} critical review issue${counts.Critical === 1 ? '' : 's'} remain.`); return; }
        if (!confirmed) { showToast('Reviewer confirmation required', 'Confirm that you reviewed the exceptions and calculation snapshot.'); return; }
        try {
          drawerSave.disabled = true;
          await requestPayrollWorkflow('approve', { note, confirmed:true });
          closeDrawer();
          state.payrollView = 'review';
          renderRoute();
          showToast('Payroll approved', `${state.period} payroll is Approved. Bank/WPS processing is the next controlled stage.`);
        } catch (error) {
          showToast('Payroll approval failed', error.message);
          drawerSave.disabled = false;
        }
        return;
      }
      if (!note) { drawerBody.querySelector('[name="payroll-review-note"]')?.focus(); showToast('Reviewer note required', 'Add a clear correction note before returning the payroll run.'); return; }
      const category = get('payroll-return-category') || 'Other';
      try {
        drawerSave.disabled = true;
        await requestPayrollWorkflow('return_for_changes', { note:`${category}: ${note}` });
        closeDrawer();
        state.payrollView = 'review';
        renderRoute();
        showToast('Payroll returned for changes', `${category}: the run is back in Calculated and must be recalculated after source changes.`);
      } catch (error) {
        showToast('Payroll could not be returned', error.message);
        drawerSave.disabled = false;
      }
      return;
    }

    if (state.drawerType === 'salary-component') {
      const name = get('salary-component-name');
      if (!name) {
        drawerBody.querySelector('[name="salary-component-name"]')?.focus();
        showToast('Component name required', 'Enter a name before saving this payroll component.');
        return;
      }
      const existing = state.salaryComponents.find(item => item.id === state.drawerContext) || null;
      try {
        const payload = await appApi(
          existing ? `/api/internal/salary/components/${existing.id}/` : '/api/internal/salary/components/',
          {
            method: existing ? 'PATCH' : 'POST',
            body: {
              code: get('salary-component-code'),
              name,
              category: get('salary-component-category') || 'Earning',
              recurrence: get('salary-component-recurrence') || 'Recurring',
              calculation: get('salary-component-calculation') || 'Fixed Amount',
              wps_mapping: get('salary-component-wps') || 'Not mapped',
              status: get('salary-component-status') || 'Active',
              notes: get('salary-component-notes')
            }
          }
        );
        replaceStateRecord(state.salaryComponents, payload.component);
        closeDrawer();
        showToast(existing ? 'Component updated' : 'Component created', `${payload.component.name} is available for salary configuration.`);
        if (currentRoute() !== 'salary-setup') navigate('salary-setup'); else renderRoute();
      } catch (error) {
        showToast('Salary component not saved', error.message);
      }
      return;
    }

    if (state.drawerType === 'overtime-policy') {
      const name = get('ot-policy-name');
      if (!name) {
        drawerBody.querySelector('[name="ot-policy-name"]')?.focus();
        showToast('Policy name required', 'Enter a clear overtime policy name before saving.');
        return;
      }
      const baseComponentId = get('ot-policy-base');
      if (!baseComponentId) {
        showToast('Base component required', 'Create or select an active recurring earning component first.');
        return;
      }
      const divisor = Number(get('ot-policy-divisor'));
      const multiplier = Number(get('ot-policy-multiplier'));
      if (!(divisor > 0) || !(multiplier > 0)) {
        markPayrollFieldInvalid(!(divisor > 0) ? 'ot-policy-divisor' : 'ot-policy-multiplier', 'Enter a value greater than zero');
        showToast('Check formula values', 'Divisor and multiplier must both be greater than zero.');
        return;
      }
      const existing = state.overtimePolicies.find(item => item.id === state.drawerContext) || null;
      try {
        const payload = await appApi(
          existing ? `/api/internal/salary/overtime-policies/${existing.id}/` : '/api/internal/salary/overtime-policies/',
          {
            method: existing ? 'PATCH' : 'POST',
            body: {
              code: get('ot-policy-code'),
              name,
              base_component_id: baseComponentId,
              divisor,
              multiplier,
              status: get('ot-policy-status') || 'Active',
              notes: get('ot-policy-notes')
            }
          }
        );
        replaceStateRecord(state.overtimePolicies, payload.policy);
        closeDrawer();
        state.salarySetupTab = 'overtime';
        showToast(existing ? 'Overtime policy updated' : 'Overtime policy created', `${payload.policy.name} has been saved.`);
        if (currentRoute() !== 'salary-setup') navigate('salary-setup'); else renderRoute();
      } catch (error) {
        showToast('Overtime policy not saved', error.message);
      }
      return;
    }

    if (state.drawerType === 'salary-structure') {
      const employeeId = get('salary-structure-employee');
      const employee = state.employees.find(item => item.id === employeeId);
      if (!employee) {
        showToast('Employee required', 'Select the employee who should receive this salary structure.');
        return;
      }
      const effective = get('salary-structure-effective');
      if (!effective) {
        drawerBody.querySelector('[name="salary-structure-effective"]')?.focus();
        showToast('Effective date required', 'Salary changes must have an effective date so historical salary configuration stays intact.');
        return;
      }
      const recurring = state.salaryComponents.filter(component => component.status === 'Active' && component.recurrence === 'Recurring');
      const components = recurring.map(component => {
        const amount = Number(drawerBody.querySelector(`[name="salary-amount-${component.id}"]`)?.value || 0);
        return { component_id: component.id, component, amount: Number.isFinite(amount) ? amount : 0 };
      }).filter(item => item.amount !== 0 || item.component.wpsMap === 'Basic Salary');
      const basic = components.find(item => item.component.wpsMap === 'Basic Salary');
      if (!basic || !(basic.amount > 0)) {
        if (basic?.component?.id) markPayrollFieldInvalid(`salary-amount-${basic.component.id}`, 'Enter a value greater than zero');
        showToast('Basic salary required', 'Configure one active recurring earning component as Basic Salary and enter a positive amount.');
        return;
      }
      try {
        const payload = await appApi('/api/internal/salary/structures/', {
          method: 'POST',
          body: {
            employee_id: employeeId,
            effective_from: effective,
            overtime_policy_id: get('salary-structure-ot-policy') || null,
            components: components.map(item => ({ component_id: item.component_id, amount: item.amount }))
          }
        });
        state.salaryStructureHistory[employeeId] = payload.history || [payload.structure];
        if (payload.current) state.salaryStructures[employeeId] = payload.current;
        else delete state.salaryStructures[employeeId];
        employee.basicSalary = salaryBasicForEmployee(employee);
        closeDrawer();
        showToast('Salary structure saved', `${employee.name} has a salary structure effective from ${effective}.`);
        if (currentRoute() === 'internal-employees') {
          state.employeeTab = 'salary';
          renderRoute();
        } else {
          state.salarySetupTab = 'structures';
          if (currentRoute() !== 'salary-setup') navigate('salary-setup'); else renderRoute();
        }
      } catch (error) {
        showToast('Salary structure not saved', error.message);
      }
      return;
    }

    if (state.drawerType === 'rental-worker') {
      const name = get('rental-worker-name');
      if (!name) {
        drawerBody.querySelector('[name="rental-worker-name"]')?.focus();
        showToast('Worker name required', 'Enter the rental worker name before creating the permanent worker master.');
        return;
      }
      const supplierId = get('rental-worker-supplier');
      const supplier = state.suppliers.find(item => item.id === supplierId && item.status === 'Active');
      if (!supplier) {
        showToast('Active manpower supplier required', 'Select an active supplier from the managed supplier master.');
        return;
      }
      try {
        drawerSave.disabled = true;
        const payload = await appApi('/api/rental/workers/', {
          method:'POST',
          body:{
            worker_number:get('rental-worker-code'),
            full_name:name,
            national_id:get('rental-worker-national-id'),
            phone:get('rental-worker-phone'),
            supplier_id:supplier.id,
            status:get('rental-worker-status') || 'Active',
            notes:get('rental-worker-notes')
          }
        });
        replaceStateRecord(state.rentalWorkers, payload.worker);
        state.inlineRentalDraft = null;
        refreshRentalMasterCounts();
        closeDrawer();
        showToast('Rental worker created', `${payload.worker.name} is linked to ${payload.worker.supplier} and is available for an effective-dated project assignment.`);
        navigate(`rental-workforce/${payload.worker.id}`);
      } catch (error) { showToast('Rental worker not created', error.message); }
      finally { drawerSave.disabled = false; }
      return;
    }

    if (state.drawerType === 'branch' || state.drawerType === 'branch-edit') {
      const name = get('branch-name');
      if (!name) { drawerBody.querySelector('[name="branch-name"]')?.focus(); showToast('Branch name required','Enter the branch or office name.'); return; }
      const editing = state.drawerType === 'branch-edit';
      const existing = editing ? state.branches.find(item=>item.id===state.drawerContext?.branchId) : null;
      if (editing && !existing) { closeDrawer(); return; }
      const returnContext=state.drawerContext?{...state.drawerContext}:null;
      try {
        drawerSave.disabled = true;
        const payload = await appApi(editing ? `/api/internal/branches/${existing.id}/` : '/api/internal/branches/', {
          method: editing ? 'PATCH' : 'POST',
          body: {
            name,
            code: editing ? (get('branch-code') || existing?.code || '') : get('branch-code'),
            location:get('branch-location'), address:get('branch-address'), manager:get('branch-manager'), kind:(get('branch-kind')||'Branch').toLowerCase(),
            status:get('branch-status') || 'Active'
          }
        });
        const branch = payload.branch;
        replaceStateRecord(state.branches, branch);
        state.employees.filter(employee=>employee.branchId===branch.id).forEach(employee=>{employee.branch=branch.name;});
        Object.values(state.employeeOrganizationHistory||{}).forEach(rows=>(rows||[]).forEach(row=>{if(row.branchId===branch.id)row.branch=branch.name;}));
        if (!editing && returnContext?.returnTo==='internal-employee') {
          state.inlineInternalDraft={...(state.inlineInternalDraft||{}),'employee-branch':branch.id};
          closeDrawer(); openQuickDrawer('internal-employee',{...(returnContext||{}),resumeInline:true});
          showToast('Branch created', `${branch.name} is selected for the employee being added.`); return;
        }
        closeDrawer();
        showToast(editing ? 'Branch updated' : 'Branch created', `${branch.name} is saved to the company organization master.`);
        if (editing) renderRoute(); else { state.branchTab='overview'; navigate(`branches/${branch.id}`); }
      } catch (error) { showToast('Branch not saved', error.message); }
      finally { drawerSave.disabled = false; }
      return;
    }

    if (state.drawerType === 'department' || state.drawerType === 'department-edit') {
      const name = get('department-name');
      if (!name) { drawerBody.querySelector('[name="department-name"]')?.focus(); showToast('Department name required','Enter the department name.'); return; }
      const editing = state.drawerType === 'department-edit';
      const existing = editing ? state.departments.find(item=>item.id===state.drawerContext?.departmentId) : null;
      if (editing && !existing) { closeDrawer(); return; }
      const returnContext=state.drawerContext?{...state.drawerContext}:null;
      try {
        drawerSave.disabled = true;
        const payload = await appApi(editing ? `/api/internal/departments/${existing.id}/` : '/api/internal/departments/', {
          method: editing ? 'PATCH' : 'POST',
          body: {
            name, code: editing ? (get('department-code') || existing?.code || '') : get('department-code'),
            status:get('department-status') || 'Active', notes:get('department-notes')
          }
        });
        const department = payload.department;
        replaceStateRecord(state.departments, department);
        state.employees.filter(employee=>employee.departmentId===department.id).forEach(employee=>{employee.department=department.name;});
        Object.values(state.employeeOrganizationHistory||{}).forEach(rows=>(rows||[]).forEach(row=>{if(row.departmentId===department.id)row.department=department.name;}));
        if (!editing && returnContext?.returnTo==='internal-employee') {
          state.inlineInternalDraft={...(state.inlineInternalDraft||{}),'employee-department':department.id};
          closeDrawer(); openQuickDrawer('internal-employee',{...(returnContext||{}),resumeInline:true,departmentId:department.id});
          showToast('Department created', `${department.name} is selected for the employee being added.`); return;
        }
        closeDrawer();
        showToast(editing ? 'Department updated' : 'Department created', `${department.name} is saved to the company organization master.`);
        if (editing) renderRoute(); else { state.departmentTab='overview'; navigate(`departments/${department.id}`); }
      } catch (error) { showToast('Department not saved', error.message); }
      finally { drawerSave.disabled = false; }
      return;
    }

    if (state.drawerType === 'configuration-lifecycle') {
      clearLifecycleDrawerError();
      const {kind,id,action,token}=state.drawerContext||{}; const reason=get('configuration-lifecycle-reason');
      if(action==='archive' && !reason){showToast('Archive reason required','Explain why this configuration record is being archived.');return;}
      let endpoint='', lifecycleEndpoint='';
      if(kind==='component'){endpoint=`/api/internal/salary/components/${id}/`;lifecycleEndpoint=`${endpoint}lifecycle/`;}
      else if(kind==='overtime'){endpoint=`/api/internal/salary/overtime-policies/${id}/`;lifecycleEndpoint=`${endpoint}lifecycle/`;}
      else if(kind==='template'){endpoint=`/api/internal/salary-payments/templates/${id}/`;lifecycleEndpoint=`${endpoint}lifecycle/`;}
      else if(kind==='payment-profile'){endpoint=`/api/internal/salary-payments/profiles/${id}/`;}
      if(!endpoint){closeDrawer();return;}
      try{
        drawerSave.disabled=true;
        if(action==='delete'){
          await appApi(endpoint,{method:'DELETE',body:{confirmation:get('configuration-lifecycle-confirmation'),reason}});
          if(kind==='component')state.salaryComponents=state.salaryComponents.filter(item=>item.id!==id);
          else if(kind==='overtime')state.overtimePolicies=state.overtimePolicies.filter(item=>item.id!==id);
          else if(kind==='template'){state.bankTemplates=state.bankTemplates.filter(item=>item.id!==id);await loadSalaryPayments(state.period,{force:true});}
          else if(kind==='payment-profile')await loadSalaryPayments(state.period,{force:true});
          closeDrawer();renderRoute();showToast('Unused configuration deleted','The record was permanently deleted because it had no protected history.');
        }else{
          const payload=await appApi(lifecycleEndpoint,{method:'POST',body:{action,reason}});
          if(kind==='component')replaceStateRecord(state.salaryComponents,payload.component);
          else if(kind==='overtime')replaceStateRecord(state.overtimePolicies,payload.policy);
          else if(kind==='template'){replaceStateRecord(state.bankTemplates,payload.template);await loadSalaryPayments(state.period,{force:true});}
          closeDrawer();renderRoute();showToast(action==='archive'?'Configuration archived':'Configuration restored',action==='archive'?'Historical records remain intact.':'The restored record remains inactive until explicitly activated.');
        }
      }catch(error){drawerSave.disabled=false;showLifecycleDrawerError(error);showToast('Lifecycle action blocked',error.message);}
      return;
    }

    if (state.drawerType === 'project-lifecycle') {
      clearLifecycleDrawerError();
      const {projectId,action}=state.drawerContext||{};
      const project=state.projects.find(item=>item.id===projectId);
      if(!project){closeDrawer();return;}
      const reason=get('project-lifecycle-reason');
      if (['archive','delete'].includes(action) && !reason) { showToast('Reason required','Enter a reason for the project lifecycle audit trail.'); return; }
      try {
        drawerSave.disabled=true;
        if(action==='delete'){
          const confirmation=get('project-lifecycle-confirmation');
          await appApi(`/api/rental/projects/${encodeURIComponent(project.id)}/`,{method:'DELETE',body:{confirmation,reason}});
          closeDrawer();reloadIntoRoute('trash');return;
        }
        const payload=await appApi(`/api/rental/projects/${encodeURIComponent(project.id)}/lifecycle/`,{method:'POST',body:{action:action==='restore'?'restore_archive':'archive',reason}});
        replaceStateRecord(state.projects,payload.project);
        closeDrawer();
        if(action==='archive'){reloadIntoRoute('archive');return;}
        location.reload();
        return;
      }catch(error){showLifecycleDrawerError(error);showToast('Project action not completed',error.message);}
      finally{drawerSave.disabled=false;}
      return;
    }

    if (state.drawerType === 'organization-lifecycle') {
      clearLifecycleDrawerError();
      const { kind, id, action } = state.drawerContext || {};
      const collection = kind === 'branch' ? state.branches : state.departments;
      const record = collection.find(item => item.id === id);
      if (!record) { closeDrawer(); return; }
      const reason = get('organization-lifecycle-reason');
      if (['archive','delete'].includes(action) && !reason) { showToast('Reason required','Explain why this organization master is being archived or deleted.'); return; }
      try {
        drawerSave.disabled = true;
        if (action === 'delete') {
          const confirmation = get('organization-lifecycle-confirmation');
          const endpoint = kind === 'branch' ? `/api/internal/branches/${id}/` : `/api/internal/departments/${id}/`;
          await appApi(endpoint, { method:'DELETE', body:{confirmation,reason} });
          closeDrawer();
          reloadIntoRoute('trash');
          return;
        } else {
          const endpoint = kind === 'branch' ? `/api/internal/branches/${id}/lifecycle/` : `/api/internal/departments/${id}/lifecycle/`;
          const payload = await appApi(endpoint, { method:'POST', body:{action:action==='restore'?'restore_archive':'archive',reason} });
          const updated = kind === 'branch' ? payload.branch : payload.department; replaceStateRecord(collection, updated);
          closeDrawer();
          if (action === 'archive') { reloadIntoRoute('archive'); return; }
          location.reload();
          return;
        }
      } catch (error) { showLifecycleDrawerError(error); showToast('Lifecycle action not completed', error.message); }
      finally { drawerSave.disabled = false; }
      return;
    }

    if (state.drawerType === 'rental-master-lifecycle') {
      clearLifecycleDrawerError();
      const {kind,id,action}=state.drawerContext||{}; const collection=kind==='supplier'?state.suppliers:state.rentalWorkers; const record=collection.find(item=>item.id===id); if(!record){closeDrawer();return;}
      const reason=get('rental-lifecycle-reason');
      let selectedAction=action==='manage'?get('rental-lifecycle-action'):action;
      if (['archive','deactivate','terminate','delete'].includes(selectedAction) && !reason) {showToast('Reason required','Enter a lifecycle reason for the audit trail.');return;}
      try {
        drawerSave.disabled=true;
        if (selectedAction==='delete') {
          const confirmation=get('rental-lifecycle-confirmation');
          const endpoint=kind==='supplier'?`/api/rental/suppliers/${id}/`:`/api/rental/workers/${id}/`;
          await appApi(endpoint,{method:'DELETE',body:{confirmation,reason}});
          closeDrawer();reloadIntoRoute('trash');return;
        }
        const endpoint=kind==='supplier'?`/api/rental/suppliers/${id}/lifecycle/`:`/api/rental/workers/${id}/lifecycle/`;
        const body={action:selectedAction==='restore'?'restore_archive':selectedAction,reason};
        if(kind==='worker' || kind==='supplier')body.effective_date=get('rental-lifecycle-effective');
        const payload=await appApi(endpoint,{method:'POST',body}); const updated=kind==='supplier'?payload.supplier:payload.worker;replaceStateRecord(collection,updated);closeDrawer();
        if (selectedAction==='archive') { reloadIntoRoute('archive'); return; }
        if (selectedAction==='restore' || selectedAction==='restore_archive') { location.reload(); return; }
        renderRoute();showToast('Status updated',`${updated.name} · ${updated.status||updated.masterStatus}`);
      } catch(error){showLifecycleDrawerError(error);showToast('Lifecycle action not completed',error.message);} finally{drawerSave.disabled=false;}
      return;
    }

    if (state.drawerType === 'employee-organization') {
      const employee=state.employees.find(item=>item.id===state.drawerContext?.employeeId); if(!employee){closeDrawer();return;}
      const branch=state.branches.find(item=>item.id===get('organization-branch'));
      const department=state.departments.find(item=>item.id===get('organization-department'));
      const position=get('organization-position')||employee.position;
      const effective=get('organization-effective'); const reason=get('organization-reason');
      if(!branch || branch.status!=='Active'){showToast('Active branch required','Choose an active Branch / Office record.');return;}
      if(!department || department.status!=='Active'){showToast('Active department required','Choose an active Department record.');return;}
      if(!effective){showToast('Effective date required','Choose when this organization change takes effect.');return;}
      try {
        drawerSave.disabled = true;
        const payload = await appApi(`/api/internal/employees/${employee.id}/organization/`, {
          method:'POST', body:{branch_id:branch.id,department_id:department.id,position,effective_from:effective,reason}
        });
        replaceStateRecord(state.employees, payload.employee);
        state.employeeOrganizationHistory[employee.id]=payload.history || [];
        closeDrawer(); renderRoute();
        showToast('Organization assignment updated', `${payload.employee.name} → ${payload.employee.branch} · ${payload.employee.department}. Previous assignment history is preserved.`);
      } catch (error) { showToast('Organization not changed', error.message); }
      finally { drawerSave.disabled = false; }
      return;
    }

    if (state.drawerType === 'internal-employee') {
      const name = get('employee-name');
      if (!name) { drawerBody.querySelector('[name="employee-name"]')?.focus(); showToast('Employee name required', 'Enter the employee name before creating the master record.'); return; }
      const branch=state.branches.find(item=>item.id===get('employee-branch'));
      const department=state.departments.find(item=>item.id===get('employee-department'));
      if (!branch || !department) { showToast('Organization required','Choose an active branch and department.'); return; }
      try {
        drawerSave.disabled = true;
        const payload = await appApi('/api/internal/employees/', {
          method:'POST', body:{
            employee_number:get('employee-id'),
            full_name:name, position:get('employee-position'), department_id:department.id, branch_id:branch.id,
            joining_date:get('employee-joining'), status:get('employee-status') || 'Active',
            national_id:get('employee-national-id'), phone:get('employee-phone'), address:get('employee-address')
          }
        });
        const employee=payload.employee;
        replaceStateRecord(state.employees, employee);
        state.employeeOrganizationHistory[employee.id]=payload.history || [];
        state.inlineInternalDraft=null; closeDrawer();
        showToast('Employee created', `${employee.name} is now in the internal employee master.`);
        navigate(`internal-employees/${employee.id}`);
      } catch (error) { showToast('Employee not created', error.message); }
      finally { drawerSave.disabled = false; }
      return;
    }

    if (state.drawerType === 'employee-lifecycle') {
      clearLifecycleDrawerError();
      const employee=state.employees.find(item=>item.id===state.drawerContext?.employeeId); if(!employee){closeDrawer();return;}
      const action=get('employee-lifecycle-action');
      const reason=get('employee-lifecycle-reason');
      const effective=get('employee-lifecycle-effective');
      if (!action) { showToast('Employment action required','Choose a lifecycle action.'); return; }
      if (['leave','deactivate','terminate'].includes(action) && !reason) { showToast('Reason required','Enter a reason so the lifecycle audit trail explains this change.'); return; }
      if (action === 'terminate' && !effective) { showToast('Employment end date required',"Choose the employee's final employment date."); return; }
      try {
        drawerSave.disabled = true;
        const payload=await appApi(`/api/internal/employees/${employee.id}/lifecycle/`, {method:'POST',body:{action,effective_date:effective,reason}});
        replaceStateRecord(state.employees,payload.employee);
        if (payload.history) state.employeeOrganizationHistory[employee.id]=payload.history;
        closeDrawer(); renderRoute();
        const labels={leave:'Employee placed on leave',activate:'Employee reactivated',deactivate:'Employee deactivated',terminate:'Employment terminated'};
        showToast(labels[action] || 'Employment updated',`${payload.employee.name} · ${payload.employee.status}`);
      } catch(error) { showLifecycleDrawerError(error); showToast('Employment action not completed',error.message); }
      finally { drawerSave.disabled = false; }
      return;
    }

    if (state.drawerType === 'employee-record-lifecycle') {
      clearLifecycleDrawerError();
      const employee=state.employees.find(item=>item.id===state.drawerContext?.employeeId); if(!employee){closeDrawer();return;}
      const action=state.drawerContext?.action;
      const reason=get('employee-record-reason');
      if (['archive','delete'].includes(action) && !reason) { showToast('Reason required','Enter a reason for the lifecycle audit trail.'); return; }
      try {
        drawerSave.disabled=true;
        if (action === 'delete') {
          const confirmation=get('employee-record-confirmation');
          if (confirmation.trim().toUpperCase() !== String(employee.employeeId || '').trim().toUpperCase()) { showToast('Employee ID confirmation required',`Type ${employee.employeeId} exactly before deleting this employee.`); return; }
          await appApi(`/api/internal/employees/${employee.id}/`, {method:'DELETE',body:{confirmation,reason}});
          closeDrawer(); reloadIntoRoute('trash'); return;
        }
        const lifecycleAction = action === 'restore' ? 'restore_archive' : 'archive';
        const payload=await appApi(`/api/internal/employees/${employee.id}/lifecycle/`, {method:'POST',body:{action:lifecycleAction,reason}});
        replaceStateRecord(state.employees,payload.employee);
        if (payload.history) state.employeeOrganizationHistory[employee.id]=payload.history;
        closeDrawer();
        if (action === 'archive') { reloadIntoRoute('archive'); return; }
        location.reload();
        return;
      } catch(error) { showLifecycleDrawerError(error); showToast('Record action not completed',error.message); }
      finally { drawerSave.disabled=false; }
      return;
    }

    if (state.drawerType === 'internal-employee-edit') {
      const employee=state.employees.find(item=>item.id===state.drawerContext?.employeeId); if(!employee){closeDrawer();return;}
      try {
        drawerSave.disabled = true;
        const payload=await appApi(`/api/internal/employees/${employee.id}/`, {method:'PATCH',body:{
          employee_number:get('employee-id'), full_name:get('employee-name'), joining_date:get('employee-joining'),
          national_id:get('employee-national-id'), phone:get('employee-phone'), address:get('employee-address')
        }});
        replaceStateRecord(state.employees,payload.employee); closeDrawer(); renderRoute();
        showToast('Employee updated', `${payload.employee.name}'s master details were saved.`);
      } catch(error) { showToast('Employee not updated', error.message); }
      finally { drawerSave.disabled = false; }
      return;
    }

    if (state.drawerType === 'supplier' || state.drawerType === 'supplier-edit') {
      const editing = state.drawerType === 'supplier-edit';
      const returnContext = state.drawerContext ? { ...state.drawerContext } : null;
      const current = editing ? state.suppliers.find(item => item.id === state.drawerContext?.supplierId) : null;
      if (editing && !current) { closeDrawer(); return; }
      const name = get('supplier-name');
      if (!name) {
        drawerBody.querySelector('[name="supplier-name"]')?.focus();
        showToast('Supplier name required', 'Enter the manpower supplier company name.');
        return;
      }
      try {
        drawerSave.disabled = true;
        const payload = await appApi(editing ? `/api/rental/suppliers/${current.id}/` : '/api/rental/suppliers/', {
          method: editing ? 'PATCH' : 'POST',
          body:{
            name,
            code:get('supplier-code'),
            status:editing ? (current.statusValue || (current.status === 'Inactive' ? 'inactive' : current.status === 'Terminated' ? 'terminated' : 'active')) : (get('supplier-status') || 'Active'),
            contact:get('supplier-contact'),
            phone:get('supplier-phone'),
            email:get('supplier-email'),
            cr:get('supplier-cr'),
            vat:get('supplier-vat'),
            payment_terms:get('supplier-payment-terms'),
            address:get('supplier-address'),
            notes:get('supplier-notes')
          }
        });
        const supplier=payload.supplier;
        replaceStateRecord(state.suppliers,supplier);
        state.rentalWorkers.filter(worker=>worker.supplierId===supplier.id).forEach(worker=>{worker.supplier=supplier.name;});
        closeDrawer();
        showToast(editing ? 'Supplier updated' : 'Supplier created', `${supplier.name} is saved to the managed manpower-supplier master.`);
        if (!editing && returnContext?.returnTo === 'rental-worker') {
          state.inlineRentalDraft={...(state.inlineRentalDraft||{}),'rental-worker-supplier':supplier.id};
          openQuickDrawer('rental-worker',{resumeInline:true});
        } else if (!editing && returnContext?.returnTo === 'rental-onboarding') {
          state.rentalOnboarding.defaultSupplierId=supplier.id;
          if(currentRoute()!=='rental-onboarding') navigate('rental-onboarding'); else renderRoute();
        } else if (editing) {
          renderRoute();
        } else {
          state.supplierTab='overview'; navigate(`suppliers/${supplier.id}`);
        }
      } catch(error) { showToast(editing ? 'Supplier not updated' : 'Supplier not created', error.message); }
      finally { drawerSave.disabled = false; }
      return;
    }

    if (state.drawerType === 'project' || state.drawerType === 'project-edit') {
      const editing = state.drawerType === 'project-edit';
      const projectReturnContext = state.drawerContext ? { ...state.drawerContext } : null;
      const current = editing ? state.projects.find(item => item.id === state.drawerContext?.projectId) : null;
      if (editing && !current) { closeDrawer(); return; }
      const name = get('project-name');
      const startDate = get('project-start');
      if (!name) {
        drawerBody.querySelector('[name="project-name"]')?.focus();
        showToast('Project name required', 'Enter the project name.');
        return;
      }
      if (!startDate) {
        drawerBody.querySelector('[name="project-start"]')?.focus();
        showToast('Project start date required', 'Enter the project start date.');
        return;
      }
      try {
        drawerSave.disabled = true;
        const payload = await appApi(editing ? `/api/rental/projects/${current.id}/` : '/api/rental/projects/', {
          method: editing ? 'PATCH' : 'POST',
          body:{
            name,
            code:get('project-code'),
            client:get('project-client'),
            location:get('project-location'),
            start_date:startDate,
            end_date:get('project-end') || null,
            manager:get('project-manager'),
            status:get('project-status') || 'Active',
            notes:get('project-notes')
          }
        });
        const project=payload.project;
        replaceStateRecord(state.projects,project);
        closeDrawer();
        showToast(editing ? 'Project updated' : 'Project created', `${project.name} is saved to the managed rental-project master.`);
        if (!editing && projectReturnContext?.returnTo === 'rental-worker') {
          showToast('Worker master first', 'The worker is created without a project. Use effective-dated assignments to link the worker to a project separately.');
          openQuickDrawer('rental-worker',{resumeInline:true});
        } else if (!editing && projectReturnContext?.returnTo === 'rental-onboarding') {
          if(currentRoute()!=='rental-onboarding') navigate('rental-onboarding'); else renderRoute();
        } else if (editing) {
          renderRoute();
        } else {
          state.projectTab='overview'; navigate(`projects/${project.id}`);
        }
      } catch(error) { showToast(editing ? 'Project not updated' : 'Project not created', error.message); }
      finally { drawerSave.disabled = false; }
      return;
    }
  }

  function initDrawer() {
    document.getElementById('drawerClose').addEventListener('click', closeDrawer);
    document.getElementById('drawerCancel').addEventListener('click', closeDrawer);
    drawerScrim.addEventListener('click', closeDrawer);
    drawerSave.addEventListener('click', saveDrawer);
    document.querySelectorAll('[data-quick-add]').forEach(btn => btn.addEventListener('click', () => openQuickDrawer(btn.dataset.quickAdd, btn.dataset.adjustmentPersonContext ? { workforce:btn.dataset.adjustmentWorkforceContext || (state.workspace==='rental'?'Rental Worker':'Internal Employee'), personId:btn.dataset.adjustmentPersonContext, type:btn.dataset.adjustmentTypeContext || 'Salary Advance' } : (btn.dataset.employeeBranchContext || btn.dataset.employeeDepartmentContext) ? { branchId:btn.dataset.employeeBranchContext || null, departmentId:btn.dataset.employeeDepartmentContext || null } : null)));
  }

  function permissionGuardAction(target) {
    if (!target) return null;
    if (target.matches('[data-settings-save]') && !roleCanSettings()) return 'settings';
    if (target.matches('[data-payment-start],[data-payment-start-batch],[data-payment-export],[data-payment-retry],[data-payment-close-payroll],[data-payment-close-batch],[data-supplier-payment-new],[data-pay-supplier-settlement],[data-supplier-payment-retry],[data-settlement-close]') && !roleCanPay()) return 'payment';
    if (target.matches('[data-review-approve],[data-review-return]') && !roleCanApprove()) return 'approval';
    if (target.matches('[data-adjustment-action="approve"]') && !roleCanApprove()) return 'approval';
    if (target.matches('[data-settlement-return]') && !roleCanApprove()) return 'approval';
    if (target.matches('[data-settlement-progress]')) {
      if (target.dataset.settlementProgress === 'Approved') return roleCanApprove() ? null : 'approval';
      if (!roleCanEdit('rental')) return 'edit';
      return null;
    }
    if (target.matches('[data-timesheet-workflow]')) {
      const next=timesheetNextAction(timesheetStatus()).next;
      if (['Approved','Locked'].includes(next) && !roleCanApprove()) return 'approval';
      if (next === 'Submitted' && !roleCanEdit('internal')) return 'edit';
    }
    if (target.matches('[data-rental-timesheet-workflow]')) {
      const next=rentalTimesheetNextAction(rentalTimesheetStatus()).next;
      if (['Approved','Locked'].includes(next) && !roleCanApprove()) return 'approval';
      if (next === 'Submitted' && !roleCanEdit('rental')) return 'edit';
    }
    const editSelector = [
      '[data-quick-add]','[data-edit-branch]','[data-edit-department]','[data-change-employee-organization]','[data-employee-lifecycle]',
      '[data-employee-record-action]','[data-organization-lifecycle]','[data-rental-master-lifecycle]','[data-project-lifecycle]','[data-record-bin-restore]',
      '[data-salary-component-add]','[data-salary-component-edit]','[data-salary-structure-new]','[data-salary-structure-edit]',
      '[data-overtime-policy-add]','[data-overtime-policy-edit]','[data-timesheet-bulk-action]','[data-timesheet-import]','[data-timesheet-save]',
      '[data-rental-timesheet-import]','[data-rental-timesheet-save]','[data-rental-ts-bulk]','[data-payroll-calculate]','[data-payroll-reopen]','[data-payroll-reset-run]','[data-payroll-submit-review]',
      '[data-bank-batch-prepare]','[data-bank-template-new]','[data-bank-template-edit]','[data-wps-prepare]','[data-wps-validate]','[data-payment-profile-edit]','[data-payment-settings]',
      '[data-rental-worker-action]','[data-onboarding-create-master]','[data-onboarding-import]','[data-onboarding-apply-defaults]','[data-settlement-progress]','[data-adjustment-action="submit"]','[data-document-generate]'
    ].join(',');
    if (target.matches(editSelector) && !roleCanEdit(state.workspace)) return 'edit';
    return null;
  }

  function initPermissionGuard() {
    document.body.dataset.accessRole = state.accessRole;
    document.addEventListener('click', event => {
      const target = event.target.closest('button,a');
      const reason = permissionGuardAction(target);
      if (!reason) return;
      event.preventDefault(); event.stopImmediatePropagation();
      const message = reason === 'approval' ? 'This role does not have final review/approval authority.' : reason === 'payment' ? 'This role does not have payment posting/reconciliation authority.' : reason === 'settings' ? 'Only a role with company-settings authority can change this section.' : 'This role has read-only access to the current operational workspace.';
      showToast('Action restricted', `${roleDefinition().label}: ${message}`);
    }, true);
    document.addEventListener('input', event => {
      const target = event.target;
      if (roleCanEdit(state.workspace)) return;
      if (target.matches?.('[data-attendance-input],[data-ot-hours],[data-rental-ts-input],[data-rental-ot-hours],[data-rental-ot-rate],[data-onboarding-field]')) {
        event.preventDefault();
        showToast('Read-only workspace access', `${roleDefinition().label} cannot edit operational values.`);
        renderRoute();
      }
    }, true);
  }

  function showToast(title, message) {
    if (message === 'Your sign-in session is no longer active. Sign in again to continue.') {
      title = 'Sign-in session expired';
    }
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.innerHTML = `<span class="toast__dot"></span><span><strong>${escapeHtml(title)}</strong><span>${escapeHtml(message)}</span></span>`;
    toastStack.appendChild(toast);
    setTimeout(() => toast.remove(), 3600);
  }

  document.addEventListener('fullscreenchange', () => {
    if (!document.fullscreenElement && state.timesheetFullscreen) {
      state.timesheetFullscreen = false;
      applyTimesheetFullscreenState();
      if (currentRoute() === 'timesheets') renderRoute();
    }
  });

  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && state.timesheetFullscreen && !document.fullscreenElement) {
      event.preventDefault();
      leaveTimesheetFullscreen({ exitBrowser:false, rerender:true });
    }
  });

  syncWorkspaceUrl(state.workspace);
  renderWorkspaceShell();
  initDropdowns();
  initWorkspaceSwitcher();
  initPeriod();
  initSidebar();
  initSearch();
  initDrawer();
  initPermissionGuard();
  document.documentElement.lang = 'en';
  window.addEventListener('hashchange', () => { state.projectTab = currentProjectId() ? state.projectTab : 'overview'; state.branchTab = currentBranchId() ? state.branchTab : 'overview'; state.departmentTab = currentDepartmentId() ? state.departmentTab : 'overview'; state.supplierTab = currentSupplierId() ? state.supplierTab : 'overview'; state.employeeTab = currentEmployeeId() ? state.employeeTab : 'overview'; state.rentalWorkerTab = currentRentalWorkerId() ? state.rentalWorkerTab : 'overview'; renderRoute(); });
  if (!location.hash) location.hash = '#/overview'; else renderRoute();
})();
