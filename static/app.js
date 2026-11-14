function formatINR(val) {
  if (val == null || isNaN(val)) return "₹0";
  const num = Math.round(Number(val));
  return "₹" + num.toLocaleString("en-IN");
}

// Frontend script for RL Travel Guide
// Master Questionnaire, Unified Personalisation, and Recommender Engine

// String title helper
String.prototype.title = function() {
  return this.replace(/\b\w/g, c => c.toUpperCase());
};

const state = {
  currentUser: null,
  currentStep: 1,
  questionnaire: null,
  config: null,
  detailedConfig: null,

  // Basic Profile State (starts with none pre-selected, no assumptions)
  basicAnswers: {
    age_group: null,
    travel_experience: null,
    companions: null,
    planning_approach: null,
    travel_goals: new Set(),
    place_interests: new Set(),
    experience_preference: null,
    dietary: new Set(),
    preferred_climate: null,
    budget_tier: null,
    assistance_autonomy: null
  },

  currentProfile: null,
  detailedProfile: null,

  // Unified Personal Profile (Adaptive Questionnaire with 10 sections + Past Trips)
  precision: { bank: null, answers: {}, context: {}, tab: "p1", exists: false, past_trips: [] }
};

// Recommendation engine client state
let recCache = {};
let currentOffset = 0;
let totalCandidateCount = 16;

// Helper: Format FastAPI / backend errors into human-readable text
function formatApiError(data, fallback = "An unexpected error occurred") {
  if (!data) return fallback;
  const detail = data.detail !== undefined ? data.detail : (data.message || data.error || data);
  if (!detail) return fallback;

  if (typeof detail === "string") {
    return detail;
  }

  const questionNames = {
    age_group: "Age Group",
    travel_experience: "Travel Experience",
    companions: "Companions",
    planning_approach: "Planning Approach",
    travel_goals: "Travel Goals",
    place_interests: "Place Interests",
    experience_preference: "Experience Preference",
    dietary: "Dietary Preferences",
    preferred_climate: "Preferred Climate",
    budget_tier: "Budget Tier",
    assistance_autonomy: "AI Assistance Level",
    interests: "Interests",
    destination_id: "Destination",
    start_date: "Start Date",
    end_date: "End Date",
    travellers_count: "Travellers Count",
    total_budget: "Total Budget",
    currency: "Currency"
  };

  if (Array.isArray(detail)) {
    const lines = detail.map(item => {
      if (typeof item === "string") return item;
      const rawField = Array.isArray(item.loc)
        ? item.loc.filter(l => l !== "body" && l !== "query" && l !== "path").join(".")
        : (item.loc || "");
      const fieldName = questionNames[rawField] || rawField;
      const msg = item.msg || item.message || JSON.stringify(item);
      return fieldName ? `${fieldName}: ${msg}` : msg;
    });
    return lines.join("\n");
  }

  if (typeof detail === "object") {
    if (detail.missing && Array.isArray(detail.missing)) {
      const missingLabels = detail.missing.map(m => {
        if (typeof m === "string") return questionNames[m] || m;
        if (typeof m === "object" && m !== null) {
          return m.question || m.label || questionNames[m.field] || m.field || m.id || JSON.stringify(m);
        }
        return String(m);
      });
      return (detail.message ? detail.message + ":\n• " : "Please answer the following required questions:\n• ") + missingLabels.join("\n• ");
    }
    if (detail.errors && Array.isArray(detail.errors)) {
      const errList = detail.errors.map(e => typeof e === "string" ? e : (e.msg || JSON.stringify(e)));
      return (detail.message ? detail.message + "\n• " : "") + errList.join("\n• ");
    }
    if (detail.message && typeof detail.message === "string") {
      return detail.message;
    }
    try {
      return Object.entries(detail).map(([k, v]) => {
        const label = questionNames[k] || k;
        return `${label}: ${typeof v === "object" ? JSON.stringify(v) : v}`;
      }).join("\n");
    } catch (e) {
      return JSON.stringify(detail);
    }
  }

  return String(detail);
}

function formatOptionLabel(val) {
  if (!val) return "";
  const key = String(val);
  if (state.questionnaire && state.questionnaire.questions) {
    for (const q of Object.values(state.questionnaire.questions)) {
      if (q && q.options) {
        const found = q.options.find(o => o.id === key);
        if (found && found.label) return found.label;
      }
    }
  }
  if (state.precision && state.precision.bank && state.precision.bank.questions) {
    for (const q of Object.values(state.precision.bank.questions)) {
      if (q && q.options) {
        const found = q.options.find(o => o.id === key);
        if (found && found.label) return found.label;
      }
    }
  }
  return key.replace(/_/g, " ").title();
}

// Icons map
const ICON_MAP = {
  relaxation: "fa-umbrella-beach",
  adventure: "fa-person-hiking",
  culture_history: "fa-landmark",
  nature: "fa-tree",
  food_dining: "fa-utensils",
  shopping: "fa-bag-shopping",
  socializing: "fa-users",
  photography: "fa-camera",
  growth: "fa-spa",
  quality_time: "fa-heart",
  work_study: "fa-briefcase",

  mountains_nature: "fa-mountain",
  beaches_coastal: "fa-water",
  forests_wildlife: "fa-paw",
  historical_sites: "fa-monument",
  museums_art: "fa-palette",
  local_markets: "fa-store",
  cafes_restaurants: "fa-mug-hot",
  religious_spiritual: "fa-place-of-worship",
  theme_parks: "fa-ticket",
  nightlife_music: "fa-music",
  villages_communities: "fa-house-chimney",
  architecture_photo: "fa-building-columns",

  alone: "fa-user",
  partner: "fa-heart",
  friends: "fa-user-group",
  family_children: "fa-people-roof",
  family_older: "fa-person-cane",
  tour_group: "fa-bus"
};

const PREC_KIND_STYLE = {
  constraint: { cls: "bg-rose-50 border-rose-200 text-rose-900", icon: "fa-shield-halved text-rose-600", label: "Hard Safety Rule" },
  penalty:    { cls: "bg-amber-50 border-amber-200 text-amber-900", icon: "fa-triangle-exclamation text-amber-600", label: "Preference Avoidance" },
  preference: { cls: "bg-blue-50 border-blue-200 text-blue-900", icon: "fa-heart text-blue-600", label: "Positive Weight" },
  rule:       { cls: "bg-slate-50 border-slate-200 text-slate-800", icon: "fa-compass text-indigo-600", label: "Planning Rule" }
};

// On Page Load
document.addEventListener("DOMContentLoaded", async () => {
  await loadQuestionnaireData();
  await initGoogleGIS();
  await checkPersistedSession();
});

async function loadQuestionnaireData() {
  try {
    const res = await fetch("/api/config/questionnaire");
    state.questionnaire = await res.json();
    renderBasicForm();
  } catch (err) {
    console.error("Error loading questionnaire:", err);
  }
}

async function checkPersistedSession() {
  const saved = localStorage.getItem("rl_travel_user");
  if (saved) {
    let storedUser;
    try {
      storedUser = JSON.parse(saved);
    } catch (_) {
      localStorage.removeItem("rl_travel_user");
      showView("auth");
      return;
    }
    state.currentUser = storedUser;
    try {
      // Validate saved sessions before loading the dashboard's other profile endpoints.
      const sessionRes = await fetch("/api/profile/status");
      if (sessionRes.status === 401 || sessionRes.status === 403) {
        localStorage.removeItem("rl_travel_user");
        state.currentUser = null;
        updateNavUser();
        showView("auth");
        const message = document.getElementById("authFormMessage");
        if (message) {
          message.textContent = "Your sign-in session expired. Sign in again to continue planning your trip.";
          message.classList.remove("hidden");
        }
        return;
      }
      if (!sessionRes.ok) throw new Error("Could not verify your sign-in session.");
      updateNavUser();
      if (state.currentUser.has_profile) {
        await loadUserProfile(state.currentUser.user_id);
      } else {
        showView("onboarding");
      }
      return;
    } catch (_) {
      // Keep the saved token on network/server errors so a transient outage does not sign out
      // the user, while avoiding partially loading the dashboard.
      state.currentUser = null;
      updateNavUser();
      showView("auth");
      const message = document.getElementById("authFormMessage");
      if (message) {
        message.textContent = "We could not verify your sign-in. Check your connection and try again.";
        message.classList.remove("hidden");
      }
      return;
    }
  }
  showView("auth");
}

function updateNavUser() {
  const navBadge = document.getElementById("navUserBadge");
  const navAvatar = document.getElementById("navAvatar");
  const navName = document.getElementById("navUserName");
  const inspector = document.getElementById("modelInspectorNavBtn");

  if (state.currentUser) {
    navBadge.classList.remove("hidden");
    if (inspector) inspector.classList.remove("hidden");
    navName.textContent = state.currentUser.display_name;
    navAvatar.textContent = state.currentUser.display_name.charAt(0).toUpperCase();
  } else {
    navBadge.classList.add("hidden");
    if (inspector) inspector.classList.add("hidden");
  }
}

// Switch between views
function showView(viewId) {
  document.getElementById("authView").classList.add("hidden");
  document.getElementById("onboardingView").classList.add("hidden");
  document.getElementById("dashboardView").classList.add("hidden");

  if (viewId === "auth") {
    document.getElementById("authView").classList.remove("hidden");
  } else if (viewId === "onboarding") {
    document.getElementById("onboardingView").classList.remove("hidden");
    goToStep(1);
  } else if (viewId === "dashboard") {
    document.getElementById("dashboardView").classList.remove("hidden");
  }
}

// Auth Tabs
let emailAuthMode = "login";

function switchAuthTab(tabName) {
  ["google", "manual", "phone"].forEach(t => {
    const btn = document.getElementById(`tab-${t}`);
    const content = document.getElementById(`authContent-${t}`);
    if (t === tabName) {
      btn.className = "flex-1 py-2 rounded-lg bg-white text-indigo-700 font-bold shadow-sm transition flex items-center justify-center gap-1.5";
      content.classList.remove("hidden");
    } else {
      btn.className = "flex-1 py-2 rounded-lg text-slate-600 transition flex items-center justify-center gap-1.5";
      content.classList.add("hidden");
    }
  });
  const phoneTab = document.getElementById("tab-phone");
  if (phoneTab) phoneTab.setAttribute("aria-selected", String(tabName === "phone"));
  if (tabName === "manual") updateEmailAuthMode();
}
switchAuthTab("google");

function updateEmailAuthMode() {
  const signup = emailAuthMode === "signup";
  const nameWrap = document.getElementById("manualNameWrap");
  const nameInput = document.getElementById("manualName");
  const password = document.getElementById("manualPassword");
  const submit = document.getElementById("emailSubmitBtn");
  const prompt = document.getElementById("emailModePrompt");
  const toggle = document.getElementById("emailModeToggle");
  if (nameWrap) nameWrap.classList.toggle("hidden", !signup);
  if (nameInput) nameInput.required = signup;
  if (password) {
    password.autocomplete = signup ? "new-password" : "current-password";
    password.minLength = signup ? 8 : 1;
    password.placeholder = signup ? "At least 8 characters" : "Enter your password";
  }
  if (submit) submit.textContent = signup ? "Create account" : "Sign in";
  if (prompt) prompt.textContent = signup ? "Already have an account?" : "New here?";
  if (toggle) toggle.textContent = signup ? "Sign in" : "Create an account";
}

function toggleEmailAuthMode() {
  emailAuthMode = emailAuthMode === "login" ? "signup" : "login";
  const message = document.getElementById("authFormMessage");
  if (message) message.classList.add("hidden");
  updateEmailAuthMode();
}

function togglePasswordVisibility() {
  const input = document.getElementById("manualPassword");
  const button = document.getElementById("passwordVisibilityBtn");
  if (!input || !button) return;
  input.type = input.type === "password" ? "text" : "password";
  button.textContent = input.type === "password" ? "Show" : "Hide";
}

// Auth API call
async function sendAuthRequest(payload) {
  const submit = document.getElementById("emailSubmitBtn");
  const message = document.getElementById("authFormMessage");
  if (submit) {
    submit.disabled = true;
    submit.textContent = payload.mode === "signup" ? "Creating account…" : "Signing in…";
  }
  if (message) message.classList.add("hidden");
  try {
    const res = await fetch("/api/auth", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (!res.ok) throw new Error(formatApiError(data, "Login failed"));

    state.currentUser = data;
    localStorage.setItem("rl_travel_user", JSON.stringify(data));
    updateNavUser();

    if (data.has_profile) {
      await loadUserProfile(data.user_id);
    } else {
      showView("onboarding");
    }
  } catch (err) {
    if (message) {
      message.textContent = err.message;
      message.classList.remove("hidden");
    } else {
      alert(err.message);
    }
  } finally {
    if (submit) {
      submit.disabled = false;
      updateEmailAuthMode();
    }
  }
}

// Google GIS SDK Hook
let googleGisInitializedFor = null;
async function initGoogleGIS() {
  try {
    const res = await fetch("/api/config/google");
    const data = await res.json();
    const clientId = data.client_id;

    const chooser = document.getElementById("googleChooserBtn");
    const setupLink = document.getElementById("googleSetupLink");
    const status = document.getElementById("googleAuthStatus");
    const btnContainer = document.getElementById("googleOfficialBtn");
    if (clientId && window.google && window.google.accounts) {
      if (googleGisInitializedFor === clientId && btnContainerHasGoogleButton()) return;
      google.accounts.id.initialize({
        client_id: clientId,
        callback: async (resp) => {
          try {
            const r = await fetch("/api/auth/google-token", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ credential: resp.credential })
            });
            const u = await r.json();
            if (!r.ok) throw new Error(formatApiError(u, "Google sign-in failed."));
            state.currentUser = u;
            localStorage.setItem("rl_travel_user", JSON.stringify(u));
            updateNavUser();
            if (u.has_profile) loadUserProfile(u.user_id);
            else showView("onboarding");
          } catch (err) {
            if (status) {
              status.textContent = err.message;
              status.classList.remove("hidden");
            }
          }
        },
        auto_select: false
      });

      if (btnContainer) {
        google.accounts.id.renderButton(btnContainer, { theme: "outline", size: "large", width: Math.min(320, btnContainer.clientWidth || 320) });
        if (chooser) chooser.classList.add("hidden");
        if (setupLink) setupLink.classList.add("hidden");
        if (status) status.classList.add("hidden");
        googleGisInitializedFor = clientId;
      }
    } else if (!clientId) {
      if (setupLink) setupLink.classList.add("hidden");
      if (status) {
        status.textContent = "Google sign-in hasn’t been configured on this site. Email sign-in is ready to use.";
        status.classList.remove("hidden");
      }
    } else if (status) {
      status.textContent = "Google sign-in couldn’t be loaded. Try email sign-in instead.";
      status.classList.remove("hidden");
    }
  } catch (e) {
    const status = document.getElementById("googleAuthStatus");
    if (status) {
      status.textContent = "Google sign-in couldn’t be loaded. Try email sign-in instead.";
      status.classList.remove("hidden");
    }
  }
}

function btnContainerHasGoogleButton() {
  const container = document.getElementById("googleOfficialBtn");
  return !!(container && container.querySelector("iframe"));
}

function startGoogleSignIn() {
  const clientId = document.getElementById("googleOfficialBtn");
  if (clientId && clientId.querySelector("iframe")) {
    const status = document.getElementById("googleAuthStatus");
    if (status) {
      status.textContent = "Use the Google button above to choose your account.";
      status.classList.remove("hidden");
    }
    return;
  }
  const status = document.getElementById("googleAuthStatus");
  if (status) {
    status.textContent = "Google sign-in isn’t configured. Choose Email to sign in or create an account.";
    status.classList.remove("hidden");
  }
}

async function saveGoogleClientId() {
  const input = document.getElementById("googleClientIdInput");
  const clientId = input ? input.value.trim() : "";
  if (!clientId) {
    alert("Please enter a Google Client ID.");
    return;
  }
  try {
    const res = await fetch("/api/config/google", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ client_id: clientId })
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(formatApiError(data, "Failed to save Google Client ID"));
    }
    closeModal("googleConfigModal");
    alert("Google Client ID saved successfully.");
    initGoogleGIS();
  } catch (err) {
    alert("Error saving Google Client ID: " + err.message);
  }
}

function handleManualAuth(e) {
  e.preventDefault();
  const name = document.getElementById("manualName").value.trim();
  const email = document.getElementById("manualEmail").value.trim();
  const password = document.getElementById("manualPassword").value;
  sendAuthRequest({
    provider: "email",
    mode: emailAuthMode,
    identifier: email,
    password,
    display_name: name || undefined
  });
}

function logout() {
  localStorage.removeItem("rl_travel_user");
  state.currentUser = null;
  state.currentProfile = null;
  state.detailedProfile = null;
  state.precision = { bank: state.precision.bank, answers: {}, context: {}, tab: "p1", exists: false, past_trips: [] };
  resetAnswers();
  emailAuthMode = "login";
  updateEmailAuthMode();
  updateNavUser();
  goToStep(1);
  showView("auth");
}

function resetAnswers() {
  state.basicAnswers = {
    age_group: null,
    travel_experience: null,
    companions: null,
    planning_approach: null,
    travel_goals: new Set(),
    place_interests: new Set(),
    experience_preference: null,
    dietary: new Set(),
    preferred_climate: null,
    budget_tier: null,
    assistance_autonomy: null
  };
  renderBasicForm();
}

// Modal generic open/close
function openModal(id) {
  const el = document.getElementById(id);
  if (el) el.classList.remove("hidden");
  if (id === "academicModal") loadAcademicInspector();
  if (id === "googleConfigModal") {
    fetch("/api/config/google").then(r => r.json()).then(d => {
      const inp = document.getElementById("googleClientIdInput");
      if (inp && d.client_id) inp.value = d.client_id;
    }).catch(() => {});
  }
}

function closeModal(id) {
  const el = typeof id === "string" ? document.getElementById(id) : id;
  if (el) el.classList.add("hidden");
  if (id === "activityRejectModal" || id === "activityAlternativeModal") {
    pendingFeedbackContext = null;
  }
}

// Global Escape listener to dismiss topmost visible modal
window.addEventListener("keydown", (e) => {
  if (e.key === "Escape" || e.keyCode === 27) {
    const visibleOverlays = Array.from(document.querySelectorAll(".fixed.inset-0:not(.hidden)"));
    if (visibleOverlays.length > 0) {
      const topModal = visibleOverlays[visibleOverlays.length - 1];
      closeModal(topModal.id || topModal);
      pendingFeedbackContext = null;
    }
  }
});

// ==========================================
// BASIC ONBOARDING FORM (30–60 SECONDS)
// ==========================================

