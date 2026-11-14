// C: required, resumable trip feedback. History is owned and built by Person A.
(function () {
  const button='px-3 py-2 rounded-lg bg-indigo-600 text-white text-xs font-semibold disabled:opacity-50';
  let epoch=0;
  async function render(container,ctx) {
    const request=++epoch;
    const C=window.CTripRuntime;
    container.innerHTML='<p class="text-xs text-slate-500">Loading saved feedback…</p>';
    if(!ctx.tripId || !ctx.userId) { container.textContent='Select a trip first.'; return; }
    try {
      const snapshot=await C.api(ctx,'/runtime',null,'GET');
      if(request!==epoch || !C.isCurrent(ctx)) return;
      C.lifecycle(ctx,snapshot);
      if(snapshot.status!=='completed') { container.innerHTML='<p class="text-xs">End the trip in LIVE TRIP before submitting post-trip feedback.</p>'; return; }
      const runs=snapshot.runs||[];
      const planned=(snapshot.schedule||[]).length;
      const actual=runs.filter(run=>run.outcome==='completed').length;
      const early=runs.filter(run=>run.outcome==='early_ended').length;
      const tripSummary=`<div class="te-card"><h3>Trip summary</h3><p>${snapshot.total_days} of ${snapshot.total_days} days finished · ${planned} activities planned · ${actual} completed · ${early} ended early · ${runs.filter(run=>['skipped','not_done'].includes(run.outcome)).length} skipped / not done.</p></div>`;
      if(snapshot.closed_out) {
        container.innerHTML=`${tripSummary}<h3 class="text-sm font-bold text-emerald-800">Trip closed out — feedback saved</h3><p class="text-xs mt-2">${C.esc(snapshot.post_feedback.notes)}</p><div data-c-learning></div>`;
        try {
          const summary=await TravelModules.api(`/api/live/${encodeURIComponent(ctx.userId)}/learning-summary?caller_user_id=${encodeURIComponent(ctx.userId)}`);
          const box=container.querySelector('[data-c-learning]');
          if(request===epoch && C.isCurrent(ctx) && box) box.innerHTML=`<p class="text-xs mt-3">${C.esc(window.TripExperience?.publicText(summary.explanation)||'Your feedback will help personalise future recommendations.')}</p>`;
        } catch (_) {
          const box=container.querySelector('[data-c-learning]');
          if(request===epoch && C.isCurrent(ctx) && box) box.textContent='Feedback is saved. Your recommendation summary is temporarily unavailable.';
        }
        return;
      }
      const draft=snapshot.post_feedback || {};
      const trip=await window.TripExperience.api(`/api/trips/detail/${encodeURIComponent(ctx.tripId)}?user_id=${encodeURIComponent(ctx.userId)}`);
      if(request!==epoch || !C.isCurrent(ctx)) return;
      const savedType=draft.trip_type||trip.trip_type||({partner:'couple',family_kids:'family',family_seniors:'family'}[trip.companions]||trip.companions);
      const tripType=['solo','couple','friends','family'].includes(savedType)?savedType:'';
      const placeDraft=Object.fromEntries((draft.per_place_ratings||[]).map(p=>[p.activity_id,p.ratings?.overall||'']));
      container.innerHTML=`${tripSummary}<form class="space-y-4" novalidate><h3 class="font-bold text-sm">Post-trip feedback</h3><p class="text-xs">Submission is required to close out this trip. Save a draft at any time to resume later.</p>
        <div class="grid grid-cols-2 gap-3">${C.ratingFields(snapshot.rating_keys,draft.ratings)}</div>
        <details><summary class="text-xs">Trip type: ${C.esc(tripType?C.label(tripType):'Not available — please confirm')} · correct if needed</summary><label class="block text-xs">Correct trip type (optional when already saved)<select name="trip_type" class="block border rounded-lg p-2 w-full"><option value="">Choose a type</option>${['solo','couple','friends','family'].map(v=>`<option value="${v}" ${tripType===v?'selected':''}>${C.label(v)}</option>`).join('')}</select><span data-field-error="trip_type" class="text-rose-700"></span></label></details>
        <label class="block text-xs">Would you revisit?<select name="would_revisit" class="block border rounded-lg p-2 w-full" required><option value="">Choose an answer</option>${['yes','no','maybe'].map(v=>`<option value="${v}" ${draft.would_revisit===v?'selected':''}>${C.label(v)}</option>`).join('')}</select><span data-field-error="would_revisit" class="text-rose-700"></span></label>
        ${['liked','disliked','notes'].map(key=>`<label class="block text-xs">${C.label(key)}${key==='notes'?' (optional)':''}<textarea name="${key}" maxlength="2000" class="block border rounded-lg p-2 w-full">${C.esc(draft[key]||'')}</textarea><span data-field-error="${key}" class="text-rose-700"></span></label>`).join('')}
        <details class="border rounded-lg p-3"><summary class="text-xs font-semibold">Optional per-place overall ratings</summary>${snapshot.schedule.map(slot=>`<label class="block text-xs mt-2">Day ${slot.day_number}: ${C.esc(slot.title)}<select class="border rounded p-1 ml-2" data-c-place="${C.esc(slot.id)}"><option value="">Not rated</option>${[1,2,3,4,5].map(n=>`<option value="${n}" ${Number(placeDraft[slot.id])===n?'selected':''}>${n}</option>`).join('')}</select></label>`).join('')}</details>
        <div class="flex gap-2"><button type="button" class="border rounded-lg px-3 py-2 text-xs" data-c-save-draft>Save draft</button><button type="submit" class="${button}">Submit and close out trip</button></div><div data-c-error></div><p data-c-saved role="status" class="text-xs text-emerald-700"></p></form>`;
      const form=container.querySelector('form');
      function collect(isDraft) {
        const ratings=C.readRatings(form,!isDraft);
        let valid=ratings!==null;
        const body={draft:isDraft,ratings:ratings||{},per_place_ratings:[]};
        for(const key of ['trip_type','would_revisit','liked','disliked','notes']) {
          const value=form.elements[key].value.trim();
          const invalidEnum=(key==='trip_type' && value && !['solo','couple','friends','family'].includes(value)) ||
            (key==='would_revisit' && value && !['yes','no','maybe'].includes(value));
          const bad=(!isDraft && key!=='notes' && !value) || value.length>2000 || invalidEnum;
          form.querySelector(`[data-field-error="${key}"]`).textContent=bad?(invalidEnum?'Choose a valid option.':value.length>2000?'Use at most 2,000 characters.':'This field is required.'):'';
          if(bad) valid=false;
          if(value) body[key]=value;
        }
        form.querySelectorAll('[data-c-place]').forEach(field=>{
          if(field.value) {
            const value=Number(field.value);
            if(!Number.isInteger(value)||value<1||value>5) valid=false;
            else body.per_place_ratings.push({activity_id:field.dataset.cPlace,ratings:{overall:value}});
          }
        });
        return valid?body:null;
      }
      async function save(isDraft,control) {
        const body=collect(isDraft); if(!body) return;
        if(form.dataset.inFlight==='true') return;
        form.dataset.inFlight='true';
        await C.submitButton(control,form,async()=>{
          form.querySelectorAll('button').forEach(b=>{if(b!==control) b.disabled=true;});
          try {
            const next=await C.api(ctx,'/post-feedback',body);
            if(!C.isCurrent(ctx)) return;
            C.lifecycle(ctx,next);
            if(isDraft) form.querySelector('[data-c-saved]').textContent='Draft saved. You can leave and resume this form.';
            else { window.dispatchEvent(new CustomEvent('trip:feedback-saved',{detail:{tripId:ctx.tripId}})); await render(container,ctx); }
          } finally { form.querySelectorAll('button').forEach(b=>{if(b!==control) b.disabled=false;}); }
        });
        form.dataset.inFlight='false';
      }
      form.querySelector('[data-c-save-draft]').onclick=event=>save(true,event.currentTarget);
      form.onsubmit=event=>{event.preventDefault();save(false,form.querySelector('[type="submit"]'));};
    } catch(error) {
      if(request===epoch && C.isCurrent(ctx)) container.innerHTML=`<p role="alert" class="text-xs text-rose-700">${C.esc(error.message)}</p><button class="border rounded p-2 text-xs" data-c-post-retry>Retry</button>`;
      container.querySelector('[data-c-post-retry]')?.addEventListener('click',()=>render(container,ctx));
    }
  }
  window.CPostTrip={render};
})();
