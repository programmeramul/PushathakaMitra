// Shared UI helpers: cover generator (mock, no external images), shelf renderer,
// nav/footer injection. ES module shared by every page.
import { bookService, profileService } from "./services/api.js";
import { load } from "./services/api.js";

const COVER_PALETTES = [
  ["#1b4332", "#2d6a4f"], ["#c2871d", "#8f6310"], ["#3d405b", "#52577a"],
  ["#5b2a49", "#7a3d64"], ["#20506b", "#2d6a4f"], ["#6b3d1e", "#8f5a2e"],
];
export function coverGradient(id) {
  const [a, b] = COVER_PALETTES[[...id].reduce((s, c) => s + c.charCodeAt(0), 0) % COVER_PALETTES.length];
  return `linear-gradient(150deg, ${a} 0%, ${b} 100%)`;
}
export function bookCover(b, { wide = false } = {}) {
  return `<span class="cover-wrap" style="display:block">
    <span style="display:flex;align-items:flex-end;justify-content:center;height:100%;background:${coverGradient(b.id)};padding:14%;color:#fff">
      <span style="font-family:var(--serif);font-size:${wide ? "1.1rem" : ".8rem"};line-height:1.35;overflow:hidden;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical">${b.title}${b.titleEn ? `<br><i style="opacity:.8;font-size:.85em">${b.titleEn}</i>` : ""}</span>
    </span></span>`;
}
export function bookCard(b, { reason = false } = {}) {
  const saved = profileService.savedBooks().includes(b.id);
  return `<a class="bookcard" href="/pages/book.html?id=${b.id}" data-id="${b.id}">
    ${bookCover(b)}
    <span class="info">
      <span class="title">${b.title}</span>
      <span class="meta">${b.author} · ${b.year}</span>
      <span style="display:flex;gap:.35rem;flex-wrap:wrap"><span class="tag">${b.language}</span><span class="tag gold">★ ${b.rating.toFixed(1)}</span></span>
      ${b.libCount ? `<span class="meta">📚 ${b.libCount}</span>` : ""}
      ${reason ? `<span class="hint">${b.appReason}</span>` : ""}
    </span>
  </a>`;
}

export function renderShelf(el, books, { reason = false } = {}) {
  el.innerHTML = books.map((b) => bookCard(b, { reason })).join("");
}

export function navbar(active) {
  const p = load();
  const links = [
    ["Home", "/index.html"], ["Dashboard", "/pages/dashboard.html"],
    ["Discover", "/pages/discover.html"], ["Saved", "/pages/saved.html"],
    ["Profile", "/pages/profile.html"],
  ];
  return `<div class="inner">
    <a class="logo" href="/index.html"><span class="mark">ಪ</span>PustakaMitra AI</a>
    <div class="links">
      ${links.map(([t, u]) => `<a href="${u}"${active === t ? ' aria-current="page"' : ""}>${t}</a>`).join("")}
      ${p.email ? `<a class="btn secondary small" href="/pages/dashboard.html">${p.name}</a>`
                : `<a class="btn small" href="/pages/signup.html">Sign up</a>`}
    </div>
  </div>`;
}

export function footer() {
  return `<footer><div class="container inner">
    <span>ಪುಸ್ತಕಮಿತ್ರ · Nimma Interest, Nimma Next Book!</span>
    <span>Demo build — books, libraries &amp; availability are <b>[MOCK]</b> fixtures. <a href="#" onclick="alert('Design reference: Stitch project 5841520769242524299 — see /design');return false;">Design source</a></span>
  </div></footer>`;
}

export function mountChrome(active) {
  const nav = document.getElementById("nav");
  if (nav) nav.innerHTML = navbar(active);
  const foot = document.getElementById("footer");
  if (foot) foot.outerHTML = footer();
}

export { profileService };