function goToStep(step) {
  if (step === 2 && state.currentStep === 1) {
    if (!state.basicAnswers.age_group && !state.basicAnswers.travel_experience && !state.basicAnswers.companions) {
      alert("Please select at least one background option (age, experience, or companions) before continuing.");
      return;
    }
  }
  if (step === 3 && state.currentStep === 2) {
    if (state.basicAnswers.travel_goals.size < 2) {
      alert("Please select at least 2 travel goals before continuing.");
      return;
    }
    if (state.basicAnswers.place_interests.size < 2) {
      alert("Please select at least 2 types of places you enjoy before continuing.");
      return;
    }
  }

  state.currentStep = step;
  [1, 2, 3].forEach(s => {
    document.getElementById(`step-${s}`).classList.toggle("hidden", s !== step);
  });

  const titles = {
    1: "Background & Travel Style",
    2: "Goals, Places & Experience Style",
    3: "Food, Climate, Budget & Assistance"
  };
  document.getElementById("stepIndicator").textContent = `Step ${step} of 3`;
  document.getElementById("stepSubheading").textContent = titles[step];
  document.getElementById("progressBar").style.width = `${(step / 3) * 100}%`;
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function renderBasicForm() {
  if (!state.questionnaire) return;
  const q = state.questionnaire.questions || {};

  // Age Group
  renderPillOptions("basicAgeGroupGrid", (q.q1 || q.b01_age || {}).options || [], state.basicAnswers.age_group, (val) => {
    state.basicAnswers.age_group = val;
  });

  // Travel Experience
  renderCardOptions("basicExperienceGrid", (q.q2 || q.b04_experience || {}).options || [], state.basicAnswers.travel_experience, (val) => {
    state.basicAnswers.travel_experience = val;
  });

  // Companions
  renderIconCards("basicCompanionsGrid", (q.q3 || q.b03_companions || {}).options || [], state.basicAnswers.companions, (val) => {
    state.basicAnswers.companions = val;
  });

  // Planning Approach
  renderCardOptions("basicPlanningGrid", (q.q4 || q.planning_approach || {}).options || [], state.basicAnswers.planning_approach, (val) => {
    state.basicAnswers.planning_approach = val;
  });

  // Travel Goals (Multi, min 2 required, no max limit)
  renderMultiChips("basicGoalsGrid", (q.q5 || q.b05_travel_goals || {}).options || [], state.basicAnswers.travel_goals, "goalsCounter");

  // Place Types (Multi, min 2 required, no max limit)
  renderMultiChips("basicPlacesGrid", (q.q14 || q.b06_place_interests || {}).options || [], state.basicAnswers.place_interests, "placesCounter");

  // Experience Style
  renderCardOptions("basicExpStyleGrid", (q.q17 || q.b07_pace || {}).options || [], state.basicAnswers.experience_preference, (val) => {
    state.basicAnswers.experience_preference = val;
  });

  // Dietary Needs
  renderMultiPills("basicDietaryGrid", (q.q20 || q.b09_dietary || {}).options || [], state.basicAnswers.dietary);

  // Climate
  renderPillOptions("basicClimateGrid", (q.q26 || q.b11_climate || {}).options || [], state.basicAnswers.preferred_climate, (val) => {
    state.basicAnswers.preferred_climate = val;
  });

  // Budget
  renderCardOptions("basicBudgetGrid", (q.q32 || q.b10_budget || {}).options || [], state.basicAnswers.budget_tier, (val) => {
    state.basicAnswers.budget_tier = val;
  });

  // Assistance Autonomy
  renderCardOptions("basicAutonomyGrid", (q.q41 || q.b12_autonomy || {}).options || [], state.basicAnswers.assistance_autonomy, (val) => {
    state.basicAnswers.assistance_autonomy = val;
  });
}

// Helpers for Basic Controls
function renderPillOptions(containerId, options, currentVal, onSelect) {
  const container = document.getElementById(containerId);
  if (!container) return;
  container.innerHTML = "";
  (options || []).forEach(opt => {
    const btn = document.createElement("button");
    btn.type = "button";
    const isSel = opt.id === currentVal;
    btn.className = `px-3 py-1.5 rounded-xl text-xs font-semibold border transition ${
      isSel ? "bg-indigo-600 text-white border-indigo-600 shadow-xs" : "bg-white text-slate-700 border-slate-200 hover:border-slate-300"
    }`;
    btn.textContent = opt.label;
    btn.onclick = () => {
      Array.from(container.children).forEach(b => {
        b.className = "px-3 py-1.5 rounded-xl text-xs font-semibold border bg-white text-slate-700 border-slate-200 hover:border-slate-300 transition";
      });
      btn.className = "px-3 py-1.5 rounded-xl text-xs font-semibold border bg-indigo-600 text-white border-indigo-600 shadow-xs transition";
      onSelect(opt.id);
    };
    container.appendChild(btn);
  });
}

function renderCardOptions(containerId, options, currentVal, onSelect) {
  const container = document.getElementById(containerId);
  if (!container) return;
  container.innerHTML = "";
  (options || []).forEach(opt => {
    const card = document.createElement("div");
    const isSel = opt.id === currentVal;
    card.className = `selectable-card p-3 rounded-xl bg-white border cursor-pointer text-left transition ${isSel ? "selected" : ""}`;
    card.onclick = () => {
      Array.from(container.children).forEach(c => c.classList.remove("selected"));
      card.classList.add("selected");
      onSelect(opt.id);
    };
    card.innerHTML = `
      <div class="flex items-center justify-between">
        <span class="text-xs font-bold text-slate-800">${opt.label}</span>
        <i class="check-icon fa-solid fa-circle-check text-indigo-600 text-xs hidden"></i>
      </div>
      ${opt.desc ? `<p class="text-[11px] text-slate-500 mt-0.5 leading-tight">${opt.desc}</p>` : ""}
    `;
    container.appendChild(card);
  });
}

function renderIconCards(containerId, options, currentVal, onSelect) {
  const container = document.getElementById(containerId);
  if (!container) return;
  container.innerHTML = "";
  (options || []).forEach(opt => {
    const card = document.createElement("div");
    const isSel = opt.id === currentVal;
    card.className = `selectable-card p-2.5 rounded-xl bg-white border text-center cursor-pointer transition ${isSel ? "selected" : ""}`;
    card.onclick = () => {
      Array.from(container.children).forEach(c => c.classList.remove("selected"));
      card.classList.add("selected");
      onSelect(opt.id);
    };
    const iconClass = ICON_MAP[opt.id] || "fa-compass";
    card.innerHTML = `
      <i class="fa-solid ${iconClass} text-indigo-500 text-xs mb-1 block"></i>
      <span class="text-xs font-semibold text-slate-800 block">${opt.label}</span>
    `;
    container.appendChild(card);
  });
}

function renderMultiChips(containerId, options, activeSet, counterId) {
  const container = document.getElementById(containerId);
  if (!container) return;
  container.innerHTML = "";
  updateCounter(counterId, (activeSet ? activeSet.size : 0));

  (options || []).forEach(opt => {
    const isSel = activeSet.has(opt.id);
    const card = document.createElement("div");
    card.className = `selectable-card p-2.5 rounded-xl bg-white border flex items-center justify-between text-xs cursor-pointer transition ${isSel ? "selected" : ""}`;
    card.onclick = () => {
      if (activeSet.has(opt.id)) {
        activeSet.delete(opt.id);
        card.classList.remove("selected");
      } else {
        activeSet.add(opt.id);
        card.classList.add("selected");
      }
      updateCounter(counterId, activeSet.size);
    };

    const iconClass = opt.icon || ICON_MAP[opt.id] || "fa-tag";
    card.innerHTML = `
      <div class="flex items-center gap-2">
        <i class="fa-solid ${iconClass} text-indigo-500 text-xs"></i>
        <span class="font-semibold text-slate-800 text-[11px] leading-tight">${opt.label}</span>
      </div>
      <i class="check-icon fa-solid fa-circle-check text-indigo-600 text-xs hidden"></i>
    `;
    container.appendChild(card);
  });
}

function updateCounter(counterId, current) {
  const el = document.getElementById(counterId);
  if (el) el.textContent = `${current} selected (min 2 required)`;
}

function renderMultiPills(containerId, options, activeSet) {
  const container = document.getElementById(containerId);
  if (!container) return;
  container.innerHTML = "";
  (options || []).forEach(opt => {
    const btn = document.createElement("button");
    btn.type = "button";
    const isSel = activeSet.has(opt.id);
    btn.className = `px-3 py-1.5 rounded-xl text-xs font-semibold border transition ${
      isSel ? "bg-indigo-600 text-white border-indigo-600 shadow-xs" : "bg-white text-slate-700 border-slate-200 hover:border-slate-300"
    }`;
    btn.textContent = opt.label;
    btn.onclick = () => {
      if (opt.id === "none") {
        if (activeSet.has("none")) {
          // Deselect "none"
          activeSet.delete("none");
          btn.className = "px-3 py-1.5 rounded-xl text-xs font-semibold border bg-white text-slate-700 border-slate-200 hover:border-slate-300 transition";
          return;
        }
        activeSet.clear();
        activeSet.add("none");
        Array.from(container.children).forEach(b => {
          b.className = "px-3 py-1.5 rounded-xl text-xs font-semibold border bg-white text-slate-700 border-slate-200 hover:border-slate-300 transition";
        });
        btn.className = "px-3 py-1.5 rounded-xl text-xs font-semibold border bg-indigo-600 text-white border-indigo-600 shadow-xs transition";
        return;
      }
      
      // If user clicks a specific restriction, remove "none"
      if (activeSet.has("none")) {
        activeSet.delete("none");
        Array.from(container.children).forEach(b => {
          if (b.textContent.toLowerCase().includes("no restriction") || b.textContent.toLowerCase().includes("none")) {
            b.className = "px-3 py-1.5 rounded-xl text-xs font-semibold border bg-white text-slate-700 border-slate-200 hover:border-slate-300 transition";
          }
        });
      }

      if (activeSet.has(opt.id)) {
        activeSet.delete(opt.id);
        btn.className = "px-3 py-1.5 rounded-xl text-xs font-semibold border bg-white text-slate-700 border-slate-200 hover:border-slate-300 transition";
      } else {
        activeSet.add(opt.id);
        btn.className = "px-3 py-1.5 rounded-xl text-xs font-semibold border bg-indigo-600 text-white border-indigo-600 shadow-xs transition";
      }
    };
    container.appendChild(btn);
  });
}

// Basic Form Submit
async function handleProfileSubmit(e) {
  e.preventDefault();
  if (!state.currentUser) {
    alert("Please sign in first.");
    return;
  }

  const payload = {
    age_group: state.basicAnswers.age_group,
    travel_experience: state.basicAnswers.travel_experience,
    companions: state.basicAnswers.companions,
    planning_approach: state.basicAnswers.planning_approach,
    travel_goals: Array.from(state.basicAnswers.travel_goals),
    place_interests: Array.from(state.basicAnswers.place_interests),
    experience_preference: state.basicAnswers.experience_preference,
    dietary: Array.from(state.basicAnswers.dietary),
    preferred_climate: state.basicAnswers.preferred_climate,
    budget_tier: state.basicAnswers.budget_tier,
    assistance_autonomy: state.basicAnswers.assistance_autonomy,
    raw_answers: {
      ...state.basicAnswers,
      travel_goals: Array.from(state.basicAnswers.travel_goals),
      place_interests: Array.from(state.basicAnswers.place_interests),
      dietary: Array.from(state.basicAnswers.dietary)
    }
  };

  try {
    const res = await fetch(`/api/profile/${state.currentUser.user_id}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (!res.ok) throw new Error(formatApiError(data, "Save failed"));

    state.currentUser.has_profile = true;
    localStorage.setItem("rl_travel_user", JSON.stringify(state.currentUser));
    state.currentProfile = data;


    renderDashboard(data);
    showView("dashboard");
  } catch (err) {
    alert("Error: " + err.message);
  }
}

function editProfile() {
  if (state.currentProfile) {
    const p = state.currentProfile;
    const raw = p.raw_answers || {};
    state.basicAnswers = {
      age_group: p.age_group || raw.age_group || null,
      travel_experience: p.travel_experience || raw.travel_experience || null,
      companions: p.companions || raw.companions || null,
      planning_approach: p.planning_approach || raw.planning_approach || null,
      travel_goals: new Set(p.travel_goals || raw.travel_goals || []),
      place_interests: new Set(p.place_interests || raw.place_interests || []),
      experience_preference: p.experience_preference || raw.experience_preference || null,
      dietary: new Set(p.dietary || raw.dietary || []),
      preferred_climate: p.preferred_climate || raw.preferred_climate || null,
      budget_tier: p.budget_tier || raw.budget_tier || null,
      assistance_autonomy: p.assistance_autonomy || raw.assistance_autonomy || null,
    };
  }
  renderBasicForm();
  showView("onboarding");
  goToStep(1);
}

// ==========================================
// DASHBOARD VIEW
// ==========================================

async function loadUserProfile(userId) {
  try {
    const res = await fetch(`/api/profile/${userId}`);
    if (res.ok) {
      const data = await res.json();
      state.currentProfile = data;
      renderDashboard(data);
      showView("dashboard");
    } else {
      showView("onboarding");
    }
  } catch (err) {
    showView("onboarding");
  }
}

async function renderDashboard(profile) {
  document.getElementById("dashWelcomeName").textContent = `Welcome, ${state.currentUser.display_name}`;
  document.getElementById("dashSummaryText").textContent = profile.summary_text;

  document.getElementById("dashExperience").textContent = (profile.travel_experience || "Occasional").replace("_", " ").title();
  document.getElementById("dashCompanions").textContent = (profile.companions || "Solo").replace("_", " ").title();
  document.getElementById("dashBudget").textContent = humanLabel(profile.budget_tier || "Balanced");
  document.getElementById("dashClimate").textContent = (profile.preferred_climate || "Mild").replace("_", " ").title();

  // Goals chips
  const goalsContainer = document.getElementById("dashGoalsContainer");
  goalsContainer.innerHTML = "";
  const goals = profile.travel_goals && profile.travel_goals.length > 0 ? profile.travel_goals : ["relaxation", "sightseeing"];
  goals.forEach(g => {
    const chip = document.createElement("span");
    chip.className = "px-2.5 py-1 bg-indigo-50 text-indigo-700 text-xs font-semibold rounded-full border border-indigo-100 flex items-center gap-1.5";
    const ic = ICON_MAP[g] || "fa-circle";
    chip.innerHTML = `<i class="fa-solid ${ic} text-[10px]"></i> ${formatOptionLabel(g)}`;
    goalsContainer.appendChild(chip);
  });

  // Places chips
  const placesContainer = document.getElementById("dashPlacesContainer");
  placesContainer.innerHTML = "";
  const places = profile.place_interests && profile.place_interests.length > 0 ? profile.place_interests : (profile.interests || ["historical_sites"]);
  places.forEach(p => {
    const chip = document.createElement("span");
    chip.className = "px-2.5 py-1 bg-slate-100 text-slate-700 text-xs font-semibold rounded-full border border-slate-200 flex items-center gap-1.5";
    const ic = ICON_MAP[p] || "fa-map-pin";
    chip.innerHTML = `<i class="fa-solid ${ic} text-[10px] text-slate-500"></i> ${formatOptionLabel(p)}`;
    placesContainer.appendChild(chip);
  });

  // Load the unified personal profile state
  await syncUnifiedProfileCard(state.currentUser.user_id);

  // Load travel recommendations
  loadRecommendations();

  // Load planned trips and active itinerary
  loadUserTrips();
}

async function syncUnifiedProfileCard(userId) {
  const banner = document.getElementById("personalProfileBanner");
  const summaryCard = document.getElementById("personalProfileSummaryCard");

  try {
    // Check real completeness status from status endpoint
    const statusRes = await fetch(`/api/profile/${userId}/status`);
    if (statusRes.ok) {
      state.profileStatus = await statusRes.json();
    }

    const res = await fetch(`/api/profile/precision/${userId}`);
    if (!res.ok) {
      banner.classList.remove("hidden");
      summaryCard.classList.add("hidden");
      return;
    }
    const data = await res.json();
    
    const hasPrecision = !!(data && data.exists);
    state.precision.exists = hasPrecision;
    state.precision.answers = data.answers || {};

    if (!hasPrecision) {
      // Keep the central prominent Deep Personalisation box visible!
      banner.classList.remove("hidden");
      summaryCard.classList.remove("hidden");

      const badge = banner.querySelector(".inline-flex");
      if (badge) badge.innerHTML = `<i class="fa-solid fa-wand-magic-sparkles"></i> Deep AI Personalisation for India`;

      const bannerTitle = banner.querySelector("h3");
      if (bannerTitle) bannerTitle.textContent = "Complete Deep Personalisation for India";

      const bannerP = banner.querySelector("p");
      if (bannerP) bannerP.textContent = "Calibrate the AI guide for Indian travel realities: winding ghat roads, Vande Bharat & train classes, Himalayan altitude acclimatization, temple stairs, and regional food traditions.";

      const bannerBtn = banner.querySelector("button");
      if (bannerBtn) bannerBtn.innerHTML = `Complete Deep Personalisation (24 questions) &rarr;`;
    } else {
      // Deep personalisation is fully calibrated
      banner.classList.add("hidden");
      summaryCard.classList.remove("hidden");
      
      const statusEl = document.getElementById("personalProfileStatus");
      if (statusEl) statusEl.textContent = "Recommendations tailored to your travel style • Deep Personalisation Active (100%)";
    }

    // Display human-readable preferences
    const walkVal = data.answers.q74 || "m10";
    document.getElementById("dashWalkLimit").textContent = walkVal === "m5" ? "Light (<5 km)" : (walkVal === "m20" ? "High (15+ km)" : "Moderate (5–10 km)");

    const densityVal = data.answers.q60 || "balanced";
    document.getElementById("dashDensity").textContent = densityVal === "one_major" ? "1 Major Spot" : (densityVal === "packed" ? "Full Schedule" : "2–3 Activities");

    const stayVal = data.answers.d17_stay_types || data.answers.q56 || data.answers.q34 || "boutique_hotel";
    document.getElementById("dashStay").textContent = typeof stayVal === "string" ? formatOptionLabel(stayVal) : (Array.isArray(stayVal) ? stayVal.map(formatOptionLabel).join(", ") : "Boutique Hotel");

    const transitVal = data.answers.d14_road_transit || data.answers.q57 || data.answers.q35 || "public_transit";
    document.getElementById("dashTransit").textContent = typeof transitVal === "string" ? formatOptionLabel(transitVal) : "Public Transit";

    // Avoidances
    const avoidContainer = document.getElementById("dashAvoidancesContainer");
    avoidContainer.innerHTML = "";
    const avoidances = data.answers.d22_avoidances || data.answers.q12 || [];
    if (avoidances.length > 0) {
      avoidances.forEach(a => {
        const chip = document.createElement("span");
        chip.className = "px-2.5 py-1 bg-rose-50 text-rose-700 text-xs font-semibold rounded-md border border-rose-200 flex items-center gap-1.5";
        chip.innerHTML = `<i class="fa-solid fa-ban text-[10px]"></i> ${formatOptionLabel(a)}`;
        avoidContainer.appendChild(chip);
      });
    } else {
      avoidContainer.innerHTML = "<span class='text-xs text-slate-400 italic'>No special dislikes or restrictions selected</span>";
    }

    // Rules
    const rulesList = document.getElementById("personalProfileRulesList");
    rulesList.innerHTML = "";
    if (data.insights && data.insights.length > 0) {
      data.insights.slice(0, 6).forEach(i => {
        rulesList.appendChild(precInsightRow(i));
      });
    } else {
      rulesList.innerHTML = "<p class='text-xs text-slate-400 italic'>Personal travel rules active.</p>";
    }

    // Past Trips
    loadPastTripsSummary(userId);

  } catch (err) {
    banner.classList.remove("hidden");
    summaryCard.classList.add("hidden");
  }
}

async function loadPastTripsSummary(userId) {
  const tripsContainer = document.getElementById("dashPastTripsContainer");
  if (!tripsContainer) return;
  tripsContainer.innerHTML = "";

  try {
    const res = await fetch(`/api/profile/detailed/${userId}`);
    if (res.ok) {
      const data = await res.json();
      if (data.past_trips && data.past_trips.length > 0) {
        state.precision.past_trips = data.past_trips;
        data.past_trips.forEach(t => {
          const row = document.createElement("div");
          row.className = "p-2.5 rounded-xl bg-slate-50 border border-slate-200 text-xs flex justify-between items-center";
          row.innerHTML = `
            <div>
              <span class="font-bold text-slate-800">${t.destination}</span>
              <span class="text-amber-500 font-bold ml-1">${"★".repeat(Math.round(t.rating))}</span>
              <div class="text-[11px] text-slate-500">Highlight: ${t.favorite_activity || "General exploration"}</div>
            </div>
            ${t.skipped_or_disliked ? `<span class="text-[10px] bg-rose-100 text-rose-700 px-2 py-0.5 rounded font-medium">Disliked: ${t.skipped_or_disliked}</span>` : ""}
          `;
          tripsContainer.appendChild(row);
        });
        return;
      }
    }
  } catch (e) {}
  tripsContainer.innerHTML = "<span class='text-xs text-slate-400 italic'>No previous trips recorded yet</span>";
}

// ==========================================
// TRAVEL RECOMMENDATIONS (FEATURE TWO)
// ==========================================

async function loadRecommendations(isRefresh = false) {
  if (!state.currentUser) return;
  const basisEl = document.getElementById("recBasisSummary");
  const recGrid = document.getElementById("recommendedGrid");
  const trendGrid = document.getElementById("trendingGrid");
  const seaGrid = document.getElementById("seasonalGrid");

  if (!recGrid || !trendGrid || !seaGrid) return;

  if (!isRefresh) {
    recGrid.innerHTML = `<div class="col-span-full py-8 text-center text-xs text-slate-400"><i class="fa-solid fa-spinner fa-spin mr-1.5 text-indigo-600"></i> Finding recommendations matched to your profile...</div>`;
  }

  try {
    const res = await fetch(`/api/recommendations/${state.currentUser.user_id}?offset=${currentOffset}`);
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Personalised recommendations require a complete travel profile." }));
      const msg = formatApiError(err, "Complete your profile to unlock recommendations.");
      basisEl.textContent = msg;
      recGrid.innerHTML = `
        <div class="col-span-full py-10 px-6 bg-slate-50 border border-dashed border-amber-200 rounded-2xl text-center space-y-3">
          <div class="w-12 h-12 rounded-full bg-amber-100 text-amber-700 flex items-center justify-center mx-auto text-xl">
            <i class="fa-solid fa-lock"></i>
          </div>
          <h4 class="text-sm font-bold text-slate-800">Personalised Recommendations Locked</h4>
          <p class="text-xs text-slate-600 max-w-md mx-auto leading-relaxed">
            ${msg}
          </p>
          <div class="pt-2">
            <button onclick="openPersonalProfileModal()" class="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white font-bold text-xs rounded-xl shadow transition">
              Complete Personal Travel Profile &rarr;
            </button>
          </div>
        </div>
      `;
      return;
    }

    const data = await res.json();
    basisEl.textContent = data.basis_summary;
    totalCandidateCount = data.total_candidates || 16;

    // Cache destination cards for instant Explore Modal lookup
    (data.recommended_for_you || []).forEach(d => { recCache[d.id] = d; });
    (data.trending_trips || []).forEach(d => { recCache[d.id] = d; });
    (data.seasonal_and_upcoming || []).forEach(d => { recCache[d.id] = d; });

    // Render Recommended For You
    recGrid.innerHTML = "";
    if (data.recommended_for_you && data.recommended_for_you.length > 0) {
      data.recommended_for_you.forEach(item => {
        recGrid.appendChild(renderRecommendationCard(item, "recommended"));
      });
    } else {
      recGrid.innerHTML = `<div class="col-span-full py-4 text-center text-xs text-slate-400 italic">No matches found for this page. Click Refresh Options to cycle through destinations.</div>`;
    }

    // Render Trending Trips
    trendGrid.innerHTML = "";
    if (data.trending_trips && data.trending_trips.length > 0) {
      data.trending_trips.forEach(item => {
        trendGrid.appendChild(renderRecommendationCard(item, "trending"));
      });
    }

    // Render Seasonal Experiences
    seaGrid.innerHTML = "";
    if (data.seasonal_and_upcoming && data.seasonal_and_upcoming.length > 0) {
      data.seasonal_and_upcoming.forEach(item => {
        seaGrid.appendChild(renderRecommendationCard(item, "seasonal"));
      });
    }
  } catch (err) {
    basisEl.textContent = "Unable to fetch recommendations at this time.";
    recGrid.innerHTML = `<div class="col-span-full py-4 text-center text-xs text-rose-500">Failed to load recommendations: ${err.message}</div>`;
  }
}

async function refreshRecommendations() {
  if (!state.currentUser) return;
  const icon = document.getElementById("refreshIcon");
  if (icon) icon.classList.add("fa-spin");
  currentOffset = (currentOffset + 4) % (totalCandidateCount || 16);
  await loadRecommendations(true);
  if (icon) icon.classList.remove("fa-spin");
}

function renderRecommendationCard(item, category) {
  const card = document.createElement("div");
  card.className = "bg-white rounded-2xl border border-slate-200 shadow-sm hover:shadow-md transition flex flex-col justify-between overflow-hidden group";

  // Category badge
  let badgeHtml = "";
  if (category === "recommended") {
    badgeHtml = `<span class="px-2.5 py-1 rounded-full text-[11px] font-bold bg-white/95 text-emerald-800 shadow-sm backdrop-blur-sm flex items-center gap-1">
      <i class="fa-solid fa-sparkles text-emerald-600 text-[10px]"></i> ${Math.round(item.match_score)}% Match
    </span>`;
  } else if (category === "trending") {
    badgeHtml = `<span class="px-2.5 py-1 rounded-full text-[11px] font-bold bg-white/95 text-amber-800 shadow-sm backdrop-blur-sm flex items-center gap-1">
      <i class="fa-solid fa-fire text-amber-500 text-[10px]"></i> Trending now
    </span>`;
  } else if (category === "seasonal") {
    badgeHtml = `<span class="px-2.5 py-1 rounded-full text-[11px] font-bold bg-white/95 text-sky-800 shadow-sm backdrop-blur-sm flex items-center gap-1">
      <i class="fa-regular fa-calendar-check text-sky-500 text-[10px]"></i> ${item.seasonal_timing || "Seasonal"}
    </span>`;
  }

  // Tags HTML
  const tagsHtml = (item.tags || []).slice(0, 3).map(tag => `
    <span class="px-2 py-0.5 rounded-md bg-slate-100 text-slate-600 text-[10px] font-medium">${tag}</span>
  `).join("");

  const isShortlisted = !!item.is_shortlisted;

  card.innerHTML = `
    <div>
      <!-- Photo banner with offline fallback -->
      <div class="relative h-44 w-full bg-slate-100 overflow-hidden">
        <img src="${item.image_url || '/static/images/destination-placeholder.svg'}" alt="${item.name}" class="w-full h-full object-cover group-hover:scale-105 transition duration-300"
          onerror="this.onerror=null; this.src='/static/images/destination-placeholder.svg';">
        <div class="absolute inset-0 bg-gradient-to-t from-slate-900/60 via-transparent to-transparent"></div>
        <div class="absolute top-3 left-3">${badgeHtml}</div>
        <button type="button" onclick="toggleShortlist('${item.id}', this)" data-shortlist-dest="${item.id}"
          class="absolute top-3 right-3 w-8 h-8 rounded-full bg-white/90 hover:bg-white text-slate-700 shadow flex items-center justify-center transition"
          title="${isShortlisted ? 'Remove from shortlist' : 'Add to shortlist'}">
          <i class="${isShortlisted ? 'fa-solid text-amber-500' : 'fa-regular'} fa-bookmark text-xs"></i>
        </button>
        <div class="absolute bottom-2.5 left-3 text-white">
          <h4 class="text-base font-bold tracking-tight leading-tight">${item.name}</h4>
          <span class="text-[11px] text-slate-200 font-medium">${item.country}</span>
        </div>
      </div>

      <!-- Card details -->
      <div class="p-4 space-y-3">
        <!-- Duration & Budget & Tags -->
        <div class="flex items-center justify-between text-[11px] text-slate-500 pb-1 border-b border-slate-100">
          <span class="font-medium flex items-center gap-1">
            <i class="fa-regular fa-clock text-slate-400"></i> ${item.duration || '4–6 days'}
          </span>
          <span class="font-semibold text-slate-700">
            ${escapeHtml(humanLabel(item.budget_tier))}
          </span>
        </div>

        <div class="flex flex-wrap gap-1">
          ${tagsHtml}
        </div>

        <!-- Tagline & Because you said attribution -->
        ${item.because_you_said ? `
          <div class="p-2 rounded-lg bg-indigo-50/90 border border-indigo-100 text-[11px] text-indigo-900 leading-snug">
            <span class="font-bold text-indigo-700 block text-[10px] uppercase tracking-wider mb-0.5"><i class="fa-solid fa-sparkles text-amber-500 mr-1"></i>Because you said:</span>
            ${item.because_you_said}
          </div>
        ` : `
          <p class="text-xs text-slate-600 line-clamp-2 leading-relaxed">
            <strong class="text-slate-800 font-semibold">Why this fits you:</strong> ${item.why_it_suits}
          </p>
        `}
      </div>
    </div>

    <!-- Actions -->
    <div class="p-4 pt-0 flex items-center gap-2">
      <button type="button" onclick="openExploreModal('${item.id}')" class="flex-1 py-2 text-xs font-semibold text-indigo-600 bg-indigo-50 hover:bg-indigo-100 rounded-xl transition text-center">
        Explore Details
      </button>
      <button type="button" onclick="toggleShortlist('${item.id}', this)" data-shortlist-btn="${item.id}"
        class="px-3 py-2 text-xs font-semibold rounded-xl border transition flex items-center gap-1.5 ${isShortlisted ? 'bg-amber-50 border-amber-200 text-amber-800' : 'border-slate-200 text-slate-600 hover:bg-slate-50'}">
        <i class="${isShortlisted ? 'fa-solid text-amber-500' : 'fa-regular'} fa-bookmark"></i>
        <span>${isShortlisted ? 'Saved' : 'Shortlist'}</span>
      </button>
    </div>
  `;

  return card;
}

// Explore Modal (Task 5: Complete Travel Experience)
let currentExploredDestination = null;

async function openExploreModal(destId) {
  const item = recCache[destId] || {};
  openModal("exploreModal");

  const loadingEl = document.getElementById("exploreLoadingState");
  const contentEl = document.getElementById("exploreContentContainer");
  if (loadingEl) loadingEl.classList.remove("hidden");
  if (contentEl) contentEl.classList.add("hidden");

  // Immediate preview from cache if available
  const imgEl = document.getElementById("exploreImg");
  if (imgEl && item.image_url) {
    imgEl.src = item.image_url;
    imgEl.onerror = () => { imgEl.onerror = null; imgEl.src = '/static/images/destination-placeholder.svg'; };
  }
  if (document.getElementById("exploreTitle")) {
    document.getElementById("exploreTitle").textContent = item.name || destId.replace(/_/g, " ");
  }
  if (document.getElementById("exploreBadge")) {
    document.getElementById("exploreBadge").textContent = `${Math.round(item.match_score || 95)}% Match`;
  }

  try {
    const userId = state.currentUser ? state.currentUser.user_id : "";
    const res = await fetch(`/api/destination/${encodeURIComponent(destId)}/explore?user_id=${encodeURIComponent(userId)}&duration_days=3`);
    if (!res.ok) throw new Error("Failed to load destination details");
    const data = await res.json();
    currentExploredDestination = data;

    // 1. Header & Quick Meta
    if (imgEl && data.image_url) imgEl.src = data.image_url;
    document.getElementById("exploreTitle").textContent = data.name;
    document.getElementById("exploreCountry").textContent = data.country || "India";
    const stateBadge = document.getElementById("exploreStateBadge");
    if (stateBadge) stateBadge.textContent = data.state || "India";
    if (document.getElementById("exploreDuration")) {
      document.getElementById("exploreDuration").textContent = `${data.recommended_duration_days || 3} Days Recommended`;
    }
    if (document.getElementById("exploreSeasonTag")) {
      document.getElementById("exploreSeasonTag").textContent = data.best_season_and_weather;
    }

    // Tags
    const tagsCont = document.getElementById("exploreTags");
    if (tagsCont) {
      tagsCont.innerHTML = "";
      (data.tags || []).forEach(t => {
        const s = document.createElement("span");
        s.className = "px-2.5 py-0.5 rounded-full bg-slate-100 text-slate-700 text-xs font-semibold";
        s.textContent = t;
        tagsCont.appendChild(s);
      });
    }

    // 2. Overview & Atmosphere
    const overviewEl = document.getElementById("exploreOverview");
    if (overviewEl) overviewEl.textContent = data.overview;

    // 3. Personalized "Why Recommended For You"
    const whyList = document.getElementById("exploreWhyList");
    if (whyList) {
      whyList.innerHTML = "";
      (data.why_recommended_for_you || []).forEach(r => {
        const li = document.createElement("li");
        li.className = "flex items-start gap-2 leading-relaxed";
        li.innerHTML = `<i class="fa-solid fa-sparkles text-indigo-600 text-xs mt-0.5 shrink-0"></i> <span>${r}</span>`;
        whyList.appendChild(li);
      });
    }

    // 4. Main Attractions Grid
    const attGrid = document.getElementById("exploreAttractionsGrid");
    if (attGrid) {
      attGrid.innerHTML = "";
      (data.main_attractions || []).forEach(att => {
        const card = document.createElement("div");
        card.className = "p-3 rounded-xl border border-slate-200 bg-white space-y-1.5 shadow-xs hover:border-slate-300 transition";
        card.innerHTML = `
          <div class="flex items-center justify-between gap-1">
            <span class="font-bold text-slate-800 text-xs truncate">${escapeHtml(att.name)}</span>
            <span class="text-[10px] px-2 py-0.5 rounded font-bold ${att.is_cost_verified ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-100 text-slate-600'} shrink-0">
              ${escapeHtml(att.cost_label)}
            </span>
          </div>
          <div class="flex items-center gap-2 text-[10px] text-slate-500">
            <span><i class="fa-solid fa-location-dot text-indigo-500 mr-1"></i>${escapeHtml(att.neighborhood)}</span>
            <span>&bull;</span>
            <span><i class="fa-regular fa-clock text-slate-400 mr-1"></i>${escapeHtml(att.opening_hours)}</span>
          </div>
          <p class="text-[11px] text-slate-600 line-clamp-2 leading-relaxed">${escapeHtml(att.description)}</p>
        `;
        attGrid.appendChild(card);
      });
    }

    // 5. Suggested Day-Wise Itinerary
    const itinDaysEl = document.getElementById("exploreItineraryDays");
    if (itinDaysEl) {
      itinDaysEl.innerHTML = "";
      (data.suggested_itinerary || []).forEach(day => {
        const dCard = document.createElement("div");
        dCard.className = "p-3.5 rounded-xl border border-slate-200 bg-slate-50/70 space-y-2.5";
        
        let slotsHtml = "";
        (day.slots || []).forEach(slot => {
          if (slot.slot === "Midday Commute & Lunch") {
            slotsHtml += `
              <div class="p-2 rounded-lg bg-indigo-50/80 border border-indigo-100 text-[11px] flex items-center justify-between gap-2">
                <span class="text-indigo-900 font-semibold flex items-center gap-1.5">
                  <i class="fa-solid fa-taxi text-indigo-600"></i> ${escapeHtml(slot.transit_note)}
                </span>
                <span class="text-indigo-700 font-bold truncate">
                  <i class="fa-solid fa-utensils mr-1"></i> ${escapeHtml(slot.lunch_spot)}
                </span>
              </div>
            `;
          } else {
            slotsHtml += `
              <div class="p-2 rounded-lg bg-white border border-slate-200 text-[11px] space-y-1">
                <div class="flex items-center justify-between">
                  <span class="font-bold text-slate-800">${escapeHtml(slot.slot)} &bull; ${escapeHtml(slot.title)}</span>
                  <span class="text-[10px] text-slate-400">${escapeHtml(slot.neighborhood)}</span>
                </div>
                <p class="text-slate-600 text-[10px] leading-relaxed">${escapeHtml(slot.description)}</p>
              </div>
            `;
          }
        });

        dCard.innerHTML = `
          <h5 class="font-bold text-slate-900 text-xs flex items-center gap-1.5">
            <span class="w-5 h-5 rounded-full bg-indigo-600 text-white flex items-center justify-center text-[10px]">${day.day_number}</span>
            <span>${escapeHtml(day.title)}</span>
          </h5>
          <div class="space-y-1.5">${slotsHtml}</div>
        `;
        itinDaysEl.appendChild(dCard);
      });
    }

    // 6. Culinary & Dining Grid
    const foodGrid = document.getElementById("exploreFoodGrid");
    if (foodGrid) {
      foodGrid.innerHTML = "";
      (data.food_experiences || []).forEach(f => {
        const fCard = document.createElement("div");
        fCard.className = "p-2.5 rounded-xl border border-amber-200/80 bg-amber-50/40 space-y-1 text-xs";
        fCard.innerHTML = `
          <div class="font-bold text-amber-950 truncate">${escapeHtml(f.name)}</div>
          <div class="text-[10px] text-amber-800 font-medium">${escapeHtml(f.neighborhood || 'Local Area')}</div>
          <p class="text-[10px] text-slate-600 leading-snug">${escapeHtml(f.type)}</p>
          <div class="text-[10px] font-bold text-amber-900 pt-0.5">Est. Cost: ~₹${f.cost_est}</div>
        `;
        foodGrid.appendChild(fCard);
      });
    }

    // 7. Shopping Recommendations Grid
    const shopGrid = document.getElementById("exploreShoppingGrid");
    if (shopGrid) {
      shopGrid.innerHTML = "";
      (data.shopping_recommendations || []).forEach(s => {
        const sCard = document.createElement("div");
        sCard.className = "p-2.5 rounded-xl border border-rose-200/80 bg-rose-50/40 space-y-1 text-xs";
        sCard.innerHTML = `
          <div class="font-bold text-rose-950 truncate">${escapeHtml(s.name)}</div>
          <div class="text-[10px] text-rose-800 font-semibold">${escapeHtml(s.type)}</div>
          <p class="text-[10px] text-slate-600 leading-snug">${escapeHtml(s.best_for)}</p>
        `;
        shopGrid.appendChild(sCard);
      });
    }

    // 8. Budget Summary
    if (data.budget_summary) {
      const bareMinEl = document.getElementById("exploreBareMinBudget");
      const recBudgetEl = document.getElementById("exploreRecBudget");
      if (bareMinEl) bareMinEl.textContent = `₹${Math.round(data.budget_summary.bare_minimum_budget).toLocaleString('en-IN')}`;
      if (recBudgetEl) recBudgetEl.textContent = `₹${Math.round(data.budget_summary.recommended_budget).toLocaleString('en-IN')}`;
    }

    // 9. Practical Information Grid
    const pracGrid = document.getElementById("explorePracticalGrid");
    if (pracGrid) {
      pracGrid.innerHTML = "";
      (data.practical_tips || []).forEach(tip => {
        const tCard = document.createElement("div");
        tCard.className = "p-2.5 rounded-xl border border-slate-200 bg-slate-50 space-y-0.5 text-xs";
        tCard.innerHTML = `
          <div class="font-bold text-slate-800 text-[11px]">${escapeHtml(tip.title)}</div>
          <p class="text-[10px] text-slate-600 leading-relaxed">${escapeHtml(tip.detail)}</p>
        `;
        pracGrid.appendChild(tCard);
      });
    }

    // Shortlist action button in modal
    const shortBtn = document.getElementById("exploreShortlistBtn");
    if (shortBtn) {
      const isShortlisted = !!item.is_shortlisted;
      shortBtn.innerHTML = `
        <i class="${isShortlisted ? 'fa-solid text-amber-500' : 'fa-regular'} fa-bookmark"></i>
        <span>${isShortlisted ? 'Shortlisted ✓' : 'Shortlist'}</span>
      `;
      shortBtn.onclick = () => {
        toggleShortlist(destId, shortBtn);
      };
    }

    if (loadingEl) loadingEl.classList.add("hidden");
    if (contentEl) contentEl.classList.remove("hidden");
  } catch (err) {
    console.error("Explore error:", err);
    if (loadingEl) {
      loadingEl.innerHTML = `<div class="p-6 text-rose-500 text-xs">Failed to load rich exploration: ${escapeHtml(err.message)}</div>`;
    }
  }
}

// Task 5: Seamless "Plan This Trip" CTA action
function planTripFromExplore() {
  if (!currentExploredDestination) {
    closeModal("exploreModal");
    toggleTripFormModal();
    return;
  }

  const d = currentExploredDestination;
  selectedDynamicLocation = null;
  clearTripCitySearch();
  closeModal("exploreModal");
  toggleTripFormModal();

  // Pre-fill destination select or search input
  const destSelect = document.getElementById("tripDestSelect");
  let found = false;
  if (destSelect) {
    for (let i = 0; i < destSelect.options.length; i++) {
      if (destSelect.options[i].value === d.destination_id) {
        destSelect.selectedIndex = i;
        found = true;
        break;
      }
    }
    if (!found) {
      // Dynamic destination insertion
      const opt = document.createElement("option");
      opt.value = d.destination_id;
      opt.text = `${d.name} (${d.state || 'India'})`;
      destSelect.add(opt, 0);
      destSelect.selectedIndex = 0;
    }
    handleFeaturedDestinationChange(destSelect.value);
  }

  // Pre-fill budget if recommended budget available
  if (d.budget_summary && d.budget_summary.recommended_budget) {
    const budgetInput = document.getElementById("tripBudgetInput");
    if (budgetInput) {
      budgetInput.value = Math.round(d.budget_summary.recommended_budget);
    }
  }

  // Trigger recalculation so slider and breakdown adapt immediately
  calculateTripMinimumBudget();
}

// Toggle Shortlist
async function toggleShortlist(destId, btnElement) {
  if (!state.currentUser) {
    alert("Please sign in first.");
    return;
  }

  try {
    const res = await fetch(`/api/shortlist/${state.currentUser.user_id}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ destination_id: destId })
    });
    if (!res.ok) {
      const errData = await res.json().catch(() => null);
      throw new Error(formatApiError(errData, "Could not update shortlist"));
    }
    const data = await res.json();
    const isShort = data.is_shortlisted;

    if (recCache[destId]) {
      recCache[destId].is_shortlisted = isShort;
    }

    // Update all icon bookmark buttons on cards
    document.querySelectorAll(`[data-shortlist-dest="${destId}"]`).forEach(btn => {
      btn.innerHTML = `<i class="${isShort ? 'fa-solid text-amber-500' : 'fa-regular'} fa-bookmark text-xs"></i>`;
    });

    // Update text shortlist buttons on cards
    document.querySelectorAll(`[data-shortlist-btn="${destId}"]`).forEach(btn => {
      btn.className = `px-3 py-2 text-xs font-semibold rounded-xl border transition flex items-center gap-1.5 ${isShort ? 'bg-amber-50 border-amber-200 text-amber-800' : 'border-slate-200 text-slate-600 hover:bg-slate-50'}`;
      btn.innerHTML = `<i class="${isShort ? 'fa-solid text-amber-500' : 'fa-regular'} fa-bookmark"></i> <span>${isShort ? 'Saved' : 'Shortlist'}</span>`;
    });

    // Update modal button if currently open
    const modalBtn = document.getElementById("exploreShortlistBtn");
    if (modalBtn) {
      modalBtn.innerHTML = `
        <i class="${isShort ? 'fa-solid text-amber-500' : 'fa-regular'} fa-bookmark"></i>
        <span>${isShort ? 'Shortlisted ✓' : 'Shortlist This Destination'}</span>
      `;
    }
  } catch (err) {
    alert("Error updating shortlist: " + err.message);
  }
}

