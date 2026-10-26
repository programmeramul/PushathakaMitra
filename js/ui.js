// Shared UI helpers: cover placeholder (restrained, clearly "unavailable"),
// shelf renderer, nav/footer injection. ES module shared by every page.
import { load, profileService, libraryService } from "./services/api.js";

// missing-cover placeholder: flat neutral tile with the title, NOT a fake cover
export function bookCover(b, { wide = false } = {}) {
  const img = typeof b === "object" && b.cover_url;
  if (img) {
    return `<span class="cover-wrap" style="display:block;background:#e9e2d3">
      <img src="${b.cover_url}" alt="Cover of ${b.title}" loading="lazy"
           style="width:100%;height:100%;object-fit:cover;display:block"
           onerror="this.replaceWith(Object.assign(document.createElement('span'),{textContent:'Cover unavailable',className:'cover-none'}))">
    </span>`;
  }
  return `<span class="cover-wrap" style="display:block;background:#e9e2d3;display:grid;place-items:center;text-align:center;color:#5a5245;font-family:var(--serif);font-size:${wide ? "1rem" : ".75rem"};padding:12%;line-height:1.4">
    <span>${b.title}<br><small style="opacity:.75">Cover unavailable</small></span>
  </span>`;
}

export function bookCard(b, { reason = false, engine = "" } = {}) {
  const saved = profileService.savedBooks().includes(b.id);
  const tags = [
    b.language ? `<span class="tag">${b.language}</span>` : "",
    ...(b.subject_slugs || []).slice(0, 2).map((s) =>
      `<span class="tag">${s.replace(/-/g, " ")}</span>`),
  ].join("");
  const src = b.source === "openlibrary"
    ? `<span class="meta" style="font-size:.7rem">Source: Open Library · ${b.source_id}</span>` : "";
  return `<a class="bookcard" href="/pages/book.html?id=${b.id}" data-id="${b.id}">
    ${bookCover(b)}
    <span class="info">
      <span class="title">${b.title}</span>
      <span class="meta">${(b.authors || []).join(", ") || "Author not recorded"}${b.year ? " · " + b.year : ""}</span>
      <span style="display:flex;gap:.35rem;flex-wrap:wrap">${tags}</span>
      ${reason ? `<span class="hint">${engine === "groq" ? "✦ " : ""}${b.reason}</span>` : ""}
      <span class="meta">Library availability not yet verified.</span>
      ${src}
    </span>
    <span class="savebtn" data-save="${b.id}" role="button" title="${saved ? "Remove from shelf" : "Save to my shelf"}">${saved ? "★" : "☆"}</span>
  </a>`;
}

export function renderShelf(el, books, { reason = false, engine = "" } = {}) {
  if (!books.length) {
    el.innerHTML = `<p class="muted">No records found. Catalogue may still be importing — try the sync admin endpoint.</p>`;
    return;
  }
  el.innerHTML = books.map((b) => bookCard(b, { reason, engine })).join("");
  el.querySelectorAll("[data-save]").forEach((btn) => btn.addEventListener("click", (e) => {
    e.preventDefault(); e.stopPropagation();
    profileService.toggleSavedBook(btn.dataset.save);
    btn.textContent = profileService.savedBooks().includes(btn.dataset.save) ? "★" : "☆";
    btn.title = btn.textContent === "★" ? "Remove from shelf" : "Save to my shelf";
  }));
}

export function navbar(active) {
  const p = load();
  const links = [
    ["Home", "/index.html"],
    ["Discover", "/pages/discover.html"], ["Saved", "/pages/saved.html"],
    ["Profile", "/pages/profile.html"],
  ];
  return `<div class="inner">
    <a class="logo" href="/index.html"><span class="mark">ಪ</span>PustakaMitra AI</a>
    <div class="links">
      ${links.map(([t, u]) => `<a href="${u}"${active === t ? ' aria-current="page"' : ""}>${t}</a>`).join("")}
      ${p.email ? `<a class="btn secondary small" href="/pages/profile.html">${p.name}</a>`
                : `<a class="btn small" href="/pages/signup.html">Sign up</a>`}
    </div>
  </div>`;
}

export function footer() {
  return `<footer><div class="container inner">
    <span>ಪುಸ್ತಕಮಿತ್ರ · Nimma Interest, Nimma Next Book!</span>
    <span>Book metadata from <a href="https://openlibrary.org" target="_blank" rel="noopener">Open Library</a>.
    Library holdings not yet verified by any integrated source.</span>
  </div></footer>`;
}

export function mountChrome(active) {
  const nav = document.getElementById("nav");
  if (nav) nav.innerHTML = navbar(active);
  const foot = document.getElementById("footer");
  if (foot) foot.outerHTML = footer();
}

export { profileService, libraryService };
