// Interactive Timed Itinerary Editor UI Module
// Owner: Person C (Integrator)
// Displays day-by-day timed schedule (Activities, Transit, Meals, Rest),
// alternative suggestions modal, Finalize Itinerary, and Start Trip actions.

TravelModules.register("itinerary_editor", {
  async render(container, ctx) {
    const userId = ctx.userId;
    const tripId = ctx.tripId;

    if (!userId) {
      container.innerHTML = `<div class="p-6 text-center text-slate-500 text-sm">Please sign in to view your itinerary.</div>`;
      return;
    }

    if (!tripId) {
      container.innerHTML = `
        <div class="p-6 text-center text-slate-500 text-sm space-y-2">
          <i class="fa-solid fa-plane-departure text-3xl text-indigo-400"></i>
          <p class="font-medium">No trip selected.</p>
          <p class="text-xs text-slate-400">Please select an existing trip from the dropdown above, or plan a new trip from the dashboard.</p>
        </div>`;
      return;
    }

    let state = {
      loading: true,
      error: null,
      data: null,
      selectedDay: 1,
      altsModal: {
        open: false,
        activityId: null,
        loading: false,
        alternatives: []
      }
    };

    async function loadData() {
      state.loading = true;
      state.error = null;
      renderUI();
      try {
        const res = await ctx.api(`/api/trip-actions/${tripId}/timed-view`);
        state.data = res;
      } catch (err) {
        state.error = err.message || "Failed to load itinerary";
      } finally {
        state.loading = false;
        renderUI();
      }
    }

    function renderUI() {
      if (state.loading) {
        container.innerHTML = `
          <div class="p-10 text-center text-slate-500 text-sm">
            <i class="fa-solid fa-spinner fa-spin mr-2"></i> Loading timed itinerary...
          </div>`;
        return;
      }

      if (state.error) {
        container.innerHTML = `
          <div class="p-4 bg-rose-50 border border-rose-200 text-rose-700 text-xs rounded-xl">
            <i class="fa-solid fa-circle-exclamation mr-1.5"></i> ${state.error}
          </div>`;
        return;
      }

      const d = state.data;
      if (!d || !d.has_itinerary) {
        container.innerHTML = `
          <div class="p-8 text-center text-slate-600 text-sm space-y-3 bg-slate-50 rounded-2xl border border-slate-200">
            <i class="fa-solid fa-calendar-xmark text-4xl text-amber-500"></i>
            <h3 class="font-bold text-slate-800">Itinerary Not Generated Yet</h3>
            <p class="text-xs text-slate-500 max-w-md mx-auto">
              You haven't generated a day-by-day plan for ${d.trip.destination_name} yet.
              Generate one from your dashboard first.
            </p>
          </div>`;
        return;
      }

      const trip = d.trip;
      const tripStatus = d.trip_status;
      const days = d.days || [];
      const currentDay = days.find(x => x.day_number === state.selectedDay) || days[0];

      // Status Badge Styling
      let statusBadge = "";
      if (tripStatus === "active_trip") {
        statusBadge = `<span class="bg-emerald-100 text-emerald-800 border border-emerald-300 px-3 py-1 rounded-full text-xs font-bold flex items-center gap-1.5 animate-pulse">
          <i class="fa-solid fa-location-dot"></i> ACTIVE TRIP (LIVE)
        </span>`;
      } else if (tripStatus === "finalized") {
        statusBadge = `<span class="bg-blue-100 text-blue-800 border border-blue-300 px-3 py-1 rounded-full text-xs font-bold flex items-center gap-1.5">
          <i class="fa-solid fa-circle-check"></i> FINALIZED
        </span>`;
      } else {
        statusBadge = `<span class="bg-amber-100 text-amber-800 border border-amber-300 px-3 py-1 rounded-full text-xs font-bold flex items-center gap-1.5">
          <i class="fa-solid fa-pen-ruler"></i> PLANNING (EDITABLE)
        </span>`;
      }

      container.innerHTML = `
        <div class="space-y-4 text-slate-800">
          <!-- Trip Header Summary -->
          <div class="bg-gradient-to-r from-indigo-50 to-blue-50 border border-indigo-100 p-4 rounded-2xl flex flex-wrap justify-between items-center gap-3">
            <div>
              <div class="text-[11px] font-semibold text-indigo-600 uppercase tracking-wider">Itinerary Schedule</div>
              <h3 class="text-lg font-bold text-slate-900">${trip.destination_name}</h3>
              <p class="text-xs text-slate-500 flex items-center gap-2 mt-0.5">
                <span><i class="fa-solid fa-calendar mr-1"></i>${trip.start_date} → ${trip.end_date}</span>
                <span>•</span>
                <span><i class="fa-solid fa-clock mr-1"></i>${trip.duration_days} Days</span>
              </p>
            </div>
            <div>
              ${statusBadge}
            </div>
          </div>

          <!-- Day Navigation Tabs -->
          <div class="flex flex-wrap gap-1.5 border-b border-slate-200 pb-2">
            ${days.map(day => `
              <button data-day="${day.day_number}" class="day-tab px-3 py-1.5 rounded-lg text-xs font-semibold transition ${state.selectedDay === day.day_number ? 'bg-indigo-600 text-white shadow-sm' : 'bg-slate-100 hover:bg-slate-200 text-slate-700'}">
                Day ${day.day_number}
              </button>
            `).join("")}
          </div>

          <!-- Day Date Subtitle -->
          ${currentDay ? `
            <div class="flex justify-between items-center text-xs font-semibold text-slate-600 px-1">
              <span><i class="fa-regular fa-calendar-days mr-1 text-indigo-500"></i> ${currentDay.formatted_date}</span>
              <span class="text-[11px] text-slate-400 font-normal">Timed Schedule: Activities, Travel, Meals & Rest</span>
            </div>
          ` : ''}

          <!-- Timeline Blocks for the Day -->
          <div class="space-y-2.5">
            ${currentDay && currentDay.timeline ? currentDay.timeline.map(block => renderTimelineCard(block, d.itinerary.id)).join("") : ''}
          </div>

          <!-- Action Footer: Finalize & Start Trip -->
          <div class="mt-6 pt-4 border-t border-slate-200 flex flex-wrap justify-between items-center gap-3 bg-white p-3 rounded-2xl">
            <div class="text-xs text-slate-500">
              ${tripStatus === "planning" ? "Review and customize activities before finalizing." : ""}
              ${tripStatus === "finalized" ? "Your itinerary is locked. Ready to head out?" : ""}
              ${tripStatus === "active_trip" ? "🎉 Enjoy your journey! Real-time alerts are running." : ""}
            </div>
            <div class="flex items-center gap-2">
              ${tripStatus === "planning" ? `
                <button id="btnFinalizeTrip" class="bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-xs px-4 py-2 rounded-xl transition flex items-center gap-1.5 shadow-sm">
                  <i class="fa-solid fa-lock"></i> Finalize Itinerary
                </button>
              ` : ''}
              ${tripStatus === "finalized" ? `
                <button id="btnStartTrip" class="bg-emerald-600 hover:bg-emerald-700 text-white font-bold text-xs px-5 py-2.5 rounded-xl transition flex items-center gap-2 shadow-md animate-bounce">
                  <i class="fa-solid fa-plane-departure"></i> Start Trip
                </button>
              ` : ''}
              ${tripStatus === "active_trip" ? `
                <span class="bg-emerald-50 text-emerald-700 text-xs font-bold px-3 py-1.5 rounded-lg border border-emerald-200">
                  <i class="fa-solid fa-compass fa-spin mr-1"></i> Trip in Progress
                </span>
              ` : ''}
            </div>
          </div>

          <!-- LinUCB Alternative Suggestions Modal Container -->
          <div id="altsModalOverlay" class="${state.altsModal.open ? '' : 'hidden'} fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
            <div class="bg-white rounded-2xl max-w-md w-full p-5 shadow-2xl space-y-4 max-h-[85vh] overflow-y-auto">
              <div class="flex justify-between items-center border-b border-slate-100 pb-2">
                <div>
                  <h4 class="font-bold text-sm text-slate-900">Personalized Alternatives</h4>
                  <p class="text-[11px] text-slate-500">Recommended by LinUCB Bandit based on your preferences</p>
                </div>
                <button id="closeAltsBtn" class="text-slate-400 hover:text-slate-600 text-sm">✕</button>
              </div>

              <div id="altsModalBody">
                ${state.altsModal.loading ? `<div class="p-6 text-center text-slate-500 text-xs"><i class="fa-solid fa-spinner fa-spin mr-2"></i>Finding alternative activities...</div>` : ''}
                ${!state.altsModal.loading && state.altsModal.alternatives.length === 0 ? `<div class="p-4 text-center text-slate-400 text-xs">No suitable alternatives found.</div>` : ''}
                ${!state.altsModal.loading && state.altsModal.alternatives.map(alt => `
                  <div class="p-3 border border-slate-200 rounded-xl hover:border-indigo-400 hover:bg-indigo-50/40 transition space-y-2 mb-2">
                    <div class="flex justify-between items-start">
                      <div>
                        <h5 class="font-bold text-xs text-slate-900">${alt.title || alt.name}</h5>
                        <p class="text-[10px] text-slate-500">${alt.category} • ${alt.neighborhood || 'Nearby'}</p>
                      </div>
                      <span class="text-[10px] font-bold bg-indigo-100 text-indigo-700 px-1.5 py-0.5 rounded">
                        Score: ${(alt.predicted_reward || 0.8).toFixed(2)}
                      </span>
                    </div>
                    <p class="text-[11px] text-slate-600 line-clamp-2">${alt.description || ''}</p>
                    <button data-swap-id="${alt.id}" class="btn-swap-item w-full bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-xs py-1.5 rounded-lg transition">
                      Swap with this activity
                    </button>
                  </div>
                `).join("")}
              </div>
            </div>
          </div>
        </div>
      `;

      // Event Listeners
      container.querySelectorAll(".day-tab").forEach(b => {
        b.onclick = () => {
          state.selectedDay = parseInt(b.dataset.day, 10);
          renderUI();
        };
      });

      const finalizeBtn = container.querySelector("#btnFinalizeTrip");
      if (finalizeBtn) {
        finalizeBtn.onclick = async () => {
          try {
            await ctx.api(`/api/trip-actions/${tripId}/finalize?user_id=${userId}`, { method: "POST" });
            await loadData();
          } catch (e) {
            alert("Error finalizing trip: " + e.message);
          }
        };
      }

      const startBtn = container.querySelector("#btnStartTrip");
      if (startBtn) {
        startBtn.onclick = async () => {
          try {
            const res = await ctx.api(`/api/trip-actions/${tripId}/start?user_id=${userId}`, { method: "POST" });
            alert(res.message);
            await loadData();
          } catch (e) {
            alert("Error starting trip: " + e.message);
          }
        };
      }

      // Activity action listeners: Suggest & Remove
      container.querySelectorAll(".btn-suggest-alt").forEach(b => {
        b.onclick = () => openAlternativesModal(b.dataset.actId, d.itinerary.id);
      });

      container.querySelectorAll(".btn-remove-act").forEach(b => {
        b.onclick = async () => {
          if (!confirm("Are you sure you want to remove this activity from your schedule?")) return;
          try {
            await ctx.api(`/api/trip-actions/${tripId}/activity/${b.dataset.actId}?user_id=${userId}`, { method: "DELETE" });
            await loadData();
          } catch (e) {
            alert("Error removing activity: " + e.message);
          }
        };
      });

      const closeAlts = container.querySelector("#closeAltsBtn");
      if (closeAlts) closeAlts.onclick = () => { state.altsModal.open = false; renderUI(); };

      container.querySelectorAll(".btn-swap-item").forEach(b => {
        b.onclick = async () => {
          const replacementId = b.dataset.swapId;
          const targetActivityId = state.altsModal.activityId;
          try {
            await ctx.api(`/api/trip-actions/${tripId}/activity/${targetActivityId}/swap`, {
              method: "POST",
              body: { user_id: userId, replacement_activity_id: replacementId, is_trip_specific: true }
            });
            state.altsModal.open = false;
            await loadData();
          } catch (e) {
            alert("Error swapping activity: " + e.message);
          }
        };
      });
    }

    function renderTimelineCard(block, itineraryId) {
      // 1. Transit Block
      if (block.type === "transit") {
        return `
          <div class="flex items-center gap-3 py-1.5 px-3 bg-slate-100/70 border border-dashed border-slate-300 rounded-xl text-xs text-slate-600">
            <span class="w-6 h-6 rounded-full bg-slate-200 text-slate-600 flex items-center justify-center text-[10px]">
              <i class="fa-solid fa-route"></i>
            </span>
            <div class="flex-1 flex justify-between items-center">
              <div>
                <span class="font-semibold text-slate-700">${block.title}</span>
                <span class="text-slate-400 ml-1 text-[11px]">• ${block.description}</span>
              </div>
              <span class="text-[11px] text-slate-500 font-mono">${block.time_range}</span>
            </div>
          </div>`;
      }

      // 2. Meal / Dining Block
      if (block.type === "meal") {
        return `
          <div class="flex items-start gap-3 p-3 bg-amber-50/60 border border-amber-200 rounded-xl text-xs text-amber-900">
            <span class="w-7 h-7 rounded-lg bg-amber-100 text-amber-700 flex items-center justify-center text-xs mt-0.5">
              <i class="fa-solid fa-utensils"></i>
            </span>
            <div class="flex-1">
              <div class="flex justify-between items-start">
                <h5 class="font-bold text-amber-950">${block.title}</h5>
                <span class="text-[11px] font-mono text-amber-800 bg-amber-100/80 px-2 py-0.5 rounded-md font-semibold">${block.time_range}</span>
              </div>
              <p class="text-[11px] text-amber-700 mt-0.5">${block.description}</p>
            </div>
          </div>`;
      }

      // 3. Rest & Downtime Block
      if (block.type === "rest") {
        return `
          <div class="flex items-start gap-3 p-3 bg-emerald-50/60 border border-emerald-200 rounded-xl text-xs text-emerald-900">
            <span class="w-7 h-7 rounded-lg bg-emerald-100 text-emerald-700 flex items-center justify-center text-xs mt-0.5">
              <i class="fa-solid fa-mug-hot"></i>
            </span>
            <div class="flex-1">
              <div class="flex justify-between items-start">
                <h5 class="font-bold text-emerald-950">${block.title}</h5>
                <span class="text-[11px] font-mono text-emerald-800 bg-emerald-100/80 px-2 py-0.5 rounded-md font-semibold">${block.time_range}</span>
              </div>
              <p class="text-[11px] text-emerald-700 mt-0.5">${block.description}</p>
            </div>
          </div>`;
      }

      // 4. Sightseeing / Activity Block
      return `
        <div class="bg-white border border-slate-200 hover:border-indigo-300 rounded-xl p-3.5 transition shadow-2xs space-y-2">
          <div class="flex items-start justify-between gap-2">
            <div class="flex items-start gap-3">
              <span class="w-7 h-7 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center text-xs mt-0.5">
                <i class="fa-solid fa-monument"></i>
              </span>
              <div>
                <h5 class="font-bold text-sm text-slate-900">${block.title}</h5>
                <p class="text-[11px] text-slate-500">${block.category} • ${block.neighborhood || block.location_name || 'Destination Area'}</p>
              </div>
            </div>
            <div class="text-right">
              <span class="text-[11px] font-mono text-indigo-700 bg-indigo-50 font-semibold px-2 py-0.5 rounded-md">
                ${block.time_range}
              </span>
              <p class="text-[10px] text-slate-400 mt-0.5">Approx. $${block.cost_estimate || 0}</p>
            </div>
          </div>

          <p class="text-xs text-slate-600">${block.description}</p>

          <!-- Edit & Suggestion Buttons -->
          ${block.can_edit ? `
            <div class="pt-2 border-t border-slate-100 flex items-center justify-between text-xs">
              <button data-act-id="${block.activity_id}" class="btn-suggest-alt text-indigo-600 hover:text-indigo-800 font-semibold text-[11px] flex items-center gap-1">
                <i class="fa-solid fa-lightbulb text-amber-500"></i> Suggest Alternatives
              </button>
              <button data-act-id="${block.activity_id}" class="btn-remove-act text-rose-500 hover:text-rose-700 text-[11px] flex items-center gap-1">
                <i class="fa-solid fa-trash-can"></i> Remove
              </button>
            </div>
          ` : ''}
        </div>`;
    }

    async function openAlternativesModal(activityId, itineraryId) {
      state.altsModal.open = true;
      state.altsModal.activityId = activityId;
      state.altsModal.loading = true;
      state.altsModal.alternatives = [];
      renderUI();

      try {
        const res = await ctx.api(`/api/itinerary/alternatives/${itineraryId}/${activityId}?user_id=${userId}`);
        state.altsModal.alternatives = res.alternatives || [];
      } catch (err) {
        alert("Failed to load alternatives: " + err.message);
      } finally {
        state.altsModal.loading = false;
        renderUI();
      }
    }

    // Initial load
    await loadData();
  }
});
