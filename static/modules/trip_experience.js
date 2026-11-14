/* UI: trip workspace. The server owns schedules, acceptance and runtime state. */
(() => {
  'use strict';
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const indiaToday = (date = new Date()) => {
    const parts=new Intl.DateTimeFormat('en', {timeZone:'Asia/Kolkata',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(date);
    const part=key=>parts.find(p=>p.type===key).value;
    return `${part('year')}-${part('month')}-${part('day')}`;
  };
  const publicText = value => /linucb|bandit|sherman|state.vector|reinforcement|policy|feature.dimension/i.test(String(value || '')) ? 'Personalised using your travel preferences and feedback.' : String(value || '');
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
    return {pre:!!snapshot, live:snapshot?.status === 'live', post:snapshot?.status === 'completed', edit:snapshot?.status === 'draft'};
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
  if(form) {
    const extra=document.createElement('section'); extra.className='te-card'; extra.id='teTripPreferences';
    extra.innerHTML=`<h3>Travel plans & personal time</h3><p id="teCapabilityNotice" role="status"></p>
      <label>Trip type<select id="teTripType"><option value="solo">Solo</option><option value="couple">Couple</option><option value="friends">Friends</option><option value="family">Family (adults, with or without children)</option></select></label>
      <p>Trip type is your choice. Ages and accessibility needs are entered separately below.</p>
      <fieldset data-te-capability="schedule_preferences_v2" disabled><legend>Arrival and return journey</legend><div class="te-grid">
      ${timeField('teDestinationArrival','Arrival at destination (day 1)','12:00')}
      <label>Return transport<select id="teDepartureMode"><option value="flight">Flight</option><option value="train">Train</option><option value="road">Road</option></select></label>
      ${timeField('teTransportDeparture','Actual transport departure (last day)','18:00')}
      <label>Airport, station or pickup point<input id="teDepartureTerminal" maxlength="200" placeholder="Terminal / station / address"></label>
      ${numberField('teCheckinBuffer','Time at airport / station before departure (minutes)',120,0,360)}
      ${numberField('teTerminalTravel','Travel from last stop to terminal (minutes)',60,0,360)}
      <label>Activities on the last day?<select id="teFinalActivities"><option value="yes">Yes, if time allows</option><option value="no">No, keep the day free</option></select></label></div>
      <p id="teDepartureWindow" role="status">Hotel checkout and transport departure are separate. Allow time to collect luggage.</p></fieldset>
      <fieldset data-te-capability="schedule_preferences_v2" disabled><legend>Meals, rest and shopping</legend><div class="te-grid">
      ${timeField('teLunchTime','Preferred lunch time','13:00')}${numberField('teLunchDuration','Lunch duration (minutes)',60,15,180)}
      ${timeField('teDinnerTime','Preferred dinner time','19:00')}${numberField('teDinnerDuration','Dinner duration (minutes)',60,15,180)}
      <label>Daily rest<select id="teRestDuration"><option value="0">None</option><option value="20">Short · 20 minutes</option><option value="30" selected>Standard · 30 minutes</option><option value="60">Long · 60 minutes</option></select></label>
      <label><input type="checkbox" id="teShopping"> Include shopping</label>
      ${numberField('teShoppingDuration','Shopping time per trip (minutes)',90,15,480)}
      ${numberField('teShoppingBudget','Shopping budget, INR (optional)',0,0,1000000)}</div></fieldset>
      <div id="teFormError" class="te-error" role="alert"></div>`;
    el('schedulePrefsMount')?.after(extra);
    const discard=document.createElement('button');discard.type='button';discard.className='text-xs underline';discard.textContent='Discard saved form draft';
    discard.onclick=()=>{if(!confirm('Discard these unsaved form changes? This cannot be undone.'))return;try{sessionStorage.removeItem(draftKey());}catch(_){}form.reset();window.SchedulePrefs?.fill({});selectedDynamicLocation=null;el('tripDestSelect').value='';dirty=false;notice('Saved form draft discarded.',el('teFormError'));};
    form.prepend(discard);
    const oldShopping=el('tripIncludeShoppingCheck')?.closest('label');if(oldShopping)oldShopping.hidden=true;
    el('hotelDepartureTime')?.parentElement.childNodes.forEach(n => {if(n.nodeType===3) n.textContent='Hotel checkout (last day)';});
    document.querySelectorAll('input[name="tripCompanionsRadio"]').forEach(input=>{const label=input.closest('label');if(label)label.hidden=true;});
    function syncType() {
      const type=el('teTripType').value;
      const old=document.querySelector(`input[name="tripCompanionsRadio"][value="${type==='couple'?'partner':type}"]`);
      if(old) { old.checked=true; onCompanionTypeChanged(old.value); }
    }
    el('teTripType').addEventListener('change',syncType);
    document.querySelectorAll('input[name="tripCompanionsRadio"]').forEach(input=>input.addEventListener('change',()=>{el('teTripType').value=input.value==='partner'?'couple':input.value;}));
    el('teDepartureMode').addEventListener('change',()=>{el('teCheckinBuffer').value=({flight:120,train:60,road:0})[el('teDepartureMode').value]; departureWindow();});
    function departureWindow() {
      const [h,m]=el('teTransportDeparture').value.split(':').map(Number);
      const cutoff=h*60+m-Number(el('teCheckinBuffer').value)-Number(el('teTerminalTravel').value);
      el('teDepartureWindow').textContent=el('teFinalActivities').value==='no'?'The last day is reserved for departure.':cutoff<0?'Your buffers begin the previous day. Choose a later departure or review the available time.':`Last activity must end by ${String(Math.floor(cutoff/60)).padStart(2,'0')}:${String(cutoff%60).padStart(2,'0')}. Checkout is separate; include luggage collection time.`;
    }
    extra.addEventListener('input',departureWindow);
    const dateMin=()=>{el('tripStartDateInput').min=editingTripId && el('tripStartDateInput').value<indiaToday()?el('tripStartDateInput').value:indiaToday();el('tripEndDateInput').min=el('tripStartDateInput').value || indiaToday();};
    ['tripStartDateInput','tripEndDateInput'].forEach(id=>el(id)?.addEventListener('change',dateMin)); dateMin();
    form.addEventListener('invalid',event=>{const input=event.target;if(input.id)fieldError(input.id,input.validationMessage||'Check this value.');},true);
    window.addEventListener('submit',event=>{
      if(event.target!==form)return;
      const errors=dateErrors(el('tripStartDateInput').value,el('tripEndDateInput').value,indiaToday(),!!editingTripId);
      const budget=Number(el('tripBudgetInput').value);
      if(!el('tripBudgetInput').value || !Number.isInteger(budget) || budget<1000 || budget>1000000) errors.tripBudgetInput='Enter a whole-rupee budget between ₹1,000 and ₹10,00,000.';
      if(!el('tripDestSelect').value) errors.tripCitySearchInput='Choose a recommendation or a search result.';
      if(!['solo','couple','friends','family'].includes(el('teTripType').value))errors.teTripType='Choose solo, couple, friends or family.';
      for(const id of ['tripAdultsInput','tripChildrenInput','tripSeniorsInput']) {
        const value=Number(el(id).value);
        if(!el(id).value || !Number.isInteger(value)||value<(id==='tripAdultsInput'?1:0)||value>30)errors[id]='Enter a whole number within the allowed party size.';
        fieldError(id,errors[id]);
      }
      if(readTripParty().adults+readTripParty().children+readTripParty().seniors>30)errors.tripAdultsInput='A trip can include at most 30 travellers.';
      if(el('teTripType').value==='solo' && (readTripParty().adults!==1 || readTripParty().children || readTripParty().seniors))errors.teTripType='Choose a group trip type or select exactly one adult.';
      if(el('teTripType').value==='family' && !can('explicit_trip_type') && !readTripParty().children && !readTripParty().seniors) errors.teTripType='Adult-only family trips await the trip-type update. Your selection has been kept.';
      for(const id of ['tripStartDateInput','tripEndDateInput','tripBudgetInput','tripCitySearchInput','teTripType','tripAdultsInput']) fieldError(id,errors[id]);
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
        if(can('explicit_trip_type')) body.trip_type=el('teTripType').value;
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
          body.trip_preferences={...body.trip_preferences,include_shopping:p.include_shopping};
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
      dirty=true;
    }catch(_){}
  }
  let dirty=false, routing=false, routeEpoch=0;
  form?.addEventListener('input',()=>{dirty=true;saveDraft();});
  form?.addEventListener('change',()=>{dirty=true;saveDraft();});
  window.addEventListener('beforeunload',event=>{if(dirty && (location.hash==='#/trips/new'||location.hash.endsWith('/edit'))){saveDraft();event.preventDefault();event.returnValue='';}});
  const planner=el('itineraryPlannerSection'), modal=el('tripFormModal');
  if(!planner || !modal) return;
  const placeholder=document.createComment('UI: planner lives in the dedicated trip workspace');planner.before(placeholder);
  const view=document.createElement('section');view.id='tripExperienceView';view.hidden=true;view.innerHTML=`<nav class="te-workspace-nav" aria-label="Trip navigation"><a href="#/">← Back to main menu</a><a href="#/trips">My trips</a><a href="#/trips/new">Plan another trip</a></nav><p id="teRouteNotice" class="te-error" role="status" hidden></p><div id="teTripList" hidden></div>`;
  el('dashboardView').after(view);view.append(planner,modal);
  const launcher=document.createElement('section');launcher.className='te-card';launcher.innerHTML='<h2>Your trips</h2><p>Plan a journey, continue your current trip or finish feedback.</p><a class="te-primary" href="#/trips/new">Plan new trip</a> <a href="#/trips">My trips & history</a>';placeholder.after(launcher);
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
    if(!routing){location.hash=`/trips/${encodeURIComponent(currentPlannedTripId)}/edit`;return;}
    await rawEdit();
  };
  const oldMode=window.switchWorkspaceMode;
  window.switchWorkspaceMode=mode=>{
    const current=getSnapshot(currentPlannedTripId);
    if(!access(current)[mode]){notice(current?'This section is locked until the trip reaches the right stage.':'Loading saved trip permissions. Please retry shortly.');return;}
    notice('');return oldMode(mode);
  };
  Trip.applySnapshot=(ctx,next)=>{
    if(ctx.tripId!==currentPlannedTripId)return;
    snapshot=next;snapshotTrip=ctx.tripId;
    const allowed=access(next);
    ['pre','live','post'].forEach(mode=>{const btn=el('wsTabBtn-'+mode);if(btn){btn.disabled=!allowed[mode];btn.setAttribute('aria-disabled',String(!allowed[mode]));btn.title=allowed[mode]?'':mode==='live'?'Start this trip to unlock live activities.':'Complete the trip to unlock feedback.';}});
    document.querySelectorAll('[onclick="editSelectedTrip()"],[onclick="regenerateEntireItinerary()"],[onclick="deleteSelectedTrip()"],#preSubContent-stay button').forEach(button=>{button.disabled=!allowed.edit;});
    const preferred=next.status==='completed'?'post':next.status==='live'?'live':'pre';
    if(!allowed[currentWorkspaceMode])oldMode(preferred);
    el('itinSummaryNotes').textContent=next.status==='completed'?(next.closed_out?'Archived trip · feedback saved':'Trip ended · finish your feedback'):'Your personalised itinerary.';
    if(next.status==='completed') [...el('userTripsSelect').options].filter(option=>option.value===ctx.tripId).forEach(option=>option.remove());
    window.dispatchEvent(new CustomEvent('trip:runtime',{detail:{tripId:ctx.tripId,snapshot:next}}));
  };
  async function listTrips() {
    const box=el('teTripList');box.hidden=false;box.innerHTML='<p role="status">Loading your trips…</p>';
    try{
      const userPath=`/api/trips/${encodeURIComponent(user().user_id)}`;
      const groups=await Promise.all([api(userPath),api(userPath+'/feedback-pending'),api(userPath+'/archive')]);
      const trips=[...new Map(groups.flat().map(trip=>[trip.id,trip])).values()];
      const enriched=await Promise.all(trips.map(async trip=>{try{return {...trip,runtime:await api(`/api/trips/${encodeURIComponent(trip.id)}/runtime?${query()}`)};}catch(_){return {...trip,runtime:null};}}));
      if(location.hash!=='#/trips')return;
      box.innerHTML='<h2>My trips</h2>'+['Active trips','Past trips'].map((heading,index)=>{
        const group=enriched.filter(t=>index?t.runtime?.status==='completed':t.runtime?.status!=='completed');
        return `<section class="te-card"><h3>${heading}</h3>${group.length?group.map(t=>`<article class="te-list-row"><div><h4>${esc(t.destination_name)}</h4><p>${esc(t.start_date)} – ${esc(t.end_date)}</p><small>${t.runtime?t.runtime.closed_out?'Feedback saved':t.runtime.status==='completed'?'Feedback pending':esc(t.runtime.status):'Progress unavailable — open to retry'}</small></div><a class="te-primary" href="#/trips/${encodeURIComponent(t.id)}">${t.runtime?.status==='completed'&&!t.runtime.closed_out?'Finish feedback':'Open trip'}</a></article>`).join(''):'<p>No trips here yet.</p>'}</section>`;
      }).join('');
      const select=el('userTripsSelect');[...select.options].forEach(option=>{const t=enriched.find(t=>t.id===option.value);if(t?.runtime?.status==='completed')option.remove();});
    }catch(error){box.innerHTML=`<p role="alert">${esc(error.message)}</p><button id="teListRetry">Retry</button>`;el('teListRetry').onclick=listTrips;}
  }
  async function route() {
    const epoch=++routeEpoch;
    const path=location.hash.slice(1)||'/';
    if(!path.startsWith('/trips')) {routing=false;view.hidden=true;if(user())el('dashboardView').classList.remove('hidden');return;}
    if(!user()){view.hidden=true;return;}
    if(!await window.ProfileGate.require()){view.hidden=true;return;}
    if(epoch!==routeEpoch)return;
    if(!Trip.allowPlanning()){view.hidden=true;el('dashboardView').classList.remove('hidden');return;}
    routing=true;
    try {
      view.hidden=false;el('dashboardView').classList.add('hidden');el('teTripList').hidden=true;planner.hidden=false;rawClose('tripFormModal');notice('');
      if(path==='/trips/new') {
        planner.hidden=true;await loadCapabilities();if(epoch!==routeEpoch)return;
        await oldToggle();if(epoch!==routeEpoch)return;
        let saved=false;try{saved=!!sessionStorage.getItem(draftKey());}catch(_){}
        if(saved)restoreDraft();else{el('tripDestSelect').value='';selectedDynamicLocation=null;el('tripNearbyPlacesArea')?.classList.add('hidden');}
        el('tripStartDateInput').min=indiaToday();el('tripEndDateInput').min=el('tripStartDateInput').value||indiaToday();
        modal.classList.remove('hidden');
        window.dispatchEvent(new CustomEvent('trip:creation-ready')); // E: explicit recommendation handoff.
      }
      else if(path==='/trips') {planner.hidden=true;await listTrips();}
      else {
        const match=path.match(/^\/trips\/([^/]+)(\/edit)?$/);if(!match){notice('This trip link is invalid.');return;}
        const id=decodeURIComponent(match[1]);
        await loadCapabilities();
        const next=await api(`/api/trips/${encodeURIComponent(id)}/runtime?${query()}`);
        if(epoch!==routeEpoch)return;
        currentPlannedTripId=id; snapshot=next;snapshotTrip=id;
        // Explicit selection avoids auto-generation while resuming a live or archived trip.
        const itinerary=await api(`/api/itinerary/${encodeURIComponent(id)}?${query()}`);
        if(epoch!==routeEpoch)return;
        currentItinerary=itinerary;renderItinerary(itinerary);
        Trip.applySnapshot(getWorkspaceContext(),next);
        oldMode(next.status==='completed'?'post':next.status==='live'?'live':'pre');
        if(match[2]){if(next.status!=='draft'){notice('Reopen a finalized trip before editing. Live and completed trips cannot be edited.');return;}await editSelectedTrip();await fillExperience(id);restoreDraft();}
      }
      view.querySelector('h2,h3')?.setAttribute('tabindex','-1');view.querySelector('h2,h3')?.focus();
    }catch(error){notice(error.message);}
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
    el('teShopping').checked=!!prefs.include_shopping;el('teFinalActivities').value=prefs.final_day_activities===false?'no':'yes';
    el('tripStartDateInput').min=trip.start_date<indiaToday()?trip.start_date:indiaToday();el('tripEndDateInput').min=el('tripStartDateInput').value;
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
  window.addEventListener('load',route);
  // Keep direct links private when the existing session controller signs out.
  new MutationObserver(()=>{
    if(!el('authView').classList.contains('hidden')){
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
