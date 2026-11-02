// Places API Explorer & Dynamic Itinerary Planner
// Module ID: places
// Owner: Person C (Integrator)
// Allows travellers to dynamically search real locations anywhere in India,
// fetch real live attractions via API, and generate timed LinUCB itineraries.

TravelModules.register("places", {
  async render(container, ctx) {
    container.innerHTML = `
      <div class="space-y-6">
        <!-- Header Banner -->
        <div class="bg-gradient-to-r from-teal-900 to-indigo-900 text-white rounded-xl p-5 shadow-sm">
          <div class="flex items-center gap-3">
            <div class="w-10 h-10 rounded-lg bg-teal-500/20 flex items-center justify-center text-teal-300">
              <i class="fa-solid fa-location-dot text-lg"></i>
            </div>
            <div>
              <h3 class="text-lg font-bold">Real-Time India Places API</h3>
              <p class="text-xs text-teal-200">Dynamically geocode any location in India & fetch live attractions on-demand via OpenStreetMap & Wikipedia/Wikivoyage.</p>
            </div>
          </div>
        </div>

        <!-- Search Bar -->
        <div class="bg-white border border-slate-200 rounded-xl p-5 shadow-sm space-y-4">
          <div class="flex flex-col md:flex-row gap-3">
            <div class="relative flex-1">
              <i class="fa-solid fa-magnifying-glass absolute left-3 top-3 text-slate-400"></i>
              <input type="text" id="placesSearchInput" placeholder="Search any city or tourist hub in India (e.g., Manali, Goa, Jaipur, Pondicherry, Shimla)..."
                class="w-full pl-9 pr-4 py-2.5 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-teal-500" />
            </div>
            <button id="placesSearchBtn" class="px-5 py-2.5 bg-teal-600 hover:bg-teal-700 text-white text-sm font-semibold rounded-lg shadow-sm transition flex items-center justify-center gap-2">
              <i class="fa-solid fa-cloud-arrow-down"></i> Search API
            </button>
          </div>

          <!-- Quick Hub Chips -->
          <div>
            <span class="text-xs font-semibold text-slate-400 uppercase tracking-wider block mb-2">Popular Real-World Hubs:</span>
            <div class="flex flex-wrap gap-2" id="placesQuickChips">
              ${["Manali", "Goa", "Jaipur", "Varanasi", "Udaipur", "Munnar", "Leh Ladakh", "Rishikesh", "Pondicherry", "Amritsar", "Darjeeling", "Shimla"].map(c => `
                <button type="button" class="quick-chip-btn text-xs px-3 py-1.5 bg-slate-100 hover:bg-teal-50 hover:text-teal-700 text-slate-700 rounded-full border border-slate-200 transition font-medium" data-city="${c}">
                  <i class="fa-solid fa-map-pin text-teal-500 text-[10px] mr-1"></i> ${c}
                </button>
              `).join("")}
            </div>
          </div>
        </div>

        <!-- Trip Config Panel (Hidden by default, shown when city selected) -->
        <div id="placesPlanConfig" class="hidden bg-indigo-50 border border-indigo-200 rounded-xl p-5 space-y-3">
          <div class="flex items-center justify-between">
            <h4 class="text-sm font-bold text-indigo-900 flex items-center gap-2">
              <i class="fa-solid fa-sliders text-indigo-600"></i>
              Plan Real Itinerary for: <span id="selectedCityName" class="text-teal-700 font-extrabold"></span>
            </h4>
            <span class="text-xs bg-indigo-100 text-indigo-800 px-2 py-0.5 rounded font-medium" id="selectedCoords"></span>
          </div>

          <div class="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-2">
            <div>
              <label class="block text-xs font-medium text-slate-700 mb-1">Start Date</label>
              <input type="date" id="placesStartDate" class="w-full px-3 py-1.5 text-xs border border-slate-200 rounded-lg bg-white" value="2026-11-10" />
            </div>
            <div>
              <label class="block text-xs font-medium text-slate-700 mb-1">Duration</label>
              <select id="placesDuration" class="w-full px-3 py-1.5 text-xs border border-slate-200 rounded-lg bg-white">
                <option value="2">2 Days (Weekend Trip)</option>
                <option value="3" selected>3 Days (Short Holiday)</option>
                <option value="4">4 Days (Extended Trip)</option>
                <option value="5">5 Days (Full Experience)</option>
              </select>
            </div>
            <div>
              <label class="block text-xs font-medium text-slate-700 mb-1">Travel Pace</label>
              <select id="placesPace" class="w-full px-3 py-1.5 text-xs border border-slate-200 rounded-lg bg-white">
                <option value="relaxed">Relaxed (Slow Travel)</option>
                <option value="balanced" selected>Balanced (Standard)</option>
                <option value="packed">Packed (See Everything)</option>
              </select>
            </div>
          </div>

          <div class="flex items-center justify-end gap-2 pt-2">
            <button id="cancelPlanBtn" class="px-3 py-1.5 text-xs text-slate-600 hover:text-slate-800">Cancel</button>
            <button id="generateTripBtn" class="px-5 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold rounded-lg shadow-sm flex items-center gap-2">
              <i class="fa-solid fa-wand-magic-sparkles"></i> Generate Timed Itinerary via LinUCB
            </button>
          </div>
        </div>

        <!-- Search Results & Live Attractions View -->
        <div id="placesResultsContainer" class="space-y-4">
          <div class="text-center py-10 bg-slate-50 border border-slate-200 border-dashed rounded-xl">
            <div class="w-12 h-12 mx-auto rounded-full bg-slate-200 flex items-center justify-center text-slate-400 mb-3">
              <i class="fa-solid fa-magnifying-glass-location text-xl"></i>
            </div>
            <p class="text-sm font-semibold text-slate-700">Type any Indian city name above or click a popular hub</p>
            <p class="text-xs text-slate-400 max-w-md mx-auto mt-1">The system will dynamically query live geocoding and fetch real-time tourist attractions, viewpoints, and dining places.</p>
          </div>
        </div>
      </div>
    `;

    let selectedLocation = null;

    // Search function
    async function doSearch(query) {
      if (!query || query.trim().length < 2) return;
      const resBox = document.getElementById("placesResultsContainer");
      resBox.innerHTML = `
        <div class="p-8 text-center text-slate-500">
          <i class="fa-solid fa-spinner fa-spin text-2xl text-teal-600 mb-2"></i>
          <p class="text-xs">Querying OpenStreetMap Nominatim for "${query}"...</p>
        </div>
      `;

      try {
        const data = await ctx.api(`/api/places/search?q=${encodeURIComponent(query)}`);
        const results = data.results || [];

        if (results.length === 0) {
          resBox.innerHTML = `
            <div class="p-6 text-center text-slate-400 bg-white border border-slate-200 rounded-xl">
              <p class="text-sm font-semibold text-slate-600">No matching locations found for "${query}"</p>
              <p class="text-xs text-slate-400 mt-1">Try another city or check spelling.</p>
            </div>
          `;
          return;
        }

        resBox.innerHTML = `
          <div class="space-y-3">
            <div class="flex items-center justify-between text-xs text-slate-500 px-1">
              <span>Found <strong>${results.length}</strong> matching locations in India</span>
              <span class="text-teal-700 font-medium"><i class="fa-solid fa-bolt mr-1"></i>Live Geocoding</span>
            </div>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
              ${results.map((loc, idx) => `
                <div class="bg-white border border-slate-200 hover:border-teal-400 rounded-xl p-4 shadow-sm hover:shadow transition flex flex-col justify-between">
                  <div>
                    <div class="flex items-start justify-between gap-2">
                      <h4 class="font-bold text-slate-900 text-sm">${loc.city}</h4>
                      <span class="text-[10px] uppercase font-bold bg-teal-50 text-teal-700 px-2 py-0.5 rounded border border-teal-200">${loc.state}</span>
                    </div>
                    <p class="text-xs text-slate-500 mt-1 line-clamp-2">${loc.display_name}</p>
                    <div class="text-[11px] text-slate-400 mt-2 font-mono flex items-center gap-2">
                      <i class="fa-solid fa-crosshairs text-teal-500"></i> ${loc.latitude.toFixed(4)}, ${loc.longitude.toFixed(4)}
                    </div>
                  </div>

                  <div class="mt-4 pt-3 border-t border-slate-100 flex items-center gap-2">
                    <button class="view-attractions-btn flex-1 py-1.5 px-3 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold rounded-lg transition"
                      data-idx="${idx}">
                      <i class="fa-solid fa-eye text-slate-500 mr-1"></i> View Places
                    </button>
                    <button class="select-plan-btn flex-1 py-1.5 px-3 bg-teal-600 hover:bg-teal-700 text-white text-xs font-semibold rounded-lg transition shadow-sm"
                      data-idx="${idx}">
                      <i class="fa-solid fa-route mr-1"></i> Plan Trip
                    </button>
                  </div>
                </div>
              `).join("")}
            </div>
            <div id="liveAttractionsDrawer" class="hidden mt-4"></div>
          </div>
        `;

        // Bind buttons
        document.querySelectorAll(".view-attractions-btn").forEach(btn => {
          btn.onclick = () => {
            const loc = results[parseInt(btn.dataset.idx)];
            showAttractions(loc);
          };
        });

        document.querySelectorAll(".select-plan-btn").forEach(btn => {
          btn.onclick = () => {
            const loc = results[parseInt(btn.dataset.idx)];
            openPlanConfig(loc);
          };
        });

      } catch (err) {
        resBox.innerHTML = `
          <div class="p-6 text-center text-rose-600 bg-rose-50 border border-rose-200 rounded-xl text-xs">
            Failed to search locations: ${err.message}
          </div>
        `;
      }
    }

    // Show attractions for a location
    async function showAttractions(loc) {
      const drawer = document.getElementById("liveAttractionsDrawer");
      drawer.classList.remove("hidden");
      drawer.innerHTML = `
        <div class="bg-slate-900 text-white rounded-xl p-5 space-y-4">
          <div class="flex items-center justify-between">
            <h4 class="font-bold text-sm text-teal-300 flex items-center gap-2">
              <i class="fa-solid fa-compass"></i> Live Attractions for ${loc.city} (${loc.state})
            </h4>
            <span class="text-xs text-slate-400">Fetching live from Wikivoyage & Wikipedia...</span>
          </div>
          <div class="py-6 text-center text-xs text-slate-400">
            <i class="fa-solid fa-spinner fa-spin text-lg text-teal-400 mb-2"></i>
            <p>Retrieving real sights, viewpoints, and dining spots...</p>
          </div>
        </div>
      `;

      try {
        const data = await ctx.api(`/api/places/attractions?city=${encodeURIComponent(loc.city)}&lat=${loc.latitude}&lon=${loc.longitude}`);
        const list = data.attractions || [];

        if (list.length === 0) {
          drawer.innerHTML = `
            <div class="bg-slate-900 text-white rounded-xl p-5 text-center text-xs text-slate-400">
              No specific places found via live API. Click 'Plan Trip' to synthesize structured itinerary.
            </div>
          `;
          return;
        }

        drawer.innerHTML = `
          <div class="bg-slate-900 text-white rounded-xl p-5 space-y-4 shadow-lg border border-slate-700">
            <div class="flex items-center justify-between border-b border-slate-800 pb-3">
              <div>
                <h4 class="font-bold text-sm text-teal-300 flex items-center gap-2">
                  <i class="fa-solid fa-location-dot"></i> Real Places in ${loc.city} (${list.length} found)
                </h4>
                <p class="text-xs text-slate-400">Verified sights with coordinates and categories for LinUCB scheduling.</p>
              </div>
              <button id="closeDrawerBtn" class="text-slate-400 hover:text-white text-xs px-2 py-1 rounded bg-slate-800">
                Close
              </button>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              ${list.map(a => `
                <div class="bg-slate-800/80 border border-slate-700 rounded-lg p-3 flex flex-col justify-between">
                  <div>
                    <div class="flex items-start justify-between gap-2">
                      <span class="font-bold text-xs text-white">${a.name}</span>
                      <span class="text-[9px] uppercase px-1.5 py-0.5 rounded font-mono ${
                        a.category === 'culture_history' ? 'bg-amber-900/60 text-amber-300' :
                        a.category === 'nature_outdoors' ? 'bg-emerald-900/60 text-emerald-300' :
                        a.category === 'scenic' ? 'bg-sky-900/60 text-sky-300' :
                        a.category === 'food_dining' ? 'bg-rose-900/60 text-rose-300' :
                        'bg-purple-900/60 text-purple-300'
                      }">${a.category.replace('_', ' ')}</span>
                    </div>
                    <p class="text-[11px] text-slate-300 mt-2 line-clamp-3">${a.description}</p>
                  </div>
                  <div class="mt-3 pt-2 border-t border-slate-700/60 flex items-center justify-between text-[10px] text-slate-400">
                    <span><i class="fa-regular fa-clock mr-1"></i>${a.duration_minutes}m</span>
                    <span>${a.cost_tier.toUpperCase()}</span>
                  </div>
                </div>
              `).join("")}
            </div>

            <div class="pt-2 text-right">
              <button id="planFromDrawerBtn" class="px-4 py-2 bg-teal-500 hover:bg-teal-600 text-slate-900 font-bold text-xs rounded-lg shadow transition">
                <i class="fa-solid fa-route mr-1"></i> Plan Itinerary with These Places
              </button>
            </div>
          </div>
        `;

        document.getElementById("closeDrawerBtn").onclick = () => drawer.classList.add("hidden");
        document.getElementById("planFromDrawerBtn").onclick = () => openPlanConfig(loc);

      } catch (err) {
        drawer.innerHTML = `
          <div class="bg-slate-900 text-rose-400 rounded-xl p-4 text-xs text-center">
            Error loading attractions: ${err.message}
          </div>
        `;
      }
    }

    // Open configuration box
    function openPlanConfig(loc) {
      selectedLocation = loc;
      const box = document.getElementById("placesPlanConfig");
      box.classList.remove("hidden");
      document.getElementById("selectedCityName").innerText = `${loc.city}, ${loc.state}`;
      document.getElementById("selectedCoords").innerText = `${loc.latitude.toFixed(4)}, ${loc.longitude.toFixed(4)}`;
      box.scrollIntoView({ behavior: "smooth" });
    }

    document.getElementById("cancelPlanBtn").onclick = () => {
      document.getElementById("placesPlanConfig").classList.add("hidden");
    };

    // Plan Dynamic Trip
    document.getElementById("generateTripBtn").onclick = async () => {
      if (!selectedLocation) return;
      if (!ctx.userId) {
        alert("Please log in first to save your trip itinerary.");
        return;
      }

      const btn = document.getElementById("generateTripBtn");
      btn.disabled = true;
      btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin mr-1"></i> Scheduling LinUCB Itinerary...`;

      try {
        const payload = {
          user_id: ctx.userId,
          city_name: selectedLocation.city,
          state: selectedLocation.state,
          latitude: selectedLocation.latitude,
          longitude: selectedLocation.longitude,
          start_date: document.getElementById("placesStartDate").value,
          duration_days: parseInt(document.getElementById("placesDuration").value),
          pace_preference: document.getElementById("placesPace").value,
          budget_tier: "balanced"
        };

        const res = await ctx.api("/api/places/plan-trip", {
          method: "POST",
          body: payload
        });

        // Trip generated successfully!
        // Show success alert and switch to itinerary editor tab
        alert(`Success! Generated a ${payload.duration_days}-day itinerary for ${selectedLocation.city} with ${res.places_fetched_count} real places.`);
        
        // Switch companion modal tab to 'itinerary_editor'
        document.querySelectorAll("#companionTabs button").forEach(b => {
          if (b.dataset.id === "itinerary_editor") {
            b.click();
          }
        });

      } catch (e) {
        alert("Failed to plan trip: " + e.message);
      } finally {
        btn.disabled = false;
        btn.innerHTML = `<i class="fa-solid fa-wand-magic-sparkles mr-1"></i> Generate Timed Itinerary via LinUCB`;
      }
    };

    // Bind Search Input & Button
    document.getElementById("placesSearchBtn").onclick = () => {
      const q = document.getElementById("placesSearchInput").value;
      doSearch(q);
    };

    document.getElementById("placesSearchInput").onkeydown = (e) => {
      if (e.key === "Enter") {
        doSearch(e.target.value);
      }
    };

    // Bind Quick Chips
    document.querySelectorAll(".quick-chip-btn").forEach(chip => {
      chip.onclick = () => {
        const city = chip.dataset.city;
        document.getElementById("placesSearchInput").value = city;
        doSearch(city);
      };
    });
  }
});
