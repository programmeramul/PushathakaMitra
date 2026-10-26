// Book details + similar row + Find-in-libraries action.
import { bookService, profileService, libraryService } from "../services/api.js";
import { mountChrome, renderShelf, bookCover } from "../ui.js";

const main = document.getElementById("main");
const id = new URLSearchParams(location.search).get("id");
const book = await bookService.getBook(id);

if (!book) {
  main.innerHTML = `<section class="section"><h1>Book not found</h1><p class="muted">Unknown book id “${id}” in the fixture set. <a href="/pages/discover.html">Back to Discover</a></p></section>`;
} else {
  const saved = profileService.savedBooks().includes(book.id);
  const genres = book.genres.map((g) => `<span class="tag">${(bookService.genres.find((x) => x.id === g) || {}).en}</span>`).join(" ");
  main.innerHTML = `
  <section class="section" style="display:grid;grid-template-columns:220px 1fr;gap:2rem;align-items:start">
    <a href="#" class="bookcard" style="pointer-events:none">${bookCover(book)}</a>
    <div>
      <h1>${book.title}</h1>
      ${book.titleEn ? `<p class="muted serif" style="font-size:1.1rem">${book.titleEn}</p>` : ""}
      <p><b>${book.author}</b> · ${book.year} · <span class="tag gold">★ ${book.rating.toFixed(1)}</span></p>
      <p style="display:flex;gap:.4rem;flex-wrap:wrap;margin:.5rem 0 1rem">${genres}<span class="tag">${book.language}</span></p>
      <p style="max-width:60ch">${book.appReason}</p>
      <div class="panel soft" style="margin:1rem 0 1.5rem;border-left:4px solid var(--gold)">
        <b>Why we picked this for you</b>
        <p class="muted" style="margin-top:.3rem">${book.appReason} <span class="mock-note">[MOCK] — generated-from-genre-score today; Groq explanation lands here later.</span></p>
      </div>
      <div style="display:flex;gap:.8rem;flex-wrap:wrap">
        <a class="btn" id="findlibs" href="/pages/libraries.html?book=${book.id}">Find in Bengaluru Libraries</a>
        <button class="btn secondary" id="savebtn">${saved ? "★ Saved — remove" : "Save to my shelf"}</button>
      </div>
    </div>
  </section>
  <section class="section">
    <h2>Similar books</h2>
    <div class="shelf" style="margin-top:1rem" id="similar"></div>
  </section>`;
  renderShelf(main.querySelector("#similar"), book.similar || [], { reason: true });
  main.querySelector("#savebtn").addEventListener("click", () => {
    profileService.toggleSavedBook(book.id);
    main.querySelector("#savebtn").textContent = profileService.savedBooks().includes(book.id) ? "★ Saved — remove" : "Save to my shelf";
  });
}

mountChrome("");
