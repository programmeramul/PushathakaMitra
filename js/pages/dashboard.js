// Dashboard — recommendations with explanations + reading goal progress.
import { recommendationService, profileService, bookService } from "../services/api.js";
import { mountChrome, renderShelf, bookCover } from "../ui.js";

const main = document.getElementById("main");
const p = await profileService.current();
const recs = await recommendationService.forReader(p);
const books = await bookService.listBooks();
const names = (ids) => ids.map((g) => (bookService.genres.find((x) => x.id === g) || {}).en).filter(Boolean).join(", ");

const goalBooks = 6, read = Math.min(p.saved.length, goalBooks), pct = Math.round((read / goalBooks) * 100);

main.innerHTML = `
<section class="section">
  <h1>Namaskara, ${p.name} 🙏</h1>
  <p class="muted">Followed genres: ${names(p.genres) || "none yet"} · Goal: read more</p>
</section>

<section class="section">
  <h2>Your next book, matched</h2>
  <p class="mock-note">[MOCK] recommendations — order by followed-genre scoring today; Groq-generated explanations arrive via the service layer.</p>
  <div class="shelf" style="margin-top:1rem" id="recs"></div>
</section>

<section class="section" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:1rem">
  <div class="panel" style="display:flex;gap:1rem;align-items:center">
    <div style="width:84px;height:84px;flex:none;border-radius:50%;background:conic-gradient(var(--gold) ${pct}%, var(--ivory-400) 0);display:grid;place-items:center">
      <span style="width:66px;height:66px;border-radius:50%;background:#fffdf8;display:grid;place-items:center;font-weight:700;color:var(--green)">${pct}%</span>
    </div>
    <div><h2 style="margin-bottom:.3rem">Reading goal</h2><span class="muted">${read} of ${goalBooks} books saved/read this month</span></div>
  </div>
  <div class="panel"><h2 style="margin-bottom:.3rem">Quick links</h2>
    <div class="chipbar" style="margin-top:.6rem">
      <a class="chip" href="/pages/discover.html">Discover books</a>
      <a class="chip" href="/pages/saved.html">Saved books</a>
      <a class="chip" href="/pages/libraries.html?book=">Bengaluru libraries</a>
      ${p.onboarded ? "" : '<a class="chip" href="/pages/onboarding.html">Finish onboarding</a>'}
    </div>
  </div>
</section>`;

renderShelf(main.querySelector("#recs"), recs, { reason: true });
mountChrome("Dashboard");
