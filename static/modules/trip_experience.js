/* UI: trip workspace. The server owns schedules, acceptance and runtime state. */
(() => {
  'use strict';
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const minutes = value => /^([01]\d|2[0-3]):[0-5]\d$/.test(value || '')
    ? Number(value.slice(0,2))*60+Number(value.slice(3,5)) : NaN;
  const indiaToday = (date = new Date()) => {
    const parts=new Intl.DateTimeFormat('en', {timeZone:'Asia/Kolkata',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(date);
    const part=key=>parts.find(p=>p.type===key).value;
    return `${part('year')}-${part('month')}-${part('day')}`;
  };
  const publicText = value => /linucb|bandit|sherman|state.vector|reinforcement|policy.weights|feature.dimension/i.test(String(value || '')) ? 'Personalised using your travel preferences and feedback.' : String(value || '');
  function matchLabel(item) {
    const score = Number(item.calibrated_match_score);
    return item.score_calibrated === true && Number.isFinite(score) && score >= 0 && score <= 100
      ? `${Math.round(score)}% preference match` : publicText(item.match_label) || 'Recommended for you';
  }
  function dateErrors(start, end, today = indiaToday(), editing = false) {
    const errors = {};
    const valid = value => /^\d{4}-\d{2}-\d{2}$/.test(value || '') && !Number.isNaN(Date.parse(value+'T00:00:00Z')) && new Date(value+'T00:00:00Z').toISOString().slice(0,10) === value;
    if (!valid(start)) errors.tripStartDateInput = 'Choose a valid departure date.';
    else if (!editing && start < today) errors.tripStartDateInput = 'Departure cannot be before today in India.';
    if (!valid(end)) errors.tripEndDateInput = 'Choose a valid return date.';
    else if (valid(start) && end < start) errors.tripEndDateInput = 'Return must be on or after departure.';
    else if (valid(start) && (Date.parse(end)-Date.parse(start))/86400000 >= 90) errors.tripEndDateInput = 'Keep trips to 90 days or fewer.';
    return errors;
  }
  function access(snapshot) {
    return {pre:!!snapshot, live:snapshot?.status === 'live', post:snapshot?.status === 'completed', edit:['draft','finalized'].includes(snapshot?.status)};
  }
  const occurrenceId = block => block.itinerary_activity_id || block.occurrence_id || block.id || null;
  const acceptance = block => ['accepted','rejected'].includes(block.acceptance_status) ? block.acceptance_status : 'unreviewed';
  function isHomeDestination(item, profile) {
    profile=profile || (typeof state!=='undefined'?state.currentProfile:null) || {};
    if(item.excluded_home_area===true)return true;
    if(profile.residence_country!=='IN'||!profile.residence_city)return false;
    const normal=value=>String(value||'').normalize('NFKC').toLocaleLowerCase().replace(/[^\p{L}\p{N}]+/gu,' ').trim();
    const home=normal(profile.residence_city);
    return [item.city,item.name,item.destination_name].some(value=>` ${normal(value)} `.includes(` ${home} `));
  }
  const finishedDays = s => s?.status==='completed'?s.total_days:s?.phase==='day_summary'?s.runtime.current_day:Math.max(0,(s?.runtime?.current_day||1)-1);
  const api = async (url, options = {}) => {
    const controller = new AbortController(), timer = setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch(url, {...options,signal:controller.signal,headers:{'Content-Type':'application/json',...options.headers},body: options.body && typeof options.body !== 'string' ? JSON.stringify(options.body) : options.body});
      const data = response.status===204 ? {} : await response.json().catch(() => {throw new Error('The server response could not be read. Your entries are kept; please retry.');});
      if (!response.ok) { const error = new Error(publicText(typeof data.detail === 'string' ? data.detail : 'The request could not be completed. Please retry.')); error.field=data.field; error.status=response.status; throw error; }
      return data;
    } catch (error) {
      if(error.name === 'AbortError') throw new Error('The request timed out. Your entries are kept. Retry when connected.');
      if(error instanceof TypeError) throw new Error('Connection failed. Your entries are kept. Please retry.');
      throw error;
    } finally { clearTimeout(timer); }
  };
  let capabilities = {}, snapshot = null, snapshotTrip = null;
  const user = () => typeof state !== 'undefined' ? state.currentUser : null;
  const query = () => `user_id=${encodeURIComponent(user()?.user_id || '')}`;
  const can = key => capabilities[key] === true;
  const getSnapshot = id => snapshotTrip === id ? snapshot : null;
  const Trip = window.TripExperience = {esc,indiaToday,publicText,matchLabel,dateErrors,access,occurrenceId,acceptance,isHomeDestination,finishedDays,api,can,getSnapshot,query};
  if (typeof document === 'undefined') return;
  const el = id => document.getElementById(id);
  const form = el('tripCreateForm');
  const notice = (message, target = el('teRouteNotice')) => { if(target) { target.textContent=message; target.hidden=!message; } };
  function fieldError(id, message) {
    const input=el(id); if(!input) return;
    let error=el(id+'UiError');
    if(!error) { error=document.createElement('span'); error.id=id+'UiError'; error.className='te-error'; error.setAttribute('role','alert'); input.after(error); }
    error.textContent=message || ''; input.setAttribute('aria-invalid',message?'true':'false');
    input.setAttribute('aria-describedby',error.id);
  }
  Trip.allowPlanning = () => {
    if(!user()) { showView('auth'); return false; }
    if(!state.profileStatus?.complete) { openPersonalProfileModal(); return false; }
    return true;
  };
  async function loadCapabilities() {
    try { capabilities=await api(`/api/trip-experience/capabilities?${query()}`); }
    catch (_) { capabilities={}; }
    document.querySelectorAll('[data-te-capability]').forEach(node => { node.disabled=!can(node.dataset.teCapability); });
    notice(can('schedule_preferences_v2') ? '' : 'Some new scheduling options await the scheduling update. Your existing trip settings remain available.',el('teCapabilityNotice'));
  }
  const timeField = (id,label,value) => `<label>${label}<input type="time" id="${id}" value="${value}" required></label>`;
  const numberField = (id,label,value,min,max) => `<label>${label}<input type="number" id="${id}" value="${value}" min="${min}" max="${max}" step="1" required></label>`;
  // Form setup, draft persistence, routing and request serialization share these.
  let budgetTouched=false, overridesHost, addMealOverride, suggestProfileBudget;
  if(form) {
    const extra=document.createElement('section'); extra.className='te-card'; extra.id='teTripPreferences';
    extra.innerHTML=`<h3>Travel plans & personal time</h3><p id="teCapabilityNotice" role="status"></p>
      <input type="hidden" id="teTripType" value="solo">
      <input type="hidden" id="teCreationRequestId" value="">
      <fieldset data-te-capability="schedule_preferences_v2" disabled><legend>Arrival and return journey</legend><div class="te-grid">
      ${timeField('teDestinationArrival','Arrival at destination (day 1)','12:00')}
      <label>Return transport<select id="teDepartureMode"><option value="flight">Flight</option><option value="train">Train</option><option value="road">Road</option></select></label>
      ${timeField('teTransportDeparture','Actual transport departure (last day)','18:00')}
      <label>Airport, station or pickup point<input id="teDepartureTerminal" maxlength="200" placeholder="Terminal / station / address"></label>
      ${numberField('teCheckinBuffer','Time at airport / station before departure (minutes)',120,0,360)}
      ${numberField('teTerminalTravel','Travel from last stop to terminal (minutes)',60,0,360)}
      <label>Activities on the last day?<select id="teFinalActivities"><option value="yes">Yes, if time allows</option><option value="no">No, keep the day free</option></select></label></div>
      <p id="teDepartureWindow" role="status">Accommodation check-out and transport departure are separate. Allow time to collect luggage.</p></fieldset>
      <fieldset data-te-capability="schedule_preferences_v2" disabled><legend>Meals, rest and shopping</legend>
      <p>Meal times are preferences. The itinerary can move lunch or dinner by up to one hour to fit activities. Confirmed bookings and departure times stay fixed.</p>
      <div class="te-grid">
      ${timeField('teLunchTime','Preferred lunch time','14:00')}${numberField('teLunchDuration','Lunch duration (minutes)',60,15,180)}
      ${timeField('teDinnerTime','Preferred dinner time','20:00')}${numberField('teDinnerDuration','Dinner duration (minutes)',60,15,180)}
      <label>Daily rest<select id="teRestDuration"><option value="0">None</option><option value="20">Short · 20 minutes</option><option value="30" selected>Standard · 30 minutes</option><option value="60">Long · 60 minutes</option></select></label>
      <label><input type="checkbox" id="teShopping"> Include shopping</label>
      ${numberField('teShoppingDuration','Shopping time per trip (minutes)',90,15,480)}
      ${numberField('teShoppingBudget','Shopping budget, INR (optional)',0,0,1000000)}</div></fieldset>
      <div id="teFormError" class="te-error" role="alert"></div>`;
    el('schedulePrefsMount')?.after(extra);
    ['teRestDuration','teShopping','teShoppingDuration','teShoppingBudget'].forEach(id=>{
      const field=el(id)?.closest('label');
      if(field){field.dataset.tePostPlan='true';field.hidden=true;}
    });
    const formBlock=id=>[...form.children].find(node=>node.querySelector?.(`#${id}`));
    const destinationBlock=formBlock('tripCitySearchInput'),partyBlock=formBlock('tripTravellersInput'),budgetBlock=formBlock('tripBudgetInput');
    const accommodationBlock=formBlock('tripAccomSelect'),departureBlock=formBlock('tripDepartureInput');
    const legacyHotelFlow=formBlock('hotelWorkflowOptB')?.querySelector('#hotelWorkflowOptB')?.closest('.bg-slate-50');
    if(legacyHotelFlow)legacyHotelFlow.hidden=true;
    if(accommodationBlock){
      const stayFields=document.createElement('section');stayFields.id='teAccommodationDetails';stayFields.className='te-card';
      stayFields.innerHTML='<h3>Accommodation details</h3><p>Choose a property type. If you already have a property, enter its name and the full expected cost for the stay. The trip guide does not book accommodation.</p><div class="te-grid"><label>Property name (optional until confirmed)<input id="teAccommodationName" maxlength="160" autocomplete="organization"></label><label>Full expected stay cost (₹)<input id="teAccommodationCost" type="number" min="0" max="1000000000" step="1" inputmode="numeric"></label></div><p id="teAccommodationError" class="te-error" role="alert"></p>';
      accommodationBlock.after(stayFields);
      const transitLabel=el('tripTransitSelect')?.closest('div');
      if(transitLabel){
        const logistics=document.createElement('section');logistics.id='teTransportPreferenceBlock';logistics.className='te-card';
        logistics.innerHTML='<h3>Travel to your destination</h3><label>Intercity / international transport<select id="teJourneyMode"><option value="flight">Flight (domestic or international)</option><option value="train">Train (within India)</option><option value="bus">Intercity bus (within India)</option><option value="car">Private car / cab (within India)</option></select></label><label>Confirmed intercity / international travel cost (₹, optional)<input id="teIntercityCost" type="number" min="0" max="1000000000" step="1" inputmode="numeric"></label><p>Choose a journey mode and confirm the route with your provider. Availability and fares are not checked here.</p>';
        stayFields.after(logistics);
        extra.querySelector('fieldset')?.append(transitLabel);
      }
      const departureQuestion=el('teFinalActivities')?.closest('label');
      if(departureQuestion){
        const intent=document.createElement('section');intent.id='teDepartureDayIntent';intent.className='te-card';
        intent.innerHTML='<h3>Departure-day plan</h3><p>Would you like to include activities on the day you leave?</p>';
        intent.append(departureQuestion);
        (el('teTransportPreferenceBlock')||stayFields).after(intent);
      }
    }
    const editOptions=el('tripEditOptions'),submitFooter=el('generateItinerarySubmitBtn')?.parentElement;
    const ordered=[destinationBlock,partyBlock,budgetBlock,accommodationBlock,el('teAccommodationDetails'),el('teTransportPreferenceBlock'),el('teDepartureDayIntent'),departureBlock,el('schedulePrefsMount'),extra].filter(Boolean);
    const orderedSet=new Set(ordered);
    const trailing=[...form.children].filter(node=>!orderedSet.has(node)&&node!==editOptions&&node!==submitFooter);
    [editOptions,...ordered,...trailing,submitFooter].filter(Boolean).forEach(node=>form.append(node));
    let budgetSuggestionAvailable=false;
    const budgetInput=el('tripBudgetInput'),budgetSuggestion=document.createElement('p');budgetSuggestion.id='teProfileBudgetSuggestion';budgetSuggestion.className='text-xs text-slate-600';budgetSuggestion.setAttribute('role','status');budgetInput?.after(budgetSuggestion);
    budgetInput?.addEventListener('input',()=>{budgetTouched=true;});
    const oldBudgetEstimate=window.calculateTripMinimumBudget;
    if(typeof oldBudgetEstimate==='function')window.calculateTripMinimumBudget=async(...args)=>{const keep=budgetSuggestionAvailable&&!budgetTouched?budgetInput?.value:null;const result=await oldBudgetEstimate.apply(window,args);if(keep&&budgetInput){budgetInput.value=keep;window.onBudgetNumberInputChange?.(keep);}return result;};
    const oldFetch=window.fetch;
    if(typeof oldFetch==='function')window.fetch=async(input,init={})=>{const url=new URL(typeof input==='string'?input:input.url,location.href);if(url.pathname==='/api/budget/estimate-minimum'&&init.body){try{const body=JSON.parse(init.body),cost=el('teAccommodationCost')?.value,intercity=el('teIntercityCost')?.value;if(cost&&/^\\d+$/.test(cost))body.accommodation_cost_inr=Number(cost);if(intercity&&/^\\d+$/.test(intercity))body.intercity_cost_inr=Number(intercity);init={...init,body:JSON.stringify(body)};}catch(_){}}return oldFetch.call(window,input,init);};
    suggestProfileBudget=async function(){
      if(editingTripId||budgetTouched||!user()?.user_id)return;
      const userId=user().user_id,start=el('tripStartDateInput').value,end=el('tripEndDateInput').value,days=start&&end?Math.max(1,Math.floor((Date.parse(end)-Date.parse(start))/86400000)+1):1;
      const people=Math.max(1,Number(el('tripAdultsInput').value||0)+Number(el('tripChildrenInput').value||0)+Number(el('tripSeniorsInput').value||0));
      try{const profile=await api(`/api/profile/${encodeURIComponent(userId)}`);if(userId!==user()?.user_id)return;const band=String(profile.raw_answers?.b10_budget||profile.budget_tier||'').toLowerCase();const tierDaily=band.includes('backpacker')||band==='budget'?1750:band.includes('premium')||band==='luxury'?10500:band.includes('mid_range')||band==='balanced'?4250:null;const profileDaily=Number(profile.daily_budget_inr);const daily=Number.isInteger(profileDaily)&&profileDaily>0?profileDaily:tierDaily;if(!daily){budgetSuggestion.textContent='Profile budget is unavailable. Enter your preferred whole-trip budget.';return;}const total=Math.round(daily*people*days);budgetSuggestionAvailable=true;budgetInput.value=String(total);budgetSuggestion.textContent=`Suggested from your profile: ₹${daily.toLocaleString('en-IN')} per person/day × ${people} travellers × ${days} days = ₹${total.toLocaleString('en-IN')} whole-party total. Edit this amount anytime.`;window.onBudgetNumberInputChange?.(String(total));}
      catch(_){if(userId===user()?.user_id)budgetSuggestion.textContent='Profile budget suggestion is temporarily unavailable. Your entered details are kept; enter your preferred whole-trip budget.';}
    };
    ['tripStartDateInput','tripEndDateInput','tripAdultsInput','tripChildrenInput','tripSeniorsInput'].forEach(id=>el(id)?.addEventListener('change',()=>setTimeout(suggestProfileBudget,0)));
    const discard=document.createElement('button');discard.id='teDiscardFormDraft';discard.type='button';discard.className='text-xs underline';discard.textContent='Discard saved form draft';discard.hidden=true;
    discard.onclick=()=>{if(!confirm('Discard these unsaved form changes? This cannot be undone.'))return;try{sessionStorage.removeItem(draftKey());}catch(_){}form.reset();window.SchedulePrefs?.fill({});selectedDynamicLocation=null;el('tripDestSelect').value='';discard.hidden=true;dirty=false;notice('Saved form draft discarded.',el('teFormError'));};
    destinationBlock?.after(discard);
    const oldShopping=el('tripIncludeShoppingCheck')?.closest('label');if(oldShopping)oldShopping.hidden=true;
    el('hotelArrivalTime')?.parentElement.childNodes.forEach(n => {if(n.nodeType===3) n.textContent='Accommodation arrival (day 1)';});
    el('hotelDepartureTime')?.parentElement.childNodes.forEach(n => {if(n.nodeType===3) n.textContent='Accommodation checkout (last day)';});
    document.querySelectorAll('input[name="tripCompanionsRadio"]').forEach(input=>{const label=input.closest('label');if(label)label.hidden=true;});
    function syncType() {
      const type=el('teTripType').value;
      const old=document.querySelector(`input[name="tripCompanionsRadio"][value="${type==='couple'?'partner':type}"]`);
      if(old) { old.checked=true; onCompanionTypeChanged(old.value); }
    }
    el('teTripType').addEventListener('change',syncType);
    document.querySelectorAll('input[name="tripCompanionsRadio"]').forEach(input=>input.addEventListener('change',()=>{el('teTripType').value=input.value==='partner'?'couple':input.value;}));
    el('teDepartureMode').addEventListener('change',()=>{el('teCheckinBuffer').value=({flight:120,train:60,road:0})[el('teDepartureMode').value]; departureWindow();});
    extra.querySelector('fieldset:nth-of-type(2) legend')?.replaceChildren(document.createTextNode('Meals and evening plans'));
    const overrideButton=document.createElement('button');overrideButton.type='button';overrideButton.textContent='Add a per-day meal time';
    overridesHost=document.createElement('div');overridesHost.id='teMealOverrides';overridesHost.className='space-y-2';
    const overrideLabel=document.createElement('div');overrideLabel.textContent='Per-day meal time overrides';overrideLabel.append(overrideButton,overridesHost);
    extra.querySelector('fieldset:nth-of-type(2)')?.append(overrideLabel);
    addMealOverride=function(value={}){
      const start=el('tripStartDateInput').value,end=el('tripEndDateInput').value;
      const count=start&&end?Math.floor((Date.parse(end)-Date.parse(start))/86400000)+1:0;
      if(overridesHost.children.length>=Math.min(90,Math.max(0,count))){el('teFormError').textContent='Choose valid dates first; one override is allowed per trip day.';return null;}
      const row=document.createElement('div');row.className='te-grid';
      row.innerHTML='<label>Day<select class="teMealOverrideDay"></select></label><label>Lunch<input type="time" class="teMealOverrideLunch"></label><label>Lunch duration (minutes)<input type="number" class="teMealOverrideLunchDuration" min="15" max="180" step="1" value="60"></label><label>Dinner<input type="time" class="teMealOverrideDinner"></label><label>Dinner duration (minutes)<input type="number" class="teMealOverrideDinnerDuration" min="15" max="180" step="1" value="60"></label><button type="button" class="teMealOverrideRemove">Remove day override</button>';
      for(let day=1;day<=count;day++)row.querySelector('select').add(new Option(`Day ${day}`,String(day)));
      if(value.day)row.querySelector('.teMealOverrideDay').value=String(value.day);
      for(const [key,selector]of [['lunch_start_time','.teMealOverrideLunch'],['lunch_duration_minutes','.teMealOverrideLunchDuration'],['dinner_start_time','.teMealOverrideDinner'],['dinner_duration_minutes','.teMealOverrideDinnerDuration']])if(value[key]!=null)row.querySelector(selector).value=value[key];
      row.querySelector('.teMealOverrideRemove').onclick=()=>row.remove();overridesHost.append(row);
      return row;
    };
    overrideButton.addEventListener('click',()=>addMealOverride());
    function departureWindow() {
      const [h,m]=el('teTransportDeparture').value.split(':').map(Number);
      const cutoff=h*60+m-Number(el('teCheckinBuffer').value)-Number(el('teTerminalTravel').value);
      el('teDepartureWindow').textContent=el('teFinalActivities').value==='no'?'The last day is reserved for departure.':cutoff<0?'Your buffers begin the previous day. Choose a later departure or review the available time.':`Last activity must end by ${String(Math.floor(cutoff/60)).padStart(2,'0')}:${String(cutoff%60).padStart(2,'0')}. Accommodation check-out is separate; include luggage collection time.`;
    }
    extra.addEventListener('input',departureWindow);
    el('teFinalActivities').addEventListener('change',departureWindow);
    const dateMin=()=>{el('tripStartDateInput').min=editingTripId && el('tripStartDateInput').value<indiaToday()?el('tripStartDateInput').value:indiaToday();el('tripEndDateInput').min=el('tripStartDateInput').value || indiaToday();};
    ['tripStartDateInput','tripEndDateInput'].forEach(id=>el(id)?.addEventListener('input',dateMin)); dateMin();
    form.addEventListener('invalid',event=>{const input=event.target;if(input.id)fieldError(input.id,input.validationMessage||'Check this value.');},true);
    window.addEventListener('submit',event=>{
      if(event.target!==form)return;
      const errors=dateErrors(el('tripStartDateInput').value,el('tripEndDateInput').value,indiaToday(),!!editingTripId);
      const budget=Number(el('tripBudgetInput').value);
      if(!el('tripBudgetInput').value || !Number.isInteger(budget) || budget<1000 || budget>1000000) errors.tripBudgetInput='Enter a whole-rupee budget between ₹1,000 and ₹10,00,000.';
      if(!el('tripDestSelect').value) errors.tripCitySearchInput='Choose a recommendation or a search result.';
      for(const id of ['tripAdultsInput','tripChildrenInput','tripSeniorsInput']) {
        const value=Number(el(id).value);
        if(!el(id).value || !Number.isInteger(value)||value<(id==='tripAdultsInput'?1:0)||value>30)errors[id]='Enter a whole number within the allowed party size.';
        fieldError(id,errors[id]);
      }
      if(readTripParty().adults+readTripParty().children+readTripParty().seniors>30)errors.tripAdultsInput='A trip can include at most 30 travellers.';
      const accommodationName=el('teAccommodationName')?.value.trim()||'', accommodationCost=el('teAccommodationCost')?.value.trim()||'';
      if(Boolean(accommodationName)!==Boolean(accommodationCost))errors.teAccommodationCost='Enter both property name and full stay cost, or leave both blank until confirmed.';
      if(accommodationName.length>160)errors.teAccommodationName='Use 160 characters or fewer.';
      if(accommodationCost&&(!/^\d+$/.test(accommodationCost)||Number(accommodationCost)>1000000000))errors.teAccommodationCost='Enter a whole-rupee cost from ₹0 to ₹1,000,000,000.';
      const intercity=el('teIntercityCost')?.value.trim()||'';if(intercity&&(!/^\d+$/.test(intercity)||Number(intercity)>1000000000))errors.teIntercityCost='Enter a whole-rupee cost from ₹0 to ₹1,000,000,000.';
      if(!['flight','train','bus','car'].includes(el('teJourneyMode')?.value))errors.teJourneyMode='Choose flight, train, intercity bus or private car.';
      const overrides={};for(const row of overridesHost.querySelectorAll('.te-grid')){const day=row.querySelector('.teMealOverrideDay').value;if(!day){errors.teMealOverrides='Choose valid trip dates before adding day overrides.';break;}if(overrides[day]){errors.teMealOverrides='Use only one meal override per day.';break;}overrides[day]={};for(const [key,selector]of [['lunch_start_time','.teMealOverrideLunch'],['lunch_duration_minutes','.teMealOverrideLunchDuration'],['dinner_start_time','.teMealOverrideDinner'],['dinner_duration_minutes','.teMealOverrideDinnerDuration']]){const value=row.querySelector(selector).value;if(value)overrides[day][key]=key.includes('duration')?Number(value):value;}if(Object.values(overrides[day]).some(value=>typeof value==='number'&&(!Number.isInteger(value)||value<15||value>180)))errors.teMealOverrides='Meal duration must be from 15 to 180 minutes.';}
      for(const id of ['tripStartDateInput','tripEndDateInput','tripBudgetInput','tripCitySearchInput','tripAdultsInput']) fieldError(id,errors[id]);
      fieldError('teAccommodationName',errors.teAccommodationName);fieldError('teAccommodationCost',errors.teAccommodationCost);fieldError('teIntercityCost',errors.teIntercityCost);
      fieldError('teJourneyMode',errors.teJourneyMode);
      const mealError=el('teMealOverrides');if(mealError)mealError.setAttribute('aria-invalid',errors.teMealOverrides?'true':'false');if(errors.teMealOverrides)el('teFormError').textContent=errors.teMealOverrides;
      if(can('schedule_preferences_v2')) {
        extra.querySelectorAll('input:not([type=checkbox])').forEach(input=>{if(!input.checkValidity()) errors[input.id]='Check this value.';fieldError(input.id,errors[input.id]);});
        if(el('teDepartureMode').value==='flight' && Number(el('teCheckinBuffer').value)<120) errors.teCheckinBuffer='Allow at least 120 minutes at the airport.';
        if(el('teDepartureMode').value==='train' && Number(el('teCheckinBuffer').value)<30) errors.teCheckinBuffer='Allow at least 30 minutes at the station.';
        fieldError('teCheckinBuffer',errors.teCheckinBuffer);
      }
      if(Object.keys(errors).length) {event.preventDefault();event.stopImmediatePropagation();el(Object.keys(errors)[0])?.focus();}
    },true);
  }
  function readExperience() {
    return {destination_arrival_time:el('teDestinationArrival').value,transport_departure_time:el('teTransportDeparture').value,departure_mode:el('teDepartureMode').value,departure_terminal:el('teDepartureTerminal').value.trim(),terminal_buffer_minutes:Number(el('teCheckinBuffer').value),terminal_travel_minutes:Number(el('teTerminalTravel').value),final_day_activities:el('teFinalActivities').value==='yes',lunch_time:el('teLunchTime').value,lunch_duration_minutes:Number(el('teLunchDuration').value),dinner_time:el('teDinnerTime').value,dinner_duration_minutes:Number(el('teDinnerDuration').value),rest_duration_minutes:Number(el('teRestDuration').value),include_shopping:el('teShopping').checked,shopping_duration_minutes:Number(el('teShoppingDuration').value),shopping_budget:Number(el('teShoppingBudget').value)};
  }
  Trip.readExperience=readExperience;
  // Add only agreed optional fields to trip writes; never alter lifecycle requests.
  const originalFetch=window.fetch;
  window.fetch=async(input,init={})=>{
    const path=new URL(typeof input==='string'?input:input.url,location.href).pathname;
    if(['POST','PATCH'].includes(String(init.method).toUpperCase()) && (/^\/api\/trips\/[^/]+$/.test(path)||path==='/api/places/plan-dynamic') && init.body) {
      let body;try{body=JSON.parse(init.body);}catch(_){}
      if(body && form) {
        if(String(init.method).toUpperCase()==='POST'){
          const requestId=el('teCreationRequestId');
          if(!requestId.value)requestId.value=crypto.randomUUID();
          body.creation_request_id=requestId.value;
          saveDraft();
        }
        if(can('explicit_trip_type')) {const companions=inferTripCompanions();body.companions=companions;body.trip_type=companions==='partner'?'couple':companions;}
        body.trip_preferences={...body.trip_preferences,intercity_transport_mode:el('teJourneyMode').value};
        if(can('schedule_preferences_v2')) {
          const p=readExperience();
          const later=(time,minutes)=>{const [h,m]=time.split(':').map(Number);const total=h*60+m+minutes;return `${String(Math.floor(total/60)%24).padStart(2,'0')}:${String(total%60).padStart(2,'0')}`;};
          Object.assign(body,{destination_arrival_time:p.destination_arrival_time,hotel_checkin_time:el('hotelArrivalTime').value,hotel_checkout_time:el('hotelDepartureTime').value,
            transport_departure_time:p.transport_departure_time,departure_transport_mode:p.departure_mode==='road'?'other':p.departure_mode,departure_terminal:p.departure_terminal||null,
            final_day_activities:p.final_day_activities,terminal_arrival_buffer_minutes:p.departure_mode==='flight'?p.terminal_buffer_minutes:120,
            station_arrival_buffer_minutes:p.departure_mode==='train'?p.terminal_buffer_minutes:45,terminal_journey_minutes:p.terminal_travel_minutes,
            lunch_start_time:p.lunch_time,lunch_end_time:later(p.lunch_time,p.lunch_duration_minutes),lunch_duration_minutes:p.lunch_duration_minutes,
            dinner_start_time:p.dinner_time,dinner_end_time:later(p.dinner_time,p.dinner_duration_minutes),dinner_duration_minutes:p.dinner_duration_minutes,
            rest_preference:p.rest_duration_minutes===0?'none':p.rest_duration_minutes<=20?'short':p.rest_duration_minutes<=30?'standard':'long',
            shopping_enabled:p.include_shopping,shopping_duration_minutes:p.include_shopping?p.shopping_duration_minutes:0,shopping_budget_inr:p.shopping_budget});
          const accommodationName=el('teAccommodationName')?.value.trim()||'', accommodationCost=el('teAccommodationCost')?.value.trim();
          const mealOverrides={};for(const row of overridesHost.querySelectorAll('.te-grid')){const day=row.querySelector('.teMealOverrideDay').value;if(!day)continue;mealOverrides[day]={};for(const [key,selector]of [['lunch_start_time','.teMealOverrideLunch'],['lunch_duration_minutes','.teMealOverrideLunchDuration'],['dinner_start_time','.teMealOverrideDinner'],['dinner_duration_minutes','.teMealOverrideDinnerDuration']]){const value=row.querySelector(selector).value;if(value)mealOverrides[day][key]=key.includes('duration')?Number(value):value;}}
          body.trip_preferences={...body.trip_preferences,include_shopping:p.include_shopping,night_activities:true,meal_overrides:mealOverrides,checkout_gap_choice:'activity',intercity_cost_inr:el('teIntercityCost')?.value?Number(el('teIntercityCost').value):null,accommodation:{property_type:el('tripAccomSelect').value,property_name:accommodationName||null,expected_total_cost_inr:accommodationCost?Number(accommodationCost):null}};
          body.trip_preferences.accommodation=Object.fromEntries(Object.entries(body.trip_preferences.accommodation).filter(([,value])=>value!==null));
        }
        init={...init,body:JSON.stringify(body)};
      }
    }
    const response=await originalFetch(input,init);
    if(!response.ok && form && (/^\/api\/trips\/[^/]+$/.test(path)||path==='/api/places/plan-dynamic')) {
      try{const result=await response.clone().json();notice(publicText(typeof result.detail==='string'?result.detail:'Please check your trip details.'),el('teFormError'));}catch(_){}
    }
    return response;
  };
  function draftKey(){const match=location.hash.match(/^#\/trips\/([^/]+)\/edit$/);return `trip_creation_draft_${user()?.user_id || 'signed_out'}_${match?match[1]:'new'}`;}
  function saveDraft() {
    if(!user() || !form) return;
    const values={};form.querySelectorAll('input[id],select[id],textarea[id]').forEach(input=>{values[input.id]={value:input.value,checked:input.checked};});
    values.destination={id:el('tripDestSelect').value,label:el('tripDestSelect').selectedOptions[0]?.textContent,location:typeof selectedDynamicLocation!=='undefined'?selectedDynamicLocation:null};
    values.freeBlocks=[...document.querySelectorAll('#freeBlocksList > div')].map(row=>({day:row.querySelector('.freeDay').value,start:row.querySelector('.freeStart').value,end:row.querySelector('.freeEnd').value,label:row.querySelector('.freeLabel').value}));
    values.mealOverrides=[...overridesHost.querySelectorAll('.te-grid')].map(row=>({day:row.querySelector('.teMealOverrideDay').value,lunch_start_time:row.querySelector('.teMealOverrideLunch').value,lunch_duration_minutes:Number(row.querySelector('.teMealOverrideLunchDuration').value),dinner_start_time:row.querySelector('.teMealOverrideDinner').value,dinner_duration_minutes:Number(row.querySelector('.teMealOverrideDinnerDuration').value)}));
    try{sessionStorage.setItem(draftKey(),JSON.stringify(values));}catch(_){notice('Draft storage is unavailable. Keep this page open until you save.',el('teFormError'));}
  }
  function restoreDraft() {
    try{
      const values=JSON.parse(sessionStorage.getItem(draftKey())||'null');if(!values)return;
      const destination=values.destination, select=el('tripDestSelect');
      if(destination?.id && ![...select.options].some(o=>o.value===destination.id))select.add(new Option(destination.label||destination.id,destination.id));
      if(destination?.location)selectedDynamicLocation=destination.location;
      Object.entries(values).forEach(([id,data])=>{const node=el(id);if(node){node.value=data.value; if(node.type==='checkbox'||node.type==='radio')node.checked=data.checked;}});
      window.SchedulePrefs?.fill({...window.SchedulePrefs.readPrefs(),free_blocks:values.freeBlocks||[]});el('teTripType')?.dispatchEvent(new Event('change'));
      overridesHost.replaceChildren();(values.mealOverrides||[]).forEach(addMealOverride);
      dirty=true;
    }catch(_){}
  }
  let dirty=false, routing=false, routeEpoch=0;
  const formChanged=()=>{dirty=true;el('teCreationRequestId').value='';saveDraft();};
  form?.addEventListener('input',formChanged);
  form?.addEventListener('change',formChanged);
  window.addEventListener('beforeunload',event=>{if(dirty && (location.hash==='#/trips/new'||location.hash.endsWith('/edit'))){saveDraft();event.preventDefault();event.returnValue='';}});
  const planner=el('itineraryPlannerSection'), modal=el('tripFormModal');
  if(!planner || !modal) return;
  // Header navigation is the single dashboard entry point for trips.
  const view=document.createElement('section');view.id='tripExperienceView';view.hidden=true;view.innerHTML=`<nav class="te-workspace-nav" aria-label="Trip navigation"><a href="#/">← Back to main menu</a><a href="#/trips">My trips</a><a href="#/trips/new">Plan another trip</a></nav><p id="teRouteNotice" class="te-error" role="status" hidden></p><div id="teTripList" hidden></div>`;
  el('dashboardView').after(view);view.append(planner,modal);
  modal.classList.add('te-form-page');
  const rawOpen=window.openModal,rawClose=window.closeModal;
  window.openModal=function(id){if(id==='academicModal')return;if(id==='tripFormModal'){if(!Trip.allowPlanning())return;modal.classList.remove('hidden');if(!routing)location.hash=editingTripId?`/trips/${encodeURIComponent(editingTripId)}/edit`:'/trips/new';return;}return rawOpen(id);};
  window.closeModal=function(id){if(id==='tripFormModal'){if(form.dataset.teSubmitting==='true')return;saveDraft();rawClose(id);if(!routing)location.hash=currentPlannedTripId?`/trips/${encodeURIComponent(currentPlannedTripId)}`:'/trips';return;}return rawClose(id);};
  const oldToggle=window.toggleTripFormModal;
  window.toggleTripFormModal=async()=>{if(!await window.ProfileGate.require())return;if(!Trip.allowPlanning())return;return oldToggle();};
  const rawSubmit=window.handleTripCreateSubmit;
  window.handleTripCreateSubmit=async event=>{
    event.preventDefault();
    if(form.dataset.teSubmitting==='true')return;
    form.dataset.teSubmitting='true';
    try{await rawSubmit(event);}finally{form.dataset.teSubmitting='false';}
  };
  const rawEdit=window.editSelectedTrip;
  window.editSelectedTrip=async()=>{
    if(!routing){if(getSnapshot(currentPlannedTripId)?.status==='finalized'){await api(`/api/trips/${encodeURIComponent(currentPlannedTripId)}/unfinalize?${query()}`,{method:'POST',body:JSON.stringify({})});}location.hash=`/trips/${encodeURIComponent(currentPlannedTripId)}/edit`;return;}
    await rawEdit();
  };
  const oldMode=window.switchWorkspaceMode;
  window.switchWorkspaceMode=mode=>{
    const current=getSnapshot(currentPlannedTripId);
    if(mode==='budget'&&current){notice('');return oldMode(mode);}
    if(!access(current)[mode]){notice(current?'This section is locked until the trip reaches the right stage.':'Loading saved trip permissions. Please retry shortly.');return;}
    notice('');return oldMode(mode);
  };
  Trip.applySnapshot=(ctx,next)=>{
    if(ctx.tripId!==currentPlannedTripId)return false;
    const previous=getSnapshot(ctx.tripId);
    if(previous&&Number(next.runtime?.version||0)<Number(previous.runtime?.version||0))return false;
    snapshot=next;snapshotTrip=ctx.tripId;
    const allowed={...access(next)};
    ['pre','live','post'].forEach(mode=>{const btn=el('wsTabBtn-'+mode);if(btn){btn.disabled=!allowed[mode];btn.setAttribute('aria-disabled',String(!allowed[mode]));btn.title=allowed[mode]?'':mode==='live'?'Start this trip to unlock live activities.':'Complete the trip to unlock feedback.';}});
    document.querySelectorAll('[onclick="editSelectedTrip()"],[onclick="regenerateEntireItinerary()"],#preSubContent-stay button').forEach(button=>{button.disabled=!allowed.edit;});
    const preferred=next.status==='completed'?'post':next.status==='live'?'live':'pre';
    if(!allowed[currentWorkspaceMode]&&!window.BudgetExperience?.isOpen(ctx.tripId)&&!window.ShoppingExperience?.isOpen(ctx.tripId))oldMode(preferred);
    el('itinSummaryNotes').textContent=next.status==='completed'?(next.closed_out?'Archived trip · feedback saved':'Trip ended · finish your feedback'):'Your personalised itinerary.';
    if(next.status==='completed') [...el('userTripsSelect').options].filter(option=>option.value===ctx.tripId).forEach(option=>option.remove());
    window.dispatchEvent(new CustomEvent('trip:runtime',{detail:{tripId:ctx.tripId,snapshot:next}}));
    return true;
  };
  let emptyTripsDialog=null;
  function closeEmptyTripsDialog() {
    if(emptyTripsDialog){emptyTripsDialog.dataset.restoreFocus='false';emptyTripsDialog.close();emptyTripsDialog.remove();emptyTripsDialog=null;}
  }
  function showEmptyTripsDialog() {
    closeEmptyTripsDialog();
    const opener=document.activeElement;
    const dialog=document.createElement('dialog');dialog.id='teNoTripsDialog';dialog.className='te-dialog';
    dialog.setAttribute('aria-labelledby','teNoTripsMessage');
    const message=document.createElement('h2');message.id='teNoTripsMessage';message.textContent='no trips';
    const dismiss=document.createElement('button');dismiss.type='button';dismiss.className='te-primary';dismiss.textContent='Close';
    dismiss.onclick=()=>dialog.close();
    dialog.addEventListener('close',()=>{dialog.remove();if(emptyTripsDialog===dialog)emptyTripsDialog=null;if(dialog.dataset.restoreFocus!=='false'&&opener?.isConnected)opener.focus({preventScroll:true});},{once:true});
    dialog.append(message,dismiss);document.body.append(dialog);emptyTripsDialog=dialog;dialog.showModal();dismiss.focus();
  }
  async function listTrips(epoch=routeEpoch) {
    const actor=user()?.user_id;
    if(!actor)return;
    const current=()=>actor===user()?.user_id&&epoch===routeEpoch&&location.hash==='#/trips';
    const box=el('teTripList');box.hidden=false;box.innerHTML='<p role="status">Loading your trips…</p>';
    try{
      const userPath=`/api/trips/${encodeURIComponent(actor)}`;
      const [all,pending,archived,history]=await Promise.all([api(userPath),api(userPath+'/feedback-pending'),api(userPath+'/archive'),api('/api/profile/history')]);
      if(!current())return;
      if(![all,pending,archived].every(Array.isArray)||!Array.isArray(history?.entries))throw new Error('Your trip history could not be read. Please retry.');
      const completedIds=new Set([...pending,...archived].map(t=>t.id));
      const trips=[...new Map([...all,...pending,...archived].map(trip=>[trip.id,trip])).values()];
      const tripIds=new Set(trips.map(trip=>trip.id));
      const recorded=history.entries.filter(entry=>entry.source==='manual'||!entry.trip_id||!tripIds.has(entry.trip_id));
      const enriched=await Promise.all(trips.map(async trip=>{
        try{return {...trip,runtime:await api(`/api/trips/${encodeURIComponent(trip.id)}/runtime?user_id=${encodeURIComponent(actor)}`)};}
        catch(_){return {...trip,runtime:null};}
      }));
      if(!current())return;
      const isPast=t=>t.runtime?.status==='completed'||completedIds.has(t.id)||['completed','archived'].includes(t.status);
      box.innerHTML='<h2>My trips</h2>'+['Active trips','Past trips'].map((heading,index)=>{
        const group=enriched.filter(t=>index?isPast(t):!isPast(t));
        if(!group.length)return '';
        return `<section class="te-card"><h3>${heading}</h3>${group.map(t=>`<article class="te-list-row"><div><h4>${esc(t.destination_name)}</h4><p>${esc(t.start_date)} – ${esc(t.end_date)}</p><small>${t.runtime?t.runtime.closed_out?'Feedback saved':t.runtime.status==='completed'?'Feedback pending':esc(t.runtime.status):'Progress unavailable — open to retry'}</small></div><a class="te-primary" href="#/trips/${encodeURIComponent(t.id)}">${t.runtime?.status==='completed'&&!t.runtime.closed_out?'Finish feedback':'Open trip'}</a></article>`).join('')}</section>`;
      }).join('');
      if(recorded.length)box.insertAdjacentHTML('beforeend',`<section class="te-card" aria-labelledby="teHistoryHeading"><h3 id="teHistoryHeading">Travel history</h3><p>Past travel recorded in your profile.</p>${recorded.map(entry=>`<article class="te-list-row"><div><h4>${esc(entry.destination||entry.city||'Recorded trip')}</h4><p>${esc(entry.visited_on||'Date not recorded')} · ${esc(entry.trip_type||'Trip type not recorded')}</p><details><summary>View history details</summary><p>Would revisit: ${entry.would_revisit===true?'Yes':entry.would_revisit===false?'No':'Not recorded'}</p>${Object.entries(entry.ratings||{}).map(([key,value])=>`<p>${esc(key.replace(/_/g,' '))}: ${esc(value)} / 5</p>`).join('')}${entry.notes?`<p>${esc(entry.notes)}</p>`:''}</details></div></article>`).join('')}</section>`);
      if(!trips.length&&!recorded.length){box.innerHTML='<h2>My trips</h2><p>no trips</p>';showEmptyTripsDialog();}
      const select=el('userTripsSelect');[...select.options].forEach(option=>{const t=enriched.find(t=>t.id===option.value);if(t?.runtime?.status==='completed')option.remove();});
    }catch(error){if(current()){closeEmptyTripsDialog();box.innerHTML=`<p role="alert">${esc(error.message)}</p><button id="teListRetry">Retry</button>`;el('teListRetry').onclick=()=>listTrips(routeEpoch);}}
  }
  async function route() {
    const epoch=++routeEpoch;
    closeEmptyTripsDialog();
    const path=location.hash.slice(1)||'/';
    if(!path.startsWith('/trips')) {routing=false;view.hidden=true;if(user())el('dashboardView').classList.remove('hidden');return;}
    if(!user()){view.hidden=true;return;}
    const actor=user().user_id;
    const current=()=>epoch===routeEpoch&&actor===user()?.user_id;
    // Reading history and resuming existing trips never requires a questionnaire.
    if(path==='/trips/new'||path.endsWith('/edit')){
      if(!await window.ProfileGate.require()){if(current()){view.hidden=true;history.replaceState(null,'','#/');el('dashboardView').classList.remove('hidden');}return;}
      if(!current())return;
      if(!Trip.allowPlanning()){view.hidden=true;el('dashboardView').classList.remove('hidden');history.replaceState(null,'','#/');return;}
    }
    if(!current())return;
    if(path!=='/trips/new'&&!path.endsWith('/edit'))window.dispatchEvent(new Event('trip:history-opened'));
    routing=true;
    try {
      view.hidden=false;el('authView').classList.add('hidden');el('onboardingView').classList.add('hidden');el('dashboardView').classList.add('hidden');el('teTripList').hidden=true;planner.hidden=false;rawClose('tripFormModal');notice('');
      if(path==='/trips/new') {
        setPostPlanOptions(false);
        if(el('teDiscardFormDraft'))el('teDiscardFormDraft').hidden=true;
        planner.hidden=true;await loadCapabilities();if(!current())return;
        await oldToggle();if(!current())return;
        let saved=false;try{saved=!!sessionStorage.getItem(draftKey());}catch(_){}
        if(saved){restoreDraft();if(el('teDiscardFormDraft'))el('teDiscardFormDraft').hidden=false;}else{el('teCreationRequestId').value='';el('tripDestSelect').value='';selectedDynamicLocation=null;el('tripNearbyPlacesArea')?.classList.add('hidden');el('tripBudgetInput').value='';budgetTouched=false;setTimeout(suggestProfileBudget,0);}
        el('tripStartDateInput').min=indiaToday();el('tripEndDateInput').min=el('tripStartDateInput').value||indiaToday();
        modal.classList.remove('hidden');
        window.dispatchEvent(new CustomEvent('trip:creation-ready')); // E: explicit recommendation handoff.
      }
      else if(path==='/trips') {planner.hidden=true;await listTrips(epoch);}
      else {
        const match=path.match(/^\/trips\/([^/]+)(\/edit)?$/);if(!match){notice('This trip link is invalid.');return;}
        const id=decodeURIComponent(match[1]);
        await loadCapabilities();
        if(!current())return;
        const next=await api(`/api/trips/${encodeURIComponent(id)}/runtime?${query()}`);
        if(!current())return;
        currentPlannedTripId=id;
        const previous=getSnapshot(id);
        if(!previous||Number(next.runtime?.version||0)>=Number(previous.runtime?.version||0)){snapshot=next;snapshotTrip=id;}
        // Explicit selection avoids auto-generation while resuming a live or archived trip.
        const itinerary=await api(`/api/itinerary/${encodeURIComponent(id)}?${query()}`);
        if(!current())return;
        currentItinerary=itinerary;renderItinerary(itinerary);
        const effective=getSnapshot(id)||next;
        Trip.applySnapshot(getWorkspaceContext(),effective);
        if(window.ShoppingExperience?.isOpen(id))window.ShoppingExperience.restore(id);
        else if(window.BudgetExperience?.isOpen(id))window.BudgetExperience.restore(id);
        else oldMode(effective.status==='completed'?'post':effective.status==='live'?'live':'pre');
        if(match[2]){if(next.status!=='draft'){notice('Reopen a finalized trip before editing. Live and completed trips cannot be edited.');return;}await editSelectedTrip();await fillExperience(id);restoreDraft();setPostPlanOptions(true);}
      }
      if(current()&&!emptyTripsDialog){view.querySelector('h2,h3')?.setAttribute('tabindex','-1');view.querySelector('h2,h3')?.focus();}
    }catch(error){if(current())notice(error.message);}
    finally{if(epoch===routeEpoch)routing=false;}
  }
  async function fillExperience(id) {
    const trip=await api(`/api/trips/detail/${encodeURIComponent(id)}?${query()}`);
    const prefs={...trip.trip_preferences,...trip};
    Object.assign(prefs,{departure_mode:trip.departure_transport_mode==='other'?'road':trip.departure_transport_mode,
      terminal_buffer_minutes:trip.departure_transport_mode==='train'?trip.station_arrival_buffer_minutes:trip.terminal_arrival_buffer_minutes,
      terminal_travel_minutes:trip.terminal_journey_minutes,lunch_time:trip.lunch_start_time,dinner_time:trip.dinner_start_time,
      shopping_budget:trip.shopping_budget_inr,include_shopping:trip.shopping_enabled,rest_duration_minutes:({none:0,short:20,standard:30,long:60})[trip.rest_preference]});
    const mapping={destination_arrival_time:'teDestinationArrival',transport_departure_time:'teTransportDeparture',departure_mode:'teDepartureMode',departure_terminal:'teDepartureTerminal',terminal_buffer_minutes:'teCheckinBuffer',terminal_travel_minutes:'teTerminalTravel',lunch_time:'teLunchTime',lunch_duration_minutes:'teLunchDuration',dinner_time:'teDinnerTime',dinner_duration_minutes:'teDinnerDuration',rest_duration_minutes:'teRestDuration',shopping_duration_minutes:'teShoppingDuration',shopping_budget:'teShoppingBudget'};
    Object.entries(mapping).forEach(([key,id])=>{if(prefs[key]!=null)el(id).value=prefs[key];});
    el('teTripType').value=trip.trip_type||({partner:'couple',family_kids:'family',family_seniors:'family'}[trip.companions]||trip.companions)||'solo';
    el('teTripType').dispatchEvent(new Event('change'));
    const accommodation=trip.trip_preferences?.accommodation||{};
    el('teAccommodationName').value=accommodation.property_name||'';
    el('teAccommodationCost').value=accommodation.expected_total_cost_inr??'';
    el('teIntercityCost').value=trip.trip_preferences?.intercity_cost_inr??'';
    el('teJourneyMode').value=trip.trip_preferences?.intercity_transport_mode||'flight';
    overridesHost.replaceChildren();Object.entries(trip.trip_preferences?.meal_overrides||{}).forEach(([day,meals])=>addMealOverride({day,...meals}));
    el('teShopping').checked=!!prefs.include_shopping;el('teFinalActivities').value=prefs.final_day_activities===false?'no':'yes';
    el('tripStartDateInput').min=trip.start_date<indiaToday()?trip.start_date:indiaToday();el('tripEndDateInput').min=el('tripStartDateInput').value;
  }
  function setPostPlanOptions(editing){
    document.querySelectorAll('[data-te-post-plan]').forEach(field=>{field.hidden=!editing;});
    if(!editing){el('teRestDuration').value='0';el('teShopping').checked=false;el('teShoppingDuration').value='90';el('teShoppingBudget').value='0';}
  }
  const oldLoadTrips=window.loadUserTrips;
  window.loadUserTrips=async(...args)=>{
    const result=await oldLoadTrips(...args);
    if(args[0] && !routing) {dirty=false;try{sessionStorage.removeItem(draftKey());}catch(_){}location.hash=`/trips/${encodeURIComponent(args[0])}`;}
    else if(location.hash.startsWith('#/trips')&&!routing)await route();
    return result;
  };
  const oldSelect=window.onTripSelectChanged;
  window.onTripSelectChanged=id=>{if(id)location.hash=`/trips/${encodeURIComponent(id)}`;else oldSelect(id);};
  window.addEventListener('hashchange',route);
  document.addEventListener('click',event=>{
    if(event.defaultPrevented||event.button!==0||event.metaKey||event.ctrlKey||event.shiftKey||event.altKey)return;
    if(location.hash==='#/trips'&&event.target.closest?.('a[href="#/trips"]')){event.preventDefault();route();}
  });
  window.addEventListener('load',()=>{if(view.hidden)route();});
  // Keep direct links private when the existing session controller signs out.
  new MutationObserver(()=>{
    if(!el('authView').classList.contains('hidden')){
      routeEpoch++;routing=false;closeEmptyTripsDialog();el('teTripList').replaceChildren();
      view.hidden=true;
      // E: remove account-specific workspace state before a different sign-in.
      snapshot=null;snapshotTrip=null;currentPlannedTripId=null;currentItinerary=null;dirty=false;
      el('itineraryDisplayContainer').classList.add('hidden');
      form?.reset();window.SchedulePrefs?.fill({});selectedDynamicLocation=null;
      window.dispatchEvent(new CustomEvent('trip:context-cleared'));
    }
  }).observe(el('authView'),{attributes:true,attributeFilter:['class']});
  // Recommendations are real server results, never the old mandatory catalogue dropdown.
  const choices=document.createElement('div');choices.id='teDestinationRecommendations';choices.className='te-destination-grid';el('tripDestSelect').after(choices);
  async function destinations() {
    if(!user())return;
    choices.textContent='Loading recommendations…';
    try {
      const result=await api(`/api/recommendations/${encodeURIComponent(user().user_id)}`);
      const items=(result.recommended_for_you||[]).filter(item=>!isHomeDestination(item));choices.replaceChildren();
      if(!items.length){choices.innerHTML='<p>No matches yet. Search a destination or update your travel preferences.</p>';return;}
      items.forEach(item=>{
        const button=document.createElement('button');button.type='button';button.className='te-destination';
        button.innerHTML=`<strong>${esc(item.name||item.destination_name||item.id)}</strong><small>${esc(matchLabel(item))}</small><span>${esc(publicText(item.why_recommended||item.reason||item.description||'Based on your saved travel preferences.'))}</span>`;
        button.onclick=async()=>{
          const select=el('tripDestSelect');if(![...select.options].some(o=>o.value===item.id))select.add(new Option(item.name||item.destination_name,item.id));
          select.value=item.id;select.dispatchEvent(new Event('change',{bubbles:true}));
          choices.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));
          dirty=true;saveDraft();
        };choices.append(button);
      });
    }catch(error){choices.replaceChildren();const text=document.createElement('p');text.textContent=error.message;const retry=document.createElement('button');retry.type='button';retry.textContent='Retry recommendations';retry.onclick=destinations;choices.append(text,retry);}
  }
  new MutationObserver(()=>{if(!modal.classList.contains('hidden'))destinations();}).observe(modal,{attributes:true,attributeFilter:['class']});
  Trip.route=route;
})();
