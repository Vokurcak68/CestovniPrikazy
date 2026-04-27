const STORAGE_KEY = "travelOrders.cz.autonomous.v1";

const STATUS_OPTIONS = [
  { value: "draft", label: "Rozpracováno" },
  { value: "submitted", label: "Ke schválení" },
  { value: "approved", label: "Schváleno" },
  { value: "settlement", label: "Vyúčtování" },
  { value: "closed", label: "Uzavřeno" },
  { value: "rejected", label: "Zamítnuto" },
];

const TRANSPORT_OPTIONS = {
  private_car: "Vlastní vozidlo",
  company_car: "Služební vozidlo",
  public_transport: "Veřejná doprava",
  other: "Jiné",
};

const FUEL_OPTIONS = {
  ba95: "Benzin 95",
  ba98: "Benzin 98",
  diesel: "Nafta",
  electricity: "Elektřina",
  other: "Jiné",
};

const FUEL_PRICE_MODE_OPTIONS = {
  decree: "Dle vyhlášky",
  receipt: "Dle dokladu",
};

const DOCUMENT_KIND_OPTIONS = {
  receipt: "Účtenka",
  invoice: "Faktura",
  ticket: "Jízdenka",
  other: "Jiný doklad",
};

const EXPENSE_KIND_OPTIONS = {
  fuel: "PHM / nabíjení",
  fare: "Jízdné",
  lodging: "Ubytování",
  parking: "Parkovné",
  meal: "Stravování",
  other: "Ostatní výdaj",
};

const DEFAULT_RATES = {
  validFrom: "2026-01-01",
  validTo: null,
  regulationNo: "573/2025 Sb.",
  sourceUrl: "https://ppropo.mpsv.cz/Vyhlaska_573_2025",
  sourceNote: "Sazby dle vyhlášky MPSV pro tuzemské cestovní náhrady.",
  checkedAt: null,
  basicKmRate: 5.9,
  mealBands: [
    { key: "5_12", label: "5 až 12 hodin", min: 5, max: 12, amount: 155, reductionPct: 70 },
    { key: "12_18", label: "nad 12 až 18 hodin", min: 12, max: 18, amount: 236, reductionPct: 35 },
    { key: "18_plus", label: "nad 18 hodin", min: 18, max: null, amount: 370, reductionPct: 25 },
  ],
  fuelPrices: {
    ba95: 34.7,
    ba98: 39,
    diesel: 34.1,
    electricity: 7.2,
  },
};

const TABS = [
  { id: "trip", label: "Cesta" },
  { id: "employee", label: "Zaměstnanec" },
  { id: "settlement", label: "Vyúčtování" },
  { id: "vehicle", label: "Vozidlo" },
  { id: "documents", label: "Doklady" },
  { id: "summary", label: "Souhrn" },
  { id: "rates", label: "Sazby" },
];

const API_ENABLED = location.protocol !== "file:";
const AUTH_TOKEN_KEY = "travelOrders.authToken";

let state = loadState();
let activeTab = "trip";
let currentUser = null;
let currentDefaults = null;
let defaultsLoaded = false;
let appStarted = false;
let appMode = "orders";
let adminState = {
  users: [],
  options: { roles: [], approvers: [] },
  selectedUserId: null,
  loaded: false,
  message: "",
};
let approvalState = {
  summary: { pending_count: 0, overdue_count: 0, pending_gross_amount: 0 },
  orders: [],
  detail: null,
  selectedApprovalId: null,
  notifications: { badge: { unread_count: 0, failed_count: 0 }, items: [] },
  loaded: false,
  message: "",
};
let profileState = {
  data: null,
  loaded: false,
  message: "",
};
let rateMonitorState = {
  loaded: false,
  message: "",
  monitor: null,
  rate: null,
};

const els = {
  form: document.getElementById("orderForm"),
  list: document.getElementById("ordersList"),
  empty: document.getElementById("emptyState"),
  print: document.getElementById("printSheet"),
  search: document.getElementById("searchInput"),
  statusFilter: document.getElementById("statusFilter"),
  newOrder: document.getElementById("newOrderBtn"),
  printBtn: document.getElementById("printBtn"),
  exportBtn: document.getElementById("exportBtn"),
  ordersMode: document.getElementById("ordersModeBtn"),
  approvalsMode: document.getElementById("approvalsModeBtn"),
  profileMode: document.getElementById("profileModeBtn"),
  adminMode: document.getElementById("adminModeBtn"),
  approvalBadge: document.getElementById("approvalBadge"),
  userInfo: document.getElementById("userInfo"),
  logoutBtn: document.getElementById("logoutBtn"),
};

init();

async function init() {
  if (API_ENABLED) {
    const authenticated = await restoreSession();
    if (!authenticated) {
      showLogin();
      return;
    }
  }

  try {
    await startApp();
    resetViewportScroll();
  } catch (error) {
    handleStartupFailure(error);
  }
}

async function startApp() {
  await ensureCurrentDefaults();
  await loadLegislationRates();

  const ownershipChanged = claimLegacyOrdersForCurrentUser();
  const accessibleOrders = visibleOrders();
  if (!accessibleOrders.length) {
    const firstOrder = createBlankOrder();
    state.orders.push(firstOrder);
    state.selectedId = firstOrder.id;
    saveState();
  } else if (!accessibleOrders.some((order) => order.id === state.selectedId)) {
    state.selectedId = accessibleOrders[0].id;
    saveState();
  } else {
    const defaultsChanged = applyDefaultsToExistingDraft();
    if (ownershipChanged || defaultsChanged) saveState();
  }

  if (!appStarted) {
    STATUS_OPTIONS.forEach((status) => {
      const option = document.createElement("option");
      option.value = status.value;
      option.textContent = status.label;
      els.statusFilter.append(option);
    });

    els.newOrder.addEventListener("click", () => {
      appMode = "orders";
      const order = createBlankOrder();
      state.orders.unshift(order);
      state.selectedId = order.id;
      saveState();
      render();
      resetViewportScroll();
    });

    els.printBtn.addEventListener("click", () => {
      renderPrintSheet(getSelectedOrder());
      window.print();
    });

    els.exportBtn.addEventListener("click", exportBackup);
    els.logoutBtn.addEventListener("click", logout);
    els.ordersMode.addEventListener("click", () => setMode("orders"));
    els.approvalsMode.addEventListener("click", () => setMode("approvals"));
    els.profileMode.addEventListener("click", () => setMode("profile"));
    els.adminMode.addEventListener("click", () => setMode("admin"));
    els.search.addEventListener("input", renderList);
    els.statusFilter.addEventListener("change", renderList);

    els.list.addEventListener("click", (event) => {
      const adminItem = event.target.closest("[data-admin-user-id]");
      if (adminItem) {
        adminState.selectedUserId = adminItem.dataset.adminUserId;
        renderAdmin();
        return;
      }

      const newAdmin = event.target.closest("[data-admin-new]");
      if (newAdmin) {
        adminState.selectedUserId = "new";
        renderAdmin();
        return;
      }

      const item = event.target.closest("[data-order-id]");
      if (!item) return;
      appMode = "orders";
      state.selectedId = item.dataset.orderId;
      saveState();
      render();
    });

    els.form.addEventListener("input", handleFormInput);
    els.form.addEventListener("change", handleFormInput);
    els.form.addEventListener("click", handleFormClick);
    appStarted = true;
  }

  updateUserChrome();
  refreshNotificationBadge();
  render();
}

function loadState() {
  const fallback = {
    orders: [],
    selectedId: null,
    rates: structuredClone(DEFAULT_RATES),
  };

  try {
    const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY));
    if (!parsed || !Array.isArray(parsed.orders)) return fallback;
    return {
      orders: parsed.orders,
      selectedId: parsed.selectedId || parsed.orders[0]?.id || null,
      rates: mergeRates(parsed.rates),
    };
  } catch {
    return fallback;
  }
}

function mergeRates(rates) {
  return {
    ...structuredClone(DEFAULT_RATES),
    ...(rates || {}),
    fuelPrices: {
      ...DEFAULT_RATES.fuelPrices,
      ...(rates?.fuelPrices || {}),
    },
    mealBands: (rates?.mealBands || DEFAULT_RATES.mealBands).map((band, index) => ({
      ...DEFAULT_RATES.mealBands[index],
      ...band,
    })),
  };
}

function saveState() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

function can(role) {
  return Boolean(currentUser?.roles?.includes(role));
}

function currentUserId() {
  return currentUser?.user_id || currentUser?.id || "";
}

function currentUserLabels() {
  const employee = currentDefaults?.employee || {};
  return [
    currentUserId(),
    currentUser?.login_name,
    currentUser?.email,
    currentUser?.display_name,
    employee.personalNo,
    employee.name,
  ].filter(Boolean).map(normalizeIdentity);
}

function normalizeIdentity(value) {
  return normalize(String(value || "").trim());
}

function ownsOrder(order) {
  if (!API_ENABLED || !currentUser) return true;
  const userId = currentUserId();
  if (order.ownerUserId) return order.ownerUserId === userId;

  const legacyOrderLabels = [
    order.employee?.personalNo,
    order.employee?.name,
  ].filter(Boolean).map(normalizeIdentity);
  const labels = currentUserLabels();
  return legacyOrderLabels.some((label) => labels.includes(label));
}

function visibleOrders() {
  return state.orders.filter(ownsOrder);
}

function stampOrderOwner(order) {
  if (!API_ENABLED || !currentUser) return order;
  order.ownerUserId = currentUserId();
  order.ownerLogin = currentUser.login_name || currentUser.email || "";
  order.ownerName = currentUser.display_name || "";
  return order;
}

function claimLegacyOrdersForCurrentUser() {
  if (!API_ENABLED || !currentUser) return false;
  let changed = false;
  state.orders.forEach((order) => {
    if (!order.ownerUserId && ownsOrder(order)) {
      stampOrderOwner(order);
      changed = true;
    }
  });
  return changed;
}

async function setMode(mode) {
  if (mode === "admin" && !can("admin")) return;
  if (mode === "approvals" && !(can("approver") || can("admin") || can("accountant"))) return;
  if (mode === "profile" && (!API_ENABLED || !currentUser)) return;

  appMode = mode;
  if (mode === "admin") await loadAdminData();
  if (mode === "approvals") await loadApprovalData();
  if (mode === "profile") await loadProfileData();
  render();
  resetViewportScroll();
}

async function restoreSession() {
  const token = localStorage.getItem(AUTH_TOKEN_KEY);
  if (!token) return false;

  try {
    const response = await apiFetch("/api/auth/me");
    if (!response.ok) {
      localStorage.removeItem(AUTH_TOKEN_KEY);
      return false;
    }
    const payload = await response.json();
    currentUser = payload.user;
    return true;
  } catch {
    return false;
  }
}

async function apiFetch(path, options = {}) {
  const token = localStorage.getItem(AUTH_TOKEN_KEY);
  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {}),
  };

  if (token) headers.Authorization = `Bearer ${token}`;

  return fetch(path, {
    ...options,
    headers,
  });
}

async function ensureCurrentDefaults(force = false) {
  if (!API_ENABLED || !currentUser) return;
  if (defaultsLoaded && !force) return;

  try {
    const response = await apiFetch("/api/users/me/defaults");
    if (response.ok) {
      currentDefaults = await response.json();
    }
  } catch {
    currentDefaults = null;
  } finally {
    defaultsLoaded = true;
  }
}

async function loadLegislationRates(force = false) {
  if (!API_ENABLED || !currentUser) return;
  if (rateMonitorState.loaded && !force) return;

  try {
    const [rateResponse, monitorResponse] = await Promise.all([
      apiFetch(`/api/rates/current?date=${encodeURIComponent(todayString())}`),
      apiFetch("/api/rates/monitor"),
    ]);
    if (rateResponse.ok) {
      const rate = await rateResponse.json();
      state.rates = mergeRates(rate);
      rateMonitorState.rate = rate;
      saveState();
    }
    if (monitorResponse.ok) {
      const payload = await monitorResponse.json();
      rateMonitorState.monitor = payload.monitor || null;
      rateMonitorState.rate = payload.rate || rateMonitorState.rate;
      rateMonitorState.message = payload.monitor?.effectiveMessage || "";
    }
  } catch {
    rateMonitorState.message = "Kontrolu sazeb se teď nepodařilo načíst.";
  } finally {
    rateMonitorState.loaded = true;
  }
}

async function refreshRateMonitor() {
  if (!API_ENABLED || !currentUser) return;
  try {
    const response = await apiFetch("/api/rates/monitor/check", { method: "POST" });
    if (!response.ok) {
      rateMonitorState.message = "Kontrolu sazeb může spustit jen administrátor.";
      return;
    }
    const payload = await response.json();
    rateMonitorState.monitor = payload.monitor || null;
    rateMonitorState.rate = payload.rate || null;
    if (payload.rate) {
      state.rates = mergeRates(payload.rate);
      saveState();
    }
    rateMonitorState.message = payload.monitor?.effectiveMessage || "Kontrola sazeb proběhla.";
  } catch {
    rateMonitorState.message = "Kontrolu sazeb se nepodařilo spustit.";
  }
}

function showLogin(error = "") {
  document.body.classList.add("login-mode");
  els.form.innerHTML = "";
  els.list.innerHTML = "";
  els.empty.hidden = true;
  updateUserChrome();

  const existing = document.getElementById("loginOverlay");
  if (existing) existing.remove();

  const overlay = document.createElement("div");
  overlay.id = "loginOverlay";
  overlay.className = "login-overlay";
  overlay.innerHTML = `
    <form class="login-panel" autocomplete="on">
      <div>
        <p class="eyebrow">Lokální režim</p>
        <h2>Přihlášení</h2>
      </div>
      <label>
        <span>Uživatel nebo e-mail</span>
        <input name="login" type="text" autocomplete="username" value="admin@local" required />
      </label>
      <label>
        <span>Heslo</span>
        <input name="password" type="password" autocomplete="current-password" required />
      </label>
      <p class="login-error" ${error ? "" : "hidden"}>${escapeHtml(error)}</p>
      <button class="primary-btn" type="submit">Přihlásit</button>
    </form>
  `;
  document.body.append(overlay);
  overlay.querySelector("form").addEventListener("submit", handleLogin);
}

