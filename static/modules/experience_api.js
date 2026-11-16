/* E: one adapter for discovery, money and assistant contracts. No client ledger. */
(() => {
  'use strict';
  const categories=['accommodation','food','intercity_transport','local_transport','activities','shopping','emergency_reserve','other'];
  const flags=['discovery','budget_options','expense_tracking','itinerary_check','day_options','assistant_chat','assistant_actions'];
  const serverCategory=c=>c==='intercity_transport'?'intercity_travel':c;
  const clientCategory=c=>c==='intercity_travel'?'intercity_transport':c;
  const previews=new Map(),assistantPreviews=new Map(),conversations=new Map();
  function discoveryBody(v={}) {
    const party=v.party||v;const exact=Boolean(v.start_date&&v.end_date)&&(v.date_mode==='dates'||!v.date_mode);
    const rawAccessibility=v.accessibility;
    const accessibility=Array.isArray(rawAccessibility)?rawAccessibility.filter(x=>typeof x==='string'&&x.trim()).map(x=>x.trim()):typeof rawAccessibility==='string'&&rawAccessibility.trim()?[rawAccessibility.trim()]:[];
    const count=Number(v.party_size)||Number(party.adults||0)+Number(party.children||0)+Number(party.seniors||0)||1;
    return {origin:typeof v.origin==='string'&&v.origin.trim()?v.origin.trim():null,...(exact?{start_date:v.start_date,end_date:v.end_date}:{duration_days:Number(v.duration_days||3)}),comfortable_budget_inr:v.total_budget==null||v.total_budget===''?null:Number(v.total_budget),party_size:count,trip_type:v.trip_type||'solo',mood:v.mood==='mixed'?null:v.mood,transport:v.transport==='any'?null:v.transport==='road'?'driving':v.transport||null,...(v.max_travel_hours!=null&&v.max_travel_hours!==''?{max_travel_minutes:Math.round(Number(v.max_travel_hours)*60)}:{}),walking_limit_km:v.walking_limit_km==null||v.walking_limit_km===''?null:Number(v.walking_limit_km),accessibility};
  }
  function destination(d) {
    return {...d,travel_time_label:d.travel_time_label||(d.estimated_travel_minutes!=null?'About '+Math.floor(d.estimated_travel_minutes/60)+'h '+(d.estimated_travel_minutes%60)+'m · indicative; route unverified':undefined),estimated_total_inr:d.estimated_total_inr??d.estimated_total_cost_inr,tradeoff:d.tradeoff||d.trade_off,estimate_note:d.estimate_note||(d.estimate_limitations||[]).join(' '),is_shortlisted:d.is_shortlisted??d.saved,comparison_basis:typeof d.comparison_basis==='string'?d.comparison_basis:`${d.duration_days||3} days · same party and cost scope`,sample_itinerary:Array.isArray(d.sample_itinerary)&&d.sample_itinerary[0]?.name?[{day_number:1,activities:d.sample_itinerary.map(a=>a.name)}]:d.sample_itinerary};
  }
  function expense(d) {return {...d,category:({stay:'accommodation',transport:'local_transport'})[d.category]||d.category,description:d.note,planned_item_id:clientCategory(d.planned_cost_key),payment_state:d.is_final_for_planned_cost?'final':'partial'};}
  function expenseBody(v) {return {amount_inr:v.amount_inr,category:({accommodation:'stay',intercity_transport:'transport',local_transport:'transport'})[v.category]||v.category,spent_on:v.spent_on,note:v.description||'',paid_by:v.paid_by||null,planned_cost_key:v.planned_item_id?serverCategory(v.planned_item_id):null,is_final_for_planned_cost:!!v.planned_item_id&&v.payment_state==='final'};}
  const optionKey=(trip,kind,id)=>`${contextKey(trip)}:${kind}:${id}`;
  async function previewOption(trip,kind,id) {const proposal=previews.get(optionKey(trip,kind,id));if(!proposal)throw new Error('Request fresh options before previewing this change.');return request(tripPath(trip,'').replace('/api/trips/','/api/trip-actions/')+'/preview',{method:'POST',body:proposal});}
  const confirmPreview=(trip,token)=>request(`/api/trip-actions/${id(trip)}/confirm`,{method:'POST',body:{token}});
  const user=()=>typeof state!=='undefined'?state.currentUser:null;
  const uid=()=>user()?.user_id || null;
  const tripId=()=>typeof getWorkspaceContext==='function'?getWorkspaceContext().tripId:null;
  function workspaceTrip(){if(typeof location==='undefined')return tripId();const match=location.hash.match(/^#\/trips\/([^/]+)$/);if(!match||match[1]==='new')return null;try{const value=decodeURIComponent(match[1]);return value===tripId()?value:null;}catch(_){return null;}}
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const text=value=>/linucb|bandit|sherman|state.vector|feature.dimension|reinforcement.learning|policy.weights/i.test(String(value||''))?'Personalised using your travel preferences and feedback.':String(value??'');
  const id=value=>{if(typeof value!=='string'||!value.trim()||value.length>200)throw new Error('The selected record is unavailable. Refresh and try again.');return encodeURIComponent(value);};
  const amount=value=>!['string','number'].includes(typeof value)||(typeof value==='string'&&!value.trim())?null:Number.isFinite(Number(value))?Number(value):null;
  const money=value=>amount(value)===null?'Not available':typeof formatINR==='function'?formatINR(Number(value)):new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR',maximumFractionDigits:0}).format(Number(value));
  function integer(value,min=0,max=1000000000) {
    return ['number','string'].includes(typeof value)&&!(typeof value==='string'&&!value.trim())&&Number.isInteger(Number(value))&&Number(value)>=min&&Number(value)<=max;
  }
  function isoDate(value) {
    return typeof value==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(value)&&!Number.isNaN(Date.parse(value+'T00:00:00Z'))&&new Date(value+'T00:00:00Z').toISOString().slice(0,10)===value;
  }
  function discoveryErrors(values,today) {
    const e={};
    if(typeof values.origin!=='string'||values.origin.trim().length<2||values.origin.length>200||!/[\p{L}]/u.test(values.origin))e.origin='Enter your departure town or city (2–200 characters).';
    if(values.date_mode==='dates') {
      if(!isoDate(values.start_date)||values.start_date<today)e.start_date='Choose today or a future departure date.';
      if(!isoDate(values.end_date)||values.end_date<values.start_date)e.end_date='Return must be on or after departure.';
      if(isoDate(values.start_date)&&isoDate(values.end_date)&&(Date.parse(values.end_date)-Date.parse(values.start_date))/86400000>=90)e.end_date='Keep the trip to 90 days or fewer.';
    } else if(values.date_mode==='flexible') {
      if(!integer(values.duration_days,1,90))e.duration_days='Choose 1–90 days. Exact dates can be decided later.';
    } else e.date_mode='Choose exact dates or a flexible duration.';
    if(!integer(values.total_budget,1000,1000000))e.total_budget='Enter a whole-rupee total budget from ₹1,000 to ₹10,00,000.';
    if(!['solo','couple','friends','family'].includes(values.trip_type))e.trip_type='Choose a valid trip type.';
    let size=0;
    for(const key of ['adults','children','seniors']){if(!integer(values[key],key==='adults'?1:0,30))e[key]='Enter a whole number from '+(key==='adults'?1:0)+' to 30.';size+=Number(values[key]);}
    if(size>30)e.adults='A party can contain at most 30 travellers.';
    if(values.trip_type==='solo'&&(size!==1||Number(values.adults)!==1))e.trip_type='Solo requires exactly one adult.';
    if(!['relaxing','adventure','nature','food','culture','mixed'].includes(values.mood))e.mood='Choose a mood or a mix.';
    for(const key of ['max_travel_hours','walking_limit_km'])if(values[key]!==''&&(!Number.isFinite(Number(values[key]))||Number(values[key])<0||Number(values[key])>100))e[key]='Enter a value between 0 and 100, or leave blank.';
    if(values.max_travel_hours!==''&&values.max_travel_hours!=null&&(!Number.isFinite(Number(values.max_travel_hours))||Number(values.max_travel_hours)<=0||Number(values.max_travel_hours)>24))e.max_travel_hours='Enter more than 0 and up to 24 hours, or leave blank.';
    if(String(values.accessibility||'').length>500)e.accessibility='Use 500 characters or fewer.';
    return e;
  }
  function expenseErrors(v) {
    const e={};if(!integer(v.amount_inr,1))e.amount_inr='Enter a positive whole-rupee amount.';
    if(!categories.includes(v.category))e.category='Choose an expense category.';
    if(!isoDate(v.spent_on))e.spent_on='Choose a valid expense date.';
    if(String(v.description||'').trim().length>500)e.description='Use 500 characters or fewer.';
    if(String(v.paid_by||'').trim().length>80)e.paid_by='Use 80 characters or fewer.';
    return e;
  }
  function normalizeSummary(data) {
    if(!data||typeof data!=='object'||Array.isArray(data))throw new Error('The budget summary could not be read. Please retry.');
    const s=data.summary||data.budget||data;
    return {...s,total_budget:amount(s.total_budget_inr??s.total_budget),planned_cost:amount(s.planned_total_inr??s.planned_cost),actual_spending:amount(s.actual_spending_inr??s.actual_total_inr??s.actual_spending),estimated_remaining_costs:amount(s.estimated_remaining_costs_inr??s.estimated_remaining_inr??s.estimated_remaining_costs),remaining_to_pay:amount(s.remaining_to_pay_inr??s.remaining_to_pay),forecast_final_cost:amount(s.forecast_final_cost_inr??s.forecast_total_inr??s.forecast_final_cost),forecast_with_reserve:amount(s.forecast_with_reserve_inr??s.forecast_with_reserve),emergency_reserve:amount(s.emergency_reserve_inr??s.emergency_reserve),shopping_remaining:amount(s.shopping_remaining_inr??s.shopping_remaining),available_buffer:amount(s.available_buffer_inr??s.buffer_inr??s.available_buffer),over_budget:amount(s.over_budget_inr??s.over_budget),allocations:Array.isArray(s.allocations)?s.allocations.map(a=>({...a,category:clientCategory(a.category)})):[],planned_items:(s.planned_items||[]).map(p=>({...p,id:clientCategory(p.id)}))};
  }
  function contextKey(trip=workspaceTrip()) {return `${uid()||''}:${trip||''}`;}
  let caps={},capsUser=null,capsPromise=null;
  async function request(path,options={}) {
    if(!uid())throw new Error('Sign in to continue.');
    const owner=uid(), controller=new AbortController(),timer=setTimeout(()=>controller.abort(),20000);
    try {
      const headers={'Content-Type':'application/json',...options.headers};
      const response=await fetch(path,{...options,headers,signal:controller.signal,body:options.body===undefined?undefined:JSON.stringify(options.body)});
      if(owner!==uid())throw new Error('The signed-in account changed. Reopen this view.');
      let data={};
      if(response.status!==204){try{data=await response.json();}catch(_){throw new Error('The server response could not be read. Your entries are kept. Please retry.');}}
      if(data===null||typeof data!=='object')throw new Error('The server returned an unreadable response. Your entries are kept; please retry.');
      if(!response.ok){
        const issue=Array.isArray(data.detail)?data.detail[0]:null;
        const path=Array.isArray(issue?.loc)?issue.loc.filter(part=>!['body','query','path'].includes(part)):[];
        const field=data.field||(path.length?String(path[path.length-1]):null);
        const message=typeof data.detail==='string'?data.detail:issue?.msg?String(issue.msg).replace(/^Value error,\s*/,''):'This action could not be completed. Please retry.';
        const error=new Error(text(message));error.field=field;error.code=data.code;error.status=response.status;throw error;
      }
      return data;
    }catch(error){if(error.name==='AbortError')throw new Error('The request timed out. Your entries are kept; please retry.');if(error instanceof TypeError)throw new Error('Connection failed. Your entries are kept; please retry.');throw error;}finally{clearTimeout(timer);}
  }
  async function capabilities(force=false) {
    const owner=uid();if(!owner)return {};
    if(!force&&capsUser===owner)return caps;
    if(capsPromise?.owner===owner)return capsPromise.promise;
    const promise=(async()=>{
      try{const result=await request('/api/experience/capabilities');if(owner!==uid())return {};const source=result.capabilities||result;caps=Object.fromEntries(flags.map(key=>[key,source[key]===true]));caps.assistant_mode=source.assistant_mode||'unknown';caps.conversation_persistence=source.conversation_persistence||'unknown';capsUser=owner;}
      catch(_){if(owner===uid()){caps={};capsUser=null;}}
      return owner===uid()?caps:{};
    })();capsPromise={owner,promise};try{return await promise;}finally{if(capsPromise?.promise===promise)capsPromise=null;}
  }
  const can=key=>capsUser===uid()&&caps[key]===true;
  function requireFeature(key){if(!can(key))throw new Error('This feature is currently unavailable. Your entries are kept. You can retry availability or use the existing planner.');}
  const tripPath=(trip,suffix='')=>`/api/trips/${id(trip)}${suffix}`;
  const nonce=()=>window.crypto?.randomUUID?.()||`${Date.now()}-${Math.random().toString(36).slice(2)}`;
  const keyed=(key,body)=>({method:'POST',headers:{'Idempotency-Key':key},body:{...body,idempotency_key:key}});
  const API={
    capabilities,can,request,contextKey,nonce,uid,user,tripId,workspaceTrip,esc,text,amount,money,integer,isoDate,discoveryErrors,expenseErrors,normalizeSummary,categories,
    async discover(body){requireFeature('discovery');const r=await request('/api/discovery/suggestions',{method:'POST',body:discoveryBody(body)});return {...r,recommendations:r.recommendations.map(destination),assumptions:r.limitations};},
    async shelves(context={}){let path='/api/discovery/recommendations';if(context.total_budget!=null||context.duration_days!=null||context.start_date||context.end_date||context.party){const params=new URLSearchParams();for(const [key,value]of Object.entries(discoveryBody(context)))if(value!==null&&value!==undefined)params.set(key,String(value));path+='?'+params.toString();}const r=await request(path);return {...r,groups:Array.isArray(r.groups)?r.groups:Object.entries(r.groups||{}).map(([key,entries])=>({title:key.replace(/_/g,' '),destinations:entries.map(destination)}))};},
    async savedPlaces(){const r=await request('/api/discovery/saved');return {...r,destinations:(r.destinations||[]).map(destination)};},
    async feedback(body){requireFeature('discovery');return request('/api/discovery/feedback',{method:'POST',body:{destination_id:body.destination_id,action:body.action,reason:({too_expensive:'cost',too_far:'distance',too_crowded:'crowding',wrong_activity_type:'unsuitable_activities',not_interested:'other'})[body.reason]||body.reason||null}});},
    async compare(ids,context={}){requireFeature('discovery');if(ids.length<2||ids.length>3||new Set(ids).size!==ids.length)throw new Error('Select two or three different destinations.');const r=await request('/api/discovery/compare',{method:'POST',body:{destination_ids:ids,context:discoveryBody(context)}});return {...r,destinations:r.destinations.map(destination)};},
    legacyRecommendations:()=>request(`/api/recommendations/${id(uid())}`),
    saveLegacy:destination=>request(`/api/shortlist/${id(uid())}`,{method:'POST',body:{destination_id:destination}}),
    async budget(trip){requireFeature('expense_tracking');return normalizeSummary(await request(tripPath(trip,'/budget')));},
    async allocate(trip,body){requireFeature('expense_tracking');const allocations=Object.fromEntries(body.allocations.filter(a=>a.amount_inr!==null).map(a=>[serverCategory(a.category),{amount_inr:a.amount_inr,basis:a.basis,status:a.status,...(a.basis==='per_room_night'?{rooms:body.rooms}:{})}]));return request(tripPath(trip,'/budget'),{method:'PUT',body:{total_budget_inr:body.total_budget_inr,allocations,version:body.version,release_emergency_reserve:body.release_emergency_reserve}});},
    async expenses(trip){requireFeature('expense_tracking');const r=await request(tripPath(trip,'/expenses'));return {...r,expenses:r.expenses.map(expense)};},
    async saveExpense(trip,body,key,expenseId){requireFeature('expense_tracking');body=expenseBody(body);return request(tripPath(trip,'/expenses')+(expenseId?'/'+id(expenseId):''),expenseId?{method:'PATCH',body}:keyed(key,body));},
    async deleteExpense(trip,expenseId){requireFeature('expense_tracking');return request(tripPath(trip,'/expenses/')+id(expenseId),{method:'DELETE'});},
    async legacyExpenses(trip){return request(tripPath(trip,'/expenses'));},
    async legacyAddExpense(trip,body){return request(tripPath(trip,'/expenses'),{method:'POST',body});},
    async budgetOptions(trip,body){requireFeature('budget_options');const r=await request(tripPath(trip,'/budget-options'),{method:'POST',body:{max_additional_budget_inr:body.max_extra_inr,current_budget_inr:body.current_budget_inr,priorities:[body.priority]}});return {...r,options:r.options.map(o=>{if(o.preview_request)previews.set(optionKey(trip,'budget',o.id),o.preview_request);return {...o,title:o.label||o.title,unchanged:o.stays_the_same||o.unchanged,tradeoffs:o.trade_offs||o.tradeoffs,can_apply:!!o.preview_request,estimate_note:(o.estimate_limitations||[]).join(' ')};})};},
    async budgetPreview(trip,optionId){requireFeature('budget_options');return previewOption(trip,'budget',optionId);},
    async budgetConfirm(trip,token){requireFeature('budget_options');return confirmPreview(trip,token);},
    async check(trip){requireFeature('itinerary_check');const r=await request(tripPath(trip,'/itinerary-check'));for(const f of r.findings)for(const fix of f.resolutions||[])if(fix.preview_request)previews.set(optionKey(trip,'check',f.id+':'+fix.id),fix.preview_request);return {...r,findings:r.findings.map(f=>({...f,title:f.title||f.kind?.replace(/_/g,' '),severity:f.severity==='confirmed'?'conflict':f.severity,resolutions:(f.resolutions||[]).filter(x=>typeof x==='object')}))};},
    async checkPreview(trip,findingId,resolutionId){requireFeature('itinerary_check');return previewOption(trip,'check',findingId+':'+resolutionId);},
    async checkConfirm(trip,token){requireFeature('itinerary_check');return confirmPreview(trip,token);},
    async dayOptions(trip,day,goal){requireFeature('day_options');const r=await request(tripPath(trip,`/day-options?day_number=${Number(day)}&goal=${encodeURIComponent(goal)}`));return {...r,options:(r.day_options||r.options||[]).map(o=>{if(o.preview_request)previews.set(optionKey(trip,'day',o.id),o.preview_request);return {...o,title:o.label||o.title,benefits:[o.explanation],tradeoffs:[o.trade_off],cost_delta_inr:o.estimated_cost_change_inr??null,can_apply:!!o.preview_request};})};},
    async dayPreview(trip,optionId){requireFeature('day_options');return previewOption(trip,'day',optionId);},
    async dayConfirm(trip,token){requireFeature('day_options');return confirmPreview(trip,token);},
    async itineraryPreferences(trip,body){requireFeature('day_options');return request(tripPath(trip,'/day-options/preferences'),{method:'PATCH',body});},
    async chat(body,key){requireFeature('assistant_chat');const context=contextKey(body.trip_id),history=conversations.get(context)||[];const r=await request('/api/assistant/chat',{method:'POST',headers:{'Idempotency-Key':key},body:{message:body.message,trip_id:body.trip_id,conversation:history}});conversations.set(context,[...history,{role:'user',content:body.message},{role:'assistant',content:r.answer}].slice(-6));const p=r.preview?.preview;const proposals=[];if(p?.token&&r.proposal){assistantPreviews.set(`${context}:${p.token}`,p);proposals.push({id:p.token,trip_id:body.trip_id,action_type:({swap:'swap_activity',remove:'remove_activity',reschedule:'adjust_schedule',move_day:'move_activity',preferences:'adjust_schedule'})[r.proposal.operation],summary:p.summary,title:'Suggested itinerary change'});}return {reply:r.answer,message_id:key,conversation_id:r.conversation_id,proposals};},
    async assistantPreview(proposalId,trip){requireFeature('assistant_actions');const p=assistantPreviews.get(`${contextKey(trip)}:${proposalId}`);if(!p)throw new Error('Ask for a fresh proposal before previewing.');return {preview:p};},
    async assistantConfirm(proposalId,token,trip){requireFeature('assistant_actions');if(proposalId!==token||!assistantPreviews.has(`${contextKey(trip)}:${proposalId}`))throw new Error('Ask for a fresh proposal.');return confirmPreview(trip,token);},
    async clearConversation(conversationId){return request('/api/assistant/conversations/'+id(conversationId),{method:'DELETE'});},
    clearChat(trip){conversations.delete(contextKey(trip));},
    async exportExpenses(trip){requireFeature('expense_tracking');return tripPath(trip,'/expenses/export.csv');}
  };
  window.addEventListener?.('trip:context-cleared',()=>{previews.clear();assistantPreviews.clear();conversations.clear();});
  window.ExperienceAPI=API;
})();
