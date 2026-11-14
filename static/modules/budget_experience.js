/* E: allocations, server financial summaries and an editable expense ledger. */
(() => {
  'use strict';
  const A=window.ExperienceAPI,U=window.ExperienceUI;
  if(!A||!U||typeof document==='undefined')return;
  const display=document.getElementById('itineraryDisplayContainer');if(!display)return;
  const label=key=>({accommodation:'Accommodation',food:'Food',intercity_transport:'Travel to / from destination',local_transport:'Local transport',activities:'Activities',shopping:'Shopping',emergency_reserve:'Emergency reserve',other:'Other'})[key]||key;
  const panel=U.el('section',null,'ex-budget');panel.id='exBudgetPane';panel.hidden=true;panel.setAttribute('aria-labelledby','exBudgetTitle');
  const compact=U.el('aside',null,'ex-budget-compact');compact.id='exBudgetCompact';compact.hidden=true;
  document.getElementById('cTripLifecycle')?.after(compact);display.append(panel);
  const tab=U.button('Budget & expenses',()=>window.switchWorkspaceMode('budget'),'ex-button');tab.id='exBudgetTab';tab.setAttribute('aria-controls',panel.id);tab.setAttribute('aria-expanded','false');
  document.getElementById('wsTabBtn-post')?.parentElement.after(tab);
  let open=false,epoch=0,summary=null,ledger=[],context=null,lastStatus=null,compactKey=null,account=A.uid();
  function clearAccount(force=false){if(!force&&account===A.uid())return;account=A.uid();epoch++;summary=null;ledger=[];context=null;compactKey=null;open=false;panel.hidden=true;panel.replaceChildren();compact.hidden=true;compact.replaceChildren();tab.setAttribute('aria-expanded','false');}
  new MutationObserver(()=>clearAccount()).observe(document.getElementById('dashboardView'),{attributes:true,attributeFilter:['class']});
  window.addEventListener('trip:context-cleared',()=>clearAccount(true));
  function current(key){return key===A.contextKey()&&open;}
  const rawMode=window.switchWorkspaceMode;
  window.switchWorkspaceMode=function(mode){
    if(mode!=='budget'){open=false;panel.hidden=true;tab.setAttribute('aria-expanded','false');return rawMode(mode);}
    const trip=A.tripId();if(!trip||!window.TripExperience.getSnapshot(trip))return;
    open=true;panel.hidden=false;tab.setAttribute('aria-expanded','true');
    for(const id of ['workspacePreTrip','workspaceLiveTrip','workspacePostTrip'])document.getElementById(id)?.classList.add('hidden');
    for(const id of ['wsTabBtn-pre','wsTabBtn-live','wsTabBtn-post'])document.getElementById(id)?.setAttribute('aria-selected','false');
    load();
  };
  function compactSummary(s) {
    compact.replaceChildren();compact.hidden=false;const heading=U.el('strong','Budget at a glance');compact.append(heading);
    for(const [title,key] of [['Total budget','total_budget'],['Spent so far','actual_spending'],['Estimated costs still to come','estimated_remaining_costs'],['Forecast final cost','forecast_final_cost'],['Available buffer','available_buffer']]) {
      const cell=U.el('span');cell.append(U.el('small',title),U.el('b',A.money(s[key])));compact.append(cell);
    }
    compact.append(U.button('Open budget',()=>window.switchWorkspaceMode('budget')));
  }
  async function load() {
    const ticket=++epoch,key=A.contextKey(),trip=A.tripId();if(context!==key){summary=null;ledger=[];}context=key;
    panel.replaceChildren(U.el('p','Loading saved budget and expenses…'));panel.setAttribute('aria-busy','true');
    try {
      await A.capabilities();if(ticket!==epoch||!current(key))return;
      if(!A.can('expense_tracking')) {
        const legacy=await A.legacyExpenses(trip);if(ticket!==epoch||!current(key))return;
        renderLegacy(legacy,trip,key);return;
      }
      const [s,l]=await Promise.all([A.budget(trip),A.expenses(trip)]);if(ticket!==epoch||!current(key))return;
      if(!Array.isArray(l.expenses))throw new Error('The expense list could not be read. Please retry.');
      summary=s;ledger=l.expenses;render(trip,key);compactSummary(s);
    }catch(error){if(current(key)&&ticket===epoch){panel.replaceChildren(U.el('h2','Budget & expenses'),U.el('p',error.message,'ex-error'),U.button('Retry',load));}}
    finally{if(ticket===epoch)panel.removeAttribute('aria-busy');}
  }
  function heading(){const h=U.el('h2','Budget & expenses');h.id='exBudgetTitle';panel.append(h);panel.append(U.el('p','Manual recordkeeping only. Bookings, food orders, shopping payments and bill settlements happen outside this app.','ex-muted'));}
  function renderLegacy(data,trip,key) {
    if(!Array.isArray(data.expenses))throw new Error('The expense list could not be read. Please retry.');
    panel.replaceChildren();heading();const totals=data.planned_vs_actual||{};ledger=data.expenses;
    panel.append(U.el('p',`Planned estimate: ${A.money(totals.planned_total_inr)} · Recorded spending: ${ledger.length?A.money(totals.actual_total_inr):'Not entered'}`));
    U.unavailable(panel,'Detailed allocations, remaining-cost forecasts and expense corrections are not available yet. Recorded spending is not the amount you can freely spend.',async()=>{await A.capabilities(true);await load();});
    panel.append(U.button('Add expense',()=>expenseForm(trip,key,null,true),'ex-primary'));
    expenseRows(panel,ledger,trip,key,false);
    panel.append(U.button('Explore my budget',()=>window.BudgetExperience.openOptions(trip)));
  }
  function render(trip,key) {
    panel.replaceChildren();heading();
    const metrics=U.el('dl',null,'ex-metrics');
    const fields=[['Total budget','total_budget'],['Planned cost','planned_cost'],['Spent so far','actual_spending'],['Estimated remaining costs','estimated_remaining_costs'],['Forecast final cost','forecast_final_cost'],['Available buffer','available_buffer']];
    for(const [name,field] of fields){const cell=U.el('div');cell.append(U.el('dt',name),U.el('dd',field==='actual_spending'&&!ledger.length&&summary.actual_spending===0&&!summary.expenses_complete?'Not entered':A.money(summary[field])));metrics.append(cell);}panel.append(metrics);
    if(summary.over_budget>0)panel.append(U.el('p','Forecast exceeds your budget by '+A.money(summary.over_budget),'ex-warning'));
    panel.append(U.el('p','Forecast = recorded spending + estimated remaining costs. The emergency reserve stays protected unless you explicitly release it. Unrecorded expenses are not assumed to be zero.','ex-muted'));
    const actions=U.el('div',null,'ex-actions');const notice=U.status(panel);
    const allocate=U.button('Edit allocations',()=>allocations(trip,key));
    const snapshot=window.TripExperience.getSnapshot(trip);
    allocate.disabled=summary.can_edit_allocations===false||(!summary.can_edit_allocations&&snapshot?.status!=='draft');allocate.title=allocate.disabled?'Allocation editing is locked for this trip stage.':'';
    const add=U.button('Add expense',()=>expenseForm(trip,key),'ex-primary');add.disabled=summary.can_add_expense===false;
    const csv=U.button('Download expenses CSV',()=>U.busy(csv,notice,async()=>{
      const url=await A.exportExpenses(trip);const response=await fetch(url);
      if(!response.ok)throw new Error('The expense export could not be downloaded. Please retry.');
      if(!/text\/csv|application\/octet-stream/.test(response.headers.get('Content-Type')||''))throw new Error('The export service did not return a CSV file.');
      const blob=await response.blob();if(!current(key))return;const link=U.el('a');const objectUrl=URL.createObjectURL(blob);link.href=objectUrl;link.download='trip-expenses.csv';link.click();setTimeout(()=>URL.revokeObjectURL(objectUrl),1000);
    }));actions.append(allocate,add,U.button('Explore my budget',()=>openOptions(trip)),csv);panel.append(actions);
    if(allocate.disabled)panel.append(U.el('p','Allocation editing is locked for this trip stage. Expense corrections remain available when permitted.','ex-muted'));
    const switcher=U.el('label','Display amounts ');const units=U.el('select');for(const [value,title] of [['party','Whole party'],['person','Equal share per person']]){const o=U.el('option',title);o.value=value;units.append(o);}switcher.append(units);panel.append(switcher,U.el('p','Per-person amounts are an equal-share view, not settlement instructions. Room/night rates remain labelled separately.','ex-muted'));
    const storedTrip=typeof activeUserTrips!=='undefined'?activeUserTrips.find(item=>item.id===trip):null;
    const people=Number(summary.travellers_count??summary.party_size??storedTrip?.travellers_count);
    units.options[1].disabled=!Number.isInteger(people)||people<1;
    if(units.options[1].disabled)panel.append(U.el('small','Party size is unavailable, so the per-person view is disabled.'));
    const tableBox=U.el('div',null,'ex-table-scroll');panel.append(tableBox);
    const draw=()=>{
      const divisor=units.value==='person'&&Number.isInteger(people)&&people>0?people:1;
      const table=U.el('table',null,'ex-table');const cap=U.el('caption',units.value==='person'?'Category totals divided equally per traveller':'Whole-party category totals');table.append(cap);
      const head=U.el('tr');for(const text of ['Category','Planned','Spent','Estimated remaining','Basis'])head.append(U.el('th',text));table.append(head);
      for(const category of A.categories) {
        const rowData=summary.allocations.find(a=>a.category===category)||{};
        const row=U.el('tr');row.append(U.el('th',label(category)));
        for(const field of ['planned_inr','actual_inr','estimated_remaining_inr'])row.append(U.el('td',A.amount(rowData[field])===null?'Not entered':A.money(Number(rowData[field])/divisor)));
        row.append(U.el('td',A.text(rowData.basis_label||rowData.unit_label||'Total allowance')));table.append(row);
      }tableBox.replaceChildren(table);
    };units.onchange=draw;draw();
    U.lines(panel,'Budget warnings',summary.warnings);
    const alternatives=summary.lower_cost_alternatives||[];
    if(alternatives.length){U.lines(panel,'Lower-cost upcoming ideas',alternatives.map(a=>a.explanation||a.title));panel.append(U.button('Compare a lower-cost plan',()=>openOptions(trip)));}
    panel.append(U.el('h3','Your expenses'));expenseRows(panel,ledger,trip,key,true);
  }
  function expenseRows(parent,items,trip,key,editable) {
    if(!items.length){parent.append(U.el('p','No expenses entered yet.'));return;}
    const list=U.el('ul',null,'ex-expenses');
    for(const item of items){const row=U.el('li');const amount=item.amount_inr??item.amount;row.append(U.el('strong',`${A.money(amount)} · ${label(item.category)}`),U.el('p',`${item.spent_on||item.date||''} · ${item.description||item.note||'No description'}`));if(item.paid_by)row.append(U.el('small','Paid by '+item.paid_by));
      if(item.planned_item_id)row.append(U.el('p',A.text(item.remaining_estimate_message||'Linked to a planned cost. Payments and its remaining estimate are managed together.')));
      if(editable){const edit=U.button('Edit',()=>expenseForm(trip,key,item));edit.disabled=item.can_edit===false;const remove=U.button('Delete',()=>{
        const d=U.dialog('Delete expense?',`${A.money(amount)} · ${item.description||item.note||label(item.category)}. The server will recalculate the remaining estimate.`);d.close.textContent='Cancel';const confirm=U.button('Delete expense',()=>U.busy(confirm,d.notice,async()=>{if(!current(key))throw new Error('The trip changed. Reopen the expense.');await A.deleteExpense(trip,item.id);d.box.close();await load();}),'ex-danger');d.actions.prepend(confirm);
      });remove.disabled=item.can_delete===false;row.append(edit,remove);}list.append(row);
    }parent.append(list);
  }
  function expenseForm(trip,key,existing=null,legacy=false) {
    const d=U.dialog(existing?'Edit expense':'Add expense','Enter an amount and category. Descriptions and payer labels are optional.');const f=U.form('expense-'+A.nonce());d.content.append(f);
    const categoryOptions=A.categories.filter(c=>c!=='emergency_reserve').map(c=>[c,label(c)]);
    if(legacy){categoryOptions.splice(0,categoryOptions.length,...[['stay','Stay'],['food','Food'],['transport','Transport'],['activities','Activities'],['shopping','Shopping'],['other','Other']]);}
    U.field(f,'amount_inr','Amount (whole INR)',{type:'number',min:1,max:1000000000,value:existing?.amount_inr??existing?.amount??'',required:true});
    U.field(f,'category','Category',{options:categoryOptions,value:existing?.category||'food',required:true});
    U.field(f,'spent_on','Date',{type:'date',value:existing?.spent_on||U.today(),required:true});
    U.field(f,'description','Description (optional)',{value:existing?.description||existing?.note||'',maxlength:500});
    if(!legacy) {
      U.field(f,'paid_by','Paid by (optional)',{value:existing?.paid_by||'',maxlength:100,help:'For recordkeeping only; this does not settle a group bill.'});
      const plans=(summary?.planned_items||[]).map(p=>[p.id,`${p.label||p.category} · ${A.money(p.estimated_remaining_inr)} estimated remaining`]);
      U.field(f,'planned_item_id','Link to planned cost (optional)',{options:[['','Unlinked expense'],...plans],value:existing?.planned_item_id||'',help:'A linked payment reduces the remaining estimate. A deposit does not mark the full cost paid.'});
      U.field(f,'payment_state','Payment status',{options:[['partial','Partial payment / deposit'],['final','Final payment — no further cost expected']],value:existing?.payment_state||'partial'});
    }
    const submit=U.el('button',existing?'Save correction':'Save expense','ex-primary');submit.type='submit';f.append(submit);let inFlight=false;const requestKey=A.nonce();
    f.onsubmit=async event=>{
      event.preventDefault();if(inFlight)return;const values=U.values(f);const validation=legacy?{...values,category:({stay:'accommodation',transport:'local_transport'})[values.category]||values.category}:values;
      if(!U.errors(f,A.expenseErrors(validation)))return;
      inFlight=true;await U.busy(submit,d.notice,async()=>{
        if(!current(key))throw new Error('The trip or account changed. Reopen the expense form.');
        const body={...values,amount_inr:Number(values.amount_inr),description:values.description.trim(),paid_by:values.paid_by?.trim()||null,planned_item_id:values.planned_item_id||null};
        const inputs=[...f.querySelectorAll('input,select')];inputs.forEach(n=>n.disabled=true);d.close.disabled=true;
        try{if(legacy)await A.legacyAddExpense(trip,{amount_inr:body.amount_inr,category:values.category,note:body.description,spent_on:values.spent_on});else await A.saveExpense(trip,body,requestKey,existing?.id);f.dataset.dirty='false';d.box.close();await load();}
        catch(error){if(error.field&&f.elements[error.field])U.errors(f,{[error.field]:error.message});throw error;}
        finally{inputs.forEach(n=>n.disabled=false);d.close.disabled=false;}
      });inFlight=false;
    };
    f.addEventListener('input',()=>{f.dataset.dirty='true';});d.box.addEventListener('cancel',event=>{if(inFlight)event.preventDefault();});
  }
  function allocations(trip,key) {
    const d=U.dialog('Plan your budget','Reserve stay, food and transport before choosing activities. Emergency money is protected. Amounts are allowances, not bookings.');const f=U.form('allocations');d.content.append(f);
    U.field(f,'total_budget_inr','Total trip budget (INR)',{type:'number',min:1000,value:summary.total_budget,required:true});
    const rows=[];
    for(const category of A.categories){const saved=summary.allocations.find(a=>a.category===category)||{};const group=U.el('fieldset');group.append(U.el('legend',label(category)));f.append(group);const rowForm=U.form('allocation-'+category);
      // Fields belong to the outer form; each row is a fieldset, never a nested form.
      rowForm.dataset.formId='allocation-'+category;
      const amount=U.field(rowForm,category+'_amount','Amount / allowance (INR)',{type:'number',min:0,value:saved.amount_inr??(!saved.basis||saved.basis==='total'?saved.planned_inr:'')??'',help:'Leave blank when unknown; zero means no allowance.'});
      const basis=U.field(rowForm,category+'_basis','Basis',{options:category==='food'?[['total','Whole-party total'],['per_person_day','Per person / day']]:category==='accommodation'?[['total','Whole stay total'],['per_room_night','Per room / night']]:[['total','Whole-party total']],value:saved.basis||'total'});
      const state=U.field(rowForm,category+'_state','Amount status',{options:[['estimated','Estimated'],['booked','Booked / agreed cost']],value:saved.status||'estimated'});
      while(rowForm.firstChild)group.append(rowForm.firstChild);rows.push({category,amount,basis,state});
    }
    U.field(f,'rooms','Rooms (required for room/night estimates)',{type:'number',min:1,max:30,value:summary.rooms??'',help:'Confirm the number of rooms. No room count is guessed.'});
    const release=U.field(f,'release_emergency_reserve','Release emergency reserve for normal spending?',{options:[['no','No — keep protected'],['yes','Yes — explicitly release it']],value:'no'});
    const save=U.el('button','Save allocations','ex-primary');save.type='submit';f.append(save);
    f.onsubmit=event=>{event.preventDefault();const e={};if(!A.integer(f.elements.total_budget_inr.value,1000))e.total_budget_inr='Enter a whole-rupee total of at least ₹1,000.';for(const row of rows)if(row.amount.value!==''&&!A.integer(row.amount.value,0))e[row.amount.name]='Enter whole INR, or leave unknown.';if((f.elements.rooms.value!==''||rows.some(row=>row.basis.value==='per_room_night'))&&!A.integer(f.elements.rooms.value,1,30))e.rooms='Enter 1–30 rooms.';if(!U.errors(f,e))return;
      U.busy(save,d.notice,async()=>{if(!current(key)||window.TripExperience.getSnapshot(trip)?.status!=='draft')throw new Error('The trip is no longer editable.');await A.allocate(trip,{total_budget_inr:Number(f.elements.total_budget_inr.value),...(f.elements.rooms.value!==''?{rooms:Number(f.elements.rooms.value)}:{}),release_emergency_reserve:release.value==='yes',allocations:rows.map(r=>({category:r.category,amount_inr:r.amount.value===''?null:Number(r.amount.value),basis:r.basis.value,status:r.state.value})),version:summary.version});d.box.close();await load();});};
  }
  async function openOptions(trip=A.workspaceTrip()) {
    if(!await U.planningGate())return;
    if(!trip){const d=U.dialog('Explore your budget','Choose a destination first, or discover three places within your comfortable budget.');d.content.append(U.button('Help me choose',()=>{d.box.close();window.RecommendationDiscovery?.open();}),'');return;}
    const key=A.contextKey(trip);const d=U.dialog('What could a little more budget get you?','Compare the same destination, dates and party. Extra money may improve comfort or convenience rather than add activities.');const f=U.form('budget-options');d.content.append(f);
    const cached=key===context?summary:null;
    U.field(f,'current_budget_inr','Current comfortable budget (INR)',{type:'number',min:1000,value:cached?.total_budget??'',required:true});
    U.field(f,'max_extra_inr','Maximum additional amount to consider (INR)',{type:'number',min:0,value:0,required:true,help:'This is a limit to explore, not a commitment to spend.'});
    U.field(f,'priority','What would you value most?',{options:[['experiences','Relevant experiences'],['stay_comfort','Stay comfort'],['transport_convenience','Transport convenience'],['downtime','More downtime']]});
    const submit=U.el('button','Compare budget options','ex-primary');submit.type='submit';submit.disabled=true;f.append(submit);const results=U.el('div');d.content.append(results);
    await A.capabilities();submit.disabled=!A.can('budget_options');if(!A.can('budget_options')){U.unavailable(d.content,'Budget comparisons are unavailable. Your current itinerary and budget are unchanged.',async()=>{await A.capabilities(true);submit.disabled=!A.can('budget_options');});}
    f.onsubmit=event=>{event.preventDefault();const v=U.values(f),errors={};if(!A.integer(v.current_budget_inr,1000))errors.current_budget_inr='Enter a whole-rupee budget of at least ₹1,000.';if(!A.integer(v.max_extra_inr,0))errors.max_extra_inr='Enter a non-negative whole-rupee amount.';if(!U.errors(f,errors))return;
      U.busy(submit,d.notice,async()=>{if(key!==A.contextKey())throw new Error('The selected trip changed. Reopen this comparison.');const response=await A.budgetOptions(trip,{...v,current_budget_inr:Number(v.current_budget_inr),max_extra_inr:Number(v.max_extra_inr)});if(!d.box.isConnected||key!==A.contextKey())return;results.replaceChildren();
        if(!Array.isArray(response.options))throw new Error('The budget comparison could not be read.');
        if(response.message)results.append(U.el('p',A.text(response.message),'ex-note'));
        if(response.keep_current_recommended===true||response.recommendation==='keep_current')results.append(U.el('p','Your current budget is a good fit. Additional spending offers little relevant benefit.','ex-note'));
        for(const option of response.options.slice(0,3)) {
          const card=U.el('article',null,'ex-option');card.append(U.el('h3',A.text(option.title||option.label)),U.el('strong',A.money(option.total_cost_inr)),U.el('p','Additional cost: '+A.money(option.additional_cost_inr)));
          U.lines(card,'What changes',option.changes);U.lines(card,'What stays the same',option.unchanged);U.lines(card,'Benefits',option.benefits);U.lines(card,'Trade-offs',option.tradeoffs);
          if(option.estimate_note)card.append(U.el('p',A.text(option.estimate_note),'ex-muted'));
          const use=U.button('Preview this option',()=>U.busy(use,d.notice,async()=>{const next=await A.budgetPreview(trip,option.id);U.confirmation('Review budget option',next.preview||next,{current:()=>key===A.contextKey(),confirm:token=>A.budgetConfirm(trip,token),done:async()=>{d.box.close();await refreshTrip(trip);}});}));
          const snapshot=window.TripExperience.getSnapshot(trip);
          const outsideLimit=A.amount(option.total_cost_inr)===null||A.amount(option.additional_cost_inr)===null||Number(option.additional_cost_inr)>Number(v.max_extra_inr)||Number(option.total_cost_inr)>Number(v.current_budget_inr)+Number(v.max_extra_inr);
          use.disabled=outsideLimit||option.can_apply===false||snapshot?.status!=='draft';if(outsideLimit)card.append(U.el('p','This option is outside your stated limit or has no comparable price. It cannot be applied.','ex-warning'));else if(use.disabled)use.title='This trip stage does not allow a new planning budget.';card.append(use);results.append(card);
        }
        if(!response.options.length)results.append(U.el('p','No feasible alternatives were returned. Try a different maximum or keep the current plan.'));
      });};
  }
  async function refreshTrip(trip) {
    if(trip!==A.tripId())return;
    window.dispatchEvent(new CustomEvent('experience:trip-updated',{detail:{tripId:trip}}));
    if(open)await load();await window.TripExperience?.route();
  }
  window.BudgetExperience={openOptions,open:()=>window.switchWorkspaceMode('budget'),refresh:load,refreshTrip};
  window.addEventListener('trip:runtime',event=>{
    clearAccount();
    const next=event.detail,key=A.contextKey(next.tripId);
    if(open&&(context!==key||(lastStatus&&lastStatus!==next.snapshot.status))){open=false;panel.hidden=true;tab.setAttribute('aria-expanded','false');}
    lastStatus=next.snapshot.status;
    if(summary&&context===key)compactSummary(summary);else{compact.hidden=true;loadCompact(next.tripId);}
  });
  async function loadCompact(trip) {
    const key=A.contextKey(trip);if(compactKey===key||!trip)return;compactKey=key;
    try{
      await A.capabilities();
      if(key!==A.contextKey())return;
      if(A.can('expense_tracking')){const result=await A.budget(trip);if(key!==A.contextKey())return;summary=result;context=key;compactSummary(result);}
      else {const result=await A.legacyExpenses(trip);if(key!==A.contextKey())return;compact.replaceChildren(U.el('strong','Budget at a glance'),U.el('span','Planned estimate: '+A.money(result.planned_vs_actual?.planned_total_inr)),U.el('span','Recorded spending: '+(result.expenses?.length?A.money(result.planned_vs_actual?.actual_total_inr):'Not entered')),U.button('Open budget',()=>window.switchWorkspaceMode('budget')));compact.hidden=false;}
    }catch(_){if(key===A.contextKey()){compact.replaceChildren(U.el('span','Budget summary unavailable.'),U.button('Retry budget',()=>{compactKey=null;loadCompact(trip);}));compact.hidden=false;compactKey=null;}}
  }
  window.addEventListener('experience:expenses-updated',event=>{if(event.detail.tripId!==A.tripId())return;compactKey=null;loadCompact(event.detail.tripId);if(open)load();});
  window.addEventListener('hashchange',()=>{if(!/^#\/trips\/[^/]+$/.test(location.hash)){open=false;panel.hidden=true;compact.hidden=true;tab.setAttribute('aria-expanded','false');}});
})();
