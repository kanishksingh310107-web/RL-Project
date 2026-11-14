/* E: recommendation feedback, guided discovery and fair destination comparison. */
(() => {
  'use strict';
  const A=window.ExperienceAPI,U=window.ExperienceUI;
  if(!A||!U||typeof document==='undefined')return;
  const root=document.getElementById('recommendationsSection');if(!root)return;
  const items=new Map(),compared=new Map();let owner=null,discoveryContext={},requestVersion=0,handoff=null;
  const entry=U.el('section',null,'ex-discovery');entry.id='exDiscovery';
  entry.append(U.el('h2','Where will you go next?'),U.el('p','Discover places that fit you, compare your choices, then turn a favourite into a trip.','ex-muted'));
  const actions=U.el('div',null,'ex-entry-actions');
  actions.append(U.button('I know my destination',()=>window.toggleTripFormModal(),'ex-primary'),U.button('Help me choose',()=>openDiscovery()),U.button('Explore my budget',()=>window.BudgetExperience?.openOptions()));entry.append(actions);
  const shelves=U.el('div');shelves.id='exRecommendationShelves';const selection=U.el('aside',null,'ex-comparison-bar');selection.id='exComparisonBar';selection.hidden=true;entry.append(shelves,selection);root.before(entry);
  const notice=U.status(entry);
  const isHome=item=>window.TripExperience?.isHomeDestination(item);
  const canonicalId=item=>item.destination_id||item.id;
  const name=item=>item.name||item.destination_name||'Destination';
  const texts=value=>Array.isArray(value)?value.map(v=>typeof v==='string'?v:v.message||v.text||'').filter(Boolean):typeof value==='string'?[value]:[];
  const reasons=item=>texts(item.reasons||item.why_recommended||item.why_recommended_for_you||item.explanation);
  function checkOwner(){if(owner!==A.uid()){owner=A.uid();compared.clear();items.clear();selection.hidden=true;discoveryContext={};shelves.replaceChildren();handoff=null;}}
  function register(item){checkOwner();const id=canonicalId(item);if(typeof id!=='string'||isHome(item))return null;items.set(id,item);return id;}
  function addComparison(item,feedback=notice){
    const id=register(item);if(!id)return;
    if(compared.has(id))compared.delete(id);
    else if(compared.size>=3){feedback.textContent='Compare up to three destinations. Remove one before adding another.';return;}
    else compared.set(id,item);
    drawSelection();document.querySelectorAll('[data-ex-compare]').forEach(n=>{n.setAttribute('aria-pressed',String(compared.has(n.dataset.exCompare)));n.textContent=compared.has(n.dataset.exCompare)?'Remove comparison':'Compare';});
  }
  function drawSelection(){
    selection.replaceChildren();selection.hidden=!compared.size;if(!compared.size)return;
    selection.append(U.el('strong',`${compared.size} of 3 destinations selected`));
    for(const [id,item] of compared)selection.append(U.button('Remove '+name(item),()=>{compared.delete(id);drawSelection();document.querySelectorAll('[data-ex-compare]').forEach(n=>{if(n.dataset.exCompare===id){n.textContent='Compare';n.setAttribute('aria-pressed','false');}});}));
    const compare=U.button('Compare destinations',()=>compareDestinations(),'ex-primary');compare.disabled=compared.size<2;selection.append(compare);
  }
  function feedbackControls(item,parent,context={}) {
    const id=register(item);if(!id)return;
    const bar=U.el('div',null,'ex-actions'),message=U.status(parent);
    const compare=U.button(compared.has(id)?'Remove comparison':'Compare',()=>addComparison(item,message));compare.dataset.exCompare=id;compare.setAttribute('aria-pressed',String(compared.has(id)));bar.append(compare);
    const send=async(action,reason,control)=>U.busy(control,message,async()=>{
      if(!await window.ProfileGate.require())return;await A.capabilities();
      const result=await A.feedback({destination_id:id,action,reason:reason||null,context});
      if(owner!==A.uid())return;
      message.textContent=result.message||'Preference saved. Refresh suggestions to see updated choices.';
      control.setAttribute('aria-pressed','true');
      window.dispatchEvent(new CustomEvent('experience:recommendation-feedback',{detail:{destinationId:id,action}}));
    });
    for(const [value,title] of [['interested','Interested'],['already_visited','Already visited']]){const b=U.button(title,()=>send(value,null,b));bar.append(b);}
    const reject=U.button('Not for me',()=>{
      const d=U.dialog('What would make this a better suggestion?','Your answer helps refine future recommendations.');
      for(const [reason,title] of [['too_expensive','Too expensive'],['too_far','Too far'],['too_crowded','Too crowded'],['wrong_activity_type','Wrong activity type'],['not_interested','Not interested']]){
        const b=U.button(title,()=>U.busy(b,d.notice,async()=>{await A.capabilities();const result=await A.feedback({destination_id:id,action:'not_for_me',reason,context});message.textContent=result.message||'Preference saved.';d.box.close();}));d.content.append(b);
      }
    });bar.append(reject);
    for(const [value,title] of [['more_like_this','More like this'],['closer_to_home','Closer to home'],['too_expensive','Too expensive']]){const b=U.button(title,()=>send(value,null,b));bar.append(b);}
    parent.append(bar);
    A.capabilities().then(()=>{if(!parent.isConnected)return;bar.querySelectorAll('button').forEach(b=>{if(b!==compare){b.disabled=!A.can('discovery');if(b.disabled)b.title='Preference refinement is temporarily unavailable. Existing Save and Explore controls still work.';}});});
  }
  const rawCard=window.renderRecommendationCard;
  if(typeof rawCard==='function')window.renderRecommendationCard=function(item,category){
    const card=rawCard(item,category);register(item);
    const explanation=U.el('div',null,'ex-card-explanation');U.lines(explanation,'Why this place?',reasons(item).slice(0,2));
    const downside=item.tradeoff||item.trade_off||item.drawback;if(downside)explanation.append(U.el('p','Trade-off: '+A.text(downside),'ex-muted'));
    const target=card.lastElementChild||card;target.append(explanation);feedbackControls(item,target,{});return card;
  };
  function card(item,context={}) {
    register(item);const box=U.el('article',null,'ex-destination-card');box.append(U.el('h3',name(item)));
    box.append(U.el('strong',window.TripExperience.matchLabel(item)));
    U.lines(box,'Why this fits',reasons(item));
    box.append(U.el('p','Estimated full-trip cost: '+A.money(item.estimated_total_inr??item.total_cost_inr)),U.el('p','Travel time: '+(item.travel_time_label||'Not available')));
    const drawback=item.tradeoff||item.drawback;box.append(U.el('p',drawback?'Trade-off: '+A.text(drawback):'Trade-off information is not available.','ex-muted'));
    if(item.estimate_note)box.append(U.el('p',A.text(item.estimate_note),'ex-muted'));U.safeLinks(box,item.sources);
    const actionBar=U.el('div',null,'ex-actions');
    actionBar.append(U.button('Explore',()=>explore(item,context)),U.button('Plan this trip',()=>plan(item,context),'ex-primary'));
    const save=U.button(item.is_shortlisted?'Saved · remove':'Save for later',()=>U.busy(save,notice,async()=>{
      if(!await window.ProfileGate.require())return;
      const result=await A.saveLegacy(canonicalId(item));if(typeof result.is_shortlisted!=='boolean')throw new Error('The saved state could not be read. Refresh your recommendations before retrying.');
      item.is_shortlisted=result.is_shortlisted;save.textContent=result.is_shortlisted?'Saved · remove':'Save for later';save.setAttribute('aria-pressed',String(result.is_shortlisted));notice.textContent=result.is_shortlisted?'Destination saved.':'Destination removed from saved places.';
    }));actionBar.append(save);box.append(actionBar);feedbackControls(item,box,context);return box;
  }
  function explore(item,context) {
    const d=U.dialog(name(item),'Sample plans and prices are estimates unless their source says otherwise.');d.content.append(cardDetails(item));d.actions.prepend(U.button('Plan this trip',()=>{d.box.close();plan(item,context);},'ex-primary'));
  }
  function cardDetails(item) {
    const box=U.el('div');U.lines(box,'Why recommended',reasons(item));
    U.lines(box,'Estimated cost breakdown',Object.entries(item.cost_breakdown||{}).map(([category,value])=>category.replace(/_/g,' ')+': '+A.money(typeof value==='object'?value.total_inr??value.per_party:value)));
    const days=item.sample_itinerary?.days||item.sample_itinerary||[];
    if(Array.isArray(days))for(const day of days){box.append(U.el('h4',day.theme||'Day '+day.day_number));U.lines(box,'Suggested experiences',day.activities||day.stops||[]);}
    if(!Array.isArray(days)||!days.length)box.append(U.el('p','A sample itinerary is not available. Choose your dates in the planner to generate one.'));
    U.safeLinks(box,item.sources);return box;
  }
  async function compareDestinations() {
    if(compared.size<2||compared.size>3)return;
    const selected=[...compared.values()],d=U.dialog('Compare destinations','Costs are comparable only when dates or duration, party and scope match. Unavailable information is shown explicitly.');
    const render=list=>{
      const wrap=U.el('div',null,'ex-table-scroll'),table=U.el('table',null,'ex-table');table.append(U.el('caption','Destination comparison'));
      const heading=U.el('tr');heading.append(U.el('th','Compare'));for(const item of list)heading.append(U.el('th',name(item)));table.append(heading);
      const fields=[['Why this fits',item=>reasons(item).join(' · ')||'Not available'],['Estimated whole-trip cost',item=>A.money(item.estimated_total_inr??item.total_cost_inr)],['Travel time',item=>item.travel_time_label||'Not available'],['Main trade-off',item=>item.tradeoff||item.drawback||'Not available'],['Accessibility',item=>item.accessibility_summary||'Not available'],['Comparison basis',item=>item.comparison_basis||'Check dates, duration and party before choosing']];
      for(const [title,get] of fields){const row=U.el('tr');row.append(U.el('th',title));for(const item of list)row.append(U.el('td',A.text(get(item))));table.append(row);}wrap.append(table);d.content.replaceChildren(wrap);
      for(const item of list)d.content.append(U.button('Choose '+name(item),()=>{d.box.close();plan(item,discoveryContext);}));
    };
    render(selected);await A.capabilities();if(!A.can('discovery')){d.notice.textContent='Showing information already supplied with these recommendations. A tailored comparison is currently unavailable.';return;}
    try{const result=await A.compare(selected.map(canonicalId),discoveryContext);if(d.box.isConnected&&Array.isArray(result.destinations))render(result.destinations);}catch(error){if(d.box.isConnected)d.notice.textContent=error.message;}
  }
  async function openDiscovery() {
    if(!await window.ProfileGate.require())return;checkOwner();
    const profile=typeof state!=='undefined'?state.currentProfile||{}:{};
    const d=U.dialog('Help me choose a destination','A few preferences help us recommend distinct places and explain the trade-offs.');const f=U.form('discovery');d.content.append(f);
    U.field(f,'origin','Where are you travelling from?',{value:profile.residence_country==='IN'?profile.residence_city||'':'',required:true});
    const dates=U.field(f,'date_mode','When would you like to travel?',{options:[['dates','I have exact dates'],['flexible','My dates are flexible']],value:discoveryContext.date_mode||'dates'});
    U.field(f,'start_date','Departure date',{type:'date',min:U.today(),value:discoveryContext.start_date||'',required:true});U.field(f,'end_date','Return date',{type:'date',min:U.today(),value:discoveryContext.end_date||'',required:true});
    U.field(f,'duration_days','Duration (days)',{type:'number',min:1,max:90,value:discoveryContext.duration_days||3});
    const dateMode=()=>{for(const name of ['start_date','end_date']){f.elements[name].disabled=dates.value!=='dates';f.elements[name].closest('label').hidden=dates.value!=='dates';}f.elements.duration_days.disabled=dates.value!=='flexible';f.elements.duration_days.closest('label').hidden=dates.value!=='flexible';};dates.onchange=dateMode;dateMode();
    U.field(f,'total_budget','Comfortable total budget (whole INR)',{type:'number',min:1000,value:discoveryContext.total_budget||25000,help:'Include stay, food, travel, activities and shopping. This is for the whole party.',required:true});
    U.field(f,'trip_type','Trip type',{options:[['solo','Solo'],['couple','Couple'],['friends','Friends'],['family','Family — adults, with or without children']],value:discoveryContext.trip_type||'solo'});
    for(const [key,title,value] of [['adults','Adults',1],['children','Children',0],['seniors','Seniors',0]])U.field(f,key,title,{type:'number',min:key==='adults'?1:0,max:30,value:discoveryContext[key]??value,required:true});
    U.field(f,'mood','What kind of trip feels right?',{options:[['mixed','A mix'],['relaxing','Relaxing'],['adventure','Adventure'],['nature','Nature'],['food','Food'],['culture','Culture']],value:discoveryContext.mood||'mixed'});
    U.field(f,'max_travel_hours','Maximum travel time (hours, optional)',{type:'number',min:0,max:100,value:discoveryContext.max_travel_hours||''});
    U.field(f,'transport','Preferred transport',{options:[['any','Any'],['train','Train'],['flight','Flight'],['road','Road']],value:discoveryContext.transport||'any'});
    U.field(f,'walking_limit_km','Comfortable walking per day (km, optional)',{type:'number',min:0,max:100,value:profile.walking_limit_km||''});
    U.field(f,'accessibility','Accessibility or comfort needs (optional)',{type:'textarea',value:profile.accessibility_needs||'',maxlength:500});
    const submit=U.el('button','Find three places for me','ex-primary');submit.type='submit';submit.disabled=true;f.append(submit);const results=U.el('div',null,'ex-result-grid');d.content.append(results);
    await A.capabilities();submit.disabled=!A.can('discovery');if(!A.can('discovery')){U.unavailable(d.content,'Guided destination discovery is currently unavailable. Your existing personalised recommendations and destination search still work.',async()=>{await A.capabilities(true);submit.disabled=!A.can('discovery');});}
    f.onsubmit=event=>{
      event.preventDefault();const v={...U.values(f),date_mode:dates.value};if(!U.errors(f,A.discoveryErrors(v,U.today())))return;
      const body={...v,origin:v.origin.trim(),total_budget:Number(v.total_budget),party:{adults:Number(v.adults),children:Number(v.children),seniors:Number(v.seniors)},accessibility:v.accessibility.trim(),max_travel_hours:v.max_travel_hours===''?null:Number(v.max_travel_hours),walking_limit_km:v.walking_limit_km===''?null:Number(v.walking_limit_km)};
      delete body.adults;delete body.children;delete body.seniors;
      if(v.date_mode==='flexible'){delete body.start_date;delete body.end_date;body.duration_days=Number(v.duration_days);}else delete body.duration_days;
      const ticket=++requestVersion,key=A.uid();
      U.busy(submit,d.notice,async()=>{
        const response=await A.discover(body);if(ticket!==requestVersion||key!==A.uid()||!d.box.isConnected)return;
        const returned=response.destinations||response.recommendations;if(!Array.isArray(returned))throw new Error('The discovery results could not be read. Please retry.');
        const nextContext={...body,adults:body.party.adults,children:body.party.children,seniors:body.party.seniors};
        if(JSON.stringify(nextContext)!==JSON.stringify(discoveryContext)){compared.clear();drawSelection();}
        discoveryContext=nextContext;results.replaceChildren();
        const choices=returned.filter(item=>!isHome(item)).slice(0,3);
        if(!choices.length){results.append(U.el('p',response.message||'No matches fit these preferences. Increase the travel window, change the budget or choose a different mood.'));f.elements.total_budget.focus();return;}
        if(response.assumptions)d.notice.textContent=texts(response.assumptions).join(' · ');
        for(const item of choices)results.append(card(item,discoveryContext));
        f.dataset.dirty='false';
      });
    };
  }
  async function plan(item,context={}) {
    if(!await U.planningGate())return;
    const d=U.dialog('Use this recommendation in your planner?','The destination will be selected. Your existing form values stay unless you explicitly choose to replace them.');
    d.content.append(U.el('h3',name(item)));U.lines(d.content,'Suggested planning details',[context.origin?'From '+context.origin:'',context.start_date?context.start_date+' – '+context.end_date:context.duration_days?context.duration_days+' days · exact dates undecided':'',context.total_budget?'Whole-party budget '+A.money(context.total_budget):'',context.trip_type?'Trip type: '+context.trip_type:''].filter(Boolean));
    const label=U.el('label');const replace=U.el('input');replace.type='checkbox';label.append(replace,document.createTextNode(' Replace existing dates, party and budget with these suggested values'));d.content.append(label);
    const apply=U.button('Confirm and open planner',()=>{handoff={owner:A.uid(),item,context,replace:replace.checked};d.box.close();if(location.hash==='#/trips/new')window.TripExperience.route();else location.hash='/trips/new';},'ex-primary');d.actions.prepend(apply);
  }
  window.addEventListener('trip:creation-ready',async()=>{
    if(!handoff||handoff.owner!==A.uid())return;const choice=handoff;handoff=null;
    const select=document.getElementById('tripDestSelect'),item=choice.item,id=canonicalId(item);if(!id)return;
    if(![...select.options].some(o=>o.value===id))select.add(new Option(name(item),id));select.value=id;
    if(id.startsWith('geo_')&&Number.isFinite(Number(item.latitude??item.lat))&&Number.isFinite(Number(item.longitude??item.lon))){selectedDynamicLocation={...item,name:name(item),city:item.city||name(item),lat:Number(item.latitude??item.lat),lon:Number(item.longitude??item.lon)};}
    else await window.handleFeaturedDestinationChange?.(id);
    if(choice.owner!==A.uid()||location.hash!=='#/trips/new')return;
    const v=choice.context,map={origin:'tripDepartureInput',start_date:'tripStartDateInput',end_date:'tripEndDateInput',total_budget:'tripBudgetInput',trip_type:'teTripType',adults:'tripAdultsInput',children:'tripChildrenInput',seniors:'tripSeniorsInput'};
    for(const [key,field] of Object.entries(map)){const input=document.getElementById(field);if(input&&v[key]!==undefined&&(choice.replace||!input.value))input.value=v[key];}
    if(choice.replace)window.syncTripPartyFromCounts?.();document.getElementById('tripCreateForm').dispatchEvent(new Event('input',{bubbles:true}));
    const note=U.el('p',choice.replace?'Suggested dates, party and budget were transferred. Review every field before creating your trip.':'Destination selected. Existing dates, party and budget were kept.','ex-note');document.getElementById('teFormError')?.before(note);select.dispatchEvent(new Event('change',{bubbles:true}));
  });
  async function loadShelves() {
    checkOwner();if(!A.uid())return;const account=A.uid();await A.capabilities();if(account!==A.uid()||!A.can('discovery'))return;
    try{const response=await A.request('/api/discovery/recommendations');if(account!==A.uid())return;shelves.replaceChildren();
      const groups=Array.isArray(response.groups)?response.groups:[];
      for(const group of groups){const entries=(group.destinations||group.items||[]).filter(item=>!isHome(item));if(!entries.length)continue;const section=U.el('section');section.append(U.el('h3',A.text(group.title)));const grid=U.el('div',null,'ex-result-grid');for(const item of entries)grid.append(card(item,{}));section.append(grid);shelves.append(section);}
    }catch(error){if(account===A.uid())U.unavailable(shelves,error.message,loadShelves);}
  }
  new MutationObserver(()=>{const visible=!document.getElementById('dashboardView').classList.contains('hidden');if(visible&&owner!==A.uid()){checkOwner();loadShelves();}}).observe(document.getElementById('dashboardView'),{attributes:true,attributeFilter:['class']});
  window.addEventListener('experience:recommendation-feedback',()=>{loadShelves();window.loadRecommendations?.(true);});
  window.addEventListener('load',loadShelves);
  window.addEventListener('trip:context-cleared',()=>{owner=A.uid();compared.clear();items.clear();selection.hidden=true;selection.replaceChildren();shelves.replaceChildren();discoveryContext={};handoff=null;});
  window.RecommendationDiscovery={open:openDiscovery,compare:compareDestinations,plan,refresh:loadShelves,addComparison};
})();
