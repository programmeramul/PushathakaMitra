// Library search results — branch, address, catalogue link, EXPLICIT mock labels.
// Availability is fixture data and every branch name/hold is tagged [MOCK];
// nothing here may be published as real Bengaluru library holdings.
import { libraryService } from "../services/api.js";
import { mountChrome, bookCover } from "../ui.js";

const main = document.getElementById("main");
const bookId = new URLSearchParams(location.search).get("book");
const book = bookId ? await (await import("../services/api.js")).bookService.getBook(bookId) : null;
const libs = await (book ? libraryService.findLibrariesForBook(book.id) : libraryService.listLibraries());

main.innerHTML = `
<section class="section" style="margin-bottom:1rem">
  <h1>Find in Bengaluru Libraries</h1>
  ${book ? `<div style="display:flex;gap:1rem;align-items:center;margin-top:1rem">
      <a style="width:64px;display:block;pointer-events:none" class="bookcard">${bookCover(book)}</a>
      <div><b class="serif" style="font-size:1.05rem;color:var(--green-700)">${book.title}</b><br><span class="muted">${book.author}</span></div>
    </div>` : `<p class="muted">Showing all sample branches. Pick a book from <a href="/pages/discover.html">Discover</a> to see holdings.</p>`}
  <p class="mock-note" style="margin-top:1rem">⚠ Demo data only — every branch, address, catalogue link and availability status below is a <b>[MOCK]</b> fixture. No real Bengaluru library holdings are claimed anywhere in this app.</p>
</section>
<section style="max-width:760px">
  <div class="panel">
    ${libs.length ? libs.map((l) => `
      <div class="librow">
        <div class="branch">${l.branch}<br><span class="meta muted" style="font-weight:400;font-size:.85rem" class="muted">${l.address}</span></div>
        <div><a href="${l.catalogue}" target="_blank" rel="noopener">Catalogue ↗</a></div>
        ${book ? `<span class="status ${l.status}">${l.statusLabel}</span>` : ""}
      </div>`).join("") : "<p class='muted'>No fixture branch reports holding this title — that is a real 'not found', not a fake in-stock claim.</p>"}
  </div>
</section>`;

mountChrome("");
