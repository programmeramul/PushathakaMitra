"""PustakaMitra AI backend — FastAPI + MongoDB.

Registration/login/profile endpoints with:
- Argon2id password hashing (argon2-cffi); plaintext never stored
- unique normalized (lowercased) email via a MongoDB unique index;
  duplicateDoc KeyErrors — including concurrent inserts — mapped to a 409
- server-managed sessions in Mongo (TTL index) behind HTTP-only cookies;
  cookie value is opaque; Mongo stores only a keyed SHA-256 of it
- profile edits allowed after registration; email immutably keys the account
- privacy: GET endpoints return the caller's own doc only; no endpoint ever
  returns any other user's phone/address/PIN

Kept out of the frontend: Mongo credentials and hashing/session secrets come
from environment variables only.
"""
import hashlib
import json
import logging
import os
import re
import secrets
import socket
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import uvicorn
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import Cookie, Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
from pymongo import MongoClient, errors

# backend/.env is loaded explicitly (next to main.py) so startup works from any
# cwd. Real environment variables always win (override=False) — shell/CI settings
# are never silently replaced by file values.
from pathlib import Path as _Path
from dotenv import load_dotenv as _load_dotenv
_load_dotenv(_Path(__file__).with_name(".env"), override=False)

SESSION_COOKIE = "pm_session"
SESSION_TTL_MIN = int(os.environ.get("SESSION_TTL_MIN", "180"))
SESSION_HASH_KEY = os.environ.get("SESSION_HASH_KEY", "dev-only-session-key")
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.environ.get("MONGO_DB", "pustakamitra")  # tests override to pustakamitra_test
SECURE_COOKIES = os.environ.get("SECURE_COOKIES") == "1"
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

ph = PasswordHasher()

DB = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)[MONGO_DB]
users = DB.users
sessions = DB.sessions


def _ensure_indexes() -> None:
    users.create_index([("email", 1)], unique=True, name="uq_email")
    users.create_index([("interests", 1)], name="ix_interests")
    sessions.create_index([("sid", 1)], unique=True, name="uq_sid")
    # TTL index: Mongo autoremoves expired session docs
    sessions.create_index([("expires_at", 1)], name="ttl_sessions",
                          expireAfterSeconds=0)


_ensure_indexes()


