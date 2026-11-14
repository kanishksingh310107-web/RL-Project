/* A: country-first residence and optional reference-currency display. */
(() => {
  const el = id => document.getElementById(id);
  let metadata, metadataRequest;
  async function options() {
    if (metadata) return metadata;
    if (!metadataRequest) metadataRequest = (async () => {
      const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),8000);
      try {
        const response = await fetch('/api/config/residence',{signal:controller.signal});
        if (!response.ok) throw new Error('Country choices unavailable');
        const data=await response.json();
        if(!Array.isArray(data.countries) || !Array.isArray(data.currencies) || !Array.isArray(data.indian_states))throw new Error('Country choices unavailable');
        metadata=data;
        return metadata;
      } catch (_) { throw new Error('Country choices could not be loaded. Please retry.'); }
      finally { clearTimeout(timer); }
    })().finally(() => { metadataRequest = null; });
    return metadataRequest;
  }
  function message(id, text) { const node = el(id+'Error'); if (node) node.textContent = text; }
  function fillSelect(select, rows, placeholder) {
    select.replaceChildren(new Option(placeholder, ''));
    rows.forEach(row => select.add(new Option(row.label, row.value)));
  }
  function countryChanged(reset = true) {
    const country = el('residenceCountry').value;
    const india = country === 'IN';
    el('residenceIndiaFields').classList.toggle('hidden', !india);
    el('residenceCurrencyFields').classList.toggle('hidden', !country || india);
    for (const id of ['residenceState','residenceCity']) {
      el(id).required = india; el(id).disabled = !india;
      if (reset || !india) el(id).value = '';
      message(id, '');
    }
    const preferred = el('preferredCurrency');
    if (reset) preferred.value = india ? 'INR' : (metadata?.countries.find(row => row.code===country)?.currencies[0] || 'USD');
    preferred.required = Boolean(country && !india);
    updateCityField();
    message('residenceCountry','');
    Object.assign(state.basicAnswers, read(false) || {});
  }
  function updateCityField() {
    const visible=el('residenceCountry').value==='IN' && Boolean(el('residenceState').value);
    el('residenceCityField').classList.toggle('hidden',!visible);
    el('residenceCity').disabled=!visible;
    el('residenceCity').required=visible;
  }
  function read(validate = true) {
    const country = el('residenceCountry')?.value || '';
    const homeState = country==='IN' ? el('residenceState').value : null;
    const city = country==='IN' ? el('residenceCity').value.trim() : null;
    const currency = country==='IN' ? 'INR' : country ? el('preferredCurrency')?.value || '' : null;
    if (validate) {
      ['residenceCountry','residenceState','residenceCity','preferredCurrency'].forEach(id=>message(id,''));
      if (!country) { message('residenceCountry','Choose the country you currently live in.'); el('residenceCountry').focus(); return null; }
      if (country==='IN' && !homeState) { message('residenceState','Choose your state or union territory.'); el('residenceState').focus(); return null; }
      if (country==='IN' && (!city || city.length<2 || city.length>100 || !/\p{L}/u.test(city) || /[<>\x00-\x1f\x7f]/.test(city))) {
        message('residenceCity','Enter a town or city name using 2–100 characters.'); el('residenceCity').focus(); return null;
      }
      if (!currency) { message('preferredCurrency','Choose the currency you prefer to see alongside INR.'); return null; }
    }
    return {residence_country:country || null,residence_state:homeState,residence_city:city,preferred_currency:currency || null};
  }
  async function render(profile = {}) {
    if (!el('residenceCountry')) return;
    try {
      const data = await options();
      if (!el('residenceCountry').options.length || !el('residenceCountry').dataset.ready) {
        fillSelect(el('residenceCountry'), data.countries.map(row=>({label:row.name,value:row.code})), 'Select your country');
        fillSelect(el('residenceState'), data.indian_states.map(name=>({label:name,value:name})), 'Select your state / union territory');
        fillSelect(el('preferredCurrency'), data.currencies.map(code=>({label:code,value:code})), 'Select display currency');
        el('residenceCountry').dataset.ready = 'true';
      }
      el('residenceCountry').value = profile.residence_country || '';
      el('residenceState').value = profile.residence_state || '';
      el('residenceCity').value = profile.residence_city || '';
      el('preferredCurrency').value = profile.preferred_currency || (data.countries.find(row=>row.code===profile.residence_country)?.currencies[0] || 'USD');
      countryChanged(false);
      message('residenceCountry','');
      el('residenceRetry').classList.add('hidden');
    } catch(error) {
      message('residenceCountry',error.message);
      el('residenceRetry').classList.remove('hidden');
    }
  }
  let conversion = null, activeKey = '', requestEpoch = 0;
  window.UserCurrency = {
    async setProfile(profile) {
      const code = profile?.residence_country && profile.residence_country!=='IN' ? profile.preferred_currency || 'INR' : 'INR';
      const key = String(state.currentUser?.user_id || '')+':'+code;
      if (key===activeKey) return;
      activeKey = key; conversion = null;
      this.updateBudgetPreview(null);
      const epoch = ++requestEpoch;
      const notice = el('displayCurrencyNotice');
      if (notice) { notice.textContent=''; notice.classList.add('hidden'); }
      if (code==='INR') return;
      const controller = new AbortController(), timeout = setTimeout(()=>controller.abort(),8000);
      try {
        const response = await fetch('/api/currency/rate?currency='+encodeURIComponent(code),{signal:controller.signal});
        if (!response.ok) throw new Error('Currency conversion is unavailable. Prices are shown in INR.');
        const data = await response.json();
        if (epoch!==requestEpoch) return;
        if (data.available && Number.isFinite(data.rate) && data.rate>0) conversion=data;
        if (notice) {
          notice.textContent = conversion ? `Prices remain in INR. Approximate ${code} amounts use ${data.stale?'a cached':'a'} reference rate dated ${data.as_of}; bank and card charges may differ.` : data.message;
          notice.classList.remove('hidden');
        }
        if(!conversion)activeKey='';
      } catch(error) {
        if (epoch===requestEpoch) {
          activeKey='';
          if(notice){notice.textContent='Currency conversion is unavailable. Prices remain in INR; your currency preference has been kept.';notice.classList.remove('hidden');}
        }
      } finally { clearTimeout(timeout);if(epoch===requestEpoch)this.updateBudgetPreview(el('tripBudgetInput')?.value); }
    },
    formatAmount(amount, inrText) {
      if (!conversion) return inrText;
      try { return inrText+' (≈ '+new Intl.NumberFormat(undefined,{style:'currency',currency:conversion.currency,maximumFractionDigits:2}).format(amount*conversion.rate)+')'; }
      catch (_) { return inrText; }
    },
    updateBudgetPreview(amount) {
      const target=el('tripBudgetCurrencyPreview');if(!target)return;
      if(!conversion || !Number.isFinite(Number(amount))){target.textContent='';return;}
      target.textContent='Approximate display: '+this.formatAmount(Number(amount),'₹'+Number(amount).toLocaleString('en-IN'))+
        ' · Reference rate '+conversion.as_of+'. Enter the budget in INR above.';
    },
    clear() { conversion=null; activeKey=''; requestEpoch++;this.updateBudgetPreview(null); }
  };
  window.ResidenceForm = {render,read};
  el('residenceCountry')?.addEventListener('change',()=>countryChanged());
  el('residenceState')?.addEventListener('change',()=>{
    el('residenceCity').value='';message('residenceState','');message('residenceCity','');updateCityField();
    Object.assign(state.basicAnswers,read(false) || {});
  });
  el('residenceRetry')?.addEventListener('click',()=>render(state.basicAnswers));
})();