async function handleLogin(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector("button");
  const errorBox = form.querySelector(".login-error");
  button.disabled = true;
  errorBox.hidden = true;
  let loginAccepted = false;

  const data = new FormData(form);
  try {
    const response = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        login: data.get("login"),
        password: data.get("password"),
      }),
    });

    if (!response.ok) {
      throw new Error("Neplatné přihlašovací údaje.");
    }

    const payload = await response.json();
    loginAccepted = true;
    localStorage.setItem(AUTH_TOKEN_KEY, payload.token);
    currentUser = payload.user;
    defaultsLoaded = false;
    await startApp();
    document.getElementById("loginOverlay")?.remove();
    document.body.classList.remove("login-mode");
    resetViewportScroll();
  } catch (error) {
    if (loginAccepted) {
      console.error(error);
      localStorage.removeItem(AUTH_TOKEN_KEY);
      currentUser = null;
      currentDefaults = null;
      defaultsLoaded = false;
      updateUserChrome();
      errorBox.textContent = "Přihlášení proběhlo, ale aplikaci se nepodařilo načíst. Zkus stránku obnovit.";
    } else {
      errorBox.textContent = error.message || "Přihlášení se nepodařilo.";
    }
    errorBox.hidden = false;
  } finally {
    button.disabled = false;
  }
}

function handleStartupFailure(error) {
  console.error(error);
  if (API_ENABLED) {
    localStorage.removeItem(AUTH_TOKEN_KEY);
    currentUser = null;
    currentDefaults = null;
    defaultsLoaded = false;
    showLogin("Aplikaci se nepodařilo načíst. Zkus se prosím přihlásit znovu.");
  }
}

function resetViewportScroll() {
  window.scrollTo(0, 0);
}

async function logout() {
  if (API_ENABLED) {
    try {
      await apiFetch("/api/auth/logout", { method: "POST" });
    } catch {
      // Session cleanup is local-first; server logout failure should not trap the user.
    }
  }
  localStorage.removeItem(AUTH_TOKEN_KEY);
  currentUser = null;
  currentDefaults = null;
  defaultsLoaded = false;
  profileState = { data: null, loaded: false, message: "" };
  showLogin();
}

function updateUserChrome() {
  if (!els.userInfo || !els.logoutBtn) return;

  els.ordersMode.hidden = false;
  els.profileMode.hidden = !API_ENABLED || !currentUser;
  els.approvalsMode.hidden = !API_ENABLED || !(can("approver") || can("admin") || can("accountant"));
  els.adminMode.hidden = !API_ENABLED || !can("admin");

  if (API_ENABLED && currentUser) {
    els.userInfo.hidden = false;
    els.logoutBtn.hidden = false;
    els.userInfo.textContent = currentUser.display_name || currentUser.email || currentUser.login_name;
  } else {
    els.userInfo.hidden = true;
    els.logoutBtn.hidden = true;
  }
}

function render() {
  updateUserChrome();
  updateModeButtons();

  if (appMode === "admin") {
    renderAdmin();
    return;
  }

  if (appMode === "approvals") {
    renderApprovals();
    return;
  }

  if (appMode === "profile") {
    renderProfile();
    return;
  }

  renderList();
  renderForm();
}

function updateModeButtons() {
  [els.ordersMode, els.approvalsMode, els.profileMode, els.adminMode].forEach((button) => button?.classList.remove("active"));
  if (appMode === "orders") els.ordersMode?.classList.add("active");
  if (appMode === "approvals") els.approvalsMode?.classList.add("active");
  if (appMode === "profile") els.profileMode?.classList.add("active");
  if (appMode === "admin") els.adminMode?.classList.add("active");
}

async function loadAdminData() {
  if (!API_ENABLED || !can("admin")) return;
  const [optionsResponse, usersResponse] = await Promise.all([
    apiFetch("/api/admin/users/options"),
    apiFetch("/api/admin/users"),
  ]);
  if (!optionsResponse.ok || !usersResponse.ok) {
    adminState.message = "Nepodařilo se načíst správu uživatelů.";
    return;
  }
  adminState.options = await optionsResponse.json();
  const usersPayload = await usersResponse.json();
  adminState.users = usersPayload.users || [];
  adminState.loaded = true;
  if (!adminState.selectedUserId && adminState.users[0]) {
    adminState.selectedUserId = adminState.users[0].id;
  }
}

function renderAdmin() {
  els.empty.hidden = true;
  els.form.hidden = false;
  els.list.innerHTML = adminSidebar();
  const selected = getSelectedAdminUser();

  els.form.innerHTML = `
    <div class="detail-column">
      <div class="form-header">
        <div>
          <h2>Správa uživatelů</h2>
          <div class="header-meta">
            <span>Lokální účty dnes, Helios synchronizace později</span>
          </div>
        </div>
        <div class="header-actions">
          <button type="button" class="primary-btn" data-admin-action="save-user">Uložit uživatele</button>
        </div>
      </div>
      ${adminState.message ? `<p class="inline-message">${escapeHtml(adminState.message)}</p>` : ""}
      ${adminUserSection(selected)}
      ${adminSyncSection()}
    </div>
  `;
}

function adminSidebar() {
  const items = adminState.users.map((user) => `
    <button type="button" class="order-list-item ${user.id === adminState.selectedUserId ? "active" : ""}" data-admin-user-id="${escapeHtml(user.id)}">
      <span class="order-list-title">
        <span>${escapeHtml(user.display_name)}</span>
        ${user.is_active ? `<span class="status-pill status-approved">Aktivní</span>` : `<span class="status-pill status-rejected">Vypnutý</span>`}
      </span>
      <span class="order-list-meta">${escapeHtml(user.email || user.login_name)}</span>
      <span class="order-list-meta">Schvalovatel: ${escapeHtml(user.default_approver_name || "nenastaven")}</span>
    </button>
  `).join("");

  return `
    <button type="button" class="primary-btn full-width" data-admin-new>Nový uživatel</button>
    <div class="orders-list">${items || `<p class="note">Zatím nejsou žádní uživatelé.</p>`}</div>
  `;
}

function getSelectedAdminUser() {
  if (adminState.selectedUserId === "new") return createEmptyAdminUser();
  return adminState.users.find((user) => user.id === adminState.selectedUserId) || adminState.users[0] || createEmptyAdminUser();
}

function createEmptyAdminUser() {
  return {
    id: "",
    login_name: "",
    email: "",
    display_name: "",
    personal_number: "",
    address: "",
    phone: "",
    organization_name: "",
    work_start: "08:00",
    work_end: "16:30",
    cost_center_code: "",
    cost_center_name: "",
    department_name: "",
    default_transport_kind: "private_car",
    default_approver_user_id: "",
    approver_options: [],
    manager_user_id: "",
    accountant_user_id: "",
    vehicles: [createEmptyAdminVehicle(true)],
    is_active: true,
    roles: ["employee"],
  };
}

function adminUserSection(user) {
  return `
    <section class="section">
      <div class="section-header">
        <h3>${user.id ? "Účet a role" : "Nový uživatel"}</h3>
      </div>
      <div class="section-body form-grid">
        <input type="hidden" data-admin-field="id" value="${escapeHtml(user.id || "")}" />
        ${adminField("Login", "login_name", user.login_name)}
        ${adminField("E-mail", "email", user.email || "", "email")}
        ${adminField("Jméno", "display_name", user.display_name)}
        ${adminField(user.id ? "Nové heslo" : "Heslo", "password", "", "password")}
        <label class="checkbox-line">
          <input data-admin-field="is_active" type="checkbox" ${user.is_active ? "checked" : ""} />
          <span>Aktivní účet</span>
        </label>
        <div class="wide">
          <span class="field-caption">Oprávnění účtu</span>
          <div class="role-grid">
            ${(adminState.options.roles || []).map((role) => `
              <label class="checkbox-line role-option">
                <input data-admin-role="${escapeHtml(role.code)}" type="checkbox" ${user.roles?.includes(role.code) ? "checked" : ""} />
                <span>
                  <strong>${escapeHtml(role.name)}</strong>
                  ${role.description ? `<small>${escapeHtml(role.description)}</small>` : ""}
                </span>
              </label>
            `).join("")}
          </div>
        </div>
      </div>
    </section>
    <section class="section">
      <div class="section-header">
        <h3>Údaje do cestovního příkazu</h3>
      </div>
      <div class="section-body form-grid">
        ${adminField("Organizace", "organization_name", user.organization_name || "")}
        ${adminField("Osobní číslo", "personal_number", user.personal_number || user.login_name || "")}
        ${adminField("Středisko - kód", "cost_center_code", user.cost_center_code || "")}
        ${adminField("Středisko - název", "cost_center_name", user.cost_center_name || "")}
        ${adminField("Útvar", "department_name", user.department_name || "")}
        ${adminField("Telefon", "phone", user.phone || "")}
        ${adminField("Pracovní doba od", "work_start", user.work_start || "08:00", "time")}
        ${adminField("Pracovní doba do", "work_end", user.work_end || "16:30", "time")}
        ${adminChoiceSelect("Výchozí doprava", "default_transport_kind", user.default_transport_kind || "private_car", adminState.options.transportKinds || transportAdminOptions())}
        ${adminField("Bydliště", "address", user.address || "", "text", null, "wide")}
      </div>
    </section>
    <section class="section">
      <div class="section-header">
        <h3>Výchozí schvalování</h3>
      </div>
      <div class="section-body form-grid">
        ${adminApproverOptions(user)}
        ${adminSelect("Manažer", "manager_user_id", user.manager_user_id, adminState.options.approvers || [])}
        ${adminSelect("Účetní", "accountant_user_id", user.accountant_user_id, adminState.options.approvers || [])}
      </div>
    </section>
    <section class="section">
      <div class="section-header">
        <h3>Vozidla zaměstnance</h3>
        <button type="button" class="secondary-btn" data-admin-action="add-vehicle">Přidat vozidlo</button>
      </div>
      <div class="section-body">
        <div class="vehicle-list" data-admin-vehicles>
          ${adminVehicleList(user).map((vehicle, index) => adminVehicleCard(vehicle, index)).join("")}
        </div>
      </div>
    </section>
  `;
}

function adminApproverOptions(user) {
  const selected = new Map((user.approver_options || []).map((approver) => [approver.id, approver]));
  const fallbackDefaultId = user.default_approver_user_id || "";
  const options = (adminState.options.approvers || []).map((approver) => {
    const current = selected.get(approver.id);
    return {
      ...approver,
      checked: Boolean(current) || approver.id === fallbackDefaultId,
      is_default: Boolean(current?.is_default) || approver.id === fallbackDefaultId,
    };
  });

  return `
    <div class="wide">
      <span class="field-caption">Povolení schvalovatelé</span>
      <div class="approver-option-list">
        ${options.map((approver) => `
          <label class="approver-option">
            <input data-admin-approver-option="${escapeHtml(approver.id)}" type="checkbox" ${approver.checked ? "checked" : ""} />
            <input data-admin-approver-default name="adminDefaultApprover" value="${escapeHtml(approver.id)}" type="radio" ${approver.is_default ? "checked" : ""} />
            <span>
              <strong>${escapeHtml(approver.display_name)}</strong>
              <small>${escapeHtml(approver.email || approver.login_name)}</small>
            </span>
          </label>
        `).join("") || `<p class="note">Nejdřív musí existovat uživatel s rolí Schvalovatel.</p>`}
      </div>
    </div>
  `;
}

function adminVehicleList(user) {
  const vehicles = Array.isArray(user.vehicles) ? user.vehicles : [];
  if (vehicles.length) {
    const normalized = vehicles.map((vehicle) => ({
      id: vehicle.id || "",
      brand: vehicle.brand || "",
      plate: vehicle.plate || "",
      engine_volume: vehicle.engine_volume ?? vehicle.engineVolume ?? "",
      fuel_type: vehicle.fuel_type || vehicle.fuelType || "ba95",
      consumption: vehicle.consumption ?? 0,
      secondary_fuel_type: vehicle.secondary_fuel_type || vehicle.secondaryFuelType || "",
      secondary_consumption: vehicle.secondary_consumption ?? vehicle.secondaryConsumption ?? "",
      is_default: Boolean(vehicle.is_default || vehicle.isDefault),
    }));
    if (!normalized.some((vehicle) => vehicle.is_default)) normalized[0].is_default = true;
    return normalized;
  }

  if (user.vehicle_brand || user.vehicle_plate || user.vehicle_engine_volume || Number(user.vehicle_consumption || 0) > 0) {
    return [{
      id: user.default_vehicle_id || "",
      brand: user.vehicle_brand || "",
      plate: user.vehicle_plate || "",
      engine_volume: user.vehicle_engine_volume || "",
      fuel_type: user.vehicle_fuel_type || "ba95",
      consumption: user.vehicle_consumption || 0,
      secondary_fuel_type: user.vehicle_secondary_fuel_type || "",
      secondary_consumption: user.vehicle_secondary_consumption || "",
      is_default: true,
    }];
  }

  return [createEmptyAdminVehicle(true)];
}

function createEmptyAdminVehicle(isDefault = false) {
  return {
    id: "",
    brand: "",
    plate: "",
    engine_volume: "",
    fuel_type: "ba95",
    consumption: "",
    secondary_fuel_type: "",
    secondary_consumption: "",
    is_default: isDefault,
  };
}

function adminVehicleCard(vehicle, index) {
  return `
    <article class="vehicle-card" data-admin-vehicle>
      <div class="vehicle-card-head">
        <label class="checkbox-line">
          <input data-admin-vehicle-default name="adminDefaultVehicle" type="radio" ${vehicle.is_default ? "checked" : ""} />
          <span>Výchozí vozidlo</span>
        </label>
        <button type="button" class="table-icon-btn" data-admin-remove-vehicle title="Odebrat vozidlo" aria-label="Odebrat vozidlo">×</button>
      </div>
      <div class="form-grid">
        <input type="hidden" data-admin-vehicle-field="id" value="${escapeHtml(vehicle.id || "")}" />
        ${adminVehicleField("Tovární značka / typ", "brand", vehicle.brand || "")}
        ${adminVehicleField("SPZ", "plate", vehicle.plate || "")}
        ${adminVehicleField("Obsah motoru", "engine_volume", vehicle.engine_volume || "", "number", "1")}
        ${adminVehicleSelect("Druh PHM", "fuel_type", vehicle.fuel_type || "ba95", adminState.options.fuelTypes || fuelAdminOptions())}
        ${adminVehicleField("Spotřeba na 100 km", "consumption", vehicle.consumption || "", "number", "0.01")}
        ${adminVehicleOptionalFuelSelect("Druhá energie", "secondary_fuel_type", vehicle.secondary_fuel_type || "", adminState.options.fuelTypes || fuelAdminOptions())}
        ${adminVehicleField("Spotřeba druhé energie na 100 km", "secondary_consumption", vehicle.secondary_consumption || "", "number", "0.01")}
      </div>
    </article>
  `;
}

