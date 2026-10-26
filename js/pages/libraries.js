// Library page — HONEST state: no verified holdings source integrated yet.
// We never display fictional branches or availability statuses.
import { bookService } from "../services/api.js";
import { mountChrome, bookCover } from "../ui.js";

const main = document.getElementById("main");
const bookId = new URLSearchParams(location.search).get("book");
const book = bookId ? await bookService.getBook(bookId).catch(() => null) : null;

main.innerHTML = `
<section class="section" style="margin-bottom:1rem">
  <h1>Find in Bengaluru Libraries</h1>
  ${book ? `<div style="display:flex;gap:1rem;align-items:center;margin-top:1rem">
      <a style="width:64px;display:block;pointer-events:none" class="bookcard">${bookCover(book, { wide: true })}</a>
      <div><b class="serif" style="font-size:1.05rem;color:var(--green-700)">${book.title}</b><br><span class="muted">${(book.authors || []).join(", ")}</span></div>
    </div>` : ""}
</section>
<section style="max-width:760px">
  <div class="panel">
    <b>Library availability not yet verified.</b>
    <p class="muted" style="margin-top:.5rem">PustakaMitra AI has not yet integrated a real
    Bengaluru library catalogue API, so we cannot tell you whether any branch holds this
    title — and we won't guess. Once a verified holdings source is connected, per-branch
    availability will appear here.</p>
    <p class="muted" style="margin-top:.5rem">In the meantime, search WorldCat for nearby
    copies: <a href="https://www.worldcat.org/search?q=${encodeURIComponent(book ? book.title : "")}"
    target="_blank" rel="noopener">WorldCat ↗</a></p>
  </div>
</section>`;

mountChrome("");
