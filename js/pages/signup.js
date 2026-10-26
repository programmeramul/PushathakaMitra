// Sign-up & login — full account form in sections (Account, Personal, Address,
// Interests), with inline validation, loading/success/failure states.
// Design preserved: cream/forest-green PustakaMitra system.
import { authApi, GENRE_OPTIONS, GENDER_OPTIONS } from "../services/auth.js";

const main = document.getElementById("main");
const isLogin = window.location.hash === "#login";
function field(id, label, inner, hint = "") {
  return `<div class="field" data-f="${id}"><label for="${id}">${label}</label>${inner}
    ${hint ? `<span class="hint">${hint}</span>` : ""}<span class="err hint" style="color:#b3541e" id="err-${id}"></span></div>`;
}
const txt = (id, attrs = "") => `<input id="${id}" name="${id}" ${attrs}>`;

const accountSection = `
<h1 style="font-size:1.7rem;margin-bottom:1rem">Create your account</h1>
<div class="panel">
  <b>Account Details</b>
  ${field("name", "Full name*", txt("name", 'required minlength="2" maxlength="80"'))}
  ${field("email", "Email address*", txt("email", 'required type="email"'), "Will be the sign-in ID (stored lowercase).")}
  ${field("phone", "Phone number*", txt("phone", 'required'), 'With country code — India (+91) default, e.g. "+91 98765 43210".')}
  ${field("password", "Password*", `<span class="pw-wrap">${txt("password", 'required type="password" minlength="8"')}<button type="button" class="pw-toggle" data-toggle="password" aria-label="Show password">Show</button></span>`, "Minimum 8 characters.")}
  ${field("password_confirm", "Confirm password*", `<span class="pw-wrap">${txt("password_confirm", 'required type="password"')}<button type="button" class="pw-toggle" data-toggle="password_confirm" aria-label="Show password">Show</button></span>`)}
</div>
<div class="panel" style="margin-top:1rem">
  <b>Personal Details</b> <span class="hint">— optional, private to you</span>
  <div class="row-2">
    ${field("age", "Age*", txt("age", 'required type="number" min="5" max="120"'))}
    ${field("dob", "Date of birth", txt("dob", 'type="date"'), "Optional; must match age. No future dates.")}
  </div>
  ${field("gender", "Gender", `<select id="gender">
      <option value="prefer-not-to-say">Prefer not to say</option>
      ${GENDER_OPTIONS.map(([v, l]) => `<option value="${v}">${l}</option>`).join("")}
    </select>`)}
</div>
<div class="panel" style="margin-top:1rem">
  <b>Address</b> <span class="hint">— optional, private to you</span>
  ${field("home_address", "Home address", `<textarea id="home_address" rows="3" maxlength="320"></textarea>`)}
  ${field("pin_code", "PIN code", txt("pin_code", 'inputmode="numeric" pattern="[1-9][0-9]{5}" maxlength="6"'), "Six-digit Indian postal PIN.")}
</div>
<div class="panel" style="margin-top:1rem">
  <b>Reading Interests*</b> <span class="hint">— the main input for book recommendations</span>
  <div class="chipbar" style="margin-top:.6rem" id="chips">
    ${GENRE_OPTIONS.map(([v, l]) => `<button type="button" class="chip" data-g="${v}" aria-pressed="false">${l}</button>`).join("")}
  </div>
  <div class="field" data-f="other_interest" style="margin-top:.8rem">
    <label for="other_interest">Custom interest (for Other)</label>
    ${txt("other_interest", 'placeholder="e.g. Cozy Kerala fiction"')}
    <span class="err hint" style="color:#b3541e" id="err-other_interest"></span>
  </div>
  <span class="err hint" style="color:#b3541e" id="err-interests"></span>
</div>
<div class="panel" style="margin-top:1rem" data-f="__all__">
  <span class="err hint" style="color:#b3541e" id="err-__all__"></span>
  <div style="display:flex;gap:1rem;align-items:center;margin-top:.5rem">
    <button class="btn" type="submit" id="submit">Create account</button>
    <a href="#login" id="toggle">Already registered? Log in</a>
    <span class="hint" id="state"></span>
  </div>
</div>
</form>
</section></div>`;

