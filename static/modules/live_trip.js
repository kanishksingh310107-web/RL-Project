// C: persisted execution flow. Existing schedule and replan APIs remain authoritative.
(function () {
  const state = {snapshot:null, epoch:0, busy:false};
  let resumedTrip=null;
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const label = value => String(value).replace(/_/g,' ').replace(/\b\w/g,c=>c.toUpperCase());
  const button = 'px-3 py-2 rounded-lg bg-indigo-600 text-white text-xs font-semibold disabled:opacity-50';
  const isCurrent = ctx => typeof getWorkspaceContext!=='function' || getWorkspaceContext().tripId===ctx.tripId;
  const errorBox = error => `<p role="alert" class="text-xs text-rose-700 mt-2">${esc(error.message)}</p>`;

  async function api(ctx,path,body,method='POST') {
    let response;
    try {
      response=await fetch(`/api/trips/${encodeURIComponent(ctx.tripId)}${path}${path.includes('?')?'&':'?'}user_id=${encodeURIComponent(ctx.userId)}`,{
        method,headers:{'Content-Type':'application/json'},...(method==='GET'?{}:{body:JSON.stringify(body || {})})});
    } catch (_) { throw new Error('Connection failed. Your entered information has been kept. Please retry.'); }
    let data;
    try { data=await response.json(); } catch (_) { throw new Error('The server response could not be read. Please retry.'); }
    if(!response.ok) {
      const error=new Error(typeof data.detail==='string'?data.detail:'The request could not be completed.');
      error.field=data.field; error.code=data.code; throw error;
    }
    return data;
  }

  function applyLocks(snapshot) {
    const locked=snapshot.status!=='draft';
    for(const id of ['workspaceEditorContainer','itineraryDaysContainer']) {
      document.getElementById(id)?.querySelectorAll('button,input,select,textarea').forEach(control=>{
        control.disabled=locked; control.title=locked?'Itinerary locked by trip runtime':'';
      });
    }
    document.querySelectorAll('#btnFinalizeTrip,#btnStartTrip').forEach(control=>{control.hidden=true;});
    document.querySelectorAll('[onclick="editSelectedTrip()"]').forEach(control=>{control.disabled=locked;});
  }

  function lifecycle(ctx,snapshot) {
    if(!isCurrent(ctx)) return;
    state.snapshot=snapshot;
    const box=document.getElementById('cTripLifecycle');
    if(!box) return;
    const action=snapshot.status==='draft'?'Finalize itinerary':snapshot.status==='finalized'?'Start trip':null;
    box.innerHTML=`<div class="flex flex-wrap items-center gap-3"><strong>${esc(label(snapshot.status))}</strong>
      ${action?`<button class="${button}" data-c-lifecycle>${action}</button>`:''}
      ${snapshot.status==='finalized'?'<button class="border rounded-lg px-3 py-2" data-c-reopen>Reopen to edit</button>':''}
      <span>${snapshot.feedback_required?'Post-trip feedback required to close out this trip.':snapshot.closed_out?'Trip closed out. Feedback saved.':snapshot.status==='live'?`Day ${snapshot.runtime.current_day} of ${snapshot.total_days}`:'Finalize your itinerary when ready.'}</span></div><div data-c-error></div>`;
    box.querySelector('[data-c-lifecycle]')?.addEventListener('click',async event=>{
      await submitButton(event.currentTarget,box,async()=>{
        const next=await api(ctx,snapshot.status==='draft'?'/finalize':'/start');
        if(!isCurrent(ctx)) return;
        lifecycle(ctx,next);
        if(next.status==='live') switchWorkspaceMode('live');
      });
    });
    box.querySelector('[data-c-reopen]')?.addEventListener('click',async event=>{
      await submitButton(event.currentTarget,box,async()=>{
        const next=await api(ctx,'/unfinalize');
        if(!isCurrent(ctx)) return;
        lifecycle(ctx,next);
        await loadTripItinerary(ctx.tripId);
      });
    });
    applyLocks(snapshot);
  }

  async function submitButton(control,box,work) {
    if(control.disabled) return;
    control.disabled=true;
    const errors=box.querySelector('[data-c-error]');
    if(errors) errors.innerHTML='';
    try { await work(); }
    catch(error) {
      const rating=error.field?.startsWith('ratings.')?error.field.split('.').pop():null;
      const field=error.field?box.querySelector(`[data-field-error="${error.field}"]`):null;
      const ratingField=rating?box.querySelector(`[data-rating-error="${rating}"]`):null;
      if(field || ratingField) (field || ratingField).textContent=error.message;
      else if(errors) errors.innerHTML=errorBox(error);
    }
    finally { if(control.isConnected) control.disabled=false; }
  }

  async function loadLifecycle() {
    const ctx=typeof getWorkspaceContext==='function'?getWorkspaceContext():null;
    if(!ctx?.tripId || !ctx.userId) return;
    const requestTrip=ctx.tripId;
    try {
      const snapshot=await api(ctx,'/runtime',null,'GET');
      if(getWorkspaceContext().tripId===requestTrip) {
        lifecycle(ctx,snapshot);
        if(resumedTrip!==requestTrip) {
          resumedTrip=requestTrip;
          if(snapshot.status==='live') switchWorkspaceMode('live');
          else if(snapshot.status==='completed') switchWorkspaceMode('post');
        }
      }
    } catch(error) {
      const box=document.getElementById('cTripLifecycle');
      if(box && getWorkspaceContext().tripId===requestTrip) box.innerHTML=errorBox(error);
    }
  }

  function ratingFields(keys,values={}) {
    return keys.map(key=>`<label class="block text-xs">${esc(label(key))}
      <select name="rating_${esc(key)}" data-rating="${esc(key)}" class="block border border-slate-300 rounded-lg p-2 w-full mt-1" required>
      <option value="">Select 1–5</option>${[1,2,3,4,5].map(n=>`<option value="${n}" ${Number(values[key])===n?'selected':''}>${n}</option>`).join('')}</select>
      <span class="block text-rose-700" data-rating-error="${esc(key)}"></span></label>`).join('');
  }

  function readRatings(form,requireAll=true) {
    const ratings={}; let valid=true;
    form.querySelectorAll('[data-rating]').forEach(field=>{
      const number=Number(field.value);
      const okay=field.value!=='' && Number.isInteger(number) && number>=1 && number<=5;
      const error=form.querySelector(`[data-rating-error="${field.dataset.rating}"]`);
      if(!okay && (requireAll || field.value!=='')) { valid=false; if(error) error.textContent='Choose an integer from 1 to 5.'; }
      else { if(error) error.textContent=''; if(okay) ratings[field.dataset.rating]=number; }
    });
    return valid?ratings:null;
  }

  async function render(container,ctx) {
    const epoch=++state.epoch;
    container.innerHTML='<p class="text-xs text-slate-500">Loading saved trip progress…</p>';
    if(!ctx.tripId || !ctx.userId) { container.textContent='Select a trip to begin.'; return; }
    try {
      const snapshot=await api(ctx,'/runtime',null,'GET');
      if(epoch!==state.epoch || !isCurrent(ctx)) return;
      lifecycle(ctx,snapshot);
      renderSnapshot(container,ctx,snapshot);
    } catch(error) {
      if(epoch===state.epoch && isCurrent(ctx)) container.innerHTML=errorBox(error)+'<button data-c-retry class="border rounded p-2 text-xs">Retry</button>';
      container.querySelector('[data-c-retry]')?.addEventListener('click',()=>render(container,ctx));
    }
  }

  function renderSnapshot(container,ctx,snapshot) {
    if(!isCurrent(ctx)) return;
    lifecycle(ctx,snapshot);
    if(snapshot.status==='completed') {
      container.innerHTML='<p class="text-sm font-semibold">Trip completed.</p><p class="text-xs">Open POST-TRIP to save or resume the required feedback.</p><button class="'+button+' mt-3" data-c-post>Open post-trip feedback</button>';
      container.querySelector('[data-c-post]').onclick=()=>switchWorkspaceMode('post'); return;
    }
    if(snapshot.status!=='live') {
      container.innerHTML='<p class="text-sm">Finalize the itinerary, then press Start trip in the trip controls above.</p>'; return;
    }
    const current=snapshot.current_activity;
    const dayRuns=snapshot.runs.filter(run=>run.day_number===snapshot.runtime.current_day);
    container.innerHTML=`<div class="space-y-4"><div><h3 class="text-sm font-bold">Day ${snapshot.runtime.current_day} of ${snapshot.total_days}</h3>
      <span class="text-xs text-slate-500">Your progress is saved automatically.</span></div>
      ${current?`<div class="rounded-xl border border-indigo-200 bg-indigo-50 p-4"><span class="text-xs font-semibold">Current activity · In progress</span>
        <h4 class="font-bold mt-1">${esc(current.title)}</h4><p class="text-xs mt-1">${esc(current.neighborhood || '')}</p>
        <label class="block text-xs mt-3">How did it finish?<select data-c-outcome class="border rounded-lg p-2 ml-2"><option value="completed">Completed</option><option value="early_ended">Ended early</option><option value="skipped">Skipped</option><option value="not_done">Not done</option></select></label>
        <button class="${button} mt-3" data-c-end>${esc(snapshot.end_activity_label)}</button></div>`:''}
      <div data-c-review></div><div data-c-decision></div>
      ${snapshot.phase==='day_summary'?`<div class="p-3 bg-emerald-50 rounded-xl"><strong>Day ${snapshot.runtime.current_day} summary</strong><p class="text-xs mt-1">${dayRuns.filter(r=>r.outcome==='completed').length} completed, ${dayRuns.filter(r=>r.outcome==='early_ended').length} ended early, ${dayRuns.filter(r=>['skipped','not_done'].includes(r.outcome)).length} skipped/not done.</p>
        <button class="${button} mt-3" data-c-next>${snapshot.runtime.current_day<snapshot.total_days?`Start day ${snapshot.runtime.current_day+1}`:'End trip'}</button></div>`:''}
      ${snapshot.phase==='awaiting_day_end'?`<button class="${button}" data-c-close-day>${snapshot.runtime.current_day===snapshot.total_days?'End trip':'End day'}</button>`:''}
      <details class="border rounded-xl p-3"><summary class="text-xs font-semibold">Rest of this day and activity history</summary><ul class="space-y-2 mt-2">${snapshot.today.map(slot=>`<li class="text-xs">${esc(slot.title)} · ${esc(slot.run?label(slot.run.outcome):'Upcoming')}</li>`).join('')}</ul></details>
      ${current?'<details class="border rounded-xl p-3"><summary class="text-xs font-semibold">End day with unfinished activities</summary><p class="text-xs mt-2">Each unfinished activity must explicitly be marked skipped or not done.</p><div data-c-marks></div><button class="'+button+' mt-2" data-c-mark-end>Save marked outcomes and end day</button></details>':''}
      <div data-c-alerts></div><div data-c-error></div></div>`;
    const refresh=next=>renderSnapshot(container,ctx,next);
    container.querySelector('[data-c-end]')?.addEventListener('click',event=>submitButton(event.currentTarget,container,async()=>{
      refresh(await api(ctx,`/activities/${encodeURIComponent(current.id)}/end`,{outcome:container.querySelector('[data-c-outcome]').value}));
    }));
    const boundary=async()=>{
      let next=await api(ctx,`/days/${snapshot.runtime.current_day}/end`,{dispositions:{}});
      if(!isCurrent(ctx)) return;
      if(snapshot.runtime.current_day===snapshot.total_days) {
        next=await api(ctx,'/end'); if(!isCurrent(ctx)) return; lifecycle(ctx,next); switchWorkspaceMode('post');
      } else refresh(next);
    };
    container.querySelector('[data-c-close-day]')?.addEventListener('click',event=>submitButton(event.currentTarget,container,boundary));
    container.querySelector('[data-c-next]')?.addEventListener('click',event=>submitButton(event.currentTarget,container,async()=>{
      if(snapshot.runtime.current_day===snapshot.total_days) { const next=await api(ctx,'/end'); if(!isCurrent(ctx)) return; lifecycle(ctx,next); switchWorkspaceMode('post'); }
      else refresh(await api(ctx,`/days/${snapshot.runtime.current_day+1}/start`));
    }));
    if(snapshot.pending_review) renderReview(container.querySelector('[data-c-review]'),container,ctx,snapshot,refresh);
    if(snapshot.pending_decision) renderDecision(container.querySelector('[data-c-decision]'),ctx,snapshot,refresh);
    const marks=container.querySelector('[data-c-marks]');
    if(marks) {
      const unfinished=snapshot.today.filter(slot=>!slot.run || !slot.run.ended_at);
      marks.innerHTML=unfinished.map(slot=>`<label class="block text-xs my-2">${esc(slot.title)}<select class="border rounded p-1 ml-2" data-c-disposition="${esc(slot.id)}"><option value="">Choose an outcome</option><option value="skipped">Skipped</option><option value="not_done">Not done</option></select><span class="text-rose-700" data-c-mark-error></span></label>`).join('');
      container.querySelector('[data-c-mark-end]').onclick=event=>submitButton(event.currentTarget,container,async()=>{
        const dispositions={}; let valid=true;
        marks.querySelectorAll('[data-c-disposition]').forEach(field=>{
          field.parentElement.querySelector('[data-c-mark-error]').textContent=field.value?'':' Choose skipped or not done.';
          if(!field.value) valid=false; else dispositions[field.dataset.cDisposition]=field.value;
        });
        if(valid) refresh(await api(ctx,`/days/${snapshot.runtime.current_day}/end`,{dispositions}));
      });
    }
    renderAlerts(container.querySelector('[data-c-alerts]'),ctx,snapshot);
  }

  function renderReview(box,container,ctx,snapshot,refresh) {
    const slot=snapshot.pending_review;
    const skipped=['skipped','not_done'].includes(slot.run.outcome);
    const key=`c_activity_draft_${ctx.tripId}_${slot.id}`;
    let draft={}; try { draft=JSON.parse(localStorage.getItem(key)||'{}'); } catch (_) { /* storage is optional */ }
    box.innerHTML=`<form class="p-4 border rounded-xl space-y-3" novalidate><h4 class="text-sm font-bold">Review: ${esc(slot.title)}</h4>
      ${skipped?'<p class="text-xs">No ratings are required for an activity you did not do.</p>':`<div class="grid grid-cols-2 gap-3">${ratingFields(slot.applicable_rating_keys,draft.ratings)}</div>`}
      <label class="block text-xs">Optional note<textarea name="notes" maxlength="1000" class="block w-full border rounded-lg p-2 mt-1">${esc(draft.notes||'')}</textarea><span data-c-note-error class="text-rose-700"></span></label>
      <label class="block text-xs font-semibold">Enhance the itinerary, change it, or leave it as it is?
        <select name="action" class="block w-full border rounded-lg p-2 mt-1" required><option value="">Choose an answer</option>${[['keep','Leave it as it is'],['enhance','Enhance the remaining trip'],['change','Change upcoming activities']].map(([value,text])=>`<option value="${value}" ${draft.action===value?'selected':''}>${text}</option>`).join('')}</select><span data-c-action-error class="text-rose-700"></span></label>
      <button class="${button}" type="submit">Save review and continue</button><div data-c-error></div></form>`;
    const form=box.querySelector('form');
    form.addEventListener('input',()=>{
      const ratings={}; form.querySelectorAll('[data-rating]').forEach(field=>{if(field.value) ratings[field.dataset.rating]=Number(field.value);});
      try { localStorage.setItem(key,JSON.stringify({ratings,notes:form.elements.notes.value,action:form.elements.action.value})); } catch (_) { /* form remains usable */ }
    });
    form.onsubmit=event=>{
      event.preventDefault();
      const ratings=skipped?{}:readRatings(form);
      const action=form.elements.action.value;
      const notes=form.elements.notes.value.trim();
      form.querySelector('[data-c-action-error]').textContent=['keep','enhance','change'].includes(action)?'':'Choose keep, enhance or change.';
      form.querySelector('[data-c-note-error]').textContent=notes.length<=1000?'':'Use at most 1,000 characters.';
      if(ratings===null || !['keep','enhance','change'].includes(action) || notes.length>1000) return;
      submitButton(form.querySelector('button'),form,async()=>{
        const next=await api(ctx,`/activities/${encodeURIComponent(slot.id)}/review`,{ratings,action,notes});
        try { localStorage.removeItem(key); } catch (_) { /* optional */ }
        refresh(next);
      });
    };
  }

  async function renderDecision(box,ctx,snapshot,refresh) {
    box.innerHTML=`<div class="p-3 border rounded-xl space-y-3"><h4 class="text-sm font-bold">${snapshot.pending_decision.action==='enhance'?'Improve the remaining trip':'Change upcoming activities'}</h4><p class="text-xs">Review a proposed change before confirming it. Your current itinerary is kept until then.</p>
      <button class="${button}" data-c-suggest>Suggest alternatives</button><button class="border rounded-lg px-3 py-2 text-xs" data-c-continue>Leave it as it is and continue</button><div data-c-proposals></div><div data-c-preview></div><div data-c-error></div></div>`;
    box.querySelector('[data-c-continue]').onclick=event=>submitButton(event.currentTarget,box,async()=>refresh(await api(ctx,'/continue')));
    const previewBox=box.querySelector('[data-c-preview]');
    function showPreview(preview) {
      previewBox.innerHTML=`<div class="bg-amber-50 rounded-lg p-3 text-xs">Preview: ${esc(preview.title)}. ${preview.affected_count} upcoming occurrence(s) affected.<button class="${button} ml-2" data-c-confirm>Confirm change</button></div>`;
      previewBox.querySelector('[data-c-confirm]').onclick=event=>submitButton(event.currentTarget,box,async()=>refresh(await api(ctx,'/adjustments/confirm',{token:preview.token})));
    }
    if(snapshot.preview) showPreview(snapshot.preview);
    box.querySelector('[data-c-suggest]').onclick=event=>submitButton(event.currentTarget,box,async()=>{
      const data=await api(ctx,'/suggestions',null,'GET');
      const proposals=box.querySelector('[data-c-proposals]');
      if(!data.targets.length) { proposals.textContent=data.message; return; }
      proposals.innerHTML=`<label class="block text-xs">Upcoming activity<select data-c-target class="block border rounded p-2 w-full">${data.targets.map(t=>`<option value="${esc(t.activity_id)}">Day ${t.day}: ${esc(t.title)}</option>`).join('')}</select></label>
        <label class="block text-xs mt-2">Improvement<select data-c-replacement class="block border rounded p-2 w-full"><option value="">Choose an alternative</option>${data.alternatives.map(a=>`<option value="${esc(a.id)}">${esc(a.name)}</option>`).join('')}</select></label><p class="text-xs text-slate-500">Recommendations are checked again for the selected activity before a change is applied.</p>
        <button class="${button} mt-2" data-c-swap>Preview swap</button>${snapshot.pending_decision.action==='change'?'<button class="border rounded px-3 py-2 ml-2 text-xs" data-c-remove>Preview removal</button>':''}<p class="text-xs text-rose-700" data-c-choice-error></p>`;
      proposals.querySelector('[data-c-target]').onchange=async event=>{
        const selection=proposals.querySelector('[data-c-replacement]');
        const target=event.currentTarget.value;
        selection.disabled=true;
        try {
          const updated=await api(ctx,`/suggestions?activity_id=${encodeURIComponent(target)}`,null,'GET');
          if(proposals.querySelector('[data-c-target]').value===target) selection.innerHTML='<option value="">Choose an alternative</option>'+updated.alternatives.map(a=>`<option value="${esc(a.id)}">${esc(a.name)}</option>`).join('');
        } catch(error) { proposals.querySelector('[data-c-choice-error]').textContent=error.message; }
        finally { selection.disabled=false; }
      };
      function preview(operation) {
        return async event=>submitButton(event.currentTarget,box,async()=>{
          const replacement=proposals.querySelector('[data-c-replacement]').value;
          if(operation==='swap' && !replacement) { proposals.querySelector('[data-c-choice-error]').textContent='Choose an alternative before previewing.'; return; }
          const next=await api(ctx,'/adjustments/preview',{target_activity_id:proposals.querySelector('[data-c-target]').value,operation,...(operation==='swap'?{replacement_activity_id:replacement}:{})});
          showPreview(next.preview);
        });
      }
      proposals.querySelector('[data-c-swap]').onclick=preview('swap');
      proposals.querySelector('[data-c-remove]')?.addEventListener('click',preview('remove'));
    });
    if(!snapshot.preview) box.querySelector('[data-c-suggest]').click();
  }

  async function renderAlerts(box,ctx,snapshot) {
    try {
      const response=await fetch(`/api/live/${encodeURIComponent(ctx.tripId)}/today?user_id=${encodeURIComponent(ctx.userId)}&day=${snapshot.runtime.current_day}`);
      if(!response.ok) throw new Error('Alerts could not be loaded. Refresh to retry.');
      const data=await response.json();
      if(!box.isConnected) return;
      const alerts=(data.activities||[]).flatMap(a=>a.alerts||[]);
      box.innerHTML=`<details class="border rounded-xl p-3"><summary class="font-semibold text-xs">Budget, weather and disruptions</summary>
        ${(data.budget_alerts||[]).map(a=>`<p class="text-xs text-amber-800 mt-2">${esc(a.message)}</p>`).join('')}
        ${data.weather?`<p class="text-xs mt-2">${esc(data.weather.label)} · ${esc(data.weather.message)}</p>`:''}
        ${alerts.map(a=>`<p class="text-xs mt-2">${esc(a.title)} — ${esc(a.message)}</p>`).join('')}
        <p class="text-xs mt-2 text-slate-500">Disruption simulations use the existing live-trip service.</p>
        <select data-c-condition class="border rounded p-2 text-xs"><option value="heavy_rain">Heavy rain</option><option value="closure">Closure</option><option value="fatigue">Fatigue</option><option value="traffic_delay">Traffic delay</option></select>
        <button class="border rounded px-3 py-2 text-xs" data-c-simulate>Simulate disruption</button><div data-c-error></div></details>`;
      box.querySelector('[data-c-simulate]').onclick=event=>submitButton(event.currentTarget,box,async()=>{
        await TravelModules.api(`/api/live/${encodeURIComponent(ctx.tripId)}/simulate`,{method:'POST',body:{user_id:ctx.userId,day_number:snapshot.runtime.current_day,condition_type:box.querySelector('[data-c-condition]').value}});
        await renderAlerts(box,ctx,snapshot);
      });
    } catch(error) { if(box.isConnected) box.innerHTML=errorBox(error); }
  }

  function install() {
    if(TravelModules.live) TravelModules.live.render=(container,ctx)=>ctx.workspaceMode==='post'?window.CPostTrip.render(container,ctx):render(container,ctx);
    const title=document.getElementById('itinDestinationTitle');
    if(title) new MutationObserver(()=>loadLifecycle()).observe(title,{childList:true});
    const editor=document.getElementById('workspaceEditorContainer');
    if(editor) new MutationObserver(()=>{if(state.snapshot) applyLocks(state.snapshot);}).observe(editor,{childList:true,subtree:true});
    document.getElementById('userTripsSelect')?.addEventListener('change',()=>loadLifecycle());
    loadLifecycle();
  }

  window.CTripRuntime={install,render,api,esc,label,ratingFields,readRatings,submitButton,lifecycle,isCurrent};
  window.addEventListener('load',install);
})();