// ==========================================
// UNIFIED PERSONAL PROFILE QUESTIONNAIRE
// ==========================================

function precEl(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined && text !== null) e.textContent = text;
  return e;
}

function precAnswered(v) {
  if (v === null || v === undefined) return false;
  if (Array.isArray(v)) return v.length > 0;
  if (typeof v === "string") return v.trim().length > 0;
  return true;
}

function precFull() {
  return { ...state.precision.context, ...state.precision.answers };
}

function precCondTrue(cond, full) {
  if (cond.any) return cond.any.some(c => precCondTrue(c, full));
  if (cond.all) return cond.all.every(c => precCondTrue(c, full));
  const bank = state.precision.bank ? state.precision.bank.questions : {};
  if (bank[cond.q] && !precVisible(cond.q, full)) return false;
  const v = full[cond.q];
  const arr = Array.isArray(v) ? v : (precAnswered(v) ? [v] : []);
  return arr.some(x => cond.includes_any.includes(x));
}

function precVisible(qid, full) {
  if (!state.precision.bank || !state.precision.bank.questions) return false;
  const q = state.precision.bank.questions[qid];
  if (!q) return false;
  return !q.show_if || precCondTrue(q.show_if, full);
}

function precVisibleIds(sectionId) {
  const full = precFull();
  if (!state.precision.bank || !state.precision.bank.questions) return [];
  return Object.values(state.precision.bank.questions)
    .filter(q => (!sectionId || q.section === sectionId) && precVisible(q.id, full))
    .map(q => q.id);
}

async function openPersonalProfileModal() {
  if (!state.currentUser) {
    alert("Please sign in first.");
    return;
  }
  try {
    if (!state.precision.bank) {
      const r = await fetch("/api/config/precision-questionnaire");
      if (!r.ok) throw new Error("Could not load the questionnaire");
      state.precision.bank = await r.json();
    }
    const res = await fetch(`/api/profile/precision/${state.currentUser.user_id}`);
    const data = await res.json();
    if (!res.ok) throw new Error(formatApiError(data, "Could not load your saved answers"));
    state.precision.answers = data.answers || {};
    state.precision.context = data.context_answers || {};
    state.precision.exists = !!data.exists;

    // Pre-seed default non-empty answers for scale & multi questions if uncalibrated
    if (!state.precision.answers.d05_monsoon_rain) state.precision.answers.d05_monsoon_rain = 3;
    if (!state.precision.answers.d06_high_altitude) state.precision.answers.d06_high_altitude = 3;
    if (!state.precision.answers.d07_heat_humidity) state.precision.answers.d07_heat_humidity = 3;
    if (!state.precision.answers.d08_winter_cold) state.precision.answers.d08_winter_cold = 3;
    if (!state.precision.answers.d11_food_allergens || state.precision.answers.d11_food_allergens.length === 0) {
      state.precision.answers.d11_food_allergens = ["no_allergies"];
    }
    if (!state.precision.answers.d21_medical_logistics || state.precision.answers.d21_medical_logistics.length === 0) {
      state.precision.answers.d21_medical_logistics = ["no_medical_logistics"];
    }
    
    // Auto-focus first section with unanswered applicable questions for smooth completion
    const firstUnansSec = state.precision.bank.sections.find(sec => {
      const ids = precVisibleIds(sec.id);
      return ids.some(id => !precAnswered(state.precision.answers[id]));
    });
    state.precision.tab = firstUnansSec ? firstUnansSec.id : state.precision.bank.sections[0].id;
    showPersonalPane("form");
    renderPersonalSection();
    renderPastTripsInModal();
    openModal("personalProfileModal");
  } catch (err) {
    alert("Error: " + err.message);
  }
}

