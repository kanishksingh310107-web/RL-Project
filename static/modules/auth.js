/* Account flows owned by A. Loaded after app.js to keep the existing shell intact. */
(() => {
  const byId = (id) => document.getElementById(id);
  const oldFetch = window.fetch.bind(window);
  window.fetch = (input, init = {}) => {
    const saved = localStorage.getItem("rl_travel_user");
    let user = null;
    try { user = saved ? JSON.parse(saved) : null; } catch (_) {}
    if (user && user.token) {
      const headers = new Headers(init.headers || (input instanceof Request ? input.headers : undefined));
      if (!headers.has("Authorization")) headers.set("Authorization", `Bearer ${user.token}`);
      init = { ...init, headers };
    }
    return oldFetch(input, init);
  };

  function ensureSignupFields() {
    const form = byId("authContent-manual");
    const email = byId("manualEmail");
    if (email) { email.type = "text"; email.autocomplete = "username"; email.placeholder = "you@example.com or username"; }
    if (!form || byId("aUsernameWrap")) return;
    const emailError = document.createElement("p"); emailError.id = "aEmailError"; emailError.className = "hidden mt-1 text-xs text-rose-600";
    if (email) email.after(emailError);
    const wrap = document.createElement("div");
    wrap.id = "aUsernameWrap";
    wrap.className = "hidden";
    const label = document.createElement("label");
    label.htmlFor = "aUsername"; label.textContent = "Username";
    label.className = "block text-xs font-semibold text-slate-700 mb-1";
    const input = document.createElement("input");
    input.id = "aUsername"; input.autocomplete = "username"; input.minLength = 3; input.maxLength = 24;
    input.pattern = "[A-Za-z0-9_.-]{3,24}"; input.title = "3–24 letters, numbers, dots, underscores, or hyphens";
    input.className = "w-full px-3 py-2.5 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500";
    input.setAttribute("aria-describedby", "aUsernameError");
    const error = document.createElement("p"); error.id = "aUsernameError"; error.className = "hidden mt-1 text-xs text-rose-600";
    wrap.append(label, input, error);
    const confirm = document.createElement("div"); confirm.id = "aConfirmWrap"; confirm.className = "hidden";
    const cLabel = document.createElement("label"); cLabel.htmlFor = "aConfirmPassword"; cLabel.textContent = "Confirm password";
    cLabel.className = "block text-xs font-semibold text-slate-700 mb-1";
    const cInput = document.createElement("input"); cInput.id = "aConfirmPassword"; cInput.type = "password"; cInput.autocomplete = "new-password";
    cInput.className = input.className;
    const cError = document.createElement("p"); cError.id = "aConfirmError"; cError.className = "hidden mt-1 text-xs text-rose-600";
    confirm.append(cLabel, cInput, cError);
    const nameWrap = byId("manualNameWrap");
    if (nameWrap) nameWrap.after(wrap); else form.prepend(wrap);
    const pass = byId("manualPassword"); if (pass) { pass.minLength = 10; pass.autocomplete = "new-password"; pass.after(confirm); }
    const passwordError = document.createElement("p"); passwordError.id = "aPasswordError"; passwordError.className = "hidden mt-1 text-xs text-rose-600";
    if (pass) pass.after(passwordError);
  }

  function updateFields() {
    ensureSignupFields();
    const signup = typeof emailAuthMode !== "undefined" && emailAuthMode === "signup";
    byId("aUsernameWrap")?.classList.toggle("hidden", !signup);
    byId("aConfirmWrap")?.classList.toggle("hidden", !signup);
    const pass = byId("manualPassword"); if (pass) { pass.autocomplete = signup ? "new-password" : "current-password"; pass.minLength = signup ? 10 : 1; }
  }

  async function continueAsGuest(button) {
    const message = button?.parentElement.querySelector(".aGuestMessage") || byId("authFormMessage");
    if (button) { button.disabled = true; button.textContent = "Opening your guest profile…"; }
    if (message) { message.textContent = ""; message.classList.add("hidden"); }
    try {
      let guestId = localStorage.getItem("rl_travel_guest_id");
      if (!guestId) {
        guestId = (window.crypto?.randomUUID?.() || `${Date.now()}_${Math.random().toString(36).slice(2)}${Math.random().toString(36).slice(2)}`).replace(/[^A-Za-z0-9_-]/g, "").slice(0, 64);
        localStorage.setItem("rl_travel_guest_id", guestId);
      }
      const response = await fetch("/api/account/guest", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ guest_id: guestId }) });
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === "object" ? data.detail.detail : (data.detail || "Guest sign-in failed. Try again."));
      state.currentUser = data; localStorage.setItem("rl_travel_user", JSON.stringify(data)); updateNavUser();
      if (data.has_profile) await loadUserProfile(data.user_id); else showView("onboarding");
    } catch (error) {
      if (message) { message.textContent = error.message; message.classList.remove("hidden"); }
    } finally {
      if (button) { button.disabled = false; button.textContent = "Continue as guest"; }
    }
  }

  function addGuestButton(parent) {
    if (!parent || parent.querySelector(".aGuestLogin")) return;
    const button = document.createElement("button"); button.type = "button"; button.className = "aGuestLogin w-full mt-3 py-2.5 border border-slate-200 hover:border-indigo-300 text-slate-700 font-semibold text-sm rounded-xl transition"; button.textContent = "Continue as guest";
    button.addEventListener("click", () => continueAsGuest(button)); parent.append(button);
    const msg = document.createElement("p"); msg.className = "aGuestMessage hidden mt-2 text-center text-xs text-rose-600"; button.after(msg);
  }

  function installGuestButtons() {
    addGuestButton(byId("authContent-google"));
    addGuestButton(byId("authContent-manual"));
  }

  window.sendAuthRequest = async (payload) => {
    updateFields();
    const message = byId("authFormMessage");
    const submit = byId("emailSubmitBtn");
    const username = byId("aUsername");
    const confirm = byId("aConfirmPassword");
    const emailInput = byId("manualEmail");
    const emailError = byId("aEmailError");
    if (message) { message.textContent = ""; message.classList.add("hidden"); }
    if (emailError) emailError.classList.add("hidden");
    const identity = String(payload.identifier || "").trim();
    const validEmail = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(identity);
    const validUsername = /^[A-Za-z0-9_.-]{3,24}$/.test(identity);
    if ((payload.mode === "signup" && !validEmail) || (payload.mode === "login" && !validEmail && !validUsername)) {
      if (emailInput) { emailInput.setCustomValidity(payload.mode === "signup" ? "Enter a valid email address." : "Enter your email address or username."); emailInput.focus(); emailInput.reportValidity(); }
      if (emailError) { emailError.textContent = emailInput?.validationMessage || "Enter a valid email or username."; emailError.classList.remove("hidden"); }
      return;
    }
    if (emailInput) emailInput.setCustomValidity("");
    if (username) { username.setCustomValidity(""); byId("aUsernameError")?.classList.add("hidden"); }
    if (confirm) { confirm.setCustomValidity(""); byId("aConfirmError")?.classList.add("hidden"); }
    if (payload.mode === "signup" && username && !username.checkValidity()) {
      username.setCustomValidity("Enter a username with 3–24 letters, numbers, dots, underscores, or hyphens.");
      byId("aUsernameError").textContent = username.validationMessage;
      byId("aUsernameError").classList.remove("hidden"); username.reportValidity(); return;
    }
    const password = byId("manualPassword");
    const passwordError = byId("aPasswordError");
    if (payload.mode === "signup" && password && !(/^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{10,128}$/.test(password.value))) {
      passwordError.textContent = "Use 10–128 characters with an uppercase letter, lowercase letter, and number.";
      passwordError.classList.remove("hidden"); password.focus(); return;
    }
    password?.addEventListener("input", () => passwordError?.classList.add("hidden"), { once: true });
    if (payload.mode === "signup" && confirm && confirm.value !== payload.password) {
      confirm.setCustomValidity("Passwords do not match.");
      byId("aConfirmError").textContent = confirm.validationMessage;
      byId("aConfirmError").classList.remove("hidden"); confirm.reportValidity(); return;
    }
    if (submit) { submit.disabled = true; submit.textContent = payload.mode === "signup" ? "Creating account…" : "Signing in…"; }
    try {
      const endpoint = payload.mode === "signup" ? "/api/account/register" : "/api/account/login";
      const response = await fetch(endpoint, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email: identity, password: payload.password, mode: payload.mode, username: username?.value.trim(), display_name: byId("manualName")?.value.trim() || username?.value.trim(), confirm_password: confirm?.value }) });
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === "object" ? data.detail.detail : (data.detail || "Could not sign in. Try again."));
      state.currentUser = data; localStorage.setItem("rl_travel_user", JSON.stringify(data)); updateNavUser();
      if (data.has_profile) await loadUserProfile(data.user_id); else showView("onboarding");
    } catch (error) {
      if (message) { message.textContent = error.message; message.classList.remove("hidden"); }
    } finally {
      if (submit) { submit.disabled = false; if (typeof updateEmailAuthMode === "function") updateEmailAuthMode(); }
    }
  };

  const oldToggle = window.toggleEmailAuthMode;
  if (typeof oldToggle === "function") window.toggleEmailAuthMode = function () { oldToggle(); updateFields(); };
  const oldLogout = window.logout;
  if (typeof oldLogout === "function") window.logout = function () {
    fetch("/api/account/logout", { method: "POST" }).catch(() => {
  const byId = (id) => document.getElementById(id);});
    return oldLogout();
  };
  document.addEventListener("click", (event) => { if (event.target.closest("#emailModeToggle")) setTimeout(updateFields, 0); });
  document.addEventListener("DOMContentLoaded", updateFields);
  document.addEventListener("DOMContentLoaded", installGuestButtons);
  updateFields();
  installGuestButtons();
})();
