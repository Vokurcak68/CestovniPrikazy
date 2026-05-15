const STORAGE_KEY = "travelOrders.cz.autonomous.v1";
const LAST_USER_KEY = "travelOrders.lastUserKey";

const STATUS_OPTIONS = [
  { value: "draft", label: "Rozpracováno" },
  { value: "submitted", label: "Ke schválení" },
  { value: "returned", label: "Vráceno k doplnění" },
  { value: "approved", label: "Schváleno" },
  { value: "imported", label: "Naimportováno" },
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

const SEGMENT_TYPE_OPTIONS = {
  private: "Soukromý",
  domestic: "Tuzemský",
  foreign: "Zahraniční",
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

const CURRENCY_OPTIONS = {
  CZK: "CZK",
  EUR: "EUR",
  USD: "USD",
  GBP: "GBP",
  PLN: "PLN",
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
const draftSyncTimers = new Map();

let state = loadState();
let activeTab = "trip";
let currentUser = null;
let currentDefaults = null;
let defaultsLoaded = false;
let appStarted = false;
let appMode = "orders";
let requestState = {
  items: [],
  selectedId: null,
  loaded: false,
  message: "",
};
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
  requests: [],
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
let foreignTravelState = {
  loaded: false,
  date: "",
  countries: [],
  expenseCodes: [],
  currencies: ["CZK"],
  message: "",
};

const els = {
  form: document.getElementById("orderForm"),
  list: document.getElementById("ordersList"),
  empty: document.getElementById("emptyState"),
  print: document.getElementById("printSheet"),
  search: document.getElementById("searchInput"),
  statusFilter: document.getElementById("statusFilter"),
  printBtn: document.getElementById("printBtn"),
  exportBtn: document.getElementById("exportBtn"),
  ordersMode: document.getElementById("ordersModeBtn"),
  requestsMode: document.getElementById("requestsModeBtn"),
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
  ensureRequestsModeButton();
  await ensureCurrentDefaults();
  await loadLegislationRates();
  await loadForeignTravelReference(todayString());
  await refreshOwnedOrderStatuses();

  const removedOthers = removeOtherUsersOrders();
  const ownershipChanged = claimLegacyOrdersForCurrentUser();
  const accessibleOrders = visibleOrders();
  if (!accessibleOrders.length) {
    // Don't auto-create a blank order - user should create manually
    state.selectedId = null;
    if (removedOthers || ownershipChanged) saveState();
  } else if (!accessibleOrders.some((order) => order.id === state.selectedId)) {
    state.selectedId = accessibleOrders[0].id;
    saveState();
  } else {
    const defaultsChanged = applyDefaultsToExistingDraft();
    if (removedOthers || ownershipChanged || defaultsChanged) saveState();
  }

  if (!appStarted) {
    STATUS_OPTIONS.forEach((status) => {
      const option = document.createElement("option");
      option.value = status.value;
      option.textContent = status.label;
      els.statusFilter.append(option);
    });


    els.printBtn.addEventListener("click", () => {
      renderPrintSheet(getSelectedOrder());
      window.print();
    });

    els.exportBtn.addEventListener("click", exportBackup);
    els.logoutBtn.addEventListener("click", logout);
    els.ordersMode.addEventListener("click", () => setMode("orders"));
    els.requestsMode?.addEventListener("click", () => setMode("requests"));
    els.approvalsMode.addEventListener("click", () => setMode("approvals"));
    els.profileMode.addEventListener("click", () => setMode("profile"));
    els.adminMode.addEventListener("click", () => setMode("admin"));
    els.search.addEventListener("input", renderList);
    els.statusFilter.addEventListener("change", renderList);

    // Initialize tooltip system
    initTooltips();

    els.list.addEventListener("click", (event) => {
      const requestItem = event.target.closest("[data-request-id]");
      if (requestItem) {
        appMode = "requests";
        requestState.selectedId = requestItem.dataset.requestId;
        renderRequests();
        return;
      }

      const newRequest = event.target.closest("[data-request-action='new']");
      if (newRequest) {
        appMode = "requests";
        requestState.selectedId = null;
        renderRequests();
        return;
      }

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
    window.addEventListener("focus", refreshOwnedOrdersAndRender);
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) refreshOwnedOrdersAndRender();
    });
    window.setInterval(refreshOwnedOrdersAndRender, 30000);

    // Initialize help panel and tooltips (Phase 1 & Phase 2)
    initTooltips();
    initHelpPanel();

    appStarted = true;
  }

  updateUserChrome();
  refreshNotificationBadge();

  // Set default mode for accountants to approvals
  if (can("accountant") && !can("admin")) {
    await setMode("approvals");
  } else {
    render();
  }
}

function loadState() {
  const fallback = {
    orders: [],
    selectedId: null,
    rates: structuredClone(DEFAULT_RATES),
  };

  try {
    const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY));
    if (!parsed) return fallback;
    return {
      orders: [],
      selectedId: parsed.selectedId || null,
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
  localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({
      selectedId: state.selectedId,
      rates: state.rates,
    }),
  );
}

// Override for staged approval workflow (accounting -> manager).
async function decideApproval_legacy1(action, approvalId) {
  const stage = String(approvalState.detail?.approval?.stage || "manager");
  let comment = "";
  if (action !== "approved") {
    const promptLabel = action === "returned" ? "Důvod vrácení k doplnění:" : "Důvod zamítnutí:";
    comment = prompt(promptLabel, "") || "";
    if (!comment.trim()) {
      approvalState.message = "Komentář je povinný.";
      renderApprovals();
      return;
    }
  }
  const response = await apiFetch(`/api/approval-requests/${approvalId}/decision`, {
    method: "POST",
    body: JSON.stringify({ action, comment }),
  });
  const payload = await response.json().catch(() => ({}));

  if (!response.ok) {
    approvalState.message = approvalDecisionErrorMessage(payload.error, stage);
  } else {
    approvalState.message = approvalDecisionMessage(action, payload.decision, stage);
    approvalState.detail = null;
    approvalState.selectedApprovalId = null;
  }

  await loadApprovalData();
  renderApprovals();
  refreshNotificationBadge();
}

function approvalDecisionMessage_legacy1(action, decision = {}, stage = "manager") {
  if (action !== "approved") return "Rozhodnutí bylo uloženo.";
  if (stage === "accounting") return "Kontrola účetní byla schválena a předána finálnímu schvalovateli.";
  const sync = decision.helios_staging_sync;
  if (!sync) return "Cestovní příkaz byl schválen.";
  if (sync.ok) {
    return `Cestovní příkaz byl schválen a Helios staging byl aktualizován. K importu je ${Number(sync.activeImportCount || 0)} položek.`;
  }
  return `Cestovní příkaz byl schválen, ale Helios staging se nepodařilo aktualizovat: ${heliosStagingSyncError(sync.error)}.`;
}

function approvalDecisionErrorMessage_legacy1(code = "", stage = "manager") {
  if (code === "invalid_action_for_accounting") return "V účetní fázi lze jen schválit nebo vrátit k doplnění.";
  if (code === "missing_return_comment") return "U vrácení k doplnění je povinný komentář.";
  if (code === "invalid_action_for_manager") return "Ve finální fázi lze jen schválit nebo zamítnout.";
  if (code === "missing_rejection_reason") return "U zamítnutí je povinný důvod.";
  if (code === "missing_final_approver") return "U zaměstnance chybí finální schvalovatel.";
  if (code === "approval_not_found") return "Schvalovací úkol nebyl nalezen nebo už byl vyřízen.";
  if (stage === "accounting") return "Rozhodnutí účetní se nepodařilo uložit.";
  return "Rozhodnutí se nepodařilo uložit.";
}

function sessionUserKey(user = currentUser) {
  return String(user?.user_id || user?.id || user?.login_name || user?.email || "").trim().toLowerCase();
}

function isolateLocalStatePerUser() {
  if (!API_ENABLED || !currentUser) return;
  const currentKey = sessionUserKey(currentUser);
  if (!currentKey) return;

  const previousKey = String(localStorage.getItem(LAST_USER_KEY) || "").trim().toLowerCase();
  if (previousKey && previousKey !== currentKey) {
    state.orders = [];
    state.selectedId = null;
    saveState();
  }

  localStorage.setItem(LAST_USER_KEY, currentKey);
}

function can(role) {
  return Boolean(currentUser?.roles?.includes(role));
}

function canAccessMode(mode) {
  if (mode === "requests") return API_ENABLED && Boolean(currentUser);
  if (mode === "admin") return can("admin");
  if (mode === "approvals") return can("approver") || can("admin") || can("accountant");
  if (mode === "profile") return API_ENABLED && Boolean(currentUser);
  return true;
}

function enforceAppModeAccess() {
  if (!canAccessMode(appMode)) appMode = "orders";
}

function resetSessionScopedState() {
  adminState = {
    users: [],
    options: { roles: [], approvers: [] },
    selectedUserId: null,
    loaded: false,
    message: "",
  };
  approvalState = {
    summary: { pending_count: 0, overdue_count: 0, pending_gross_amount: 0 },
    orders: [],
    requests: [],
    detail: null,
    selectedApprovalId: null,
    notifications: { badge: { unread_count: 0, failed_count: 0 }, items: [] },
    loaded: false,
    message: "",
  };
  profileState = { data: null, loaded: false, message: "" };
  requestState = { items: [], selectedId: null, loaded: false, message: "" };
}

function currentUserId() {
  return currentUser?.user_id || currentUser?.id || "";
}

function orderApproverOptions() {
  const ownId = currentUserId();
  return (currentDefaults?.approvers || []).filter((approver) => approver.id && approver.id !== ownId);
}

function defaultOrderApprover() {
  const approvers = orderApproverOptions();
  return approvers.find((approver) => approver.is_default) || approvers[0] || null;
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
  // Check if user owns the order
  if (order.ownerUserId === userId) return true;
  // Allow accountants to see orders they're reviewing (from approval detail)
  // These orders are marked with a special flag when loaded for editing
  if (can("accountant") && order._editingAsAccountant) return true;
  return false;
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

function removeOtherUsersOrders() {
  if (!API_ENABLED || !currentUser) return false;
  const beforeCount = state.orders.length;
  state.orders = state.orders.filter(ownsOrder);
  const afterCount = state.orders.length;
  return beforeCount !== afterCount;
}

function claimLegacyOrdersForCurrentUser() {
  if (!API_ENABLED || !currentUser) return false;
  let changed = false;
  state.orders.forEach((order) => {
    if (!order.ownerUserId) {
      // Assign current user as owner of orders without ownerUserId
      // This handles migration from old version
      stampOrderOwner(order);
      changed = true;
    }
  });
  return changed;
}

async function setMode(mode) {
  if (!canAccessMode(mode)) return;

  appMode = mode;
  try {
    if (mode === "requests") {
      await loadMyTravelRequests(true);
      // Also load orders to check for existing travel orders linked to requests
      await refreshOwnedOrderStatuses();
    }
    if (mode === "orders") {
      await refreshOwnedOrderStatuses();
      // Also load requests to show request numbers in order details
      await loadMyTravelRequests(false);
    }
    if (mode === "admin") await loadAdminData();
    if (mode === "approvals") await loadApprovalData();
    if (mode === "profile") await loadProfileData();
  } catch (error) {
    if (mode === "approvals") {
      approvalState.message = "Schvalování se nepodařilo načíst, zkus obnovit stránku.";
    }
  }
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
    isolateLocalStatePerUser();
    state.orders = [];
    state.selectedId = null;
    enforceAppModeAccess();
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

async function loadForeignTravelReference(date = todayString()) {
  if (!API_ENABLED || !currentUser) return;
  const targetDate = normalizeDateOnly(date) || todayString();
  if (foreignTravelState.loaded && foreignTravelState.date === targetDate) return;

  try {
    const response = await apiFetch(`/api/foreign-travel/reference?date=${encodeURIComponent(targetDate)}`);
    if (!response.ok) throw new Error("foreign_reference_failed");
    const payload = await response.json();
    foreignTravelState = {
      loaded: true,
      date: targetDate,
      countries: Array.isArray(payload.countries) ? payload.countries : [],
      expenseCodes: Array.isArray(payload.expenseCodes) ? payload.expenseCodes : [],
      currencies: Array.isArray(payload.currencies) ? payload.currencies : ["CZK"],
      message: "",
    };
  } catch {
    foreignTravelState = {
      ...foreignTravelState,
      loaded: false,
      date: targetDate,
      message: "Číselníky pro zahraniční cesty se nepodařilo načíst z Heliosu.",
    };
  }
}

async function refreshForeignTravelReferenceForOrder(order) {
  await loadForeignTravelReference(normalizeDateOnly(order?.trip?.startAt) || todayString());
}

async function fetchExchangeRate(currencyCode, date) {
  const currency = normalizeCurrencyCode(currencyCode);
  const targetDate = normalizeDateOnly(date) || todayString();
  if (!API_ENABLED || !currentUser || currency === "CZK") {
    return { currencyCode: currency, exchangeRate: 1, exchangeRateDate: targetDate };
  }

  try {
    const response = await apiFetch(`/api/foreign-travel/exchange-rate?currency=${encodeURIComponent(currency)}&date=${encodeURIComponent(targetDate)}`);
    if (!response.ok) throw new Error("exchange_rate_failed");
    return response.json();
  } catch {
    return { currencyCode: currency, exchangeRate: 1, exchangeRateDate: targetDate };
  }
}

function showLogin(error = "", message = "") {
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
      <p class="inline-message" ${message ? "" : "hidden"}>${escapeHtml(message)}</p>
      <p class="login-error" ${error ? "" : "hidden"}>${escapeHtml(error)}</p>
      <button class="primary-btn" type="submit">Přihlásit</button>
      <button class="secondary-btn" type="button" data-auth-register>Vytvořit účet</button>
    </form>
  `;
  document.body.append(overlay);
  overlay.querySelector("form").addEventListener("submit", handleLogin);
  overlay.querySelector("[data-auth-register]").addEventListener("click", () => showRegister());
}

function showRegister(error = "", message = "") {
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
        <p class="eyebrow">Nový přístup</p>
        <h2>Registrace</h2>
      </div>
      <label>
        <span>Jméno</span>
        <input name="display_name" type="text" autocomplete="name" required />
      </label>
      <label>
        <span>E-mail</span>
        <input name="email" type="email" autocomplete="email" required />
      </label>
      <label>
        <span>Heslo</span>
        <input name="password" type="password" autocomplete="new-password" minlength="8" required />
        <label>Heslo znovu</label>
        <input name="password_confirm" type="password" autocomplete="new-password" minlength="8" required />
      </label>
      <p class="inline-message" ${message ? "" : "hidden"}>${escapeHtml(message)}</p>
      <p class="login-error" ${error ? "" : "hidden"}>${escapeHtml(error)}</p>
      <button class="primary-btn" type="submit">Registrovat</button>
      <button class="secondary-btn" type="button" data-auth-login>Zpět na přihlášení</button>
    </form>
  `;
  document.body.append(overlay);
  overlay.querySelector("form").addEventListener("submit", handleRegister);
  overlay.querySelector("[data-auth-login]").addEventListener("click", () => showLogin());
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
    isolateLocalStatePerUser();
    resetSessionScopedState();
    appMode = "orders";
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
      appMode = "orders";
      resetSessionScopedState();
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

async function handleRegister(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector("button");
  const errorBox = form.querySelector(".login-error");
  const messageBox = form.querySelector(".inline-message");
  button.disabled = true;
  errorBox.hidden = true;
  messageBox.hidden = true;

  const data = new FormData(form);
  const password = String(data.get("password") || "");
  const passwordConfirm = String(data.get("password_confirm") || "");
  if (password !== passwordConfirm) {
    errorBox.textContent = "Hesla se neshodují.";
    errorBox.hidden = false;
    button.disabled = false;
    return;
  }

  try {
    const response = await fetch("/api/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        display_name: data.get("display_name"),
        email: data.get("email"),
        password: data.get("password"),
      }),
    });
    const payload = await response.json().catch(() => ({}));

    if (!response.ok) {
      throw new Error(registerErrorMessage(payload.error));
    }

    const message = payload.emailSent
      ? "Registrace je založená. Zkontroluj e-mail a potvrď účet ověřovacím odkazem."
      : `Registrace je založená. Pro lokální test otevři ověřovací odkaz: ${payload.devVerificationUrl || ""}`;
    showLogin("", message);
  } catch (error) {
    errorBox.textContent = error.message || "Registrace se nepodařila.";
    errorBox.hidden = false;
  } finally {
    button.disabled = false;
  }
}

function registerErrorMessage(code) {
  if (code === "invalid_email") return "Zadej platný e-mail.";
  if (code === "weak_password") return "Heslo musí mít alespo ? 8 znaků.";
  if (code === "missing_display_name") return "Zadej jméno.";
  if (code === "account_exists" || code === "email_exists") return "Účet s tímto e-mailem už v databázi cestovních příkazů existuje.";
  return "Registrace se nepodařila.";
}

function handleStartupFailure(error) {
  console.error(error);
  if (API_ENABLED) {
    localStorage.removeItem(AUTH_TOKEN_KEY);
    currentUser = null;
    currentDefaults = null;
    defaultsLoaded = false;
    appMode = "orders";
    resetSessionScopedState();
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
  appMode = "orders";
  resetSessionScopedState();
  showLogin();
}

function updateUserChrome() {
  if (!els.userInfo || !els.logoutBtn) return;

  // Hide orders mode for accountants who are not admins
  els.ordersMode.hidden = can("accountant") && !can("admin");
  if (els.requestsMode) els.requestsMode.hidden = !API_ENABLED || !currentUser;
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
  enforceAppModeAccess();
  updateUserChrome();
  updateModeButtons();

  if (appMode === "requests") {
    renderRequests();
    return;
  }

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
  enforceAppModeAccess();
  [els.ordersMode, els.requestsMode, els.approvalsMode, els.profileMode, els.adminMode].forEach((button) => button?.classList.remove("active"));
  if (appMode === "orders") els.ordersMode?.classList.add("active");
  if (appMode === "requests") els.requestsMode?.classList.add("active");
  if (appMode === "approvals") els.approvalsMode?.classList.add("active");
  if (appMode === "profile") els.profileMode?.classList.add("active");
  if (appMode === "admin") els.adminMode?.classList.add("active");
}

function ensureRequestsModeButton() {
  if (els.requestsMode) return;
  const nav = document.querySelector(".top-actions");
  if (!nav || !els.ordersMode) return;
  const btn = document.createElement("button");
  btn.id = "requestsModeBtn";
  btn.type = "button";
  btn.className = "icon-text-btn mode-btn";
  btn.hidden = true;
  btn.title = "Žádosti o vycestování";
  btn.innerHTML = `<span aria-hidden="true">✉</span><span>Žádosti</span>`;
  nav.insertBefore(btn, els.approvalsMode || els.profileMode || els.adminMode || els.printBtn);
  els.requestsMode = btn;
}

async function loadMyTravelRequests(force = false) {
  if (!API_ENABLED || !currentUser) return;
  if (requestState.loaded && !force) return;
  try {
    const response = await apiFetch("/api/travel-requests/my");
    const payload = await response.json().catch(() => []);
    if (!response.ok) {
      requestState.items = [];
      requestState.loaded = true;
      requestState.message = "Žádosti se nepodařilo načíst.";
      return;
    }
    requestState.items = Array.isArray(payload) ? payload : [];
    if (!requestState.selectedId && requestState.items[0]) requestState.selectedId = requestState.items[0].id;
    if (requestState.selectedId && !requestState.items.some((i) => i.id === requestState.selectedId)) {
      requestState.selectedId = requestState.items[0]?.id || null;
    }
    requestState.loaded = true;
    requestState.message = "";
  } catch {
    requestState.items = [];
    requestState.loaded = true;
    requestState.message = "Žádosti se nepodařilo načíst.";
  }
}

function getSelectedRequest() {
  return requestState.items.find((item) => item.id === requestState.selectedId) || null;
}


function requestDateValue(value) {
  const v = String(value || "").trim()
  return v ? v.slice(0, 10) : ""
}

function requestErrorMessage(code) {
  if (code === "missing_destination") return "Vyplň cíl cesty."
  if (code === "missing_purpose") return "Vyplň důvod cesty."
  if (code === "missing_dates") return "Vyplň datum odjezdu a příjezdu."
  if (code === "missing_approver") return "Vyber schvalovatele."
  if (code === "self_approver_not_allowed") return "Nemůžeš být schvalovatel vlastní žádosti."
  if (code === "request_save_failed") return "Žádost se nepodařilo uložit."
  return "Žádost se nepodařilo uložit."
}
function createEmptyRequest() {
  const defaultApprover = defaultOrderApprover();
  return {
    id: "",
    requestNo: "",
    destination: "",
    startAt: "",
    endAt: "",
    purpose: "",
    transport: "",
    approverUserId: defaultApprover?.id || "",
    approverName: defaultApprover?.name || "",
    status: "draft",
  };
}

function collectRequestFromForm() {
  const base = getSelectedRequest() || createEmptyRequest();
  const next = { ...base };
  const fields = els.form.querySelectorAll("[data-request-path]");
  fields.forEach((field) => {
    const path = field.dataset.requestPath;
    if (!path) return;
    next[path] = parseInputValue(field);
  });
  return next;
}

async function saveRequestFromForm() {
  const requestItem = collectRequestFromForm();
  try {
    const response = await apiFetch("/api/travel-requests", {
      method: "POST",
      body: JSON.stringify(requestItem),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      requestState.message = requestErrorMessage(payload.error || "");
      renderRequests();
      return false;
    }
    requestState.message = "Žáádost uložena.";
    requestState.loaded = false;
    await loadMyTravelRequests(true);
    if (payload.request?.id) requestState.selectedId = payload.request.id;
    renderRequests();
    return true;
  } catch {
    requestState.message = "Žádost se nepodařilo uložit.";
    renderRequests();
    return false;
  }
}

async function submitRequestFromForm() {
  const saved = await saveRequestFromForm();
  if (!saved) return false;
  const selected = getSelectedRequest();
  if (!selected?.id) return false;
  try {
    const response = await apiFetch(`/api/travel-requests/${encodeURIComponent(selected.id)}/submit`, { method: "POST" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      requestState.message = payload.error || "Odeslání žádosti se nepodařilo.";
      renderRequests();
      return false;
    }
    requestState.message = "Žádost odeslána ke schválení.";
    requestState.loaded = false;
    await loadMyTravelRequests(true);
    requestState.selectedId = payload.submission?.id || selected.id;
    renderRequests();
    return true;
  } catch {
    requestState.message = "Odeslání žádosti se nepodařilo.";
    renderRequests();
    return false;
  }
}

async function fetchApprovedRequestsWithoutOrder() {
  if (!API_ENABLED || !currentUser) return [];
  try {
    const response = await apiFetch("/api/travel-requests/my/approved-without-order");
    if (!response.ok) return [];
    const data = await response.json();
    return Array.isArray(data) ? data : [];
  } catch {
    return [];
  }
}

async function pickApprovedRequestForNewOrder() {
  const items = await fetchApprovedRequestsWithoutOrder();
  if (!items.length) {
    alert("Nemáš schválenou žádost bez navázaného cestovního příkazu.");
    return null;
  }
  if (items.length === 1) return items[0];
  const lines = items.map((item, idx) => `${idx + 1}: ${item.requestNo} | ${item.destination} | ${formatDateTime(item.startAt)} - ${formatDateTime(item.endAt)}`).join("\n");
  const pick = Number(prompt(`Vyber číslo schválené žádosti:\n${lines}`, "1"));
  if (!Number.isInteger(pick) || pick < 1 || pick > items.length) return null;
  return items[pick - 1];
}

function createOrderFromRequest(requestItem) {
  const order = createBlankOrder();
  order.travelRequestId = requestItem.id || "";
  order.trip.destination = requestItem.destination || "";
  order.trip.startAt = requestItem.startAt || "";
  order.trip.endAt = requestItem.endAt || "";
  order.trip.purpose = requestItem.purpose || "";
  order.trip.reportDate = (requestItem.endAt || "").slice(0, 10) || todayString();
  order.requestNo = requestItem.requestNo || "";
  order.history.push({ at: new Date().toISOString(), status: "draft", note: `Navázáno na žádost ${requestItem.requestNo || ""}` });
  return order;
}

async function createOrderFromApprovedRequest() {
  const selectedRequest = getSelectedRequest();
  if (!selectedRequest || selectedRequest.status !== "approved") {
    alert("Vybraná žádost není schválená.");
    return;
  }

  // Create order from the approved request
  const order = createOrderFromRequest(selectedRequest);
  state.orders.unshift(order);
  state.selectedId = order.id;
  saveState();
  queueDraftSync(order, true);

  // Switch to orders mode and render
  appMode = "orders";
  render();
  resetViewportScroll();
}

function renderRequests() {
  const selected = getSelectedRequest() || createEmptyRequest();
  const approvers = orderApproverOptions();
  const selectedApproverId = selected.approverUserId || defaultOrderApprover()?.id || "";

  // Check if travel order already exists for this request
  const hasExistingOrder = selected.id && state && state.orders && state.orders.some(order => order.travelRequestId === selected.id);

  els.empty.hidden = true;
  els.form.hidden = false;
  els.list.innerHTML = `
    <button type="button" class="primary-btn full-width" data-request-action="new">Nová žádost</button>
    <div class="orders-list">
      ${requestState.items.map((r) => `
        <button type="button" class="order-list-item ${r.id === requestState.selectedId ? "active" : ""}" data-request-id="${escapeHtml(r.id)}">
          <span class="order-list-title"><span>${escapeHtml(r.requestNo || "Žádost")}</span>${statusPill(r.status || "draft")}</span>
          <span class="order-list-meta">${escapeHtml(r.destination || "")}</span>
          <span class="order-list-meta">${escapeHtml(requestDateValue(r.startAt || ""))} - ${escapeHtml(requestDateValue(r.endAt || ""))}</span>
        </button>
      `).join("") || `<p class="note">Zatím nemáš žádné žádosti.</p>`}
    </div>
  `;

  els.form.innerHTML = `
    <div class="detail-column">
      <div class="form-header">
        <div><h2>Žádost o vycestování</h2></div>
        <div class="header-actions">
          ${selected.status === "approved" && !hasExistingOrder ? `<button type="button" class="primary-btn" data-request-action="create-order">+ Založit cestovní příkaz</button>` : ""}
          ${hasExistingOrder ? `<p class="note">Cestovní příkaz již existuje</p>` : ""}
          ${selected.status === "draft" || !selected.status ? `<button type="button" class="primary-btn" data-request-action="save">Uložit žádost</button>` : ""}
          ${selected.id && selected.status !== "approved" ? `<button type="button" class="status-btn submitted" data-request-action="submit">Odeslat ke schválení</button>` : ""}
        </div>
      </div>
      ${requestState.message ? `<p class="inline-message">${escapeHtml(requestState.message)}</p>` : ""}
      <section class="section"><div class="section-body form-grid">
        <input type="hidden" data-request-path="id" value="${escapeHtml(selected.id || "")}" />
        <label><span>Cíl cesty</span><input data-request-path="destination" type="text" value="${escapeHtml(selected.destination || "")}" /></label>
        <label><span>Odjezd</span><input data-request-path="startAt" type="date" value="${escapeHtml(requestDateValue(selected.startAt || ""))}" /></label>
        <label><span>Příjezd</span><input data-request-path="endAt" type="date" value="${escapeHtml(requestDateValue(selected.endAt || ""))}" /></label>
        <label>
          <span>Doprava</span>
          <select data-request-path="transport">
            <option value="">Vyber druh dopravy</option>
            ${Object.entries(TRANSPORT_OPTIONS).map(([key, label]) => `<option value="${escapeHtml(key)}" ${key === (selected.transport || "") ? "selected" : ""}>${escapeHtml(label)}</option>`).join("")}
          </select>
        </label>
        <label>
          <span>Schvalovatel</span>
          <select data-request-path="approverUserId">
            <option value="">Vyber schvalovatele</option>
            ${approvers.map((a) => `<option value="${escapeHtml(a.id)}" ${a.id === selectedApproverId ? "selected" : ""}>${escapeHtml(a.name || a.email || a.id)}</option>`).join("")}
          </select>
        </label>
        <label class="wide"><span>Důvod cesty</span><textarea data-request-path="purpose">${escapeHtml(selected.purpose || "")}</textarea></label>
      </div></section>
    </div>
  `;
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
  if (!can("admin")) {
    appMode = "orders";
    render();
    return;
  }
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
          ${selected?.id ? `<button type="button" class="status-btn danger" data-admin-action="delete-user">Smazat uživatele</button>` : ""}
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
        ${adminField("Osobní číslo", "personal_number", user.personal_number || "")}
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
  const options = (adminState.options.approvers || []).filter((approver) => approver.id !== user.id).map((approver) => {
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
      helios_id: vehicle.helios_id || vehicle.heliosId || "",
      source_system: vehicle.source_system || vehicle.sourceSystem || "local",
      helios_export_status: vehicle.helios_export_status || vehicle.heliosExportStatus || "not_ready",
      helios_export_error: vehicle.helios_export_error || vehicle.heliosExportError || "",
      documents: vehicleDocumentsList(vehicle),
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
      helios_id: user.vehicle_helios_id || "",
      source_system: user.vehicle_source_system || "local",
      helios_export_status: user.vehicle_helios_export_status || "not_ready",
      helios_export_error: "",
      documents: [],
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
    helios_id: "",
    source_system: "local",
    helios_export_status: "not_ready",
    helios_export_error: "",
    client_id: newId(),
    documents: [],
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
        ${vehicleErpBadge(vehicle)}
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
      <div class="vehicle-documents">
        <input type="hidden" data-admin-vehicle-field="client_id" value="${escapeHtml(vehicle.client_id || vehicle.clientId || newId())}" />
        <div class="vehicle-documents-head">
          <span>Příloha OTP</span>
          <label class="secondary-btn file-action">
            Přidat fotku/soubor
            <input data-vehicle-document-file type="file" accept="image/*,.pdf" hidden />
          </label>
        </div>
        <div class="vehicle-document-list" data-vehicle-documents-list>
          ${vehicleDocumentsList(vehicle).map(vehicleDocumentCard).join("") || `<p class="note">Není přiložené OTP.</p>`}
        </div>
      </div>
    </article>
  `;
}

function vehicleDocumentsList(vehicle) {
  const documents = vehicle?.documents || vehicle?.vehicleDocuments || [];
  return Array.isArray(documents) ? documents.map((document) => ({
    id: document.id || "",
    clientDocumentId: document.clientDocumentId || document.client_document_id || document.clientId || document.id || newId(),
    documentKind: document.documentKind || document.document_kind || "otp",
    fileName: document.fileName || document.file_name || document.name || "OTP",
    contentType: document.contentType || document.content_type || "",
    byteSize: document.byteSize ?? document.byte_size ?? 0,
    dataUrl: document.dataUrl || document.data_url || "",
  })) : [];
}

function vehicleDocumentCard(document) {
  const open = document.dataUrl
    ? `<a class="secondary-btn" href="${escapeHtml(document.dataUrl)}" download="${escapeHtml(document.fileName || "OTP")}">Otevřít</a>`
    : document.id
      ? `<button type="button" class="secondary-btn" data-download-vehicle-document>Otevřít</button>`
      : `<span class="status-pill status-approved">Uloženo</span>`;
  return `
    <article class="vehicle-document" data-vehicle-document>
      <input type="hidden" data-vehicle-document-field="id" value="${escapeHtml(document.id || "")}" />
      <input type="hidden" data-vehicle-document-field="clientDocumentId" value="${escapeHtml(document.clientDocumentId || document.id || newId())}" />
      <input type="hidden" data-vehicle-document-field="documentKind" value="${escapeHtml(document.documentKind || "otp")}" />
      <input type="hidden" data-vehicle-document-field="fileName" value="${escapeHtml(document.fileName || "OTP")}" />
      <input type="hidden" data-vehicle-document-field="contentType" value="${escapeHtml(document.contentType || "")}" />
      <input type="hidden" data-vehicle-document-field="byteSize" value="${escapeHtml(document.byteSize || 0)}" />
      <input type="hidden" data-vehicle-document-field="dataUrl" value="${escapeHtml(document.dataUrl || "")}" />
      <div>
        <strong>${escapeHtml(document.fileName || "OTP")}</strong>
        <small>${escapeHtml(formatBytes(Number(document.byteSize || 0)))}</small>
      </div>
      <div class="vehicle-document-actions">
        ${open}
        <button type="button" class="table-icon-btn" data-remove-vehicle-document title="Odebrat přílohu OTP" aria-label="Odebrat přílohu OTP">×</button>
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
          <p class="note">Synchronizace z Heliosu plní osobní údaje, středisko, vozidla a příznak schvalovatele.</p>
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
    const error = await response.json().catch(() => ({}));
    adminState.message = adminSaveErrorMessage(error.error);
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

async function deleteAdminUser(user) {
  if (!user?.id) return;
  if (user.id === currentUser?.user_id) {
    adminState.message = "Nelze smazat právě přihlášeného uživatele.";
    renderAdmin();
    return;
  }

  const label = user.display_name || user.login_name || user.email || "tohoto uživatele";
  if (!window.confirm(`Opravdu smazat uživatele ${label}? Tato akce je nevratná.`)) return;

  const response = await apiFetch(`/api/admin/users/${user.id}`, {
    method: "DELETE",
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    adminState.message = adminDeleteErrorMessage(error.error);
    renderAdmin();
    return;
  }

  adminState.message = "Uživatel byl smazán.";
  if (adminState.selectedUserId === user.id) {
    adminState.selectedUserId = adminState.users.find((candidate) => candidate.id !== user.id)?.id || "";
  }
  await loadAdminData();
  renderAdmin();
}

function adminSaveErrorMessage(code) {
  if (code === "invalid_email") return "Zadej platný e-mail.";
  if (code === "email_exists") return "Uživatel s tímto e-mailem už v databázi cestovních příkazů existuje.";
  if (code === "login_exists") return "Uživatel s tímto přihlašovacím jménem už existuje.";
  if (code === "personal_number_exists") return "Toto osobní číslo už je zadané u jiného uživatele v databázi cestovních příkazů.";
  if (code === "missing_required_fields") return "Vypl ? přihlašovací jméno a jméno uživatele.";
  return "Uložení uživatele se nepodařilo.";
}

function adminDeleteErrorMessage(code) {
  if (code === "cannot_delete_self") return "Nelze smazat právě přihlášeného uživatele.";
  if (code === "user_not_found") return "Uživatel nebyl nalezen.";
  if (code === "erp_managed_user") return "Uživatel je ověřený přes ERP/Helios a nelze ho smazat.";
  if (code === "user_has_travel_orders") return "Uživatel má vytvořené cestovní příkazy a nelze ho smazat.";
  if (code === "user_has_travel_requests") return "Uživatel má žádosti o vycestování a nelze ho smazat.";
  if (code === "user_has_references") return "Uživatel má navázané záznamy v systému a nelze ho smazat.";
  if (code === "forbidden") return "Na tuto akci nemáš oprávnění.";
  return "Smazání uživatele se nepodařilo.";
}

function collectAdminVehiclesFromForm() {
  return Array.from(els.form.querySelectorAll("[data-admin-vehicle]")).map((card) => {
    const vehicle = {};
    card.querySelectorAll("[data-admin-vehicle-field]").forEach((field) => {
      vehicle[field.dataset.adminVehicleField] = field.value.trim();
    });
    vehicle.is_default = Boolean(card.querySelector("[data-admin-vehicle-default]")?.checked);
    vehicle.documents = collectVehicleDocumentsFromCard(card);
    return vehicle;
  }).filter((vehicle) => {
    return vehicle.brand || vehicle.plate || vehicle.engine_volume || Number(vehicle.consumption || 0) > 0 || (vehicle.documents || []).length;
  });
}

function collectVehicleDocumentsFromCard(card) {
  return Array.from(card.querySelectorAll("[data-vehicle-document]")).map((documentCard) => {
    const document = {};
    documentCard.querySelectorAll("[data-vehicle-document-field]").forEach((field) => {
      document[field.dataset.vehicleDocumentField] = field.value;
    });
    return document;
  }).filter((document) => document.id || document.dataUrl || document.fileName);
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

async function removeAdminVehicleCard(button) {
  const card = button.closest("[data-admin-vehicle]");
  const list = card?.closest("[data-admin-vehicles]");
  if (!card || !list) return;

  const wasDefault = Boolean(card.querySelector("[data-admin-vehicle-default]")?.checked);
  if (adminVehicleCardNeedsDeleteConfirmation(card)) {
    const label = adminVehicleCardDeleteLabel(card);
    const message = wasDefault
      ? `Opravdu odebrat výchozí vozidlo ${label}? Po odebrání se jako výchozí nastaví jiné vozidlo.`
      : `Opravdu odebrat vozidlo ${label}?`;
    if (!window.confirm(message)) return;
  }

  card.remove();
  const remaining = list.querySelectorAll("[data-admin-vehicle]");
  if (!remaining.length) {
    list.insertAdjacentHTML("beforeend", adminVehicleCard(createEmptyAdminVehicle(true), 0));
    return;
  }
  if (wasDefault) {
    remaining[0].querySelector("[data-admin-vehicle-default]").checked = true;
  }

  if (appMode === "profile") {
    profileState.message = "Ukládám odebrání vozidla...";
    await saveProfileFromForm("Vozidlo bylo odebráno a profil uložen.");
  } else if (appMode === "admin") {
    showTransientFormMessage("Vozidlo je odebrané z formuláře. Pro trvalé odstranění ulož uživatele.");
  }
}

async function addVehicleDocumentFiles(input) {
  const card = input.closest("[data-admin-vehicle]");
  const list = card?.querySelector("[data-vehicle-documents-list]");
  if (!card || !list || !input.files?.length) return;

  list.querySelector(".note")?.remove();
  for (const file of Array.from(input.files)) {
    if (file.size > 10 * 1024 * 1024) {
      showTransientFormMessage("Příloha OTP je moc velká. Maximum je 10 MB.");
      continue;
    }
    const dataUrl = await fileToDataUrl(file);
    list.insertAdjacentHTML("beforeend", vehicleDocumentCard({
      id: "",
      clientDocumentId: newId(),
      documentKind: "otp",
      fileName: file.name,
      contentType: file.type || "application/octet-stream",
      byteSize: file.size,
      dataUrl,
    }));
  }
}

async function removeVehicleDocumentCard(button) {
  const documentCard = button.closest("[data-vehicle-document]");
  const list = documentCard?.closest("[data-vehicle-documents-list]");
  if (!documentCard || !list) return;

  const fileName = documentCard.querySelector('[data-vehicle-document-field="fileName"]')?.value || "OTP";
  if (!window.confirm(`Opravdu odebrat přílohu ${fileName}?`)) return;
  documentCard.remove();
  if (!list.querySelector("[data-vehicle-document]")) {
    list.innerHTML = `<p class="note">Není přiložené OTP.</p>`;
  }

  if (appMode === "profile") {
    profileState.message = "Ukládám odebrání přílohy OTP...";
    await saveProfileFromForm("Příloha OTP byla odebrána a profil uložen.");
  } else if (appMode === "admin") {
    showTransientFormMessage("Příloha OTP je odebraná z formuláře. Pro trvalé odstranění ulož uživatele.");
  }
}

async function downloadVehicleDocument(button) {
  const documentCard = button.closest("[data-vehicle-document]");
  const vehicleCard = button.closest("[data-admin-vehicle]");
  const vehicleId = vehicleCard?.querySelector('[data-admin-vehicle-field="id"]')?.value || "";
  const documentId = documentCard?.querySelector('[data-vehicle-document-field="id"]')?.value || "";
  const fileName = documentCard?.querySelector('[data-vehicle-document-field="fileName"]')?.value || "OTP";
  if (!vehicleId || !documentId) return;

  const response = await fetch(`/api/vehicles/${encodeURIComponent(vehicleId)}/documents/${encodeURIComponent(documentId)}`, {
    headers: { Authorization: `Bearer ${localStorage.getItem(AUTH_TOKEN_KEY) || ""}` },
  });
  if (!response.ok) {
    showTransientFormMessage("Přílohu OTP se nepodařilo otevřít.");
    return;
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  link.target = "_blank";
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}

function adminVehicleCardNeedsDeleteConfirmation(card) {
  const hasPersistedId = Boolean(card.querySelector('[data-admin-vehicle-field="id"]')?.value.trim());
  const hasVehicleData = Array.from(card.querySelectorAll("[data-admin-vehicle-field]")).some((field) => {
    if (field.dataset.adminVehicleField === "id") return false;
    return Boolean(field.value.trim());
  });
  return hasPersistedId || hasVehicleData;
}

function adminVehicleCardDeleteLabel(card) {
  const brand = card.querySelector('[data-admin-vehicle-field="brand"]')?.value.trim() || "";
  const plate = card.querySelector('[data-admin-vehicle-field="plate"]')?.value.trim() || "";
  return [brand, plate].filter(Boolean).join(" / ") || "bez popisu";
}

function showTransientFormMessage(message) {
  let element = els.form.querySelector("[data-transient-message]");
  if (!element) {
    element = document.createElement("p");
    element.className = "inline-message";
    element.dataset.transientMessage = "true";
    const header = els.form.querySelector(".form-header");
    header?.insertAdjacentElement("afterend", element);
  }
  element.textContent = message;
  element.hidden = false;
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
          ${profilePersonalNumberField(profile)}
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
    helios_id: vehicle.heliosId || "",
    source_system: vehicle.sourceSystem || "local",
    helios_export_status: vehicle.heliosExportStatus || "not_ready",
    helios_export_error: vehicle.heliosExportError || "",
    documents: vehicle.documents || [],
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
    default_approver_user_id: defaultOrderApprover()?.id || "",
    approver_options: orderApproverOptions(),
    vehicles: vehicles.length ? vehicles : [createEmptyAdminVehicle(true)],
  };
}

function profileApproverSelect(profile) {
  const rawApprovers = profile.approver_options?.length ? profile.approver_options : orderApproverOptions();
  const approvers = rawApprovers.filter((approver) => approver.id !== currentUserId());
  const fallback = approvers.find((approver) => approver.is_default) || approvers[0] || {};
  const selectedId = approvers.some((approver) => approver.id === profile.default_approver_user_id)
    ? profile.default_approver_user_id
    : fallback.id || "";
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
  const rawApprovers = profile.approver_options?.length ? profile.approver_options : orderApproverOptions();
  const approvers = rawApprovers.filter((approver) => approver.id !== currentUserId());
  const selectedId = profile.default_approver_user_id || "";
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

function profilePersonalNumberField(profile) {
  return `
    <label>
      <span>Osobní číslo</span>
      <div class="input-action-row">
        <input data-profile-field="personal_number" type="text" value="${escapeHtml(profile.personal_number || "")}" />
        <button type="button" class="secondary-btn" data-profile-action="sync-erp">Synchronizace s ERP</button>
      </div>
    </label>
  `;
}

async function saveProfileFromForm(successMessage = "Profil byl uložen.") {
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
  profileState.message = successMessage;
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

async function syncProfileWithErp() {
  const personalNumber = els.form.querySelector('[data-profile-field="personal_number"]')?.value.trim() || "";
  if (!personalNumber) {
    profileState.message = "Nejdřív vypl ? osobní číslo.";
    renderProfile();
    return;
  }

  profileState.message = "Synchronizuji údaje z ERP Helios...";
  renderProfile();

  const response = await apiFetch("/api/users/me/erp-sync", {
    method: "POST",
    body: JSON.stringify({ personal_number: personalNumber }),
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    profileState.message = erpSyncErrorMessage(payload.error, payload.message);
    renderProfile();
    return;
  }

  const payload = await response.json();
  profileState.data = payload.profile;
  profileState.loaded = true;
  currentUser = {
    ...currentUser,
    display_name: payload.profile.display_name || currentUser?.display_name || "",
    email: payload.profile.email || currentUser?.email || "",
  };
  if (payload.erp?.roleSync?.approver_from_erp) {
    currentUser.roles = Array.from(new Set([...(currentUser.roles || []), "approver"]));
  }
  defaultsLoaded = false;
  await ensureCurrentDefaults(true);
  applyDefaultsToExistingDraft();
  saveState();
  updateUserChrome();
  const vehicleCount = Number(payload.erp?.vehicleCount || 0);
  const approverMessage = payload.erp?.roleSync?.approver_from_erp ? " Uživatel je označen jako schvalovatel." : "";
  profileState.message = `Synchronizace z ERP proběhla. Doplněno vozidel: ${vehicleCount}.${approverMessage}`;
  renderProfile();
}

function erpSyncErrorMessage(code, detail = "") {
  if (code === "missing_personal_number") return "Nejdřív vypl ? osobní číslo.";
  if (code === "erp_employee_not_found") return "V ERP Helios nebyl nalezen zaměstnanec s tímto osobním číslem.";
  if (code === "personal_number_exists") return "Toto osobní číslo už je zadané u jiného uživatele v databázi cestovních příkazů.";
  if (code === "erp_error") return `ERP Helios teď nelze načíst.${detail ? ` Detail: ${detail}` : ""}`;
  return "Synchronizace z ERP se nepodařila.";
}

async function loadApprovalData() {
  if (!API_ENABLED) return;
  try {
    const [dashboardResponse, notificationsResponse, requestsResponse] = await Promise.all([
      apiFetch("/api/approver/dashboard"),
      apiFetch("/api/notifications"),
      apiFetch("/api/travel-requests/pending"),
    ]);

    const dashboard = dashboardResponse.ok ? await dashboardResponse.json().catch(() => ({})) : {};
    const notifications = notificationsResponse.ok ? await notificationsResponse.json().catch(() => ({})) : {};
    const requests = requestsResponse.ok ? await requestsResponse.json().catch(() => ([])) : [];

    approvalState.summary = dashboard.summary || { pending_count: 0, overdue_count: 0, pending_gross_amount: 0 };
    approvalState.orders = Array.isArray(dashboard.orders) ? dashboard.orders : [];
    approvalState.requests = Array.isArray(requests) ? requests : [];
    approvalState.notifications = normalizeApprovalNotifications(notifications || {});
    approvalState.loaded = true;
    approvalState.message =
      !dashboardResponse.ok || !notificationsResponse.ok || !requestsResponse.ok
        ? "Cast schvalovacich dat se nepodarilo nacist."
        : "";
    updateApprovalBadge(approvalState.summary.pending_count);
  } catch {
    approvalState.summary = { pending_count: 0, overdue_count: 0, pending_gross_amount: 0 };
    approvalState.orders = [];
    approvalState.requests = [];
    approvalState.notifications = { badge: { unread_count: 0, failed_count: 0 }, items: [] };
    approvalState.loaded = true;
    approvalState.message = "Nepodarilo se nacist schvalovani.";
    updateApprovalBadge(0);
  }
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
  if (!(can("approver") || can("admin") || can("accountant"))) {
    updateApprovalBadge(0);
    return;
  }

  try {
    const response = await apiFetch("/api/approver/dashboard");
    if (!response.ok) return;
    const dashboard = await response.json();
    approvalState.summary = dashboard.summary || approvalState.summary;
    updateApprovalBadge(approvalState.summary.pending_count);
  } catch {
    // Badge refresh is opportunistic.
  }
}

async function refreshOwnedOrderStatuses() {
  if (!API_ENABLED || !currentUser) return false;

  try {
    // Load full draft orders from server
    const draftsResponse = await apiFetch("/api/travel-orders/my/drafts");
    const draftsPayload = draftsResponse.ok ? await draftsResponse.json().catch(() => ({})) : {};
    const drafts = Array.isArray(draftsPayload.drafts) ? draftsPayload.drafts : [];

    // Load statuses for submitted/approved orders
    const statusResponse = await apiFetch("/api/travel-orders/my/statuses");
    const statuses = statusResponse.ok ? await statusResponse.json().catch(() => []) : [];

    const byServerId = new Map([
      ...drafts.map((d) => [d.order?.serverId, d]),
      ...statuses.map((item) => [item.travelOrderId, item]),
    ]);
    let changed = false;

    // Remove orders that no longer exist on server
    state.orders = state.orders.filter((order) => {
      // Always keep orders being edited by accountant
      if (order._editingAsAccountant) return true;
      if (!ownsOrder(order)) return true;
      if (order.serverId) return byServerId.has(order.serverId);
      return order.status === "draft" && !order.serverId; // Keep unsaved drafts
    });

    // Load full draft orders
    drafts.forEach((draftData) => {
      const serverDraft = draftData.order || {};
      const serverId = serverDraft.serverId;
      if (!serverId) return;

      let order = state.orders.find((item) => item.serverId && item.serverId === serverId);
      if (!order) {
        // Create order from full server data
        order = {
          id: newId(),
          serverId,
          number: serverDraft.number || generateNumber(),
          status: "draft",
          createdAt: serverDraft.createdAt || new Date().toISOString(),
          updatedAt: serverDraft.updatedAt || new Date().toISOString(),
          travelRequestId: serverDraft.travelRequestId || "",
          employee: serverDraft.employee || {},
          trip: serverDraft.trip || {},
          approval: serverDraft.approval || {},
          vehicle: serverDraft.vehicle || {},
          routeLines: serverDraft.routeLines || [],
          attachments: serverDraft.attachments || [],
          history: serverDraft.history || [],
        };
        stampOrderOwner(order);
        state.orders.unshift(order);
        changed = true;
      } else {
        // Update existing draft with server data
        Object.assign(order, {
          number: serverDraft.number || order.number,
          employee: serverDraft.employee || order.employee,
          trip: serverDraft.trip || order.trip,
          approval: serverDraft.approval || order.approval,
          vehicle: serverDraft.vehicle || order.vehicle,
          routeLines: serverDraft.routeLines || order.routeLines,
          attachments: serverDraft.attachments || order.attachments,
          updatedAt: serverDraft.updatedAt || order.updatedAt,
        });
        changed = true;
      }
    });

    // Load statuses for submitted/approved orders
    statuses.forEach((serverOrder) => {
      let order = state.orders.find((item) => item.serverId && item.serverId === serverOrder.travelOrderId);
      if (!order) {
        order = createBlankOrder();
        order.number = serverOrder.orderNo || order.number;
        order.serverId = serverOrder.travelOrderId || "";
        stampOrderOwner(order);
        state.orders.unshift(order);
        changed = true;
      }
      changed = applyServerOrderStatus(order, serverOrder) || changed;
    });

    if (!state.orders.length) {
      // Don't auto-create a blank order - user should create manually
      state.selectedId = null;
      changed = true;
    } else if (!state.orders.some((order) => order.id === state.selectedId)) {
      state.selectedId = state.orders[0].id;
      changed = true;
    }

    if (changed) saveState();
    return changed;
  } catch {
    return false;
  }
}

async function refreshOwnedOrdersAndRender() {
  if (appMode !== "orders") return;
  // Don't refresh if accountant is editing someone else's order
  const selectedOrder = state.orders.find((o) => o.id === state.selectedId);
  if (selectedOrder?._editingAsAccountant) return;
  const changed = await refreshOwnedOrderStatuses();
  if (changed) render();
}

function queueDraftSync(order, immediate = false) {
  if (!API_ENABLED || !currentUser || !order) return;
  if (order.status !== "draft" || !ownsOrder(order)) return;
  if (draftSyncTimers.has(order.id)) {
    clearTimeout(draftSyncTimers.get(order.id));
    draftSyncTimers.delete(order.id);
  }
  const run = async () => {
    draftSyncTimers.delete(order.id);
    await syncDraftToServer(order);
  };
  if (immediate) {
    run();
    return;
  }
  const timer = window.setTimeout(run, 700);
  draftSyncTimers.set(order.id, timer);
}

async function syncDraftToServer(order) {
  if (!API_ENABLED || !currentUser || !order || order.status !== "draft") return false;
  try {
    const calculation = calculateOrder(order);
    const response = await apiFetch("/api/travel-orders/save-draft", {
      method: "POST",
      body: JSON.stringify({ order, calculation }),
    });
    if (!response.ok) return false;
    const payload = await response.json().catch(() => ({}));
    const saved = payload.saved || {};
    if (saved.travel_order_id && order.serverId !== saved.travel_order_id) order.serverId = saved.travel_order_id;
    if (saved.order_no && order.number !== saved.order_no) order.number = saved.order_no;
    return true;
  } catch {
    return false;
  }
}

function applyServerOrderStatus(order, serverOrder) {
  let changed = false;
  const nextStatus = serverOrder.status || order.status;
  if (nextStatus && order.status !== nextStatus) {
    order.status = nextStatus;
    changed = true;
  }

  if (serverOrder.travelOrderId && order.serverId !== serverOrder.travelOrderId) {
    order.serverId = serverOrder.travelOrderId;
    changed = true;
  }
  if (serverOrder.travelRequestId && order.travelRequestId !== serverOrder.travelRequestId) {
    order.travelRequestId = serverOrder.travelRequestId;
    changed = true;
  }
  if (serverOrder.approvalStage && order.approvalStage !== serverOrder.approvalStage) {
    order.approvalStage = serverOrder.approvalStage;
    changed = true;
  }
  if (serverOrder.exportStatus && order.exportStatus !== serverOrder.exportStatus) {
    order.exportStatus = serverOrder.exportStatus;
    changed = true;
  }
  if ((serverOrder.heliosDocumentId || "") !== (order.heliosDocumentId || "")) {
    order.heliosDocumentId = serverOrder.heliosDocumentId || "";
    changed = true;
  }
  if ((serverOrder.heliosExportedAt || "") !== (order.heliosExportedAt || "")) {
    order.heliosExportedAt = serverOrder.heliosExportedAt || "";
    changed = true;
  }

  const decisionStatus = serverOrder.approvalStatus || "";
  const decisionAt = serverOrder.approvalDecidedAt || "";
  const decisionComment = serverOrder.approvalDecisionComment || "";
  const shouldShowReturnNotice = decisionStatus === "returned" && nextStatus === "draft";
  if (shouldShowReturnNotice) {
    const nextNotice = { status: "returned", at: decisionAt, comment: decisionComment };
    const currentNotice = order.returnNotice || {};
    if (
      currentNotice.status !== nextNotice.status ||
      (currentNotice.at || "") !== (nextNotice.at || "") ||
      (currentNotice.comment || "") !== (nextNotice.comment || "")
    ) {
      order.returnNotice = nextNotice;
      changed = true;
    }
  } else if (order.returnNotice) {
    delete order.returnNotice;
    changed = true;
  }

  order.approval = order.approval || {};
  if (nextStatus === "submitted") {
    const nextApproverId = serverOrder.currentApproverUserId || "";
    if ((order.approval.approverUserId || "") !== nextApproverId) {
      order.approval.approverUserId = nextApproverId;
      order.approval.approverName = serverOrder.currentApproverName || "";
      changed = true;
    }
  }

  const updatedAt = serverOrder.updatedAt || serverOrder.approvedAt || serverOrder.rejectedAt;
  if (updatedAt && order.updatedAt !== updatedAt) {
    order.updatedAt = updatedAt;
    changed = true;
  }

  if (serverOrder.approvedAt) {
    order.history = Array.isArray(order.history) ? order.history : [];
    if (!order.history.some((item) => item.status === "approved" && item.at === serverOrder.approvedAt)) {
      order.history.push({ at: serverOrder.approvedAt, status: "approved", note: "Schváleno" });
      changed = true;
    }
  }
  if (serverOrder.rejectedAt) {
    order.history = Array.isArray(order.history) ? order.history : [];
    if (!order.history.some((item) => item.status === "rejected" && item.at === serverOrder.rejectedAt)) {
      const note = decisionComment ? `Zamítnuto: ${decisionComment}` : "Zamítnuto";
      order.history.push({ at: serverOrder.rejectedAt, status: "rejected", note });
      changed = true;
    }
  }
  if (shouldShowReturnNotice && decisionAt) {
    order.history = Array.isArray(order.history) ? order.history : [];
    if (!order.history.some((item) => item.status === "returned" && item.at === decisionAt)) {
      const note = decisionComment ? `Vráceno k doplnění: ${decisionComment}` : "Vráceno k doplnění";
      order.history.push({ at: decisionAt, status: "returned", note });
      changed = true;
    }
  }

  changed = hydrateOrderFromServerSnapshot(order, serverOrder) || changed;

  return changed;
}

function hydrateOrderFromServerSnapshot(order, serverOrder) {
  const snapshotOrder = serverOrder?.calculationSnapshot?.order;
  if (!snapshotOrder || typeof snapshotOrder !== "object") return false;

  const shouldHydrateDetail = ["approved", "imported", "closed"].includes(serverOrder?.status || "")
    || isOrderDetailMostlyEmpty(order);
  if (!shouldHydrateDetail) return false;

  let changed = false;

  const nextTrip = {
    ...(order.trip || {}),
    ...(snapshotOrder.trip || {}),
  };
  if (JSON.stringify(nextTrip) !== JSON.stringify(order.trip || {})) {
    order.trip = nextTrip;
    changed = true;
  }

  const nextEmployee = {
    ...(order.employee || {}),
    ...(snapshotOrder.employee || {}),
  };
  if (JSON.stringify(nextEmployee) !== JSON.stringify(order.employee || {})) {
    order.employee = nextEmployee;
    changed = true;
  }

  const nextVehicle = {
    ...(order.vehicle || {}),
    ...(snapshotOrder.vehicle || {}),
  };
  if (JSON.stringify(nextVehicle) !== JSON.stringify(order.vehicle || {})) {
    order.vehicle = nextVehicle;
    changed = true;
  }

  const nextApproval = {
    ...(order.approval || {}),
    ...(snapshotOrder.approval || {}),
  };
  if (JSON.stringify(nextApproval) !== JSON.stringify(order.approval || {})) {
    order.approval = nextApproval;
    changed = true;
  }

  if (Array.isArray(snapshotOrder.routeLines) && snapshotOrder.routeLines.length) {
    const nextLines = snapshotOrder.routeLines.map((line) => ({
      id: line.id || newId(),
      startAt: line.startAt || "",
      from: line.from || "",
      to: line.to || "",
      endAt: line.endAt || "",
      company: line.company || "",
      purpose: line.purpose || "",
      segmentType: line.segmentType || "domestic",
      countryCode: line.countryCode || "",
      countryName: line.countryName || "",
      foreignCurrencyCode: line.foreignCurrencyCode || "",
      foreignMealRate: Number(line.foreignMealRate || 0),
      foreignExchangeRate: Number(line.foreignExchangeRate || 1),
      foreignExchangeRateDate: line.foreignExchangeRateDate || "",
      foreignMealAmountCzk: Number(line.foreignMealAmountCzk || 0),
      transport: line.transport || "private_car",
      vehicleId: line.vehicleId || "",
      km: Number(line.km || 0),
      fare: Number(line.fare || 0),
      lodging: Number(line.lodging || 0),
      other: Number(line.other || 0),
      freeMeals: Number(line.freeMeals || 0),
    }));
    if (JSON.stringify(nextLines) !== JSON.stringify(order.routeLines || [])) {
      order.routeLines = nextLines;
      changed = true;
    }
  }

  if (Array.isArray(snapshotOrder.attachments)) {
    const nextAttachments = snapshotOrder.attachments.map((attachment) => ({
      ...attachment,
      id: attachment.id || newId(),
    }));
    if (JSON.stringify(nextAttachments) !== JSON.stringify(order.attachments || [])) {
      order.attachments = nextAttachments;
      changed = true;
    }
  }

  return changed;
}

function isOrderDetailMostlyEmpty(order) {
  const trip = order?.trip || {};
  const hasTripText = Boolean(
    String(trip.purpose || "").trim()
    || String(trip.destination || "").trim()
    || String(trip.visitedCompanies || "").trim()
  );
  const hasExpenses = Number(trip.expectedExpense || 0) > 0 || Number(trip.advance || 0) > 0;
  const hasAttachments = Array.isArray(order?.attachments) && order.attachments.length > 0;
  const hasMeaningfulLine = Array.isArray(order?.routeLines) && order.routeLines.some((line) => {
    return Boolean(
      String(line.from || "").trim()
      || String(line.to || "").trim()
      || String(line.purpose || "").trim()
      || String(line.company || "").trim()
      || Number(line.km || 0) > 0
      || Number(line.fare || 0) > 0
      || Number(line.lodging || 0) > 0
      || Number(line.other || 0) > 0
    );
  });
  return !(hasTripText || hasExpenses || hasAttachments || hasMeaningfulLine);
}

function updateApprovalBadge(count) {
  if (!els.approvalBadge) return;
  const pending = Number(count || 0);
  els.approvalBadge.hidden = pending === 0;
  els.approvalBadge.textContent = String(pending);
}

function normalizeApprovalNotifications(payload) {
  const items = (payload?.items || []).filter((item) => item.type_code === "approval_requested");
  const repairedItems = items.map((item) => ({
    ...item,
    title: repairMojibakeText(item.title || ""),
    message: repairMojibakeText(item.message || ""),
  }));
  return {
    ...payload,
    items: repairedItems,
    badge: {
      unread_count: repairedItems.length,
      failed_count: Number(payload?.badge?.failed_count || 0),
    },
  };
}

function repairMojibakeText(value) {
  const text = String(value || "");
  if (!text) return text;
  let fixed = text;
  const replacements = [
    ["Ăˇ", "á"], ["Ă©", "é"], ["Ă­", "í"], ["Ăł", "ó"], ["Ăş", "ú"], ["Ă˝", "ý"],
    ["ÄŤ", "č"], ["ÄŹ", "ď"], ["Ä›", "ě"], ["Ĺ", "ň"], ["Ĺ™", "ř"], ["Ĺˇ", "š"],
    ["ĹĄ", "ť"], ["ĹŻ", "ů"], ["Ĺľ", "ž"], ["Ă", ""], ["Â", ""],
  ];
  for (const [from, to] of replacements) {
    fixed = fixed.split(from).join(to);
  }
  return fixed;
}

function renderApprovals() {
  els.empty.hidden = true;
  els.form.hidden = false;
  els.list.innerHTML = approvalSidebar();
  const summary = approvalState.summary || {};
  const orders = approvalState.orders || [];
  const requests = approvalState.requests || [];

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
          <h3>Žádosti o vycestování</h3>
        </div>
        <div class="section-body approval-stack">
          ${requests.length ? requests.map(pendingRequestCard).join("") : `<p class="note">Teď tu není žádná žádost ke schválení.</p>`}
        </div>
      </section>
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
  const stage = String(item.stage || "manager");
  const stageLabel = stage === "accounting" ? "Kontrola účetní" : "Finální schválení";
  return `
    <article class="approval-card ${approvalState.selectedApprovalId === item.approval_request_id ? "active" : ""}">
      <div>
        <span class="route-index">${escapeHtml(item.order_no)}</span>
        <p><span class="status-pill status-submitted">${escapeHtml(stageLabel)}</span></p>
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
  const stage = String(approval.stage || "manager");
  const isAccounting = stage === "accounting";
  return `
    <section class="section approval-detail" id="approvalDetail">
      <div class="section-header">
        <div>
          <h3>Kontrola ${escapeHtml(order.number || "")}</h3>
          <p class="section-subtitle">${escapeHtml(employee.name || "Neznámý žadatel")} · ${escapeHtml(order.destination || "Bez místa jednání")}</p>
        </div>
        <div class="approval-actions">
          <button type="button" class="secondary-btn" data-approval-action="back">Zpět na frontu</button>
          ${isAccounting ? `<button type="button" class="secondary-btn" data-approval-action="edit" data-travel-order-id="${escapeHtml(order.id)}">Upravit před schválením</button>` : ""}
          <button type="button" class="primary-btn" data-approval-action="approved" data-approval-id="${escapeHtml(approval.id)}">${isAccounting ? "Schválit kontrolu účetní" : "Schválit"}</button>
          <button type="button" class="secondary-btn" data-approval-action="returned" data-approval-id="${escapeHtml(approval.id)}">Vrátit k doplnění</button>
          ${isAccounting ? "" : `<button type="button" class="status-btn danger" data-approval-action="rejected" data-approval-id="${escapeHtml(approval.id)}">Zamítnout</button>`}
        </div>
      </div>
      <div class="section-body approval-detail-body">
        <div class="approval-check-grid">
          ${approvalCheck("Fáze schválení", isAccounting ? "Kontrola účetní" : "Finální schválení")}
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
                <th>Typ</th>
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
    return [`<tr><td colspan="10">Nejsou zadané žádné úseky cesty.</td></tr>`];
  }

  return lines.map((line, index) => {
    const calcLine = calcLines[index] || {};
    const isPrivateSegment = (line.segmentType || line.segment_type || "domestic") === "private";
    const transportAmount = isPrivateSegment ? 0 : number(line.fare) + number(line.calculatedPrivateVehicleAmount || calcLine.privateComp);
    const mealAmount = isPrivateSegment ? 0 : number(line.calculatedMealAmount || calcLine.meal);
    const lodging = isPrivateSegment ? 0 : number(line.lodging);
    const other = isPrivateSegment ? 0 : number(line.other);
    const total = number(line.calculatedTotalAmount || calcLine.total) || transportAmount + mealAmount + lodging + other;
    return `
      <tr>
        <td>
          <strong>${escapeHtml(line.from || "Odkud")} → ${escapeHtml(line.to || "Kam")}</strong><br />
          <small>${escapeHtml(line.company || line.purpose || "")}</small>
        </td>
        <td>${escapeHtml(formatDateTime(line.startAt))}<br /><small>${escapeHtml(formatDateTime(line.endAt))}</small></td>
        <td>${escapeHtml(segmentTypeLabel(line.segmentType || line.segment_type))}</td>
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
        <strong>${formatAttachmentAmount(attachment)}</strong>
        <small>Přepočet ${escapeHtml(formatCurrency(attachmentAmountCzk(attachment)))}</small>
        <small>${escapeHtml(formatBytes(attachment.byteSize || 0))}</small>
      </div>
    </div>
  `;
}

function fuelLabel(value) {
  return FUEL_OPTIONS[value] || value || "-";
}

function segmentTypeLabel(value) {
  return SEGMENT_TYPE_OPTIONS[value] || SEGMENT_TYPE_OPTIONS.domestic;
}

function fuelPriceModeLabel(value) {
  return FUEL_PRICE_MODE_OPTIONS[value] || "Dle vyhlášky";
}

async function decideApproval_legacy_old(action, approvalId) {
  const comment = action === "approved" ? "" : prompt("Poznámka pro žadatele:", "") || "";
  const response = await apiFetch(`/api/approval-requests/${approvalId}/decision`, {
    method: "POST",
    body: JSON.stringify({ action, comment }),
  });
  const payload = await response.json().catch(() => ({}));

  if (!response.ok) {
    approvalState.message = "Rozhodnutí se nepodařilo uložit.";
  } else {
    approvalState.message = approvalDecisionMessage(action, payload.decision);
    approvalState.detail = null;
    approvalState.selectedApprovalId = null;
  }

  await loadApprovalData();
  renderApprovals();
  refreshNotificationBadge();
}

function approvalDecisionMessage_legacy2(action, decision = {}) {
  if (action !== "approved") return "Rozhodnutí bylo uloženo.";
  const sync = decision.helios_staging_sync;
  if (!sync) return "Cestovní příkaz byl schválen.";
  if (sync.ok) {
    return `Cestovní příkaz byl schválen a Helios staging byl aktualizován. K importu je ${Number(sync.activeImportCount || 0)} položek.`;
  }
  return `Cestovní příkaz byl schválen, ale Helios staging se nepodařilo aktualizovat: ${heliosStagingSyncError(sync.error)}.`;
}

function heliosStagingSyncError(code = "") {
  if (String(code).includes("missing_helios_import_api_token")) return "chybí HELIOS_IMPORT_API_TOKEN";
  if (String(code).includes("import_list_api_failed")) return "API nevrátilo seznam k importu";
  if (String(code).includes("import_full_api_failed")) return "API nevrátilo detail k importu";
  return "zkontroluj připojení k MSSQL a staging tabulku";
}

async function decideTravelRequest(action, requestId) {
  if (!requestId) return;
  let reason = "";
  if (action === "rejected") {
    reason = prompt("Důvod zamítnutí žádosti:", "") || "";
    if (!reason.trim()) {
      approvalState.message = "Důvod zamítnutí je povinný.";
      renderApprovals();
      return;
    }
  }
  const response = await apiFetch(`/api/travel-requests/${encodeURIComponent(requestId)}/decision`, {
    method: "POST",
    body: JSON.stringify({ action, reason }),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    approvalState.message = travelRequestDecisionError(payload.error);
  } else {
    approvalState.message = action === "approved" ? "Žádost byla schválena." : "Žádost byla zamítnuta.";
  }
  await loadApprovalData();
  renderApprovals();
}

function travelRequestDecisionError(code = "") {
  if (code === "missing_rejection_reason") return "Důvod zamítnutí je povinný.";
  if (code === "invalid_action") return "Neplatná akce žádosti.";
  if (code === "request_decision_failed") return "Žádost už byla vyřízena, nebo k ní nemáš přístup.";
  return "Rozhodnutí o žádosti se nepodařilo uložit.";
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
      const statusMatches = statusFilter === "all" || effectiveOrderStatus(order) === statusFilter;
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
    button.className = `order-list-item ${order.id === state.selectedId ? "active" : ""} ${hasReturnNotice(order) ? "needs-attention" : ""}`;
    button.dataset.orderId = order.id;
    button.innerHTML = `
        <span class="order-list-title">
          <span>${escapeHtml(order.number)}</span>
        ${orderStatusPill(order)}
      </span>
      <span class="order-list-meta">${escapeHtml(order.employee.name || "Bez zaměstnance")}</span>
      <span class="order-list-meta">${escapeHtml(order.trip.purpose || "Bez účelu")} · ${formatCurrency(calc.totalGross)}</span>
      ${hasReturnNotice(order) ? `<span class="order-list-alert">${escapeHtml(returnNoticeSummary(order))}</span>` : ""}
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

  // Find linked travel request if exists
  let requestInfo = "";
  if (order.requestNo) {
    requestInfo = `<span>Žádost ${escapeHtml(order.requestNo)}</span>`;
  } else if (order.travelRequestId) {
    const linkedRequest = requestState.items.find(r => r.id === order.travelRequestId);
    if (linkedRequest && linkedRequest.requestNo) {
      requestInfo = `<span>Žádost ${escapeHtml(linkedRequest.requestNo)}</span>`;
    } else {
      requestInfo = `<span>Žádost navázána</span>`;
    }
  } else {
    requestInfo = `<span>Bez schválené žádosti</span>`;
  }

  els.form.innerHTML = `
    <div class="detail-column">
      <div class="form-header">
        <div>
          <h2>${escapeHtml(order.number)}</h2>
          <div class="header-meta">
            ${orderStatusPill(order)}
            <span>Aktualizováno ${formatDateTime(order.updatedAt)}</span>
            <span>${escapeHtml(order.employee.name || "Bez zaměstnance")}</span>
            ${requestInfo}
          </div>
        </div>
        <div class="header-actions">
          ${workflowButtons(order)}
          <button type="button" class="secondary-btn" data-action="duplicate">Duplikovat</button>
          <button type="button" class="status-btn danger" data-action="delete">Smazat</button>
        </div>
      </div>

      ${returnNoticeBanner(order)}
      ${overviewSection(order, calc)}
      ${tabsSection()}
      ${activeTabSection(order, calc)}
    </div>
  `;

  renderPrintSheet(order);
  restoreTabbarPosition(options.tabScrollLeft ?? previousTabScrollLeft, Boolean(options.revealActiveTab));
  if (options.focusLineId) focusRouteLine(options.focusLineId);

  // Initialize Flatpickr datetime pickers
  initDateTimePickers();
}

function focusRouteLine(lineId) {
  requestAnimationFrame(() => {
    const row = Array.from(document.querySelectorAll("[data-line-id]")).find((item) => item.dataset.lineId === lineId);
    if (!row) return;
    row.scrollIntoView({ block: "center", behavior: "smooth" });
    const preferredField = row.querySelector('[data-line-field="to"]') || row.querySelector("[data-line-field]");
    preferredField?.focus({ preventScroll: true });
    preferredField?.select?.();
  });
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

function returnNoticeBanner(order) {
  if (!hasReturnNotice(order)) return "";
  const comment = String(order.returnNotice?.comment || "").trim();
  return `
    <section class="return-notice" aria-label="Vrácení cestovního příkazu">
      <div>
        <strong>Vráceno k doplnění</strong>
        <span>${escapeHtml(order.returnNotice?.at ? formatDateTime(order.returnNotice.at) : "")}</span>
      </div>
      <p>${escapeHtml(comment || "Schvalovatel nevyplnil poznámku.")}</p>
    </section>
  `;
}

function returnNoticeSummary(order) {
  const comment = String(order.returnNotice?.comment || "").trim();
  return comment ? `Poznámka: ${comment}` : "Vráceno k doplnění";
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
        ${field("Počátek cesty", "trip.startAt", order.trip.startAt, "datetime-local", "", null, false, "Datum a čas zahájení celé pracovní cesty")}
        ${field("Konec cesty", "trip.endAt", order.trip.endAt, "datetime-local", "", null, false, "Datum a čas ukončení celé pracovní cesty")}
        <label>
          <span>Měna vyúčtování</span>
          <select data-path="trip.currencyCode">${currencyOptionsHtml(order.trip.currencyCode || "CZK")}</select>
        </label>
        ${readonlyField("Kurz měny", formatExchangeRate(order.trip.exchangeRate, order.trip.exchangeRateDate), "exchange-rate-field")}
        ${field("Místo jednání", "trip.destination", order.trip.destination, "text", "", null, false, "Zadejte místo, kde se cesta konala (např. Praha, Berlin)")}
        ${field("Účel cesty", "trip.purpose", order.trip.purpose, "text", "wide", null, false, "Popište stručně důvod a cíl pracovní cesty")}
        ${field("Navštívené firmy", "trip.visitedCompanies", order.trip.visitedCompanies, "text", "wide", null, false, "Uveďte názvy firem nebo organizací, které jste navštívili")}
        ${field("Spolucestující", "trip.companions", order.trip.companions, "text", "wide", null, false, "Jména osob, které s vámi cestovaly (pokud byly)")}
        ${field("Předpokládané výdaje", "trip.expectedExpense", order.trip.expectedExpense, "number", "", "0.01", false, "Odhadovaná celková částka výdajů na cestu")}
        ${field("Povolená záloha", "trip.advance", order.trip.advance, "number", "", "0.01", false, "Částka poskytnutá předem na pokrytí výdajů")}
        ${field("Datum cestovní zprávy", "trip.reportDate", order.trip.reportDate, "date", "", null, false, "Datum, kdy byla cestovní zpráva vyplněna")}
      </div>
    </section>
  `;
}

function currencyOptionsHtml(selectedValue = "CZK") {
  const selected = normalizeCurrencyCode(selectedValue);
  const currencies = new Set(Object.keys(CURRENCY_OPTIONS));
  currencies.add(selected);
  foreignTravelState.currencies.forEach((currency) => currencies.add(normalizeCurrencyCode(currency)));
  foreignTravelState.countries.forEach((country) => currencies.add(normalizeCurrencyCode(country.currencyCode)));
  return Array.from(currencies).sort().map((code) => {
    return `<option value="${escapeHtml(code)}" ${code === selected ? "selected" : ""}>${escapeHtml(code)}</option>`;
  }).join("");
}

function readonlyField(label, value, className = "") {
  return `
    <label class="${escapeHtml(className)}">
      <span>${escapeHtml(label)}</span>
      <input class="readonly-input" readonly value="${escapeHtml(value || "")}" />
    </label>
  `;
}

function formatExchangeRate(rate, date) {
  const value = number(rate || 1);
  const dateText = normalizeDateOnly(date);
  return `${formatNumber(value, 6)}${dateText ? ` (${dateText})` : ""}`;
}

function approverPickerField(order) {
  const approvers = orderApproverOptions();
  if (!approvers.length) {
    return `
      <div class="wide form-note">
        <span class="field-caption">Schvalovatel tohoto příkazu</span>
        <p class="note">Není nastavený žádný dostupný schvalovatel.</p>
      </div>
    `;
  }
  const fallback = defaultOrderApprover();
  const selectedId = approvers.some((approver) => approver.id === order.approval?.approverUserId)
    ? order.approval.approverUserId
    : fallback?.id || "";
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
  const status = vehicleErpStatusText(vehicle);
  if (main) return vehicle.is_default ? `${main} (výchozí, ${status})` : `${main} (${status})`;
  return vehicle.is_default ? `Výchozí vozidlo (${status})` : `Uložené vozidlo (${status})`;
}

function vehicleErpStatusText(vehicle = {}) {
  const heliosId = vehicle.helios_id || vehicle.heliosId || "";
  const status = vehicle.helios_export_status || vehicle.heliosExportStatus || "not_ready";
  if (heliosId || status === "exported") return "v ERP";
  if (status === "queued" || status === "ready") return "čeká na ERP";
  if (status === "failed") return "ERP chyba";
  return "lokální";
}

function vehicleErpBadge(vehicle = {}) {
  const status = vehicle.helios_export_status || vehicle.heliosExportStatus || "not_ready";
  const text = vehicleErpStatusText(vehicle);
  const className = status === "failed"
    ? "status-rejected"
    : status === "queued" || status === "ready"
      ? "status-submitted"
      : vehicle.helios_id || vehicle.heliosId || status === "exported"
        ? "status-approved"
        : "status-draft";
  const title = text === "lokální"
    ? "Do ERP se zařadí až ve chvíli, kdy bude použité v odeslaném cestovním příkazu."
    : "";
  return `<span class="status-pill ${className}" title="${escapeHtml(title)}">${escapeHtml(text)}</span>`;
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
  const approver = orderApproverOptions().find((item) => item.id === approverId);
  order.approval = {
    approverUserId: approver?.id || "",
    approverName: approver?.name || approver?.display_name || "",
  };
}

function routesSection(order, calc) {
  const cards = order.routeLines.map((line, index) => routeCard(line, calc.lines[index], index, order.routeLines.length)).join("");
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

function routeCard(line, lineCalc, index, totalLines) {
  const lastLineActions = index === totalLines - 1
    ? `<div class="route-card-actions"><button type="button" class="primary-btn" data-action="add-line">Přidat další řádek</button></div>`
    : "";
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
        ${lineField("Odjezd", "startAt", line.startAt, "datetime-local", null, "Datum a čas začátku tohoto úseku cesty")}
        ${lineField("Odkud", "from", line.from, "text", null, "Místo odjezdu (město, adresa)")}
        ${lineField("Kam", "to", line.to, "text", null, "Místo příjezdu (město, adresa)")}
        ${lineField("Příjezd", "endAt", line.endAt, "datetime-local", null, "Datum a čas konce tohoto úseku cesty")}
        ${lineField("Firma / místo", "company", line.company, "text", null, "Název firmy nebo místa, které jste navštívili")}
        ${lineField("Účel", "purpose", line.purpose, "text", null, "Účel návštěvy nebo jednání na tomto úseku")}
        ${lineField("Kilometry", "km", line.km, "number", "1", "Počet ujetých kilometrů (vyplňte při použití osobního vozidla)")}
        <label>
          <span>Typ úseku</span>
          ${lineSegmentTypeSelect(line.segmentType || "domestic")}
        </label>
        ${foreignCountryField(line)}
        <label>
          <span>Doprava</span>
          ${lineTransportSelect(line.transport)}
        </label>
      </div>
      <div class="route-costs">
        ${lineField("Jízdné", "fare", line.fare, "number", "0.01", "Náklady na dopravu (vlak, letadlo, taxi, atd.)")}
        ${lineField("Nocležné", "lodging", line.lodging, "number", "0.01", "Náklady na ubytování")}
        ${lineField("Vedlejší výdaje", "other", line.other, "number", "0.01", "Ostatní výdaje (parkování, telefon, atd.)")}
        ${lineField("Jídla zdarma", "freeMeals", line.freeMeals, "number", "1", "Počet jídel poskytnutých zdarma (snižuje stravné)")}
        ${foreignLineInfo(line)}
      </div>
      ${lastLineActions}
    </article>
  `;
}

function foreignCountryField(line) {
  if ((line.segmentType || "domestic") !== "foreign") return "";
  if (!foreignTravelState.countries.length) {
    return `
      <label>
        <span>Země</span>
        <input class="readonly-input" readonly value="Číselník zemí není načtený" />
      </label>
    `;
  }
  const countryOptions = [...foreignTravelState.countries];
  if (line.countryCode && !countryOptions.some((country) => country.code === line.countryCode)) {
    countryOptions.unshift({
      code: line.countryCode,
      mealRate: line.foreignMealRate || 0,
      currencyCode: line.foreignCurrencyCode || "EUR",
      exchangeRate: line.foreignExchangeRate || 1,
    });
  }
  const options = countryOptions.map((country) => {
    const selected = country.code === line.countryCode ? "selected" : "";
    const label = `${country.code} · ${formatCurrency(country.mealRate, country.currencyCode)} · kurz ${formatNumber(country.exchangeRate || 1, 6)}`;
    return `<option value="${escapeHtml(country.code)}" ${selected}>${escapeHtml(label)}</option>`;
  });
  return `
    <label>
      <span>Země</span>
      <select data-line-field="countryCode">${options.join("")}</select>
    </label>
  `;
}

function foreignLineInfo(line) {
  if ((line.segmentType || "domestic") !== "foreign") return "";
  const currency = normalizeCurrencyCode(line.foreignCurrencyCode || "EUR");
  return `
    <div class="route-foreign-info">
      <span>Stravné ${escapeHtml(formatCurrency(line.foreignMealRate || 0, currency))}</span>
      <span>Kurz ${escapeHtml(formatExchangeRate(line.foreignExchangeRate || 1, line.foreignExchangeRateDate))}</span>
    </div>
  `;
}

function routeTitle(line) {
  if (line.from || line.to) return `${line.from || "Odkud"} → ${line.to || "Kam"}`;
  return "Nový úsek cesty";
}

function lineField(label, fieldName, value, type = "text", step = null, help = "") {
  const stepAttr = step ? `step="${escapeHtml(step)}"` : "";
  const numberAttrs = type === "number" ? `min="0" inputmode="decimal"` : "";
  const helpIcon = help ? `<span class="help-icon" data-help="${escapeHtml(help)}" title="${escapeHtml(help)}">?</span>` : "";
  return `
    <label>
      <span>${escapeHtml(label)}${helpIcon}</span>
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

function lineSegmentTypeSelect(value) {
  const normalized = SEGMENT_TYPE_OPTIONS[value] ? value : "domestic";
  const options = Object.entries(SEGMENT_TYPE_OPTIONS).map(([key, label]) => {
    return `<option value="${key}" ${key === normalized ? "selected" : ""}>${label}</option>`;
  });
  return `<select data-line-field="segmentType">${options.join("")}</select>`;
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
            <span>Náklad Helios</span>
            <select data-attachment-meta="heliosExpenseCodeId">${expenseCodeOptionsHtml()}</select>
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
          <label>
            <span>Měna</span>
            <select data-attachment-meta="currencyCode">${currencyOptionsHtml(order.trip.currencyCode || "CZK")}</select>
          </label>
          <label>
            <span>Kurz do Kč</span>
            <input data-attachment-meta="exchangeRate" type="number" min="0" step="0.000001" inputmode="decimal" value="1" />
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

function expenseCodeOptionsHtml(selectedValue = "") {
  const selected = String(selectedValue || "");
  const options = [`<option value="">Automaticky podle typu výdaje</option>`];
  foreignTravelState.expenseCodes.forEach((code) => {
    const value = String(code.id || "");
    const label = `${code.label || code.code || value}${code.code ? ` (${code.code})` : ""}`;
    options.push(`<option value="${escapeHtml(value)}" ${value === selected ? "selected" : ""}>${escapeHtml(label)}</option>`);
  });
  return options.join("");
}

function attachmentCard(attachment) {
  const download = attachment.dataUrl
    ? `<a class="secondary-btn" href="${escapeHtml(attachment.dataUrl)}" download="${escapeHtml(attachment.fileName || "doklad")}">Otevřít</a>`
    : "";
  return `
    <article class="attachment-card" data-attachment-id="${escapeHtml(attachment.id)}">
      <div>
        <strong>${escapeHtml(attachment.fileName || "Doklad")}</strong>
        <p>${escapeHtml(expenseKindLabel(attachment.expenseKind))} · ${escapeHtml(documentKindLabel(attachment.documentKind))}${attachment.heliosExpenseCodeLabel ? ` · ${escapeHtml(attachment.heliosExpenseCodeLabel)}` : ""}</p>
        <small>
          ${escapeHtml(attachment.documentDate || "bez data")}
          · ${escapeHtml(formatAttachmentAmount(attachment))}
          · přepočet ${escapeHtml(formatCurrency(attachmentAmountCzk(attachment)))}
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
            <tr><th>Vedlejší výdaje v řádcích</th><td data-summary="totalLineOther">${formatCurrency(calc.totalLineOther)}</td></tr>
            <tr><th>Přiložené doklady</th><td data-summary="totalAttachmentExpenses">${formatCurrency(calc.totalAttachmentExpenses)}</td></tr>
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

function field(label, path, value, type = "text", className = "", step = null, rate = false, help = "") {
  const attr = rate ? `data-rate-path="${escapeHtml(path.replace(/^rates\./, ""))}"` : `data-path="${escapeHtml(path)}"`;
  const stepAttr = step ? `step="${escapeHtml(step)}"` : "";
  const inputMode = type === "number" ? `inputmode="decimal"` : "";
  const helpIcon = help ? `<span class="help-icon" data-help="${escapeHtml(help)}" title="${escapeHtml(help)}">?</span>` : "";
  return `
    <label class="${escapeHtml(className)}">
      <span>${escapeHtml(label)}${helpIcon}</span>
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
  if (isImportedOrder(order)) {
    return buttons.join("");
  }
  if (order.status === "draft" || order._editingAsAccountant) {
    buttons.push(button("submit", "Předat ke schválení"));
  }
  if (order.status === "submitted" && !API_ENABLED) {
    buttons.push(button("approve", "Schválit"));
    buttons.push(button("return", "Vrátit"));
    buttons.push(button("reject", "Zamítnout", "danger"));
  }
  if (order.status === "approved") {
    buttons.push(button("settlement", "Otevřít vyúčtování"));
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

function orderStatusPill(order) {
  const status = effectiveOrderStatus(order);
  // If status is "submitted" and we have approvalStage, show more specific label
  if (status === "submitted" && order.approvalStage === "accounting") {
    return `<span class="status-pill status-${escapeHtml(status)}">Kontrola účetní</span>`;
  }
  return statusPill(status);
}

function effectiveOrderStatus(order) {
  if (hasReturnNotice(order)) return "returned";
  return isImportedOrder(order) ? "imported" : order.status;
}

function hasReturnNotice(order) {
  return Boolean(order && order.status === "draft" && order.returnNotice?.status === "returned");
}

function isImportedOrder(order) {
  return Boolean(order && (order.exportStatus === "exported" || order.heliosDocumentId));
}

function canEditOrder(order) {
  // Allow editing drafts owned by user
  if (order && order.status === "draft" && ownsOrder(order)) return true;
  // Allow accountants to edit orders they're reviewing
  if (order && order._editingAsAccountant) return true;
  return false;
}

function blockLockedOrderEdit(order) {
  if (canEditOrder(order)) return false;
  if (isImportedOrder(order)) {
    alert("Cestovní příkaz už je naimportovaný do Heliosu a nejde ho vrátit do úprav.");
    renderForm();
    return true;
  }
  alert("Schválený cestovní příkaz nejde upravovat přímo. Nejdřív ho vrať do úprav, oprav položky, znovu předej ke schválení a po schválení proveď novou synchronizaci do Heliosu.");
  renderForm();
  return true;
}

async function handleFormInput(event) {
  if (appMode === "requests") {
    const field = event.target.closest("[data-request-path]");
    if (field) return;
  }

  const vehicleDocumentInput = event.target.closest("[data-vehicle-document-file]");
  if (vehicleDocumentInput) {
    if (event.type !== "change") return;
    await addVehicleDocumentFiles(vehicleDocumentInput);
    vehicleDocumentInput.value = "";
    if (appMode === "profile") {
      profileState.message = "Ukládám přílohu OTP...";
      await saveProfileFromForm("Příloha OTP byla uložena.");
    } else if (appMode === "admin") {
      showTransientFormMessage("Příloha OTP je připravená. Pro trvalé uložení ulož uživatele.");
    }
    return;
  }

  const order = getSelectedOrder();
  if (!order) return;

  const attachmentInput = event.target.closest("[data-attachment-file]");
  if (attachmentInput) {
    if (event.type !== "change") return;
    if (blockLockedOrderEdit(order)) return;
    await addAttachmentFiles(order, attachmentInput);
    attachmentInput.value = "";
    touch(order);
    saveState();
    queueDraftSync(order);
    renderForm();
    renderList();
    return;
  }

  const lineField = event.target.closest("[data-line-field]");
  if (lineField) {
    if (blockLockedOrderEdit(order)) return;
    const row = lineField.closest("[data-line-id]");
    const line = order.routeLines.find((item) => item.id === row.dataset.lineId);
    if (!line) return;
    line[lineField.dataset.lineField] = parseInputValue(lineField);
    if (lineField.dataset.lineField === "segmentType") {
      if (line.segmentType === "foreign") {
        await refreshForeignTravelReferenceForOrder(order);
        applyForeignCountryToLine(line, line.countryCode || foreignTravelState.countries[0]?.code || "");
        renderForm();
      } else {
        clearForeignLine(line);
        renderForm();
      }
    }
    if (lineField.dataset.lineField === "countryCode") {
      applyForeignCountryToLine(line, line.countryCode);
      renderForm();
    }
    touch(order);
    saveState();
    queueDraftSync(order);
    refreshDerivedUi(order);
    renderList();
    return;
  }

  const vehiclePicker = event.target.closest("[data-vehicle-picker]");
  if (vehiclePicker) {
    if (blockLockedOrderEdit(order)) return;
    applyVehicleToOrder(order, vehiclePicker.value);
    touch(order);
    saveState();
    queueDraftSync(order);
    renderForm();
    renderList();
    return;
  }

  const approverPicker = event.target.closest("[data-approver-picker]");
  if (approverPicker) {
    if (blockLockedOrderEdit(order)) return;
    applyApproverToOrder(order, approverPicker.value);
    touch(order);
    saveState();
    queueDraftSync(order);
    renderList();
    return;
  }

  const pathField = event.target.closest("[data-path]");
  if (pathField) {
    if (blockLockedOrderEdit(order)) return;
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
    if (pathField.dataset.path === "trip.startAt") {
      await refreshForeignTravelReferenceForOrder(order);
      await refreshTripExchangeRate(order);
      refreshForeignLinesForOrder(order);
      renderForm();
    }
    if (pathField.dataset.path === "trip.currencyCode") {
      await refreshTripExchangeRate(order);
      renderForm();
    }
    touch(order);
    saveState();
    queueDraftSync(order);
    refreshDerivedUi(order);
    renderList();
    return;
  }

  const rateField = event.target.closest("[data-rate-path]");
  if (rateField) {
    if (blockLockedOrderEdit(order)) return;
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
    queueDraftSync(order);
    refreshDerivedUi(order);
    renderList();
  }
}

async function openOrderForEdit(travelOrderId) {
  if (!travelOrderId) return;

  // Get order data from approval detail
  const detail = approvalState.detail;
  if (!detail || detail.order?.id !== travelOrderId) {
    alert("Cestovní příkaz se nepodařilo najít.");
    return;
  }

  // Find the order in state by serverId
  let order = state.orders.find((o) => o.serverId === travelOrderId);

  if (!order) {
    // Create order from approval detail snapshot
    const snapshotOrder = detailSnapshotOrder(detail);
    const calc = detailCalculation(detail);

    order = {
      id: newId(),
      serverId: travelOrderId,
      number: detail.order.number || generateNumber(),
      status: detail.order.status || "submitted",
      approvalStage: detail.order.approvalStage || "",
      createdAt: detail.order.createdAt || new Date().toISOString(),
      updatedAt: detail.order.updatedAt || new Date().toISOString(),
      travelRequestId: detail.order.travelRequestId || "",
      employee: snapshotOrder.employee || {},
      trip: snapshotOrder.trip || {},
      approval: snapshotOrder.approval || {},
      vehicle: snapshotOrder.vehicle || {},
      routeLines: snapshotOrder.routeLines || [],
      attachments: snapshotOrder.attachments || [],
      history: [],
      // Set owner from detail.employee (the actual owner, not the accountant)
      ownerUserId: detail.employee?.id || "",
      ownerLogin: detail.employee?.email || "",
      ownerName: detail.employee?.name || "",
      // Mark this order as being edited by accountant for approval
      _editingAsAccountant: true,
    };
    state.orders.unshift(order);
  }

  // Switch to orders mode and select this order
  appMode = "orders";
  state.selectedId = order.id;
  saveState();
  render();
  resetViewportScroll();
}

async function handleFormClick(event) {
  const requestAction = event.target.closest("[data-request-action]");
  if (requestAction) {
    if (requestAction.dataset.requestAction === "save") {
      await saveRequestFromForm();
    } else if (requestAction.dataset.requestAction === "submit") {
      await submitRequestFromForm();
    } else if (requestAction.dataset.requestAction === "create-order") {
      await createOrderFromApprovedRequest();
    } else if (requestAction.dataset.requestAction === "new") {
      requestState.selectedId = null;
      renderRequests();
    }
    return;
  }

  const profileAction = event.target.closest("[data-profile-action]");
  if (profileAction) {
    if (profileAction.dataset.profileAction === "save-profile") {
      await saveProfileFromForm();
    } else if (profileAction.dataset.profileAction === "add-vehicle") {
      addAdminVehicleCard();
    } else if (profileAction.dataset.profileAction === "sync-erp") {
      await syncProfileWithErp();
    }
    return;
  }

  const adminAction = event.target.closest("[data-admin-action]");
  if (adminAction) {
    if (adminAction.dataset.adminAction === "save-user") {
      await saveAdminUserFromForm();
    } else if (adminAction.dataset.adminAction === "delete-user") {
      const selected = getSelectedAdminUser();
      await deleteAdminUser(selected);
    } else if (adminAction.dataset.adminAction === "add-vehicle") {
      addAdminVehicleCard();
    }
    return;
  }

  const removeAdminVehicle = event.target.closest("[data-admin-remove-vehicle]");
  if (removeAdminVehicle) {
    await removeAdminVehicleCard(removeAdminVehicle);
    return;
  }

  const removeVehicleDocument = event.target.closest("[data-remove-vehicle-document]");
  if (removeVehicleDocument) {
    await removeVehicleDocumentCard(removeVehicleDocument);
    return;
  }

  const downloadVehicleDoc = event.target.closest("[data-download-vehicle-document]");
  if (downloadVehicleDoc) {
    await downloadVehicleDocument(downloadVehicleDoc);
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
    } else if (action === "edit") {
      await openOrderForEdit(approvalAction.dataset.travelOrderId);
    } else {
      await decideApproval(action, approvalAction.dataset.approvalId);
    }
    return;
  }

  const requestApprovalAction = event.target.closest("[data-travel-request-action]");
  if (requestApprovalAction) {
    await decideTravelRequest(
      requestApprovalAction.dataset.travelRequestAction,
      requestApprovalAction.dataset.travelRequestId,
    );
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
    if (blockLockedOrderEdit(order)) return;
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
    if (blockLockedOrderEdit(order)) return;
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
    if (blockLockedOrderEdit(order)) return;
    const newLine = createNextLine(order);
    order.routeLines.push(newLine);
    touch(order);
    saveState();
    renderForm({ focusLineId: newLine.id });
    renderList();
    return;
  } else if (action === "sync-trip-dates") {
    if (blockLockedOrderEdit(order)) return;
    syncTripDates(order);
  } else if (action === "check-rates") {
    await refreshRateMonitor();
    renderForm();
    return;
  } else if (action === "reset-rates") {
    if (blockLockedOrderEdit(order)) return;
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
    // Remember if this is an accountant-edited order before submission
    const isAccountantEdit = order._editingAsAccountant === true;
    const submitted = await submitOrderForApproval(order);
    if (!submitted) return;

    // If accountant submitted someone else's order, return to approvals mode
    if (isAccountantEdit) {
      // Remove the order from local state (it's not ours)
      state.orders = state.orders.filter((o) => o.id !== order.id);
      saveState();
      // Switch back to approvals mode and refresh
      await setMode("approvals");
      return;
    }

    applyWorkflowAction(order, action);
  } else if (API_ENABLED && ["approve", "reject"].includes(action)) {
    alert("Schválení se provádí jen ve frontě vybraného schvalovatele.");
    return;
  } else if (API_ENABLED && action === "return" && order.status !== "approved") {
    alert("Vrácení ke schvalování se provádí jen ve frontě vybraného schvalovatele.");
    return;
  } else if (API_ENABLED && action === "return" && order.status === "approved") {
    if (isImportedOrder(order)) {
      alert("Cestovní příkaz už je naimportovaný do Heliosu a nejde ho vrátit do úprav.");
      return;
    }
    const returned = await returnOrderToDraft(order);
    if (!returned) return;
    applyWorkflowAction(order, action);
  } else {
    applyWorkflowAction(order, action);
  }

  touch(order);
  saveState();
  render();
}

async function returnOrderToDraft(order) {
  if (!ownsOrder(order)) {
    alert("Do úprav může cestovní příkaz vrátit jen jeho vlastník.");
    return false;
  }
  const orderId = order.serverId || order.id;
  if (!orderId) {
    alert("Cestovní příkaz nemá serverové ID.");
    return false;
  }
  try {
    const response = await apiFetch(`/api/travel-orders/${encodeURIComponent(orderId)}/return-to-draft`, {
      method: "POST",
      body: JSON.stringify({ reason: "owner_edit" }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      alert(returnToDraftErrorMessage(payload.error));
      return false;
    }
    order.serverId = payload.order?.travelOrderId || order.serverId;
    order.exportStatus = payload.order?.exportStatus || "not_ready";
    order.heliosDocumentId = payload.order?.heliosDocumentId || "";
    order.heliosExportedAt = payload.order?.heliosExportedAt || "";
    order.approval = order.approval || {};
    order.approval.approverUserId = order.approval.approverUserId || defaultOrderApprover()?.id || "";
    const sync = payload.order?.helios_staging_sync;
    if (sync && !sync.ok) {
      alert(`Cestovní příkaz je vrácený do úprav, ale Helios staging se nepodařilo aktualizovat: ${heliosStagingSyncError(sync.error)}.`);
    }
    return true;
  } catch {
    alert("Vrácení cestovního příkazu do úprav se nepodařilo.");
    return false;
  }
}

function returnToDraftErrorMessage(code) {
  if (code === "travel_order_not_found") return "Cestovní příkaz nebyl na serveru nalezen pod tímto uživatelem.";
  if (code === "travel_order_imported") return "Cestovní příkaz už je naimportovaný do Heliosu a nejde ho vrátit do úprav.";
  if (code === "travel_order_not_returnable") return "Cestovní příkaz teď není ve stavu, který lze vrátit do úprav.";
  return "Vrácení cestovního příkazu do úprav se nepodařilo.";
}

async function submitOrderForApproval(order) {
  // Allow accountants to submit orders they're editing for approval
  if (!ownsOrder(order) && !order._editingAsAccountant) {
    alert("Tento cestovní příkaz nemůže předat jiný uživatel než jeho vlastník.");
    return false;
  }
  // Don't normalize approver when accountant is submitting someone else's order
  if (!order._editingAsAccountant) {
    normalizeOrderApprover(order);
  }
  if (!order.approval?.approverUserId) {
    alert("Vyber schvalovatele cestovního příkazu.");
    return false;
  }
  // Don't check self-approval when accountant is submitting someone else's order
  if (!order._editingAsAccountant && order.approval.approverUserId === currentUserId()) {
    alert("Vlastní cestovní příkaz si nemůžeš schválit sám sobě.");
    return false;
  }
  const routeValidation = normalizeRouteLinesForSubmit(order);
  if (!routeValidation.ok) {
    activeTab = "settlement";
    render();
    alert(routeValidation.message);
    return false;
  }
  if (routeValidation.lines.length !== order.routeLines.length) {
    order.routeLines = routeValidation.lines;
  }
  const calculation = calculateOrder(order);
  try {
    const response = await apiFetch("/api/travel-orders/submit", {
      method: "POST",
      body: JSON.stringify({
        order,
        calculation,
        accountantSubmit: order._editingAsAccountant || false
      }),
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      alert(submitErrorMessageSafe(payload.error, payload));
      return false;
    }
    const payload = await response.json().catch(() => ({}));
    if (payload.submission?.travel_order_id) {
      order.serverId = payload.submission.travel_order_id;
    }
    if (payload.submission?.order_no) {
      order.number = payload.submission.order_no;
    }
    if (payload.submission?.approver_user_id) {
      order.approval = order.approval || {};
      order.approval.approverUserId = payload.submission.approver_user_id;
    }
    await refreshNotificationBadge();
    return true;
  } catch {
    alert("Předání ke schválení se nepodařilo.");
    return false;
  }
}

function normalizeRouteLinesForSubmit(order) {
  const tripPurpose = String(order?.trip?.purpose || "").trim();
  if (!tripPurpose) {
    return {
      ok: false,
      lines: [],
      message: "Doplň účel pracovní cesty v hlavičce cestovního příkazu.",
    };
  }

  const lines = [];
  for (const [index, line] of (order.routeLines || []).entries()) {
    const startAt = String(line.startAt || "").trim();
    const endAt = String(line.endAt || "").trim();
    const hasContent = routeLineHasBusinessContent(line);

    if (!hasContent && startAt && !endAt) continue;
    if (!hasContent && !startAt && !endAt) continue;
    if (!startAt || !endAt) {
      return {
        ok: false,
        lines,
        message: `Úsek ${index + 1} nemá vyplněné datum/čas odjezdu i příjezdu.`,
      };
    }
    const startKey = dateMinuteKey(startAt);
    const endKey = dateMinuteKey(endAt);
    if (startKey === null || endKey === null) {
      return {
        ok: false,
        lines,
        message: `Úsek ${index + 1} má neplatný datum/čas odjezdu nebo příjezdu.`,
      };
    }
    if (endKey < startKey) {
      return {
        ok: false,
        lines,
        message: `Úsek ${index + 1} má příjezd dříve než odjezd.`,
      };
    }
    if ((line.segmentType || "domestic") === "foreign" && !line.countryCode) {
      return {
        ok: false,
        lines,
        message: `Úsek ${index + 1} je zahraniční, ale nemá vybranou zemi.`,
      };
    }
    if (!String(line.from || "").trim() || !String(line.to || "").trim()) {
      return {
        ok: false,
        lines,
        message: `Úsek ${index + 1} nemá vyplněné pole Od a Do.`,
      };
    }
    if (!String(line.purpose || "").trim()) {
      return {
        ok: false,
        lines,
        message: `Úsek ${index + 1} nemá vyplněný účel úseku.`,
      };
    }
    lines.push(line);
  }

  if (!lines.length) {
    return {
      ok: false,
      lines,
      message: "Dopl ? alespo ? jeden úplný řádek vyúčtování cesty.",
    };
  }

  const tripDateValidation = validateTripDatesAgainstRouteLines(order.trip || {}, lines);
  if (!tripDateValidation.ok) {
    return { ...tripDateValidation, lines };
  }

  return { ok: true, lines };
}

function validateTripDatesAgainstRouteLines(trip, lines) {
  const headerStartKey = dateMinuteKey(trip.startAt);
  const headerEndKey = dateMinuteKey(trip.endAt);
  if (headerStartKey === null || headerEndKey === null) {
    return {
      ok: false,
      message: "V hlavičce dopl ? datum/čas začátku i konce pracovní cesty.",
    };
  }
  if (headerEndKey < headerStartKey) {
    return {
      ok: false,
      message: "V hlavičce je konec pracovní cesty dříve než začátek.",
    };
  }

  let firstStartKey = null;
  let firstStartValue = "";
  let lastEndKey = null;
  let lastEndValue = "";
  lines.forEach((line) => {
    const startKey = dateMinuteKey(line.startAt);
    const endKey = dateMinuteKey(line.endAt);
    if (firstStartKey === null || startKey < firstStartKey) {
      firstStartKey = startKey;
      firstStartValue = line.startAt;
    }
    if (lastEndKey === null || endKey > lastEndKey) {
      lastEndKey = endKey;
      lastEndValue = line.endAt;
    }
  });

  if (headerStartKey !== firstStartKey || headerEndKey !== lastEndKey) {
    return {
      ok: false,
      message: `Datumy v hlavičce neodpovídají položkám. V hlavičce má být ${formatDateTime(firstStartValue)} až ${formatDateTime(lastEndValue)}. Použij tlačítko "Převzít první a poslední čas" a odešli znovu.`,
    };
  }
  return { ok: true };
}

function dateMinuteKey(value) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return Math.floor(date.getTime() / 60000);
}

function routeLineHasBusinessContent(line) {
  return Boolean(
    String(line.from || "").trim() ||
    String(line.to || "").trim() ||
    String(line.company || "").trim() ||
    String(line.purpose || "").trim() ||
    String(line.countryCode || "").trim() ||
    number(line.km) ||
    number(line.fare) ||
    number(line.lodging) ||
    number(line.other) ||
    number(line.freeMeals)
  );
}

function submitErrorMessage(code, payload = {}) {
  if (code === "missing_approver") return "Nejdřív musí být nastavený schvalovatel.";
  if (code === "self_approval_not_allowed") return "Vlastní cestovní příkaz nejde schválit sám sobě.";
  if (code === "approver_not_available") return "Vybraný schvalovatel není pro tohoto zaměstnance povolený.";
  if (code === "invalid_approver") return "Vybraný schvalovatel není platný.";
  if (code === "missing_route_lines") return "Dopl ? alespo ? jeden úplný řádek vyúčtování cesty.";
  if (code === "route_line_missing_dates") return `Úsek ${payload.line || ""} nemá vyplněné datum/čas odjezdu i příjezdu.`;
  if (code === "route_line_missing_foreign_country") return `Úsek ${payload.line || ""} je zahraniční, ale nemá vybranou zemi.`;
  if (code === "route_line_invalid_dates") return `Úsek ${payload.line || ""} má neplatný datum/čas odjezdu nebo příjezdu.`;
  if (code === "route_line_invalid_range") return `Úsek ${payload.line || ""} má příjezd dříve než odjezd.`;
  if (code === "missing_trip_dates") return "V hlavičce dopl ? datum/čas začátku i konce pracovní cesty.";
  if (code === "trip_dates_invalid_range") return "V hlavičce je konec pracovní cesty dříve než začátek.";
  if (code === "trip_dates_mismatch") {
    return `Datumy v hlavičce neodpovídají položkám. V hlavičce má být ${formatDateTime(payload.expectedStartAt)} až ${formatDateTime(payload.expectedEndAt)}. Použij tlačítko "Převzít první a poslední čas" a odešli znovu.`;
  }
  return code || "Předání ke schválení se nepodařilo.";
}

function submitErrorMessageSafe(code, payload = {}) {
  if (code === "missing_trip_purpose") return "Doplň účel pracovní cesty v hlavičce cestovního příkazu.";
  if (code === "route_line_missing_places") return `Úsek ${payload.line || ""} nemá vyplněné pole Od a Do.`;
  if (code === "route_line_missing_purpose") return `Úsek ${payload.line || ""} nemá vyplněný účel úseku.`;
  if (code === "missing_travel_request") return "Pro založení cestovního příkazu nejdřív vyber schválenou žádost o vycestování.";
  if (code === "travel_request_not_approved") return "Vybraná žádost není schválená, nebo nepatří přihlášenému uživateli.";
  if (code === "no_accountant_available") return "Není dostupná žádná aktivní účetní pro kontrolu cestovního příkazu.";
  return submitErrorMessage(code, payload);
}

function pendingRequestCard(item) {
  return `
    <article class="approval-card">
      <div>
        <span class="route-index">${escapeHtml(item.requestNo || "Žádost")}</span>
        <p><span class="status-pill status-submitted">Žádost ke schválení</span></p>
        <h3>${escapeHtml(item.purpose || "Bez účelu")}</h3>
        <p>${escapeHtml(item.ownerName || "Neznámý žadatel")} · ${escapeHtml(item.destination || "Bez místa")}</p>
        <p>${escapeHtml(formatDateTime(item.startAt || ""))} - ${escapeHtml(formatDateTime(item.endAt || ""))}</p>
      </div>
      <div class="approval-actions">
        <button type="button" class="primary-btn" data-travel-request-action="approved" data-travel-request-id="${escapeHtml(item.id)}">Schválit</button>
        <button type="button" class="status-btn danger" data-travel-request-action="rejected" data-travel-request-id="${escapeHtml(item.id)}">Zamítnout</button>
      </div>
    </article>
  `;
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
  if (action === "submit" || action === "reopen") delete order.returnNotice;
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

async function duplicateOrder(order) {
  // If API is available, check for approved travel requests
  const token = localStorage.getItem(AUTH_TOKEN_KEY);
  console.log("duplicateOrder: API_ENABLED=", API_ENABLED, "token=", token ? "exists" : "missing");
  if (API_ENABLED && token) {
    try {
      const response = await fetch("/api/travel-requests/my/approved-without-order", {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (response.ok) {
        const availableRequests = await response.json();

        if (!availableRequests || availableRequests.length === 0) {
          showToast("Nelze duplikovat cestovní příkaz - není dostupná žádná schválená žádost o služební cestu", "warning", 6000);
          return;
        }

        // Show dialog to select travel request
        const selectedRequest = await showTravelRequestSelectionDialog(availableRequests);
        if (!selectedRequest) {
          // User cancelled
          return;
        }

        // Create duplicate with selected travel request
        const clone = structuredClone(order);

        // Reset all IDs and server-related fields
        clone.id = newId();
        clone.number = generateNumber();
        clone.status = "draft";

        // Clear all server-side and old travel request references
        delete clone.serverId;
        delete clone.travelRequestId;
        delete clone.requestNo;
        delete clone.heliosId;
        delete clone.importedAt;
        delete clone.exportedAt;
        delete clone.approvedAt;
        delete clone.submittedAt;
        delete clone.rejectedAt;
        delete clone.returnNotice;

        // Set new travel request
        clone.travelRequestId = selectedRequest.id;
        clone.requestNo = selectedRequest.requestNo;

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

        // Sync to server immediately to mark travel request as used
        console.log("Attempting to sync duplicate to server...", {
          id: clone.id,
          status: clone.status,
          travelRequestId: clone.travelRequestId,
          currentUser: !!currentUser,
          API_ENABLED
        });
        try {
          const syncResult = await syncDraftToServer(clone);
          console.log("Sync result:", syncResult);
          if (syncResult) {
            console.log("✅ Duplicate synced to server successfully");
          } else {
            console.warn("⚠️ Sync returned false - draft not saved to server");
            showToast("Duplikát vytvořen lokálně, ale neuložil se na server", "warning", 5000);
          }
        } catch (error) {
          console.error("❌ Failed to sync duplicate to server:", error);
          showToast("Duplikát vytvořen, ale nepodařilo se synchronizovat se serverem", "warning", 5000);
        }

        return;
      } else {
        showToast("Chyba při načítání schválených žádostí", "error");
        return;
      }
    } catch (error) {
      console.error("Error fetching travel requests:", error);
      showToast("Chyba při duplikaci cestovního příkazu", "error");
      return;
    }
  }

  // API není dostupné nebo uživatel není přihlášený
  showToast("Duplikace vyžaduje připojení k serveru a přihlášení", "info");
}

/**
 * Toast notification system
 * @param {string} message - The message to display
 * @param {string} type - Type: 'info', 'success', 'warning', 'error'
 * @param {number} duration - Duration in milliseconds (default 5000, 0 = no auto-dismiss)
 */
function showToast(message, type = 'info', duration = 5000) {
  // Ensure toast container exists
  let container = document.getElementById('toastContainer');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toastContainer';
    container.className = 'toast-container';
    document.body.appendChild(container);
  }

  // Icon mapping
  const icons = {
    info: 'ℹ️',
    success: '✓',
    warning: '⚠️',
    error: '✕'
  };

  // Create toast element
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `
    <div class="toast-icon">${icons[type] || icons.info}</div>
    <div class="toast-content">
      <p class="toast-message">${escapeHtml(message)}</p>
    </div>
    <button class="toast-close" aria-label="Zavřít" type="button">×</button>
  `;

  container.appendChild(toast);

  // Close button handler
  const closeBtn = toast.querySelector('.toast-close');
  closeBtn.addEventListener('click', () => dismissToast(toast));

  // Swipe to dismiss on mobile
  let startY = 0;
  let currentY = 0;
  toast.addEventListener('touchstart', (e) => {
    startY = e.touches[0].clientY;
  });
  toast.addEventListener('touchmove', (e) => {
    currentY = e.touches[0].clientY;
    const deltaY = startY - currentY;
    if (deltaY > 10) {
      // Swiping up
      toast.style.transform = `translateY(-${deltaY}px)`;
      toast.style.opacity = Math.max(0, 1 - (deltaY / 100));
    }
  });
  toast.addEventListener('touchend', () => {
    const deltaY = startY - currentY;
    if (deltaY > 50) {
      dismissToast(toast);
    } else {
      toast.style.transform = '';
      toast.style.opacity = '';
    }
  });

  // Auto dismiss
  if (duration > 0) {
    setTimeout(() => dismissToast(toast), duration);
  }

  return toast;
}

function dismissToast(toast) {
  if (!toast || !toast.parentElement) return;
  toast.classList.add('toast-exit');
  setTimeout(() => {
    toast.remove();
    // Remove container if empty
    const container = document.getElementById('toastContainer');
    if (container && container.children.length === 0) {
      container.remove();
    }
  }, 200);
}

/**
 * Tooltip system - shows help text when clicking help icon
 * @param {HTMLElement} icon - The help icon element
 * @param {string} message - The help message to display
 */
function showTooltip(icon, message) {
  // Remove any existing tooltips
  document.querySelectorAll('.tooltip-popup').forEach(t => t.remove());

  const tooltip = document.createElement('div');
  tooltip.className = 'tooltip-popup';
  tooltip.textContent = message;

  // Add to body first
  document.body.appendChild(tooltip);

  // Position tooltip - use fixed positioning
  const iconRect = icon.getBoundingClientRect();
  const tooltipRect = tooltip.getBoundingClientRect();

  let top = iconRect.bottom + 10;
  let left = iconRect.left + (iconRect.width / 2) - (tooltipRect.width / 2);

  // Keep tooltip on screen horizontally
  const margin = 20;
  if (left < margin) {
    left = margin;
  } else if (left + tooltipRect.width > window.innerWidth - margin) {
    left = window.innerWidth - tooltipRect.width - margin;
  }

  // Keep tooltip on screen vertically
  if (top + tooltipRect.height > window.innerHeight - margin) {
    top = iconRect.top - tooltipRect.height - 10;
  }

  // Make sure tooltip is never cut off at top
  if (top < margin) {
    top = margin;
  }

  tooltip.style.top = `${top}px`;
  tooltip.style.left = `${left}px`;

  console.log('Tooltip created:', { top, left, message, isMobile: window.innerWidth <= 768 });

  // Close on click outside
  const closeTooltip = (e) => {
    if (!tooltip.contains(e.target) && e.target !== icon) {
      console.log('Closing tooltip');
      tooltip.remove();
      document.removeEventListener('click', closeTooltip);
      document.removeEventListener('touchend', closeTooltip);
    }
  };

  // Add longer delay for mobile to prevent immediate close
  const isMobile = window.innerWidth <= 768;
  const delay = isMobile ? 1500 : 150;

  console.log('Setting up close listener with delay:', delay);

  setTimeout(() => {
    document.addEventListener('click', closeTooltip);
    if (isMobile) {
      document.addEventListener('touchend', closeTooltip);
    }
  }, delay);

  // Close on scroll
  const closeOnScroll = () => {
    tooltip.remove();
    document.removeEventListener('scroll', closeOnScroll, true);
    document.removeEventListener('click', closeTooltip);
    document.removeEventListener('touchend', closeTooltip);
  };
  document.addEventListener('scroll', closeOnScroll, true);
}

function initTooltips() {
  document.addEventListener('click', (e) => {
    const helpIcon = e.target.closest('.help-icon');
    if (helpIcon) {
      e.preventDefault();
      e.stopPropagation();
      const message = helpIcon.dataset.help || helpIcon.getAttribute('title') || 'Nápověda';
      showTooltip(helpIcon, message);
    }
  });
}

/**
 * Initialize Flatpickr datetime pickers for all datetime-local inputs
 */
function initDateTimePickers() {
  // Destroy existing flatpickr instances first
  document.querySelectorAll('input[type="datetime-local"]').forEach(input => {
    if (input._flatpickr) {
      input._flatpickr.destroy();
    }
  });

  // Initialize flatpickr on all datetime-local inputs
  document.querySelectorAll('input[type="datetime-local"]').forEach(input => {
    flatpickr(input, {
      enableTime: true,
      time_24hr: true,
      dateFormat: "Y-m-d H:i",
      altInput: true,
      altFormat: "j. n. Y H:i",
      locale: "cs",
      onChange: function(selectedDates, dateStr, instance) {
        // Trigger input event so the form updates
        input.value = dateStr;
        input.dispatchEvent(new Event('input', { bubbles: true }));
      }
    });
  });
}

function showTravelRequestSelectionDialog(requests) {
  return new Promise((resolve) => {
    const existing = document.getElementById("travelRequestSelectionOverlay");
    if (existing) existing.remove();

    const overlay = document.createElement("div");
    overlay.id = "travelRequestSelectionOverlay";
    overlay.className = "login-overlay";

    const requestRows = requests.map((req) => {
      const startAt = req.startAt ? new Date(req.startAt).toLocaleDateString("cs-CZ") : "";
      const endAt = req.endAt ? new Date(req.endAt).toLocaleDateString("cs-CZ") : "";
      const transport = req.transport ? (TRANSPORT_OPTIONS[req.transport] || req.transport) : "neuvedeno";
      return `
        <div class="request-row" data-request-id="${escapeHtml(req.id)}">
          <div>
            <strong>${escapeHtml(req.requestNo || "")}</strong> - ${escapeHtml(req.destination || "")}
          </div>
          <div style="font-size: 0.9em; color: #666;">
            ${startAt} – ${endAt} | Doprava: ${escapeHtml(transport)}
          </div>
          <div style="font-size: 0.85em; color: #777; margin-top: 4px;">
            ${escapeHtml(req.purpose || "")}
          </div>
        </div>
      `;
    }).join("");

    overlay.innerHTML = `
      <div class="login-panel" style="max-width: 600px;">
        <div>
          <h2>Vyberte schválenou žádost o služební cestu</h2>
          <p style="margin-top: 8px; color: #666;">Duplikace cestovního příkazu vyžaduje výběr schválené žádosti.</p>
        </div>
        <div class="request-list" style="max-height: 400px; overflow-y: auto; margin: 16px 0;">
          ${requestRows}
        </div>
        <div style="display: flex; gap: 8px; margin-top: 16px;">
          <button class="primary-btn" type="button" data-action="select" disabled>Vybrat</button>
          <button class="secondary-btn" type="button" data-action="cancel">Zrušit</button>
        </div>
      </div>
    `;

    document.body.append(overlay);

    let selectedRequestId = null;
    const selectBtn = overlay.querySelector('[data-action="select"]');
    const cancelBtn = overlay.querySelector('[data-action="cancel"]');
    const rowElements = overlay.querySelectorAll(".request-row");

    rowElements.forEach((row) => {
      row.addEventListener("click", () => {
        rowElements.forEach((r) => r.classList.remove("selected"));
        row.classList.add("selected");
        selectedRequestId = row.dataset.requestId;
        selectBtn.disabled = false;
      });
    });

    selectBtn.addEventListener("click", () => {
      overlay.remove();
      const selected = requests.find((r) => r.id === selectedRequestId);
      resolve(selected);
    });

    cancelBtn.addEventListener("click", () => {
      overlay.remove();
      resolve(null);
    });

    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) {
        overlay.remove();
        resolve(null);
      }
    });
  });
}

async function deleteOrder(order) {
  if (!ownsOrder(order)) {
    alert("Tento cestovní příkaz nepatří přihlášenému uživateli.");
    return;
  }
  const ok = confirm(`Smazat ${order.number}?`);
  if (!ok) return;

  // If order has serverId, delete from server
  if (API_ENABLED && order.serverId) {
    try {
      const response = await apiFetch(`/api/travel-orders/${order.serverId}`, {
        method: "DELETE",
      });

      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        if (error.error === "cannot_delete_non_draft") {
          alert(`Nelze smazat příkaz ${order.number} - příkaz již není rozpracovaný (status: ${error.status}).`);
        } else if (error.error === "order_not_found") {
          alert(`Příkaz ${order.number} nebyl nalezen na serveru.`);
        } else {
          alert(`Nepodařilo se smazat příkaz ${order.number} ze serveru.`);
        }
        return;
      }
    } catch (error) {
      alert(`Chyba při mazání příkazu: ${error.message}`);
      return;
    }
  }

  // Remove from local state
  state.orders = state.orders.filter((item) => item.id !== order.id);
  const remainingOwnOrders = visibleOrders();
  state.selectedId = remainingOwnOrders[0]?.id || null;

  // Don't auto-create a blank order - user should use "Nový příkaz" button
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
  const currencyCode = normalizeCurrencyCode(value("currencyCode"));
  const exchangeRate = currencyCode === "CZK" ? 1 : positiveNumber(value("exchangeRate"), 1);
  const amount = number(value("amount"));
  const heliosExpenseCodeId = value("heliosExpenseCodeId");
  const heliosExpenseCode = foreignTravelState.expenseCodes.find((code) => String(code.id) === String(heliosExpenseCodeId));
  return {
    expenseKind: value("expenseKind") || "other",
    heliosExpenseCodeId: heliosExpenseCodeId ? Number(heliosExpenseCodeId) : "",
    heliosExpenseCodeLabel: heliosExpenseCode?.label || "",
    documentKind: value("documentKind") || "receipt",
    documentDate: value("documentDate") || todayString(),
    amount,
    currencyCode,
    exchangeRate,
    amountCzk: Math.round(amount * exchangeRate * 100) / 100,
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
    totalLineOther: formatCurrency(calc.totalLineOther),
    totalOther: formatCurrency(calc.totalOther),
    totalAttachmentExpenses: formatCurrency(calc.totalAttachmentExpenses),
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
  const attachmentTotals = calculateAttachmentTotals(order);
  const totalKm = sum(lines, "km");
  const totalHours = sum(lines, "hours");
  const totalMeals = sum(lines, "meal");
  const totalFare = sum(lines, "fare");
  const totalBasicKmComp = sum(lines, "basicKmComp");
  const totalFuel = sum(lines, "fuelComp");
  const totalPrivateComp = sum(lines, "privateComp");
  const totalTransport = totalFare + totalPrivateComp;
  const totalLodging = sum(lines, "lodging");
  const totalLineOther = sum(lines, "other");
  const totalOther = totalLineOther + attachmentTotals.totalCzk;
  const totalGross = totalTransport + totalMeals + totalLodging + totalOther;
  const advance = number(order.trip.advance);
  const balance = totalGross - advance;

  return {
    lines,
    totalKm,
    totalHours,
    totalMeals,
    totalFare,
    totalBasicKmComp,
    totalFuel,
    totalPrivateComp,
    totalTransport,
    totalLodging,
    totalLineOther,
    totalOther,
    totalAttachmentExpenses: attachmentTotals.totalCzk,
    attachmentExpenses: attachmentTotals.items,
    totalGross,
    advance,
    balance,
    balanceRounded: Math.round(balance),
  };
}

function calculateAttachmentTotals(order) {
  const attachments = Array.isArray(order.attachments) ? order.attachments : [];
  const items = attachments.map((attachment) => ({
    id: attachment.id || "",
    expenseKind: attachment.expenseKind || "other",
    currencyCode: normalizeCurrencyCode(attachment.currencyCode),
    amount: number(attachment.amount),
    exchangeRate: attachmentExchangeRate(attachment),
    amountCzk: attachmentAmountCzk(attachment),
  }));
  return {
    items,
    totalCzk: sum(items, "amountCzk"),
  };
}

function calculateLine(order, line) {
  const isPrivateSegment = (line.segmentType || "domestic") === "private";
  const isForeignSegment = (line.segmentType || "domestic") === "foreign";
  const hours = hoursBetween(line.startAt, line.endAt);
  const km = number(line.km);
  const fare = isPrivateSegment ? 0 : number(line.fare);
  const lodging = isPrivateSegment ? 0 : number(line.lodging);
  const other = isPrivateSegment ? 0 : number(line.other);
  const meal = isPrivateSegment
    ? { base: 0, reduction: 0, amount: 0, currency: "CZK", exchangeRate: 1, foreignAmount: 0 }
    : isForeignSegment
      ? foreignMealAllowance(line, number(line.freeMeals))
      : mealAllowance(hours, number(line.freeMeals));
  const basicKmComp = !isPrivateSegment && line.transport === "private_car" ? km * getBasicKmRate(order) : 0;
  const fuelComp = !isPrivateSegment && line.transport === "private_car" ? km * getFuelKmRate(order) : 0;
  const privateComp = basicKmComp + fuelComp;
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
    mealCurrency: meal.currency || "CZK",
    mealExchangeRate: meal.exchangeRate || 1,
    mealForeignAmount: meal.foreignAmount || 0,
    basicKmComp,
    fuelComp,
    privateComp,
    total,
  };
}

function foreignMealAllowance(line, freeMeals) {
  const base = number(line.foreignMealRate);
  const exchangeRate = positiveNumber(line.foreignExchangeRate, 1);
  const meals = Math.max(0, Math.min(3, Math.round(freeMeals || 0)));
  const reduction = Math.min(base, base * 0.25 * meals);
  const foreignAmount = Math.max(0, base - reduction);
  return {
    base,
    reduction,
    amount: Math.round(foreignAmount * exchangeRate * 100) / 100,
    currency: normalizeCurrencyCode(line.foreignCurrencyCode || "EUR"),
    exchangeRate,
    foreignAmount,
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
  return getBasicKmRate(order) + getFuelKmRate(order);
}

function getBasicKmRate(order) {
  return number(order.vehicle.basicKmRate || state.rates.basicKmRate);
}

function getFuelKmRate(order) {
  const consumption = number(order.vehicle.consumption);
  const fuelPrice = number(order.vehicle.fuelPrice || state.rates.fuelPrices[order.vehicle.fuelType]);
  const secondaryFuelType = order.vehicle.secondaryFuelType;
  const secondaryConsumption = secondaryFuelType ? number(order.vehicle.secondaryConsumption) : 0;
  const secondaryFuelPrice = secondaryFuelType ? number(order.vehicle.secondaryFuelPrice || state.rates.fuelPrices[secondaryFuelType]) : 0;
  return (consumption / 100) * fuelPrice + (secondaryConsumption / 100) * secondaryFuelPrice;
}

function createBlankOrder() {
  const now = new Date().toISOString();
  const defaults = orderDefaults();
  return stampOrderOwner({
    id: newId(),
    number: generateNumber(),
    travelRequestId: "",
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
      currencyCode: "CZK",
      exchangeRate: 1,
      exchangeRateDate: "",
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
  const approver = defaultOrderApprover() || {};
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
  order.trip = order.trip || {};
  changed = fillMissing(order.trip, { currencyCode: "CZK", exchangeRate: 1, exchangeRateDate: "" }, ["currencyCode", "exchangeRate", "exchangeRateDate"]) || changed;
  changed = fillMissing(order.vehicle, defaults.vehicle, ["id", "brand", "plate", "engineVolume", "fuelType", "consumption", "fuelPriceMode", "fuelPrice", "secondaryFuelType", "secondaryConsumption", "secondaryFuelPriceMode", "secondaryFuelPrice", "basicKmRate"]) || changed;
  order.approval = order.approval || {};
  changed = normalizeOrderApprover(order) || changed;
  changed = fillMissing(order.approval, defaults.approval, ["approverUserId", "approverName"]) || changed;
  if (!Array.isArray(order.attachments)) {
    order.attachments = [];
    changed = true;
  }

  const firstLine = order.routeLines?.[0];
  (order.routeLines || []).forEach((line) => {
    if (!line.countryCode) line.countryCode = "";
    if (!line.foreignCurrencyCode) line.foreignCurrencyCode = "";
    if (line.foreignMealRate === undefined) line.foreignMealRate = 0;
    if (line.foreignExchangeRate === undefined) line.foreignExchangeRate = 1;
  });
  if (firstLine && (!firstLine.transport || firstLine.transport === "private_car") && firstLine.transport !== defaults.routeTransport) {
    firstLine.transport = defaults.routeTransport;
    changed = true;
  }

  if (changed) touch(order);
  return changed;
}

function normalizeOrderApprover(order) {
  const approvers = orderApproverOptions();
  const fallback = defaultOrderApprover();
  order.approval = order.approval || {};
  const currentId = order.approval.approverUserId || "";
  const isValid = currentId && approvers.some((approver) => approver.id === currentId);
  if (isValid) return false;

  order.approval = {
    approverUserId: fallback?.id || "",
    approverName: fallback?.name || fallback?.display_name || "",
  };
  return Boolean(currentId || fallback);
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
    segmentType: "domestic",
    countryCode: "",
    countryName: "",
    foreignCurrencyCode: "",
    foreignMealRate: 0,
    foreignExchangeRate: 1,
    foreignExchangeRateDate: "",
    foreignMealAmountCzk: 0,
    km: 0,
    transport: transport || orderDefaults().routeTransport,
    fare: 0,
    lodging: 0,
    other: 0,
    freeMeals: 0,
  };
}

function createNextLine(order) {
  const previous = Array.isArray(order?.routeLines) ? order.routeLines.at(-1) : null;
  const next = createBlankLine(previous?.transport || orderDefaults().routeTransport);
  if (!previous) return next;

  next.startAt = previous.endAt || "";
  next.from = previous.to || "";
  next.segmentType = SEGMENT_TYPE_OPTIONS[previous.segmentType] ? previous.segmentType : "domestic";
  if (next.segmentType === "foreign") {
    applyForeignCountryToLine(next, previous.countryCode || foreignTravelState.countries[0]?.code || "");
  }
  return next;
}

function applyForeignCountryToLine(line, countryCode) {
  const country = foreignTravelState.countries.find((item) => item.code === countryCode) || foreignTravelState.countries[0];
  if (!country) return;
  line.countryCode = country.code || "";
  line.countryName = country.label || country.code || "";
  line.foreignCurrencyCode = normalizeCurrencyCode(country.currencyCode);
  line.foreignMealRate = number(country.mealRate);
  line.foreignExchangeRate = positiveNumber(country.exchangeRate, 1);
  line.foreignExchangeRateDate = country.exchangeRateDate || "";
  line.foreignMealAmountCzk = Math.round(line.foreignMealRate * line.foreignExchangeRate * 100) / 100;
}

function clearForeignLine(line) {
  line.countryCode = "";
  line.countryName = "";
  line.foreignCurrencyCode = "";
  line.foreignMealRate = 0;
  line.foreignExchangeRate = 1;
  line.foreignExchangeRateDate = "";
  line.foreignMealAmountCzk = 0;
}

function refreshForeignLinesForOrder(order) {
  (order.routeLines || []).forEach((line) => {
    if ((line.segmentType || "domestic") === "foreign") {
      applyForeignCountryToLine(line, line.countryCode || foreignTravelState.countries[0]?.code || "");
    }
  });
}

async function refreshTripExchangeRate(order) {
  order.trip = order.trip || {};
  const currency = normalizeCurrencyCode(order.trip.currencyCode || "CZK");
  const rate = await fetchExchangeRate(currency, order.trip.startAt || todayString());
  order.trip.currencyCode = currency;
  order.trip.exchangeRate = positiveNumber(rate.exchangeRate, 1);
  order.trip.exchangeRateDate = normalizeDateOnly(rate.exchangeRateDate) || normalizeDateOnly(order.trip.startAt) || todayString();
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
  queueDraftSync(order);
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

function positiveNumber(value, fallback = 1) {
  const parsed = number(value);
  return parsed > 0 ? parsed : fallback;
}

function normalizeCurrencyCode(value) {
  const code = String(value || "CZK").trim().toUpperCase();
  return /^[A-Z]{3}$/.test(code) ? code : "CZK";
}

function attachmentExchangeRate(attachment) {
  const currencyCode = normalizeCurrencyCode(attachment?.currencyCode);
  if (currencyCode === "CZK") return 1;
  return positiveNumber(attachment?.exchangeRate, 1);
}

function attachmentAmountCzk(attachment) {
  const explicit = number(attachment?.amountCzk);
  if (explicit > 0) return explicit;
  return Math.round(number(attachment?.amount) * attachmentExchangeRate(attachment) * 100) / 100;
}

function formatAttachmentAmount(attachment) {
  const currencyCode = normalizeCurrencyCode(attachment?.currencyCode);
  return formatCurrency(number(attachment?.amount), currencyCode);
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

function formatCurrency(value, currency = "CZK") {
  return new Intl.NumberFormat("cs-CZ", {
    style: "currency",
    currency: normalizeCurrencyCode(currency),
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

function normalizeDateOnly(value) {
  const text = String(value || "").trim();
  const match = text.match(/^\d{4}-\d{2}-\d{2}/);
  return match ? match[0] : "";
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
        <td>${escapeHtml(segmentTypeLabel(line.segmentType))}</td>
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
      <div class="print-line"><strong>Stav:</strong> ${escapeHtml(STATUS_OPTIONS.find((item) => item.value === effectiveOrderStatus(order))?.label || effectiveOrderStatus(order))}</div>
    </div>
    <div class="print-line"><strong>Účel cesty:</strong> ${escapeHtml(order.trip.purpose)}</div>
    <div class="print-line"><strong>Spolucestující:</strong> ${escapeHtml(order.trip.companions)}</div>
    <h2>VYÚČTOVÁNÍ PRACOVNÍ CESTY</h2>
    <table class="print-table">
      <thead>
        <tr>
          <th>Odjezd</th>
          <th>Příjezd</th>
          <th>Typ</th>
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

// Final overrides: staged approval workflow (accounting -> manager).
async function decideApproval(action, approvalId) {
  const stage = String(approvalState.detail?.approval?.stage || "manager");
  let comment = "";
  if (action !== "approved") {
    const promptLabel = action === "returned" ? "Důvod vrácení k doplnění:" : "Důvod zamítnutí:";
    comment = prompt(promptLabel, "") || "";
    if (!comment.trim()) {
      approvalState.message = "Komentář je povinný.";
      renderApprovals();
      return;
    }
  }
  const response = await apiFetch(`/api/approval-requests/${approvalId}/decision`, {
    method: "POST",
    body: JSON.stringify({ action, comment }),
  });
  const payload = await response.json().catch(() => ({}));

  if (!response.ok) {
    approvalState.message = approvalDecisionErrorMessage(payload.error, stage);
  } else {
    approvalState.message = approvalDecisionMessage(action, payload.decision, stage);
    approvalState.detail = null;
    approvalState.selectedApprovalId = null;
  }

  await loadApprovalData();
  renderApprovals();
  refreshNotificationBadge();
}

function approvalDecisionMessage(action, decision = {}, stage = "manager") {
  if (action !== "approved") return "Rozhodnutí bylo uloženo.";
  if (stage === "accounting") return "Kontrola účetní byla schválena a předána finálnímu schvalovateli.";
  const sync = decision.helios_staging_sync;
  if (!sync) return "Cestovní příkaz byl schválen.";
  if (sync.ok) {
    return `Cestovní příkaz byl schválen a Helios staging byl aktualizován. K importu je ${Number(sync.activeImportCount || 0)} položek.`;
  }
  return `Cestovní příkaz byl schválen, ale Helios staging se nepodařilo aktualizovat: ${heliosStagingSyncError(sync.error)}.`;
}

function approvalDecisionErrorMessage(code = "", stage = "manager") {
  if (code === "invalid_action_for_accounting") return "V účetní fázi lze jen schválit nebo vrátit k doplnění.";
  if (code === "missing_return_comment") return "U vrácení k doplnění je povinný komentář.";
  if (code === "invalid_action_for_manager") return "Ve finální fázi lze jen schválit nebo zamítnout.";
  if (code === "missing_rejection_reason") return "U zamítnutí je povinný důvod.";
  if (code === "missing_final_approver") return "U zaměstnance chybí finální schvalovatel.";
  if (code === "approval_not_found") return "Schvalovací úkol nebyl nalezen nebo už byl vyřízen.";
  if (stage === "accounting") return "Rozhodnutí účetní se nepodařilo uložit.";
  return "Rozhodnutí se nepodařilo uložit.";
}

// ========================================
// Help Panel (Bottom Sheet) + FAB
// ========================================

const HELP_CONTENT = [
  {
    title: "Jak vytvořit cestovní příkaz",
    content: `
      <p>Cestovní příkazy se vytváří ze schválených žádostí o vycestování:</p>
      <ol>
        <li>Klikněte na tlačítko <strong>"Nový"</strong> v seznamu cestovních příkazů</li>
        <li>Vyberte schválenou žádost ze seznamu</li>
        <li>Vyplňte detaily cesty a jednotlivé úseky trasy</li>
        <li>Odešlete k schválení tlačítkem <strong>"Odeslat"</strong></li>
      </ol>
      <p>Pokud nemáte žádnou schválenou žádost, můžete:</p>
      <ul>
        <li>Duplikovat existující cestovní příkaz tlačítkem <strong>"Duplikovat"</strong></li>
        <li>Nebo požádat o vytvoření nové žádosti o vycestování</li>
      </ul>
    `
  },
  {
    title: "Jak vyplnit trasu cesty",
    content: `
      <p>Trasa se skládá z jednotlivých úseků, které reprezentují jednotlivé etapy vaší cesty:</p>
      <ol>
        <li>Klikněte na <strong>"+ Přidat úsek"</strong> pro vytvoření nového úseku</li>
        <li>Vyplňte <strong>datum a čas</strong> odjezdu a příjezdu</li>
        <li>Zadejte <strong>odkud</strong> a <strong>kam</strong> jedete (město, adresa)</li>
        <li>Uveďte <strong>účel</strong> návštěvy a <strong>název firmy</strong></li>
        <li>Vyberte <strong>typ dopravy</strong> (auto, vlak, letadlo, atd.)</li>
      </ol>
      <p><strong>Tip:</strong> Pokud jedete vlastním vozidlem, vyplňte počet kilometrů pro automatický výpočet náhrady.</p>
    `
  },
  {
    title: "Výdaje a náhrady",
    content: `
      <p>U každého úseku cesty můžete zadat jednotlivé výdaje:</p>
      <ul>
        <li><strong>Jízdné:</strong> Náklady na dopravu (vlak, letadlo, taxi, benzín)</li>
        <li><strong>Nocležné:</strong> Náklady na ubytování</li>
        <li><strong>Vedlejší výdaje:</strong> Parkování, telefon, drobné výdaje</li>
        <li><strong>Jídla zdarma:</strong> Počet jídel poskytnutých zdarma (snižuje stravné)</li>
      </ul>
      <p><strong>Stravné</strong> se počítá automaticky podle délky cesty a typu úseku (tuzemsko/zahraničí).</p>
      <p><strong>Náhrada za km:</strong> Při použití osobního vozidla se počítá podle základní sazby uvedené ve vašem profilu.</p>
    `
  },
  {
    title: "Stavy cestovního příkazu",
    content: `
      <dl>
        <dt><strong>Rozpracováno</strong></dt>
        <dd>Cestovní příkaz je v přípravě a ještě nebyl odeslán ke schválení. Můžete ho dále upravovat.</dd>

        <dt><strong>Odesláno</strong></dt>
        <dd>Cestovní příkaz čeká na schválení nadřízeným. Nelze ho již upravovat.</dd>

        <dt><strong>Schváleno</strong></dt>
        <dd>Cestovní příkaz byl schválen. Můžete vyrazit na cestu.</dd>

        <dt><strong>Zamítnuto</strong></dt>
        <dd>Cestovní příkaz nebyl schválen. Zkontrolujte poznámku schvalovatele.</dd>

        <dt><strong>Importováno</strong></dt>
        <dd>Cestovní příkaz byl přenesen do účetního systému (Helios).</dd>
      </dl>
    `
  },
  {
    title: "Schvalování cestovních příkazů",
    content: `
      <p>Proces schvalování probíhá takto:</p>
      <ol>
        <li>Po odeslání cestovního příkazu obdrží <strong>schvalovatel</strong> notifikaci e-mailem</li>
        <li>Schvalovatel zkontroluje detaily cesty a výdaje</li>
        <li>Schvalovatel může příkaz:
          <ul>
            <li><strong>Schválit</strong> - cestovní příkaz je schválen</li>
            <li><strong>Zamítnout</strong> - s povinnou poznámkou důvodu</li>
            <li><strong>Vrátit k doplnění</strong> - vyžaduje úpravu</li>
          </ul>
        </li>
        <li>O rozhodnutí obdržíte notifikaci e-mailem</li>
      </ol>
      <p><strong>Tip:</strong> Schvalovat můžete pouze pokud máte oprávnění schvalovatele.</p>
    `
  },
  {
    title: "Zahraniční cesty",
    content: `
      <p>Pro zahraniční cesty je třeba vyplnit dodatečné informace:</p>
      <ul>
        <li><strong>Typ úseku:</strong> Vyberte "Zahraničí" nebo "Zahraničí se stravným"</li>
        <li><strong>Země:</strong> Vyberte navštívenou zemi ze seznamu</li>
        <li><strong>Měna:</strong> Automaticky se doplní podle země</li>
        <li><strong>Kurz:</strong> Zadejte směnný kurz a datum jeho platnosti</li>
        <li><strong>Stravné v cizí měně:</strong> Automaticky se vypočte podle země</li>
      </ul>
      <p><strong>Pozor:</strong> Kurz měny musíte zadat ručně podle aktuálního kurzu ČNB.</p>
    `
  }
];

function initHelpPanel() {
  // Create FAB button
  const fab = document.createElement('button');
  fab.id = 'helpFab';
  fab.className = 'help-fab';
  fab.innerHTML = '?';
  fab.title = 'Nápověda';
  fab.type = 'button';
  fab.setAttribute('aria-label', 'Otevřít nápovědu');
  document.body.appendChild(fab);

  // Create bottom sheet
  const sheet = document.createElement('div');
  sheet.id = 'helpSheet';
  sheet.className = 'help-sheet';
  sheet.innerHTML = `
    <div class="help-sheet-overlay"></div>
    <div class="help-sheet-content">
      <div class="help-sheet-header">
        <h2>Nápověda</h2>
        <button class="help-sheet-close" type="button" aria-label="Zavřít">×</button>
      </div>
      <div class="help-sheet-body">
        ${HELP_CONTENT.map((section, index) => `
          <details class="help-section" ${index === 0 ? 'open' : ''}>
            <summary>${escapeHtml(section.title)}</summary>
            <div class="help-section-content">${section.content}</div>
          </details>
        `).join('')}
      </div>
    </div>
  `;
  document.body.appendChild(sheet);

  // Event handlers
  fab.addEventListener('click', () => openHelpSheet());
  sheet.querySelector('.help-sheet-overlay').addEventListener('click', () => closeHelpSheet());
  sheet.querySelector('.help-sheet-close').addEventListener('click', () => closeHelpSheet());

  // Close on Escape key
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && sheet.classList.contains('help-sheet-open')) {
      closeHelpSheet();
    }
  });
}

function openHelpSheet() {
  const sheet = document.getElementById('helpSheet');
  if (sheet) {
    sheet.classList.add('help-sheet-open');
    document.body.style.overflow = 'hidden'; // Prevent body scroll
  }
}

function closeHelpSheet() {
  const sheet = document.getElementById('helpSheet');
  if (sheet) {
    sheet.classList.remove('help-sheet-open');
    document.body.style.overflow = ''; // Restore body scroll
  }
}

