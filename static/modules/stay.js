// Stay and Accommodation Module UI (Person B)
// Plugs into the planner via TravelModules.register("stay", ...)

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

  TravelModules.register("stay", {
    title: "Stay & Hotels",
    icon: "fa-hotel",

    render: function (container, ctx) {
      if (!ctx || !ctx.tripId) {
        container.innerHTML = `
          <div class="p-8 text-center text-slate-500">
            <i class="fa-solid fa-hotel text-3xl mb-3 text-slate-400"></i>
            <p class="font-medium text-slate-700">No active trip selected.</p>
            <p class="text-xs text-slate-400 mt-1">Please select an active trip from the dashboard first.</p>
          </div>
        `;
        return;
      }

      container.innerHTML = `
        <div class="space-y-6">
          <!-- Module Header -->
          <div class="pb-4 border-b border-slate-100 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <h3 class="text-lg font-bold text-slate-800 flex items-center gap-2">
                <i class="fa-solid fa-hotel text-indigo-600"></i>
                <span>Accommodation & Stay Anchor</span>
              </h3>
              <p class="text-xs text-slate-500 mt-0.5">Pick an optimized neighborhood to minimize daily commute or link your booked hotel.</p>
            </div>
            <div id="stayActiveBadge" class="hidden text-xs bg-indigo-50 border border-indigo-200 text-indigo-700 px-3 py-1.5 rounded-lg font-semibold flex items-center gap-2">
              <i class="fa-solid fa-circle-check text-indigo-600"></i>
              <span id="stayActiveName">Stay Anchored</span>
            </div>
          </div>

          <!-- Two Paths Selection -->
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <button id="stayModeRecommendBtn" class="p-4 rounded-xl border-2 border-indigo-600 bg-indigo-50/40 text-left transition-all hover:bg-indigo-50">
              <div class="flex items-center gap-2.5 text-indigo-700 font-bold text-sm">
                <i class="fa-solid fa-compass"></i>
                <span>Help Me Pick an Area to Stay</span>
              </div>
              <p class="text-xs text-slate-500 mt-1.5 leading-relaxed">Analyzes all scheduled stops in your plan to recommend the top 3 neighborhoods with the lowest daily commute.</p>
            </button>

            <button id="stayModeHotelFirstBtn" class="p-4 rounded-xl border-2 border-slate-200 bg-white text-left transition-all hover:border-slate-300 hover:bg-slate-50">
              <div class="flex items-center gap-2.5 text-slate-800 font-bold text-sm">
                <i class="fa-solid fa-building-circle-check"></i>
                <span>I Already Have a Hotel</span>
              </div>
              <p class="text-xs text-slate-500 mt-1.5 leading-relaxed">Enter your booked property to anchor your daily start and end points and preview commute efficiency.</p>
            </button>
          </div>

          <!-- SECTION A: Area Recommender & Options (Active by default) -->
          <div id="stayAreaSection" class="space-y-6">
            <!-- Top 3 Areas Recommendation -->
            <div class="p-4 rounded-xl border border-slate-200 bg-white space-y-3 shadow-sm">
              <div class="flex items-center justify-between">
                <h4 class="text-xs font-bold uppercase tracking-wider text-slate-600 flex items-center gap-1.5">
                  <i class="fa-solid fa-map-location-dot text-indigo-500"></i>
                  <span>Recommended Neighborhoods (Least Daily Commute)</span>
                </h4>
                <span class="text-[10px] text-slate-400">Sum of round-trip legs</span>
              </div>

              <div id="stayAreasGrid" class="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div class="p-4 text-center text-xs text-slate-400 col-span-3">Loading area recommendations...</div>
              </div>
            </div>

            <!-- Hotel Options in Selected Area -->
            <div id="stayHotelsContainer" class="p-4 rounded-xl border border-slate-200 bg-white space-y-3 shadow-sm">
              <div class="flex items-center justify-between">
                <div>
                  <h4 class="text-xs font-bold text-slate-800 flex items-center gap-2">
                    <span id="staySelectedAreaTitle">Hotel Options</span>
                    <span class="text-[11px] font-normal text-slate-500" id="stayBudgetBandText"></span>
                  </h4>
                  <p class="text-[11px] text-slate-400 mt-0.5">Rates require external search; free hotel price APIs do not exist.</p>
                </div>
              </div>

              <div id="stayHotelList" class="divide-y divide-slate-100">
                <!-- Hotel cards -->
              </div>
            </div>
          </div>

          <!-- SECTION B: Hotel-First Input Form -->
          <div id="stayHotelFirstSection" class="hidden p-5 rounded-xl border border-slate-200 bg-white space-y-4 shadow-sm">
            <h4 class="text-sm font-bold text-slate-800">Anchor Your Booked Hotel</h4>
            <div class="space-y-3">
              <div>
                <label class="block text-xs font-semibold text-slate-700 mb-1">Hotel or Property Name</label>
                <input id="stayInputHotelName" type="text" placeholder="e.g., The Imperial, Janpath" class="w-full text-xs p-2.5 rounded-lg border border-slate-300 focus:outline-none focus:border-indigo-500" />
              </div>
              <button id="staySaveHotelFirstBtn" class="px-4 py-2 text-xs font-bold rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 transition-colors flex items-center gap-2">
                <i class="fa-solid fa-anchor"></i> Save & Preview Commute
              </button>
            </div>

            <!-- Commute Preview Card -->
            <div id="stayPreviewBox" class="hidden p-4 rounded-xl border border-indigo-100 bg-indigo-50/40 space-y-2 text-xs">
              <div class="flex items-center justify-between font-bold text-indigo-900">
                <span>Commute Preview Analysis</span>
                <span class="px-2 py-0.5 rounded text-[10px] bg-indigo-100 text-indigo-700 uppercase">Preview</span>
              </div>
              <p id="stayPreviewText" class="text-slate-600 leading-relaxed"></p>
            </div>
          </div>

          <!-- Footnote & Attribution -->
          <div class="pt-4 border-t border-slate-100 flex flex-col sm:flex-row items-center justify-between text-[11px] text-slate-400 gap-2">
            <div>
              <span>Powered by Geoapify</span> &bull; 
              <span>OpenStreetMap contributors</span>
            </div>
            <div class="text-[10px] bg-slate-100 px-2 py-0.5 rounded text-slate-500">
              No live hotel prices shown &bull; Nightly budget band calculated from trip total
            </div>
          </div>
        </div>
      `;

      // Event Handlers for Mode Toggles
      const recBtn = container.querySelector("#stayModeRecommendBtn");
      const hfBtn = container.querySelector("#stayModeHotelFirstBtn");
      const areaSec = container.querySelector("#stayAreaSection");
      const hfSec = container.querySelector("#stayHotelFirstSection");

      recBtn.onclick = () => {
        recBtn.className = "p-4 rounded-xl border-2 border-indigo-600 bg-indigo-50/40 text-left transition-all hover:bg-indigo-50";
        hfBtn.className = "p-4 rounded-xl border-2 border-slate-200 bg-white text-left transition-all hover:border-slate-300 hover:bg-slate-50";
        areaSec.classList.remove("hidden");
        hfSec.classList.add("hidden");
      };

      hfBtn.onclick = () => {
        hfBtn.className = "p-4 rounded-xl border-2 border-indigo-600 bg-indigo-50/40 text-left transition-all hover:bg-indigo-50";
        recBtn.className = "p-4 rounded-xl border-2 border-slate-200 bg-white text-left transition-all hover:border-slate-300 hover:bg-slate-50";
        hfSec.classList.remove("hidden");
        areaSec.classList.add("hidden");
      };

      // Load Recommended Areas
      async function loadAreas() {
        try {
          const res = await fetch(`/api/stay/${ctx.tripId}/areas`);
          if (!res.ok) throw new Error("Failed to load areas");
          const data = await res.json();
          renderAreas(data.recommended_areas || []);
        } catch (err) {
          console.error("Error loading stay areas:", err);
        }
      }

      function renderAreas(areas) {
        const grid = container.querySelector("#stayAreasGrid");
        grid.innerHTML = "";

        if (areas.length === 0) {
          grid.innerHTML = `<div class="p-4 text-center text-xs text-slate-400 col-span-3">No area recommendations available yet.</div>`;
          return;
        }

        areas.forEach((a, idx) => {
          const card = document.createElement("div");
          card.className = `p-3.5 rounded-xl border cursor-pointer transition-all ${idx === 0 ? 'border-indigo-500 bg-indigo-50/30 ring-2 ring-indigo-500/20' : 'border-slate-200 bg-white hover:border-slate-300'}`;
          card.innerHTML = `
            <div class="flex items-center justify-between">
              <span class="text-xs font-bold text-slate-800">${escapeHtml(a.area_name)}</span>
              <span class="text-[10px] font-bold px-1.5 py-0.5 rounded ${idx === 0 ? 'bg-indigo-600 text-white' : 'bg-slate-100 text-slate-600'}">#${idx+1}</span>
            </div>
            <div class="mt-2 text-indigo-700 font-bold text-xs">
              <i class="fa-solid fa-car-side mr-1"></i>~${a.estimated_daily_commute_minutes} mins / day
            </div>
            <p class="text-[11px] text-slate-500 mt-1 leading-snug">${escapeHtml(a.reason)}</p>
          `;
          card.onclick = () => loadHotels(a.area_name, a.lat, a.lon);
          grid.appendChild(card);
        });

        // Load hotels for top recommended area by default
        if (areas[0]) {
          loadHotels(areas[0].area_name, areas[0].lat, areas[0].lon);
        }
      }

      async function loadHotels(areaName, lat, lon) {
        container.querySelector("#staySelectedAreaTitle").textContent = `Hotels near ${areaName}`;
        const list = container.querySelector("#stayHotelList");
        list.innerHTML = `<div class="p-6 text-center text-xs text-slate-400"><i class="fa-solid fa-spinner fa-spin mr-2"></i>Loading accommodation options...</div>`;

        try {
          const res = await fetch(`/api/stay/${ctx.tripId}/options?area_name=${encodeURIComponent(areaName)}&lat=${lat}&lon=${lon}`);
          if (!res.ok) throw new Error("Failed to load hotel options");
          const data = await res.json();

          container.querySelector("#stayBudgetBandText").textContent = `(Estimated Budget: ${formatINR(data.nightly_budget_estimate_inr)}/night)`;

          if (data.active_stay) {
            container.querySelector("#stayActiveBadge").classList.remove("hidden");
            container.querySelector("#stayActiveName").textContent = `Anchored: ${data.active_stay.name}`;
          }

          renderHotels(data.options || []);
        } catch (err) {
          list.innerHTML = `<div class="p-4 text-center text-rose-500 text-xs">${escapeHtml(err.message)}</div>`;
        }
      }

      function renderHotels(hotels) {
        const list = container.querySelector("#stayHotelList");
        list.innerHTML = "";

        if (hotels.length === 0) {
          list.innerHTML = `<div class="p-6 text-center text-xs text-slate-400">No properties found in this location.</div>`;
          return;
        }

        hotels.forEach(h => {
          const row = document.createElement("div");
          row.className = "py-3 flex flex-col sm:flex-row sm:items-center justify-between gap-2.5";
          row.innerHTML = `
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2">
                <span class="text-xs font-bold text-slate-800">${escapeHtml(h.name)}</span>
                <span class="text-[10px] px-1.5 py-0.5 rounded bg-slate-100 text-slate-600 capitalize">${escapeHtml(h.tier_label || humanLabel(h.stay_type))}</span>
              </div>
              <p class="text-xs text-slate-400 mt-0.5 whitespace-normal">${escapeHtml(stayDescription(h))}</p>
            </div>
            <div class="flex items-center gap-2">
              <a href="${escapeHtml(h.external_search_url)}" target="_blank" rel="noopener noreferrer" class="px-2.5 py-1 text-xs rounded border border-slate-300 text-slate-600 hover:bg-slate-50 transition-colors flex items-center gap-1">
                <span>Find hotels here</span>
                <i class="fa-solid fa-arrow-up-right-from-square text-[10px]"></i>
              </a>
              <button class="staySelectBtn px-3 py-1 text-xs font-bold rounded bg-indigo-600 text-white hover:bg-indigo-700 transition-colors">
                ${h.kind === "area" ? "Use area as base" : "Select Stay"}
              </button>
            </div>
          `;

          row.querySelector(".staySelectBtn").onclick = async () => {
            try {
              const res = await fetch(`/api/stay/${ctx.tripId}/select`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(h)
              });
              if (res.ok) {
                container.querySelector("#stayActiveBadge").classList.remove("hidden");
                container.querySelector("#stayActiveName").textContent = `Anchored: ${h.name}`;
                if (confirm(`Hotel "${h.name}" selected! Would you like to regenerate your itinerary right now anchored around this hotel?`)) {
                  const replanRes = await fetch(`/api/stay/${ctx.tripId}/replan`, { method: "POST" });
                  if (replanRes.ok) {
                    alert(`Itinerary successfully regenerated around "${h.name}" as your daily starting and ending anchor!`);
                    if (window.TravelModules && window.TravelModules.switch) {
                      window.TravelModules.switch("plan");
                    }
                  } else {
                    alert("Itinerary replan failed. You can re-generate anytime from the Trip Plan tab.");
                  }
                }
              }
            } catch (err) {
              alert("Failed to select stay: " + err.message);
            }
          };

          list.appendChild(row);
        });
      }

      // Hotel-first submission
      const hfSubmitBtn = container.querySelector("#staySaveHotelFirstBtn");
      hfSubmitBtn.onclick = async () => {
        const nameInput = container.querySelector("#stayInputHotelName");
        if (!nameInput.value.trim()) {
          alert("Please enter a hotel name.");
          return;
        }

        try {
          const res = await fetch(`/api/stay/${ctx.tripId}/hotel-first-preview`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ hotel_name: nameInput.value.trim() })
          });
          if (res.ok) {
            const data = await res.json();
            const previewBox = container.querySelector("#stayPreviewBox");
            previewBox.classList.remove("hidden");
            container.querySelector("#stayPreviewText").innerHTML = `
              <div><strong>Before hotel anchor:</strong> ~${data.preview.before_estimated_daily_commute_minutes} mins daily commute. <strong>After hotel anchor:</strong> ~${data.preview.after_estimated_daily_commute_minutes} mins.</div>
              <div class="mt-2 text-indigo-900 font-semibold">${escapeHtml(data.preview.message)}</div>
              <button id="stayHotelFirstReplanBtn" class="mt-3 px-3.5 py-1.5 text-xs font-bold rounded-lg bg-emerald-600 text-white hover:bg-emerald-700 transition flex items-center gap-1.5 shadow-xs">
                <i class="fa-solid fa-arrows-rotate"></i> Re-generate Itinerary Around This Hotel
              </button>
            `;
            const replanBtn = container.querySelector("#stayHotelFirstReplanBtn");
            if (replanBtn) {
              replanBtn.onclick = async () => {
                replanBtn.disabled = true;
                replanBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Regenerating itinerary...`;
                const replanRes = await fetch(`/api/stay/${ctx.tripId}/replan`, { method: "POST" });
                if (replanRes.ok) {
                  alert(`Itinerary successfully regenerated around ${data.stay.name} as your anchor!`);
                  if (window.TravelModules && window.TravelModules.switch) {
                    window.TravelModules.switch("plan");
                  }
                } else {
                  alert("Failed to regenerate itinerary.");
                  replanBtn.disabled = false;
                }
              };
            }
            container.querySelector("#stayActiveBadge").classList.remove("hidden");
            container.querySelector("#stayActiveName").textContent = `Anchored: ${data.stay.name}`;
          }
        } catch (err) {
          alert("Hotel-first preview error: " + err.message);
        }
      };

      loadAreas();
    }
  });
})();