async function closePersonalProfileModal() {
  closeModal("personalProfileModal");
  if (state.currentUser) await renderDashboard(state.currentProfile);
}

function showPersonalPane(which) {
  document.getElementById("personalFormPane").classList.toggle("hidden", which !== "form");
  document.getElementById("personalResultPane").classList.toggle("hidden", which !== "result");
  document.getElementById("personalTabs").classList.toggle("hidden", which !== "form");
}

function personalStep(delta) {
  const secs = state.precision.bank.sections;
  const idx = secs.findIndex(s => s.id === state.precision.tab);
  const next = Math.min(Math.max(idx + delta, 0), secs.length - 1);
  state.precision.tab = secs[next].id;
  renderPersonalSection();
  document.getElementById("personalBody").scrollTop = 0;
}

function updatePersonalProgress() {
  const sections = state.precision.bank.sections;
  const answers = state.precision.answers;
  let totalVis = 0, totalAns = 0;

  const tabs = document.getElementById("personalTabs");
  tabs.innerHTML = "";
  sections.forEach((sec, i) => {
    const vis = precVisibleIds(sec.id);
    const ans = vis.filter(id => precAnswered(answers[id])).length;
    totalVis += vis.length;
    totalAns += ans;
    const active = sec.id === state.precision.tab;
    const btn = precEl("button", active
      ? "px-3 py-1.5 rounded-lg bg-indigo-50 text-indigo-700 whitespace-nowrap font-bold border border-indigo-200"
      : "px-3 py-1.5 rounded-lg text-slate-600 hover:bg-slate-50 whitespace-nowrap border border-transparent",
      `${i + 1}. ${sec.title} (${ans}/${vis.length})`);
    btn.type = "button";
    btn.onclick = () => {
      state.precision.tab = sec.id;
      renderPersonalSection();
      document.getElementById("personalBody").scrollTop = 0;
    };
    tabs.appendChild(btn);
  });

  const pct = totalVis ? Math.round((100 * totalAns) / totalVis) : 0;
  document.getElementById("personalProgressText").textContent = `${totalAns} of ${totalVis} applicable questions answered`;
  document.getElementById("personalProgressPct").textContent = `${pct}%`;
  document.getElementById("personalProgressBar").style.width = `${pct}%`;

  const saveBtn = document.getElementById("personalSaveBtn");
  if (saveBtn) {
    if (totalAns < totalVis) {
      saveBtn.disabled = true;
      saveBtn.className = "px-5 py-2 bg-slate-600 text-slate-300 font-bold text-xs rounded-xl cursor-not-allowed opacity-75 flex items-center gap-2";
      saveBtn.innerHTML = `<i class="fa-solid fa-lock text-amber-300"></i> Complete Profile (${totalVis - totalAns} left)`;
      saveBtn.title = `Answer remaining ${totalVis - totalAns} applicable questions to save`;
    } else {
      saveBtn.disabled = false;
      saveBtn.className = "px-5 py-2 bg-indigo-600 hover:bg-indigo-700 text-white font-bold text-xs rounded-xl transition shadow flex items-center gap-2";
      saveBtn.innerHTML = `<i class="fa-solid fa-check"></i> Save Personal Travel Profile (100%)`;
      saveBtn.title = "";
    }
  }
}

function setPrecisionAnswer(qid, value, rerender = true) {
  const a = state.precision.answers;
  if (precAnswered(value)) a[qid] = value; else delete a[qid];

  const full = precFull();
  Object.keys(a).forEach(id => { if (!precVisible(id, full)) delete a[id]; });

  if (rerender) {
    renderPersonalSection();
  } else {
    updatePersonalProgress();
  }
}

function renderPersonalSection() {
  const body = document.getElementById("personalBody");
  const keepScroll = body.scrollTop;
  const bank = state.precision.bank;
  const sec = bank.sections.find(s => s.id === state.precision.tab);

  document.getElementById("personalSectionPurpose").textContent = sec.purpose;
  const container = document.getElementById("personalQuestions");
  container.innerHTML = "";

  const ids = precVisibleIds(sec.id);
  ids.forEach(id => container.appendChild(renderPrecisionQuestion(bank.questions[id])));
  if (!ids.length) container.appendChild(precEl("p", "text-xs text-slate-400 italic", "No relevant questions in this section based on your preferences."));

  // Show past trips section when in last section (Assistant & Decision Support)
  const isLast = sec.id === bank.sections[bank.sections.length - 1].id;
  const pastTripsSec = document.getElementById("personalPastTripsSection");
  if (pastTripsSec) pastTripsSec.classList.toggle("hidden", !isLast);

  const secs = bank.sections;
  const idx = secs.findIndex(s => s.id === sec.id);
  document.getElementById("personalPrevBtn").style.visibility = idx === 0 ? "hidden" : "visible";
  
  const nextBtn = document.getElementById("personalNextBtn");
  if (nextBtn) {
    nextBtn.style.visibility = idx === secs.length - 1 ? "hidden" : "visible";
    const unansInSec = ids.filter(id => !precAnswered(state.precision.answers[id]));
    if (unansInSec.length > 0) {
      nextBtn.disabled = true;
      nextBtn.className = "px-3 py-2 border border-slate-200 text-slate-400 font-semibold text-xs rounded-xl cursor-not-allowed bg-slate-100 opacity-60";
      nextBtn.title = `Please answer all questions in this section (${unansInSec.length} remaining) to continue`;
    } else {
      nextBtn.disabled = false;
      nextBtn.className = "px-3 py-2 border border-indigo-200 text-indigo-700 font-semibold text-xs rounded-xl hover:bg-indigo-50 bg-white transition";
      nextBtn.title = "";
    }
  }

  updatePersonalProgress();
  body.scrollTop = keepScroll;
}

// Clean question label rendering without technical "Q14." or "P1." prefixes!
function renderPrecisionQuestion(q) {
  const answers = state.precision.answers;
  const cur = answers[q.id];

  const wrap = precEl("div", "p-3.5 rounded-xl border border-slate-200 bg-white space-y-2");
  const head = precEl("div", "flex items-start justify-between gap-2");
  
  // Clean question title: ONLY English text, no raw ID prefix!
  const qText = q.question || q.text || q.label || "";
  head.appendChild(precEl("label", "block text-xs font-bold text-slate-800 leading-snug", qText));
  
  const right = precEl("div", "flex items-center gap-2 shrink-0");
  if (precAnswered(cur)) {
    const answeredBadge = precEl("span", "text-[10px] px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 font-bold border border-emerald-200", "Answered ✓");
    right.appendChild(answeredBadge);
  } else {
    const reqBadge = precEl("span", "text-[10px] px-2 py-0.5 rounded-full bg-amber-50 text-amber-700 font-bold border border-amber-200", "Required *");
    right.appendChild(reqBadge);
  }
  head.appendChild(right);
  wrap.appendChild(head);

  if (q.why) wrap.appendChild(precEl("p", "text-[11px] text-slate-500 leading-snug", q.why));

  if (q.type === "single") wrap.appendChild(precSingle(q, cur));
  else if (q.type === "multi") wrap.appendChild(precMulti(q, cur));
  else if (q.type === "scale") wrap.appendChild(precScale(q, cur));
  else if (q.type === "number") wrap.appendChild(precNumber(q, cur));
  else wrap.appendChild(precText(q, cur));
  return wrap;
}

function precOptionCard(opt, selected, onClick) {
  const card = precEl("div", `selectable-card p-2 rounded-xl bg-white border flex items-center justify-between text-xs cursor-pointer transition ${selected ? "selected" : ""}`);
  const left = precEl("div", "");
  left.appendChild(precEl("span", "font-medium text-slate-800 text-[11px] leading-tight block", opt.label));
  if (opt.desc) left.appendChild(precEl("span", "text-[10px] text-slate-500 block", opt.desc));
  card.appendChild(left);
  const check = precEl("i", "check-icon fa-solid fa-circle-check text-indigo-600 text-xs hidden");
  card.appendChild(check);
  card.onclick = onClick;
  return card;
}

function precSingle(q, cur) {
  const grid = precEl("div", "grid grid-cols-1 sm:grid-cols-2 gap-1.5");
  q.options.forEach(opt => grid.appendChild(precOptionCard(opt, cur === opt.id, () => setPrecisionAnswer(q.id, opt.id))));
  return grid;
}

function precMulti(q, cur) {
  const sel = Array.isArray(cur) ? cur : [];
  const grid = precEl("div", "grid grid-cols-2 gap-1.5");
  if (q.max) grid.appendChild(precEl("p", "col-span-2 text-[10px] text-slate-400", `Choose up to ${q.max} (${sel.length}/${q.max})`));
  const exclusiveId = q.exclusive || (q.id === "d11_food_allergens" ? "no_allergies" : (q.id === "d21_medical_logistics" ? "no_medical_logistics" : null));
  q.options.forEach(opt => {
    grid.appendChild(precOptionCard(opt, sel.includes(opt.id), () => {
      let next = sel.slice();
      if (next.includes(opt.id)) {
        next = next.filter(x => x !== opt.id);
      } else if (exclusiveId && opt.id === exclusiveId) {
        next = [opt.id];
      } else {
        if (exclusiveId) next = next.filter(x => x !== exclusiveId);
        if (q.max && next.length >= q.max) { alert(`You can choose up to ${q.max} options.`); return; }
        next.push(opt.id);
      }
      if (next.length === 0 && exclusiveId) {
        next = [exclusiveId];
      }
      setPrecisionAnswer(q.id, next);
    }));
  });
  return grid;
}

function precScale(q, cur) {
  const box = precEl("div", "space-y-1");
  const row = precEl("div", "grid grid-cols-5 gap-1.5");
  for (let n = 1; n <= 5; n++) {
    const isSelected = cur !== undefined && cur !== null && Number(cur) === n;
    const b = precEl("button", `selectable-card py-2 rounded-lg bg-white border text-xs font-bold text-slate-700 ${isSelected ? "selected" : ""}`, String(n));
    b.type = "button";
    b.onclick = () => setPrecisionAnswer(q.id, Number(n));
    row.appendChild(b);
  }
  box.appendChild(row);
  const labels = precEl("div", "flex justify-between text-[10px] text-slate-500");
  labels.appendChild(precEl("span", "", `1 = ${q.low}`));
  labels.appendChild(precEl("span", "text-right", `5 = ${q.high}`));
  box.appendChild(labels);
  return box;
}

function precNumber(q, cur) {
  const box = precEl("div", "space-y-1");
  const isSet = typeof cur === "number";
  const val = isSet ? cur : (q.default ?? q.min);
  const label = precEl("div", `text-xs font-semibold ${isSet ? "text-indigo-700" : "text-slate-400"}`,
    isSet ? `${val} ${q.unit}` : `Not set - move the slider (${q.unit})`);
  const input = document.createElement("input");
  input.type = "range";
  input.min = q.min; input.max = q.max; input.step = q.step || 1; input.value = val;
  input.className = "w-full accent-indigo-600";
  input.oninput = () => { label.textContent = `${input.value} ${q.unit}`; label.className = "text-xs font-semibold text-indigo-700"; };
  input.onchange = () => setPrecisionAnswer(q.id, parseFloat(input.value));
  box.appendChild(label);
  box.appendChild(input);
  const ends = precEl("div", "flex justify-between text-[10px] text-slate-400");
  ends.appendChild(precEl("span", "", String(q.min)));
  ends.appendChild(precEl("span", "", String(q.max)));
  box.appendChild(ends);
  return box;
}

function precText(q, cur) {
  const ta = document.createElement("textarea");
  ta.rows = 2;
  ta.maxLength = 500;
  ta.value = typeof cur === "string" ? cur : "";
  ta.placeholder = q.placeholder || "Optional notes or details";
  ta.className = "w-full px-3 py-2 text-xs border border-slate-300 rounded-lg";
  ta.oninput = () => setPrecisionAnswer(q.id, ta.value.trim() ? ta.value : null, false);
  return ta;
}

// Past Trips in modal
function addPastTripEntry() {
  const dest = document.getElementById("pastTripDest").value.trim();
  const rating = parseFloat(document.getElementById("pastTripRating").value);
  const fav = document.getElementById("pastTripFav").value.trim();
  const dislike = document.getElementById("pastTripDislike").value.trim();

  if (!dest) {
    alert("Please enter a destination name.");
    return;
  }

  state.precision.past_trips.push({
    destination: dest,
    rating: rating,
    favorite_activity: fav,
    skipped_or_disliked: dislike
  });

  document.getElementById("pastTripDest").value = "";
  document.getElementById("pastTripFav").value = "";
  document.getElementById("pastTripDislike").value = "";
  renderPastTripsInModal();
}

function renderPastTripsInModal() {
  const list = document.getElementById("pastTripsList");
  if (!list) return;
  list.innerHTML = "";
  state.precision.past_trips.forEach((t, i) => {
    const item = document.createElement("div");
    item.className = "p-2 rounded-lg bg-white border border-slate-200 text-xs flex justify-between items-center";
    item.innerHTML = `
      <div>
        <span class="font-bold text-slate-800">${t.destination}</span>
        <span class="text-amber-500 font-bold ml-1">${"★".repeat(Math.round(t.rating))}</span>
        <div class="text-[10px] text-slate-500">${t.favorite_activity || "No highlight"}</div>
      </div>
      <button type="button" onclick="state.precision.past_trips.splice(${i}, 1); renderPastTripsInModal();" class="text-slate-400 hover:text-rose-600 text-xs px-2">
        <i class="fa-solid fa-trash-can"></i>
      </button>
    `;
    list.appendChild(item);
  });
}

// Submit Unified Profile
async function submitPersonalProfile() {
  if (!state.currentUser) return;
  const btn = document.getElementById("personalSaveBtn");
  btn.disabled = true;

  // Guarantee default values for climate tolerance, allergies, and health logistics before sending
  const ans = { ...(state.precision.answers || {}) };
  if (!ans.d05_monsoon_rain) ans.d05_monsoon_rain = 3;
  if (!ans.d06_high_altitude) ans.d06_high_altitude = 3;
  if (!ans.d07_heat_humidity) ans.d07_heat_humidity = 3;
  if (!ans.d08_winter_cold) ans.d08_winter_cold = 3;
  if (!ans.d09_spice_tolerance) ans.d09_spice_tolerance = 3;
  if (!ans.d10_street_food) ans.d10_street_food = 3;
  if (!ans.d15_motion_sickness) ans.d15_motion_sickness = 3;
  if (!ans.d16_early_starts) ans.d16_early_starts = 3;
  if (!ans.d20_temple_stairs_terrain) ans.d20_temple_stairs_terrain = 3;
  if (!ans.d11_food_allergens || !ans.d11_food_allergens.length) ans.d11_food_allergens = ["no_allergies"];
  if (!ans.d21_medical_logistics || !ans.d21_medical_logistics.length) ans.d21_medical_logistics = ["no_medical_logistics"];
  state.precision.answers = ans;

  try {
    const res = await fetch(`/api/profile/precision/${state.currentUser.user_id}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answers: state.precision.answers })
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(formatApiError(data, "Save failed"));
    }

    state.precision.answers = data.answers;
    state.precision.exists = true;

    // Save past trips if any were added
    if (state.precision.past_trips.length > 0) {
      await fetch(`/api/profile/detailed/${state.currentUser.user_id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          past_trips: state.precision.past_trips,
          avoidances: state.precision.answers.q12 || []
        })
      });
    }

    renderPersonalResult(data);
    // Refresh completeness status and unlock trip planner
    if (state.currentUser) {
      const statusRes = await fetch('/api/profile/' + state.currentUser.user_id + '/status');
      if (statusRes.ok) {
        state.profileStatus = await statusRes.json();
      }
      loadUserTrips();
    }
  } catch (err) {
    alert("Error: " + err.message);
  } finally {
    btn.disabled = false;
  }
}

function precInsightRow(i) {
  const st = PREC_KIND_STYLE[i.kind] || PREC_KIND_STYLE.rule;
  const row = precEl("div", `flex gap-2 p-2.5 rounded-lg border text-[11px] leading-snug ${st.cls}`);
  row.appendChild(precEl("i", `fa-solid ${st.icon} mt-0.5`));
  const t = precEl("div", "");
  t.appendChild(precEl("span", "font-bold uppercase text-[9px] block opacity-70", st.label));
  t.appendChild(precEl("span", "", i.text));
  row.appendChild(t);
  return row;
}

function renderPersonalResult(data) {
  document.getElementById("precResAnswered").textContent = `${data.answered} of ${data.applicable}`;
  document.getElementById("precResConstraints").textContent = data.insights.filter(i => i.kind === "constraint").length;

  const list = document.getElementById("precResInsights");
  list.innerHTML = "";
  if (!data.insights.length) {
    list.appendChild(precEl("p", "text-xs text-slate-400 italic", "Your responses have been saved and applied to your recommendations."));
  }
  data.insights.forEach(i => list.appendChild(precInsightRow(i)));
  showPersonalPane("result");
}

// ==========================================
// ACADEMIC MODEL INSPECTOR (VIVA & EVALUATION)
// ==========================================

async function loadAcademicInspector() {
  if (!state.currentUser) return;
  try {
    const res = await fetch(`/api/rl/state/${state.currentUser.user_id}`);
    if (res.ok) {
      const data = await res.json();
      document.getElementById("acadVectorDimBadge").textContent = `d = ${data.dimension_count}`;
      document.getElementById("acadVectorLevel").textContent = `${data.level.title()} state representation`;
      document.getElementById("acadRawVectorDisplay").textContent = JSON.stringify(data.state_vector, null, 2);

      const tbody = document.getElementById("acadVectorTableBody");
      tbody.innerHTML = "";
      (data.feature_breakdown || []).forEach((f, idx) => {
        const tr = document.createElement("tr");
        tr.className = f.is_constraint_mask ? "bg-rose-50/50" : "";
        tr.innerHTML = `
          <td class="p-2 text-slate-400">${idx + 1}</td>
          <td class="p-2 font-semibold text-slate-800">${f.feature_name}</td>
          <td class="p-2 text-indigo-600 font-bold">${typeof f.value === 'number' ? f.value.toFixed(2) : f.value}</td>
          <td class="p-2 text-slate-500">${f.role_in_agent || (f.is_constraint_mask ? 'Hard Negative Constraint Mask' : 'Continuous Preference Feature')}</td>
        `;
        tbody.appendChild(tr);
      });
    }

    // Load LinUCB Policy inspection
    const polRes = await fetch(`/api/rl/policy/${state.currentUser.user_id}`);
    if (polRes.ok) {
      const polData = await polRes.json();
      const pullBadge = document.getElementById("acadLinucbPullBadge");
      if (pullBadge) pullBadge.textContent = `Interactions: ${polData.total_interactions}`;

      const armsTable = document.getElementById("acadLinucbArmsTable");
      if (armsTable) {
        armsTable.innerHTML = "";
        (polData.arms || []).forEach(a => {
          const tr = document.createElement("tr");
          const topWeights = Object.entries(a.top_feature_weights || {})
            .map(([k, v]) => `<span class="inline-block px-1.5 py-0.5 rounded ${v >= 0 ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-700'} text-[10px] mr-1 mb-1 font-mono">${k.replace('user_interest_', '').replace('activity_', '')}: ${v > 0 ? '+' : ''}${v}</span>`)
            .join("");
          tr.innerHTML = `
            <td class="p-2 font-bold text-slate-800">${a.arm_id.replace('_', ' ').title()}</td>
            <td class="p-2 text-slate-600">${a.pull_count}</td>
            <td class="p-2 font-bold ${a.average_reward >= 0 ? 'text-emerald-600' : 'text-rose-600'}">${a.average_reward > 0 ? '+' : ''}${a.average_reward.toFixed(2)}</td>
            <td class="p-2">${topWeights || '<span class="text-slate-400">Priors neutral</span>'}</td>
          `;
          armsTable.appendChild(tr);
        });
      }

      const logList = document.getElementById("acadFeedbackLogList");
      if (logList) {
        logList.innerHTML = "";
        if (!polData.recent_feedback || polData.recent_feedback.length === 0) {
          logList.innerHTML = `<p class="text-slate-400 italic">No interaction feedback recorded yet.</p>`;
        } else {
          polData.recent_feedback.forEach(fb => {
            const row = document.createElement("div");
            row.className = "flex items-center justify-between p-1.5 rounded bg-white border border-slate-200";
            const badgeColor = fb.action_type === 'accept' ? 'bg-emerald-100 text-emerald-800' : (fb.action_type === 'reject' ? 'bg-red-100 text-red-800' : 'bg-amber-100 text-amber-800');
            row.innerHTML = `
              <div class="flex items-center gap-1.5">
                <span class="px-1.5 py-0.5 rounded text-[9px] font-bold uppercase ${badgeColor}">${fb.action_type}</span>
                <span class="font-semibold text-slate-700">${fb.activity_id}</span>
                ${fb.rejection_reason ? `<span class="text-slate-400 text-[10px]">(${fb.rejection_reason})</span>` : ''}
              </div>
              <div class="flex items-center gap-2">
                ${fb.is_trip_specific ? '<span class="text-[9px] bg-slate-100 text-slate-600 px-1 rounded">trip-only</span>' : ''}
                <span class="font-mono font-bold ${fb.reward >= 0 ? 'text-emerald-600' : 'text-rose-600'}">${fb.reward > 0 ? '+' : ''}${fb.reward.toFixed(1)}</span>
              </div>
            `;
            logList.appendChild(row);
          });
        }
      }
    }
  } catch (err) {
    console.error("Error loading academic model inspection:", err);
  }
}

