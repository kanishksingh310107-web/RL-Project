/* E: one adapter for discovery, money and assistant contracts. No client ledger. */
(() => {
  'use strict';
  const categories=['accommodation','food','intercity_transport','local_transport','activities','shopping','emergency_reserve','other'];
  const flags=['discovery','budget_options','expense_tracking','itinerary_check','day_options','assistant_chat','assistant_actions'];
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
    if(!integer(values.total_budget,1000))e.total_budget='Enter a whole-rupee total budget of at least ₹1,000.';
    if(!['solo','couple','friends','family'].includes(values.trip_type))e.trip_type='Choose a valid trip type.';
    let size=0;
    for(const key of ['adults','children','seniors']){if(!integer(values[key],key==='adults'?1:0,30))e[key]='Enter a whole number from '+(key==='adults'?1:0)+' to 30.';size+=Number(values[key]);}
    if(size>30)e.adults='A party can contain at most 30 travellers.';
    if(values.trip_type==='solo'&&(size!==1||Number(values.adults)!==1))e.trip_type='Solo requires exactly one adult.';
    if(!['relaxing','adventure','nature','food','culture','mixed'].includes(values.mood))e.mood='Choose a mood or a mix.';
    for(const key of ['max_travel_hours','walking_limit_km'])if(values[key]!==''&&(!Number.isFinite(Number(values[key]))||Number(values[key])<0||Number(values[key])>100))e[key]='Enter a value between 0 and 100, or leave blank.';
    if(String(values.accessibility||'').length>500)e.accessibility='Use 500 characters or fewer.';
    return e;
  }
  function expenseErrors(v) {
    const e={};if(!integer(v.amount_inr,1))e.amount_inr='Enter a positive whole-rupee amount.';
    if(!categories.includes(v.category))e.category='Choose an expense category.';
    if(!isoDate(v.spent_on))e.spent_on='Choose a valid expense date.';
    if(String(v.description||'').trim().length>500)e.description='Use 500 characters or fewer.';
    if(String(v.paid_by||'').trim().length>100)e.paid_by='Use 100 characters or fewer.';
    return e;
  }
  function normalizeSummary(data) {
    if(!data||typeof data!=='object'||Array.isArray(data))throw new Error('The budget summary could not be read. Please retry.');
    const s=data.summary||data.budget||data;
    return {...s,total_budget:amount(s.total_budget_inr??s.total_budget),planned_cost:amount(s.planned_total_inr??s.planned_cost),actual_spending:amount(s.actual_spending_inr??s.actual_total_inr??s.actual_spending),estimated_remaining_costs:amount(s.estimated_remaining_costs_inr??s.estimated_remaining_inr??s.estimated_remaining_costs),forecast_final_cost:amount(s.forecast_final_cost_inr??s.forecast_total_inr??s.forecast_final_cost),available_buffer:amount(s.available_buffer_inr??s.buffer_inr??s.available_buffer),over_budget:amount(s.over_budget_inr??s.over_budget),allocations:Array.isArray(s.allocations)?s.allocations:[]};
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
      if(!response.ok){const error=new Error(text(typeof data.detail==='string'?data.detail:'This action could not be completed. Please retry.'));error.field=data.field;error.code=data.code;error.status=response.status;throw error;}
      return data;
    }catch(error){if(error.name==='AbortError')throw new Error('The request timed out. Your entries are kept; please retry.');if(error instanceof TypeError)throw new Error('Connection failed. Your entries are kept; please retry.');throw error;}finally{clearTimeout(timer);}
  }
  async function capabilities(force=false) {
    const owner=uid();if(!owner)return {};
    if(!force&&capsUser===owner)return caps;
    if(capsPromise?.owner===owner)return capsPromise.promise;
    const promise=(async()=>{
      try{const result=await request('/api/experience/capabilities');if(owner!==uid())return {};const source=result.capabilities||result;caps=Object.fromEntries(flags.map(key=>[key,source[key]===true]));caps.conversation_persistence=source.conversation_persistence||'unknown';capsUser=owner;}
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
    async discover(body){requireFeature('discovery');return request('/api/discovery/recommendations',{method:'POST',body});},
    async feedback(body){requireFeature('discovery');return request('/api/discovery/feedback',keyed(nonce(),body));},
    async compare(ids,context={}){requireFeature('discovery');if(ids.length<2||ids.length>3||new Set(ids).size!==ids.length)throw new Error('Select two or three different destinations.');return request('/api/discovery/compare',{method:'POST',body:{destination_ids:ids,context}});},
    legacyRecommendations:()=>request(`/api/recommendations/${id(uid())}`),
    saveLegacy:destination=>request(`/api/shortlist/${id(uid())}`,{method:'POST',body:{destination_id:destination}}),
    async budget(trip){requireFeature('expense_tracking');return normalizeSummary(await request(tripPath(trip,'/budget')));},
    async allocate(trip,body){requireFeature('expense_tracking');return request(tripPath(trip,'/budget'),{method:'PUT',body});},
    async expenses(trip){requireFeature('expense_tracking');return request(tripPath(trip,'/expenses'));},
    async saveExpense(trip,body,key,expenseId){requireFeature('expense_tracking');return request(tripPath(trip,'/expenses')+(expenseId?'/'+id(expenseId):''),expenseId?{method:'PATCH',body}:keyed(key,body));},
    async deleteExpense(trip,expenseId){requireFeature('expense_tracking');return request(tripPath(trip,'/expenses/')+id(expenseId),{method:'DELETE'});},
    async legacyExpenses(trip){return request(tripPath(trip,'/expenses'));},
    async legacyAddExpense(trip,body){return request(tripPath(trip,'/expenses'),{method:'POST',body});},
    async budgetOptions(trip,body){requireFeature('budget_options');return request(tripPath(trip,'/budget-options'),{method:'POST',body});},
    async budgetPreview(trip,optionId){requireFeature('budget_options');return request(tripPath(trip,'/budget-options/preview'),{method:'POST',body:{option_id:optionId}});},
    async budgetConfirm(trip,token){requireFeature('budget_options');return request(tripPath(trip,'/budget-options/confirm'),keyed(token,{token}));},
    async check(trip){requireFeature('itinerary_check');return request(tripPath(trip,'/itinerary-check'),{method:'POST',body:{}});},
    async checkPreview(trip,findingId,resolutionId){requireFeature('itinerary_check');return request(tripPath(trip,'/itinerary-check/preview'),{method:'POST',body:{finding_id:findingId,resolution_id:resolutionId}});},
    async checkConfirm(trip,token){requireFeature('itinerary_check');return request(tripPath(trip,'/itinerary-check/confirm'),keyed(token,{token}));},
    async dayOptions(trip,day,goal){requireFeature('day_options');return request(tripPath(trip,'/day-options'),{method:'POST',body:{day_number:day,goal}});},
    async dayPreview(trip,optionId){requireFeature('day_options');return request(tripPath(trip,'/day-options/preview'),{method:'POST',body:{option_id:optionId}});},
    async dayConfirm(trip,token){requireFeature('day_options');return request(tripPath(trip,'/day-options/confirm'),keyed(token,{token}));},
    async itineraryPreferences(trip,body){requireFeature('day_options');return request(tripPath(trip,'/day-options/preferences'),{method:'PATCH',body});},
    async chat(body,key){requireFeature('assistant_chat');return request('/api/assistant/messages',keyed(key,body));},
    async assistantPreview(proposalId,trip){requireFeature('assistant_actions');return request('/api/assistant/proposals/'+id(proposalId)+'/preview',{method:'POST',body:{trip_id:trip||null}});},
    async assistantConfirm(proposalId,token,trip){requireFeature('assistant_actions');return request('/api/assistant/proposals/'+id(proposalId)+'/confirm',keyed(token,{token,trip_id:trip||null}));},
    async clearConversation(conversationId){return request('/api/assistant/conversations/'+id(conversationId),{method:'DELETE'});},
    async exportExpenses(trip){requireFeature('expense_tracking');return tripPath(trip,'/expenses/export');}
  };
  window.ExperienceAPI=API;
})();
