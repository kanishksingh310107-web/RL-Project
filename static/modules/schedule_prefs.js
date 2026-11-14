/* Person B: trip schedule preference form and client-side validation. */
(() => {
  "use strict";
  const byId = id => document.getElementById(id);
  const mount = document.getElementById("schedulePrefsMount");
  if (!mount) return;
  const field = (id, label, value, help = "") => `<label class="block text-slate-700">${label}<input id="${id}" type="time" value="${value}" class="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-2 py-1.5"><span id="${id}Error" class="block text-rose-700 text-[10px] mt-0.5" role="alert"></span>${help ? `<small class="text-slate-500">${help}</small>` : ""}</label>`;
  mount.innerHTML = `<section class="rounded-xl border border-indigo-200 bg-indigo-50/50 p-3.5 space-y-3" aria-labelledby="schedulePrefsTitle">
    <h4 id="schedulePrefsTitle" class="font-bold text-slate-800">Daily schedule</h4>
    <div class="grid grid-cols-2 gap-2">
      ${field("hotelArrivalTime", "Hotel arrival (day 1)", "14:00")}
      ${field("hotelDepartureTime", "Hotel departure (last day)", "11:00")}
      ${field("wakeTime", "Wake time", "07:00")}
      ${field("activityStartTime", "Activity start time", "09:00")}
      ${field("bedTime", "Bed time", "21:00", "Earlier clock times are treated as after midnight.")}
    </div>
    <div><div class="flex items-center justify-between"><strong class="text-slate-700">Reserved free time</strong><button id="addFreeBlockBtn" type="button" class="px-2 py-1 rounded border bg-white">Add block</button></div>
      <div id="freeBlocksList" class="space-y-2 mt-2"></div><span id="freeBlocksError" class="block text-rose-700 text-[10px]" role="alert"></span>
    </div>
  </section>`;
  const ids = ["hotelArrivalTime", "hotelDepartureTime", "wakeTime", "activityStartTime", "bedTime"];
  const minutes = (value) => {
    if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(value || "")) return NaN;
    const [h, m] = value.split(":").map(Number); return h * 60 + m;
  };
  function addBlock(block = {}) {
    const list = document.getElementById("freeBlocksList");
    if (list.children.length >= 10) { document.getElementById("freeBlocksError").textContent = "You can add up to 10 blocks."; return; }
    const row = document.createElement("div");
    row.className = "grid grid-cols-2 sm:grid-cols-5 gap-1.5 rounded-lg border bg-white p-2";
    row.innerHTML = `<label class="text-slate-600">Day <select class="freeDay w-full border rounded p-1"><option value="">Every day</option></select></label>
      <label class="text-slate-600">Start <input class="freeStart w-full border rounded p-1" type="time" value="${block.start || "12:00"}"></label>
      <label class="text-slate-600">End <input class="freeEnd w-full border rounded p-1" type="time" value="${block.end || "13:00"}"></label>
      <label class="text-slate-600 col-span-2">Label <input class="freeLabel w-full border rounded p-1" maxlength="60" value=""></label>
      <button type="button" class="removeFreeBlock col-span-2 sm:col-span-1 text-rose-700 underline self-end">Remove</button>
      <span class="freeError col-span-full text-rose-700 text-[10px]" role="alert"></span>`;
    row.querySelector(".freeLabel").value = block.label || "";
    row.querySelector(".removeFreeBlock").addEventListener("click", () => row.remove());
    const daySelect = row.querySelector(".freeDay");
    const days = Math.max(1, Math.min(366, Math.round((new Date(document.getElementById("tripEndDateInput")?.value || "") - new Date(document.getElementById("tripStartDateInput")?.value || "")) / 86400000) + 1 || 1));
    for (let day = 1; day <= days; day++) daySelect.add(new Option(`Day ${day}`, String(day)));
    if (block.day) daySelect.value = String(block.day);
    list.appendChild(row);
  }
  document.getElementById("addFreeBlockBtn").addEventListener("click", () => addBlock());
  function readPrefs() {
    const prefs = {
      hotel_arrival_time: byId("hotelArrivalTime").value,
      hotel_departure_time: byId("hotelDepartureTime").value,
      wake_time: byId("wakeTime").value,
      bed_time: byId("bedTime").value,
      activity_start_time: byId("activityStartTime").value,
      free_blocks: [...document.querySelectorAll("#freeBlocksList > div")].map(row => ({
        day: row.querySelector(".freeDay").value ? Number(row.querySelector(".freeDay").value) : null,
        start: row.querySelector(".freeStart").value, end: row.querySelector(".freeEnd").value,
        label: row.querySelector(".freeLabel").value.trim()
      }))
    };
    return prefs;
  }
  function show(fieldId, message) {
    const error = document.getElementById(`${fieldId}Error`);
    if (error) error.textContent = message;
  }
  const timedSchedules = new Map();
  function renderMarkers(trip) {
    const prefs = trip?.schedule_prefs;
    if (!markers || !prefs) return;
    markers.replaceChildren();
    const panel = document.createElement("div");
    panel.className = "mb-3 rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-2 text-xs text-indigo-900";
    const heading = document.createElement("strong"); heading.textContent = "Your schedule preferences"; panel.appendChild(heading);
    const details = document.createElement("p");
    details.textContent = `Day 1 hotel arrival ${prefs.hotel_arrival_time} · Last day hotel departure ${prefs.hotel_departure_time} · Activities ${prefs.activity_start_time}–${prefs.bed_time}`;
    panel.appendChild(details);
    (prefs.free_blocks || []).forEach(block => {
      const line = document.createElement("p"); line.textContent = `${block.day ? `Day ${block.day}` : "Every day"}: ${block.start}–${block.end} · ${block.label}`; panel.appendChild(line);
    });
    const schedule = timedSchedules.get(trip.id);
    if (schedule) (schedule.days || []).forEach(day => {
      const dayHeader = document.createElement("strong");
      dayHeader.className = "block mt-2";
      dayHeader.textContent = `Day ${day.day_number}${day.arrival_marker ? ` · Hotel arrival ${day.arrival_marker}` : ""}${day.departure_marker ? ` · Hotel departure ${day.departure_marker}` : ""}`;
      panel.appendChild(dayHeader);
      (day.slots || []).forEach(slot => {
        const line = document.createElement("p");
        line.textContent = `${slot.start_time}–${slot.end_time} · ${slot.title}`;
        panel.appendChild(line);
      });
      if (day.note) { const note = document.createElement("p"); note.className = "text-amber-800"; note.textContent = day.note; panel.appendChild(note); }
    });
    markers.appendChild(panel);
  }
  async function generateTimedSchedule(tripId, userId) {
    const response = await originalFetch(`/api/itinerary/timed/generate/${encodeURIComponent(tripId)}?user_id=${encodeURIComponent(userId || "")}`, { method: "POST" });
    if (!response.ok) throw new Error("Could not refresh the timed schedule.");
    const result = await response.json();
    timedSchedules.set(tripId, result);
    const trip = typeof activeUserTrips !== "undefined" && activeUserTrips.find(item => item.id === tripId);
    if (trip) renderMarkers(trip);
  }
  function validate() {
    [...ids].forEach(id => show(id, ""));
    document.getElementById("freeBlocksError").textContent = "";
    document.querySelectorAll(".freeError").forEach(el => el.textContent = "");
    let valid = true;
    const p = readPrefs();
    for (const id of ids) if (!Number.isFinite(minutes(document.getElementById(id).value))) { show(id, "Enter a valid time in 24-hour format."); valid = false; }
    const start = minutes(p.activity_start_time), bedRaw = minutes(p.bed_time);
    if (minutes(p.wake_time) > start) { show("activityStartTime", "Activity start time must be at or after wake time."); valid = false; }
    const bed = bedRaw <= start ? bedRaw + 1440 : bedRaw;
    if (Number.isFinite(start) && Number.isFinite(bed) && bed - start < 60) { show("bedTime", "Bed time must leave at least 60 minutes for one activity."); valid = false; }
    if (Number.isFinite(start) && Number.isFinite(bed) && bed - start > 18 * 60) { show("bedTime", "The daily activity window cannot exceed 18 hours."); valid = false; }
    const arrival = minutes(p.hotel_arrival_time), departure = minutes(p.hotel_departure_time);
    const startDate = document.getElementById("tripStartDateInput")?.value, endDate = document.getElementById("tripEndDateInput")?.value;
    if (startDate && endDate && startDate === endDate && Number.isFinite(arrival) && arrival >= departure) { show("hotelArrivalTime", "Hotel arrival must be before departure on a same-day trip."); valid = false; }
    if (startDate && endDate && startDate === endDate && Number.isFinite(start) && Number.isFinite(arrival) && Number.isFinite(departure)) {
      const firstActivity = Math.max(start, arrival + 60);
      if (departure - 60 - firstActivity < 60) { show("hotelDepartureTime", "Hotel departure must leave at least one activity after transfer buffers."); valid = false; }
    }
    const sorted = [];
    [...document.querySelectorAll("#freeBlocksList > div")].forEach(row => {
      const s = minutes(row.querySelector(".freeStart").value), er = minutes(row.querySelector(".freeEnd").value);
      const e = er < s ? er + 1440 : er;
      const label = row.querySelector(".freeLabel").value.trim();
      let error = "";
      if (!Number.isFinite(s) || !Number.isFinite(er)) error = "Enter valid start and end times.";
      else if (!label) error = "Add a label for this free block.";
      else if (label.length > 60) error = "Keep labels to 60 characters or fewer.";
      else if (e === s) error = "Start and end must be different.";
      let relativeStart = s;
      while (relativeStart < start) relativeStart += 1440;
      const relativeEnd = relativeStart + (e - s);
      if (!error && (relativeStart < start || relativeEnd > bed)) error = "Keep this block inside the daily activity window.";
      if (error) { row.querySelector(".freeError").textContent = error; valid = false; }
      else sorted.push([relativeStart, relativeEnd, row, row.querySelector(".freeDay").value || null]);
    });
    sorted.sort((a,b) => a[0]-b[0]);
    for (let i=0; i<sorted.length; i++) for (let j=i+1; j<sorted.length; j++) {
      if ((!sorted[i][3] || !sorted[j][3] || sorted[i][3] === sorted[j][3]) && sorted[i][0] < sorted[j][1] && sorted[j][0] < sorted[i][1]) {
        sorted[j][2].querySelector(".freeError").textContent = "Free time blocks cannot overlap."; valid = false;
      }
    }
    const dateDays = Math.max(1, Math.min(366, Math.round((new Date(endDate || "") - new Date(startDate || "")) / 86400000) + 1 || 1));
    for (let day=1; day<=dateDays; day++) {
      let windowStart = day === 1 ? Math.max(start, arrival + 60) : start;
      let leave = departure;
      if (bedRaw <= start && leave <= bedRaw) leave += 1440;
      const windowEnd = day === dateDays ? Math.min(bed, leave - 60) : bed;
      const relevant = sorted.filter(item => !item[3] || Number(item[3]) === day).map(item => [item[0],item[1]]).sort((a,b)=>a[0]-b[0]);
      let cursor = windowStart, maxGap = 0;
      for (const [s,e] of relevant) {
        if (s < windowEnd && e > windowStart) { maxGap = Math.max(maxGap,Math.min(s,windowEnd)-cursor); cursor = Math.max(cursor,e); }
      }
      maxGap = Math.max(maxGap,windowEnd-cursor);
      if (maxGap < 60) {
        const row = sorted.find(item => !item[3] || Number(item[3]) === day)?.[2];
        if (row) row.querySelector(".freeError").textContent = `Free blocks leave no activity window on day ${day}.`;
        else show(day === 1 ? "hotelArrivalTime" : "hotelDepartureTime", `Hotel buffers leave no activity window on day ${day}.`);
        valid = false;
      }
    }
    if (!valid) document.querySelector("#tripCreateForm [aria-invalid='true']")?.focus();
    return valid;
  }
  for (const id of ids) document.getElementById(id).addEventListener("input", () => show(id, ""));
  document.getElementById("tripCreateForm").addEventListener("submit", event => {
    if (!validate()) { event.preventDefault(); event.stopImmediatePropagation(); }
  }, true);

  const originalFetch = window.fetch.bind(window);
  window.fetch = async (input, init = {}) => {
    const url = typeof input === "string" ? input : input.url;
    const method = String(init.method || (typeof input !== "string" ? input.method : "GET")).toUpperCase();
    if (method === "POST" || method === "PATCH") {
      try {
        const body = JSON.parse(init.body || "{}");
        const pathname = new URL(url, location.href).pathname;
        if (/^\/api\/trips\/[^/]+$/.test(pathname) || pathname === "/api/places/plan-dynamic") {
          if (url.includes("/api/places/plan-dynamic")) {
            body.trip_preferences = body.trip_preferences || {};
            body.trip_preferences.schedule_prefs = readPrefs();
          } else body.schedule_prefs = readPrefs();
          init = { ...init, body: JSON.stringify(body) };
        }
      } catch (_) { /* Requests without JSON bodies pass through unchanged. */ }
    }
    const response = await originalFetch(input, init);
    if (!response.ok && (url.includes("/api/trips/") || url.includes("/api/places/plan-dynamic"))) {
      try {
        const body = await response.clone().json();
        if (body.field === "schedule_prefs" || body.field?.startsWith("schedule_prefs.")) {
          show("activityStartTime", body.detail || "Check your schedule preferences.");
        }
      } catch (_) { /* The calling flow presents its regular request error. */ }
    }
    if (response.ok) {
      try {
        if (method === "POST" && url.includes("/api/itinerary/generate/")) {
          const tripId = url.split("/api/itinerary/generate/")[1].split(/[?/#]/)[0];
          const userId = new URL(url, location.href).searchParams.get("user_id");
          await generateTimedSchedule(tripId, userId);
        } else if (url.includes("/api/places/plan-dynamic")) {
          const result = await response.clone().json();
          if (result.trip?.id) await generateTimedSchedule(result.trip.id, result.trip.user_id);
        } else if (method === "PATCH" && url.match(/\/api\/trips\/[^/?]+/)) {
          const result = await response.clone().json();
          if (result.id) await generateTimedSchedule(result.id, result.user_id);
        } else if (method === "POST" && (url.includes("/api/trip-actions/") || url.includes("/api/itinerary/feedback/")) && typeof currentPlannedTripId !== "undefined") {
          const trip = typeof activeUserTrips !== "undefined" && activeUserTrips.find(item => item.id === currentPlannedTripId);
          if (trip) await generateTimedSchedule(trip.id, trip.user_id);
        }
      } catch (_) { /* The trip can still be used if the timed schedule refresh fails. */ }
    }
    return response;
  };

  function fill(prefs) {
    if (!prefs) return;
    byId("hotelArrivalTime").value = prefs.hotel_arrival_time || "14:00";
    byId("hotelDepartureTime").value = prefs.hotel_departure_time || "11:00";
    byId("wakeTime").value = prefs.wake_time || "07:00";
    byId("bedTime").value = prefs.bed_time || "21:00";
    byId("activityStartTime").value = prefs.activity_start_time || "09:00";
    document.getElementById("freeBlocksList").replaceChildren();
    (prefs.free_blocks || []).forEach(addBlock);
  }
  if (typeof window.editSelectedTrip === "function") {
    const originalEdit = window.editSelectedTrip;
    window.editSelectedTrip = async (...args) => {
      const result = await originalEdit(...args);
      const tripId = typeof editingTripId !== "undefined" ? editingTripId : "";
      if (tripId) {
        try { const response = await originalFetch(`/api/trips/detail/${encodeURIComponent(tripId)}`); if (response.ok) fill((await response.json()).schedule_prefs); }
        catch (_) { /* Keep the entered defaults visible if loading fails. */ }
      }
      return result;
    };
  }
  const markers = document.getElementById("scheduleMarkersMount");
  const days = document.getElementById("itineraryDaysContainer");
  if (markers && days) new MutationObserver(() => {
    try {
      const trip = typeof activeUserTrips !== "undefined" && activeUserTrips.find(item => item.id === currentPlannedTripId);
      renderMarkers(trip);
    } catch (_) { /* Markers are optional while another trip is loading. */ }
  }).observe(days, { childList: true, subtree: true });
})();
