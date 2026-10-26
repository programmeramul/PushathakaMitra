// Auth + profile API client for the FastAPI backend (backend/main.py, port 8001).
// Cookie-based sessions: credentials:"include" + backend CORS(allow_credentials).
// No tokens/secrets live in this file — cookies are HttpOnly and server-managed.
export const API = (import.meta?.env?.VITE_API_BASE) || "http://127.0.0.1:8001";

async function call(path, { method = "GET", body, expect } = {}) {
  const res = await fetch(API + path, {
    method,
    credentials: "include",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  let data = null;
  try { data = await res.json(); } catch { /* non-JSON error body */ }
  if (!res.ok) {
    const detail = (data && data.detail) || {};
    const err = new Error(detail.message || res.statusText || "Request failed");
    err.code = detail.code || "http_" + res.status;
    err.field = FIELD_OF[err.code];
    throw err;
  }
  return data;
}

// backend error-code → form field, for inline validation display
const FIELD_OF = {
  name_invalid: "name",
  email_invalid: "email", email_taken: "email",
  password_mismatch: "password_confirm", password_weak: "password",
  phone_invalid: "phone", phone_country: "phone",
  age_invalid: "age", age_dob_mismatch: "dob", dob_invalid: "dob", dob_future: "dob",
  gender_invalid: "gender", pin_invalid: "pin_code",
  genre_invalid: "interests", interests_empty: "interests", other_required: "other_interest",
};

export const GENRE_OPTIONS = [
  ["horror", "Horror"], ["supernatural", "Supernatural"], ["spirituality", "Spirituality"],
  ["mystery", "Mystery"], ["thriller", "Thriller"], ["fantasy", "Fantasy"],
  ["romance", "Romance"], ["science-fiction", "Science Fiction"], ["technology", "Technology"],
  ["self-development", "Self-Development"], ["biography", "Biography"], ["history", "History"],
  ["philosophy", "Philosophy"], ["kannada-literature", "Kannada Literature"], ["other", "Other…"],
];
export const GENDER_OPTIONS = [
  ["woman", "Woman"], ["man", "Man"], ["non-binary", "Non-binary"],
  ["prefer-to-self-describe", "Prefer to self-describe"], ["prefer-not-to-say", "Prefer not to say"],
];

export const authApi = {
  register(payload) { return call("/api/auth/register", { method: "POST", body: payload }); },
  login(email, password) { return call("/api/auth/login", { method: "POST", body: { email, password } }); },
  logout() { return call("/api/auth/logout", { method: "POST" }); },
  me() { return call("/api/profile/me"); },
  updateMe(patch) { return call("/api/profile/me", { method: "PUT", body: patch }); },
};

export function fieldErrors(err) {
  return { [err.field || "__all__"]: err.message };
}