def _fail(status: int, code: str, msg: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": msg})


def _keyed(sid: str) -> str:
    return hashlib.sha256((SESSION_HASH_KEY + sid).encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ------------------------------- validation -------------------------------
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PIN_RE = re.compile(r"^[1-9][0-9]{5}$")

CANON_CLASSES = {
    "IN": {"country": "+91", "digits": 10, "first": (6, 9)},  # 10-digit mobile, first digit 6-9
    "US": {"country": "+1", "digits": 10, "first": (2, 9)},
    "GB": {"country": "+44", "digits": 10, "first": (1, 9)},
}

GENRES = {
    "horror", "supernatural", "spirituality", "mystery", "thriller", "fantasy",
    "romance", "science-fiction", "technology", "self-development",
    "biography", "history", "philosophy", "kannada-literature", "other",
}
GENDERS = {"man", "woman", "non-binary", "prefer-to-self-describe", "prefer-not-to-say"}


def _validate_phone(raw: str, country: str = "IN") -> str:
    """Validate loosely but persistently: strip separators, keep E.164 output.
    Per-country digit rules instead of a universal 'exactly 10 digits'."""
    rule = CANON_CLASSES.get(country.upper())
    if not rule:
        raise _fail(422, "phone_country", "Unsupported country code")
    digits = re.sub(r"[^0-9]", "", raw)
    if digits.startswith("0"):
        digits = digits.lstrip("0")
    if digits.startswith(rule["country"].lstrip("+")) and len(digits) > rule["digits"]:
        digits = digits[len(rule["country"].lstrip("+")):]
    if len(digits) != rule["digits"] or not digits[0].isdigit() or not (int(rule["first"][0]) <= int(digits[0]) <= int(rule["first"][1])):
        raise _fail(422, "phone_invalid",
                    f"Enter a valid {country} mobile number ({rule['digits']} digits)")
    return rule["country"] + digits


def _validate_register(d: dict) -> dict:
    email = (d.get("email") or "").strip().lower()
    if not _EMAIL_RE.fullmatch(email):
        raise _fail(422, "email_invalid", "Enter a valid email address.")

    pw, pwc = d.get("password") or "", d.get("password_confirm") or ""
    if pw != pwc:
        raise _fail(422, "password_mismatch", "Passwords do not match.")
    if len(pw) < 8:
        raise _fail(422, "password_weak", "Password must be at least 8 characters.")

    phone = _validate_phone(d.get("phone") or "", "IN")

    age = d.get("age")
    if age is None or not isinstance(age, int) or not (5 <= age <= 120):
        raise _fail(422, "age_invalid", "Age must be between 5 and 120.")

    dob_raw = d.get("dob") or None
    if dob_raw:
        try:
            dob = datetime.strptime(dob_raw, "%Y-%m-%d").date()
        except ValueError:
            raise _fail(422, "dob_invalid", "Date of birth must be YYYY-MM-DD.")
        if dob > _now().date():
            raise _fail(422, "dob_future", "Date of birth cannot be in the future.")
        today = _now().date()
        computed = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        if computed != age:
            raise _fail(422, "age_dob_mismatch",
                        "Age and date of birth do not match.")

    gender = d.get("gender") or "prefer-not-to-say"
    if gender not in GENDERS:
        raise _fail(422, "gender_invalid", "Choose a listed gender option.")

    address = (d.get("home_address") or "").strip() or None
    pin = (d.get("pin_code") or "").replace(" ", "") or None
    if pin and not _PIN_RE.fullmatch(pin):
        raise _fail(422, "pin_invalid", "PIN code must be six digits.")

    interests = d.get("interests") or []
    unknown = [g for g in interests if g not in GENRES]
    if unknown:
        raise _fail(422, "genre_invalid", f"Unknown genre: {unknown[0]}")
    if not interests:
        raise _fail(422, "interests_empty", "Pick at least one book interest.")
    other_interest = (d.get("other_interest") or "").strip() or None
    if "other" in interests and not other_interest:
        raise _fail(422, "other_required", "Describe your custom interest for Other.")
    if "other" not in interests:
        other_interest = None

    name = (d.get("name") or "").strip()
    if not (2 <= len(name) <= 80):
        raise _fail(422, "name_invalid", "Name must be 2–80 characters.")

    return dict(name=name, email=email, phone=phone, age=age, dob=dob_raw,
                gender=gender, home_address=address, pin_code=pin,
                interests=interests, other_interest=other_interest,
                password=pw)


# --------------------------------- models ---------------------------------
class RegisterIn(BaseModel):
    name: str
    email: str
    phone: str
    age: int
    dob: Optional[str] = None
    gender: Optional[str] = None
    home_address: Optional[str] = Field(default=None, max_length=320)
    pin_code: Optional[str] = None
    interests: List[str]
    other_interest: Optional[str] = None
    password: str
    password_confirm: str


class LoginIn(BaseModel):
    email: str
    password: str


class ProfileIn(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    age: Optional[int] = None
    dob: Optional[str] = None
    gender: Optional[str] = None
    home_address: Optional[str] = None
    pin_code: Optional[str] = None
    interests: Optional[List[str]] = None
    other_interest: Optional[str] = None
    goal: Optional[str] = None          # onboarding reading goal id
    level: Optional[str] = None         # onboarding reading level id
    language: Optional[str] = None      # preferred reading language
    password: Optional[str] = None
    password_confirm: Optional[str] = None


# --------------------------------- app ---------------------------------
app = FastAPI(title="PustakaMitra AI API", version="0.3.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o for o in os.environ.get(
        "CORS_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000").split(",") if o],
    allow_credentials=True,
    allow_methods=["*"], allow_headers=["Content-Type"],
)


def _self_doc(user: dict) -> dict:
    """Everything the OWNER may see (own phone/address). Never used for others."""
    return {
        "id": str(user["_id"]), "name": user["name"], "email": user["email"],
        "phone": user["phone"], "age": user["age"], "dob": user["dob"],
        "gender": user["gender"], "home_address": user.get("home_address"),
        "pin_code": user.get("pin_code"),
        "interests": user.get("interests", []), "other_interest": user.get("other_interest"),
        "goal": user.get("goal"), "level": user.get("level"), "language": user.get("language"),
        "created_at": user["created_at"].isoformat(),
        "updated_at": user["updated_at"].isoformat(),
    }


def _start_session(resp: Response, user_id: ObjectId) -> None:
    sid = secrets.token_urlsafe(32)
    sessions.insert_one({"sid": _keyed(sid), "user_id": str(user_id),
                         "created_at": _now(),
                         "expires_at": _now() + timedelta(minutes=SESSION_TTL_MIN)})
    resp.set_cookie(SESSION_COOKIE, sid,
                    max_age=SESSION_TTL_MIN * 60, path="/",
                    httponly=True, samesite="lax", secure=SECURE_COOKIES)


def _current_user(pm_session: Optional[str] = Cookie(default=None)) -> dict:
    if not pm_session:
        raise _fail(401, "no_session", "Not signed in.")
    rec = sessions.find_one({"sid": _keyed(pm_session)})
    if not rec or rec["expires_at"].replace(tzinfo=timezone.utc) < _now():
        raise _fail(401, "session_expired", "Session expired — log in again.")
    user = users.find_one({"_id": ObjectId(rec["user_id"])})
    if not user:
        raise _fail(401, "user_gone", "Account no longer exists.")
    return user


def health():
    DB.command("ping")
    return {"status": "ok", "ok": True}

# one implementation, two paths: /health is the public probe (monitors, curl),
# /api/health is what the existing tests/clients already use. Both require a
# live MongoDB round-trip — never report ok without checking the DB.
app.add_api_route("/health", health, methods=["GET"])


@app.get("/api/health")
def health_api():
    return health()


@app.post("/api/auth/register", status_code=201)
def register(data: RegisterIn, response: Response):
    try:
        v = _validate_register(data.model_dump())
    except HTTPException:
        raise

    doc = {**v, "password_hash": ph.hash(v["password"]), "created_at": _now(),
           "updated_at": _now()}
    doc.pop("password")
    try:
        user_id = users.insert_one(doc).inserted_id
    except errors.DuplicateKeyError:
        # unique index catches both existing and concurrent duplicate emails
        raise _fail(409, "email_taken", "An account with this email already exists.")

    _start_session(response, user_id)
    return {"created": True, "user": _self_doc(users.find_one({"_id": user_id}))}


@app.post("/api/auth/login")
def login(data: LoginIn, response: Response):
    user = users.find_one({"email": (data.email or "").strip().lower()})
    if not user:
        raise _fail(401, "bad_credentials", "Email or password is incorrect.")
    try:
        ph.verify(user["password_hash"], data.password)
    except (VerifyMismatchError, InvalidHashError):
        raise _fail(401, "bad_credentials", "Email or password is incorrect.")
    # transparent rehash on Argon2 parameter changes
    if ph.check_needs_rehash(user["password_hash"]):
        users.update_one({"_id": user["_id"]},
                         {"$set": {"password_hash": ph.hash(data.password)}})
    _start_session(response, user["_id"])
    return {"ok": True, "user": _self_doc(user)}


@app.post("/api/auth/logout")
def logout(response: Response, pm_session: Optional[str] = Cookie(default=None)):
    if pm_session:
        sessions.delete_one({"sid": _keyed(pm_session)})
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@app.get("/api/profile/me")
def get_me(user: dict = Depends(_current_user)):
    return _self_doc(user)


@app.put("/api/profile/me")
def update_me(data: ProfileIn, user: dict = Depends(_current_user)):
    upd: dict = {"updated_at": _now()}
    d = data.model_dump(exclude_unset=True)

    interests = d.get("interests")
    if interests is not None:
        unknown = [g for g in interests if g not in GENRES]
        if not interests or unknown:
            raise _fail(422, "genre_invalid", "Invalid or empty interests list.")
        upd.update(interests=interests, other_interest=d.get("other_interest") or None)

    if d.get("password"):
        if d["password"] != (d.get("password_confirm") or ""):
            raise _fail(422, "password_mismatch", "Passwords do not match.")
        if len(d["password"]) < 8:
            raise _fail(422, "password_weak", "Password must be at least 8 characters.")
        upd["password_hash"] = ph.hash(d["password"])

    if d.get("pin_code"):
        pin = d["pin_code"].replace(" ", "")
        if not _PIN_RE.fullmatch(pin):
            raise _fail(422, "pin_invalid", "PIN code must be six digits.")
        upd["pin_code"] = pin
    if "pin_code" in d and not d.get("pin_code"):
        upd["pin_code"] = None

    for k in ("name", "home_address", "gender", "dob", "phone", "age", "goal", "level", "language"):
        if k in d:
            upd[k] = d[k]
    if upd.get("phone"):
        upd["phone"] = _validate_phone(upd["phone"])
    if upd.get("age") is not None and not (5 <= upd["age"] <= 120):
        raise _fail(422, "age_invalid", "Age must be between 5 and 120.")
    if upd.get("dob"):
        try:
            dd = datetime.strptime(upd["dob"], "%Y-%m-%d").date()
        except ValueError:
            raise _fail(422, "dob_invalid", "Date of birth must be YYYY-MM-DD.")
        if dd > _now().date():
            raise _fail(422, "dob_future", "Date of birth cannot be in the future.")

    users.update_one({"_id": user["_id"]}, {"$set": upd})
    return _self_doc(users.find_one({"_id": user["_id"]}))



# ------------------------------ catalogue ------------------------------
books_coll = DB["books"]
books_coll.create_index("source_id", unique=True)

SYNC_TOKEN = os.environ.get("CATALOG_SYNC_TOKEN")


def _pub_book(b: dict) -> dict:
    """Public book shape — only sourced fields, no ratings, no holdings."""
    return {
        "id": str(b["_id"]), "title": b["title"], "authors": b.get("authors") or [],
        "year": b.get("year"), "language": b.get("language"),
        "subject_slugs": b.get("subject_slugs") or [],
        "description": b.get("description"),
        "cover_url": b.get("cover_url"),
        # provenance is public by design — traceability is the point
        "source": b.get("source"), "source_id": b.get("source_id"),
    }


@app.get("/api/books")
def list_books(q: str = "", genre: str = "", lang: str = "",
               page: int = 1, page_size: int = 24):
    cur: dict = {}
    if q.strip():
        rx = {"$regex": re.escape(q.strip()), "$options": "i"}
        cur["$or"] = [{"title": rx}, {"authors": rx}]
    if genre:
        cur["subject_slugs"] = genre
    if lang:
        cur["language"] = lang
    page, page_size = max(1, page), max(1, min(60, page_size))
    total = books_coll.count_documents(cur)
    docs = books_coll.find(cur, sort=[("year", -1), ("_id", 1)]
                           ).skip((page - 1) * page_size).limit(page_size)
    return {"total": total, "page": page, "page_size": page_size,
            "items": [_pub_book(b) for b in docs]}


@app.get("/api/books/{book_id}")
def get_book(book_id: str, response: Response):
    try:
        b = books_coll.find_one({"_id": book_id})
    except Exception:
        b = None
    if not b:
        raise _fail(404, "book_not_found", "No such book in the catalogue.")
    out = _pub_book(b)
    out["subjects"] = b.get("subjects") or []
    out["language_codes"] = b.get("language_codes") or []
    out["isbn"] = b.get("isbn")
    out["imported_at"] = b.get("imported_at")
    # similar = share a category slug; honest "None yet" when categories missing
    slugs = b.get("subject_slugs") or []
    out["similar"] = ([_pub_book(s) for s in books_coll.find(
        {"_id": {"$ne": b["_id"]}, "subject_slugs": {"$in": slugs}}).limit(6)]
        if slugs else [])
    return out


@app.post("/api/catalog/sync")
def catalog_sync(request: Request):
    # admin-only, token from env; 503 with a clear message when not configured
    if not SYNC_TOKEN:
        raise _fail(503, "sync_unconfigured",
                    "Set CATALOG_SYNC_TOKEN to enable catalogue sync.")
    if request.headers.get("X-Admin-Token") != SYNC_TOKEN:
        raise _fail(401, "bad_admin_token", "Invalid admin token.")
    from importlib import import_module
    catalog = import_module("catalog") if not __package__ else import_module("backend.catalog")
    fetch_books, upsert_books = catalog.fetch_books, catalog.upsert_books
    totals = {"inserted": 0, "updated": 0, "rejected": 0}
    for q in json.load(open(os.path.join(os.path.dirname(__file__),
                                         "catalog_queries.json"))):
        try:
            r = upsert_books(books_coll, fetch_books(q["q"], limit=q.get("limit", 100)))
        except Exception:
            continue                      # failed query: skip, never fabricate
        for k in totals:
            totals[k] += r[k]
    return {"ok": True, "counts": totals, "total_in_db": books_coll.count_documents({})}


# --------------------------- recommendations ---------------------------
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
# Cloudflare in front of Groq hard-blocks the default "Python-urllib" client
# (HTTP 403, CF error 1010) — a named UA is required for any production call.
GROQ_UA = "pustakamitra-backend/0.3"

# sanitized fallback explanations returned to the frontend (never contain the key)
_GROQ_REASONS = {
    "config_missing": "AI isn't configured on this server yet.",
    "invalid_credentials": "The AI service rejected its credentials — the maintainer should check the Groq key.",
    "rate_limited": "The AI service is rate-limited right now.",
    "timeout": "The AI service didn't respond in time.",
    "network": "The AI service could not be reached.",
    "model_unavailable": "The configured AI model isn't currently available.",
    "malformed_response": "The AI returned an unexpected response format.",
    "no_candidates": "The AI had no catalogue books to work from.",
}


def _classify_groq_failure(e: Exception) -> str:
    """Map a urllib exception to a safe reason code. Logs it without secrets."""
    if isinstance(e, urllib.error.HTTPError):
        detail = ""
        try:
            detail = e.read().decode()[:200]
        except Exception:
            pass
        logging.getLogger("pustakamitra.groq").warning(
            "Groq HTTP %s (%s) — detail: %s", e.code, e.reason, detail[:120])
        if e.code in (401, 403):
            return "invalid_credentials"
        if e.code == 404:
            return "model_unavailable"
        if e.code == 429:
            return "rate_limited"
        return "network"
    if isinstance(e, TimeoutError):
        return "timeout"
    if isinstance(e, socket.timeout):
        return "timeout"
    try:
        raise e                                 # re-raise to see the real type
    except (urllib.error.URLError, ConnectionError, OSError):
        return "network"
    except Exception:
        logging.getLogger("pustakamitra.groq").warning(
            "Groq failed: %s: %s", type(e).__name__, str(e)[:200])
        return "malformed_response"


def _keyword_rank(cands: list, interests: list, limit: int = 6) -> list:
    """Deterministic metadata-only fallback. Labels genre overlap; no ratings."""
    def score(b):
        return (-len(set(b.get("subject_slugs") or []) & set(interests)),
                -(b.get("year") or 0))
    out = sorted(cands, key=score)[:limit]
    return [{"id": str(b["_id"]),
             "reason": "Matches your interest" + ("s" if len(set(b.get("subject_slugs") or []) & set(interests)) > 1 else "") + ": " + ", ".join(
                 sorted(set(b.get("subject_slugs") or []) & set(interests)))
             if set(b.get("subject_slugs") or []) & set(interests)
             else "From the current catalogue"}
            for b in out]


def _groq_rank(cands: list, interests: list) -> Optional[list]:
    """Ask Groq to pick from candidates. Returns None on any failure."""
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        return None    # only titles/authors/categories go out — never the user's PII
    payload_cands = [{"id": str(b["_id"]), "title": b["title"],
                      "authors": b.get("authors") or [], "year": b.get("year"),
                      "categories": b.get("subject_slugs") or []} for b in cands]
    body = json.dumps({
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content":
             "You recommend books for a reader. From the given candidates ONLY, "
             "pick the best matches for their reading interests. Respond with "
             "strict JSON: {\"recommendations\": [{\"id\": \"<candidate id>\", "
             "\"reason\": \"<one concise sentence, max 20 words, referencing "
             "only the candidate's own metadata>\"}]}. Use only candidate ids "
             "from the list. Never invent books, ratings or availability."},
            {"role": "user", "content": json.dumps(
                {"interests": interests, "candidates": payload_cands})},
        ],
        "temperature": 0.3, "max_tokens": 800,
        "response_format": {"type": "json_object"},
    }).encode()
    req = urllib.request.Request(GROQ_URL, data=body, headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json",
        "User-Agent": GROQ_UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            content = json.load(resp)["choices"][0]["message"]["content"]
        recs = json.loads(content).get("recommendations") or []
    except Exception:
        return None
    # validate: keep only known candidate ids with a string reason
    valid = {str(b["_id"]) for b in cands}
    out = [{"id": r["id"], "reason": str(r.get("reason") or "")[:200]}
           for r in recs
           if isinstance(r, dict) and str(r.get("id")) in valid and r.get("reason")]
    return out[:6] or None


@app.get("/api/recommendations")
def recommendations(user: dict = Depends(_current_user)):
    interests = user.get("interests") or []
    # no interests yet: say so honestly instead of blanket-recommending
    if not interests:
        return {"engine": "no_interests", "items": []}
    cands = list(books_coll.find({"subject_slugs": {"$in": interests}}, limit=100))
    if not cands:
        return {"engine": "empty", "items": []}      # honest empty catalogue
    recs = _groq_rank(cands, interests)
    engine = "groq"
    if recs is None:
        recs, engine = _keyword_rank(cands, interests), "keyword"
    by_id = {str(b["_id"]): b for b in cands}
    return {"engine": engine,
            "items": [{**_pub_book(by_id[r["id"]]), "reason": r.get("reason", "")}
                      for r in recs if r["id"] in by_id and r.get("reason")][:6]}


# ------------------------------ chatbot ------------------------------
# AI reading companion over the REAL catalogue. Authenticated + onboarded only.
class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=600)
    history: List[dict] = Field(default_factory=list, max_length=10)
    locality: Optional[str] = Field(default=None, max_length=80)


