// Landing page — brand, hero, search, genre chips and how-it-works. No book
// cards here: browsing lives on Discover, recommendations after onboarding.
import { bookService } from "../services/api.js";
import { mountChrome } from "../ui.js";

const main = document.getElementById("main");

main.innerHTML = `
<section class="section" style="text-align:center">
  <p class="tag gold" style="margin-bottom:1rem">ಪುಸ್ತಕಮಿತ್ರ · PustakaMitra AI</p>
  <h1>Nimma Interest,<br>Nimma Next Book!</h1>
  <p class="muted" style="max-width:560px;margin:1rem auto 1.5rem">
    Personalised book discovery in Kannada &amp; English, for Bengaluru readers —
    grounded in a real, source-traceable catalogue.
  </p>
  <form class="searchbar" style="max-width:560px;margin:0 auto;text-align:left" action="/pages/discover.html">
    <input type="search" name="q" placeholder="Search books by title or author…" aria-label="Search books">
    <button class="btn" type="submit">Search</button>
  </form>
</section>

<section class="section">
  <h2>Browse by genre</h2>
  <div class="chipbar" style="margin-top:1rem" id="genrechips"></div>
</section>

<section class="section" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:1rem">
  <div class="panel"><h2>🎯 How it works</h2><p class="muted">Sign up, complete a 4-step reading-interest onboarding, and we match your interests against real catalogue records — with a short reason for every pick.</p></div>
  <div class="panel"><h2>📖 Traceable data</h2><p class="muted">Every record shows its source — Open Library work IDs — so you can verify anything we display.</p></div>
  <div class="panel"><h2>📚 Library next</h2><p class="muted">Physical Bengaluru holdings are a planned integration — we never guess availability.</p></div>
</section>`;

document.getElementById("genrechips").innerHTML = bookService.genres
  .map((g) => `<a class="chip" href="/pages/discover.html?genre=${g[0]}" style="text-decoration:none">${g[1]}<span class="kn">${g[2]}</span></a>`)
  .join("");

mountChrome("Home");
