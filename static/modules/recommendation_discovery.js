/* E: recommendation feedback and guided destination discovery. */
(() => {
  'use strict';
  const A=window.ExperienceAPI,U=window.ExperienceUI;
  if(!A||!U||typeof document==='undefined')return;
  const root=document.getElementById('recommendationsSection');if(!root)return;
  const items=new Map();let owner=null,discoveryContext={},requestVersion=0,handoff=null;
  let shelfRevision=0,shelfUsesPersonalContext=false;
  const layout=U.el('div',null,'ex-discovery-layout');layout.id='exDiscoveryLayout';layout.dataset.hasSaved='false';
  const mainColumn=U.el('div',null,'ex-discovery-main');mainColumn.id='exDiscoveryMain';
  const savedAside=U.el('aside',null,'ex-saved-places');savedAside.id='exSavedPlaces';savedAside.hidden=true;savedAside.setAttribute('aria-labelledby','exSavedPlacesHeading');
  root.before(layout);layout.append(mainColumn,savedAside);mainColumn.append(root);
  const entry=U.el('section',null,'ex-discovery');entry.id='exDiscovery';
  entry.append(U.el('h2','Where will you go next?'),U.el('p','Discover places that fit you, then turn a favourite into a trip.','ex-muted'));
  const actions=U.el('div',null,'ex-entry-actions');
  const comingUp=U.button('Coming Up Next',()=>{
    const target=[...shelves.querySelectorAll('section')].find(section=>section.querySelector('h3')?.textContent.toLowerCase().includes('seasonal'))||mainColumn.querySelector('#seasonalGrid');
    if(target){target.scrollIntoView({behavior:'smooth',block:'start'});target.classList.add('ex-coming-up-focus');setTimeout(()=>target.classList.remove('ex-coming-up-focus'),1800);}
    else openDiscovery();
  },'ex-primary');
  actions.append(comingUp,U.button('Help me choose',()=>openDiscovery()),U.button('Explore my budget',()=>window.BudgetExperience?.openOptions()));entry.append(actions);
  const shelves=U.el('div');shelves.id='exRecommendationShelves';entry.append(shelves);mainColumn.prepend(entry);
  const moreDestinations=U.el('details',null,'ex-more-destinations');moreDestinations.open=true;moreDestinations.append(U.el('summary','More destinations & seasonal ideas'));mainColumn.append(moreDestinations);moreDestinations.append(root);
  moreDestinations.addEventListener('toggle',()=>{if(!moreDestinations.open)moreDestinations.open=true;});
  const notice=U.status(entry);
  const savedState=U.el('div',null,'ex-saved-state');savedState.hidden=true;savedState.setAttribute('role','status');savedState.setAttribute('aria-live','polite');entry.append(savedState);
  const isHome=item=>window.TripExperience?.isHomeDestination(item);
  const canonicalId=item=>item.destination_id||item.id;
  const name=item=>item.name||item.destination_name||'Destination';
  const headingText=value=>({
    'within your budget':'Within your budget',
    'recommended for you':'Recommended for you',
    'selected for your profile':'Selected for your profile',
    'trending destinations':'Popular in our destination guide',
    'seasonal & upcoming experiences':'Seasonal ideas for the coming months'
  })[String(value||'').trim().toLocaleLowerCase()]||String(value||'').trim().replace(/^\p{L}/u,letter=>letter.toLocaleUpperCase());
  const texts=value=>Array.isArray(value)?value.map(v=>typeof v==='string'?v:v.message||v.text||'').filter(Boolean):typeof value==='string'?[value]:[];
  const reasons=item=>texts(item.reasons||item.why_recommended||item.why_recommended_for_you||item.explanation||item.because_you_said||item.why_it_suits).map(value=>A.text(value).replace(/\s*\(Q\d+\)/gi,'').replace(/_/g,' '));
  function checkOwner(){if(owner!==A.uid()){owner=A.uid();shelfRevision++;items.clear();discoveryContext={};shelfUsesPersonalContext=false;shelves.replaceChildren();savedAside.replaceChildren();savedAside.hidden=true;layout.dataset.hasSaved='false';savedState.hidden=true;handoff=null;}}
  function register(item){checkOwner();const id=canonicalId(item);if(typeof id!=='string'||isHome(item))return null;const known=items.get(id);if(typeof item.is_shortlisted!=='boolean'&&typeof known?.is_shortlisted==='boolean')item.is_shortlisted=known.is_shortlisted;items.set(id,item);return id;}
  function feedbackControls(item,parent,context={}) {
    const id=register(item);if(!id)return;
    const bar=U.el('div',null,'ex-actions ex-feedback-actions'),message=U.status(parent);
    const send=async(action,reason,control)=>U.busy(control,message,async()=>{
      if(!await window.ProfileGate.require())return;await A.capabilities();
      const result=await A.feedback({destination_id:id,action,reason:reason||null,context});
      if(owner!==A.uid())return;
      message.textContent=result.message||'Preference saved. Refresh suggestions to see updated choices.';
      control.setAttribute('aria-pressed','true');
      window.dispatchEvent(new CustomEvent('experience:recommendation-feedback',{detail:{destinationId:id,action}}));
    });
    for(const [value,title] of [['interested','Interested']]){const b=U.button(title,()=>send(value,null,b));bar.append(b);}
    const reject=U.button('Not for me',()=>{
      const d=U.dialog('What would make this a better suggestion?','Your answer helps refine future recommendations.');
      for(const [reason,title] of [['too_expensive','Too expensive'],['too_far','Too far'],['too_crowded','Too crowded'],['wrong_activity_type','Wrong activity type'],['not_interested','Not interested']]){
        const b=U.button(title,()=>U.busy(b,d.notice,async()=>{await A.capabilities();const result=await A.feedback({destination_id:id,action:'not_for_me',reason,context});message.textContent=result.message||'Preference saved.';d.box.close();}));d.content.append(b);
      }
    });bar.append(reject);
    const extra=U.el('details',null,'ex-feedback-more');extra.append(U.el('summary','More feedback options'));const extraActions=U.el('div',null,'ex-actions');for(const [value,title] of [['already_visited','Already visited'],['more_like_this','More like this'],['closer_to_home','Closer to home'],['too_expensive','Too expensive']]){const b=U.button(title,()=>send(value,null,b));extraActions.append(b);}extra.append(extraActions);bar.append(extra);
    parent.append(bar);
    A.capabilities().then(()=>{if(!parent.isConnected)return;bar.querySelectorAll('button').forEach(b=>{b.disabled=!A.can('discovery');if(b.disabled)b.title='Preference refinement is temporarily unavailable. Explore and plan controls still work.';});});
  }
  const rawCard=window.renderRecommendationCard;
  if(typeof rawCard==='function')window.renderRecommendationCard=function(item,category){
    const card=rawCard(item,category);register(item);
    if(category==='trending'){
      const badge=[...card.querySelectorAll('span')].find(node=>node.textContent.trim()==='Trending now');
      if(badge)badge.textContent='Popular in our destination guide';
    }
    const explanation=U.el('div',null,'ex-card-explanation');
    if(!item.because_you_said&&!item.why_it_suits)U.lines(explanation,'Why this place?',reasons(item).slice(0,2));
    const downside=item.tradeoff||item.trade_off||item.drawback;if(downside)explanation.append(U.el('p','Trade-off: '+A.text(downside),'ex-muted'));
    const target=U.el('div',null,'destination-card-feedback');
    if(explanation.childElementCount)target.append(explanation);
    feedbackControls(item,target,{});card.append(target);return card;
  };
  function card(item,context={},savedOnly=false) {
    register(item);const box=U.el('article',null,'ex-destination-card');
    const photo=U.el('img');photo.className='ex-destination-photo';photo.alt='Photo of '+name(item);photo.loading='lazy';photo.decoding='async';
    const fallback='/static/images/destination-placeholder.svg';
    let imageUrl=typeof item.image_url==='string'&&item.image_url.trim()?item.image_url.trim():fallback;
    try{const parsed=new URL(imageUrl,location.origin);if(!['https:','http:'].includes(parsed.protocol)||(parsed.protocol==='http:'&&location.protocol==='https:'))imageUrl='';else imageUrl=parsed.href;}catch(_){imageUrl='';}
    photo.src=imageUrl||fallback;photo.onerror=()=>{photo.onerror=null;photo.src=fallback;};
    box.append(photo,U.el('h3',name(item)));
    if(typeof item.image_source_url==='string'&&item.image_source_url.startsWith('https://en.wikipedia.org/wiki/')){
      const credit=U.el('a','Photo source','ex-muted');credit.href=item.image_source_url;credit.target='_blank';credit.rel='noopener noreferrer';box.append(credit);
    }
    if(!savedOnly){
    box.append(U.el('strong',window.TripExperience.matchLabel(item)));
    U.lines(box,'Why this fits',reasons(item));
    box.append(U.el('p','Estimated full-trip cost: '+A.money(item.estimated_total_inr??item.total_cost_inr)),U.el('p','Travel time: '+(item.travel_time_label||'Not available')));
    const drawback=item.tradeoff||item.drawback;box.append(U.el('p',drawback?'Trade-off: '+A.text(drawback):'Trade-off information is not available.','ex-muted'));
    if(item.estimate_note){const details=U.el('details',null,'ex-estimate-details');details.append(U.el('summary','Estimate details'),U.el('p',A.text(item.estimate_note),'ex-muted'));box.append(details);}U.safeLinks(box,item.sources);
    }
    const actionBar=U.el('div',null,'ex-actions');
    actionBar.append(U.button('Explore',()=>explore(item,context)),U.button('Plan this trip',()=>plan(item,context),'ex-primary'));
    box.append(actionBar);feedbackControls(item,box,context);return box;
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
  async function openDiscovery() {
    if(!await window.ProfileGate.require())return;checkOwner();
    const profile=typeof state!=='undefined'?state.currentProfile||{}:{};
    const d=U.dialog('Help me choose a destination','A few preferences help us recommend distinct places and explain the trade-offs.');const f=U.form('discovery');d.content.append(f);
    U.field(f,'origin','Where are you travelling from?',{value:profile.residence_country==='IN'?profile.residence_city||'':'',required:true});
    const dates=U.field(f,'date_mode','When would you like to travel?',{options:[['dates','I have exact dates'],['flexible','My dates are flexible']],value:discoveryContext.date_mode||'dates'});
    U.field(f,'start_date','Departure date',{type:'date',min:U.today(),value:discoveryContext.start_date||'',required:true});U.field(f,'end_date','Return date',{type:'date',min:U.today(),value:discoveryContext.end_date||'',required:true});
    U.field(f,'duration_days','Duration (days)',{type:'number',min:1,max:90,value:discoveryContext.duration_days||3});
    const dateMode=()=>{for(const name of ['start_date','end_date']){f.elements[name].disabled=dates.value!=='dates';f.elements[name].closest('label').hidden=dates.value!=='dates';}f.elements.duration_days.disabled=dates.value!=='flexible';f.elements.duration_days.closest('label').hidden=dates.value!=='flexible';};dates.onchange=dateMode;dateMode();
    const companion=String(profile.companions||'').toLowerCase();const defaultParty=({alone:1,solo:1,partner:2,friends:2,family_kids:3,family_children:3,family_seniors:3})[companion]||1;
    const defaultTripType=({alone:'solo',solo:'solo',partner:'couple',friends:'friends',family_kids:'family',family_children:'family',family_seniors:'family'})[companion]||'solo';
    const suggestedParty=Number(discoveryContext.party_size)||Number(discoveryContext.adults||0)+Number(discoveryContext.children||0)+Number(discoveryContext.seniors||0)||defaultParty;
    const suggestedDays=discoveryContext.start_date&&discoveryContext.end_date?Math.max(1,Math.round((Date.parse(discoveryContext.end_date+'T00:00:00Z')-Date.parse(discoveryContext.start_date+'T00:00:00Z'))/86400000)+1):Number(discoveryContext.duration_days)||3;
    const profileSuggestedBudget=Number.isInteger(Number(profile.daily_budget_inr))?Math.min(1000000,Number(profile.daily_budget_inr)*suggestedDays*suggestedParty):'';
    U.field(f,'total_budget','Comfortable total budget (whole INR)',{type:'number',min:1000,max:1000000,value:discoveryContext.total_budget||profileSuggestedBudget||'',help:profileSuggestedBudget?`Suggested from ₹${Number(profile.daily_budget_inr).toLocaleString('en-IN')} per person/day × ${suggestedParty} traveller(s) × ${suggestedDays} days. Edit this whole-party amount for this trip.`:'Enter a whole-party budget for this trip. Add a daily budget in your profile to prefill this next time.',required:true});
    U.field(f,'trip_type','Trip type',{options:[['solo','Solo'],['couple','Couple'],['friends','Friends'],['family','Family — adults, with or without children']],value:discoveryContext.trip_type||defaultTripType});
    for(const [key,title,value] of [['adults','Adults',defaultParty],['children','Children',0],['seniors','Seniors',0]])U.field(f,key,title,{type:'number',min:key==='adults'?1:0,max:30,value:discoveryContext[key]??value,required:true});
    U.field(f,'mood','What kind of trip feels right?',{options:[['mixed','A mix'],['relaxing','Relaxing'],['adventure','Adventure'],['nature','Nature'],['food','Food'],['culture','Culture']],value:discoveryContext.mood||'mixed'});
    U.field(f,'max_travel_hours','Maximum travel time (hours, optional)',{type:'number',min:0.1,max:24,value:discoveryContext.max_travel_hours||''});
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
        discoveryContext=nextContext;results.replaceChildren();
        let choices=returned.filter(item=>!isHome(item)).slice(0,3);
        if(!choices.length){
          const shelfResponse=await A.shelves(discoveryContext);
          if(ticket!==requestVersion||key!==A.uid()||!d.box.isConnected)return;
          const shelfItems=(shelfResponse.groups||[]).flatMap(group=>group.destinations||group.items||[]);
          choices=shelfItems.filter(item=>!isHome(item)).slice(0,3);
        }
        if(!choices.length){results.append(U.el('p','No places matched these trip preferences. Recommendations behind this window are based on your saved profile and may not match this search. Try a wider date window, a different budget or another trip style.'));f.elements.total_budget.focus();return;}
        if(response.assumptions)d.notice.textContent=texts(response.assumptions).join(' · ');
        for(const item of choices)results.append(card(item,discoveryContext));
        f.dataset.dirty='false';
      });
    };
  }
  async function plan(item,context={}) {
    if(!await U.planningGate())return;
    const d=U.dialog('Use this recommendation in your planner?','The destination will be selected. Your search preferences will be carried into this trip.');
    d.content.append(U.el('h3',name(item)));U.lines(d.content,'Suggested planning details',[context.origin?'From '+context.origin:'',context.start_date?context.start_date+' – '+context.end_date:context.duration_days?context.duration_days+' days · exact dates undecided':'',context.total_budget?'Whole-party budget '+A.money(context.total_budget):'',context.trip_type?'Trip type: '+context.trip_type:''].filter(Boolean));
    const label=U.el('label');const replace=U.el('input');replace.type='checkbox';replace.checked=true;replace.disabled=true;label.append(replace,document.createTextNode(' Use these search preferences in the planner'));d.content.append(label);
    const apply=U.button('Confirm and open planner',()=>{window.dispatchEvent(new Event('trip:recommendation-handoff-start'));handoff={owner:A.uid(),item,context,replace:true};d.box.close();if(location.hash==='#/trips/new')window.TripExperience.route();else location.hash='/trips/new';},'ex-primary');d.actions.prepend(apply);
  }
  window.addEventListener('trip:creation-ready',async()=>{
    if(!handoff||handoff.owner!==A.uid())return;const choice=handoff;handoff=null;
    const select=document.getElementById('tripDestSelect'),item=choice.item,id=canonicalId(item);if(!id)return;
    if(![...select.options].some(o=>o.value===id))select.add(new Option(name(item),id));select.value=id;
    if(id.startsWith('geo_')&&Number.isFinite(Number(item.latitude??item.lat))&&Number.isFinite(Number(item.longitude??item.lon))){selectedDynamicLocation={...item,name:name(item),city:item.city||name(item),lat:Number(item.latitude??item.lat),lon:Number(item.longitude??item.lon)};}
    else await window.handleFeaturedDestinationChange?.(id);
    if(choice.owner!==A.uid()||location.hash!=='#/trips/new')return;
    const v=choice.context;
    if(v.transport&&v.transport!=='any'){const journey=document.getElementById('teJourneyMode');if(journey)journey.value=v.transport==='road'?'car':v.transport;}
    if(v.duration_days&&!v.end_date){const start=document.getElementById('tripStartDateInput').value;if(start){const end=new Date(start+'T12:00:00Z');end.setUTCDate(end.getUTCDate()+Number(v.duration_days)-1);document.getElementById('tripEndDateInput').value=end.toISOString().slice(0,10);}}
    const map={origin:'tripDepartureInput',start_date:'tripStartDateInput',end_date:'tripEndDateInput',total_budget:'tripBudgetInput',trip_type:'teTripType',adults:'tripAdultsInput',children:'tripChildrenInput',seniors:'tripSeniorsInput'};
    for(const [key,field] of Object.entries(map)){const input=document.getElementById(field);if(input&&v[key]!==undefined&&(choice.replace||!input.value))input.value=v[key];}
    if(choice.replace)window.syncTripPartyFromCounts?.();
    document.getElementById('tripEndDateInput').min=document.getElementById('tripStartDateInput').value||U.today();
    for(const field of ['tripStartDateInput','tripEndDateInput'])document.getElementById(field)?.dispatchEvent(new Event('input',{bubbles:true}));document.getElementById('tripCreateForm').dispatchEvent(new Event('input',{bubbles:true}));
    const note=U.el('p',choice.replace?'Suggested dates, party and budget were transferred. Review every field before creating your trip.':'Destination selected. Existing dates, party and budget were kept.','ex-note');document.getElementById('teFormError')?.before(note);
    const destinationSearch=document.getElementById('tripCitySearchInput');
    if(destinationSearch){destinationSearch.value=name(item);document.getElementById('tripCityClearBtn')?.classList.remove('hidden');}
    window.dispatchEvent(new Event('trip:recommendation-prefill-applied'));
  });
  async function loadShelves() {
    checkOwner();if(!A.uid())return;
    const account=A.uid(),revision=++shelfRevision;
    savedState.replaceChildren(U.el('span','Loading saved places…'));savedState.hidden=false;
    await A.capabilities();
    if(account!==A.uid()||revision!==shelfRevision)return;
    const savedTask=A.savedPlaces();
    const shelvesTask=A.can('discovery')?A.shelves(discoveryContext):Promise.resolve(null);
    const [savedResult,shelvesResult]=await Promise.allSettled([savedTask,shelvesTask]);
    if(account!==A.uid()||revision!==shelfRevision)return;

    if(savedResult.status==='fulfilled'&&Array.isArray(savedResult.value.destinations)){
      const destinations=savedResult.value.destinations.filter(item=>typeof canonicalId(item)==='string'&&canonicalId(item));
      savedState.hidden=true;savedState.replaceChildren();savedAside.replaceChildren();
      layout.dataset.hasSaved=String(destinations.length>0);
      if(destinations.length){
        const heading=U.el('h2','Saved places');heading.id='exSavedPlacesHeading';
        const grid=U.el('div',null,'ex-result-grid');
        for(const item of destinations)grid.append(card(item,{},true));
        savedAside.append(heading,grid);savedAside.hidden=false;
      }else savedAside.hidden=true;
    }else{
      savedAside.replaceChildren();savedAside.hidden=true;layout.dataset.hasSaved='false';
      savedState.replaceChildren(U.el('span','Saved places could not be checked. Your saved list has not been changed.'),U.button('Retry',loadShelves));savedState.hidden=false;
    }

    shelves.replaceChildren();
    if(shelvesResult.status==='fulfilled'&&shelvesResult.value){
      const response=shelvesResult.value;
      shelfUsesPersonalContext=response.personalized_context===true;
      if(response.sample_context)shelves.append(U.el('p',response.sample_context,'ex-muted'));
      shelves.append(U.el('p','Trip costs are indicative estimates with a contingency allowance; lodging and travel prices are not confirmed quotes.','ex-muted'));
      if((response.groups||[]).some(group=>String(group.title||'').toLowerCase().includes('seasonal')))shelves.append(U.el('p','Seasonal windows come from the destination guide; confirm festival dates and local conditions before booking.','ex-muted'));
      const groups=Array.isArray(response.groups)?response.groups:[];
      const shown=new Set();for(const group of groups){const entries=(group.destinations||group.items||[]).filter(item=>{const id=canonicalId(item);if(isHome(item)||shown.has(id))return false;shown.add(id);return true;});if(!entries.length)continue;const section=U.el('section');section.append(U.el('h3',headingText(A.text(group.title))));const grid=U.el('div',null,'ex-result-grid');for(const item of entries)grid.append(card(item,discoveryContext));section.append(grid);shelves.append(section);}
    }else if(A.can('discovery')){
      moreDestinations.open=true;U.unavailable(shelves,shelvesResult.reason?.message||'Recommendations could not be loaded. Please retry.',loadShelves);
    }else moreDestinations.open=true;
  }
  new MutationObserver(()=>{const visible=!document.getElementById('dashboardView').classList.contains('hidden');if(visible&&owner!==A.uid()){checkOwner();loadShelves();}}).observe(document.getElementById('dashboardView'),{attributes:true,attributeFilter:['class']});
  const oldNavUpdate=window.updateNavUser;
  if(typeof oldNavUpdate==='function')window.updateNavUser=function(...args){const result=oldNavUpdate.apply(this,args);if(owner!==A.uid()){checkOwner();if(!document.getElementById('dashboardView').classList.contains('hidden'))loadShelves();}return result;};
  window.addEventListener('experience:recommendation-feedback',()=>{loadShelves();window.loadRecommendations?.(true);});
  window.addEventListener('load',loadShelves);
  window.addEventListener('trip:context-cleared',()=>{owner=A.uid();shelfRevision++;items.clear();shelves.replaceChildren();savedAside.replaceChildren();savedAside.hidden=true;savedState.replaceChildren();savedState.hidden=true;layout.dataset.hasSaved='false';discoveryContext={};shelfUsesPersonalContext=false;handoff=null;});
  window.RecommendationDiscovery={open:openDiscovery,plan,refresh:loadShelves};
})();