function switchAcademicTab(tab) {
  ["vector", "mdp", "weights", "linucb"].forEach(t => {
    const btn = document.getElementById(`acadTab-${t}`);
    const pane = document.getElementById(`acadPane-${t}`);
    if (btn && pane) {
      if (t === tab) {
        btn.className = "px-3 py-1.5 rounded-lg bg-indigo-50 text-indigo-700 font-bold";
        pane.classList.remove("hidden");
      } else {
        btn.className = "px-3 py-1.5 rounded-lg text-slate-600 hover:bg-slate-50";
        pane.classList.add("hidden");
      }
    }
  });
}

async function runLiveAcademicBenchmark() {
  const btn = document.getElementById("runBenchmarkBtn");
  const area = document.getElementById("benchmarkResultsArea");
  if (btn) btn.disabled = true;
  if (btn) btn.textContent = "Running (20-round demo, not evidence)...";

  try {
    const res = await fetch("/api/evaluation/benchmark?persona=nature_enthusiast&rounds=20");
    if (res.ok) {
      const data = await res.json();
      if (area) area.classList.remove("hidden");
      document.getElementById("benchLinucbAcc").textContent = `${(data.adaptive_linucb.acceptance_rate * 100).toFixed(1)}% (Cumulative: ${data.adaptive_linucb.cumulative_reward > 0 ? '+' : ''}${data.adaptive_linucb.cumulative_reward})`;
      document.getElementById("benchBaselineAcc").textContent = `${(data.baseline.acceptance_rate * 100).toFixed(1)}% (Cumulative: ${data.baseline.cumulative_reward > 0 ? '+' : ''}${data.baseline.cumulative_reward})`;
      document.getElementById("benchRewardDiff").textContent = `${data.relative_improvement_pct > 0 ? '+' : ''}${data.relative_improvement_pct}% relative acceptance gain`;
    }
  } catch (err) {
    console.error("Benchmark error:", err);
  } finally {
    if (btn) btn.disabled = false;
    if (btn) btn.textContent = "Run 20-round demo, not evidence";
  }
}

// ==========================================
// UNIFIED TRIP LOCATION SEARCH, GPS & NEARBY PLACE DISCOVERY
// ==========================================
let selectedDynamicLocation = null;
let activeTripCoords = null;
let currentDynamicRadius = 15000;
let _citySearchTimer = null;
let _lastCitySearchResults = [];

const FEATURED_DESTINATION_COORDS = {
  manali_spiti_india: { name: "Manali & Spiti Valley", city: "Manali", state: "Himachal Pradesh", lat: 32.2432, lon: 77.1892 },
  rishikesh_haridwar_india: { name: "Rishikesh & Haridwar", city: "Rishikesh", state: "Uttarakhand", lat: 30.0869, lon: 78.2676 },
  leh_ladakh_india: { name: "Leh Ladakh", city: "Leh", state: "Ladakh", lat: 34.1526, lon: 77.5771 },
  varanasi_india: { name: "Varanasi", city: "Varanasi", state: "Uttar Pradesh", lat: 25.3176, lon: 82.9739 },
  udaipur_mewar_india: { name: "Udaipur & Mewar", city: "Udaipur", state: "Rajasthan", lat: 24.5854, lon: 73.7125 },
  jaipur_jodhpur_india: { name: "Jaipur & Jodhpur", city: "Jaipur", state: "Rajasthan", lat: 26.9124, lon: 75.7873 },
  south_goa_india: { name: "South Goa", city: "South Goa", state: "Goa", lat: 15.2736, lon: 73.9580 },
  kerala_alleppey_india: { name: "Munnar & Alleppey (Kerala)", city: "Alleppey", state: "Kerala", lat: 9.4981, lon: 76.3388 },
  hampi_india: { name: "Hampi", city: "Hampi", state: "Karnataka", lat: 15.3350, lon: 76.4600 },
  ooty_coorg_india: { name: "Ooty & Coorg", city: "Ooty", state: "Tamil Nadu & Karnataka", lat: 11.4102, lon: 76.6950 },
  darjeeling_gangtok_india: { name: "Darjeeling & Gangtok", city: "Darjeeling", state: "West Bengal & Sikkim", lat: 27.0410, lon: 88.2663 },
  meghalaya_shillong_india: { name: "Meghalaya (Shillong & Cherrapunji)", city: "Shillong", state: "Meghalaya", lat: 25.5788, lon: 91.8933 }
};

function clearTripCitySearch() {
  const input = document.getElementById("tripCitySearchInput");
  const resultsEl = document.getElementById("citySearchResults");
  const clearBtn = document.getElementById("tripCityClearBtn");
  if (input) input.value = "";
  if (resultsEl) {
    resultsEl.classList.add("hidden");
    resultsEl.innerHTML = "";
  }
  if (clearBtn) clearBtn.classList.add("hidden");
}

function handleRadiusChange(val) {
  currentDynamicRadius = parseInt(val, 10) || 15000;
  const coords = selectedDynamicLocation || activeTripCoords;
  if (coords && coords.lat !== undefined && coords.lon !== undefined) {
    fetchTripNearbyPlaces(coords.lat, coords.lon, currentDynamicRadius);
  }
}

function updateDestinationSourceBanner(loc, provenanceText, isLive) {
  const sourceInfo = document.getElementById("destinationSourceInfo");
  const sourceText = document.getElementById("destinationSourceText");
  const provBadge = document.getElementById("destinationProvenanceBadge");
  if (!sourceInfo || !sourceText) return;

  const latVal = Number(loc.lat ?? loc.latitude);
  const lonVal = Number(loc.lon ?? loc.longitude);
  const latStr = Number.isFinite(latVal) ? latVal.toFixed(3) : "--";
  const lonStr = Number.isFinite(lonVal) ? lonVal.toFixed(3) : "--";
  const displayName = loc.formatted || `${loc.name || loc.city}, ${loc.state || "India"}`;

  sourceInfo.classList.remove("hidden");
  sourceText.textContent = `${displayName} (${latStr}° N, ${lonStr}° E)`;

  if (provBadge) {
    if (isLive) {
      provBadge.className = "text-[9px] px-1.5 py-0.5 rounded-full bg-emerald-100 text-emerald-800 font-semibold";
      provBadge.textContent = provenanceText || "Live Geoapify";
    } else {
      provBadge.className = "text-[9px] px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-800 font-semibold";
      provBadge.textContent = provenanceText || "Curated Catalogue";
    }
  }
}

async function detectUserLocation() {
  const btn = document.getElementById("gpsDetectBtn");
  if (!navigator.geolocation) {
    alert("Geolocation is not supported by your browser. Please search any Indian city using the search bar.");
    return;
  }

  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> <span>Locating...</span>';
  }

  navigator.geolocation.getCurrentPosition(
    async (pos) => {
      try {
        const lat = pos.coords.latitude;
        const lon = pos.coords.longitude;

        const res = await fetch(`/api/places/reverse-geocode?lat=${lat}&lon=${lon}`);
        const data = await res.json();

        if (!res.ok) {
          throw new Error(data.detail || "Unable to resolve your GPS position.");
        }

        const loc = data.location || {
          name: data.city || "Current Location",
          city: data.city || "Current Location",
          state: data.state || "India",
          country: data.country || "India",
          formatted: data.formatted,
          lat: data.lat ?? lat,
          lon: data.lon ?? lon,
          provenance: data.provenance || {}
        };
        const isLive = Boolean(loc.provenance && loc.provenance.is_live);
        await selectGeocodedCity(loc, isLive ? "geoapify" : "curated");
      } catch (err) {
        alert(err.message || "Failed to resolve your GPS location.");
        const input = document.getElementById("tripCitySearchInput");
        if (input) input.focus();
      } finally {
        if (btn) {
          btn.disabled = false;
          btn.innerHTML = '<i class="fa-solid fa-location-crosshairs"></i> <span>Use My Location</span>';
        }
      }
    },
    (err) => {
      let msg = "Could not retrieve your location.";
      if (err.code === err.PERMISSION_DENIED) {
        msg = "Location permission denied. Please search for any Indian city or town using the search box.";
      } else if (err.code === err.POSITION_UNAVAILABLE) {
        msg = "Location signal unavailable. Please use the search bar to find your destination.";
      } else if (err.code === err.TIMEOUT) {
        msg = "Location request timed out. Please try again or search manually.";
      }
      alert(msg);
      const input = document.getElementById("tripCitySearchInput");
      if (input) input.focus();

      if (btn) {
        btn.disabled = false;
        btn.innerHTML = '<i class="fa-solid fa-location-crosshairs"></i> <span>Use My Location</span>';
      }
    },
    { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 }
  );
}

async function fetchTripNearbyPlaces(lat, lon, radius) {
  const area = document.getElementById("tripNearbyPlacesArea");
  const grid = document.getElementById("tripNearbyPlacesGrid");
  const countText = document.getElementById("tripDiscoveredCountText");
  if (!area || !grid) return;

  const numLat = Number(lat);
  const numLon = Number(lon);
  if (!Number.isFinite(numLat) || !Number.isFinite(numLon)) {
    area.classList.add("hidden");
    return;
  }

  area.classList.remove("hidden");
  grid.innerHTML = '<div class="col-span-full py-4 text-center text-slate-500 text-xs"><i class="fa-solid fa-spinner fa-spin mr-1.5 text-indigo-600"></i>Discovering nearby places &amp; scoring with LinUCB...</div>';

  try {
    const userId = state.currentUser ? state.currentUser.user_id : "";
    const res = await fetch(`/api/places/discover?lat=${numLat}&lon=${numLon}&radius_meters=${radius}&user_id=${encodeURIComponent(userId)}&limit=12`);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Failed to discover nearby places");
    }

    const data = await res.json();
    const places = data.places || [];

    if (countText) {
      countText.textContent = `${places.length} places (${(radius / 1000).toFixed(0)} km · feeds LinUCB planner)`;
    }

    if (places.length === 0) {
      grid.innerHTML = '<div class="col-span-full py-4 text-center text-slate-500 text-xs">No nearby attractions found in this radius. Try widening the discovery radius.</div>';
      return;
    }

    const armIcons = {
      culture_history: "fa-landmark",
      nature_outdoors: "fa-tree",
      food_dining: "fa-utensils",
      adventure: "fa-person-hiking",
      relaxation: "fa-spa",
      shopping_local: "fa-bag-shopping",
      scenic: "fa-mountain-sun"
    };

    grid.innerHTML = places.map(p => {
      const arm = p.arm || p.category || "culture_history";
      const icon = armIcons[arm] || "fa-map-pin";
      const isLive = p.provenance && p.provenance.is_live;
      const provBadge = isLive
        ? '<span class="text-[9px] px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-800 font-semibold">Live</span>'
        : '<span class="text-[9px] px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 font-semibold">Curated</span>';
      const distBadge = p.distance_km !== null && p.distance_km !== undefined
        ? `<span><i class="fa-solid fa-route text-indigo-500 mr-1"></i>${p.distance_km} km</span>`
        : "";
      const scoreBadge = p.score !== undefined
        ? `<span class="font-mono px-1.5 py-0.5 rounded bg-indigo-50 text-indigo-700 border border-indigo-100">LinUCB ${Number(p.score).toFixed(2)}</span>`
        : "";

      return `
        <div class="bg-white border border-slate-200 rounded-lg p-2.5 flex flex-col justify-between gap-1.5 text-[11px] shadow-2xs">
          <div class="flex items-start justify-between gap-1.5">
            <span class="inline-flex items-center gap-1 text-[9px] font-bold uppercase text-indigo-700 bg-indigo-50 px-1.5 py-0.5 rounded">
              <i class="fa-solid ${icon}"></i> ${escapeHtml(arm.replace(/_/g, " "))}
            </span>
            ${provBadge}
          </div>
          <div>
            <div class="font-bold text-slate-800 leading-snug truncate" title="${escapeHtml(p.name)}">${escapeHtml(p.name)}</div>
            <div class="text-[10px] text-slate-500 truncate">${escapeHtml(p.neighbourhood || p.address || "Local attraction")}</div>
          </div>
          <div class="flex items-center justify-between text-[10px] text-slate-500 pt-1 border-t border-slate-100">
            ${distBadge}
            ${scoreBadge}
          </div>
        </div>
      `;
    }).join("");
  } catch (err) {
    grid.innerHTML = `<div class="col-span-full py-4 text-center text-rose-500 text-xs">${escapeHtml(err.message || "Failed to load nearby places")}</div>`;
  }
}

async function handleFeaturedDestinationChange(destId) {
  if (!destId) return;
  if (destId.startsWith("geo_")) {
    if (selectedDynamicLocation) {
      await fetchTripNearbyPlaces(selectedDynamicLocation.lat, selectedDynamicLocation.lon, currentDynamicRadius);
    }
    return;
  }

  selectedDynamicLocation = null;
  clearTripCitySearch();
  if (typeof clearOptionAHotel === "function") clearOptionAHotel();

  const meta = FEATURED_DESTINATION_COORDS[destId];
  if (meta) {
    activeTripCoords = { ...meta };
    updateDestinationSourceBanner(meta, "Curated Catalogue", false);
    await fetchTripNearbyPlaces(meta.lat, meta.lon, currentDynamicRadius);
  }
  calculateTripMinimumBudget();
}


// ==========================================
// ADAPTIVE PRE-TRIP ITINERARY PLANNER
// ==========================================

let activeUserTrips = [];
let currentPlannedTripId = null;
let currentItinerary = null;
let pendingFeedbackContext = null;


function isIndianDestinationId(destId) {
  if (!destId) return false;
  const id = destId.toLowerCase();
  if (id.endsWith("_india") || id.includes("india")) return true;
  const indianIds = [
    "manali_spiti", "rishikesh_haridwar", "leh_ladakh", "varanasi",
    "udaipur_mewar", "jaipur_jodhpur", "south_goa", "kerala_alleppey",
    "hampi", "ooty_coorg", "darjeeling_gangtok", "meghalaya_shillong"
  ];
  return indianIds.some(i => id.includes(i));
}

function isIndianTrip(trip) {
  if (!trip) return false;
  if (trip.destination_id && trip.destination_id.startsWith("geo_")) return true;
  return isIndianDestinationId(trip.destination_id);
}

async function handleCitySearchInput(val) {
  clearTimeout(_citySearchTimer);
  const resultsEl = document.getElementById("citySearchResults");
  const clearBtn = document.getElementById("tripCityClearBtn");
  if (!resultsEl) return;

  const query = (val || "").trim();
  if (clearBtn) {
    clearBtn.classList.toggle("hidden", query.length === 0);
  }

  if (query.length < 2) {
    resultsEl.classList.add("hidden");
    resultsEl.innerHTML = "";
    return;
  }

  _citySearchTimer = setTimeout(async () => {
    try {
      resultsEl.classList.remove("hidden");
      resultsEl.innerHTML = '<div class="p-2.5 text-slate-500 text-xs"><i class="fa-solid fa-spinner fa-spin mr-1.5"></i>Searching Indian cities &amp; destinations...</div>';

      const res = await fetch(`/api/places/search-locations?q=${encodeURIComponent(query)}&limit=6`);
      if (!res.ok) throw new Error("Location search failed");
      const data = await res.json();
      const results = data.results || [];
      _lastCitySearchResults = results;

      if (results.length === 0) {
        resultsEl.innerHTML = '<div class="p-2.5 text-slate-500 text-xs">No matching Indian locations found. Try another spelling.</div>';
        return;
      }

      resultsEl.innerHTML = results.map((loc, idx) => {
        const isLive = Boolean(loc.provenance && loc.provenance.is_live);
        const provBadge = isLive
          ? '<span class="text-[9px] px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-800 font-semibold">Live Geoapify</span>'
          : '<span class="text-[9px] px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 font-semibold">Curated</span>';
        const latVal = Number(loc.lat ?? loc.latitude);
        const lonVal = Number(loc.lon ?? loc.longitude);
        const coordsText = Number.isFinite(latVal) && Number.isFinite(lonVal)
          ? `${latVal.toFixed(2)}°, ${lonVal.toFixed(2)}°`
          : "";
        const subText = loc.formatted || `${loc.city || loc.name}, ${loc.state || "India"}`;

        return `
          <div onclick="selectSearchedLocationIndex(${idx})"
               class="p-2.5 hover:bg-emerald-50 cursor-pointer flex items-center justify-between gap-2 text-xs transition">
            <div class="flex items-center gap-2 min-w-0">
              <i class="fa-solid fa-location-dot text-emerald-600 shrink-0"></i>
              <div class="min-w-0">
                <span class="font-bold text-slate-800 block truncate">${escapeHtml(loc.name)}</span>
                <span class="text-slate-500 text-[11px] block truncate">${escapeHtml(subText)}</span>
              </div>
            </div>
            <div class="flex items-center gap-1.5 shrink-0">
              ${coordsText ? `<span class="text-[10px] text-slate-400 font-mono">${coordsText}</span>` : ""}
              ${provBadge}
            </div>
          </div>
        `;
      }).join("");
    } catch (e) {
      console.warn("Location search error:", e);
      resultsEl.innerHTML = `<div class="p-2.5 text-rose-500 text-xs">${escapeHtml(e.message || "Failed to search locations.")}</div>`;
    }
  }, 300);
}

async function selectSearchedLocationIndex(idx) {
  const loc = _lastCitySearchResults[idx];
  if (!loc) return;
  const isLive = Boolean(loc.provenance && loc.provenance.is_live);
  await selectGeocodedCity(loc, isLive ? "geoapify" : (loc.provenance?.source || "curated"));
}

async function selectGeocodedCity(item, src) {
  const latVal = Number(item.lat !== undefined ? item.lat : item.latitude);
  const lonVal = Number(item.lon !== undefined ? item.lon : item.longitude);
  const stateName = item.state || item.admin1 || "India";
  const countryName = item.country || "India";
  const cityName = item.city || item.name;
  const displayName = item.name || cityName;
  const isLive = Boolean((item.provenance && item.provenance.is_live) || src === "geoapify");

  selectedDynamicLocation = {
    city: cityName,
    state: stateName,
    name: displayName,
    lat: latVal,
    lon: lonVal,
    formatted: item.formatted || `${displayName}, ${stateName}`,
    provenance: item.provenance || { source: src || "curated_catalogue", is_live: isLive }
  };
  activeTripCoords = { ...selectedDynamicLocation };

  const destSelect = document.getElementById("tripDestSelect");
  const searchInput = document.getElementById("tripCitySearchInput");
  const clearBtn = document.getElementById("tripCityClearBtn");
  const resultsEl = document.getElementById("citySearchResults");

  if (resultsEl) resultsEl.classList.add("hidden");
  if (searchInput) searchInput.value = item.formatted || `${displayName}, ${stateName}`;
  if (clearBtn) clearBtn.classList.toggle("hidden", !(searchInput && searchInput.value));

  const destId = `geo_${displayName.toLowerCase().replace(/[^a-z0-9]/g, "_")}_${countryName.toLowerCase().replace(/[^a-z0-9]/g, "_")}`;
  const label = `${displayName}${stateName && stateName !== "India" ? ", " + stateName : ""} (${countryName})`;

  if (destSelect) {
    let opt = Array.from(destSelect.options).find(o => o.value === destId);
    if (!opt) {
      opt = document.createElement("option");
      opt.value = destId;
      opt.textContent = label;
      destSelect.insertBefore(opt, destSelect.firstChild);
    }
    destSelect.value = destId;
  }

  if (typeof clearOptionAHotel === "function") clearOptionAHotel();
  updateDestinationSourceBanner(selectedDynamicLocation, isLive ? "Live Geoapify" : "Curated Catalogue", isLive);
  await fetchTripNearbyPlaces(latVal, lonVal, currentDynamicRadius);
  calculateTripMinimumBudget();
}

function showInternationalTripNotice(trip) {
  const emptyState = document.getElementById("itineraryEmptyState");
  const displayContainer = document.getElementById("itineraryDisplayContainer");
  const daysContainer = document.getElementById("itineraryDaysContainer");

  emptyState.classList.add("hidden");
  displayContainer.classList.remove("hidden");

  document.getElementById("itinDestinationTitle").textContent = `${trip.destination_name} (Unsupported Destination)`;
  document.getElementById("itinDatesBadge").textContent = `${trip.duration_days} Days · ${trip.start_date}`;
  document.getElementById("itinSummaryNotes").textContent = "International destinations are not currently supported.";
  document.getElementById("itinTotalCostDisplay").textContent = "₹0";

  daysContainer.innerHTML = `
    <div class="bg-amber-50 border border-amber-200 rounded-2xl p-6 sm:p-8 text-center space-y-4 shadow-sm my-4">
      <div class="w-14 h-14 rounded-full bg-amber-100 text-amber-700 flex items-center justify-center mx-auto text-2xl shadow-inner">
        <i class="fa-solid fa-triangle-exclamation"></i>
      </div>
      <div>
        <h4 class="text-base font-bold text-slate-800">International Destination Not Supported</h4>
        <p class="text-xs text-slate-600 max-w-md mx-auto leading-relaxed mt-1">
          <strong>${trip.destination_name}</strong> is an international destination. This application exclusively supports travel planning within India. Additional itinerary activities cannot be generated for international destinations.
        </p>
      </div>
      <div class="pt-2 flex justify-center">
        <button onclick="toggleTripFormModal()" class="px-5 py-2.5 bg-emerald-600 hover:bg-emerald-700 text-white font-bold text-xs rounded-xl shadow transition flex items-center gap-2">
          <i class="fa-solid fa-plus"></i>
          <span>Plan an Indian Destination Trip Now &rarr;</span>
        </button>
      </div>
    </div>
  `;
}

