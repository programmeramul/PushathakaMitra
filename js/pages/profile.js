// Profile & editable preferences — re-uses onboarding steps inline.
import { profileService, bookService } from "../services/api.js";
import { navbar, footer } from "../ui.js";

const main = document.getElementById("main");
const p = await profileService.current();

main.innerHTML = `
<section class="section" style="max-width:640px">
  <h1>Profile &amp; preferences</h1>
  <form id="prefs" style="margin-top:1rem">
    <div class="panel">
      <div class="field"><label for="name">Name</label><input id="name" value="${p.name}"></div>
      <div class="field"><label for="email">Email</label><input id="email" type="email" value="${p.email}"></div>
    </div>
    <div class="panel" style="margin-top:1rem">
      <b>Followed genres</b>
      <div class="chipbar" style="margin-top:.6rem" id="chips">
        ${bookService.genres.map((g) => `<button type="button" class="chip" data-g="${g.id}" aria-pressed="${p.genres.includes(g.id)}">${g.en}<span class="kn">${g.kn}</span></button>`).join("")}
      </div>
      <div class="field" style="margin-top:1rem"><label for="level">Reading level</label>
        <select id="level">
          <option value="casual" ${p.level === "casual" ? "selected" : ""}>Casual reader</option>
          <option value="regular" ${p.level === "regular" ? "selected" : ""}>Regular reader</option>
          <option value="voracious" ${p.level === "voracious" ? "selected" : ""}>Voracious</option>
        </select></div>
      <div class="field"><label for="lang">Preferred language</label>
        <select id="lang">
          ${["Kannada", "English", "Bilingual"].map((l) => `<option value="${l}" ${p.lang === l ? "selected" : ""}>${l}</option>`).join("")}
        </select></div>
      <button class="btn" type="submit">Save preferences</button>
      <span class="hint" style="margin-left:1rem">[MOCK] profile stored in localStorage — moves to MongoDB account later.</span>
    </div>
  </form>
  <p style="margin-top:2rem"><a href="/pages/onboarding.html">Run the onboarding wizard again →</a></p>
</section>`;

const state = { genres: [...p.genres] };
main.querySelectorAll("[data-g]").forEach((c) => c.addEventListener("click", () => {
  const g = c.dataset.g;
  state.genres = state.genres.includes(g) ? state.genres.filter((x) => x !== g) : [...state.genres, g];
  c.setAttribute("aria-pressed", state.genres.includes(g));
}));
main.querySelector("#prefs").addEventListener("submit", (e) => {
  e.preventDefault();
  profileService.save({
    name: main.querySelector("#name").value.trim(),
    email: main.querySelector("#email").value.trim(),
    genres: state.genres,
    level: main.querySelector("#level").value,
    lang: main.querySelector("#lang").value,
  });
  alert("[+] Preferences saved");
});
navbar("Profile"); footer();
