/**
 * Person B Frontend: During-Trip Support and Post-Trip Learning Module
 * Registered via TravelModules.register("live", ...)
 */

(function () {
  let activeSubtab = "during"; // "during" or "post"
  let currentDay = 1;
  let todayData = null;
  let tripState = null;
  let replanTargetAct = null;
  let replanCondition = "";
  let replanCandidates = [];

  // Star rating helper
  function renderStars(rating, onSelect = null) {
    let html = '<div class="flex items-center gap-1">';
    for (let i = 1; i <= 5; i++) {
      const active = i <= rating;
      const color = active ? "text-amber-400" : "text-slate-300";
      if (onSelect) {
        html += `<button type="button" onclick="${onSelect}(${i})" class="${color} hover:text-amber-400 text-lg transition focus:outline-none"><i class="fa-solid fa-star"></i></button>`;
      } else {
        html += `<span class="${color} text-sm"><i class="fa-solid fa-star"></i></span>`;
      }
    }
    html += '</div>';
    return html;
  }

  // Category label helper
  function formatCategory(cat) {
    if (!cat) return "Sightseeing";
    return cat.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
  }

  // Status badge styling helper
  function getStatusBadge(status) {
    const s = (status || "upcoming").toLowerCase();
    switch (s) {
      case "completed":
        return `<span class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800"><i class="fa-solid fa-circle-check"></i> Completed</span>`;
      case "in_progress":
        return `<span class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-blue-100 text-blue-800"><i class="fa-solid fa-spinner fa-spin"></i> In Progress</span>`;
      case "delayed":
        return `<span class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-100 text-amber-800"><i class="fa-solid fa-clock"></i> Delayed</span>`;
      case "skipped":
        return `<span class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-rose-100 text-rose-800"><i class="fa-solid fa-forward-step"></i> Skipped</span>`;
      default:
        return `<span class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-700"><i class="fa-solid fa-hourglass-start"></i> Upcoming</span>`;
    }
  }

  // Main render entrypoint
  async function render(container, ctx) {
    if (!ctx.tripId) {
      container.innerHTML = `
        <div class="text-center py-10 bg-slate-50 rounded-xl border border-dashed border-slate-200">
          <i class="fa-solid fa-compass text-slate-400 text-3xl mb-3"></i>
          <h3 class="font-semibold text-slate-700">No Trip Selected</h3>
          <p class="text-xs text-slate-500 mt-1">Please plan or select an active trip in the companion dropdown above.</p>
        </div>
      `;
      return;
    }

    container.innerHTML = `<div class="py-8 text-center text-sm text-slate-500"><i class="fa-solid fa-spinner fa-spin mr-2"></i>Loading live companion data…</div>`;

    try {
      tripState = await ctx.api(`/api/live/${ctx.tripId}/state?user_id=${ctx.userId}`).catch(() => ({
        is_completed: 0, current_day: 1
      }));
      todayData = await ctx.api(`/api/live/${ctx.tripId}/today?day=${currentDay}&user_id=${ctx.userId}`).catch(() => null);
    } catch (err) {
      container.innerHTML = `<div class="p-4 bg-rose-50 text-rose-700 rounded-lg text-sm">Failed to load live trip: ${err.message}</div>`;
      return;
    }

    if (!todayData || !todayData.activities) {
      container.innerHTML = `
        <div class="text-center py-10 bg-slate-50 rounded-xl border border-dashed border-slate-200">
          <i class="fa-solid fa-map-location-dot text-slate-400 text-3xl mb-3"></i>
          <h3 class="font-semibold text-slate-700">No Pre-Trip Itinerary Found</h3>
          <p class="text-xs text-slate-500 mt-1">Generate a day-by-day itinerary from the dashboard before using live during-trip support.</p>
        </div>
      `;
      return;
    }

    renderView(container, ctx);
  }

  function renderView(container, ctx) {
    const totalDays = todayData.total_days || 1;
    const isCompleted = tripState && tripState.is_completed === 1;

    container.innerHTML = `
      <!-- Subtab Navigation -->
      <div class="flex border-b border-slate-200 mb-4 justify-between items-center">
        <div class="flex gap-2">
          <button id="liveTabDuring" class="px-3 py-2 text-xs font-semibold border-b-2 ${activeSubtab === "during" ? "border-indigo-600 text-indigo-600" : "border-transparent text-slate-500 hover:text-slate-700"} flex items-center gap-1.5 transition">
            <i class="fa-solid fa-compass"></i>
            <span>During-Trip Support</span>
          </button>
          <button id="liveTabPost" class="px-3 py-2 text-xs font-semibold border-b-2 ${activeSubtab === "post" ? "border-indigo-600 text-indigo-600" : "border-transparent text-slate-500 hover:text-slate-700"} flex items-center gap-1.5 transition">
            <i class="fa-solid fa-graduation-cap"></i>
            <span>Post-Trip Evaluation & Learning</span>
            ${isCompleted ? '<span class="w-2 h-2 rounded-full bg-emerald-500 inline-block ml-1"></span>' : ''}
          </button>
        </div>

        <div class="flex items-center gap-2">
          ${!isCompleted ? `
            <button id="btnCompleteTripHeader" class="text-xs bg-slate-100 hover:bg-slate-200 text-slate-700 font-medium px-2.5 py-1 rounded transition flex items-center gap-1">
              <i class="fa-solid fa-flag-checkered text-slate-500"></i> Mark Trip Complete
            </button>
          ` : `
            <span class="text-[11px] font-semibold bg-emerald-100 text-emerald-800 px-2 py-0.5 rounded-full flex items-center gap-1">
              <i class="fa-solid fa-check"></i> Trip Completed
            </span>
          `}
        </div>
      </div>

      <!-- Main Body Container -->
      <div id="liveSubtabContent"></div>
    `;

    document.getElementById("liveTabDuring").onclick = () => { activeSubtab = "during"; renderView(container, ctx); };
    document.getElementById("liveTabPost").onclick = () => { activeSubtab = "post"; renderView(container, ctx); };

    const completeBtn = document.getElementById("btnCompleteTripHeader");
    if (completeBtn) {
      completeBtn.onclick = async () => {
        if (!confirm("Are you sure you want to mark this trip as completed? This will finalize execution and unlock post-trip feedback.")) return;
        try {
          await ctx.api(`/api/live/${ctx.tripId}/complete`, { method: "POST", body: { user_id: ctx.userId } });
          tripState.is_completed = 1;
          activeSubtab = "post";
          render(container, ctx);
        } catch (e) {
          alert("Error completing trip: " + e.message);
        }
      };
    }

    const contentBox = document.getElementById("liveSubtabContent");
    if (activeSubtab === "during") {
      renderDuringTrip(contentBox, ctx, container);
    } else {
      renderPostTrip(contentBox, ctx, container);
    }
  }

  // -------------------------------------------------------------------------
  // SUBTAB 1: DURING TRIP SUPPORT
  // -------------------------------------------------------------------------
  function renderDuringTrip(box, ctx, mainContainer) {
    const totalDays = todayData.total_days || 1;
    const activities = todayData.activities || [];
    const conditions = todayData.conditions || [];

    // Collect all active alerts across activities
    let allAlerts = [];
    activities.forEach(a => {
      if (a.alerts && a.alerts.length) {
        allAlerts.push(...a.alerts);
      }
    });

    let daysPills = "";
    for (let d = 1; d <= totalDays; d++) {
      const active = d === currentDay;
      daysPills += `
        <button data-day="${d}" class="live-day-btn text-xs font-medium px-3 py-1.5 rounded-lg transition ${active ? "bg-indigo-600 text-white shadow-sm" : "bg-slate-100 text-slate-700 hover:bg-slate-200"}">
          Day ${d}
        </button>
      `;
    }

    box.innerHTML = `
      <!-- Day Selector & Simulation Banner -->
      <div class="flex flex-wrap items-center justify-between gap-2 mb-3 bg-slate-50 p-2.5 rounded-xl border border-slate-200">
        <div class="flex items-center gap-1.5 flex-wrap">
          <span class="text-xs font-semibold text-slate-500 mr-1"><i class="fa-solid fa-calendar-day mr-1"></i>Day:</span>
          ${daysPills}
        </div>
        <div class="flex items-center gap-1.5 text-[11px] font-semibold text-amber-800 bg-amber-100/90 px-2 py-0.5 rounded-md">
          <i class="fa-solid fa-flask"></i>
          <span>SIMULATED DEMO ENVIRONMENT</span>
        </div>
      </div>

      <!-- Simulation Trigger Panel -->
      <div class="bg-gradient-to-r from-amber-50 to-orange-50 border border-amber-200 rounded-xl p-3 mb-4">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div>
            <div class="text-xs font-bold text-amber-900 flex items-center gap-1.5">
              <i class="fa-solid fa-cloud-bolt text-amber-600"></i>
              <span>Simulate Travel Conditions (Demonstration)</span>
            </div>
            <p class="text-[11px] text-amber-700 mt-0.5">Inject simulated environmental disruptions to test proactive alerts and targeted replanning.</p>
          </div>
          <div class="flex items-center gap-2">
            <select id="simConditionSelect" class="border border-amber-300 rounded-lg px-2.5 py-1 text-xs bg-white text-slate-800 focus:outline-none focus:ring-1 focus:ring-amber-500">
              <option value="heavy_rain">🌧️ Heavy Rain (Outdoor Disruption)</option>
              <option value="extreme_heat">☀️ Extreme Heat (Midday Advisory)</option>
              <option value="closure">⛔ Attraction Closure (Venue Unavailable)</option>
              <option value="traffic_delay">🚗 Transit Congestion (Traffic Delay)</option>
              <option value="strike">🚫 Transit Strike (Route Disrupted)</option>
              <option value="fatigue">🛌 Traveller Fatigue (Pacing Advisory)</option>
              <option value="unexpected_crowding">👥 Visitor Surge (Crowd Alert)</option>
            </select>
            <button id="btnSimulateCondition" class="bg-amber-600 hover:bg-amber-700 text-white text-xs font-medium px-3 py-1 rounded-lg transition flex items-center gap-1">
              <i class="fa-solid fa-play text-[10px]"></i> Simulate
            </button>
          </div>
        </div>
      </div>

      <!-- Active Alerts Section -->
      ${allAlerts.length ? `
        <div class="mb-4 space-y-2">
          ${allAlerts.map(alert => `
            <div class="p-3 rounded-xl border ${alert.severity === 'critical' ? 'bg-rose-50 border-rose-200' : 'bg-amber-50 border-amber-200'} flex items-start justify-between gap-3 shadow-xs">
              <div class="flex items-start gap-2.5">
                <i class="fa-solid ${alert.severity === 'critical' ? 'fa-circle-exclamation text-rose-500' : 'fa-triangle-exclamation text-amber-500'} text-base mt-0.5"></i>
                <div>
                  <div class="flex items-center gap-2">
                    <span class="text-xs font-bold text-slate-800">${alert.title}</span>
                    <span class="text-[10px] uppercase font-bold px-1.5 py-0.2 rounded ${alert.severity === 'critical' ? 'bg-rose-200 text-rose-800' : 'bg-amber-200 text-amber-800'}">${alert.severity}</span>
                  </div>
                  <p class="text-xs text-slate-600 mt-0.5">${alert.message}</p>
                  <p class="text-[11px] text-indigo-700 font-medium mt-1"><i class="fa-solid fa-lightbulb mr-1"></i>Recommendation: ${alert.suggested_action}</p>
                </div>
              </div>
              <div class="flex items-center gap-1.5 shrink-0">
                <button data-act-id="${alert.activity_id}" data-condition="${alert.title}" class="btn-alert-replan bg-white border border-slate-300 hover:border-indigo-500 hover:text-indigo-600 text-xs px-2.5 py-1 rounded-lg font-medium transition flex items-center gap-1 shadow-2xs">
                  <i class="fa-solid fa-arrows-rotate text-indigo-500 text-[10px]"></i> Replan
                </button>
                <button data-alert-id="${alert.id}" class="btn-dismiss-alert text-slate-400 hover:text-slate-600 p-1 rounded" title="Dismiss Alert">
                  <i class="fa-solid fa-xmark text-sm"></i>
                </button>
              </div>
            </div>
          `).join("")}
        </div>
      ` : ''}

      <!-- Today's Schedule Timeline -->
      <div class="space-y-3" id="todayActivityList">
        ${activities.length ? activities.map((act, idx) => `
          <div class="bg-white border border-slate-200 hover:border-slate-300 rounded-xl p-3.5 shadow-2xs transition">
            <div class="flex items-start justify-between gap-3">
              <div class="flex items-start gap-3">
                <div class="w-8 h-8 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center font-bold text-xs shrink-0 mt-0.5">
                  ${idx + 1}
                </div>
                <div>
                  <div class="flex items-center gap-2 flex-wrap">
                    <h4 class="font-bold text-sm text-slate-900">${act.title}</h4>
                    <span class="text-[10px] font-medium bg-slate-100 text-slate-600 px-2 py-0.5 rounded">${act.time_slot ? act.time_slot.toUpperCase() : 'AFTERNOON'}</span>
                    <span class="text-[10px] font-medium bg-indigo-50 text-indigo-700 px-2 py-0.5 rounded">${formatCategory(act.category)}</span>
                    ${getStatusBadge(act.status)}
                  </div>
                  <p class="text-xs text-slate-500 mt-1 flex items-center gap-3">
                    <span><i class="fa-solid fa-location-dot text-slate-400 mr-1"></i>${act.neighborhood || "Kyoto Area"}</span>
                    <span><i class="fa-solid fa-clock text-slate-400 mr-1"></i>${act.duration_minutes || 90} mins</span>
                    <span><i class="fa-solid fa-tag text-slate-400 mr-1"></i>$${act.cost_estimate || 0}</span>
                  </p>
                  ${act.why_it_suits ? `
                    <p class="text-[11px] text-slate-500 italic mt-1.5 bg-slate-50 p-1.5 rounded border border-slate-100">
                      <i class="fa-solid fa-sparkles text-indigo-500 mr-1"></i>${act.why_it_suits}
                    </p>
                  ` : ''}
                </div>
              </div>

              <!-- Status & Replan Actions -->
              <div class="flex flex-col items-end gap-2 shrink-0">
                <div class="flex items-center gap-1">
                  <select data-act-id="${act.activity_id}" class="sel-act-status border border-slate-200 rounded-lg px-2 py-1 text-xs bg-slate-50 text-slate-700 hover:bg-white focus:outline-none focus:ring-1 focus:ring-indigo-500">
                    <option value="upcoming" ${act.status === 'upcoming' ? 'selected' : ''}>Upcoming</option>
                    <option value="in_progress" ${act.status === 'in_progress' ? 'selected' : ''}>In Progress</option>
                    <option value="completed" ${act.status === 'completed' ? 'selected' : ''}>Completed</option>
                    <option value="skipped" ${act.status === 'skipped' ? 'selected' : ''}>Skipped</option>
                    <option value="delayed" ${act.status === 'delayed' ? 'selected' : ''}>Delayed</option>
                  </select>
                  <button data-act-id="${act.activity_id}" class="btn-act-replan bg-slate-50 hover:bg-indigo-50 border border-slate-200 hover:border-indigo-200 text-slate-700 hover:text-indigo-700 text-xs px-2.5 py-1 rounded-lg font-medium transition flex items-center gap-1">
                    <i class="fa-solid fa-arrows-rotate text-[10px]"></i>
                    <span>Replan</span>
                  </button>
                </div>
              </div>
            </div>
          </div>
        `).join("") : `
          <div class="text-center py-8 text-xs text-slate-400">No activities scheduled for Day ${currentDay}.</div>
        `}
      </div>

      <!-- Replan Alternatives Modal (Hidden by Default) -->
      <div id="liveReplanModal" class="hidden fixed inset-0 z-60 bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4">
        <div class="bg-white rounded-2xl shadow-xl w-full max-w-lg p-5 max-h-[85vh] overflow-y-auto">
          <div class="flex justify-between items-center mb-3">
            <h3 class="font-bold text-base text-slate-800 flex items-center gap-2">
              <i class="fa-solid fa-arrows-rotate text-indigo-600"></i>
              <span>Targeted Activity Replanning</span>
            </h3>
            <button id="btnCloseReplanModal" class="text-slate-400 hover:text-slate-600 text-lg">✕</button>
          </div>
          <div class="p-2.5 bg-indigo-50 rounded-lg border border-indigo-100 text-xs text-indigo-800 mb-3 flex items-start gap-2">
            <i class="fa-solid fa-circle-info text-indigo-500 mt-0.5"></i>
            <div>
              <span class="font-semibold">Targeted Replacement Guarantee:</span> Only this specific activity will be replaced. All other activities and time slots in your trip remain strictly untouched.
            </div>
          </div>
          <div id="replanAlternativesList" class="space-y-2 mb-4"></div>
        </div>
      </div>
    `;

    // Bind Day Switchers
    box.querySelectorAll(".live-day-btn").forEach(btn => {
      btn.onclick = async () => {
        currentDay = parseInt(btn.dataset.day);
        todayData = await ctx.api(`/api/live/${ctx.tripId}/today?day=${currentDay}&user_id=${ctx.userId}`);
        renderDuringTrip(box, ctx, mainContainer);
      };
    });

    // Bind Condition Simulator
    const simBtn = document.getElementById("btnSimulateCondition");
    if (simBtn) {
      simBtn.onclick = async () => {
        const cType = document.getElementById("simConditionSelect").value;
        simBtn.disabled = true;
        simBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin text-[10px]"></i> Simulating…`;
        try {
          const simRes = await ctx.api(`/api/live/${ctx.tripId}/simulate`, {
            method: "POST",
            body: { condition_type: cType, day_number: currentDay, user_id: ctx.userId }
          });
          todayData = await ctx.api(`/api/live/${ctx.tripId}/today?day=${currentDay}&user_id=${ctx.userId}`);
          renderDuringTrip(box, ctx, mainContainer);
        } catch (e) {
          alert("Simulation error: " + e.message);
          simBtn.disabled = false;
          simBtn.innerHTML = `<i class="fa-solid fa-play text-[10px]"></i> Simulate`;
        }
      };
    }

    // Bind Alert Dismissal
    box.querySelectorAll(".btn-dismiss-alert").forEach(btn => {
      btn.onclick = async () => {
        const alertId = btn.dataset.alertId;
        try {
          await ctx.api(`/api/live/${ctx.tripId}/alerts/${alertId}/dismiss?user_id=${ctx.userId}`, { method: "POST" });
          todayData = await ctx.api(`/api/live/${ctx.tripId}/today?day=${currentDay}&user_id=${ctx.userId}`);
          renderDuringTrip(box, ctx, mainContainer);
        } catch (e) {
          alert("Error dismissing alert: " + e.message);
        }
      };
    });

    // Bind Activity Status Dropdowns
    box.querySelectorAll(".sel-act-status").forEach(sel => {
      sel.onchange = async () => {
        const actId = sel.dataset.actId;
        const newStatus = sel.value;
        try {
          await ctx.api(`/api/live/${ctx.tripId}/activity/${actId}/status`, {
            method: "POST",
            body: { status: newStatus, user_id: ctx.userId }
          });
          todayData = await ctx.api(`/api/live/${ctx.tripId}/today?day=${currentDay}&user_id=${ctx.userId}`);
          renderDuringTrip(box, ctx, mainContainer);
        } catch (e) {
          alert("Error updating status: " + e.message);
        }
      };
    });

    // Bind Replan Buttons
    const openReplan = async (actId, conditionLabel = "") => {
      replanTargetAct = actId;
      replanCondition = conditionLabel;
      const modal = document.getElementById("liveReplanModal");
      const list = document.getElementById("replanAlternativesList");
      modal.classList.remove("hidden");
      list.innerHTML = `<div class="py-6 text-center text-xs text-slate-500"><i class="fa-solid fa-spinner fa-spin mr-2"></i>Finding suitable alternatives via LinUCB…</div>`;

      try {
        const condParam = conditionLabel.includes("Rain") ? "heavy_rain" : (conditionLabel.includes("Fatigue") ? "fatigue" : "");
        const res = await ctx.api(`/api/live/${ctx.tripId}/replan?activity_id=${actId}&condition=${condParam}&user_id=${ctx.userId}`);
        const alts = res.alternatives || [];
        if (!alts.length) {
          list.innerHTML = `<div class="p-4 text-center text-xs text-slate-500">No additional candidates found for this slot.</div>`;
          return;
        }

        list.innerHTML = alts.map(a => `
          <div class="border border-slate-200 hover:border-indigo-300 rounded-xl p-3 transition bg-white shadow-2xs">
            <div class="flex items-start justify-between gap-2">
              <div>
                <h5 class="font-bold text-sm text-slate-900">${a.name}</h5>
                <p class="text-[11px] text-slate-500 mt-0.5">
                  <span>${formatCategory(a.category)}</span> • <span>${a.neighborhood || "Kyoto"}</span> • <span>$${a.estimated_cost || 0}</span>
                </p>
                <p class="text-[11px] text-emerald-700 font-medium mt-1">
                  <i class="fa-solid fa-check mr-1"></i>${a.replan_suitability_reason || "Suitable replacement"}
                </p>
              </div>
              <button data-rep-id="${a.id}" class="btn-confirm-swap bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold px-3 py-1.5 rounded-lg transition shrink-0">
                Select
              </button>
            </div>
          </div>
        `).join("");

        list.querySelectorAll(".btn-confirm-swap").forEach(btn => {
          btn.onclick = async () => {
            const repId = btn.dataset.repId;
            if (!confirm("Confirm replacement? Only this activity will be replaced. Remaining itinerary is preserved.")) return;
            btn.disabled = true;
            btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin text-[10px]"></i>`;
            try {
              await ctx.api(`/api/live/${ctx.tripId}/replan`, {
                method: "POST",
                body: {
                  activity_id: replanTargetAct,
                  replacement_activity_id: repId,
                  reason: replanCondition || "Traveller modification",
                  is_trip_specific: true,
                  user_id: ctx.userId
                }
              });
              modal.classList.add("hidden");
              todayData = await ctx.api(`/api/live/${ctx.tripId}/today?day=${currentDay}&user_id=${ctx.userId}`);
              renderDuringTrip(box, ctx, mainContainer);
            } catch (e) {
              alert("Error replanning: " + e.message);
              btn.disabled = false;
              btn.textContent = "Select";
            }
          };
        });
      } catch (err) {
        list.innerHTML = `<div class="p-3 bg-rose-50 text-rose-700 text-xs rounded-lg">${err.message}</div>`;
      }
    };

    box.querySelectorAll(".btn-act-replan").forEach(btn => {
      btn.onclick = () => openReplan(btn.dataset.actId, "");
    });
    box.querySelectorAll(".btn-alert-replan").forEach(btn => {
      btn.onclick = () => openReplan(btn.dataset.actId, btn.dataset.condition);
    });

    const closeReplan = document.getElementById("btnCloseReplanModal");
    if (closeReplan) {
      closeReplan.onclick = () => document.getElementById("liveReplanModal").classList.add("hidden");
    }
  }

  // -------------------------------------------------------------------------
  // SUBTAB 2: POST TRIP EVALUATION & LINUCB LEARNING
  // -------------------------------------------------------------------------
  async function renderPostTrip(box, ctx, mainContainer) {
    box.innerHTML = `<div class="py-8 text-center text-xs text-slate-500"><i class="fa-solid fa-spinner fa-spin mr-2"></i>Loading post-trip review…</div>`;

    let postripData = null;
    let learningSummary = null;

    try {
      postripData = await ctx.api(`/api/live/${ctx.tripId}/postrip?user_id=${ctx.userId}`).catch(() => ({ has_feedback: false }));
      learningSummary = await ctx.api(`/api/live/${ctx.userId}/learning-summary?caller_user_id=${ctx.userId}`).catch(() => null);
    } catch (e) {
      // Continue with fallbacks
    }

    const isCompleted = tripState && tripState.is_completed === 1;

    // State 1: Trip not yet completed
    if (!isCompleted) {
      box.innerHTML = `
        <div class="text-center py-10 px-4 bg-slate-50 rounded-2xl border border-dashed border-slate-200">
          <div class="w-12 h-12 rounded-full bg-indigo-50 text-indigo-600 flex items-center justify-center mx-auto mb-3 text-lg">
            <i class="fa-solid fa-plane-arrival"></i>
          </div>
          <h3 class="font-bold text-base text-slate-800">Trip Currently In Progress</h3>
          <p class="text-xs text-slate-500 max-w-md mx-auto mt-1 mb-4">
            Post-trip evaluation and Reinforcement Learning policy updates unlock once your journey is complete.
          </p>
          <button id="btnMarkCompleteFromTab" class="bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-xs px-4 py-2 rounded-xl transition inline-flex items-center gap-2 shadow-xs">
            <i class="fa-solid fa-flag-checkered"></i> Mark Trip as Completed
          </button>
        </div>
      `;
      const btn = document.getElementById("btnMarkCompleteFromTab");
      if (btn) {
        btn.onclick = async () => {
          if (!confirm("Mark this trip as completed?")) return;
          try {
            await ctx.api(`/api/live/${ctx.tripId}/complete`, { method: "POST", body: { user_id: ctx.userId } });
            tripState.is_completed = 1;
            renderPostTrip(box, ctx, mainContainer);
          } catch (e) {
            alert("Error: " + e.message);
          }
        };
      }
      return;
    }

    // State 2: Trip Completed & Feedback Already Submitted
    if (postripData && postripData.has_feedback) {
      renderCompletedFeedbackView(box, postripData, learningSummary, ctx);
      return;
    }

    // State 3: Trip Completed, Feedback Not Yet Submitted -> Questionnaire Form
    renderFeedbackQuestionnaire(box, ctx, mainContainer, learningSummary);
  }

  function renderCompletedFeedbackView(box, postripData, learningSummary, ctx) {
    const rev = postripData.review || {};
    const evals = postripData.activity_evaluations || [];

    box.innerHTML = `
      <div class="bg-emerald-50 border border-emerald-200 rounded-xl p-3.5 mb-4 flex items-center justify-between gap-3">
        <div class="flex items-center gap-2.5">
          <i class="fa-solid fa-circle-check text-emerald-600 text-xl"></i>
          <div>
            <h4 class="font-bold text-sm text-emerald-900">Post-Trip Feedback Submitted</h4>
            <p class="text-xs text-emerald-700">Thank you! Your ratings have permanently updated your personal LinUCB recommendation policy.</p>
          </div>
        </div>
        <div class="text-right">
          <span class="text-xs font-semibold text-emerald-800">Overall:</span>
          ${renderStars(Math.round(rev.overall_satisfaction || 5))}
        </div>
      </div>

      <!-- Activity Evaluations List -->
      <div class="bg-white border border-slate-200 rounded-xl p-4 mb-4 shadow-2xs">
        <h4 class="font-bold text-sm text-slate-800 mb-2.5 flex items-center gap-2">
          <i class="fa-solid fa-list-check text-indigo-600"></i> Evaluated Activities (${evals.length})
        </h4>
        <div class="space-y-2">
          ${evals.map(e => `
            <div class="flex items-center justify-between text-xs py-2 border-b border-slate-100 last:border-0">
              <div>
                <span class="font-semibold text-slate-800">${e.activity_title}</span>
                <span class="text-slate-400 ml-1">(${formatCategory(e.arm_id)})</span>
                ${e.remember_preference ? '<span class="text-[10px] text-indigo-600 bg-indigo-50 px-1.5 py-0.2 rounded ml-1">Learned</span>' : '<span class="text-[10px] text-slate-500 bg-slate-100 px-1.5 py-0.2 rounded ml-1">One-off</span>'}
              </div>
              <div class="flex items-center gap-3">
                <span class="font-bold ${e.reward_assigned > 0 ? 'text-emerald-600' : (e.reward_assigned < 0 ? 'text-rose-600' : 'text-slate-500')}">
                  ${e.reward_assigned > 0 ? '+' : ''}${e.reward_assigned} r
                </span>
                ${renderStars(e.rating)}
              </div>
            </div>
          `).join("")}
        </div>
      </div>

      <!-- LinUCB Policy Insights Section -->
      ${renderLearningSummarySection(learningSummary)}
    `;
  }

  function renderFeedbackQuestionnaire(box, ctx, mainContainer, learningSummary) {
    const activities = (todayData && todayData.activities) || [];
    let overallRating = 5;
    const actRatings = {};
    const actRemember = {};

    activities.forEach(a => {
      actRatings[a.activity_id] = 5;
      actRemember[a.activity_id] = true;
    });

    box.innerHTML = `
      <form id="postTripForm" class="space-y-4">
        <div class="bg-white border border-slate-200 rounded-xl p-4 shadow-2xs">
          <h4 class="font-bold text-sm text-slate-900 mb-1 flex items-center gap-2">
            <i class="fa-solid fa-clipboard-question text-indigo-600"></i> Overall Journey Feedback
          </h4>
          <p class="text-xs text-slate-500 mb-3">Rate your completed trip to adjust future itinerary pacing, budget allocation, and attraction styles.</p>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
            <div>
              <label class="block font-semibold text-slate-700 mb-1">Overall Trip Satisfaction</label>
              <div class="flex items-center gap-3 bg-slate-50 p-2 rounded-lg border border-slate-200">
                <div id="overallStarPicker" class="flex gap-1.5 text-xl cursor-pointer">
                  ${[1, 2, 3, 4, 5].map(s => `
                    <button type="button" data-star="${s}" class="star-pick text-amber-400 hover:scale-110 transition"><i class="fa-solid fa-star"></i></button>
                  `).join("")}
                </div>
                <span id="overallRatingLabel" class="font-bold text-slate-700">5 / 5 (Excellent)</span>
              </div>
            </div>

            <div>
              <label class="block font-semibold text-slate-700 mb-1">Daily Travel Pace</label>
              <select id="fbPace" class="w-full border border-slate-200 rounded-lg p-2 bg-slate-50 text-slate-800">
                <option value="just_right" selected>Just Right (Balanced pacing)</option>
                <option value="too_slow">Too Slow (Could fit more attractions)</option>
                <option value="too_fast">Too Fast (Felt rushed at times)</option>
              </select>
            </div>

            <div>
              <label class="block font-semibold text-slate-700 mb-1">Budget Accuracy</label>
              <select id="fbBudget" class="w-full border border-slate-200 rounded-lg p-2 bg-slate-50 text-slate-800">
                <option value="accurate" selected>Accurate (Matched actual expenditure)</option>
                <option value="cheaper">Cheaper (Cost less than expected)</option>
                <option value="more_expensive">More Expensive (Cost more than planned)</option>
              </select>
            </div>

            <div>
              <label class="block font-semibold text-slate-700 mb-1">Itinerary Realism</label>
              <select id="fbRealism" class="w-full border border-slate-200 rounded-lg p-2 bg-slate-50 text-slate-800">
                <option value="realistic" selected>Realistic & Well-Sequenced</option>
                <option value="overly_ambitious">Overly Ambitious (Distances too far)</option>
                <option value="too_relaxed">Too Relaxed (Lots of dead time)</option>
              </select>
            </div>
          </div>

          <div class="mt-3">
            <label class="block font-semibold text-slate-700 mb-1 text-xs">General Comments (Optional)</label>
            <textarea id="fbComments" rows="2" placeholder="What stood out during your journey? What would you change next time?" class="w-full border border-slate-200 rounded-lg p-2 text-xs bg-slate-50 text-slate-800 focus:bg-white focus:outline-none"></textarea>
          </div>
        </div>

        <!-- Activity Specific Evaluations -->
        <div class="bg-white border border-slate-200 rounded-xl p-4 shadow-2xs">
          <div class="flex items-center justify-between mb-2">
            <h4 class="font-bold text-sm text-slate-900 flex items-center gap-2">
              <i class="fa-solid fa-star-half-stroke text-amber-500"></i> Individual Activity Evaluations
            </h4>
            <div class="text-[11px] text-slate-500 bg-slate-100 px-2 py-0.5 rounded">
              Reward Key: 5★ = +1.0 | 4★ = +0.5 | 3★ = 0 | 2★ = -0.5 | 1★ = -1.0
            </div>
          </div>
          <p class="text-xs text-slate-500 mb-3">Each rating updates the category arm in your LinUCB preference model using the activity's original 24-dimensional context vector.</p>

          <div class="space-y-3" id="actEvaluationList">
            ${activities.map(act => `
              <div class="p-3 rounded-lg border border-slate-100 bg-slate-50/70 hover:bg-white hover:border-slate-300 transition">
                <div class="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <span class="font-bold text-xs text-slate-900">${act.title}</span>
                    <span class="text-[10px] text-indigo-700 bg-indigo-50 px-1.5 py-0.2 rounded font-medium ml-1">${formatCategory(act.category)}</span>
                  </div>
                  <div class="flex items-center gap-3">
                    <div class="flex gap-1 text-base act-star-group" data-act-id="${act.activity_id}">
                      ${[1, 2, 3, 4, 5].map(s => `
                        <button type="button" data-val="${s}" class="star-btn text-amber-400 hover:scale-110 transition"><i class="fa-solid fa-star"></i></button>
                      `).join("")}
                    </div>
                    <span class="text-xs font-bold text-slate-700 act-rating-num" data-act-id="${act.activity_id}">5★</span>
                  </div>
                </div>

                <div class="mt-2 pt-2 border-t border-slate-100 flex items-center justify-between text-[11px] text-slate-600">
                  <label class="flex items-center gap-1.5 cursor-pointer">
                    <input type="checkbox" checked class="act-remember-cb rounded text-indigo-600 focus:ring-0" data-act-id="${act.activity_id}">
                    <span>Remember this preference for future recommendations</span>
                  </label>
                  <span class="text-[10px] text-slate-400">(Uncheck if this was a one-off anomaly)</span>
                </div>
              </div>
            `).join("")}
          </div>
        </div>

        <div class="flex justify-end gap-2">
          <button type="submit" id="btnSubmitFeedback" class="bg-indigo-600 hover:bg-indigo-700 text-white font-bold text-xs px-5 py-2.5 rounded-xl transition flex items-center gap-2 shadow-xs">
            <i class="fa-solid fa-paper-plane"></i> Submit Post-Trip Evaluation
          </button>
        </div>
      </form>

      <!-- LinUCB Learning Insights -->
      <div class="mt-6">
        ${renderLearningSummarySection(learningSummary)}
      </div>
    `;

    // Overall Star Picker interaction
    const picker = box.querySelector("#overallStarPicker");
    const label = box.querySelector("#overallRatingLabel");
    const starLabels = ["1 / 5 (Poor)", "2 / 5 (Fair)", "3 / 5 (Neutral)", "4 / 5 (Good)", "5 / 5 (Excellent)"];
    picker.querySelectorAll(".star-pick").forEach(btn => {
      btn.onclick = () => {
        overallRating = parseInt(btn.dataset.star);
        label.textContent = starLabels[overallRating - 1];
        picker.querySelectorAll(".star-pick").forEach((b, i) => {
          b.classList.toggle("text-amber-400", i < overallRating);
          b.classList.toggle("text-slate-300", i >= overallRating);
        });
      };
    });

    // Individual Activity Star Pickers
    box.querySelectorAll(".act-star-group").forEach(group => {
      const actId = group.dataset.actId;
      const numLabel = box.querySelector(`.act-rating-num[data-act-id="${actId}"]`);
      group.querySelectorAll(".star-btn").forEach(btn => {
        btn.onclick = () => {
          const val = parseInt(btn.dataset.val);
          actRatings[actId] = val;
          if (numLabel) numLabel.textContent = `${val}★`;
          group.querySelectorAll(".star-btn").forEach((b, i) => {
            b.classList.toggle("text-amber-400", i < val);
            b.classList.toggle("text-slate-300", i >= val);
          });
        };
      });
    });

    // Checkboxes
    box.querySelectorAll(".act-remember-cb").forEach(cb => {
      cb.onchange = () => {
        actRemember[cb.dataset.actId] = cb.checked;
      };
    });

    // Form submission
    const form = box.querySelector("#postTripForm");
    form.onsubmit = async (e) => {
      e.preventDefault();
      const submitBtn = box.querySelector("#btnSubmitFeedback");
      submitBtn.disabled = true;
      submitBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin mr-1"></i>Updating LinUCB…`;

      const payload = {
        user_id: ctx.userId,
        overall_satisfaction: overallRating,
        pace_rating: document.getElementById("fbPace").value,
        budget_accuracy: document.getElementById("fbBudget").value,
        itinerary_realistic: document.getElementById("fbRealism").value,
        comments: document.getElementById("fbComments").value || null,
        activity_ratings: Object.keys(actRatings).map(aid => ({
          activity_id: aid,
          rating: actRatings[aid],
          remember_preference: !!actRemember[aid]
        }))
      };

      try {
        await ctx.api(`/api/live/${ctx.tripId}/postrip`, { method: "POST", body: payload });
        renderPostTrip(box, ctx, mainContainer);
      } catch (err) {
        alert("Feedback submission failed: " + err.message);
        submitBtn.disabled = false;
        submitBtn.innerHTML = `<i class="fa-solid fa-paper-plane mr-1"></i>Submit Post-Trip Evaluation`;
      }
    };
  }

  // Helper to render the LinUCB Learning Summary Table
  function renderLearningSummarySection(summary) {
    if (!summary || !summary.arms_summary) {
      return `
        <div class="bg-white border border-slate-200 rounded-xl p-4 text-xs text-slate-500 shadow-2xs">
          <h4 class="font-bold text-sm text-slate-800 mb-1 flex items-center gap-2">
            <i class="fa-solid fa-brain text-indigo-600"></i> Learned LinUCB Preferences
          </h4>
          <p>No post-trip feedback recorded yet for this profile.</p>
        </div>
      `;
    }

    const arms = summary.arms_summary || [];

    return `
      <div class="bg-white border border-slate-200 rounded-xl p-4 shadow-2xs">
        <div class="flex items-center justify-between mb-2">
          <h4 class="font-bold text-sm text-slate-900 flex items-center gap-2">
            <i class="fa-solid fa-brain text-indigo-600"></i> Learned LinUCB Recommendation Weights
          </h4>
          <span class="text-[11px] font-semibold bg-indigo-50 text-indigo-700 px-2 py-0.5 rounded">
            ${summary.total_evaluations_processed} Evaluations Processed
          </span>
        </div>
        <p class="text-xs text-slate-500 mb-3">Live parameter inspection of category arms in the user's disjoint LinUCB policy ($A_a, b_a, \\hat{\\theta}_a$).</p>

        <div class="overflow-x-auto">
          <table class="w-full text-left text-xs border border-slate-100 rounded-lg overflow-hidden">
            <thead class="bg-slate-50 text-slate-600 font-semibold border-b border-slate-200">
              <tr>
                <th class="p-2">Category Arm</th>
                <th class="p-2 text-center">Interactions</th>
                <th class="p-2 text-center">Cumulative Reward</th>
                <th class="p-2 text-center">Weight Norm ||θ||</th>
                <th class="p-2 text-center">Status</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100">
              ${arms.map(a => `
                <tr class="hover:bg-slate-50/50">
                  <td class="p-2 font-medium text-slate-800 flex items-center gap-1.5">
                    <span class="w-2 h-2 rounded-full ${a.pull_count > 0 ? (a.total_reward >= 0 ? 'bg-emerald-500' : 'bg-rose-500') : 'bg-slate-300'}"></span>
                    ${formatCategory(a.arm_id)}
                  </td>
                  <td class="p-2 text-center font-semibold text-slate-700">${a.pull_count}</td>
                  <td class="p-2 text-center font-bold ${a.total_reward > 0 ? 'text-emerald-600' : (a.total_reward < 0 ? 'text-rose-600' : 'text-slate-500')}">
                    ${a.total_reward > 0 ? '+' : ''}${a.total_reward}
                  </td>
                  <td class="p-2 text-center font-mono text-[11px] text-slate-600">${a.weight_norm.toFixed(4)}</td>
                  <td class="p-2 text-center">
                    ${a.pull_count > 0 ? (
                      a.total_reward > 0
                        ? '<span class="text-[10px] font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded">Reinforced ↑</span>'
                        : '<span class="text-[10px] font-semibold text-rose-700 bg-rose-50 px-2 py-0.5 rounded">Penalized ↓</span>'
                    ) : '<span class="text-[10px] text-slate-400">Baseline</span>'}
                  </td>
                </tr>
              `).join("")}
            </tbody>
          </table>
        </div>

        <div class="mt-3 p-2.5 bg-slate-50 rounded-lg border border-slate-100 text-[11px] text-slate-600 leading-relaxed">
          <i class="fa-solid fa-circle-info text-indigo-500 mr-1"></i>
          <span class="font-semibold">Academic Transparency:</span> ${summary.explanation}
        </div>
      </div>
    `;
  }

  // Register in Travel Companion system
  if (window.TravelModules && window.TravelModules.register) {
    TravelModules.register("live", { render });
  } else {
    // Retry once on window load
    window.addEventListener("load", () => {
      if (window.TravelModules && window.TravelModules.register) {
        TravelModules.register("live", { render });
      }
    });
  }
})();
