/* A: profile fields, global navigation and discovery presentation. */
(() => {
  'use strict';
  const form = document.getElementById('profileForm');
  const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const gender = document.getElementById('basicGender');
  const daily = document.getElementById('basicDailyBudget');
  const setError = (id, message) => {
    const field = document.getElementById(id);
    const error = document.getElementById(id + 'Error');
    if (error) error.textContent = message || '';
    if (field) field.setAttribute('aria-invalid', String(!!message));
  };
  function syncFields(profile) {
    const data = profile || (typeof state !== 'undefined' ? state.basicAnswers : {}) || {};
    if (gender && data.gender) gender.value = data.gender;
    if (daily && data.daily_budget_inr != null) daily.value = String(data.daily_budget_inr);
  }
  if (typeof window.renderBasicForm === 'function') {
    const render = window.renderBasicForm;
    window.renderBasicForm = function (...args) { const result = render.apply(this, args); syncFields(); return result; };
  }
  window.addEventListener('load', () => {
    const tripApi=window.TripExperience;
    if(tripApi?.isHomeDestination&&!tripApi.isHomeDestination.__profileHomeAware){
      const originalHomeCheck=tripApi.isHomeDestination;
      const homeAware=function(item,profile){
        profile=profile||(typeof state!=='undefined'?state.currentProfile:null)||{};
        const normal=value=>String(value||'').normalize('NFKC').toLocaleLowerCase().replace(/[^\p{L}\p{N}]+/gu,' ').trim();
        const destinationCountry=normal(item?.country||item?.destination_country);
        const homeCountry=normal(profile.residence_country_name||profile.residence_country);
        if(profile.residence_city&&destinationCountry&&homeCountry&&destinationCountry===homeCountry){
          const home=normal(profile.residence_city);
          if([item?.city,item?.name,item?.destination_name].some(value=>` ${normal(value)} `.includes(` ${home} `)))return true;
        }
        return originalHomeCheck(item,profile);
      };
      homeAware.__profileHomeAware=true;tripApi.isHomeDestination=homeAware;
    }
    const original = window.renderRecommendationCard;
    if (typeof original !== 'function') return;
    window.renderRecommendationCard = function (item, category) {
      const fallback='/static/images/destination-placeholder.svg';
      let source=typeof item.image_url==='string'?item.image_url.trim():'';
      try {
        const parsed=new URL(source,location.origin);
        if(!['https:','http:'].includes(parsed.protocol)||(location.protocol==='https:'&&parsed.protocol==='http:'))source='';
        else source=parsed.href;
      } catch (_) { source=''; }
      const safeItem={...item,
        name:escapeHTML(item.name||'Destination'),
        country:escapeHTML(item.country||'India'),
        duration:escapeHTML(item.duration||'4–6 days'),
        seasonal_timing:escapeHTML(item.seasonal_timing||'Seasonal'),
        image_url:source||fallback,
        tags:(Array.isArray(item.tags)?item.tags:[]).map(escapeHTML)
      };
      const card = original.call(this, safeItem, category);
      const image = card.querySelector('img');
      if (image) {
        image.alt = 'Photo of ' + String(item.name || 'destination');
        image.loading = 'lazy'; image.decoding = 'async';
        image.onerror = () => { image.onerror = null; image.src = fallback; };
        image.src = safeItem.image_url;
      }
      const title = card.querySelector('.absolute.bottom-2\\.5 h4');
      const country = card.querySelector('.absolute.bottom-2\\.5 span');
      if (title) title.textContent = String(item.name || 'Destination');
      if (country) country.textContent = String(item.country || 'India');
      return card;
    };
  }, {once:true});
  if (form) {
    form.addEventListener('input', event => {
      if (event.target === gender) { state.basicAnswers.gender = gender.value || null; setError('basicGender', ''); }
      if (event.target === daily) { state.basicAnswers.daily_budget_inr = daily.value; setError('basicDailyBudget', ''); }
    }, true);
    form.addEventListener('submit', event => {
      const amountText = daily?.value.trim() || '';
      const amount = /^\d{1,7}$/.test(amountText) ? Number(amountText) : NaN;
      const genderError = ['female', 'male', 'other'].includes(gender?.value) ? '' : 'Choose female, male or other.';
      const budgetError = Number.isSafeInteger(amount) && amount >= 1 && amount <= 1000000
        ? '' : 'Enter a positive whole-rupee amount from ₹1 to ₹10,00,000.';
      setError('basicGender', genderError); setError('basicDailyBudget', budgetError);
      if (genderError || budgetError) {
        event.preventDefault(); event.stopImmediatePropagation();
        const target = genderError ? gender : daily;
        if (target) { target.focus(); target.scrollIntoView({block: 'center', behavior: 'smooth'}); }
        return;
      }
      state.basicAnswers.gender = gender.value;
      state.basicAnswers.daily_budget_inr = amount;
    }, true);
    syncFields();
  }

  const budgetInput = document.getElementById('tripBudgetInput');
  let recommendationHandoff = false;
  function fillSuggestedTripBudget() {
    if (!budgetInput || budgetInput.value.trim()) return;
    const dailyAmount = Number(state.currentProfile?.daily_budget_inr);
    if (!Number.isSafeInteger(dailyAmount) || dailyAmount < 1 || dailyAmount > 1000000) return;
    const adults = Number(document.getElementById('tripAdultsInput')?.value || 1);
    const children = Number(document.getElementById('tripChildrenInput')?.value || 0);
    const seniors = Number(document.getElementById('tripSeniorsInput')?.value || 0);
    const partySize = Math.max(1, adults + children + seniors);
    const start = document.getElementById('tripStartDateInput')?.value;
    const end = document.getElementById('tripEndDateInput')?.value;
    const dates = start && end ? [Date.parse(start+'T00:00:00Z'),Date.parse(end+'T00:00:00Z')] : [];
    const days = dates.length && dates.every(Number.isFinite) && dates[1] >= dates[0] ? Math.round((dates[1]-dates[0])/86400000)+1 : 3;
    budgetInput.value = String(Math.min(1000000, dailyAmount * partySize * days));
    window.onBudgetNumberInputChange?.(budgetInput.value);
  }
  window.addEventListener('trip:recommendation-handoff-start', () => { recommendationHandoff = true; });
  window.addEventListener('trip:creation-ready', () => { if (!recommendationHandoff) setTimeout(fillSuggestedTripBudget, 80); });
  window.addEventListener('trip:recommendation-prefill-applied', () => { recommendationHandoff = false; fillSuggestedTripBudget(); });
  window.addEventListener('trip:context-cleared', () => { recommendationHandoff = false; });

  // Keep the account-owned Home value understandable to international visitors.
  const openAccount = window.openAccountProfile;
  if (typeof openAccount === 'function') window.openAccountProfile = function (...args) {
    const result = openAccount.apply(this, args);
    const profile = state.currentProfile || {};
    const box = document.getElementById('accountProfileDialog');
    const firstValue = box?.querySelector('.grid > div:first-child strong');
    if (firstValue && profile.residence_country && profile.residence_country !== 'IN') {
      firstValue.textContent = profile.residence_country_name || profile.residence_country;
    }
    if (box && profile.gender) {
      const details=box.querySelector('.grid');
      if(details&&!details.querySelector('[data-profile-gender]')){
        const item=document.createElement('div');item.className='rounded-xl bg-slate-50 border border-slate-100 p-3';
        const label=document.createElement('small');label.className='block text-slate-500';label.textContent='Gender';
        const value=document.createElement('strong');value.className='text-slate-800';value.dataset.profileGender='true';value.textContent=profile.gender.charAt(0).toUpperCase()+profile.gender.slice(1);item.append(label,value);details.append(item);
      }
    }
    if (box && Number.isSafeInteger(profile.daily_budget_inr)) {
      const details=box.querySelector('.grid');
      if(details&&!details.querySelector('[data-daily-budget]')){
        const item=document.createElement('div');item.className='rounded-xl bg-slate-50 border border-slate-100 p-3';
        const label=document.createElement('small');label.className='block text-slate-500';label.textContent='Usual per person/day';
        const value=document.createElement('strong');value.className='text-slate-800';value.dataset.dailyBudget='true';value.textContent='₹'+profile.daily_budget_inr.toLocaleString('en-IN');item.append(label,value);details.append(item);
      }
    }
    return result;
  };

  // Remove the two legacy navigation controls without removing their still-used routes/modal.
  function cleanNavigation() {
    document.querySelector('a.app-nav-link[href="#/"]')?.remove();
    for (const button of document.querySelectorAll('button[onclick*="infoModal"]')) button.remove();
    document.querySelectorAll('details.ex-more-destinations').forEach(node => { node.open = true; });
    const headings=document.querySelectorAll('#recommendationsSection h3');
    for(const heading of headings){
      if(heading.textContent.trim()==='Trending Destinations')heading.textContent='More destinations for your profile';
      if(heading.textContent.trim()==='Seasonal & Upcoming Experiences')heading.textContent='Coming up in India';
    }
    const seasonalLabel=[...document.querySelectorAll('#recommendationsSection span')].find(node=>node.textContent.trim()==='Timed to upcoming seasons, weather & local events');
    if(seasonalLabel)seasonalLabel.textContent='Catalogue season windows; confirm event dates and local conditions.';
    const trendLabel=[...document.querySelectorAll('#recommendationsSection span')].find(node=>node.textContent.trim()==='Popular destinations with great feedback right now');
    if(trendLabel)trendLabel.textContent='Additional destinations selected around your travel profile.';
    const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
    let node;while((node=walker.nextNode())){
      if(/linucb|thompson sampling|reinforcement learning|contextual bandit/i.test(node.nodeValue))
        node.nodeValue=node.nodeValue.replace(/LinUCB|Thompson Sampling|contextual bandit/gi,'travel recommendation system').replace(/Reinforcement Learning/gi,'personalised travel').replace(/bandit/gi,'recommendation system');
    }
  }
  cleanNavigation();
  new MutationObserver(cleanNavigation).observe(document.body, {childList: true, subtree: true});

  // Keep Active trips compact while retaining their open/resume link.
  function compactTrips() {
    const list = document.getElementById('teTripList');
    if (!list) return;
    for (const section of list.querySelectorAll('section')) {
      if (section.querySelector('h3')?.textContent.trim() !== 'Active trips') continue;
      section.querySelectorAll('.te-list-row small').forEach(node => node.remove());
    }
  }
  const tripList = document.getElementById('teTripList');
  if (tripList) new MutationObserver(compactTrips).observe(tripList, {childList: true, subtree: true});
  compactTrips();

  const style = document.createElement('style');
  style.textContent = '#exDiscovery{margin-bottom:2rem}#exRecommendationShelves>section{margin-top:2rem;padding-top:1.5rem;border-top:1px solid #e2e8f0}#exRecommendationShelves>section:first-child{margin-top:1.75rem}#exDiscoveryLayout .ex-more-destinations{display:block;margin-top:2rem}#exDiscoveryLayout .ex-more-destinations>summary{display:none}.ex-destination-photo{display:block;width:100%;height:10rem;object-fit:cover;background:#f1f5f9;border-radius:.85rem;margin-bottom:.85rem}.ex-coming-up-focus{outline:3px solid #a5b4fc;outline-offset:4px;border-radius:1rem}';
  document.head.append(style);
})();
/* end A: profile fields, global navigation and discovery presentation. */
