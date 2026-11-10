// Builds a "Companion" button + modal, one tab per backend module (GET /api/modules).
// Enforces deep personalization lock before Companion features can be used.
// Excludes ranking displays from the Companion interface.
window.TravelModules = (function () {
  const registry = {};
  let tabs = [], activeId = null, trips = [], tripId = null;
  let isUnlocked = false;

  function api(path, opts = {}) {
    const o = Object.assign({ headers: { "Content-Type": "application/json" } }, opts);
    if (o.body && typeof o.body !== "string") o.body = JSON.stringify(o.body);
    return fetch(path, o).then(async r => {
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(data.detail || r.statusText);
      return data;
    });
  }
  const ctx = () => ({ user: state.currentUser, userId: state.currentUser && state.currentUser.user_id,
                       tripId, trips, api });

  function register(id, mod) { registry[id] = mod; }

  // Global currency helper for INR
  window.formatINR = function (val) {
    if (val == null || isNaN(val)) return "₹0";
    const num = Math.round(Number(val));
    return "₹" + num.toLocaleString("en-IN");
  };

  async function checkCompanionAccess() {
    if (!state.currentUser || !state.currentUser.user_id) {
      isUnlocked = false;
      return false;
    }
    try {
      const status = await api(`/api/companion/status/${state.currentUser.user_id}`);
      isUnlocked = Boolean(status.unlocked);
      return isUnlocked;
    } catch {
      isUnlocked = false;
      return false;
    }
  }

  function updateButtonState(btn) {
    if (!btn) return;
    if (isUnlocked) {
      btn.className = "text-xs bg-[#2b2278] hover:bg-[#1b1452] text-white font-medium px-3.5 py-1.5 rounded-xl transition flex items-center gap-1.5 shadow-sm";
      btn.innerHTML = `<i class="fa-solid fa-compass text-[#e27141]"></i><span>Companion</span>`;
    } else {
      btn.className = "text-xs bg-[#2b2278] hover:bg-[#1b1452] text-white font-medium px-3 py-1.5 rounded-xl transition flex items-center gap-1.5 shadow-sm border border-indigo-900";
      btn.innerHTML = `<i class="fa-solid fa-lock text-[#e27141]"></i><span>Companion</span><span class="text-[10px] bg-[#e27141] text-white px-1.5 py-0.5 rounded-md font-bold uppercase tracking-wider">Locked</span>`;
    }
  }

  async function open() {
    if (!state.currentUser) {
      alert("Please log in first.");
      return;
    }

    const modal = document.getElementById("companionModal");
    modal.classList.remove("hidden");

    // Re-verify deep personalization status
    await checkCompanionAccess();
    const btn = document.getElementById("companionHeaderBtn");
    updateButtonState(btn);

    const lockedCard = document.getElementById("companionLockedCard");
    const unlockedContent = document.getElementById("companionUnlockedContent");

    if (!isUnlocked) {
      lockedCard.classList.remove("hidden");
      unlockedContent.classList.add("hidden");
      return;
    }

    lockedCard.classList.add("hidden");
    unlockedContent.classList.remove("hidden");

    trips = await api(`/api/trips/${state.currentUser.user_id}`).catch(() => []);
    const sel = document.getElementById("companionTrip");
    sel.innerHTML = trips.length
      ? trips.map(t => `<option value="${t.id}">${t.destination_name} (${t.start_date} → ${t.end_date})</option>`).join("")
      : `<option value="">No trips yet – plan one from the dashboard</option>`;
    tripId = sel.value || null;
    sel.onchange = () => { tripId = sel.value || null; show(activeId); };

    // Default to first available tab (excluding ranking/places)
    const validTabs = tabs.filter(t => t.id !== "ranking" && t.id !== "places");
    show(activeId || (validTabs[0] && validTabs[0].id));
  }

  async function show(id) {
    if (!id || !isUnlocked) return;
    activeId = id;
    document.querySelectorAll("#companionTabs button").forEach(b => {
      const on = b.dataset.id === id;
      b.classList.toggle("bg-[#2b2278]", on); b.classList.toggle("text-white", on);
      b.classList.toggle("bg-slate-100", !on);
    });
    const box = document.getElementById("companionBody");
    box.innerHTML = `<div class="p-8 text-center text-slate-500 text-xs"><i class="fa-solid fa-spinner fa-spin mr-2"></i>Loading module...</div>`;
    if (!registry[id]) {
      await new Promise(res => {
        const s = document.createElement("script");
        s.src = `/static/modules/${id}.js`;
        s.onload = res;
        s.onerror = res;
        document.body.appendChild(s);
      });
    }
    box.innerHTML = "";
    if (registry[id]) {
      try {
        await registry[id].render(box, ctx());
      } catch (e) {
        box.innerHTML = `<p class="text-rose-600 text-sm">Module error: ${e.message}</p>`;
      }
    } else {
      box.innerHTML = `<p class="text-slate-500 text-sm">No UI file found: static/modules/${id}.js</p>`;
    }
  }

  async function init() {
    // Check initial deep personalization status
    await checkCompanionAccess();

    // Fetch modules without exposing ranking
    const allModules = await api("/api/modules").catch(() => []);
    tabs = allModules.filter(t => t.id !== "ranking" && t.id !== "places");

    const modal = document.createElement("div");
    modal.id = "companionModal";
    modal.className = "hidden fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4";
    modal.innerHTML = `
      <div class="bg-white rounded-2xl shadow-xl w-full max-w-3xl max-h-[90vh] overflow-y-auto p-5">
        <div class="flex justify-between items-center mb-3">
          <div class="flex items-center gap-2">
            <h2 class="font-bold text-lg text-slate-900">Personal Travel Companion</h2>
            <span class="text-[10px] font-bold px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 border border-indigo-200">Level 2 Personalization</span>
          </div>
          <button onclick="document.getElementById('companionModal').classList.add('hidden')" class="text-slate-400 hover:text-slate-600 text-base">✕</button>
        </div>

        <!-- Locked State Banner & Questionnaire Redirect -->
        <div id="companionLockedCard" class="hidden p-8 text-center space-y-4 border border-slate-200 rounded-2xl bg-gradient-to-b from-slate-50 to-white my-4 shadow-sm">
          <div class="w-14 h-14 bg-amber-100 text-amber-600 rounded-2xl flex items-center justify-center mx-auto text-2xl shadow-inner">
            <i class="fa-solid fa-lock"></i>
          </div>
          <div class="space-y-1">
            <h3 class="text-base font-bold text-slate-900">Personal Travel Profile Required</h3>
            <p class="text-xs text-slate-600 max-w-md mx-auto leading-relaxed">
              Travel Companion requires a completed <strong>Level 2 Personal Travel Profile</strong>.
              It adapts packing lists, weather advisories, schedule timing, and alternative choices specifically to your comfort levels, dietary needs, and walking pace.
            </p>
          </div>
          <div class="pt-2">
            <button onclick="document.getElementById('companionModal').classList.add('hidden'); if (typeof openPersonalProfileModal === 'function') openPersonalProfileModal();"
              class="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white font-bold text-xs rounded-xl shadow transition inline-flex items-center gap-2">
              <i class="fa-solid fa-sparkles text-amber-300"></i>
              <span>Complete Personal Travel Profile &rarr;</span>
            </button>
          </div>
        </div>

        <!-- Unlocked Companion Content -->
        <div id="companionUnlockedContent" class="space-y-3">
          <div class="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 bg-slate-50 p-2.5 rounded-xl border border-slate-200">
            <label class="text-xs font-semibold text-slate-600">Select Trip:</label>
            <select id="companionTrip" class="border border-slate-300 rounded-lg px-2.5 py-1.5 text-xs bg-white w-full sm:w-auto font-medium"></select>
          </div>
          <div id="companionTabs" class="flex flex-wrap gap-2 pt-1 border-b border-slate-100 pb-3">
            ${tabs.map(t => `<button data-id="${t.id}" class="text-xs px-3 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 font-medium transition flex items-center gap-1.5">
                <i class="fa-solid ${t.icon || "fa-puzzle-piece"}"></i> ${t.title}</button>`).join("")}
          </div>
          <div id="companionBody"></div>
        </div>
      </div>`;
    document.body.appendChild(modal);

    modal.querySelectorAll("#companionTabs button").forEach(b => b.onclick = () => show(b.dataset.id));

    // Companion Header Button
    const btn = document.createElement("button");
    btn.id = "companionHeaderBtn";
    updateButtonState(btn);
    btn.onclick = open;
    const first = document.querySelector("header button");
    if (first && first.parentNode) {
      first.parentNode.insertBefore(btn, first);
    }
  }

  async function refreshLockStatus() {
    await checkCompanionAccess();
    const btn = document.getElementById("companionHeaderBtn");
    updateButtonState(btn);
  }

  window.addEventListener("load", init);
  return { register, api, refreshLockStatus, checkCompanionAccess };
})();
