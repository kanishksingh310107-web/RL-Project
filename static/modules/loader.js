// Builds a "Companion" button + modal, one tab per backend module (GET /api/modules).
// Each module ships static/modules/<id>.js which calls TravelModules.register(id, {render(container, ctx)}).
window.TravelModules = (function () {
  const registry = {};
  let tabs = [], activeId = null, trips = [], tripId = null;

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

  async function open() {
    if (!state.currentUser) { alert("Please log in first."); return; }
    document.getElementById("companionModal").classList.remove("hidden");
    trips = await api(`/api/trips/${state.currentUser.user_id}`).catch(() => []);
    const sel = document.getElementById("companionTrip");
    sel.innerHTML = trips.length
      ? trips.map(t => `<option value="${t.id}">${t.destination_name} (${t.start_date} → ${t.end_date})</option>`).join("")
      : `<option value="">No trips yet – plan one from the dashboard</option>`;
    tripId = sel.value || null;
    sel.onchange = () => { tripId = sel.value || null; show(activeId); };
    show(activeId || (tabs[0] && tabs[0].id));
  }

  async function show(id) {
    if (!id) return;
    activeId = id;
    document.querySelectorAll("#companionTabs button").forEach(b => {
      const on = b.dataset.id === id;
      b.classList.toggle("bg-indigo-600", on); b.classList.toggle("text-white", on);
      b.classList.toggle("bg-slate-100", !on);
    });
    const box = document.getElementById("companionBody");
    box.innerHTML = "Loading…";
    if (!registry[id]) {
      await new Promise(res => { const s = document.createElement("script");
        s.src = `/static/modules/${id}.js`; s.onload = res; s.onerror = res; document.body.appendChild(s); });
    }
    box.innerHTML = "";
    if (registry[id]) { try { await registry[id].render(box, ctx()); }
                        catch (e) { box.innerHTML = `<p class="text-rose-600 text-sm">Module error: ${e.message}</p>`; } }
    else box.innerHTML = `<p class="text-slate-500 text-sm">No UI file found: static/modules/${id}.js</p>`;
  }

  async function init() {
    tabs = await api("/api/modules").catch(() => []);
    if (!tabs.length) return;
    const modal = document.createElement("div");
    modal.id = "companionModal";
    modal.className = "hidden fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4";
    modal.innerHTML = `
      <div class="bg-white rounded-2xl shadow-xl w-full max-w-3xl max-h-[90vh] overflow-y-auto p-5">
        <div class="flex justify-between items-center mb-3">
          <h2 class="font-bold text-lg">Travel Companion</h2>
          <button onclick="document.getElementById('companionModal').classList.add('hidden')" class="text-slate-500">✕</button>
        </div>
        <select id="companionTrip" class="border rounded-lg px-2 py-1 text-sm mb-3 w-full"></select>
        <div id="companionTabs" class="flex flex-wrap gap-2 mb-4">
          ${tabs.map(t => `<button data-id="${t.id}" class="text-xs px-3 py-1.5 rounded-lg bg-slate-100">
              <i class="fa-solid ${t.icon || "fa-puzzle-piece"}"></i> ${t.title}</button>`).join("")}
        </div>
        <div id="companionBody"></div>
      </div>`;
    document.body.appendChild(modal);
    modal.querySelectorAll("#companionTabs button").forEach(b => b.onclick = () => show(b.dataset.id));
    const btn = document.createElement("button");
    btn.className = "text-xs bg-indigo-600 hover:bg-indigo-700 text-white font-medium px-3 py-1.5 rounded-lg transition flex items-center gap-1.5";
    btn.innerHTML = `<i class="fa-solid fa-suitcase-rolling"></i><span>Companion</span>`;
    btn.onclick = open;
    const first = document.querySelector("header button");
    first.parentNode.insertBefore(btn, first);
  }
  window.addEventListener("load", init);
  return { register, api };
})();
