/* A: official Google button, recoverable SDK loading, and persistent setup. */
(() => {
  const el = id => document.getElementById(id);
  let inFlight, renderedFor, configuration;
  const status = text => { const node=el('googleAuthStatus'); if(node){node.textContent=text;node.classList.toggle('hidden',!text);} };
  function sdkReady() {
    if (window.google?.accounts?.id) return Promise.resolve();
    return new Promise((resolve,reject)=>{
      let timer;
      const cleanup=()=>{clearTimeout(timer);window.removeEventListener('google-identity-ready',ready);window.removeEventListener('google-identity-error',failed);};
      const ready=()=>{cleanup();resolve();};
      const failed=()=>{cleanup();reject(new Error('Google sign-in could not load. Check your connection and press Retry Google sign-in.'));};
      window.addEventListener('google-identity-ready',ready,{once:true});
      window.addEventListener('google-identity-error',failed,{once:true});
      timer=setTimeout(failed,12000);
      let script=el('googleIdentitySdk');
      if (!script || script.dataset.failed==='true') {
        script?.remove();script=document.createElement('script');script.id='googleIdentitySdk';
        script.src='https://accounts.google.com/gsi/client';script.async=true;
        script.onload=()=>window.dispatchEvent(new Event('google-identity-ready'));
        script.onerror=()=>{script.dataset.failed='true';window.dispatchEvent(new Event('google-identity-error'));};
        document.head.appendChild(script);
      }
    });
  }
  async function acceptCredential(response) {
    if (!response.credential) { status('Google did not return a sign-in credential. Please choose your account again.');return; }
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),15000);
    status('Signing in with Google…');
    try {
      const result=await fetch('/api/auth/google-token',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({credential:response.credential}),signal:controller.signal});
      const user=await result.json();
      if(!result.ok)throw new Error(formatApiError(user,'Google sign-in failed. Please choose your account again.'));
      state.currentUser=user;localStorage.setItem('rl_travel_user',JSON.stringify(user));updateNavUser();
      window.UserCurrency?.clear();
      if(user.has_profile)await loadUserProfile(user.user_id);
      else {resetAnswers();showView('onboarding');}
      status('');
    }catch(error){status(error.name==='AbortError'?'Google sign-in timed out. Please try again.':error.message || 'Google sign-in is unavailable. Please retry.');}
    finally{clearTimeout(timer);}
  }
  window.initGoogleGIS=async function() {
    if(document.readyState==='loading')return;
    if(inFlight)return inFlight;
    inFlight=(async()=>{
      const chooser=el('googleChooserBtn');if(chooser)chooser.disabled=true;
      const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),8000);
      try {
        const response=await fetch('/api/config/google',{signal:controller.signal});
        if(!response.ok)throw new Error('Google sign-in settings could not be loaded. Please retry.');
        configuration=await response.json();
        const originHint=el('googleOriginHint');
        if(originHint)originHint.textContent='Authorized JavaScript origin for this app: '+window.location.origin;
        el('googleSetupLink')?.classList.toggle('hidden',!configuration.can_configure);
        if(!configuration.client_id){status('Google sign-in needs a Google OAuth Web client ID. Complete Google setup to enable it; email and guest sign-in remain available.');return;}
        status('Loading Google sign-in…');
        await sdkReady();
        const container=el('googleOfficialBtn');if(!container)return;
        if(renderedFor!==configuration.client_id || !container.childElementCount){
          container.replaceChildren();
          google.accounts.id.initialize({client_id:configuration.client_id,callback:acceptCredential,auto_select:false,ux_mode:'popup'});
          google.accounts.id.renderButton(container,{theme:'outline',size:'large',width:Math.min(320,container.clientWidth || 320)});
          renderedFor=configuration.client_id;
        }
        chooser?.classList.add('hidden');status('');
      }catch(error){status(error.name==='AbortError'?'Google sign-in settings timed out. Please retry.':error.message);el('googleBtnLabel').textContent='Retry Google sign-in';}
      finally{clearTimeout(timer);if(chooser)chooser.disabled=false;}
    })().finally(()=>{inFlight=null;});
    return inFlight;
  };
  window.startGoogleSignIn=async function(){
    await window.initGoogleGIS();
    if(!configuration?.client_id && configuration?.can_configure)openModal('googleConfigModal');
    else el('googleOfficialBtn')?.scrollIntoView({block:'nearest',behavior:'smooth'});
  };
  window.addEventListener('google-identity-ready',()=>{if(document.readyState!=='loading')window.initGoogleGIS();});
})();