async function loadUserTrips(preferredTripId = null) {
  if (!state.currentUser) return;
  const select = document.getElementById("userTripsSelect");
  if (!select) return;

  try {
    const res = await fetch(`/api/trips/${state.currentUser.user_id}`);
    if (res.ok) {
      activeUserTrips = await res.json();
      state.userTrips = activeUserTrips;
      const tripLabelCounts = new Map();
      activeUserTrips.forEach(trip => {
        const label = tripSelectorLabel(trip);
        tripLabelCounts.set(label, (tripLabelCounts.get(label) || 0) + 1);
      });
      select.innerHTML = `<option value="">-- Select Planned Trip (${activeUserTrips.length}) --</option>`;
      activeUserTrips.forEach(t => {
        const opt = document.createElement("option");
        opt.value = t.id;
        if (!isIndianTrip(t)) {
          opt.textContent = `${t.destination_name} (Unsupported - International) · ${t.duration_days}d`;
          opt.style.color = "#b45309";
        } else {
          const label = tripSelectorLabel(t);
          opt.textContent = tripLabelCounts.get(label) > 1 ? `${label} · #${t.id.slice(0, 6)}` : label;
        }
        select.appendChild(opt);
      });

      const isDeepComplete = state.profileStatus ? state.profileStatus.complete : false;
      const lockedState = document.getElementById("itineraryLockedState");
      const emptyState = document.getElementById("itineraryEmptyState");
      const displayContainer = document.getElementById("itineraryDisplayContainer");

      if (!isDeepComplete) {
        if (displayContainer) displayContainer.classList.add("hidden");
        if (emptyState) emptyState.classList.add("hidden");
        if (lockedState) lockedState.classList.remove("hidden");
        return;
      }
      if (lockedState) lockedState.classList.add("hidden");

      if (activeUserTrips.length > 0) {
        const preferred = preferredTripId ? activeUserTrips.find(t => t.id === preferredTripId) : null;
        const firstIndian = activeUserTrips.find(isIndianTrip);
        currentPlannedTripId = preferred ? preferred.id : (firstIndian ? firstIndian.id : activeUserTrips[0].id);
        select.value = currentPlannedTripId;
        await loadTripItinerary(currentPlannedTripId);
      } else {
        currentPlannedTripId = null;
        if (emptyState) emptyState.classList.remove("hidden");
        if (displayContainer) displayContainer.classList.add("hidden");
      }
    }
  } catch (err) {
    console.error("Error loading user trips:", err);
  }
}

function onTripSelectChanged(tripId) {
  const isDeepComplete = state.profileStatus ? state.profileStatus.complete : false;
  const lockedState = document.getElementById("itineraryLockedState");
  const emptyState = document.getElementById("itineraryEmptyState");
  const displayContainer = document.getElementById("itineraryDisplayContainer");

  if (!isDeepComplete) {
    if (displayContainer) displayContainer.classList.add("hidden");
    if (emptyState) emptyState.classList.add("hidden");
    if (lockedState) lockedState.classList.remove("hidden");
    return;
  }
  if (lockedState) lockedState.classList.add("hidden");

  if (!tripId) {
    currentPlannedTripId = null;
    if (emptyState) emptyState.classList.remove("hidden");
    if (displayContainer) displayContainer.classList.add("hidden");
    return;
  }
  currentPlannedTripId = tripId;
  resetItineraryWeatherBanner();
  loadTripItinerary(tripId);
}

function setTripDeparture(city) {
  const input = document.getElementById("tripDepartureInput");
  if (input) input.value = city;
}

function updateTripDurationPreview() {
  const s = document.getElementById("tripStartDateInput")?.value;
  const e = document.getElementById("tripEndDateInput")?.value;
  const badge = document.getElementById("tripDurationBadge");
  if (!badge) return;
  if (s && e) {
    const d1 = new Date(s);
    const d2 = new Date(e);
    const diffTime = d2 - d1;
    const days = Math.round(diffTime / (1000 * 60 * 60 * 24)) + 1;
    if (days > 0) {
      badge.textContent = `${days} Day${days > 1 ? "s" : ""}`;
      return;
    }
  }
  badge.textContent = "—";
}

function onCompanionTypeChanged(val) {
  const travellersInput = document.getElementById("tripTravellersInput");
  const hasKidsCheck = document.getElementById("tripHasChildrenCheck");
  const hasElderlyCheck = document.getElementById("tripHasElderlyCheck");
  if (val === "solo") {
    if (travellersInput) travellersInput.value = "1";
    if (hasKidsCheck) hasKidsCheck.checked = false;
    if (hasElderlyCheck) hasElderlyCheck.checked = false;
  } else if (val === "partner") {
    if (travellersInput) travellersInput.value = "2";
  } else if (val === "friends") {
    if (travellersInput && parseInt(travellersInput.value) < 2) {
      travellersInput.value = "3";
    }
  } else if (val === "family") {
    if (travellersInput && parseInt(travellersInput.value) < 3) {
      travellersInput.value = "3";
    }
  }
  const total = Number(travellersInput?.value || 1);
  document.getElementById('tripAdultsInput').value = total;
  document.getElementById('tripChildrenInput').value = val === 'family' ? 1 : 0;
  document.getElementById('tripSeniorsInput').value = 0;
  if (val === 'family') document.getElementById('tripAdultsInput').value = Math.max(1,total-1);
  if (val === 'friends') document.getElementById('tripAdultsInput').value = Math.max(3,total);
  syncTripPartyFromCounts();
}

function escapeHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function toggleBudgetBreakdownTable() {
  const container = document.getElementById("budgetBreakdownTableContainer");
  const icon = document.getElementById("budgetToggleIcon");
  if (!container) return;
  const isHidden = container.classList.contains("hidden");
  container.classList.toggle("hidden", !isHidden);
  if (icon) {
    icon.className = isHidden ? "fa-solid fa-chevron-up text-indigo-500" : "fa-solid fa-chevron-down text-indigo-500";
  }
}

