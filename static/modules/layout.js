/* Responsive app shell and profile-aware dashboard layout. */
(() => {
  'use strict';
  const byId = id => document.getElementById(id);
  const headerActions = byId('headerTripActions');
  const main = document.querySelector('main');
  const dashboard = byId('dashboardView');
  const tripView = byId('tripExperienceView');
  if (!headerActions || !main || !dashboard) return;

  // Each page starts with its original photo, followed by curated alternatives.
  const backgroundAlternatives = {
    auth: [['red-fort', '65% 58%'], ['stone-carving', '30% 50%'], ['palace-at-night', '65% 54%']],
    onboarding: [['tea-garden', 'center 73%'], ['green-valley', 'center 62%'], ['forest-road', 'center 74%'], ['parrot', '68% 42%']],
    discover: [['waterfall', '36% 70%']],
    trips: [['hill-fort', 'center 67%'], ['india-gate', 'center 65%']],
    plan: [['desert-sunset', '73% 65%'], ['sand-dunes', 'center 64%'], ['hill-sunrise', 'center 55%']],
    trip: [['river-bridge', '38% 72%']],
  };
  const backgroundIndices = new Map();
  let activeBackgroundPage;

  function rotateBackground(page) {
    if (page === activeBackgroundPage) return;
    activeBackgroundPage = page;

    const alternatives = backgroundAlternatives[page];
    const key = `travel-guide-background:${page}`;
    let previous = backgroundIndices.get(page) ?? -1;
    if (!backgroundIndices.has(page)) {
      try {
        const saved = Number(sessionStorage.getItem(key) ?? -1);
        if (Number.isInteger(saved) && saved >= 0 && saved <= alternatives.length) previous = saved;
      } catch (_) {
        // In-memory rotation still works when storage is unavailable.
      }
    }
    const index = (previous + 1) % (alternatives.length + 1);
    backgroundIndices.set(page, index);
    try { sessionStorage.setItem(key, String(index)); } catch (_) {}

    const style = document.body.style;
    if (index === 0) {
      style.removeProperty('--rotating-photo');
      style.removeProperty('--rotating-photo-position');
      return;
    }
    const [photo, position] = alternatives[index - 1];
    style.setProperty('--rotating-photo', `url("/static/images/background-rotation/${photo}.jpg")`);
    style.setProperty('--rotating-photo-position', position);
  }

  const overview = document.createElement('div');
  overview.id = 'dashboardOverview';
  const basic = byId('dashBasicProfileCard');
  let personal = null;
  if (basic) {
    basic.before(overview);
    personal = document.createElement('div');
    personal.id = 'dashboardPersonalProfile';
    personal.className = 'app-personal-profile';
    overview.append(basic, personal);
    for (const id of ['personalProfileBanner', 'personalProfileSummaryCard']) {
      const card = byId(id);
      if (card) personal.append(card);
    }
  }

  const labels = new Map([
    ['recommended for you', 'Recommended for you'],
    ['selected for your profile', 'Selected for your profile'],
    ['trending destinations', 'Trending destinations'],
    ['seasonal & upcoming experiences', 'Seasonal & upcoming experiences'],
    ['within your budget', 'Within your budget'],
    ['your saved places', 'Your saved places'],
    ['create my personal travel profile', 'Create my personal travel profile'],
    ['personalised itinerary & daily schedule', 'Personalised itinerary & daily schedule'],
    ['personalised itinerary & trip planner locked', 'Personalised itinerary & trip planner locked'],
    ['no active itinerary selected', 'No active itinerary selected'],
    ['select an indian destination', 'Select an Indian destination'],
    ['personal travel profile saved!', 'Personal travel profile saved!']
  ]);
  const setText = (node, value) => { if (node && node.textContent !== value) node.textContent = value; };
  const setHidden = (node, hidden) => { if (node && node.hidden !== hidden) node.hidden = hidden; };
  const setProfileHidden = (node, hidden) => {
    setHidden(node, hidden);
    if (node && node.classList.contains('hidden') !== hidden) node.classList.toggle('hidden', hidden);
  };
  function sentenceCaseDashboardHeadings() {
    for (const heading of dashboard.querySelectorAll('h1,h2,h3,h4')) {
      const replacement = labels.get(heading.textContent.trim().toLocaleLowerCase());
      if (replacement && heading.textContent !== replacement) heading.textContent = replacement;
    }
  }

  let accountId = null;
  function syncProfileOverview() {
    if (!overview || !basic || !personal) return;
    const user = typeof state !== 'undefined' ? state.currentUser : null;
    const profile = typeof state !== 'undefined' ? state.currentProfile : null;
    const nextAccount = user?.user_id || null;
    if (accountId !== nextAccount) {
      accountId = nextAccount;
      setHidden(overview, true);
      setHidden(basic, true);
      for (const card of personal.children) setHidden(card, true);
    }

    const profileLoaded = !!nextAccount && profile?.user_id === nextAccount;
    if (!profileLoaded) {
      setHidden(overview, true);
      overview.dataset.panels = '0';
      return;
    }

    setHidden(basic, false);
    const basicBadge = basic.querySelector('.inline-flex');
    setText(basicBadge, 'Basic profile complete');

    const banner = byId('personalProfileBanner');
    const summary = byId('personalProfileSummaryCard');
    const precision = typeof state !== 'undefined' ? state.precision : null;
    const savedPrecision = typeof profile.has_precision_profile === 'boolean'
      ? profile.has_precision_profile : precision?.exists === true;
    const hasPrecision = savedPrecision && state.profileStatus?.complete === true;
    const precisionKnown = profile.has_precision_profile === false || typeof state.profileStatus?.complete === 'boolean';

    if (banner) {
      setProfileHidden(banner, hasPrecision);
      const badge = banner.querySelector('.inline-flex');
      const title = banner.querySelector('h3');
      const description = banner.querySelector('p');
      const button = banner.querySelector('button');
      setText(badge, precisionKnown ? 'Deep Personalisation · Incomplete' : 'Deep Personalisation · Status unavailable');
      setText(title, precisionKnown ? 'Complete Deep Personalisation for India' : 'Deep Personalisation status unavailable');
      setText(description, precisionKnown
        ? 'Your basic travel profile is complete. Add your comfort, accessibility and travel preferences to tailor recommendations and itineraries further.'
        : 'We could not verify your Deep Personalisation status. Retry after reconnecting to check your saved profile.');
      setText(button, precisionKnown ? 'Complete Deep Personalisation' : 'Retry profile status');
      if (button) button.onclick = () => precisionKnown
        ? window.openPersonalProfileModal?.() : window.renderDashboard?.(state.currentProfile);
    }
    if (summary) {
      setProfileHidden(summary, !hasPrecision);
      const badge = summary.querySelector('.bg-emerald-50');
      const status = byId('personalProfileStatus');
      setText(badge, 'Deep Personalisation complete');
      setText(status, 'Your detailed answers are tailoring recommendations and trip plans.');
    }

    setHidden(personal, ![banner, summary].some(card => card && !card.hidden && !card.classList.contains('hidden')));
    const count = [basic, personal].filter(panel => !panel.hidden && !panel.classList.contains('hidden')).length;
    overview.dataset.panels = String(count);
    setHidden(overview, count === 0);
    sentenceCaseDashboardHeadings();
  }

  function sync() {
    const signedIn = typeof state !== 'undefined' && !!state.currentUser;
    headerActions.hidden = !signedIn;
    main.dataset.screen = !byId('authView').classList.contains('hidden') ? 'auth'
      : !byId('onboardingView').classList.contains('hidden') ? 'onboarding' : 'app';
    const path = location.hash.slice(1) || '/';
    let page = main.dataset.screen;
    if (page === 'app') {
      if (!tripView || tripView.hidden) page = 'discover';
      else if (path === '/trips') page = 'trips';
      else if (path === '/trips/new' || path.endsWith('/edit')) page = 'plan';
      else page = 'trip';
    }
    document.body.dataset.page = page;
    rotateBackground(page);
    for (const link of headerActions.querySelectorAll('a')) {
      if (link.hash === '#/' && path === '/' || link.hash === '#/trips' && path.startsWith('/trips') && path !== '/trips/new') link.setAttribute('aria-current', 'page');
      else link.removeAttribute('aria-current');
    }
    syncProfileOverview();
  }

  const plan = byId('headerPlanTripBtn');
  plan.onclick = async () => {
    if (plan.disabled) return;
    plan.disabled = true;
    try {
      if (window.TripExperience?.route) {
        if (location.hash === '#/trips/new') await window.TripExperience.route();
        else location.hash = '/trips/new';
      } else await window.toggleTripFormModal();
    }
    catch (error) { window.showAppNotice?.(error.message || 'Trip planning could not open. Please retry.'); }
    finally { plan.disabled = false; }
  };
  const oldNav = window.updateNavUser;
  window.updateNavUser = function (...args) { const result = oldNav?.apply(this, args); sync(); return result; };

  const oldRenderDashboard = window.renderDashboard;
  if (typeof oldRenderDashboard === 'function') {
    window.renderDashboard = async function (...args) {
      const result = await oldRenderDashboard.apply(this, args);
      sync();
      return result;
    };
  }
  const observer = new MutationObserver(sync);
  for (const id of ['authView', 'onboardingView', 'dashboardView']) observer.observe(byId(id), {attributes: true, attributeFilter: ['class', 'hidden']});
  if (tripView) observer.observe(tripView, {attributes: true, attributeFilter: ['hidden']});
  observer.observe(dashboard, {subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ['class', 'hidden']});
  window.addEventListener('hashchange', sync);
  window.DashboardLayout = {refresh: sync};
  sync();
})();
