// Saved Books page — browser-local shelf of real catalogue records.
import { bookService, profileService } from "../services/api.js";
import { requireAuth } from "../services/auth.js";
import { mountChrome, renderShelf } from "../ui.js";

const main = document.getElementById("main");
const user = await requireAuth();
if (user) {
  const savedIds = profileService.savedBooks();
  const all = await bookService.listBooks().catch(() => []);
  const saved = all.filter((b) => savedIds.includes(b.id));
  const gone = savedIds.filter((id) => !all.some((b) => b.id === id));

  main.innerHTML = `
  <section class="section">
    <h1>Saved Books</h1>
    ${saved.length ? `<div class="shelf" style="margin-top:1rem" id="grid"></div>`
      : `<p class="muted">Your shelf is empty. Wander through <a href="/pages/discover.html">Discover</a> and press <b>Save to my shelf</b>.</p>`}
    ${gone.length ? `<p class="muted" style="font-size:.85rem">${gone.length} saved record${gone.length === 1 ? "" : "s"} no longer in the catalogue and hidden.</p>` : ""}
  </section>`;

  if (saved.length) renderShelf(main.querySelector("#grid"), saved, {});
  mountChrome("Saved");
}
