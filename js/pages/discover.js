// Discover Books — search, genre filter, language filter, availability toggle.
import { bookService } from "../services/api.js";
import { navbar, footer, renderShelf, bookCover } from "../ui.js";

const main = document.getElementById("main");
const params = new URLSearchParams(location.search);
const state = { q: params.get("q") || "", genre: params.get("genre") || "all", lang: "all", availableOnly: false };

main.innerHTML = `
<section class="section" style="margin-bottom:1rem">
  <h1>Discover Books</h1>
  <form class="searchbar" style="max-width:640px" id="sform">
    <input type="search" name="q" value="${state.q}" placeholder="Search by title or author…">
    <button class="btn" type="submit">Search</button>
  </form>
  <div class="chipbar" style="margin-top:1rem" id="genrechips">
    <button class="chip" data-g="all" aria-pressed="${state.genre === "all"}">All</button>
    ${bookService.genres.map((g) => `<button class="chip" data-g="${g.id}" aria-pressed="${state.genre === g.id}">${g.en}<span class="kn">${g.kn}</span></button>`).join("")}
  </div>
  <div class="chipbar" style="margin-top:.6rem">
    ${["all", "Kannada", "English", "Bilingual"].map((l) => `<button class="chip" data-l="${l}" aria-pressed="${state.lang === l}">${l === "all" ? "Any language" : l}</button>`).join("")}
    <button class="chip" id="availbtn" aria-pressed="${state.availableOnly}">In Bengaluru libraries only</button>
  </div>
</section>
<section>
  <p class="muted" id="count"></p>
  <div class="shelf" id="grid" style="margin-top:1rem"></div>
</section>`;

async function run() {
  const books = await bookService.search(state.q, state);
  renderShelf(main.querySelector("#grid"), books, { reason: true });
  main.querySelector("#count").textContent = `${books.length} book${books.length === 1 ? "" : "s"} · ${state.genre !== "all" ? bookService.genres.find((g) => g.id === state.genre).en : "all genres"} · [MOCK] fixtures`;
}

main.querySelectorAll("[data-g]").forEach((c) => c.addEventListener("click", () => {
  state.genre = c.dataset.g; document.getElementById("sform").q.value = state.q;
  main.querySelectorAll("[data-g]").forEach((x) => x.setAttribute("aria-pressed", x.dataset.g === state.genre));
  run();
}));
main.querySelectorAll("[data-l]").forEach((c) => c.addEventListener("click", () => {
  state.lang = c.dataset.l;
  main.querySelectorAll("[data-l]").forEach((x) => x.setAttribute("aria-pressed", x.dataset.l === state.lang));
  run();
}));
main.querySelector("#availbtn").addEventListener("click", (e) => {
  state.availableOnly = !state.availableOnly;
  e.currentTarget.setAttribute("aria-pressed", state.availableOnly);
  // Only demo books carry mock library holdings, so filter to those with libCount.
  run();
});
main.querySelector("#sform").addEventListener("submit", (e) => { e.preventDefault(); state.q = e.target.q.value; run(); });

run();
navbar("Discover"); footer();