function adminVehicleField(label, field, value, type = "text", step = null) {
  const stepAttr = step ? `step="${escapeHtml(step)}"` : "";
  const inputMode = type === "number" ? `inputmode="decimal" min="0"` : "";
  return `
    <label>
      <span>${escapeHtml(label)}</span>
      <input data-admin-vehicle-field="${escapeHtml(field)}" type="${escapeHtml(type)}" ${stepAttr} ${inputMode} value="${escapeHtml(value || "")}" />
    </label>
  `;
}

function adminVehicleSelect(label, field, value, options) {
  const optionHtml = options.map((option) => {
    return `<option value="${escapeHtml(option.code)}" ${option.code === value ? "selected" : ""}>${escapeHtml(option.name)}</option>`;
  }).join("");
  return `
    <label>
      <span>${escapeHtml(label)}</span>
      <select data-admin-vehicle-field="${escapeHtml(field)}">${optionHtml}</select>
    </label>
  `;
}

function adminVehicleOptionalFuelSelect(label, field, value, options) {
  const optionHtml = [`<option value="">Žádná</option>`].concat(options.map((option) => {
    return `<option value="${escapeHtml(option.code)}" ${option.code === value ? "selected" : ""}>${escapeHtml(option.name)}</option>`;
  }));
  return `
    <label>
      <span>${escapeHtml(label)}</span>
      <select data-admin-vehicle-field="${escapeHtml(field)}">${optionHtml.join("")}</select>
    </label>
  `;
}

function adminField(label, field, value, type = "text", step = null, className = "") {
  const stepAttr = step ? `step="${escapeHtml(step)}"` : "";
  const inputMode = type === "number" ? `inputmode="decimal" min="0"` : "";
  return `
    <label class="${escapeHtml(className)}">
      <span>${escapeHtml(label)}</span>
      <input data-admin-field="${escapeHtml(field)}" type="${escapeHtml(type)}" ${stepAttr} ${inputMode} value="${escapeHtml(value || "")}" />
    </label>
  `;
}

function adminSelect(label, field, value, users) {
  const options = [`<option value="">Nenastaveno</option>`].concat(users.map((user) => {
    return `<option value="${escapeHtml(user.id)}" ${user.id === value ? "selected" : ""}>${escapeHtml(user.display_name)} (${escapeHtml(user.login_name)})</option>`;
  }));
  return `
    <label>
      <span>${escapeHtml(label)}</span>
      <select data-admin-field="${escapeHtml(field)}">${options.join("")}</select>
    </label>
  `;
}

function adminChoiceSelect(label, field, value, options) {
  const optionHtml = options.map((option) => {
    return `<option value="${escapeHtml(option.code)}" ${option.code === value ? "selected" : ""}>${escapeHtml(option.name)}</option>`;
  }).join("");
  return `
    <label>
      <span>${escapeHtml(label)}</span>
      <select data-admin-field="${escapeHtml(field)}">${optionHtml}</select>
    </label>
  `;
}

function transportAdminOptions() {
  return Object.entries(TRANSPORT_OPTIONS).map(([code, name]) => ({ code, name }));
}

function fuelAdminOptions() {
  return Object.entries(FUEL_OPTIONS).map(([code, name]) => ({ code, name }));
}

function adminSyncSection() {
  return `
    <section class="section">
      <div class="section-header">
        <h3>Helios synchronizace</h3>
      </div>
      <div class="section-body sync-grid">
        <div>
          <strong>Teď</strong>
          <p class="note">Uživatelé jsou lokální. Schvalovatel se nastavuje ručně v profilu zaměstnance.</p>
        </div>
        <div>
          <strong>Později</strong>
          <p class="note">Synchronizace z Heliosu bude plnit osobní číslo, středisko, manažera, výchozího schvalovatele a aktivitu účtu.</p>
        </div>
      </div>
    </section>
  `;
}

