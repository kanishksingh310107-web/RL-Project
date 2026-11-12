/* Mandatory history, revisit list, and profile gate owned by A. */
(() => {
  const byId = (id) => document.getElementById(id);
  const root = byId("aProfileRoot");
  const make = (tag, text, cls) => { const el = document.createElement(tag); if (text != null) el.textContent = text; if (cls) el.className = cls; return el; };
  const user = () => (typeof state !== "undefined" ? state.currentUser : null);
  const authHeaders = () => ({ "Content-Type": "application/json" });
  let entries = [];
  let editing = null;

  function showMessage(message, isError = true) {
    const el = byId("aHistoryMessage");
    if (el) { el.textContent = message; el.className = `mb-3 text-sm ${isError ? "text-rose-600" : "text-emerald-700"}`; el.classList.remove("hidden"); }
  }

  function ensurePanel() {
    if (byId("aHistoryPanel")) return;
    const overlay = make("div", null, "hidden fixed inset-0 z-[100] bg-slate-950/50 p-4 flex items-center justify-center");
    overlay.id = "aHistoryPanel";
    const panel = make("section", null, "bg-white rounded-2xl max-w-3xl w-full max-h-[92vh] overflow-y-auto p-6 shadow-2xl");
    const heading = make("div", null, "flex items-start justify-between gap-4 mb-4");
    const title = make("div"); title.append(make("h2", "Your travel history", "text-xl font-bold text-slate-900"), make("p", "This finishes your basic personalization and unlocks trip planning.", "text-sm text-slate-500 mt-1"));
    const close = make("button", "Close", "text-sm text-slate-500 hover:text-slate-900"); close.type = "button"; close.onclick = () => overlay.classList.add("hidden");
    heading.append(title, close);
    const message = make("p", "", "hidden"); message.id = "aHistoryMessage";
    const choice = make("div", null, "flex flex-wrap gap-3 mb-5"); choice.id = "aHistoryChoice";
    const none = make("button", "I have no travel history", "rounded-xl border border-slate-200 px-4 py-2 text-sm hover:border-indigo-400"); none.type = "button";
    none.onclick = () => saveChoice("none");
    const provided = make("button", "Add past trips", "rounded-xl border border-slate-200 px-4 py-2 text-sm hover:border-indigo-400"); provided.type = "button";
    provided.onclick = () => { byId("aHistoryFormWrap").classList.remove("hidden"); };
    choice.append(none, provided);
    const list = make("div", null, "space-y-2 mb-5"); list.id = "aHistoryEntries";
    const formWrap = make("div", null, "hidden border-t border-slate-200 pt-4"); formWrap.id = "aHistoryFormWrap";
    const form = make("form", null, "grid grid-cols-1 sm:grid-cols-2 gap-3"); form.id = "aHistoryForm";
    const field = (id, labelText, type = "text", required = true) => {
      const wrap = make("label", null, "text-xs font-semibold text-slate-700"); wrap.append(document.createTextNode(labelText));
      const input = document.createElement("input"); input.id = id; input.type = type; input.required = required;
      input.className = "mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm font-normal";
      input.maxLength = id === "aHistNotes" ? 1000 : 120; input.setAttribute("aria-describedby", `${id}Error`);
      const err = make("span", "", "hidden text-rose-600 font-normal"); err.id = `${id}Error`;
      wrap.append(input, err); form.append(wrap);
      input.addEventListener("input", () => { err.classList.add("hidden"); if (id === "aHistDestination") input.setCustomValidity(input.value.trim() && !/[\p{L}\p{N}]/u.test(input.value) ? "Enter a destination name, not symbols only." : ""); });
      if (id === "aHistDate") input.max = new Date().toISOString().slice(0, 10);
      return input;
    };
    field("aHistDestination", "Destination *"); field("aHistCity", "City (optional)", "text", false); field("aHistDate", "When did you visit? *", "date");
    const tripWrap = make("label", null, "text-xs font-semibold text-slate-700"); tripWrap.append(document.createTextNode("Who did you travel with? *"));
    const tripSelect = document.createElement("select"); tripSelect.id = "aHistTripType"; tripSelect.required = true; tripSelect.className = "mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm font-normal";
    [["", "Choose one"], ["solo", "Solo"], ["couple", "Couple"], ["friends", "Friends"], ["family", "Family"]].forEach(([v, t]) => { const o = document.createElement("option"); o.value = v; o.textContent = t; tripSelect.append(o); }); tripWrap.append(tripSelect); form.append(tripWrap);
    const ratings = make("fieldset", null, "sm:col-span-2 grid grid-cols-2 sm:grid-cols-4 gap-2"); ratings.append(make("legend", "Rate each from 1 (poor) to 5 (excellent) *", "text-xs font-semibold mb-2"));
    const ratingLabels = { scenery: "Scenery", food: "Food", safety: "Safety", value_for_money: "Value for money", crowds: "Crowds", accessibility: "Accessibility", stay_quality: "Stay quality", overall: "Overall" };
    Object.entries(ratingLabels).forEach(([key, label]) => { const wrap = make("label", null, "text-xs text-slate-600"); wrap.append(document.createTextNode(label)); const sel = document.createElement("select"); sel.dataset.rating = key; sel.required = true; sel.className = "mt-1 block w-full rounded-lg border border-slate-300 px-2 py-2"; [["", "Rate"], [1, "1"], [2, "2"], [3, "3"], [4, "4"], [5, "5"]].forEach(([v,t]) => { const o=document.createElement("option"); o.value=v; o.textContent=t; sel.append(o); }); wrap.append(sel); ratings.append(wrap); }); form.append(ratings);
    const revisitWrap = make("label", null, "text-xs font-semibold text-slate-700"); revisitWrap.append(document.createTextNode("Would you like to revisit? *")); const revisit = document.createElement("select"); revisit.id = "aHistRevisit"; revisit.required = true; revisit.className = "mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm font-normal"; [["", "Choose one"], ["true", "Yes"], ["false", "No"]].forEach(([v,t]) => { const o=document.createElement("option"); o.value=v; o.textContent=t; revisit.append(o); }); revisitWrap.append(revisit); form.append(revisitWrap);
    field("aHistNotes", "Notes (optional)", "text", false);
    const actions = make("div", null, "sm:col-span-2 flex gap-2"); const save = make("button", "Save trip", "rounded-xl bg-indigo-600 px-4 py-2 text-white text-sm font-semibold disabled:opacity-50"); save.type = "submit"; save.id = "aHistorySave"; const cancel = make("button", "Cancel", "rounded-xl border border-slate-300 px-4 py-2 text-sm"); cancel.type = "button"; cancel.onclick = () => { editing = null; form.reset(); formWrap.classList.add("hidden"); }; actions.append(save,cancel); form.append(actions);
    form.addEventListener("invalid", event => {
      const target = event.target;
      const error = target.id ? byId(`${target.id}Error`) : null;
      if (error) { error.textContent = target.validationMessage || "Complete this field."; error.classList.remove("hidden"); }
      else { let errorEl = target.parentElement.querySelector(".aRatingInlineError"); if (!errorEl) { errorEl = make("span", null, "aRatingInlineError block text-rose-600 font-normal"); target.parentElement.append(errorEl); } errorEl.textContent = target.validationMessage || "Choose a rating."; }
    }, true);
    form.addEventListener("input", event => { const error = event.target.id ? byId(`${event.target.id}Error`) : null; error?.classList.add("hidden"); });
    form.onsubmit = submitHistory;
    formWrap.append(form);
    panel.append(heading, message, choice, list, formWrap);
    overlay.append(panel); root.append(overlay);
  }

  async function saveChoice(choice) {
    const button = [...document.querySelectorAll("#aHistoryChoice button")].find(b => b.textContent.includes(choice === "none" ? "no travel history" : "Add past trips"));
    if (button) button.disabled = true;
    try {
      const res = await fetch("/api/profile/history/choice", { method: "POST", headers: authHeaders(), body: JSON.stringify({ choice }) }); const data = await res.json();
      if (!res.ok) throw new Error(data.detail?.detail || data.detail || "Could not save your choice");
      setGateState(!data.profile_complete);
      byId("aHistoryPanel").classList.add("hidden"); await refreshRevisits();
    } catch (err) { showMessage(err.message); } finally { if (button) button.disabled = false; }
  }

  async function submitHistory(event) {
    event.preventDefault(); const form = event.currentTarget; const save = byId("aHistorySave"); save.disabled = true;
    const ratings = {}; form.querySelectorAll("[data-rating]").forEach(el => { ratings[el.dataset.rating] = Number(el.value); });
    const payload = { destination: byId("aHistDestination").value.trim(), city: byId("aHistCity").value.trim() || null, visited_on: byId("aHistDate").value, trip_type: byId("aHistTripType").value, ratings, would_revisit: byId("aHistRevisit").value === "true", notes: byId("aHistNotes").value.trim() || null };
    try {
      const url = editing ? `/api/profile/history/${encodeURIComponent(editing)}` : "/api/profile/history";
      const res = await fetch(url, { method: editing ? "PUT" : "POST", headers: authHeaders(), body: JSON.stringify(payload) }); const data = await res.json();
      if (!res.ok) throw new Error(data.detail?.detail || data.detail || "Could not save this trip");
      editing = null; form.reset(); byId("aHistoryFormWrap").classList.add("hidden"); await loadHistory();
      setGateState(!data.profile_complete);
      if (data.profile_complete) { showMessage("Trip saved. You can add more trips or close this panel.", false); await refreshRevisits(); }
    } catch (err) { showMessage(err.message); } finally { save.disabled = false; }
  }

  function renderEntries() {
    const list = byId("aHistoryEntries"); if (!list) return; list.replaceChildren();
    entries.forEach(item => {
      const card = make("article", null, "flex items-center justify-between gap-3 rounded-xl border border-slate-200 p-3 text-sm");
      const info = make("div"); info.append(make("strong", item.destination, "text-slate-900"), make("p", `${item.visited_on || "Date to update"} · ${item.trip_type || "Trip type to update"}`, "text-xs text-slate-500"));
      const actions = make("div", null, "flex gap-2");
      if (item.source === "manual") { const edit = make("button", "Edit", "text-indigo-600 text-xs font-semibold"); edit.type = "button"; edit.onclick = () => fillEdit(item); actions.append(edit); }
      const remove = make("button", "Remove trip", "text-rose-600 text-xs font-semibold"); remove.type = "button"; remove.onclick = () => deleteHistory(item.id); actions.append(remove); card.append(info, actions); list.append(card);
    });
  }

  function fillEdit(item) {
    if (item.source !== "manual") return;
    editing = item.id; const wrap = byId("aHistoryFormWrap"); wrap.classList.remove("hidden");
    byId("aHistDestination").value = item.destination; byId("aHistCity").value = item.city || ""; byId("aHistDate").value = item.visited_on || ""; byId("aHistTripType").value = item.trip_type || ""; byId("aHistRevisit").value = item.would_revisit == null ? "" : String(item.would_revisit); byId("aHistNotes").value = item.notes || "";
    document.querySelectorAll("[data-rating]").forEach(el => { el.value = item.ratings?.[el.dataset.rating] ?? ""; }); byId("aHistorySave").textContent = "Update trip";
  }

  async function loadHistory() {
    if (!user()) return;
    ensurePanel();
    try { const res = await fetch("/api/profile/history"); if (!res.ok) return; const data = await res.json(); entries = data.entries || []; renderEntries(); }
    catch (_) { showMessage("Could not load history. Check your connection and try again."); }
  }

  async function deleteHistory(id) {
    try { const res = await fetch(`/api/profile/history/${encodeURIComponent(id)}`, { method: "DELETE" }); const data = await res.json(); if (!res.ok) throw new Error(data.detail?.detail || data.detail || "Could not remove this trip"); setGateState(!data.profile_complete); await loadHistory(); await refreshRevisits(); }
    catch (err) { showMessage(err.message); }
  }

  async function removeRevisit(id) {
    try { const res = await fetch(`/api/profile/revisit/${encodeURIComponent(id)}`, { method: "DELETE" }); const data = await res.json(); if (!res.ok) throw new Error(data.detail?.detail || data.detail || "Could not remove this place"); await refreshRevisits(); }
    catch (err) { showMessage(err.message); }
  }

  function renderRevisits() {
    if (!user()) return;
    let section = byId("aRevisitSection");
    const anchor = byId("recommendationsSection"); if (!anchor) return;
    if (!section) { section = make("section", null, "mt-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"); section.id = "aRevisitSection"; anchor.after(section); }
    const titleRow = make("div", null, "mb-3 flex items-center justify-between gap-2");
    titleRow.append(make("h2", "Places to revisit", "text-lg font-bold text-slate-900"));
    const manage = make("button", "Manage travel history", "text-xs font-semibold text-indigo-600 hover:underline"); manage.type = "button"; manage.onclick = openQuestionnaire; titleRow.append(manage); section.replaceChildren(titleRow);
    const revisit = entries.filter(x => x.would_revisit && !x._excluded);
    if (!revisit.length) { section.append(make("p", "Places you marked for a return trip will appear here.", "text-sm text-slate-500")); return; }
    const grid = make("div", null, "grid gap-3 sm:grid-cols-2");
    revisit.forEach(item => {
      const card = make("article", null, "rounded-xl border border-slate-200 p-4"); card.append(make("h3", item.destination, "font-semibold text-slate-900"), make("p", item.visited_on ? `Visited ${item.visited_on}` : "From a completed trip", "text-xs text-slate-500 mt-1"));
      const actions = make("div", null, "mt-3 flex gap-2"); const plan = make("button", "Plan a trip here", "rounded-lg bg-emerald-600 px-3 py-2 text-xs font-semibold text-white"); plan.type = "button"; plan.onclick = () => window.ProfileGate.require(() => { originalToggle?.(); setTimeout(() => window.dispatchEvent(new CustomEvent("trip:prefill-destination", { detail: { destination: item.destination } })), 350); });
      const remove = make("button", "Remove from list", "rounded-lg border border-slate-300 px-3 py-2 text-xs font-semibold text-slate-600"); remove.type = "button"; remove.onclick = () => removeRevisit(item.id); actions.append(plan,remove); card.append(actions); grid.append(card);
    }); section.append(grid);
  }

  async function refreshRevisits() { await loadHistory(); renderRevisits(); }

  async function status() {
    const res = await fetch("/api/profile/status");
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const detail = typeof data.detail === "object" ? data.detail : {};
      const error = new Error(detail.detail || data.detail || "Could not check your profile. Please try again.");
      error.code = detail.code;
      error.status = res.status;
      throw error;
    }
    return data;
  }

  function handleAuthFailure() {
    localStorage.removeItem("rl_travel_user");
    if (typeof state !== "undefined") state.currentUser = null;
    if (typeof updateNavUser === "function") updateNavUser();
    if (typeof showView === "function") showView("auth");
    const authMessage = byId("authFormMessage");
    if (authMessage) { authMessage.textContent = "Your sign-in session has expired. Sign in again, then try planning your trip."; authMessage.classList.remove("hidden"); }
  }
  let gateCheckInFlight = null;

  async function openQuestionnaire() {
    ensurePanel(); await loadHistory(); byId("aHistoryPanel").classList.remove("hidden");
    const choice = byId("aHistoryChoice");
    choice.querySelectorAll("button").forEach(b => b.classList.remove("hidden"));
    const state = await fetch("/api/profile/history").then(r => r.ok ? r.json() : null).catch(() => null);
    if (state?.history_choice === "provided") choice.querySelector("button:last-child").textContent = "Add another past trip";
    if (state?.history_choice === "none") choice.querySelector("button:last-child").textContent = "Add past trips instead";
  }

  function setGateState(incomplete) {
    const targets = [byId("dashboardView"), byId("itineraryPlannerSection")].filter(Boolean);
    targets.forEach(target => {
      let notice = target.querySelector(":scope > #aProfileGateNotice");
      if (incomplete && !notice) {
        notice = make("div", null, "mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4");
        notice.id = "aProfileGateNotice";
        notice.append(make("p", "Complete your basic profile and travel history to unlock trip planning.", "text-sm text-amber-900"));
        const button = make("button", "Complete profile", "rounded-lg bg-indigo-600 px-3 py-2 text-xs font-semibold text-white"); button.type = "button"; button.onclick = openQuestionnaire; notice.append(button);
        target.prepend(notice);
      } else if (!incomplete && notice) notice.remove();
    });
    document.querySelectorAll('button[onclick*="toggleTripFormModal"]').forEach(button => {
      if (incomplete && !button.disabled) { button.dataset.aGateDisabled = "true"; button.disabled = true; button.title = "Complete your profile to plan a trip"; button.classList.add("opacity-50", "cursor-not-allowed"); }
      else if (!incomplete && button.dataset.aGateDisabled === "true") { button.disabled = false; delete button.dataset.aGateDisabled; button.removeAttribute("title"); button.classList.remove("opacity-50", "cursor-not-allowed"); }
    });
  }

  window.ProfileGate = {
    async require(callback) {
      try { const s = await status(); if (s.profile_complete) { callback?.(); return true; } showMessage("Finish the required profile and travel history to plan a trip.", false); await openQuestionnaire(); return false; }
      catch (error) {
        const authFailed = error.code === "AUTH_REQUIRED" || error.code === "SESSION_EXPIRED";
        if (authFailed) {
          handleAuthFailure();
        } else showMessage(error.message || "Could not check your profile. Please try again.");
        return false;
      }
    },
    async checkAndPrompt() {
      if (!user() || gateCheckInFlight) return gateCheckInFlight;
      gateCheckInFlight = (async () => {
        try { const s = await status(); setGateState(!s.profile_complete); if (!s.profile_complete) await openQuestionnaire(); else { await refreshRevisits(); } }
        catch (error) { if (error.code === "AUTH_REQUIRED" || error.code === "SESSION_EXPIRED") handleAuthFailure(); }
      })();
      try { await gateCheckInFlight; } finally { gateCheckInFlight = null; }
    }
  };

  const originalToggle = window.toggleTripFormModal;
  if (typeof originalToggle === "function") window.toggleTripFormModal = function (...args) {
    window.ProfileGate.require(() => originalToggle.apply(this, args));
  };

  window.addEventListener("trip:prefill-destination", event => {
    const destination = String(event.detail?.destination || "").trim();
    const input = byId("tripCitySearchInput");
    if (!destination || !input) return;
    input.value = destination;
    if (typeof handleCitySearchInput === "function") handleCitySearchInput(destination);
    const normalize = value => String(value || "").toLocaleLowerCase().replace(/[^\p{L}\p{N}]+/gu, " ").trim();
    const wanted = normalize(destination);
    const known = typeof FEATURED_DESTINATION_COORDS !== "undefined" && Object.values(FEATURED_DESTINATION_COORDS).find(loc => normalize(loc.name) === wanted || normalize(loc.city) === wanted);
    if (known && typeof selectGeocodedCity === "function") {
      selectGeocodedCity(known, "curated").catch(() => {});
      return;
    }
    const baseline = typeof _lastCitySearchResults !== "undefined" ? _lastCitySearchResults : null;
    let attempts = 0;
    const selectMatch = () => {
      attempts += 1;
      const results = typeof _lastCitySearchResults !== "undefined" ? _lastCitySearchResults : [];
      const index = results.findIndex(loc => [loc.name, loc.city, loc.formatted].some(value => normalize(value) === wanted));
      if (index >= 0 && typeof selectSearchedLocationIndex === "function") selectSearchedLocationIndex(index).catch(() => {});
      else if (attempts < 20 && (results === baseline || !results.length)) setTimeout(selectMatch, 250);
      else input.focus();
    };
    setTimeout(selectMatch, 500);
  });

  const originalLoadProfile = window.loadUserProfile;
  if (typeof originalLoadProfile === "function") window.loadUserProfile = async function (...args) {
    const result = await originalLoadProfile.apply(this, args);
    setTimeout(() => window.ProfileGate.checkAndPrompt(), 200);
    return result;
  };

  // Existing basic-profile save remains in app.js; refresh the A panel after it succeeds.
  const baseFetch = window.fetch;
  window.fetch = async (input, init) => {
    const result = await baseFetch(input, init);
    if (typeof input === "string" && /^\/api\/profile\/[^/]+$/.test(input) && init?.method === "POST" && result.ok) {
      setTimeout(() => window.ProfileGate.checkAndPrompt(), 250);
    }
    return result;
  };
  window.addEventListener("load", () => setTimeout(() => {
  const byId = (id) => document.getElementById(id); if (user()) window.ProfileGate.checkAndPrompt(); }, 500));
})();