_KN_HINTS = ("ಕನ್ನಡ", "ಪುಸ್ತಕ", "ಓದು", "ಗ್ರಂಥಾಲಯ", "ಪುಸ್ತಕಾಲಯ")
_LIBRARY_HINTS = ("library", "librar", "granthalaya", "ಗ್ರಂಥಾಲಯ", "ಪುಸ್ತಕಾಲಯ",
                  "ಗ್ರಂಥಾಲಯದ")
_GENRE_HINTS = {
    "mystery": ("mystery", "mysteries", "ರಹಸ್ಯ"),
    "horror": ("horror", "ಭಯ", "ಭೀತಿ"),
    "fantasy": ("fantasy", "ಕಲ್ಪನಾವಿಶ್ವ"),
    "romance": ("romance", "love story", "ಪ್ರೇಮ"),
    "thriller": ("thriller", "ಥ್ರಿಲ್ಲರ್"),
    "science-fiction": ("science fiction", "sci-fi", "ಸೈನ್ಸ್ ಫಿಕ್ಷನ್"),
    "spirituality": ("spiritual", "spirituality", "ಆಧ್ಯಾತ್ಮ"),
    "philosophy": ("philosophy", "ತತ್ವ", "ತತ್ವಶಾಸ್ತ್ರ"),
    "history": ("history", "ಇತಿಹಾಸ"),
    "technology": ("technology", "business", "ತಂತ್ರಜ್ಞಾನ"),
    "biography": ("biography", "leader", "leadership", "ಜೀವನಚರಿತ್ರೆ"),
    "self-development": ("self-help", "self development", "beginner", "start reading",
                         "ಸ್ವಯಂ"),
    "kannada-literature": ("kannada literature", "kannada novel", "ಕನ್ನಡ ಸಾಹಿತ್ಯ",
                           "parva", "parvœ"),
}