let budgetEstimateRequestSeq = 0;
async function calculateTripMinimumBudget() {
  const requestSeq = ++budgetEstimateRequestSeq;
  const destSelect = document.getElementById("tripDestSelect");
  if (!destSelect) return;
  const destId = destSelect.value;
  const selectedOption = destSelect.options[destSelect.selectedIndex];
  const destination = (selectedOption ? selectedOption.text : destId) || "Jaipur, Rajasthan";

  const departure = document.getElementById("tripDepartureInput")?.value.trim() || "Delhi";
  const startDate = document.getElementById("tripStartDateInput")?.value;
  const endDate = document.getElementById("tripEndDateInput")?.value;
  const travellers = parseInt(document.getElementById("tripTravellersInput")?.value) || 1;
  const accommodation = document.getElementById("tripAccomSelect")?.value || "budget_hotel";
  const transport = document.getElementById("tripTransitSelect")?.value || "public_transit";
  const pace = document.getElementById("tripPaceSelect")?.value || "balanced";
  const includeShopping = document.getElementById("tripIncludeShoppingCheck")?.checked || false;

  let durationDays = 4;
  if (startDate && endDate) {
    const s = new Date(startDate);
    const e = new Date(endDate);
    const diff = Math.round((e - s) / (1000 * 60 * 60 * 24)) + 1;
    if (diff > 0) durationDays = diff;
  }

  const payload = {
    destination_id: destId,
    destination_name: destination,
    departure_location: departure,
    duration_days: durationDays,
    travellers_count: travellers,
    accommodation_tier: accommodation,
    transit_pref: transport,
    travel_pace: pace,
    include_shopping: includeShopping,
    party: readTripParty(),
    food_style: document.getElementById('tripDietarySelect').value,
    start_date: startDate || null, end_date: endDate || null
  };

  try {
    const res = await fetch("/api/budget/estimate-minimum", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (!res.ok) return;
    const data = await res.json();
    if (requestSeq !== budgetEstimateRequestSeq) return;
    state.activeBudgetEstimate = data;

    // Display minimum & recommended cards
    const minDisplay = document.getElementById("bareMinimumBudgetDisplay");
    const recDisplay = document.getElementById("recommendedBudgetDisplay");
    const minSubtext = document.getElementById("bareMinSubtext");
    const recSubtext = document.getElementById("recommendedSubtext");

    if (minDisplay) minDisplay.textContent = formatINR(data.bare_minimum_budget);
    if (recDisplay) recDisplay.textContent = formatINR(data.recommended_budget);
    const minPer = data.bare_minimum_per_person || Math.round(data.bare_minimum_budget / (data.travellers_count || 1));
    const recPer = data.recommended_per_person || Math.round(data.recommended_budget / (data.travellers_count || 1));
    if (minSubtext) minSubtext.textContent = `₹${minPer.toLocaleString("en-IN")}/person (${data.duration_days} days)`;
    if (recSubtext) recSubtext.textContent = `₹${recPer.toLocaleString("en-IN")}/person (${data.duration_days} days)`;

    // Populate category breakdown table
    const tbody = document.getElementById("budgetBreakdownTbody");
    if (tbody && Array.isArray(data.categories)) {
      tbody.innerHTML = "";
      data.categories.forEach(item => {
        const catName = item.name || item.category_name || item.category || "Expense";
        const minCost = item.minimum_cost ?? item.minimum_amount ?? 0;
        const recCost = item.recommended_cost ?? item.recommended_amount ?? 0;
        const basis = item.assumptions || item.basis || item.description || "";
        const prov = item.data_source || item.provenance || "estimated";

        const tr = document.createElement("tr");
        tr.className = "hover:bg-slate-50 transition border-b border-slate-100";
        tr.innerHTML = `
          <td class="p-2 font-semibold text-slate-800">${escapeHtml(catName)}</td>
          <td class="p-2 text-right font-bold text-slate-700">${formatINR(minCost)}</td>
          <td class="p-2 text-right font-bold text-emerald-700">${formatINR(recCost)}</td>
          <td class="p-2 text-slate-500 text-[10px]">${escapeHtml(basis)}</td>
          <td class="p-2 text-center">
            ${prov === "verified"
              ? '<span class="px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 text-[9px] font-bold">Verified</span>'
              : (prov === "estimated"
                ? '<span class="px-2 py-0.5 rounded-full bg-amber-100 text-amber-800 text-[9px] font-bold">Estimated</span>'
                : '<span class="px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 text-[9px]">Unavailable</span>')}
          </td>
        `;
        tbody.appendChild(tr);
      });
    }

    // Configure slider
    const slider = document.getElementById("tripBudgetSlider");
    const budgetInput = document.getElementById("tripBudgetInput");
    const minBound = document.getElementById("sliderMinBound");
    const maxBound = document.getElementById("sliderMaxBound");

    if (slider && data.slider_config) {
      slider.min = data.slider_config.min ?? data.slider_config.min_slider;
      slider.max = data.slider_config.max ?? data.slider_config.max_slider;
      slider.step = data.slider_config.step || 500;

      const minVal = data.slider_config.min ?? data.slider_config.min_slider;
      const maxVal = data.slider_config.max ?? data.slider_config.max_slider;
      if (minBound) minBound.textContent = `Min: ${formatINR(minVal)}`;
      if (maxBound) maxBound.textContent = `Max: ${formatINR(maxVal)}`;

      const currentVal = budgetInput ? parseFloat(budgetInput.value) : 0;
      if (!currentVal || currentVal < data.bare_minimum_budget) {
        if (budgetInput) budgetInput.value = data.bare_minimum_budget;
        slider.value = data.bare_minimum_budget;
      } else {
        slider.value = currentVal;
      }
    }

    updateBudgetAllowanceLabels(budgetInput ? parseFloat(budgetInput.value) : data.bare_minimum_budget);
  } catch (err) {
    console.warn("Failed to calculate minimum budget estimate:", err);
  }
}

function onBudgetSliderChange(val) {
  const num = Number(val);
  const input = document.getElementById("tripBudgetInput");
  if (input) input.value = num;
  updateBudgetAllowanceLabels(num);
}

function onBudgetNumberInputChange(val) {
  const num = Number(val);
  const slider = document.getElementById("tripBudgetSlider");
  if (slider && !isNaN(num)) {
    if (num >= Number(slider.min) && num <= Number(slider.max)) {
      slider.value = num;
    }
  }
  updateBudgetAllowanceLabels(num);
}

function updateBudgetAllowanceLabels(numVal) {
  const est = state.activeBudgetEstimate;
  const allowanceLabel = document.getElementById("sliderAllowanceLabel");
  const warningBox = document.getElementById("tripBudgetWarningBox");
  const warningText = document.getElementById("tripBudgetWarningText");
  const tierBadge = document.getElementById("budgetTierBadge");

  if (!est) return;

  const min = est.bare_minimum_budget;
  const rec = est.recommended_budget;
  const diff = numVal - min;

  if (diff < 0) {
    if (allowanceLabel) {
      allowanceLabel.textContent = `Shortfall: ${formatINR(Math.abs(diff))}`;
      allowanceLabel.className = "text-xs font-bold text-rose-700 bg-rose-100 px-2 py-0.5 rounded-full";
    }
    if (warningBox) warningBox.classList.remove("hidden");
    if (warningText) {
      warningText.textContent = `Entered budget of ${formatINR(numVal)} is below the minimum viable estimated cost of ${formatINR(min)} (Shortfall: ${formatINR(Math.abs(diff))}). Transport, accommodation, or meal requirements cannot be met without cutting days or travellers.`;
    }
    if (tierBadge) {
      tierBadge.textContent = est.budget_band_labels?.insufficient || 'Below minimum';
      tierBadge.className = "px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-100 text-rose-800 border border-rose-300";
    }
  } else {
    if (warningBox) warningBox.classList.add("hidden");
    if (allowanceLabel) {
      allowanceLabel.textContent = diff === 0 ? "Bare Minimum Allowance" : `+${formatINR(diff)} above minimum`;
      allowanceLabel.className = "text-xs font-bold text-emerald-700 bg-emerald-100 px-2 py-0.5 rounded-full";
    }
    if (tierBadge) {
      if (numVal < rec) {
        tierBadge.textContent = est.budget_band_labels?.budget_conscious || 'Budget-Conscious';
        tierBadge.className = "px-2 py-0.5 rounded-full text-[10px] font-bold bg-blue-100 text-blue-800 border border-blue-300";
      } else {
        tierBadge.textContent = est.budget_band_labels?.comfortable || 'Comfortable';
        tierBadge.className = "px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-300";
      }
    }
  }
}

function toggleTripFormModal() {
  editingTripId = null;
  document.getElementById('tripEditOptions').classList.add('hidden');
  document.getElementById('tripDestSelect').disabled = false;
  // Pre-fill trip form with default dates (14 days from today) and user profile defaults
  const startInput = document.getElementById("tripStartDateInput");
  const endInput = document.getElementById("tripEndDateInput");
  if (startInput && !startInput.value) {
    const d1 = new Date();
    d1.setDate(d1.getDate() + 14);
    startInput.value = d1.toISOString().split("T")[0];
    const d2 = new Date();
    d2.setDate(d2.getDate() + 18);
    endInput.value = d2.toISOString().split("T")[0];
  }
  updateTripDurationPreview();

  // Prefill companions from profile if available
  const companionsPref = state.currentProfile?.companions || (state.precision?.context?.b03_companions);
  if (companionsPref) {
    let compRadio = "solo";
    if (companionsPref.includes("partner") || companionsPref.includes("couple")) compRadio = "partner";
    else if (companionsPref.includes("friend")) compRadio = "friends";
    else if (companionsPref.includes("family")) compRadio = "family";
    const radioEl = document.querySelector(`input[name="tripCompanionsRadio"][value="${compRadio}"]`);
    if (radioEl) {
      radioEl.checked = true;
      onCompanionTypeChanged(compRadio);
    }
  }

  // Prefill children & elderly flags
  const hasKidsCheck = document.getElementById("tripHasChildrenCheck");
  const hasElderlyCheck = document.getElementById("tripHasElderlyCheck");
  if (hasKidsCheck && (companionsPref === "family_kids" || state.precision?.answers?.d02_children_age_group)) {
    hasKidsCheck.checked = true;
  }
  if (hasElderlyCheck && (companionsPref === "family_seniors" || state.precision?.answers?.d03_senior_accessibility)) {
    hasElderlyCheck.checked = true;
  }

  // Pre-fill pace, stay style, and transit from profile
  if (state.detailedProfile || state.currentProfile) {
    const paceSel = document.getElementById("tripPaceSelect");
    const sched = state.detailedProfile?.schedule_density || state.currentProfile?.schedule_density;
    if (paceSel && sched) {
      if (sched.includes("relaxed")) paceSel.value = "relaxed";
      else if (sched.includes("packed")) paceSel.value = "packed";
      else paceSel.value = "balanced";
    }
    const accomSel = document.getElementById("tripAccomSelect");
    const stay = state.detailedProfile?.stay_style || state.currentProfile?.stay_style;
    if (accomSel && stay) accomSel.value = stay;
    const transitSel = document.getElementById("tripTransitSelect");
    const tr = state.detailedProfile?.transit_pref || state.currentProfile?.transit_pref;
    if (transitSel && tr) transitSel.value = tr;
  }

  syncTripPartyFromChecks();
  openModal("tripFormModal");

  const destSelect = document.getElementById("tripDestSelect");
  if (destSelect && destSelect.value) {
    if (destSelect.value.startsWith("geo_") && selectedDynamicLocation) {
      updateDestinationSourceBanner(
        selectedDynamicLocation,
        selectedDynamicLocation.provenance?.is_live ? "Live Geoapify" : "Curated Catalogue",
        Boolean(selectedDynamicLocation.provenance?.is_live)
      );
      fetchTripNearbyPlaces(selectedDynamicLocation.lat, selectedDynamicLocation.lon, currentDynamicRadius);
    } else if (FEATURED_DESTINATION_COORDS[destSelect.value]) {
      const meta = FEATURED_DESTINATION_COORDS[destSelect.value];
      activeTripCoords = { ...meta };
      updateDestinationSourceBanner(meta, "Curated Catalogue", false);
      fetchTripNearbyPlaces(meta.lat, meta.lon, currentDynamicRadius);
    }
  }

  calculateTripMinimumBudget();
}

// Option A vs Option B Hotel Selection (Task 4)
let currentHotelWorkflow = "option_b";

function toggleHotelWorkflowOption(opt) {
  currentHotelWorkflow = opt;
  const labelA = document.getElementById("hotelOptionALabel");
  const labelB = document.getElementById("hotelOptionBLabel");
  const contA = document.getElementById("hotelOptionAContainer");

  if (opt === "option_a") {
    if (labelA) labelA.className = "cursor-pointer border-2 border-emerald-500 bg-white rounded-xl p-2.5 transition flex flex-col justify-between shadow-xs";
    if (labelB) labelB.className = "cursor-pointer border-2 border-slate-200 bg-white rounded-xl p-2.5 transition flex flex-col justify-between";
    if (contA) contA.classList.remove("hidden");
  } else {
    if (labelB) labelB.className = "cursor-pointer border-2 border-emerald-500 bg-white rounded-xl p-2.5 transition flex flex-col justify-between shadow-xs";
    if (labelA) labelA.className = "cursor-pointer border-2 border-slate-200 bg-white rounded-xl p-2.5 transition flex flex-col justify-between";
    if (contA) contA.classList.add("hidden");
    clearOptionAHotel();
  }
}

async function searchHotelsForOptionA(radiusMeters = 12000) {
  const destSelect = document.getElementById("tripDestSelect");
  const destId = destSelect ? destSelect.value : "";
  const destName = destSelect && destSelect.options[destSelect.selectedIndex] ? destSelect.options[destSelect.selectedIndex].text : "";
  const budget = parseFloat(document.getElementById("tripBudgetInput")?.value) || 25000;
  
  let days = 4;
  const startDate = document.getElementById("tripStartDateInput")?.value;
  const endDate = document.getElementById("tripEndDateInput")?.value;
  if (startDate && endDate) {
    const s = new Date(startDate);
    const e = new Date(endDate);
    const diff = Math.round((e - s) / (1000 * 60 * 60 * 24)) + 1;
    if (diff > 0) days = diff;
  }

  const loadingEl = document.getElementById("optionAHotelLoading");
  const resultsEl = document.getElementById("optionAHotelResults");
  if (loadingEl) loadingEl.classList.remove("hidden");
  if (resultsEl) resultsEl.innerHTML = "";

  try {
    const coords = selectedDynamicLocation || activeTripCoords || FEATURED_DESTINATION_COORDS[destId];
    const coordParams = coords && Number.isFinite(Number(coords.lat)) && Number.isFinite(Number(coords.lon))
      ? `&lat=${encodeURIComponent(coords.lat)}&lon=${encodeURIComponent(coords.lon)}`
      : "";
    const res = await fetch(`/api/stay/search?destination_id=${encodeURIComponent(destId)}&destination_name=${encodeURIComponent(destName)}${coordParams}&budget=${budget}&duration_days=${days}&radius_meters=${radiusMeters}&accommodation_tier=${encodeURIComponent(document.getElementById("tripAccomSelect").value)}&limit=10`);
    if (!res.ok) throw new Error("Could not find verified accommodations");
    const data = await res.json();
    renderOptionAHotels(data.options || []);
  } catch (err) {
    if (resultsEl) resultsEl.innerHTML = `<div class="p-3 text-center text-xs text-rose-500">Could not retrieve hotels: ${escapeHtml(err.message)}</div>`;
  } finally {
    if (loadingEl) loadingEl.classList.add("hidden");
  }
}

function renderOptionAHotels(options) {
  const resultsEl = document.getElementById("optionAHotelResults");
  if (!resultsEl) return;
  resultsEl.innerHTML = "";

  if (options.length === 0) {
    resultsEl.innerHTML = `<div class="p-3 text-center text-xs text-slate-400">No stays or curated areas inside the selected radius. <button type="button" onclick="searchHotelsForOptionA(40000)" class="underline">Try within 40 km</button></div>`;
    return;
  }

  options.forEach(h => {
    const card = document.createElement("div");
    card.className = "p-2.5 rounded-xl border border-slate-200 bg-white hover:border-emerald-400 transition flex items-center justify-between gap-2";
    card.innerHTML = `
      <div class="flex-1 min-w-0">
        <div class="flex items-center gap-1.5">
          <span class="font-bold text-slate-800 text-xs truncate">${escapeHtml(h.name)}</span>
          <span class="text-[9px] px-1.5 py-0.2 rounded bg-slate-100 text-slate-600 capitalize">${escapeHtml(h.tier_label || humanLabel(h.stay_type || 'hotel'))}</span>
        </div>
        <p class="text-[10px] text-slate-400 whitespace-normal">${escapeHtml(stayDescription(h))}</p>
      </div>
      <div class="flex items-center gap-1.5 shrink-0">
        <a href="${escapeHtml(h.external_search_url)}" target="_blank" rel="noopener noreferrer" class="px-2 py-1 text-[10px] rounded border border-slate-200 text-slate-500 hover:bg-slate-50">
          Find hotels here <i class="fa-solid fa-arrow-up-right-from-square text-[8px]"></i>
        </a>
        <button type="button" class="selectHotelOptBtn px-2.5 py-1 text-[10px] font-bold rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white transition">
          ${h.kind === "area" ? "Use area as base" : "Select Hotel"}
        </button>
      </div>
    `;
    card.querySelector(".selectHotelOptBtn").onclick = () => selectOptionAHotel(h);
    resultsEl.appendChild(card);
  });
}

function selectOptionAHotel(h) {
  const idEl = document.getElementById("selectedHotelId");
  const nameEl = document.getElementById("selectedHotelName");
  const latEl = document.getElementById("selectedHotelLat");
  const lonEl = document.getElementById("selectedHotelLon");
  const addrEl = document.getElementById("selectedHotelAddress");
  const typeEl = document.getElementById("selectedHotelType");

  if (idEl) idEl.value = h.stay_id || "";
  if (nameEl) nameEl.value = h.name || "";
  if (latEl) latEl.value = h.lat !== undefined ? h.lat : "";
  if (lonEl) lonEl.value = h.lon !== undefined ? h.lon : "";
  if (addrEl) addrEl.value = h.address || "";
  if (typeEl) typeEl.value = h.stay_type || "hotel";

  const badge = document.getElementById("optionASelectedHotelBadge");
  const badgeName = document.getElementById("optionASelectedHotelName");
  const badgeAddr = document.getElementById("optionASelectedHotelAddr");
  const resultsEl = document.getElementById("optionAHotelResults");

  if (badgeName) badgeName.textContent = h.name;
  if (badgeAddr) badgeAddr.textContent = h.address || "Central location";
  if (badge) badge.classList.remove("hidden");
  if (resultsEl) resultsEl.innerHTML = "";
}

function clearOptionAHotel() {
  const idEl = document.getElementById("selectedHotelId");
  const nameEl = document.getElementById("selectedHotelName");
  const latEl = document.getElementById("selectedHotelLat");
  const lonEl = document.getElementById("selectedHotelLon");
  const addrEl = document.getElementById("selectedHotelAddress");
  const typeEl = document.getElementById("selectedHotelType");

  if (idEl) idEl.value = "";
  if (nameEl) nameEl.value = "";
  if (latEl) latEl.value = "";
  if (lonEl) lonEl.value = "";
  if (addrEl) addrEl.value = "";
  if (typeEl) typeEl.value = "";

  const badge = document.getElementById("optionASelectedHotelBadge");
  if (badge) badge.classList.add("hidden");
}

async function handleTripCreateSubmit(e) {
  e.preventDefault();
  if (!state.currentUser) return;

  const destSelect = document.getElementById("tripDestSelect");
  const destId = destSelect.value;
  const selectedOption = destSelect.options[destSelect.selectedIndex];
  const destName = selectedOption ? selectedOption.text : destId;

  const startDate = document.getElementById("tripStartDateInput").value;
  const endDate = document.getElementById("tripEndDateInput").value;
  const travellers = parseInt(document.getElementById("tripTravellersInput").value) || 1;
  const budget = parseFloat(document.getElementById("tripBudgetInput").value) || 25000;
  const pace = document.getElementById("tripPaceSelect").value;
  const accom = document.getElementById("tripAccomSelect").value;
  const transit = document.getElementById("tripTransitSelect") ? document.getElementById("tripTransitSelect").value : "public_transit";

  const departureLocation = document.getElementById("tripDepartureInput")?.value.trim() || "Delhi";
  const compRadio = document.querySelector('input[name="tripCompanionsRadio"]:checked')?.value || "solo";
  const hasChildren = document.getElementById("tripHasChildrenCheck")?.checked || false;
  const hasElderly = document.getElementById("tripHasElderlyCheck")?.checked || false;
  const dietaryStyle = document.getElementById("tripDietarySelect")?.value || "all";
  const tripNotes = document.getElementById("tripNotesInput")?.value.trim() || "";
  const tripPrefs = { dietary: dietaryStyle, food_style: dietaryStyle, notes: tripNotes,
    include_shopping: document.getElementById('tripIncludeShoppingCheck').checked, party: readTripParty() };

  // Validate destination
  const isGeo = destId.startsWith("geo_");
  if (!isGeo && !isIndianDestinationId(destId)) {
    alert("Please select a valid Indian destination or search any city via Open-Meteo Geocoding.");
    return;
  }

  // Validate dates
  if (!startDate || !endDate) {
    alert("Please select both departure and return dates.");
    return;
  }

  const dStart = new Date(startDate);
  const dEnd = new Date(endDate);
  if (dEnd < dStart) {
    alert("Return date must be on or after departure date.");
    return;
  }

  if (travellers < 1) {
    alert("Travellers count must be at least 1.");
    return;
  }

  if (budget <= 0) {
    alert("Total trip budget in INR (₹) must be greater than zero.");
    return;
  }

  const btn = document.getElementById("generateItinerarySubmitBtn");
  if (btn) btn.disabled = true;
  if (btn) btn.textContent = "Generating LinUCB Itinerary...";

  try {
    const hotelName = document.getElementById("selectedHotelName")?.value.trim() || null;
    const hotelLat = parseFloat(document.getElementById("selectedHotelLat")?.value) || null;
    const hotelLon = parseFloat(document.getElementById("selectedHotelLon")?.value) || null;
    const hotelId = document.getElementById("selectedHotelId")?.value.trim() || null;
    const hotelAddr = document.getElementById("selectedHotelAddress")?.value.trim() || null;
    const hotelType = document.getElementById("selectedHotelType")?.value.trim() || null;

    if (editingTripId) {
      const result = await TravelModules.api(`/api/trips/${editingTripId}?user_id=${encodeURIComponent(state.currentUser.user_id)}`, {
        method:'PATCH', body:{start_date:startDate,end_date:endDate,party:readTripParty(),companions:compRadio,
          total_budget:budget,travel_pace:pace,accommodation_tier:accom,transit_pref:transit,
          departure_location:departureLocation,trip_preferences:tripPrefs,
          regeneration_mode:document.getElementById('tripRegenerationMode').value}
      });
      editingTripId = null;
      closeModal('tripFormModal');
      await loadUserTrips(result.id);
      return;
    }
    // Dynamic trip planning route if a dynamic location is selected or geocoded
    if (selectedDynamicLocation && (destId.startsWith("geo_") || selectedDynamicLocation.name === destName || destId.includes((selectedDynamicLocation.city || "").toLowerCase()))) {
      const planRes = await fetch(`/api/places/plan-dynamic`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: state.currentUser.user_id,
          city: selectedDynamicLocation.city || selectedDynamicLocation.name,
          state: selectedDynamicLocation.state || "India",
          lat: selectedDynamicLocation.lat,
          lon: selectedDynamicLocation.lon,
          start_date: startDate,
          end_date: endDate,
          travellers_count: travellers,
          total_budget: budget,
          accommodation_tier: accom,
          transit_pref: transit,
          travel_pace: pace,
          radius_meters: currentDynamicRadius || 15000,
          departure_location: departureLocation,
          party: readTripParty(),
        companions: compRadio,
          has_children: hasChildren,
          has_elderly: hasElderly,
          trip_preferences: tripPrefs,
          stay_id: hotelId,
          stay_name: hotelName,
          stay_lat: hotelLat,
          stay_lon: hotelLon,
          stay_address: hotelAddr,
          stay_type: hotelType
        })
      });
      if (!planRes.ok) {
        const errData = await planRes.json();
        alert("Error generating dynamic itinerary: " + formatApiError(errData, "Invalid trip details"));
        return;
      }
      const planData = await planRes.json();
      const createdTripId = planData.trip ? planData.trip.id : null;
      currentPlannedTripId = createdTripId;
      closeModal("tripFormModal");
      await loadUserTrips(createdTripId);
      return;
    }

    // 1. Create Trip Record (Standard fixed catalog)
    const curatedCoords = activeTripCoords || FEATURED_DESTINATION_COORDS[destId] || {};

    const tripRes = await fetch(`/api/trips/${state.currentUser.user_id}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        destination_id: destId,
        destination_name: destName,
        destination_lat: curatedCoords.lat ?? null,
        destination_lon: curatedCoords.lon ?? null,
        resolved_location: curatedCoords.formatted || destName,
        start_date: startDate,
        end_date: endDate,
        travellers_count: travellers,
        total_budget: budget,
        currency: "INR",
        accommodation_tier: accom,
        transit_pref: transit,
        travel_pace: pace,
        specific_interests: [],
        departure_location: departureLocation,
        party: readTripParty(),
        companions: compRadio,
        has_children: hasChildren,
        has_elderly: hasElderly,
        trip_preferences: tripPrefs,
        stay_id: hotelId,
        stay_name: hotelName,
        stay_lat: hotelLat,
        stay_lon: hotelLon,
        stay_address: hotelAddr,
        stay_type: hotelType
      })
    });

    if (!tripRes.ok) {
      const errData = await tripRes.json();
      alert("Error creating trip: " + formatApiError(errData, "Invalid trip details"));
      return;
    }

    const newTrip = await tripRes.json();
    closeModal("tripFormModal");

    // 2. Generate LinUCB Itinerary & Plan Engine
    if (hotelName && hotelLat !== null) {
      try {
        await fetch(`/api/plan/generate/${newTrip.id}`, { method: "POST" });
      } catch (e) {
        console.warn("Plan engine generation note:", e);
      }
    }

    const itinRes = await fetch(`/api/itinerary/generate/${newTrip.id}?user_id=${state.currentUser.user_id}`, {
      method: "POST"
    });

    if (itinRes.ok) {
      currentItinerary = await itinRes.json();
      currentPlannedTripId = newTrip.id;
      await loadUserTrips(newTrip.id);
    } else {
      const errData = await itinRes.json();
      alert("Could not generate itinerary: " + formatApiError(errData, "Server error"));
    }
  } catch (err) {
    console.error("Trip creation error:", err);
    alert("Could not generate itinerary: " + err.message);
  } finally {
    if (btn) btn.disabled = false;
    if (btn) btn.textContent = "Generate LinUCB Itinerary →";
  }
}

// ============================================================================
// UNIFIED TRIP WORKSPACE: PRE-TRIP, LIVE TRIP, POST-TRIP CONTROLLER
// ============================================================================
let currentWorkspaceMode = "pre";
let currentPreSubtab = "itin";

function switchWorkspaceMode(mode) {
  const deepProfileComplete = !!(state.profileStatus && state.profileStatus.complete);
  if ((mode === "live" || mode === "post") && !deepProfileComplete) {
    mode = "pre";
    currentPreSubtab = "itin";
    const lockedState = document.getElementById("itineraryLockedState");
    if (lockedState) lockedState.classList.remove("hidden");
  }
  currentWorkspaceMode = mode;
  const modes = ["pre", "live", "post"];
  modes.forEach(m => {
    const btn = document.getElementById(`wsTabBtn-${m}`);
    const pane = document.getElementById(m === "pre" ? "workspacePreTrip" : (m === "live" ? "workspaceLiveTrip" : "workspacePostTrip"));
    if (btn) {
      if (m === mode) {
        btn.className = "flex-1 py-2.5 px-4 rounded-lg bg-indigo-600 text-white shadow-sm flex items-center justify-center gap-2 transition";
      } else {
        btn.className = "flex-1 py-2.5 px-4 rounded-lg text-slate-600 hover:text-slate-900 hover:bg-white flex items-center justify-center gap-2 transition";
      }
    }
    if (pane) {
      pane.classList.toggle("hidden", m !== mode);
    }
  });

  if (mode === "live") {
    renderLiveTripWorkspace();
  } else if (mode === "post") {
    renderPostTripWorkspace();
  } else if (mode === "pre") {
    switchPreSubtab(currentPreSubtab);
  }
}

function switchPreSubtab(sub) {
  currentPreSubtab = sub;
  const subs = ["itin", "stay", "prep"];
  subs.forEach(s => {
    const btn = document.getElementById(`preSubBtn-${s}`);
    const pane = document.getElementById(`preSubContent-${s}`);
    if (btn) {
      if (s === sub) {
        btn.className = "px-3.5 py-1.5 rounded-lg bg-slate-900 text-white shadow-xs transition";
      } else {
        btn.className = "px-3.5 py-1.5 rounded-lg text-slate-600 hover:bg-slate-100 transition";
      }
    }
    if (pane) {
      pane.classList.toggle("hidden", s !== sub);
    }
  });

  if (sub === "stay") {
    renderStayWorkspace();
  } else if (sub === "prep") {
    renderPrepWorkspace();
  }
}

function getWorkspaceContext() {
  const api = async (endpoint, opts = {}) => {
    const res = await fetch(endpoint, opts);
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || "API request failed");
    }
    return res.json();
  };
  return {
    user: state.currentUser,
    userId: state.currentUser ? state.currentUser.user_id : null,
    tripId: currentPlannedTripId,
    workspaceMode: currentWorkspaceMode,
    trips: state.userTrips || [],
    api: (window.TravelModules && window.TravelModules.api) ? window.TravelModules.api : api
  };
}

function renderStayWorkspace() {
  const container = document.getElementById("workspaceStayContainer");
  if (!container) return;
  const ctx = getWorkspaceContext();
  if (window.TravelModules && window.TravelModules.stay && typeof window.TravelModules.stay.render === "function") {
    window.TravelModules.stay.render(container, ctx);
  } else {
    container.innerHTML = `<div class="p-6 text-center text-slate-400 text-xs"><i class="fa-solid fa-spinner fa-spin mr-2"></i>Loading stays & accommodation...</div>`;
  }
}

function renderPrepWorkspace() {
  const container = document.getElementById("workspacePrepContainer");
  if (!container) return;
  const ctx = getWorkspaceContext();
  if (window.TravelModules && window.TravelModules.prep && typeof window.TravelModules.prep.render === "function") {
    window.TravelModules.prep.render(container, ctx);
  } else {
    container.innerHTML = `<div class="p-6 text-center text-slate-400 text-xs"><i class="fa-solid fa-spinner fa-spin mr-2"></i>Loading packing & preparation...</div>`;
  }
}

function renderLiveTripWorkspace() {
  document.getElementById('workspacePostContainer').innerHTML='';
  const container = document.getElementById("workspaceLiveContainer");
  if (!container) return;
  const ctx = getWorkspaceContext();
  if (window.TravelModules && window.TravelModules.live && typeof window.TravelModules.live.render === "function") {
    window.TravelModules.live.render(container, ctx);
  } else {
    container.innerHTML = `<div class="p-6 text-center text-slate-400 text-xs"><i class="fa-solid fa-spinner fa-spin mr-2"></i>Loading live trip...</div>`;
  }
}

function renderPostTripWorkspace() {
  document.getElementById('workspaceLiveContainer').innerHTML='';
  const container = document.getElementById("workspacePostContainer");
  if (!container) return;
  const ctx = getWorkspaceContext();
  if (window.TravelModules && window.TravelModules.live && typeof window.TravelModules.live.render === "function") {
    window.TravelModules.live.render(container, ctx);
  } else {
    container.innerHTML = `<div class="p-6 text-center text-slate-400 text-xs"><i class="fa-solid fa-spinner fa-spin mr-2"></i>Loading post-trip feedback...</div>`;
  }
}

async function loadTripItinerary(tripId) {
  if (!state.currentUser || !tripId) return;

  const isDeepComplete = state.profileStatus ? state.profileStatus.complete : false;
  const lockedState = document.getElementById("itineraryLockedState");
  const emptyState = document.getElementById("itineraryEmptyState");
  const displayContainer = document.getElementById("itineraryDisplayContainer");

  if (!isDeepComplete) {
    if (displayContainer) displayContainer.classList.add("hidden");
    if (emptyState) emptyState.classList.add("hidden");
    if (lockedState) lockedState.classList.remove("hidden");
    return;
  }

  const tripObj = activeUserTrips.find(t => t.id === tripId);
  if (tripObj && !isIndianTrip(tripObj)) {
    showInternationalTripNotice(tripObj);
    return;
  }

  try {
    const res = await fetch(`/api/itinerary/${tripId}?user_id=${state.currentUser.user_id}`);
    if (res.ok) {
      currentItinerary = await res.json();
      renderItinerary(currentItinerary);
    } else {
      // Auto-generate if not yet generated for Indian destinations
      const genRes = await fetch(`/api/itinerary/generate/${tripId}?user_id=${state.currentUser.user_id}`, {
        method: "POST"
      });
      if (genRes.ok) {
        currentItinerary = await genRes.json();
        renderItinerary(currentItinerary);
      }
    }
  } catch (err) {
    console.error("Error loading itinerary:", err);
  }
}

function renderItinerary(itin) {
  const emptyState = document.getElementById("itineraryEmptyState");
  const displayContainer = document.getElementById("itineraryDisplayContainer");
  const daysContainer = document.getElementById("itineraryDaysContainer");
  const lockedState = document.getElementById("itineraryLockedState");

  // Trip planner should not show info if deep personalization is not completed
  const isDeepComplete = state.profileStatus ? state.profileStatus.complete : false;
  if (!isDeepComplete) {
    if (displayContainer) displayContainer.classList.add("hidden");
    if (emptyState) emptyState.classList.add("hidden");
    if (lockedState) lockedState.classList.remove("hidden");
    return;
  }

  if (lockedState) lockedState.classList.add("hidden");

  if (!itin || !itin.days || itin.days.length === 0) {
    emptyState.classList.remove("hidden");
    displayContainer.classList.add("hidden");
    return;
  }

  emptyState.classList.add("hidden");
  displayContainer.classList.remove("hidden");

  document.getElementById("itinDestinationTitle").textContent = itin.destination_name;
  document.getElementById("itinDatesBadge").textContent = `${itin.total_days} Days Planned`;
  document.getElementById("itinSummaryNotes").textContent = itin.summary_notes || "Tailored by Contextual LinUCB bandit.";
  document.getElementById("itinTotalCostDisplay").textContent = formatINR(itin.total_estimated_cost);

  // Companion and departure location badges
  const currentTrip = (activeUserTrips || []).find(t => t.id === (itin.trip_id || currentPlannedTripId));
  const compBadge = document.getElementById("itinCompanionsBadge");
  if (compBadge) {
    if (currentTrip) {
      const compLabel = currentTrip.party_label || `${currentTrip.travellers_count} traveller(s)`;
      compBadge.textContent = compLabel;
      compBadge.classList.remove("hidden");
    } else {
      compBadge.textContent = "Personalized Trip";
    }
  }
  const depBadge = document.getElementById("itinDepartureBadge");
  if (depBadge) {
    if (currentTrip && currentTrip.departure_location) {
      depBadge.textContent = `From: ${currentTrip.departure_location}`;
      depBadge.classList.remove("hidden");
    } else {
      depBadge.textContent = "From: Delhi";
    }
  }

  renderCostBreakdown(itin.cost_estimate);
  if (window.TravelModules?.itinerary_editor) {
    window.TravelModules.itinerary_editor.render(document.getElementById('workspaceEditorContainer'), getWorkspaceContext());
  }
  // Ensure Pre-trip daily itinerary tab is active
  switchWorkspaceMode("pre");
  switchPreSubtab("itin");

  // Load and display weather for this specific trip's resolved coordinates & dates
  loadItineraryLiveWeather({
    tripId: itin.trip_id || currentPlannedTripId,
    destinationId: itin.destination_id || currentTrip?.destination_id || "",
    destinationName: itin.destination_name || currentTrip?.destination_name || "",
    resolvedLocation: itin.resolved_location || currentTrip?.resolved_location || itin.destination_name || currentTrip?.destination_name || "",
    lat: itin.destination_lat ?? currentTrip?.destination_lat ?? null,
    lon: itin.destination_lon ?? currentTrip?.destination_lon ?? null,
    startDate: itin.start_date || currentTrip?.start_date || "",
    endDate: itin.end_date || currentTrip?.end_date || ""
  });

  daysContainer.innerHTML = "";

  itin.days.forEach(day => {
    const dayCard = document.createElement("div");
    dayCard.className = "bg-slate-50 border border-slate-200 rounded-2xl p-4 sm:p-5 space-y-4";

    const header = document.createElement("div");
    header.className = "flex flex-col sm:flex-row sm:items-center justify-between pb-3 border-b border-slate-200 gap-2";
    header.innerHTML = `
      <div>
        <div class="flex items-center gap-2">
          <span class="px-2 py-0.5 rounded text-[10px] font-bold bg-indigo-600 text-white">Day ${day.day_number}</span>
          <span class="text-xs font-semibold text-slate-500">${day.date}</span>
        </div>
        <h4 class="text-sm font-bold text-slate-900 mt-0.5">${day.theme}</h4>
      </div>
      <div class="flex items-center gap-2 text-xs">
        <span class="text-slate-500">${day.activities.length} activities · Est. ${formatINR(day.total_cost)}</span>
      </div>
    `;
    dayCard.appendChild(header);

    const actList = document.createElement("div");
    actList.className = "space-y-3";

    day.activities.forEach(act => {
      const actRow = document.createElement("div");
      const isAccepted = act.status === 'accepted';
      const isRejected = act.status === 'rejected';
      const isModified = act.status === 'modified';

      let statusBadge = `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-200 text-slate-700">Proposed</span>`;
      let borderHighlight = "border-slate-200";

      if (isAccepted) {
        statusBadge = `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-100 text-emerald-800"><i class="fa-solid fa-check"></i> Accepted</span>`;
        borderHighlight = "border-emerald-300 bg-emerald-50/20";
      } else if (isRejected) {
        statusBadge = `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-red-100 text-red-800"><i class="fa-solid fa-xmark"></i> Skipped</span>`;
        borderHighlight = "border-red-200 opacity-60";
      } else if (isModified) {
        statusBadge = `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-100 text-amber-800"><i class="fa-solid fa-arrows-rotate"></i> Modified</span>`;
        borderHighlight = "border-amber-300 bg-amber-50/20";
      }

      actRow.className = `p-3.5 bg-white rounded-xl border ${borderHighlight} transition shadow-sm hover:shadow flex flex-col md:flex-row justify-between gap-3`;

      actRow.innerHTML = `
        <div class="flex gap-3">
          ${act.photo_url ? `<img src="${act.photo_url}" onerror="this.onerror=null;this.src='/static/images/destination-placeholder.svg'" class="w-16 h-16 rounded-lg object-cover flex-shrink-0" alt="${act.title}">` : `
          <div class="w-16 h-16 rounded-lg bg-indigo-50 text-indigo-500 flex items-center justify-center flex-shrink-0">
            <i class="fa-solid fa-location-dot text-xl"></i>
          </div>`}
          <div class="space-y-1">
            <div class="flex flex-wrap items-center gap-1.5">
              <span class="text-[10px] font-bold uppercase tracking-wider text-slate-500">${act.time_slot}</span>
              ${statusBadge}
              <span class="text-[10px] bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded">${act.neighborhood || 'Local Area'}</span>
              <span class="text-[10px] font-bold text-slate-700">${act.duration_minutes} mins · ${formatINR(act.cost_estimate)}</span>
            </div>
            <h5 class="text-sm font-bold text-slate-900">${act.title}</h5>
            <p class="text-xs text-slate-600 leading-snug">${act.description || ''}</p>
            <div class="text-[11px] text-indigo-700 bg-indigo-50/80 border border-indigo-100 rounded-md px-2 py-1 font-medium flex items-start gap-1.5 mt-1">
              <i class="fa-solid fa-sparkles text-[10px] text-indigo-500 mt-0.5 shrink-0"></i>
              <span>${act.because_you_said || act.why_it_suits || 'Matches your travel pacing and style.'}</span>
            </div>
            ${act.transit_suggestion ? `<div class="text-[10px] text-slate-400"><i class="fa-solid fa-person-walking"></i> ${act.transit_suggestion}</div>` : ''}
          </div>
        </div>

        <div class="flex md:flex-col justify-end items-end gap-1.5 flex-shrink-0 pt-2 md:pt-0">
          <div class="flex items-center gap-1">
            <button onclick="acceptActivity('${itin.id}', '${act.activity_id}')" class="px-2.5 py-1.5 rounded-lg text-xs font-semibold ${isAccepted ? 'bg-emerald-600 text-white' : 'bg-emerald-50 text-emerald-700 hover:bg-emerald-100'} transition flex items-center gap-1" title="Accept recommendation">
              <i class="fa-solid fa-check"></i>
              <span>Accept</span>
            </button>
            <button onclick="openRejectModal('${itin.id}', '${act.activity_id}')" class="px-2.5 py-1.5 rounded-lg text-xs font-semibold ${isRejected ? 'bg-red-600 text-white' : 'bg-red-50 text-red-700 hover:bg-red-100'} transition flex items-center gap-1" title="Reject / Skip recommendation">
              <i class="fa-solid fa-xmark"></i>
              <span>Skip</span>
            </button>
            <button onclick="openModifyModal('${itin.id}', '${act.activity_id}')" class="px-2.5 py-1.5 rounded-lg text-xs font-semibold bg-slate-100 text-slate-700 hover:bg-slate-200 transition flex items-center gap-1" title="Change to alternative">
              <i class="fa-solid fa-arrows-rotate"></i>
              <span>Modify</span>
            </button>
          </div>
        </div>
      `;

      actList.appendChild(actRow);
    });

    dayCard.appendChild(actList);
    daysContainer.appendChild(dayCard);
  });
}

