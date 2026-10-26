// Landing page — hero + search + featured genres + popular books (mock data).
import { bookService, recommendationService } from "../services/api.js";
import { navbar, footer, renderShelf } from "../ui.js";

const main = document.getElementById("main");

const search = `
<section class="section" style="text-align:center">
  <p class="tag gold" style="margin-bottom:1rem">ಪುಸ್ತಕಮಿತ್ರ · PustakaMitra AI</p>
  <h1>Nimma Interest,<br>Nimma Next Book!</h1>
  <p class="muted" style="max-width:560px;margin:1rem auto 1.5rem">
    Personalised book recommendations in Kannada &amp; English — plus where to find
    them in Bengaluru libraries.
  </p>
  <form class="searchbar" style="max-width:560px;margin:0 auto;text-align:left" action="/pages/discover.html">
    <input type="search" name="q" placeholder="Search books by title or author…" aria-label="Search books">
    <button class="btn" type="submit">Search</button>
  </form>
</section>`;

const genreSection = `
<section class="section">
  <h2>Featured genres</h2>
  <div class="chipbar" style="margin-top:1rem" id="genrechips"></div>
</section>`;

const popularSection = `
<section class="section">
  <div style="display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap">
    <h2>Popular with readers like you</h2>
    <a href="/pages/discover.html">See all books →</a>
  </div>
  <p class="mock-note">Mock data — books, ratings and availability are demo fixtures.</p>
  <div class="shelf" style="margin-top:1rem" id="popular"></div>
</section>`;

const pitch = `
<section class="section" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:1rem">
  <div class="panel"><h2>📖 Told why</h2><p class="muted">Every recommendation explains itself — matched to your genres, language and reading goals.</p></div>
  <div class="panel"><h2>📚 Bengaluru-first</h2><p class="muted">Find which branch can hand you the book today, with clearly-labelled availability.</p></div>
  <div class="panel"><h2>🗣 Kannada &amp; English</h2><p class="muted">ಕನ್ನಡ ಸಾಹಿತ್ಯ sits beside global fiction — in your language.</p></div>
</section>`;

main.innerHTML = search + genreSection + popularSection + pitch;

// Wire interactive pieces.
renderShelf(document.getElementById("popular"), await recommendationService.forReader(null), { reason: true });

const chipbar = document.getElementById("genrechips");
chipbar.innerHTML = bookService.genres
  .map((g) => `<a class="chip" href="/pages/discover.html?genre=${g.id}" style="text-decoration:none">${g.en}<span class="kn">${g.kn}</span></a>`)
  .join("");

navbar("Home"); footer();