const loginMarkup = `
<div style="max-width:420px;margin:var(--space-4) auto">
  <div class="panel">
    <h1 style="font-size:1.5rem;margin-bottom:1rem">Welcome back</h1>
    ${field("email", "Email", txt("email", 'required type="email"'))}
    ${field("password", "Password", txt("password", 'required type="password"'))}
    <div data-f="__all__"><span class="err hint" style="color:#b3541e" id="err-__all__"></span></div>
    <button class="btn" type="submit" id="submit" style="width:100%">Log in</button>
    <p style="margin-top:1rem">New here? <a href="#signup" id="toggle">Create an account</a></p>
  </div>
</div>`;

const errors = {};
let mode = isLogin ? "login" : "signup";
const picks = new Set();


/* real builder */
function build() {
  main.innerHTML = `
  <div class="split" style="align-items:start">
    <aside class="left panel green" style="border-radius:0;position:sticky;top:64px;height:calc(100vh - 64px)">
      <blockquote>PustakaMitra AI — Nimma Interest, Nimma Next Book!</blockquote>
      <div class="by">${mode === "login"
        ? "Welcome back — your shelf is waiting."
        : "One profile powers recommendations in Kannada &amp; English and shows where books wait at Bengaluru libraries."}</div>
      <div class="by" style="margin-top:auto">Sessions are secure (HTTP-only cookies, Argon2-hashed passwords in MongoDB).</div>
    </aside>
    <section class="right" style="display:block;padding:2rem 1.5rem 4rem">
      <form id="regform" novalidate>${mode === "login" ? loginMarkup : accountSection}</form>
    </section>
  </div>`;
  if (mode === "signup") wire();
  else wireLogin();
}

function clearErrors() {
  main.querySelectorAll(".err").forEach((e) => (e.textContent = ""));
  main.querySelectorAll(".field").forEach((f) => f.querySelector(".err")?.removeAttribute("style"));
}
function showErr(field, msg) {
  const el = main.querySelector(`#err-${field}`) || main.querySelector(`#err-__all__`);
  if (el) el.textContent = msg;
  const f = main.querySelector(`[data-f="${field}"]`);
  if (f) f.style.borderLeft = "3px solid #b3541e";
}

