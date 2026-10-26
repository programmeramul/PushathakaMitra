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

export const GENRES = [
  ["horror", "Horror", "ಭಯ"], ["supernatural", "Supernatural", "ಅಲೌಕಿಕ"],
  ["spirituality", "Spirituality", "ಆಧ್ಯಾತ್ಮ"], ["mystery", "Mystery", "ರಹಸ್ಯ"],
  ["thriller", "Thriller", "ಥ್ರಿಲ್ಲರ್"], ["fantasy", "Fantasy", "ಕಲ್ಪನಾವಿಶ್ವ"],
  ["romance", "Romance", "ಪ್ರೇಮ"], ["science-fiction", "Science Fiction", "ಸೈನ್ಸ್ ಫಿಕ್ಷನ್"],
  ["technology", "Technology", "ತಂತ್ರಜ್ಞಾನ"], ["self-development", "Self-Development", "ಸ್ವಯಂ"],
  ["biography", "Biography", "ಜೀವನಚರಿತ್ರೆ"], ["history", "History", "ಇತಿಹಾಸ"],
  ["philosophy", "Philosophy", "ತತ್ವಶಾಸ್ತ್ರ"],
  ["kannada-literature", "Kannada Literature", "ಕನ್ನಡ ಸಾಹಿತ್ಯ"],
];

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
