// Multi-step onboarding: interests → genres → goals → skill level.
// Goal + skill are stored but only emojis/UI today; Groq tailors reasons later.
import { bookService } from "../services/api.js";
import { authApi, requireAuth } from "../services/auth.js";
import { mountChrome } from "../ui.js";

const main = document.getElementById("main");

// this page is for AUTHENTICATED users only — server decides, no mock user
const user = await requireAuth();
const p0 = user || {};
const state = { genres: p0.interests || [], goal: p0.goal || "read-more", level: p0.level || "", lang: p0.language || "Bilingual" };

const GOALS = [
  ["read-more", "Read more, more often", "📚 Ishtu vaina ishtu pustaka"],
  ["finish-classics", "Finish Kannada classics", "🕌"],
  ["focus", "Deep focus, fewer distractions", "🧘"],
  ["explore", "Explore something entirely new", "🧭"],
];
const LEVELS = [
  ["casual", "Casual reader", "1–2 books a year"],
  ["regular", "Regular reader", "A book a month"],
  ["voracious", "Voracious", "Always have twenty on the go"],
];

function stepsHTML(step) {
  const labels = ["Interests", "Genres", "Goals", "Level"];
  return `<div class="steps">${labels.map((l, i) =>
    `<span class="dot${i < step ? " done" : i === step ? " active" : ""}" style="flex:1"></span>`).join("")}
  <span class="hint" style="flex:none;padding-left:.5rem">Step ${step + 1} of 4 — ${labels[step]}</span></div>`;
}

let step = p0.onboarded ? 0 : 0;

function paint() {
  let body = "";
  if (step === 0) body = `
    <h1>What do you like to read about?</h1>
    <p class="muted">Pick as many as you want — you can change these anytime.</p>
    <div class="panel soft" style="padding:1.25rem">
      <div class="chipbar" id="chips">${bookService.genres.map((g) =>
        `<button class="chip" data-g="${g.id}" aria-pressed="${state.genres.includes(g.id)}">${g.en}<span class="kn">${g.kn}</span></button>`).join("")}</div>
    </div>`;
  else if (step === 1) body = `
    <h1>Which language should we match?</h1>
    <div class="chipbar">${["Kannada", "English", "Bilingual"].map((l) =>
      `<button class="chip" data-l="${l}" aria-pressed="${state.lang === l}">${l}</button>`).join("")}</div>`;
  else if (step === 2) body = `
    <h1>What's your reading goal?</h1>
    <div class="shelf" style="grid-template-columns:repeat(auto-fill,minmax(220px,1fr));margin-top:1rem">
      ${GOALS.map(([id, t, s]) => `<button class="chip" data-goal="${id}" aria-pressed="${state.goal === id}" style="text-align:left;padding:1rem;border-radius:12px">
        <b>${t}</b><br><span class="muted" style="font-weight:400">${s}</span></button>`).join("")}
    </div>`;
  else body = `
    <h1>How often do you read?</h1>
    <div class="chipbar" style="flex-direction:column;align-items:flex-start">
      ${LEVELS.map(([id, t, s]) => `<button class="chip" data-level="${id}" aria-pressed="${state.level === id}"><b>${t}</b> · <span class="muted">${s}</span></button>`).join("")}</div>
    <div class="panel soft" style="margin-top:1rem">Finished! Hit <b>Save &amp; open my shelf</b> — your dashboard is ready.</div>`;

  main.innerHTML = `
  <section style="max-width:680px;margin:var(--space-4) auto">
    ${stepsHTML(step)}
    ${body}
    <div style="display:flex;gap:1rem;margin-top:var(--space-3)">
      <button class="btn secondary" id="back" ${step === 0 ? "disabled" : ""}>Back</button>
      <button class="btn" id="next">${step === 3 ? "Save &amp; open my shelf" : "Continue"}</button>
    </div>
  </section>`;
  wire();
}

function wire() {
  main.querySelectorAll("[data-g]").forEach((c) => c.addEventListener("click", () => {
    const g = c.dataset.g;
    state.genres = state.genres.includes(g) ? state.genres.filter((x) => x !== g) : [...state.genres, g];
    c.setAttribute("aria-pressed", state.genres.includes(g));
  }));
  main.querySelectorAll("[data-l]").forEach((c) => c.addEventListener("click", () => { state.lang = c.dataset.l; paint(); }));
  main.querySelectorAll("[data-goal]").forEach((c) => c.addEventListener("click", () => { state.goal = c.dataset.goal; paint(); }));
  main.querySelectorAll("[data-level]").forEach((c) => c.addEventListener("click", () => { state.level = c.dataset.level; paint(); }));
  main.querySelector("#back").addEventListener("click", () => { step = Math.max(0, step - 1); paint(); });
  main.querySelector("#next").addEventListener("click", async () => {
    if (step === 0 && !state.genres.length) { alert("Pick at least one genre to continue"); return; }    if (step === 3) {
      // persist onboarding to the AUTHENTICATED user's Mongo document
      // mock chip ids map onto the backend's canonical genre vocabulary
      const backendGenres = state.genres.map((g) => (g === "kannada" ? "kannada-literature" : g));
      const local = JSON.parse(localStorage.getItem("pustakamitra.profile.v1") || "{}");
      try {
        await authApi.updateMe({
          interests: backendGenres,
          goal: state.goal, level: state.level, language: state.lang,
        });
        save({ ...user, interests: backendGenres, genres: backendGenres, goal: state.goal, level: state.level, lang: state.lang, onboarded: true, persisted: true });
        localStorage.setItem("onboarding.other", "");
      } catch (err) {
        alert(err.message || "Could not save preferences"); return;
      }
      window.location.href = "/pages/discover.html";
      return;
    }
    step += 1; paint();
  });
}

paint();
mountChrome("Profile");