function wire() {
  main.querySelectorAll("[data-g]").forEach((c) => c.addEventListener("click", () => {
    picks.has(c.dataset.g) ? picks.delete(c.dataset.g) : picks.add(c.dataset.g);
    c.setAttribute("aria-pressed", picks.has(c.dataset.g));
  }));

  // password show/hide
  main.querySelectorAll(".pw-toggle").forEach((t) => t.addEventListener("click", () => {
    const input = main.querySelector("#" + t.dataset.toggle);
    const show = input.type === "password";
    input.type = show ? "text" : "password";
    t.textContent = show ? "Hide" : "Show";
    t.setAttribute("aria-label", show ? "Hide password" : "Show password");
  }));

  main.querySelector("#regform").addEventListener("submit", async (e) => {
    e.preventDefault();
    clearErrors();
    const g = (id) => main.querySelector("#" + id).value.trim();

    // client-side pass (backend re-validates everything)
    let bad = false;
    const clientErrs = {};
    if (g("name").length < 2) clientErrs.name = "Name must be at least 2 characters.";
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(g("email"))) clientErrs.email = "Enter a valid email address.";
    const digits = g("phone").replace(/[^0-9]/g, "").replace(/^0+/, "");
    const ink = digits.startsWith("91") ? digits.slice(2) : digits;
    if (!/^[6-9][0-9]{9}$/.test(ink)) clientErrs.phone = "Enter a 10-digit Indian mobile number, e.g. +91 98765 43210.";
    const ageNum = parseInt(g("age"), 10);
    if (!Number.isInteger(ageNum) || ageNum < 5 || ageNum > 120) clientErrs.age = "Age must be between 5 and 120.";
    const pw = main.querySelector("#password").value;
    if (pw !== g("password_confirm")) clientErrs.password_confirm = "Passwords do not match.";
    if (pw.length < 8) clientErrs.password = "Password must be at least 8 characters.";
    if (picks.size === 0) clientErrs.interests = "Pick at least one book interest.";
    if (picks.has("other") && !g("other_interest")) clientErrs.other_interest = 'Describe your custom interest for "Other".';
    if (g("pin_code") && !/^[1-9][0-9]{5}$/.test(g("pin_code"))) clientErrs.pin_code = "PIN code must be six digits.";
    if (g("dob")) {
      const dob = new Date(g("dob"));
      if (isNaN(dob) || dob > new Date()) clientErrs.dob = "Date of birth cannot be in the future (or is invalid).";
      else if (!clientErrs.age) {
        const today = new Date();
        const computed = today.getFullYear() - dob.getFullYear() - ((today.getMonth() < dob.getMonth()) || (today.getMonth() === dob.getMonth() && today.getDate() < dob.getDate()) ? 1 : 0);
        if (computed !== ageNum) clientErrs.dob = `Age (${ageNum}) and date of birth do not match.`;
      }
    }
    for (const [k, v] of Object.entries(clientErrs)) showErr(k, v);
    if (Object.keys(clientErrs).length) return;

    // loading state
    const btn = main.querySelector("#submit");
    btn.disabled = true; btn.textContent = "Creating account…";
    btn.style.opacity = ".7";
    try {
      const payload = {
        name: g("name"), email: g("email"), phone: g("phone"),
        age: ageNum, dob: g("dob") || null,
        gender: g("gender"), home_address: g("home_address") || null,
        pin_code: g("pin_code") || null,
        interests: [...picks], other_interest: picks.has("other") ? g("other_interest") : null,
        password: pw, password_confirm: g("password_confirm"),
      };
      const { user } = await authApi.register(payload);
      // success state
      localStorage.setItem("pustakamitra.profile.v1", JSON.stringify({
        ...JSON.parse(localStorage.getItem("pustakamitra.profile.v1") || "{}"),
        id: user.id, name: user.name, email: user.email, genres: user.interests,
        interests: user.interests, onboarded: true, persisted: true,
      }));
      btn.textContent = "✓ Account created!";
      setTimeout(() => (window.location.href = "/pages/dashboard.html"), 700);
    } catch (err) {
      btn.disabled = false; btn.style.opacity = ""; btn.textContent = "Create account";
      showErr(err.field || "__all__", err.message);
      main.querySelector(`#err-${err.field || "__all__"}`)?.scrollIntoView({ block: "center", behavior: "smooth" });
    }
  });
  main.querySelector("#toggle").addEventListener("click", (e) => { e.preventDefault(); mode = "login"; build(); history.replaceState(null, "", "#login"); });
}

function wireLogin() {
  main.querySelector("#regform").addEventListener("submit", async (e) => {
    e.preventDefault();
    clearErrors();
    const btn = main.querySelector("#submit");
    btn.disabled = true; btn.textContent = "Logging in…";
    try {
      const { user } = await authApi.login(main.querySelector("#email").value.trim(), main.querySelector("#password").value);
      localStorage.setItem("pustakamitra.profile.v1", JSON.stringify({
        ...(JSON.parse(localStorage.getItem("pustakamitra.profile.v1") || "{}")),
        id: user.id, name: user.name, email: user.email, interests: user.interests,
        genres: user.interests, onboarded: true, persisted: true,
      }));
      btn.textContent = "✓";
      setTimeout(() => (window.location.href = "/pages/dashboard.html"), 500);
    } catch (err) {
      btn.disabled = false; btn.textContent = "Log in";
      showErr(err.code === "bad_credentials" ? "__all__" : err.field || "__all__", err.message);
    }
  });
  main.querySelector("#toggle").addEventListener("click", (e) => { e.preventDefault(); mode = "signup"; build(); history.replaceState(null, "", "#signup"); });
}

build();

// chrome (no footer on auth)
document.getElementById("nav").innerHTML = `<div class="inner"><a class="logo" href="/index.html"><span class="mark">ಪ</span>PustakaMitra AI</a><div class="links"><a href="/index.html" class="btn secondary small">← Back to home</a></div></div>`;
document.getElementById("footer")?.remove();
