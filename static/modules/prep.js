// Pre-trip Preparation Module UI (Person A)
// Plugs into Travel Companion via TravelModules.register("prep", ...)

(function () {
  function escapeHtml(str) {
    if (str === null || str === undefined) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  // Local storage helper for packing list checked state
  function getCheckedItems(tripId) {
    try {
      const saved = localStorage.getItem(`prep_packed_${tripId}`);
      return saved ? JSON.parse(saved) : {};
    } catch (e) {
      return {};
    }
  }

  function setCheckedItem(tripId, itemName, isChecked) {
    try {
      const state = getCheckedItems(tripId);
      if (isChecked) {
        state[itemName] = true;
      } else {
        delete state[itemName];
      }
      localStorage.setItem(`prep_packed_${tripId}`, JSON.stringify(state));
    } catch (e) {
      // Ignore localStorage exceptions
    }
  }

  async function render(container, ctx) {
    if (!ctx || !ctx.tripId) {
      container.innerHTML = `
        <div class="text-center py-8 text-slate-500">
          <i class="fa-solid fa-map-location-dot text-3xl mb-2 text-indigo-400"></i>
          <p class="font-medium">No trip selected</p>
          <p class="text-xs text-slate-400 mt-1">Please plan or choose a trip from the dashboard dropdown above.</p>
        </div>`;
      return;
    }

    container.innerHTML = `
      <div class="flex items-center justify-center py-10 text-slate-400 text-sm">
        <i class="fa-solid fa-circle-notch fa-spin mr-2"></i> Loading pre-trip preparation...
      </div>`;

    try {
      // Parallel fetch for weather, packing, documents, reminders, and safety (Task B8)
      const [weather, packing, documents, remindersData, safetyData] = await Promise.all([
        ctx.api(`/api/prep/${ctx.tripId}/weather`),
        ctx.api(`/api/prep/${ctx.tripId}/packing`),
        ctx.api(`/api/prep/${ctx.tripId}/documents`),
        ctx.api(`/api/prep/${ctx.tripId}/reminders`),
        ctx.api(`/api/prep/${ctx.tripId}/safety`).catch(() => ({ nearby_facilities: [], emergency_numbers: [], permits_and_ticketing: [] })),
      ]);

      const checkedMap = getCheckedItems(ctx.tripId);

      // Group packing items by category
      const packingByCat = {};
      (packing.items || []).forEach(item => {
        const cat = item.category || "General";
        if (!packingByCat[cat]) packingByCat[cat] = [];
        packingByCat[cat].push(item);
      });

      const weatherSourceBadge = weather.source === "open-meteo"
        ? `<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-emerald-100 text-emerald-800">
             <i class="fa-solid fa-cloud-sun mr-1"></i> Live forecast (Open-Meteo)
           </span>`
        : `<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-amber-100 text-amber-800">
             <i class="fa-solid fa-chart-line mr-1"></i> Offline estimate – not a live forecast
           </span>`;

      const luggageBadge = packing.user_luggage_tier === "carry_on"
        ? `<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-indigo-100 text-indigo-800">
             <i class="fa-solid fa-briefcase mr-1"></i> Carry-On Capsule
           </span>`
        : `<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-slate-100 text-slate-700">
             <i class="fa-solid fa-suitcase-rolling mr-1"></i> Standard Checked Luggage
           </span>`;

      container.innerHTML = `
        <div class="space-y-6 text-slate-800 text-sm">

          <!-- 1. WEATHER & CLIMATE CARD -->
          <div class="bg-gradient-to-br from-slate-50 to-indigo-50/40 p-4 rounded-xl border border-slate-200 shadow-sm">
            <div class="flex flex-wrap items-center justify-between gap-2 mb-3">
              <div class="flex items-center gap-2">
                <div class="w-8 h-8 rounded-lg bg-indigo-600 text-white flex items-center justify-center font-bold text-sm">
                  <i class="fa-solid fa-cloud-sun-rain"></i>
                </div>
                <div>
                  <h3 class="font-bold text-base text-slate-900">${escapeHtml(packing.destination_name)} Weather Summary</h3>
                  <p class="text-xs text-slate-500">Scheduled: ${escapeHtml(packing.trip_length_days)} days • Fetched: ${escapeHtml(new Date(weather.fetched_at).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}))}</p>
                </div>
              </div>
              <div>${weatherSourceBadge}</div>
            </div>

            <div class="grid grid-cols-2 sm:grid-cols-4 gap-2.5 pt-1 text-center">
              <div class="bg-white p-2.5 rounded-lg border border-slate-200">
                <span class="block text-xs text-slate-400">Min Temp</span>
                <span class="text-lg font-bold text-slate-800">${escapeHtml(weather.summary.temp_min_c)}°C</span>
              </div>
              <div class="bg-white p-2.5 rounded-lg border border-slate-200">
                <span class="block text-xs text-slate-400">Max Temp</span>
                <span class="text-lg font-bold text-slate-800">${escapeHtml(weather.summary.temp_max_c)}°C</span>
              </div>
              <div class="bg-white p-2.5 rounded-lg border border-slate-200">
                <span class="block text-xs text-slate-400">Peak Wind</span>
                <span class="text-lg font-bold text-slate-800">${escapeHtml(weather.summary.wind_kmh)} <span class="text-xs font-normal">km/h</span></span>
              </div>
              <div class="bg-white p-2.5 rounded-lg border border-slate-200">
                <span class="block text-xs text-slate-400">Precipitation</span>
                <span class="text-lg font-bold ${weather.summary.rain_expected ? 'text-indigo-600' : 'text-slate-800'}">
                  ${weather.summary.rain_expected ? '<i class="fa-solid fa-umbrella text-sm"></i> Rain Likely' : 'Dry / Low Rain'}
                </span>
              </div>
            </div>
          </div>

          <!-- 2. DYNAMIC PACKING LIST -->
          <div class="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
            <div class="flex flex-wrap items-center justify-between gap-2 mb-3 border-b pb-2">
              <div>
                <h3 class="font-bold text-base text-slate-900 flex items-center gap-1.5">
                  <i class="fa-solid fa-clipboard-check text-indigo-600"></i> Personalized Packing List
                </h3>
                <p class="text-xs text-slate-500">
                  Driven by weather, ${escapeHtml(packing.itinerary_status === 'generated' ? 'itinerary activities' : 'default recommendations')}, and personal profile.
                </p>
              </div>
              <div class="flex items-center gap-2">
                ${luggageBadge}
                <span class="text-xs text-slate-400 font-mono">${packing.total_items} items</span>
              </div>
            </div>

            <div class="space-y-4">
              ${Object.keys(packingByCat).map(category => `
                <div>
                  <h4 class="text-xs font-bold uppercase tracking-wider text-slate-500 mb-2 flex items-center gap-1.5">
                    <span class="w-2 h-2 rounded-full bg-indigo-500"></span> ${escapeHtml(category)}
                  </h4>
                  <div class="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    ${packingByCat[category].map(item => {
                      const isChecked = !!checkedMap[item.name];
                      return `
                        <label class="flex items-start gap-2.5 p-2 rounded-lg border border-slate-100 hover:bg-slate-50/80 cursor-pointer transition">
                          <input type="checkbox" data-item="${escapeHtml(item.name)}" class="prep-pack-check mt-1 rounded text-indigo-600 focus:ring-indigo-500" ${isChecked ? 'checked' : ''} />
                          <div class="flex-1 min-w-0">
                            <div class="flex items-center justify-between">
                              <span class="font-medium text-xs text-slate-900 ${isChecked ? 'line-through text-slate-400' : ''}">${escapeHtml(item.name)}</span>
                              ${item.quantity ? `<span class="text-[10px] bg-slate-100 px-1.5 py-0.5 rounded text-slate-600 ml-1 whitespace-nowrap">${escapeHtml(item.quantity)}</span>` : ''}
                            </div>
                            <p class="text-[11px] text-slate-500 mt-0.5 leading-snug">${escapeHtml(item.reason)}</p>
                          </div>
                        </label>`;
                    }).join("")}
                  </div>
                </div>
              `).join("")}
            </div>
          </div>

          <!-- 3. DOCUMENTS & ENTRY CHECKLIST -->
          <div class="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
            <div class="flex items-center justify-between mb-2 border-b pb-2">
              <div>
                <h3 class="font-bold text-base text-slate-900 flex items-center gap-1.5">
                  <i class="fa-solid fa-passport text-indigo-600"></i> Documents & Entry Checklist
                </h3>
                <p class="text-xs text-slate-500">${escapeHtml(documents.disclaimer)}</p>
              </div>
              <span class="text-xs bg-rose-50 text-rose-700 px-2 py-0.5 rounded border border-rose-200 text-[11px] font-medium">
                Verify on official site
              </span>
            </div>

            <div class="space-y-2.5 mt-3">
              ${(documents.items || []).map(doc => `
                <div class="p-2.5 rounded-lg border border-slate-100 bg-slate-50/50 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                  <div class="flex-1">
                    <div class="flex items-center gap-2">
                      <span class="text-xs font-semibold text-slate-900">${escapeHtml(doc.name)}</span>
                      <span class="text-[10px] bg-slate-200/70 text-slate-700 px-1.5 py-0.2 rounded">${escapeHtml(doc.category)}</span>
                      ${doc.official_check_required ? '<span class="text-[10px] text-rose-600 font-medium"><i class="fa-solid fa-triangle-exclamation"></i> Check official</span>' : ''}
                    </div>
                    <p class="text-[11px] text-slate-600 mt-0.5">${escapeHtml(doc.note)}</p>
                  </div>
                </div>
              `).join("")}
            </div>
          </div>

          <!-- 4. TIMED REMINDERS & THOMPSON SAMPLING BANDIT -->
          <div class="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
            <div class="flex flex-wrap items-center justify-between gap-2 mb-2 border-b pb-2">
              <div>
                <h3 class="font-bold text-base text-slate-900 flex items-center gap-1.5">
                  <i class="fa-solid fa-bell text-indigo-600"></i> Timed Reminders
                </h3>
                <p class="text-xs text-slate-500">
                  Prioritized by Thompson Sampling bandit • Alert budget: active max ${remindersData.alert_budget}/day
                </p>
              </div>
              <div class="flex items-center gap-1 text-xs">
                <span class="bg-indigo-50 text-indigo-700 px-2 py-0.5 rounded font-medium border border-indigo-200">
                  ${remindersData.active_count} Active
                </span>
                <span class="bg-slate-100 text-slate-600 px-2 py-0.5 rounded font-medium">
                  ${remindersData.waiting_count} Deferred
                </span>
              </div>
            </div>

            <div class="space-y-2 mt-3">
              ${(remindersData.reminders || []).map(rem => {
                const isDone = rem.status === "done";
                const isDismissed = rem.status === "dismissed";
                return `
                  <div class="p-2.5 rounded-lg border ${rem.is_active ? 'border-indigo-200 bg-indigo-50/20' : 'border-slate-200 bg-slate-50/40'} flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                    <div class="flex-1">
                      <div class="flex items-center gap-1.5 flex-wrap">
                        <span class="text-xs font-semibold ${isDone ? 'line-through text-slate-400' : 'text-slate-900'}">${escapeHtml(rem.text)}</span>
                        <span class="text-[10px] bg-indigo-100 text-indigo-800 px-1.5 py-0.2 rounded font-medium">${escapeHtml(rem.category)}</span>
                        <span class="text-[10px] text-slate-400 font-mono">Due: ${escapeHtml(rem.due_date)}</span>
                        ${rem.is_active ? '<span class="text-[10px] bg-emerald-100 text-emerald-800 px-1 py-0.2 rounded font-semibold">Today\'s Alert</span>' : ''}
                      </div>
                      <div class="text-[10px] text-slate-400 mt-0.5 flex items-center gap-2">
                        <span>Status: <b class="${isDone ? 'text-emerald-600' : isDismissed ? 'text-slate-400' : 'text-indigo-600'}">${escapeHtml(rem.status)}</b></span>
                        <span>Bandit Score (θ): <b class="font-mono text-slate-600">${escapeHtml(rem.bandit_score)}</b></span>
                        <span>Shown: ${escapeHtml(rem.shown_count)}x</span>
                      </div>
                    </div>
                    <div class="flex items-center gap-1 shrink-0">
                      <button data-id="${escapeHtml(rem.id)}" data-action="useful" title="Mark useful (+1 reward)" class="prep-rem-action text-xs px-2 py-1 rounded bg-slate-100 hover:bg-emerald-100 hover:text-emerald-800 text-slate-700 transition">
                        👍 Useful
                      </button>
                      <button data-id="${escapeHtml(rem.id)}" data-action="not_useful" title="Not useful (-1 reward)" class="prep-rem-action text-xs px-2 py-1 rounded bg-slate-100 hover:bg-rose-100 hover:text-rose-800 text-slate-700 transition">
                        👎 Not useful
                      </button>
                      <button data-id="${escapeHtml(rem.id)}" data-action="done" title="Mark completed" class="prep-rem-action text-xs px-2 py-1 rounded bg-slate-100 hover:bg-indigo-100 hover:text-indigo-800 text-slate-700 transition">
                        ✔ Done
                      </button>
                    </div>
                  </div>`;
              }).join("")}
            </div>

            <!-- Bandit Learned State Strip -->
            <div class="mt-4 pt-3 border-t border-slate-100">
              <div class="flex items-center justify-between text-xs mb-2">
                <span class="font-bold text-slate-700">
                  <i class="fa-solid fa-brain text-indigo-500 mr-1"></i> What the Bandit Learned (Beta Posterior)
                </span>
                <span class="text-[10px] text-slate-400 italic">${escapeHtml(remindersData.disclaimer)}</span>
              </div>
              <div class="grid grid-cols-2 sm:grid-cols-6 gap-2">
                ${(remindersData.bandit_state || []).map(b => `
                  <div class="bg-slate-50 p-1.5 rounded border border-slate-200 text-center">
                    <span class="block text-[10px] font-semibold text-slate-600 truncate">${escapeHtml(b.category)}</span>
                    <span class="block text-xs font-mono font-bold text-indigo-600">μ=${escapeHtml(b.mean)}</span>
                    <span class="block text-[9px] text-slate-400">α=${escapeHtml(b.alpha)} β=${escapeHtml(b.beta)}</span>
                  </div>
                `).join("")}
              </div>
            </div>
          </div>

          <!-- 4. SAFETY ESSENTIALS & EMERGENCY SUPPORT (Task B8) -->
          <div class="bg-white p-4 rounded-xl border border-slate-200 shadow-sm space-y-4">
            <div class="flex items-center justify-between pb-2 border-b border-slate-100">
              <div class="flex items-center gap-2">
                <div class="w-8 h-8 rounded-lg bg-rose-600 text-white flex items-center justify-center font-bold text-sm">
                  <i class="fa-solid fa-kit-medical"></i>
                </div>
                <div>
                  <h4 class="font-bold text-slate-800 text-sm">Safety Essentials & Emergency Protocol</h4>
                  <p class="text-xs text-slate-400">Nearby emergency facilities, verified national helplines, and permit advisories.</p>
                </div>
              </div>
              <span class="text-[10px] font-bold px-2 py-0.5 rounded bg-rose-50 text-rose-700 uppercase">Emergency Support</span>
            </div>

            <!-- Nearby Facilities -->
            <div class="space-y-2">
              <h5 class="text-xs font-bold text-slate-700 flex items-center gap-1.5">
                <i class="fa-solid fa-hospital text-rose-500"></i>
                <span>Nearest Healthcare & Financial Services</span>
              </h5>
              <div class="grid grid-cols-1 sm:grid-cols-3 gap-2 text-xs">
                ${(safetyData.nearby_facilities || []).map(f => `
                  <div class="p-2.5 rounded-lg border border-slate-100 bg-slate-50/70">
                    <div class="flex items-center gap-1.5 font-bold text-slate-800 truncate">
                      <i class="fa-solid ${f.type === 'hospital' ? 'fa-square-h text-rose-600' : (f.type === 'pharmacy' ? 'fa-prescription-bottle-medical text-emerald-600' : 'fa-money-bill-wave text-indigo-600')} text-xs"></i>
                      <span class="truncate">${escapeHtml(f.name)}</span>
                    </div>
                    <p class="text-[11px] text-slate-500 mt-1 line-clamp-1">${escapeHtml(f.address || 'Local listing')}</p>
                    ${f.phone ? `<p class="text-[10px] text-indigo-600 font-mono mt-0.5">${escapeHtml(f.phone)}</p>` : ''}
                  </div>
                `).join("")}
              </div>
            </div>

            <!-- Emergency Helplines & Permits -->
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2">
              <!-- Helplines -->
              <div class="p-3 rounded-lg border border-slate-100 bg-slate-50/50 space-y-1.5">
                <h5 class="text-xs font-bold text-slate-700 flex items-center gap-1.5">
                  <i class="fa-solid fa-phone-volume text-indigo-600"></i>
                  <span>Verified National Helplines (Pan-India)</span>
                </h5>
                <div class="space-y-1 text-xs">
                  ${(safetyData.emergency_numbers || []).map(n => `
                    <div class="flex items-center justify-between py-0.5">
                      <span class="text-slate-600 text-[11px]">${escapeHtml(n.service)}</span>
                      <span class="font-mono font-bold text-slate-900 bg-white px-1.5 py-0.2 rounded border border-slate-200 text-xs">${escapeHtml(n.number)}</span>
                    </div>
                  `).join("")}
                </div>
              </div>

              <!-- Permits & Ticketing -->
              <div class="p-3 rounded-lg border border-slate-100 bg-slate-50/50 space-y-1.5">
                <h5 class="text-xs font-bold text-slate-700 flex items-center gap-1.5">
                  <i class="fa-solid fa-passport text-amber-600"></i>
                  <span>Permits & Entry Ticketing Checklist</span>
                </h5>
                <div class="space-y-1 text-[11px] text-slate-600">
                  ${(safetyData.permits_and_ticketing || []).map(p => `
                    <div class="border-b border-slate-100 pb-1 last:border-0">
                      <div class="font-bold text-slate-800">${escapeHtml(p.requirement)}</div>
                      <p class="text-[10px] text-slate-500">${escapeHtml(p.action)}</p>
                    </div>
                  `).join("")}
                </div>
              </div>
            </div>
          </div>

        </div>`;

      // Event listeners for packing checkboxes
      container.querySelectorAll(".prep-pack-check").forEach(chk => {
        chk.addEventListener("change", e => {
          const name = e.target.getAttribute("data-item");
          setCheckedItem(ctx.tripId, name, e.target.checked);
          const labelSpan = e.target.parentElement.querySelector("span");
          if (labelSpan) {
            labelSpan.classList.toggle("line-through", e.target.checked);
            labelSpan.classList.toggle("text-slate-400", e.target.checked);
          }
        });
      });

      // Event listeners for reminder action buttons
      container.querySelectorAll(".prep-rem-action").forEach(btn => {
        btn.addEventListener("click", async e => {
          const remId = e.target.getAttribute("data-id");
          const action = e.target.getAttribute("data-action");
          e.target.disabled = true;
          e.target.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i>`;
          try {
            await ctx.api(`/api/prep/${ctx.tripId}/reminders/${remId}/feedback`, {
              method: "POST",
              body: { feedback: action },
            });
            // Re-render view to reflect updated bandit state and ordering
            await render(container, ctx);
          } catch (err) {
            alert("Feedback failed: " + err.message);
            await render(container, ctx);
          }
        });
      });

    } catch (err) {
      container.innerHTML = `
        <div class="p-4 rounded-xl border border-rose-200 bg-rose-50 text-rose-800 text-sm">
          <p class="font-bold mb-1"><i class="fa-solid fa-triangle-exclamation mr-1"></i> Failed to load Trip Preparation module</p>
          <p class="text-xs text-rose-600">${escapeHtml(err.message || String(err))}</p>
        </div>`;
    }
  }

  // Register in TravelModules loader registry
  if (window.TravelModules && typeof window.TravelModules.register === "function") {
    window.TravelModules.register("prep", { render });
  } else {
    // If loader hasn't executed yet, define fallback registry
    window.TravelModules = window.TravelModules || {};
    window.TravelModules.register = window.TravelModules.register || function (id, mod) {
      window.TravelModules[id] = mod;
    };
    window.TravelModules.register("prep", { render });
  }
})();
