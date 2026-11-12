// Planner module registry and shared JSON transport.
window.TravelModules = (function () {
  const registry = {};
  async function api(path, opts = {}) {
    const options = {...opts, headers: {'Content-Type':'application/json', ...(opts.headers || {})}};
    if (options.body && typeof options.body !== 'string') options.body = JSON.stringify(options.body);
    const response = await fetch(path, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail || response.statusText));
    return data;
  }
  function register(id, mod) { registry[id] = mod; window.TravelModules[id] = mod; }
  return {register, api};
})();
