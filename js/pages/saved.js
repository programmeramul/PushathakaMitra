// Saved Books page — from local profile store (mock persistence).
import { bookService, profileService } from "../services/api.js";
import { requireAuth } from "../services/auth.js";
import { mountChrome, renderShelf } from "../ui.js";

const main = document.getElementById("main");
const user = await requireAuth();
if (user) {
const savedIds = profileService.savedBooks();
const all = await bookService.listBooks();
const saved = all.filter((b) => savedIds.includes(b.id));

main.innerHTML = `
<section class="section">
  <h1>Saved Books</h1>
  ${saved.length ? `<div class="shelf" style="margin-top:1rem" id="grid"></div>`
  : `<p class="muted">Your shelf is empty. Wander through <a href="/pages/discover.html">Discover</a> and press <b>Save to my shelf</b>.</p>`}
</section>`;

if (saved.length) renderShelf(main.querySelector("#grid"), saved, { reason: true });
mountChrome("Saved"); footer && null;
}
