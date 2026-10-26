// Profile & editable preferences — real persistence via FastAPI/MongoDB.
// Interests (book genres) are the only recommendation signal; age/gender/
// address/phone are stored as account data and displayed only to the owner.
import { authApi, GENRE_OPTIONS, GENDER_OPTIONS } from "../services/auth.js";
import { mountChrome } from "../ui.js";

const main = document.getElementById("main");
const local = JSON.parse(localStorage.getItem("pustakamitra.profile.v1") || "{}");

let user = null;
try { user = await authApi.me(); }
catch (e) {
  main.innerHTML = `<section class="section"><h1>Not signed in</h1>
    <p class="muted">${e.message}. <a href="/pages/signup.html#login">Log in</a> to edit your profile.</p></section>`;
}

if (user) {
  main.innerHTML = `
  <section class="section" style="max-width:680px">
    <div style="display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:.5rem">
      <h1>Profile &amp; preferences</h1>
      <button class="btn secondary small" id="logout">Log out</button>
    </div>
    <span class="mock-note">Persistent MongoDB account — edits save immediately to the backend.</span>
    <form id="prefs" style="margin-top:1rem" novalidate>
      <div class="panel">
        <b>Account Details</b>
        <div class="field"><label for="name">Full name</label><input id="name" value="${user.name}"></div>
        <div class="field"><label for="email">Email</label><input id="email" value="${user.email}" disabled readonly><span class="hint">Email is the sign-in ID and cannot be changed here.</span></div>
        <div class="field"><label for="phone">Phone</label><input id="phone" value="${user.phone || ""}"></div>
        <div class="field"><label for="password">New password</label><input id="password" type="password" placeholder="leave blank to keep current">
          <input id="password_confirm" type="password" placeholder="confirm new password" style="margin-top:.4rem"></div>
        <span class="err hint" style="color:#b3541e" id="err-password"></span>
      </div>
      <div class="panel" style="margin-top:1rem">
        <b>Personal Details</b> <span class="hint">— private to you</span>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:1rem">
          <div class="field"><label for="age">Age</label><input id="age" type="number" min="5" max="120" value="${user.age ?? ""}"></div>
          <div class="field"><label for="dob">Date of birth</label><input id="dob" type="date" value="${user.dob || ""}"></div>
        </div>
        <div class="field"><label for="gender">Gender</label><select id="gender">
          <option value="prefer-not-to-say">Prefer not to say</option>
          ${GENDER_OPTIONS.map(([v, l]) => `<option value="${v}" ${user.gender === v ? "selected" : ""}>${l}</option>`).join("")}
        </select></div>
      </div>
      <div class="panel" style="margin-top:1rem">
        <b>Address</b> <span class="hint">— private to you, never shown publicly</span>
        <div class="field"><label for="home_address">Home address</label><textarea id="home_address" rows="2">${user.home_address || ""}</textarea></div>
        <div class="field"><label for="pin_code">PIN code</label><input id="pin_code" value="${user.pin_code || ""}" inputmode="numeric" maxlength="6"></div>
      </div>
      <div class="panel" style="margin-top:1rem">
        <b>Reading Interests</b> <span class="hint">— primary recommendation signal</span>
        <div class="chipbar" style="margin-top:.6rem" id="chips">
          ${GENRE_OPTIONS.map(([v, l]) => `<button type="button" class="chip" data-g="${v}" aria-pressed="${(user.interests || []).includes(v)}">${l}</button>`).join("")}
        </div>
        <div class="field" style="margin-top:.8rem"><label for="other_interest">Custom interest (for Other)</label>
          <input id="other_interest" value="${user.other_interest || ""}"></div>
      </div>
      <div class="panel soft" style="margin-top:1rem" data-f="__all__">
        <span class="err hint" style="color:#b3541e" id="err-__all__"></span>
        <div style="display:flex;gap:1rem;align-items:center;margin-top:.4rem">
          <button class="btn" type="submit" id="savebtn">Save preferences</button>
          <span class="hint" id="state"></span>
        </div>
      </div>
    </form>
  </section>`;

  const picks = new Set(user.interests || []);
  main.querySelectorAll("[data-g]").forEach((c) => c.addEventListener("click", () => {
    picks.has(c.dataset.g) ? picks.delete(c.dataset.g) : picks.add(c.dataset.g);
    c.setAttribute("aria-pressed", picks.has(c.dataset.g));
  }));
  main.querySelector("#logout").addEventListener("click", async () => {
    await authApi.logout();
    localStorage.removeItem("pustakamitra.profile.v1");
    window.location.href = "/index.html";
  });

  main.querySelector("#prefs").addEventListener("submit", async (e) => {
    e.preventDefault();
    ["err-__all__", "err-password"].forEach((id) => (main.querySelector("#" + id).parentElement.style.borderLeft = ""));
    const g = (id) => main.querySelector("#" + id).value.trim();
    const btn = main.querySelector("#savebtn");
    btn.disabled = true; btn.textContent = "Saving…";
    main.querySelector("#state").textContent = "";
    const patch = {
      name: g("name"), phone: g("phone"),
      age: parseInt(g("age"), 10) || undefined,
      dob: g("dob") || null,
      gender: g("gender"),
      home_address: g("home_address") || null,
      pin_code: g("pin_code") || null,
      interests: [...picks],
      other_interest: picks.has("other") ? g("other_interest") : null,
    };
    if (g("password")) { patch.password = main.querySelector("#password").value; patch.password_confirm = main.querySelector("#password_confirm").value; }
    try {
      const fresh = await authApi.updateMe(patch);
      const merged = { ...local, id: fresh.id, name: fresh.name, email: fresh.email, genres: fresh.interests, interests: fresh.interests, onboarded: true, persisted: true };
      localStorage.setItem("pustakamitra.profile.v1", JSON.stringify(merged));
      btn.textContent = "✓ Saved";
      main.querySelector("#state").textContent = "Synced to MongoDB at " + new Date().toLocaleTimeString();
      setTimeout(() => (btn.textContent = "Save preferences"), 1600);
    } catch (err) {
      btn.disabled = false; btn.textContent = "Save preferences";
      (main.querySelector("#err-" + (err.field || "__all__")) || main.querySelector("#err-__all__")).textContent = err.message;
    }
  });
}

mountChrome("Profile");
