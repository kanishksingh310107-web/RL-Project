/* E: explain a day, check feasibility and compare server-generated alternatives. */
(() => {
  'use strict';
  const A=window.ExperienceAPI,U=window.ExperienceUI;
  if(!A||!U||typeof document==='undefined')return;
  const selected=new Map();
  const runtime=trip=>window.TripExperience.getSnapshot(trip);
  const editable=(trip,remaining=false)=>runtime(trip)?.status==='draft'||(runtime(trip)?.status==='live'&&remaining&& !runtime(trip)?.pending_review);
  window.addEventListener('trip:timeline-rendered',event=>{
    const {tripId,dayNumber,data,container}=event.detail;if(tripId!==A.tripId())return;selected.set(tripId,dayNumber);
    const day=data.days?.find(d=>d.day_number===dayNumber);if(!day)return;
    const box=U.el('section',null,'ex-itinerary-insights');box.setAttribute('aria-label','Day insights');
    if(day.theme||day.day_theme)box.append(U.el('h3',A.text(day.theme||day.day_theme)));
    const why=day.order_explanation||day.why_this_order;if(why)box.append(U.el('p','Why this order: '+A.text(why)));
    const measures=[];
    if(A.amount(day.active_hours)!==null)measures.push(day.active_hours+' active hours');
    if(A.amount(day.walking_km)!==null)measures.push('approximately '+day.walking_km+' km walking');
    if(A.amount(day.travel_minutes)!==null)measures.push('approximately '+day.travel_minutes+' minutes travelling');
    if(A.amount(day.total_cost)!==null)measures.push('day estimate '+A.money(day.total_cost));
    if(measures.length)box.append(U.el('p',measures.join(' · '),'ex-note'));
    box.append(U.el('p','Opening hours, walking and travel estimates may be incomplete. Check current details before booking or travelling.','ex-muted'));
    const actions=U.el('div',null,'ex-actions'),status=U.status(box);
    const check=U.button('Check my itinerary',()=>U.busy(check,status,()=>checkItinerary(tripId)));
    const improve=U.button('Recommend a better day',()=>dayOptions(tripId,dayNumber));
    const prefs=U.button('Day priorities & walking limits',()=>preferences(tripId,data));prefs.disabled=runtime(tripId)?.status!=='draft';
    actions.append(check,improve,prefs);box.append(actions);container.prepend(box);
    for(const row of container.querySelectorAll('[data-occurrence]')) {
      const block=day.timeline.find(b=>window.TripExperience.occurrenceId(b)===row.dataset.occurrence);if(!block)continue;
      const extra=U.el('div',null,'ex-stop-details');
      const priority=block.priority|| (block.must_visit?'must_do':null);
      if(priority)extra.append(U.el('strong',({must_do:'Must do',nice_to_do:'Nice to do',avoid:'Avoid'})[priority]||'Priority set'));
      if(block.is_fixed_booking)extra.append(U.el('p','Fixed booking · protected when plans change.'));
      if(block.opening_hours_label)extra.append(U.el('p',`Opening hours${block.hours_verified?' (verified)':' (unverified)'}: ${block.opening_hours_label}`));
      if(block.last_entry_time)extra.append(U.el('p','Last entry: '+block.last_entry_time));
      if(block.booking_required===true)extra.append(U.el('p','Advance booking required — confirm availability with the venue.'));
      if(block.source_as_of)extra.append(U.el('small','Information dated '+block.source_as_of));
      U.safeLinks(extra,block.sources);if(extra.childNodes.length)row.querySelector('article')?.append(extra);
    }
    A.capabilities().then(()=>{if(!box.isConnected)return;check.disabled=!A.can('itinerary_check');improve.disabled=!A.can('day_options');prefs.disabled=!A.can('day_options')||runtime(tripId)?.status!=='draft';if(check.disabled||improve.disabled)status.textContent='New checks and day alternatives are currently unavailable. Existing itinerary editing remains available.';});
  });
  async function checkItinerary(trip=A.tripId()) {
    const key=A.contextKey(trip),d=U.dialog('Check my itinerary','This checks the available information. It is not a guarantee of opening hours, availability or travel conditions.');
    const run=async()=>{
      d.notice.textContent='Checking timing, travel, priorities and budget…';
      try {
        const result=await A.check(trip);if(key!==A.contextKey()||!d.box.isConnected)return;
        if(!Array.isArray(result.findings))throw new Error('The itinerary check could not be read.');d.content.replaceChildren();d.notice.textContent='';
        const buckets=[['Needs attention',['error','conflict']],['Warnings',['warning']],['Information unavailable',['unavailable','unknown','info']]];
        for(const [title,severities] of buckets) {
          const findings=result.findings.filter(f=>severities.includes(f.severity)||title==='Information unavailable'&&!['error','conflict','warning','unavailable','unknown','info'].includes(f.severity));
          if(!findings.length)continue;const section=U.el('section');section.append(U.el('h3',title));
          for(const finding of findings){const card=U.el('article',null,'ex-finding');card.append(U.el('h4',A.text(finding.title||finding.code?.replace(/_/g,' ')||title)),U.el('p',A.text(finding.message||finding.explanation)));
            if(finding.day_number)card.append(U.el('small','Day '+finding.day_number));
            if(finding.occurrence_ids?.length)card.append(U.el('small','Affected activities: '+finding.occurrence_ids.join(', ')));
            for(const resolution of finding.resolutions||[]) {
              const resolve=U.button(resolution.label||resolution.title||'Review fix',()=>U.busy(resolve,d.notice,async()=>{
                const next=await A.checkPreview(trip,finding.id,resolution.id);U.confirmation('Review itinerary fix',next.preview||next,{current:()=>key===A.contextKey()&&editable(trip,resolution.remaining_only===true),confirm:token=>A.checkConfirm(trip,token),done:async()=>{d.box.close();await window.BudgetExperience?.refreshTrip(trip);}});
              }));resolve.disabled=!editable(trip,resolution.remaining_only===true);card.append(resolve);
            }section.append(card);
          }d.content.append(section);
        }
        if(!result.findings.length)d.content.append(U.el('p',result.complete===true?'No conflicts were reported in the information checked. Confirm live details before travelling.':'No findings were returned. Some information may still be unavailable.'));
        U.lines(d.content,'Sources or checks unavailable',result.unavailable_checks);U.safeLinks(d.content,result.sources);
      }catch(error){if(d.box.isConnected){d.notice.textContent=error.message;d.content.append(U.button('Retry check',()=>{d.content.replaceChildren();run();}));}}
    };await A.capabilities();if(!A.can('itinerary_check')){U.unavailable(d.content,'Itinerary checks are currently unavailable.',async()=>{await A.capabilities(true);if(A.can('itinerary_check'))run();});return;}await run();
  }
  async function dayOptions(trip,day) {
    const key=A.contextKey(trip),d=U.dialog('Recommend a better day','Compare alternatives for day '+day+'. Completed activities, bookings and your priorities must remain protected.');const f=U.form('day-options');d.content.append(f);
    U.field(f,'goal','What would improve this day?',{options:[['less_walking','Less walking'],['local_experiences','More local experiences'],['lower_cost','Lower cost'],['more_downtime','More downtime']]});
    const submit=U.el('button','Find two alternatives','ex-primary');submit.type='submit';submit.disabled=true;f.append(submit);const results=U.el('div',null,'ex-result-grid');d.content.append(results);
    await A.capabilities();submit.disabled=!A.can('day_options');if(submit.disabled)U.unavailable(d.content,'Alternative day plans are currently unavailable.',async()=>{await A.capabilities(true);submit.disabled=!A.can('day_options');});
    f.onsubmit=event=>{event.preventDefault();U.busy(submit,d.notice,async()=>{
      if(key!==A.contextKey())throw new Error('The selected trip changed. Reopen this day.');
      const result=await A.dayOptions(trip,day,f.elements.goal.value);if(key!==A.contextKey()||!d.box.isConnected)return;
      if(!Array.isArray(result.options))throw new Error('The day alternatives could not be read.');results.replaceChildren();
      if(result.message)results.append(U.el('p',A.text(result.message)));
      for(const option of result.options.slice(0,2)){
        const card=U.el('article',null,'ex-option');card.append(U.el('h3',A.text(option.title||option.label)));
        U.lines(card,'Activities added',option.added);U.lines(card,'Activities removed',option.removed);U.lines(card,'Benefits',option.benefits);U.lines(card,'Trade-offs',option.tradeoffs);
        if(option.timing_summary)card.append(U.el('p','Timing: '+A.text(option.timing_summary)));if(option.walking_summary)card.append(U.el('p','Walking: '+A.text(option.walking_summary)));
        card.append(U.el('p','Estimated day cost: '+A.money(option.total_cost_inr)));
        if(A.amount(option.cost_delta_inr)!==null)card.append(U.el('p','Cost change: '+A.money(option.cost_delta_inr)));
        const preview=U.button('Preview this day',()=>U.busy(preview,d.notice,async()=>{
          const next=await A.dayPreview(trip,option.id);U.confirmation('Review day '+day,next.preview||next,{current:()=>key===A.contextKey()&&editable(trip,option.remaining_only===true),confirm:token=>A.dayConfirm(trip,token),done:async()=>{d.box.close();await window.BudgetExperience?.refreshTrip(trip);}});
        }));preview.disabled=option.can_apply===false||!editable(trip,option.remaining_only===true);card.append(preview);results.append(card);
      }
      if(!result.options.length)results.append(U.el('p','No feasible alternatives were returned. Your current day is unchanged.'));
    });};
  }
  function preferences(trip,data) {
    if(runtime(trip)?.status!=='draft')return;
    const key=A.contextKey(trip),d=U.dialog('Day priorities & comfort','Choose priorities independently of activity acceptance. Fixed bookings stay protected.');const f=U.form('day-preferences');d.content.append(f);
    const tripData=data.trip||{};U.field(f,'intensity','Daily intensity',{options:[['relaxed','Relaxed'],['balanced','Balanced'],['active','Active']],value:tripData.travel_pace||'balanced'});
    U.field(f,'walking_limit_km','Maximum comfortable walking per day (km, optional)',{type:'number',min:0,max:100,value:tripData.walking_limit_km??''});
    U.field(f,'accessibility_notes','Accessibility or fatigue needs (optional)',{type:'textarea',value:tripData.accessibility_notes||'',maxlength:500});
    const blocks=(data.days||[]).flatMap(day=>(day.timeline||[]).filter(b=>b.type==='activity').map(b=>({...b,day_number:day.day_number})));
    for(const block of blocks){const field=U.field(f,'priority_'+window.TripExperience.occurrenceId(block),`Day ${block.day_number}: ${block.title}`,{options:[['nice_to_do','Nice to do'],['must_do','Must do'],['avoid','Avoid']],value:block.priority||(block.must_visit?'must_do':'nice_to_do')});field.disabled=!!block.is_fixed_booking;if(field.disabled)field.closest('label').append(U.el('small','Fixed booking — protected.'));}
    const save=U.el('button','Save preferences','ex-primary');save.type='submit';f.append(save);
    f.onsubmit=event=>{event.preventDefault();const v=U.values(f),e={};if(v.walking_limit_km!==''&&(!Number.isFinite(Number(v.walking_limit_km))||Number(v.walking_limit_km)<0||Number(v.walking_limit_km)>100))e.walking_limit_km='Use 0–100 km, or leave blank.';if(v.accessibility_notes.trim().length>500)e.accessibility_notes='Use 500 characters or fewer.';if(!U.errors(f,e))return;
      U.busy(save,d.notice,async()=>{if(key!==A.contextKey()||runtime(trip)?.status!=='draft')throw new Error('The trip is no longer editable.');await A.itineraryPreferences(trip,{intensity:v.intensity,walking_limit_km:v.walking_limit_km===''?null:Number(v.walking_limit_km),accessibility_notes:v.accessibility_notes.trim(),priorities:blocks.filter(b=>!b.is_fixed_booking).map(b=>({occurrence_id:window.TripExperience.occurrenceId(b),priority:v['priority_'+window.TripExperience.occurrenceId(b)]}))});d.box.close();await window.BudgetExperience?.refreshTrip(trip);});};
  }
  window.ItineraryInsights={check:checkItinerary,dayOptions,selectedDay:trip=>selected.get(trip)||1};
})();
