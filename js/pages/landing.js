// Landing page — hero, real catalogue browsing, genre entry points.
// Section titles reflect actual data; never claims popularity or personal
//ization without evidence (AI picks are labelled only when Groq succeeded).
import { bookService, recommendationService, load } from "../services/api.js";
import { mountChrome, renderShelf } from "../ui.js";

const main = document.getElementById("main");

const search = `
<section class="section" style="text-align:center">
  <p class="tag gold" style="margin-bottom:1rem">ಪುಸ್ತಕಮಿತ್ರ · PustakaMitra AI</p>
  <h1>Nimma Interest,<br>Nimma Next Book!</h1>
  <p class="muted" style="max-width:560px;margin:1rem auto 1.5rem">
    Book discovery for Kannada &amp; English readers in Bengaluru — grounded in a
    real, source-traceable catalogue.
  </p>
  <form class="searchbar" style="max-width:560px;margin:0 auto;text-align:left" action="/pages/discover.html">
    <input type="search" name="q" placeholder="Search books by title or author…" aria-label="Search books">
    <button class="btn" type="submit">Search</button>
  </form>
</section>`;

const browse = (title) => `
<section class="section">
  <div style="display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap">
    <h2 id="shelftitle">${title}</h2>
    <a href="/pages/discover.html">See all books →</a>
  </div>
  <div class="shelf" style="margin-top:1rem" id="shelf"><p class="muted">Loading catalogue…</p></div>
</section>`;

main.innerHTML = search + browse("Discover books") + `
<section class="section">
  <h2>Browse by genre</h2>
  <div class="chipbar" style="margin-top:1rem" id="genrechips"></div>
</section>

<section class="section" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:1rem">
  <div class="panel"><h2>📖 Traceable data</h2><p class="muted">Every record shows its source — Open Library work IDs — so you can verify anything we display.</p></div>
  <div class="panel"><h2>🗣 Kannada &amp; English</h2><p class="muted">ಕನ್ನಡ ಸಾಹಿತ್ಯ sits beside global fiction — in your language.</p></div>
  <div class="panel"><h2>📚 Library next</h2><p class="muted">Physical Bengaluru holdings are a planned integration — we never guess availability.</p></div>
</section>`;

try {
  const local = load();
  let first = "Discover books", items = null, engine = "";
  if (local.id) {
    // logged in: try real AI recommendations; only label them as AI if they worked
    try {
      const rec = await recommendationService.forReader();
      if (rec.engine === "groq" && rec.items.length) {
        items = rec.items; first = "Recommended for your interests"; engine = "groq";
      }
    } catch { /* fall through to plain browse */ }
  }
  if (!items) {
    const p = await bookService.search({ page_size: 12 });
    if (!p.items.length) {
      document.getElementById("shelf").innerHTML = `<p class="muted">The catalogue is
        empty right now. It is imported from Open Library by an admin sync
        (<code>POST /api/catalog/sync</code>) — nothing sample-based is shown instead.</p>`;
    } else {
      items = p.items;
    }
  }
  if (items) {
    document.getElementById("shelftitle").textContent = first;
    renderShelf(document.getElementById("shelf"), items, { reason: !!engine, engine });
  }

  document.getElementById("genrechips").innerHTML = bookService.genres
    .map((g) => `<a class="chip" href="/pages/discover.html?genre=${g[0]}" style="text-decoration:none">${g[1]}<span class="kn">${g[2]}</span></a>`)
    .join("");
} catch (e) {
  document.getElementById("shelf").innerHTML =
    `<p class="muted">Could not reach the book service — no sample data is shown instead. (${e.message})</p>`;
}

mountChrome("Home");
