// Dynamic Time-Budget Plan Engine Module UI (Person A)
// Plugs into Travel Companion via TravelModules.register("plan", ...)

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

  function downloadICS(plan) {
    if (!plan || !plan.days) return;
    let ics = [
      "BEGIN:VCALENDAR",
      "VERSION:2.0",
      "PRODID:-//RL Travel Guide//Plan Engine//EN",
      "CALSCALE:GREGORIAN",
      "METHOD:PUBLISH"
    ];

    const todayStr = new Date().toISOString().replace(/[-:]/g, "").split(".")[0] + "Z";

    plan.days.forEach(day => {
      (day.blocks || []).forEach((b, idx) => {
        if (b.block_type === "travel") return; // Skip transit legs in calendar
        const title = b.place ? b.place.name : (b.notes || b.block_type);
        const startTime = (b.start_time || "09:00").replace(":", "") + "00";
        const endTime = (b.end_time || "10:00").replace(":", "") + "00";
        
        // Use placeholder date if none
        const baseDate = new Date();
        baseDate.setDate(baseDate.getDate() + (day.day_number - 1));
        const dateStr = baseDate.toISOString().slice(0, 10).replace(/-/g, "");

        ics.push("BEGIN:VEVENT");
        ics.push(`UID:plan-${plan.trip_id}-d${day.day_number}-b${idx}@rltravelguide.local`);
        ics.push(`DTSTAMP:${todayStr}`);
        ics.push(`DTSTART:${dateStr}T${startTime}`);
        ics.push(`DTEND:${dateStr}T${endTime}`);
        ics.push(`SUMMARY:${title}`);
        ics.push(`DESCRIPTION:${b.notes || ''} (Type: ${b.block_type})`);
        ics.push("STATUS:CONFIRMED");
        ics.push("END:VEVENT");
      });
    });

    ics.push("END:VCALENDAR");

    const blob = new Blob([ics.join("\r\n")], { type: "text/calendar;charset=utf-8" });
    const link = document.createElement("a");
    link.href = window.URL.createObjectURL(blob);
    link.setAttribute("download", `trip_itinerary_${plan.destination_id || 'trip'}.ics`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  }

  TravelModules.register("plan", {
    title: "Trip Plan",
    icon: "fa-calendar-days",

    render: function (container, ctx) {
      if (!ctx || !ctx.tripId) {
        container.innerHTML = `
          <div class="p-8 text-center text-slate-500">
            <i class="fa-solid fa-plane-slash text-3xl mb-3 text-slate-400"></i>
            <p class="font-medium text-slate-700">No active trip selected.</p>
            <p class="text-xs text-slate-400 mt-1">Create or select a trip on the dashboard to access your dynamic plan.</p>
          </div>
        `;
        return;
      }

      container.innerHTML = `
        <div class="space-y-6">
          <!-- Top Control Header -->
          <div class="flex flex-col sm:flex-row sm:items-center justify-between pb-4 border-b border-slate-100 gap-3">
            <div>
              <h3 class="text-lg font-bold text-slate-800 flex items-center gap-2">
                <i class="fa-solid fa-calendar-days text-indigo-600"></i>
                <span>Dynamic Time-Budget Plan</span>
              </h3>
              <p class="text-xs text-slate-500 mt-0.5">Time-window scheduled, LinUCB prioritized, and multimodal travel estimated.</p>
            </div>
            <div class="flex items-center gap-2">
              <button id="planRegenerateBtn" class="px-3 py-1.5 text-xs font-semibold rounded-lg bg-indigo-50 text-indigo-700 hover:bg-indigo-100 transition-colors flex items-center gap-1.5">
                <i class="fa-solid fa-rotate"></i> Re-Plan
              </button>
              <button id="planExportIcsBtn" class="px-3 py-1.5 text-xs font-semibold rounded-lg bg-emerald-50 text-emerald-700 hover:bg-emerald-100 transition-colors flex items-center gap-1.5">
                <i class="fa-solid fa-file-arrow-down"></i> Export .ICS
              </button>
            </div>
          </div>

          <!-- Loading Indicator -->
          <div id="planLoadingArea" class="p-8 text-center text-slate-400 text-xs">
            <i class="fa-solid fa-spinner fa-spin text-lg mb-2"></i>
            <p>Optimizing time-budget itinerary...</p>
          </div>

          <!-- Plan Content Area -->
          <div id="planContentArea" class="hidden space-y-6">
            <!-- Stay Anchor Banner if available -->
            <div id="planStayAnchorCard" class="hidden p-3.5 rounded-xl border border-indigo-100 bg-indigo-50/50 flex items-center justify-between text-xs">
              <div class="flex items-center gap-2.5">
                <span class="w-7 h-7 rounded-lg bg-indigo-600 text-white flex items-center justify-center font-bold">
                  <i class="fa-solid fa-hotel text-xs"></i>
                </span>
                <div>
                  <span class="font-bold text-slate-800" id="planStayAnchorName">Hotel</span>
                  <span class="text-slate-500 ml-1.5" id="planStayAnchorType">(Stay Anchor Active)</span>
                  <p class="text-[11px] text-slate-400">All daily routes start and return to this anchor.</p>
                </div>
              </div>
            </div>

            <!-- Budget Ledger Overview -->
            <div class="p-4 rounded-xl border border-slate-200 bg-white shadow-sm space-y-3">
              <div class="flex items-center justify-between">
                <h4 class="text-xs font-bold uppercase tracking-wider text-slate-500">Budget Allocation Ledger</h4>
                <span id="planOverallBudgetBadge" class="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-emerald-100 text-emerald-800">Budget on Track</span>
              </div>
              <div id="planBudgetGrid" class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-2">
                <!-- Dynamically filled -->
              </div>
            </div>

            <!-- Day by Day Timeline -->
            <div id="planDaysContainer" class="space-y-6">
              <!-- Dynamically filled with day cards -->
            </div>

            <!-- Leftovers Drawer (Places that did not fit) -->
            <div id="planLeftoversSection" class="hidden p-4 rounded-xl border border-slate-200 bg-slate-50/60 space-y-3">
              <div class="flex items-center justify-between">
                <h4 class="text-xs font-bold text-slate-700 flex items-center gap-2">
                  <i class="fa-solid fa-clock-rotate-left text-amber-500"></i>
                  <span>Unscheduled Leftovers (Did Not Fit Day Window)</span>
                </h4>
                <span class="text-[11px] text-slate-400">Optional swap candidates</span>
              </div>
              <div id="planLeftoversList" class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2 text-xs">
                <!-- Leftover cards -->
              </div>
            </div>

            <!-- Attribution & Methodology Footer -->
            <div class="pt-4 border-t border-slate-100 flex flex-col sm:flex-row items-center justify-between text-[11px] text-slate-400 gap-2">
              <div>
                <span>Powered by Geoapify</span> &bull; 
                <span>OpenStreetMap contributors</span> &bull; 
                <span>Weather data by Open-Meteo.com</span>
              </div>
              <div class="text-[10px] bg-slate-100 px-2 py-0.5 rounded text-slate-500">
                Transit times: straight-line distance &times; circuity factor &bull; Estimates only
              </div>
            </div>
          </div>
        </div>
      `;

      let currentPlan = null;

      async function fetchPlan(regenerate = false) {
        const loading = container.querySelector("#planLoadingArea");
        const content = container.querySelector("#planContentArea");
        if (loading) loading.classList.remove("hidden");
        if (content) content.classList.add("hidden");

        try {
          const url = regenerate
            ? `/api/plan/generate/${ctx.tripId}`
            : `/api/plan/${ctx.tripId}`;
          const method = regenerate ? "POST" : "GET";
          const res = await fetch(url, { method });

          if (!res.ok) {
            throw new Error(`Plan request failed with status ${res.status}`);
          }

          currentPlan = await res.json();
          renderPlanDetails(currentPlan);
        } catch (err) {
          console.error("Plan loading error:", err);
          if (loading) {
            loading.innerHTML = `
              <div class="text-rose-500">
                <i class="fa-solid fa-triangle-exclamation text-lg mb-1"></i>
                <p>Failed to load plan: ${escapeHtml(err.message)}</p>
                <button id="planRetryBtn" class="mt-2 px-3 py-1 bg-slate-100 text-slate-700 rounded text-xs hover:bg-slate-200">Retry</button>
              </div>
            `;
            const retry = loading.querySelector("#planRetryBtn");
            if (retry) retry.onclick = () => fetchPlan(false);
          }
        }
      }

      function renderPlanDetails(plan) {
        const loading = container.querySelector("#planLoadingArea");
        const content = container.querySelector("#planContentArea");
        if (loading) loading.classList.add("hidden");
        if (content) content.classList.remove("hidden");

        // 1. Stay Anchor
        const stayCard = container.querySelector("#planStayAnchorCard");
        if (plan.stay_anchor) {
          stayCard.classList.remove("hidden");
          container.querySelector("#planStayAnchorName").textContent = plan.stay_anchor.name;
          container.querySelector("#planStayAnchorType").textContent = `(${plan.stay_anchor.stay_type.replace('_', ' ')})`;
        } else {
          stayCard.classList.add("hidden");
        }

        // 2. Budget Ledger
        const badge = container.querySelector("#planOverallBudgetBadge");
        badge.className = `px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
          plan.overall_budget_status === 'green' ? 'bg-emerald-100 text-emerald-800' :
          (plan.overall_budget_status === 'amber' ? 'bg-amber-100 text-amber-800' : 'bg-rose-100 text-rose-800')
        }`;
        badge.textContent = `Budget: ${plan.overall_budget_status}`;

        const bGrid = container.querySelector("#planBudgetGrid");
        bGrid.innerHTML = "";
        (plan.budget_ledger || []).forEach(line => {
          const col = document.createElement("div");
          col.className = "p-2 rounded-lg bg-slate-50 border border-slate-100 text-center";
          col.innerHTML = `
            <div class="text-[10px] uppercase font-bold text-slate-400">${escapeHtml(line.category)}</div>
            <div class="text-xs font-bold text-slate-800 mt-0.5">&#8377;${line.estimated_spent}</div>
            <div class="text-[10px] text-slate-400">/ &#8377;${line.allocated_amount}</div>
          `;
          bGrid.appendChild(col);
        });

        // 3. Days Container
        const daysCont = container.querySelector("#planDaysContainer");
        daysCont.innerHTML = "";
        let allLeftovers = [];

        (plan.days || []).forEach(day => {
          const dayEl = document.createElement("div");
          dayEl.className = "rounded-xl border border-slate-200 bg-white overflow-hidden shadow-sm";

          const blocksHtml = (day.blocks || []).map(b => {
            if (b.block_type === "travel") {
              const leg = b.travel_leg || {};
              return `
                <div class="px-4 py-1.5 flex items-center gap-3 text-[11px] text-slate-400 bg-slate-50/70 border-y border-dashed border-slate-200">
                  <i class="fa-solid fa-arrow-down text-[10px] text-indigo-400"></i>
                  <span>${b.start_time} - ${b.end_time}</span>
                  <span class="font-medium text-slate-600"><i class="fa-solid fa-route mr-1 text-slate-400"></i>${escapeHtml(b.notes)}</span>
                  ${leg.estimated_cost ? `<span class="ml-auto text-[10px] bg-slate-200/60 px-1.5 py-0.5 rounded text-slate-600">&#8377;${leg.estimated_cost}</span>` : ''}
                </div>
              `;
            }

            let typeBadge = "";
            let icon = "fa-location-dot";
            if (b.block_type === "meal") {
              typeBadge = "bg-amber-100 text-amber-800";
              icon = "fa-utensils";
            } else if (b.block_type === "shopping") {
              typeBadge = "bg-purple-100 text-purple-800";
              icon = "fa-bag-shopping";
            } else {
              typeBadge = "bg-indigo-100 text-indigo-800";
              icon = "fa-landmark";
            }

            return `
              <div class="p-3.5 flex items-start gap-3 hover:bg-slate-50/50 transition-colors">
                <span class="w-8 h-8 rounded-lg flex items-center justify-center text-xs mt-0.5 ${typeBadge}">
                  <i class="fa-solid ${icon}"></i>
                </span>
                <div class="flex-1 min-w-0">
                  <div class="flex items-center gap-2">
                    <span class="text-xs font-bold text-slate-800 truncate">${escapeHtml(b.place ? b.place.name : b.notes)}</span>
                    <span class="text-[10px] font-mono text-slate-400">${b.start_time} - ${b.end_time} (${b.duration_minutes}m)</span>
                  </div>
                  <p class="text-xs text-slate-500 mt-0.5 line-clamp-1">${escapeHtml(b.notes || (b.place && b.place.address) || '')}</p>
                </div>
                ${b.place && b.place.cost_amount ? `<div class="text-xs font-bold text-slate-700">&#8377;${b.place.cost_amount}</div>` : ''}
              </div>
            `;
          }).join("");

          dayEl.innerHTML = `
            <div class="px-4 py-2.5 bg-slate-50/80 border-b border-slate-200 flex items-center justify-between">
              <span class="font-bold text-xs text-slate-800 flex items-center gap-2">
                <span class="w-5 h-5 rounded-full bg-indigo-600 text-white flex items-center justify-center text-[10px]">${day.day_number}</span>
                <span>Day ${day.day_number} Itinerary</span>
              </span>
              <span class="text-[11px] font-mono text-slate-500">${day.window.start_time} - ${day.window.end_time}</span>
            </div>
            <div class="divide-y divide-slate-100">
              ${blocksHtml}
            </div>
          `;
          daysCont.appendChild(dayEl);

          if (day.leftovers && day.leftovers.length > 0) {
            allLeftovers = allLeftovers.concat(day.leftovers);
          }
        });

        // 4. Leftovers
        const leftSec = container.querySelector("#planLeftoversSection");
        const leftList = container.querySelector("#planLeftoversList");
        if (allLeftovers.length > 0) {
          leftSec.classList.remove("hidden");
          leftList.innerHTML = allLeftovers.map(l => `
            <div class="p-2.5 rounded-lg border border-slate-200 bg-white">
              <div class="font-bold text-slate-800 truncate">${escapeHtml(l.name)}</div>
              <div class="text-[10px] text-slate-400 capitalize">${escapeHtml(l.category.replace('_', ' '))}</div>
            </div>
          `).join("");
        } else {
          leftSec.classList.add("hidden");
        }
      }

      // Event Listeners
      const regenBtn = container.querySelector("#planRegenerateBtn");
      if (regenBtn) regenBtn.onclick = () => fetchPlan(true);

      const expBtn = container.querySelector("#planExportIcsBtn");
      if (expBtn) expBtn.onclick = () => downloadICS(currentPlan);

      // Initial Fetch
      fetchPlan(false);
    }
  });
})();
