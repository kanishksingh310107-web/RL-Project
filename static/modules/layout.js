/* Presentation only: keep all planning permissions in the existing profile gate. */
(() => {
  'use strict';
  const byId = id => document.getElementById(id);
  const headerActions = byId('headerTripActions');
  const main = document.querySelector('main');
  const dashboard = byId('dashboardView');
  if (!headerActions || !main || !dashboard) return;

  const overview = document.createElement('div');
  overview.id = 'dashboardOverview';
  const basic = byId('dashBasicProfileCard');
  if (basic) {
    basic.before(overview);
    overview.append(basic);
    const personal = document.createElement('div');
    personal.className = 'app-personal-profile';
    for (const id of ['personalProfileBanner', 'personalProfileSummaryCard']) {
      const card = byId(id);
      if (card) personal.append(card);
    }
    overview.append(personal);
  }

  function sync() {
    const signedIn = typeof state !== 'undefined' && !!state.currentUser;
    headerActions.hidden = !signedIn;
    main.dataset.screen = !byId('authView').classList.contains('hidden') ? 'auth'
      : !byId('onboardingView').classList.contains('hidden') ? 'onboarding' : 'app';
    const path = location.hash.slice(1) || '/';
    for (const link of headerActions.querySelectorAll('a')) {
      if (link.hash === '#/' && path === '/' || link.hash === '#/trips' && path.startsWith('/trips') && path !== '/trips/new') link.setAttribute('aria-current', 'page');
      else link.removeAttribute('aria-current');
    }
  }
  const plan = byId('headerPlanTripBtn');
  plan.onclick = async () => {
    if (plan.disabled) return;
    plan.disabled = true;
    try { await window.toggleTripFormModal(); }
    catch (error) { window.showAppNotice?.(error.message || 'Trip planning could not open. Please retry.'); }
    finally { plan.disabled = false; }
  };
  const oldNav = window.updateNavUser;
  window.updateNavUser = function (...args) { const result = oldNav?.apply(this, args); sync(); return result; };
  const observer = new MutationObserver(sync);
  for (const id of ['authView', 'onboardingView', 'dashboardView']) observer.observe(byId(id), {attributes: true, attributeFilter: ['class']});
  window.addEventListener('hashchange', sync);
  sync();
})();