async function saveAdminUserFromForm() {
  const payload = {};
  els.form.querySelectorAll("[data-admin-field]").forEach((field) => {
    if (field.type === "checkbox") {
      payload[field.dataset.adminField] = field.checked;
    } else {
      payload[field.dataset.adminField] = field.value.trim();
    }
  });
  payload.roles = Array.from(els.form.querySelectorAll("[data-admin-role]:checked")).map((role) => role.dataset.adminRole);
  if (!payload.roles.length) payload.roles = ["employee"];
  payload.vehicles = collectAdminVehiclesFromForm();
  payload.approver_options = collectAdminApproversFromForm();
  payload.default_approver_user_id = payload.approver_options.find((approver) => approver.is_default)?.id || "";

  const isEdit = Boolean(payload.id);
  const response = await apiFetch(isEdit ? `/api/admin/users/${payload.id}` : "/api/admin/users", {
    method: isEdit ? "PUT" : "POST",
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    adminState.message = "Uložení uživatele se nepodařilo.";
    renderAdmin();
    return;
  }

  const saved = await response.json();
  adminState.message = "Uživatel byl uložen.";
  adminState.selectedUserId = saved.user.id;
  if (saved.user.id === currentUser?.user_id) {
    await ensureCurrentDefaults(true);
    applyDefaultsToExistingDraft();
    saveState();
  }
  await loadAdminData();
  renderAdmin();
}

function collectAdminVehiclesFromForm() {
  return Array.from(els.form.querySelectorAll("[data-admin-vehicle]")).map((card) => {
    const vehicle = {};
    card.querySelectorAll("[data-admin-vehicle-field]").forEach((field) => {
      vehicle[field.dataset.adminVehicleField] = field.value.trim();
    });
    vehicle.is_default = Boolean(card.querySelector("[data-admin-vehicle-default]")?.checked);
    return vehicle;
  }).filter((vehicle) => {
    return vehicle.brand || vehicle.plate || vehicle.engine_volume || Number(vehicle.consumption || 0) > 0;
  });
}

function collectAdminApproversFromForm() {
  const defaultId = els.form.querySelector("[data-admin-approver-default]:checked")?.value || "";
  const selected = Array.from(els.form.querySelectorAll("[data-admin-approver-option]:checked")).map((field) => field.dataset.adminApproverOption);
  const approverIds = selected.includes(defaultId) || !defaultId ? selected : selected.concat(defaultId);
  return approverIds.map((id, index) => ({
    id,
    is_default: id === defaultId || (!defaultId && index === 0),
  }));
}

function addAdminVehicleCard() {
  const list = els.form.querySelector("[data-admin-vehicles]");
  if (!list) return;
  const hasVehicle = Boolean(list.querySelector("[data-admin-vehicle]"));
  list.insertAdjacentHTML("beforeend", adminVehicleCard(createEmptyAdminVehicle(!hasVehicle), list.children.length));
}

function removeAdminVehicleCard(button) {
  const card = button.closest("[data-admin-vehicle]");
  const list = card?.closest("[data-admin-vehicles]");
  if (!card || !list) return;

  const wasDefault = Boolean(card.querySelector("[data-admin-vehicle-default]")?.checked);
  card.remove();
  const remaining = list.querySelectorAll("[data-admin-vehicle]");
  if (!remaining.length) {
    list.insertAdjacentHTML("beforeend", adminVehicleCard(createEmptyAdminVehicle(true), 0));
    return;
  }
  if (wasDefault) {
    remaining[0].querySelector("[data-admin-vehicle-default]").checked = true;
  }
}

async function loadProfileData(force = false) {
  if (!API_ENABLED || !currentUser) return;
  if (profileState.loaded && !force) return;

  const response = await apiFetch("/api/users/me/profile");
  if (!response.ok) {
    profileState.message = "Nepodařilo se načíst profil.";
    return;
  }

  const payload = await response.json();
  profileState.data = payload.profile;
  profileState.loaded = true;
}

function renderProfile() {
  els.empty.hidden = true;
  els.form.hidden = false;
  els.list.innerHTML = profileSidebar();
  const profile = profileState.data || profileFromDefaults();

  els.form.innerHTML = `
    <div class="detail-column">
      <div class="form-header">
        <div>
          <h2>Můj profil</h2>
          <div class="header-meta">
            <span>Výchozí údaje pro moje cestovní příkazy</span>
          </div>
        </div>
        <div class="header-actions">
          <button type="button" class="primary-btn" data-profile-action="save-profile">Uložit profil</button>
        </div>
      </div>
      ${profileState.message ? `<p class="inline-message">${escapeHtml(profileState.message)}</p>` : ""}
      <section class="section">
        <div class="section-header">
          <h3>Moje údaje pro příkaz</h3>
        </div>
        <div class="section-body form-grid">
          ${profileField("Jméno", "display_name", profile.display_name || "")}
          ${profileField("E-mail", "email", profile.email || "", "email")}
          ${profileField("Organizace", "organization_name", profile.organization_name || "")}
          ${profileField("Osobní číslo", "personal_number", profile.personal_number || "")}
          ${profileField("Středisko - kód", "cost_center_code", profile.cost_center_code || "")}
          ${profileField("Středisko - název", "cost_center_name", profile.cost_center_name || "")}
          ${profileField("Útvar", "department_name", profile.department_name || "")}
          ${profileField("Telefon", "phone", profile.phone || "")}
          ${profileField("Pracovní doba od", "work_start", profile.work_start || "08:00", "time")}
          ${profileField("Pracovní doba do", "work_end", profile.work_end || "16:30", "time")}
          ${adminChoiceSelect("Výchozí doprava", "default_transport_kind", profile.default_transport_kind || "private_car", transportAdminOptions())}
          ${profileField("Bydliště", "address", profile.address || "", "text", "wide")}
        </div>
      </section>
      <section class="section">
        <div class="section-header">
          <h3>Moje vozidla</h3>
          <button type="button" class="secondary-btn" data-profile-action="add-vehicle">Přidat vozidlo</button>
        </div>
        <div class="section-body">
          <div class="vehicle-list" data-admin-vehicles>
            ${adminVehicleList(profile).map((vehicle, index) => adminVehicleCard(vehicle, index)).join("")}
          </div>
        </div>
      </section>
      <section class="section">
        <div class="section-header">
          <h3>Schvalování</h3>
        </div>
        <div class="section-body form-grid">
          ${profileApproverSelect(profile)}
          <div class="wide">
            <p class="note">Tady si vybíráš výchozího schvalovatele pro nové příkazy. Seznam dostupných schvalovatelů určí firma, případně později Helios.</p>
          </div>
        </div>
      </section>
    </div>
  `;
}

function profileSidebar() {
  const profile = profileState.data || profileFromDefaults();
  const vehicleCount = adminVehicleList(profile).filter((vehicle) => vehicle.brand || vehicle.plate).length;

  return `
    <div class="approval-sidebar">
      <div class="notification-item">
        <span>${escapeHtml(profile.display_name || currentUser?.display_name || "Můj profil")}</span>
        <small>${escapeHtml(profile.email || currentUser?.email || currentUser?.login_name || "")}</small>
      </div>
      <div class="notification-item">
        <span>${vehicleCount}</span>
        <small>Uložená vozidla pro cestovní příkaz</small>
      </div>
      <div class="notification-item">
        <span>${escapeHtml(selectedProfileApprover(profile)?.name || "Schvalovatel nenastaven")}</span>
        <small>Výchozí schvalovatel pro nové příkazy</small>
      </div>
    </div>
  `;
}

function profileFromDefaults() {
  const employee = currentDefaults?.employee || {};
  const vehicles = (currentDefaults?.vehicles || []).map((vehicle) => ({
    id: vehicle.id || "",
    brand: vehicle.brand || "",
    plate: vehicle.plate || "",
    engine_volume: vehicle.engineVolume || "",
    fuel_type: vehicle.fuelType || "ba95",
    consumption: vehicle.consumption || "",
    secondary_fuel_type: vehicle.secondaryFuelType || "",
    secondary_consumption: vehicle.secondaryConsumption || "",
    is_default: Boolean(vehicle.is_default),
  }));

  return {
    display_name: employee.name || currentUser?.display_name || "",
    email: currentUser?.email || "",
    organization_name: employee.organization || "",
    personal_number: employee.personalNo || "",
    address: employee.address || "",
    phone: employee.phone || "",
    work_start: employee.workStart || "08:00",
    work_end: employee.workEnd || "16:30",
    cost_center_code: employee.costCenterCode || "",
    cost_center_name: employee.costCenterName || "",
    department_name: employee.department || "",
    default_transport_kind: currentDefaults?.route?.transport || "private_car",
    default_approver_user_id: currentDefaults?.approver?.id || "",
    approver_options: currentDefaults?.approvers || [],
    vehicles: vehicles.length ? vehicles : [createEmptyAdminVehicle(true)],
  };
}

function profileApproverSelect(profile) {
  const approvers = profile.approver_options || currentDefaults?.approvers || [];
  const selectedId = profile.default_approver_user_id || currentDefaults?.approver?.id || approvers.find((approver) => approver.is_default)?.id || "";
  if (!approvers.length) {
    return `
      <div class="wide">
        <span class="field-caption">Výchozí schvalovatel</span>
        <p class="note">Zatím není dostupný žádný schvalovatel.</p>
      </div>
    `;
  }

  const options = approvers.map((approver) => {
    const label = `${approver.name || approver.display_name} (${approver.email || approver.login || ""})`;
    return `<option value="${escapeHtml(approver.id)}" ${approver.id === selectedId ? "selected" : ""}>${escapeHtml(label)}</option>`;
  });

  return `
    <label class="wide">
      <span>Výchozí schvalovatel</span>
      <select data-profile-approver>${options.join("")}</select>
    </label>
  `;
}

function selectedProfileApprover(profile) {
  const approvers = profile.approver_options || currentDefaults?.approvers || [];
  const selectedId = profile.default_approver_user_id || currentDefaults?.approver?.id || "";
  return approvers.find((approver) => approver.id === selectedId) || approvers.find((approver) => approver.is_default);
}

function profileField(label, field, value, type = "text", className = "") {
  return `
    <label class="${escapeHtml(className)}">
      <span>${escapeHtml(label)}</span>
      <input data-profile-field="${escapeHtml(field)}" type="${escapeHtml(type)}" value="${escapeHtml(value || "")}" />
    </label>
  `;
}

async function saveProfileFromForm() {
  const payload = {};
  els.form.querySelectorAll("[data-profile-field]").forEach((field) => {
    payload[field.dataset.profileField] = field.value.trim();
  });
  const transportField = els.form.querySelector('[data-admin-field="default_transport_kind"]');
  payload.default_transport_kind = transportField?.value || "private_car";
  payload.default_approver_user_id = els.form.querySelector("[data-profile-approver]")?.value || "";
  payload.vehicles = collectAdminVehiclesFromForm();

  const response = await apiFetch("/api/users/me/profile", {
    method: "PUT",
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    profileState.message = "Uložení profilu se nepodařilo. Zkontroluj hlavně osobní číslo a e-mail.";
    renderProfile();
    return;
  }

  const saved = await response.json();
  profileState.data = saved.profile;
  profileState.loaded = true;
  profileState.message = "Profil byl uložen.";
  currentUser = {
    ...currentUser,
    display_name: saved.profile.display_name,
    email: saved.profile.email,
  };
  await ensureCurrentDefaults(true);
  applyDefaultsToExistingDraft();
  saveState();
  updateUserChrome();
  renderProfile();
}

async function loadApprovalData() {
  if (!API_ENABLED) return;
  const [dashboardResponse, notificationsResponse] = await Promise.all([
    apiFetch("/api/approver/dashboard"),
    apiFetch("/api/notifications"),
  ]);

  if (!dashboardResponse.ok || !notificationsResponse.ok) {
    approvalState.message = "Nepodařilo se načíst schvalování.";
    return;
  }

  const dashboard = await dashboardResponse.json();
  approvalState.summary = dashboard.summary || { pending_count: 0, overdue_count: 0, pending_gross_amount: 0 };
  approvalState.orders = dashboard.orders || [];
  approvalState.notifications = await notificationsResponse.json();
  approvalState.loaded = true;
}

async function loadApprovalDetail(approvalId) {
  if (!API_ENABLED || !approvalId) return false;
  const response = await apiFetch(`/api/approval-requests/${approvalId}/detail`);
  if (!response.ok) {
    approvalState.message = "Detail cestovního příkazu se nepodařilo načíst.";
    approvalState.detail = null;
    approvalState.selectedApprovalId = null;
    return false;
  }
  approvalState.detail = await response.json();
  approvalState.selectedApprovalId = approvalId;
  approvalState.message = "";
  return true;
}

async function refreshNotificationBadge() {
  if (!API_ENABLED || !currentUser || !els.approvalBadge) return;
  try {
    const response = await apiFetch("/api/notifications");
    if (!response.ok) return;
    approvalState.notifications = await response.json();
    const unread = Number(approvalState.notifications?.badge?.unread_count || 0);
    els.approvalBadge.hidden = unread === 0;
    els.approvalBadge.textContent = String(unread);
  } catch {
    // Badge refresh is opportunistic.
  }
}

function renderApprovals() {
  els.empty.hidden = true;
  els.form.hidden = false;
  els.list.innerHTML = approvalSidebar();
  const summary = approvalState.summary || {};
  const orders = approvalState.orders || [];

  els.form.innerHTML = `
    <div class="detail-column">
      <div class="form-header">
        <div>
          <h2>Schvalování</h2>
          <div class="header-meta">
            <span>Úkoly čekající na tvoje rozhodnutí</span>
          </div>
        </div>
      </div>
      ${approvalState.message ? `<p class="inline-message">${escapeHtml(approvalState.message)}</p>` : ""}
      <section class="order-overview">
        <div class="overview-main">
          <span class="overview-label">Fronta schvalovatele</span>
          <strong>${Number(summary.pending_count || 0)} čeká</strong>
          <span>${Number(summary.overdue_count || 0)} po termínu</span>
        </div>
        <div class="overview-stats">
          ${compactStat("Čeká", "approvalPending", String(summary.pending_count || 0))}
          ${compactStat("Po termínu", "approvalOverdue", String(summary.overdue_count || 0))}
          ${compactStat("Objem", "approvalAmount", formatCurrency(summary.pending_gross_amount || 0))}
          ${compactStat("Notifikace", "approvalUnread", String(approvalState.notifications?.badge?.unread_count || 0))}
        </div>
      </section>
      ${approvalState.detail ? approvalDetailSection(approvalState.detail) : ""}
      <section class="section">
        <div class="section-header">
          <h3>Ke schválení</h3>
          <button type="button" class="secondary-btn" data-approval-action="refresh">Obnovit</button>
        </div>
        <div class="section-body approval-stack">
          ${orders.length ? orders.map(approvalCard).join("") : `<p class="note">Teď tu není žádný cestovní příkaz ke schválení.</p>`}
        </div>
      </section>
    </div>
  `;
}

function approvalSidebar() {
  const notifications = approvalState.notifications?.items || [];
  return `
    <div class="approval-sidebar">
      <strong>Upozornění</strong>
      ${notifications.length ? notifications.map((item) => `
        <div class="notification-item">
          <span>${escapeHtml(item.title)}</span>
          <small>${escapeHtml(item.message || "")}</small>
        </div>
      `).join("") : `<p class="note">Žádná upozornění.</p>`}
    </div>
  `;
}

function approvalCard(item) {
  return `
    <article class="approval-card ${approvalState.selectedApprovalId === item.approval_request_id ? "active" : ""}">
      <div>
        <span class="route-index">${escapeHtml(item.order_no)}</span>
        <h3>${escapeHtml(item.purpose || "Bez účelu")}</h3>
        <p>${escapeHtml(item.requester_name || "Neznámý žadatel")} · ${escapeHtml(item.destination || "Bez místa")}</p>
      </div>
      <div class="approval-amount">
        <span>Částka</span>
        <strong>${formatCurrency(item.gross_amount || 0)}</strong>
      </div>
      <div class="approval-actions">
        <button type="button" class="primary-btn" data-approval-action="detail" data-approval-id="${escapeHtml(item.approval_request_id)}">Zkontrolovat</button>
      </div>
    </article>
  `;
}

function approvalDetailSection(detail) {
  const order = detail.order || {};
  const employee = detail.employee || {};
  const approval = detail.approval || {};
  const total = detail.total || {};
  const calc = detailCalculation(detail);
  const vehicle = detailSnapshotOrder(detail).vehicle || {};
  const attachments = detail.attachments || [];
  return `
    <section class="section approval-detail" id="approvalDetail">
      <div class="section-header">
        <div>
          <h3>Kontrola ${escapeHtml(order.number || "")}</h3>
          <p class="section-subtitle">${escapeHtml(employee.name || "Neznámý žadatel")} · ${escapeHtml(order.destination || "Bez místa jednání")}</p>
        </div>
        <div class="approval-actions">
          <button type="button" class="secondary-btn" data-approval-action="back">Zpět na frontu</button>
          <button type="button" class="primary-btn" data-approval-action="approved" data-approval-id="${escapeHtml(approval.id)}">Schválit</button>
          <button type="button" class="secondary-btn" data-approval-action="returned" data-approval-id="${escapeHtml(approval.id)}">Vrátit k doplnění</button>
          <button type="button" class="status-btn danger" data-approval-action="rejected" data-approval-id="${escapeHtml(approval.id)}">Zamítnout</button>
        </div>
      </div>
      <div class="section-body approval-detail-body">
        <div class="approval-check-grid">
          ${approvalCheck("Žadatel", employee.name || "", employee.personalNumber ? `Os. č. ${employee.personalNumber}` : employee.email || "")}
          ${approvalCheck("Termín cesty", formatDateTime(order.plannedStartAt), formatDateTime(order.plannedEndAt))}
          ${approvalCheck("Účel a místo", order.purpose || "Bez účelu", order.destination || "Bez místa")}
          ${approvalCheck("Lhůta schválení", approval.dueAt ? formatDateTime(approval.dueAt) : "Bez termínu", approval.isOverdue ? "Po termínu" : "V termínu")}
        </div>

        <div class="approval-total-strip">
          ${compactStat("Celkem", "approvalGross", formatCurrency(total.grossAmount || calc.totalGross || 0))}
          ${compactStat("Cestovné", "approvalTransport", formatCurrency(total.transportAmount || calc.totalTransport || 0))}
          ${compactStat("Stravné", "approvalMeals", formatCurrency(total.mealAmount || calc.totalMeals || 0))}
          ${compactStat("Nocležné", "approvalLodging", formatCurrency(total.lodgingAmount || calc.totalLodging || 0))}
          ${compactStat("Výdaje", "approvalOther", formatCurrency(total.otherAmount || calc.totalOther || 0))}
          ${compactStat("K výplatě", "approvalBalance", formatCurrency(total.balanceRounded || calc.balanceRounded || 0))}
        </div>

        <div class="approval-detail-grid">
          <div class="detail-panel">
            <h4>Zaměstnanec a organizace</h4>
            ${detailRow("Organizace", employee.organization)}
            ${detailRow("Středisko", employee.costCenter)}
            ${detailRow("Útvar", employee.department)}
            ${detailRow("Adresa", employee.address)}
            ${detailRow("Telefon", employee.phone)}
          </div>
          <div class="detail-panel">
            <h4>Vozidlo a sazby</h4>
            ${detailRow("Vozidlo", [vehicle.brand, vehicle.plate].filter(Boolean).join(" · ") || "Neuvedeno")}
            ${detailRow("PHM", fuelLabel(vehicle.fuelType))}
            ${detailRow("Spotřeba", vehicle.consumption ? `${formatNumber(vehicle.consumption, 2)} / 100 km` : "")}
            ${detailRow("Cena PHM", vehicle.fuelPrice ? `${formatCurrency(vehicle.fuelPrice)} (${fuelPriceModeLabel(vehicle.fuelPriceMode)})` : "")}
            ${vehicle.secondaryFuelType ? detailRow("Druhá energie", `${fuelLabel(vehicle.secondaryFuelType)} · ${formatNumber(vehicle.secondaryConsumption, 2)} / 100 km`) : ""}
            ${detailRow("Základní náhrada", vehicle.basicKmRate ? `${formatCurrency(vehicle.basicKmRate)} / km` : "")}
          </div>
        </div>

        <div class="table-wrap">
          <table class="calc-table approval-lines-table">
            <thead>
              <tr>
                <th>Úsek</th>
                <th>Čas</th>
                <th>Doprava</th>
                <th>Km</th>
                <th>Jízdné/PHM</th>
                <th>Stravné</th>
                <th>Nocležné</th>
                <th>Výdaje</th>
                <th>Celkem</th>
              </tr>
            </thead>
            <tbody>${approvalRouteRows(detail).join("")}</tbody>
          </table>
        </div>

        <div class="detail-panel">
          <h4>Doklady</h4>
          ${attachments.length ? attachments.map(approvalAttachmentRow).join("") : `<p class="note">K příkazu nejsou přiložené doklady.</p>`}
        </div>
      </div>
    </section>
  `;
}

function approvalCheck(label, value, meta = "") {
  return `
    <div class="approval-check">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value || "-")}</strong>
      ${meta ? `<small>${escapeHtml(meta)}</small>` : ""}
    </div>
  `;
}

function detailRow(label, value) {
  return `
    <div class="detail-row">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value || "-")}</strong>
    </div>
  `;
}

function detailCalculation(detail) {
  const snapshot = detail?.total?.calculationSnapshot || {};
  return snapshot.calculation || snapshot || {};
}

function detailSnapshotOrder(detail) {
  const snapshot = detail?.total?.calculationSnapshot || {};
  return snapshot.order || {};
}

function approvalRouteRows(detail) {
  const lines = detail.routeLines || [];
  const calcLines = detailCalculation(detail).lines || [];
  if (!lines.length) {
    return [`<tr><td colspan="9">Nejsou zadané žádné úseky cesty.</td></tr>`];
  }

  return lines.map((line, index) => {
    const calcLine = calcLines[index] || {};
    const transportAmount = number(line.fare) + number(line.calculatedPrivateVehicleAmount || calcLine.privateComp);
    const mealAmount = number(line.calculatedMealAmount || calcLine.meal);
    const lodging = number(line.lodging);
    const other = number(line.other);
    const total = number(line.calculatedTotalAmount || calcLine.total) || transportAmount + mealAmount + lodging + other;
    return `
      <tr>
        <td>
          <strong>${escapeHtml(line.from || "Odkud")} → ${escapeHtml(line.to || "Kam")}</strong><br />
          <small>${escapeHtml(line.company || line.purpose || "")}</small>
        </td>
        <td>${escapeHtml(formatDateTime(line.startAt))}<br /><small>${escapeHtml(formatDateTime(line.endAt))}</small></td>
        <td>${escapeHtml(TRANSPORT_OPTIONS[line.transport] || line.transport || "-")}</td>
        <td>${formatNumber(line.km || 0, 0)}</td>
        <td>${formatCurrency(transportAmount)}</td>
        <td>${formatCurrency(mealAmount)}</td>
        <td>${formatCurrency(lodging)}</td>
        <td>${formatCurrency(other)}</td>
        <td><strong>${formatCurrency(total)}</strong></td>
      </tr>
    `;
  });
}

function approvalAttachmentRow(attachment) {
  return `
    <div class="approval-attachment">
      <div>
        <strong>${escapeHtml(attachment.fileName || "Doklad")}</strong>
        <small>${escapeHtml(expenseKindLabel(attachment.expenseKind))} · ${escapeHtml(documentKindLabel(attachment.documentKind))}</small>
      </div>
      <div>
        <span>${escapeHtml(attachment.documentDate || "bez data")}</span>
        <strong>${formatCurrency(attachment.amount || 0)}</strong>
        <small>${escapeHtml(formatBytes(attachment.byteSize || 0))}</small>
      </div>
    </div>
  `;
}

function fuelLabel(value) {
  return FUEL_OPTIONS[value] || value || "-";
}

function fuelPriceModeLabel(value) {
  return FUEL_PRICE_MODE_OPTIONS[value] || "Dle vyhlášky";
}

async function decideApproval(action, approvalId) {
  const comment = action === "approved" ? "" : prompt("Poznámka pro žadatele:", "") || "";
  const response = await apiFetch(`/api/approval-requests/${approvalId}/decision`, {
    method: "POST",
    body: JSON.stringify({ action, comment }),
  });

  if (!response.ok) {
    approvalState.message = "Rozhodnutí se nepodařilo uložit.";
  } else {
    approvalState.message = "Rozhodnutí bylo uloženo.";
    approvalState.detail = null;
    approvalState.selectedApprovalId = null;
  }

  await loadApprovalData();
  renderApprovals();
  refreshNotificationBadge();
}

function renderList() {
  const query = normalize(els.search.value);
  const statusFilter = els.statusFilter.value;
  const orders = visibleOrders()
    .filter((order) => {
      const text = normalize([
        order.number,
        order.employee.name,
        order.trip.purpose,
        order.trip.destination,
        order.employee.costCenter,
      ].join(" "));
      const statusMatches = statusFilter === "all" || order.status === statusFilter;
      return statusMatches && (!query || text.includes(query));
    })
    .sort((a, b) => new Date(b.updatedAt) - new Date(a.updatedAt));

  els.list.innerHTML = "";

  if (!orders.length) {
    els.list.innerHTML = `<p class="note">Žádné položky pro aktuální filtr.</p>`;
    return;
  }

  orders.forEach((order) => {
    const calc = calculateOrder(order);
    const button = document.createElement("button");
    button.type = "button";
    button.className = `order-list-item ${order.id === state.selectedId ? "active" : ""}`;
    button.dataset.orderId = order.id;
    button.innerHTML = `
      <span class="order-list-title">
        <span>${escapeHtml(order.number)}</span>
        ${statusPill(order.status)}
      </span>
      <span class="order-list-meta">${escapeHtml(order.employee.name || "Bez zaměstnance")}</span>
      <span class="order-list-meta">${escapeHtml(order.trip.purpose || "Bez účelu")} · ${formatCurrency(calc.totalGross)}</span>
    `;
    els.list.append(button);
  });
}

function renderForm(options = {}) {
  const order = getSelectedOrder();
  const previousTabScrollLeft = document.querySelector(".tabbar")?.scrollLeft || 0;
  els.empty.hidden = Boolean(order);
  els.form.hidden = !order;

  if (!order) {
    els.form.innerHTML = "";
    els.print.innerHTML = "";
    return;
  }

  const calc = calculateOrder(order);
  els.form.innerHTML = `
    <div class="detail-column">
      <div class="form-header">
        <div>
          <h2>${escapeHtml(order.number)}</h2>
          <div class="header-meta">
            ${statusPill(order.status)}
            <span>Aktualizováno ${formatDateTime(order.updatedAt)}</span>
            <span>${escapeHtml(order.employee.name || "Bez zaměstnance")}</span>
          </div>
        </div>
        <div class="header-actions">
          ${workflowButtons(order)}
          <button type="button" class="secondary-btn" data-action="duplicate">Duplikovat</button>
          <button type="button" class="status-btn danger" data-action="delete">Smazat</button>
        </div>
      </div>

      ${overviewSection(order, calc)}
      ${tabsSection()}
      ${activeTabSection(order, calc)}
    </div>
  `;

  renderPrintSheet(order);
  restoreTabbarPosition(options.tabScrollLeft ?? previousTabScrollLeft, Boolean(options.revealActiveTab));
}

function overviewSection(order, calc) {
  const purpose = order.trip.purpose || "Bez účelu";
  const place = order.trip.destination || "Bez místa jednání";
  return `
    <section class="order-overview" aria-label="Souhrn cestovního příkazu">
      <div class="overview-main">
        <span class="overview-label">Aktuální příkaz</span>
        <strong data-overview="purpose">${escapeHtml(purpose)}</strong>
        <span data-overview="destination">${escapeHtml(place)}</span>
      </div>
      <div class="overview-stats">
        ${compactStat("Náhrady", "totalGross", formatCurrency(calc.totalGross))}
        ${compactStat("Doplatek", "balanceRounded", formatCurrency(calc.balanceRounded))}
        ${compactStat("Km", "totalKm", formatNumber(calc.totalKm, 0))}
        ${compactStat("Hodin", "totalHours", formatNumber(calc.totalHours, 2))}
      </div>
    </section>
  `;
}

function compactStat(label, key, value) {
  return `
    <div class="compact-stat">
      <span>${escapeHtml(label)}</span>
      <strong data-summary="${escapeHtml(key)}">${escapeHtml(value)}</strong>
    </div>
  `;
}

function tabsSection() {
  const buttons = TABS.map((tab, index) => {
    const isActive = tab.id === activeTab;
    return `
      <button type="button" class="tab-button ${isActive ? "active" : ""}" data-tab="${tab.id}" aria-selected="${isActive}">
        <span>${index + 1}</span>
        ${escapeHtml(tab.label)}
      </button>
    `;
  }).join("");

  return `<nav class="tabbar" aria-label="Kroky zadání">${buttons}</nav>`;
}

function restoreTabbarPosition(scrollLeft = 0, revealActiveTab = false) {
  requestAnimationFrame(() => {
    const tabbar = document.querySelector(".tabbar");
    if (!tabbar) return;
    tabbar.scrollLeft = scrollLeft;

    if (!revealActiveTab) return;
    const activeButton = tabbar.querySelector(`[data-tab="${activeTab}"]`);
    if (!activeButton) return;
    const targetLeft = activeButton.offsetLeft - Math.max(0, (tabbar.clientWidth - activeButton.offsetWidth) / 2);
    tabbar.scrollLeft = Math.max(0, targetLeft);
  });
}

function activeTabSection(order, calc) {
  if (activeTab === "employee") return employeeSection(order);
  if (activeTab === "settlement") return routesSection(order, calc);
  if (activeTab === "vehicle") return vehicleSection(order);
  if (activeTab === "documents") return documentsSection(order);
  if (activeTab === "summary") return summarySection(order, calc);
  if (activeTab === "rates") return ratesSection();
  return tripSection(order);
}

function employeeSection(order) {
  return `
    <section class="section">
      <div class="section-header">
        <h3>Zaměstnanec a organizace</h3>
      </div>
      <div class="section-body form-grid">
        ${field("Organizace", "employee.organization", order.employee.organization)}
        ${field("Jméno a titul", "employee.name", order.employee.name)}
        ${field("Osobní číslo", "employee.personalNo", order.employee.personalNo)}
        ${field("Středisko", "employee.costCenter", order.employee.costCenter)}
        ${field("Útvar", "employee.department", order.employee.department)}
        ${field("Telefon", "employee.phone", order.employee.phone)}
        ${field("Pracovní doba od", "employee.workStart", order.employee.workStart, "time")}
        ${field("Pracovní doba do", "employee.workEnd", order.employee.workEnd, "time")}
        ${field("Bydliště", "employee.address", order.employee.address, "text", "wide")}
      </div>
    </section>
  `;
}

function tripSection(order) {
  return `
    <section class="section">
      <div class="section-header">
        <h3>Cestovní příkaz</h3>
      </div>
      <div class="section-body form-grid">
        ${approverPickerField(order)}
        ${field("Počátek cesty", "trip.startAt", order.trip.startAt, "datetime-local")}
        ${field("Konec cesty", "trip.endAt", order.trip.endAt, "datetime-local")}
        ${field("Místo jednání", "trip.destination", order.trip.destination)}
        ${field("Účel cesty", "trip.purpose", order.trip.purpose, "text", "wide")}
        ${field("Navštívené firmy", "trip.visitedCompanies", order.trip.visitedCompanies, "text", "wide")}
        ${field("Spolucestující", "trip.companions", order.trip.companions, "text", "wide")}
        ${field("Předpokládané výdaje", "trip.expectedExpense", order.trip.expectedExpense, "number", "", "0.01")}
        ${field("Povolená záloha", "trip.advance", order.trip.advance, "number", "", "0.01")}
        ${field("Datum cestovní zprávy", "trip.reportDate", order.trip.reportDate, "date")}
      </div>
    </section>
  `;
}

function approverPickerField(order) {
  const approvers = currentDefaults?.approvers || [];
  if (!approvers.length) return "";
  const selectedId = order.approval?.approverUserId || currentDefaults?.approver?.id || approvers.find((approver) => approver.is_default)?.id || "";
  const options = approvers.map((approver) => {
    const label = `${approver.name || approver.display_name} (${approver.email || approver.login || ""})`;
    return `<option value="${escapeHtml(approver.id)}" ${approver.id === selectedId ? "selected" : ""}>${escapeHtml(label)}</option>`;
  });

  return `
    <label class="wide">
      <span>Schvalovatel tohoto příkazu</span>
      <select data-approver-picker>${options.join("")}</select>
    </label>
  `;
}

function vehicleSection(order) {
  const vehiclePicker = vehiclePickerField(order);
  const secondaryFuelOptions = { none: "Žádná", ...FUEL_OPTIONS };
  const secondaryFuelValue = order.vehicle.secondaryFuelType || "none";
  return `
    <section class="section">
      <div class="section-header">
        <h3>Vozidlo a PHM</h3>
      </div>
      <div class="section-body form-grid">
        ${vehiclePicker}
        ${field("Tovární značka / typ", "vehicle.brand", order.vehicle.brand)}
        ${field("SPZ", "vehicle.plate", order.vehicle.plate)}
        ${field("Obsah motoru", "vehicle.engineVolume", order.vehicle.engineVolume, "number", "", "1")}
        ${selectField("Druh PHM", "vehicle.fuelType", order.vehicle.fuelType, FUEL_OPTIONS)}
        ${field("Spotřeba na 100 km", "vehicle.consumption", order.vehicle.consumption, "number", "", "0.01")}
        ${selectField("Cena PHM použít", "vehicle.fuelPriceMode", order.vehicle.fuelPriceMode || "decree", FUEL_PRICE_MODE_OPTIONS)}
        ${field("Cena PHM", "vehicle.fuelPrice", order.vehicle.fuelPrice, "number", "", "0.01")}
        ${selectField("Druhá energie", "vehicle.secondaryFuelType", secondaryFuelValue, secondaryFuelOptions)}
        ${field("Spotřeba druhé energie na 100 km", "vehicle.secondaryConsumption", order.vehicle.secondaryConsumption, "number", "", "0.01")}
        ${selectField("Cena druhé energie použít", "vehicle.secondaryFuelPriceMode", order.vehicle.secondaryFuelPriceMode || "decree", FUEL_PRICE_MODE_OPTIONS)}
        ${field("Cena druhé energie", "vehicle.secondaryFuelPrice", order.vehicle.secondaryFuelPrice, "number", "", "0.01")}
        ${field("Základní náhrada Kč/km", "vehicle.basicKmRate", order.vehicle.basicKmRate, "number", "", "0.01")}
        <label>
          <span>Km cena vlastního vozidla</span>
          <input class="readonly-input" readonly data-summary-value="privateKmRate" value="${formatCurrency(getPrivateKmRate(order))} / km" />
        </label>
      </div>
    </section>
  `;
}

function vehiclePickerField(order) {
  const vehicles = currentDefaults?.vehicles || [];
  if (!vehicles.length) return "";

  const selectedId = vehicles.some((vehicle) => vehicle.id === order.vehicle.id) ? order.vehicle.id : "";
  const options = [`<option value="">Ručně zadané vozidlo</option>`].concat(vehicles.map((vehicle) => {
    const label = vehicleLabel(vehicle);
    return `<option value="${escapeHtml(vehicle.id)}" ${vehicle.id === selectedId ? "selected" : ""}>${escapeHtml(label)}</option>`;
  }));

  return `
    <label class="wide">
      <span>Použít uložené vozidlo</span>
      <select data-vehicle-picker>${options.join("")}</select>
    </label>
  `;
}

function vehicleLabel(vehicle) {
  const main = [vehicle.brand, vehicle.plate].filter(Boolean).join(" · ");
  if (main) return vehicle.is_default ? `${main} (výchozí)` : main;
  return vehicle.is_default ? "Výchozí vozidlo" : "Uložené vozidlo";
}

function applyVehicleToOrder(order, vehicleId) {
  const vehicle = (currentDefaults?.vehicles || []).find((item) => item.id === vehicleId);
  if (!vehicle) {
    order.vehicle.id = "";
    return;
  }

  const fuelType = FUEL_OPTIONS[vehicle.fuelType] ? vehicle.fuelType : "ba95";
  const secondaryFuelType = FUEL_OPTIONS[vehicle.secondaryFuelType] ? vehicle.secondaryFuelType : "";
  order.vehicle = {
    ...order.vehicle,
    id: vehicle.id || "",
    brand: vehicle.brand || "",
    plate: vehicle.plate || "",
    engineVolume: vehicle.engineVolume || "",
    fuelType,
    consumption: vehicle.consumption || 0,
    fuelPriceMode: "decree",
    fuelPrice: state?.rates?.fuelPrices?.[fuelType] || DEFAULT_RATES.fuelPrices[fuelType] || 0,
    secondaryFuelType,
    secondaryConsumption: vehicle.secondaryConsumption || 0,
    secondaryFuelPriceMode: "decree",
    secondaryFuelPrice: secondaryFuelType ? state?.rates?.fuelPrices?.[secondaryFuelType] || DEFAULT_RATES.fuelPrices[secondaryFuelType] || 0 : 0,
  };
}

function applyApproverToOrder(order, approverId) {
  const approver = (currentDefaults?.approvers || []).find((item) => item.id === approverId);
  order.approval = {
    approverUserId: approver?.id || "",
    approverName: approver?.name || approver?.display_name || "",
  };
}

function routesSection(order, calc) {
  const cards = order.routeLines.map((line, index) => routeCard(line, calc.lines[index], index)).join("");
  return `
    <section class="section">
      <div class="section-header">
        <h3>Vyúčtování pracovní cesty</h3>
        <button type="button" class="secondary-btn" data-action="add-line">Přidat řádek</button>
      </div>
      <div class="section-body">
        <div class="route-stack">${cards}</div>
        <div class="helper-row">
          <button type="button" class="secondary-btn" data-action="sync-trip-dates">Převzít první a poslední čas</button>
        </div>
      </div>
    </section>
  `;
}

function routeCard(line, lineCalc, index) {
  return `
    <article class="route-card" data-line-id="${escapeHtml(line.id)}">
      <div class="route-card-head">
        <div>
          <span class="route-index">Úsek ${index + 1}</span>
          <strong>${escapeHtml(routeTitle(line))}</strong>
        </div>
        <div class="route-total">
          <span>Celkem</span>
          <strong data-line-total>${formatCurrency(lineCalc.total)}</strong>
        </div>
        <button class="table-icon-btn" data-remove-line type="button" title="Odebrat řádek" aria-label="Odebrat řádek">×</button>
      </div>
      <div class="route-grid">
        ${lineField("Odjezd", "startAt", line.startAt, "datetime-local")}
        ${lineField("Odkud", "from", line.from)}
        ${lineField("Kam", "to", line.to)}
        ${lineField("Příjezd", "endAt", line.endAt, "datetime-local")}
        ${lineField("Firma / místo", "company", line.company)}
        ${lineField("Účel", "purpose", line.purpose)}
        ${lineField("Kilometry", "km", line.km, "number", "1")}
        <label>
          <span>Doprava</span>
          ${lineTransportSelect(line.transport)}
        </label>
      </div>
      <div class="route-costs">
        ${lineField("Jízdné", "fare", line.fare, "number", "0.01")}
        ${lineField("Nocležné", "lodging", line.lodging, "number", "0.01")}
        ${lineField("Vedlejší výdaje", "other", line.other, "number", "0.01")}
        ${lineField("Jídla zdarma", "freeMeals", line.freeMeals, "number", "1")}
      </div>
    </article>
  `;
}

function routeTitle(line) {
  if (line.from || line.to) return `${line.from || "Odkud"} → ${line.to || "Kam"}`;
  return "Nový úsek cesty";
}

function lineField(label, fieldName, value, type = "text", step = null) {
  const stepAttr = step ? `step="${escapeHtml(step)}"` : "";
  const numberAttrs = type === "number" ? `min="0" inputmode="decimal"` : "";
  return `
    <label>
      <span>${escapeHtml(label)}</span>
      <input data-line-field="${escapeHtml(fieldName)}" type="${type}" ${numberAttrs} ${stepAttr} value="${escapeHtml(inputValue(value))}" />
    </label>
  `;
}

function lineTransportSelect(value) {
  const options = Object.entries(TRANSPORT_OPTIONS).map(([key, label]) => {
    return `<option value="${key}" ${key === value ? "selected" : ""}>${label}</option>`;
  });
  return `<select data-line-field="transport">${options.join("")}</select>`;
}

function documentsSection(order) {
  order.attachments = Array.isArray(order.attachments) ? order.attachments : [];
  const attachmentCards = order.attachments.length
    ? order.attachments.map((attachment) => attachmentCard(attachment)).join("")
    : `<div class="empty-inline">Zatím bez přiložených dokladů.</div>`;

  return `
    <section class="section">
      <div class="section-header">
        <h3>Doklady a přílohy</h3>
      </div>
      <div class="section-body">
        <div class="document-upload-grid">
          <label>
            <span>Typ výdaje</span>
            <select data-attachment-meta="expenseKind">${optionsHtml(EXPENSE_KIND_OPTIONS, "fuel")}</select>
          </label>
          <label>
            <span>Typ dokladu</span>
            <select data-attachment-meta="documentKind">${optionsHtml(DOCUMENT_KIND_OPTIONS, "receipt")}</select>
          </label>
          <label>
            <span>Datum dokladu</span>
            <input data-attachment-meta="documentDate" type="date" value="${todayString()}" />
          </label>
          <label>
            <span>Částka na dokladu</span>
            <input data-attachment-meta="amount" type="number" min="0" step="0.01" inputmode="decimal" value="0" />
          </label>
          <label class="wide">
            <span>Popis</span>
            <input data-attachment-meta="description" type="text" placeholder="Např. tankování, hotel, parkovné" />
          </label>
          <label class="wide file-picker">
            <span>Přiložit soubor</span>
            <input data-attachment-file type="file" multiple accept="image/*,.pdf,.txt,.csv,.doc,.docx,.xls,.xlsx" />
          </label>
        </div>
        <div class="attachment-list">${attachmentCards}</div>
      </div>
    </section>
  `;
}

function attachmentCard(attachment) {
  const download = attachment.dataUrl
    ? `<a class="secondary-btn" href="${escapeHtml(attachment.dataUrl)}" download="${escapeHtml(attachment.fileName || "doklad")}">Otevřít</a>`
    : "";
  return `
    <article class="attachment-card" data-attachment-id="${escapeHtml(attachment.id)}">
      <div>
        <strong>${escapeHtml(attachment.fileName || "Doklad")}</strong>
        <p>${escapeHtml(expenseKindLabel(attachment.expenseKind))} · ${escapeHtml(documentKindLabel(attachment.documentKind))}</p>
        <small>
          ${escapeHtml(attachment.documentDate || "bez data")}
          · ${escapeHtml(formatCurrency(attachment.amount || 0))}
          · ${escapeHtml(formatBytes(attachment.byteSize || 0))}
        </small>
        ${attachment.description ? `<p>${escapeHtml(attachment.description)}</p>` : ""}
      </div>
      <div class="attachment-actions">
        ${download}
        <button class="table-icon-btn" data-remove-attachment type="button" title="Odebrat doklad" aria-label="Odebrat doklad">×</button>
      </div>
    </article>
  `;
}

function summarySection(order, calc) {
  return `
    <section class="section">
      <div class="section-header">
        <h3>Souhrn náhrad</h3>
      </div>
      <div class="section-body summary-layout">
        <div class="kpi-grid">
          ${kpi("Ujeto km", "totalKm", formatNumber(calc.totalKm, 0))}
          ${kpi("Doba cest", "totalHours", `${formatNumber(calc.totalHours, 2)} h`)}
          ${kpi("Hrubé náhrady", "totalGross", formatCurrency(calc.totalGross))}
          ${kpi("Doplatek / přeplatek", "balanceRounded", formatCurrency(calc.balanceRounded))}
        </div>
        <table class="calc-table">
          <tbody>
            <tr><th>Cestovné a PHM</th><td data-summary="totalTransport">${formatCurrency(calc.totalTransport)}</td></tr>
            <tr><th>Stravné</th><td data-summary="totalMeals">${formatCurrency(calc.totalMeals)}</td></tr>
            <tr><th>Nocležné</th><td data-summary="totalLodging">${formatCurrency(calc.totalLodging)}</td></tr>
            <tr><th>Vedlejší výdaje</th><td data-summary="totalOther">${formatCurrency(calc.totalOther)}</td></tr>
            <tr><th>Celkem</th><td data-summary="totalGross">${formatCurrency(calc.totalGross)}</td></tr>
            <tr><th>Záloha</th><td data-summary="advance">${formatCurrency(calc.advance)}</td></tr>
            <tr><th>K výplatě / vrácení</th><td><strong data-summary="balanceRounded">${formatCurrency(calc.balanceRounded)}</strong></td></tr>
          </tbody>
        </table>
      </div>
    </section>
  `;
}

function ratesSection() {
  const bands = state.rates.mealBands.map((band, index) => `
    <tr>
      <td>${escapeHtml(band.label)}</td>
      <td><input data-rate-path="mealBands.${index}.amount" type="number" min="0" step="1" value="${numberValue(band.amount)}" /></td>
      <td><input data-rate-path="mealBands.${index}.reductionPct" type="number" min="0" max="100" step="1" value="${numberValue(band.reductionPct)}" /></td>
    </tr>
  `).join("");
  const monitor = rateMonitorState.monitor;
  const status = monitor?.effectiveStatus || monitor?.status || "unknown";
  const message = rateMonitorState.message || monitor?.message || "Kontrola sazeb ještě neproběhla.";
  const sourceUrl = monitor?.sourceUrl || state.rates.sourceUrl;
  const checkButton = API_ENABLED && can("admin")
    ? `<button type="button" class="secondary-btn" data-action="check-rates">Zkontrolovat vyhlášku</button>`
    : "";

  return `
    <section class="section">
      <div class="section-header">
        <h3>Sazby</h3>
        <div class="section-actions">
          ${checkButton}
          <button type="button" class="secondary-btn" data-action="reset-rates">Obnovit 2026</button>
        </div>
      </div>
      <div class="section-body summary-layout">
        <div class="rate-monitor">
          <div>
            <span class="monitor-pill ${monitorStatusClass(status)}">${escapeHtml(rateMonitorLabel(status))}</span>
            <h4>${escapeHtml(state.rates.regulationNo || "Vyhláška")}</h4>
            <p>${escapeHtml(message)}</p>
          </div>
          <div class="rate-source">
            <span>Platnost od ${escapeHtml(state.rates.validFrom || "")}</span>
            <span>Kontrola ${escapeHtml(formatDateTime(monitor?.lastCheckedAt || state.rates.checkedAt) || "neproběhla")}</span>
            ${sourceUrl ? `<a href="${escapeHtml(sourceUrl)}" target="_blank" rel="noreferrer">Zdroj MPSV</a>` : ""}
          </div>
        </div>
        <div class="grid grid-2">
          ${field("Platnost od", "rates.validFrom", state.rates.validFrom, "date", "", null, true)}
          ${field("Základní náhrada Kč/km", "rates.basicKmRate", state.rates.basicKmRate, "number", "", "0.01", true)}
          ${rateField("Benzin 95", "fuelPrices.ba95", state.rates.fuelPrices.ba95)}
          ${rateField("Benzin 98", "fuelPrices.ba98", state.rates.fuelPrices.ba98)}
          ${rateField("Nafta", "fuelPrices.diesel", state.rates.fuelPrices.diesel)}
          ${rateField("Elektřina", "fuelPrices.electricity", state.rates.fuelPrices.electricity)}
        </div>
        <div class="table-wrap">
          <table class="calc-table">
            <thead>
              <tr><th>Pásmo</th><th>Sazba Kč</th><th>Krácení za jídlo %</th></tr>
            </thead>
            <tbody>${bands}</tbody>
          </table>
        </div>
      </div>
    </section>
  `;
}

function kpi(label, key, value) {
  return `<div class="kpi"><span>${escapeHtml(label)}</span><strong data-summary="${escapeHtml(key)}">${escapeHtml(value)}</strong></div>`;
}

function field(label, path, value, type = "text", className = "", step = null, rate = false) {
  const attr = rate ? `data-rate-path="${escapeHtml(path.replace(/^rates\./, ""))}"` : `data-path="${escapeHtml(path)}"`;
  const stepAttr = step ? `step="${escapeHtml(step)}"` : "";
  const inputMode = type === "number" ? `inputmode="decimal"` : "";
  return `
    <label class="${escapeHtml(className)}">
      <span>${escapeHtml(label)}</span>
      <input ${attr} type="${type}" ${stepAttr} ${inputMode} value="${escapeHtml(inputValue(value))}" />
    </label>
  `;
}

function rateField(label, path, value) {
  return `
    <label>
      <span>${escapeHtml(label)}</span>
      <input data-rate-path="${escapeHtml(path)}" type="number" min="0" step="0.01" inputmode="decimal" value="${numberValue(value)}" />
    </label>
  `;
}

function selectField(label, path, value, options) {
  return `
    <label>
      <span>${escapeHtml(label)}</span>
      <select data-path="${escapeHtml(path)}">${optionsHtml(options, value)}</select>
    </label>
  `;
}

function optionsHtml(options, value) {
  return Object.entries(options).map(([key, text]) => {
    return `<option value="${key}" ${key === value ? "selected" : ""}>${escapeHtml(text)}</option>`;
  }).join("");
}

function workflowButtons(order) {
  const buttons = [];
  if (order.status === "draft") {
    buttons.push(button("submit", "Předat ke schválení"));
  }
  if (order.status === "submitted") {
    buttons.push(button("approve", "Schválit"));
    buttons.push(button("return", "Vrátit"));
    buttons.push(button("reject", "Zamítnout", "danger"));
  }
  if (order.status === "approved") {
    buttons.push(button("settlement", "Otevřít vyúčtování"));
    buttons.push(button("return", "Vrátit"));
  }
  if (order.status === "settlement") {
    buttons.push(button("close", "Uzavřít"));
    buttons.push(button("return", "Vrátit"));
  }
  if (order.status === "rejected" || order.status === "closed") {
    buttons.push(button("reopen", "Znovu otevřít"));
  }
  return buttons.join("");
}

function button(action, label, extraClass = "") {
  return `<button type="button" class="status-btn ${extraClass}" data-action="${action}">${label}</button>`;
}

function statusPill(status) {
  const found = STATUS_OPTIONS.find((item) => item.value === status);
  const label = found?.label || status;
  return `<span class="status-pill status-${escapeHtml(status)}">${escapeHtml(label)}</span>`;
}

async function handleFormInput(event) {
  const order = getSelectedOrder();
  if (!order) return;

  const attachmentInput = event.target.closest("[data-attachment-file]");
  if (attachmentInput) {
    if (event.type !== "change") return;
    await addAttachmentFiles(order, attachmentInput);
    attachmentInput.value = "";
    touch(order);
    saveState();
    renderForm();
    renderList();
    return;
  }

  const lineField = event.target.closest("[data-line-field]");
  if (lineField) {
    const row = lineField.closest("[data-line-id]");
    const line = order.routeLines.find((item) => item.id === row.dataset.lineId);
    if (!line) return;
    line[lineField.dataset.lineField] = parseInputValue(lineField);
    touch(order);
    saveState();
    refreshDerivedUi(order);
    renderList();
    return;
  }

  const vehiclePicker = event.target.closest("[data-vehicle-picker]");
  if (vehiclePicker) {
    applyVehicleToOrder(order, vehiclePicker.value);
    touch(order);
    saveState();
    renderForm();
    renderList();
    return;
  }

  const approverPicker = event.target.closest("[data-approver-picker]");
  if (approverPicker) {
    applyApproverToOrder(order, approverPicker.value);
    touch(order);
    saveState();
    renderList();
    return;
  }

  const pathField = event.target.closest("[data-path]");
  if (pathField) {
    setByPath(order, pathField.dataset.path, parseInputValue(pathField));
    if (pathField.dataset.path.startsWith("vehicle.") && pathField.dataset.path !== "vehicle.fuelPrice" && pathField.dataset.path !== "vehicle.basicKmRate") {
      order.vehicle.id = "";
    }
    if (pathField.dataset.path === "vehicle.fuelPriceMode" && order.vehicle.fuelPriceMode === "decree") {
      order.vehicle.fuelPrice = state.rates.fuelPrices[order.vehicle.fuelType] || 0;
      renderForm();
    }
    if (pathField.dataset.path === "vehicle.secondaryFuelPriceMode" && order.vehicle.secondaryFuelPriceMode === "decree") {
      order.vehicle.secondaryFuelPrice = order.vehicle.secondaryFuelType ? state.rates.fuelPrices[order.vehicle.secondaryFuelType] || 0 : 0;
      renderForm();
    }
    if (pathField.dataset.path === "vehicle.fuelType") {
      if ((order.vehicle.fuelPriceMode || "decree") === "decree") {
        order.vehicle.fuelPrice = state.rates.fuelPrices[order.vehicle.fuelType] || 0;
      }
      renderForm();
    }
    if (pathField.dataset.path === "vehicle.secondaryFuelType") {
      if (order.vehicle.secondaryFuelType === "none") order.vehicle.secondaryFuelType = "";
      if ((order.vehicle.secondaryFuelPriceMode || "decree") === "decree") {
        order.vehicle.secondaryFuelPrice = order.vehicle.secondaryFuelType ? state.rates.fuelPrices[order.vehicle.secondaryFuelType] || 0 : 0;
      }
      if (!order.vehicle.secondaryFuelType) order.vehicle.secondaryConsumption = 0;
      renderForm();
    }
    touch(order);
    saveState();
    refreshDerivedUi(order);
    renderList();
    return;
  }

  const rateField = event.target.closest("[data-rate-path]");
  if (rateField) {
    setByPath(state.rates, rateField.dataset.ratePath, parseInputValue(rateField));
    if (rateField.dataset.ratePath === "basicKmRate") {
      order.vehicle.basicKmRate = state.rates.basicKmRate;
    }
    if (rateField.dataset.ratePath.startsWith("fuelPrices.")) {
      if ((order.vehicle.fuelPriceMode || "decree") === "decree") {
        order.vehicle.fuelPrice = state.rates.fuelPrices[order.vehicle.fuelType] || 0;
      }
      if ((order.vehicle.secondaryFuelPriceMode || "decree") === "decree" && order.vehicle.secondaryFuelType) {
        order.vehicle.secondaryFuelPrice = state.rates.fuelPrices[order.vehicle.secondaryFuelType] || 0;
      }
    }
    touch(order);
    saveState();
    refreshDerivedUi(order);
    renderList();
  }
}

async function handleFormClick(event) {
  const profileAction = event.target.closest("[data-profile-action]");
  if (profileAction) {
    if (profileAction.dataset.profileAction === "save-profile") {
      await saveProfileFromForm();
    } else if (profileAction.dataset.profileAction === "add-vehicle") {
      addAdminVehicleCard();
    }
    return;
  }

  const adminAction = event.target.closest("[data-admin-action]");
  if (adminAction) {
    if (adminAction.dataset.adminAction === "save-user") {
      await saveAdminUserFromForm();
    } else if (adminAction.dataset.adminAction === "add-vehicle") {
      addAdminVehicleCard();
    }
    return;
  }

  const removeAdminVehicle = event.target.closest("[data-admin-remove-vehicle]");
  if (removeAdminVehicle) {
    removeAdminVehicleCard(removeAdminVehicle);
    return;
  }

  const approvalAction = event.target.closest("[data-approval-action]");
  if (approvalAction) {
    const action = approvalAction.dataset.approvalAction;
    if (action === "refresh") {
      await loadApprovalData();
      renderApprovals();
    } else if (action === "detail") {
      await loadApprovalDetail(approvalAction.dataset.approvalId);
      renderApprovals();
    } else if (action === "back") {
      approvalState.detail = null;
      approvalState.selectedApprovalId = null;
      renderApprovals();
    } else {
      await decideApproval(action, approvalAction.dataset.approvalId);
    }
    return;
  }

  const tabBtn = event.target.closest("[data-tab]");
  if (tabBtn) {
    const tabbar = tabBtn.closest(".tabbar");
    activeTab = tabBtn.dataset.tab;
    renderForm({
      tabScrollLeft: tabbar?.scrollLeft || 0,
      revealActiveTab: true,
    });
    return;
  }

  const order = getSelectedOrder();
  if (!order) return;

  const removeBtn = event.target.closest("[data-remove-line]");
  if (removeBtn) {
    const row = removeBtn.closest("[data-line-id]");
    if (order.routeLines.length === 1) {
      order.routeLines = [createBlankLine()];
    } else {
      order.routeLines = order.routeLines.filter((line) => line.id !== row.dataset.lineId);
    }
    touch(order);
    saveState();
    render();
    return;
  }

  const removeAttachmentBtn = event.target.closest("[data-remove-attachment]");
  if (removeAttachmentBtn) {
    const card = removeAttachmentBtn.closest("[data-attachment-id]");
    order.attachments = (order.attachments || []).filter((attachment) => attachment.id !== card?.dataset.attachmentId);
    touch(order);
    saveState();
    renderForm();
    renderList();
    return;
  }

  const actionBtn = event.target.closest("[data-action]");
  if (!actionBtn) return;

  const action = actionBtn.dataset.action;
  if (action === "add-line") {
    order.routeLines.push(createBlankLine());
  } else if (action === "sync-trip-dates") {
    syncTripDates(order);
  } else if (action === "check-rates") {
    await refreshRateMonitor();
    renderForm();
    return;
  } else if (action === "reset-rates") {
    state.rates = structuredClone(DEFAULT_RATES);
    order.vehicle.basicKmRate = state.rates.basicKmRate;
    order.vehicle.fuelPriceMode = "decree";
    order.vehicle.secondaryFuelPriceMode = "decree";
    order.vehicle.fuelPrice = state.rates.fuelPrices[order.vehicle.fuelType] || 0;
    order.vehicle.secondaryFuelPrice = order.vehicle.secondaryFuelType ? state.rates.fuelPrices[order.vehicle.secondaryFuelType] || 0 : 0;
  } else if (action === "duplicate") {
    duplicateOrder(order);
    return;
  } else if (action === "delete") {
    deleteOrder(order);
    return;
  } else if (action === "submit" && API_ENABLED) {
    const submitted = await submitOrderForApproval(order);
    if (!submitted) return;
    applyWorkflowAction(order, action);
  } else {
    applyWorkflowAction(order, action);
  }

  touch(order);
  saveState();
  render();
}

async function submitOrderForApproval(order) {
  if (!ownsOrder(order)) {
    alert("Tento cestovní příkaz nemůže předat jiný uživatel než jeho vlastník.");
    return false;
  }
  const calculation = calculateOrder(order);
  try {
    const response = await apiFetch("/api/travel-orders/submit", {
      method: "POST",
      body: JSON.stringify({ order, calculation }),
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      alert(payload.error || "Předání ke schválení se nepodařilo.");
      return false;
    }
    await refreshNotificationBadge();
    return true;
  } catch {
    alert("Předání ke schválení se nepodařilo.");
    return false;
  }
}

function applyWorkflowAction(order, action) {
  const nextStatus = {
    submit: "submitted",
    approve: "approved",
    settlement: "settlement",
    close: "closed",
    return: "draft",
    reject: "rejected",
    reopen: "draft",
  }[action];

  if (!nextStatus) return;
  order.status = nextStatus;
  if (action === "settlement") activeTab = "settlement";
  if (action === "close") activeTab = "summary";
  order.history.push({
    at: new Date().toISOString(),
    status: nextStatus,
    note: workflowNote(action),
  });
}

function workflowNote(action) {
  return {
    submit: "Předáno ke schválení",
    approve: "Schváleno",
    settlement: "Otevřeno vyúčtování",
    close: "Uzavřeno",
    return: "Vráceno k doplnění",
    reject: "Zamítnuto",
    reopen: "Znovu otevřeno",
  }[action] || "Změna stavu";
}

function duplicateOrder(order) {
  const clone = structuredClone(order);
  clone.id = newId();
  clone.number = generateNumber();
  clone.status = "draft";
  clone.createdAt = new Date().toISOString();
  clone.updatedAt = clone.createdAt;
  clone.history = [{ at: clone.createdAt, status: "draft", note: "Duplikováno" }];
  clone.routeLines = clone.routeLines.map((line) => ({ ...line, id: newId() }));
  clone.attachments = (clone.attachments || []).map((attachment) => ({ ...attachment, id: newId() }));
  stampOrderOwner(clone);
  state.orders.unshift(clone);
  state.selectedId = clone.id;
  saveState();
  render();
}

function deleteOrder(order) {
  if (!ownsOrder(order)) {
    alert("Tento cestovní příkaz nepatří přihlášenému uživateli.");
    return;
  }
  const ok = confirm(`Smazat ${order.number}?`);
  if (!ok) return;
  state.orders = state.orders.filter((item) => item.id !== order.id);
  const remainingOwnOrders = visibleOrders();
  state.selectedId = remainingOwnOrders[0]?.id || null;
  if (!remainingOwnOrders.length) {
    const fresh = createBlankOrder();
    state.orders.push(fresh);
    state.selectedId = fresh.id;
  }
  saveState();
  render();
}

function syncTripDates(order) {
  const starts = order.routeLines.map((line) => line.startAt).filter(Boolean).sort();
  const ends = order.routeLines.map((line) => line.endAt).filter(Boolean).sort();
  if (starts[0]) order.trip.startAt = starts[0];
  if (ends[ends.length - 1]) order.trip.endAt = ends[ends.length - 1];
}

async function addAttachmentFiles(order, input) {
  const files = Array.from(input.files || []);
  if (!files.length) return;
  const section = input.closest(".section");
  const meta = attachmentMetaFromSection(section);
  order.attachments = Array.isArray(order.attachments) ? order.attachments : [];

  for (const file of files) {
    if (file.size > 10 * 1024 * 1024) {
      alert(`Soubor ${file.name} je větší než 10 MB.`);
      continue;
    }
    const dataUrl = await fileToDataUrl(file);
    order.attachments.push({
      id: newId(),
      fileName: file.name,
      contentType: file.type || "application/octet-stream",
      byteSize: file.size,
      dataUrl,
      ...meta,
    });
  }
}

function attachmentMetaFromSection(section) {
  const value = (field) => section?.querySelector(`[data-attachment-meta="${field}"]`)?.value || "";
  return {
    expenseKind: value("expenseKind") || "other",
    documentKind: value("documentKind") || "receipt",
    documentDate: value("documentDate") || todayString(),
    amount: number(value("amount")),
    description: value("description"),
  };
}

function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.addEventListener("load", () => resolve(reader.result));
    reader.addEventListener("error", () => reject(reader.error));
    reader.readAsDataURL(file);
  });
}

