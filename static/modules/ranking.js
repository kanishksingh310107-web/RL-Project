// Seasonal & Multi-Criteria Ranking UI Module
// Owner: Person C
// Vanilla JS with Tailwind CSS classes. Registers with TravelModules.

TravelModules.register("ranking", {
  async render(container, ctx) {
    const userId = ctx.userId;
    if (!userId) {
      container.innerHTML = `<div class="p-4 text-center text-slate-500">Please sign in to view personalized rankings.</div>`;
      return;
    }

    // Default query state
    let state = {
      date: new Date().toISOString().split("T")[0],
      budget: "",
      closed: "",
      advisory: "",
      activeTab: "overall",
      loading: false,
      data: null,
      error: null
    };

    function renderUI() {
      container.innerHTML = `
        <div class="space-y-4 text-slate-800">
          <!-- Disclosure Banner -->
          <div class="bg-amber-50 border-l-4 border-amber-400 p-3 rounded-r-lg text-xs text-amber-800 space-y-1">
            <div class="font-semibold flex items-center gap-1.5">
              <i class="fa-solid fa-triangle-exclamation"></i>
              SIMULATED / STATIC DATA NOTICE
            </div>
            <p>
              Destination catalogue is sample data. Popularity scores are static estimates as of Nov 2026.
              Live conditions feed is absent (neutral 0.5 placeholder). Weights are subjective assumptions.
            </p>
          </div>

          <!-- Filter & Constraint Controls -->
          <div class="bg-slate-50 p-3 rounded-xl border border-slate-200 grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
            <div>
              <label class="block font-medium text-slate-600 mb-1">Travel Date</label>
              <input type="date" id="rkDate" value="${state.date}" class="w-full bg-white border border-slate-300 rounded-lg px-2.5 py-1.5 text-slate-800 focus:outline-none focus:ring-1 focus:ring-indigo-500">
            </div>
            <div>
              <label class="block font-medium text-slate-600 mb-1">Daily Budget Cap (USD/day)</label>
              <input type="number" id="rkBudget" placeholder="Optional (e.g. 100)" value="${state.budget}" class="w-full bg-white border border-slate-300 rounded-lg px-2.5 py-1.5 text-slate-800 focus:outline-none focus:ring-1 focus:ring-indigo-500">
            </div>
            <div class="flex items-end">
              <button id="rkApplyBtn" class="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-medium py-1.5 px-3 rounded-lg transition flex items-center justify-center gap-1.5">
                <i class="fa-solid fa-arrows-rotate"></i>
                <span>Update Rankings</span>
              </button>
            </div>
          </div>

          <!-- Color Legend for 6 Breakdown Components -->
          <div class="flex flex-wrap items-center gap-3 text-[11px] text-slate-600 bg-white p-2 rounded-lg border border-slate-100">
            <span class="font-semibold text-slate-700">Components:</span>
            <span class="flex items-center gap-1"><span class="w-2.5 h-2.5 rounded-full bg-indigo-500"></span>Interest (25%)</span>
            <span class="flex items-center gap-1"><span class="w-2.5 h-2.5 rounded-full bg-emerald-500"></span>Season (20%)</span>
            <span class="flex items-center gap-1"><span class="w-2.5 h-2.5 rounded-full bg-amber-500"></span>Popularity (15%)</span>
            <span class="flex items-center gap-1"><span class="w-2.5 h-2.5 rounded-full bg-blue-500"></span>Feasibility (15%)</span>
            <span class="flex items-center gap-1"><span class="w-2.5 h-2.5 rounded-full bg-slate-400"></span>Live Placeholder (10%)</span>
            <span class="flex items-center gap-1"><span class="w-2.5 h-2.5 rounded-full bg-rose-500"></span>Feedback (15%)</span>
          </div>

          <!-- Navigation Tabs for the 4 Specialized Lists + Overall -->
          <div class="flex flex-wrap gap-1 border-b border-slate-200 pb-2 text-xs">
            <button data-tab="overall" class="rk-tab px-3 py-1.5 rounded-lg font-medium ${state.activeTab === 'overall' ? 'bg-indigo-600 text-white' : 'bg-slate-100 hover:bg-slate-200 text-slate-700'}">
              <i class="fa-solid fa-list-ol mr-1"></i>Overall
            </button>
            <button data-tab="trending_now" class="rk-tab px-3 py-1.5 rounded-lg font-medium ${state.activeTab === 'trending_now' ? 'bg-indigo-600 text-white' : 'bg-slate-100 hover:bg-slate-200 text-slate-700'}">
              <i class="fa-solid fa-arrow-trend-up mr-1"></i>Trending Now
            </button>
            <button data-tab="best_this_season" class="rk-tab px-3 py-1.5 rounded-lg font-medium ${state.activeTab === 'best_this_season' ? 'bg-indigo-600 text-white' : 'bg-slate-100 hover:bg-slate-200 text-slate-700'}">
              <i class="fa-solid fa-cloud-sun mr-1"></i>Best This Season
            </button>
            <button data-tab="best_for_you" class="rk-tab px-3 py-1.5 rounded-lg font-medium ${state.activeTab === 'best_for_you' ? 'bg-indigo-600 text-white' : 'bg-slate-100 hover:bg-slate-200 text-slate-700'}">
              <i class="fa-solid fa-user-check mr-1"></i>Best For You
            </button>
            <button data-tab="best_feasible" class="rk-tab px-3 py-1.5 rounded-lg font-medium ${state.activeTab === 'best_feasible' ? 'bg-indigo-600 text-white' : 'bg-slate-100 hover:bg-slate-200 text-slate-700'}">
              <i class="fa-solid fa-wallet mr-1"></i>Best Feasible
            </button>
          </div>

          <!-- Main Content Area -->
          <div id="rkContentArea">
            ${state.loading ? `<div class="p-8 text-center text-slate-500 text-sm"><i class="fa-solid fa-spinner fa-spin mr-2"></i>Computing scores...</div>` : ''}
            ${state.error ? `<div class="p-4 bg-rose-50 text-rose-700 text-xs rounded-lg">${state.error}</div>` : ''}
            ${!state.loading && state.data ? renderRankedList(state.data) : ''}
          </div>

          <!-- Excluded Destinations Section -->
          ${state.data && state.data.excluded && state.data.excluded.length > 0 ? renderExcluded(state.data.excluded) : ''}

          <!-- Geoapify & OSM Attribution -->
          <div class="text-[10px] text-slate-400 text-center pt-3 border-t border-slate-100">
            Powered by Geoapify | &copy; OpenStreetMap contributors
          </div>
        </div>
      `;

      // Attach DOM Event Listeners
      const applyBtn = container.querySelector("#rkApplyBtn");
      if (applyBtn) {
        applyBtn.onclick = () => {
          state.date = container.querySelector("#rkDate").value;
          state.budget = container.querySelector("#rkBudget").value;
          fetchRankings();
        };
      }

      container.querySelectorAll(".rk-tab").forEach(btn => {
        btn.onclick = () => {
          state.activeTab = btn.dataset.tab;
          renderUI();
        };
      });
    }

    function renderRankedList(data) {
      let list = [];
      let listTitle = "Overall Destination Ranking";
      if (state.activeTab === "overall") {
        list = data.overall_ranking || [];
        listTitle = "Overall Ranked Destinations";
      } else if (state.activeTab === "trending_now") {
        list = data.trending_now || [];
        listTitle = "Trending Destinations (Static Catalogue Flag)";
      } else if (state.activeTab === "best_this_season") {
        list = data.best_this_season || [];
        listTitle = "Best Destinations for Selected Month";
      } else if (state.activeTab === "best_for_you") {
        list = data.best_for_you || [];
        listTitle = "Top Matches for Your Stated Interests";
      } else if (state.activeTab === "best_feasible") {
        list = data.best_feasible || [];
        listTitle = "Top Feasible (Budget & Companions Alignment)";
      }

      if (!list.length) {
        return `<div class="p-6 text-center text-slate-400 text-sm">No destinations available for this filter.</div>`;
      }

      return `
        <div class="space-y-3">
          <div class="text-xs font-semibold text-slate-500 uppercase tracking-wide flex justify-between items-center">
            <span>${listTitle} (${list.length} results)</span>
            <span class="text-[10px] text-slate-400 font-normal">Score scale: 0 - 100 pts</span>
          </div>
          ${list.map((dest, idx) => renderDestinationCard(dest, idx + 1)).join("")}
        </div>
      `;
    }

    function renderDestinationCard(dest, rank) {
      const b = dest.breakdown;
      const cInterest = b.interest.contribution;
      const cSeason = b.season.contribution;
      const cPopularity = b.popularity.contribution;
      const cFeasibility = b.feasibility.contribution;
      const cLive = b.live.contribution;
      const cFeedback = b.feedback.contribution;

      return `
        <div class="bg-white border border-slate-200 rounded-xl p-3.5 hover:shadow-sm transition space-y-2.5">
          <div class="flex items-start justify-between gap-3">
            <div class="flex items-center gap-3">
              <span class="w-6 h-6 rounded-full bg-slate-100 text-slate-700 font-bold text-xs flex items-center justify-center">
                #${rank}
              </span>
              <div>
                <h4 class="font-bold text-sm text-slate-900">${dest.name}, <span class="font-normal text-slate-500">${dest.country}</span></h4>
                <p class="text-[11px] text-slate-500 line-clamp-1">${dest.tagline}</p>
              </div>
            </div>
            <div class="text-right">
              <span class="inline-block bg-indigo-50 text-indigo-700 border border-indigo-200 font-bold text-xs px-2 py-0.5 rounded-md">
                ${dest.total_score} pts
              </span>
              <p class="text-[10px] text-slate-400 mt-0.5">${dest.estimated_cost}</p>
            </div>
          </div>

          <!-- Stacked Component Breakdown Bar -->
          <div class="space-y-1">
            <div class="w-full bg-slate-100 rounded-full h-2.5 flex overflow-hidden">
              <div style="width: ${cInterest}%" class="bg-indigo-500 h-full" title="Interest: +${cInterest} pts (${b.interest.note})"></div>
              <div style="width: ${cSeason}%" class="bg-emerald-500 h-full" title="Season: +${cSeason} pts (${b.season.note})"></div>
              <div style="width: ${cPopularity}%" class="bg-amber-500 h-full" title="Popularity: +${cPopularity} pts (${b.popularity.note})"></div>
              <div style="width: ${cFeasibility}%" class="bg-blue-500 h-full" title="Feasibility: +${cFeasibility} pts (${b.feasibility.note})"></div>
              <div style="width: ${cLive}%" class="bg-slate-400 h-full" title="Live: +${cLive} pts (${b.live.note})"></div>
              <div style="width: ${cFeedback}%" class="bg-rose-500 h-full" title="Feedback: +${cFeedback} pts (${b.feedback.note})"></div>
            </div>

            <!-- Notes & Mini Tags -->
            <div class="flex flex-wrap gap-2 text-[10px] text-slate-500 pt-1">
              <span>🎯 ${b.interest.note}</span>
              <span>•</span>
              <span>🍂 ${b.season.note}</span>
              <span>•</span>
              <span>🧭 Feasibility: ${b.feasibility.value * 100}%</span>
            </div>
          </div>
        </div>
      `;
    }

    function renderExcluded(excludedList) {
      return `
        <div class="mt-4 border border-rose-200 bg-rose-50/50 rounded-xl p-3 text-xs space-y-2">
          <div class="font-semibold text-rose-800 flex items-center gap-1.5">
            <i class="fa-solid fa-ban text-rose-600"></i>
            Excluded Destinations (${excludedList.length}) - Filtered by Hard Constraints
          </div>
          <ul class="divide-y divide-rose-100">
            ${excludedList.map(item => `
              <li class="py-1.5 flex justify-between items-center text-slate-700">
                <span class="font-medium">${item.name}</span>
                <span class="text-rose-600 text-[11px] italic">${item.reason}</span>
              </li>
            `).join("")}
          </ul>
        </div>
      `;
    }

    async function fetchRankings() {
      state.loading = true;
      state.error = null;
      renderUI();

      let url = `/api/ranking/${userId}?date=${encodeURIComponent(state.date)}&limit=10`;
      if (state.budget && Number(state.budget) > 0) {
        url += `&budget=${encodeURIComponent(state.budget)}`;
      }

      try {
        const res = await ctx.api(url);
        state.data = res;
      } catch (err) {
        state.error = err.message || "Failed to load rankings";
      } finally {
        state.loading = false;
        renderUI();
      }
    }

    // Initial load
    await fetchRankings();
  }
});
