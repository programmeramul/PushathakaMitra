// Discover Books — real Mongo catalogue: search, genre filter, pagination.
import { bookService } from "../services/api.js";
import { mountChrome, renderShelf } from "../ui.js";

const main = document.getElementById("main");
const params = new URLSearchParams(location.search);
const state = { q: params.get("q") || "", genre: params.get("genre") || "all", lang: "all", page: 1 };

main.innerHTML = `
<section class="section" style="margin-bottom:1rem">
  <h1>Discover Books</h1>
  <form class="searchbar" style="max-width:640px" id="sform">
    <input type="search" name="q" value="${state.q}" placeholder="Search by title or author…">
    <button class="btn" type="submit">Search</button>
  </form>
  <div class="chipbar" style="margin-top:1rem" id="genrechips">
    <button class="chip" data-g="all" aria-pressed="${state.genre === "all"}">All</button>
    ${bookService.genres.map((g) => `<button class="chip" data-g="${g[0]}" aria-pressed="${state.genre === g[0]}">${g[1]}<span class="kn">${g[2]}</span></button>`).join("")}
  </div>
  <div class="chipbar" style="margin-top:.6rem">
    ${["all", "Kannada", "English", "Bilingual"].map((l) => `<button class="chip" data-l="${l}" aria-pressed="${state.lang === l}">${l === "all" ? "Any language" : l}</button>`).join("")}
  </div>
</section>
<section>
  <p class="muted" id="count"></p>
  <div class="shelf" id="grid" style="margin-top:1rem"><p class="muted">Loading…</p></div>
  <p style="display:flex;gap:.8rem;justify-content:center;margin:1.5rem 0">
    <button class="btn secondary small" id="prev">← Previous</button>
    <button class="btn secondary small" id="next">Next →</button>
  </p>
</section>`;

const grid = main.querySelector("#grid");

async function run() {
  grid.innerHTML = `<p class="muted">Loading…</p>`;
  main.querySelector("#count").textContent = "";
  try {
    const res = await bookService.search({
      q: state.q, genre: state.genre, lang: state.lang, page: state.page, page_size: 24,
    });
    const pages = Math.max(1, Math.ceil(res.total / res.page_size));
    main.querySelector("#count").textContent =
      `${res.total} book${res.total === 1 ? "" : "s"} · page ${res.page} of ${pages}`;
    renderShelf(grid, res.items, {});
    main.querySelector("#prev").disabled = res.page <= 1;
    main.querySelector("#next").disabled = res.page >= pages;
  } catch (e) {
    grid.innerHTML = `<p class="muted">Could not load the catalogue — no sample data is shown instead. (${e.message})</p>`;
  }
}

main.querySelectorAll("[data-g]").forEach((c) => c.addEventListener("click", () => {
  state.genre = c.dataset.g; state.page = 1;
  main.querySelectorAll("[data-g]").forEach((x) => x.setAttribute("aria-pressed", x.dataset.g === state.genre));
  run();
}));
main.querySelectorAll("[data-l]").forEach((c) => c.addEventListener("click", () => {
  state.lang = c.dataset.l; state.page = 1;
  main.querySelectorAll("[data-l]").forEach((x) => x.setAttribute("aria-pressed", x.dataset.l === state.lang));
  run();
}));
main.querySelector("#sform").addEventListener("submit", (e) => {
  e.preventDefault(); state.q = e.target.q.value; state.page = 1; run();
});
main.querySelector("#prev").addEventListener("click", () => { state.page -= 1; run(); });
main.querySelector("#next").addEventListener("click", () => { state.page += 1; run(); });

run();
mountChrome("Discover");