function refreshDerivedUi(order) {
  const calc = calculateOrder(order);
  document.querySelectorAll("[data-line-id]").forEach((row) => {
    const line = order.routeLines.find((item) => item.id === row.dataset.lineId);
    const index = order.routeLines.indexOf(line);
    const target = row.querySelector("[data-line-total]");
    if (target && calc.lines[index]) {
      target.textContent = formatCurrency(calc.lines[index].total);
    }
  });

  updateSummaryValues(order, calc);
  updateOverview(order);

  renderPrintSheet(order);
}

function updateSummaryValues(order, calc) {
  const values = {
    totalKm: formatNumber(calc.totalKm, 0),
    totalHours: formatNumber(calc.totalHours, 2),
    totalGross: formatCurrency(calc.totalGross),
    balanceRounded: formatCurrency(calc.balanceRounded),
    totalTransport: formatCurrency(calc.totalTransport),
    totalMeals: formatCurrency(calc.totalMeals),
    totalLodging: formatCurrency(calc.totalLodging),
    totalOther: formatCurrency(calc.totalOther),
    advance: formatCurrency(calc.advance),
  };

  Object.entries(values).forEach(([key, value]) => {
    document.querySelectorAll(`[data-summary="${key}"]`).forEach((el) => {
      el.textContent = value;
    });
  });

  document.querySelectorAll('[data-summary-value="privateKmRate"]').forEach((el) => {
    el.value = `${formatCurrency(getPrivateKmRate(order))} / km`;
  });
}

