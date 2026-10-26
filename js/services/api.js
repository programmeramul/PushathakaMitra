// Service layer — the ONLY place pages touch data. All reads go to the FastAPI
// backend (:8001) which serves MongoDB catalogue records. No mock fallback:
// an empty database shows an honest empty state, never fabricated fixtures.
const API = "http://127.0.0.1:8001";

async function call(path, { method = "GET", body, expect } = {}) {
  const res = await fetch(API + path, {
    method,
    credentials: "include",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  let data = null;
  try { data = await res.json(); } catch { /* non-JSON body */ }
  if (!res.ok) {
    const detail = (data && data.detail) || {};
    const err = new Error(detail.message || res.statusText || "Request failed");
    err.code = detail.code || "http_" + res.status;
    err.status = res.status;
    throw err;
  }
  return data;
}

export { call };

// Canonical genre vocabulary — stable IDs + English/Kannada labels.
// The only interest data source: onboarding chips, Discover filters and
// profile picks all read these fields (id / en / kn). Backend GENRES must match.
export const GENRES = [
  { id: "horror", en: "Horror", kn: "ಭಯ" },
  { id: "supernatural", en: "Supernatural", kn: "ಅಲೌಕಿಕ" },
  { id: "spirituality", en: "Spirituality", kn: "ಆಧ್ಯಾತ್ಮ" },
  { id: "mystery", en: "Mystery", kn: "ರಹಸ್ಯ" },
  { id: "thriller", en: "Thriller", kn: "ಥ್ರಿಲ್ಲರ್" },
  { id: "fantasy", en: "Fantasy", kn: "ಕಲ್ಪನಾವಿಶ್ವ" },
  { id: "romance", en: "Romance", kn: "ಪ್ರೇಮ" },
  { id: "science-fiction", en: "Science Fiction", kn: "ಸೈನ್ಸ್ ಫಿಕ್ಷನ್" },
  { id: "technology", en: "Technology", kn: "ತಂತ್ರಜ್ಞಾನ" },
  { id: "self-development", en: "Self-Development", kn: "ಸ್ವಯಂ" },
  { id: "biography", en: "Biography", kn: "ಜೀವನಚರಿತ್ರೆ" },
  { id: "history", en: "History", kn: "ಇತಿಹಾಸ" },
  { id: "philosophy", en: "Philosophy", kn: "ತತ್ವಶಾಸ್ತ್ರ" },
  { id: "kannada-literature", en: "Kannada Literature", kn: "ಕನ್ನಡ ಸಾಹಿತ್ಯ" },
];
// validate once at load: a broken entry must fail loudly here, not render "undefined"
for (const g of GENRES) {
  if (!g.id || !g.en || !g.kn) throw new Error(`Bad genre entry: ${JSON.stringify(g)}`);
}

export const bookService = {
  async search({ q = "", genre = "", lang = "", page = 1, page_size = 24 } = {}) {
    const p = new URLSearchParams();
    if (q.trim()) p.set("q", q.trim());
    if (genre && genre !== "all") p.set("genre", genre);
    if (lang && lang !== "all") p.set("lang", lang);
    p.set("page", page); p.set("page_size", page_size);
    return call(`/api/books?${p}`);
  },
  async listBooks() { return (await this.search({ page_size: 60 })).items; },
  async getBook(id) {
    try { return await call(`/api/books/${encodeURIComponent(id)}`); }
    catch (e) { return e.status === 404 ? null : Promise.reject(e); }
  },
  genres: GENRES,
};

export const recommendationService = {
  async forReader() { return call("/api/recommendations"); },
};

export const libraryService = {
  // Holdings are NOT verified by any integrated source. We return the honest
  // "not verified" state instead of fabricating branches or availability.
  async notVerified() { return { verified: false }; },
};

// ---- profile persistence (browser-local mirror of the server profile)
const KEY = "pustakamitra.profile.v1";
export function load() {
  try {
    return JSON.parse(localStorage.getItem(KEY)) || { name: "", email: "", genres: [], goal: "", level: "", saved: [], onboarded: false };
  } catch {
    return { name: "", email: "", genres: [], goal: "", level: "", saved: [], onboarded: false };
  }
}
export function save(partial) {
  const next = { ...load(), ...partial };
  localStorage.setItem(KEY, JSON.stringify(next));
  return next;
}
export function toggleSavedBook(id) {
  const cur = load().saved;
  const next = cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id];
  return save({ saved: next }).saved;
}
export const profileService = {
  current() { return load(); },
  save,
  toggleSavedBook,
  savedBooks() { return load().saved; },
};
