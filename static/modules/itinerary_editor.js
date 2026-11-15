/* UI: a single timeline. Only server-confirmed changes alter the itinerary. */
TravelModules.register('itinerary_editor', {
  async render(container,ctx) {
    const T=window.TripExperience;
    if(!T){container.textContent='Loading trip tools…';return;}
    // Keep legacy mounts for compatibility; the unified timeline is the visible schedule.
    document.getElementById('itineraryDaysContainer')?.classList.add('hidden');
    document.getElementById('scheduleMarkersMount')?.classList.add('hidden');
    const {esc,api}=T, tripId=ctx.tripId, userId=ctx.userId;
    const query=`user_id=${encodeURIComponent(userId)}`;
    const endpoint=path=>`/api/trip-actions/${encodeURIComponent(tripId)}${path}?${query}`;
    const current=()=>container.isConnected&&getWorkspaceContext().tripId===tripId;
    const activity=b=>['activity','shopping'].includes(b.type)||['activity','shopping'].includes(b.slot_type);
    const money=n=>n!=null&&Number.isFinite(Number(n))?formatINR(Number(n)):'Cost unavailable';
    const costLabel=b=>{const kind=b.type||b.slot_type;return ['transit','travel'].includes(kind)?'Covered by your local transport allowance':kind==='meal'?'Covered by your food allowance':kind==='unplanned'?'No fixed spend planned':money(b.cost_estimate);};
    let data,runtime,weatherData=null,selectedDay=window.ItineraryInsights?.selectedDay(tripId)||1,busy=false,dragId=null;
    function message(text){const node=container.querySelector('[data-status]');if(node)node.textContent=text;}
    async function action(control,work){if(busy||control.disabled)return;busy=true;control.disabled=true;message('');try{await work();}catch(error){if(current())message(error.message);}finally{busy=false;if(control.isConnected)control.disabled=false;}}
    async function load(){
      container.innerHTML='<p role="status">Loading your saved itinerary…</p>';
      try{
        [data,runtime,weatherData]=await Promise.all([api(endpoint('/timed-view')),api(`/api/trips/${encodeURIComponent(tripId)}/runtime?${query}`),api(`/api/prep/${encodeURIComponent(tripId)}/weather?${query}`).catch(()=>null)]);
        if(!current())return;T.applySnapshot(ctx,runtime);render();
      }catch(error){if(current()){container.innerHTML=`<p role="alert" class="te-error">${esc(error.message)}</p><button data-retry>Retry</button>`;container.querySelector('[data-retry]').onclick=load;}}
    }
    function render(){
      if(!current())return;
      const days=data.days||[], day=days.find(d=>d.day_number===selectedDay)||days[0];
      if(!day){container.innerHTML='<p>No timed activities fit this trip. Review the dates and preferences before regenerating.</p>';return;}
      selectedDay=day.day_number;
      const editable=runtime.status==='draft'&&state.profileStatus?.complete===true, all=days.flatMap(d=>d.timeline||[]).filter(activity), blocks=day.timeline||[];
      const accepted=all.filter(b=>T.acceptance(b)==='accepted').length;
      const calendarDate=data.trip?.start_date?new Date(`${data.trip.start_date}T00:00:00Z`):null;
      if(calendarDate&&!Number.isNaN(calendarDate.valueOf()))calendarDate.setUTCDate(calendarDate.getUTCDate()+day.day_number-1);
      const dayDate=calendarDate&&!Number.isNaN(calendarDate.valueOf())?calendarDate.toISOString().slice(0,10):null;
      const weatherDay=(weatherData?.daily||[]).find(item=>item.date===dayDate);
      const topWeather=document.getElementById('itinWeatherCard');if(topWeather)topWeather.hidden=true;
      const weatherHtml=weatherDay?`<p class="te-day-weather" role="note">Weather · ${esc(weatherDay.temp_min_c)}–${esc(weatherDay.temp_max_c)}°C · ${esc(weatherDay.rain_probability_pct)}% rain · ${esc(weatherDay.label||weatherData.label||'Estimate')}</p>`:`<p class="te-day-weather" role="note">Weather unavailable for this day. Check again when a forecast is available.</p>`;
      const tripPrefs=data.trip?.trip_preferences||{};const stay=tripPrefs.accommodation||{};
      const stayReminder=(!stay.property_name||stay.expected_total_cost_inr==null)?'<aside class="te-marker"><strong>Accommodation details needed before finalizing.</strong> Review the suggested neighbourhood in Stays, then enter the property name and full expected cost in Edit trip. The app does not book accommodation.</aside>':'';
      const dayTitle=`Day ${selectedDay}${dayDate?` · ${new Date(`${dayDate}T00:00:00Z`).toLocaleDateString(undefined,{weekday:'short',month:'short',day:'numeric',timeZone:'UTC'})}`:''}`;
      container.innerHTML=`<section class="te-card"><h3>${esc(data.trip?.destination_name||'Your itinerary')}</h3><p>${editable?'Review each activity, then finalize when ready.':'Saved itinerary · read only'}</p>${stayReminder}
        <p>${accepted} of ${all.length} activities accepted${T.can('occurrence_acceptance')?'':' · Individual acceptance awaits the server update.'}</p>
        <nav class="te-day-nav" aria-label="Itinerary day">${days.map(d=>`<button data-day="${d.day_number}" aria-current="${d.day_number===selectedDay}">Day ${d.day_number}</button>`).join('')}</nav>
        <div class="te-toolbar"><button data-print>Print itinerary</button><button data-map>Open day route</button>
        ${editable?`<button data-balance ${T.can('itinerary_preview')?'':'disabled'}>Balance all days</button><button data-all ${T.can('occurrence_acceptance')?'':'disabled'}>Accept all activities</button><button data-custom ${T.can('custom_activities')?'':'disabled'}>Add custom activity</button><button data-undo ${data.undo_token&&T.can('itinerary_preview')?'':'disabled'}>Undo last edit</button>`:''}
        <button data-expenses ${T.can('expenses')?'':'disabled'}>Expenses</button><button data-share ${T.can('readonly_sharing')?'':'disabled'}>Share read-only</button></div>
        <p data-status role="status" class="te-error"></p><h4 class="font-bold">${dayTitle}${day.formatted_date&& !/^Day\s+\d+$/i.test(day.formatted_date)?` · ${esc(day.formatted_date)}`:''}</h4>${weatherHtml}
        ${(day.markers||[{label:'Accommodation arrival',time:day.arrival_marker},{label:'Accommodation check-out',time:day.departure_marker}]).filter(m=>m.time).map(m=>`<p class="te-marker">${esc(m.label)} · ${esc(m.time)}</p>`).join('')}
        ${day.note?`<p class="te-marker">${esc(T.publicText(day.note))}</p>`:''}
        ${(day.conflicts||[]).map(c=>`<p role="alert" class="te-error">${esc(T.publicText(c.message||c))}</p>`).join('')}
        <ol class="te-timeline">${blocks.map((b,index)=>{
          const id=T.occurrenceId(b), kind=b.type||b.slot_type||'activity', choice=T.acceptance(b), edit=editable&&activity(b)&&id;
          const disabled=!T.can('itinerary_preview')||b.pinned?'disabled':'';
          return `<li class="te-stop" data-occurrence="${esc(id||'')}" ${edit&&!disabled?'draggable="true"':''}><div class="te-stop-time">${esc(b.time_range||[b.start_time,b.end_time].filter(Boolean).join(' – ')||'Time unavailable')}</div><article class="te-stop-content" data-kind="${esc(kind)}"><small>${index+1} · ${esc(b.slot_type_label||kind.replace(/_/g,' '))}${b.duration_minutes!=null?' · '+esc(b.duration_minutes)+' min':''}</small><h4>${esc(b.title||b.name)}</h4><p>${esc(b.neighborhood||b.location||'')}</p><p>${esc(T.publicText(b.description))}</p><p>${esc(costLabel(b))}${b.is_fixed_booking?' · confirmed booking cost':b.is_estimate?' · estimate':''}</p>
          ${activity(b)?`<p>${choice==='unreviewed'?'Not reviewed':choice==='accepted'?'Accepted':'Not selected'}${b.is_fixed_booking?' · Confirmed booking and cost':b.pinned?' · Pinned':''}${b.must_visit?' · Must visit':''}</p>`:''}
          ${b.provenance?.booking_required?`<p class="te-booking-note">Booking required · proposed Day ${esc(b.provenance.proposed_day||day.day_number)}, ${esc(b.provenance.proposed_start_time||'time not set')}–${esc(b.provenance.proposed_end_time||'time not set')}. Confirm availability directly with the venue.</p>`:''}
          ${edit?`<div class="te-stop-actions"><button data-choice="accept" ${T.can('occurrence_acceptance')?'':'disabled'}>Keep activity</button><button data-edit="earlier" ${disabled} aria-label="Move ${esc(b.title)} earlier">↑ Earlier</button><button data-edit="later" ${disabled} aria-label="Move ${esc(b.title)} later">↓ Later</button><button data-edit="move_day" ${disabled}>Move day</button><button data-edit="swap" ${disabled}>Recommend other</button><button data-edit="remove" ${disabled}>Remove</button>${(b.provenance?.booking_required||b.requires_booking||b.booking_required||b.requires_advance_booking)&&!b.is_fixed_booking?`<button data-booking ${T.can('itinerary_preview')?'':'disabled'}>Fix in itinerary</button>`:''}<button data-edit="pin" ${T.can('itinerary_preview')?'':'disabled'}>${b.pinned?'Unpin':'Pin activity'}</button><button data-edit="must_visit" ${T.can('itinerary_preview')?'':'disabled'}>${b.must_visit?'Unmark':'Mark'} must visit</button></div>`:''}</article></li>`;
        }).join('')}</ol><p>Times and travel costs are estimates unless marked verified. Missing travel times must be resolved before finalizing.</p></section>`;
      container.querySelectorAll('[data-day]').forEach(b=>b.onclick=()=>{selectedDay=Number(b.dataset.day);render();});
      container.querySelector('[data-print]').onclick=printItinerary;
      container.querySelector('[data-map]').onclick=()=>{
        const stops=blocks.filter(activity).map(b=>b.coordinates||(b.lat!=null&&b.lon!=null?[b.lat,b.lon]:null));
        if(!stops.length||stops.some(c=>!Array.isArray(c)||c.length!==2||!c.every(v=>Number.isFinite(Number(v)))||Math.abs(c[0])>90||Math.abs(c[1])>180)){message('Coordinates are unavailable for one or more stops. No route has been invented.');return;}
        const points=stops.map(c=>c.map(Number).join(',')),url=new URL('https://www.google.com/maps/dir/');url.searchParams.set('api','1');url.searchParams.set('origin',points[0]);url.searchParams.set('destination',points.at(-1));if(points.length>2)url.searchParams.set('waypoints',points.slice(1,-1).join('|'));window.open(url.href,'_blank','noopener,noreferrer');
      };
      container.querySelectorAll('[data-choice]').forEach(b=>b.onclick=()=>action(b,async()=>{await api(endpoint('/acceptance'),{method:'POST',body:{itinerary_activity_id:b.closest('[data-occurrence]').dataset.occurrence,action:b.dataset.choice}});await load();}));
      container.querySelector('[data-all]')?.addEventListener('click',event=>action(event.currentTarget,async()=>{if(!confirm(`Accept all ${all.length} scheduled activities?`))return;await api(endpoint('/acceptance'),{method:'POST',body:{action:'accept_all',occurrence_ids:all.map(T.occurrenceId)}});await load();}));
      container.querySelectorAll('[data-edit]').forEach(b=>b.onclick=()=>edit(b,b.closest('[data-occurrence]').dataset.occurrence,b.dataset.edit));
      container.querySelectorAll('[data-booking]').forEach(button=>button.onclick=()=>bookingForm(button.closest('[data-occurrence]').dataset.occurrence,blocks.find(item=>T.occurrenceId(item)===button.closest('[data-occurrence]').dataset.occurrence)));
      container.querySelectorAll('[draggable=true]').forEach(row=>{
        row.addEventListener('dragstart',e=>{dragId=row.dataset.occurrence;e.dataTransfer.setData('text/plain',dragId);});row.addEventListener('dragover',e=>e.preventDefault());row.addEventListener('drop',e=>{e.preventDefault();const target=row.dataset.occurrence;if(dragId&&target&&dragId!==target)preview({operation:'reorder',target_activity_id:dragId,before_activity_id:target});dragId=null;});row.addEventListener('dragend',()=>{dragId=null;});
      });
      container.querySelector('[data-balance]')?.addEventListener('click',()=>preview({operation:'rebalance'}));
      container.querySelector('[data-undo]')?.addEventListener('click',e=>action(e.currentTarget,async()=>{await api(endpoint('/undo'),{method:'POST',body:{token:data.undo_token}});await load();}));
      container.querySelector('[data-custom]')?.addEventListener('click',customActivity);
      container.querySelector('[data-expenses]').onclick=expenses;container.querySelector('[data-share]').onclick=share;
      window.dispatchEvent(new CustomEvent('trip:timeline-rendered',{detail:{tripId,dayNumber:selectedDay,data,runtime,container}})); // E: explanation/check extensions.
    }
    function dialog(title,html){const box=document.createElement('dialog');box.className='te-dialog';box.innerHTML=`<h3 class="font-bold mb-3">${esc(title)}</h3>${html}<p data-error role="alert" class="te-error"></p><button data-close class="mt-3 border rounded p-2">Cancel / close</button>`;document.body.append(box);box.querySelector('[data-close]').onclick=()=>box.close();box.addEventListener('close',()=>box.remove());box.showModal();return box;}
    async function dialogAction(box,button,work){if(button.disabled)return;button.disabled=true;try{await work();}catch(error){if(box.isConnected)box.querySelector('[data-error]').textContent=error.message;}finally{if(button.isConnected)button.disabled=false;}}
    async function preview(body){
      if(!T.can('itinerary_preview')||busy)return;busy=true;
      try{
        const result=await api(endpoint('/preview'),{method:'POST',body});if(!current())return;const change=result.preview||result;
        if(!change.token)throw new Error('No confirmation token was returned. The itinerary has not changed.');
        if(body.operation==='move_day'){
          const moved=(change.timeline||[]).find(item=>String(item.id||item.occurrence_id||'')===String(body.target_activity_id));
          if(!moved||Number(moved.day_number)!==Number(body.target_day))throw new Error('No compatible open slot is available on that day. Use Recommend other or choose another day.');
        }
        const before=(data.days||[]).flatMap(d=>(d.timeline||[]).map(item=>({...item,day_number:d.day_number}))).find(item=>String(T.occurrenceId(item))===String(body.target_activity_id));
        const after=(change.timeline||[]).find(item=>String(item.id||item.occurrence_id||'')===String(body.target_activity_id));
        const consequence=body.operation==='swap'&&before&&after?`<p><strong>Current:</strong> Day ${before.day_number} · ${esc(before.time_range||'Time unavailable')} · ${esc(before.title||before.name)}</p><p><strong>After:</strong> Day ${after.day_number} · ${esc(after.time_range||'Time unavailable')} · ${esc(after.title||after.name)}</p>`:'';
        const box=dialog('Review itinerary change',`<p>${esc(T.publicText(change.summary||change.title))}</p>${consequence}<p>${esc(change.time_impact||'Review the updated times below.')}</p><p>${esc(change.budget_impact||'')}</p><p>Confirm to apply this change. Close this preview to keep the current itinerary.</p>${(change.warnings||[]).map(w=>`<p class="te-error">${esc(T.publicText(w))}</p>`).join('')}<ol>${(change.timeline||[]).map(b=>`<li>Day ${b.day_number||''} · ${esc(b.time_range)} · ${esc(b.title)}</li>`).join('')}</ol><button data-confirm class="te-primary mt-3">Confirm change</button>`);
        box.querySelector('[data-confirm]').onclick=e=>dialogAction(box,e.currentTarget,async()=>{await api(endpoint('/confirm'),{method:'POST',body:{token:change.token}});box.close();await load();});
      }catch(error){if(current())message(error.message);}finally{busy=false;}
    }
    async function edit(button,id,operation){
      if(operation==='move_day'){const currentDay=Number(data.days.find(d=>d.timeline?.some(item=>T.occurrenceId(item)===id))?.day_number);const otherDays=data.days.filter(d=>d.day_number!==currentDay);const box=dialog('Move to another day',`<p>Choose a day, then preview it. The scheduler checks whether the activity fits. If there is no open slot, use “Recommend other” or choose a different day.</p>${otherDays.length?`<label>Day<select data-day class="border rounded p-2">${otherDays.map(d=>`<option value="${d.day_number}">Day ${d.day_number} · slot checked on preview</option>`).join('')}</select></label><button data-preview class="te-primary">Check slot and preview move</button>`:'<p>This is the only itinerary day. Use “Recommend other” to choose a different activity.</p>'}`);box.querySelector('[data-preview]')?.addEventListener('click',()=>{const day=Number(box.querySelector('[data-day]').value);box.close();preview({operation,target_activity_id:id,target_day:day});});return;}
      if(operation==='swap'){
        await action(button,async()=>{const result=await api(endpoint(`/occurrences/${encodeURIComponent(id)}/alternatives`));const box=dialog('Suggested alternatives',`${(result.alternatives||[]).map(a=>`<button data-alt="${esc(a.id)}" class="block border rounded p-3 my-2 w-full text-left"><strong>${esc(a.name||a.title)}</strong><p>${esc(T.publicText(a.description))}</p><small>${esc(money(a.cost_amount))}</small></button>`).join('')||'<p>No alternatives fit this activity.</p>'}`);box.querySelectorAll('[data-alt]').forEach(b=>b.onclick=()=>{box.close();preview({operation:'swap',target_activity_id:id,replacement_activity_id:b.dataset.alt});});});return;
      }
      preview({operation:['earlier','later'].includes(operation)?'reschedule':operation,target_activity_id:id,...(['earlier','later'].includes(operation)?{direction:operation}:{})});
    }
    function bookingForm(id,activity){
      const box=dialog('Fix confirmed booking time',`<p>Book directly with the venue first. This only updates your itinerary; the app does not make the booking.</p><form data-booking-form class="te-card"><label><input name="confirmed" type="checkbox" required> I have confirmed this booking</label><label>Booked start time<input name="start" type="time" required value="${esc(activity?.booking_start_time||'')}"></label><label>Booked end time<input name="end" type="time" required value="${esc(activity?.booking_end_time||'')}"></label><label>Confirmed full cost (INR)<input name="cost" type="number" min="0" max="1000000000" step="1" required value="${Number.isInteger(Number(activity?.cost_estimate))?Number(activity.cost_estimate):''}"></label><label>Booking label<input name="label" maxlength="120" required value="${esc(activity?.booking_label||activity?.title||'Confirmed activity booking')}"></label><button class="te-primary">Preview fixed slot</button></form>`);
      box.querySelector('[data-booking-form]').onsubmit=event=>{event.preventDefault();const form=event.currentTarget,v=Object.fromEntries(new FormData(form));if(!form.elements.confirmed.checked){box.querySelector('[data-error]').textContent='Confirm that you have booked this activity first.';return;}if(!v.start||!v.end||v.end<=v.start){box.querySelector('[data-error]').textContent='Choose a valid start and end time on the same day.';return;}if(!/^\d+$/.test(v.cost)||Number(v.cost)<0||Number(v.cost)>1000000000){box.querySelector('[data-error]').textContent='Enter a whole-rupee cost from 0 to 1,000,000,000.';return;}if(!v.label.trim()||v.label.length>120){box.querySelector('[data-error]').textContent='Enter a booking label up to 120 characters.';return;}box.close();preview({operation:'fix_booking',target_activity_id:id,booking_confirmed:true,booking_start_time:v.start,booking_end_time:v.end,booking_cost_inr:Number(v.cost),booking_label:v.label.trim()});};
    }
    function customActivity(){
      const box=dialog('Add custom activity','<form class="te-card"><label>Name<input name="title" maxlength="120" required></label><label>Location<input name="location" maxlength="200" required></label><label>Duration (minutes)<input name="duration_minutes" type="number" min="15" max="480" step="1" required></label><label>Budget (INR)<input name="cost" type="number" min="0" max="1000000" step="1" value="0" required></label><button class="te-primary">Preview addition</button></form>');
      box.querySelector('form').onsubmit=e=>{e.preventDefault();const v=Object.fromEntries(new FormData(e.currentTarget));if(!v.title.trim()||!v.location.trim()){box.querySelector('[data-error]').textContent='Enter a name and location.';return;}box.close();preview({operation:'add_custom',target_day:selectedDay,activity:{title:v.title.trim(),location:v.location.trim(),duration_minutes:Number(v.duration_minutes),cost:Number(v.cost)}});};
    }
    async function expenses(){
      const box=dialog('Trip expenses','<p data-summary>Loading expenses…</p><form class="te-card"><label>Category<select name="category"><option value="other">Other</option><option value="food">Food</option><option value="stay">Stay</option><option value="transport">Transport</option><option value="activities">Activities</option><option value="shopping">Shopping</option></select></label><label>Date<input type="date" name="spent_on" required></label><label>Description<input name="description" maxlength="200" required></label><label>Actual amount (INR)<input type="number" name="amount" min="1" max="1000000" step="1" required></label><button class="te-primary">Save expense</button></form>');
      box.querySelector('[name=spent_on]').value=T.indiaToday();
      try{const result=await api(`/api/trips/${encodeURIComponent(tripId)}/expenses?${query}`);const s=result.budget||result.planned_vs_actual||{},date=box.querySelector('[name=spent_on]');if(s.start_date){date.min=s.start_date;date.max=s.end_date;date.value=date.value<s.start_date?s.start_date:date.value>s.end_date?s.end_date:date.value;}if(box.isConnected)box.querySelector('[data-summary]').textContent=`Planned: ${money(result.planned_vs_actual?.planned_total_inr)} · Actual: ${money(result.planned_vs_actual?.actual_total_inr)} · spending entered so far`;}catch(error){if(box.isConnected)box.querySelector('[data-error]').textContent=error.message;}
      box.querySelector('form').onsubmit=e=>{e.preventDefault();const form=e.currentTarget,v=Object.fromEntries(new FormData(form));if(!v.description.trim())return;dialogAction(box,form.querySelector('button'),async()=>{const result=await api(`/api/trips/${encodeURIComponent(tripId)}/expenses?${query}`,{method:'POST',body:{note:v.description.trim(),amount_inr:Number(v.amount),category:form.elements.category.value,spent_on:form.elements.spent_on.value}});box.querySelector('[data-summary]').textContent=`Actual spending entered: ${money(result.planned_vs_actual?.actual_total_inr)}`;form.reset();window.dispatchEvent(new CustomEvent('experience:expenses-updated',{detail:{tripId}}));});};
    }
    function share(){
      const box=dialog('Share a read-only itinerary','<p>The shared view contains only the itinerary. Residence, account details, reviews and private notes remain private. Anyone with the link can view it until revoked.</p><button data-create class="te-primary mt-3">Create read-only link</button><button data-revoke class="border rounded p-2 ml-2">Revoke links</button><p data-result role="status"></p>');
      box.querySelector('[data-create]').onclick=e=>dialogAction(box,e.currentTarget,async()=>{const result=await api(`/api/trips/${encodeURIComponent(tripId)}/share?${query}`,{method:'POST',body:{read_only:true}});const url=new URL(result.url_path,location.origin);if(url.origin!==location.origin||!['https:','http:'].includes(url.protocol))throw new Error('The sharing service returned an invalid link.');const a=document.createElement('a');a.href=url.href;a.textContent=url.href;a.target='_blank';a.rel='noopener noreferrer';box.querySelector('[data-result]').replaceChildren(a);});
      box.querySelector('[data-revoke]').onclick=e=>dialogAction(box,e.currentTarget,async()=>{await api(`/api/trips/${encodeURIComponent(tripId)}/share?${query}`,{method:'DELETE'});box.querySelector('[data-result]').textContent='All sharing links revoked.';});
    }
    function printItinerary(){
      const frame=document.createElement('iframe');frame.title='Printable itinerary';frame.hidden=true;document.body.append(frame);const doc=frame.contentDocument;
      doc.open();doc.write(`<!doctype html><html><head><title>Trip itinerary</title><style>body{font:14px sans-serif;color:#172033;padding:24px}h2{break-before:page}li{margin:12px 0;break-inside:avoid}small{display:block}</style></head><body><h1>${esc(data.trip?.destination_name)}</h1>${data.days.map(day=>`<h2>Day ${day.day_number}</h2>${day.note?`<p>${esc(T.publicText(day.note))}</p>`:''}<ol>${(day.timeline||[]).map(b=>`<li><strong>${esc(b.time_range)} · ${esc(b.title)}</strong><small>${esc(b.location||b.neighborhood||'')} · ${esc(costLabel(b))}</small></li>`).join('')}</ol>`).join('')}<p>Times and costs may be estimates.</p></body></html>`);doc.close();frame.contentWindow.focus();frame.contentWindow.print();setTimeout(()=>frame.remove(),1000);
    }
    await load();
  }
});