def _book_card(b: dict) -> dict:
    c = _pub_book(b)
    c.pop("description", None)                   # cards stay compact
    return c


def _candidates_for(message: str, interests: list) -> list:
    msg = message.lower()
    want_kn = "kannada" in msg or any(h in message for h in _KN_HINTS)
    slugs = {s for s in interests}
    for slug, hints in _GENRE_HINTS.items():
        if any(h in msg for h in hints):
            slugs.add(slug)
    if not slugs:
        slugs = {s for s in interests} or set()   # fall back to real saved interests
    cur: dict = {}
    slug_list = sorted(slugs)
    if slug_list:
        cur["subject_slugs"] = {"$in": slug_list}
    if want_kn:
        cur["language"] = "Kannada"
    cands = list(books_coll.find(cur, limit=60)) or \
        list(books_coll.find({"subject_slugs": {"$in": slug_list}} if slug_list else {},
                             limit=60))
    return cands


def _groq_chat(cands: list, interests: list, message: str, history: list):
    """Groq chat turn over candidates. Returns ({message, recs}|None, reason|None);
    reason is a safe code from _GROQ_REASONS when result is None."""
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        return None, "config_missing"
    if not cands:
        return None, "no_candidates"
    payload = {"interests": interests, "candidates": [
        {"id": str(b["_id"]), "title": b["title"], "authors": b.get("authors") or [],
         "year": b.get("year"), "categories": b.get("subject_slugs") or []}
        for b in cands[:40]]}
    body = json.dumps({
        "model": GROQ_MODEL, "temperature": 0.4, "max_tokens": 500,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content":
             "You are PustakaMitra AI, a warm reading companion for Kannada and "
             "English readers in Bengaluru. Answer in the user's language "
             "(Kannada or English). Recommend from the given candidates ONLY. "
             "Reply with strict JSON: {\"message\": \"<2-4 friendly sentences>\", "
             "\"recommendations\": [{\"id\": \"<candidate id>\", \"reason\": "
             "\"<one short sentence>\"}]}. Use only candidate ids from the list. "
             "Never invent books, ratings, or library availability. Do not repeat "
             "books already given in the conversation history."},
            {"role": "user", "content": json.dumps(
                {"history": history[-6:], "message": message, "context": payload})},
        ],
    }).encode()
    req = urllib.request.Request(GROQ_URL, data=body, headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json",
        "User-Agent": GROQ_UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            content = json.load(resp)["choices"][0]["message"]["content"]
        out = json.loads(content)
    except Exception as e:
        return None, _classify_groq_failure(e)   # timeout/429/malformed → fallback
    msg = str(out.get("message") or "").strip() or None
    valid = {str(b["_id"]) for b in cands}
    recs = [{"id": str(r.get("id")), "reason": str(r.get("reason") or "")[:200]}
            for r in (out.get("recommendations") or [])
            if isinstance(r, dict) and str(r.get("id")) in valid and r.get("reason")]
    if msg is None and not recs:
        return None, "malformed_response"
    return {"message": msg, "recs": recs[:5]}, None


_PIN_RE = re.compile(r"\b([1-9][0-9]{5})\b")
_NEAR_RE = re.compile(r"(?:near|in|around|list|available)\s+([A-Za-z][A-Za-z .]{2,40}?)(?:\s*[?.!]|$|\s+library|\s+public)", re.I)


def _library_links(message: str, locality: Optional[str]) -> dict:
    """Bengaluru library discovery: NO real location dataset exists (Mongo has no
    libraries collection), so we return official search links only and never
    claim verified addresses/holdings. Locality/PIN is parsed deterministically."""
    loc_named = (locality or "").strip()
    if not loc_named:
        m = _NEAR_RE.search(message)
        if m:
            loc_named = m.group(1).strip()
    pin = _PIN_RE.search(message)
    if pin and not loc_named:
        loc_named = pin.group(1)
    q = loc_named[:80] or "Bengaluru"
    loc = urllib.request.quote(q)
    holdings_note = ("No live catalogue integration exists, so shelf/borrowing "
                     "availability is UNVERIFIED for every book.")
    return {
        "verified": False,
        "note": ("No verified Bengaluru library location dataset is integrated "
                 "yet, so I can't confirm addresses or holdings. These official "
                 "search pages are the reliable starting point for " + q + ":"),
        "links": [
            {"label": "City Central Library — State Library Directory",
             "url": "https://karnataka.gov.in/newpage/Public%20Libraries.aspx"},
            {"label": "e-Granthalaya catalogue (participating libraries)",
             "url": "https://egranthalaya.nic.in/"},
            {"label": f"Map search: public libraries near {q}",
             "url": f"https://www.google.com/maps/search/public+library+{loc}+Bengaluru"},
            {"label": "WorldCat — search library holdings for a book",
             "url": "https://search.worldcat.org/"},
        ],
        "holdings": {"available": False, "note": holdings_note},
    }


@app.post("/api/chat")
def chat(data: ChatIn, user: dict = Depends(_current_user)):
    msg = data.message.strip()
    # honest guard: chatbot is for users who completed onboarding (interests saved)
    interests = user.get("interests") or []
    history = [h for h in data.history if
               isinstance(h, dict) and isinstance(h.get("role"), str)
               and isinstance(h.get("content"), str)][:10]
    if any(h in msg for h in _LIBRARY_HINTS) or (data.locality or "").strip():
        return {"engine": "links", "reply":
                "I can point you to official library search pages — "
                "I don't have verified Bengaluru holdings data yet.",
                "books": [], "library": _library_links(msg, data.locality)}
    cands = _candidates_for(msg, interests)
    if not cands:
        return {"engine": "empty", "reply":
                "I couldn't find anything in the catalogue for that yet — try "
                "another topic or genre and I'll look again. (The catalogue is "
                "real Open Library records, so not everything is available.)",
                "books": [], "library": None}
    groq, groq_err = _groq_chat(cands, interests, msg, history)
    if groq and groq["recs"]:
        by_id = {str(b["_id"]): b for b in cands}
        return {"engine": "groq", "reply": groq["message"] or
                "Here are some picks from the catalogue:",
                "books": [_book_card(by_id[r["id"]]) for r in groq["recs"]
                          if r["id"] in by_id],   # re-validate: never trust model ids
                "library": None}
    # deterministic fallback — clearly labelled with the REAL cause, never smart-AI
    reason = groq_err or "no_candidates"
    explain = _GROQ_REASONS.get(reason, "The AI service is unavailable.")
    ranked = _keyword_rank(cands, interests, limit=4)
    by_id = {str(b["_id"]): b for b in cands}
    return {"engine": "keyword", "fallback_reason": reason,
            "reply": f"({explain}) Genre-matched picks from the real catalogue:",
            "books": [{**_book_card(by_id[r["id"]]), "reason": r["reason"]}
                      for r in ranked if r["id"] in by_id],
            "library": None}


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8001)