function updateOverview(order) {
  const purpose = document.querySelector('[data-overview="purpose"]');
  const destination = document.querySelector('[data-overview="destination"]');
  if (purpose) purpose.textContent = order.trip.purpose || "Bez účelu";
  if (destination) destination.textContent = order.trip.destination || "Bez místa jednání";
}

function calculateOrder(order) {
  const lines = order.routeLines.map((line) => calculateLine(order, line));
  const totalKm = sum(lines, "km");
  const totalHours = sum(lines, "hours");
  const totalMeals = sum(lines, "meal");
  const totalFare = sum(lines, "fare");
  const totalPrivateComp = sum(lines, "privateComp");
  const totalTransport = totalFare + totalPrivateComp;
  const totalLodging = sum(lines, "lodging");
  const totalOther = sum(lines, "other");
  const totalGross = totalTransport + totalMeals + totalLodging + totalOther;
  const advance = number(order.trip.advance);
  const balance = totalGross - advance;

  return {
    lines,
    totalKm,
    totalHours,
    totalMeals,
    totalFare,
    totalPrivateComp,
    totalTransport,
    totalLodging,
    totalOther,
    totalGross,
    advance,
    balance,
    balanceRounded: Math.round(balance),
  };
}

function calculateLine(order, line) {
  const hours = hoursBetween(line.startAt, line.endAt);
  const km = number(line.km);
  const fare = number(line.fare);
  const lodging = number(line.lodging);
  const other = number(line.other);
  const meal = mealAllowance(hours, number(line.freeMeals));
  const privateComp = line.transport === "private_car" ? km * getPrivateKmRate(order) : 0;
  const total = fare + lodging + other + meal.amount + privateComp;

  return {
    hours,
    km,
    fare,
    lodging,
    other,
    meal: meal.amount,
    mealBase: meal.base,
    mealReduction: meal.reduction,
    privateComp,
    total,
  };
}

