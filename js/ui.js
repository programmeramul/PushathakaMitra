// Shared UI helpers: cover placeholder (restrained, clearly "unavailable"),
// shelf renderer, nav/footer injection. ES module shared by every page.
import { load, profileService, libraryService } from "./services/api.js";
import { authApi } from "./services/auth.js";
import { initChatbot, destroyChatbot } from "./chatbot.js";

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
  // base links render immediately (no flash); session-dependent links are
  // filled by authoriseNavbar() below — localStorage is NOT proof of auth.
  return `<div class="inner">
    <a class="logo" href="/index.html"><img src="/favicon.svg" alt="" class="mark" width="32" height="32">PustakaMitra AI</a>
    <div class="links" id="navlinks">
      <a href="/index.html"${active === "Home" ? ' aria-current="page"' : ""}>Home</a>
      <a href="/pages/discover.html"${active === "Discover" ? ' aria-current="page"' : ""}>Discover</a>
    </div>
  </div>`;
}

// Resolve the REAL session from the server (`GET /api/profile/me`, cookies
// included) and render the right links. Logged out / expired / network error
// all show Login + Sign up (server truth, never a localStorage fallback).
export async function authoriseNavbar(active) {
  const links = document.getElementById("navlinks");
  if (!links) return;
  const a = (u, label, cls = "", opts = {}) =>
    `<a href="${u}"${cls}${opts.page && active === opts.page ? ' aria-current="page"' : ""}>${label}</a>`;
  let user = null;
  try { user = await authApi.me(); } catch { /* 401 or offline */ }
  if (user) {
    links.innerHTML = a("/index.html", "Home", "", { page: "Home" })
      + a("/pages/discover.html", "Discover", "", { page: "Discover" })
      + a("/pages/saved.html", "Saved", "", { page: "Saved" })
      + a("/pages/profile.html", "Profile", "", { page: "Profile" })
      + `<a class="btn secondary small" href="/pages/profile.html">${user.name || user.email}</a>`
      + `<button class="btn small" id="navlogout" aria-label="Log out">Log out</button>`;
    document.getElementById("navlogout").addEventListener("click", async () => {
      await authApi.logout();
      destroyChatbot();                       // wipe conversation + widget on logout
      localStorage.removeItem("pustakamitra.profile.v1");
      window.location.href = "/index.html";
    });
    // chatbot appears only for users WITH saved interests (server truth)
    if ((user.interests || []).length) { initChatbot(user.interests); }
  } else {
    destroyChatbot();
    links.innerHTML = a("/index.html", "Home", "", { page: "Home" })
      + a("/pages/discover.html", "Discover", "", { page: "Discover" })
      + `<a class="btn secondary small" href="/pages/signup.html#login">Login</a>`
      + `<a class="btn small" href="/pages/signup.html">Sign up</a>`;
  }
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
  if (nav) {
    nav.innerHTML = navbar(active);
    authoriseNavbar(active);   // resolves session server-side, then updates links
  }
  const foot = document.getElementById("footer");
  if (foot) foot.outerHTML = footer();
}

export { profileService, libraryService };
