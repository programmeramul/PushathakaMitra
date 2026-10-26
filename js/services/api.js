// Service layer — the ONLY place pages touch data. Swap the mock-backed
// functions for MongoDB + Groq backend calls here; no key ever reaches the
// frontend. `implementation` marks the current backing store.
import { BOOKS, LIBRARIES, GENRES, AVAIL_LABEL } from "../mock-data.js";

const implementation = "mock-data";

const delay = (ms = 120) => new Promise((r) => setTimeout(r, ms));

export const libraryService = {
  implementation,
  async listLibraries() {
    await delay();
    return LIBRARIES.map(({ id, branch, address, catalogue, holds }) => ({
      id, branch, address, catalogue, holds,
    }));
  },
  // Find which mock libraries hold a book. Labels are explicit mock labels.
  async findLibrariesForBook(bookId) {
    await delay();
    const hits = [];
    for (const lib of LIBRARIES) {
      const status = lib.holds[bookId];
      if (status) hits.push({ ...lib, status, statusLabel: AVAIL_LABEL[status] });
    }
    return hits;
  },
};

export const bookService = {
  implementation,
  async listBooks() { await delay(); return [...BOOKS]; },
  async getBook(id) {
    await delay();
    const book = BOOKS.find((b) => b.id === id) || null;
    if (!book) return null;
    // Similar books = share a genre, then closest first.
    const similar = BOOKS.filter((b) => b.id !== id && b.genres.some((g) => book.genres.includes(g)));
    return { ...book, similar };
  },
  async search(query, { genre = "all", lang = "all", availableOnly = false } = {}) {
    await delay();
    const q = query.trim().toLowerCase();
    let out = BOOKS.filter((b) => {
      const matchQ = !q || b.title.toLowerCase().includes(q) || (b.titleEn || "").toLowerCase().includes(q) || b.author.toLowerCase().includes(q);
      const matchG = genre === "all" || b.genres.includes(genre);
      const matchL = lang === "all" || b.language.toLowerCase() === lang.toLowerCase();
      const matchA = !availableOnly || (b.libCount || "").startsWith("[MOCK]");
      return matchQ && matchG && matchL && matchA;
    });
    return out;
  },
  genres: GENRES,
  availabilityLabels: AVAIL_LABEL,
};

// RecommendationService: today sorts mock data; wire to Groq explained-recommendations here later.
export const recommendationService = {
  implementation,
  async forReader(profile) {
    await delay(150);
    const followed = (profile && profile.genres) || [];
    const scored = BOOKS.map((b) => ({
      ...b,
      score: b.genres.reduce((acc, g) => acc + (followed.includes(g) ? 2 : 0), 0) + b.rating / 10,
    }));
    scored.sort((a, b) => b.score - a.score);
    return scored.slice(0, 6);
  },
};

export const profileService = {
  implementation,
  async current() { return load(); },
  save,
  toggleSavedBook,
  savedBooks() { return load().saved; },
};

// ---- profile persistence (mock: localStorage; swaps to MongoDB account later)
const KEY = "pustakamitra.profile.v1";
export function load() {
  try {
    return JSON.parse(localStorage.getItem(KEY)) || { name: "Ananya", email: "", genres: [], goal: "", level: "", saved: [], onboarded: false };
  } catch {
    return { name: "Ananya", email: "", genres: [], goal: "", level: "", saved: [], onboarded: false };
  }
}
export function save(partial) {
  const next = { ...load(), ...partial };
  localStorage.setItem(KEY, JSON.stringify(next));
  return next;
}
export function toggleSavedBook(id) {
  const p = load();
  p.saved = p.saved.includes(id) ? p.saved.filter((x) => x !== id) : [...p.saved, id];
  return save(p).saved;
}
