// Book details — only sourced fields; honest gaps (no rating, no holdings claim).
import { bookService, profileService } from "../services/api.js";
import { mountChrome, renderShelf, bookCover } from "../ui.js";

const main = document.getElementById("main");
const id = new URLSearchParams(location.search).get("id");
const book = id ? await bookService.getBook(id).catch((e) => ({ error: e })) : null;

if (!book || book.error) {
  const msg = book && book.error ? book.error.message : "";
  main.innerHTML = `<section class="section"><h1>${book && book.error ? "Could not load book" : "Book not found"}</h1>
    <p class="muted">${msg || `No record “${id}” in the catalogue.`}
    <a href="/pages/discover.html">Back to Discover</a></p></section>`;
} else {
  const saved = profileService.savedBooks().includes(book.id);
  const tags = [
    book.language ? `<span class="tag">${book.language}</span>` : "",
    ...(book.subject_slugs || []).map((s) => `<span class="tag">${s.replace(/-/g, " ")}</span>`),
  ].join(" ");
  main.innerHTML = `
  <section class="section" style="display:grid;grid-template-columns:220px 1fr;gap:2rem;align-items:start">
    <a href="#" class="bookcard" style="pointer-events:none">${bookCover(book, { wide: true })}</a>
    <div>
      <h1>${book.title}</h1>
      <p><b>${(book.authors || []).join(", ") || "Author not recorded"}</b>${book.year ? " · " + book.year : ""}</p>
      <p style="display:flex;gap:.4rem;flex-wrap:wrap;margin:.5rem 0 1rem">${tags}</p>
      ${book.description
        ? `<p style="max-width:60ch">${book.description}</p>`
        : `<p class="muted">No description available from the source for this record.</p>`}
      <div class="panel soft" style="margin:1rem 0 1.5rem;border-left:4px solid var(--gold)">
        <b>Provenance</b>
        <p class="muted" style="margin-top:.3rem">Metadata from ${book.source}
        ${book.source_id ? `<a href="https://openlibrary.org${book.source_id}" target="_blank" rel="noopener">${book.source_id} ↗</a>` : ""}.
        Library availability not yet verified.</p>
      </div>
      <div style="display:flex;gap:.8rem;flex-wrap:wrap">
        <a class="btn" id="findlibs" href="/pages/libraries.html?book=${book.id}">Find in Bengaluru Libraries</a>
        <button class="btn secondary" id="savebtn">${saved ? "★ Saved — remove" : "Save to my shelf"}</button>
      </div>
    </div>
  </section>
  <section class="section">
    <h2>Similar books <span class="muted" style="font-size:.85rem">· shared categories</span></h2>
    <div class="shelf" style="margin-top:1rem" id="similar"></div>
  </section>`;
  if (book.similar && book.similar.length) {
    renderShelf(main.querySelector("#similar"), book.similar, {});
  }
  main.querySelector("#savebtn").addEventListener("click", () => {
    profileService.toggleSavedBook(book.id);
    main.querySelector("#savebtn").textContent = profileService.savedBooks().includes(book.id) ? "★ Saved — remove" : "Save to my shelf";
  });
}

mountChrome("");