function mealAllowance(hours, freeMeals) {
  const band = getMealBand(hours);
  if (!band) return { base: 0, reduction: 0, amount: 0 };
  const meals = Math.max(0, Math.min(3, Math.round(freeMeals || 0)));
  const reduction = Math.min(band.amount, band.amount * (band.reductionPct / 100) * meals);
  return {
    base: band.amount,
    reduction,
    amount: Math.max(0, Math.round(band.amount - reduction)),
  };
}

function getMealBand(hours) {
  if (hours < 5) return null;
  if (hours <= 12) return state.rates.mealBands[0];
  if (hours <= 18) return state.rates.mealBands[1];
  return state.rates.mealBands[2];
}

function getPrivateKmRate(order) {
  const basic = number(order.vehicle.basicKmRate || state.rates.basicKmRate);
  const consumption = number(order.vehicle.consumption);
  const fuelPrice = number(order.vehicle.fuelPrice || state.rates.fuelPrices[order.vehicle.fuelType]);
  const secondaryFuelType = order.vehicle.secondaryFuelType;
  const secondaryConsumption = secondaryFuelType ? number(order.vehicle.secondaryConsumption) : 0;
  const secondaryFuelPrice = secondaryFuelType ? number(order.vehicle.secondaryFuelPrice || state.rates.fuelPrices[secondaryFuelType]) : 0;
  return basic + (consumption / 100) * fuelPrice + (secondaryConsumption / 100) * secondaryFuelPrice;
}

