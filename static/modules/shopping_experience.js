/* Shopping plans and actual spending share the existing itinerary and ledger. */
(() => {
  'use strict';
  const A=window.ExperienceAPI,U=window.ExperienceUI;
  if(!A||!U||typeof document==='undefined')return;
  const host=document.getElementById('itineraryDisplayContainer');if(!host)return;
  const panel=U.el('section',null,'ex-shopping');panel.id='shoppingPane';panel.hidden=true;panel.setAttribute('aria-label','Shopping');host.append(panel);
  const tab=U.button('Shopping',()=>window.switchWorkspaceMode('shopping'));tab.id='shoppingTab';tab.disabled=true;tab.setAttribute('aria-controls',panel.id);tab.setAttribute('aria-expanded','false');document.getElementById('exBudgetTab')?.after(tab);
  let open=false,key=null,epoch=0,status=null;
  const current=()=>open&&key===A.contextKey();
  function isOpen(trip){return current()&&trip===A.tripId();}
  function restore(trip){if(!isOpen(trip))return;panel.hidden=false;for(const id of ['workspacePreTrip','workspaceLiveTrip','workspacePostTrip'])document.getElementById(id)?.classList.add('hidden');currentWorkspaceMode='shopping';}
  function hide(){open=false;panel.hidden=true;tab.setAttribute('aria-expanded','false');}
  const previous=window.switchWorkspaceMode;
  window.switchWorkspaceMode=function(mode){
    if(mode!=='shopping'){hide();return previous(mode);}
    const trip=A.workspaceTrip();if(!trip||!window.TripExperience.getSnapshot(trip))return;
    previous('pre');open=true;key=A.contextKey(trip);tab.setAttribute('aria-expanded','true');restore(trip);return load(trip);
  };
  async function load(trip){
    const ticket=++epoch;panel.replaceChildren(U.el('p','Loading shopping plan…'));panel.setAttribute('aria-busy','true');
    try{
      await A.capabilities();const [view,budget]=await Promise.all([A.request('/api/trip-actions/'+encodeURIComponent(trip)+'/timed-view'),A.budget(trip)]);
      if(ticket!==epoch||!current())return;
      const stored=view.trip?.trip_preferences||view.trip?.trip_preferences_json||{};
      const prefs=typeof stored==='string'?JSON.parse(stored):stored;
      const allowance=budget.allocations.find(a=>a.category==='shopping')||{};
      panel.replaceChildren(U.el('h2','Shopping'),U.el('p','Keep shopping time and spending together. Purchases and payments happen outside this app.','ex-muted'));
      const totals=U.el('dl',null,'ex-metrics');
      for(const [title,value] of [['Shopping allowance',A.money(allowance.planned_inr)],['Recorded spending',A.money(allowance.actual_inr)],['Shopping time',prefs.shopping_enabled?(prefs.shopping_duration_minutes||90)+' minutes per trip':'Not included']]){const cell=U.el('div');cell.append(U.el('dt',title),U.el('dd',value));totals.append(cell);}panel.append(totals);
      const plans=(view.days||[]).flatMap(day=>(day.timeline||[]).filter(s=>s.type==='shopping'||s.category==='shopping_local').map(s=>({...s,day:day.day_number})));
      if(plans.length){for(const plan of plans){const card=U.el('article',null,'te-card');card.append(U.el('h3',A.text(plan.title)),U.el('p','Day '+plan.day+' · '+plan.time_range));panel.append(card);}}
      else panel.append(U.el('p',prefs.shopping_enabled?'No shopping venue currently fits your schedule. Choose a suitable place or adjust your time window.':'Turn on shopping in the trip settings to reserve time.','ex-note'));
      const actions=U.el('div',null,'ex-actions');actions.append(U.button('Record shopping expense',()=>window.BudgetExperience.addShoppingExpense(),'ex-primary'));
      const edit=U.button('Edit shopping time & allowance',()=>{location.hash='/trips/'+encodeURIComponent(trip)+'/edit';});edit.disabled=window.TripExperience.getSnapshot(trip)?.status!=='draft';actions.append(edit);panel.append(actions);
      U.lines(panel,'Planning notes',['Shopping allowances are estimates. Any extra spending appears in your overall trip forecast.']);
    }catch(error){if(current()){panel.replaceChildren(U.el('h2','Shopping'),U.el('p',error.message,'ex-error'),U.button('Retry',()=>load(trip)));}}
    finally{if(ticket===epoch)panel.removeAttribute('aria-busy');}
  }
  window.addEventListener('trip:runtime',event=>{const next=event.detail;if(next.tripId!==A.tripId())return;tab.disabled=false;if(open&&status&&status!==next.snapshot.status){hide();previous(next.snapshot.status==='completed'?'post':next.snapshot.status==='live'?'live':'pre');}status=next.snapshot.status;});
  window.addEventListener('trip:context-cleared',()=>{epoch++;hide();key=null;status=null;tab.disabled=true;panel.replaceChildren();});
  window.addEventListener('hashchange',()=>{if(!/^#\/trips\/[^/]+$/.test(location.hash))hide();});
  window.ShoppingExperience={isOpen,restore};
})();