// -------------------------------------------------------------
// Interactive Feedback Actions
// -------------------------------------------------------------

async function acceptActivity(itineraryId, activityId) {
  if (!state.currentUser) return;
  try {
    const res = await fetch(`/api/itinerary/feedback/${state.currentUser.user_id}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        itinerary_id: itineraryId,
        activity_id: activityId,
        action_type: "accept"
      })
    });
    if (res.ok) {
      await loadTripItinerary(currentPlannedTripId);
    }
  } catch (err) {
    console.error("Error accepting activity:", err);
  }
}

function openRejectModal(itineraryId, activityId) {
  pendingFeedbackContext = { itineraryId, activityId };
  openModal("activityRejectModal");
}

async function confirmActivityRejection() {
  if (!state.currentUser || !pendingFeedbackContext) return;

  const radio = document.querySelector('input[name="rejectReasonRadio"]:checked');
  const reason = radio ? radio.value : "not_interested";
  const tripSpecific = document.getElementById("rejectIsTripSpecificCheck").checked;

  try {
    const res = await fetch(`/api/itinerary/feedback/${state.currentUser.user_id}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        itinerary_id: pendingFeedbackContext.itineraryId,
        activity_id: pendingFeedbackContext.activityId,
        action_type: "reject",
        rejection_reason: reason,
        is_trip_specific: tripSpecific
      })
    });
    if (res.ok) {
      closeModal("activityRejectModal");
      await loadTripItinerary(currentPlannedTripId);
    }
  } catch (err) {
    console.error("Error rejecting activity:", err);
  }
}

async function openModifyModal(itineraryId, activityId) {
  if (!state.currentUser) return;
  pendingFeedbackContext = { itineraryId, activityId };
  openModal("activityAlternativeModal");

  const container = document.getElementById("alternativesListContainer");
  container.innerHTML = `<div class="text-center py-6 text-slate-400"><i class="fa-solid fa-spinner fa-spin mr-2"></i>Finding tailored alternatives...</div>`;

  try {
    const res = await fetch(`/api/itinerary/alternatives/${itineraryId}/${activityId}?user_id=${state.currentUser.user_id}`);
    if (res.ok) {
      const data = await res.json();
      const alts = data.alternatives || [];
      if (alts.length === 0) {
        container.innerHTML = `<p class="text-slate-500 italic text-center py-4">No alternative candidates available for this slot.</p>`;
        return;
      }
      container.innerHTML = "";
      alts.forEach(alt => {
        const item = document.createElement("div");
        item.className = "p-3 bg-slate-50 hover:bg-slate-100 border border-slate-200 rounded-xl transition cursor-pointer flex justify-between items-center gap-3";
        item.innerHTML = `
          <div>
            <div class="flex items-center gap-1.5 mb-0.5">
              <span class="text-[10px] font-bold uppercase bg-indigo-100 text-indigo-700 px-1.5 py-0.5 rounded">${alt.category.replace('_', ' ')}</span>
              <span class="text-[10px] text-slate-500">${alt.duration_minutes} mins · ${formatINR(alt.cost_amount)}</span>
            </div>
            <h5 class="text-xs font-bold text-slate-900">${alt.name}</h5>
            <p class="text-[11px] text-slate-500 leading-tight">${alt.description}</p>
          </div>
          <button onclick="selectAlternative('${alt.id}')" class="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white font-bold rounded-lg text-xs whitespace-nowrap">
            Choose This
          </button>
        `;
        container.appendChild(item);
      });
    }
  } catch (err) {
    console.error("Error loading alternatives:", err);
  }
}

async function selectAlternative(replacementId) {
  if (!state.currentUser || !pendingFeedbackContext) return;

  try {
    const res = await fetch(`/api/itinerary/feedback/${state.currentUser.user_id}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        itinerary_id: pendingFeedbackContext.itineraryId,
        activity_id: pendingFeedbackContext.activityId,
        action_type: "modify",
        replacement_activity_id: replacementId
      })
    });
    if (res.ok) {
      closeModal("activityAlternativeModal");
      await loadTripItinerary(currentPlannedTripId);
    }
  } catch (err) {
    console.error("Error applying modification:", err);
  }
}

async function regenerateEntireItinerary() {
  if (!state.currentUser || !currentPlannedTripId) return;
  const tripObj = activeUserTrips.find(t => t.id === currentPlannedTripId);
  if (tripObj && !isIndianTrip(tripObj)) {
    alert("Itinerary regeneration is only supported for Indian destinations. This trip is an unsupported international destination.");
    return;
  }
  if (!confirm("Regenerate itinerary? This will preserve your accepted activities while replacing skipped slots with fresh recommendations.")) return;

  try {
    const res = await fetch(`/api/itinerary/generate/${currentPlannedTripId}?user_id=${state.currentUser.user_id}`, {
      method: "POST"
    });
    if (res.ok) {
      currentItinerary = await res.json();
      renderItinerary(currentItinerary);
    }
  } catch (err) {
    console.error("Error regenerating itinerary:", err);
  }
}

let _weatherRequestSeq = 0;

function resetItineraryWeatherBanner() {
  _weatherRequestSeq += 1;
  const summaryEl = document.getElementById("itinWeatherSummary");
  const detailsEl = document.getElementById("itinWeatherDetails");
  const badgeEl = document.getElementById("itinWeatherSourceBadge");
  if (summaryEl) summaryEl.textContent = "Checking weather...";
  if (detailsEl) detailsEl.textContent = "";
  if (badgeEl) {
    badgeEl.textContent = "Loading...";
    badgeEl.className = "text-[10px] font-mono px-2 py-0.5 rounded bg-slate-100 text-slate-600 border border-slate-200";
  }
}

async function loadItineraryLiveWeather(tripCtx) {
  const card = document.getElementById("itinWeatherCard");
  const summaryEl = document.getElementById("itinWeatherSummary");
  const detailsEl = document.getElementById("itinWeatherDetails");
  const badgeEl = document.getElementById("itinWeatherSourceBadge");
  if (!card || !tripCtx) return;

  const ctxObj = typeof tripCtx === "string"
    ? { destinationName: tripCtx, resolvedLocation: tripCtx }
    : tripCtx;

  const reqSeq = ++_weatherRequestSeq;
  const resolvedLoc = ctxObj.resolvedLocation || ctxObj.destinationName || "Selected destination";
  const dateLabel = ctxObj.startDate && ctxObj.endDate
    ? ` (${ctxObj.startDate} to ${ctxObj.endDate})`
    : (ctxObj.startDate ? ` (${ctxObj.startDate})` : "");

  const setUnavailable = () => {
    if (summaryEl) summaryEl.textContent = "Weather information unavailable";
    if (detailsEl) detailsEl.textContent = `${resolvedLoc}${dateLabel}`;
    if (badgeEl) {
      badgeEl.textContent = "Unavailable";
      badgeEl.className = "text-[10px] font-mono px-2 py-0.5 rounded bg-slate-100 text-slate-600 border border-slate-200";
    }
  };

  try {
    card.classList.remove("hidden");
    if (summaryEl) summaryEl.textContent = `Checking weather for ${resolvedLoc}...`;
    if (detailsEl) detailsEl.textContent = `${resolvedLoc}${dateLabel}`;
    if (badgeEl) {
      badgeEl.textContent = "Loading...";
      badgeEl.className = "text-[10px] font-mono px-2 py-0.5 rounded bg-sky-50 text-sky-700 border border-sky-200";
    }

    let lat = ctxObj.lat;
    let lon = ctxObj.lon;

    if ((lat === null || lat === undefined || !Number.isFinite(Number(lat))) && ctxObj.destinationId && FEATURED_DESTINATION_COORDS[ctxObj.destinationId]) {
      lat = FEATURED_DESTINATION_COORDS[ctxObj.destinationId].lat;
      lon = FEATURED_DESTINATION_COORDS[ctxObj.destinationId].lon;
    }

    // Legacy trip fallback without stored coordinates: resolve strictly via India location search (never silent Manali)
    if (lat === null || lat === undefined || lon === null || lon === undefined) {
      const cleanQuery = (ctxObj.destinationName || "").split("(")[0].split(",")[0].trim();
      if (cleanQuery.length >= 2) {
        const locRes = await fetch(`/api/places/search-locations?q=${encodeURIComponent(cleanQuery)}&limit=1`);
        if (locRes.ok) {
          const locData = await locRes.json();
          const first = (locData.results || [])[0];
          if (first && first.lat !== undefined && first.lon !== undefined) {
            lat = first.lat;
            lon = first.lon;
          }
        }
      }
    }

    if (_weatherRequestSeq !== reqSeq) return;
    if (lat === null || lat === undefined || lon === null || lon === undefined || !Number.isFinite(Number(lat)) || !Number.isFinite(Number(lon))) {
      setUnavailable();
      return;
    }

    const params = new URLSearchParams({
      lat: String(lat),
      lon: String(lon)
    });
    if (ctxObj.startDate) params.set("start_date", ctxObj.startDate);
    if (ctxObj.endDate) params.set("end_date", ctxObj.endDate);

    const wRes = await fetch(`/api/prep/${encodeURIComponent(ctxObj.tripId || currentPlannedTripId)}/weather`);
    if (_weatherRequestSeq !== reqSeq) return;
    if (!wRes.ok) {
      setUnavailable();
      return;
    }

    const wData = await wRes.json();
    if (_weatherRequestSeq !== reqSeq) return;

    if (!wData || wData.available === false || wData.weather_type === "unavailable" || wData.source === "unavailable") {
      setUnavailable();
      return;
    }

    const hasTemps = wData.temp_min_c !== undefined && wData.temp_max_c !== undefined;
    const tempRange = hasTemps ? `${wData.temp_min_c}°C – ${wData.temp_max_c}°C` : "";
    const desc = wData.weather_description || (wData.weather_type === "forecast" ? "Forecast" : "Seasonal Climate");
    if (summaryEl) {
      summaryEl.textContent = tempRange ? `${desc} · ${tempRange}` : desc;
    }

    const rain = wData.rain_probability !== undefined ? ` · Rain ${wData.rain_probability}%` : "";
    const wind = wData.wind_kmh !== undefined ? ` · Wind ${wData.wind_kmh} km/h` : "";
    const isForecast = wData.weather_type === "forecast" || wData.api_type === "open-meteo-forecast";
    const refNote = !isForecast && wData.reference_period ? ` · Climate avg (${wData.reference_period})` : "";

    if (detailsEl) {
      detailsEl.textContent = `${resolvedLoc}${dateLabel}${rain}${wind}${refNote}. ${wData.message || ''}`;
      let chips = document.getElementById('tripWeatherDaily');
      if (chips) chips.innerHTML = (wData.daily || []).map(d => `<span class="inline-block rounded border px-2 py-1 text-[10px]">${escapeHtml(d.date)} · ${d.rain_probability_pct >= 40 ? '🌧' : '☀'} ${d.temp_min_c}–${d.temp_max_c}°C · ${d.rain_probability_pct}% rain · ${escapeHtml(d.label)}</span>`).join(' ');
    }

    if (badgeEl) {
      const cacheSuffix = wData.source === "cache" ? " · Cached" : "";
      if (isForecast) {
        badgeEl.textContent = `Current Forecast · Open-Meteo${cacheSuffix}`;
        badgeEl.className = "text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200";
      } else {
        badgeEl.textContent = wData.source === 'offline-estimate' ? wData.label : `Historical Climate Estimate · ${wData.label}`;
        badgeEl.className = "text-[10px] font-mono px-2 py-0.5 rounded bg-amber-50 text-amber-700 border border-amber-200";
      }
    }
  } catch (err) {
    console.warn("Failed to load trip weather:", err);
    if (_weatherRequestSeq === reqSeq) {
      setUnavailable();
    }
  }
}



// Shared planner presentation helpers.
let editingTripId = null;
function humanLabel(value) {
  const labels = {mid_range:'Mid-range', boutique:'Boutique & Heritage', boutique_hotel:'Boutique & Heritage',
    resort:'Luxury', budget_hostel:'Hostel', public_transit:'Public transit', cab_rental:'Private cab', partner:'Couple'};
  return labels[value] || String(value || '').replace(/_/g,' ').replace(/\b\w/g,c=>c.toUpperCase());
}
function stayDescription(stay) {
  const bands = Object.values(stay.price_bands || {}).map(b => `${b.label}: ${formatINR(b.min_inr)}–${formatINR(b.max_inr)}`).join('; ');
  return `${stay.label || 'Rates require confirmation'} · ${stay.distance_km ?? '?'} km${bands ? ' · Per room/night: '+bands : ''}`;
}
function tripSelectorLabel(trip) {
  const start = new Date(trip.start_date+'T00:00:00');
  const end = new Date(trip.end_date+'T00:00:00');
  const dateText = `${start.getDate()}–${end.toLocaleDateString('en-IN',{day:'numeric',month:'short'})}`;
  return `${trip.destination_name.replace(/\s*\([^)]*\)/g,'')} · ${dateText} · ${trip.travellers_count} traveller${trip.travellers_count===1?'':'s'}`;
}
function readTripParty() {
  return {adults:Math.max(1,Number(document.getElementById('tripAdultsInput').value)||1),
    children:Math.max(0,Number(document.getElementById('tripChildrenInput').value)||0),
    seniors:Math.max(0,Number(document.getElementById('tripSeniorsInput').value)||0)};
}
function syncTripPartyFromCounts() {
  const party=readTripParty(), total=party.adults+party.children+party.seniors;
  document.getElementById('tripTravellersInput').value=total;
  document.getElementById('tripHasChildrenCheck').checked=party.children>0;
  document.getElementById('tripHasElderlyCheck').checked=party.seniors>0;
  const type=party.children || party.seniors ? 'family' : total===1 ? 'solo' : total===2 ? 'partner' : 'friends';
  const radio=document.querySelector(`input[name="tripCompanionsRadio"][value="${type}"]`);
  if(radio) radio.checked=true;
  calculateTripMinimumBudget();
}
function syncTripPartyFromTotal() {
  const total=Math.max(1,Number(document.getElementById('tripTravellersInput').value)||1);
  document.getElementById('tripAdultsInput').value=total;
  document.getElementById('tripChildrenInput').value=0;
  document.getElementById('tripSeniorsInput').value=0;
  syncTripPartyFromCounts();
}
function syncTripPartyFromChecks() {
  document.getElementById('tripChildrenInput').value=document.getElementById('tripHasChildrenCheck').checked?Math.max(1,readTripParty().children):0;
  document.getElementById('tripSeniorsInput').value=document.getElementById('tripHasElderlyCheck').checked?Math.max(1,readTripParty().seniors):0;
  syncTripPartyFromCounts();
}
function renderCostBreakdown(cost) {
  const element=document.getElementById('tripCostBreakdown');
  if(!cost || !element) return;
  element.innerHTML=`<strong>Indicative estimate — not live prices</strong><div>${escapeHtml(cost.budget_message)} · ${formatINR(cost.per_person_per_day)} per person/day</div>`+
    Object.entries(cost.cost_breakdown).map(([key,value])=>`<span class="inline-block mr-3">${escapeHtml(humanLabel(key))}: ${formatINR(value.per_party)} (${formatINR(value.per_person)}/person)</span>`).join('')+
    `<details><summary>Planning assumptions</summary><div>${escapeHtml(JSON.stringify(cost.assumptions))}</div></details>`;
}
async function editSelectedTrip() {
  const trip=activeUserTrips.find(t=>t.id===currentPlannedTripId);
  if(!trip) return;
  toggleTripFormModal();
  editingTripId=trip.id;
  document.getElementById('tripEditOptions').classList.remove('hidden');
  const fields={tripDestSelect:trip.destination_id,tripStartDateInput:trip.start_date,tripEndDateInput:trip.end_date,
    tripBudgetInput:trip.total_budget,tripPaceSelect:trip.travel_pace,tripTransitSelect:trip.transit_pref,
    tripAccomSelect:trip.accommodation_tier,tripDepartureInput:trip.departure_location,
    tripDietarySelect:trip.trip_preferences?.food_style || trip.trip_preferences?.dietary || 'all',
    tripNotesInput:trip.trip_preferences?.notes || '',tripAdultsInput:trip.party?.adults || trip.travellers_count,
    tripChildrenInput:trip.party?.children || 0,tripSeniorsInput:trip.party?.seniors || 0};
  for(const [id,value] of Object.entries(fields)) document.getElementById(id).value=value;
  document.getElementById('tripDestSelect').disabled=true;
  document.getElementById('tripIncludeShoppingCheck').checked=!!trip.trip_preferences?.include_shopping;
  syncTripPartyFromCounts();
}
async function deleteSelectedTrip() {
  if(!currentPlannedTripId || !confirm('Delete this trip, itinerary and trip feedback? Your learned preferences will be kept.')) return;
  try {
    await TravelModules.api(`/api/trips/${currentPlannedTripId}?user_id=${encodeURIComponent(state.currentUser.user_id)}`,{method:'DELETE'});
    currentPlannedTripId=null;
    await loadUserTrips();
  } catch(error) { alert(error.message); }
}