function createBlankOrder() {
  const now = new Date().toISOString();
  const defaults = orderDefaults();
  return stampOrderOwner({
    id: newId(),
    number: generateNumber(),
    status: "draft",
    createdAt: now,
    updatedAt: now,
    employee: { ...defaults.employee },
    trip: {
      purpose: "",
      destination: "",
      visitedCompanies: "",
      companions: "",
      startAt: "",
      endAt: "",
      expectedExpense: 0,
      advance: 0,
      reportDate: todayString(),
    },
    approval: { ...defaults.approval },
    vehicle: { ...defaults.vehicle },
    routeLines: [createBlankLine(defaults.routeTransport)],
    attachments: [],
    history: [{ at: now, status: "draft", note: "Založeno" }],
  });
}

function orderDefaults() {
  const employee = currentDefaults?.employee || {};
  const vehicle = currentDefaults?.vehicle || {};
  const route = currentDefaults?.route || {};
  const approver = currentDefaults?.approver || (currentDefaults?.approvers || []).find((item) => item.is_default) || {};
  const fuelType = FUEL_OPTIONS[vehicle.fuelType] ? vehicle.fuelType : "ba95";
  const secondaryFuelType = FUEL_OPTIONS[vehicle.secondaryFuelType] ? vehicle.secondaryFuelType : "";

  return {
    employee: {
      organization: employee.organization || "",
      name: employee.name || currentUser?.display_name || "",
      personalNo: employee.personalNo || "",
      address: employee.address || "",
      costCenter: employee.costCenter || formatCostCenter(employee),
      department: employee.department || "",
      phone: employee.phone || "",
      workStart: employee.workStart || "08:00",
      workEnd: employee.workEnd || "16:30",
    },
    vehicle: {
      id: vehicle.id || "",
      brand: vehicle.brand || "",
      plate: vehicle.plate || "",
      engineVolume: vehicle.engineVolume || "",
      fuelType,
      consumption: vehicle.consumption || 0,
      fuelPriceMode: "decree",
      fuelPrice: state?.rates?.fuelPrices?.[fuelType] || DEFAULT_RATES.fuelPrices[fuelType] || 0,
      secondaryFuelType,
      secondaryConsumption: vehicle.secondaryConsumption || 0,
      secondaryFuelPriceMode: "decree",
      secondaryFuelPrice: secondaryFuelType ? state?.rates?.fuelPrices?.[secondaryFuelType] || DEFAULT_RATES.fuelPrices[secondaryFuelType] || 0 : 0,
      basicKmRate: state?.rates?.basicKmRate || DEFAULT_RATES.basicKmRate,
    },
    approval: {
      approverUserId: approver.id || "",
      approverName: approver.name || approver.display_name || "",
    },
    routeTransport: TRANSPORT_OPTIONS[route.transport] ? route.transport : "private_car",
  };
}

function formatCostCenter(employee) {
  const code = employee.costCenterCode || "";
  const name = employee.costCenterName || "";
  return [code, name].filter(Boolean).join(" - ");
}

function applyDefaultsToExistingDraft() {
  const order = getSelectedOrder();
  if (!order || order.status !== "draft" || !currentDefaults) return false;

  const hasTravelData = Boolean(
    order.trip?.purpose ||
    order.trip?.destination ||
    order.routeLines?.some((line) => line.startAt || line.from || line.to || line.endAt || Number(line.km || 0) > 0)
  );
  if (hasTravelData) return false;

  return applyMissingDefaults(order);
}

function applyMissingDefaults(order) {
  const defaults = orderDefaults();
  let changed = false;
  changed = fillMissing(order.employee, defaults.employee, ["organization", "name", "personalNo", "address", "costCenter", "department", "phone", "workStart", "workEnd"]) || changed;
  changed = fillMissing(order.vehicle, defaults.vehicle, ["id", "brand", "plate", "engineVolume", "fuelType", "consumption", "fuelPriceMode", "fuelPrice", "secondaryFuelType", "secondaryConsumption", "secondaryFuelPriceMode", "secondaryFuelPrice", "basicKmRate"]) || changed;
  order.approval = order.approval || {};
  changed = fillMissing(order.approval, defaults.approval, ["approverUserId", "approverName"]) || changed;
  if (!Array.isArray(order.attachments)) {
    order.attachments = [];
    changed = true;
  }

  const firstLine = order.routeLines?.[0];
  if (firstLine && (!firstLine.transport || firstLine.transport === "private_car") && firstLine.transport !== defaults.routeTransport) {
    firstLine.transport = defaults.routeTransport;
    changed = true;
  }

  if (changed) touch(order);
  return changed;
}

function fillMissing(target, source, fields) {
  if (!target || !source) return false;
  let changed = false;
  fields.forEach((fieldName) => {
    const current = target[fieldName];
    const incoming = source[fieldName];
    if (incoming === undefined || incoming === null || incoming === "") return;
    if (current === undefined || current === null || current === "" || current === 0) {
      target[fieldName] = incoming;
      changed = true;
    }
  });
  return changed;
}

function newId() {
  if (globalThis.crypto?.randomUUID) {
    return globalThis.crypto.randomUUID();
  }

  if (globalThis.crypto?.getRandomValues) {
    const bytes = new Uint8Array(16);
    globalThis.crypto.getRandomValues(bytes);
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0"));
    return `${hex.slice(0, 4).join("")}-${hex.slice(4, 6).join("")}-${hex.slice(6, 8).join("")}-${hex.slice(8, 10).join("")}-${hex.slice(10, 16).join("")}`;
  }

  return `id-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}-${Math.random().toString(36).slice(2, 10)}`;
}

function createBlankLine(transport = null) {
  return {
    id: newId(),
    startAt: "",
    from: "",
    to: "",
    endAt: "",
    company: "",
    purpose: "",
    km: 0,
    transport: transport || orderDefaults().routeTransport,
    fare: 0,
    lodging: 0,
    other: 0,
    freeMeals: 0,
  };
}

function generateNumber() {
  const year = new Date().getFullYear();
  const next = state.orders
    .map((order) => order.number)
    .filter((number) => number?.startsWith(`CP-${year}-`))
    .map((number) => Number(number.split("-").pop()))
    .filter(Number.isFinite)
    .reduce((max, value) => Math.max(max, value), 0) + 1;
  return `CP-${year}-${String(next).padStart(4, "0")}`;
}

function getSelectedOrder() {
  const orders = visibleOrders();
  return orders.find((order) => order.id === state.selectedId) || orders[0] || null;
}

function touch(order) {
  order.updatedAt = new Date().toISOString();
}

function setByPath(target, path, value) {
  const parts = path.split(".");
  let current = target;
  parts.slice(0, -1).forEach((part) => {
    current = current[part];
  });
  current[parts[parts.length - 1]] = value;
}

function parseInputValue(input) {
  if (input.type === "number") return number(input.value);
  return input.value;
}

function inputValue(value) {
  if (value === null || value === undefined) return "";
  return String(value);
}

function numberValue(value) {
  if (value === null || value === undefined || value === "") return "";
  return String(Number(value));
}

function number(value) {
  if (value === "" || value === null || value === undefined) return 0;
  const parsed = Number(String(value).replace(",", "."));
  return Number.isFinite(parsed) ? parsed : 0;
}

function sum(items, key) {
  return items.reduce((total, item) => total + number(item[key]), 0);
}

function hoursBetween(start, end) {
  if (!start || !end) return 0;
  const startDate = new Date(start);
  const endDate = new Date(end);
  const diff = endDate - startDate;
  if (!Number.isFinite(diff) || diff <= 0) return 0;
  return diff / 36e5;
}

function formatCurrency(value) {
  return new Intl.NumberFormat("cs-CZ", {
    style: "currency",
    currency: "CZK",
    maximumFractionDigits: 2,
  }).format(number(value));
}

function formatNumber(value, digits = 2) {
  return new Intl.NumberFormat("cs-CZ", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(number(value));
}

function formatDateTime(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("cs-CZ", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(date);
}

function formatBytes(value) {
  const bytes = number(value);
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${formatNumber(bytes / 1024, 1)} kB`;
  return `${formatNumber(bytes / 1024 / 1024, 1)} MB`;
}

function documentKindLabel(value) {
  return DOCUMENT_KIND_OPTIONS[value] || DOCUMENT_KIND_OPTIONS.other;
}

function expenseKindLabel(value) {
  return EXPENSE_KIND_OPTIONS[value] || EXPENSE_KIND_OPTIONS.other;
}

function rateMonitorLabel(value) {
  return {
    ok: "Sazby aktuální",
    out_of_date: "Zkontrolovat",
    missing: "Chybí sazby",
    unknown: "Neověřeno",
  }[value] || "Neověřeno";
}

function monitorStatusClass(value) {
  return value === "ok" ? "ok" : value === "out_of_date" || value === "missing" ? "warn" : "neutral";
}

function todayString() {
  return new Date().toISOString().slice(0, 10);
}

function normalize(value) {
  return value
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function exportBackup() {
  const blob = new Blob([JSON.stringify(state, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `cestovni-prikazy-${todayString()}.json`;
  link.click();
  URL.revokeObjectURL(url);
}

function renderPrintSheet(order) {
  if (!order) {
    els.print.innerHTML = "";
    return;
  }

  const calc = calculateOrder(order);
  const lines = order.routeLines.map((line, index) => {
    const lineCalc = calc.lines[index];
    return `
      <tr>
        <td>${escapeHtml(formatDateTime(line.startAt))}<br />${escapeHtml(line.from || "")}</td>
        <td>${escapeHtml(formatDateTime(line.endAt))}<br />${escapeHtml(line.to || "")}</td>
        <td>${escapeHtml(TRANSPORT_OPTIONS[line.transport] || "")}</td>
        <td>${formatNumber(lineCalc.km, 0)}</td>
        <td>${formatCurrency(lineCalc.fare + lineCalc.privateComp)}</td>
        <td>${formatCurrency(lineCalc.meal)}</td>
        <td>${formatCurrency(lineCalc.lodging)}</td>
        <td>${formatCurrency(lineCalc.other)}</td>
        <td>${formatCurrency(lineCalc.total)}</td>
      </tr>
    `;
  }).join("");

  els.print.innerHTML = `
    <h1>CESTOVNÍ PŘÍKAZ</h1>
    <h2>${escapeHtml(order.number)}</h2>
    <div class="print-grid">
      <div class="print-line"><strong>Organizace:</strong> ${escapeHtml(order.employee.organization)}</div>
      <div class="print-line"><strong>Zaměstnanec:</strong> ${escapeHtml(order.employee.name)}</div>
      <div class="print-line"><strong>Osobní číslo:</strong> ${escapeHtml(order.employee.personalNo)}</div>
      <div class="print-line"><strong>Středisko:</strong> ${escapeHtml(order.employee.costCenter)}</div>
      <div class="print-line"><strong>Počátek:</strong> ${escapeHtml(formatDateTime(order.trip.startAt))}</div>
      <div class="print-line"><strong>Konec:</strong> ${escapeHtml(formatDateTime(order.trip.endAt))}</div>
      <div class="print-line"><strong>Místo jednání:</strong> ${escapeHtml(order.trip.destination)}</div>
      <div class="print-line"><strong>Stav:</strong> ${escapeHtml(STATUS_OPTIONS.find((item) => item.value === order.status)?.label || order.status)}</div>
    </div>
    <div class="print-line"><strong>Účel cesty:</strong> ${escapeHtml(order.trip.purpose)}</div>
    <div class="print-line"><strong>Spolucestující:</strong> ${escapeHtml(order.trip.companions)}</div>
    <h2>VYÚČTOVÁNÍ PRACOVNÍ CESTY</h2>
    <table class="print-table">
      <thead>
        <tr>
          <th>Odjezd</th>
          <th>Příjezd</th>
          <th>Doprava</th>
          <th>km</th>
          <th>Cestovné</th>
          <th>Stravné</th>
          <th>Nocležné</th>
          <th>Výdaje</th>
          <th>Celkem</th>
        </tr>
      </thead>
      <tbody>${lines}</tbody>
    </table>
    <table class="print-table">
      <tbody>
        <tr><th>Celkem km</th><td>${formatNumber(calc.totalKm, 0)}</td><th>Cestovné a PHM</th><td>${formatCurrency(calc.totalTransport)}</td></tr>
        <tr><th>Stravné</th><td>${formatCurrency(calc.totalMeals)}</td><th>Nocležné</th><td>${formatCurrency(calc.totalLodging)}</td></tr>
        <tr><th>Vedlejší výdaje</th><td>${formatCurrency(calc.totalOther)}</td><th>Celkem</th><td>${formatCurrency(calc.totalGross)}</td></tr>
        <tr><th>Záloha</th><td>${formatCurrency(calc.advance)}</td><th>Doplatek / přeplatek</th><td>${formatCurrency(calc.balanceRounded)}</td></tr>
      </tbody>
    </table>
  `;
}
